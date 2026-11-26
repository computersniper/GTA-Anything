# Vinewood Hills Patrol & Incident Response (`vinewood_patrol_rph`) — Gameplay Specification

- **Mod ID**: `vinewood_patrol_rph`
- **Mod Name**: `Vinewood Hills Patrol & Incident Response (RPH)`
- **Version**: `0.2.0`
- **Author**: `GTA-Anything Clean-Room`
- **License**: `MIT`
- **Target Editions**: `enhanced_gen9`, `legacy_gen8`
- **Loader Target**: `rph`
- **Activation Key**: `LeftControl + F10` (`activation_key: F10`, `modifier_key: LeftControl`)
- **UI Preview Mode**: `static_sprite` (2D static unit card preview; zero live 3D vehicle spawning in menu callbacks)

## 1. Operational Gameplay Overview

`vinewood_patrol_rph` is Flagship Clean-Room Example #3 demonstrating the **RAGE Plugin Hook (`loader_target: "rph"`)** dual-loader backend with a complete **Vinewood Hills & Downtown Patrol / Incident Response (`dispatch_zones`)** lifecycle:
1. **Patrol Shift Selection (`MenuSelecting`)**: Pressing `LeftControl + F10` opens the Vinewood Patrol dispatch menu using `static_sprite` 2D SVG unit cards (zero `CreateVehicle` calls during menu navigation). The player selects a patrol unit (`patrol_interceptor_primary` -> vanilla `police3`, or `tactical_response_suv` -> vanilla `fbi2`) and confirms the patrol shift.
2. **Safe Model Streaming (`ResourceStreaming`)**: `SafeModelStreamer` requests the chosen patrol vehicle (`police3` or `fbi2`) and the incident coordinator NPC (`ranger_field_liaison` -> vanilla `s_m_y_ranger_01`) with bounded timeout release (`MarkAsNoLongerNeeded()` on timeout before vanilla fallback).
3. **Shift Spawning & Unit Staging (`SpawningShift`)**: Spawns the patrol vehicle at the Vinewood Hills Observatory Overlook staging point (`-412.5, 1172.4, 325.8`), validates non-null handle, registers the lease in `WorldSession`, and seats the player.
4. **Vinewood & Downtown Patrol Loop (`ActivePatrol`)**:
   - The player patrols 4 incident response zones spanning Vinewood Hills and Downtown Los Santos (Observatory Overlook -> Vinewood Sign Ridge -> Vinewood Boulevard Precinct -> Mission Row Downtown Hub).
   - At each zone, the player holds position for the incident check-in dwell timer (`8–12 seconds`), coordinates with the leased `s_m_y_ranger_01` liaison NPC, and clears the incident for a `$150` patrol response stipend.
5. **Shift Summary & Deterministic RPH `OnUnload` Teardown (`ShiftSummary` -> `Teardown`)**:
   - Completing all 4 zones or triggering an early abort transitions cleanly to `ShiftSummary` -> `Teardown`, where `WorldSession.DisposeAll()` releases all leased patrol vehicles, liaison NPCs, blips, and model handles (and hooks RPH `OnUnload` for zero-leak cleanup).

## 2. Entity Slots (`entities`)

| Slot ID | Role | Vanilla Fallback Model | Preferred Add-on Model | Stream Timeout (ms) | Player Vehicle |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `patrol_interceptor_primary` | `player_service_vehicle` | `police3` | `null` | `5000` | `true` |
| `tactical_response_suv` | `player_service_vehicle` | `fbi2` | `null` | `5000` | `true` |
| `ranger_field_liaison` | `incident_coordinator_npc` | `s_m_y_ranger_01` | `null` | `3000` | `false` |

## 3. Patrol & Incident Response Zones (`routes_or_zones`)

- **Track ID**: `vinewood_downtown_patrol`
- **Track Name**: `Vinewood Hills & Downtown Incident Response Circuit`
- **Mode**: `dispatch_zones`
- **Stipend per Cleared Zone**: `150`
- **Allowed Vehicle Slots**: `patrol_interceptor_primary`, `tactical_response_suv`
- **Patrol & Incident Response Zones (4 Zones)**:
  0. `Vinewood Hills Observatory Overlook` (`x=-412.5, y=1172.4, z=325.8, dwell_seconds=10`)
  1. `Vinewood Sign Ridge Checkpoint` (`x=732.1, y=1285.6, z=360.3, dwell_seconds=8`)
  2. `Vinewood Boulevard Precinct Staging` (`x=618.4, y=12.8, z=82.8, dwell_seconds=12`)
  3. `Mission Row Downtown Response Hub` (`x=428.9, y=-981.2, z=30.7, dwell_seconds=10`)

## 4. Operational State Machine (`state_machine`)

- `Idle` (`standby`) -> `MenuSelecting` (`ui`) on `HotkeyPressed`
- `MenuSelecting` (`ui`) -> `Idle` (`standby`) on `MenuCancelled`
- `MenuSelecting` (`ui`) -> `ResourceStreaming` (`streaming`) on `ShiftConfirmed`
- `ResourceStreaming` (`streaming`) -> `SpawningShift` (`spawning`) on `ModelReadyOrFallback`
- `ResourceStreaming` (`streaming`) -> `Teardown` (`cleanup`) on `CriticalStreamFailure`
- `SpawningShift` (`spawning`) -> `ActivePatrol` (`operation`) on `UnitStagedAndSeated`
- `SpawningShift` (`spawning`) -> `Teardown` (`cleanup`) on `SpawnReturnedNull`
- `ActivePatrol` (`operation`) -> `ShiftSummary` (`completion`) on `PatrolCircuitCompleted`
- `ActivePatrol` (`operation`) -> `Teardown` (`cleanup`) on `ShiftAbortedOrVehicleDestroyed`
- `ShiftSummary` (`completion`) -> `Teardown` (`cleanup`) on `SummaryAcknowledged`
- `Teardown` (`cleanup`) -> `Idle` (`standby`) on `ResourcesReleased`
