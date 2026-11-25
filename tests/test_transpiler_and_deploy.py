from __future__ import annotations

import json
from pathlib import Path

import pytest

from gta_anything.deploy.profile_manager import ProfileManager
from gta_anything.models.ir import GameplayIR
from gta_anything.transpiler.csharp_codegen import generate_csharp_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CS_DIR = REPO_ROOT / "runtime" / "csharp" / "GtaAnything.Runtime"


def _sample_metro_ir() -> GameplayIR:
    return GameplayIR.from_dict(
        {
            "schema_version": "0.1.0",
            "meta": {
                "id": "metro_shuttle_loop",
                "name": "Los Santos Metro Shuttle Loop",
                "version": "0.1.0",
                "author": "GTA-Anything Clean-Room",
                "license": "MIT",
                "description": "Fixed-route urban transit operational loop.",
                "source_kind": "spec_and_xml",
                "target_editions": ["enhanced_gen9", "legacy_gen8"],
            },
            "loader_target": "shvdn_enhanced",
            "inputs": {
                "activation_key": "F9",
                "modifier_key": "LeftShift",
                "menu_library": "LemonUI",
                "avoid_conflicts_with": ["F4", "Insert", "B", "N", "E"],
            },
            "ui_spec": {
                "title": "Metro Shuttle Dispatch",
                "subtitle": "Select route & vehicle class",
                "preview_mode": "static_sprite",
            },
            "entities": [
                {
                    "slot_id": "transit_coach_primary",
                    "role": "player_service_vehicle",
                    "vanilla_fallback_model": "bus",
                    "preferred_addon_model": "shuttle_addon_coach",
                    "stream_timeout_ms": 5000,
                    "is_player_vehicle": True,
                },
                {
                    "slot_id": "commuter_passenger",
                    "role": "boarding_npc",
                    "vanilla_fallback_model": "a_m_y_business_01",
                    "preferred_addon_model": None,
                    "stream_timeout_ms": 3000,
                    "is_player_vehicle": False,
                },
            ],
            "routes_or_zones": [
                {
                    "track_id": "route_10_downtown",
                    "name": "Route 10 Downtown Circular",
                    "mode": "ordered_stops",
                    "fare_or_reward": 15,
                    "allowed_vehicle_slots": ["transit_coach_primary"],
                    "stops": [
                        {"index": 0, "name": "Terminal Depot", "x": 436.2, "y": -645.8, "z": 28.7, "dwell_seconds": 6},
                        {"index": 1, "name": "Legion Square North", "x": 215.4, "y": -810.1, "z": 30.7, "dwell_seconds": 8},
                    ],
                }
            ],
            "state_machine": {
                "initial_state": "Idle",
                "cleanup_state": "Teardown",
                "states": [
                    {"name": "Idle", "phase": "standby", "description": "Standby."},
                    {"name": "MenuSelecting", "phase": "ui", "description": "Menu selection."},
                    {"name": "ResourceStreaming", "phase": "streaming", "description": "Streaming models."},
                    {"name": "SpawningShift", "phase": "spawning", "description": "Spawning vehicle."},
                    {"name": "ActiveRoute", "phase": "operation", "description": "Active route."},
                    {"name": "ShiftSummary", "phase": "completion", "description": "Summary."},
                    {"name": "Teardown", "phase": "cleanup", "description": "Teardown."},
                ],
                "transitions": [
                    {"from_state": "Idle", "to_state": "MenuSelecting", "trigger": "HotkeyPressed"},
                    {"from_state": "MenuSelecting", "to_state": "Idle", "trigger": "MenuCancelled"},
                    {"from_state": "MenuSelecting", "to_state": "ResourceStreaming", "trigger": "ShiftConfirmed"},
                    {"from_state": "ResourceStreaming", "to_state": "SpawningShift", "trigger": "ModelReadyOrFallback"},
                    {"from_state": "ResourceStreaming", "to_state": "Teardown", "trigger": "CriticalStreamFailure"},
                    {"from_state": "SpawningShift", "to_state": "ActiveRoute", "trigger": "DriverSeated"},
                    {"from_state": "SpawningShift", "to_state": "Teardown", "trigger": "SpawnReturnedNull"},
                    {"from_state": "ActiveRoute", "to_state": "ShiftSummary", "trigger": "FinalStopCompleted"},
                    {"from_state": "ActiveRoute", "to_state": "Teardown", "trigger": "ShiftAbortedOrVehicleDestroyed"},
                    {"from_state": "ShiftSummary", "to_state": "Teardown", "trigger": "SummaryAcknowledged"},
                    {"from_state": "Teardown", "to_state": "Idle", "trigger": "ResourcesReleased"},
                ],
            },
            "evidence": [
                {
                    "source_file": "spec.md",
                    "locator": "L1-L20",
                    "extracted_fact": "Clean-room transit operational loop.",
                    "confidence": 1.0,
                }
            ],
        }
    )


def test_generate_csharp_mod_structure_and_contents(tmp_path: Path):
    ir = _sample_metro_ir()
    out_dir = tmp_path / "generated_metro_mod"

    res = generate_csharp_mod(ir, out_dir)
    assert res["ok"] is True
    assert res["mod_id"] == "metro_shuttle_loop"
    assert Path(res["output_dir"]).exists()
    assert len(res["generated_files"]) >= 4

    csproj_files = list(out_dir.glob("*.csproj"))
    assert len(csproj_files) == 1
    csproj_text = csproj_files[0].read_text(encoding="utf-8")
    assert "GtaAnything.Runtime" in csproj_text
    assert "GTAV_ENHANCED" in csproj_text or "GTAV_LEGACY" in csproj_text

    entrypoint = out_dir / "ModEntrypoint.cs"
    assert entrypoint.exists()
    cs_text = entrypoint.read_text(encoding="utf-8")
    assert "WorldSession" in cs_text
    assert "OperationalStateMachine" in cs_text
    assert "SafeModelStreamer" in cs_text
    assert "DecoupledMenuController" in cs_text
    assert "PhasedJsonLogger" in cs_text

    config_files = list(out_dir.glob("*Config.json"))
    assert len(config_files) >= 1
    cfg_data = json.loads(config_files[0].read_text(encoding="utf-8"))
    assert "metro_shuttle_loop" in json.dumps(cfg_data)

    verify_doc = out_dir / "BUILD_AND_VERIFY.md"
    assert verify_doc.exists()
    verify_text = verify_doc.read_text(encoding="utf-8")
    assert "L1" in verify_text and "L7" in verify_text


def test_csharp_runtime_sdk_sources_present():
    expected_files = [
        RUNTIME_CS_DIR / "GtaAnything.Runtime.csproj",
        RUNTIME_CS_DIR / "README.md",
        RUNTIME_CS_DIR / "Compatibility" / "GameEditionDetector.cs",
        RUNTIME_CS_DIR / "Compatibility" / "LoaderAdapter.cs",
        RUNTIME_CS_DIR / "Lifecycle" / "WorldSession.cs",
        RUNTIME_CS_DIR / "Lifecycle" / "OperationalStateMachine.cs",
        RUNTIME_CS_DIR / "Streaming" / "SafeModelStreamer.cs",
        RUNTIME_CS_DIR / "UI" / "DecoupledMenuController.cs",
        RUNTIME_CS_DIR / "Telemetry" / "PhasedJsonLogger.cs",
    ]
    for path in expected_files:
        assert path.exists(), f"Missing Clean-Room C# Runtime SDK file: {path}"

    streamer_cs = (RUNTIME_CS_DIR / "Streaming" / "SafeModelStreamer.cs").read_text(encoding="utf-8")
    assert "ReleaseModelRequest" in streamer_cs or "MarkAsNoLongerNeeded" in streamer_cs


def test_profile_manager_stage_switch_and_rollback(tmp_path: Path):
    game_dir = tmp_path / "GameRoot"
    profiles_root = tmp_path / "ProfilesStore"
    game_dir.mkdir(parents=True)
    profiles_root.mkdir(parents=True)

    # Create two synthetic mod builds: 'transit' and 'patrol'
    transit_build = tmp_path / "builds" / "transit_build"
    (transit_build / "scripts").mkdir(parents=True)
    (transit_build / "scripts" / "MetroShuttleLoopConfig.json").write_text('{"profile": "transit"}', encoding="utf-8")

    patrol_build = tmp_path / "builds" / "patrol_build"
    (patrol_build / "plugins").mkdir(parents=True)
    (patrol_build / "plugins" / "HarborPatrolConfig.json").write_text('{"profile": "patrol"}', encoding="utf-8")

    pm = ProfileManager(game_dir=game_dir, profiles_root=profiles_root)
    # Disable real process blocking if running in test environment by overriding detector if supported
    if hasattr(pm, "_check_running_processes"):
        pm._check_running_processes = lambda: []  # type: ignore[attr-defined]

    # 1. Stage both profiles
    stage_transit = pm.stage_profile("transit", transit_build, loader_chain="shvdn", dry_run=False)
    assert stage_transit["ok"] is True

    stage_patrol = pm.stage_profile("patrol", patrol_build, loader_chain="rph", dry_run=False)
    assert stage_patrol["ok"] is True

    # 2. Switch to 'transit'
    sw1 = pm.switch_profile("transit", dry_run=False)
    assert sw1["ok"] is True
    status1 = pm.status()
    assert status1["active_profile"] == "transit"
    assert (game_dir / "scripts" / "MetroShuttleLoopConfig.json").exists()

    # 3. Switch from 'transit' to 'patrol' -> 'transit' must be cleanly parked in Inactive/transit
    sw2 = pm.switch_profile("patrol", dry_run=False)
    assert sw2["ok"] is True
    status2 = pm.status()
    assert status2["active_profile"] == "patrol"
    assert (game_dir / "plugins" / "HarborPatrolConfig.json").exists()
    assert not (game_dir / "scripts" / "MetroShuttleLoopConfig.json").exists()

    # 4. Rollback -> restores previous profile ('transit') cleanly
    rb = pm.rollback(dry_run=False)
    assert rb["ok"] is True
    status3 = pm.status()
    assert status3["active_profile"] == "transit"
    assert (game_dir / "scripts" / "MetroShuttleLoopConfig.json").exists()


def test_profile_manager_lock_and_dry_run(tmp_path: Path):
    game_dir = tmp_path / "GameRootLockTest"
    profiles_root = tmp_path / "ProfilesLockTest"
    game_dir.mkdir(parents=True)
    profiles_root.mkdir(parents=True)

    mod_build = tmp_path / "sample_build"
    (mod_build / "scripts").mkdir(parents=True)
    (mod_build / "scripts" / "Sample.json").write_text('{"test": true}', encoding="utf-8")

    pm = ProfileManager(game_dir=game_dir, profiles_root=profiles_root)
    if hasattr(pm, "_check_running_processes"):
        pm._check_running_processes = lambda: []  # type: ignore[attr-defined]

    # Dry run stage should not mutate or activate game_dir
    dry_stage = pm.stage_profile("transit", mod_build, loader_chain="shvdn", dry_run=True)
    assert dry_stage["ok"] is True
    assert not (game_dir / "scripts" / "Sample.json").exists()

    # Stage for real, then test switch dry_run
    pm.stage_profile("transit", mod_build, loader_chain="shvdn", dry_run=False)
    dry_switch = pm.switch_profile("transit", dry_run=True)
    assert dry_switch["ok"] is True
    assert not (game_dir / "scripts" / "Sample.json").exists()

    # Test lock-file protection when switch.lock is already held
    lock_file = profiles_root / "switch.lock"
    lock_file.write_text("LOCKED_BY_ANOTHER_PROCESS", encoding="utf-8")
    locked_attempt = pm.switch_profile("transit", dry_run=False)
    assert locked_attempt["ok"] is False
    assert "lock" in json.dumps(locked_attempt).lower()

    # Remove lock file and verify switch succeeds
    lock_file.unlink()
    unlocked_attempt = pm.switch_profile("transit", dry_run=False)
    assert unlocked_attempt["ok"] is True
