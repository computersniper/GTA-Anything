"""Phase 7: Multi-Log Correlator across ScriptHookV, SHVDN, RPH, and Phased JSONL Telemetry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TIMESTAMP_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?|\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b)"
)
SHV_BUILD_RE = re.compile(r"\b(VER_(?:EN_)?\d+_\d+_\d+_\d+[A-Z0-9_]*)\b")
LAYER_TAG_RE = re.compile(r"\bL([1-7])\b|\"layer\"\s*:\s*([1-7])", re.IGNORECASE)

PHASE_TO_LAYER: dict[str, int] = {
    "configloaded": 1,
    "config_loaded": 1,
    "asset_read": 1,
    "loader_detected": 2,
    "loader_ready": 2,
    "script_init": 3,
    "initialized": 3,
    "menuselecting": 4,
    "menu_open": 4,
    "menu_selecting": 4,
    "resourcestreaming": 5,
    "spawning": 5,
    "shift_start": 5,
    "mission_start": 5,
    "activeoperation": 6,
    "active_operation": 6,
    "stop_reached": 6,
    "checkpoint_reached": 6,
    "completing": 6,
    "teardown": 7,
    "disposeall": 7,
    "disposed": 7,
    "cleanup_complete": 7,
}


def _extract_timestamp(text: str, fallback_idx: int) -> str:
    m = TIMESTAMP_RE.search(text)
    if m:
        return m.group(1)
    return f"00:00:{fallback_idx:04d}"


def _make_issue(
    *,
    category: str,
    severity: str,
    code: str,
    source: str,
    timestamp: str,
    message: str,
    evidence: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "category": category,  # "environment" | "loader" | "asset" | "script_logic"
        "severity": severity,  # "CRITICAL" | "ERROR" | "WARNING"
        "code": code,
        "source": source,
        "timestamp": timestamp,
        "message": message,
        "evidence": evidence.strip()[:300],
        "recommendation": recommendation,
    }


def _parse_jsonl_file(
    path: Path,
    seq_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    timeline: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    highest_layer = 0

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return timeline, issues, highest_layer

    for offset, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        ts = _extract_timestamp(stripped, seq_start + offset)
        try:
            record = json.loads(stripped)
        except Exception:
            continue

        ts = str(
            record.get("timestampUtc")
            or record.get("timestamp")
            or record.get("ts")
            or ts
        )
        phase = str(record.get("phase") or record.get("state") or record.get("event") or "")
        event_name = str(record.get("event") or "")
        details_str = str(record.get("details") or "")
        error_str = str(record.get("error") or "")
        level = "ERROR" if error_str else str(record.get("level") or record.get("severity") or "INFO").upper()
        msg = str(
            record.get("message")
            or record.get("msg")
            or (f"{event_name}: {details_str}" if event_name and details_str else event_name)
            or phase
            or stripped
        )

        layer = record.get("layer") or record.get("acceptance_layer")
        layer_num = 0
        if isinstance(layer, int) and 1 <= layer <= 7:
            layer_num = layer
        elif isinstance(layer, str):
            m = re.search(r"([1-7])", layer)
            if m:
                layer_num = int(m.group(1))
        if layer_num == 0 and phase:
            layer_num = PHASE_TO_LAYER.get(phase.lower().replace(" ", ""), 0)

        if layer_num > highest_layer:
            highest_layer = layer_num

        timeline.append(
            {
                "timestamp": ts,
                "source": path.name,
                "layer": layer_num or None,
                "phase": phase or None,
                "level": level,
                "event": msg,
            }
        )

        combined_lower = f"{phase} {msg} {json.dumps(record)}".lower()
        if "timeout" in combined_lower and ("stream" in combined_lower or "model" in combined_lower):
            issues.append(
                _make_issue(
                    category="asset",
                    severity="ERROR",
                    code="MODEL_STREAM_TIMEOUT",
                    source=path.name,
                    timestamp=ts,
                    message=f"Model streaming timeout in telemetry: {msg}",
                    evidence=stripped,
                    recommendation=(
                        "Call Model.MarkAsNoLongerNeeded() immediately on stream timeout, verify "
                        "dlclist.xml registration (Gate 2) and Gen9 .yft=171/.ytd=5 format (Gate 1), "
                        "and fall back to vanilla_fallback_model."
                    ),
                )
            )
        if "script_rt" in combined_lower and ("dxt1" in combined_lower or "crash" in combined_lower or "error" in combined_lower):
            issues.append(
                _make_issue(
                    category="asset",
                    severity="CRITICAL",
                    code="GEN9_SCRIPT_RT_FORMAT_CRASH",
                    source=path.name,
                    timestamp=ts,
                    message="Render-target texture (script_rt_*) format crash detected on Gen9.",
                    evidence=stripped,
                    recommendation=(
                        "Convert script_rt_* (e.g. script_rt_dials_race) in the vehicle .ytd from "
                        "DXT1 to single-mip (mipCount=1) B8G8R8A8_UNORM."
                    ),
                )
            )
        if "nullreferenceexception" in combined_lower:
            issues.append(
                _make_issue(
                    category="script_logic",
                    severity="ERROR",
                    code="SCRIPT_NULL_REFERENCE",
                    source=path.name,
                    timestamp=ts,
                    message=f"NullReferenceException reported in telemetry: {msg}",
                    evidence=stripped,
                    recommendation=(
                        "Decouple menu UI selection from 3D CreateVehicle preview and null-check "
                        "spawned vehicle handles before calling entity methods."
                    ),
                )
            )

    return timeline, issues, highest_layer


def _parse_text_log_file(
    path: Path,
    seq_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, str | None]:
    timeline: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    highest_layer = 0
    detected_alias: str | None = None

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return timeline, issues, highest_layer, detected_alias

    lines = content.splitlines()
    if lines:
        highest_layer = max(highest_layer, 1)

    for offset, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        ts = _extract_timestamp(stripped, seq_start + offset)
        lower = stripped.lower()

        # Check ScriptHookV build alias (e.g. VER_EN_1_0_1158_13)
        alias_match = SHV_BUILD_RE.search(stripped)
        if alias_match:
            detected_alias = alias_match.group(1)
            highest_layer = max(highest_layer, 2)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 2,
                    "phase": "loader_detected",
                    "level": "INFO",
                    "event": f"Detected ScriptHookV build alias {detected_alias}: {stripped}",
                }
            )

        # Track explicit layer markers or lifecycle milestones in text logs
        layer_m = LAYER_TAG_RE.search(stripped)
        if layer_m:
            l_val = int(layer_m.group(1) or layer_m.group(2))
            highest_layer = max(highest_layer, l_val)

        if any(k in lower for k in ("loading *.asi", "initializing", "asiplugins", "loaded plugin")):
            highest_layer = max(highest_layer, 2)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 2,
                    "phase": "loader_ready",
                    "level": "INFO",
                    "event": stripped,
                }
            )
        elif any(k in lower for k in ("instantiating script", "started script", "found 1 script", "found 2 script")):
            highest_layer = max(highest_layer, 3)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 3,
                    "phase": "script_init",
                    "level": "INFO",
                    "event": stripped,
                }
            )
        elif any(k in lower for k in ("menuselecting", "menu opened", "static_metadata", "static_sprite")):
            highest_layer = max(highest_layer, 4)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 4,
                    "phase": "menu_selecting",
                    "level": "INFO",
                    "event": stripped,
                }
            )
        elif any(k in lower for k in ("spawning", "shift started", "route started", "createvehicle")):
            highest_layer = max(highest_layer, 5)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 5,
                    "phase": "spawning",
                    "level": "INFO",
                    "event": stripped,
                }
            )
        elif any(k in lower for k in ("activeoperation", "stop reached", "passenger boarded", "checkpoint")):
            highest_layer = max(highest_layer, 6)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 6,
                    "phase": "active_operation",
                    "level": "INFO",
                    "event": stripped,
                }
            )
        elif any(k in lower for k in ("teardown", "disposeall", "worldsession disposed", "unloading")):
            highest_layer = max(highest_layer, 7)
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": 7,
                    "phase": "teardown",
                    "level": "INFO",
                    "event": stripped,
                }
            )

        # Issue classification rules
        # 1. Environment issues (DX memory, out of memory, pagefile/commit, disk full)
        if any(
            k in lower
            for k in (
                "err_mem_embeddedalloc",
                "d3d_err",
                "dxgi_error",
                "outofmemoryexception",
                "out of memory",
                "failed to allocate",
                "pagefile",
                "commit limit",
                "disk full",
                "no space left",
            )
        ):
            issues.append(
                _make_issue(
                    category="environment",
                    severity="CRITICAL",
                    code="ENV_RESOURCE_EXHAUSTION",
                    source=path.name,
                    timestamp=ts,
                    message=f"System memory/graphics/disk resource exhaustion: {stripped}",
                    evidence=stripped,
                    recommendation=(
                        "Verify OS committable memory >= 1536 MB and target disk free space >= 10 GB "
                        "via `gta-anything preflight`, and release unused streaming models."
                    ),
                )
            )
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": highest_layer or None,
                    "phase": "error",
                    "level": "CRITICAL",
                    "event": stripped,
                }
            )

        # 2. Loader issues (FATAL: Unknown game version, failed to load assembly, missing dependency)
        if any(
            k in lower
            for k in (
                "fatal: unknown game version",
                "unknown game version",
                "failed to load assembly",
                "filenotfoundexception",
                "could not load file or assembly",
                "badimageformatexception",
                "asi loader error",
            )
        ):
            issues.append(
                _make_issue(
                    category="loader",
                    severity="CRITICAL",
                    code="LOADER_COMPATIBILITY_FAILURE",
                    source=path.name,
                    timestamp=ts,
                    message=f"Loader/ABI mismatch or missing assembly: {stripped}",
                    evidence=stripped,
                    recommendation=(
                        "Verify ScriptHookV / SHVDN edition matches GTA5_Enhanced.exe (Gen9) vs "
                        "GTA5.exe (Gen8) and ensure all required runtime assemblies are staged."
                    ),
                )
            )
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": highest_layer or 2,
                    "phase": "loader_error",
                    "level": "CRITICAL",
                    "event": stripped,
                }
            )

        # 3. Script logic issues (NullReferenceException, OnIndexChange preview spawn, unhandled exception)
        if "nullreferenceexception" in lower or (
            "unhandled exception" in lower and "nullreference" in content.lower()
        ):
            is_preview_bug = any(
                k in content.lower()
                for k in ("onindexchange", "createvehicle", "removeallextras", "preview")
            )
            msg = (
                "NullReferenceException during menu preview / synchronous CreateVehicle call."
                if is_preview_bug
                else f"NullReferenceException in script execution: {stripped}"
            )
            rec = (
                "Decouple menu UI from 3D vehicle spawning: never call CreateVehicle inside "
                "OnIndexChange; use static_metadata or static_sprite preview_mode and guard "
                "spawned vehicle handles with null/Exists() checks."
                if is_preview_bug
                else "Add null and Exists() checks around world entity handles and register "
                "entities in WorldSession."
            )
            issues.append(
                _make_issue(
                    category="script_logic",
                    severity="ERROR",
                    code="SCRIPT_NULL_REFERENCE_PREVIEW" if is_preview_bug else "SCRIPT_NULL_REFERENCE",
                    source=path.name,
                    timestamp=ts,
                    message=msg,
                    evidence=stripped,
                    recommendation=rec,
                )
            )
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": highest_layer or 4,
                    "phase": "script_exception",
                    "level": "ERROR",
                    "event": stripped,
                }
            )
        elif any(k in lower for k in ("unhandled exception", "caught fatal unhandled exception")):
            issues.append(
                _make_issue(
                    category="script_logic",
                    severity="ERROR",
                    code="SCRIPT_UNHANDLED_EXCEPTION",
                    source=path.name,
                    timestamp=ts,
                    message=f"Unhandled script exception: {stripped}",
                    evidence=stripped,
                    recommendation=(
                        "Wrap tick/state transitions in OperationalStateMachine try/catch and "
                        "transition cleanly to Teardown (WorldSession.DisposeAll)."
                    ),
                )
            )
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": highest_layer or 3,
                    "phase": "script_exception",
                    "level": "ERROR",
                    "event": stripped,
                }
            )

        # 4. Asset issues (model stream timeout, script_rt DXT1 crash, invalid model hash)
        if any(
            k in lower
            for k in (
                "script_rt",
                "dxt1",
                "model stream timeout",
                "streaming timeout",
                "failed to stream model",
                "invalid model",
                "cannot load model",
            )
        ):
            is_rt = "script_rt" in lower or "dxt1" in lower
            issues.append(
                _make_issue(
                    category="asset",
                    severity="CRITICAL" if is_rt else "ERROR",
                    code="GEN9_SCRIPT_RT_FORMAT_CRASH" if is_rt else "ASSET_STREAMING_FAILURE",
                    source=path.name,
                    timestamp=ts,
                    message=(
                        f"Gen9 script_rt render-target format error: {stripped}"
                        if is_rt
                        else f"Asset streaming / model loading failure: {stripped}"
                    ),
                    evidence=stripped,
                    recommendation=(
                        "Convert script_rt_* textures in .ytd from DXT1 to single-mip B8G8R8A8_UNORM "
                        "and run `gta-anything asset-check`."
                        if is_rt
                        else "Call MarkAsNoLongerNeeded() on stream timeout, fall back to "
                        "vanilla_fallback_model, and audit DLC registration via `gta-anything asset-check`."
                    ),
                )
            )
            timeline.append(
                {
                    "timestamp": ts,
                    "source": path.name,
                    "layer": highest_layer or 5,
                    "phase": "asset_error",
                    "level": "ERROR",
                    "event": stripped,
                }
            )

    return timeline, issues, highest_layer, detected_alias


def diagnose_logs(
    log_paths: list[str | Path],
    commit_available_mb: float | None = None,
) -> dict[str, Any]:
    """Correlate ScriptHookV, SHVDN, RPH, and JSONL logs into a timeline with root-cause attribution."""
    timeline: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    highest_layer = 0
    detected_build_alias: str | None = None

    if commit_available_mb is not None:
        if commit_available_mb < 1024.0:
            issues.append(
                _make_issue(
                    category="environment",
                    severity="CRITICAL",
                    code="LOW_COMMIT_MEMORY_CRITICAL",
                    source="system_preflight",
                    timestamp="00:00:0000",
                    message=(
                        f"OS committable memory is critically low ({commit_available_mb:.1f} MB < 1024.0 MB). "
                        "Process termination or DirectX allocation failure is likely an environment exhaustion "
                        "rather than a script logic defect."
                    ),
                    evidence=f"commit_available_mb={commit_available_mb}",
                    recommendation=(
                        "Close memory-heavy background apps or expand OS pagefile so committable memory "
                        "exceeds 1536 MB before running high-load GTA V mod sessions."
                    ),
                )
            )
        elif commit_available_mb < 1536.0:
            issues.append(
                _make_issue(
                    category="environment",
                    severity="WARNING",
                    code="LOW_COMMIT_MEMORY_WARNING",
                    source="system_preflight",
                    timestamp="00:00:0000",
                    message=(
                        f"OS committable memory is below recommended margin ({commit_available_mb:.1f} MB < 1536.0 MB)."
                    ),
                    evidence=f"commit_available_mb={commit_available_mb}",
                    recommendation="Free at least 1536 MB of committable memory before loading addon DLC packs.",
                )
            )

    seq_counter = 0
    for raw_path in log_paths:
        p = Path(raw_path)
        seq_counter += 1000
        if not p.exists() or not p.is_file():
            issues.append(
                _make_issue(
                    category="environment",
                    severity="WARNING",
                    code="LOG_FILE_MISSING",
                    source=str(p),
                    timestamp=f"00:00:{seq_counter:04d}",
                    message=f"Log file does not exist: {p}",
                    evidence=str(p),
                    recommendation="Verify log file path or check if the corresponding loader ran.",
                )
            )
            continue

        if p.suffix.lower() == ".jsonl":
            tl, iss, layer = _parse_jsonl_file(p, seq_counter)
            timeline.extend(tl)
            issues.extend(iss)
            highest_layer = max(highest_layer, layer)
        else:
            tl, iss, layer, alias = _parse_text_log_file(p, seq_counter)
            timeline.extend(tl)
            issues.extend(iss)
            highest_layer = max(highest_layer, layer)
            if alias:
                detected_build_alias = alias

    timeline.sort(key=lambda item: str(item.get("timestamp", "")))

    # Deduplicate recommendations while preserving priority order
    recommendations: list[str] = []
    seen_recs: set[str] = set()
    for issue in issues:
        rec = issue.get("recommendation", "")
        if rec and rec not in seen_recs:
            seen_recs.add(rec)
            recommendations.append(rec)

    if not recommendations:
        recommendations.append(
            "All parsed logs completed cleanly with no environment, loader, asset, or script_logic errors."
        )

    has_blocking = any(
        i["severity"] in {"CRITICAL", "ERROR"} for i in issues
    )

    return {
        "ok": not has_blocking,
        "detected_build_alias": detected_build_alias,
        "highest_acceptance_layer_reached": highest_layer,
        "timeline": timeline,
        "issues": issues,
        "recommendations": recommendations,
    }
