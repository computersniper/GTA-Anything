"""Entity definitions for the 2D pizza delivery scooter and hungry neighborhood customers."""

from __future__ import annotations

from dataclasses import dataclass


PLAYER_DELIVERY_SCOOTER = {
    "id": "pizza_delivery_scooter",
    "name": "Vespucci Thermal-Box Moped Scooter",
    "type": "pizza_scooter_bike",
    "role": "player_service_vehicle",
    "top_speed_grid_units": 18.5,
    "thermal_bag_capacity": 5,
}

HUNGRY_CUSTOMER_NPC = {
    "id": "hungry_pizza_customer",
    "name": "Hungry Beachfront Apartment Customer",
    "type": "hungry_customer_npc",
    "role": "customer_recipient_npc",
    "patience_seconds": 45,
    "tip_multiplier": 1.25,
}


@dataclass
class ScooterCourierEntity:
    """2D arcade representation of the player's pizza delivery moped scooter."""

    slot_id: str = "pizza_delivery_scooter"
    vehicle_category: str = "scooter_pizza_bike"
    grid_x: float = 14.0
    grid_y: float = 18.0
    pizzas_loaded: int = 5


@dataclass
class HungryCustomerEntity:
    """2D arcade representation of a customer waiting at an apartment drop-off point."""

    slot_id: str = "hungry_pizza_customer"
    npc_archetype: str = "customer_hungry_resident"
    grid_x: float = 32.5
    grid_y: float = 41.0
    order_slices: int = 8
