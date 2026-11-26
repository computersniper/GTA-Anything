from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from click.testing import CliRunner

from gta_anything.assets.auditor import audit_assets
from gta_anything.assets.fixer import build_synthetic_dxt1_dds, fix_assets
from gta_anything.cli import cli
from gta_anything.compiler.dotnet_builder import compile_csharp_mod
from gta_anything.extractor.analyzer import extract_gameplay_ir
from gta_anything.models.ir import validate_gameplay_ir
from gta_anything.simulator.world_sim import simulate_gameplay_ir
from gta_anything.transpiler.csharp_codegen import generate_csharp_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
PIZZA_RUSH_DIR = EXAMPLES_DIR / "external_pizza_rush_src"
METRO_IR_PATH = EXAMPLES_DIR / "metro_shuttle_loop" / "gameplay_ir.json"


def test_polyglot_ast_extracts_pizza_rush_and_simulates_l7(tmp_path: Path):
    assert PIZZA_RUSH_DIR.is_dir(), f"Missing {PIZZA_RUSH_DIR}"

    ir = extract_gameplay_ir(PIZZA_RUSH_DIR, target_edition="enhanced_gen9")
    report = validate_gameplay_ir(ir)
    assert report.valid is True, f"Pizza Rush IR invalid: {report.errors}"

    # Verify scooter fallback ('faggio') and NPC fallback
    fallbacks = {e.vanilla_fallback_model for e in ir.entities}
    assert "faggio" in fallbacks, f"Expected 'faggio' scooter fallback in {fallbacks}"

    # Verify 2D grid coordinates (0..100) were projected to real Los Santos street coordinates
    assert len(ir.routes_or_zones) >= 1
    stops = ir.routes_or_zones[0].stops
    assert len(stops) >= 5
    for stop in stops:
        assert -3500.0 <= stop.x <= 4000.0
        assert -3500.0 <= stop.y <= 4000.0
        assert abs(stop.z) > 0.5, f"Expected realistic non-zero road elevation Z, got {stop.z}"
        # Ensure coordinates are no longer raw 0..100 2D canvas values
        assert abs(stop.x) > 100.0 or abs(stop.y) > 100.0

    # Verify line-level EvidenceAnchors exist
    assert len(ir.evidence) >= 5
    assert any(
        ev.source_file.endswith(".py") and ("L" in ev.locator or ev.locator.isdigit())
        for ev in ir.evidence
    ), f"Expected line-level Python EvidenceAnchors, got {ir.evidence[:3]}"

    # Full L1-L7 headless simulation pass
    tel_path = tmp_path / "pizza_rush_sim.jsonl"
    sim_res = simulate_gameplay_ir(ir, telemetry_out=tel_path)
    assert sim_res["ok"] is True
    assert sim_res["highest_acceptance_layer_reached"] == 7
    assert sim_res["active_leases_after_teardown"] == 0
    assert sim_res["stops_completed"] == len(stops)
    assert tel_path.exists()


def test_asset_fixer_reencodes_dxt1_script_rt_and_repairs_dlclist(tmp_path: Path):
    src_dir = tmp_path / "broken_gen9_assets"
    src_dir.mkdir()

    dds_path = src_dir / "script_rt_dials_race.dds"
    dds_bytes = build_synthetic_dxt1_dds(width=8, height=8, mip_count=3)
    dds_path.write_bytes(dds_bytes)

    # Confirm broken asset fails enhanced_gen9 audit before fixing
    pre_audit = audit_assets(src_dir, target_edition="enhanced_gen9")
    assert pre_audit["ok"] is False

    # Broken dlclist.xml with backslashes, missing trailing slash, duplicates, empty item
    dlclist_path = src_dir / "dlclist.xml"
    dlclist_path.write_text(
        "<SMandatoryPacksData><Paths>"
        "<Item>dlcpacks:\\pizza_scooter</Item>"
        "<Item>dlcpacks:/pizza_scooter/</Item>"
        "<Item></Item>"
        "</Paths></SMandatoryPacksData>",
        encoding="utf-8",
    )

    # 1. Dry-run must not mutate or create output files
    out_dir = tmp_path / "fixed_gen9_assets"
    dry_res = fix_assets(src_dir, output_dir=out_dir, target_edition="enhanced_gen9", dry_run=True)
    assert dry_res["ok"] is True
    assert dry_res["dry_run"] is True
    assert dry_res["repaired_count"] >= 2
    assert not out_dir.exists()

    # 2. Real fix into output_dir
    fix_res = fix_assets(src_dir, output_dir=out_dir, target_edition="enhanced_gen9", dry_run=False)
    assert fix_res["ok"] is True
    assert fix_res["dry_run"] is False
    assert fix_res["repaired_count"] >= 2

    fixed_dds = out_dir / "script_rt_dials_race.dds"
    assert fixed_dds.exists()
    raw = fixed_dds.read_bytes()
    assert raw[:4] == b"DDS "
    assert len(raw) >= 128 + (8 * 8 * 4)

    # Check DDS_HEADER mipMapCount at byte offset 28 == 1
    mip_count = struct.unpack_from("<I", raw, 28)[0]
    assert mip_count == 1

    # Check DDS_PIXELFORMAT at byte offset 76: dwSize=32, dwFlags=0x41 (ALPHAPIXELS|RGB),
    # dwFourCC=0, dwRGBBitCount=32, B8G8R8A8 masks
    pf_size, pf_flags, pf_fourcc, pf_bpp, r_mask, g_mask, b_mask, a_mask = struct.unpack_from(
        "<IIIIIIII", raw, 76
    )
    assert pf_size == 32
    assert pf_flags == 0x41
    assert pf_fourcc == 0
    assert pf_bpp == 32
    assert (r_mask, g_mask, b_mask, a_mask) == (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)

    # Check repaired dlclist.xml
    fixed_dlc = (out_dir / "dlclist.xml").read_text(encoding="utf-8")
    assert fixed_dlc.count("dlcpacks:/pizza_scooter/") == 1

    # Roundtrip audit on fixed directory must pass with 0 errors
    post_audit = audit_assets(out_dir, target_edition="enhanced_gen9")
    assert post_audit["ok"] is True, f"Post-fix audit failed: {post_audit['findings']}"
    errors = [f for f in post_audit["findings"] if f.get("severity") == "ERROR"]
    assert errors == []


@pytest.mark.parametrize(
    "source_kind,source_path,expected_mod_class",
    [
        ("ir_json", METRO_IR_PATH, "MetroShuttleLoop"),
        ("polyglot_py", PIZZA_RUSH_DIR, "ExternalPizzaRushSrc"),
    ],
)
def test_offline_standalone_dll_compilation(
    tmp_path: Path,
    source_kind: str,
    source_path: Path,
    expected_mod_class: str,
):
    ir = extract_gameplay_ir(source_path, target_edition="enhanced_gen9")
    assert validate_gameplay_ir(ir).valid is True

    mod_dir = tmp_path / f"mod_{source_kind}"
    transpile_res = generate_csharp_mod(ir, mod_dir)
    assert transpile_res["ok"] is True

    bin_dir = tmp_path / f"bin_{source_kind}"
    comp_res = compile_csharp_mod(
        mod_dir=mod_dir,
        game_dir=None,
        output_dir=bin_dir,
        edition="enhanced_gen9",
    )

    assert comp_res["ok"] is True, f"Compilation failed: {comp_res['errors']}"
    assert comp_res["live_host_linked"] is False
    assert comp_res["mod_class_name"] == expected_mod_class

    runtime_dll = bin_dir / "GtaAnything.Runtime.dll"
    mod_dll = bin_dir / f"{expected_mod_class}.dll"
    assert runtime_dll.is_file() and runtime_dll.stat().st_size > 0
    assert mod_dll.is_file() and mod_dll.stat().st_size > 0
    assert runtime_dll.read_bytes()[:2] == b"MZ"
    assert mod_dll.read_bytes()[:2] == b"MZ"


def test_cli_v030_json_subcommands_e2e(tmp_path: Path):
    runner = CliRunner()

    # 1. asset-fix --json
    bad_assets = tmp_path / "cli_bad_assets"
    bad_assets.mkdir()
    (bad_assets / "script_rt_dials_race.dds").write_bytes(
        build_synthetic_dxt1_dds(width=4, height=4, mip_count=2)
    )
    fixed_assets = tmp_path / "cli_fixed_assets"
    res_fix = runner.invoke(
        cli,
        [
            "--json",
            "asset-fix",
            str(bad_assets),
            "-o",
            str(fixed_assets),
            "--edition",
            "enhanced_gen9",
        ],
    )
    assert res_fix.exit_code == 0, f"asset-fix failed: {res_fix.output}"
    fix_data = json.loads(res_fix.output)
    assert fix_data["ok"] is True
    assert fix_data["repaired_count"] >= 1
    assert (fixed_assets / "script_rt_dials_race.dds").is_file()

    # 2. pipeline --compile --json on external_pizza_rush_src
    pipe_dir = tmp_path / "cli_pizza_pipeline"
    res_pipe = runner.invoke(
        cli,
        [
            "--json",
            "pipeline",
            str(PIZZA_RUSH_DIR),
            "-o",
            str(pipe_dir),
            "--edition",
            "enhanced_gen9",
            "--compile",
        ],
    )
    assert res_pipe.exit_code == 0, f"pipeline --compile failed: {res_pipe.output}"
    pipe_data = json.loads(res_pipe.output)
    assert pipe_data["ok"] is True
    assert "compile" in pipe_data
    assert pipe_data["compile"]["ok"] is True
    assert (pipe_dir / "bin" / "GtaAnything.Runtime.dll").read_bytes()[:2] == b"MZ"
    assert (pipe_dir / "bin" / "ExternalPizzaRushSrc.dll").read_bytes()[:2] == b"MZ"

    # 3. build-dll --json standalone on transpiled output
    standalone_bin = tmp_path / "cli_standalone_bin"
    res_build = runner.invoke(
        cli,
        [
            "--json",
            "build-dll",
            str(pipe_dir),
            "-o",
            str(standalone_bin),
            "--edition",
            "enhanced_gen9",
        ],
    )
    assert res_build.exit_code == 0, f"build-dll failed: {res_build.output}"
    build_data = json.loads(res_build.output)
    assert build_data["ok"] is True
    assert (standalone_bin / "GtaAnything.Runtime.dll").read_bytes()[:2] == b"MZ"
    assert (standalone_bin / "ExternalPizzaRushSrc.dll").read_bytes()[:2] == b"MZ"
