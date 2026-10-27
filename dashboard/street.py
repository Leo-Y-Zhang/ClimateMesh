"""Full-screen, provenance-first view of the same database as the dashboard."""

from __future__ import annotations

import html
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.playbooks import playbook_for
from backend.risk_engine import alert_type_for
from config.nodes import NEIGHBOURS
from dashboard.accessibility import PALETTES, text_on
from dashboard.badges import source_badge_html
from dashboard.formatting import node_name, score_text, short_name
from dashboard.street_helpers import (
    THEMES,
    data_age,
    environment_label,
    is_fresh,
    join_nodes,
    london_time,
    mesh_status,
    multiplier_sentences,
    rotation_interval,
    rotation_order,
    select_node,
    site_position,
    sparkline_svg,
    SUPPORTING_LABELS,
    subscore_bars,
)
from data.database import DB_PATH, get_latest_readings_per_node, get_risk_scores, init_db

CSS = """
<style>
[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stSidebar"], .stAppDeployButton {display:none!important}
html, body, .stApp, [data-testid="stAppViewContainer"] {
 background:var(--background);color:var(--ink)}
html, body, .stApp, .street, .street * {
 font-family:system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "DejaVu Sans", sans-serif!important;
 box-sizing:border-box;font-variant-numeric:tabular-nums}
html, body {margin:0;overflow-x:hidden}
[data-testid="stMainBlockContainer"], .block-container {
 padding:0!important;max-width:100%!important}
[data-testid="stVerticalBlock"] {gap:0}
[data-testid="stMarkdownContainer"] > div {width:100%}
.street {--scale:1;--heading:clamp(20px,2.8vh,34px);--body:clamp(16px,2.2vh,28px);
 color:var(--ink);background:var(--background);width:100%;min-height:100svh;
 padding:clamp(10px,2vh,24px) 2vw;display:flex;flex-direction:column;
 gap:clamp(8px,1.5vh,18px);overflow-wrap:anywhere}
.street.large {--scale:1.12}
.street h1, .street h2, .street p, .street ol {margin:0;color:inherit}
.street h2 {font-size:calc(var(--heading)*var(--scale));font-weight:750;line-height:1.15}
.street p, .street li {font-size:calc(var(--body)*var(--scale))}
.street-header {display:grid;grid-template-columns:minmax(0,1fr) auto;
 gap:4px 2vw;align-items:center}
.identity, .source, .street main > *, .driver {min-width:0}
.eyebrow {display:flex;align-items:center;gap:1.5em;flex-wrap:wrap;
 color:var(--muted);font-size:clamp(13px,1.7vh,20px);line-height:1.3}
.wordmark {font-weight:800;letter-spacing:.14em}
.site {font-size:calc(clamp(26px,4.5vh,52px)*var(--scale));
 font-weight:750;line-height:1.08;letter-spacing:-.025em}
.meta {font-size:calc(clamp(16px,2.2vh,28px)*var(--scale));line-height:1.25}
.site-meta {color:var(--muted);margin-top:3px}
.source {text-align:right}
.street .source span {font-size:inherit!important;margin:0 0 4px!important;
 white-space:normal!important;line-height:1.25}
.age {color:var(--muted)}
.rotation {grid-column:1/-1;height:3px;overflow:hidden;background:var(--track)}
.rotation::after {content:"";display:block;height:100%;background:var(--ink);
 transform-origin:left;animation:rotation-fill var(--duration) linear infinite;
 animation-delay:var(--delay)}
@keyframes rotation-fill {from {transform:scaleX(0)} to {transform:scaleX(1)}}
.street main {flex:1;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);
 grid-template-areas:"hero drivers" "actions trend";
 grid-template-rows:auto auto;gap:clamp(8px,1.5vh,18px);align-content:stretch}
.panel, .band {border:1px solid var(--line);border-radius:12px;
 padding:clamp(10px,1.8vh,22px) clamp(12px,1.6vw,30px)}
.panel {background:var(--surface)}
.band {grid-area:hero;display:flex;flex-direction:column;justify-content:center;
 gap:clamp(6px,1.3vh,16px);border-color:currentColor}
.hero-numbers {display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}
.band h1 {font-size:calc(clamp(48px,min(7vw,11vh),128px)*var(--scale));
 font-weight:850;line-height:1;letter-spacing:-.045em}
.score {font-size:calc(clamp(38px,7vh,82px)*var(--scale));font-weight:750;line-height:1}
.score small {font-size:.42em;font-weight:600}
.hazard {font-size:calc(clamp(18px,2.6vh,32px)*var(--scale));font-weight:650;line-height:1.15}
.street .why {font-size:calc(clamp(16px,2.3vh,30px)*var(--scale));line-height:1.24}
.band-scale {position:relative;padding-top:8px}
.scale-segments {display:grid;grid-template-columns:30fr 30fr 20fr 20fr;
 border:1px solid currentColor;border-radius:3px;overflow:hidden}
.scale-segments span {text-align:center;font-size:clamp(12px,1.6vh,19px);
 line-height:1.6;font-weight:800;white-space:nowrap}
.scale-marker {position:absolute;top:-2px;
 width:0;height:0;border-left:8px solid transparent;border-right:8px solid transparent;
 border-top:11px solid currentColor;transform:translateX(-50%)}
.scale-ticks {position:relative;height:1.2em;font-size:clamp(12px,1.6vh,19px);line-height:1.2}
.scale-ticks span {position:absolute;transform:translateX(-50%);white-space:nowrap}
.scale-ticks span:first-child {transform:none}.scale-ticks span:last-child {transform:translateX(-100%)}
.drivers {grid-area:drivers;display:flex;flex-direction:column;justify-content:center;
 gap:clamp(6px,1vh,12px)}
.driver-list {display:grid;gap:clamp(4px,.8vh,10px)}
.driver {display:grid;grid-template-columns:minmax(105px,auto) minmax(20px,1fr) 2.4em;
 gap:.6em;align-items:center;font-size:calc(clamp(16px,2.1vh,26px)*var(--scale));line-height:1.15}
.driver.top {font-weight:800}
.driver.supporting {opacity:.7}
.driver-sep {font-size:.72em;font-weight:700;letter-spacing:.08em;
 text-transform:uppercase;opacity:.7;margin-top:.35em}
.driver.top .driver-label {text-decoration:underline;text-underline-offset:.18em}
.driver-value {text-align:right}
.driver-track {height:.4em;border-radius:3px;background:var(--track);overflow:hidden}
.driver-fill {display:block;height:100%;background:var(--muted)}
.driver.top .driver-fill {background:var(--ink)}
.multipliers {display:grid;gap:3px;border-top:1px solid var(--line);padding-top:clamp(5px,.8vh,10px)}
.street .multipliers p {font-size:calc(clamp(16px,2vh,24px)*var(--scale));line-height:1.2}
.actions {grid-area:actions;display:flex;flex-direction:column;justify-content:center;gap:8px}
.street .actions ol {padding-left:1.6em;display:grid;gap:clamp(5px,1vh,12px)}
.street .actions li {line-height:1.24;padding-left:.15em}
.actions li::marker {font-weight:800}
.trend {grid-area:trend;display:flex;flex-direction:column;justify-content:center;gap:6px}
.trend svg {display:block;width:100%;height:clamp(65px,10vh,150px);overflow:visible}
.trend-guide {stroke:var(--muted);stroke-width:1;stroke-dasharray:4 5;opacity:.6}
.trend-line {fill:none;stroke:currentColor;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.trend-axis {display:flex;justify-content:space-between;color:var(--muted);
 font-size:clamp(16px,2vh,24px)}
.mesh {border-top:1px solid var(--line);padding-top:clamp(6px,1vh,12px);
 display:grid;gap:5px;font-size:calc(clamp(16px,2vh,24px)*var(--scale))}
.neighbours {display:flex;flex-wrap:wrap;gap:5px 10px;align-items:center}
.chip {display:inline-flex;align-items:center;gap:.4em;border:1px solid var(--line);
 border-radius:6px;padding:3px 8px;background:var(--surface);line-height:1.15}
.dot {flex:none;width:.65em;height:.65em;border:1px solid var(--ink);border-radius:50%}
.street .mesh-status {font-size:inherit;color:var(--muted);line-height:1.2}
.empty {justify-content:center;align-items:center;text-align:center;gap:4vh}
.empty h1 {font-size:clamp(34px,5vw,90px)}
.empty code {font:inherit;font-size:clamp(20px,3vw,50px);background:var(--surface);
 color:var(--ink);padding:12px;white-space:normal}
@media (orientation:landscape) and (max-height:600px) {
 .street {padding:6px 2vw;gap:6px;--heading:20px;--body:16px}
 .street-header {gap:2px 12px}.eyebrow {font-size:12px;line-height:1.1}
 .site {font-size:calc(26px*var(--scale))}.meta {font-size:calc(16px*var(--scale))}
 .site-meta {margin-top:1px}.source span {padding:2px 6px!important}
 .street main {grid-template-areas:"hero actions" "drivers drivers";gap:6px;
 grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-rows:1fr auto}
 .panel, .band {padding:8px 10px;border-radius:8px}
 .band {gap:4px}.band h1 {font-size:calc(46px*var(--scale))}
 .score {font-size:calc(34px*var(--scale))}.hazard {font-size:calc(18px*var(--scale))}
 .street .why {font-size:calc(16px*var(--scale));line-height:1.18}
 .hero-numbers {gap:4px;flex-wrap:nowrap}
 .scale-segments span, .scale-ticks {font-size:12px}
 .drivers {display:grid;grid-template-columns:auto minmax(0,1fr);
  align-items:center;gap:5px 16px;padding:6px 10px}
 .drivers h2 {grid-column:1;grid-row:1}
 .driver-list {grid-column:1/-1;grid-row:2;
  grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}
 .driver {grid-template-columns:minmax(0,1fr) auto;gap:3px;font-size:14px}
 .driver-track {grid-row:2;grid-column:1/-1;height:4px}
 .driver-value {grid-column:2;grid-row:1}
 .multipliers {grid-column:2;grid-row:1;grid-template-columns:1fr 1.5fr;
  border:0;padding:0;gap:8px}
 .street .multipliers p {font-size:14px;line-height:1.15}
 .actions {gap:6px}.street .actions ol {gap:6px}
 .street .actions li {line-height:1.18}
 .trend {display:none}
 .mesh {font-size:14px;padding-top:4px;gap:3px}
 .neighbours {gap:4px 6px}.chip {padding:2px 6px}
}
@media (orientation:portrait), (max-width:600px) {
 .street {padding:1.5vh 3vw;gap:1vh;--heading:clamp(22px,3.6vw,32px);
 --body:clamp(18px,2.8vw,24px)}
 .street main {grid-template-columns:minmax(0,1fr);grid-template-rows:auto;
 grid-template-areas:"hero" "actions" "drivers" "trend";gap:1vh}
 .panel, .band {padding:1vh 3vw}
 .site {font-size:calc(clamp(26px,5.2vw,42px)*var(--scale))}
 .meta {font-size:calc(clamp(16px,2.5vw,22px)*var(--scale))}
 .eyebrow {font-size:clamp(12px,2.2vw,18px);gap:1em}
 .source {max-width:28vw}
 .band {gap:.8vh}.band h1 {font-size:calc(clamp(48px,11vw,96px)*var(--scale))}
 .score {font-size:calc(clamp(38px,8vw,68px)*var(--scale))}
 .street .why {font-size:calc(clamp(18px,2.8vw,24px)*var(--scale));line-height:1.22}
 .hazard {font-size:calc(clamp(18px,3.5vw,28px)*var(--scale))}
 .driver {font-size:calc(clamp(17px,2.6vw,23px)*var(--scale))}
 .driver-list {gap:.5vh}
 .street .multipliers p {font-size:calc(clamp(17px,2.6vw,23px)*var(--scale))}
 .street .actions ol {gap:.7vh}.street .actions li {line-height:1.2}
 .trend svg {height:4.5vh}
 .mesh {font-size:calc(clamp(16px,2.6vw,23px)*var(--scale))}
}
@media (prefers-reduced-motion:reduce) {
 *, *::before, *::after {animation:none!important;transition:none!important}
 .rotation::after {transform:scaleX(1)}
}
</style>
"""


def get_score_history(node_id: str, now: datetime | None = None) -> list[dict]:
    """The dashboard's ten-minute window, querying stored risk rather than sensors.

    Kept here because the shared history loader returns only sensor readings.
    An optional trend must never prevent the current display from rendering.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    path = Path(os.environ.get("CLIMATE_MESH_DB", DB_PATH)).resolve()
    try:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT timestamp, score FROM risk_scores "
                "WHERE node_id=? AND timestamp>=? AND timestamp<=? "
                "ORDER BY timestamp, id",
                (node_id, (now - timedelta(minutes=10)).isoformat(), now.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.Error, OSError):
        return []


def esc(value) -> str:
    return html.escape(str(value))


def band_scale_html(score: float, colours: dict[str, str]) -> str:
    segments = "".join(
        f'<span style="background:{bg};color:{text_on(bg)}">{band}</span>'
        for band, bg in colours.items()
    )
    ticks = "".join(
        f'<span style="left:{value}%">{value}</span>' for value in (0, 30, 60, 80, 100)
    )
    return (
        f'<div class="band-scale" style="--score:{max(0, min(100, score))}%" '
        'role="img" aria-label="Risk bands: Safe 0 to 30, Moderate 30 to 60, '
        f'Warning 60 to 80, Critical 80 to 100. Score {score:g}.">'
        # Inline left: Streamlit's HTML sanitiser drops CSS custom properties,
        # so a var(--score) position silently fell back to 0.
        f'<span class="scale-marker" style="left:{min(max(score, 1.0), 99.0):g}%"></span>'
        f'<div class="scale-segments">{segments}</div>'
        f'<div class="scale-ticks">{ticks}</div></div>'
    )


def drivers_html(row: dict) -> str:
    bars = []
    separated = False
    for i, (label, value) in enumerate(subscore_bars(row)):
        top = " top" if i == 0 and value is not None and value > 0 else ""
        supporting = label in SUPPORTING_LABELS
        if supporting and not separated:
            bars.append('<div class="driver-sep">Supporting signals</div>')
            separated = True
        displayed = f"{value:g}" if value is not None else "—"
        bars.append(
            f'<div class="driver{top}{" supporting" if supporting else ""}">'
            f'<span class="driver-label">{label}</span>'
            '<span class="driver-track" aria-hidden="true">'
            f'<span class="driver-fill" style="width:{value or 0}%"></span></span>'
            f'<span class="driver-value">{displayed}</span></div>'
        )
    words = "".join(f"<p>{esc(line)}</p>" for line in multiplier_sentences(row))
    return (
        '<section class="panel drivers" aria-labelledby="drivers-heading">'
        '<h2 id="drivers-heading">What is driving it</h2>'
        f'<div class="driver-list">{"".join(bars)}</div>'
        f'<div class="multipliers">{words}</div></section>'
    )


def neighbours_html(row: dict, rows: list[dict], colours: dict[str, str]) -> str:
    by_id = {r["node_id"]: r for r in rows}
    chips = []
    for neighbour in NEIGHBOURS.get(row["node_id"], []):
        other = by_id.get(neighbour)
        fresh = other and is_fresh(other)
        band = other["level"] if fresh else "No fresh data"
        colour = colours.get(band, "var(--track)")
        name = short_name(
            other.get("node_name") or node_name(neighbour)
        ) if other else node_name(neighbour)
        score = score_text(other["score"]).split("/")[0] if fresh else "—"
        chips.append(
            f'<span class="chip" aria-label="{esc(name)}: {esc(band)}, {score}">'
            f'<span class="dot" style="background:{colour}" aria-hidden="true"></span>'
            f'{esc(name)} {score}</span>'
        )
    status = mesh_status(row.get("corroboration"), row.get("correlated_count") or 0)
    return (
        '<div class="mesh" role="contentinfo" aria-label="Neighbouring sites">'
        f'<div class="neighbours">{"".join(chips)}</div>'
        f'<p class="mesh-status">{esc(status)}</p></div>'
    )


def render() -> None:
    st.set_page_config(
        page_title="Climate Mesh — Street", page_icon="🌍", layout="wide"
    )
    theme = THEMES["light" if st.query_params.get("theme") == "light" else "dark"]
    variables = ";".join(f"--{key}:{value}" for key, value in theme.items())
    st.markdown(f"<style>:root {{{variables}}}</style>" + CSS, unsafe_allow_html=True)
    try:
        init_db()
        rows = join_nodes(get_latest_readings_per_node(), get_risk_scores())
    except (sqlite3.Error, OSError):
        rows = []
    started = st.session_state.setdefault("street_started", time.monotonic())
    elapsed = time.monotonic() - started
    pinned = st.query_params.get("node")
    row = select_node(rows, elapsed, pinned)
    large = " large" if st.query_params.get("large") == "1" else ""
    if not row or not is_fresh(row):
        content = (
            "<h1>No fresh data: is the engine running?</h1>"
            "<code>python run.py --mode auto</code>"
        )
        st.markdown(
            f'<div class="street empty{large}">{content}</div>', unsafe_allow_html=True
        )
    else:
        colours = PALETTES[
            "colour-blind safe"
            if st.query_params.get("palette") == "cb"
            else "standard"
        ]
        bg = colours[row["level"]]
        hazard = alert_type_for(row)
        hazard_name = {
            "sensor-check": "Sensor check", "risk": "Climate risk",
            "flood": "Flood risk", "smog": "Air quality risk",
            "heatwave": "Heat risk", "storm": "Storm risk", "cold": "Cold risk",
        }[hazard]
        # A SAFE site gets a calm all-clear, not a playbook for a hazard it does not have.
        steps = (["Nothing to do: conditions are normal here.",
                  "This screen checks again every few seconds."]
                 if row["level"] == "SAFE" else playbook_for(hazard))
        actions = "".join(f"<li>{esc(step)}</li>" for step in steps)
        ordered = rotation_order(rows)
        progress = ""
        if not pinned and len(ordered) > 1:
            interval = rotation_interval(ordered)
            progress = (
                f'<div class="rotation" style="--duration:{interval}s;'
                f'--delay:-{elapsed % interval:.2f}s" aria-hidden="true"></div>'
            )
        now = datetime.now(timezone.utc)
        svg = sparkline_svg(get_score_history(row["node_id"], now), now)
        trend = (
            f'{svg}<div class="trend-axis"><span>10 min ago</span><span>Now</span></div>'
            if svg else '<p>History builds as scores arrive.</p>'
        )
        score = score_text(row["score"]).split("/")[0]
        content = f"""<div class="street{large}">
<div class="street-header" role="banner"><div class="identity">
<div class="eyebrow"><span class="wordmark">CLIMATE MESH</span><span>{site_position(rows, row, bool(pinned))}</span></div>
<div class="site">{esc(row.get("node_name") or row["node_id"])}</div>
<div class="meta site-meta">{esc(environment_label(row.get("environment")))} · {london_time(now)}</div></div>
<div class="meta source">{source_badge_html(row.get("source"))}<div class="age">updated {data_age(row):.0f} s ago</div></div>{progress}</div>
<main><section class="band" style="background:{bg};color:{text_on(bg)}" aria-labelledby="band-heading">
<div class="hero-numbers"><h1 id="band-heading">{esc(row["level"])}</h1><div class="score">{score}<small>/100</small></div></div>
<div class="hazard">{hazard_name}</div>{band_scale_html(float(row["score"]), colours)}
<p class="why">{esc(row.get("explanation") or "Explanation unavailable.")}</p></section>
<section class="panel actions" aria-labelledby="actions-heading"><h2 id="actions-heading">What to do</h2><ol>{actions}</ol></section>
{drivers_html(row)}<section class="panel trend" aria-labelledby="trend-heading"><h2 id="trend-heading">Score · last 10 minutes</h2>{trend}</section></main>
{neighbours_html(row, rows, colours)}</div>"""
        st.markdown(content, unsafe_allow_html=True)
    # Match the main dashboard's dependency-free refresh mechanism.
    if st.session_state.get("auto_refresh", True):
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    render()
