"""Formal Gameplay Intermediate Representation (Gameplay IR v0.1) models and static validator."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any


VALID_EDITIONS = {"enhanced_gen9", "legacy_gen8"}
VALID_LOADER_TARGETS = {"shvdn_v3", "shvdn_enhanced", "rph"}
VALID_PREVIEW_MODES = {"static_metadata", "static_sprite"}
FORBIDDEN_PREVIEW_MODES = {"live_3d_spawn"}
VALID_TRACK_MODES = {"ordered_stops", "dispatch_zones"}
OPERATIONAL_PHASES_REQUIRING_TEARDOWN = {
    "streaming",
    "spawning",
    "operation",
    "completion",
}
HIGH_CONFLICT_SINGLE_KEYS = {
    "F4": "RAGE Plugin Hook (RPH) console / Native Trainer default key",
    "INSERT": "ScriptHookVDotNet (SHVDN) script reload key",
    "F3": "Simple Trainer / Menyoo menu key",
    "F8": "Menyoo / FiveM console key",
    "B": "LSPDFR Backup Menu / Pointing key",
    "N": "LSPDFR Interaction Menu / Push-to-talk key",
    "E": "GTA V primary context interaction / horn / siren key",
    "Y": "LSPDFR Callout acceptance key",
}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass
class ModMeta:
    """Metadata and clean-room provenance of a Gameplay IR package."""

    id: str
    name: str
    version: str = "0.1.0"
    author: str = "GTA-Anything Clean-Room"
    license: str = "MIT"
    description: str = ""
    source_kind: str = "spec_and_xml"
    target_editions: list[str] = field(
        default_factory=lambda: ["enhanced_gen9", "legacy_gen8"]
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModMeta:
        return cls(
            id=str(data.get("id", "unnamed_mod")),
            name=str(data.get("name", "Unnamed Mod")),
            version=str(data.get("version", "0.1.0")),
            author=str(data.get("author", "GTA-Anything Clean-Room")),
            license=str(data.get("license", "")),
            description=str(data.get("description", "")),
            source_kind=str(data.get("source_kind", "spec_and_xml")),
            target_editions=list(
                data.get("target_editions", ["enhanced_gen9", "legacy_gen8"])
            ),
        )


@dataclass
class InputBindings:
    """Activation hotkey and UI library bindings with conflict avoidance list."""

    activation_key: str = "F9"
    modifier_key: str | None = "LeftShift"
    menu_library: str = "LemonUI"
    avoid_conflicts_with: list[str] = field(
        default_factory=lambda: ["F4", "Insert", "B", "N", "E"]
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputBindings:
        raw_mod = data.get("modifier_key", "LeftShift")
        modifier_key = str(raw_mod) if raw_mod not in (None, "") else None
        return cls(
            activation_key=str(data.get("activation_key", "F9")),
            modifier_key=modifier_key,
            menu_library=str(data.get("menu_library", "LemonUI")),
            avoid_conflicts_with=list(
                data.get("avoid_conflicts_with", ["F4", "Insert", "B", "N", "E"])
            ),
        )


@dataclass
class EntitySlot:
    """World entity contract with mandatory vanilla fallback model and stream timeout."""

    slot_id: str
    role: str
    vanilla_fallback_model: str
    preferred_addon_model: str | None = None
    stream_timeout_ms: int = 5000
    is_player_vehicle: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntitySlot:
        raw_addon = data.get("preferred_addon_model")
        preferred_addon = str(raw_addon) if raw_addon not in (None, "") else None
        raw_fallback = data.get("vanilla_fallback_model", "")
        fallback = "" if raw_fallback is None else str(raw_fallback)
        return cls(
            slot_id=str(data.get("slot_id", "")),
            role=str(data.get("role", "ambient_entity")),
            vanilla_fallback_model=fallback,
            preferred_addon_model=preferred_addon,
            stream_timeout_ms=int(data.get("stream_timeout_ms", 5000)),
            is_player_vehicle=bool(data.get("is_player_vehicle", False)),
        )


@dataclass
class StopNode:
    """Spatial waypoint or dispatch stop node in GTA world coordinates."""

    index: int
    name: str
    x: float
    y: float
    z: float
    dwell_seconds: int = 6

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StopNode:
        return cls(
            index=int(data.get("index", 0)),
            name=str(data.get("name", "Stop")),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            z=float(data.get("z", 0.0)),
            dwell_seconds=int(data.get("dwell_seconds", 6)),
        )


@dataclass
class SpatialTrack:
    """Ordered route or dispatch zone cluster."""

    track_id: str
    name: str
    mode: str = "ordered_stops"
    stops: list[StopNode] = field(default_factory=list)
    fare_or_reward: int = 0
    allowed_vehicle_slots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "name": self.name,
            "mode": self.mode,
            "fare_or_reward": self.fare_or_reward,
            "allowed_vehicle_slots": list(self.allowed_vehicle_slots),
            "stops": [s.to_dict() for s in self.stops],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpatialTrack:
        stops = [
            s if isinstance(s, StopNode) else StopNode.from_dict(s)
            for s in data.get("stops", [])
        ]
        return cls(
            track_id=str(data.get("track_id", "default_track")),
            name=str(data.get("name", "Default Track")),
            mode=str(data.get("mode", "ordered_stops")),
            stops=stops,
            fare_or_reward=int(data.get("fare_or_reward", 0)),
            allowed_vehicle_slots=list(data.get("allowed_vehicle_slots", [])),
        )


@dataclass
class StateNode:
    """A node in the operational lifecycle finite state machine."""

    name: str
    phase: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateNode:
        return cls(
            name=str(data.get("name", "")),
            phase=str(data.get("phase", "operation")),
            description=str(data.get("description", "")),
        )


@dataclass
class TransitionEdge:
    """A directed state transition triggered by an operational event."""

    from_state: str
    to_state: str
    trigger: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransitionEdge:
        return cls(
            from_state=str(data.get("from_state", "")),
            to_state=str(data.get("to_state", "")),
            trigger=str(data.get("trigger", "")),
        )


@dataclass
class StateMachineSpec:
    """Complete operational lifecycle state machine specification."""

    initial_state: str = "Idle"
    states: list[StateNode] = field(default_factory=list)
    transitions: list[TransitionEdge] = field(default_factory=list)
    cleanup_state: str = "Teardown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_state": self.initial_state,
            "cleanup_state": self.cleanup_state,
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateMachineSpec:
        states = [
            s if isinstance(s, StateNode) else StateNode.from_dict(s)
            for s in data.get("states", [])
        ]
        transitions = [
            t if isinstance(t, TransitionEdge) else TransitionEdge.from_dict(t)
            for t in data.get("transitions", [])
        ]
        return cls(
            initial_state=str(data.get("initial_state", "Idle")),
            states=states,
            transitions=transitions,
            cleanup_state=str(data.get("cleanup_state", "Teardown")),
        )


@dataclass
class MenuUISpec:
    """Decoupled UI menu specification (static metadata or 2D sprite only)."""

    title: str = "GTA-Anything Mod Menu"
    subtitle: str = "Select route & vehicle class"
    preview_mode: str = "static_sprite"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MenuUISpec:
        return cls(
            title=str(data.get("title", "GTA-Anything Mod Menu")),
            subtitle=str(data.get("subtitle", "Select route & vehicle class")),
            preview_mode=str(data.get("preview_mode", "static_sprite")),
        )


@dataclass
class EvidenceAnchor:
    """Evidence anchor linking an extracted mechanism to a source document or code range."""

    source_file: str
    locator: str
    extracted_fact: str
    confidence: float = 0.95

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceAnchor:
        return cls(
            source_file=str(data.get("source_file", "")),
            locator=str(data.get("locator", "L1")),
            extracted_fact=str(data.get("extracted_fact", "")),
            confidence=float(data.get("confidence", 0.95)),
        )


@dataclass
class GameplayIR:
    """Top-level Gameplay Intermediate Representation (G-IR v0.1)."""

    meta: ModMeta
    loader_target: str = "shvdn_enhanced"
    inputs: InputBindings = field(default_factory=InputBindings)
    entities: list[EntitySlot] = field(default_factory=list)
    routes_or_zones: list[SpatialTrack] = field(default_factory=list)
    state_machine: StateMachineSpec = field(default_factory=StateMachineSpec)
    ui_spec: MenuUISpec = field(default_factory=MenuUISpec)
    evidence: list[EvidenceAnchor] = field(default_factory=list)
    schema_version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "meta": self.meta.to_dict(),
            "loader_target": self.loader_target,
            "inputs": self.inputs.to_dict(),
            "ui_spec": self.ui_spec.to_dict(),
            "entities": [e.to_dict() for e in self.entities],
            "routes_or_zones": [r.to_dict() for r in self.routes_or_zones],
            "state_machine": self.state_machine.to_dict(),
            "evidence": [ev.to_dict() for ev in self.evidence],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameplayIR:
        meta_raw = data.get("meta", {})
        meta = meta_raw if isinstance(meta_raw, ModMeta) else ModMeta.from_dict(meta_raw)

        inputs_raw = data.get("inputs", {})
        inputs = (
            inputs_raw
            if isinstance(inputs_raw, InputBindings)
            else InputBindings.from_dict(inputs_raw)
        )

        ui_raw = data.get("ui_spec", {})
        ui_spec = (
            ui_raw if isinstance(ui_raw, MenuUISpec) else MenuUISpec.from_dict(ui_raw)
        )

        entities = [
            e if isinstance(e, EntitySlot) else EntitySlot.from_dict(e)
            for e in data.get("entities", [])
        ]
        routes_or_zones = [
            r if isinstance(r, SpatialTrack) else SpatialTrack.from_dict(r)
            for r in data.get("routes_or_zones", [])
        ]
        sm_raw = data.get("state_machine", {})
        state_machine = (
            sm_raw
            if isinstance(sm_raw, StateMachineSpec)
            else StateMachineSpec.from_dict(sm_raw)
        )
        evidence = [
            ev if isinstance(ev, EvidenceAnchor) else EvidenceAnchor.from_dict(ev)
            for ev in data.get("evidence", [])
        ]

        return cls(
            schema_version=str(data.get("schema_version", "0.1.0")),
            meta=meta,
            loader_target=str(data.get("loader_target", "shvdn_enhanced")),
            inputs=inputs,
            ui_spec=ui_spec,
            entities=entities,
            routes_or_zones=routes_or_zones,
            state_machine=state_machine,
            evidence=evidence,
        )

    @classmethod
    def from_json(cls, raw_json: str) -> GameplayIR:
        return cls.from_dict(json.loads(raw_json))


@dataclass
class ValidationReport:
    """Result of static Gameplay IR invariant checks."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_invariants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_gameplay_ir(ir: GameplayIR | dict[str, Any]) -> ValidationReport:
    """Validate all static engineering invariants defined in docs/GAMEPLAY_IR_SPEC.md."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    errors: list[str] = []
    warnings: list[str] = []
    checked_invariants: list[str] = [
        "vanilla_fallback_model_required",
        "ui_spawn_decoupling_no_live_3d_spawn",
        "state_machine_reachability_and_teardown_path",
        "hotkey_conflict_guard",
        "clean_room_license_check",
    ]

    # 1. Clean-room license check
    license_val = (ir_obj.meta.license or "").strip()
    if not license_val or license_val.lower() in {
        "proprietary-unlicensed",
        "unlicensed-proprietary",
        "proprietary",
        "none",
        "unknown",
    }:
        errors.append(
            f"[clean_room_license_check] Invalid or unlicensed meta.license '{ir_obj.meta.license}'. "
            "Must be an explicit open/authorized license (e.g. 'MIT', 'Apache-2.0')."
        )

    if not (ir_obj.meta.id or "").strip():
        errors.append("[meta] meta.id must not be empty.")

    if ir_obj.loader_target not in VALID_LOADER_TARGETS:
        errors.append(
            f"[loader_target] Unsupported loader_target '{ir_obj.loader_target}'. "
            f"Expected one of {sorted(VALID_LOADER_TARGETS)}."
        )

    # 2. Vanilla fallback completeness
    if not ir_obj.entities:
        errors.append(
            "[vanilla_fallback_model_required] entities list must contain at least one EntitySlot."
        )
    slot_ids: set[str] = set()
    for idx, entity in enumerate(ir_obj.entities):
        slot_label = entity.slot_id or f"entities[{idx}]"
        if not entity.slot_id or not _IDENTIFIER_RE.match(entity.slot_id):
            errors.append(
                f"[vanilla_fallback_model_required] Entity '{slot_label}' has an invalid slot_id."
            )
        else:
            slot_ids.add(entity.slot_id)

        fallback = (entity.vanilla_fallback_model or "").strip()
        if (
            not fallback
            or fallback.lower() in {"null", "none"}
            or not _IDENTIFIER_RE.match(fallback)
        ):
            errors.append(
                f"[vanilla_fallback_model_required] Entity slot '{slot_label}' is missing a valid "
                f"vanilla_fallback_model (got '{entity.vanilla_fallback_model}')."
            )
        if entity.stream_timeout_ms <= 0:
            errors.append(
                f"[vanilla_fallback_model_required] Entity slot '{slot_label}' must specify "
                f"stream_timeout_ms > 0 (got {entity.stream_timeout_ms})."
            )

    # 3. UI-Spawn decoupling (prohibit live_3d_spawn)
    preview_mode = (ir_obj.ui_spec.preview_mode or "").strip()
    if preview_mode in FORBIDDEN_PREVIEW_MODES or preview_mode == "live_3d_spawn":
        errors.append(
            "[ui_spawn_decoupling_no_live_3d_spawn] ui_spec.preview_mode 'live_3d_spawn' is strictly "
            "forbidden because synchronous/asynchronous 3D vehicle spawning during menu OnIndexChange "
            "triggers NullReferenceException and streaming leaks. Use 'static_sprite' or 'static_metadata'."
        )
    elif preview_mode not in VALID_PREVIEW_MODES:
        errors.append(
            f"[ui_spawn_decoupling_no_live_3d_spawn] Invalid ui_spec.preview_mode '{preview_mode}'. "
            f"Allowed values: {sorted(VALID_PREVIEW_MODES)}."
        )

    # 4. State machine completeness, forward reachability, and reverse teardown reachability
    sm = ir_obj.state_machine
    state_map: dict[str, StateNode] = {s.name: s for s in sm.states if s.name}
    if not state_map:
        errors.append(
            "[state_machine_reachability_and_teardown_path] state_machine.states cannot be empty."
        )
    else:
        if sm.initial_state not in state_map:
            errors.append(
                f"[state_machine_reachability_and_teardown_path] initial_state '{sm.initial_state}' "
                "does not exist in state_machine.states."
            )
        if sm.cleanup_state not in state_map:
            errors.append(
                f"[state_machine_reachability_and_teardown_path] cleanup_state '{sm.cleanup_state}' "
                "does not exist in state_machine.states."
            )

        forward_adj: dict[str, list[str]] = {name: [] for name in state_map}
        reverse_adj: dict[str, list[str]] = {name: [] for name in state_map}
        for edge in sm.transitions:
            if edge.from_state not in state_map:
                errors.append(
                    f"[state_machine_reachability_and_teardown_path] Transition from unknown state "
                    f"'{edge.from_state}' -> '{edge.to_state}'."
                )
                continue
            if edge.to_state not in state_map:
                errors.append(
                    f"[state_machine_reachability_and_teardown_path] Transition to unknown state "
                    f"'{edge.from_state}' -> '{edge.to_state}'."
                )
                continue
            forward_adj[edge.from_state].append(edge.to_state)
            reverse_adj[edge.to_state].append(edge.from_state)

        # Forward BFS from initial_state
        if sm.initial_state in state_map:
            visited_fwd: set[str] = {sm.initial_state}
            queue_fwd: deque[str] = deque([sm.initial_state])
            while queue_fwd:
                curr = queue_fwd.popleft()
                for nxt in forward_adj.get(curr, []):
                    if nxt not in visited_fwd:
                        visited_fwd.add(nxt)
                        queue_fwd.append(nxt)
            unreachable = [name for name in state_map if name not in visited_fwd]
            if unreachable:
                errors.append(
                    f"[state_machine_reachability_and_teardown_path] Unreachable states from "
                    f"initial_state '{sm.initial_state}': {unreachable}."
                )

        # Reverse BFS from cleanup_state
        if sm.cleanup_state in state_map:
            can_reach_cleanup: set[str] = {sm.cleanup_state}
            queue_rev: deque[str] = deque([sm.cleanup_state])
            while queue_rev:
                curr = queue_rev.popleft()
                for prev in reverse_adj.get(curr, []):
                    if prev not in can_reach_cleanup:
                        can_reach_cleanup.add(prev)
                        queue_rev.append(prev)

            dead_end_states: list[str] = []
            for state_name, node in state_map.items():
                if state_name == sm.cleanup_state:
                    continue
                if node.phase in OPERATIONAL_PHASES_REQUIRING_TEARDOWN or (
                    node.phase not in {"standby", "cleanup"}
                    and state_name != sm.initial_state
                ):
                    if state_name not in can_reach_cleanup:
                        dead_end_states.append(state_name)

            if dead_end_states:
                errors.append(
                    f"[state_machine_reachability_and_teardown_path] States {dead_end_states} have no "
                    f"directed transition path to cleanup_state '{sm.cleanup_state}' (Teardown)."
                )

    # 5. Hotkey conflict check
    act_key = (ir_obj.inputs.activation_key or "").strip()
    act_key_upper = act_key.upper()
    mod_key = (ir_obj.inputs.modifier_key or "").strip()
    avoid_upper = {k.strip().upper() for k in ir_obj.inputs.avoid_conflicts_with if k}

    if not act_key:
        errors.append("[hotkey_conflict_guard] inputs.activation_key must not be empty.")
    elif not mod_key:
        if act_key_upper in HIGH_CONFLICT_SINGLE_KEYS or act_key_upper in avoid_upper:
            reason = HIGH_CONFLICT_SINGLE_KEYS.get(
                act_key_upper, "listed in avoid_conflicts_with"
            )
            warnings.append(
                f"[hotkey_conflict_guard] Unmodified activation_key '{act_key}' conflicts with "
                f"{reason}. Add a modifier_key (e.g. 'LeftShift') or choose a safe function key."
            )

    # 6. Route / zone sanity checks
    for track in ir_obj.routes_or_zones:
        if track.mode not in VALID_TRACK_MODES:
            errors.append(
                f"[routes_or_zones] Track '{track.track_id}' has invalid mode '{track.mode}'. "
                f"Expected one of {sorted(VALID_TRACK_MODES)}."
            )
        if not track.stops:
            warnings.append(
                f"[routes_or_zones] Track '{track.track_id}' has an empty stops list."
            )
        for slot in track.allowed_vehicle_slots:
            if slot_ids and slot not in slot_ids:
                errors.append(
                    f"[routes_or_zones] Track '{track.track_id}' references unknown vehicle slot '{slot}'."
                )

    if not ir_obj.evidence:
        warnings.append(
            "[evidence] GameplayIR contains no EvidenceAnchor records; attach source anchors for traceability."
        )

    return ValidationReport(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        checked_invariants=checked_invariants,
    )
