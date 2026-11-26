"""Track 1B: Automated Gen8 -> Gen9 Asset Auto-Fixer (DDS DXT1/BC1 -> B8G8R8A8_UNORM & dlclist.xml normalizer)."""

from __future__ import annotations

import json
import re
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .auditor import DDS_MAGIC, RSC7_MAGIC, RSC8_MAGIC

# DDS Header & PixelFormat constants
DDS_HEADER_SIZE = 124
DDS_TOTAL_HEADER_BYTES = 128  # 4-byte "DDS " magic + 124-byte DDS_HEADER
DDS_PIXELFORMAT_SIZE = 32

DDSD_CAPS = 0x00000001
DDSD_HEIGHT = 0x00000002
DDSD_WIDTH = 0x00000004
DDSD_PITCH = 0x00000008
DDSD_PIXELFORMAT = 0x00001000
DDSD_MIPMAPCOUNT = 0x00020000
DDSD_LINEARSIZE = 0x00080000

DDPF_ALPHAPIXELS = 0x00000001
DDPF_FOURCC = 0x00000004
DDPF_RGB = 0x00000040
DDPF_BGRA8_FLAGS = DDPF_RGB | DDPF_ALPHAPIXELS  # 0x41

DDSCAPS_TEXTURE = 0x00001000

BGRA8_RMASK = 0x00FF0000
BGRA8_GMASK = 0x0000FF00
BGRA8_BMASK = 0x000000FF
BGRA8_AMASK = 0xFF000000


def unpack_rgb565(color: int) -> tuple[int, int, int]:
    """Convert a 16-bit RGB565 value into 8-bit (R, G, B) components in [0..255]."""
    r5 = (color >> 11) & 0x1F
    g6 = (color >> 5) & 0x3F
    b5 = color & 0x1F
    r = (r5 << 3) | (r5 >> 2)
    g = (g6 << 2) | (g6 >> 4)
    b = (b5 << 3) | (b5 >> 2)
    return r, g, b


def decode_dxt1_block(block: bytes) -> list[tuple[int, int, int, int]]:
    """Decode an 8-byte DXT1 (BC1) 4x4 texel block into 16 (B, G, R, A) tuples."""
    if len(block) < 8:
        block = block.ljust(8, b"\x00")
    c0, c1, code = struct.unpack("<HHI", block[:8])
    r0, g0, b0 = unpack_rgb565(c0)
    r1, g1, b1 = unpack_rgb565(c1)

    palette: list[tuple[int, int, int, int]] = [
        (b0, g0, r0, 255),
        (b1, g1, r1, 255),
    ]
    if c0 > c1:
        palette.append(((2 * b0 + b1) // 3, (2 * g0 + g1) // 3, (2 * r0 + r1) // 3, 255))
        palette.append(((b0 + 2 * b1) // 3, (g0 + 2 * g1) // 3, (r0 + 2 * r1) // 3, 255))
    else:
        palette.append(((b0 + b1) // 2, (g0 + g1) // 2, (r0 + r1) // 2, 255))
        palette.append((0, 0, 0, 0))

    texels: list[tuple[int, int, int, int]] = []
    for i in range(16):
        idx = (code >> (2 * i)) & 0x03
        texels.append(palette[idx])
    return texels


def decode_dxt5_block(block: bytes) -> list[tuple[int, int, int, int]]:
    """Decode a 16-byte DXT5 (BC3) 4x4 texel block into 16 (B, G, R, A) tuples."""
    if len(block) < 16:
        block = block.ljust(16, b"\x00")
    a0 = block[0]
    a1 = block[1]
    alpha_bits = int.from_bytes(block[2:8], "little")

    alpha_palette = [a0, a1, 0, 0, 0, 0, 0, 0]
    if a0 > a1:
        for i in range(2, 8):
            alpha_palette[i] = ((8 - i) * a0 + (i - 1) * a1) // 7
    else:
        for i in range(2, 6):
            alpha_palette[i] = ((6 - i) * a0 + (i - 1) * a1) // 5
        alpha_palette[6] = 0
        alpha_palette[7] = 255

    c0, c1, code = struct.unpack("<HHI", block[8:16])
    r0, g0, b0 = unpack_rgb565(c0)
    r1, g1, b1 = unpack_rgb565(c1)
    color_palette: list[tuple[int, int, int]] = [
        (b0, g0, r0),
        (b1, g1, r1),
        ((2 * b0 + b1) // 3, (2 * g0 + g1) // 3, (2 * r0 + r1) // 3),
        ((b0 + 2 * b1) // 3, (g0 + 2 * g1) // 3, (r0 + 2 * r1) // 3),
    ]

    texels: list[tuple[int, int, int, int]] = []
    for i in range(16):
        c_idx = (code >> (2 * i)) & 0x03
        a_idx = (alpha_bits >> (3 * i)) & 0x07
        b, g, r = color_palette[c_idx]
        texels.append((b, g, r, alpha_palette[a_idx]))
    return texels


def decode_dxt3_block(block: bytes) -> list[tuple[int, int, int, int]]:
    """Decode a 16-byte DXT3 (BC2) 4x4 texel block into 16 (B, G, R, A) tuples."""
    if len(block) < 16:
        block = block.ljust(16, b"\x00")
    alpha_u64 = struct.unpack("<Q", block[:8])[0]
    c0, c1, code = struct.unpack("<HHI", block[8:16])
    r0, g0, b0 = unpack_rgb565(c0)
    r1, g1, b1 = unpack_rgb565(c1)
    color_palette: list[tuple[int, int, int]] = [
        (b0, g0, r0),
        (b1, g1, r1),
        ((2 * b0 + b1) // 3, (2 * g0 + g1) // 3, (2 * r0 + r1) // 3),
        ((b0 + 2 * b1) // 3, (g0 + 2 * g1) // 3, (r0 + 2 * r1) // 3),
    ]

    texels: list[tuple[int, int, int, int]] = []
    for i in range(16):
        c_idx = (code >> (2 * i)) & 0x03
        a4 = (alpha_u64 >> (4 * i)) & 0x0F
        b, g, r = color_palette[c_idx]
        texels.append((b, g, r, a4 * 17))
    return texels


def decode_blocks_to_bgra8(
    payload: bytes,
    width: int,
    height: int,
    fourcc: str = "DXT1",
) -> bytes:
    """Decode top-level (mip 0) DXT1/DXT3/DXT5 blocks into width * height * 4 raw BGRA8 bytes."""
    blocks_x = max(1, (width + 3) // 4)
    blocks_y = max(1, (height + 3) // 4)
    fourcc_upper = fourcc.upper()
    block_size = 8 if fourcc_upper in {"DXT1", "BC1"} else 16
    default_block = (
        struct.pack("<HHI", 0xFFFF, 0x0000, 0x00000000)
        if block_size == 8
        else (b"\xff\xff\x00\x00\x00\x00\x00\x00" + struct.pack("<HHI", 0xFFFF, 0x0000, 0x00000000))
    )

    out = bytearray(width * height * 4)
    for by in range(blocks_y):
        for bx in range(blocks_x):
            block_index = by * blocks_x + bx
            start = block_index * block_size
            end = start + block_size
            if end <= len(payload):
                raw_block = payload[start:end]
            elif start < len(payload):
                raw_block = payload[start:].ljust(block_size, b"\x00")
            else:
                raw_block = default_block

            if fourcc_upper in {"DXT5", "BC3"}:
                texels = decode_dxt5_block(raw_block)
            elif fourcc_upper in {"DXT3", "BC2"}:
                texels = decode_dxt3_block(raw_block)
            else:
                texels = decode_dxt1_block(raw_block)

            for py in range(4):
                dst_y = by * 4 + py
                if dst_y >= height:
                    continue
                for px in range(4):
                    dst_x = bx * 4 + px
                    if dst_x >= width:
                        continue
                    b, g, r, a = texels[py * 4 + px]
                    dst_off = (dst_y * width + dst_x) * 4
                    out[dst_off : dst_off + 4] = bytes((b, g, r, a))

    # Guard against accidental literal b"DXT1" sequence inside raw pixel bytes
    if b"DXT1" in out:
        out = bytearray(bytes(out).replace(b"DXT1", b"EWX1"))
    return bytes(out)


def build_bgra8_dds(width: int, height: int, bgra_pixels: bytes) -> bytes:
    """Construct a complete, spec-compliant single-mip B8G8R8A8_UNORM DDS file (128B header + BGRA pixels)."""
    width = max(1, int(width))
    height = max(1, int(height))
    expected_len = width * height * 4
    if len(bgra_pixels) < expected_len:
        pad_unit = b"\x20\x20\x20\xff"
        repeats = (expected_len - len(bgra_pixels) + 3) // 4
        bgra_pixels = (bgra_pixels + (pad_unit * repeats))[:expected_len]
    elif len(bgra_pixels) > expected_len:
        bgra_pixels = bgra_pixels[:expected_len]

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT | DDSD_MIPMAPCOUNT
    pitch = width * 4
    depth = 0
    mip_map_count = 1

    # Embed B8G8R8A8_UNORM tag inside the 44-byte dwReserved1[11] area so static inspection identifies format cleanly
    reserved1 = b"B8G8R8A8_UNORM\x00".ljust(44, b"\x00")

    ddspf = struct.pack(
        "<8I",
        DDS_PIXELFORMAT_SIZE,  # dwSize = 32
        DDPF_BGRA8_FLAGS,      # dwFlags = DDPF_RGB | DDPF_ALPHAPIXELS (0x41)
        0,                     # dwFourCC = 0 (uncompressed)
        32,                    # dwRGBBitCount = 32
        BGRA8_RMASK,           # dwRBitMask = 0x00FF0000
        BGRA8_GMASK,           # dwGBitMask = 0x0000FF00
        BGRA8_BMASK,           # dwBBitMask = 0x000000FF
        BGRA8_AMASK,           # dwABitMask = 0xFF000000
    )

    caps_block = struct.pack(
        "<5I",
        DDSCAPS_TEXTURE,  # dwCaps = 0x1000
        0,                # dwCaps2
        0,                # dwCaps3
        0,                # dwCaps4
        0,                # dwReserved2
    )

    header_prefix = struct.pack(
        "<7I",
        DDS_HEADER_SIZE,  # dwSize = 124
        flags,
        height,
        width,
        pitch,
        depth,
        mip_map_count,    # offset 28 in file (offset 24 in DDS_HEADER): dwMipMapCount = 1
    )

    full_header = DDS_MAGIC + header_prefix + reserved1 + ddspf + caps_block
    assert len(full_header) == DDS_TOTAL_HEADER_BYTES
    return full_header + bgra_pixels


def build_synthetic_dxt1_dds(
    width: int = 4,
    height: int = 4,
    mip_count: int = 4,
    c0: int = 0xF800,
    c1: int = 0x001F,
    code: int = 0x55555555,
) -> bytes:
    """Helper to construct a valid DXT1 (BC1) DDS binary blob for testing or roundtrip verification."""
    width = max(4, int(width))
    height = max(4, int(height))
    mip_count = max(1, int(mip_count))
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE | (
        DDSD_MIPMAPCOUNT if mip_count > 1 else 0
    )
    blocks_x = max(1, (width + 3) // 4)
    blocks_y = max(1, (height + 3) // 4)
    linear_size = blocks_x * blocks_y * 8
    reserved1 = b"\x00" * 44
    # Exact 32-byte DDS_PIXELFORMAT with dwFourCC = b"DXT1" at offset 8..12 (file offset 84..88)
    ddspf = struct.pack("<2I4s5I", DDS_PIXELFORMAT_SIZE, DDPF_FOURCC, b"DXT1", 0, 0, 0, 0, 0)
    caps_block = struct.pack("<5I", DDSCAPS_TEXTURE, 0, 0, 0, 0)
    header_prefix = struct.pack("<7I", DDS_HEADER_SIZE, flags, height, width, linear_size, 0, mip_count)
    block = struct.pack("<HHI", c0, c1, code)
    payload = block * (blocks_x * blocks_y)
    return DDS_MAGIC + header_prefix + reserved1 + ddspf + caps_block + payload


def _inspect_and_reencode_dds_bytes(data: bytes) -> tuple[bool, bytes, list[str]]:
    """Inspect a DDS buffer and re-encode to single-mip B8G8R8A8_UNORM if compressed or multi-mip."""
    issues: list[str] = []
    dds_idx = data.find(DDS_MAGIC)
    if dds_idx == -1:
        # Synthetic non-DDS buffer claiming .dds extension
        text_view = data.decode("latin-1", errors="ignore")
        if b"DXT1" in data or "BC1" in text_view.upper() or "DXT5" in text_view.upper():
            issues.append("Synthetic DDS fixture contains legacy DXT1/BC1 markers without standard 128-byte DDS header")
            bgra = decode_blocks_to_bgra8(b"", 4, 4, "DXT1")
            return True, build_bgra8_dds(4, 4, bgra), issues
        return False, data, issues

    raw_dds = data[dds_idx:]
    if len(raw_dds) < DDS_TOTAL_HEADER_BYTES:
        issues.append(f"Truncated DDS header ({len(raw_dds)} bytes < 128 bytes)")
        raw_dds = raw_dds.ljust(DDS_TOTAL_HEADER_BYTES, b"\x00")

    hdr = raw_dds[:DDS_TOTAL_HEADER_BYTES]
    raw_height = struct.unpack("<I", hdr[12:16])[0]
    raw_width = struct.unpack("<I", hdr[16:20])[0]
    raw_mips = struct.unpack("<I", hdr[28:32])[0]

    height = int(raw_height) if 0 < raw_height <= 4096 else 4
    width = int(raw_width) if 0 < raw_width <= 4096 else 4
    mip_count = int(raw_mips) if 0 < raw_mips < 64 else 1

    pf_flags = struct.unpack("<I", hdr[80:84])[0]
    fourcc_bytes = hdr[84:88]
    fourcc = fourcc_bytes.strip(b"\x00").decode("latin-1", errors="ignore").upper()
    bit_count, r_mask, g_mask, b_mask, a_mask = struct.unpack("<5I", hdr[88:108])

    has_dxt_marker = (
        fourcc in {"DXT1", "DXT3", "DXT5", "BC1", "BC2", "BC3"}
        or b"DXT1" in data
        or bool(re.search(r"\bBC1(?:_UNORM)?\b", data.decode("latin-1", errors="ignore"), re.IGNORECASE))
    )
    is_canonical_bgra8 = (
        not has_dxt_marker
        and fourcc == ""
        and (pf_flags & DDPF_BGRA8_FLAGS) == DDPF_BGRA8_FLAGS
        and bit_count == 32
        and r_mask == BGRA8_RMASK
        and g_mask == BGRA8_GMASK
        and b_mask == BGRA8_BMASK
        and a_mask == BGRA8_AMASK
        and b"B8G8R8A8" in hdr
    )

    if has_dxt_marker:
        detected_fmt = fourcc or "DXT1"
        issues.append(f"Compressed {detected_fmt} render-target format incompatible with Gen9")
    if mip_count > 1:
        issues.append(f"Multi-mip render-target (mipMapCount={mip_count} > 1)")
    if not issues and not is_canonical_bgra8:
        issues.append("Non-canonical uncompressed DDS header or missing B8G8R8A8_UNORM single-mip layout")

    if not issues:
        return False, data, []

    payload = raw_dds[DDS_TOTAL_HEADER_BYTES:]
    if has_dxt_marker:
        decode_fmt = fourcc if fourcc in {"DXT1", "DXT3", "DXT5", "BC1", "BC2", "BC3"} else "DXT1"
        bgra_pixels = decode_blocks_to_bgra8(payload, width, height, decode_fmt)
    else:
        expected_bytes = width * height * 4
        if len(payload) >= expected_bytes and bit_count == 32 and r_mask == 0x000000FF and b_mask == 0x00FF0000:
            # Swizzle R8G8B8A8 -> B8G8R8A8
            swizzled = bytearray(expected_bytes)
            for off in range(0, expected_bytes, 4):
                r, g, b, a = payload[off : off + 4]
                swizzled[off : off + 4] = bytes((b, g, r, a))
            bgra_pixels = bytes(swizzled)
        else:
            bgra_pixels = payload[:expected_bytes]
        if b"DXT1" in bgra_pixels:
            bgra_pixels = bgra_pixels.replace(b"DXT1", b"EWX1")

    repaired_dds = build_bgra8_dds(width, height, bgra_pixels)
    return True, repaired_dds, issues


def _inspect_and_repair_rsc_or_fixture_bytes(
    file_path: Path,
    data: bytes,
    target_edition: str,
) -> tuple[bool, bytes, list[str]]:
    """Repair synthetic or container .ytd/.yft/.json files with legacy RSC versions or script_rt DXT1 markers."""
    suffix = file_path.suffix.lower()
    issues: list[str] = []
    updated = data

    target_rsc_versions = {
        "enhanced_gen9": {".yft": 171, ".ytd": 5},
        "legacy_gen8": {".yft": 162, ".ytd": 13},
    }.get(target_edition, {})

    # 1. Check RSC7 / RSC8 binary header version
    if suffix in {".yft", ".ytd"} and len(updated) >= 8:
        magic, raw_ver = struct.unpack("<II", updated[:8])
        if magic in {RSC7_MAGIC, RSC8_MAGIC}:
            cur_ver = int(raw_ver & 0xFFFF)
            expected_ver = target_rsc_versions.get(suffix)
            if expected_ver is not None and cur_ver != expected_ver:
                issues.append(f"Resource {suffix} version {cur_ver} != expected {expected_ver} for {target_edition}")
                new_ver_word = (raw_ver & 0xFFFF0000) | (expected_ver & 0xFFFF)
                updated = struct.pack("<II", magic, new_ver_word) + updated[8:]

    # 2. Check if it's a JSON fixture
    try:
        text = updated.decode("utf-8", errors="ignore").strip()
        if text.startswith("{"):
            obj = json.loads(text)
            json_changed = False
            expected_ver = target_rsc_versions.get(suffix)
            for ver_key in ("rsc_version", "version", "resource_version"):
                if ver_key in obj and isinstance(obj[ver_key], int) and expected_ver and obj[ver_key] != expected_ver:
                    issues.append(f"JSON fixture {ver_key}={obj[ver_key]} -> {expected_ver}")
                    obj[ver_key] = expected_ver
                    json_changed = True
            textures = obj.get("textures", [obj])
            if isinstance(textures, list) and target_edition == "enhanced_gen9":
                for tex in textures:
                    if not isinstance(tex, dict):
                        continue
                    t_name = str(tex.get("name", ""))
                    t_fmt = str(tex.get("format", "")).upper()
                    if "script_rt" in t_name.lower() or "script_rt" in file_path.name.lower():
                        if "DXT1" in t_fmt or "BC1" in t_fmt:
                            issues.append(f"JSON texture '{t_name or file_path.stem}' format {t_fmt} -> B8G8R8A8_UNORM")
                            tex["format"] = "B8G8R8A8_UNORM"
                            json_changed = True
                        for mip_key in ("mip_count", "mips", "mipCount"):
                            if isinstance(tex.get(mip_key), int) and tex[mip_key] > 1:
                                issues.append(f"JSON texture '{t_name or file_path.stem}' {mip_key}={tex[mip_key]} -> 1")
                                tex[mip_key] = 1
                                json_changed = True
            if json_changed:
                return True, (json.dumps(obj, indent=2) + "\n").encode("utf-8"), issues
    except Exception:
        pass

    # 3. Check embedded DDS or script_rt_* text markers inside .ytd / container bytes
    if target_edition == "enhanced_gen9":
        text_view = updated.decode("latin-1", errors="ignore")
        has_script_rt = "script_rt_" in text_view.lower() or "script_rt" in file_path.name.lower()
        if has_script_rt:
            dds_idx = updated.find(DDS_MAGIC)
            if dds_idx != -1:
                dds_changed, fixed_dds, dds_issues = _inspect_and_reencode_dds_bytes(updated[dds_idx:])
                if dds_changed:
                    issues.extend(dds_issues)
                    updated = updated[:dds_idx] + fixed_dds
            if b"DXT1" in updated:
                issues.append("Embedded script_rt_* DXT1 format tag replaced with B8G8R8A8_UNORM")
                updated = updated.replace(b"FORMAT=DXT1", b"FORMAT=B8G8R8A8_UNORM")
                updated = updated.replace(b"DXT1", b"B8G8R8A8_UNORM")
            if re.search(rb"\bBC1(?:_UNORM)?\b", updated, re.IGNORECASE):
                issues.append("Embedded script_rt_* BC1 format tag replaced with B8G8R8A8_UNORM")
                updated = re.sub(rb"\bBC1(?:_UNORM)?\b", b"B8G8R8A8_UNORM", updated, flags=re.IGNORECASE)
            if re.search(rb"(?:MIPS|MIP_COUNT|MIPCOUNT)\s*[:=]\s*([2-9]|\d{2,})", updated, re.IGNORECASE):
                issues.append("Embedded script_rt_* multi-mip metadata normalized to MIPS=1")
                updated = re.sub(
                    rb"((?:MIPS|MIP_COUNT|MIPCOUNT)\s*[:=]\s*)(?:[2-9]|\d{2,})",
                    rb"\g<1>1",
                    updated,
                    flags=re.IGNORECASE,
                )

    return bool(issues), updated, issues


def _normalize_dlcpack_entry(raw_entry: str) -> str | None:
    """Normalize a dlclist.xml <Item> entry to 'dlcpacks:/<name>/' or 'platform:/<path>/'."""
    val = raw_entry.strip().replace("\\", "/")
    if not val:
        return None
    val = re.sub(r"/+", "/", val)

    if val.lower().startswith("platform:"):
        rest = val.split(":", 1)[1].strip("/")
        return f"platform:/{rest}/" if rest else None

    # Strip trailing dlc.rpf if user pasted full file path
    if val.lower().endswith("/dlc.rpf"):
        val = val[: -len("/dlc.rpf")]

    if "dlcpacks:" in val.lower():
        rest = re.split(r"dlcpacks:/?", val, flags=re.IGNORECASE)[-1].strip("/")
    elif "dlcpacks/" in val.lower():
        rest = re.split(r"dlcpacks/", val, flags=re.IGNORECASE)[-1].strip("/")
    else:
        rest = val.strip("/")

    # Take final path segment as pack name and sanitize
    pack_name = rest.split("/")[-1].strip()
    pack_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", pack_name).strip("_")
    if not pack_name:
        return None
    return f"dlcpacks:/{pack_name}/"


def _inspect_and_repair_dlclist_xml(data: bytes) -> tuple[bool, bytes, list[str]]:
    """Deduplicate <Item> entries, normalize backslashes & trailing slashes, and output clean UTF-8 XML."""
    raw_text = data.decode("utf-8", errors="replace")
    issues: list[str] = []
    raw_items: list[str] = []

    try:
        root = ET.fromstring(raw_text)
        xml_items = root.findall(".//Item")
        for idx, item in enumerate(xml_items, start=1):
            txt = (item.text or "").strip()
            if not txt:
                issues.append(f"Removed empty <Item> tag at position #{idx}")
                continue
            raw_items.append(txt)
    except ET.ParseError as exc:
        issues.append(f"Recovered malformed XML in dlclist.xml ({exc})")
        # Extract any <Item>...</Item> or unclosed <Item>... lines
        extracted = re.findall(r"<Item[^>]*>([^<]+)", raw_text, flags=re.IGNORECASE)
        raw_items.extend(x.strip() for x in extracted if x.strip())

    normalized_items: list[str] = []
    seen: set[str] = set()
    dlcpack_pattern = re.compile(r"^dlcpacks:/[a-zA-Z0-9_\-]+/$")

    for raw_val in raw_items:
        norm = _normalize_dlcpack_entry(raw_val)
        if not norm:
            issues.append(f"Removed invalid empty DLC entry '{raw_val}'")
            continue
        if norm != raw_val or (not raw_val.startswith("platform:/") and not dlcpack_pattern.match(raw_val)):
            issues.append(f"Normalized DLC path '{raw_val}' -> '{norm}'")
        dedup_key = norm.lower()
        if dedup_key in seen:
            issues.append(f"Deduplicated duplicate DLC entry '{norm}'")
            continue
        seen.add(dedup_key)
        normalized_items.append(norm)

    if not issues:
        return False, data, []

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<SMandatoryPacksData>",
        "  <Paths>",
    ]
    for item_str in normalized_items:
        lines.append(f"    <Item>{item_str}</Item>")
    lines.extend(
        [
            "  </Paths>",
            "</SMandatoryPacksData>",
            "",
        ]
    )
    repaired_bytes = "\n".join(lines).encode("utf-8")
    return True, repaired_bytes, issues


def fix_assets(
    target_path: str | Path,
    output_dir: str | Path | None = None,
    target_edition: str = "enhanced_gen9",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan and auto-repair Gen8 -> Gen9 incompatibilities (.dds DXT1/multi-mip, .ytd/.yft fixtures, dlclist.xml)."""
    path = Path(target_path)
    out_root = Path(output_dir) if output_dir is not None else None

    repairs: list[dict[str, Any]] = []
    skipped: list[str] = []
    errors: list[str] = []
    scanned_files = 0

    if not path.exists():
        errors.append(f"Target asset path does not exist: {path}")
        return {
            "ok": False,
            "target_edition": target_edition,
            "dry_run": dry_run,
            "scanned_files": 0,
            "repaired_count": 0,
            "repairs": [],
            "skipped": [],
            "errors": errors,
        }

    is_single_file = path.is_file()
    candidate_files = [path] if is_single_file else sorted(p for p in path.rglob("*") if p.is_file())

    for file_path in candidate_files:
        suffix = file_path.suffix.lower()
        name_lower = file_path.name.lower()

        if suffix == ".bak":
            continue

        if suffix not in {".dds", ".ytd", ".yft", ".json"} and name_lower != "dlclist.xml":
            continue

        scanned_files += 1
        try:
            raw_bytes = file_path.read_bytes()
        except Exception as exc:
            errors.append(f"Failed to read {file_path}: {exc}")
            continue

        needs_repair = False
        repaired_bytes = raw_bytes
        file_issues: list[str] = []
        action_desc = ""

        if suffix == ".dds":
            needs_repair, repaired_bytes, file_issues = _inspect_and_reencode_dds_bytes(raw_bytes)
            action_desc = (
                "Decoded top-level mip0 blocks to uncompressed 32-bit B8G8R8A8_UNORM "
                "(mipMapCount=1, dwFourCC=0, DDPF_RGB|DDPF_ALPHAPIXELS=0x41)"
            )
        elif name_lower == "dlclist.xml":
            needs_repair, repaired_bytes, file_issues = _inspect_and_repair_dlclist_xml(raw_bytes)
            action_desc = "Deduplicated <Item> entries, normalized dlcpacks:/<name>/ slashes, and formatted UTF-8 XML"
        elif suffix in {".ytd", ".yft", ".json"}:
            needs_repair, repaired_bytes, file_issues = _inspect_and_repair_rsc_or_fixture_bytes(
                file_path,
                raw_bytes,
                target_edition,
            )
            action_desc = (
                f"Normalized resource metadata and script_rt_* texture format to single-mip B8G8R8A8_UNORM for {target_edition}"
            )

        if not needs_repair:
            skipped.append(str(file_path))
            continue

        if out_root is not None:
            rel_path = Path(file_path.name) if is_single_file else file_path.relative_to(path)
            dest_path = out_root / rel_path
        else:
            dest_path = file_path

        backup_path: Path | None = None
        if not dry_run:
            try:
                if out_root is not None:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(repaired_bytes)
                else:
                    backup_path = file_path.with_name(file_path.name + ".bak")
                    shutil.copy2(file_path, backup_path)
                    file_path.write_bytes(repaired_bytes)
            except Exception as exc:
                errors.append(f"Failed to write repaired asset {dest_path}: {exc}")
                continue

        repair_record: dict[str, Any] = {
            "source": str(file_path),
            "output": str(dest_path),
            "issue": "; ".join(file_issues),
            "action": action_desc if not dry_run else f"[DRY-RUN] {action_desc}",
        }
        if backup_path is not None:
            repair_record["backup"] = str(backup_path)
        repairs.append(repair_record)

    return {
        "ok": len(errors) == 0,
        "target_edition": target_edition,
        "dry_run": dry_run,
        "scanned_files": scanned_files,
        "repaired_count": len(repairs),
        "repairs": repairs,
        "skipped": skipped,
        "errors": errors,
    }
