"""2D grid coordinates (0..100 x 0..100 canvas) and drop-off stops for Vespucci Pizza Rush."""

from __future__ import annotations

CANVAS_WIDTH = 100
CANVAS_HEIGHT = 100
BASE_DELIVERY_REWARD = 35
COUNTDOWN_DWELL_SECONDS = 7

# 5 pizza drop-off shops & apartments on the 2D (0..100 x 0..100) grid canvas
PIZZA_DELIVERY_STOPS = [
    {
        "name": "Capolavoro Wood-Fired Pizzeria Depot",
        "x": 14.0,
        "y": 18.0,
        "dwell_seconds": 6,
        "tip": 35,
    },
    {
        "name": "Palomino Boardwalk Surf Shop",
        "x": 32.5,
        "y": 41.0,
        "dwell_seconds": 7,
        "tip": 40,
    },
    {
        "name": "Magellan Beachfront Loft 3B",
        "x": 58.0,
        "y": 64.5,
        "dwell_seconds": 8,
        "tip": 45,
    },
    {
        "name": "Bay City Marina Courtyard Apartments",
        "x": 79.0,
        "y": 82.0,
        "dwell_seconds": 7,
        "tip": 50,
    },
    {
        "name": "Aguja Canal Terrace Penthouse",
        "x": 46.0,
        "y": 29.5,
        "dwell_seconds": 6,
        "tip": 55,
    },
]
