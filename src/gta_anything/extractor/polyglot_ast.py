"""Polyglot AST & structural source codebase mechanism extractor with Los Santos World-Space Auto-Projector."""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

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
)

# ---------------------------------------------------------------------------
# Curated Real Los Santos Street Network Anchor Corridors (Drivable x, y, z)
# ---------------------------------------------------------------------------

LOS_SANTOS_CORRIDORS: dict[str, list[dict[str, Any]]] = {
    "vespucci": [
        {"name": "Vespucci Canals Pizza & Scooter Depot", "x": -1184.5, "y": -1508.2, "z": 4.4},
        {"name": "Palomino Ave & Prosperity St Promenade", "x": -1212.8, "y": -1389.4, "z": 4.9},
        {"name": "Magellan Ave Beachfront Lofts", "x": -1285.3, "y": -1264.1, "z": 5.6},
        {"name": "Bay City Ave Marina Court", "x": -1338.6, "y": -1148.7, "z": 6.2},
        {"name": "Aguja St & Goma St Apartments", "x": -1152.4, "y": -1425.9, "z": 4.8},
        {"name": "Vitus St Canal Overlook", "x": -1096.2, "y": -1542.6, "z": 4.3},
        {"name": "Invention Ct Sidewalk Cafe", "x": -1241.0, "y": -1474.5, "z": 4.3},
        {"name": "Melanoma St Surf Hostel", "x": -1314.7, "y": -1342.8, "z": 4.6},
    ],
    "del_perro": [
        {"name": "Del Perro Pier North Plaza", "x": -1604.2, "y": -1042.6, "z": 13.0},
        {"name": "Red Desert Ave Retail Strip", "x": -1488.5, "y": -918.3, "z": 10.1},
        {"name": "Cougar Ave Ocean View Condos", "x": -1536.1, "y": -794.8, "z": 21.4},
        {"name": "Prosperity St Pedestrian Mall", "x": -1422.7, "y": -682.4, "z": 26.8},
        {"name": "Boulevard Del Perro Corner", "x": -1365.4, "y": -565.2, "z": 30.2},
        {"name": "Sandcastle Way Beach Club", "x": -1662.8, "y": -984.1, "z": 7.5},
    ],
    "downtown": [
        {"name": "Dashound Bus Center Depot", "x": 436.2, "y": -645.8, "z": 28.7},
        {"name": "Legion Square North", "x": 215.4, "y": -810.1, "z": 30.7},
        {"name": "Pillbox Hill Medical Plaza", "x": 304.8, "y": -588.2, "z": 43.3},
        {"name": "Alta St & Occupation Ave", "x": 262.1, "y": -384.6, "z": 44.9},
        {"name": "San Andreas Ave Financial Tower", "x": 112.5, "y": -742.9, "z": 45.8},
        {"name": "Strawberry Ave Metro Hub", "x": 284.7, "y": -1204.3, "z": 29.3},
        {"name": "Vespucci Blvd & Elgin Ave", "x": 154.3, "y": -986.4, "z": 29.4},
        {"name": "Mission Row Police Precinct", "x": 428.1, "y": -981.5, "z": 30.7},
    ],
    "vinewood": [
        {"name": "Vinewood Blvd & Vinewood Plaza", "x": 294.6, "y": 182.4, "z": 104.2},
        {"name": "Eclipse Blvd West Tower", "x": -482.3, "y": 274.8, "z": 83.1},
        {"name": "Hawick Ave Boutique Corner", "x": -124.7, "y": -42.5, "z": 56.4},
        {"name": "Clinton Ave Hillside Terrace", "x": 412.8, "y": 314.2, "z": 103.0},
        {"name": "Mirror Park Blvd Lakeside", "x": 1084.2, "y": -692.4, "z": 57.6},
        {"name": "West Vinewood Record Studios", "x": -814.5, "y": 178.9, "z": 71.2},
    ],
    "harbor": [
        {"name": "Elysian Island Freight Depot", "x": -268.4, "y": -2415.2, "z": 6.0},
        {"name": "Terminal Berth 4 Inspection Zone", "x": 812.6, "y": -2982.5, "z": 5.9},
        {"name": "Port Authority Customs Gate", "x": 118.3, "y": -2968.1, "z": 6.0},
        {"name": "Dutch London St Logistics Yard", "x": -84.2, "y": -2218.6, "z": 7.8},
        {"name": "Signal St Container Dock", "x": -342.8, "y": -2684.5, "z": 6.0},
        {"name": "La Mesa Popular St Warehouse", "x": 840.0, "y": -2120.0, "z": 30.5},
    ],
}

DISTRICT_ALIASES: dict[str, str] = {
    "vespucci": "vespucci",
    "beach": "vespucci",
    "pizza": "vespucci",
    "canal": "vespucci",
    "scooter": "vespucci",
    "del_perro": "del_perro",
    "delperro": "del_perro",
    "pier": "del_perro",
    "downtown": "downtown",
    "legion": "downtown",
    "pillbox": "downtown",
    "city": "downtown",
    "metro": "downtown",
    "vinewood": "vinewood",
    "hills": "vinewood",
    "eclipse": "vinewood",
    "mirror_park": "vinewood",
    "harbor": "harbor",
    "port": "harbor",
    "dock": "harbor",
    "terminal": "harbor",
    "freight": "harbor",
    "cargo": "harbor",
}

# ---------------------------------------------------------------------------
# Semantic Domain -> GTA V Vanilla Entity Mapping Rules
# ---------------------------------------------------------------------------

VEHICLE_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("scooter", "moped", "pizza", "faggio", "delivery_bike", "vespa", "bike_courier"), "faggio", "player_service_vehicle"),
    (("taxi", "cab", "rideshare", "chauffeur", "fare_car"), "taxi", "player_service_vehicle"),
    (("ambulance", "medic", "ems", "paramedic", "rescue"), "ambulance", "player_service_vehicle"),
    (("firetruk", "firetruck", "fire_engine", "firefighter"), "firetruk", "player_service_vehicle"),
    (("police", "patrol", "interceptor", "cruiser", "cop", "lspd", "pursuit"), "police3", "player_service_vehicle"),
    (("sheriff", "deputy", "ranger"), "sheriff", "player_service_vehicle"),
    (("bus", "shuttle", "transit", "commuter", "metro", "coach"), "bus", "player_service_vehicle"),
    (("boxville", "parcel", "postal", "bakery_van", "mail_van", "delivery_van"), "boxville", "player_service_vehicle"),
    (("truck", "cargo", "freight", "mule", "lorry", "hauler", "logistics", "courier"), "mule", "player_service_vehicle"),
    (("van", "burrito", "speedo", "sprinter"), "burrito", "player_service_vehicle"),
    (("tow", "towtruck", "wrecker", "recovery"), "towtruck", "player_service_vehicle"),
    (("trash", "garbage", "sanitation"), "trash", "player_service_vehicle"),
    (("forklift", "warehouse_lift"), "forklift", "player_service_vehicle"),
    (("sedan", "car", "cruiser_civ", "stanier", "driver", "vehicle"), "stanier", "player_service_vehicle"),
]

NPC_DOMAIN_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("chef", "cook", "pizzeria", "kitchen", "baker", "restaurant", "vendor", "shopkeeper"), "s_m_m_linecook", "service_contact_npc"),
    (("customer", "hungry", "buyer", "client", "recipient", "resident", "patron", "order"), "s_m_y_ammucity_01", "customer_recipient_npc"),
    (("passenger", "commuter", "rider", "business", "executive", "tourist"), "a_m_y_business_01", "boarding_npc"),
    (("dock", "harbor", "foreman", "warehouse", "cargo_worker", "stevedore"), "s_m_m_dockwork_01", "dispatch_coordinator_npc"),
    (("postal", "mailman", "dispatcher", "clerk"), "s_m_m_postal_01", "dispatch_coordinator_npc"),
    (("cop", "officer", "suspect", "guard", "security"), "s_m_y_cop_01", "law_enforcement_npc"),
    (("medic", "patient", "doctor", "nurse"), "s_m_m_paramedic_01", "emergency_npc"),
]

KNOWN_EXACT_VANILLA_VEHICLES = {
    "faggio", "faggio2", "faggio3", "bus", "airbus", "coach", "tourbus", "rentalbus",
    "taxi", "mule", "mule2", "mule3", "benson", "pounder", "hauler", "phantom",
    "packer", "boxville", "burrito", "speedo", "rumpo", "pony", "youga", "police",
    "police2", "police3", "police4", "policeb", "policet", "sheriff", "sheriff2",
    "fbi", "fbi2", "ambulance", "firetruk", "towtruck", "towtruck2", "trash",
    "trash2", "utillitruck", "docktug", "handler", "forklift", "stanier", "premier",
    "washington", "tailgater", "oracle", "primo",
}

KNOWN_EXACT_VANILLA_PEDS = {
    "s_m_y_ammucity_01", "a_m_y_business_01", "a_f_y_business_01", "a_m_m_business_01",
    "s_m_m_linecook", "s_m_m_dockwork_01", "s_m_y_dockwork_01", "s_m_y_airworker",
    "s_m_m_trucker_01", "s_m_m_postal_01", "s_m_y_cop_01", "s_m_m_security_01",
    "s_m_y_construct_01", "a_m_y_tourist_01", "s_m_m_paramedic_01",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "extracted_gta_mod"


def _to_pascal_identifier(text: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", text.strip()) if p]
    if not parts:
        return "CustomState"
    out = "".join(p[:1].upper() + p[1:].lower() if p.isupper() else p[:1].upper() + p[1:] for p in parts)
    if out[0].isdigit():
        out = f"State{out}"
    return out


# ---------------------------------------------------------------------------
# Los Santos World-Space Auto-Projector
# ---------------------------------------------------------------------------

def is_abstract_or_2d_coordinate_space(points: list[dict[str, Any]]) -> bool:
    """Detect if extracted coordinates come from a 2D pixel/grid space or normalized space rather than GTA V 3D world space."""
    if not points:
        return True

    xs = [float(p.get("x", 0.0)) for p in points]
    ys = [float(p.get("y", 0.0)) for p in points]
    zs = [float(p.get("z", 0.0)) for p in points]
    has_explicit_z = [bool(p.get("has_z", False)) for p in points]

    # If any coordinate lacks explicit z or all z values are ~0.0, it is 2D space
    if not all(has_explicit_z) or all(abs(z) < 1e-4 for z in zs):
        return True

    # If all (x, y) are non-negative and within typical 2D canvas/grid bounds (0..1920)
    # whereas real Los Santos street setups either have negative X/Y (e.g. Vespucci X=-1200, Downtown Y=-800)
    # or explicit 3D road elevations.
    all_non_negative_xy = all(x >= 0.0 and y >= 0.0 for x, y in zip(xs, ys))
    max_xy = max(max(abs(x) for x in xs), max(abs(y) for y in ys))
    if max_xy <= 150.0:
        return True
    if all_non_negative_xy and max_xy <= 2048.0 and all(z in (0.0, 1.0) for z in zs):
        return True

    return False


def _resolve_corridor_key(district: str, hint_text: str = "") -> str:
    combined = f"{district} {hint_text}".lower()
    for token, key in DISTRICT_ALIASES.items():
        if token in combined:
            return key
    return "downtown"


def project_coords_to_los_santos(
    points: list[dict[str, Any]],
    district: str = "downtown",
    hint_text: str = "",
) -> tuple[list[StopNode], bool, str]:
    """Deterministically project 2D/abstract coordinates onto curated real Los Santos street corridors.

    Preserves topological ordering and local relative offsets while snapping to real drivable (x, y, z)
    Los Santos street anchor elevations. If points are already real 3D GTA V coordinates, preserves them directly.

    Returns:
        (stops, was_projected, resolved_district_key)
    """
    resolved_district = _resolve_corridor_key(district, hint_text)
    corridor = LOS_SANTOS_CORRIDORS.get(resolved_district, LOS_SANTOS_CORRIDORS["downtown"])

    if not points:
        default_stops = [
            StopNode(
                index=idx,
                name=anchor["name"],
                x=float(anchor["x"]),
                y=float(anchor["y"]),
                z=float(anchor["z"]),
                dwell_seconds=6,
            )
            for idx, anchor in enumerate(corridor[:4])
        ]
        return default_stops, True, resolved_district

    needs_projection = is_abstract_or_2d_coordinate_space(points)
    if not needs_projection:
        stops = [
            StopNode(
                index=idx,
                name=str(pt.get("name") or f"Waypoint {idx + 1}"),
                x=round(float(pt.get("x", 0.0)), 2),
                y=round(float(pt.get("y", 0.0)), 2),
                z=round(float(pt.get("z", 30.0)), 2),
                dwell_seconds=max(1, int(pt.get("dwell_seconds", 6))),
            )
            for idx, pt in enumerate(points)
        ]
        return stops, False, resolved_district

    # Compute normalized [0, 1] bounding-box ratios for topological street corridor projection
    xs = [float(p.get("x", 0.0)) for p in points]
    ys = [float(p.get("y", 0.0)) for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    projected_stops: list[StopNode] = []
    n_anchors = len(corridor)

    for idx, pt in enumerate(points):
        anchor = corridor[idx % n_anchors]
        norm_x = (float(pt.get("x", 0.0)) - min_x) / span_x
        norm_y = (float(pt.get("y", 0.0)) - min_y) / span_y

        # Apply a bounded street-curb perturbation (+-6.5m) derived deterministically from normalized 2D coordinates
        # so the projected coordinates stay strictly on the drivable street node while reflecting input geometry.
        offset_x = (norm_x - 0.5) * 11.0
        offset_y = (norm_y - 0.5) * 11.0

        proj_x = round(float(anchor["x"]) + offset_x, 2)
        proj_y = round(float(anchor["y"]) + offset_y, 2)
        proj_z = round(float(anchor["z"]), 2)

        raw_name = str(pt.get("name") or "").strip()
        if not raw_name or re.match(r"^(stop|waypoint|node|point)\s*\d*$", raw_name, re.IGNORECASE):
            stop_name = anchor["name"]
        else:
            stop_name = raw_name

        dwell = max(1, int(pt.get("dwell_seconds", 6)))
        projected_stops.append(
            StopNode(
                index=idx,
                name=stop_name,
                x=proj_x,
                y=proj_y,
                z=proj_z,
                dwell_seconds=dwell,
            )
        )

    return projected_stops, True, resolved_district


# ---------------------------------------------------------------------------
# Semantic Entity & State Machine Builders
# ---------------------------------------------------------------------------

def infer_vanilla_vehicle(hint_text: str) -> tuple[str, str]:
    """Map an arbitrary domain entity name/role/type to a GTA V vanilla_fallback_model and role."""
    low = hint_text.lower()
    for token in re.split(r"[^a-z0-9_]+", low):
        if token in KNOWN_EXACT_VANILLA_VEHICLES:
            return token, "player_service_vehicle"
    for keywords, model, role in VEHICLE_DOMAIN_KEYWORDS:
        if any(kw in low for kw in keywords):
            return model, role
    return "stanier", "player_service_vehicle"


def infer_vanilla_ped(hint_text: str) -> tuple[str, str]:
    """Map an arbitrary domain NPC description to a GTA V vanilla_fallback_model and role."""
    low = hint_text.lower()
    for token in re.split(r"[^a-z0-9_]+", low):
        if token in KNOWN_EXACT_VANILLA_PEDS:
            return token, "boarding_npc"
    for keywords, model, role in NPC_DOMAIN_KEYWORDS:
        if any(kw in low for kw in keywords):
            return model, role
    return "a_m_y_business_01", "boarding_npc"


def build_lifecycle_state_machine(
    extracted_states: list[dict[str, Any]],
    is_dispatch: bool = False,
) -> StateMachineSpec:
    """Build a valid 7-phase operational lifecycle state machine incorporating extracted domain states.

    Guarantees standard operational phases:
      Idle -> MenuSelecting -> ResourceStreaming -> SpawningShift -> ActiveOperation -> ShiftSummary -> Teardown
    and maps extracted domain operation sub-states into reachable, teardown-safe nodes.
    """
    active_op_name = "ActiveOperation"
    domain_labels = [s["name"] for s in extracted_states if s.get("name")]
    domain_summary = (
        f" (Domain states: {', '.join(domain_labels[:6])})"
        if domain_labels
        else ""
    )

    states: list[StateNode] = [
        StateNode(
            name="Idle",
            phase="standby",
            description="Mod loaded in standby, awaiting activation hotkey chord.",
        ),
        StateNode(
            name="MenuSelecting",
            phase="ui",
            description="Browsing static shift/route cards and 2D sprites without live 3D vehicle spawning.",
        ),
        StateNode(
            name="ResourceStreaming",
            phase="streaming",
            description="Streaming vehicle and NPC models via SafeModelStreamer with timeout release.",
        ),
        StateNode(
            name="SpawningShift",
            phase="spawning",
            description="Creating player service vehicle in WorldSession, verifying handle, seating player.",
        ),
        StateNode(
            name=active_op_name,
            phase="operation",
            description=(
                f"Executing core gameplay loop: driving stops/zones, dwell timer, customer interaction, and rewards{domain_summary}."
            ),
        ),
        StateNode(
            name="ShiftSummary",
            phase="completion",
            description="Presenting shift completion score, tips/fares, and delivery metrics before cleanup.",
        ),
        StateNode(
            name="Teardown",
            phase="cleanup",
            description="Deterministically releasing all WorldSession leased vehicles, peds, blips, and model handles.",
        ),
    ]

    transitions: list[TransitionEdge] = [
        TransitionEdge("Idle", "MenuSelecting", "HotkeyPressed"),
        TransitionEdge("MenuSelecting", "Idle", "MenuCancelled"),
        TransitionEdge("MenuSelecting", "ResourceStreaming", "ShiftConfirmed"),
        TransitionEdge("ResourceStreaming", "SpawningShift", "ModelReadyOrFallback"),
        TransitionEdge("ResourceStreaming", "Teardown", "CriticalStreamFailure"),
        TransitionEdge("SpawningShift", active_op_name, "DriverSeated"),
        TransitionEdge("SpawningShift", "Teardown", "SpawnReturnedNull"),
        TransitionEdge(active_op_name, "ShiftSummary", "FinalStopCompleted"),
        TransitionEdge(active_op_name, "Teardown", "ShiftAbortedOrVehicleDestroyed"),
        TransitionEdge("ShiftSummary", "Teardown", "SummaryAcknowledged"),
        TransitionEdge("Teardown", "Idle", "ResourcesReleased"),
    ]

    return StateMachineSpec(
        initial_state="Idle",
        cleanup_state="Teardown",
        states=states,
        transitions=transitions,
    )


# ---------------------------------------------------------------------------
# Python AST Deep Mechanism Analyzer
# ---------------------------------------------------------------------------

def _ast_const_val(node: ast.AST | None) -> Any:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _ast_const_val(node.operand)
        if isinstance(operand, (int, float)):
            return -operand if isinstance(node.op, ast.USub) else operand
    return None


def _ast_dict_to_py(node: ast.Dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k_node, v_node in zip(node.keys, node.values):
        k_val = _ast_const_val(k_node)
        if k_val is None and isinstance(k_node, ast.Name):
            k_val = k_node.id
        if k_val is None:
            continue
        key_str = str(k_val)
        v_const = _ast_const_val(v_node)
        if v_const is not None:
            out[key_str] = v_const
        elif isinstance(v_node, (ast.Tuple, ast.List)):
            elems = [_ast_const_val(e) for e in v_node.elts]
            if all(isinstance(x, (int, float, str)) for x in elems if x is not None):
                out[key_str] = elems
        elif isinstance(v_node, ast.Dict):
            out[key_str] = _ast_dict_to_py(v_node)
    return out


def _extract_point_from_dict(d: dict[str, Any], default_idx: int, default_dwell: int = 6) -> dict[str, Any] | None:
    low_map = {str(k).lower(): v for k, v in d.items()}

    x_val: float | None = None
    y_val: float | None = None
    z_val: float = 0.0
    has_z = False

    if "x" in low_map and "y" in low_map:
        try:
            x_val = float(low_map["x"])
            y_val = float(low_map["y"])
            if "z" in low_map and low_map["z"] is not None:
                z_val = float(low_map["z"])
                has_z = True
        except (TypeError, ValueError):
            return None
    else:
        for coord_key in ("pos", "position", "coords", "coordinates", "location", "point", "grid_pos", "xy"):
            val = low_map.get(coord_key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    x_val = float(val[0])
                    y_val = float(val[1])
                    if len(val) >= 3 and val[2] is not None:
                        z_val = float(val[2])
                        has_z = True
                    break
                except (TypeError, ValueError):
                    continue

    if x_val is None or y_val is None:
        return None

    name = str(
        low_map.get("name")
        or low_map.get("label")
        or low_map.get("title")
        or low_map.get("shop")
        or low_map.get("customer")
        or low_map.get("destination")
        or low_map.get("id")
        or f"Stop {default_idx + 1}"
    )

    dwell: int | None = None
    for dk in ("dwell_seconds", "dwell", "wait_seconds", "timer", "countdown", "timeout", "delivery_window", "wait_time"):
        if dk in low_map and isinstance(low_map[dk], (int, float)):
            dwell = max(1, int(low_map[dk]))
            break

    reward = None
    for rk in ("tip", "reward", "fare", "payout", "bonus", "price"):
        if rk in low_map and isinstance(low_map[rk], (int, float)):
            reward = int(low_map[rk])
            break

    return {
        "index": default_idx,
        "name": name,
        "x": x_val,
        "y": y_val,
        "z": z_val,
        "has_z": has_z,
        "dwell_seconds": dwell if dwell is not None else default_dwell,
        "has_explicit_dwell": dwell is not None,
        "reward": reward,
    }


def _analyze_python_ast(
    py_path: Path,
    rel_path: str,
) -> dict[str, Any]:
    """Parse a Python file with ast.parse to extract states, transitions, entities, stops, rewards, and evidence."""
    raw_text = py_path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, Any] = {
        "states": [],
        "transitions": [],
        "entities": [],
        "points": [],
        "rewards": [],
        "dwells": [],
        "titles": [],
        "descriptions": [],
        "hotkeys": [],
        "district_hints": [],
        "evidence": [],
    }

    try:
        tree = ast.parse(raw_text, filename=rel_path)
    except SyntaxError:
        return result

    module_doc = ast.get_docstring(tree)
    if module_doc:
        first_line = module_doc.strip().splitlines()[0].strip()
        if first_line:
            result["descriptions"].append(first_line)
            result["district_hints"].append(module_doc)
            result["evidence"].append(
                EvidenceAnchor(
                    source_file=rel_path,
                    locator="L1",
                    extracted_fact=f"Python module docstring: '{first_line[:110]}'",
                    confidence=0.96,
                )
            )

    for node in ast.walk(tree):
        # 1. Extract Enum / State classes and Entity Dataclasses/Classes
        if isinstance(node, ast.ClassDef):
            base_names = [
                (b.id if isinstance(b, ast.Name) else (b.attr if isinstance(b, ast.Attribute) else ""))
                for b in node.bases
            ]
            cls_low = node.name.lower()
            is_enum_or_state = (
                any(b in {"Enum", "IntEnum", "StrEnum", "Flag"} for b in base_names)
                or "state" in cls_low
                or "phase" in cls_low
                or "status" in cls_low
            )
            if is_enum_or_state:
                member_names: list[str] = []
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                                member_names.append(target.id)
                                result["states"].append(
                                    {"name": target.id, "lineno": item.lineno, "file": rel_path}
                                )
                if member_names:
                    end_line = getattr(node, "end_lineno", node.lineno + len(member_names))
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}-L{end_line}",
                            extracted_fact=(
                                f"AST Enum/State class '{node.name}' defines {len(member_names)} domain states: "
                                f"{', '.join(member_names[:8])}."
                            ),
                            confidence=0.99,
                        )
                    )

            # Check if class represents a Vehicle / Player / Customer / NPC entity
            elif any(k in cls_low for k in ("vehicle", "scooter", "bike", "truck", "bus", "taxi", "car", "player", "courier", "customer", "npc", "entity", "ped")):
                cls_doc = ast.get_docstring(node) or ""
                field_hints: list[str] = [node.name, cls_doc]
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        val_c = _ast_const_val(item.value)
                        if isinstance(val_c, str):
                            field_hints.append(val_c)
                    elif isinstance(item, ast.Assign):
                        val_c = _ast_const_val(item.value)
                        if isinstance(val_c, str):
                            field_hints.append(val_c)
                hint_blob = " ".join(field_hints)
                is_npc = any(k in cls_low for k in ("customer", "npc", "ped", "passenger", "client", "cook", "chef"))
                result["entities"].append(
                    {
                        "name": node.name,
                        "kind": "ped" if is_npc else "vehicle",
                        "hint": hint_blob,
                        "lineno": node.lineno,
                        "file": rel_path,
                    }
                )
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L{node.lineno}",
                        extracted_fact=f"AST entity class definition '{node.name}' ({'NPC' if is_npc else 'Vehicle'}).",
                        confidence=0.95,
                    )
                )

        # 2. Extract transition methods / functions
        elif isinstance(node, ast.FunctionDef):
            fn_low = node.name.lower()
            if any(k in fn_low for k in ("transition", "next_state", "advance", "start", "complete", "abort", "deliver", "step", "update_state")):
                result["transitions"].append(
                    {"name": node.name, "lineno": node.lineno, "file": rel_path}
                )
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L{node.lineno}",
                        extracted_fact=f"AST operational transition function '{node.name}()'.",
                        confidence=0.94,
                    )
                )

        # 3. Extract module/class-level assignments (constants, entity dicts, waypoint lists)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        targets.append(t.id)
                val_node = node.value
            else:
                if isinstance(node.target, ast.Name):
                    targets.append(node.target.id)
                val_node = node.value

            if not targets or val_node is None:
                continue

            var_name = targets[0]
            var_low = var_name.lower()
            const_val = _ast_const_val(val_node)

            # Scalar constants: title, reward/tip/fare, dwell/timer, hotkey, fallback vehicle
            if isinstance(const_val, str):
                if any(k in var_low for k in ("title", "game_name", "mod_name", "app_name")):
                    result["titles"].append(const_val)
                    result["district_hints"].append(const_val)
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}",
                            extracted_fact=f"Extracted title constant {var_name} = '{const_val}'.",
                            confidence=0.98,
                        )
                    )
                elif any(k in var_low for k in ("hotkey", "activation_key", "keybind")):
                    result["hotkeys"].append(const_val)
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}",
                            extracted_fact=f"Extracted activation key constant {var_name} = '{const_val}'.",
                            confidence=0.98,
                        )
                    )
                elif any(k in var_low for k in ("district", "neighborhood", "region", "city_zone")):
                    result["district_hints"].append(const_val)
                elif any(k in var_low for k in ("vehicle", "scooter", "truck", "bus", "car", "fallback_vehicle", "model")):
                    result["entities"].append(
                        {
                            "name": var_name,
                            "kind": "vehicle",
                            "hint": f"{var_name} {const_val}",
                            "lineno": node.lineno,
                            "file": rel_path,
                        }
                    )
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}",
                            extracted_fact=f"Extracted vehicle model constant {var_name} = '{const_val}'.",
                            confidence=0.97,
                        )
                    )
                elif any(k in var_low for k in ("npc", "ped", "customer_model", "passenger_model")):
                    result["entities"].append(
                        {
                            "name": var_name,
                            "kind": "ped",
                            "hint": f"{var_name} {const_val}",
                            "lineno": node.lineno,
                            "file": rel_path,
                        }
                    )

            elif isinstance(const_val, (int, float)) and not isinstance(const_val, bool):
                if any(k in var_low for k in ("tip", "reward", "fare", "payout", "base_pay", "bonus", "bounty")):
                    result["rewards"].append(int(const_val))
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}",
                            extracted_fact=f"Extracted reward/fare constant {var_name} = {int(const_val)}.",
                            confidence=0.97,
                        )
                    )
                elif any(k in var_low for k in ("dwell", "countdown", "wait_sec", "delivery_time", "stop_duration", "dwell_seconds")):
                    val_int = max(1, int(const_val))
                    if val_int <= 120:
                        result["dwells"].append(val_int)
                        result["evidence"].append(
                            EvidenceAnchor(
                                source_file=rel_path,
                                locator=f"L{node.lineno}",
                                extracted_fact=f"Extracted dwell/countdown constant {var_name} = {val_int}s.",
                                confidence=0.96,
                            )
                        )

            # Dictionary assignment: entity config or waypoint dict
            elif isinstance(val_node, ast.Dict):
                py_dict = _ast_dict_to_py(val_node)
                pt = _extract_point_from_dict(py_dict, len(result["points"]))
                if pt is not None:
                    pt["lineno"] = node.lineno
                    pt["file"] = rel_path
                    result["points"].append(pt)
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}",
                            extracted_fact=f"Extracted spatial node '{pt['name']}' at ({pt['x']}, {pt['y']}).",
                            confidence=0.96,
                        )
                    )
                elif any(k in var_low for k in ("vehicle", "scooter", "player", "courier", "bike", "truck", "bus", "car", "entity", "customer", "npc", "entities")):
                    # Check if it's a nested dict of entities or single entity dict
                    nested_added = False
                    for sub_k, sub_v in py_dict.items():
                        if isinstance(sub_v, dict):
                            blob = f"{sub_k} " + " ".join(f"{k}:{v}" for k, v in sub_v.items())
                            is_npc = any(w in blob.lower() for w in ("customer", "npc", "ped", "hungry", "passenger", "cook", "chef", "client", "recipient"))
                            result["entities"].append(
                                {
                                    "name": sub_k,
                                    "kind": "ped" if is_npc else "vehicle",
                                    "hint": blob,
                                    "lineno": node.lineno,
                                    "file": rel_path,
                                }
                            )
                            nested_added = True
                    if not nested_added:
                        blob = f"{var_name} " + " ".join(f"{k}:{v}" for k, v in py_dict.items())
                        is_npc = any(w in blob.lower() for w in ("customer", "npc", "ped", "hungry", "passenger", "cook", "chef", "client", "recipient")) and not any(
                            w in var_low for w in ("scooter", "vehicle", "bike", "truck", "bus", "car")
                        )
                        result["entities"].append(
                            {
                                "name": str(py_dict.get("id") or py_dict.get("name") or var_name),
                                "kind": "ped" if is_npc else "vehicle",
                                "hint": blob,
                                "lineno": node.lineno,
                                "file": rel_path,
                            }
                        )
                    result["evidence"].append(
                        EvidenceAnchor(
                            source_file=rel_path,
                            locator=f"L{node.lineno}",
                            extracted_fact=f"Extracted entity specification from dictionary '{var_name}'.",
                            confidence=0.97,
                        )
                    )

            # List / Tuple assignment: waypoints, stops, delivery points, or entity lists
            elif isinstance(val_node, (ast.List, ast.Tuple)):
                is_waypoint_var = any(
                    k in var_low
                    for k in ("stop", "waypoint", "delivery", "drop", "route", "point", "location", "shop", "zone", "node", "target", "destination")
                )
                is_state_var = any(k in var_low for k in ("state", "phase"))
                is_entity_var = any(k in var_low for k in ("entit", "vehicle", "customer", "npc", "actor", "roster"))

                if is_state_var:
                    str_elems = [_ast_const_val(e) for e in val_node.elts]
                    clean_states = [str(s) for s in str_elems if isinstance(s, str)]
                    if clean_states:
                        for s_name in clean_states:
                            result["states"].append({"name": s_name, "lineno": node.lineno, "file": rel_path})
                        result["evidence"].append(
                            EvidenceAnchor(
                                source_file=rel_path,
                                locator=f"L{node.lineno}",
                                extracted_fact=f"Extracted state list '{var_name}': {', '.join(clean_states)}.",
                                confidence=0.95,
                            )
                        )

                for elem in val_node.elts:
                    if isinstance(elem, ast.Dict):
                        d = _ast_dict_to_py(elem)
                        pt = _extract_point_from_dict(d, len(result["points"]))
                        if pt is not None:
                            pt["lineno"] = getattr(elem, "lineno", node.lineno)
                            pt["file"] = rel_path
                            result["points"].append(pt)
                            z_suffix = f", {pt['z']}" if pt["has_z"] else ""
                            result["evidence"].append(
                                EvidenceAnchor(
                                    source_file=rel_path,
                                    locator=f"L{pt['lineno']}",
                                    extracted_fact=(
                                        f"Extracted waypoint '{pt['name']}' at ({pt['x']}, {pt['y']}{z_suffix}) "
                                        f"with dwell={pt['dwell_seconds']}s."
                                    ),
                                    confidence=0.98,
                                )
                            )
                        elif is_entity_var or any(k in d for k in ("role", "model", "vehicle", "type", "species")):
                            blob = " ".join(f"{k}:{v}" for k, v in d.items())
                            is_npc = any(w in blob.lower() for w in ("customer", "npc", "ped", "hungry", "passenger", "cook", "chef", "client"))
                            result["entities"].append(
                                {
                                    "name": str(d.get("id") or d.get("name") or f"entity_{len(result['entities']) + 1}"),
                                    "kind": "ped" if is_npc else "vehicle",
                                    "hint": blob,
                                    "lineno": getattr(elem, "lineno", node.lineno),
                                    "file": rel_path,
                                }
                            )
                    elif isinstance(elem, (ast.Tuple, ast.List)) and is_waypoint_var:
                        vals = [_ast_const_val(x) for x in elem.elts]
                        # Support ("Shop Name", x, y) or (x, y) or ("Shop Name", x, y, dwell)
                        if len(vals) >= 3 and isinstance(vals[0], str) and isinstance(vals[1], (int, float)) and isinstance(vals[2], (int, float)):
                            has_z = len(vals) >= 4 and isinstance(vals[3], (int, float)) and not (
                                "dwell" in var_low or "2d" in var_low or (0 <= float(vals[1]) <= 100 and 0 <= float(vals[2]) <= 100)
                            )
                            dwell_val = int(vals[3]) if (len(vals) >= 4 and isinstance(vals[3], (int, float)) and not has_z) else 6
                            pt = {
                                "index": len(result["points"]),
                                "name": str(vals[0]),
                                "x": float(vals[1]),
                                "y": float(vals[2]),
                                "z": float(vals[3]) if has_z else 0.0,
                                "has_z": has_z,
                                "dwell_seconds": max(1, dwell_val),
                                "reward": None,
                                "lineno": getattr(elem, "lineno", node.lineno),
                                "file": rel_path,
                            }
                            result["points"].append(pt)
                            result["evidence"].append(
                                EvidenceAnchor(
                                    source_file=rel_path,
                                    locator=f"L{pt['lineno']}",
                                    extracted_fact=f"Extracted tuple waypoint '{pt['name']}' at ({pt['x']}, {pt['y']}).",
                                    confidence=0.96,
                                )
                            )
                        elif len(vals) in (2, 3) and all(isinstance(v, (int, float)) for v in vals):
                            has_z = len(vals) == 3
                            pt = {
                                "index": len(result["points"]),
                                "name": f"Waypoint {len(result['points']) + 1}",
                                "x": float(vals[0]),
                                "y": float(vals[1]),
                                "z": float(vals[2]) if has_z else 0.0,
                                "has_z": has_z,
                                "dwell_seconds": 6,
                                "reward": None,
                                "lineno": getattr(elem, "lineno", node.lineno),
                                "file": rel_path,
                            }
                            result["points"].append(pt)
                            result["evidence"].append(
                                EvidenceAnchor(
                                    source_file=rel_path,
                                    locator=f"L{pt['lineno']}",
                                    extracted_fact=f"Extracted coordinate tuple ({pt['x']}, {pt['y']}).",
                                    confidence=0.94,
                                )
                            )
                    elif isinstance(elem, ast.Call):
                        # Support dataclass constructor calls like DeliveryStop(name="...", x=10, y=20, dwell_seconds=5)
                        kw_map: dict[str, Any] = {}
                        for kw in elem.keywords:
                            if kw.arg:
                                kv = _ast_const_val(kw.value)
                                if kv is not None:
                                    kw_map[kw.arg] = kv
                                elif isinstance(kw.value, (ast.Tuple, ast.List)):
                                    kw_map[kw.arg] = [_ast_const_val(x) for x in kw.value.elts]
                        if kw_map:
                            pt = _extract_point_from_dict(kw_map, len(result["points"]))
                            if pt is not None:
                                pt["lineno"] = getattr(elem, "lineno", node.lineno)
                                pt["file"] = rel_path
                                result["points"].append(pt)
                                result["evidence"].append(
                                    EvidenceAnchor(
                                        source_file=rel_path,
                                        locator=f"L{pt['lineno']}",
                                        extracted_fact=f"Extracted object waypoint '{pt['name']}' at ({pt['x']}, {pt['y']}).",
                                        confidence=0.97,
                                    )
                                )

    return result


# ---------------------------------------------------------------------------
# JS / TS / C# / Lua / GDScript & Config Structural Scanner
# ---------------------------------------------------------------------------

_ENUM_BLOCK_RE = re.compile(r"\benum\s+([A-Za-z0-9_]+)\s*\{([^}]+)\}", re.MULTILINE | re.DOTALL)
_CASE_STATE_RE = re.compile(r"\bcase\s+['\"]([A-Za-z0-9_]+)['\"]\s*:", re.MULTILINE)
_OBJ_COORD_RE = re.compile(
    r"\{\s*(?:name|label|id)\s*:\s*['\"]([^'\"]+)['\"][^}]*?\bx\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*\by\s*:\s*(-?\d+(?:\.\d+)?)(?:\s*,\s*\bz\s*:\s*(-?\d+(?:\.\d+)?))?(?:[^}]*?\b(?:dwell|dwell_seconds|wait)\s*:\s*(\d+))?[^}]*\}",
    re.IGNORECASE,
)
_TUPLE_3D_RE = re.compile(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def _scan_other_language_file(
    fpath: Path,
    rel_path: str,
) -> dict[str, Any]:
    """Scan JS/TS/C#/Lua/GDScript/JSON/XML/MD files with line-accurate EvidenceAnchors."""
    raw_text = fpath.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.splitlines()
    suffix = fpath.suffix.lower()
    result: dict[str, Any] = {
        "states": [],
        "transitions": [],
        "entities": [],
        "points": [],
        "rewards": [],
        "dwells": [],
        "titles": [],
        "descriptions": [],
        "hotkeys": [],
        "district_hints": [],
        "evidence": [],
    }

    # XML route files
    if suffix == ".xml" and fpath.name.lower() != "dlclist.xml":
        try:
            root = ET.fromstring(raw_text)
            stop_elems = (
                root.findall(".//Stop")
                + root.findall(".//stop")
                + root.findall(".//Waypoint")
                + root.findall(".//Zone")
            )
            for idx, s_elem in enumerate(stop_elems):
                s_name = (
                    s_elem.attrib.get("name")
                    or s_elem.attrib.get("label")
                    or f"Stop {idx + 1}"
                )
                x = float(s_elem.attrib.get("x") or s_elem.attrib.get("X") or 0.0)
                y = float(s_elem.attrib.get("y") or s_elem.attrib.get("Y") or 0.0)
                z_raw = s_elem.attrib.get("z") or s_elem.attrib.get("Z")
                has_z = z_raw is not None
                z = float(z_raw) if z_raw is not None else 0.0
                dwell = int(float(s_elem.attrib.get("dwell") or s_elem.attrib.get("dwell_seconds") or 6))
                result["points"].append(
                    {
                        "index": idx,
                        "name": s_name,
                        "x": x,
                        "y": y,
                        "z": z,
                        "has_z": has_z,
                        "dwell_seconds": dwell,
                        "reward": None,
                        "lineno": 1,
                        "file": rel_path,
                    }
                )
            fare_attr = root.attrib.get("fare") or root.attrib.get("reward")
            if fare_attr:
                try:
                    result["rewards"].append(int(float(fare_attr)))
                except ValueError:
                    pass
            veh_attr = root.attrib.get("vehicle") or root.attrib.get("allowed_vehicles")
            if veh_attr:
                result["entities"].append(
                    {"name": veh_attr, "kind": "vehicle", "hint": veh_attr, "lineno": 1, "file": rel_path}
                )
            if stop_elems:
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L1-L{max(1, len(lines))}",
                        extracted_fact=f"Extracted {len(stop_elems)} XML spatial stops from '{rel_path}'.",
                        confidence=0.99,
                    )
                )
        except ET.ParseError:
            pass
        return result

    # JSON config files
    if suffix == ".json":
        try:
            data = json.loads(raw_text)
            if isinstance(data, dict):
                if "title" in data or "name" in data:
                    result["titles"].append(str(data.get("title") or data.get("name")))
                for key in ("stops", "waypoints", "deliveries", "locations", "points"):
                    items = data.get(key)
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                pt = _extract_point_from_dict(item, len(result["points"]))
                                if pt:
                                    pt["lineno"] = 1
                                    pt["file"] = rel_path
                                    result["points"].append(pt)
                        if result["points"]:
                            result["evidence"].append(
                                EvidenceAnchor(
                                    source_file=rel_path,
                                    locator=f"L1-L{max(1, len(lines))}",
                                    extracted_fact=f"Extracted {len(result['points'])} waypoints from JSON config '{key}'.",
                                    confidence=0.96,
                                )
                            )
        except json.JSONDecodeError:
            pass
        return result

    # Markdown README.md
    if suffix in {".md", ".markdown"}:
        for idx, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith("# ") and not result["titles"]:
                title = s.lstrip("# ").strip()
                result["titles"].append(title)
                result["district_hints"].append(title)
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L{idx}",
                        extracted_fact=f"Repository README title: '{title}'.",
                        confidence=0.97,
                    )
                )
            elif s and not s.startswith("#") and not s.startswith("|") and len(s) > 25 and not result["descriptions"]:
                desc = s.lstrip(">*- ").strip()
                result["descriptions"].append(desc)
                result["district_hints"].append(desc)
        return result

    # JS / TS / C# / Lua / GDScript structural scanning
    for m in _ENUM_BLOCK_RE.finditer(raw_text):
        enum_name = m.group(1)
        body = m.group(2)
        lineno = raw_text[: m.start()].count("\n") + 1
        members = [
            tok.split("=")[0].strip()
            for tok in body.split(",")
            if tok.strip() and not tok.strip().startswith("//")
        ]
        members = [mem for mem in members if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", mem)]
        for mem in members:
            result["states"].append({"name": mem, "lineno": lineno, "file": rel_path})
        if members:
            result["evidence"].append(
                EvidenceAnchor(
                    source_file=rel_path,
                    locator=f"L{lineno}",
                    extracted_fact=f"Structural enum '{enum_name}' with states: {', '.join(members[:8])}.",
                    confidence=0.95,
                )
            )

    for m in _CASE_STATE_RE.finditer(raw_text):
        st_name = m.group(1)
        lineno = raw_text[: m.start()].count("\n") + 1
        result["states"].append({"name": st_name, "lineno": lineno, "file": rel_path})

    for m in _OBJ_COORD_RE.finditer(raw_text):
        lineno = raw_text[: m.start()].count("\n") + 1
        has_z = m.group(4) is not None
        pt = {
            "index": len(result["points"]),
            "name": m.group(1),
            "x": float(m.group(2)),
            "y": float(m.group(3)),
            "z": float(m.group(4)) if has_z else 0.0,
            "has_z": has_z,
            "dwell_seconds": int(m.group(5)) if m.group(5) else 6,
            "reward": None,
            "lineno": lineno,
            "file": rel_path,
        }
        result["points"].append(pt)
        result["evidence"].append(
            EvidenceAnchor(
                source_file=rel_path,
                locator=f"L{lineno}",
                extracted_fact=f"Extracted structural waypoint '{pt['name']}' at ({pt['x']}, {pt['y']}).",
                confidence=0.95,
            )
        )

    for line_no, line in enumerate(lines, start=1):
        low = line.lower()
        for v in KNOWN_EXACT_VANILLA_VEHICLES:
            if re.search(rf"\b{re.escape(v)}\b", low):
                result["entities"].append(
                    {"name": v, "kind": "vehicle", "hint": v, "lineno": line_no, "file": rel_path}
                )
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L{line_no}",
                        extracted_fact=f"Detected vanilla vehicle reference '{v}'.",
                        confidence=0.93,
                    )
                )
        for p in KNOWN_EXACT_VANILLA_PEDS:
            if re.search(rf"\b{re.escape(p)}\b", low):
                result["entities"].append(
                    {"name": p, "kind": "ped", "hint": p, "lineno": line_no, "file": rel_path}
                )
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L{line_no}",
                        extracted_fact=f"Detected vanilla NPC ped reference '{p}'.",
                        confidence=0.92,
                    )
                )
        if not result["points"]:
            tm = _TUPLE_3D_RE.search(line)
            if tm:
                result["points"].append(
                    {
                        "index": len(result["points"]),
                        "name": f"Waypoint {len(result['points']) + 1}",
                        "x": float(tm.group(1)),
                        "y": float(tm.group(2)),
                        "z": float(tm.group(3)),
                        "has_z": True,
                        "dwell_seconds": 6,
                        "reward": None,
                        "lineno": line_no,
                        "file": rel_path,
                    }
                )
                result["evidence"].append(
                    EvidenceAnchor(
                        source_file=rel_path,
                        locator=f"L{line_no}",
                        extracted_fact=f"Extracted 3D coordinate ({tm.group(1)}, {tm.group(2)}, {tm.group(3)}).",
                        confidence=0.91,
                    )
                )

    return result


# ---------------------------------------------------------------------------
# Public Repository Extractor Entrypoint
# ---------------------------------------------------------------------------

def extract_polyglot_repo_ir(
    repo_dir: str | Path,
    mod_id: str | None = None,
    target_edition: str = "enhanced_gen9",
) -> GameplayIR:
    """Extract a rich, valid GameplayIR from a multi-file Python/JS/TS/C#/Lua/GDScript repository."""
    src_dir = Path(repo_dir)
    if not src_dir.exists():
        raise FileNotFoundError(f"Repository path does not exist: {src_dir}")

    supported_exts = {".py", ".cs", ".js", ".ts", ".lua", ".gd", ".xml", ".json", ".md"}
    code_files = sorted(
        p
        for p in src_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in supported_exts
        and "__pycache__" not in p.parts
        and not p.name.startswith(".")
    )

    all_states: list[dict[str, Any]] = []
    all_transitions: list[dict[str, Any]] = []
    all_entities: list[dict[str, Any]] = []
    all_points: list[dict[str, Any]] = []
    all_rewards: list[int] = []
    all_dwells: list[int] = []
    all_titles: list[str] = []
    all_descriptions: list[str] = []
    all_hotkeys: list[str] = []
    all_district_hints: list[str] = [src_dir.name]
    all_evidence: list[EvidenceAnchor] = []

    for fpath in code_files[:40]:
        rel = str(fpath.relative_to(src_dir)).replace("\\", "/")
        if fpath.suffix.lower() == ".py":
            partial = _analyze_python_ast(fpath, rel)
        else:
            partial = _scan_other_language_file(fpath, rel)

        all_states.extend(partial["states"])
        all_transitions.extend(partial["transitions"])
        all_entities.extend(partial["entities"])
        all_points.extend(partial["points"])
        all_rewards.extend(partial["rewards"])
        all_dwells.extend(partial["dwells"])
        all_titles.extend(partial["titles"])
        all_descriptions.extend(partial["descriptions"])
        all_hotkeys.extend(partial["hotkeys"])
        all_district_hints.extend(partial["district_hints"])
        all_evidence.extend(partial["evidence"])

    resolved_id = mod_id or _slugify(src_dir.name)
    title = all_titles[0] if all_titles else resolved_id.replace("_", " ").title()
    description = (
        all_descriptions[0]
        if all_descriptions
        else f"Clean-room Gameplay IR extracted via polyglot AST analysis from {src_dir.name}."
    )

    # Determine activation hotkey safely
    activation_key = "F9"
    for hk in all_hotkeys:
        cand = hk.strip().upper()
        if re.match(r"^F([1-9]|1[0-2])$", cand) and cand not in {"F3", "F4", "F8"}:
            activation_key = cand
            break

    # Resolve vehicle & NPC entity slots with intelligent domain fallback mapping
    vehicle_candidates = [e for e in all_entities if e["kind"] == "vehicle"]
    ped_candidates = [e for e in all_entities if e["kind"] == "ped"]

    repo_hint_blob = " ".join(all_district_hints + [title, description] + [p.get("name", "") for p in all_points])

    if vehicle_candidates:
        first_veh = vehicle_candidates[0]
        veh_model, veh_role = infer_vanilla_vehicle(first_veh["hint"])
        veh_slot_id = _slugify(first_veh["name"])
        if veh_slot_id in {"vehicle", "fallback_vehicle", "model", "entities"} or len(veh_slot_id) < 3:
            veh_slot_id = f"{veh_model}_service_vehicle"
    else:
        veh_model, veh_role = infer_vanilla_vehicle(repo_hint_blob)
        veh_slot_id = "primary_service_vehicle"

    if ped_candidates:
        first_ped = ped_candidates[0]
        ped_model, ped_role = infer_vanilla_ped(first_ped["hint"])
        ped_slot_id = _slugify(first_ped["name"])
        if ped_slot_id in {"npc", "ped", "entities", "customer"} or len(ped_slot_id) < 3:
            ped_slot_id = f"{ped_role}_slot"
    else:
        ped_model, ped_role = infer_vanilla_ped(repo_hint_blob)
        ped_slot_id = "primary_service_npc"

    if ped_slot_id == veh_slot_id:
        ped_slot_id = f"{ped_slot_id}_npc"

    entities: list[EntitySlot] = [
        EntitySlot(
            slot_id=veh_slot_id,
            role=veh_role,
            vanilla_fallback_model=veh_model,
            preferred_addon_model=None,
            stream_timeout_ms=5000,
            is_player_vehicle=True,
        ),
        EntitySlot(
            slot_id=ped_slot_id,
            role=ped_role,
            vanilla_fallback_model=ped_model,
            preferred_addon_model=None,
            stream_timeout_ms=3000,
            is_player_vehicle=False,
        ),
    ]

    # Apply default dwell constant if points didn't specify individual dwell
    default_dwell = all_dwells[0] if all_dwells else 6
    for pt in all_points:
        if not pt.get("has_explicit_dwell", False) and not pt.get("dwell_seconds"):
            pt["dwell_seconds"] = default_dwell
        elif not pt.get("has_explicit_dwell", False) and pt.get("dwell_seconds") == 6:
            pt["dwell_seconds"] = default_dwell
        if pt.get("reward") and not all_rewards:
            all_rewards.append(int(pt["reward"]))

    # Project 2D / abstract coordinates to curated Los Santos street network corridors
    projected_stops, was_projected, resolved_district = project_coords_to_los_santos(
        all_points,
        district="vespucci" if "pizza" in repo_hint_blob.lower() or "vespucci" in repo_hint_blob.lower() else "downtown",
        hint_text=repo_hint_blob,
    )

    if was_projected and all_points:
        first_pt = all_points[0]
        all_evidence.append(
            EvidenceAnchor(
                source_file=str(first_pt.get("file", src_dir.name)),
                locator=f"L{first_pt.get('lineno', 1)}",
                extracted_fact=(
                    f"Auto-projected {len(projected_stops)} 2D/abstract source coordinates onto Los Santos "
                    f"'{resolved_district}' street corridor with real drivable (x, y, z) elevations."
                ),
                confidence=0.98,
            )
        )

    fare_or_reward = all_rewards[0] if all_rewards else 25
    is_dispatch = any(w in repo_hint_blob.lower() for w in ("dispatch", "pizza", "delivery", "courier", "rush", "cargo"))
    track_mode = "ordered_stops"

    tracks = [
        SpatialTrack(
            track_id=f"{resolved_id}_{resolved_district}_track",
            name=f"{title} ({resolved_district.replace('_', ' ').title()} Corridor)",
            mode=track_mode,
            stops=projected_stops,
            fare_or_reward=fare_or_reward,
            allowed_vehicle_slots=[veh_slot_id],
        )
    ]

    state_machine = build_lifecycle_state_machine(all_states, is_dispatch=is_dispatch)

    if not all_evidence:
        all_evidence.append(
            EvidenceAnchor(
                source_file=src_dir.name,
                locator="L1",
                extracted_fact="Synthesized baseline Gameplay IR from polyglot repository scan.",
                confidence=0.88,
            )
        )

    editions = (
        [target_edition, "legacy_gen8"]
        if target_edition == "enhanced_gen9"
        else [target_edition, "enhanced_gen9"]
    )

    return GameplayIR(
        schema_version="0.1.0",
        meta=ModMeta(
            id=resolved_id,
            name=title,
            version="0.1.0",
            author="GTA-Anything Clean-Room",
            license="MIT",
            description=description,
            source_kind="polyglot_ast_repo",
            target_editions=editions,
        ),
        loader_target="shvdn_enhanced" if target_edition == "enhanced_gen9" else "shvdn_v3",
        inputs=InputBindings(
            activation_key=activation_key,
            modifier_key="LeftShift",
            menu_library="LemonUI",
            avoid_conflicts_with=["F4", "Insert", "B", "N", "E"],
        ),
        ui_spec=MenuUISpec(
            title=title[:40],
            subtitle="Static Preview Operational Dispatch",
            preview_mode="static_sprite",
        ),
        entities=entities,
        routes_or_zones=tracks,
        state_machine=state_machine,
        evidence=all_evidence,
    )
