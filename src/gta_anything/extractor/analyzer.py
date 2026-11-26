"""Evidence-backed Gameplay IR extractor for Markdown specs, route XML files, JSON IRs, and source repos."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from gta_anything.extractor.polyglot_ast import (
    extract_polyglot_repo_ir,
    project_coords_to_los_santos,
)
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


KNOWN_VANILLA_VEHICLES = [
    "bus",
    "airbus",
    "coach",
    "tourbus",
    "rentalbus",
    "mule",
    "mule2",
    "mule3",
    "benson",
    "pounder",
    "hauler",
    "phantom",
    "packer",
    "boxville",
    "burrito",
    "speedo",
    "taxi",
    "police",
    "police2",
    "police3",
    "policet",
    "fbi",
    "sheriff",
    "ambulance",
    "firetruk",
    "towtruck",
    "trash",
    "utillitruck",
    "docktug",
    "handler",
    "forklift",
]

KNOWN_VANILLA_PEDS = [
    "a_m_y_business_01",
    "a_f_y_business_01",
    "a_m_m_business_01",
    "s_m_m_dockwork_01",
    "s_m_y_dockwork_01",
    "s_m_y_airworker",
    "s_m_m_trucker_01",
    "s_m_m_postal_01",
    "s_m_y_cop_01",
    "s_m_m_security_01",
    "s_m_y_construct_01",
    "a_m_y_tourist_01",
]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "extracted_gta_mod"


def _default_state_machine(is_dispatch: bool = False) -> StateMachineSpec:
    active_name = "ActiveDispatch" if is_dispatch else "ActiveRoute"
    active_desc = (
        "On-duty dispatch operation: driving to zone, inspecting cargo, interacting with coordinator."
        if is_dispatch
        else "Driving ordered stops, handling dwell timer, doors, passenger boarding, and fares."
    )
    summary_name = "ShiftSummary"
    return StateMachineSpec(
        initial_state="Idle",
        cleanup_state="Teardown",
        states=[
            StateNode(
                name="Idle",
                phase="standby",
                description="Mod loaded, waiting for activation hotkey chord.",
            ),
            StateNode(
                name="MenuSelecting",
                phase="ui",
                description="Browsing static route/dispatch cards and 2D sprites without live 3D entity spawning.",
            ),
            StateNode(
                name="ResourceStreaming",
                phase="streaming",
                description="Requesting vehicle and NPC models with timeout and mandatory handle release.",
            ),
            StateNode(
                name="SpawningShift",
                phase="spawning",
                description="Spawning service vehicle in WorldSession, checking non-null handle, seating driver.",
            ),
            StateNode(
                name=active_name,
                phase="operation",
                description=active_desc,
            ),
            StateNode(
                name=summary_name,
                phase="completion",
                description="Recording shift completion metrics and fare/reward tally before teardown.",
            ),
            StateNode(
                name="Teardown",
                phase="cleanup",
                description="Deterministically releasing all WorldSession leased vehicles, peds, blips, and models.",
            ),
        ],
        transitions=[
            TransitionEdge("Idle", "MenuSelecting", "HotkeyPressed"),
            TransitionEdge("MenuSelecting", "Idle", "MenuCancelled"),
            TransitionEdge("MenuSelecting", "ResourceStreaming", "ShiftConfirmed"),
            TransitionEdge("ResourceStreaming", "SpawningShift", "ModelReadyOrFallback"),
            TransitionEdge("ResourceStreaming", "Teardown", "CriticalStreamFailure"),
            TransitionEdge("SpawningShift", active_name, "DriverSeated"),
            TransitionEdge("SpawningShift", "Teardown", "SpawnReturnedNull"),
            TransitionEdge(active_name, summary_name, "FinalStopCompleted"),
            TransitionEdge(active_name, "Teardown", "ShiftAbortedOrVehicleDestroyed"),
            TransitionEdge(summary_name, "Teardown", "SummaryAcknowledged"),
            TransitionEdge("Teardown", "Idle", "ResourcesReleased"),
        ],
    )


def _parse_xml_route_file(
    xml_path: Path,
    rel_name: str,
    default_slot_id: str,
) -> tuple[list[SpatialTrack], list[EvidenceAnchor]]:
    tracks: list[SpatialTrack] = []
    evidence: list[EvidenceAnchor] = []
    raw_text = xml_path.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.splitlines()

    root = ET.fromstring(raw_text)
    route_elems = (
        [root]
        if root.tag.lower() in {"route", "transitroute", "track", "dispatchroute"}
        else (
            root.findall(".//Route")
            or root.findall(".//route")
            or root.findall(".//Track")
            or [root]
        )
    )

    for r_idx, r_elem in enumerate(route_elems):
        track_id = (
            r_elem.attrib.get("id")
            or r_elem.attrib.get("track_id")
            or r_elem.findtext("Id")
            or r_elem.findtext("id")
            or f"{_slugify(xml_path.stem)}_{r_idx + 1}"
        ).strip()
        track_name = (
            r_elem.attrib.get("name")
            or r_elem.findtext("Name")
            or r_elem.findtext("name")
            or xml_path.stem.replace("_", " ").title()
        ).strip()
        fare_raw = (
            r_elem.attrib.get("fare")
            or r_elem.attrib.get("fare_or_reward")
            or r_elem.attrib.get("reward")
            or r_elem.findtext("Fare")
            or r_elem.findtext("fare")
            or r_elem.findtext("Reward")
            or "15"
        )
        try:
            fare = int(float(str(fare_raw).strip()))
        except ValueError:
            fare = 15

        mode = (
            r_elem.attrib.get("mode")
            or r_elem.findtext("Mode")
            or "ordered_stops"
        ).strip()
        if mode not in {"ordered_stops", "dispatch_zones"}:
            mode = "ordered_stops"

        allowed_raw = (
            r_elem.attrib.get("allowed_vehicle_slots")
            or r_elem.attrib.get("allowed_vehicles")
            or r_elem.attrib.get("vehicle_slot")
            or r_elem.findtext("AllowedVehicleSlots")
            or r_elem.findtext("AllowedVehicles")
            or ""
        ).strip()
        if allowed_raw:
            allowed_slots = [s.strip() for s in allowed_raw.split(",") if s.strip()]
        else:
            allowed_slots = [default_slot_id]

        # Collect stops
        stop_elems = (
            r_elem.findall(".//Stop")
            + r_elem.findall(".//stop")
            + r_elem.findall(".//Waypoint")
            + r_elem.findall(".//Zone")
        )
        stops: list[StopNode] = []
        for s_idx, s_elem in enumerate(stop_elems):
            s_name = (
                s_elem.attrib.get("name")
                or s_elem.attrib.get("label")
                or s_elem.findtext("Name")
                or s_elem.findtext("name")
                or f"Stop {s_idx + 1}"
            ).strip()
            idx_raw = (
                s_elem.attrib.get("index")
                or s_elem.attrib.get("order")
                or s_elem.attrib.get("id")
                or s_elem.findtext("Index")
                or str(s_idx)
            )
            try:
                stop_index = int(re.sub(r"[^0-9]", "", str(idx_raw)) or s_idx)
            except ValueError:
                stop_index = s_idx

            def _coord(axis: str) -> float:
                val = (
                    s_elem.attrib.get(axis)
                    or s_elem.attrib.get(axis.upper())
                    or s_elem.attrib.get(f"pos{axis.upper()}")
                    or s_elem.findtext(axis)
                    or s_elem.findtext(axis.upper())
                )
                if val is not None:
                    try:
                        return float(val)
                    except ValueError:
                        return 0.0
                pos_elem = s_elem.find("Position") or s_elem.find("Coordinates")
                if pos_elem is not None:
                    pval = pos_elem.attrib.get(axis) or pos_elem.attrib.get(axis.upper())
                    if pval is not None:
                        try:
                            return float(pval)
                        except ValueError:
                            return 0.0
                return 0.0

            dwell_raw = (
                s_elem.attrib.get("dwell_seconds")
                or s_elem.attrib.get("dwell")
                or s_elem.attrib.get("dwellSeconds")
                or s_elem.attrib.get("wait_seconds")
                or s_elem.findtext("DwellSeconds")
                or s_elem.findtext("dwell_seconds")
                or "6"
            )
            try:
                dwell = int(float(str(dwell_raw).strip()))
            except ValueError:
                dwell = 6

            stops.append(
                StopNode(
                    index=stop_index,
                    name=s_name,
                    x=_coord("x"),
                    y=_coord("y"),
                    z=_coord("z"),
                    dwell_seconds=dwell,
                )
            )

        tracks.append(
            SpatialTrack(
                track_id=track_id,
                name=track_name,
                mode=mode,
                stops=stops,
                fare_or_reward=fare,
                allowed_vehicle_slots=allowed_slots,
            )
        )
        evidence.append(
            EvidenceAnchor(
                source_file=rel_name,
                locator=f"L1-L{max(1, len(lines))}",
                extracted_fact=(
                    f"Extracted route '{track_name}' ({track_id}) with {len(stops)} ordered stops "
                    f"and fare/reward={fare} from XML."
                ),
                confidence=0.99,
            )
        )

    return tracks, evidence


def _extract_from_markdown_and_xml(
    md_path: Path,
    base_dir: Path,
    mod_id: str | None,
    target_edition: str,
) -> GameplayIR:
    raw_md = md_path.read_text(encoding="utf-8", errors="replace")
    md_lines = raw_md.splitlines()
    rel_md = md_path.name if md_path.parent == base_dir else str(md_path.relative_to(base_dir)).replace("\\", "/")

    evidence: list[EvidenceAnchor] = []

    # 1. Extract title and description from Markdown
    title = md_path.parent.name.replace("_", " ").title()
    description = "Extracted clean-room operational loop from specification."
    for idx, line in enumerate(md_lines, start=1):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("# ").strip()
            evidence.append(
                EvidenceAnchor(
                    source_file=rel_md,
                    locator=f"L{idx}",
                    extracted_fact=f"Mod title specification: '{title}'",
                    confidence=0.98,
                )
            )
            break

    for idx, line in enumerate(md_lines, start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("|") and len(stripped) > 25:
            description = stripped.lstrip(">*- ").strip()
            evidence.append(
                EvidenceAnchor(
                    source_file=rel_md,
                    locator=f"L{idx}",
                    extracted_fact=f"Gameplay summary: {description[:120]}",
                    confidence=0.95,
                )
            )
            break

    lower_md = raw_md.lower()
    is_dispatch = (
        "dispatch" in lower_md
        or "courier" in lower_md
        or "harbor" in lower_md
        or "callout" in lower_md
    ) and "shuttle" not in lower_md

    resolved_mod_id = mod_id or _slugify(
        md_path.parent.name if md_path.name.lower() == "spec.md" else md_path.stem
    )

    # 2. Extract hotkey & modifier from spec if mentioned
    activation_key = "F10" if is_dispatch else "F9"
    modifier_key: str | None = "LeftShift"
    key_match = re.search(r"\b(F[1-9]|F1[0-2])\b", raw_md)
    if key_match:
        candidate_key = key_match.group(1).upper()
        if candidate_key not in {"F4", "F3", "F8"}:
            activation_key = candidate_key

    # 3. Extract entities (vehicles & peds) from spec with line anchors
    found_vehicles: list[tuple[str, int]] = []
    found_peds: list[tuple[str, int]] = []
    for idx, line in enumerate(md_lines, start=1):
        line_low = line.lower()
        for v in KNOWN_VANILLA_VEHICLES:
            if re.search(rf"\b{re.escape(v)}\b", line_low):
                if v not in [x[0] for x in found_vehicles]:
                    found_vehicles.append((v, idx))
        for p in KNOWN_VANILLA_PEDS:
            if re.search(rf"\b{re.escape(p)}\b", line_low):
                if p not in [x[0] for x in found_peds]:
                    found_peds.append((p, idx))

    if not found_vehicles:
        default_veh = "mule" if is_dispatch else "bus"
        found_vehicles.append((default_veh, 1))
    if not found_peds:
        default_ped = "s_m_m_dockwork_01" if is_dispatch else "a_m_y_business_01"
        found_peds.append((default_ped, 1))

    primary_veh, primary_veh_line = found_vehicles[0]
    primary_slot_id = "courier_service_truck" if is_dispatch else "transit_coach_primary"
    entities: list[EntitySlot] = [
        EntitySlot(
            slot_id=primary_slot_id,
            role="player_service_vehicle",
            vanilla_fallback_model=primary_veh,
            preferred_addon_model=None,
            stream_timeout_ms=5000,
            is_player_vehicle=True,
        )
    ]
    evidence.append(
        EvidenceAnchor(
            source_file=rel_md,
            locator=f"L{primary_veh_line}",
            extracted_fact=f"Primary player service vehicle slot '{primary_slot_id}' bound to vanilla fallback '{primary_veh}'.",
            confidence=0.97,
        )
    )

    if len(found_vehicles) > 1:
        sec_veh, sec_line = found_vehicles[1]
        sec_slot_id = "secondary_service_vehicle"
        entities.append(
            EntitySlot(
                slot_id=sec_slot_id,
                role="alternate_service_vehicle",
                vanilla_fallback_model=sec_veh,
                preferred_addon_model=None,
                stream_timeout_ms=5000,
                is_player_vehicle=True,
            )
        )
        evidence.append(
            EvidenceAnchor(
                source_file=rel_md,
                locator=f"L{sec_line}",
                extracted_fact=f"Alternate service vehicle slot '{sec_slot_id}' bound to vanilla fallback '{sec_veh}'.",
                confidence=0.95,
            )
        )

    ped_model, ped_line = found_peds[0]
    ped_slot_id = "harbor_coordinator_npc" if is_dispatch else "commuter_passenger"
    ped_role = "dispatch_coordinator_npc" if is_dispatch else "boarding_npc"
    entities.append(
        EntitySlot(
            slot_id=ped_slot_id,
            role=ped_role,
            vanilla_fallback_model=ped_model,
            preferred_addon_model=None,
            stream_timeout_ms=3000,
            is_player_vehicle=False,
        )
    )
    evidence.append(
        EvidenceAnchor(
            source_file=rel_md,
            locator=f"L{ped_line}",
            extracted_fact=f"NPC entity slot '{ped_slot_id}' ({ped_role}) bound to vanilla fallback '{ped_model}'.",
            confidence=0.96,
        )
    )

    # 4. Discover and parse sibling route XML files (`routes/*.xml` or `*.xml`)
    xml_files: list[Path] = []
    routes_dir = base_dir / "routes"
    if routes_dir.is_dir():
        xml_files.extend(sorted(routes_dir.glob("*.xml")))
    xml_files.extend(
        sorted(p for p in base_dir.glob("*.xml") if p.name.lower() != "dlclist.xml")
    )

    tracks: list[SpatialTrack] = []
    allowed_vehicle_slots = [e.slot_id for e in entities if e.is_player_vehicle]
    for xml_file in xml_files:
        rel_xml = str(xml_file.relative_to(base_dir)).replace("\\", "/")
        parsed_tracks, xml_evidence = _parse_xml_route_file(
            xml_file, rel_xml, primary_slot_id
        )
        for t in parsed_tracks:
            # Ensure allowed_vehicle_slots map to valid entity slot_ids
            valid_slots = [s for s in t.allowed_vehicle_slots if s in allowed_vehicle_slots]
            t.allowed_vehicle_slots = valid_slots or list(allowed_vehicle_slots)
            tracks.append(t)
        evidence.extend(xml_evidence)

    # 5. If no XML files found, extract coordinates from Markdown or synthesize clean-room track
    if not tracks:
        coord_pattern = re.compile(
            r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)"
        )
        md_stops: list[StopNode] = []
        for idx, line in enumerate(md_lines, start=1):
            m = coord_pattern.search(line)
            if m:
                x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
                label_part = line[: m.start()].strip("|-*#0123456789.:() \t")
                stop_name = label_part.split("|")[0].strip() if label_part else f"Node {len(md_stops) + 1}"
                md_stops.append(
                    StopNode(
                        index=len(md_stops),
                        name=stop_name or f"Node {len(md_stops) + 1}",
                        x=x,
                        y=y,
                        z=z,
                        dwell_seconds=8 if is_dispatch else 6,
                    )
                )
                evidence.append(
                    EvidenceAnchor(
                        source_file=rel_md,
                        locator=f"L{idx}",
                        extracted_fact=f"Spatial node '{stop_name}' at ({x}, {y}, {z}).",
                        confidence=0.94,
                    )
                )

        if not md_stops:
            if is_dispatch:
                md_stops = [
                    StopNode(0, "Elysian Island Freight Depot", -268.4, -2415.2, 6.0, 8),
                    StopNode(1, "Terminal Berth 4 Inspection Zone", 812.6, -2982.5, 5.9, 10),
                    StopNode(2, "Port Authority Customs Gate", 118.3, -2968.1, 6.0, 6),
                ]
            else:
                md_stops = [
                    StopNode(0, "Dashound Bus Center", 436.2, -645.8, 28.7, 6),
                    StopNode(1, "Legion Square North", 215.4, -810.1, 30.7, 8),
                    StopNode(2, "Pillbox Hill Medical", 304.8, -588.2, 43.3, 6),
                ]

        tracks.append(
            SpatialTrack(
                track_id="harbor_dispatch_sector_a" if is_dispatch else "ls_downtown_loop",
                name="Port of Los Santos Courier Dispatch" if is_dispatch else "Los Santos Downtown Shuttle Loop",
                mode="dispatch_zones" if is_dispatch else "ordered_stops",
                stops=md_stops,
                fare_or_reward=120 if is_dispatch else 15,
                allowed_vehicle_slots=list(allowed_vehicle_slots),
            )
        )

    state_machine = _default_state_machine(is_dispatch=is_dispatch)
    evidence.append(
        EvidenceAnchor(
            source_file=rel_md,
            locator=f"L1-L{max(1, len(md_lines))}",
            extracted_fact=(
                f"Constructed 7-state operational lifecycle ({state_machine.initial_state} -> "
                f"... -> {state_machine.cleanup_state}) with static UI preview decoupling."
            ),
            confidence=0.96,
        )
    )

    editions = ["enhanced_gen9", "legacy_gen8"]
    if target_edition not in editions:
        editions.insert(0, target_edition)
    elif editions[0] != target_edition:
        editions = [target_edition, *[e for e in editions if e != target_edition]]

    loader_target = "shvdn_enhanced" if target_edition == "enhanced_gen9" else "shvdn_v3"
    source_kind = "spec_and_xml" if xml_files else "markdown_spec"

    return GameplayIR(
        schema_version="0.1.0",
        meta=ModMeta(
            id=resolved_mod_id,
            name=title,
            version="0.1.0",
            author="GTA-Anything Clean-Room",
            license="MIT",
            description=description,
            source_kind=source_kind,
            target_editions=editions,
        ),
        loader_target=loader_target,
        inputs=InputBindings(
            activation_key=activation_key,
            modifier_key=modifier_key,
            menu_library="LemonUI",
            avoid_conflicts_with=["F4", "Insert", "B", "N", "E"],
        ),
        ui_spec=MenuUISpec(
            title=title[:40],
            subtitle="Select route/zone & service vehicle (Static Preview)",
            preview_mode="static_sprite",
        ),
        entities=entities,
        routes_or_zones=tracks,
        state_machine=state_machine,
        evidence=evidence,
    )


def _extract_from_source_directory(
    src_dir: Path,
    mod_id: str | None,
    target_edition: str,
) -> GameplayIR:
    """Delegate source codebase extraction to the Polyglot AST & Los Santos Auto-Projector engine."""
    return extract_polyglot_repo_ir(
        repo_dir=src_dir,
        mod_id=mod_id,
        target_edition=target_edition,
    )


def extract_gameplay_ir(
    source_path: str | Path,
    mod_id: str | None = None,
    target_edition: str = "enhanced_gen9",
) -> GameplayIR:
    """Extract an evidence-backed GameplayIR from a JSON file, Markdown spec + XML route, or source directory."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Source path for extraction does not exist: {path}")

    # 1. Direct JSON IR file
    if path.is_file() and path.suffix.lower() == ".json":
        raw_text = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw_text)
        ir = GameplayIR.from_dict(data)
        if mod_id:
            ir.meta.id = mod_id
        if target_edition and target_edition not in ir.meta.target_editions:
            ir.meta.target_editions.insert(0, target_edition)
        if not ir.evidence:
            ir.evidence.append(
                EvidenceAnchor(
                    source_file=path.name,
                    locator=f"L1-L{max(1, len(raw_text.splitlines()))}",
                    extracted_fact=f"Loaded pre-defined Gameplay IR '{ir.meta.id}'.",
                    confidence=1.0,
                )
            )
        return ir

    # 2. Markdown spec file (plus sibling routes/*.xml if present)
    if path.is_file() and path.suffix.lower() in {".md", ".markdown"}:
        return _extract_from_markdown_and_xml(
            md_path=path,
            base_dir=path.parent,
            mod_id=mod_id,
            target_edition=target_edition,
        )

    # 3. Direct XML route file (plus sibling spec.md if present)
    if path.is_file() and path.suffix.lower() == ".xml":
        base_dir = path.parent.parent if path.parent.name.lower() == "routes" else path.parent
        sibling_spec = base_dir / "spec.md"
        if sibling_spec.is_file():
            return _extract_from_markdown_and_xml(
                md_path=sibling_spec,
                base_dir=base_dir,
                mod_id=mod_id,
                target_edition=target_edition,
            )
        return _extract_from_source_directory(
            src_dir=path.parent,
            mod_id=mod_id or _slugify(path.stem),
            target_edition=target_edition,
        )

    # 4. Directory input
    if path.is_dir():
        spec_md = path / "spec.md"
        if spec_md.is_file():
            return _extract_from_markdown_and_xml(
                md_path=spec_md,
                base_dir=path,
                mod_id=mod_id,
                target_edition=target_edition,
            )
        ir_json = path / "gameplay_ir.json"
        if ir_json.is_file():
            return extract_gameplay_ir(ir_json, mod_id=mod_id, target_edition=target_edition)
        return _extract_from_source_directory(
            src_dir=path,
            mod_id=mod_id,
            target_edition=target_edition,
        )

    # 5. Single code file fallback
    return _extract_from_source_directory(
        src_dir=path.parent,
        mod_id=mod_id or _slugify(path.stem),
        target_edition=target_edition,
    )
