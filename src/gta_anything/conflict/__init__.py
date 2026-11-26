"""5-Dimension Multi-Mod Conflict & Keybind Governance Engine (`gta_anything.conflict`)."""

from __future__ import annotations

from typing import Any

from gta_anything.conflict.keybind_scanner import (
    BASELINE_KEYBIND_KNOWLEDGE_BASE,
    evaluate_keybind_conflicts,
    normalize_chord,
    normalize_key_name,
    recommend_safe_chords,
    scan_installed_keybinds,
)

try:
    from gta_anything.conflict.arbitrator import (
        analyze_mod_conflicts,
        inspect_assembly_abi_conflicts,
        inspect_dlc_and_model_collisions,
        inspect_spatial_turf_overlaps,
    )
except Exception:  # pragma: no cover

    def analyze_mod_conflicts(*args: Any, **kwargs: Any) -> dict[str, Any]:
        from gta_anything.conflict.arbitrator import analyze_mod_conflicts as _fn

        return _fn(*args, **kwargs)

    def inspect_assembly_abi_conflicts(*args: Any, **kwargs: Any) -> dict[str, Any]:
        from gta_anything.conflict.arbitrator import inspect_assembly_abi_conflicts as _fn

        return _fn(*args, **kwargs)

    def inspect_spatial_turf_overlaps(*args: Any, **kwargs: Any) -> dict[str, Any]:
        from gta_anything.conflict.arbitrator import inspect_spatial_turf_overlaps as _fn

        return _fn(*args, **kwargs)

    def inspect_dlc_and_model_collisions(*args: Any, **kwargs: Any) -> dict[str, Any]:
        from gta_anything.conflict.arbitrator import inspect_dlc_and_model_collisions as _fn

        return _fn(*args, **kwargs)


__all__ = [
    "BASELINE_KEYBIND_KNOWLEDGE_BASE",
    "normalize_key_name",
    "normalize_chord",
    "scan_installed_keybinds",
    "evaluate_keybind_conflicts",
    "recommend_safe_chords",
    "inspect_assembly_abi_conflicts",
    "inspect_spatial_turf_overlaps",
    "inspect_dlc_and_model_collisions",
    "analyze_mod_conflicts",
]
