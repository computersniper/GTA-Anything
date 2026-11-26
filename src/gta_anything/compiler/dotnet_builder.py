"""Clean-room .NET C# `.dll` compiler pipeline for GTA-Anything.

Supports both:
- Offline standalone compilation (`GtaAnything.Runtime.dll` + `<ModClassName>.dll`)
  with zero proprietary game binaries.
- Live GTA V host compilation when `--game-dir` is supplied, linking against the
  user's local `ScriptHookVDotNet3.dll` (with `SHVDN_REFERENCED`) or
  `RAGEPluginHook.dll` (with `RPH_REFERENCED`) in strictly read-only mode.

Auto-detects the available C# compiler in priority order:
  1. `dotnet` SDK (verified via `dotnet --list-sdks`)
  2. Visual Studio Roslyn `csc.exe`
  3. `.NET Framework 4.x` `csc.exe` (`v4.0.30319`)
  4. `csc` / `mcs` on `PATH`
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _runtime_source_dir() -> Path:
    """Locate the bundled clean-room `GtaAnything.Runtime` C# source directory."""
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "runtime" / "csharp" / "GtaAnything.Runtime"


def _has_dotnet_sdk(dotnet_path: str) -> bool:
    """Verify `dotnet` has at least one installed SDK (not just the runtime)."""
    try:
        proc = subprocess.run(
            [dotnet_path, "--list-sdks"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return False
        return any(line.strip() for line in proc.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def _find_vs_roslyn_csc() -> str | None:
    """Probe standard Visual Studio install roots for Roslyn `csc.exe` without hardcoding user paths."""
    program_files_roots = [
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
    ]
    editions = ("Enterprise", "Professional", "Community", "BuildTools")
    years = ("2022", "2019")
    for root in program_files_roots:
        if not root:
            continue
        vs_base = Path(root) / "Microsoft Visual Studio"
        if not vs_base.is_dir():
            continue
        for year in years:
            for ed in editions:
                candidate = (
                    vs_base
                    / year
                    / ed
                    / "MSBuild"
                    / "Current"
                    / "Bin"
                    / "Roslyn"
                    / "csc.exe"
                )
                if candidate.is_file():
                    return str(candidate)
    return None


def _find_netfx_csc() -> str | None:
    """Locate `.NET Framework 4.x` `csc.exe` via `WINDIR`."""
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def detect_csharp_compiler() -> dict[str, Any]:
    """Auto-detect the best available C# compiler on the host machine."""
    dotnet_path = shutil.which("dotnet")
    if dotnet_path and _has_dotnet_sdk(dotnet_path):
        return {"kind": "dotnet_sdk", "path": dotnet_path}

    roslyn_csc = _find_vs_roslyn_csc()
    if roslyn_csc:
        return {"kind": "roslyn_csc", "path": roslyn_csc}

    netfx_csc = _find_netfx_csc()
    if netfx_csc:
        return {"kind": "netfx_csc", "path": netfx_csc}

    for tool in ("csc", "mcs"):
        found = shutil.which(tool)
        if found:
            return {"kind": "mono_csc", "path": found}

    return {"kind": "none", "path": None}


def _discover_mod_metadata(mod_path: Path) -> tuple[str, str]:
    """Return `(mod_class_name, loader_target)` inferred from the transpiled mod directory."""
    mod_class_name = ""
    loader_target = "shvdn_enhanced"

    config_files = sorted(mod_path.glob("*Config.json"))
    if config_files:
        try:
            cfg = json.loads(config_files[0].read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                mod_class_name = str(cfg.get("mod_class_name") or "").strip()
                loader_target = str(cfg.get("loader_target") or loader_target).strip()
        except (OSError, ValueError):
            pass

    if not mod_class_name:
        csproj_files = sorted(mod_path.glob("*.csproj"))
        if csproj_files:
            mod_class_name = csproj_files[0].stem
            try:
                text = csproj_files[0].read_text(encoding="utf-8")
                if "USE_RPH" in text:
                    loader_target = "rph"
            except OSError:
                pass

    if not mod_class_name:
        mod_class_name = mod_path.name.replace("-", "_").replace(" ", "_") or "GeneratedGtaMod"

    if (mod_path / "RphPluginBridge.cs").is_file():
        loader_target = "rph"

    return mod_class_name, loader_target


def _find_host_assembly(game_dir: Path, loader_target: str) -> Path | None:
    """Read-only search for `ScriptHookVDotNet3.dll` or `RAGEPluginHook.dll` in `game_dir`
    and `<game_dir>/GTA5-Profiles/Inactive/*`.
    """
    if not game_dir.is_dir():
        return None

    target_names = (
        ["RAGEPluginHookSDK.dll", "RAGEPluginHook.dll"]
        if loader_target == "rph"
        else ["ScriptHookVDotNet3.dll"]
    )

    search_dirs: list[Path] = [game_dir]
    inactive_root = game_dir / "GTA5-Profiles" / "Inactive"
    if inactive_root.is_dir():
        for child in sorted(inactive_root.iterdir()):
            if child.is_dir():
                search_dirs.append(child)

    for folder in search_dirs:
        for name in target_names:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None


def _verify_pe_dll(dll_path: Path) -> dict[str, Any]:
    """Verify a compiled `.dll` exists, has non-zero size, and starts with PE `MZ` header."""
    if not dll_path.is_file():
        return {
            "name": dll_path.name,
            "path": str(dll_path),
            "size_bytes": 0,
            "pe_header_valid": False,
        }
    size = dll_path.stat().st_size
    with dll_path.open("rb") as fh:
        magic = fh.read(2)
    return {
        "name": dll_path.name,
        "path": str(dll_path),
        "size_bytes": size,
        "pe_header_valid": size > 0 and magic == b"MZ",
    }


def _run_csc_compile(
    csc_path: str,
    sources: list[Path],
    output_dll: Path,
    defines: list[str],
    references: list[str],
) -> tuple[bool, list[str], list[str]]:
    """Invoke `csc.exe` (or `mcs`) to compile `sources` into `output_dll`."""
    cmd: list[str] = [
        csc_path,
        "/nologo",
        "/target:library",
        "/optimize+",
        f"/out:{output_dll}",
    ]
    for symbol in defines:
        cmd.append(f"/define:{symbol}")
    for ref in references:
        cmd.append(f"/reference:{ref}")
    cmd.extend(str(s) for s in sources)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    warnings: list[str] = []
    errors: list[str] = []
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if "error cs" in lower or ": error " in lower:
            errors.append(stripped)
        elif "warning cs" in lower or ": warning " in lower:
            warnings.append(stripped)

    if proc.returncode != 0 and not errors:
        errors.append(
            f"Compiler exited with code {proc.returncode}: {combined.strip() or 'no diagnostic output'}"
        )
    return proc.returncode == 0, warnings, errors


def _run_dotnet_sdk_build(
    dotnet_path: str,
    mod_path: Path,
    mod_class_name: str,
    output_dir: Path,
    edition: str,
    defines: list[str],
    host_assembly: Path | None,
) -> tuple[bool, list[str], list[str]]:
    """Invoke `dotnet build` when a full .NET SDK is available."""
    csproj_path = mod_path / f"{mod_class_name}.csproj"
    if not csproj_path.is_file():
        return False, [], [f"Missing project file: {csproj_path}"]

    edition_prop = "EnhancedGen9" if edition == "enhanced_gen9" else "LegacyGen8"
    runtime_csproj = _runtime_source_dir() / "GtaAnything.Runtime.csproj"
    cmd = [
        dotnet_path,
        "build",
        str(csproj_path),
        "-c",
        "Release",
        "-o",
        str(output_dir),
        f"-p:Edition={edition_prop}",
        f"-p:GtaAnythingRuntimeProject={runtime_csproj}",
        f"-p:DefineConstants={';'.join(defines)}",
    ]
    if host_assembly is not None:
        cmd.append(f"-p:AdditionalReferencePath={host_assembly}")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    warnings: list[str] = []
    errors: list[str] = []
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if ": error " in lower:
            errors.append(stripped)
        elif ": warning " in lower:
            warnings.append(stripped)

    if proc.returncode != 0 and not errors:
        errors.append(f"dotnet build failed with exit code {proc.returncode}: {combined.strip()}")
    return proc.returncode == 0, warnings, errors


def compile_csharp_mod(
    mod_dir: str | Path,
    game_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    edition: str = "enhanced_gen9",
) -> dict[str, Any]:
    """Compile a transpiled GTA-Anything C# mod into real PE `.dll` assemblies.

    Compiles `GtaAnything.Runtime.dll` and `<ModClassName>.dll`. When `game_dir` is
    provided and contains `ScriptHookVDotNet3.dll` (or `RAGEPluginHook.dll` for RPH),
    links against the real host assembly with `SHVDN_REFERENCED` (or `RPH_REFERENCED`).
    Otherwise compiles clean-room standalone `.dll`s with zero proprietary dependencies.
    """
    mod_path = Path(mod_dir).resolve()
    if not mod_path.is_dir():
        return {
            "ok": False,
            "mod_class_name": "",
            "loader_target": "unknown",
            "edition": edition,
            "compiler": detect_csharp_compiler(),
            "live_host_linked": False,
            "host_assembly_path": None,
            "defines": [],
            "output_dir": str(output_dir or ""),
            "artifacts": [],
            "runtime_dll": None,
            "mod_dll": None,
            "warnings": [],
            "errors": [f"Mod directory does not exist: {mod_path}"],
        }

    mod_class_name, loader_target = _discover_mod_metadata(mod_path)
    out_path = Path(output_dir).resolve() if output_dir is not None else (mod_path / "bin")
    out_path.mkdir(parents=True, exist_ok=True)

    compiler = detect_csharp_compiler()
    warnings: list[str] = []
    errors: list[str] = []

    if compiler["kind"] == "none" or not compiler["path"]:
        return {
            "ok": False,
            "mod_class_name": mod_class_name,
            "loader_target": loader_target,
            "edition": edition,
            "compiler": compiler,
            "live_host_linked": False,
            "host_assembly_path": None,
            "defines": [],
            "output_dir": str(out_path),
            "artifacts": [],
            "runtime_dll": None,
            "mod_dll": None,
            "warnings": [],
            "errors": [
                "No C# compiler found. Install .NET SDK, Visual Studio Build Tools, or Windows .NET Framework 4.x."
            ],
        }

    defines = [
        "GTAV_ENHANCED" if edition == "enhanced_gen9" else "GTAV_LEGACY",
        "USE_RPH" if loader_target == "rph" else "USE_SHVDN",
    ]

    host_assembly: Path | None = None
    extra_refs: list[str] = []
    if game_dir is not None:
        game_path = Path(game_dir)
        host_assembly = _find_host_assembly(game_path, loader_target)
        if host_assembly is not None:
            if loader_target == "rph":
                defines.append("RPH_REFERENCED")
                extra_refs.append(str(host_assembly))
            else:
                defines.append("SHVDN_REFERENCED")
                extra_refs.extend(
                    [
                        str(host_assembly),
                        "System.Windows.Forms.dll",
                        "System.Drawing.dll",
                    ]
                )
        else:
            warnings.append(
                f"Host assembly not found under '{game_path}'; falling back to clean-room standalone build."
            )

    runtime_dir = _runtime_source_dir()
    runtime_sources = sorted(runtime_dir.rglob("*.cs"))
    mod_sources = sorted(mod_path.glob("*.cs"))

    if not runtime_sources:
        errors.append(f"No GtaAnything.Runtime C# sources found under {runtime_dir}")
    if not mod_sources:
        errors.append(f"No transpiled .cs files found in {mod_path}")

    if errors:
        return {
            "ok": False,
            "mod_class_name": mod_class_name,
            "loader_target": loader_target,
            "edition": edition,
            "compiler": compiler,
            "live_host_linked": host_assembly is not None,
            "host_assembly_path": str(host_assembly) if host_assembly else None,
            "defines": defines,
            "output_dir": str(out_path),
            "artifacts": [],
            "runtime_dll": None,
            "mod_dll": None,
            "warnings": warnings,
            "errors": errors,
        }

    runtime_dll_path = out_path / "GtaAnything.Runtime.dll"
    mod_dll_path = out_path / f"{mod_class_name}.dll"

    # Prefer direct csc.exe compilation when linking external host DLLs or when using netfx/roslyn/mono csc
    use_csc = compiler["kind"] != "dotnet_sdk" or host_assembly is not None
    if use_csc and compiler["kind"] == "dotnet_sdk":
        fallback_csc = _find_vs_roslyn_csc() or _find_netfx_csc()
        if fallback_csc:
            compiler = {"kind": "netfx_csc", "path": fallback_csc}
        else:
            use_csc = False

    if use_csc:
        ok_rt, warn_rt, err_rt = _run_csc_compile(
            csc_path=compiler["path"],
            sources=runtime_sources,
            output_dll=runtime_dll_path,
            defines=defines,
            references=extra_refs,
        )
        warnings.extend(warn_rt)
        errors.extend(err_rt)

        ok_mod = False
        if ok_rt:
            mod_refs = [str(runtime_dll_path), *extra_refs]
            ok_mod, warn_mod, err_mod = _run_csc_compile(
                csc_path=compiler["path"],
                sources=mod_sources,
                output_dll=mod_dll_path,
                defines=defines,
                references=mod_refs,
            )
            warnings.extend(warn_mod)
            errors.extend(err_mod)
        compiled_ok = ok_rt and ok_mod
    else:
        compiled_ok, warn_sdk, err_sdk = _run_dotnet_sdk_build(
            dotnet_path=compiler["path"],
            mod_path=mod_path,
            mod_class_name=mod_class_name,
            output_dir=out_path,
            edition=edition,
            defines=defines,
            host_assembly=host_assembly,
        )
        warnings.extend(warn_sdk)
        errors.extend(err_sdk)

    # Copy config JSON alongside the compiled DLLs for drop-in deployment
    config_src = mod_path / f"{mod_class_name}Config.json"
    if compiled_ok and config_src.is_file():
        config_dst = out_path / config_src.name
        if config_src.resolve() != config_dst.resolve():
            shutil.copy2(config_src, config_dst)

    rt_info = _verify_pe_dll(runtime_dll_path)
    mod_info = _verify_pe_dll(mod_dll_path)
    artifacts = [rt_info, mod_info]

    if compiled_ok and not (rt_info["pe_header_valid"] and mod_info["pe_header_valid"]):
        compiled_ok = False
        errors.append("Compiled output DLL failed PE 'MZ' header verification.")

    return {
        "ok": compiled_ok,
        "mod_class_name": mod_class_name,
        "loader_target": loader_target,
        "edition": edition,
        "compiler": compiler,
        "live_host_linked": host_assembly is not None,
        "host_assembly_path": str(host_assembly) if host_assembly else None,
        "defines": defines,
        "output_dir": str(out_path),
        "artifacts": artifacts,
        "runtime_dll": str(runtime_dll_path) if rt_info["pe_header_valid"] else None,
        "mod_dll": str(mod_dll_path) if mod_info["pe_header_valid"] else None,
        "warnings": warnings,
        "errors": errors,
    }
