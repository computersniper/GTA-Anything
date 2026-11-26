"""Clean-room C# transpiler generating `<ModClassName>.csproj`, `ModEntrypoint.cs`,
optional `RphPluginBridge.cs` (for `loader_target == "rph"`), 2D SVG menu preview cards
(`cards/<track_id>_card.svg`), `<ModClassName>Config.json`, and `BUILD_AND_VERIFY.md`
targeting `GtaAnything.Runtime`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from gta_anything.models.ir import GameplayIR, validate_gameplay_ir
from gta_anything.models.manifest import ACCEPTANCE_LAYERS
from gta_anything.transpiler.card_renderer import generate_static_menu_cards
from gta_anything.transpiler.world_mapper import map_ir_to_world


_PHASE_TO_RUNTIME_ENUM = {
    "standby": "OperationalPhase.Idle",
    "ui": "OperationalPhase.MenuSelecting",
    "streaming": "OperationalPhase.ResourceStreaming",
    "spawning": "OperationalPhase.SpawningShift",
    "operation": "OperationalPhase.ActiveOperation",
    "completion": "OperationalPhase.Completing",
    "cleanup": "OperationalPhase.Teardown",
}

_LOADER_TO_RUNTIME_ENUM = {
    "shvdn_v3": "LoaderKind.ShvdnV3",
    "shvdn_enhanced": "LoaderKind.ShvdnEnhanced",
    "rph": "LoaderKind.RagePluginHook",
}


def _resolve_runtime_project_ref(out_path: Path) -> str:
    """Resolve a clean-room portable path to `GtaAnything.Runtime.csproj` without embedding any host drive or user directory."""
    repo_root = Path(__file__).resolve().parents[3]
    runtime_csproj = (
        repo_root
        / "runtime"
        / "csharp"
        / "GtaAnything.Runtime"
        / "GtaAnything.Runtime.csproj"
    )
    try:
        rel = os.path.relpath(runtime_csproj, out_path.resolve())
        if "users" not in rel.lower() and ":" not in rel:
            return rel.replace("/", "\\")
    except ValueError:
        pass
    # Fallback to a portable relative MSBuild reference path (zero host drive or personal user paths)
    return "..\\..\\runtime\\csharp\\GtaAnything.Runtime\\GtaAnything.Runtime.csproj"


def _render_csproj(
    mod_class_name: str,
    ir: GameplayIR,
    runtime_csproj_ref: str,
) -> str:
    default_edition = (
        "EnhancedGen9"
        if "enhanced_gen9" in ir.meta.target_editions
        else "LegacyGen8"
    )
    loader_symbol = "USE_RPH" if ir.loader_target == "rph" else "USE_SHVDN"
    return f"""<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>netstandard2.0</TargetFramework>
    <LangVersion>latest</LangVersion>
    <Nullable>disable</Nullable>
    <AssemblyName>{mod_class_name}</AssemblyName>
    <RootNamespace>GtaAnything.Mods.{mod_class_name}</RootNamespace>
    <Edition Condition="'$(Edition)' == ''">{default_edition}</Edition>
    <GtaAnythingRuntimeProject Condition="'$(GtaAnythingRuntimeProject)' == ''">{runtime_csproj_ref}</GtaAnythingRuntimeProject>
  </PropertyGroup>

  <PropertyGroup Condition="'$(Edition)' == 'EnhancedGen9'">
    <DefineConstants>$(DefineConstants);GTAV_ENHANCED;{loader_symbol}</DefineConstants>
  </PropertyGroup>

  <PropertyGroup Condition="'$(Edition)' == 'LegacyGen8'">
    <DefineConstants>$(DefineConstants);GTAV_LEGACY;{loader_symbol}</DefineConstants>
  </PropertyGroup>

  <ItemGroup>
    <ProjectReference Include="$(GtaAnythingRuntimeProject)" Condition="Exists('$(GtaAnythingRuntimeProject)')" />
  </ItemGroup>

  <ItemGroup>
    <None Update="{mod_class_name}Config.json">
      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
    </None>
    <None Update="cards\\**\\*.svg">
      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
    </None>
  </ItemGroup>

</Project>
"""


def _cs_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", " ")
    )


def _render_mod_entrypoint_cs(
    mod_class_name: str,
    ir: GameplayIR,
    world_mapping: dict[str, Any],
) -> str:
    ui_binding = world_mapping["ui_binding"]
    hotkey_binding = world_mapping["hotkey_binding"]
    preview_enum = ui_binding["runtime_preview_enum"]
    loader_enum = _LOADER_TO_RUNTIME_ENUM.get(ir.loader_target, "LoaderKind.ShvdnEnhanced")

    primary_veh = next(
        (
            e
            for e in world_mapping["entity_bindings"]
            if e["kind"] == "vehicle" and e["is_player_vehicle"]
        ),
        world_mapping["entity_bindings"][0],
    )
    primary_ped = next(
        (e for e in world_mapping["entity_bindings"] if e["kind"] == "ped"),
        None,
    )
    ped_fallback = primary_ped["vanilla_fallback_model"] if primary_ped else "a_m_y_business_01"
    preferred_addon_cs = (
        f"\"{_cs_escape(primary_veh['preferred_addon_model'])}\""
        if primary_veh.get("preferred_addon_model")
        else "null"
    )
    modifier_cs = (
        f"\"{_cs_escape(hotkey_binding['modifier_key'])}\""
        if hotkey_binding.get("modifier_key")
        else "null"
    )

    # Render state registrations
    state_reg_lines: list[str] = []
    for st in ir.state_machine.states:
        phase_enum = _PHASE_TO_RUNTIME_ENUM.get(st.phase, "OperationalPhase.ActiveOperation")
        state_reg_lines.append(
            f'            _stateMachine.RegisterState("{_cs_escape(st.name)}", {phase_enum});'
        )

    # Render transition registrations
    trans_reg_lines: list[str] = []
    for tr in ir.state_machine.transitions:
        trans_reg_lines.append(
            f'            _stateMachine.RegisterTransition("{_cs_escape(tr.from_state)}", '
            f'"{_cs_escape(tr.to_state)}", "{_cs_escape(tr.trigger)}");'
        )

    # Render static menu cards and route waypoints
    card_lines: list[str] = []
    stop_lines: list[str] = []
    for track in world_mapping["track_bindings"]:
        card_lines.append(
            "            _menu.AddCard(new StaticMenuCard(\n"
            f'                itemId: "{_cs_escape(track["track_id"])}",\n'
            f'                title: "{_cs_escape(track["name"])}",\n'
            f'                subtitle: "Stops: {track["stop_count"]} | Reward/Fare: ${track["fare_or_reward"]}",\n'
            f'                spriteDict: "gtav_cleanroom_cards",\n'
            f'                spriteName: "{_cs_escape(track["track_id"])}_card",\n'
            f'                vanillaFallbackModel: "{_cs_escape(primary_veh["vanilla_fallback_model"])}",\n'
            f"                preferredAddonModel: {preferred_addon_cs}\n"
            "            ));"
        )
        for stop in track["stops"]:
            stop_lines.append(
                f'            _waypoints.Add(new WaypointNode({stop["index"]}, '
                f'"{_cs_escape(stop["name"])}", {float(stop["x"]):.2f}f, '
                f'{float(stop["y"]):.2f}f, {float(stop["z"]):.2f}f, {int(stop["dwell_seconds"])}));'
            )

    active_state_name = next(
        (s.name for s in ir.state_machine.states if s.phase == "operation"),
        "ActiveRoute",
    )
    summary_state_name = next(
        (s.name for s in ir.state_machine.states if s.phase == "completion"),
        "ShiftSummary",
    )

    state_block = "\n".join(state_reg_lines)
    trans_block = "\n".join(trans_reg_lines)
    cards_block = "\n".join(card_lines)
    stops_block = "\n".join(stop_lines)

    return f"""// Auto-generated Clean-Room GTA Mod by GTA-Anything v0.2.0
// Mod ID: {ir.meta.id} | Loader Target: {ir.loader_target} | License: {ir.meta.license}
// Architectural Invariants Enforced:
//   1. UI-Spawn Decoupling (preview_mode = {ir.ui_spec.preview_mode}, never live_3d_spawn)
//   2. SafeModelStreamer with mandatory ReleaseModelRequest on timeout + vanilla fallback ('{primary_veh["vanilla_fallback_model"]}')
//   3. WorldSession leased entity tracking and deterministic Teardown cleanup
//   4. Dual Build ID detection & L1-L7 PhasedJsonLogger telemetry

using System;
using System.Collections.Generic;
using GtaAnything.Runtime.Compatibility;
using GtaAnything.Runtime.Lifecycle;
using GtaAnything.Runtime.Streaming;
using GtaAnything.Runtime.Telemetry;
using GtaAnything.Runtime.UI;

namespace GtaAnything.Mods.{mod_class_name}
{{
    public sealed class WaypointNode
    {{
        public int Index {{ get; }}
        public string Name {{ get; }}
        public float X {{ get; }}
        public float Y {{ get; }}
        public float Z {{ get; }}
        public int DwellSeconds {{ get; }}

        public WaypointNode(int index, string name, float x, float y, float z, int dwellSeconds)
        {{
            Index = index;
            Name = name;
            X = x;
            Y = y;
            Z = z;
            DwellSeconds = dwellSeconds;
        }}
    }}

    public sealed class ModEntrypoint : IDisposable
    {{
        public const string ModId = "{_cs_escape(ir.meta.id)}";
        public const string ModName = "{_cs_escape(ir.meta.name)}";
        public const string LoaderTarget = "{_cs_escape(ir.loader_target)}";
        public const string PrimaryVanillaFallbackModel = "{_cs_escape(primary_veh["vanilla_fallback_model"])}";
        public const string PrimaryNpcFallbackModel = "{_cs_escape(ped_fallback)}";
        public const int DefaultStreamTimeoutMs = {int(primary_veh["stream_timeout_ms"])};

#if GTAV_ENHANCED
        public const string CompiledEdition = "enhanced_gen9";
#elif GTAV_LEGACY
        public const string CompiledEdition = "legacy_gen8";
#else
        public const string CompiledEdition = "enhanced_gen9";
#endif

        private readonly IGtaWorldHost _host;
        private readonly PhasedJsonLogger _logger;
        private readonly WorldSession _session;
        private readonly OperationalStateMachine _stateMachine;
        private readonly SafeModelStreamer _streamer;
        private readonly DecoupledMenuController _menu;
        private readonly LoaderAdapter _loaderAdapter;
        private readonly List<WaypointNode> _waypoints = new List<WaypointNode>();

        private IVehicleHandle _activeServiceVehicle;
        private IBlipHandle _activeStopBlip;
        private int _currentWaypointIndex;
        private int _accumulatedFareOrReward;

        public string CurrentState => _stateMachine.CurrentState;
        public int ActiveLeasedEntities => _session.ActiveLeaseCount;
        public int AccumulatedFareOrReward => _accumulatedFareOrReward;

        public ModEntrypoint(IGtaWorldHost host = null, string telemetryLogPath = null)
        {{
            _host = host ?? HostBridgeFactory.CreateDefaultHost({loader_enum});
            _logger = new PhasedJsonLogger(ModId, telemetryLogPath);
            _session = new WorldSession(_host);
            _streamer = new SafeModelStreamer(_host);

            var buildInfo = GameEditionDetector.DetectFromEnvironment();
            _logger.LogLayerReached(2, "loader_boot", "BuildDetected",
                $"Edition={{buildInfo.Edition}}, Exe={{buildInfo.DiskExecutableVersion}}, SHV={{buildInfo.ScriptHookBuildAlias}}, Loader={{LoaderTarget}}");

            _stateMachine = new OperationalStateMachine(
                initialState: "{_cs_escape(ir.state_machine.initial_state)}",
                cleanupState: "{_cs_escape(ir.state_machine.cleanup_state)}",
                onTeardownCallback: ExecuteDeterministicTeardown
            );

            ConfigureStateMachine();

            _menu = new DecoupledMenuController(
                title: "{_cs_escape(ui_binding["title"])}",
                subtitle: "{_cs_escape(ui_binding["subtitle"])}",
                previewMode: MenuPreviewMode.{preview_enum}
            );

            ConfigureMenuAndWaypoints();

            var chord = new HotkeyChord("{_cs_escape(hotkey_binding["activation_key"])}", {modifier_cs});
            _loaderAdapter = new LoaderAdapter(_host, chord, {loader_enum});
            _loaderAdapter.OnActivationChordPressed += _ => OnActivationHotkeyPressed();
            _loaderAdapter.OnTick += OnTick;
            _loaderAdapter.OnAbort += OnAbort;

            _logger.LogLayerReached(3, "script_init", "SessionInitialized",
                $"Mod={{ModName}}, CompiledEdition={{CompiledEdition}}, Waypoints={{_waypoints.Count}}");
        }}

        private void ConfigureStateMachine()
        {{
{state_block}

{trans_block}
        }}

        private void ConfigureMenuAndWaypoints()
        {{
{cards_block}

{stops_block}
        }}

        public void OnActivationHotkeyPressed()
        {{
            _stateMachine.ExecuteGuarded(() =>
            {{
                if (_stateMachine.CurrentState == "{_cs_escape(ir.state_machine.initial_state)}")
                {{
                    _stateMachine.FireOrTeardown("HotkeyPressed");
                    _menu.Open();
                    _logger.LogLayerReached(4, "ui_interaction", "MenuOpened",
                        $"Card={{_menu.CurrentCard?.Title}}, PreviewMode={preview_enum}");
                }}
            }}, OnRuntimeException);
        }}

        public StaticMenuCard ScrollMenuPreview(int newIndex)
        {{
            // UI-Spawn Decoupling invariant: updates static card metadata/2D sprite only, NEVER spawns 3D vehicles
            var card = _menu.OnIndexChanged(newIndex);
            _logger.LogEvent("L4", "ui_interaction", "StaticPreviewUpdated", $"Index={{newIndex}}, Title={{card?.Title}}");
            return card;
        }}

        public bool ConfirmMenuAndStartShift()
        {{
            var selectedCard = _menu.ConfirmSelection();
            _stateMachine.FireOrTeardown("ShiftConfirmed");

            var firstStop = _waypoints.Count > 0
                ? _waypoints[0]
                : new WaypointNode(0, "Default Depot", 436.2f, -645.8f, 28.7f, 6);

            var streamResult = _streamer.StreamAndSpawnVehicle(
                preferredAddonModel: selectedCard?.PreferredAddonModel ?? {preferred_addon_cs},
                vanillaFallbackModel: selectedCard?.VanillaFallbackModel ?? PrimaryVanillaFallbackModel,
                x: firstStop.X,
                y: firstStop.Y,
                z: firstStop.Z,
                heading: 0f,
                timeoutMs: DefaultStreamTimeoutMs
            );

            if (!streamResult.Success || streamResult.Vehicle == null || !streamResult.Vehicle.Exists())
            {{
                _logger.LogEvent("L5", "resource_streaming_and_spawn", "CriticalStreamFailure",
                    streamResult.ErrorMessage ?? "Vehicle stream/spawn returned null");
                _stateMachine.FireOrTeardown("CriticalStreamFailure");
                return false;
            }}

            _stateMachine.FireOrTeardown("ModelReadyOrFallback");

            _activeServiceVehicle = _session.LeaseVehicle(streamResult.Vehicle);
            _activeServiceVehicle.Repair();
            _activeServiceVehicle.SetDoorsShut(instant: true);

            _currentWaypointIndex = 0;
            _accumulatedFareOrReward = 0;
            _activeStopBlip = _session.LeaseBlip(_host.CreateBlip(
                firstStop.X, firstStop.Y, firstStop.Z,
                sprite: {world_mapping["track_bindings"][0]["blip_sprite_id"] if world_mapping["track_bindings"] else 513},
                color: {world_mapping["track_bindings"][0]["blip_color_id"] if world_mapping["track_bindings"] else 3},
                label: firstStop.Name
            ));
            _activeStopBlip.SetRoute(true);

            _stateMachine.FireOrTeardown("DriverSeated");
            _logger.LogLayerReached(5, "resource_streaming_and_spawn", "ServiceVehicleSpawned",
                $"Model={{streamResult.ResolvedModelName}}, UsedFallback={{streamResult.UsedFallback}}");
            return true;
        }}

        public void AdvanceOperationalStop()
        {{
            _stateMachine.ExecuteGuarded(() =>
            {{
                if (_stateMachine.CurrentState != "{_cs_escape(active_state_name)}")
                {{
                    return;
                }}

                if (_activeServiceVehicle == null || !_activeServiceVehicle.Exists())
                {{
                    _stateMachine.FireOrTeardown("ShiftAbortedOrVehicleDestroyed");
                    return;
                }}

                var stop = _waypoints[_currentWaypointIndex];
                if (_host.RequestModel(PrimaryNpcFallbackModel))
                {{
                    var passenger = _host.SpawnPed(PrimaryNpcFallbackModel, stop.X + 1.5f, stop.Y + 1.5f, stop.Z);
                    if (passenger != null && passenger.Exists())
                    {{
                        _session.LeasePed(passenger);
                        passenger.TaskEnterVehicle(_activeServiceVehicle, seatIndex: 0, timeoutMs: 3000);
                    }}
                    _host.ReleaseModelRequest(PrimaryNpcFallbackModel);
                }}

                _accumulatedFareOrReward += {int(world_mapping["track_bindings"][0]["fare_or_reward"]) if world_mapping["track_bindings"] else 15};
                _logger.LogLayerReached(6, "active_operation", "StopCompleted",
                    $"Stop={{stop.Name}}, Index={{stop.Index}}, TotalReward={{_accumulatedFareOrReward}}");

                _currentWaypointIndex++;
                if (_currentWaypointIndex >= _waypoints.Count)
                {{
                    _stateMachine.FireOrTeardown("FinalStopCompleted");
                    _logger.LogEvent("L6", "completion", "ShiftSummaryRecorded",
                        $"StopsCompleted={{_waypoints.Count}}, FinalReward={{_accumulatedFareOrReward}}");
                }}
            }}, OnRuntimeException);
        }}

        public void CompleteOrAbortShift()
        {{
            if (_stateMachine.CurrentState == "{_cs_escape(summary_state_name)}")
            {{
                _stateMachine.FireOrTeardown("SummaryAcknowledged");
            }}
            else if (_stateMachine.CurrentState != "{_cs_escape(ir.state_machine.initial_state)}")
            {{
                _stateMachine.ForceTeardown("UserRequestedTeardown");
            }}

            if (_stateMachine.CurrentState == "{_cs_escape(ir.state_machine.cleanup_state)}")
            {{
                _stateMachine.TryFire("ResourcesReleased", out _);
            }}
        }}

        private void ExecuteDeterministicTeardown()
        {{
            _menu.Close();
            int released = _session.DisposeAll();
            _activeServiceVehicle = null;
            _activeStopBlip = null;
            _logger.LogLayerReached(7, "cleanup", "TeardownCompleted",
                $"ReleasedEntities={{released}}, LeasedEntitiesRemaining={{_session.ActiveLeaseCount}}");
        }}

        private void OnRuntimeException(Exception ex)
        {{
            _logger.LogException("L7", "exception_guard", ex);
        }}

        public void OnTick()
        {{
            // Hooked by LoaderAdapter on each engine frame
        }}

        public void OnAbort()
        {{
            _stateMachine.ForceTeardown("ScriptAbort");
            _logger.Dispose();
        }}

        public void Dispose()
        {{
            OnAbort();
        }}
    }}
}}
"""


def _render_rph_plugin_bridge_cs(
    mod_class_name: str,
    ir: GameplayIR,
) -> str:
    """Render clean-room RAGE Plugin Hook entrypoint bridge (`RphPluginBridge.cs`)."""
    return f"""// Auto-generated Clean-Room RAGE Plugin Hook (RPH) Bridge by GTA-Anything v0.2.0
// Mod ID: {ir.meta.id} | Loader Target: rph | License: {ir.meta.license}
// Compiles cleanly under netstandard2.0 without bundling RAGEPluginHookSDK.dll.
// Define RPH_REFERENCED when linking against a user-supplied local RPH SDK assembly.

using System;
using GtaAnything.Runtime.Compatibility;

#if USE_RPH
#if RPH_REFERENCED
[assembly: Rage.Attributes.Plugin(
    "{_cs_escape(ir.meta.name)}",
    Description = "{_cs_escape(ir.meta.description or ir.meta.name)}",
    Author = "{_cs_escape(ir.meta.author)}",
    PrefersSingleInstance = true)]
#endif

namespace GtaAnything.Mods.{mod_class_name}
{{
    /// <summary>
    /// Clean-room RAGE Plugin Hook fiber-safe plugin entrypoint and deterministic unload bridge.
    /// Delegates lifecycle, streaming, and <c>WorldSession.DisposeAll()</c> teardown to <see cref="ModEntrypoint"/>.
    /// </summary>
    public static class RphPluginBridge
    {{
        private static ModEntrypoint _entrypoint;
        private static volatile bool _running;

        public static bool IsRunning => _running;

        /// <summary>
        /// RPH plugin entry method invoked by RAGEPluginHook.exe on plugin load.
        /// </summary>
        public static void Main()
        {{
            IGtaWorldHost host = HostBridgeFactory.CreateDefaultHost(LoaderKind.RagePluginHook);
            _entrypoint = new ModEntrypoint(host);
            _running = true;

#if RPH_REFERENCED
            Rage.GameFiber.StartNew(FiberLoop, "{mod_class_name}_MainFiber");
#else
            RunFiberStep();
#endif
        }}

        /// <summary>
        /// Executes a single fiber-safe frame tick against <see cref="ModEntrypoint"/>.
        /// </summary>
        public static void RunFiberStep()
        {{
            if (!_running || _entrypoint == null)
            {{
                return;
            }}
            _entrypoint.OnTick();
        }}

#if RPH_REFERENCED
        private static void FiberLoop()
        {{
            while (_running)
            {{
                RunFiberStep();
                Rage.GameFiber.Yield();
            }}
        }}
#endif

        /// <summary>
        /// RPH plugin unload hook ensuring deterministic <c>WorldSession.DisposeAll()</c> cleanup
        /// whenever the plugin is unloaded or GTA V exits.
        /// </summary>
        public static void OnUnload(bool isTerminating)
        {{
            _running = false;
            if (_entrypoint != null)
            {{
                _entrypoint.Dispose();
                _entrypoint = null;
            }}
        }}
    }}
}}
#endif
"""


def _render_build_and_verify_md(
    mod_class_name: str,
    ir: GameplayIR,
    world_mapping: dict[str, Any],
) -> str:
    layer_rows = "\n".join(
        f"| **{l['id']}** | {l['name']} | `{l['phase']}` | {l['evidence_required']} |"
        for l in ACCEPTANCE_LAYERS
    )
    entity_rows = "\n".join(
        f"| `{e['slot_id']}` | `{e['role']}` | `{e['vanilla_fallback_model']}` (`{e['vanilla_joaat_hex']}`) | "
        f"`{e['preferred_addon_model'] or 'None (Vanilla-First)'}` | `{e['stream_timeout_ms']} ms` |"
        for e in world_mapping["entity_bindings"]
    )
    loader_note = (
        "- **Loader Chain**: RAGE Plugin Hook (`USE_RPH`, `RphPluginBridge.cs` with fiber-safe loop & `OnUnload` deterministic teardown)."
        if ir.loader_target == "rph"
        else f"- **Loader Chain**: ScriptHookVDotNet (`USE_SHVDN`, target `{ir.loader_target}`)."
    )
    return f"""# {ir.meta.name} (`{mod_class_name}`) — Build & 7-Layer Verification Guide

> Generated by **GTA-Anything Clean-Room Transpiler v0.2.0** (`schema_version = {ir.schema_version}`).

---

## 1. Compilation (`dotnet build`)

This project targets `netstandard2.0` and links against `GtaAnything.Runtime`. It supports conditional compilation for both **GTA V Enhanced (Gen9)** and **GTA V Legacy (Gen8)**:

```bash
# Build for GTA V Enhanced (Gen9)
dotnet build {mod_class_name}.csproj -c Release -p:Edition=EnhancedGen9

# Build for GTA V Legacy (Gen8)
dotnet build {mod_class_name}.csproj -c Release -p:Edition=LegacyGen8
```

{loader_note}

---

## 2. World-Model Entity Bindings (Vanilla-First Baseline)

| Slot ID | Role | Vanilla Fallback (`JOAAT`) | Preferred Add-on | Stream Timeout |
| :--- | :--- | :--- | :--- | :--- |
{entity_rows}

- **UI-Spawn Decoupling**: `preview_mode = "{ir.ui_spec.preview_mode}"` (`live_3d_spawn` blocked; static 2D SVG cards generated in `cards/`).
- **Stream Timeout Guard**: Timed-out add-on models invoke `ReleaseModelRequest` (`MarkAsNoLongerNeeded`) immediately before falling back to vanilla models.

---

## 3. 7-Layer Acceptance Evidence Ladder (L1–L7)

| Layer | Milestone | Runtime Phase | Required Verification Evidence |
| :--- | :--- | :--- | :--- |
{layer_rows}
"""


def generate_csharp_mod(
    ir: GameplayIR | dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Generate a complete clean-room C# GTA mod project from a GameplayIR."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    report = validate_gameplay_ir(ir_obj)
    if not report.valid:
        raise ValueError(
            f"Cannot transpile invalid GameplayIR '{ir_obj.meta.id}': {'; '.join(report.errors)}"
        )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    world_mapping = map_ir_to_world(ir_obj)
    mod_class_name = world_mapping["mod_class_name"]
    runtime_ref = _resolve_runtime_project_ref(out_path)

    csproj_name = f"{mod_class_name}.csproj"
    entrypoint_name = "ModEntrypoint.cs"
    config_name = f"{mod_class_name}Config.json"
    verify_doc_name = "BUILD_AND_VERIFY.md"

    csproj_path = out_path / csproj_name
    entrypoint_path = out_path / entrypoint_name
    config_path = out_path / config_name
    verify_doc_path = out_path / verify_doc_name

    csproj_path.write_text(
        _render_csproj(mod_class_name, ir_obj, runtime_ref),
        encoding="utf-8",
    )
    entrypoint_path.write_text(
        _render_mod_entrypoint_cs(mod_class_name, ir_obj, world_mapping),
        encoding="utf-8",
    )

    config_payload = {
        "mod_id": ir_obj.meta.id,
        "mod_class_name": mod_class_name,
        "version": ir_obj.meta.version,
        "loader_target": ir_obj.loader_target,
        "target_editions": ir_obj.meta.target_editions,
        "inputs": ir_obj.inputs.to_dict(),
        "ui_spec": ir_obj.ui_spec.to_dict(),
        "world_mapping": world_mapping,
    }
    config_path.write_text(
        json.dumps(config_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    verify_doc_path.write_text(
        _render_build_and_verify_md(mod_class_name, ir_obj, world_mapping),
        encoding="utf-8",
    )

    generated_files = [
        str(csproj_path),
        str(entrypoint_path),
        str(config_path),
        str(verify_doc_path),
    ]

    if ir_obj.loader_target == "rph":
        rph_bridge_path = out_path / "RphPluginBridge.cs"
        rph_bridge_path.write_text(
            _render_rph_plugin_bridge_cs(mod_class_name, ir_obj),
            encoding="utf-8",
        )
        generated_files.append(str(rph_bridge_path))

    card_files = generate_static_menu_cards(ir_obj, out_path)
    generated_files.extend(card_files)

    return {
        "ok": True,
        "mod_id": ir_obj.meta.id,
        "mod_class_name": mod_class_name,
        "loader_target": ir_obj.loader_target,
        "output_dir": str(out_path),
        "generated_files": generated_files,
        "card_files": card_files,
        "world_mapping": world_mapping,
    }
