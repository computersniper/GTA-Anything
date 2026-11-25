"""Phase 4: 5-Stage Asset Gate static auditor for GTA V Gen8 (Legacy) and Gen9 (Enhanced)."""

from __future__ import annotations

import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


RSC7_MAGIC = 0x37435352  # b"RSC7" little-endian
RSC8_MAGIC = 0x38435352  # b"RSC8" little-endian
DDS_MAGIC = b"DDS "

EXPECTED_VERSIONS: dict[str, dict[str, set[int]]] = {
    "enhanced_gen9": {
        ".yft": {171},
        ".ytd": {5},
    },
    "legacy_gen8": {
        ".yft": {162},
        ".ytd": {13},
    },
}

LEGACY_VERSIONS: dict[str, set[int]] = {
    ".yft": {162},
    ".ytd": {13},
}

GEN9_VERSIONS: dict[str, set[int]] = {
    ".yft": {171},
    ".ytd": {5},
}


def _make_finding(
    *,
    gate: str,
    severity: str,
    code: str,
    file_path: Path,
    message: str,
    remediation: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "severity": severity,  # "ERROR" | "HIGH" | "WARNING" | "INFO"
        "code": code,
        "file": str(file_path),
        "message": message,
        "remediation": remediation,
        "details": details or {},
    }


def _parse_rsc_version(data: bytes) -> tuple[str | None, int | None]:
    """Extract (header_kind, resource_version) from RSC7/RSC8 binary header or JSON/text fixture."""
    if len(data) >= 8:
        magic, version = struct.unpack("<II", data[:8])
        if magic == RSC7_MAGIC:
            return "RSC7", int(version & 0xFFFF)
        if magic == RSC8_MAGIC:
            return "RSC8", int(version & 0xFFFF)

    # Support JSON / text test fixtures embedded in .yft / .ytd / .json files
    try:
        text = data.decode("utf-8", errors="ignore").strip()
        if text.startswith("{"):
            obj = json.loads(text)
            ver = obj.get("rsc_version") or obj.get("version") or obj.get("resource_version")
            if isinstance(ver, int):
                return str(obj.get("magic", "JSON_FIXTURE")), ver
        m = re.search(r"(?:rsc_version|version)\s*[:=]\s*(\d+)", text, re.IGNORECASE)
        if m:
            return "TEXT_FIXTURE", int(m.group(1))
    except Exception:
        pass

    return None, None


def _inspect_script_rt_and_textures(
    file_path: Path,
    data: bytes,
    target_edition: str,
) -> list[dict[str, Any]]:
    """Scan binary or fixture metadata for script_rt_* textures and DXT1 / mipCount incompatibilities."""
    findings: list[dict[str, Any]] = []
    text_view = data.decode("latin-1", errors="ignore")

    # Find script_rt_* texture identifiers (e.g. script_rt_dials_race, script_rt_dials_*)
    rt_matches = sorted(set(re.findall(r"(script_rt_[a-zA-Z0-9_]+)", text_view, re.IGNORECASE)))
    if not rt_matches and "script_rt" in file_path.name.lower():
        rt_matches = [file_path.stem]

    has_dxt1_fourcc = (
        b"DXT1" in data
        or bool(re.search(r"\bBC1(?:_UNORM)?\b", text_view, re.IGNORECASE))
    )
    has_bgra8 = (
        b"B8G8R8A8" in data
        or b"A8R8G8B8" in data
        or bool(re.search(r"B8G8R8A8_UNORM|A8R8G8B8", text_view, re.IGNORECASE))
    )

    # Check DDS header if file is a .dds or embeds a DDS header
    dds_idx = data.find(DDS_MAGIC)
    mip_count: int | None = None
    dds_fourcc: str | None = None
    if dds_idx != -1 and dds_idx + 128 <= len(data):
        dds_hdr = data[dds_idx : dds_idx + 128]
        # DDS_HEADER: offset 28 is dwMipMapCount, offset 84 is ddspf.dwFourCC
        raw_mips = struct.unpack("<I", dds_hdr[28:32])[0]
        if 0 < raw_mips < 64:
            mip_count = int(raw_mips)
        fourcc_bytes = dds_hdr[84:88]
        if fourcc_bytes.strip(b"\x00"):
            dds_fourcc = fourcc_bytes.decode("latin-1", errors="ignore")
            if dds_fourcc == "DXT1":
                has_dxt1_fourcc = True

    # Also check JSON/text metadata for mip_count / format
    try:
        utf8_text = data.decode("utf-8", errors="ignore").strip()
        if utf8_text.startswith("{"):
            obj = json.loads(utf8_text)
            textures = obj.get("textures", [obj])
            if isinstance(textures, list):
                for tex in textures:
                    if not isinstance(tex, dict):
                        continue
                    t_name = str(tex.get("name", ""))
                    t_fmt = str(tex.get("format", "")).upper()
                    t_mips = tex.get("mip_count") or tex.get("mips") or tex.get("mipCount")
                    if "script_rt" in t_name.lower() and t_name not in rt_matches:
                        rt_matches.append(t_name)
                    if "DXT1" in t_fmt or "BC1" in t_fmt:
                        has_dxt1_fourcc = True
                    if isinstance(t_mips, int):
                        mip_count = t_mips
    except Exception:
        pass

    if rt_matches and target_edition == "enhanced_gen9":
        rt_list_str = ", ".join(rt_matches)
        if has_dxt1_fourcc:
            findings.append(
                _make_finding(
                    gate="gate_1_static_binary",
                    severity="HIGH",
                    code="GEN9_SCRIPT_RT_DXT1_CRASH",
                    file_path=file_path,
                    message=(
                        f"Gen9 incompatible render-target texture ({rt_list_str}) uses legacy DXT1/BC1 "
                        "compression, which causes GTA V Enhanced (Gen9) to crash on vehicle dial rendering."
                    ),
                    remediation=(
                        f"Re-export {rt_list_str} in '{file_path.name}' as uncompressed single-mip "
                        "(mipCount=1) B8G8R8A8_UNORM (A8R8G8B8) before packaging for Gen9."
                    ),
                    details={
                        "textures": rt_matches,
                        "detected_format": dds_fourcc or "DXT1",
                        "expected_format": "B8G8R8A8_UNORM",
                        "mip_count": mip_count,
                    },
                )
            )
        if mip_count is not None and mip_count > 1:
            findings.append(
                _make_finding(
                    gate="gate_1_static_binary",
                    severity="HIGH",
                    code="GEN9_SCRIPT_RT_MIPCOUNT_INVALID",
                    file_path=file_path,
                    message=(
                        f"Gen9 render-target texture ({rt_list_str}) has mipCount={mip_count} (> 1)."
                    ),
                    remediation=(
                        f"Convert {rt_list_str} to a single-mip (mipCount=1) B8G8R8A8_UNORM texture."
                    ),
                    details={
                        "textures": rt_matches,
                        "mip_count": mip_count,
                        "expected_mip_count": 1,
                    },
                )
            )
        elif not has_dxt1_fourcc and has_bgra8:
            findings.append(
                _make_finding(
                    gate="gate_1_static_binary",
                    severity="INFO",
                    code="GEN9_SCRIPT_RT_VALID",
                    file_path=file_path,
                    message=f"Render-target texture ({rt_list_str}) uses Gen9-compatible B8G8R8A8_UNORM format.",
                    remediation="No action needed.",
                    details={"textures": rt_matches, "format": "B8G8R8A8_UNORM"},
                )
            )

    return findings


def _audit_single_binary_asset(
    file_path: Path,
    target_edition: str,
) -> list[dict[str, Any]]:
    """Gate 1: Audit a .yft, .ytd, or .dds file for resource version and script_rt texture safety."""
    findings: list[dict[str, Any]] = []
    suffix = file_path.suffix.lower()
    try:
        data = file_path.read_bytes()
    except Exception as exc:
        return [
            _make_finding(
                gate="gate_1_static_binary",
                severity="ERROR",
                code="ASSET_READ_ERROR",
                file_path=file_path,
                message=f"Failed to read asset file: {exc}",
                remediation="Verify file permissions and integrity.",
            )
        ]

    if suffix in {".yft", ".ytd"}:
        header_kind, rsc_ver = _parse_rsc_version(data)
        expected_set = EXPECTED_VERSIONS.get(target_edition, {}).get(suffix, set())
        if rsc_ver is not None:
            if expected_set and rsc_ver not in expected_set:
                expected_str = "/".join(str(v) for v in sorted(expected_set))
                is_legacy_on_gen9 = (
                    target_edition == "enhanced_gen9"
                    and rsc_ver in LEGACY_VERSIONS.get(suffix, set())
                )
                is_gen9_on_legacy = (
                    target_edition == "legacy_gen8"
                    and rsc_ver in GEN9_VERSIONS.get(suffix, set())
                )
                if is_legacy_on_gen9:
                    findings.append(
                        _make_finding(
                            gate="gate_1_static_binary",
                            severity="ERROR",
                            code="GEN9_LEGACY_RSC_VERSION",
                            file_path=file_path,
                            message=(
                                f"Legacy Gen8 {suffix} resource version {rsc_ver} detected when targeting "
                                f"enhanced_gen9 (expected version {expected_str})."
                            ),
                            remediation=(
                                f"Convert '{file_path.name}' from Gen8 (v{rsc_ver}) to Gen9 "
                                f"({suffix} v{expected_str}) and verify script_rt_* textures."
                            ),
                            details={
                                "header": header_kind,
                                "detected_version": rsc_ver,
                                "expected_versions": sorted(expected_set),
                            },
                        )
                    )
                elif is_gen9_on_legacy:
                    findings.append(
                        _make_finding(
                            gate="gate_1_static_binary",
                            severity="ERROR",
                            code="GEN8_ENHANCED_RSC_VERSION",
                            file_path=file_path,
                            message=(
                                f"Gen9 {suffix} resource version {rsc_ver} detected when targeting "
                                f"legacy_gen8 (expected version {expected_str})."
                            ),
                            remediation=(
                                f"Use a Legacy Gen8 {suffix} asset (version {expected_str}) for legacy_gen8."
                            ),
                            details={
                                "header": header_kind,
                                "detected_version": rsc_ver,
                                "expected_versions": sorted(expected_set),
                            },
                        )
                    )
                else:
                    findings.append(
                        _make_finding(
                            gate="gate_1_static_binary",
                            severity="WARNING",
                            code="UNEXPECTED_RSC_VERSION",
                            file_path=file_path,
                            message=(
                                f"Resource '{file_path.name}' has {suffix} version {rsc_ver} "
                                f"(target '{target_edition}' expects {expected_str})."
                            ),
                            remediation=f"Verify resource version compatibility for {target_edition}.",
                            details={
                                "header": header_kind,
                                "detected_version": rsc_ver,
                                "expected_versions": sorted(expected_set),
                            },
                        )
                    )

    findings.extend(_inspect_script_rt_and_textures(file_path, data, target_edition))
    return findings


def _audit_dlclist_xml(file_path: Path) -> list[dict[str, Any]]:
    """Gate 2: Validate dlclist.xml XML structure, dlcpacks:/ paths, and mods/ isolation."""
    findings: list[dict[str, Any]] = []
    normalized_parts = [p.lower() for p in file_path.parts]

    # Warn if modifying root update/common outside mods/ folder
    if ("update" in normalized_parts or "common.rpf" in normalized_parts) and (
        "mods" not in normalized_parts
    ):
        findings.append(
            _make_finding(
                gate="gate_2_dlc_registration",
                severity="WARNING",
                code="DLCLIST_OUTSIDE_MODS_FOLDER",
                file_path=file_path,
                message=(
                    f"dlclist.xml at '{file_path}' appears to reside in vanilla archive path "
                    "outside 'mods/' isolation folder."
                ),
                remediation=(
                    "Copy update.rpf into 'mods/update/update.rpf' and mount via OpenRPF.asi "
                    "instead of modifying vanilla root archives."
                ),
            )
        )

    try:
        raw_xml = file_path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        findings.append(
            _make_finding(
                gate="gate_2_dlc_registration",
                severity="ERROR",
                code="DLCLIST_MALFORMED_XML",
                file_path=file_path,
                message=f"Malformed XML in dlclist.xml: {exc}",
                remediation="Fix XML syntax errors (unclosed tags or invalid characters) in dlclist.xml.",
            )
        )
        return findings
    except Exception as exc:
        findings.append(
            _make_finding(
                gate="gate_2_dlc_registration",
                severity="ERROR",
                code="DLCLIST_READ_ERROR",
                file_path=file_path,
                message=f"Could not read dlclist.xml: {exc}",
                remediation="Check file encoding and permissions.",
            )
        )
        return findings

    items = root.findall(".//Item")
    if not items:
        findings.append(
            _make_finding(
                gate="gate_2_dlc_registration",
                severity="WARNING",
                code="DLCLIST_EMPTY_ITEMS",
                file_path=file_path,
                message="dlclist.xml contains no <Item> entries.",
                remediation="Add <Item>dlcpacks:/<addon_name>/</Item> under <Paths>.",
            )
        )
        return findings

    dlcpack_pattern = re.compile(r"^dlcpacks:/[a-zA-Z0-9_\-]+/$")
    seen_entries: set[str] = set()
    for idx, item in enumerate(items, start=1):
        val = (item.text or "").strip()
        if not val:
            findings.append(
                _make_finding(
                    gate="gate_2_dlc_registration",
                    severity="ERROR",
                    code="DLCLIST_EMPTY_ITEM_TAG",
                    file_path=file_path,
                    message=f"Empty <Item> tag at position #{idx} in dlclist.xml.",
                    remediation="Remove empty <Item/> or provide 'dlcpacks:/<name>/'.",
                )
            )
            continue

        if val in seen_entries:
            findings.append(
                _make_finding(
                    gate="gate_2_dlc_registration",
                    severity="WARNING",
                    code="DLCLIST_DUPLICATE_ENTRY",
                    file_path=file_path,
                    message=f"Duplicate DLC entry '{val}' in dlclist.xml.",
                    remediation=f"Keep only one <Item>{val}</Item> entry.",
                )
            )
        seen_entries.add(val)

        if val.startswith("platform:/"):
            continue

        if not dlcpack_pattern.match(val):
            findings.append(
                _make_finding(
                    gate="gate_2_dlc_registration",
                    severity="ERROR",
                    code="DLCLIST_INVALID_PATH_FORMAT",
                    file_path=file_path,
                    message=(
                        f"Invalid dlclist.xml entry '{val}' at item #{idx}; "
                        "must use forward slashes and trailing slash: 'dlcpacks:/<name>/'."
                    ),
                    remediation=f"Format entry as '<Item>dlcpacks:/{val.strip('/\\\\').split('/')[-1].split('\\\\')[-1]}/</Item>'.",
                    details={"entry": val, "item_index": idx},
                )
            )

    return findings


def audit_assets(
    target_path: str | Path,
    target_edition: str = "enhanced_gen9",
) -> dict[str, Any]:
    """Execute the 5-Stage Asset Gate audit (Gates 1 & 2 static + Gates 3-5 runtime checklist)."""
    path = Path(target_path)
    findings: list[dict[str, Any]] = []
    scanned_files = 0

    if not path.exists():
        findings.append(
            _make_finding(
                gate="gate_1_static_binary",
                severity="ERROR",
                code="TARGET_PATH_NOT_FOUND",
                file_path=path,
                message=f"Target asset path does not exist: {path}",
                remediation="Provide a valid asset file (.yft, .ytd, .dds, dlclist.xml) or directory.",
            )
        )
    else:
        candidate_files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for file_path in candidate_files:
            suffix = file_path.suffix.lower()
            name_lower = file_path.name.lower()
            if suffix in {".yft", ".ytd", ".dds"}:
                scanned_files += 1
                findings.extend(_audit_single_binary_asset(file_path, target_edition))
            elif name_lower == "dlclist.xml":
                scanned_files += 1
                findings.extend(_audit_dlclist_xml(file_path))
            elif name_lower == "manifest.json" or suffix == ".json":
                scanned_files += 1
                try:
                    raw_bytes = file_path.read_bytes()
                    findings.extend(_inspect_script_rt_and_textures(file_path, raw_bytes, target_edition))
                except Exception:
                    pass

    blocking_severities = {"ERROR", "HIGH"}
    gate1_Blocking = [
        f for f in findings if f["gate"] == "gate_1_static_binary" and f["severity"] in blocking_severities
    ]
    gate2_Blocking = [
        f for f in findings if f["gate"] == "gate_2_dlc_registration" and f["severity"] in blocking_severities
    ]

    gates = {
        "gate_1_static_binary": {
            "stage": 1,
            "mode": "static",
            "status": "FAIL" if gate1_Blocking else "PASS",
            "description": (
                "Inspect .yft/.ytd RSC version (Gen9 yft=171, ytd=5 vs Gen8 yft=162, ytd=13) "
                "and verify script_rt_* textures use single-mip B8G8R8A8_UNORM instead of DXT1."
            ),
            "issues_count": len(gate1_Blocking),
        },
        "gate_2_dlc_registration": {
            "stage": 2,
            "mode": "static",
            "status": "FAIL" if gate2_Blocking else "PASS",
            "description": "Validate dlclist.xml well-formedness, dlcpacks:/<name>/ syntax, and mods/ folder isolation.",
            "issues_count": len(gate2_Blocking),
        },
        "gate_3_model_streaming": {
            "stage": 3,
            "mode": "runtime_checklist",
            "status": "PENDING_RUNTIME",
            "description": (
                "RequestModel with timeout guard; call MarkAsNoLongerNeeded() immediately on timeout "
                "and fall back to vanilla_fallback_model."
            ),
            "checklist": [
                "Verify Model.IsInCdImage and Model.IsValid before Request().",
                "Enforce stream_timeout_ms (e.g. 5000ms) and call MarkAsNoLongerNeeded() on timeout.",
                "Confirm seamless fallback to vanilla_fallback_model (e.g. 'bus').",
            ],
        },
        "gate_4_world_spawn": {
            "stage": 4,
            "mode": "runtime_checklist",
            "status": "PENDING_RUNTIME",
            "description": (
                "Verify CreateVehicle returns non-null handle and entity.Exists() is true before "
                "configuring extras, liveries, or registering lease in WorldSession."
            ),
            "checklist": [
                "Never call CreateVehicle inside menu OnIndexChange callbacks.",
                "Null-check spawned vehicle handle and verify Exists() before accessing properties.",
                "Register spawned entity in WorldSession lease table for deterministic teardown.",
            ],
        },
        "gate_5_interaction_loop": {
            "stage": 5,
            "mode": "runtime_checklist",
            "status": "PENDING_RUNTIME",
            "description": "Validate player seating, door bones, and NPC passenger boarding/alighting tasks.",
            "checklist": [
                "Verify driver seat and passenger seat count match operational role.",
                "Test door open/close state transitions at stop checkpoints.",
                "Confirm WorldSession.DisposeAll() cleans up vehicle, peds, and blips on exit.",
            ],
        },
    }

    error_count = sum(1 for f in findings if f["severity"] in blocking_severities)
    warn_count = sum(1 for f in findings if f["severity"] == "WARNING")
    ok = error_count == 0 and path.exists()

    summary = (
        f"Audited {scanned_files} file(s) for target '{target_edition}': "
        f"{error_count} blocking error(s), {warn_count} warning(s). "
        f"Gate 1={gates['gate_1_static_binary']['status']}, Gate 2={gates['gate_2_dlc_registration']['status']}."
    )

    return {
        "ok": ok,
        "target_edition": target_edition,
        "scanned_files": scanned_files,
        "gates": gates,
        "findings": findings,
        "summary": summary,
    }
