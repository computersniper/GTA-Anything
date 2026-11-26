"""Standalone offline Los Santos Street Radar & Gameplay IR Blueprint Dashboard generator.

Produces a 100% self-contained HTML file (inline CSS + inline SVG + inline JS, zero external CDNs)
featuring:
- GTA dark-radar styling (#0b0e14 background, #d4af37 gold, #2e8b57 GTA green, #00e5ff cyan).
- Interactive 2D SVG Los Santos radar map with track filtering and stop hover tooltips.
- Visual State-Machine diagram & phase cards highlighting initial_state, operational states, and Teardown paths.
- Entity Slots table (preferred addon, vanilla_fallback_model, stream timeout) and EvidenceAnchor traceability table.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

from gta_anything.models.ir import GameplayIR


_TRACK_COLORS = [
    "#00e5ff",  # cyan
    "#d4af37",  # gold
    "#2ecc71",  # emerald
    "#ff6b6b",  # coral
    "#b388ff",  # violet
    "#ffab40",  # amber
]


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _safe_json_for_script(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def _phase_badge_class(state_name: str, phase: str, initial: str, cleanup: str) -> str:
    if state_name == initial:
        return "badge-initial"
    if state_name == cleanup or phase == "cleanup":
        return "badge-teardown"
    if phase in {"operation", "completion"}:
        return "badge-op"
    if phase in {"streaming", "spawning"}:
        return "badge-stream"
    return "badge-ui"


def _compute_radar_geometry(ir: GameplayIR, width: int = 820, height: int = 480, pad: int = 56) -> dict[str, Any]:
    all_stops = [s for t in ir.routes_or_zones for s in t.stops]
    if not all_stops:
        return {
            "width": width,
            "height": height,
            "pad": pad,
            "min_x": -1000.0,
            "max_x": 1000.0,
            "min_y": -1000.0,
            "max_y": 1000.0,
            "tracks": [],
        }

    xs = [s.x for s in all_stops]
    ys = [s.y for s in all_stops]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span_x = max(max_x - min_x, 120.0)
    span_y = max(max_y - min_y, 120.0)

    # Add 12% margin around bounding box
    margin_x = span_x * 0.12
    margin_y = span_y * 0.12
    min_x -= margin_x
    max_x += margin_x
    min_y -= margin_y
    max_y += margin_y

    usable_w = width - 2 * pad
    usable_h = height - 2 * pad
    scale = min(usable_w / (max_x - min_x), usable_h / (max_y - min_y))

    content_w = (max_x - min_x) * scale
    content_h = (max_y - min_y) * scale
    offset_x = pad + (usable_w - content_w) / 2.0
    offset_y = pad + (usable_h - content_h) / 2.0

    def project(x: float, y: float) -> tuple[float, float]:
        sx = offset_x + (x - min_x) * scale
        # GTA +Y is North (upward), SVG +Y is downward
        sy = offset_y + (max_y - y) * scale
        return round(sx, 2), round(sy, 2)

    tracks_geo: list[dict[str, Any]] = []
    for idx, track in enumerate(ir.routes_or_zones):
        color = _TRACK_COLORS[idx % len(_TRACK_COLORS)]
        ordered_stops = sorted(track.stops, key=lambda s: s.index)
        pts: list[dict[str, Any]] = []
        total_dist = 0.0
        prev = None
        for st in ordered_stops:
            if prev is not None:
                total_dist += math.sqrt(
                    (st.x - prev.x) ** 2 + (st.y - prev.y) ** 2 + (st.z - prev.z) ** 2
                )
            sx, sy = project(st.x, st.y)
            pts.append(
                {
                    "index": st.index,
                    "name": st.name,
                    "x": st.x,
                    "y": st.y,
                    "z": st.z,
                    "sx": sx,
                    "sy": sy,
                    "dwell_seconds": st.dwell_seconds,
                    "fare_or_reward": track.fare_or_reward,
                    "track_id": track.track_id,
                    "track_name": track.name,
                    "mode": track.mode,
                }
            )
            prev = st
        tracks_geo.append(
            {
                "track_id": track.track_id,
                "name": track.name,
                "mode": track.mode,
                "color": color,
                "fare_or_reward": track.fare_or_reward,
                "total_distance_m": round(total_dist, 1),
                "stops": pts,
            }
        )

    return {
        "width": width,
        "height": height,
        "pad": pad,
        "min_x": round(min_x, 1),
        "max_x": round(max_x, 1),
        "min_y": round(min_y, 1),
        "max_y": round(max_y, 1),
        "tracks": tracks_geo,
    }


def _build_radar_svg(geo: dict[str, Any]) -> str:
    w = geo["width"]
    h = geo["height"]
    parts: list[str] = [
        f'<svg id="radar-svg" viewBox="0 0 {w} {h}" width="100%" height="100%" role="img" aria-label="Los Santos Radar Map">',
        "<defs>",
        '<radialGradient id="radarGlow" cx="50%" cy="50%" r="60%">',
        '<stop offset="0%" stop-color="#162235" stop-opacity="0.95"/>',
        '<stop offset="100%" stop-color="#0b0e14" stop-opacity="1"/>',
        "</radialGradient>",
        '<pattern id="radarGrid" width="40" height="40" patternUnits="userSpaceOnUse">',
        '<path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1b2636" stroke-width="1"/>',
        "</pattern>",
        '<marker id="arrowCyan" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        '<path d="M 0 1 L 10 5 L 0 9 z" fill="#00e5ff"/>',
        "</marker>",
        "</defs>",
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="url(#radarGlow)" rx="10"/>',
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="url(#radarGrid)" rx="10"/>',
        # Radar concentric range rings
        f'<circle cx="{w // 2}" cy="{h // 2}" r="110" fill="none" stroke="#1f3147" stroke-dasharray="4 6" stroke-width="1"/>',
        f'<circle cx="{w // 2}" cy="{h // 2}" r="210" fill="none" stroke="#1f3147" stroke-dasharray="4 6" stroke-width="1"/>',
        # Compass indicator
        f'<g transform="translate({w - 46}, 36)">',
        '<circle cx="0" cy="0" r="18" fill="#0b0e14" stroke="#d4af37" stroke-width="1.5"/>',
        '<polygon points="0,-13 4,-3 -4,-3" fill="#d4af37"/>',
        '<text x="0" y="9" text-anchor="middle" fill="#d4af37" font-size="11" font-weight="700" font-family="monospace">N</text>',
        "</g>",
        # Coordinate bounds legend
        f'<text x="14" y="{h - 12}" fill="#6e829e" font-size="10" font-family="monospace">'
        f'X: [{geo["min_x"]}, {geo["max_x"]}] | Y: [{geo["min_y"]}, {geo["max_y"]}] (Los Santos World Coords)</text>',
    ]

    if not geo["tracks"]:
        parts.append(
            f'<text x="{w // 2}" y="{h // 2}" text-anchor="middle" fill="#8b9bb4" font-size="14">'
            "No spatial tracks or stops defined in Gameplay IR.</text>"
        )
    else:
        for tr in geo["tracks"]:
            tid = _esc(tr["track_id"])
            color = _esc(tr["color"])
            stops = tr["stops"]
            parts.append(f'<g class="radar-track" data-track-id="{tid}">')
            if len(stops) >= 2 and tr["mode"] == "ordered_stops":
                poly = " ".join(f'{p["sx"]},{p["sy"]}' for p in stops)
                parts.append(
                    f'<polyline points="{poly}" fill="none" stroke="{color}" '
                    f'stroke-width="2.5" stroke-opacity="0.85" stroke-dasharray="7 4" '
                    f'marker-mid="url(#arrowCyan)"/>'
                )
            for p in stops:
                sx, sy = p["sx"], p["sy"]
                if tr["mode"] == "dispatch_zones":
                    parts.append(
                        f'<circle cx="{sx}" cy="{sy}" r="22" fill="{color}" fill-opacity="0.12" '
                        f'stroke="{color}" stroke-width="1.2" stroke-dasharray="3 3"/>'
                    )
                parts.append(
                    f'<g class="radar-stop" '
                    f'data-track-id="{tid}" '
                    f'data-track-name="{_esc(p["track_name"])}" '
                    f'data-stop-index="{p["index"]}" '
                    f'data-stop-name="{_esc(p["name"])}" '
                    f'data-x="{p["x"]}" data-y="{p["y"]}" data-z="{p["z"]}" '
                    f'data-dwell="{p["dwell_seconds"]}" data-reward="{p["fare_or_reward"]}">'
                    f'<circle class="stop-halo" cx="{sx}" cy="{sy}" r="11" fill="{color}" fill-opacity="0.18"/>'
                    f'<circle class="stop-core" cx="{sx}" cy="{sy}" r="6" fill="#0b0e14" stroke="{color}" stroke-width="2.2"/>'
                    f'<text x="{sx}" y="{sy + 3}" text-anchor="middle" fill="#f0f4f8" font-size="8" font-weight="700" font-family="monospace">{p["index"]}</text>'
                    f'<text x="{sx + 10}" y="{sy - 8}" fill="#d5dfec" font-size="10" font-family="sans-serif">{_esc(p["name"])}</text>'
                    "</g>"
                )
            parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def _build_state_machine_html(ir: GameplayIR) -> str:
    sm = ir.state_machine
    cards: list[str] = []
    for st in sm.states:
        cls = _phase_badge_class(st.name, st.phase, sm.initial_state, sm.cleanup_state)
        tags: list[str] = [f'<span class="pill {cls}">{_esc(st.phase)}</span>']
        if st.name == sm.initial_state:
            tags.append('<span class="pill badge-initial">INITIAL</span>')
        if st.name == sm.cleanup_state:
            tags.append('<span class="pill badge-teardown">CLEANUP / TEARDOWN</span>')
        cards.append(
            f'<div class="fsm-card {cls}-border">'
            f'<div class="fsm-card-head"><strong>{_esc(st.name)}</strong><div class="pill-row">{"".join(tags)}</div></div>'
            f'<p class="fsm-desc">{_esc(st.description or "Operational lifecycle state.")}</p>'
            "</div>"
        )

    edges: list[str] = []
    for edge in sm.transitions:
        is_teardown = edge.to_state == sm.cleanup_state
        row_cls = "edge-teardown" if is_teardown else "edge-normal"
        edges.append(
            f'<div class="edge-row {row_cls}">'
            f'<span class="edge-state">{_esc(edge.from_state)}</span>'
            f'<span class="edge-trigger">--[{_esc(edge.trigger)}]--></span>'
            f'<span class="edge-state">{_esc(edge.to_state)}</span>'
            "</div>"
        )

    return (
        f'<div class="fsm-grid">{"".join(cards)}</div>'
        f'<h3 class="subhead">State Transitions ({len(sm.transitions)})</h3>'
        f'<div class="edge-list">{"".join(edges)}</div>'
    )


def _build_entities_table(ir: GameplayIR) -> str:
    rows: list[str] = []
    for ent in ir.entities:
        addon_cell = (
            f'<code>{_esc(ent.preferred_addon_model)}</code>'
            if ent.preferred_addon_model
            else '<span class="muted">None (vanilla baseline)</span>'
        )
        player_badge = (
            '<span class="pill badge-initial">Player Vehicle</span>'
            if ent.is_player_vehicle
            else '<span class="pill badge-ui">World / NPC</span>'
        )
        rows.append(
            "<tr>"
            f"<td><code>{_esc(ent.slot_id)}</code></td>"
            f"<td>{_esc(ent.role)} {player_badge}</td>"
            f"<td>{addon_cell}</td>"
            f'<td><span class="pill badge-op"><code>{_esc(ent.vanilla_fallback_model)}</code></span></td>'
            f"<td>{ent.stream_timeout_ms} ms</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Slot ID</th><th>Role</th><th>Preferred Addon Model</th>"
        "<th>Vanilla Fallback (Mandatory)</th><th>Stream Timeout</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _build_evidence_table(ir: GameplayIR) -> str:
    if not ir.evidence:
        return '<p class="muted">No EvidenceAnchor records attached to this Gameplay IR.</p>'
    rows: list[str] = []
    for ev in ir.evidence:
        pct = int(round(max(0.0, min(1.0, ev.confidence)) * 100))
        rows.append(
            "<tr>"
            f"<td><code>{_esc(ev.source_file)}</code></td>"
            f"<td><code>{_esc(ev.locator)}</code></td>"
            f"<td>{_esc(ev.extracted_fact)}</td>"
            f'<td><div class="conf-wrap"><div class="conf-bar" style="width:{pct}%"></div><span>{pct}%</span></div></td>'
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Source File</th><th>Locator</th><th>Extracted Fact</th><th>Confidence</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_ir_dashboard(
    ir: GameplayIR | dict[str, Any],
    output_html_path: str | Path,
) -> dict[str, Any]:
    """Render an offline standalone Los Santos Street Radar & Gameplay IR Blueprint HTML dashboard."""
    ir_obj = ir if isinstance(ir, GameplayIR) else GameplayIR.from_dict(ir)
    out_path = Path(output_html_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    geo = _compute_radar_geometry(ir_obj)
    radar_svg = _build_radar_svg(geo)
    fsm_html = _build_state_machine_html(ir_obj)
    entities_html = _build_entities_table(ir_obj)
    evidence_html = _build_evidence_table(ir_obj)

    total_stops = sum(len(t.stops) for t in ir_obj.routes_or_zones)
    hotkey_label = (
        f"{ir_obj.inputs.modifier_key} + {ir_obj.inputs.activation_key}"
        if ir_obj.inputs.modifier_key
        else ir_obj.inputs.activation_key
    )

    track_buttons = ['<button class="track-btn active" data-track="ALL">All Tracks</button>']
    for tr in geo["tracks"]:
        track_buttons.append(
            f'<button class="track-btn" data-track="{_esc(tr["track_id"])}" '
            f'style="--dot:{_esc(tr["color"])}">'
            f'<span class="dot"></span>{_esc(tr["name"])} ({len(tr["stops"])} stops, {tr["total_distance_m"]}m)</button>'
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(ir_obj.meta.name)} — GTA-Anything Los Santos Radar &amp; IR Blueprint</title>
<style>
  :root {{
    --bg: #0b0e14;
    --surface: #121824;
    --surface-2: #182132;
    --border: #25334a;
    --gold: #d4af37;
    --gta-green: #2e8b57;
    --cyan: #00e5ff;
    --crimson: #e05263;
    --text: #e6edf6;
    --muted: #8b9bb4;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 24px;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif;
    line-height: 1.5;
  }}
  .container {{ max-width: 1280px; margin: 0 auto; }}
  header {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    padding: 20px 24px;
    background: linear-gradient(135deg, #121926 0%, #0d131d 100%);
    border: 1px solid var(--border);
    border-left: 4px solid var(--gold);
    border-radius: 10px;
    margin-bottom: 20px;
  }}
  h1 {{
    margin: 0 0 6px 0;
    font-size: 22px;
    color: var(--gold);
    letter-spacing: 0.4px;
  }}
  .subtitle {{ margin: 0; color: var(--muted); font-size: 13px; max-width: 760px; }}
  .meta-pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
  .pill {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid transparent;
    font-family: monospace;
  }}
  .badge-initial {{ background: rgba(212,175,55,0.16); color: var(--gold); border-color: rgba(212,175,55,0.45); }}
  .badge-op {{ background: rgba(46,139,87,0.2); color: #58d68d; border-color: rgba(46,139,87,0.55); }}
  .badge-stream {{ background: rgba(0,229,255,0.14); color: var(--cyan); border-color: rgba(0,229,255,0.4); }}
  .badge-ui {{ background: rgba(139,155,180,0.14); color: #c5d1e2; border-color: rgba(139,155,180,0.35); }}
  .badge-teardown {{ background: rgba(224,82,99,0.16); color: #ff8090; border-color: rgba(224,82,99,0.5); }}
  .kpi-strip {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }}
  .kpi {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
  }}
  .kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: var(--muted); }}
  .kpi-val {{ font-size: 22px; font-weight: 700; color: var(--text); margin-top: 4px; font-family: monospace; }}
  .kpi-val.gold {{ color: var(--gold); }}
  .kpi-val.green {{ color: #58d68d; }}
  .kpi-val.cyan {{ color: var(--cyan); }}
  .panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
  }}
  .panel h2 {{
    margin: 0 0 14px 0;
    font-size: 16px;
    color: var(--gold);
    text-transform: uppercase;
    letter-spacing: 0.9px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
  }}
  .subhead {{ margin: 18px 0 10px 0; font-size: 13px; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.7px; }}
  .track-controls {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
  .track-btn {{
    background: var(--surface-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }}
  .track-btn .dot {{
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--dot, var(--cyan));
    display: inline-block;
  }}
  .track-btn.active {{
    border-color: var(--gold);
    background: rgba(212,175,55,0.14);
    color: var(--gold);
  }}
  .radar-wrap {{
    position: relative;
    width: 100%;
    min-height: 420px;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    background: var(--bg);
  }}
  .radar-stop {{ cursor: pointer; }}
  .radar-stop:hover .stop-halo {{ fill-opacity: 0.45; }}
  .tooltip {{
    position: absolute;
    pointer-events: none;
    display: none;
    background: rgba(11, 14, 20, 0.95);
    border: 1px solid var(--gold);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 12px;
    color: var(--text);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
    min-width: 210px;
    z-index: 20;
  }}
  .tooltip strong {{ color: var(--gold); display: block; margin-bottom: 4px; }}
  .tooltip .tt-row {{ display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-family: monospace; font-size: 11px; }}
  .tooltip .tt-row span:last-child {{ color: var(--text); }}
  .fsm-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 12px;
  }}
  .fsm-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-left: 3px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
  }}
  .badge-initial-border {{ border-left-color: var(--gold); }}
  .badge-op-border {{ border-left-color: var(--gta-green); }}
  .badge-stream-border {{ border-left-color: var(--cyan); }}
  .badge-teardown-border {{ border-left-color: var(--crimson); }}
  .fsm-card-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .pill-row {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .fsm-desc {{ margin: 8px 0 0 0; font-size: 12px; color: var(--muted); }}
  .edge-list {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .edge-row {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-family: monospace;
    font-size: 11px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }}
  .edge-teardown {{ border-color: rgba(224,82,99,0.55); background: rgba(224,82,99,0.08); }}
  .edge-state {{ color: var(--text); font-weight: 600; }}
  .edge-trigger {{ color: var(--cyan); }}
  .edge-teardown .edge-trigger {{ color: #ff8090; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; }}
  code {{ font-family: monospace; color: var(--cyan); font-size: 12px; }}
  .muted {{ color: var(--muted); }}
  .conf-wrap {{ display: flex; align-items: center; gap: 8px; min-width: 110px; }}
  .conf-bar {{ height: 6px; border-radius: 3px; background: var(--gta-green); }}
  footer {{ text-align: center; color: var(--muted); font-size: 11px; margin-top: 20px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>{_esc(ir_obj.meta.name)}</h1>
      <p class="subtitle">{_esc(ir_obj.meta.description or "Gameplay IR Blueprint Dashboard")}</p>
      <div class="meta-pills">
        <span class="pill badge-initial">ID: {_esc(ir_obj.meta.id)}</span>
        <span class="pill badge-ui">v{_esc(ir_obj.meta.version)}</span>
        <span class="pill badge-op">License: {_esc(ir_obj.meta.license)}</span>
        <span class="pill badge-stream">Loader: {_esc(ir_obj.loader_target)}</span>
        <span class="pill badge-ui">Hotkey: {_esc(hotkey_label)}</span>
        <span class="pill badge-op">UI Preview: {_esc(ir_obj.ui_spec.preview_mode)}</span>
      </div>
    </div>
  </header>

  <section class="kpi-strip">
    <div class="kpi"><div class="kpi-label">Spatial Tracks</div><div class="kpi-val cyan">{len(ir_obj.routes_or_zones)}</div></div>
    <div class="kpi"><div class="kpi-label">Total Stops / Zones</div><div class="kpi-val gold">{total_stops}</div></div>
    <div class="kpi"><div class="kpi-label">Entity Slots</div><div class="kpi-val green">{len(ir_obj.entities)}</div></div>
    <div class="kpi"><div class="kpi-label">FSM States</div><div class="kpi-val">{len(ir_obj.state_machine.states)}</div></div>
    <div class="kpi"><div class="kpi-label">Evidence Anchors</div><div class="kpi-val">{len(ir_obj.evidence)}</div></div>
  </section>

  <section class="panel">
    <h2>Los Santos 2D Street Radar</h2>
    <div class="track-controls">{"".join(track_buttons)}</div>
    <div class="radar-wrap" id="radar-wrap">
      {radar_svg}
      <div class="tooltip" id="radar-tooltip"></div>
    </div>
  </section>

  <section class="panel">
    <h2>Operational Lifecycle State Machine</h2>
    {fsm_html}
  </section>

  <section class="panel">
    <h2>Entity Slots &amp; Vanilla Fallback Contracts</h2>
    {entities_html}
  </section>

  <section class="panel">
    <h2>EvidenceAnchor Traceability</h2>
    {evidence_html}
  </section>

  <footer>Generated offline by GTA-Anything Visualizer &bull; Zero external CDN dependencies &bull; Clean-Room Gameplay IR v{_esc(ir_obj.schema_version)}</footer>
</div>

<script>
(function() {{
  const wrap = document.getElementById("radar-wrap");
  const tooltip = document.getElementById("radar-tooltip");
  const stops = document.querySelectorAll(".radar-stop");
  const tracks = document.querySelectorAll(".radar-track");
  const buttons = document.querySelectorAll(".track-btn");

  buttons.forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      buttons.forEach(function(b) {{ b.classList.remove("active"); }});
      btn.classList.add("active");
      const target = btn.getAttribute("data-track");
      tracks.forEach(function(g) {{
        const tid = g.getAttribute("data-track-id");
        g.style.display = (target === "ALL" || tid === target) ? "" : "none";
      }});
    }});
  }});

  stops.forEach(function(node) {{
    node.addEventListener("mouseenter", function() {{
      const name = node.getAttribute("data-stop-name");
      const idx = node.getAttribute("data-stop-index");
      const trackName = node.getAttribute("data-track-name");
      const x = node.getAttribute("data-x");
      const y = node.getAttribute("data-y");
      const z = node.getAttribute("data-z");
      const dwell = node.getAttribute("data-dwell");
      const reward = node.getAttribute("data-reward");
      tooltip.innerHTML =
        "<strong>#" + idx + " " + name + "</strong>" +
        '<div class="tt-row"><span>Track</span><span>' + trackName + "</span></div>" +
        '<div class="tt-row"><span>Coords</span><span>(' + x + ", " + y + ", " + z + ")</span></div>" +
        '<div class="tt-row"><span>Dwell</span><span>' + dwell + "s</span></div>" +
        '<div class="tt-row"><span>Fare / Reward</span><span>$' + reward + "</span></div>";
      tooltip.style.display = "block";
    }});
    node.addEventListener("mousemove", function(evt) {{
      const rect = wrap.getBoundingClientRect();
      let left = evt.clientX - rect.left + 14;
      let top = evt.clientY - rect.top + 14;
      if (left + 230 > rect.width) left = Math.max(8, left - 245);
      if (top + 120 > rect.height) top = Math.max(8, top - 130);
      tooltip.style.left = left + "px";
      tooltip.style.top = top + "px";
    }});
    node.addEventListener("mouseleave", function() {{
      tooltip.style.display = "none";
    }});
  }});
}})();
</script>
</body>
</html>
"""

    out_path.write_text(html_doc, encoding="utf-8")

    return {
        "ok": True,
        "mod_id": ir_obj.meta.id,
        "output_html": str(out_path),
        "track_count": len(ir_obj.routes_or_zones),
        "state_count": len(ir_obj.state_machine.states),
    }
