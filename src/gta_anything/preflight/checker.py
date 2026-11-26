"""Phase 0: Environment, Game Build, Dual Loader & Hotkey Preflight Checker."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import platform
import re
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# Known hotkey conflict catalog across RPH, SHVDN, Trainers, and LSPDFR
HOTKEY_CONFLICT_TABLE: dict[str, list[dict[str, str]]] = {
    "F4": [
        {
            "key": "F4",
            "owner": "RAGEPluginHook / NativeTrainer",
            "category": "console_or_trainer",
            "severity": "HIGH",
            "reason": "F4 is the default RAGEPluginHook console toggle and ScripthookV NativeTrainer hotkey.",
            "suggestion": "Use F7, F9, F10, or a modifier combination like Ctrl+F4.",
        }
    ],
    "INSERT": [
        {
            "key": "Insert",
            "owner": "ScriptHookVDotNet",
            "category": "loader_reload",
            "severity": "HIGH",
            "reason": "Insert is the default ScriptHookVDotNet ReloadKey that reloads all .NET scripts.",
            "suggestion": "Avoid Insert; use F7, F10, or a modifier combination.",
        }
    ],
    "INS": [
        {
            "key": "Insert",
            "owner": "ScriptHookVDotNet",
            "category": "loader_reload",
            "severity": "HIGH",
            "reason": "Insert is the default ScriptHookVDotNet ReloadKey that reloads all .NET scripts.",
            "suggestion": "Avoid Insert; use F7, F10, or a modifier combination.",
        }
    ],
    "F3": [
        {
            "key": "F3",
            "owner": "Simple Trainer / Menyoo",
            "category": "trainer",
            "severity": "MEDIUM",
            "reason": "F3 is commonly bound by Simple Trainer for GTA V.",
            "suggestion": "Use F7, F9, F10, or add a modifier key (e.g., Shift+F3).",
        }
    ],
    "F8": [
        {
            "key": "F8",
            "owner": "Menyoo PC / FiveM Console",
            "category": "trainer",
            "severity": "MEDIUM",
            "reason": "F8 is the default activation key for Menyoo PC trainer.",
            "suggestion": "Use F7, F9, F10, or add a modifier key (e.g., Ctrl+F8).",
        }
    ],
    "B": [
        {
            "key": "B",
            "owner": "LSPDFR (Backup Menu) / Vanilla Point",
            "category": "gameplay_interaction",
            "severity": "MEDIUM",
            "reason": "Unmodified 'B' triggers LSPDFR Backup Menu when on duty.",
            "suggestion": "Use a function key (F7/F10) or require a modifier like Alt+B / Ctrl+B.",
        }
    ],
    "N": [
        {
            "key": "N",
            "owner": "LSPDFR (Interaction Menu) / Push-To-Talk",
            "category": "gameplay_interaction",
            "severity": "MEDIUM",
            "reason": "Unmodified 'N' opens LSPDFR Police Radio / Interaction menu.",
            "suggestion": "Use a function key (F7/F10) or require a modifier like Ctrl+N.",
        }
    ],
    "E": [
        {
            "key": "E",
            "owner": "GTA V Context Action / Horn / Siren / LSPDFR Traffic Stop",
            "category": "gameplay_interaction",
            "severity": "HIGH",
            "reason": "Unmodified 'E' (INPUT_CONTEXT) conflicts with horn, sirens, and context interactions.",
            "suggestion": "Never bind top-level menu activation to unmodified 'E'; use F7 or Shift+E.",
        }
    ],
    "Y": [
        {
            "key": "Y",
            "owner": "LSPDFR Callout Accept",
            "category": "gameplay_interaction",
            "severity": "MEDIUM",
            "reason": "Unmodified 'Y' accepts LSPDFR dispatch callouts.",
            "suggestion": "Use a function key (F7/F10) or add a modifier key.",
        }
    ],
}

WATCHED_PROCESS_NAMES: tuple[str, ...] = (
    "GTA5_Enhanced",
    "GTA5",
    "PlayGTAV",
    "RAGEPluginHook",
)

LOADER_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("ScriptHookV.dll", "ScriptHookV.dll"),
    ("dinput8.dll", "dinput8.dll"),
    ("ScriptHookVDotNet.asi", "ScriptHookVDotNet.asi"),
    ("ScriptHookVDotNet2.dll", "ScriptHookVDotNet2.dll"),
    ("ScriptHookVDotNet3.dll", "ScriptHookVDotNet3.dll"),
    ("OpenRPF.asi", "OpenRPF.asi"),
    ("OpenIV.asi", "OpenIV.asi"),
    ("RAGEPluginHook.exe", "RAGEPluginHook.exe"),
    ("plugins/LSPDFR.dll", "plugins/LSPDFR.dll"),
    ("plugins/LSPD First Response.dll", "plugins/LSPD First Response.dll"),
)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.wintypes.DWORD),
        ("dwMemoryLoad", ctypes.wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", ctypes.wintypes.DWORD),
        ("ProcessCount", ctypes.wintypes.DWORD),
        ("ThreadCount", ctypes.wintypes.DWORD),
    ]


def _query_commit_memory_mb() -> tuple[float | None, float | None]:
    """Return (commit_available_mb, commit_total_mb) using OS facilities."""
    if os.name == "nt":
        # 1. Try Psapi GetPerformanceInfo (CommitLimit - CommitTotal) * PageSize
        try:
            psapi = ctypes.windll.psapi  # type: ignore[attr-defined]
            perf = _PERFORMANCE_INFORMATION()
            perf.cb = ctypes.sizeof(_PERFORMANCE_INFORMATION)
            if psapi.GetPerformanceInfo(ctypes.byref(perf), perf.cb):
                page_size = int(perf.PageSize) or 4096
                commit_limit_mb = (int(perf.CommitLimit) * page_size) / (1024 * 1024)
                commit_total_mb = (int(perf.CommitTotal) * page_size) / (1024 * 1024)
                commit_avail_mb = max(0.0, commit_limit_mb - commit_total_mb)
                return round(commit_avail_mb, 2), round(commit_limit_mb, 2)
        except Exception:
            pass

        # 2. Fallback to Kernel32 GlobalMemoryStatusEx pagefile commit metrics
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            mem = _MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                avail_mb = float(mem.ullAvailPageFile) / (1024 * 1024)
                total_mb = float(mem.ullTotalPageFile) / (1024 * 1024)
                return round(avail_mb, 2), round(total_mb, 2)
        except Exception:
            pass

    # 3. Cross-platform Linux /proc/meminfo fallback
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            text = meminfo.read_text(encoding="utf-8", errors="ignore")
            kv: dict[str, int] = {}
            for line in text.splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    num = parts[1].strip().split()[0]
                    if num.isdigit():
                        kv[parts[0].strip()] = int(num)
            if "CommitLimit" in kv and "Committed_AS" in kv:
                limit_mb = kv["CommitLimit"] / 1024.0
                used_mb = kv["Committed_AS"] / 1024.0
                return round(max(0.0, limit_mb - used_mb), 2), round(limit_mb, 2)
            if "MemAvailable" in kv and "MemTotal" in kv:
                return round(kv["MemAvailable"] / 1024.0, 2), round(kv["MemTotal"] / 1024.0, 2)
        except Exception:
            pass

    return None, None


def _extract_exe_version(exe_path: Path) -> str | None:
    """Extract PE FileVersion via Win32 API or binary VS_FIXEDFILEINFO / synthetic text fallback."""
    if not exe_path.exists() or not exe_path.is_file():
        return None

    # 1. Try Win32 GetFileVersionInfoW first on Windows
    if os.name == "nt":
        try:
            version_dll = ctypes.windll.version  # type: ignore[attr-defined]
            path_str = str(exe_path)
            handle = ctypes.wintypes.DWORD(0)
            size = version_dll.GetFileVersionInfoSizeW(path_str, ctypes.byref(handle))
            if size > 0:
                buf = ctypes.create_string_buffer(size)
                if version_dll.GetFileVersionInfoW(path_str, 0, size, buf):
                    lp_buffer = ctypes.c_void_p()
                    u_len = ctypes.wintypes.UINT(0)
                    if version_dll.VerQueryValueW(
                        buf, "\\", ctypes.byref(lp_buffer), ctypes.byref(u_len)
                    ) and u_len.value >= 52:
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

    # 2. Binary scan for VS_FIXEDFILEINFO signature 0xFEEF04BD (works cross-platform & in tests!)
    try:
        data = exe_path.read_bytes()
    except Exception:
        return None

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

    # 3. Synthetic test fixture fallback (e.g. "FileVersion=1.0.1158.16" or "1.0.3411.0" in binary/text)
    try:
        decoded_ascii = data.decode("latin-1", errors="ignore")
        m = re.search(r"\b(\d+\.\d+\.\d{3,5}\.\d+)\b", decoded_ascii)
        if m:
            return m.group(1)
        decoded_utf16 = data.decode("utf-16le", errors="ignore")
        m16 = re.search(r"\b(\d+\.\d+\.\d{3,5}\.\d+)\b", decoded_utf16)
        if m16:
            return m16.group(1)
    except Exception:
        pass

    return None


def _extract_shv_build_alias(game_dir: Path) -> str | None:
    """Parse ScriptHookV.log in game_dir to extract VER_EN_* or VER_* build alias."""
    shv_log = game_dir / "ScriptHookV.log"
    if not shv_log.exists() or not shv_log.is_file():
        return None
    try:
        content = shv_log.read_text(encoding="utf-8", errors="ignore")
        matches = re.findall(r"\b(VER_(?:EN_)?\d+_\d+_\d+_\d+[A-Z0-9_]*)\b", content)
        if matches:
            return matches[-1]
    except Exception:
        pass
    return None


def _detect_running_gta_processes(
    process_probe: Callable[[], list[str]] | None = None,
) -> list[str]:
    """Detect whether watched GTA / RPH executables are currently running."""
    if process_probe is not None:
        raw_names = process_probe()
        found: list[str] = []
        for watched in WATCHED_PROCESS_NAMES:
            if any(
                p.lower() in (watched.lower(), f"{watched.lower()}.exe")
                for p in raw_names
            ):
                found.append(watched)
        return found

    found_procs: list[str] = []
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            output_lower = proc.stdout.lower()
            for watched in WATCHED_PROCESS_NAMES:
                if f'"{watched.lower()}.exe"' in output_lower:
                    found_procs.append(watched)
        except Exception:
            pass
    return found_procs


def _check_hotkey_conflicts(hotkey: str | None) -> list[dict[str, str]]:
    """Check requested hotkey against known GTA V loader/trainer/gameplay key bindings."""
    if not hotkey or not hotkey.strip():
        return []

    raw = hotkey.strip()
    parts = [p.strip().upper() for p in re.split(r"[+\-\s]+", raw) if p.strip()]
    if not parts:
        return []

    has_modifier = any(
        p in {"CTRL", "CONTROL", "ALT", "SHIFT", "LCTRL", "RCTRL", "LALT", "RALT", "LSHIFT", "RSHIFT"}
        for p in parts
    )
    primary_key = parts[-1]

    entries = HOTKEY_CONFLICT_TABLE.get(primary_key, [])
    conflicts: list[dict[str, str]] = []
    for entry in entries:
        # Single-letter gameplay keys (B/N/E/Y) or trainer keys are safe if paired with a modifier,
        # whereas F4/Insert remain risky or merit a lower-severity note if modified.
        if has_modifier and entry["category"] in {"gameplay_interaction", "trainer"}:
            continue
        conflicts.append(dict(entry))
    return conflicts


def run_preflight(
    game_dir: str | Path | None = None,
    min_free_gb: float = 10.0,
    min_commit_mb: float = 1536.0,
    hotkey: str | None = None,
    *,
    process_probe: Callable[[], list[str]] | None = None,
    commit_probe: Callable[[], tuple[float | None, float | None]] | None = None,
) -> dict[str, Any]:
    """Run Phase 0 preflight checks for disk space, committable memory, game build, loaders, and hotkeys."""
    warnings: list[str] = []
    errors: list[str] = []

    target_dir = Path(game_dir) if game_dir is not None else Path.cwd()
    probe_dir = target_dir if target_dir.exists() else Path.cwd()

    try:
        resolved_probe = probe_dir.resolve()
        disk_drive = resolved_probe.drive or str(resolved_probe.anchor or "/")
        usage = shutil.disk_usage(resolved_probe)
        disk_free_gb = round(usage.free / (1024**3), 2)
    except Exception:
        disk_drive = ""
        disk_free_gb = 0.0

    disk_ok = disk_free_gb >= float(min_free_gb)
    if not disk_ok:
        errors.append(
            f"Low disk free space on {disk_drive or 'target drive'}: "
            f"{disk_free_gb:.2f} GB free (< {min_free_gb:.2f} GB required)."
        )

    commit_avail_mb, commit_total_mb = (
        commit_probe() if commit_probe is not None else _query_commit_memory_mb()
    )
    commit_ok = True
    if commit_avail_mb is not None:
        if commit_avail_mb < 1024.0:
            commit_ok = False
            errors.append(
                f"Critically low OS committable memory: {commit_avail_mb:.1f} MB available "
                "(< 1024.0 MB hard threshold). High risk of mid-session crash or DX allocation failure."
            )
        elif commit_avail_mb < float(min_commit_mb):
            warnings.append(
                f"Low OS committable memory: {commit_avail_mb:.1f} MB available "
                f"(< {min_commit_mb:.1f} MB recommended threshold)."
            )

    game_provided = game_dir is not None
    game_exists = bool(game_provided and target_dir.exists() and target_dir.is_dir())
    edition = "unknown"
    exe_path_str: str | None = None
    exe_version: str | None = None
    shv_build_alias: str | None = None
    active_profile_mode: str | None = None
    detected_loaders: list[str] = []

    if game_provided and not game_exists:
        errors.append(f"Specified game_dir does not exist: {target_dir}")

    if game_exists:
        active_mode_file = target_dir / "GTA5-Profiles" / "ActiveMode.txt"
        if active_mode_file.exists() and active_mode_file.is_file():
            try:
                mode_text = active_mode_file.read_text(encoding="utf-8", errors="replace").strip()
                if mode_text:
                    active_profile_mode = mode_text.splitlines()[0].strip()
            except Exception:
                pass

        enhanced_exe = target_dir / "GTA5_Enhanced.exe"
        legacy_exe = target_dir / "GTA5.exe"

        if enhanced_exe.exists():
            edition = "enhanced_gen9"
            exe_path_str = str(enhanced_exe)
            exe_version = _extract_exe_version(enhanced_exe)
        elif legacy_exe.exists():
            edition = "legacy_gen8"
            exe_path_str = str(legacy_exe)
            exe_version = _extract_exe_version(legacy_exe)
        else:
            warnings.append(
                "Neither GTA5_Enhanced.exe nor GTA5.exe found in game_dir; edition is unknown."
            )

        shv_build_alias = _extract_shv_build_alias(target_dir)

        for rel_path, label in LOADER_SIGNATURES:
            candidate = target_dir / rel_path
            if candidate.exists():
                detected_loaders.append(label)

        has_shvdn = "ScriptHookVDotNet.asi" in detected_loaders
        has_rph = "RAGEPluginHook.exe" in detected_loaders or any(
            l.startswith("plugins/") for l in detected_loaders
        )
        if has_shvdn and has_rph:
            warnings.append(
                "Both SHVDN/ASI chain and RPH/LSPDFR chain detected in the same directory; "
                "use ProfileManager to isolate heavy profiles and prevent hotkey/memory contention."
            )

    running_processes = _detect_running_gta_processes(process_probe=process_probe)
    processes_clear = len(running_processes) == 0
    if not processes_clear:
        warnings.append(
            f"Active game/loader processes detected ({', '.join(running_processes)}); "
            "close them before switching profiles or deploying files."
        )

    conflicts = _check_hotkey_conflicts(hotkey)
    for conflict in conflicts:
        msg = (
            f"Hotkey conflict on '{conflict['key']}' with {conflict['owner']}: "
            f"{conflict['reason']} ({conflict['suggestion']})"
        )
        warnings.append(msg)

    installed_keybind_summary: dict[str, Any] | None = None
    recommended_safe_chords: list[dict[str, Any]] = []
    try:
        from gta_anything.conflict.keybind_scanner import (
            evaluate_keybind_conflicts,
            recommend_safe_chords,
            scan_installed_keybinds,
        )

        scanned_registry: dict[str, Any] | None = None
        if game_exists:
            scanned_registry = scan_installed_keybinds(
                target_dir, include_inactive_profiles=True
            )
            installed_keybind_summary = scanned_registry.get("summary")
            if active_profile_mode is None and scanned_registry.get("active_profile_mode"):
                active_profile_mode = scanned_registry.get("active_profile_mode")

            if hotkey and hotkey.strip():
                hk_parts = [p.strip() for p in re.split(r"[+]+", hotkey.strip()) if p.strip()]
                act_key = hk_parts[-1] if hk_parts else hotkey.strip()
                mod_key = "+".join(hk_parts[:-1]) if len(hk_parts) > 1 else None
                dyn_eval = evaluate_keybind_conflicts(
                    activation_key=act_key,
                    modifier_key=mod_key,
                    scanned_registry=scanned_registry,
                )
                for finding in dyn_eval.get("conflicts", []):
                    rel_path = finding.get("relative_path")
                    if not rel_path:
                        continue
                    dyn_entry = {
                        "key": finding.get("canonical_chord") or hotkey,
                        "owner": finding.get("owner_mod") or "InstalledMod",
                        "category": finding.get("context_scope") or "installed_ini",
                        "severity": finding.get("severity") or "CONTEXT_WARNING",
                        "reason": finding.get("reason") or f"Collides with {rel_path}:{finding.get('line')}",
                        "suggestion": finding.get("suggestion") or "Choose a conflict-free chord from recommended_safe_chords.",
                        "relative_path": rel_path,
                        "line": finding.get("line"),
                        "profile": finding.get("profile"),
                    }
                    conflicts.append(dyn_entry)
                    if str(finding.get("severity", "")).upper() in {"BLOCKING", "CONTEXT_WARNING"}:
                        warnings.append(
                            f"Dynamic keybind collision on '{dyn_entry['key']}' with "
                            f"{dyn_entry['owner']} ({rel_path}:{dyn_entry['line']}): {dyn_entry['reason']}"
                        )

        recommended_safe_chords = recommend_safe_chords(
            scanned_registry=scanned_registry, count=5
        )
    except Exception:
        pass

    ok = len(errors) == 0 and disk_ok and commit_ok

    return {
        "ok": ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_profile_mode": active_profile_mode,
        "system": {
            "os": f"{platform.system()} {platform.release()}".strip(),
            "disk_drive": disk_drive,
            "disk_free_gb": disk_free_gb,
            "disk_ok": disk_ok,
            "commit_available_mb": commit_avail_mb,
            "commit_total_mb": commit_total_mb,
            "commit_ok": commit_ok,
        },
        "game": {
            "provided": game_provided,
            "exists": game_exists,
            "edition": edition,
            "exe_path": exe_path_str,
            "exe_version": exe_version,
            "shv_build_alias": shv_build_alias,
            "active_profile_mode": active_profile_mode,
            "detected_loaders": detected_loaders,
            "running_processes": running_processes,
            "processes_clear": processes_clear,
        },
        "hotkey_check": {
            "requested_hotkey": hotkey,
            "conflicts": conflicts,
            "recommended_safe_chords": recommended_safe_chords,
            "installed_keybind_summary": installed_keybind_summary,
        },
        "warnings": warnings,
        "errors": errors,
    }
