---
name: gta-anything
description: Agent-Native harness and CLI skill for turning authorized gameplay specs, structured route/dispatch data, or source repositories into clean-room, lifecycle-safe GTA V (Enhanced Gen9 & Legacy Gen8) mods with Gameplay IR extraction, C# transpilation, 5-stage asset auditing, reversible profile deployment, and 7-layer log diagnostics.
---

# GTA-Anything Agent Skill (`gta-anything`)

Use this skill whenever the user wants to:
- Design, extract, transpile, audit, deploy, or troubleshoot a **GTA V Mod** (supporting both **GTA V Enhanced / Gen9** and **GTA V Legacy / Gen8**).
- Convert a gameplay specification (`spec.md`), transit route XML (`routes/*.xml`), dispatch table, or authorized source repository into a playable open-world simulation in GTA V.
- Audit GTA vehicle/texture assets (`.yft`, `.ytd`, `.dds`, `dlclist.xml`) for Gen8 vs. Gen9 compatibility (such as `script_rt_*` render-target format crashes).
- Isolate and switch mod profiles (`SHVDN/ASI` chain vs. `RPH` chain) reversibly without corrupting the game installation.
- Correlate `ScriptHookV.log`, `ScriptHookVDotNet.log`, `RagePluginHook.log`, and `.jsonl` phased telemetry logs into actionable root causes.

---

## 1. Workflow Triggers & Mandatory 8-Phase Execution Order

Always follow the 8-Phase SOP defined in [`HARNESS.md`](../../HARNESS.md). Always pass `--json` to `gta-anything` commands when parsing outputs programmatically.

| Phase | Trigger / Goal | CLI Command |
| :--- | :--- | :--- |
| **Phase 0** | Check disk space, Windows commit memory, dual build IDs, running processes, and hotkey conflicts | `gta-anything --json preflight [--game-dir PATH] [--hotkey KEY]` |
| **Phase 0.5** | **MANDATORY**: Scan host `.ini`/`.cfg`/`.xml` keybinds, installed DLL/ASI ABI, and active/inactive profiles | `gta-anything --json host-scan [--game-dir PATH] [--no-inactive]` |
| **Phase 1** | Extract evidence-backed `GameplayIR` from `spec.md`, `routes/*.xml`, `.json`, or source directories | `gta-anything --json extract <source_path> -o gameplay_ir.json [--edition enhanced_gen9\|legacy_gen8]` |
| **Phase 2** | Validate IR safety invariants & run 5-dimension conflict arbitration with `--auto-rebind` | `gta-anything --json validate-ir <ir_path>`<br>`gta-anything --json conflict-check <ir_path> [--game-dir PATH] [--auto-rebind] [-o OUT_IR]` |
| **Phase 3** | Map IR to GTA world catalog, generate clean-room C# project, and compile PE `.dll` assemblies | `gta-anything --json transpile <ir_path> -o <out_dir>`<br>`gta-anything --json build-dll <mod_dir> [--game-dir PATH] [-o OUT_DIR] [--edition ...]` |
| **Phase 4** | Audit `.yft`/`.ytd`/`.dds`/`dlclist.xml` against the 5-Stage Gen8/Gen9 Asset Gates & auto-reencode `script_rt_*` | `gta-anything --json asset-check <path> [--edition enhanced_gen9\|legacy_gen8]`<br>`gta-anything --json asset-fix <path> [-o OUT_DIR] [--edition ...] [--dry-run]` |
| **Phase 5** | Run offline end-to-end pipeline (optionally with `--compile`) & verify L1–L7 Acceptance Evidence Ladder (`TEST.md`) | `gta-anything --json pipeline <source_path> -o <out_dir> [--edition enhanced_gen9\|legacy_gen8] [--compile] [--game-dir PATH]` |
| **Phase 6** | Stage, switch, or rollback isolated mod profiles with lock-file guard and `--dry-run` preview | `gta-anything --json profile <status\|stage\|switch\|rollback> ... [--dry-run]` |
| **Phase 7** | Correlate multi-source logs (`ScriptHookV.log`, `ScriptHookVDotNet.log`, `.jsonl`) & memory telemetry | `gta-anything --json diagnose <log_paths...> [--commit-mb FLOAT]` |

---

## 2. Complete CLI Command Reference (`--json` Examples)

### 2.1 `preflight` — Environment, Dual Build ID & Hotkey Check
```bash
gta-anything --json preflight --hotkey F9 --min-free-gb 10.0 --min-commit-mb 1536.0
```
**Key JSON output fields to inspect**:
- `ok`: `true` if disk, commit memory, process check, and critical checks pass.
- `system.disk_free_gb` / `system.commit_available_mb`: Block heavy testing if `commit_available_mb < 1024`.
- `game.edition`: `"enhanced_gen9"` (`GTA5_Enhanced.exe`) or `"legacy_gen8"` (`GTA5.exe`).
- `game.exe_version` & `game.shv_build_alias`: **Dual Build Identity** (e.g., `1.0.1158.16` on disk vs. `VER_EN_1_0_1158_13` in Script Hook V).
- `hotkey_check.conflicts`: Flags collisions with `F4` (RPH), `Insert` (SHVDN reload), `F3`/`F8` (Trainers), `B`/`N`/`E`/`Y` (LSPDFR / vanilla controls).

### 2.2 `extract` — Evidence-Backed Gameplay IR Extraction
```bash
# Extract from Markdown spec + sibling routes/*.xml
gta-anything --json extract examples/metro_shuttle_loop/spec.md -o /tmp/metro_ir.json --edition enhanced_gen9
```
Produces a `GameplayIR` JSON file containing `meta`, `loader_target`, `inputs`, `ui_spec`, `entities`, `routes_or_zones`, `state_machine`, and `evidence` (with `source_file` and line/XML `locator`).

### 2.3 `validate-ir` — Static Invariant Verification
```bash
gta-anything --json validate-ir examples/metro_shuttle_loop/gameplay_ir.json
```
**Returns**:
```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "checked_invariants": [
    "vanilla_fallback_non_empty",
    "ui_preview_decoupled",
    "state_machine_reachability",
    "cleanup_state_reachable",
    "hotkey_conflict_check",
    "clean_room_license"
  ]
}
```

### 2.4 `transpile` — Clean-Room C# Project Codegen
```bash
gta-anything --json transpile examples/metro_shuttle_loop/gameplay_ir.json -o /tmp/metro_mod_build
```
**Generates**:
- `<ModClassName>.csproj` (with `GTAV_ENHANCED` and `GTAV_LEGACY` conditional compilation and `GtaAnything.Runtime` reference)
- `ModEntrypoint.cs` (wired with `WorldSession`, `OperationalStateMachine`, `SafeModelStreamer`, `DecoupledMenuController`, and `PhasedJsonLogger`)
- `<ModClassName>Config.json`
- `BUILD_AND_VERIFY.md`

### 2.5 `asset-check` — 5-Stage Gen8/Gen9 Asset Auditor
```bash
gta-anything --json asset-check /path/to/addon_assets --edition enhanced_gen9
```
**Checks Gate 1 & Gate 2 statically and emits Gate 3–5 runtime checklist**:
- Verifies RSC7 (`0x37435352`) / RSC8 resource versions: **Gen9 (`enhanced_gen9`)** expects `.yft = 171` and `.ytd = 5` (flags legacy Gen8 `.yft = 162` / `.ytd = 13` as incompatibility errors).
- Scans for `script_rt_*` (especially dashboard render targets like `script_rt_dials_race`): flags `DXT1` or `mipCount > 1` on `enhanced_gen9` and instructs conversion to **single-mip `B8G8R8A8_UNORM`**.
- Validates `dlclist.xml` well-formedness and `dlcpacks:/<name>/` entries.

### 2.6 `profile` — Reversible Profile Isolation (`status`, `stage`, `switch`, `rollback`)
```bash
# Always preview operations with --dry-run first!
gta-anything --json profile status --game-dir "<GAME_DIR>"
gta-anything --json profile stage transit /tmp/metro_mod_build --game-dir "<GAME_DIR>" --loader-chain shvdn --dry-run
gta-anything --json profile switch transit --game-dir "<GAME_DIR>" --dry-run
gta-anything --json profile rollback --game-dir "<GAME_DIR>" --dry-run
```

### 2.7 `diagnose` — Phased Multi-Log & Memory Correlator
```bash
gta-anything --json diagnose ScriptHookV.log ScriptHookVDotNet.log metro_shuttle_loop.telemetry.jsonl --commit-mb 823
```
**Returns**:
- `detected_build_alias` (e.g., `"VER_EN_1_0_1158_13"`)
- `highest_acceptance_layer_reached` (`0` through `7`)
- `issues`: Categorized into `environment`, `loader`, `asset`, or `script_logic`
- `recommendations`: Concrete remediation steps

### 2.8 `pipeline` — One-Shot Offline E2E Pipeline (with Optional `--compile`)
```bash
gta-anything --json pipeline examples/harbor_courier_dispatch/gameplay_ir.json -o /tmp/harbor_build --edition enhanced_gen9
gta-anything --json pipeline examples/external_pizza_rush_src -o /tmp/pizza_build --edition enhanced_gen9 --compile
```
Chains `extract` → `validate-ir` → `transpile` → (optional `build-dll`) → `asset-check` → `simulate` → `visualize` in a single deterministic invocation.

### 2.9 `asset-fix` & `build-dll` (`v0.3.0`)
```bash
# Auto-reencode legacy DXT1/DXT3/DXT5 multi-mip script_rt_* DDS textures to single-mip B8G8R8A8_UNORM and repair dlclist.xml
gta-anything --json asset-fix /path/to/addon_assets -o /tmp/fixed_assets --edition enhanced_gen9 [--dry-run]

# Compile transpiled C# mod into PE .dll assemblies (standalone clean-room or linked against local ScriptHookVDotNet3.dll / RAGEPluginHook.dll)
gta-anything --json build-dll /tmp/pizza_build -o /tmp/pizza_build/bin --edition enhanced_gen9 [--game-dir "<GAME_DIR>"]
```

### 2.10 `host-scan` & `conflict-check --auto-rebind` (`v0.4.0` — MANDATORY before codegen/deploy)
```bash
# Phase 0.5: Scan real host .ini/.xml keybinds (relative paths only), DLL ABI, and Top 5 free chords
gta-anything --json host-scan --game-dir "<GAME_DIR>"

# Phase 2: Run 5-dimension conflict arbitration (keybinds, assemblies_abi, spatial_turf, dlc_and_models, resource_budget)
# Automatically rebinds conflicting hotkeys to a guaranteed conflict-free chord when --auto-rebind is passed:
gta-anything --json conflict-check gameplay_ir.json --game-dir "<GAME_DIR>" --auto-rebind -o gameplay_ir.json

# Or enable --auto-rebind directly inside pipeline:
gta-anything --json pipeline examples/metro_shuttle_loop/spec.md -o /tmp/metro_build --game-dir "<GAME_DIR>" --auto-rebind
```
**Key `conflict-check` JSON fields**:
- `deployment_verdict`: `"SAFE_TO_MERGE"` | `"REBIND_AND_MERGE"` | `"ISOLATE_NEW_PROFILE"` | `"BLOCKED_ENVIRONMENT"`.
- `recommended_rebind`: Top conflict-free `{activation_key, modifier_key, canonical_chord, reason}` selected by `recommend_safe_chords`.
- `dimensions.spatial_turf`: Flags `< 15m` spawn/stop collisions (`SPATIAL_SPAWN_OVERLAP`) against existing route XML/JSON/INI files.
- `dimensions.assemblies_abi`: Flags dual-version DLL collisions (e.g. `LemonUI.SHVDN2.dll` + `LemonUI.SHVDN3.dll`) and `ActiveMode.txt` loader mismatches.

---

## 3. Critical Anti-Patterns & Hard Engineering Rules

When writing, reviewing, or debugging GTA V mods, **NEVER** violate these rules:

1. **NO Live 3D Vehicle Spawning in Menu Callbacks (`preview_mode != "live_3d_spawn"`)**:
   - *Anti-pattern*: Calling `World.CreateVehicle(...)` inside `OnIndexChange` while scrolling a menu. When streaming lags or memory is tight, `CreateVehicle` returns `null`, and immediate property calls (e.g., `RemoveAllExtras()`) crash the script with `NullReferenceException`.
   - *Rule*: Always use `"static_sprite"` or `"static_metadata"` in `ui_spec.preview_mode`. Only stream and spawn entities after the player confirms the shift/mission.
2. **ALWAYS Declare a Vanilla Fallback & Release Timed-Out Models**:
   - *Anti-pattern*: Hardcoding an addon vehicle name without fallback, or leaving a timed-out `Model.Request()` handle dangling in the engine streaming queue.
   - *Rule*: Every `EntitySlot` must specify a valid GTA V vanilla model (`vanilla_fallback_model`, e.g., `bus`, `airbus`, `coach`, `mule`, `benson`). On stream timeout, immediately invoke `Model.MarkAsNoLongerNeeded()` (`SafeModelStreamer.ReleaseTimedOutModel`) before falling back to the vanilla model.
3. **ALWAYS Track Dual Build IDs & Separate Loader Chains**:
   - *Rule*: Record both the executable file version (`1.0.1158.16`) and the Script Hook V enum alias (`VER_EN_1_0_1158_13`). Never mix incompatible heavy RPH (`plugins/`) and SHVDN/ASI (`scripts/` + `OpenRPF.asi`) setups in one dirty folder—isolate them via `gta-anything profile`.
4. **Enforce Gen9 `script_rt_*` `B8G8R8A8_UNORM` Rule**:
   - *Rule*: On **GTA V Enhanced (`enhanced_gen9`)**, `.yft` must target version `171`, `.ytd` must target version `5`, and any `script_rt_*` texture (such as `script_rt_dials_race`) **MUST** use single-mip (`mip=1`) uncompressed `B8G8R8A8_UNORM`. Legacy `DXT1` render-target textures cause silent Gen9 crashes.
5. **Enforce Lease-Based Entity Cleanup (`WorldSession`)**:
   - *Rule*: Never run global world sweeps that delete arbitrary vehicles or peds. Register every spawned vehicle, ped, blip, camera, and prop into `WorldSession`, and guarantee every operational state can transition to `Teardown` (`WorldSession.DisposeAll()`).
6. **Zero Proprietary Binaries & Zero Personal Paths**:
   - *Rule*: Never commit `.dll`, `.asi`, `.rpf`, `.yft`, `.ytd`, or personal machine paths into the repository.
7. **ALWAYS Run `host-scan` & `conflict-check --auto-rebind` Before Generating or Deploying**:
   - *Rule*: Never guess a hotkey or merge into a dirty game folder blindly. Always run `host-scan` and `conflict-check --auto-rebind` to inspect real `.ini` keybinds, DLL ABI, `< 15m` spatial turf, and the `SAFE_TO_MERGE` / `REBIND_AND_MERGE` / `ISOLATE_NEW_PROFILE` verdict before transpiling or staging a profile.

---

## 4. Built-in Templates & Flagship Clean-Room Examples

- **Templates**:
  - [`templates/MOD_SOP.md.template`](templates/MOD_SOP.md.template): Standard 8-Phase execution worksheet for any new mod conversion task.
  - [`templates/TEST.md.template`](templates/TEST.md.template): 7-Layer Acceptance Evidence Ladder (L1–L7) test plan & verification report template.
- **Clean-Room Flagship Examples**:
  - [`../../examples/metro_shuttle_loop/`](../../examples/metro_shuttle_loop/): Urban circular bus transit loop (`bus`/`airbus`, 8 ordered downtown stops in `routes/ls_downtown_loop.xml`, static sprite preview, stop dwell, passenger boarding, fare tally, shift teardown).
  - [`../../examples/harbor_courier_dispatch/`](../../examples/harbor_courier_dispatch/): Port of Los Santos commercial dispatch loop (`mule`/`benson`, on-duty toggle, dispatch callout, inspection zone navigation, NPC coordinator interaction, off-duty teardown).
  - [`../../examples/vinewood_patrol_rph/`](../../examples/vinewood_patrol_rph/): RPH (`loader_target: "rph"`) emergency patrol response across Vinewood Hills & Downtown (`police3`/`fbi2` + `s_m_y_ranger_01`).
  - [`../../examples/external_pizza_rush_src/`](../../examples/external_pizza_rush_src/): Standalone external 2D Python mini-game ("Vespucci Pizza Rush", `0..100` canvas, zero GTA imports) automatically extracted via `polyglot_ast` and projected onto Vespucci street coordinates (`faggio` + `s_m_y_ammucity_01`).
