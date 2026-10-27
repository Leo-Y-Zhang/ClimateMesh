"""Full-screen, provenance-first view of the same database as the dashboard."""

from __future__ import annotations

import html
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.playbooks import playbook_for
from backend.risk_engine import alert_type_for
from config.nodes import NEIGHBOURS
from dashboard.accessibility import PALETTES, text_on
from dashboard.badges import source_badge_html
from dashboard.formatting import score_text
from dashboard.street_helpers import (
    data_age,
    is_fresh,
    join_nodes,
    mesh_status,
    select_node,
)
from data.database import get_latest_readings_per_node, get_risk_scores, init_db

CSS = """
<style>
header, footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stSidebar"], .stAppDeployButton {display:none!important}
html, body, .stApp, [data-testid="stAppViewContainer"] {background:#101820;color:#f6f7f8}
[data-testid="stMainBlockContainer"], .block-container {padding:0!important;max-width:100%!important}
[data-testid="stVerticalBlock"] {gap:0}
* {box-sizing:border-box}
html, body {margin:0;overflow-x:hidden}
.street {color:#f6f7f8;--scale:1; min-height:100svh; width:100%; padding:2vh 2vw;
 display:flex;flex-direction:column;gap:2vh;font-family:Arial,sans-serif;overflow-wrap:anywhere}
.street.large {--scale:1.15}
.street h1, .street h2, .street p {margin:0;color:inherit}
.street header {display:flex!important;align-items:center;justify-content:space-between;gap:2vw;flex-wrap:wrap}
.site {font-size:calc(clamp(24px,3.2vw,58px)*var(--scale));font-weight:700;line-height:1.06}
.meta {font-size:calc(clamp(16px,1.7vw,30px)*var(--scale));line-height:1.25}
.street .source span {font-size:inherit!important;white-space:normal!important}
.street main {flex:1;display:grid;grid-template-columns:1.15fr 1fr;gap:2vw;align-items:stretch;min-width:0}
.band {border:2px solid #aab7c4;border-radius:12px;padding:2vh 2vw;display:flex;flex-direction:column;justify-content:center;gap:1.6vh;min-width:0}
.band h1 {font-size:calc(clamp(46px,7.4vw,144px)*var(--scale));font-weight:900;line-height:1;letter-spacing:-.035em}
.score {font-size:calc(clamp(24px,3.2vw,64px)*var(--scale));font-weight:700}
.why {font-size:calc(clamp(18px,1.9vw,38px)*var(--scale));line-height:1.22}
.actions {padding:1vh 1vw;min-width:0;display:flex;flex-direction:column;justify-content:center}
.actions h2 {font-size:calc(clamp(22px,2.8vw,48px)*var(--scale))}
.actions ol {margin:1vh 0;padding-left:1.5em;font-size:calc(clamp(20px,2.35vw,46px)*var(--scale));line-height:1.22}
.actions li {padding:1vh 0}
.mesh {font-size:calc(clamp(17px,2vw,36px)*var(--scale));border-top:1px solid #8fa5b5;padding-top:1vh}
.dot {display:inline-block;width:.7em;height:.7em;border:1px solid #fff;border-radius:50%;margin:0 .18em}
.empty {justify-content:center;align-items:center;text-align:center;gap:4vh}
.empty h1 {font-size:clamp(34px,5vw,90px)}
.empty code {background:#1c2b39;font-size:clamp(20px,3vw,50px);color:#fff;white-space:normal}
@media (orientation:landscape) and (max-height:600px) {
 .street {padding:1.5vh 2vw;gap:1vh}
 .site {font-size:calc(clamp(22px,3vw,32px)*var(--scale))}
 .meta {font-size:calc(clamp(15px,1.8vw,20px)*var(--scale))}
 .band {padding:1vh 1.2vw;gap:1vh}
 .band h1 {font-size:calc(clamp(42px,7vw,75px)*var(--scale))}
 .why {font-size:calc(clamp(16px,2vw,22px)*var(--scale))}
 .actions ol {font-size:calc(clamp(17px,2.1vw,24px)*var(--scale));line-height:1.15}
 .actions li {padding:.5vh 0}
 .mesh {font-size:calc(17px*var(--scale))}
}
@media (orientation:portrait), (max-width:600px) {
 .street {padding:2vh 4vw}
 .street main {grid-template-columns:1fr;gap:2vh}
 .band h1 {font-size:calc(clamp(48px,13vw,120px)*var(--scale))}
 .site {font-size:calc(clamp(26px,6vw,52px)*var(--scale))}
 .why {font-size:calc(clamp(21px,4vw,34px)*var(--scale))}
 .actions ol {font-size:calc(clamp(23px,4.5vw,38px)*var(--scale))}
 .meta, .mesh {font-size:calc(clamp(18px,3.5vw,28px)*var(--scale))}
}
@media (prefers-reduced-motion:reduce) {* {animation:none!important;transition:none!important}}
</style>
"""


def render() -> None:
    st.set_page_config(
        page_title="Climate Mesh — Street", page_icon="🌍", layout="wide"
    )
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        init_db()
        rows = join_nodes(get_latest_readings_per_node(), get_risk_scores())
    except (sqlite3.Error, OSError):
        rows = []
    started = st.session_state.setdefault("street_started", time.monotonic())
    row = select_node(rows, time.monotonic() - started, st.query_params.get("node"))
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
        esc = lambda value: html.escape(str(value))
        colours = PALETTES[
            "colour-blind safe"
            if st.query_params.get("palette") == "cb"
            else "standard"
        ]
        bg = colours[row["level"]]
        hazard = alert_type_for(row)
        actions = "".join(f"<li>{esc(step)}</li>" for step in playbook_for(hazard))
        by_id = {r["node_id"]: r for r in rows}
        dots = []
        for neighbour in NEIGHBOURS.get(row["node_id"], []):
            other = by_id.get(neighbour)
            band = other["level"] if other and is_fresh(other) else "No fresh data"
            colour = colours.get(band, "#66717c")
            dots.append(
                f'<span class="dot" style="background:{colour}" '
                f'role="img" aria-label="{esc(neighbour)}: {band}" '
                f'title="{esc(neighbour)}: {band}"></span>'
            )
        content = f"""<div class="street{large}">
<header><div><div class="site">{esc(row.get("node_name") or row["node_id"])}</div>
<div class="meta">{esc(row.get("environment", ""))} · {datetime.now().astimezone():%H:%M:%S %Z}</div></div>
<div class="meta source">{source_badge_html(row.get("source"))}<br>updated {data_age(row):.0f}s ago</div></header>
<main><section class="band" style="background:{bg};color:{text_on(bg)}">
<h1>{esc(row["level"])}</h1><div class="score">{score_text(row["score"])} · {esc(row.get("dominant_hazard", "risk"))}</div>
<p class="why">{esc(row.get("explanation", ""))}</p></section>
<section class="actions"><h2>{"Stay aware" if row["level"] == "SAFE" else "What to do"}</h2><ol>{actions}</ol></section></main>
<div class="mesh">{esc(mesh_status(row.get("corroboration"), row.get("correlated_count") or 0))} {" ".join(dots)}</div></div>"""
        st.markdown(content, unsafe_allow_html=True)
    # Match the main dashboard's dependency-free refresh mechanism.
    if st.session_state.get("auto_refresh", True):
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    render()
