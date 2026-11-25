# Los Santos Metro Shuttle Loop (`metro_shuttle_loop`) — Gameplay Specification

- **Mod ID**: `metro_shuttle_loop`
- **Mod Name**: `Los Santos Metro Shuttle Loop`
- **Version**: `0.1.0`
- **Author**: `GTA-Anything Clean-Room`
- **License**: `MIT`
- **Target Editions**: `enhanced_gen9`, `legacy_gen8`
- **Loader Target**: `shvdn_enhanced`
- **Activation Key**: `LeftShift + F9` (`activation_key: F9`, `modifier_key: LeftShift`)
- **UI Preview Mode**: `static_sprite` (2D route map and vehicle spec card only; zero live 3D vehicle spawning in menu callbacks)

## 1. Operational Gameplay Overview

`metro_shuttle_loop` implements a full urban public-transit operational lifecycle in Los Santos rather than a single-step vehicle spawner:
1. **Route & Vehicle Selection (`MenuSelecting`)**: Pressing `LeftShift + F9` opens a static dispatch menu displaying the circular route (`routes/ls_downtown_loop.xml`, 8 ordered stops, $15 base fare) and available vehicle slots using `static_sprite` preview cards.
2. **Model Streaming with Vanilla Fallback (`ResourceStreaming`)**: Confirming the shift triggers `SafeModelStreamer` to request the selected service vehicle (`transit_coach_primary` -> vanilla fallback `bus`, or `airport_shuttle_express` -> vanilla fallback `airbus`) and commuter passenger ped (`commuter_passenger` -> vanilla fallback `a_m_y_business_01`). Any timed-out addon model is immediately released via `MarkAsNoLongerNeeded()` before falling back to vanilla.
3. **Shift Spawning & Lease Registration (`SpawningShift`)**: The service bus is spawned at Dashound Bus Center Terminal (`436.2, -645.8, 28.7`), verified non-null, registered into `WorldSession`, and the player is seated in the driver seat.
4. **Ordered Stop Dwell & Passenger Boarding (`ActiveRoute`)**:
   - The system sets the active waypoint/blip to the current stop in the 8-stop circular route (`index 0` through `index 7`).
   - When the player stops within the stop zone (`speed < 0.5 m/s`), the doors open, the stop dwell timer (`6–10 seconds`) counts down, leased commuter NPCs board/alight via vehicle doors, and the fare (`$15` per boarding passenger) is added to the shift ledger.
5. **Shift Summary & Clean Teardown (`ShiftSummary` -> `Teardown`)**:
   - Completing Stop 7 displays the total passengers carried, punctuality bonus, and total fare revenue.
   - Acknowledging the summary—or aborting the shift / destroying the bus at any intermediate stage—transitions deterministically to `Teardown`, where `WorldSession.DisposeAll()` releases all leased vehicles, commuter peds, route blips, and model handles.

## 2. Entity Slots (`entities`)

| Slot ID | Role | Vanilla Fallback Model | Preferred Add-on Model | Stream Timeout (ms) | Player Vehicle |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `transit_coach_primary` | `player_service_vehicle` | `bus` | `null` | `5000` | `true` |
| `airport_shuttle_express` | `player_service_vehicle` | `airbus` | `null` | `5000` | `true` |
| `commuter_passenger` | `boarding_npc` | `a_m_y_business_01` | `null` | `3000` | `false` |

## 3. Ordered Route Definition (`routes/ls_downtown_loop.xml`)

- **Track ID**: `ls_downtown_loop`
- **Track Name**: `Route 10 Downtown Circular Shuttle`
- **Mode**: `ordered_stops`
- **Fare per Boarding Passenger**: `15`
- **Allowed Vehicle Slots**: `transit_coach_primary`, `airport_shuttle_express`
- **Ordered Stops (8 Stops)**:
  0. `Dashound Bus Center Terminal` (`x=436.2, y=-645.8, z=28.7, dwell_seconds=8`)
  1. `Mission Row Textile Station` (`x=411.5, y=-806.4, z=29.3, dwell_seconds=6`)
  2. `Legion Square North Plaza` (`x=215.4, y=-810.1, z=30.7, dwell_seconds=10`)
  3. `Pillbox Hill Medical Center` (`x=298.7, y=-584.2, z=43.2, dwell_seconds=8`)
  4. `Alta Street Metro Hub` (`x=238.1, y=-396.5, z=45.3, dwell_seconds=7`)
  5. `Vinewood Boulevard West` (`x=118.4, y=-210.8, z=54.6, dwell_seconds=6`)
  6. `Rockford Hills Civic Center` (`x=-142.3, y=-382.9, z=38.1, dwell_seconds=8`)
  7. `Little Seoul Transit Return` (`x=-305.6, y=-698.4, z=32.8, dwell_seconds=7`)

## 4. Operational State Machine (`state_machine`)

- `Idle` (`standby`) -> `MenuSelecting` (`ui`) on `HotkeyPressed`
- `MenuSelecting` (`ui`) -> `Idle` (`standby`) on `MenuCancelled`
- `MenuSelecting` (`ui`) -> `ResourceStreaming` (`streaming`) on `ShiftConfirmed`
- `ResourceStreaming` (`streaming`) -> `SpawningShift` (`spawning`) on `ModelReadyOrFallback`
- `ResourceStreaming` (`streaming`) -> `Teardown` (`cleanup`) on `CriticalStreamFailure`
- `SpawningShift` (`spawning`) -> `ActiveRoute` (`operation`) on `DriverSeated`
- `SpawningShift` (`spawning`) -> `Teardown` (`cleanup`) on `SpawnReturnedNull`
- `ActiveRoute` (`operation`) -> `ShiftSummary` (`completion`) on `FinalStopCompleted`
- `ActiveRoute` (`operation`) -> `Teardown` (`cleanup`) on `ShiftAbortedOrVehicleDestroyed`
- `ShiftSummary` (`completion`) -> `Teardown` (`cleanup`) on `SummaryAcknowledged`
- `Teardown` (`cleanup`) -> `Idle` (`standby`) on `ResourcesReleased`
