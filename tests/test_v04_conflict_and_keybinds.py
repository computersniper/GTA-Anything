from __future__ import annotations

import json
from collections import namedtuple
from pathlib import Path

from click.testing import CliRunner

from gta_anything.cli import cli
from gta_anything.conflict import (
    analyze_mod_conflicts,
    evaluate_keybind_conflicts,
    normalize_chord,
    normalize_key_name,
    recommend_safe_chords,
    scan_installed_keybinds,
)
from gta_anything.models.ir import GameplayIR

REPO_ROOT = Path(__file__).resolve().parents[1]
METRO_IR_PATH = REPO_ROOT / "examples" / "metro_shuttle_loop" / "gameplay_ir.json"
METRO_SPEC_PATH = REPO_ROOT / "examples" / "metro_shuttle_loop" / "spec.md"


def _build_realistic_lspdfr_mock_dir(root: Path) -> Path:
    """Create a realistic synthetic multi-mod GTA V directory in tmp_path."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "GTA5_Enhanced.exe").write_bytes(b"MZ" + b"\x00" * 64)
    (root / "ScriptHookV.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (root / "RAGEPluginHook.exe").write_bytes(b"MZ" + b"\x00" * 32)

    (root / "RagePluginHook.ini").write_text(
        "[Miscellaneous]\nConsoleKey=F4\nPluginTimeoutThreshold=10000\n",
        encoding="utf-8",
    )
    (root / "ScriptHookVDotNet.ini").write_text(
        "[Settings]\nReloadKey=Insert\n",
        encoding="utf-8",
    )

    policing_dir = root / "plugins" / "LSPDFR"
    policing_dir.mkdir(parents=True, exist_ok=True)
    (policing_dir / "PolicingRedefined.ini").write_text(
        "[Keybinds]\n"
        "MenuKey=F9\n"
        "ModifierKey=LeftShift\n"
        "BackupKey=B\n"
        "[HexBindings]\n"
        "SecondaryKey=0x78\n",
        encoding="utf-8",
    )

    profiles_dir = root / "GTA5-Profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / "ActiveMode.txt").write_text("LSPDFR\n", encoding="utf-8")

    bus_profile = profiles_dir / "Inactive" / "Bus"
    bus_profile.mkdir(parents=True, exist_ok=True)
    (bus_profile / "ScriptHookVDotNet3.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (bus_profile / "scripts").mkdir(parents=True, exist_ok=True)
    (bus_profile / "scripts" / "BusAddon.ini").write_text(
        "[Controls]\nToggleKey=F10\n",
        encoding="utf-8",
    )

    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "LemonUI.SHVDN2.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (scripts_dir / "LemonUI.SHVDN3.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (scripts_dir / "ExistingTransitRoute.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<Route>\n"
        '  <Stop name="DashoundOverlap" x="436.2" y="-645.8" z="28.7" />\n'
        "</Route>\n",
        encoding="utf-8",
    )
    return root


def _build_clean_shvdn_mock_dir(root: Path) -> Path:
    """Create a clean SHVDN-only GTA V directory with no conflicting chords or coords."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "GTA5_Enhanced.exe").write_bytes(b"MZ" + b"\x00" * 64)
    (root / "ScriptHookV.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (root / "ScriptHookVDotNet.asi").write_bytes(b"MZ" + b"\x00" * 32)

    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "ScriptHookVDotNet3.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (scripts_dir / "LemonUI.SHVDN3.dll").write_bytes(b"MZ" + b"\x00" * 32)
    (scripts_dir / "FarAwayRoute.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<Route>\n"
        '  <Stop name="PaletoBay" x="-150.0" y="6300.0" z="31.5" />\n'
        "</Route>\n",
        encoding="utf-8",
    )
    return root


def test_scan_installed_keybinds_parses_ini_vk_hex_profiles_and_relative_paths(tmp_path: Path):
    game_dir = _build_realistic_lspdfr_mock_dir(tmp_path / "gtav_mock")

    assert normalize_key_name("0x78") == "F9"
    assert normalize_key_name("0x2D") == "Insert"
    assert normalize_key_name("LShiftKey") == "Shift"
    assert normalize_chord("0x78", "LeftShift") == "Shift+F9"

    registry = scan_installed_keybinds(game_dir, include_inactive_profiles=True)
    assert registry["ok"] is True
    assert registry["active_profile_mode"] == "LSPDFR"
    assert "active" in registry["profiles_scanned"]
    assert "inactive:Bus" in registry["profiles_scanned"]

    bindings = registry["bindings"]
    assert len(bindings) >= 5

    # Ensure zero absolute host paths leak in relative_path or scanned_files
    abs_prefix = str(game_dir).replace("\\", "/")
    for rel in registry["scanned_files"]:
        assert not Path(rel).is_absolute()
        assert abs_prefix not in rel
    for b in bindings:
        assert not Path(b["relative_path"]).is_absolute()
        assert abs_prefix not in b["relative_path"]

    chords_by_setting = {(b["profile"], b["setting_name"]): b["canonical_chord"] for b in bindings}
    assert chords_by_setting[("active", "ConsoleKey")] == "F4"
    assert chords_by_setting[("active", "ReloadKey")] == "Insert"
    assert chords_by_setting[("active", "MenuKey")] == "Shift+F9"
    assert chords_by_setting[("active", "SecondaryKey")] == "F9"
    assert chords_by_setting[("active", "BackupKey")] == "B"
    assert chords_by_setting[("inactive:Bus", "ToggleKey")] == "F10"


def test_evaluate_keybind_conflicts_and_recommend_safe_chords(tmp_path: Path):
    game_dir = _build_realistic_lspdfr_mock_dir(tmp_path / "gtav_mock")
    registry = scan_installed_keybinds(game_dir, include_inactive_profiles=True)

    # Shift+F9 collides with PolicingRedefined.ini -> BLOCKING
    eval_shift_f9 = evaluate_keybind_conflicts(
        activation_key="F9",
        modifier_key="LeftShift",
        scanned_registry=registry,
        loader_target="shvdn_enhanced",
    )
    assert eval_shift_f9["has_conflicts"] is True
    assert eval_shift_f9["blocking_count"] >= 1
    assert any(
        c["severity"] == "BLOCKING" and "PolicingRedefined.ini" in str(c.get("relative_path", ""))
        for c in eval_shift_f9["conflicts"]
    )

    # B is classified as on_duty_police
    eval_b = evaluate_keybind_conflicts(
        activation_key="B",
        modifier_key=None,
        scanned_registry=registry,
        loader_target="shvdn_enhanced",
    )
    assert eval_b["has_conflicts"] is True
    assert any(c.get("context_scope") == "on_duty_police" for c in eval_b["conflicts"])

    # Recommend 5 guaranteed conflict-free chords
    safe_chords = recommend_safe_chords(scanned_registry=registry, count=5)
    assert len(safe_chords) == 5
    for candidate in safe_chords:
        assert candidate["canonical_chord"] != "Shift+F9"
        check = evaluate_keybind_conflicts(
            activation_key=candidate["activation_key"],
            modifier_key=candidate.get("modifier_key"),
            scanned_registry=registry,
        )
        assert check["blocking_count"] == 0, f"Recommended chord {candidate} had blocking conflict: {check}"


def test_analyze_mod_conflicts_isolate_vs_safe_to_merge(tmp_path: Path, monkeypatch):
    # Ensure tmp_path drive free-space check is deterministic regardless of host C: free space
    _Usage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda _p: _Usage(total=500 * 1024**3, used=400 * 1024**3, free=100 * 1024**3),
    )

    metro_ir = GameplayIR.from_json(METRO_IR_PATH.read_text(encoding="utf-8"))

    # 1. Realistic LSPDFR + LemonUI dual-DLL + <15m spatial overlap -> ISOLATE_NEW_PROFILE
    dirty_dir = _build_realistic_lspdfr_mock_dir(tmp_path / "dirty_gtav")
    dirty_report = analyze_mod_conflicts(metro_ir, game_dir=dirty_dir)
    assert dirty_report["deployment_verdict"] == "ISOLATE_NEW_PROFILE"
    assert dirty_report["has_blocking_conflicts"] is True

    spatial_conflicts = dirty_report["dimensions"]["spatial_turf"]["overlaps"]
    assert any(ov.get("code") == "SPATIAL_SPAWN_OVERLAP" and ov.get("distance_m", 99) < 15.0 for ov in spatial_conflicts)

    abi_conflicts = dirty_report["dimensions"]["assemblies_abi"]["conflicts"]
    abi_codes = {c.get("code") for c in abi_conflicts}
    assert "DUPLICATE_UI_LIBRARY_ABI" in abi_codes
    assert "LOADER_CHAIN_MISMATCH" in abi_codes

    # 2. Clean SHVDN directory with non-overlapping coords & free hotkey -> SAFE_TO_MERGE
    clean_dir = _build_clean_shvdn_mock_dir(tmp_path / "clean_gtav")
    clean_ir = GameplayIR.from_json(METRO_IR_PATH.read_text(encoding="utf-8"))
    clean_ir.inputs.activation_key = "F11"
    clean_ir.inputs.modifier_key = "LeftShift"

    clean_report = analyze_mod_conflicts(clean_ir, game_dir=clean_dir)
    assert clean_report["deployment_verdict"] == "SAFE_TO_MERGE"
    assert clean_report["has_blocking_conflicts"] is False
    assert clean_report["dimensions"]["spatial_turf"]["overlap_count"] == 0


def test_cli_json_host_scan_conflict_check_auto_rebind_and_pipeline(tmp_path: Path, monkeypatch):
    _Usage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda _p: _Usage(total=500 * 1024**3, used=400 * 1024**3, free=100 * 1024**3),
    )

    dirty_dir = _build_realistic_lspdfr_mock_dir(tmp_path / "cli_dirty_gtav")
    clean_dir = _build_clean_shvdn_mock_dir(tmp_path / "cli_clean_gtav")
    runner = CliRunner()

    # 1. host-scan --json
    res_scan = runner.invoke(
        cli,
        ["--json", "host-scan", "--game-dir", str(dirty_dir)],
    )
    assert res_scan.exit_code == 0, f"host-scan failed: {res_scan.output}"
    scan_data = json.loads(res_scan.output)
    assert scan_data["active_profile_mode"] == "LSPDFR"
    assert len(scan_data["recommended_safe_chords"]) == 5
    assert str(dirty_dir).replace("\\", "/") not in res_scan.output

    # 2. conflict-check --auto-rebind -o <rebound_ir.json>
    # metro_shuttle_loop uses Shift+F9 which collides with PolicingRedefined.ini in dirty_dir
    rebound_ir_path = tmp_path / "rebound_metro_ir.json"
    res_cc = runner.invoke(
        cli,
        [
            "--json",
            "conflict-check",
            str(METRO_IR_PATH),
            "--game-dir",
            str(dirty_dir),
            "--auto-rebind",
            "-o",
            str(rebound_ir_path),
        ],
    )
    assert res_cc.exit_code == 0, f"conflict-check failed: {res_cc.output}"
    cc_data = json.loads(res_cc.output)
    assert cc_data["auto_rebound"] is True
    assert cc_data["dimensions"]["keybinds"]["blocking_count"] == 0
    assert rebound_ir_path.exists()

    rebound_ir = GameplayIR.from_json(rebound_ir_path.read_text(encoding="utf-8"))
    assert normalize_chord(rebound_ir.inputs.activation_key, rebound_ir.inputs.modifier_key) != "Shift+F9"

    # 3. pipeline --auto-rebind against a directory where F9 is occupied
    (clean_dir / "scripts" / "OccupiedMenu.ini").write_text(
        "[Menu]\nMenuKey=F9\nModifierKey=LeftShift\n",
        encoding="utf-8",
    )
    pipe_out = tmp_path / "pipe_rebound_out"
    res_pipe = runner.invoke(
        cli,
        [
            "--json",
            "pipeline",
            str(METRO_SPEC_PATH),
            "-o",
            str(pipe_out),
            "--edition",
            "enhanced_gen9",
            "--game-dir",
            str(clean_dir),
            "--auto-rebind",
        ],
    )
    assert res_pipe.exit_code == 0, f"pipeline --auto-rebind failed: {res_pipe.output}"
    pipe_data = json.loads(res_pipe.output)
    assert pipe_data["ok"] is True
    assert "conflict_check" in pipe_data
    assert pipe_data["conflict_check"]["auto_rebound"] is True
    assert pipe_data["conflict_check"]["dimensions"]["keybinds"]["blocking_count"] == 0
