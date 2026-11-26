"""GTA V World-Model semantic mapper and expanded vanilla entity catalog."""

from __future__ import annotations

import re
from typing import Any

from gta_anything.models.ir import GameplayIR
from gta_anything.models.manifest import ACCEPTANCE_LAYERS


VANILLA_VEHICLE_CATALOG: dict[str, dict[str, Any]] = {
    # Transit & Public Shuttle
    "bus": {"class": "Service", "category": "transit", "seat_capacity": 16, "doors": 2, "label": "Brute Bus"},
    "airbus": {"class": "Service", "category": "transit", "seat_capacity": 16, "doors": 2, "label": "Brute Airport Bus"},
    "coach": {"class": "Service", "category": "transit", "seat_capacity": 10, "doors": 2, "label": "Brute Dashound Coach"},
    "tourbus": {"class": "Service", "category": "transit", "seat_capacity": 8, "doors": 2, "label": "Brute Tourbus"},
    "rentalbus": {"class": "Service", "category": "transit", "seat_capacity": 10, "doors": 2, "label": "Brute Rental Shuttle Bus"},
    "taxi": {"class": "Service", "category": "transit", "seat_capacity": 4, "doors": 4, "label": "Vapid Taxi"},
    "pbus": {"class": "Emergency", "category": "transit", "seat_capacity": 10, "doors": 2, "label": "Brute Police Prison Bus"},
    # Service
    "trash": {"class": "Service", "category": "service", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Trashmaster"},
    "trash2": {"class": "Service", "category": "service", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Trashmaster (Rusty)"},
    "brickade": {"class": "Service", "category": "service", "seat_capacity": 6, "doors": 4, "label": "MTL Brickade"},
    "rallytruck": {"class": "Service", "category": "service", "seat_capacity": 2, "doors": 2, "label": "MTL Dune"},
    # Commercial & Freight Vans
    "mule": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "Maibatsu Mule"},
    "mule2": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "Maibatsu Mule (Ramp)"},
    "mule3": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "Maibatsu Mule (Heist)"},
    "benson": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "Vapid Benson"},
    "pounder": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "MTL Pounder"},
    "hauler": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Hauler"},
    "phantom": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "Jobuilt Phantom"},
    "packer": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "MTL Packer"},
    "stockade": {"class": "Commercial", "category": "commercial", "seat_capacity": 4, "doors": 4, "label": "Brute Stockade"},
    "biff": {"class": "Commercial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "HVY Biff"},
    "flatbed": {"class": "Industrial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "MTL Flatbed"},
    "tiptruck": {"class": "Industrial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "Brute Tipper"},
    "mixer": {"class": "Industrial", "category": "commercial", "seat_capacity": 2, "doors": 2, "label": "HVY Mixer"},
    "boxville": {"class": "Vans", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "Brute Boxville"},
    "burrito": {"class": "Vans", "category": "commercial", "seat_capacity": 4, "doors": 4, "label": "Declasse Burrito"},
    "speedo": {"class": "Vans", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "Vapid Speedo"},
    "rumpo": {"class": "Vans", "category": "commercial", "seat_capacity": 4, "doors": 4, "label": "Bravado Rumpo"},
    "pony": {"class": "Vans", "category": "commercial", "seat_capacity": 4, "doors": 4, "label": "Brute Pony"},
    "youga": {"class": "Vans", "category": "commercial", "seat_capacity": 2, "doors": 4, "label": "Bravado Youga"},
    # Emergency & Law Enforcement
    "police": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Police Cruiser"},
    "police2": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Bravado Police Cruiser"},
    "police3": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Police Interceptor"},
    "police4": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Unmarked Cruiser"},
    "policeb": {"class": "Emergency", "category": "emergency", "seat_capacity": 1, "doors": 0, "label": "Western Police Bike"},
    "policet": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Declasse Police Transporter"},
    "pranger": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Declasse Park Ranger"},
    "sheriff": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Vapid Sheriff Cruiser"},
    "sheriff2": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Declasse Sheriff SUV"},
    "fbi": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Bravado FIB"},
    "fbi2": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Declasse FIB SUV"},
    "riot": {"class": "Emergency", "category": "emergency", "seat_capacity": 8, "doors": 4, "label": "Brute Police Riot"},
    "ambulance": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Brute Ambulance"},
    "firetruk": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "MTL Fire Truck"},
    "lguard": {"class": "Emergency", "category": "emergency", "seat_capacity": 4, "doors": 4, "label": "Declasse Lifeguard"},
    # Utility & Port Equipment
    "towtruck": {"class": "Utility", "category": "utility", "seat_capacity": 2, "doors": 2, "label": "Vapid Towtruck"},
    "towtruck2": {"class": "Utility", "category": "utility", "seat_capacity": 2, "doors": 2, "label": "Vapid Small Towtruck"},
    "utillitruck": {"class": "Utility", "category": "utility", "seat_capacity": 2, "doors": 2, "label": "Brute Utility Truck"},
    "utillitruck2": {"class": "Utility", "category": "utility", "seat_capacity": 2, "doors": 2, "label": "Brute Utility Truck (Flatbed)"},
    "docktug": {"class": "Utility", "category": "utility", "seat_capacity": 1, "doors": 2, "label": "HVY Docktug"},
    "handler": {"class": "Industrial", "category": "utility", "seat_capacity": 1, "doors": 2, "label": "HVY Dock Handler"},
    "forklift": {"class": "Utility", "category": "utility", "seat_capacity": 1, "doors": 0, "label": "HVY Forklift"},
    "airtug": {"class": "Utility", "category": "utility", "seat_capacity": 1, "doors": 0, "label": "HVY Airtug"},
    "ripley": {"class": "Utility", "category": "utility", "seat_capacity": 1, "doors": 2, "label": "HVY Ripley"},
    "tractor2": {"class": "Utility", "category": "utility", "seat_capacity": 1, "doors": 2, "label": "Stanley Fieldmaster"},
    "caddy": {"class": "Utility", "category": "utility", "seat_capacity": 2, "doors": 0, "label": "Nagasaki Caddy"},
    "scrap": {"class": "Utility", "category": "utility", "seat_capacity": 2, "doors": 2, "label": "Vapid Scrap Truck"},
    # Sedans & Executive Transport
    "stanier": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Vapid Stanier"},
    "premier": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Declasse Premier"},
    "washington": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Albany Washington"},
    "tailgater": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Obey Tailgater"},
    "oracle": {"class": "Coupes", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Ubermacht Oracle"},
    "primo": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Albany Primo"},
    "schafter2": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Benefactor Schafter"},
    "stretch": {"class": "Sedans", "category": "sedan", "seat_capacity": 6, "doors": 4, "label": "Dundreary Stretch"},
    "fugitive": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Cheval Fugitive"},
    "asterope": {"class": "Sedans", "category": "sedan", "seat_capacity": 4, "doors": 4, "label": "Karin Asterope"},
}

VANILLA_PED_CATALOG: dict[str, dict[str, Any]] = {
    # Transit & Commuters
    "a_m_y_business_01": {"group": "CIVMALE", "category": "transit", "role_hint": "commuter", "label": "Young Businessman"},
    "a_f_y_business_01": {"group": "CIVFEMALE", "category": "transit", "role_hint": "commuter", "label": "Young Businesswoman"},
    "a_m_m_business_01": {"group": "CIVMALE", "category": "transit", "role_hint": "commuter", "label": "Business Executive"},
    "a_m_y_tourist_01": {"group": "CIVMALE", "category": "transit", "role_hint": "commuter", "label": "City Tourist"},
    "a_f_y_tourist_01": {"group": "CIVFEMALE", "category": "transit", "role_hint": "commuter", "label": "City Tourist (Female)"},
    "s_m_m_gentransport": {"group": "CIVMALE", "category": "transit", "role_hint": "transit_operator", "label": "Transit Operator"},
    "s_m_y_airworker": {"group": "CIVMALE", "category": "transit", "role_hint": "ground_crew", "label": "Airport Ground Worker"},
    # Dock & Freight Workers
    "s_m_m_dockwork_01": {"group": "CIVMALE", "category": "dock_worker", "role_hint": "harbor_worker", "label": "Dock Worker"},
    "s_m_y_dockwork_01": {"group": "CIVMALE", "category": "dock_worker", "role_hint": "harbor_worker", "label": "Port Logistics Worker"},
    "s_m_m_trucker_01": {"group": "CIVMALE", "category": "dock_worker", "role_hint": "driver", "label": "Freight Trucker"},
    "s_m_m_postal_01": {"group": "CIVMALE", "category": "dock_worker", "role_hint": "courier", "label": "Postal Courier"},
    "s_m_y_construct_01": {"group": "CIVMALE", "category": "dock_worker", "role_hint": "industrial", "label": "Construction Worker"},
    # Emergency & Law Enforcement
    "s_m_y_cop_01": {"group": "COP", "category": "emergency", "role_hint": "law_enforcement", "label": "LSPD Officer"},
    "s_f_y_cop_01": {"group": "COP", "category": "emergency", "role_hint": "law_enforcement", "label": "LSPD Officer (Female)"},
    "s_m_y_sheriff_01": {"group": "COP", "category": "emergency", "role_hint": "law_enforcement", "label": "LSSD Deputy"},
    "s_f_y_sheriff_01": {"group": "COP", "category": "emergency", "role_hint": "law_enforcement", "label": "LSSD Deputy (Female)"},
    "s_m_y_ranger_01": {"group": "COP", "category": "emergency", "role_hint": "park_ranger", "label": "San Andreas Park Ranger"},
    "s_m_y_hwaycop_01": {"group": "COP", "category": "emergency", "role_hint": "highway_patrol", "label": "SAHP Highway Officer"},
    "s_m_y_swat_01": {"group": "COP", "category": "emergency", "role_hint": "tactical", "label": "NOOSE Tactical Officer"},
    "s_m_m_paramedic_01": {"group": "MEDIC", "category": "emergency", "role_hint": "ems", "label": "LSFD Paramedic"},
    "s_m_y_fireman_01": {"group": "FIREMAN", "category": "emergency", "role_hint": "firefighter", "label": "LSFD Firefighter"},
    "s_m_m_security_01": {"group": "SECURITY", "category": "emergency", "role_hint": "security", "label": "Security Guard"},
    # Civilians
    "a_m_m_downtown_01": {"group": "CIVMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Downtown Resident"},
    "a_f_m_downtown_01": {"group": "CIVFEMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Downtown Resident (Female)"},
    "a_m_y_vinewood_01": {"group": "CIVMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Vinewood Local"},
    "a_f_y_vinewood_01": {"group": "CIVFEMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Vinewood Local (Female)"},
    "a_m_y_hipster_01": {"group": "CIVMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Mirror Park Pedestrian"},
    "a_f_y_hipster_01": {"group": "CIVFEMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Mirror Park Pedestrian (Female)"},
    "a_m_m_bevhills_01": {"group": "CIVMALE", "category": "civilian", "role_hint": "pedestrian", "label": "Rockford Hills Citizen"},
}

BLIP_PRESETS: dict[str, dict[str, Any]] = {
    "ordered_stops": {
        "sprite_id": 513,
        "sprite_name": "RadarBus",
        "color_id": 3,
        "color_name": "Blue",
        "show_route": True,
        "category": "transit",
    },
    "dispatch_zones": {
        "sprite_id": 477,
        "sprite_name": "RadarTruck",
        "color_id": 5,
        "color_name": "Yellow",
        "show_route": True,
        "category": "commercial",
    },
    "patrol_zones": {
        "sprite_id": 60,
        "sprite_name": "RadarPoliceOfficer",
        "color_id": 38,
        "color_name": "DarkBlue",
        "show_route": True,
        "category": "emergency",
    },
    "emergency_response": {
        "sprite_id": 161,
        "sprite_name": "RadarEmergency",
        "color_id": 1,
        "color_name": "Red",
        "show_route": True,
        "category": "emergency",
    },
    "taxi_pickup": {
        "sprite_id": 198,
        "sprite_name": "RadarTaxi",
        "color_id": 5,
        "color_name": "Yellow",
        "show_route": True,
        "category": "transit",
    },
    "harbor_logistics": {
        "sprite_id": 478,
        "sprite_name": "RadarContainer",
        "color_id": 5,
        "color_name": "Yellow",
        "show_route": True,
        "category": "dock_worker",
    },
    "service_depot": {
        "sprite_id": 446,
        "sprite_name": "RadarGarage",
        "color_id": 2,
        "color_name": "Green",
        "show_route": False,
        "category": "service",
    },
    "utility_worksite": {
        "sprite_id": 402,
        "sprite_name": "RadarRepair",
        "color_id": 47,
        "color_name": "Orange",
        "show_route": True,
        "category": "utility",
    },
}

ZONE_ARCHETYPES: dict[str, dict[str, Any]] = {
    "downtown_ls": {
        "label": "Downtown Los Santos",
        "region": "Los Santos",
        "center": {"x": 215.0, "y": -810.0, "z": 30.7},
        "categories": ["transit", "emergency", "civilian", "sedan"],
    },
    "vinewood_hills": {
        "label": "Vinewood Hills & Observatory",
        "region": "Los Santos North",
        "center": {"x": -425.0, "y": 1120.0, "z": 325.8},
        "categories": ["emergency", "civilian", "sedan"],
    },
    "terminal_port": {
        "label": "Port of Los Santos Terminal",
        "region": "South Los Santos",
        "center": {"x": 1190.0, "y": -3250.0, "z": 7.1},
        "categories": ["commercial", "dock_worker", "utility"],
    },
    "lsia_airport": {
        "label": "Los Santos International Airport",
        "region": "South Los Santos",
        "center": {"x": -1037.0, "y": -2737.0, "z": 20.1},
        "categories": ["transit", "commercial", "service", "utility"],
    },
    "del_perro_pier": {
        "label": "Del Perro Pier & Beachfront",
        "region": "West Los Santos",
        "center": {"x": -1600.0, "y": -1045.0, "z": 13.0},
        "categories": ["transit", "civilian", "emergency"],
    },
    "la_mesa": {
        "label": "La Mesa Industrial Corridor",
        "region": "East Los Santos",
        "center": {"x": 840.0, "y": -2120.0, "z": 30.5},
        "categories": ["commercial", "service", "utility", "dock_worker"],
    },
    "sandy_shores": {
        "label": "Sandy Shores Airfield & Township",
        "region": "Blaine County",
        "center": {"x": 1735.0, "y": 3295.0, "z": 41.2},
        "categories": ["emergency", "utility", "service"],
    },
    "paleto_bay": {
        "label": "Paleto Bay Coastal Highway",
        "region": "Blaine County North",
        "center": {"x": -275.0, "y": 6225.0, "z": 31.5},
        "categories": ["emergency", "transit", "civilian"],
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


def list_world_catalog(category: str | None = None) -> dict[str, Any]:
    """Return the built-in GTA V Vanilla World-Model Semantic Catalog, optionally filtered by category."""
    cat_set: set[str] = set()
    for v in VANILLA_VEHICLE_CATALOG.values():
        if v.get("category"):
            cat_set.add(str(v["category"]))
    for p in VANILLA_PED_CATALOG.values():
        if p.get("category"):
            cat_set.add(str(p["category"]))
    for b in BLIP_PRESETS.values():
        if b.get("category"):
            cat_set.add(str(b["category"]))
    all_categories = sorted(cat_set)

    norm_cat = category.strip().lower() if isinstance(category, str) and category.strip() else None

    if norm_cat is None:
        vehicles = {k: dict(v) for k, v in VANILLA_VEHICLE_CATALOG.items()}
        peds = {k: dict(v) for k, v in VANILLA_PED_CATALOG.items()}
        blips = {k: dict(v) for k, v in BLIP_PRESETS.items()}
        zones = {k: dict(v) for k, v in ZONE_ARCHETYPES.items()}
    else:
        vehicles = {
            k: dict(v)
            for k, v in VANILLA_VEHICLE_CATALOG.items()
            if str(v.get("category", "")).lower() == norm_cat
            or str(v.get("class", "")).lower() == norm_cat
        }
        peds = {
            k: dict(v)
            for k, v in VANILLA_PED_CATALOG.items()
            if str(v.get("category", "")).lower() == norm_cat
            or str(v.get("role_hint", "")).lower() == norm_cat
        }
        blips = {
            k: dict(v)
            for k, v in BLIP_PRESETS.items()
            if str(v.get("category", "")).lower() == norm_cat
        }
        zones = {
            k: dict(v)
            for k, v in ZONE_ARCHETYPES.items()
            if norm_cat in [c.lower() for c in v.get("categories", [])]
        }

    return {
        "ok": True,
        "category": norm_cat,
        "categories": all_categories,
        "vehicles": vehicles,
        "peds": peds,
        "blips": blips,
        "zone_archetypes": zones,
    }


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
