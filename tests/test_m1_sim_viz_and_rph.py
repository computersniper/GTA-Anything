from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner

from gta_anything.cli import cli
from gta_anything.diagnose.log_correlator import diagnose_logs
from gta_anything.models.ir import GameplayIR, validate_gameplay_ir
from gta_anything.simulator.world_sim import simulate_gameplay_ir
from gta_anything.transpiler.csharp_codegen import generate_csharp_mod
from gta_anything.transpiler.world_mapper import list_world_catalog
from gta_anything.visualizer.radar_html import render_ir_dashboard

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
METRO_IR_PATH = EXAMPLES_DIR / "metro_shuttle_loop" / "gameplay_ir.json"
HARBOR_IR_PATH = EXAMPLES_DIR / "harbor_courier_dispatch" / "gameplay_ir.json"
VINEWOOD_IR_PATH = EXAMPLES_DIR / "vinewood_patrol_rph" / "gameplay_ir.json"


@pytest.mark.parametrize(
    "example_name",
    ["metro_shuttle_loop", "harbor_courier_dispatch", "vinewood_patrol_rph"],
)
def test_simulator_full_run_and_diagnose_l7(tmp_path: Path, example_name: str):
    ir_path = EXAMPLES_DIR / example_name / "gameplay_ir.json"
    ir = GameplayIR.from_json(ir_path.read_text(encoding="utf-8"))
    report = validate_gameplay_ir(ir)
    assert report.valid is True, f"{example_name} IR invalid: {report.errors}"

    telemetry_path = tmp_path / f"{example_name}_telemetry.jsonl"
    sim_res = simulate_gameplay_ir(ir, telemetry_out=telemetry_path)

    assert sim_res["ok"] is True
    assert sim_res["mod_id"] == example_name
    assert sim_res["aborted_intentionally"] is False
    assert sim_res["spawned_during_menu_scroll"] == 0
    assert sim_res["highest_acceptance_layer_reached"] == 7
    assert sim_res["active_leases_after_teardown"] == 0
    assert sim_res["stops_completed"] == sim_res["total_stops"] > 0
    assert sim_res["total_distance_m"] > 0
    assert sim_res["total_reward"] > 0
    assert "Teardown" in sim_res["state_trace"]
    assert telemetry_path.exists()

    diag = diagnose_logs([telemetry_path])
    assert diag["highest_acceptance_layer_reached"] == 7


def test_simulator_fault_injection_addon_timeout(tmp_path: Path):
    ir = GameplayIR.from_json(VINEWOOD_IR_PATH.read_text(encoding="utf-8"))
    # Give the primary entity an add-on model so timeout + vanilla fallback triggers
    ir.entities[0].preferred_addon_model = "addon_vinewood_cruiser"

    telemetry_path = tmp_path / "timeout_telemetry.jsonl"
    sim_res = simulate_gameplay_ir(
        ir,
        inject_addon_timeout=True,
        telemetry_out=telemetry_path,
    )

    assert sim_res["ok"] is True
    assert sim_res["used_vanilla_fallback"] is True
    assert sim_res["released_timed_out_models"] >= 1
    assert sim_res["highest_acceptance_layer_reached"] == 7
    assert sim_res["active_leases_after_teardown"] == 0


def test_simulator_fault_injection_abort_at_stop(tmp_path: Path):
    ir = GameplayIR.from_json(METRO_IR_PATH.read_text(encoding="utf-8"))
    telemetry_path = tmp_path / "abort_telemetry.jsonl"
    sim_res = simulate_gameplay_ir(
        ir,
        inject_abort_at_stop=1,
        telemetry_out=telemetry_path,
    )

    assert sim_res["aborted_intentionally"] is True
    assert sim_res["stops_completed"] <= 2
    assert sim_res["active_leases_after_teardown"] == 0
    assert "Teardown" in sim_res["state_trace"]


def test_visualizer_renders_standalone_radar_html(tmp_path: Path):
    ir = GameplayIR.from_json(VINEWOOD_IR_PATH.read_text(encoding="utf-8"))
    out_html = tmp_path / "vinewood_radar.html"

    viz_res = render_ir_dashboard(ir, out_html)
    assert viz_res["ok"] is True
    assert viz_res["mod_id"] == "vinewood_patrol_rph"
    assert viz_res["track_count"] == 1
    assert viz_res["state_count"] == len(ir.state_machine.states)
    assert out_html.exists()

    html_text = out_html.read_text(encoding="utf-8")
    assert "<svg" in html_text.lower()
    assert "Vinewood Hills Observatory Overlook" in html_text
    assert "ActivePatrol" in html_text
    assert "Teardown" in html_text
    assert "police3" in html_text
    assert "s_m_y_ranger_01" in html_text
    # Ensure zero personal machine paths
    token_user = "".join(["cai", "jie", "chao"])
    assert token_user not in html_text.lower()


def test_rph_transpilation_and_static_2d_svg_cards(tmp_path: Path):
    ir = GameplayIR.from_json(VINEWOOD_IR_PATH.read_text(encoding="utf-8"))
    out_dir = tmp_path / "VinewoodPatrolRphMod"
    res = generate_csharp_mod(ir, out_dir)

    assert res["ok"] is True
    assert res["mod_id"] == "vinewood_patrol_rph"

    csproj_files = list(out_dir.glob("*.csproj"))
    assert len(csproj_files) == 1
    csproj_text = csproj_files[0].read_text(encoding="utf-8")
    assert "USE_RPH" in csproj_text

    assert (out_dir / "ModEntrypoint.cs").exists()
    rph_bridge = out_dir / "RphPluginBridge.cs"
    assert rph_bridge.exists(), "Expected RphPluginBridge.cs for loader_target == 'rph'"
    rph_text = rph_bridge.read_text(encoding="utf-8")
    assert "USE_RPH" in rph_text
    assert "OnUnload" in rph_text

    card_files = list((out_dir / "cards").glob("*_card.svg"))
    assert len(card_files) >= 1
    for card_path in card_files:
        root = ET.fromstring(card_path.read_text(encoding="utf-8"))
        assert root.tag.endswith("svg")


def test_world_catalog_expanded_and_filterable():
    full = list_world_catalog()
    assert full["ok"] is True
    assert len(full["vehicles"]) >= 8
    assert len(full["peds"]) >= 4
    assert len(full["blips"]) >= 3

    emergency = list_world_catalog(category="emergency")
    assert emergency["ok"] is True
    assert "police3" in emergency["vehicles"] or "police" in emergency["vehicles"]


def test_cli_v020_json_subcommands_e2e(tmp_path: Path):
    runner = CliRunner()

    # 1. simulate --json
    sim_tel = tmp_path / "cli_sim.jsonl"
    res_sim = runner.invoke(
        cli,
        [
            "--json",
            "simulate",
            str(VINEWOOD_IR_PATH),
            "--telemetry-out",
            str(sim_tel),
        ],
    )
    assert res_sim.exit_code == 0, f"simulate failed: {res_sim.output}"
    sim_data = json.loads(res_sim.output)
    assert sim_data["highest_acceptance_layer_reached"] == 7
    assert sim_data["active_leases_after_teardown"] == 0
    assert sim_tel.exists()

    # 2. visualize --json
    viz_html = tmp_path / "cli_radar.html"
    res_viz = runner.invoke(
        cli,
        ["--json", "visualize", str(VINEWOOD_IR_PATH), "-o", str(viz_html)],
    )
    assert res_viz.exit_code == 0, f"visualize failed: {res_viz.output}"
    viz_data = json.loads(res_viz.output)
    assert viz_data["ok"] is True
    assert viz_html.exists()

    # 3. catalog --json
    res_cat = runner.invoke(cli, ["--json", "catalog", "--category", "emergency"])
    assert res_cat.exit_code == 0, f"catalog failed: {res_cat.output}"
    cat_data = json.loads(res_cat.output)
    assert cat_data["ok"] is True

    # 4. enhanced pipeline --json (includes simulation & visualization)
    pipe_dir = tmp_path / "vinewood_pipeline"
    res_pipe = runner.invoke(
        cli,
        [
            "--json",
            "pipeline",
            str(VINEWOOD_IR_PATH),
            "-o",
            str(pipe_dir),
            "--edition",
            "enhanced_gen9",
        ],
    )
    assert res_pipe.exit_code == 0, f"pipeline failed: {res_pipe.output}"
    pipe_data = json.loads(res_pipe.output)
    assert pipe_data["ok"] is True
    for key in ("extract", "validation", "transpile", "asset_check", "simulation", "visualization"):
        assert key in pipe_data, f"Missing pipeline key: {key}"
    assert (pipe_dir / "simulation_telemetry.jsonl").exists()
    assert (pipe_dir / "radar_blueprint.html").exists()
