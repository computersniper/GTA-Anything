from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from gta_anything.extractor.analyzer import extract_gameplay_ir
from gta_anything.models.ir import (
    EntitySlot,
    EvidenceAnchor,
    GameplayIR,
    InputBindings,
    MenuUISpec,
    ModMeta,
    SpatialTrack,
    StateMachineSpec,
    StateNode,
    StopNode,
    TransitionEdge,
    validate_gameplay_ir,
)
from gta_anything.models.manifest import (
    ACCEPTANCE_LAYERS,
    DeploymentManifest,
    GameBuildIdentity,
    LoaderChainSpec,
)
from gta_anything.transpiler.world_mapper import map_ir_to_world

REPO_ROOT = Path(__file__).resolve().parents[1]
METRO_IR_PATH = REPO_ROOT / "examples" / "metro_shuttle_loop" / "gameplay_ir.json"
METRO_SPEC_PATH = REPO_ROOT / "examples" / "metro_shuttle_loop" / "spec.md"
HARBOR_IR_PATH = REPO_ROOT / "examples" / "harbor_courier_dispatch" / "gameplay_ir.json"


def _make_baseline_ir_dict() -> dict:
    return {
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
                "preferred_addon_model": None,
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
                    {
                        "index": 0,
                        "name": "Terminal Depot",
                        "x": 436.2,
                        "y": -645.8,
                        "z": 28.7,
                        "dwell_seconds": 6,
                    },
                    {
                        "index": 1,
                        "name": "Legion Square North",
                        "x": 215.4,
                        "y": -810.1,
                        "z": 30.7,
                        "dwell_seconds": 8,
                    },
                ],
            }
        ],
        "state_machine": {
            "initial_state": "Idle",
            "cleanup_state": "Teardown",
            "states": [
                {"name": "Idle", "phase": "standby", "description": "Standby."},
                {"name": "MenuSelecting", "phase": "ui", "description": "Static UI selection."},
                {"name": "ResourceStreaming", "phase": "streaming", "description": "Streaming models."},
                {"name": "SpawningShift", "phase": "spawning", "description": "Spawning entities."},
                {"name": "ActiveRoute", "phase": "operation", "description": "Driving stops."},
                {"name": "ShiftSummary", "phase": "completion", "description": "Route summary."},
                {"name": "Teardown", "phase": "cleanup", "description": "Releasing entities."},
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
                "locator": "L12-L28",
                "extracted_fact": "Ordered transit stops with dwell timer and fare calculation.",
                "confidence": 0.98,
            }
        ],
    }


def test_ir_serialization_roundtrip_and_valid_baseline():
    raw = _make_baseline_ir_dict()
    ir = GameplayIR.from_dict(raw)
    assert ir.meta.id == "metro_shuttle_loop"
    assert ir.ui_spec.preview_mode == "static_sprite"
    assert len(ir.entities) == 2

    json_str = ir.to_json()
    reloaded = GameplayIR.from_json(json_str)
    assert reloaded.to_dict()["meta"]["id"] == "metro_shuttle_loop"

    report = validate_gameplay_ir(reloaded)
    assert report.valid is True
    assert report.errors == []
    assert len(report.checked_invariants) >= 4


@pytest.mark.parametrize("example_ir_path", [METRO_IR_PATH, HARBOR_IR_PATH])
def test_flagship_example_irs_are_valid(example_ir_path: Path):
    assert example_ir_path.exists(), f"Missing flagship example IR: {example_ir_path}"
    data = json.loads(example_ir_path.read_text(encoding="utf-8"))
    ir = GameplayIR.from_dict(data)
    report = validate_gameplay_ir(ir)
    assert report.valid is True, f"Validation failed for {example_ir_path}: {report.errors}"
    assert report.errors == []
    assert ir.ui_spec.preview_mode in ("static_metadata", "static_sprite")
    assert len(ir.entities) >= 1
    assert all(bool(e.vanilla_fallback_model) for e in ir.entities)
    assert len(ir.routes_or_zones) >= 1
    assert len(ir.evidence) >= 1


def test_reject_live_3d_spawn_preview_mode():
    bad = _make_baseline_ir_dict()
    bad["ui_spec"]["preview_mode"] = "live_3d_spawn"
    report = validate_gameplay_ir(bad)
    assert report.valid is False
    assert any("live_3d_spawn" in err or "preview_mode" in err for err in report.errors)


def test_reject_missing_vanilla_fallback_model():
    bad = _make_baseline_ir_dict()
    bad["entities"][0]["vanilla_fallback_model"] = ""
    report = validate_gameplay_ir(bad)
    assert report.valid is False
    assert any("vanilla_fallback_model" in err or "fallback" in err.lower() for err in report.errors)


def test_reject_dead_end_operational_state_without_teardown_path():
    bad = _make_baseline_ir_dict()
    # Add an operational state reachable from ActiveRoute that has no path to Teardown
    bad["state_machine"]["states"].append(
        {"name": "StuckDepotLock", "phase": "operation", "description": "Dead-end state."}
    )
    bad["state_machine"]["transitions"].append(
        {"from_state": "ActiveRoute", "to_state": "StuckDepotLock", "trigger": "EnteredDeadEnd"}
    )
    report = validate_gameplay_ir(bad)
    assert report.valid is False
    assert any("StuckDepotLock" in err or "Teardown" in err or "cleanup" in err.lower() for err in report.errors)


def test_reject_unreachable_state():
    bad = _make_baseline_ir_dict()
    bad["state_machine"]["states"].append(
        {"name": "OrphanState", "phase": "operation", "description": "Never transitioned into."}
    )
    bad["state_machine"]["transitions"].append(
        {"from_state": "OrphanState", "to_state": "Teardown", "trigger": "OrphanExit"}
    )
    report = validate_gameplay_ir(bad)
    assert report.valid is False
    assert any("OrphanState" in err or "unreachable" in err.lower() for err in report.errors)


def test_hotkey_conflict_warning_when_unmodified():
    risky = _make_baseline_ir_dict()
    risky["inputs"]["activation_key"] = "F4"
    risky["inputs"]["modifier_key"] = None
    report = validate_gameplay_ir(risky)
    # High-conflict single key without modifier must produce a warning (or error)
    combined = " ".join(report.warnings + report.errors)
    assert "F4" in combined or "conflict" in combined.lower()


def test_reject_unlicensed_or_empty_license_ir():
    bad = _make_baseline_ir_dict()
    bad["meta"]["license"] = "proprietary-unlicensed"
    report = validate_gameplay_ir(bad)
    assert report.valid is False
    assert any("license" in err.lower() for err in report.errors)


def test_extractor_from_spec_and_routes_xml():
    assert METRO_SPEC_PATH.exists(), f"Missing {METRO_SPEC_PATH}"
    ir = extract_gameplay_ir(METRO_SPEC_PATH, mod_id="metro_shuttle_loop", target_edition="enhanced_gen9")
    assert isinstance(ir, GameplayIR)
    assert ir.meta.id == "metro_shuttle_loop"
    assert len(ir.routes_or_zones) >= 1
    first_track = ir.routes_or_zones[0]
    assert len(first_track.stops) >= 4
    assert first_track.stops[0].dwell_seconds > 0
    assert len(ir.evidence) >= 1
    assert all(isinstance(ev, EvidenceAnchor) for ev in ir.evidence)

    report = validate_gameplay_ir(ir)
    assert report.valid is True, f"Extracted IR invalid: {report.errors}"


def test_extractor_from_synthetic_source_directory(tmp_path: Path):
    src_dir = tmp_path / "sample_patrol_mod"
    src_dir.mkdir(parents=True)
    (src_dir / "patrol_logic.py").write_text(
        """# Clean-room patrol dispatch script
MOD_NAME = "Harbor Security Patrol"
ACTIVATION_KEY = "F10"
FALLBACK_VEHICLE = "police"
STATES = ["Idle", "OnDuty", "Responding", "Teardown"]
""",
        encoding="utf-8",
    )
    (src_dir / "zones.xml").write_text(
        """<Route id="dock_patrol" name="Docklands Patrol Loop" fare="50" vehicle="police">
    <Stop index="0" name="Pier 400 Gate" x="100.5" y="-2900.0" z="6.0" dwell="10" />
    <Stop index="1" name="Container Crane North" x="240.0" y="-2980.0" z="6.0" dwell="12" />
</Route>
""",
        encoding="utf-8",
    )
    ir = extract_gameplay_ir(src_dir, mod_id="dock_patrol_mod")
    assert ir.meta.id == "dock_patrol_mod"
    assert len(ir.evidence) >= 1
    report = validate_gameplay_ir(ir)
    assert report.valid is True, f"Extracted source directory IR failed validation: {report.errors}"


def test_world_mapper_validates_vanilla_catalog():
    ir = GameplayIR.from_dict(_make_baseline_ir_dict())
    mapping = map_ir_to_world(ir)
    assert isinstance(mapping, dict)
    assert mapping.get("mod_id") == "metro_shuttle_loop"
    assert "entity_bindings" in mapping or "entities" in mapping
    bindings = mapping.get("entity_bindings") or mapping.get("entities")
    assert len(bindings) == 2
    assert any(k in mapping for k in ("telemetry_layers", "acceptance_layers", "checkpoints", "telemetry_checkpoints"))


def test_manifest_models_and_acceptance_layers():
    assert len(ACCEPTANCE_LAYERS) == 7
    layer_nums = [layer.get("layer") or layer.get("id") for layer in ACCEPTANCE_LAYERS]
    assert len(layer_nums) == 7

    build_id = GameBuildIdentity(
        edition="enhanced_gen9",
        exe_version="1.0.1158.16",
        shv_build_alias="VER_EN_1_0_1158_13",
        exe_name="GTA5_Enhanced.exe",
    )
    assert build_id.edition == "enhanced_gen9"
    assert build_id.exe_version != build_id.shv_build_alias

    loader = LoaderChainSpec(
        chain_id="shvdn",
        required_files=["ScriptHookV.dll", "ScriptHookVDotNet.asi"],
        log_files=["ScriptHookV.log", "ScriptHookVDotNet.log"],
    )
    assert loader.chain_id == "shvdn"

    manifest = DeploymentManifest(
        profile_name="transit",
        mod_id="metro_shuttle_loop",
        target_game_dir="synthetic_game_dir",
        edition="enhanced_gen9",
        created_at="2026-11-26T00:00:00Z",
        operations=[],
        sha256_map={},
    )
    assert manifest.profile_name == "transit"
