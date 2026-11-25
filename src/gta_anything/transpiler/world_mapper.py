"""GTA V World-Model semantic mapper and vanilla entity catalog."""

from __future__ import annotations

import re
from typing import Any

from gta_anything.models.ir import GameplayIR
from gta_anything.models.manifest import ACCEPTANCE_LAYERS


VANILLA_VEHICLE_CATALOG: dict[str, dict[str, Any]] = {
    "bus": {"class": "Service", "seat_capacity": 16, "doors": 2, "label": "Brute Bus"},
    "airbus": {"class": "Service", "seat_capacity": 16, "doors": 2, "label": "Brute Airport Bus"},
    "coach": {"class": "Service", "seat_capacity": 10, "doors": 2, "label": "Brute Dashound Coach"},
    "tourbus": {"class": "Service", "seat_capacity": 8, "doors": 2, "label": "Brute Tourbus"},
    "rentalbus": {"class": "Service", "seat_capacity": 10, "doors": 2, "label": "Brute Rental Shuttle Bus"},
    "taxi": {"class": "Service", "seat_capacity": 4, "doors": 4, "label": "Vapid Taxi"},
    "trash": {"class": "Service", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Trashmaster"},
    "mule": {"class": "Commercial", "seat_capacity": 2, "doors": 4, "label": "Maibatsu Mule"},
    "mule2": {"class": "Commercial", "seat_capacity": 2, "doors": 2, "label": "Maibatsu Mule (Ramp)"},
    "mule3": {"class": "Commercial", "seat_capacity": 2, "doors": 4, "label": "Maibatsu Mule (Heist)"},
    "benson": {"class": "Commercial", "seat_capacity": 2, "doors": 4, "label": "Vapid Benson"},
    "pounder": {"class": "Commercial", "seat_capacity": 2, "doors": 4, "label": "MTL Pounder"},
    "hauler": {"class": "Commercial", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Hauler"},
    "phantom": {"class": "Commercial", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Phantom"},
    "packer": {"class": "Commercial", "seat_capacity": 2, "doors": 2, "label": "MTL Packer"},
    "boxville": {"class": "Vans", "seat_capacity": 2, "doors": 4, "label": "Brute Boxville"},
    "burrito": {"class": "Vans", "seat_capacity": 4, "doors": 4, "label": "Declasse Burrito"},
    "speedo": {"class": "Vans", "seat_capacity": 2, "doors": 4, "label": "Vapid Speedo"},
    "police": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Police Cruiser"},
    "police2": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Bravado Police Cruiser"},
    "police3": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Police Interceptor"},
    "policet": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Declasse Police Transporter"},
    "sheriff": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Sheriff Cruiser"},
    "fbi": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Bravado FIB"},
    "ambulance": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "Brute Ambulance"},
    "firetruk": {"class": "Emergency", "seat_capacity": 4, "doors": 4, "label": "MTL Fire Truck"},
    "towtruck": {"class": "Utility", "seat_capacity": 2, "doors": 2, "label": "Vapid Towtruck"},
    "utillitruck": {"class": "Utility", "seat_capacity": 2, "doors": 2, "label": "Brute Utility Truck"},
    "docktug": {"class": "Utility", "seat_capacity": 1, "doors": 2, "label": "HVY Docktug"},
    "handler": {"class": "Industrial", "seat_capacity": 1, "doors": 2, "label": "HVY Dock Handler"},
    "forklift": {"class": "Utility", "seat_capacity": 1, "doors": 0, "label": "HVY Forklift"},
}

VANILLA_PED_CATALOG: dict[str, dict[str, Any]] = {
    "a_m_y_business_01": {"group": "CIVMALE", "role_hint": "commuter", "label": "Young Businessman"},
    "a_f_y_business_01": {"group": "CIVFEMALE", "role_hint": "commuter", "label": "Young Businesswoman"},
    "a_m_m_business_01": {"group": "CIVMALE", "role_hint": "commuter", "label": "Business Executive"},
    "a_m_y_tourist_01": {"group": "CIVMALE", "role_hint": "commuter", "label": "City Tourist"},
    "s_m_m_dockwork_01": {"group": "CIVMALE", "role_hint": "harbor_worker", "label": "Dock Worker"},
    "s_m_y_dockwork_01": {"group": "CIVMALE", "role_hint": "harbor_worker", "label": "Port Logistics Worker"},
    "s_m_y_airworker": {"group": "CIVMALE", "role_hint": "ground_crew", "label": "Airport Ground Worker"},
    "s_m_m_trucker_01": {"group": "CIVMALE", "role_hint": "driver", "label": "Freight Trucker"},
    "s_m_m_postal_01": {"group": "CIVMALE", "role_hint": "courier", "label": "Postal Courier"},
    "s_m_y_cop_01": {"group": "COP", "role_hint": "law_enforcement", "label": "LSPD Officer"},
    "s_m_m_security_01": {"group": "SECURITY", "role_hint": "security", "label": "Security Guard"},
    "s_m_y_construct_01": {"group": "CIVMALE", "role_hint": "industrial", "label": "Construction Worker"},
}

BLIP_PRESETS: dict[str, dict[str, Any]] = {
    "ordered_stops": {
        "sprite_id": 513,
        "sprite_name": "RadarBus",
        "color_id": 3,
        "color_name": "Blue",
        "show_route": True,
    },
    "dispatch_zones": {
        "sprite_id": 477,
        "sprite_name": "RadarTruck",
        "color_id": 5,
        "color_name": "Yellow",
        "show_route": True,
    },
}

KEYBIND_CATALOG: dict[str, int] = {
    "F1": 112,
    "F2": 113,
    "F3": 114,
    "F4": 115,
    "F5": 116,
    "F6": 117,
    "F7": 118,
    "F8": 119,
    "F9": 120,
    "F10": 121,
    "F11": 122,
    "F12": 123,
    "INSERT": 45,
    "LEFTSHIFT": 160,
    "LEFTCONTROL": 162,
    "LEFTALT": 164,
    "B": 66,
    "E": 69,
    "N": 78,
    "Y": 89,
}


def joaat_hash(name: str) -> int:
    """Compute GTA V / RAGE Jenkins One-At-A-Time (JOAAT) unsigned 32-bit hash."""
    h = 0
    for ch in name.lower().encode("utf-8"):
        h = (h + ch) & 0xFFFFFFFF
        h = (h + ((h << 10) & 0xFFFFFFFF)) & 0xFFFFFFFF
        h ^= h >> 6
    h = (h + ((h << 3) & 0xFFFFFFFF)) & 0xFFFFFFFF
    h ^= h >> 11
    h = (h + ((h << 15) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return h


def to_pascal_case(identifier: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", identifier) if p]
    if not parts:
        return "GeneratedGtaMod"
    pascal = "".join(p[:1].upper() + p[1:] for p in parts)
    if pascal[0].isdigit():
        pascal = f"Mod{pascal}"
    return pascal


def map_ir_to_world(ir: GameplayIR | dict[str, Any]) -> dict[str, Any]:
    """Map a GameplayIR into a complete GTA V World-Model binding specification."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    mod_class_name = to_pascal_case(ir_obj.meta.id)

    entity_bindings: list[dict[str, Any]] = []
    catalog_warnings: list[str] = []

    for ent in ir_obj.entities:
        fallback_low = ent.vanilla_fallback_model.lower()
        is_veh = (
            ent.is_player_vehicle
            or "vehicle" in ent.role.lower()
            or fallback_low in VANILLA_VEHICLE_CATALOG
        ) and fallback_low not in VANILLA_PED_CATALOG
        kind = "vehicle" if is_veh else "ped"
        if kind == "vehicle":
            catalog_entry = VANILLA_VEHICLE_CATALOG.get(fallback_low)
            is_known = catalog_entry is not None
            seat_capacity = catalog_entry["seat_capacity"] if catalog_entry else 4
            label = catalog_entry["label"] if catalog_entry else ent.vanilla_fallback_model
        else:
            catalog_entry = VANILLA_PED_CATALOG.get(fallback_low)
            is_known = catalog_entry is not None
            seat_capacity = 0
            label = catalog_entry["label"] if catalog_entry else ent.vanilla_fallback_model

        if not is_known:
            catalog_warnings.append(
                f"Model '{ent.vanilla_fallback_model}' for slot '{ent.slot_id}' is not in the core "
                "built-in vanilla catalog; ensure it exists in vanilla game archives."
            )

        h_val = joaat_hash(fallback_low)
        addon_hash = (
            f"0x{joaat_hash(ent.preferred_addon_model):08X}"
            if ent.preferred_addon_model
            else None
        )

        entity_bindings.append(
            {
                "slot_id": ent.slot_id,
                "role": ent.role,
                "kind": kind,
                "label": label,
                "vanilla_fallback_model": fallback_low,
                "vanilla_joaat": h_val,
                "vanilla_joaat_hex": f"0x{h_val:08X}",
                "preferred_addon_model": ent.preferred_addon_model,
                "preferred_addon_joaat_hex": addon_hash,
                "stream_timeout_ms": ent.stream_timeout_ms,
                "release_on_timeout": True,
                "is_player_vehicle": ent.is_player_vehicle,
                "seat_capacity": seat_capacity,
                "default_seat_index": -1 if ent.is_player_vehicle else 0,
                "is_known_vanilla": is_known,
            }
        )

    track_bindings: list[dict[str, Any]] = []
    for track in ir_obj.routes_or_zones:
        blip = BLIP_PRESETS.get(track.mode, BLIP_PRESETS["ordered_stops"])
        track_bindings.append(
            {
                "track_id": track.track_id,
                "name": track.name,
                "mode": track.mode,
                "fare_or_reward": track.fare_or_reward,
                "allowed_vehicle_slots": list(track.allowed_vehicle_slots),
                "blip_sprite_id": blip["sprite_id"],
                "blip_sprite_name": blip["sprite_name"],
                "blip_color_id": blip["color_id"],
                "blip_color_name": blip["color_name"],
                "show_gps_route": blip["show_route"],
                "stop_count": len(track.stops),
                "stops": [s.to_dict() for s in track.stops],
            }
        )

    act_key_upper = ir_obj.inputs.activation_key.upper()
    mod_key_upper = (ir_obj.inputs.modifier_key or "").upper()
    preview_enum = (
        "StaticSprite"
        if ir_obj.ui_spec.preview_mode == "static_sprite"
        else "StaticMetadata"
    )

    return {
        "mod_id": ir_obj.meta.id,
        "mod_class_name": mod_class_name,
        "loader_target": ir_obj.loader_target,
        "target_editions": list(ir_obj.meta.target_editions),
        "ui_binding": {
            "title": ir_obj.ui_spec.title,
            "subtitle": ir_obj.ui_spec.subtitle,
            "preview_mode": ir_obj.ui_spec.preview_mode,
            "runtime_preview_enum": preview_enum,
            "live_3d_spawn_blocked": True,
        },
        "hotkey_binding": {
            "activation_key": ir_obj.inputs.activation_key,
            "activation_vk_code": KEYBIND_CATALOG.get(act_key_upper, 120),
            "modifier_key": ir_obj.inputs.modifier_key,
            "modifier_vk_code": KEYBIND_CATALOG.get(mod_key_upper) if mod_key_upper else None,
            "menu_library": ir_obj.inputs.menu_library,
        },
        "entity_bindings": entity_bindings,
        "track_bindings": track_bindings,
        "state_machine": ir_obj.state_machine.to_dict(),
        "telemetry_checkpoints": list(ACCEPTANCE_LAYERS),
        "catalog_warnings": catalog_warnings,
    }
