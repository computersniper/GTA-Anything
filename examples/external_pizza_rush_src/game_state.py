"""Finite state machine and shift progression logic for the 2D Vespucci Pizza Rush mini-game."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


GAME_TITLE = "Vespucci Pizza Rush"
ACTIVATION_KEY = "F9"
NEIGHBORHOOD_DISTRICT = "vespucci"
BASE_TIP_REWARD = 35
DEFAULT_DWELL_SECONDS = 7


class DeliveryState(Enum):
    """Core operational states for a pizza scooter delivery shift."""

    STANDBY_KITCHEN = "standby_kitchen"
    SELECTING_ORDER_BATCH = "selecting_order_batch"
    WARMING_OVEN_AND_SCOOTER = "warming_oven_and_scooter"
    MOUNTING_SCOOTER = "mounting_scooter"
    RUSHING_DELIVERY_ROUTE = "rushing_delivery_route"
    TALLYING_TIPS = "tallying_tips"
    CLOSING_SHIFT = "closing_shift"


@dataclass
class PizzaShiftSession:
    """Tracks current state, completed stops, and accumulated tips on the 2D grid."""

    state: DeliveryState = DeliveryState.STANDBY_KITCHEN
    current_stop_index: int = 0
    total_tips_earned: int = 0
    remaining_dwell_seconds: int = DEFAULT_DWELL_SECONDS
    completed_stops: list[str] = field(default_factory=list)

    def start_shift_selection(self) -> DeliveryState:
        if self.state == DeliveryState.STANDBY_KITCHEN:
            self.state = DeliveryState.SELECTING_ORDER_BATCH
        return self.state

    def confirm_route_and_spawn(self) -> DeliveryState:
        self.state = DeliveryState.WARMING_OVEN_AND_SCOOTER
        self.state = DeliveryState.MOUNTING_SCOOTER
        self.state = DeliveryState.RUSHING_DELIVERY_ROUTE
        return self.state

    def advance_delivery_stop(self, stop_name: str, tip_bonus: int = BASE_TIP_REWARD) -> DeliveryState:
        self.completed_stops.append(stop_name)
        self.total_tips_earned += tip_bonus
        self.current_stop_index += 1
        return self.state

    def complete_shift_summary(self) -> DeliveryState:
        self.state = DeliveryState.TALLYING_TIPS
        return self.state

    def abort_or_teardown_shift(self) -> DeliveryState:
        self.state = DeliveryState.CLOSING_SHIFT
        return self.state
