"""Static 2D GTA street-styled SVG menu preview card generator.

Enforces the UI-Spawn Decoupling invariant by rendering deterministic 2D SVG preview cards
(`<output_dir>/cards/<track_id>_card.svg`) instead of spawning live 3D vehicles during
menu scrolling.
"""

from __future__ import annotations

from pathlib import Path
import re
from xml.sax.saxutils import escape as xml_escape

from gta_anything.models.ir import GameplayIR, SpatialTrack


def _safe_filename(track_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", track_id.strip())
    return cleaned or "track"


def _resolve_fallback_vehicle(ir: GameplayIR, track: SpatialTrack) -> tuple[str, str | None]:
    """Resolve the vanilla fallback vehicle model (and optional preferred addon) for a track."""
    slot_map = {ent.slot_id: ent for ent in ir.entities}
    for slot_id in track.allowed_vehicle_slots:
        ent = slot_map.get(slot_id)
        if ent is not None:
            return ent.vanilla_fallback_model, ent.preferred_addon_model

    for ent in ir.entities:
        if ent.is_player_vehicle:
            return ent.vanilla_fallback_model, ent.preferred_addon_model

    if ir.entities:
        return ir.entities[0].vanilla_fallback_model, ir.entities[0].preferred_addon_model
    return "bus", None


def _render_mini_radar(track: SpatialTrack) -> str:
    """Render a normalized 2D SVG polyline preview of the track stops inside (292..456, 76..218)."""
    box_x, box_y, box_w, box_h = 292.0, 76.0, 164.0, 142.0
    pad = 18.0
    inner_w = box_w - 2 * pad
    inner_h = box_h - 2 * pad

    parts: list[str] = [
        f'  <rect x="{box_x:.0f}" y="{box_y:.0f}" width="{box_w:.0f}" height="{box_h:.0f}" '
        'rx="8" fill="#0d131d" stroke="#223047" stroke-width="1.5" />',
        # Subtle radar grid lines
        f'  <line x1="{box_x + box_w / 2:.1f}" y1="{box_y:.1f}" x2="{box_x + box_w / 2:.1f}" '
        f'y2="{box_y + box_h:.1f}" stroke="#172233" stroke-width="1" stroke-dasharray="3,3" />',
        f'  <line x1="{box_x:.1f}" y1="{box_y + box_h / 2:.1f}" x2="{box_x + box_w:.1f}" '
        f'y2="{box_y + box_h / 2:.1f}" stroke="#172233" stroke-width="1" stroke-dasharray="3,3" />',
        f'  <text x="{box_x + 8:.0f}" y="{box_y + 15:.0f}" fill="#64748b" font-family="Segoe UI, Arial, sans-serif" '
        'font-size="9" font-weight="700" letter-spacing="1">RADAR PREVIEW</text>',
    ]

    stops = track.stops
    if not stops:
        parts.append(
            f'  <text x="{box_x + box_w / 2:.1f}" y="{box_y + box_h / 2 + 4:.1f}" '
            'text-anchor="middle" fill="#64748b" font-family="Segoe UI, Arial, sans-serif" '
            'font-size="11">NO WAYPOINTS</text>'
        )
        return "\n".join(parts)

    xs = [float(s.x) for s in stops]
    ys = [float(s.y) for s in stops]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y

    coords: list[tuple[float, float]] = []
    for s in stops:
        nx = 0.5 if span_x < 1e-6 else (float(s.x) - min_x) / span_x
        # Invert Y because GTA +Y is North whereas SVG +Y is South
        ny = 0.5 if span_y < 1e-6 else 1.0 - ((float(s.y) - min_y) / span_y)
        px = box_x + pad + nx * inner_w
        py = box_y + pad + 8.0 + ny * (inner_h - 8.0)
        coords.append((px, py))

    if len(coords) >= 2:
        pts_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in coords)
        stroke_color = "#38bdf8" if track.mode == "ordered_stops" else "#d4af37"
        parts.append(
            f'  <polyline points="{pts_str}" fill="none" stroke="{stroke_color}" '
            'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.9" />'
        )

    for idx, (px, py) in enumerate(coords):
        if idx == 0:
            fill = "#2e8b57"
            r = 5.0
        elif idx == len(coords) - 1:
            fill = "#d4af37"
            r = 5.0
        else:
            fill = "#38bdf8"
            r = 3.6
        parts.append(
            f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" fill="{fill}" '
            'stroke="#0b0e14" stroke-width="1.2" />'
        )

    parts.append(
        f'  <text x="{box_x + box_w - 8:.0f}" y="{box_y + box_h - 6:.0f}" text-anchor="end" '
        'fill="#64748b" font-family="Consolas, monospace" font-size="8.5">'
        f'X[{min_x:.0f}..{max_x:.0f}]</text>'
    )
    return "\n".join(parts)


def _render_card_svg(ir: GameplayIR, track: SpatialTrack) -> str:
    vanilla_veh, addon_veh = _resolve_fallback_vehicle(ir, track)
    title = xml_escape(track.name)
    mod_name = xml_escape(ir.meta.name)
    track_id_esc = xml_escape(track.track_id)
    mode_label = xml_escape(track.mode.replace("_", " ").upper())
    loader_badge = xml_escape(ir.loader_target.upper())
    veh_badge = xml_escape(vanilla_veh.upper())
    addon_text = xml_escape(addon_veh) if addon_veh else "VANILLA-FIRST"
    accent = "#2e8b57" if track.mode == "ordered_stops" else "#d4af37"
    radar_svg = _render_mini_radar(track)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 270" width="480" height="270" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0b0e14" />
      <stop offset="100%" stop-color="#141b29" />
    </linearGradient>
    <linearGradient id="accentBar" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{accent}" />
      <stop offset="100%" stop-color="#d4af37" />
    </linearGradient>
  </defs>

  <!-- Card Frame -->
  <rect x="2" y="2" width="476" height="266" rx="12" fill="url(#bgGrad)" stroke="#2a364c" stroke-width="2" />
  <rect x="2" y="2" width="476" height="6" rx="3" fill="url(#accentBar)" />

  <!-- Top Header Strip -->
  <text x="20" y="32" fill="#94a3b8" font-family="Segoe UI, Arial, sans-serif" font-size="10" font-weight="700" letter-spacing="1.4">{mod_name}</text>
  <rect x="366" y="17" width="94" height="20" rx="4" fill="#182234" stroke="#d4af37" stroke-width="1" />
  <text x="413" y="30" text-anchor="middle" fill="#d4af37" font-family="Consolas, monospace" font-size="9.5" font-weight="700">{loader_badge}</text>

  <!-- Track Title -->
  <text x="20" y="58" fill="#f8fafc" font-family="Segoe UI, Arial, sans-serif" font-size="17" font-weight="800">{title}</text>

  <!-- Left Metadata Panel -->
  <rect x="20" y="76" width="256" height="142" rx="8" fill="#101724" stroke="#1e293b" stroke-width="1.2" />

  <!-- Mode Badge -->
  <rect x="32" y="88" width="124" height="22" rx="4" fill="{accent}" fill-opacity="0.18" stroke="{accent}" stroke-width="1" />
  <text x="94" y="102" text-anchor="middle" fill="#e2e8f0" font-family="Segoe UI, Arial, sans-serif" font-size="9.5" font-weight="700" letter-spacing="0.8">{mode_label}</text>

  <!-- Stop Count & Fare/Reward -->
  <text x="32" y="132" fill="#94a3b8" font-family="Segoe UI, Arial, sans-serif" font-size="10" font-weight="600">WAYPOINTS / ZONES</text>
  <text x="32" y="152" fill="#f8fafc" font-family="Consolas, monospace" font-size="18" font-weight="700">{len(track.stops)}</text>

  <text x="150" y="132" fill="#94a3b8" font-family="Segoe UI, Arial, sans-serif" font-size="10" font-weight="600">FARE / REWARD</text>
  <text x="150" y="152" fill="#d4af37" font-family="Consolas, monospace" font-size="18" font-weight="700">${int(track.fare_or_reward)}</text>

  <!-- Vanilla Fallback Vehicle Badge -->
  <text x="32" y="177" fill="#94a3b8" font-family="Segoe UI, Arial, sans-serif" font-size="9.5" font-weight="600">VANILLA FALLBACK VEHICLE</text>
  <rect x="32" y="185" width="110" height="22" rx="4" fill="#1e293b" stroke="#38bdf8" stroke-width="1" />
  <text x="87" y="199" text-anchor="middle" fill="#38bdf8" font-family="Consolas, monospace" font-size="10.5" font-weight="700">{veh_badge}</text>
  <text x="150" y="199" fill="#64748b" font-family="Consolas, monospace" font-size="9">OPT: {addon_text}</text>

  <!-- Right Mini Radar Map -->
{radar_svg}

  <!-- Bottom Safety Invariant Footer -->
  <line x1="20" y1="232" x2="460" y2="232" stroke="#1e293b" stroke-width="1" />
  <text x="20" y="250" fill="#2e8b57" font-family="Consolas, monospace" font-size="9.5" font-weight="700">STATIC 2D PREVIEW · ZERO 3D SPAWN</text>
  <text x="460" y="250" text-anchor="end" fill="#64748b" font-family="Consolas, monospace" font-size="9">ID: {track_id_esc}</text>
</svg>
"""


def generate_static_menu_cards(ir: GameplayIR | dict, output_dir: str | Path) -> list[str]:
    """Generate GTA street-styled 2D SVG menu preview cards for every track in `ir.routes_or_zones`.

    Writes `<output_dir>/cards/<track_id>_card.svg` and returns the list of generated file paths.
    """
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    cards_dir = Path(output_dir) / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    generated: list[str] = []
    for track in ir_obj.routes_or_zones:
        card_filename = f"{_safe_filename(track.track_id)}_card.svg"
        card_path = cards_dir / card_filename
        card_path.write_text(_render_card_svg(ir_obj, track), encoding="utf-8")
        generated.append(str(card_path))

    return generated
