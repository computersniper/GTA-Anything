"""Evidence-backed Gameplay IR extractor package."""

from gta_anything.extractor.analyzer import extract_gameplay_ir
from gta_anything.extractor.polyglot_ast import (
    LOS_SANTOS_CORRIDORS,
    extract_polyglot_repo_ir,
    is_abstract_or_2d_coordinate_space,
    project_coords_to_los_santos,
)

__all__ = [
    "LOS_SANTOS_CORRIDORS",
    "extract_gameplay_ir",
    "extract_polyglot_repo_ir",
    "is_abstract_or_2d_coordinate_space",
    "project_coords_to_los_santos",
]
