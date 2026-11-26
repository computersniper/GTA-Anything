# Vespucci Pizza Rush (2D Grid Scooter Delivery Mini-Game)

Vespucci Pizza Rush is a standalone 2D top-down arcade pizza delivery mini-game operating on a `100 x 100` coastal neighborhood grid canvas. Players ride an agile thermal-box pizza delivery scooter between canal-side pizzerias, boardwalk shops, and beachfront apartments before the hot-bag countdown timer expires.

## Core Mechanics

- **2D Grid Canvas**: `0..100 x 0..100` abstract neighborhood coordinates (`z` is unused/2D).
- **State Machine**: Managed via `DeliveryState(Enum)` in `game_state.py`.
- **Entities**: Player delivery scooter (`pizza_delivery_scooter`) and hungry apartment customers (`hungry_pizza_customer`) in `entities.py`.
- **5 Ordered Drop-off Stops**: Defined in `delivery_map.py` with base tip rewards and countdown dwell timers.
