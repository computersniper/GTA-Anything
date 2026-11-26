"""Deterministic Headless Open-World Simulator covering Acceptance Layers L1 through L7.

Simulates Gameplay IR execution offline without requiring a running GTA V process:
- L1 (static_integrity): Gameplay IR invariant validation.
- L2 (loader_recognition): Dual-build identity & loader chain mounting.
- L3 (script_initialized): WorldSession lease table initialization.
- L4 (menu_responsive): Decoupled static menu scrolling (0 entities spawned).
- L5 (session_started): SafeModelStreamer with timeout release + vanilla fallback & vehicle lease.
- L6 (core_loop_completed): Ordered stop/zone traversal, 3D Euclidean distances, dwell, NPC lease/release, reward, and optional abort injection.
- L7 (clean_teardown): Deterministic WorldSession teardown asserting 0 leaked leases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

from gta_anything.models.ir import (
    EntitySlot,
    GameplayIR,
    SpatialTrack,
    StopNode,
    validate_gameplay_ir,
)
from gta_anything.models.manifest import (
    DEFAULT_LOADER_CHAINS,
    GameBuildIdentity,
    LoaderChainSpec,
)


_SIM_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_AVG_URBAN_SPEED_MPS = 12.5  # ~45 km/h deterministic travel speed


@dataclass
class WorldSession:
    """Lease-based entity lifecycle tracker mirroring GtaAnything.Runtime.WorldSession."""

    mod_id: str
    leased_entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    total_leased_ever: int = 0
    total_released_ever: int = 0

    def lease(self, kind: str, handle_id: str, **metadata: Any) -> str:
        """Register an entity handle in the mod-owned lease table."""
        self.leased_entities[handle_id] = {
            "kind": kind,
            "handle_id": handle_id,
            **metadata,
        }
        self.total_leased_ever += 1
        return handle_id

    def release(self, handle_id: str) -> bool:
        """Release a single leased entity handle."""
        if handle_id in self.leased_entities:
            del self.leased_entities[handle_id]
            self.total_released_ever += 1
            return True
        return False

    def dispose_all(self) -> int:
        """Deterministically release every remaining leased handle."""
        count = len(self.leased_entities)
        self.leased_entities.clear()
        self.total_released_ever += count
        return count

    @property
    def active_count(self) -> int:
        return len(self.leased_entities)


@dataclass
class SimulatedLoaderAdapter:
    """Simulated loader chain adapter for SHVDN (v3/Enhanced) or RPH."""

    loader_target: str
    build_identity: GameBuildIdentity
    chain_spec: LoaderChainSpec

    @classmethod
    def from_ir(cls, ir: GameplayIR) -> SimulatedLoaderAdapter:
        editions = ir.meta.target_editions or ["enhanced_gen9"]
        edition = "enhanced_gen9" if "enhanced_gen9" in editions else editions[0]
        if edition == "legacy_gen8":
            build = GameBuildIdentity(
                edition="legacy_gen8",
                exe_version="1.0.3411.0",
                shv_build_alias="VER_1_0_3411_0",
                exe_name="GTA5.exe",
            )
        else:
            build = GameBuildIdentity(
                edition="enhanced_gen9",
                exe_version="1.0.1158.16",
                shv_build_alias="VER_EN_1_0_1158_13",
                exe_name="GTA5_Enhanced.exe",
            )

        chain_key = "rph" if ir.loader_target == "rph" else "shvdn"
        chain_spec = DEFAULT_LOADER_CHAINS[chain_key]
        return cls(
            loader_target=ir.loader_target,
            build_identity=build,
            chain_spec=chain_spec,
        )


@dataclass
class ModelStreamOutcome:
    """Resolution outcome for a single EntitySlot streaming request."""

    slot_id: str
    requested_model: str
    resolved_model: str
    timed_out: bool
    released_timed_out_handle: bool
    used_vanilla_fallback: bool
    elapsed_ms: int


class SafeModelStreamer:
    """Simulates GtaAnything.Runtime SafeModelStreamer with timeout release & vanilla fallback."""

    def __init__(self, mounted_addons: set[str] | None = None) -> None:
        self.mounted_addons: set[str] = set(mounted_addons or set())

    def resolve_slot(
        self,
        slot: EntitySlot,
        *,
        inject_addon_timeout: bool = False,
        force_injected_timeout: bool = False,
    ) -> ModelStreamOutcome:
        """Resolve an EntitySlot model, releasing timed-out addon requests and falling back to vanilla."""
        addon = (slot.preferred_addon_model or "").strip() or None

        if addon is not None:
            addon_available = (addon in self.mounted_addons) and not inject_addon_timeout
            if not addon_available:
                # Simulate stream timeout -> MarkAsNoLongerNeeded() -> fallback to vanilla
                return ModelStreamOutcome(
                    slot_id=slot.slot_id,
                    requested_model=addon,
                    resolved_model=slot.vanilla_fallback_model,
                    timed_out=True,
                    released_timed_out_handle=True,
                    used_vanilla_fallback=True,
                    elapsed_ms=slot.stream_timeout_ms,
                )
            return ModelStreamOutcome(
                slot_id=slot.slot_id,
                requested_model=addon,
                resolved_model=addon,
                timed_out=False,
                released_timed_out_handle=False,
                used_vanilla_fallback=False,
                elapsed_ms=120,
            )

        if force_injected_timeout:
            synthetic_addon = f"{slot.slot_id}_addon_probe"
            return ModelStreamOutcome(
                slot_id=slot.slot_id,
                requested_model=synthetic_addon,
                resolved_model=slot.vanilla_fallback_model,
                timed_out=True,
                released_timed_out_handle=True,
                used_vanilla_fallback=True,
                elapsed_ms=slot.stream_timeout_ms,
            )

        return ModelStreamOutcome(
            slot_id=slot.slot_id,
            requested_model=slot.vanilla_fallback_model,
            resolved_model=slot.vanilla_fallback_model,
            timed_out=False,
            released_timed_out_handle=False,
            used_vanilla_fallback=False,
            elapsed_ms=45,
        )


def _find_state_by_phase(ir: GameplayIR, phase: str, fallback: str) -> str:
    for node in ir.state_machine.states:
        if node.phase == phase:
            return node.name
    return fallback


def _has_transition(ir: GameplayIR, from_state: str, to_state: str) -> bool:
    return any(
        t.from_state == from_state and t.to_state == to_state
        for t in ir.state_machine.transitions
    )


def _euclidean_3d(a: StopNode, b: StopNode) -> float:
    return math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2)


def _write_telemetry_jsonl(
    telemetry_out: str | Path | None,
    events: list[dict[str, Any]],
) -> str | None:
    if telemetry_out is None:
        return None
    out_path = Path(telemetry_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(ev, ensure_ascii=False) for ev in events]
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return str(out_path)


def simulate_gameplay_ir(
    ir: GameplayIR | dict[str, Any],
    track_id: str | None = None,
    inject_addon_timeout: bool = False,
    inject_abort_at_stop: int | None = None,
    telemetry_out: str | Path | None = None,
) -> dict[str, Any]:
    """Deterministically simulate all 7 Acceptance Layers (L1-L7) offline for a Gameplay IR."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    mod_id = ir_obj.meta.id

    sim_clock_seconds = 0.0
    telemetry_events: list[dict[str, Any]] = []
    state_trace: list[str] = []

    def emit(
        *,
        layer: int,
        phase: str,
        event: str,
        details: dict[str, Any],
        level: str = "INFO",
        advance_sec: float = 0.5,
    ) -> None:
        nonlocal sim_clock_seconds
        sim_clock_seconds += advance_sec
        ts = (_SIM_EPOCH + timedelta(seconds=sim_clock_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
        telemetry_events.append(
            {
                "timestamp": ts,
                "layer": layer,
                "phase": phase,
                "event": event,
                "level": level,
                "mod_id": mod_id,
                "details": details,
            }
        )

    def enter_state(state_name: str) -> None:
        if state_name and (not state_trace or state_trace[-1] != state_name):
            state_trace.append(state_name)

    # ------------------------------------------------------------------
    # L1: static_integrity
    # ------------------------------------------------------------------
    validation = validate_gameplay_ir(ir_obj)
    if not validation.valid:
        emit(
            layer=1,
            phase="static_integrity",
            event="IRValidationFailed",
            level="ERROR",
            details={
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        )
        t_path = _write_telemetry_jsonl(telemetry_out, telemetry_events)
        return {
            "ok": False,
            "mod_id": mod_id,
            "track_id": track_id or "",
            "aborted_intentionally": False,
            "used_vanilla_fallback": False,
            "released_timed_out_models": 0,
            "spawned_during_menu_scroll": 0,
            "stops_completed": 0,
            "total_stops": 0,
            "total_distance_m": 0.0,
            "total_reward": 0,
            "highest_acceptance_layer_reached": 0,
            "active_leases_after_teardown": 0,
            "state_trace": state_trace,
            "telemetry_events": telemetry_events,
            "telemetry_path": t_path,
        }

    highest_layer = 1
    emit(
        layer=1,
        phase="static_integrity",
        event="IRValidated",
        details={
            "schema_version": ir_obj.schema_version,
            "checked_invariants": validation.checked_invariants,
            "warnings_count": len(validation.warnings),
        },
    )

    # ------------------------------------------------------------------
    # L2: loader_recognition
    # ------------------------------------------------------------------
    loader = SimulatedLoaderAdapter.from_ir(ir_obj)
    highest_layer = 2
    emit(
        layer=2,
        phase="loader_recognition",
        event="LoaderMounted",
        details={
            "loader_target": loader.loader_target,
            "chain_id": loader.chain_spec.chain_id,
            "edition": loader.build_identity.edition,
            "exe_name": loader.build_identity.exe_name,
            "exe_version": loader.build_identity.exe_version,
            "shv_build_alias": loader.build_identity.shv_build_alias,
        },
    )

    # ------------------------------------------------------------------
    # L3: script_initialized
    # ------------------------------------------------------------------
    world_session = WorldSession(mod_id=mod_id)
    initial_state = ir_obj.state_machine.initial_state or "Idle"
    cleanup_state = ir_obj.state_machine.cleanup_state or "Teardown"
    enter_state(initial_state)

    highest_layer = 3
    emit(
        layer=3,
        phase="script_initialized",
        event="SessionInitialized",
        details={
            "initial_state": initial_state,
            "cleanup_state": cleanup_state,
            "active_leases": world_session.active_count,
            "activation_key": ir_obj.inputs.activation_key,
            "modifier_key": ir_obj.inputs.modifier_key,
        },
    )

    # ------------------------------------------------------------------
    # L4: menu_responsive (UI-Spawn Decoupling check)
    # ------------------------------------------------------------------
    ui_state = _find_state_by_phase(ir_obj, "ui", "MenuSelecting")
    enter_state(ui_state)

    leases_before_menu = world_session.active_count
    scrolled_tracks: list[str] = []
    for candidate in ir_obj.routes_or_zones:
        # Static metadata / 2D sprite preview only: NEVER spawn 3D entities here
        scrolled_tracks.append(candidate.track_id)
    spawned_during_menu_scroll = world_session.active_count - leases_before_menu

    selected_track: SpatialTrack | None = None
    if track_id is not None:
        for candidate in ir_obj.routes_or_zones:
            if candidate.track_id == track_id:
                selected_track = candidate
                break
        if selected_track is None:
            emit(
                layer=4,
                phase="menu_responsive",
                event="TrackNotFound",
                level="ERROR",
                details={
                    "requested_track_id": track_id,
                    "available_track_ids": scrolled_tracks,
                },
            )
            enter_state(cleanup_state)
            world_session.dispose_all()
            t_path = _write_telemetry_jsonl(telemetry_out, telemetry_events)
            return {
                "ok": False,
                "mod_id": mod_id,
                "track_id": track_id,
                "aborted_intentionally": False,
                "used_vanilla_fallback": False,
                "released_timed_out_models": 0,
                "spawned_during_menu_scroll": spawned_during_menu_scroll,
                "stops_completed": 0,
                "total_stops": 0,
                "total_distance_m": 0.0,
                "total_reward": 0,
                "highest_acceptance_layer_reached": 3,
                "active_leases_after_teardown": world_session.active_count,
                "state_trace": state_trace,
                "telemetry_events": telemetry_events,
                "telemetry_path": t_path,
            }
    elif ir_obj.routes_or_zones:
        selected_track = ir_obj.routes_or_zones[0]

    resolved_track_id = selected_track.track_id if selected_track else "default_track"
    highest_layer = 4
    emit(
        layer=4,
        phase="menu_responsive",
        event="MenuPreviewScrolled",
        details={
            "preview_mode": ir_obj.ui_spec.preview_mode,
            "tracks_scrolled": len(scrolled_tracks),
            "selected_track_id": resolved_track_id,
            "spawned_during_menu_scroll": spawned_during_menu_scroll,
        },
    )

    # ------------------------------------------------------------------
    # L5: session_started (SafeModelStreamer + vehicle/blip leasing)
    # ------------------------------------------------------------------
    streaming_state = _find_state_by_phase(ir_obj, "streaming", "ResourceStreaming")
    enter_state(streaming_state)

    streamer = SafeModelStreamer(mounted_addons=set())
    any_declared_addon = any(
        bool((e.preferred_addon_model or "").strip()) for e in ir_obj.entities
    )

    used_vanilla_fallback = False
    released_timed_out_models = 0
    resolved_models: dict[str, str] = {}

    for idx, entity in enumerate(ir_obj.entities):
        # If inject_addon_timeout=True on a vanilla-only IR, inject a timeout on the
        # player vehicle (or first slot) so the timeout+release+fallback invariant is exercised.
        force_injected = (
            inject_addon_timeout
            and not any_declared_addon
            and (entity.is_player_vehicle or idx == 0)
        )
        outcome = streamer.resolve_slot(
            entity,
            inject_addon_timeout=inject_addon_timeout,
            force_injected_timeout=force_injected,
        )
        resolved_models[entity.slot_id] = outcome.resolved_model
        if outcome.timed_out:
            used_vanilla_fallback = True
            if outcome.released_timed_out_handle:
                released_timed_out_models += 1
            emit(
                layer=5,
                phase="session_started",
                event="ModelStreamTimeoutFallback",
                level="WARNING",
                advance_sec=outcome.elapsed_ms / 1000.0,
                details={
                    "slot_id": outcome.slot_id,
                    "requested_addon": outcome.requested_model,
                    "resolved_vanilla_fallback": outcome.resolved_model,
                    "released_handle": "MarkAsNoLongerNeeded",
                    "elapsed_ms": outcome.elapsed_ms,
                },
            )
        else:
            emit(
                layer=5,
                phase="session_started",
                event="ModelStreamResolved",
                advance_sec=outcome.elapsed_ms / 1000.0,
                details={
                    "slot_id": outcome.slot_id,
                    "resolved_model": outcome.resolved_model,
                    "elapsed_ms": outcome.elapsed_ms,
                },
            )

    spawning_state = _find_state_by_phase(ir_obj, "spawning", "SpawningShift")
    enter_state(spawning_state)

    player_slot = next(
        (e for e in ir_obj.entities if e.is_player_vehicle),
        ir_obj.entities[0],
    )
    player_vehicle_handle = world_session.lease(
        "vehicle",
        f"veh:{player_slot.slot_id}",
        model=resolved_models[player_slot.slot_id],
        role=player_slot.role,
    )
    route_blip_handle = world_session.lease(
        "blip",
        f"blip:route:{resolved_track_id}",
        track_id=resolved_track_id,
    )

    highest_layer = 5
    emit(
        layer=5,
        phase="session_started",
        event="ServiceVehicleSpawned",
        details={
            "vehicle_handle": player_vehicle_handle,
            "model": resolved_models[player_slot.slot_id],
            "route_blip_handle": route_blip_handle,
            "active_leases": world_session.active_count,
            "used_vanilla_fallback": used_vanilla_fallback,
        },
    )

    # ------------------------------------------------------------------
    # L6: core_loop_completed (ordered stops/zones traversal)
    # ------------------------------------------------------------------
    operation_state = _find_state_by_phase(ir_obj, "operation", "ActiveRoute")
    enter_state(operation_state)

    npc_slot = next((e for e in ir_obj.entities if not e.is_player_vehicle), None)
    npc_model = (
        resolved_models[npc_slot.slot_id]
        if npc_slot is not None
        else "a_m_y_business_01"
    )

    stops: list[StopNode] = (
        sorted(selected_track.stops, key=lambda s: s.index)
        if selected_track is not None
        else []
    )
    fare_or_reward = selected_track.fare_or_reward if selected_track is not None else 0

    stops_completed = 0
    total_stops = len(stops)
    total_distance_m = 0.0
    total_reward = 0
    aborted_intentionally = False

    prev_stop: StopNode | None = None
    for pos, stop in enumerate(stops):
        segment_distance_m = (
            _euclidean_3d(prev_stop, stop) if prev_stop is not None else 0.0
        )
        travel_seconds = segment_distance_m / _AVG_URBAN_SPEED_MPS

        stop_blip = world_session.lease(
            "blip",
            f"blip:stop:{stop.index}",
            stop_name=stop.name,
        )
        npc_handle = world_session.lease(
            "ped",
            f"ped:stop:{stop.index}",
            model=npc_model,
            stop_name=stop.name,
        )

        if inject_abort_at_stop is not None and (
            pos == inject_abort_at_stop or stop.index == inject_abort_at_stop
        ):
            aborted_intentionally = True
            emit(
                layer=6,
                phase="core_loop_completed",
                event="ShiftAborted",
                level="WARNING",
                advance_sec=max(travel_seconds, 1.0),
                details={
                    "stop_index": stop.index,
                    "stop_name": stop.name,
                    "stops_completed_before_abort": stops_completed,
                    "active_leases_at_abort": world_session.active_count,
                    "transition_target": cleanup_state,
                },
            )
            # Guarded abort transitions straight to cleanup_state; Teardown will release all leases
            break

        total_distance_m += segment_distance_m
        total_reward += fare_or_reward
        stops_completed += 1

        # Release stop-scoped NPC & stop blip after dwell interaction completes
        world_session.release(npc_handle)
        world_session.release(stop_blip)

        emit(
            layer=6,
            phase="core_loop_completed",
            event="StopCompleted",
            advance_sec=max(travel_seconds + stop.dwell_seconds, 1.0),
            details={
                "stop_index": stop.index,
                "stop_name": stop.name,
                "segment_distance_m": round(segment_distance_m, 2),
                "travel_seconds": round(travel_seconds, 2),
                "dwell_seconds": stop.dwell_seconds,
                "reward_earned": fare_or_reward,
                "active_leases": world_session.active_count,
            },
        )
        prev_stop = stop

    highest_layer = 6

    if not aborted_intentionally:
        completion_state = _find_state_by_phase(ir_obj, "completion", "")
        if completion_state:
            enter_state(completion_state)
        emit(
            layer=6,
            phase="core_loop_completed",
            event="ShiftSummaryRecorded",
            details={
                "track_id": resolved_track_id,
                "stops_completed": stops_completed,
                "total_stops": total_stops,
                "total_distance_m": round(total_distance_m, 2),
                "total_reward": total_reward,
            },
        )

    # ------------------------------------------------------------------
    # L7: clean_teardown (Deterministic WorldSession release)
    # ------------------------------------------------------------------
    enter_state(cleanup_state)
    released_in_teardown = world_session.dispose_all()
    active_leases_after_teardown = world_session.active_count
    assert active_leases_after_teardown == 0, (
        f"WorldSession lease leak detected after teardown: {active_leases_after_teardown}"
    )

    if _has_transition(ir_obj, cleanup_state, initial_state):
        enter_state(initial_state)

    highest_layer = 7
    emit(
        layer=7,
        phase="clean_teardown",
        event="TeardownCompleted",
        details={
            "released_in_teardown": released_in_teardown,
            "total_leased_ever": world_session.total_leased_ever,
            "total_released_ever": world_session.total_released_ever,
            "active_leases_after_teardown": active_leases_after_teardown,
            "aborted_intentionally": aborted_intentionally,
        },
    )

    t_path = _write_telemetry_jsonl(telemetry_out, telemetry_events)

    return {
        "ok": active_leases_after_teardown == 0 and spawned_during_menu_scroll == 0,
        "mod_id": mod_id,
        "track_id": resolved_track_id,
        "aborted_intentionally": aborted_intentionally,
        "used_vanilla_fallback": used_vanilla_fallback,
        "released_timed_out_models": released_timed_out_models,
        "spawned_during_menu_scroll": spawned_during_menu_scroll,
        "stops_completed": stops_completed,
        "total_stops": total_stops,
        "total_distance_m": round(total_distance_m, 2),
        "total_reward": total_reward,
        "highest_acceptance_layer_reached": highest_layer,
        "active_leases_after_teardown": active_leases_after_teardown,
        "state_trace": state_trace,
        "telemetry_events": telemetry_events,
        "telemetry_path": t_path,
    }
