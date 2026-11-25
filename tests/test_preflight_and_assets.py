from __future__ import annotations

import struct
from pathlib import Path

import pytest

from gta_anything.assets.auditor import audit_assets
from gta_anything.preflight.checker import run_preflight


def _build_synthetic_exe_with_version(major: int = 1, minor: int = 0, build: int = 1158, rev: int = 16) -> bytes:
    """Create a synthetic PE binary blob containing both VS_FIXEDFILEINFO and ASCII/UTF-16 version markers."""
    file_version_ms = (major << 16) | (minor & 0xFFFF)
    file_version_ls = (build << 16) | (rev & 0xFFFF)
    vs_fixed = struct.pack(
        "<13I",
        0xFEEF04BD,  # dwSignature
        0x00010000,  # dwStrucVersion
        file_version_ms,  # dwFileVersionMS
        file_version_ls,  # dwFileVersionLS
        file_version_ms,  # dwProductVersionMS
        file_version_ls,  # dwProductVersionLS
        0x3F,
        0,
        0x00040004,
        0x00000001,
        0,
        0,
        0,
    )
    ver_str = f"{major}.{minor}.{build}.{rev}"
    utf16_marker = "FileVersion\x00".encode("utf-16le") + (ver_str + "\x00").encode("utf-16le")
    ascii_marker = f"FileVersion={ver_str}".encode("ascii")
    return b"MZ\x90\x00" + b"\x00" * 60 + vs_fixed + b"\x00" * 16 + utf16_marker + b"\x00" * 16 + ascii_marker


def _build_synthetic_rsc7(version: int, payload: bytes = b"") -> bytes:
    """Create a synthetic RAGE RSC7 header (magic 0x37435352 = b'RSC7', int32 version, flags) + payload."""
    # RSC7 magic in little-endian u32 is 0x37435352 ('RSC7')
    header = struct.pack("<III", 0x37435352, version, 0x00000001)
    return header + payload


def test_preflight_dual_build_id_and_loaders(tmp_path: Path):
    game_dir = tmp_path / "GTA5_Enhanced_Sandbox"
    game_dir.mkdir(parents=True)

    # Create synthetic GTA5_Enhanced.exe (disk version 1.0.1158.16)
    (game_dir / "GTA5_Enhanced.exe").write_bytes(_build_synthetic_exe_with_version(1, 0, 1158, 16))

    # Create synthetic ScriptHookV.log reporting internal enum VER_EN_1_0_1158_13
    (game_dir / "ScriptHookV.log").write_text(
        "// GTA V SCRIPT HOOK (build Mar 2026)\n"
        "//     (C) Alexander Blade\n"
        "Init: Detected game version VER_EN_1_0_1158_13\n",
        encoding="utf-8",
    )

    # Create dummy loader markers (text placeholders in tmp_path only)
    (game_dir / "ScriptHookV.dll").write_bytes(b"SYNTHETIC_LOADER_STUB")
    (game_dir / "ScriptHookVDotNet.asi").write_bytes(b"SYNTHETIC_SHVDN_STUB")
    (game_dir / "OpenRPF.asi").write_bytes(b"SYNTHETIC_OPENRPF_STUB")

    result = run_preflight(game_dir=game_dir, min_free_gb=0.01, min_commit_mb=128.0, hotkey="F4")

    assert isinstance(result, dict)
    assert "system" in result
    assert "game" in result
    assert "hotkey_check" in result

    game_info = result["game"]
    assert game_info["provided"] is True
    assert game_info["exists"] is True
    assert game_info["edition"] == "enhanced_gen9"
    assert game_info["shv_build_alias"] == "VER_EN_1_0_1158_13"
    assert game_info["exe_version"] == "1.0.1158.16"
    # Verify dual build IDs remain distinct!
    assert game_info["exe_version"] != game_info["shv_build_alias"]

    loaders_joined = " ".join(game_info["detected_loaders"]).lower()
    assert "scripthookv" in loaders_joined

    # F4 is RPH console hotkey and must flag a conflict
    hotkey_info = result["hotkey_check"]
    assert hotkey_info["requested_hotkey"] == "F4"
    assert len(hotkey_info["conflicts"]) >= 1


def test_preflight_without_game_dir_and_safe_hotkey():
    result = run_preflight(game_dir=None, min_free_gb=0.01, min_commit_mb=64.0, hotkey="F9")
    assert result["game"]["provided"] is False
    assert result["system"]["disk_free_gb"] > 0
    assert result["hotkey_check"]["requested_hotkey"] == "F9"
    assert result["hotkey_check"]["conflicts"] == []


def test_asset_auditor_gen9_pass_vs_gen8_fail(tmp_path: Path):
    gen9_dir = tmp_path / "gen9_assets"
    gen9_dir.mkdir()
    # Gen9 .yft = v171, .ytd = v5
    (gen9_dir / "shuttle_bus.yft").write_bytes(_build_synthetic_rsc7(171, b"GEN9_DRAWABLE_FRAGMENT"))
    (gen9_dir / "shuttle_bus.ytd").write_bytes(_build_synthetic_rsc7(5, b"GEN9_TEXTURE_DICT_B8G8R8A8_UNORM"))

    res_gen9 = audit_assets(gen9_dir, target_edition="enhanced_gen9")
    assert res_gen9["ok"] is True, f"Expected Gen9 assets to pass: {res_gen9}"
    assert res_gen9["scanned_files"] >= 2

    # Legacy Gen8 .yft = v162, .ytd = v13 audited against enhanced_gen9 MUST FAIL
    gen8_dir = tmp_path / "gen8_legacy_assets"
    gen8_dir.mkdir()
    (gen8_dir / "old_bus.yft").write_bytes(_build_synthetic_rsc7(162, b"GEN8_DRAWABLE_FRAGMENT"))
    (gen8_dir / "old_bus.ytd").write_bytes(_build_synthetic_rsc7(13, b"GEN8_TEXTURE_DICT"))

    res_mismatch = audit_assets(gen8_dir, target_edition="enhanced_gen9")
    assert res_mismatch["ok"] is False
    findings_text = " ".join(str(f) for f in res_mismatch["findings"])
    assert "162" in findings_text or "171" in findings_text


def test_asset_auditor_script_rt_dxt1_fail_vs_b8g8r8a8_pass(tmp_path: Path):
    # Case 1: Gen9 .ytd (v5) containing script_rt_dials_race with legacy DXT1 -> MUST FAIL on enhanced_gen9
    bad_rt_dir = tmp_path / "bad_script_rt"
    bad_rt_dir.mkdir()
    bad_payload = b"TEXTURE_NAME=script_rt_dials_race\x00FORMAT=DXT1\x00MIPS=4\x00"
    (bad_rt_dir / "shuttle_dials.ytd").write_bytes(_build_synthetic_rsc7(5, bad_payload))

    bad_report = audit_assets(bad_rt_dir, target_edition="enhanced_gen9")
    assert bad_report["ok"] is False
    bad_findings_str = " ".join(str(f) for f in bad_report["findings"])
    assert "script_rt" in bad_findings_str.lower()
    assert "dxt1" in bad_findings_str.lower() or "b8g8r8a8" in bad_findings_str.lower()

    # Case 2: Gen9 .ytd (v5) containing script_rt_dials_race with B8G8R8A8_UNORM and 1 mip -> MUST PASS
    good_rt_dir = tmp_path / "good_script_rt"
    good_rt_dir.mkdir()
    good_payload = b"TEXTURE_NAME=script_rt_dials_race\x00FORMAT=B8G8R8A8_UNORM\x00MIPS=1\x00"
    (good_rt_dir / "shuttle_dials_fixed.ytd").write_bytes(_build_synthetic_rsc7(5, good_payload))

    good_report = audit_assets(good_rt_dir, target_edition="enhanced_gen9")
    assert good_report["ok"] is True, f"Expected fixed script_rt_dials_race to pass: {good_report}"


def test_asset_auditor_dlclist_validation(tmp_path: Path):
    valid_dlc_dir = tmp_path / "mods" / "update" / "update.rpf" / "common" / "data"
    valid_dlc_dir.mkdir(parents=True)
    (valid_dlc_dir / "dlclist.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<SMandatoryPacksData>
  <Paths>
    <Item>dlcpacks:/mp2024_01/</Item>
    <Item>dlcpacks:/metro_shuttle/</Item>
  </Paths>
</SMandatoryPacksData>
""",
        encoding="utf-8",
    )
    valid_res = audit_assets(valid_dlc_dir, target_edition="enhanced_gen9")
    assert valid_res["ok"] is True

    # Malformed dlclist.xml must fail Gate 2
    invalid_dlc_dir = tmp_path / "bad_dlc"
    invalid_dlc_dir.mkdir()
    (invalid_dlc_dir / "dlclist.xml").write_text(
        "<SMandatoryPacksData><Paths><Item>broken_path_without_closing_tag</SMandatoryPacksData>",
        encoding="utf-8",
    )
    invalid_res = audit_assets(invalid_dlc_dir, target_edition="enhanced_gen9")
    assert invalid_res["ok"] is False
