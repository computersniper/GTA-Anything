from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from gta_anything.cli import cli
from gta_anything.diagnose.log_correlator import diagnose_logs

REPO_ROOT = Path(__file__).resolve().parents[1]
METRO_IR_PATH = REPO_ROOT / "examples" / "metro_shuttle_loop" / "gameplay_ir.json"
METRO_SPEC_PATH = REPO_ROOT / "examples" / "metro_shuttle_loop" / "spec.md"


def test_diagnose_logs_correlates_shv_shvdn_jsonl_and_low_commit(tmp_path: Path):
    shv_log = tmp_path / "ScriptHookV.log"
    shv_log.write_text(
        "// GTA V SCRIPT HOOK (build Mar 2026)\n"
        "[03:10:01] Init: Detected game version VER_EN_1_0_1158_13\n"
        "[03:10:02] Starting ASI plugins...\n",
        encoding="utf-8",
    )

    shvdn_log = tmp_path / "ScriptHookVDotNet.log"
    shvdn_log.write_text(
        "[03:10:05] [INFO] Loading scripts from scripts folder...\n"
        "[03:10:06] [INFO] Instantiating script MetroShuttleLoopMod...\n"
        "[03:10:15] [WARN] Model stream timeout after 5000ms for addon coach; releasing request.\n"
        "[03:10:20] [ERROR] Caught unhandled exception: System.NullReferenceException: Object reference not set to an instance of an object.\n"
        "   at MetroShuttleLoopMod.OnIndexChange() in CreateVehicle / RemoveAllExtras\n",
        encoding="utf-8",
    )

    telemetry_jsonl = tmp_path / "metro_shuttle_loop_telemetry.jsonl"
    telemetry_events = [
        {"timestampUtc": "2026-11-26T03:10:03Z", "modId": "metro_shuttle_loop", "layer": 1, "phase": "ConfigLoaded", "event": "ConfigValidated"},
        {"timestampUtc": "2026-11-26T03:10:05Z", "modId": "metro_shuttle_loop", "layer": 2, "phase": "LoaderReady", "event": "ShvdnAttached"},
        {"timestampUtc": "2026-11-26T03:10:06Z", "modId": "metro_shuttle_loop", "layer": 3, "phase": "Idle", "event": "ScriptInitialized"},
        {"timestampUtc": "2026-11-26T03:10:12Z", "modId": "metro_shuttle_loop", "layer": 4, "phase": "MenuSelecting", "event": "MenuOpened"},
    ]
    telemetry_jsonl.write_text(
        "\n".join(json.dumps(ev) for ev in telemetry_events) + "\n",
        encoding="utf-8",
    )

    report = diagnose_logs(
        log_paths=[shv_log, shvdn_log, telemetry_jsonl],
        commit_available_mb=823.0,
    )

    assert isinstance(report, dict)
    assert report["detected_build_alias"] == "VER_EN_1_0_1158_13"
    assert report["highest_acceptance_layer_reached"] in (4, 5)
    assert len(report["timeline"]) >= 4
    assert len(report["issues"]) >= 2

    categories = {issue.get("category") for issue in report["issues"]}
    assert "environment" in categories, f"Expected 'environment' issue for 823 MB commit memory: {report['issues']}"
    assert "script_logic" in categories, f"Expected 'script_logic' issue for NullReferenceException: {report['issues']}"
    assert len(report["recommendations"]) >= 1


def test_cli_json_subcommands_e2e(tmp_path: Path):
    runner = CliRunner()

    # 1. preflight --json
    res_preflight = runner.invoke(cli, ["--json", "preflight", "--hotkey", "F9"])
    assert res_preflight.exit_code == 0, f"preflight failed: {res_preflight.output}"
    pf_data = json.loads(res_preflight.output)
    assert "system" in pf_data and "hotkey_check" in pf_data

    # 2. validate-ir --json
    assert METRO_IR_PATH.exists(), f"Missing {METRO_IR_PATH}"
    res_val = runner.invoke(cli, ["--json", "validate-ir", str(METRO_IR_PATH)])
    assert res_val.exit_code == 0, f"validate-ir failed: {res_val.output}"
    val_data = json.loads(res_val.output)
    assert val_data.get("valid") is True

    # 3. pipeline --json (Extract -> Validate -> Transpile -> Asset-Check)
    pipeline_out = tmp_path / "pipeline_out"
    res_pipe = runner.invoke(
        cli,
        ["--json", "pipeline", str(METRO_SPEC_PATH), "-o", str(pipeline_out), "--edition", "enhanced_gen9"],
    )
    assert res_pipe.exit_code == 0, f"pipeline failed: {res_pipe.output}"
    pipe_data = json.loads(res_pipe.output)
    assert pipe_data.get("ok") is True

    # 4. asset-check --json
    asset_dir = tmp_path / "cli_assets"
    asset_dir.mkdir()
    (asset_dir / "dlclist.xml").write_text(
        "<SMandatoryPacksData><Paths><Item>dlcpacks:/metro_shuttle/</Item></Paths></SMandatoryPacksData>",
        encoding="utf-8",
    )
    res_asset = runner.invoke(
        cli,
        ["--json", "asset-check", str(asset_dir), "--edition", "enhanced_gen9"],
    )
    assert res_asset.exit_code == 0, f"asset-check failed: {res_asset.output}"
    asset_data = json.loads(res_asset.output)
    assert asset_data.get("ok") is True

    # 5. diagnose --json
    diag_log = tmp_path / "ScriptHookV.log"
    diag_log.write_text("Init: Detected game version VER_EN_1_0_1158_13\n", encoding="utf-8")
    res_diag = runner.invoke(
        cli,
        ["--json", "diagnose", str(diag_log), "--commit-mb", "823.0"],
    )
    assert res_diag.exit_code == 0, f"diagnose failed: {res_diag.output}"
    diag_data = json.loads(res_diag.output)
    assert diag_data.get("detected_build_alias") == "VER_EN_1_0_1158_13"


def test_repository_clean_room_hygiene():
    """Verify the entire repository contains zero personal paths and zero proprietary binary files."""
    forbidden_binary_exts = {".dll", ".asi", ".rpf", ".yft", ".ytd"}
    # Build forbidden personal path tokens dynamically so this test file itself stays 100% clean-room!
    token_user = "".join(["cai", "jie", "chao"])
    token_codex = "".join(["Codex", "\\", "2026"])
    token_game_drive = "".join(["G:", "\\", "Games", "\\", "GTAV"])
    token_workspace = "".join(["vibe", "-", "coding"])
    token_host_study = "".join(["D:", "\\", "study"])
    token_users_dir = "".join(["C:", "\\", "Users"])
    forbidden_strings = [
        token_user,
        token_codex,
        token_game_drive,
        token_workspace,
        token_host_study,
        token_users_dir,
    ]

    skip_dirs = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "build", "dist", "bin", "obj"}
    skip_files = {"交接说明.txt"}

    binary_violations: list[str] = []
    text_violations: list[str] = []

    for path in REPO_ROOT.rglob("*"):
        if any(part in skip_dirs or part.endswith(".egg-info") for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.name in skip_files:
            continue

        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.suffix.lower() in forbidden_binary_exts:
            binary_violations.append(rel)
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for bad in forbidden_strings:
            if bad.lower() in content.lower():
                text_violations.append(f"{rel} (contains forbidden token)")

    assert binary_violations == [], f"Found forbidden binary files in repo: {binary_violations}"
    assert text_violations == [], f"Found forbidden personal machine paths in repo: {text_violations}"
