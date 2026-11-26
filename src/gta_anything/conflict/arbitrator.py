"""5-Dimension Multi-Mod Conflict, Assembly ABI, Spatial Turf & Resource Budget Arbitrator."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import math
import os
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

from gta_anything.models.ir import GameplayIR
from gta_anything.preflight.checker import run_preflight
from gta_anything.transpiler.world_mapper import (
    VANILLA_PED_CATALOG,
    VANILLA_VEHICLE_CATALOG,
    joaat_hash,
    to_pascal_case,
)

MAX_TEXT_SCAN_BYTES = 5 * 1024 * 1024  # 5 MB safety cap for XML/JSON config parsing
BINARY_SKIP_EXTENSIONS = {
    ".rpf",
    ".exe",
    ".dll",
    ".asi",
    ".yft",
    ".ytd",
    ".ydr",
    ".ydd",
    ".ybn",
    ".ymap",
    ".ytyp",
    ".awc",
    ".dds",
    ".png",
    ".jpg",
    ".zip",
    ".7z",
    ".rar",
}

UI_LIBRARY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("lemonui", "LemonUI"),
    ("inmnativeui", "INMNativeUI"),
    ("nativeui", "NativeUI"),
    ("ragenativeui", "RAGENativeUI"),
)


def _rel_posix(path: Path, base_dir: Path) -> str:
    """Return a clean portable relative POSIX path without leaking host directories."""
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except Exception:
        try:
            return path.relative_to(base_dir).as_posix()
        except Exception:
            return path.name


def _extract_pe_file_version(file_path: Path) -> str | None:
    """Extract PE FileVersion using VS_FIXEDFILEINFO (0xFEEF04BD) binary signature scan."""
    if not file_path.exists() or not file_path.is_file():
        return None

    # 1. Binary scan for VS_FIXEDFILEINFO signature 0xFEEF04BD (cross-platform & synthetic test friendly)
    try:
        data = file_path.read_bytes()
    except Exception:
        data = b""

    if data:
        sig_bytes = b"\xbd\x04\xef\xfe"
        idx = data.find(sig_bytes)
        if idx != -1 and idx + 16 <= len(data):
            try:
                _sig, _struc_ver, file_ver_ms, file_ver_ls = struct.unpack(
                    "<IIII", data[idx : idx + 16]
                )
                major = (file_ver_ms >> 16) & 0xFFFF
                minor = file_ver_ms & 0xFFFF
                build = (file_ver_ls >> 16) & 0xFFFF
                rev = file_ver_ls & 0xFFFF
                return f"{major}.{minor}.{build}.{rev}"
            except Exception:
                pass

    # 2. Win32 API fallback on Windows
    if os.name == "nt":
        try:
            version_dll = ctypes.windll.version  # type: ignore[attr-defined]
            path_str = str(file_path)
            handle = ctypes.wintypes.DWORD(0)
            size = version_dll.GetFileVersionInfoSizeW(path_str, ctypes.byref(handle))
            if size > 0:
                buf = ctypes.create_string_buffer(size)
                if version_dll.GetFileVersionInfoW(path_str, 0, size, buf):
                    lp_buffer = ctypes.c_void_p()
                    u_len = ctypes.wintypes.UINT(0)
                    if (
                        version_dll.VerQueryValueW(
                            buf, "\\", ctypes.byref(lp_buffer), ctypes.byref(u_len)
                        )
                        and u_len.value >= 52
                    ):
                        raw = ctypes.string_at(lp_buffer.value, 52)
                        sig, _struc_ver, file_ver_ms, file_ver_ls = struct.unpack(
                            "<IIII", raw[:16]
                        )
                        if sig == 0xFEEF04BD:
                            major = (file_ver_ms >> 16) & 0xFFFF
                            minor = file_ver_ms & 0xFFFF
                            build = (file_ver_ls >> 16) & 0xFFFF
                            rev = file_ver_ls & 0xFFFF
                            return f"{major}.{minor}.{build}.{rev}"
        except Exception:
            pass

    # 3. Synthetic text version fallback for mock DLL fixtures in tests
    if data:
        try:
            decoded_ascii = data.decode("latin-1", errors="ignore")
            m = re.search(r"\b(\d+\.\d+\.\d{1,5}(?:\.\d+)?)\b", decoded_ascii)
            if m:
                return m.group(1)
            decoded_utf16 = data.decode("utf-16le", errors="ignore")
            m16 = re.search(r"\b(\d+\.\d+\.\d{1,5}(?:\.\d+)?)\b", decoded_utf16)
            if m16:
                return m16.group(1)
        except Exception:
            pass

    return None


def _classify_ui_library(filename: str) -> str | None:
    low = filename.lower()
    for token, canonical in UI_LIBRARY_PATTERNS:
        if token in low:
            return canonical
    return None


def _read_active_profile_mode(game_root: Path) -> str | None:
    active_mode_file = game_root / "GTA5-Profiles" / "ActiveMode.txt"
    if active_mode_file.exists() and active_mode_file.is_file():
        try:
            text = active_mode_file.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text.splitlines()[0].strip()
        except Exception:
            pass
    return None


def inspect_assembly_abi_conflicts(
    game_dir: str | Path,
    loader_target: str = "shvdn_enhanced",
    menu_library: str = "LemonUI",
) -> dict[str, Any]:
    """Inspect .dll and .asi assemblies in game_dir root, scripts/, and plugins/ for ABI & loader conflicts."""
    root = Path(game_dir)
    if not root.exists() or not root.is_dir():
        return {
            "ok": False,
            "loader_target": loader_target,
            "requested_menu_library": menu_library,
            "active_profile_mode": None,
            "active_loader_chains": [],
            "parked_profiles_with_target_loader": [],
            "loader_chain_matched": False,
            "coexistence_warning": False,
            "installed_assemblies": [],
            "ui_libraries": [],
            "conflicts": [
                {
                    "code": "GAME_DIR_NOT_FOUND",
                    "severity": "BLOCKING",
                    "message": "Target game directory does not exist.",
                    "files": [],
                    "recommendation": "Provide a valid GTA V installation path via --game-dir.",
                }
            ],
            "blocking_count": 1,
            "warning_count": 0,
        }

    active_profile_mode = _read_active_profile_mode(root)
    installed_assemblies: list[dict[str, Any]] = []
    ui_libraries: list[dict[str, Any]] = []

    # 1. Scan root (non-recursive), scripts/ (recursive), and plugins/ (recursive)
    candidate_files: list[tuple[Path, str]] = []
    try:
        for item in sorted(root.iterdir()):
            if item.is_file() and item.suffix.lower() in {".dll", ".asi", ".exe"}:
                if item.suffix.lower() in {".dll", ".asi"} or item.name.lower() == "ragepluginhook.exe":
                    candidate_files.append((item, "root"))
    except Exception:
        pass

    for sub_name in ("scripts", "plugins"):
        sub_dir = root / sub_name
        if sub_dir.exists() and sub_dir.is_dir():
            try:
                for item in sorted(sub_dir.rglob("*")):
                    if item.is_file() and item.suffix.lower() in {".dll", ".asi"}:
                        candidate_files.append((item, sub_name))
            except Exception:
                pass

    for file_path, location in candidate_files:
        rel_path = _rel_posix(file_path, root)
        version = _extract_pe_file_version(file_path)
        try:
            size_bytes = file_path.stat().st_size
        except Exception:
            size_bytes = 0

        ui_family = _classify_ui_library(file_path.name)
        category = "ui_library" if ui_family else ("loader" if location == "root" else f"{location}_plugin")

        entry = {
            "relative_path": rel_path,
            "name": file_path.name,
            "extension": file_path.suffix.lower(),
            "location": location,
            "file_version": version,
            "size_bytes": size_bytes,
            "category": category,
        }
        installed_assemblies.append(entry)

        if ui_family and location in {"scripts", "root", "plugins"}:
            ui_entry = dict(entry)
            ui_entry["ui_family"] = ui_family
            ui_libraries.append(ui_entry)

    # 2. Identify active loader chains in root / plugins
    root_names_lower = {
        a["name"].lower() for a in installed_assemblies if a["location"] == "root"
    }
    plugin_assemblies = [a for a in installed_assemblies if a["location"] == "plugins"]
    script_assemblies = [a for a in installed_assemblies if a["location"] == "scripts"]

    has_shv = "scripthookv.dll" in root_names_lower
    has_shvdn_asi = "scripthookvdotnet.asi" in root_names_lower
    has_shvdn2 = "scripthookvdotnet2.dll" in root_names_lower
    has_shvdn3 = "scripthookvdotnet3.dll" in root_names_lower
    has_shvdn_chain = has_shvdn_asi or has_shvdn3 or has_shvdn2 or len(script_assemblies) > 0

    has_rph_exe = (root / "RAGEPluginHook.exe").exists() or "ragepluginhook.exe" in root_names_lower
    has_lspdfr_plugin = any("lspd" in a["name"].lower() for a in plugin_assemblies)
    has_rph_chain = has_rph_exe or has_lspdfr_plugin or len(plugin_assemblies) > 0

    active_loader_chains: list[str] = []
    if has_shvdn_asi or has_shvdn3 or has_shvdn2:
        active_loader_chains.append("shvdn")
    if has_rph_chain:
        active_loader_chains.append("rph")

    # 3. Check Inactive Profiles for parked loader chains
    parked_profiles_with_target_loader: list[str] = []
    inactive_root = root / "GTA5-Profiles" / "Inactive"
    wants_shvdn = loader_target.startswith("shvdn")
    wants_rph = loader_target == "rph"

    if inactive_root.exists() and inactive_root.is_dir():
        try:
            for prof_dir in sorted(inactive_root.iterdir()):
                if not prof_dir.is_dir():
                    continue
                prof_files_lower = {
                    p.name.lower() for p in prof_dir.rglob("*") if p.is_file()
                }
                if wants_shvdn and (
                    "scripthookvdotnet.asi" in prof_files_lower
                    or "scripthookvdotnet3.dll" in prof_files_lower
                    or "scripthookv.dll" in prof_files_lower
                ):
                    parked_profiles_with_target_loader.append(prof_dir.name)
                elif wants_rph and (
                    "ragepluginhook.exe" in prof_files_lower
                    or "lspdfr.dll" in prof_files_lower
                    or "lspd first response.dll" in prof_files_lower
                ):
                    parked_profiles_with_target_loader.append(prof_dir.name)
        except Exception:
            pass

    conflicts: list[dict[str, Any]] = []

    # 4. Detect UI library ABI conflicts inside scripts/
    scripts_ui = [u for u in ui_libraries if u["location"] == "scripts"]
    lemon_dlls = [u for u in scripts_ui if u["ui_family"] == "LemonUI"]
    if len(lemon_dlls) > 1:
        lemon_files = [u["relative_path"] for u in lemon_dlls]
        has_shvdn2_lemon = any("shvdn2" in u["name"].lower() for u in lemon_dlls)
        has_shvdn3_lemon = any("shvdn3" in u["name"].lower() for u in lemon_dlls)
        versions = {u["file_version"] for u in lemon_dlls if u["file_version"]}
        if (has_shvdn2_lemon and has_shvdn3_lemon) or len(versions) > 1 or len({u["name"].lower() for u in lemon_dlls}) > 1:
            conflicts.append(
                {
                    "code": "DUPLICATE_UI_LIBRARY_ABI",
                    "severity": "BLOCKING",
                    "message": (
                        f"Multiple conflicting LemonUI assemblies detected in scripts/: "
                        f"{', '.join(lemon_files)}. Co-loading SHVDN2 and SHVDN3 or mismatched "
                        "LemonUI builds causes AppDomain type collision and menu crashes."
                    ),
                    "files": lemon_files,
                    "recommendation": (
                        "Keep only the single LemonUI.SHVDN3.dll matching ScriptHookVDotNet3, "
                        "or isolate conflicting legacy scripts into a separate profile."
                    ),
                }
            )

    ui_families_in_scripts = sorted({u["ui_family"] for u in scripts_ui})
    if len(ui_families_in_scripts) > 1:
        mixed_files = [u["relative_path"] for u in scripts_ui]
        conflicts.append(
            {
                "code": "MIXED_UI_LIBRARIES",
                "severity": "WARNING",
                "message": (
                    f"Multiple UI frameworks mixed in scripts/ ({', '.join(ui_families_in_scripts)}): "
                    f"{', '.join(mixed_files)}. Mixing NativeUI, INMNativeUI, and LemonUI increases "
                    "input hook contention and tick latency."
                ),
                "files": mixed_files,
                "recommendation": (
                    f"Prefer unified '{menu_library}' or built-in static HUD menu across active scripts."
                ),
            }
        )

    # 5. Detect missing required loader chain or active profile mismatch
    active_mode_lower = (active_profile_mode or "").lower()
    if wants_shvdn:
        active_is_rph_mode = active_mode_lower in {"lspdfr", "rph", "police"} or (
            has_rph_chain and not (has_shvdn_asi or has_shvdn3)
        )
        if active_is_rph_mode or not (has_shvdn_asi or has_shvdn3 or has_shv):
            parked_hint = (
                f" Target SHVDN loader was found parked in inactive profile(s): {', '.join(parked_profiles_with_target_loader)}."
                if parked_profiles_with_target_loader
                else ""
            )
            active_desc = (
                f"Active profile is '{active_profile_mode}'"
                if active_profile_mode
                else "Active directory lacks ScriptHookVDotNet.asi / ScriptHookVDotNet3.dll"
            )
            conflicts.append(
                {
                    "code": "LOADER_CHAIN_MISMATCH",
                    "severity": "BLOCKING",
                    "message": (
                        f"Mod requires '{loader_target}' (SHVDN chain), but {active_desc}."
                        f"{parked_hint}"
                    ),
                    "files": ["GTA5-Profiles/ActiveMode.txt"] if active_profile_mode else [],
                    "recommendation": (
                        f"Isolate or switch to profile '{parked_profiles_with_target_loader[0]}' via "
                        "`gta-anything profile switch` before deploying this SHVDN mod."
                        if parked_profiles_with_target_loader
                        else "Stage this mod into a dedicated SHVDN profile using `gta-anything profile stage`."
                    ),
                }
            )
    elif wants_rph:
        active_is_shvdn_only = (
            active_mode_lower in {"bus", "shvdn", "transit"}
            or (has_shvdn_chain and not has_rph_chain)
        )
        if active_is_shvdn_only or not has_rph_chain:
            parked_hint = (
                f" Target RPH loader was found parked in inactive profile(s): {', '.join(parked_profiles_with_target_loader)}."
                if parked_profiles_with_target_loader
                else ""
            )
            conflicts.append(
                {
                    "code": "LOADER_CHAIN_MISMATCH",
                    "severity": "BLOCKING",
                    "message": (
                        f"Mod requires 'rph' (RAGEPluginHook chain), but active directory is configured for "
                        f"'{active_profile_mode or 'SHVDN/vanilla'}'.{parked_hint}"
                    ),
                    "files": ["GTA5-Profiles/ActiveMode.txt"] if active_profile_mode else [],
                    "recommendation": "Switch to an RPH/LSPDFR profile or install RAGEPluginHook.exe.",
                }
            )

    # 6. Detect co-existence of RPH (RAGEPluginHook.exe + plugins/) and heavy SHVDN scripts
    coexistence_warning = False
    if (has_shvdn_asi or has_shvdn3 or len(script_assemblies) > 0) and (
        has_rph_exe and len(plugin_assemblies) > 0
    ):
        coexistence_warning = True
        conflicts.append(
            {
                "code": "DUAL_LOADER_COEXISTENCE",
                "severity": "WARNING",
                "message": (
                    f"RAGEPluginHook ({len(plugin_assemblies)} plugin DLLs) and ScriptHookVDotNet "
                    f"({len(script_assemblies)} script assemblies) coexist in the active directory. "
                    "Running heavy LSPDFR callouts alongside SHVDN operational loops increases commit memory "
                    "and hotkey contention."
                ),
                "files": [a["relative_path"] for a in (plugin_assemblies[:3] + script_assemblies[:3])],
                "recommendation": "Use ProfileManager (`gta-anything profile switch`) to isolate RPH and SHVDN workloads.",
            }
        )

    blocking_count = sum(1 for c in conflicts if c["severity"] == "BLOCKING")
    warning_count = sum(1 for c in conflicts if c["severity"] == "WARNING")
    loader_chain_matched = not any(c["code"] == "LOADER_CHAIN_MISMATCH" for c in conflicts)

    return {
        "ok": blocking_count == 0,
        "loader_target": loader_target,
        "requested_menu_library": menu_library,
        "active_profile_mode": active_profile_mode,
        "active_loader_chains": active_loader_chains,
        "parked_profiles_with_target_loader": parked_profiles_with_target_loader,
        "loader_chain_matched": loader_chain_matched,
        "coexistence_warning": coexistence_warning,
        "installed_assemblies": installed_assemblies,
        "ui_libraries": ui_libraries,
        "conflicts": conflicts,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
    }


def _extract_coords_from_xml(xml_text: str, rel_path: str) -> list[dict[str, Any]]:
    """Extract (x, y, z) coordinate triples from XML elements or attributes."""
    points: list[dict[str, Any]] = []
    try:
        root_elem = ET.fromstring(xml_text)
        for idx, elem in enumerate(root_elem.iter()):
            attrib_low = {k.lower(): v for k, v in elem.attrib.items()}
            x_val: float | None = None
            y_val: float | None = None
            z_val: float | None = None

            if "x" in attrib_low and "y" in attrib_low and "z" in attrib_low:
                try:
                    x_val = float(attrib_low["x"])
                    y_val = float(attrib_low["y"])
                    z_val = float(attrib_low["z"])
                except (ValueError, TypeError):
                    pass
            else:
                child_map = {
                    child.tag.split("}")[-1].lower(): (child.text or "").strip()
                    for child in elem
                }
                if "x" in child_map and "y" in child_map and "z" in child_map:
                    try:
                        x_val = float(child_map["x"])
                        y_val = float(child_map["y"])
                        z_val = float(child_map["z"])
                    except (ValueError, TypeError):
                        pass

            if x_val is not None and y_val is not None and z_val is not None:
                if x_val == 0.0 and y_val == 0.0 and z_val == 0.0:
                    continue
                point_name = (
                    attrib_low.get("name")
                    or attrib_low.get("id")
                    or attrib_low.get("station")
                    or attrib_low.get("label")
                    or f"{elem.tag.split('}')[-1]}#{idx}"
                )
                points.append(
                    {
                        "file": rel_path,
                        "name": str(point_name),
                        "x": x_val,
                        "y": y_val,
                        "z": z_val,
                    }
                )
        return points
    except Exception:
        pass

    # Regex fallback if XML has minor syntax quirks
    attr_pattern = re.compile(
        r"""x\s*=\s*["']([-+]?\d+(?:\.\d+)?)["'][^>]*?y\s*=\s*["']([-+]?\d+(?:\.\d+)?)["'][^>]*?z\s*=\s*["']([-+]?\d+(?:\.\d+)?)["']""",
        re.IGNORECASE,
    )
    for idx, match in enumerate(attr_pattern.finditer(xml_text)):
        try:
            x_val = float(match.group(1))
            y_val = float(match.group(2))
            z_val = float(match.group(3))
            if x_val == 0.0 and y_val == 0.0 and z_val == 0.0:
                continue
            points.append(
                {
                    "file": rel_path,
                    "name": f"xml_node#{idx}",
                    "x": x_val,
                    "y": y_val,
                    "z": z_val,
                }
            )
        except (ValueError, TypeError):
            continue
    return points


def _extract_coords_from_json_obj(
    obj: Any, rel_path: str, path_prefix: str = "root"
) -> list[dict[str, Any]]:
    """Recursively extract (x, y, z) coordinate triples from parsed JSON structures."""
    points: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        low_map = {str(k).lower(): v for k, v in obj.items()}
        if "x" in low_map and "y" in low_map and "z" in low_map:
            try:
                x_val = float(low_map["x"])
                y_val = float(low_map["y"])
                z_val = float(low_map["z"])
                if not (x_val == 0.0 and y_val == 0.0 and z_val == 0.0):
                    name = (
                        low_map.get("name")
                        or low_map.get("id")
                        or low_map.get("track_id")
                        or path_prefix
                    )
                    points.append(
                        {
                            "file": rel_path,
                            "name": str(name),
                            "x": x_val,
                            "y": y_val,
                            "z": z_val,
                        }
                    )
            except (ValueError, TypeError):
                pass
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                points.extend(_extract_coords_from_json_obj(v, rel_path, f"{path_prefix}.{k}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                points.extend(_extract_coords_from_json_obj(item, rel_path, f"{path_prefix}[{idx}]"))
    return points


def inspect_spatial_turf_overlaps(
    ir: GameplayIR | dict[str, Any],
    game_dir: str | Path,
    min_clearance_m: float = 15.0,
) -> dict[str, Any]:
    """Scan existing .xml and .json files in scripts/ and plugins/ for 3D spatial spawn/stop overlaps."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    root = Path(game_dir)

    ir_stops: list[dict[str, Any]] = []
    for track in ir_obj.routes_or_zones:
        for stop in track.stops:
            ir_stops.append(
                {
                    "track_id": track.track_id,
                    "stop_index": stop.index,
                    "stop_name": stop.name,
                    "x": float(stop.x),
                    "y": float(stop.y),
                    "z": float(stop.z),
                }
            )

    if not root.exists() or not root.is_dir():
        return {
            "ok": True,
            "min_clearance_m": float(min_clearance_m),
            "ir_stop_count": len(ir_stops),
            "scanned_files": [],
            "discovered_host_points": 0,
            "overlaps": [],
            "overlap_count": 0,
        }

    own_id_low = (ir_obj.meta.id or "").strip().lower()
    own_pascal_low = to_pascal_case(ir_obj.meta.id or "").lower()

    scanned_files: list[str] = []
    host_points: list[dict[str, Any]] = []

    for sub_name in ("scripts", "plugins"):
        sub_dir = root / sub_name
        if not sub_dir.exists() or not sub_dir.is_dir():
            continue
        try:
            candidates = sorted(sub_dir.rglob("*"))
        except Exception:
            continue

        for file_path in candidates:
            if not file_path.is_file():
                continue
            ext = file_path.suffix.lower()
            if ext in BINARY_SKIP_EXTENSIONS or ext not in {".xml", ".json"}:
                continue

            # Exclude files belonging to the mod's own ID
            rel_path = _rel_posix(file_path, root)
            rel_low = rel_path.lower()
            stem_low = file_path.stem.lower()
            if own_id_low and (own_id_low in stem_low or f"/{own_id_low}/" in f"/{rel_low}/"):
                continue
            if own_pascal_low and (
                own_pascal_low in stem_low or f"/{own_pascal_low}/" in f"/{rel_low}/"
            ):
                continue

            try:
                if file_path.stat().st_size > MAX_TEXT_SCAN_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            scanned_files.append(rel_path)
            if ext == ".xml":
                host_points.extend(_extract_coords_from_xml(text, rel_path))
            elif ext == ".json":
                try:
                    parsed = json.loads(text)
                    host_points.extend(_extract_coords_from_json_obj(parsed, rel_path))
                except Exception:
                    pass

    overlaps: list[dict[str, Any]] = []
    threshold = float(min_clearance_m)

    for stop in ir_stops:
        for hp in host_points:
            dx = stop["x"] - hp["x"]
            dy = stop["y"] - hp["y"]
            dz = stop["z"] - hp["z"]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < threshold:
                dist_rounded = round(dist, 2)
                overlaps.append(
                    {
                        "code": "SPATIAL_SPAWN_OVERLAP",
                        "severity": "WARNING",
                        "track_id": stop["track_id"],
                        "stop_index": stop["stop_index"],
                        "stop_name": stop["stop_name"],
                        "ir_coords": {
                            "x": stop["x"],
                            "y": stop["y"],
                            "z": stop["z"],
                        },
                        "host_file": hp["file"],
                        "host_point_name": hp["name"],
                        "host_coords": {
                            "x": hp["x"],
                            "y": hp["y"],
                            "z": hp["z"],
                        },
                        "distance_m": dist_rounded,
                        "message": (
                            f"Stop '{stop['stop_name']}' ({stop['x']}, {stop['y']}, {stop['z']}) "
                            f"is {dist_rounded:.2f}m (< {threshold:.1f}m clearance) from existing mod point "
                            f"'{hp['name']}' in '{hp['file']}'."
                        ),
                    }
                )

    return {
        "ok": len(overlaps) == 0,
        "min_clearance_m": threshold,
        "ir_stop_count": len(ir_stops),
        "scanned_files": scanned_files,
        "discovered_host_points": len(host_points),
        "overlaps": overlaps,
        "overlap_count": len(overlaps),
    }


def inspect_dlc_and_model_collisions(
    ir: GameplayIR | dict[str, Any],
    game_dir: str | Path,
) -> dict[str, Any]:
    """Inspect dlclist.xml, dlcpacks/ folders, and JOAAT 32-bit hashes of preferred_addon_model slots."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    root = Path(game_dir)

    dlclist_files: list[str] = []
    registered_dlcpacks: list[str] = []
    duplicate_dlc_entries: list[str] = []
    installed_dlcpack_folders: list[str] = []

    if root.exists() and root.is_dir():
        dlclist_candidates = [
            root / "mods" / "update" / "update.rpf" / "common" / "data" / "dlclist.xml",
            root / "mods" / "common" / "data" / "dlclist.xml",
            root / "mods" / "dlclist.xml",
            root / "update" / "dlclist.xml",
            root / "dlclist.xml",
        ]
        seen_dlc_files: set[Path] = set()
        for cand in dlclist_candidates:
            if cand.exists() and cand.is_file() and cand not in seen_dlc_files:
                seen_dlc_files.add(cand)
                dlclist_files.append(_rel_posix(cand, root))
                try:
                    if cand.stat().st_size <= MAX_TEXT_SCAN_BYTES:
                        raw_xml = cand.read_text(encoding="utf-8", errors="replace")
                        items = re.findall(
                            r"<Item>\s*dlcpacks:/([^/<>\s]+)/?\s*</Item>",
                            raw_xml,
                            flags=re.IGNORECASE,
                        )
                        seen_in_file: set[str] = set()
                        for pack in items:
                            pack_low = pack.strip().lower()
                            if pack_low in seen_in_file and pack_low not in duplicate_dlc_entries:
                                duplicate_dlc_entries.append(pack_low)
                            seen_in_file.add(pack_low)
                            if pack_low not in registered_dlcpacks:
                                registered_dlcpacks.append(pack_low)
                except Exception:
                    pass

        dlcpack_dir_candidates = [
            root / "mods" / "update" / "x64" / "dlcpacks",
            root / "update" / "x64" / "dlcpacks",
            root / "mods" / "dlcpacks",
            root / "dlcpacks",
        ]
        for dlc_dir in dlcpack_dir_candidates:
            if dlc_dir.exists() and dlc_dir.is_dir():
                try:
                    for child in sorted(dlc_dir.iterdir()):
                        if child.is_dir():
                            name_low = child.name.lower()
                            if name_low not in installed_dlcpack_folders:
                                installed_dlcpack_folders.append(name_low)
                except Exception:
                    pass

    # Precompute vanilla JOAAT hash table
    vanilla_hash_to_name: dict[int, str] = {}
    for v_name in VANILLA_VEHICLE_CATALOG:
        vanilla_hash_to_name[joaat_hash(v_name)] = v_name
    for p_name in VANILLA_PED_CATALOG:
        vanilla_hash_to_name[joaat_hash(p_name)] = p_name

    installed_dlc_hash_to_name: dict[int, str] = {}
    for pack_name in set(registered_dlcpacks) | set(installed_dlcpack_folders):
        installed_dlc_hash_to_name[joaat_hash(pack_name)] = pack_name

    entity_hashes: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []

    for dup_pack in duplicate_dlc_entries:
        collisions.append(
            {
                "code": "DUPLICATE_DLCLIST_ENTRY",
                "severity": "WARNING",
                "slot_id": None,
                "model_name": dup_pack,
                "joaat_hex": f"0x{joaat_hash(dup_pack):08X}",
                "collides_with": f"dlclist.xml ({dup_pack})",
                "message": f"Duplicate DLC entry 'dlcpacks:/{dup_pack}/' found in dlclist.xml.",
            }
        )

    seen_addon_hashes: dict[int, tuple[str, str]] = {}

    for ent in ir_obj.entities:
        fallback_name = (ent.vanilla_fallback_model or "").strip().lower()
        fallback_hash = joaat_hash(fallback_name) if fallback_name else 0
        addon_name = (ent.preferred_addon_model or "").strip().lower() if ent.preferred_addon_model else None
        addon_hash = joaat_hash(addon_name) if addon_name else None

        entity_hashes.append(
            {
                "slot_id": ent.slot_id,
                "vanilla_fallback_model": fallback_name,
                "vanilla_joaat": fallback_hash,
                "vanilla_joaat_hex": f"0x{fallback_hash:08X}",
                "preferred_addon_model": addon_name,
                "preferred_addon_joaat": addon_hash,
                "preferred_addon_joaat_hex": f"0x{addon_hash:08X}" if addon_hash is not None else None,
            }
        )

        if addon_name and addon_hash is not None:
            # 1. Check collision against built-in vanilla model JOAAT hashes
            if addon_hash in vanilla_hash_to_name:
                collided_vanilla = vanilla_hash_to_name[addon_hash]
                collisions.append(
                    {
                        "code": "ADDON_VANILLA_JOAAT_COLLISION",
                        "severity": "WARNING",
                        "slot_id": ent.slot_id,
                        "model_name": addon_name,
                        "joaat_hex": f"0x{addon_hash:08X}",
                        "collides_with": f"vanilla:{collided_vanilla}",
                        "message": (
                            f"preferred_addon_model '{addon_name}' (0x{addon_hash:08X}) in slot "
                            f"'{ent.slot_id}' collides with vanilla archetype '{collided_vanilla}'."
                        ),
                    }
                )

            # 2. Check collision against existing installed dlcpacks
            if addon_hash in installed_dlc_hash_to_name:
                collided_dlc = installed_dlc_hash_to_name[addon_hash]
                collisions.append(
                    {
                        "code": "ADDON_DLCPACK_COLLISION",
                        "severity": "WARNING",
                        "slot_id": ent.slot_id,
                        "model_name": addon_name,
                        "joaat_hex": f"0x{addon_hash:08X}",
                        "collides_with": f"dlcpacks:{collided_dlc}",
                        "message": (
                            f"preferred_addon_model '{addon_name}' (0x{addon_hash:08X}) in slot "
                            f"'{ent.slot_id}' matches existing installed DLC pack '{collided_dlc}'."
                        ),
                    }
                )

            # 3. Check duplicate addon hash across distinct entity names
            if addon_hash in seen_addon_hashes:
                prev_slot, prev_name = seen_addon_hashes[addon_hash]
                if prev_name != addon_name:
                    collisions.append(
                        {
                            "code": "INTERNAL_JOAAT_HASH_COLLISION",
                            "severity": "BLOCKING",
                            "slot_id": ent.slot_id,
                            "model_name": addon_name,
                            "joaat_hex": f"0x{addon_hash:08X}",
                            "collides_with": f"slot:{prev_slot}({prev_name})",
                            "message": (
                                f"JOAAT 32-bit hash collision (0x{addon_hash:08X}) between "
                                f"'{addon_name}' and '{prev_name}'."
                            ),
                        }
                    )
            else:
                seen_addon_hashes[addon_hash] = (ent.slot_id, addon_name)

    blocking_collisions = [c for c in collisions if c["severity"] == "BLOCKING"]
    return {
        "ok": len(blocking_collisions) == 0,
        "dlclist_files": dlclist_files,
        "registered_dlcpacks": registered_dlcpacks,
        "duplicate_dlc_entries": duplicate_dlc_entries,
        "installed_dlcpack_folders": installed_dlcpack_folders,
        "entity_hashes": entity_hashes,
        "collisions": collisions,
        "collision_count": len(collisions),
    }


def _inspect_resource_budget(
    game_dir: Path | None,
    preflight_report: dict[str, Any],
    assemblies_report: dict[str, Any],
) -> dict[str, Any]:
    """Compute active .asi/.dll count, mods/ .rpf size GB, and commit memory pressure."""
    installed = assemblies_report.get("installed_assemblies", [])
    active_asi_count = sum(1 for a in installed if a.get("extension") == ".asi")
    active_dll_count = sum(1 for a in installed if a.get("extension") == ".dll")
    active_plugin_total = active_asi_count + active_dll_count

    mods_rpf_count = 0
    mods_rpf_bytes = 0
    if game_dir is not None and game_dir.exists() and game_dir.is_dir():
        mods_dir = game_dir / "mods"
        if mods_dir.exists() and mods_dir.is_dir():
            try:
                for p in mods_dir.rglob("*.rpf"):
                    if p.is_file():
                        mods_rpf_count += 1
                        try:
                            mods_rpf_bytes += p.stat().st_size
                        except Exception:
                            pass
            except Exception:
                pass

    mods_rpf_total_gb = round(mods_rpf_bytes / (1024**3), 3)
    sys_info = preflight_report.get("system", {})
    game_info = preflight_report.get("game", {})

    commit_avail_mb = sys_info.get("commit_available_mb")
    disk_free_gb = sys_info.get("disk_free_gb", 0.0)
    disk_ok = bool(sys_info.get("disk_ok", True))
    commit_ok = bool(sys_info.get("commit_ok", True))
    processes_clear = bool(game_info.get("processes_clear", True))

    heavy_load_tight_memory = bool(
        active_plugin_total > 15
        and commit_avail_mb is not None
        and float(commit_avail_mb) < 2048.0
    )

    environment_blocked = bool(
        not disk_ok
        or not commit_ok
        or not processes_clear
        or (game_info.get("provided") and not game_info.get("exists"))
    )

    warnings: list[str] = []
    if heavy_load_tight_memory:
        warnings.append(
            f"Heavy plugin load ({active_plugin_total} active .asi/.dll files) combined with tight "
            f"OS committable memory ({commit_avail_mb} MB < 2048 MB); isolate into a clean profile."
        )
    if mods_rpf_total_gb > 25.0:
        warnings.append(
            f"Large mods/ RPF footprint ({mods_rpf_total_gb:.2f} GB across {mods_rpf_count} archives)."
        )

    return {
        "ok": not environment_blocked and not heavy_load_tight_memory,
        "environment_blocked": environment_blocked,
        "heavy_load_tight_memory": heavy_load_tight_memory,
        "active_asi_count": active_asi_count,
        "active_dll_count": active_dll_count,
        "active_plugin_total": active_plugin_total,
        "mods_rpf_count": mods_rpf_count,
        "mods_rpf_total_gb": mods_rpf_total_gb,
        "commit_available_mb": commit_avail_mb,
        "commit_total_mb": sys_info.get("commit_total_mb"),
        "commit_ok": commit_ok,
        "disk_free_gb": disk_free_gb,
        "disk_ok": disk_ok,
        "edition": game_info.get("edition", "unknown"),
        "exe_version": game_info.get("exe_version"),
        "shv_build_alias": game_info.get("shv_build_alias"),
        "running_processes": game_info.get("running_processes", []),
        "processes_clear": processes_clear,
        "warnings": warnings,
    }


def analyze_mod_conflicts(
    ir: GameplayIR | dict[str, Any],
    game_dir: str | Path | None = None,
    target_profile: str = "active",
    *,
    min_free_gb: float = 10.0,
    min_commit_mb: float = 1536.0,
    min_clearance_m: float = 15.0,
    commit_probe: Callable[[], tuple[float | None, float | None]] | None = None,
    process_probe: Callable[[], list[str]] | None = None,
) -> dict[str, Any]:
    """Run 5-Dimension Multi-Mod Conflict Arbitration and compute a deterministic Agent deployment verdict."""
    from gta_anything.conflict.keybind_scanner import (
        evaluate_keybind_conflicts,
        recommend_safe_chords,
        scan_installed_keybinds,
    )

    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    target_path = Path(game_dir) if game_dir is not None else None

    act_key = ir_obj.inputs.activation_key
    mod_key = ir_obj.inputs.modifier_key
    hotkey_str = f"{mod_key}+{act_key}" if mod_key else act_key

    # 1. Preflight check (System budget, Build IDs, Running processes)
    preflight_report = run_preflight(
        game_dir=target_path,
        min_free_gb=min_free_gb,
        min_commit_mb=min_commit_mb,
        hotkey=hotkey_str,
        commit_probe=commit_probe,
        process_probe=process_probe,
    )

    # 2. Keybind Scan & Conflict Evaluation (Dimension 1)
    if target_path is not None and target_path.exists() and target_path.is_dir():
        scanned_registry = scan_installed_keybinds(
            target_path, include_inactive_profiles=True
        )
    else:
        scanned_registry = {
            "ok": True,
            "active_profile_mode": None,
            "bindings": [],
            "scanned_files": [],
            "summary": {"total_bindings": 0, "active_bindings": 0, "inactive_bindings": 0},
        }

    keybind_eval = evaluate_keybind_conflicts(
        activation_key=act_key,
        modifier_key=mod_key,
        scanned_registry=scanned_registry,
        loader_target=ir_obj.loader_target,
        target_profile=target_profile,
    )
    safe_chords = recommend_safe_chords(scanned_registry=scanned_registry, count=5)

    # 3. Assembly & UI ABI Conflict Inspection (Dimension 2)
    if target_path is not None and target_path.exists() and target_path.is_dir():
        assemblies_abi = inspect_assembly_abi_conflicts(
            target_path,
            loader_target=ir_obj.loader_target,
            menu_library=ir_obj.inputs.menu_library,
        )
    else:
        assemblies_abi = {
            "ok": True,
            "loader_target": ir_obj.loader_target,
            "requested_menu_library": ir_obj.inputs.menu_library,
            "active_profile_mode": None,
            "active_loader_chains": [],
            "parked_profiles_with_target_loader": [],
            "loader_chain_matched": True,
            "coexistence_warning": False,
            "installed_assemblies": [],
            "ui_libraries": [],
            "conflicts": [],
            "blocking_count": 0,
            "warning_count": 0,
        }

    # 4. Spatial Turf & Spawn Overlap Inspection (Dimension 3)
    if target_path is not None and target_path.exists() and target_path.is_dir():
        spatial_turf = inspect_spatial_turf_overlaps(
            ir_obj, target_path, min_clearance_m=min_clearance_m
        )
    else:
        spatial_turf = {
            "ok": True,
            "min_clearance_m": float(min_clearance_m),
            "ir_stop_count": sum(len(t.stops) for t in ir_obj.routes_or_zones),
            "scanned_files": [],
            "discovered_host_points": 0,
            "overlaps": [],
            "overlap_count": 0,
        }

    # 5. DLC & Custom Model Hash Collision Inspection (Dimension 4)
    if target_path is not None and target_path.exists() and target_path.is_dir():
        dlc_and_models = inspect_dlc_and_model_collisions(ir_obj, target_path)
    else:
        dlc_and_models = inspect_dlc_and_model_collisions(ir_obj, Path("__nonexistent__"))

    # 6. Resource Budget & Build Identity (Dimension 5)
    resource_budget = _inspect_resource_budget(
        target_path, preflight_report, assemblies_abi
    )

    # Determine keybind conflict flags
    kb_conflicts = keybind_eval.get("conflicts", [])
    kb_blocking = [
        c for c in kb_conflicts if str(c.get("severity", "")).upper() == "BLOCKING"
    ]
    kb_warnings = [
        c for c in kb_conflicts if str(c.get("severity", "")).upper() == "CONTEXT_WARNING"
    ]
    has_keybind_conflict = (
        len(kb_blocking) > 0
        or len(kb_warnings) > 0
        or int(keybind_eval.get("blocking_count", 0)) > 0
    )

    recommended_rebind: dict[str, Any] | None = None
    if has_keybind_conflict and safe_chords:
        recommended_rebind = dict(safe_chords[0])

    # Determine assembly/profile isolation conditions
    abi_blocking = int(assemblies_abi.get("blocking_count", 0)) > 0
    loader_mismatch = not bool(assemblies_abi.get("loader_chain_matched", True))
    heavy_tight_mem = bool(resource_budget.get("heavy_load_tight_memory", False))
    dlc_blocking = not bool(dlc_and_models.get("ok", True))

    needs_profile_isolation = bool(
        abi_blocking or loader_mismatch or heavy_tight_mem or dlc_blocking
    )

    # Compute deterministic deployment_verdict
    if resource_budget["environment_blocked"]:
        deployment_verdict = "BLOCKED_ENVIRONMENT"
    elif needs_profile_isolation:
        deployment_verdict = "ISOLATE_NEW_PROFILE"
    elif has_keybind_conflict:
        deployment_verdict = "REBIND_AND_MERGE"
    else:
        deployment_verdict = "SAFE_TO_MERGE"

    has_blocking_conflicts = bool(
        resource_budget["environment_blocked"]
        or needs_profile_isolation
        or len(kb_blocking) > 0
        or int(keybind_eval.get("blocking_count", 0)) > 0
    )

    # Build actionable Agent action plan
    agent_action_plan: list[str] = []
    if deployment_verdict == "BLOCKED_ENVIRONMENT":
        for err in preflight_report.get("errors", []):
            agent_action_plan.append(f"[ENVIRONMENT] Resolve blocking preflight error: {err}")
        if not resource_budget["processes_clear"]:
            procs = ", ".join(resource_budget["running_processes"])
            agent_action_plan.append(
                f"[PROCESS] Terminate running game/loader processes ({procs}) before deployment."
            )
    elif deployment_verdict == "ISOLATE_NEW_PROFILE":
        parked = assemblies_abi.get("parked_profiles_with_target_loader", [])
        if parked:
            agent_action_plan.append(
                f"[PROFILE] Active directory is running '{assemblies_abi.get('active_profile_mode') or 'opposite loader'}'. "
                f"Switch to parked profile '{parked[0]}' (`gta-anything profile switch {parked[0]}`) or stage a dedicated profile."
            )
        else:
            agent_action_plan.append(
                f"[PROFILE] Isolate mod '{ir_obj.meta.id}' into a dedicated profile via "
                f"`gta-anything profile stage <profile_name> --mod-dir <build_dir>`."
            )
        for c in assemblies_abi.get("conflicts", []):
            agent_action_plan.append(f"[ABI] {c['code']}: {c['recommendation']}")
        if heavy_tight_mem:
            agent_action_plan.append(
                "[MEMORY] Active directory exceeds 15 plugins under < 2048 MB commit memory; avoid merging into active root."
            )
    if has_keybind_conflict and recommended_rebind:
        agent_action_plan.append(
            f"[KEYBIND] Rebind activation chord from '{keybind_eval.get('requested_chord', hotkey_str)}' "
            f"to '{recommended_rebind.get('canonical_chord')}' "
            f"(activation_key='{recommended_rebind.get('activation_key')}', "
            f"modifier_key={recommended_rebind.get('modifier_key')!r}) via `conflict-check --auto-rebind`."
        )
    if spatial_turf["overlap_count"] > 0:
        agent_action_plan.append(
            f"[SPATIAL] {spatial_turf['overlap_count']} stop(s) overlap within {min_clearance_m:.1f}m of existing mod coordinates; "
            "offset spawn/stop coordinates by >= 15m if running both mods simultaneously."
        )
    if dlc_and_models["collision_count"] > 0:
        agent_action_plan.append(
            f"[DLC_MODELS] {dlc_and_models['collision_count']} DLC/model JOAAT collision(s) detected; verify vanilla fallback or rename addon model."
        )
    if not agent_action_plan:
        agent_action_plan.append(
            f"[READY] Mod '{ir_obj.meta.id}' passed all 5 conflict dimensions and is SAFE_TO_MERGE into the target profile."
        )

    return {
        "ok": deployment_verdict != "BLOCKED_ENVIRONMENT",
        "mod_id": ir_obj.meta.id,
        "deployment_verdict": deployment_verdict,
        "has_blocking_conflicts": has_blocking_conflicts,
        "recommended_rebind": recommended_rebind,
        "recommended_safe_chords": safe_chords,
        "dimensions": {
            "keybinds": keybind_eval,
            "assemblies_abi": assemblies_abi,
            "spatial_turf": spatial_turf,
            "dlc_and_models": dlc_and_models,
            "resource_budget": resource_budget,
        },
        "agent_action_plan": agent_action_plan,
    }
