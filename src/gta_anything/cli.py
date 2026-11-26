"""Unified Click CLI (`gta-anything`) with global `--json` support for Agent-Native operation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from gta_anything import __version__
from gta_anything.extractor.analyzer import extract_gameplay_ir
from gta_anything.models.ir import GameplayIR, validate_gameplay_ir
from gta_anything.transpiler.csharp_codegen import generate_csharp_mod


def _is_json_mode(ctx: click.Context, local_json: bool = False) -> bool:
    if local_json:
        return True
    curr: click.Context | None = ctx
    while curr is not None:
        if curr.obj and curr.obj.get("json"):
            return True
        if curr.params.get("json_output"):
            return True
        curr = curr.parent
    return False


def _emit(
    ctx: click.Context,
    payload: dict[str, Any],
    human_lines: list[str],
    local_json: bool = False,
) -> None:
    if _is_json_mode(ctx, local_json):
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for line in human_lines:
            click.echo(line)


@click.group(invoke_without_command=True)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit deterministic machine-readable JSON output for AI Agent consumption.",
)
@click.version_option(__version__, prog_name="gta-anything")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """GTA-Anything: Agent-Native Gameplay Extraction, Clean-Room Transpilation,
    Gen8/Gen9 Asset Auditing, and Reversible Deployment Framework for GTA V.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    if ctx.invoked_subcommand is None:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "ok": True,
                        "name": "gta-anything",
                        "version": __version__,
                        "commands": [
                            "preflight",
                            "extract",
                            "validate-ir",
                            "transpile",
                            "asset-check",
                            "simulate",
                            "visualize",
                            "catalog",
                            "profile",
                            "diagnose",
                            "pipeline",
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            click.echo(ctx.get_help())


@cli.command("preflight")
@click.option(
    "--game-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional path to GTA V installation directory to inspect dual build IDs and loader chains.",
)
@click.option(
    "--min-free-gb",
    type=float,
    default=10.0,
    show_default=True,
    help="Minimum required free disk space in GB.",
)
@click.option(
    "--min-commit-mb",
    type=float,
    default=1536.0,
    show_default=True,
    help="Minimum recommended available OS commit memory in MB.",
)
@click.option(
    "--hotkey",
    type=str,
    default=None,
    help="Candidate activation hotkey to check for conflicts (e.g. F4, Insert, F9).",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def preflight_cmd(
    ctx: click.Context,
    game_dir: Path | None,
    min_free_gb: float,
    min_commit_mb: float,
    hotkey: str | None,
    local_json: bool,
) -> None:
    """Phase 0: Run environment, commit memory, dual build ID, and hotkey conflict preflight."""
    from gta_anything.preflight.checker import run_preflight

    report = run_preflight(
        game_dir=game_dir,
        min_free_gb=min_free_gb,
        min_commit_mb=min_commit_mb,
        hotkey=hotkey,
    )
    sys_info = report.get("system", {})
    game_info = report.get("game", {})
    human = [
        f"[Preflight] ok={report.get('ok')} | Disk free={sys_info.get('disk_free_gb')} GB | "
        f"Commit avail={sys_info.get('commit_available_mb')} MB",
        f"[Game] edition={game_info.get('edition')} | exe_version={game_info.get('exe_version')} | "
        f"shv_alias={game_info.get('shv_build_alias')}",
    ]
    for w in report.get("warnings", []):
        human.append(f"  WARN: {w}")
    for err in report.get("errors", []):
        human.append(f"  ERROR: {err}")
    _emit(ctx, report, human, local_json)


@cli.command("extract")
@click.argument("source_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional path to write the extracted gameplay_ir.json.",
)
@click.option("--mod-id", type=str, default=None, help="Override mod identifier.")
@click.option(
    "--edition",
    type=click.Choice(["enhanced_gen9", "legacy_gen8"]),
    default="enhanced_gen9",
    show_default=True,
    help="Primary target GTA V edition.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def extract_cmd(
    ctx: click.Context,
    source_path: Path,
    output: Path | None,
    mod_id: str | None,
    edition: str,
    local_json: bool,
) -> None:
    """Phase 1: Extract evidence-backed Gameplay IR from spec.md, routes/*.xml, or source directory."""
    ir = extract_gameplay_ir(source_path, mod_id=mod_id, target_edition=edition)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(ir.to_json(indent=2), encoding="utf-8")

    payload = {
        "ok": True,
        "mod_id": ir.meta.id,
        "name": ir.meta.name,
        "target_edition": edition,
        "output_path": str(output) if output else None,
        "evidence_count": len(ir.evidence),
        "ir": ir.to_dict(),
    }
    human = [
        f"[Extract] Extracted GameplayIR '{ir.meta.id}' ({ir.meta.name})",
        f"  Entities: {len(ir.entities)} | Tracks: {len(ir.routes_or_zones)} | "
        f"States: {len(ir.state_machine.states)} | Evidence Anchors: {len(ir.evidence)}",
    ]
    if output:
        human.append(f"  Written to: {output}")
    _emit(ctx, payload, human, local_json)


@cli.command("validate-ir")
@click.argument("ir_path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def validate_ir_cmd(
    ctx: click.Context,
    ir_path: Path,
    local_json: bool,
) -> None:
    """Phase 2: Validate Gameplay IR static safety invariants (vanilla fallback, UI decoupling, Teardown reachability)."""
    ir = (
        GameplayIR.from_json(ir_path.read_text(encoding="utf-8"))
        if ir_path.is_file() and ir_path.suffix.lower() == ".json"
        else extract_gameplay_ir(ir_path)
    )
    report = validate_gameplay_ir(ir)
    payload = {
        "ok": report.valid,
        "valid": report.valid,
        "mod_id": ir.meta.id,
        "errors": report.errors,
        "warnings": report.warnings,
        "checked_invariants": report.checked_invariants,
    }
    human = [
        f"[Validate-IR] mod_id={ir.meta.id} | valid={report.valid} | "
        f"errors={len(report.errors)} | warnings={len(report.warnings)}"
    ]
    for err in report.errors:
        human.append(f"  ERROR: {err}")
    for w in report.warnings:
        human.append(f"  WARN: {w}")
    _emit(ctx, payload, human, local_json)


@cli.command("transpile")
@click.argument("ir_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for generated C# mod project.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def transpile_cmd(
    ctx: click.Context,
    ir_path: Path,
    output_dir: Path,
    local_json: bool,
) -> None:
    """Phase 3: Transpile Gameplay IR into a clean-room C# mod project targeting GtaAnything.Runtime."""
    ir = (
        GameplayIR.from_json(ir_path.read_text(encoding="utf-8"))
        if ir_path.is_file() and ir_path.suffix.lower() == ".json"
        else extract_gameplay_ir(ir_path)
    )
    result = generate_csharp_mod(ir, output_dir)
    human = [
        f"[Transpile] Generated C# mod '{result['mod_class_name']}' ({result['mod_id']}) in {result['output_dir']}",
        *[f"  + {f}" for f in result["generated_files"]],
    ]
    _emit(ctx, result, human, local_json)


@cli.command("asset-check")
@click.argument("target_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--edition",
    type=click.Choice(["enhanced_gen9", "legacy_gen8"]),
    default="enhanced_gen9",
    show_default=True,
    help="Target GTA V edition for RSC version & script_rt texture format verification.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def asset_check_cmd(
    ctx: click.Context,
    target_path: Path,
    edition: str,
    local_json: bool,
) -> None:
    """Phase 4: Run 5-Stage Asset Gate static auditor (.yft v171/.ytd v5, script_rt_* B8G8R8A8_UNORM, dlclist.xml)."""
    from gta_anything.assets.auditor import audit_assets

    report = audit_assets(target_path, target_edition=edition)
    human = [
        f"[Asset-Check] ok={report.get('ok')} | edition={report.get('target_edition')} | "
        f"scanned={report.get('scanned_files')} | {report.get('summary')}"
    ]
    for finding in report.get("findings", []):
        human.append(
            f"  [{finding.get('severity', 'INFO')}] {finding.get('code', '')}: {finding.get('message', '')}"
        )
    _emit(ctx, report, human, local_json)


@cli.group("profile")
def profile_group() -> None:
    """Phase 6: Reversible profile isolation manager (status, stage, switch, rollback)."""


@profile_group.command("status")
@click.option(
    "--game-dir",
    type=click.Path(path_type=Path),
    required=True,
    help="Target GTA V directory.",
)
@click.option(
    "--profiles-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional profiles storage root.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def profile_status_cmd(
    ctx: click.Context,
    game_dir: Path,
    profiles_root: Path | None,
    local_json: bool,
) -> None:
    """Show active and parked profiles for the target GTA V directory."""
    from gta_anything.deploy.profile_manager import ProfileManager

    mgr = ProfileManager(game_dir=game_dir, profiles_root=profiles_root)
    res = mgr.status()
    human = [
        f"[Profile Status] active={res.get('active_profile')} | "
        f"available={res.get('available_profiles', res.get('profiles', []))}"
    ]
    _emit(ctx, res, human, local_json)


@profile_group.command("stage")
@click.argument("profile_name", type=str)
@click.option(
    "--game-dir",
    type=click.Path(path_type=Path),
    required=True,
    help="Target GTA V directory.",
)
@click.option(
    "--build-dir",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Transpiled mod build directory to stage.",
)
@click.option(
    "--loader",
    type=click.Choice(["shvdn", "rph"]),
    default="shvdn",
    show_default=True,
    help="Target loader chain.",
)
@click.option(
    "--profiles-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional profiles storage root.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing.")
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def profile_stage_cmd(
    ctx: click.Context,
    profile_name: str,
    game_dir: Path,
    build_dir: Path,
    loader: str,
    profiles_root: Path | None,
    dry_run: bool,
    local_json: bool,
) -> None:
    """Stage a transpiled mod build into an isolated profile slot."""
    from gta_anything.deploy.profile_manager import ProfileManager

    mgr = ProfileManager(game_dir=game_dir, profiles_root=profiles_root)
    res = mgr.stage_profile(
        profile_name=profile_name,
        mod_build_dir=build_dir,
        loader_chain=loader,
        dry_run=dry_run,
    )
    human = [f"[Profile Stage] ok={res.get('ok')} | profile={profile_name} | dry_run={dry_run}"]
    _emit(ctx, res, human, local_json)


@profile_group.command("switch")
@click.argument("profile_name", type=str)
@click.option(
    "--game-dir",
    type=click.Path(path_type=Path),
    required=True,
    help="Target GTA V directory.",
)
@click.option(
    "--profiles-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional profiles storage root.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without moving files.")
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def profile_switch_cmd(
    ctx: click.Context,
    profile_name: str,
    game_dir: Path,
    profiles_root: Path | None,
    dry_run: bool,
    local_json: bool,
) -> None:
    """Atomically switch the active mod profile using lock-guarded renames."""
    from gta_anything.deploy.profile_manager import ProfileManager

    mgr = ProfileManager(game_dir=game_dir, profiles_root=profiles_root)
    res = mgr.switch_profile(profile_name=profile_name, dry_run=dry_run)
    human = [f"[Profile Switch] ok={res.get('ok')} | profile={profile_name} | dry_run={dry_run}"]
    _emit(ctx, res, human, local_json)


@profile_group.command("rollback")
@click.option(
    "--game-dir",
    type=click.Path(path_type=Path),
    required=True,
    help="Target GTA V directory.",
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional explicit deployment manifest JSON path.",
)
@click.option(
    "--profiles-root",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional profiles storage root.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate rollback.")
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def profile_rollback_cmd(
    ctx: click.Context,
    game_dir: Path,
    manifest: Path | None,
    profiles_root: Path | None,
    dry_run: bool,
    local_json: bool,
) -> None:
    """Roll back the active profile to a clean state using the SHA-256 operation log."""
    from gta_anything.deploy.profile_manager import ProfileManager

    mgr = ProfileManager(game_dir=game_dir, profiles_root=profiles_root)
    res = mgr.rollback(manifest_path=manifest, dry_run=dry_run)
    human = [f"[Profile Rollback] ok={res.get('ok')} | dry_run={dry_run}"]
    _emit(ctx, res, human, local_json)


@cli.command("diagnose")
@click.argument(
    "log_paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--commit-mb",
    type=float,
    default=None,
    help="Available OS commit memory in MB at time of run (flags low commit memory < 1024 MB).",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def diagnose_cmd(
    ctx: click.Context,
    log_paths: tuple[Path, ...],
    commit_mb: float | None,
    local_json: bool,
) -> None:
    """Phase 7: Correlate ScriptHookV.log, ScriptHookVDotNet.log, RagePluginHook.log, and .jsonl telemetry."""
    from gta_anything.diagnose.log_correlator import diagnose_logs

    report = diagnose_logs(list(log_paths), commit_available_mb=commit_mb)
    human = [
        f"[Diagnose] ok={report.get('ok')} | build_alias={report.get('detected_build_alias')} | "
        f"highest_layer=L{report.get('highest_acceptance_layer_reached')} | "
        f"issues={len(report.get('issues', []))}"
    ]
    for issue in report.get("issues", []):
        human.append(
            f"  [{issue.get('category', 'unknown').upper()}] {issue.get('summary', issue.get('message', ''))}"
        )
    for rec in report.get("recommendations", []):
        human.append(f"  -> Recommendation: {rec}")
    _emit(ctx, report, human, local_json)


@cli.command("simulate")
@click.argument("ir_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--track-id",
    type=str,
    default=None,
    help="Optional track_id to simulate (defaults to the first track in routes_or_zones).",
)
@click.option(
    "--inject-addon-timeout",
    is_flag=True,
    default=False,
    help="Fault injection: simulate preferred add-on model streaming timeout and verify vanilla fallback + release.",
)
@click.option(
    "--inject-abort-at-stop",
    type=int,
    default=None,
    help="Fault injection: trigger guarded early abort at the given stop index and verify Teardown.",
)
@click.option(
    "--telemetry-out",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional path to write structured L1-L7 .jsonl simulation telemetry.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def simulate_cmd(
    ctx: click.Context,
    ir_path: Path,
    track_id: str | None,
    inject_addon_timeout: bool,
    inject_abort_at_stop: int | None,
    telemetry_out: Path | None,
    local_json: bool,
) -> None:
    """Run headless offline 7-layer (L1-L7) Gameplay IR simulation with optional fault injection."""
    from gta_anything.simulator.world_sim import simulate_gameplay_ir

    ir = (
        GameplayIR.from_json(ir_path.read_text(encoding="utf-8"))
        if ir_path.is_file() and ir_path.suffix.lower() == ".json"
        else extract_gameplay_ir(ir_path)
    )
    report = simulate_gameplay_ir(
        ir,
        track_id=track_id,
        inject_addon_timeout=inject_addon_timeout,
        inject_abort_at_stop=inject_abort_at_stop,
        telemetry_out=telemetry_out,
    )
    human = [
        f"[Simulate] ok={report.get('ok')} | mod_id={report.get('mod_id')} | track={report.get('track_id')}",
        f"  Layers: L1..L{report.get('highest_acceptance_layer_reached')} | "
        f"Stops: {report.get('stops_completed')}/{report.get('total_stops')} | "
        f"Distance: {report.get('total_distance_m')}m | Reward: ${report.get('total_reward')}",
        f"  Fallback used={report.get('used_vanilla_fallback')} | "
        f"Timed-out models released={report.get('released_timed_out_models')} | "
        f"Leases after teardown={report.get('active_leases_after_teardown')}",
    ]
    if report.get("telemetry_path"):
        human.append(f"  Telemetry JSONL: {report.get('telemetry_path')}")
    _emit(ctx, report, human, local_json)


@cli.command("visualize")
@click.argument("ir_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output path for the standalone offline HTML radar & state-machine blueprint.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def visualize_cmd(
    ctx: click.Context,
    ir_path: Path,
    output: Path,
    local_json: bool,
) -> None:
    """Render a standalone offline GTA Radar & Gameplay IR State-Machine HTML dashboard."""
    from gta_anything.visualizer.radar_html import render_ir_dashboard

    ir = (
        GameplayIR.from_json(ir_path.read_text(encoding="utf-8"))
        if ir_path.is_file() and ir_path.suffix.lower() == ".json"
        else extract_gameplay_ir(ir_path)
    )
    report = render_ir_dashboard(ir, output)
    human = [
        f"[Visualize] ok={report.get('ok')} | mod_id={report.get('mod_id')} | "
        f"tracks={report.get('track_count')} | states={report.get('state_count')}",
        f"  Dashboard HTML: {report.get('output_html')}",
    ]
    _emit(ctx, report, human, local_json)


@cli.command("catalog")
@click.option(
    "--category",
    type=str,
    default=None,
    help="Optional semantic category filter (e.g. transit, commercial, emergency, service, utility, sedan, dock_worker, civilian).",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def catalog_cmd(
    ctx: click.Context,
    category: str | None,
    local_json: bool,
) -> None:
    """Inspect the built-in GTA V Vanilla World-Model Semantic Catalog (vehicles, peds, blips, zones)."""
    from gta_anything.transpiler.world_mapper import list_world_catalog

    report = list_world_catalog(category=category)
    human = [
        f"[Catalog] ok={report.get('ok')} | filter={report.get('category') or 'ALL'} | "
        f"categories={', '.join(report.get('categories', []))}",
        f"  Vehicles: {len(report.get('vehicles', {}))} | Peds: {len(report.get('peds', {}))} | "
        f"Blips: {len(report.get('blips', {}))} | Zones: {len(report.get('zone_archetypes', {}))}",
    ]
    _emit(ctx, report, human, local_json)


@cli.command("pipeline")
@click.argument("source_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for extracted IR, transpiled C# project, simulation telemetry, and radar blueprint.",
)
@click.option(
    "--edition",
    type=click.Choice(["enhanced_gen9", "legacy_gen8"]),
    default="enhanced_gen9",
    show_default=True,
    help="Target GTA V edition.",
)
@click.option("--json", "local_json", is_flag=True, default=False, help="Output JSON.")
@click.pass_context
def pipeline_cmd(
    ctx: click.Context,
    source_path: Path,
    output_dir: Path,
    edition: str,
    local_json: bool,
) -> None:
    """Run end-to-end offline pipeline: Extract -> Validate-IR -> Transpile -> Asset-Check -> Simulate -> Visualize."""
    from gta_anything.assets.auditor import audit_assets
    from gta_anything.simulator.world_sim import simulate_gameplay_ir
    from gta_anything.visualizer.radar_html import render_ir_dashboard

    output_dir.mkdir(parents=True, exist_ok=True)
    ir = extract_gameplay_ir(source_path, target_edition=edition)
    ir_out_path = output_dir / "gameplay_ir.json"
    ir_out_path.write_text(ir.to_json(indent=2), encoding="utf-8")

    validation = validate_gameplay_ir(ir)
    transpiled = (
        generate_csharp_mod(ir, output_dir)
        if validation.valid
        else {
            "ok": False,
            "mod_id": ir.meta.id,
            "output_dir": str(output_dir),
            "generated_files": [],
            "world_mapping": {},
        }
    )

    asset_target = source_path if source_path.is_dir() else source_path.parent
    asset_report = audit_assets(asset_target, target_edition=edition)

    telemetry_path = output_dir / "simulation_telemetry.jsonl"
    sim_report = (
        simulate_gameplay_ir(ir, telemetry_out=telemetry_path)
        if validation.valid
        else {
            "ok": False,
            "mod_id": ir.meta.id,
            "skipped": True,
            "reason": "invalid_ir",
            "telemetry_path": None,
        }
    )

    radar_html_path = output_dir / "radar_blueprint.html"
    viz_report = render_ir_dashboard(ir, radar_html_path)

    overall_ok = (
        validation.valid
        and bool(transpiled.get("ok", False))
        and bool(asset_report.get("ok", True))
        and bool(sim_report.get("ok", False))
        and bool(viz_report.get("ok", False))
    )
    extract_stage = {
        "ok": True,
        "mod_id": ir.meta.id,
        "evidence_count": len(ir.evidence),
        "ir_path": str(ir_out_path),
    }
    validation_dict = validation.to_dict()
    payload = {
        "ok": overall_ok,
        "mod_id": ir.meta.id,
        "edition": edition,
        "output_dir": str(output_dir),
        "ir_path": str(ir_out_path),
        "telemetry_path": sim_report.get("telemetry_path"),
        "radar_html_path": viz_report.get("output_html"),
        "extract": extract_stage,
        "validation": validation_dict,
        "transpile": transpiled,
        "asset_check": asset_report,
        "simulation": sim_report,
        "visualization": viz_report,
        "stages": {
            "extract": extract_stage,
            "validate_ir": validation_dict,
            "transpile": transpiled,
            "asset_check": asset_report,
            "simulation": sim_report,
            "visualization": viz_report,
        },
    }
    human = [
        f"[Pipeline] ok={overall_ok} | mod_id={ir.meta.id} | edition={edition}",
        f"  1. Extract:       ok=True ({len(ir.evidence)} evidence anchors) -> {ir_out_path}",
        f"  2. Validate-IR:   valid={validation.valid} (errors={len(validation.errors)}, warnings={len(validation.warnings)})",
        f"  3. Transpile:     ok={transpiled.get('ok')} ({len(transpiled.get('generated_files', []))} files in {output_dir})",
        f"  4. Asset-Check:   ok={asset_report.get('ok')} (scanned={asset_report.get('scanned_files')} files)",
        f"  5. Simulation:    ok={sim_report.get('ok')} (L1..L{sim_report.get('highest_acceptance_layer_reached', 0)}, leases={sim_report.get('active_leases_after_teardown', 'n/a')}) -> {telemetry_path}",
        f"  6. Visualization: ok={viz_report.get('ok')} -> {radar_html_path}",
    ]
    _emit(ctx, payload, human, local_json)
