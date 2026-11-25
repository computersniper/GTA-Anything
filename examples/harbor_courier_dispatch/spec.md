# Port of Los Santos Harbor Courier Dispatch (`harbor_courier_dispatch`) — Gameplay Specification

- **Mod ID**: `harbor_courier_dispatch`
- **Mod Name**: `Port of Los Santos Harbor Courier Dispatch`
- **Version**: `0.1.0`
- **Author**: `GTA-Anything Clean-Room`
- **License**: `MIT`
- **Target Editions**: `enhanced_gen9`, `legacy_gen8`
- **Loader Target**: `shvdn_enhanced`
- **Activation Key**: `LeftControl + F10` (`activation_key: F10`, `modifier_key: LeftControl`)
- **UI Preview Mode**: `static_metadata` (Static cargo manifest & truck class card; zero live 3D vehicle spawning in menu callbacks)

## 1. Operational Gameplay Overview

`harbor_courier_dispatch` demonstrates the **on-duty / off-duty区域调度执勤 (Dispatch Zone)** operational lifecycle in the Port of South Los Santos (Elysian Island & Terminal):
1. **Go On Duty & Select Truck Class (`MenuSelecting`)**: Pressing `LeftControl + F10` opens the harbor logistics dispatch terminal using `static_metadata` cards. The player selects a commercial service truck slot (`freight_box_primary` -> vanilla `mule`, or `heavy_cargo_carrier` -> vanilla `benson`) and goes on duty.
2. **Safe Model Streaming (`ResourceStreaming`)**: `SafeModelStreamer` streams the selected commercial vehicle (`mule` or `benson`) and the dock inspection coordinator NPC (`dock_coordinator_npc` -> vanilla `s_m_m_dockwork_01`). Any timed-out custom model handle is immediately released via `MarkAsNoLongerNeeded()` before falling back to vanilla.
3. **Shift Spawning & Dispatch Callout Assignment (`SpawningShift`)**: The service vehicle is spawned at Elysian Island Logistics Yard (`132.4, -3092.6, 5.9`), verified non-null, registered into `WorldSession`, and the first harbor dispatch callout is assigned.
4. **Drive to Inspection Zone & Interact with NPC Coordinator (`ActiveDispatch`)**:
   - The player drives the service truck through the Port of Los Santos dispatch zones (Elysian Yard -> Pier 400 Customs Inspection Bay -> Terminal Crane Sector -> Naval Supply Gate).
   - At each inspection zone, the player parks inside the bay, holds position for the inspection dwell timer (`8–12 seconds`), interacts with the leased `s_m_m_dockwork_01` coordinator NPC to verify the cargo manifest, and resolves the callout for a `$120` dispatch reward.
5. **Resolve Callout & Go Off Duty with Clean Entity Teardown (`DispatchSummary` -> `Teardown`)**:
   - Completing the dispatch shift or going off duty early transitions to `DispatchSummary` and then `Teardown`, where `WorldSession.DisposeAll()` releases the service truck, dock coordinator NPCs, inspection zone blips, and model handles cleanly.

## 2. Entity Slots (`entities`)

| Slot ID | Role | Vanilla Fallback Model | Preferred Add-on Model | Stream Timeout (ms) | Player Vehicle |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `freight_box_primary` | `player_service_vehicle` | `mule` | `null` | `5000` | `true` |
| `heavy_cargo_carrier` | `player_service_vehicle` | `benson` | `null` | `5000` | `true` |
| `dock_coordinator_npc` | `inspection_coordinator_npc` | `s_m_m_dockwork_01` | `null` | `3000` | `false` |

## 3. Dispatch Zones (`routes_or_zones`)

- **Track ID**: `port_ls_inspection_circuit`
- **Track Name**: `Port of Los Santos Container & Customs Dispatch`
- **Mode**: `dispatch_zones`
- **Reward per Resolved Callout**: `120`
- **Allowed Vehicle Slots**: `freight_box_primary`, `heavy_cargo_carrier`
- **Dispatch & Inspection Zones (4 Zones)**:
  0. `Elysian Island Logistics Staging Yard` (`x=132.4, y=-3092.6, z=5.9, dwell_seconds=8`)
  1. `Pier 400 Customs Inspection Bay` (`x=348.2, y=-2988.4, z=5.9, dwell_seconds=12`)
  2. `Terminal Gantry Crane Transfer Zone` (`x=914.5, y=-2976.1, z=5.9, dwell_seconds=10`)
  3. `South Port Outbound Clearance Gate` (`x=1186.0, y=-3112.8, z=5.8, dwell_seconds=8`)

## 4. Operational State Machine (`state_machine`)

- `Idle` (`standby`) -> `MenuSelecting` (`ui`) on `HotkeyPressed`
- `MenuSelecting` (`ui`) -> `Idle` (`standby`) on `MenuCancelled`
- `MenuSelecting` (`ui`) -> `ResourceStreaming` (`streaming`) on `OnDutyConfirmed`
- `ResourceStreaming` (`streaming`) -> `SpawningShift` (`spawning`) on `ModelReadyOrFallback`
- `ResourceStreaming` (`streaming`) -> `Teardown` (`cleanup`) on `CriticalStreamFailure`
- `SpawningShift` (`spawning`) -> `ActiveDispatch` (`operation`) on `CalloutAssigned`
- `SpawningShift` (`spawning`) -> `Teardown` (`cleanup`) on `SpawnReturnedNull`
- `ActiveDispatch` (`operation`) -> `DispatchSummary` (`completion`) on `CalloutResolved`
- `ActiveDispatch` (`operation`) -> `Teardown` (`cleanup`) on `OffDutyOrVehicleDestroyed`
- `DispatchSummary` (`completion`) -> `Teardown` (`cleanup`) on `SummaryAcknowledged`
- `Teardown` (`cleanup`) -> `Idle` (`standby`) on `ResourcesReleased`
