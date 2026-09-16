"""Streamlit dashboard for Climate Mesh.

Seven tabs (Live Map, Network Overview, Node Detail, AI Explainability,
Evidence & Validation, Hardware Readiness, Competition Pitch). The dashboard is
a pure *reader* of the shared SQLite database — the engine process (``run.py``)
writes; this displays. Data-source labels and the active mode are shown
prominently so nobody mistakes simulated or API data for physical-sensor data.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.playbooks import playbook_for
from dashboard.formatting import (
    age_phrase, age_seconds, corroboration_line, node_name as _node_name, short_name,
)
from dashboard.badges import (
    effective_source_from_readings, quality_badge_html, source_badge_html,
    source_label, sources_legend_html,
)
from data.database import (
    get_alerts, get_latest_readings_per_node, get_latest_run_meta,
    get_node_history, get_risk_scores, init_db,
)
from sensors.hardware_status import detect
from simulation.scenarios import SCENARIO_INFO, SCENARIOS

DEMO_CONTROL_PATH = Path(__file__).parent.parent / "data" / "demo_control.json"

# Approximate courses of the main waterways through Greater London, used only
# for orientation on the tile-free offline basemap (they are hand-traced, not
# surveyed). Each is a list of (latitude, longitude) points west/north to east.
_WATERWAYS: dict[str, list[tuple[float, float]]] = {
    "River Thames": [
        (51.463, -0.320), (51.485, -0.285), (51.470, -0.250), (51.465, -0.215),
        (51.475, -0.185), (51.480, -0.160), (51.487, -0.135), (51.502, -0.122),
        (51.508, -0.100), (51.507, -0.075), (51.500, -0.050), (51.490, -0.020),
        (51.503, -0.005), (51.487, 0.005), (51.492, 0.025), (51.496, 0.040),
        (51.494, 0.070), (51.505, 0.100),
    ],
    "River Lea": [
        (51.610, -0.045), (51.585, -0.035), (51.560, -0.023), (51.545, -0.012),
        (51.530, -0.005), (51.515, 0.002), (51.508, 0.008),
    ],
    "River Wandle": [
        (51.462, -0.190), (51.450, -0.185), (51.435, -0.175), (51.415, -0.168),
        (51.400, -0.165),
    ],
    "Regent's Canal": [
        (51.523, -0.184), (51.533, -0.165), (51.541, -0.145), (51.535, -0.120),
        (51.532, -0.100), (51.528, -0.075), (51.520, -0.055), (51.512, -0.038),
    ],
}

# Where each waterway's name sits on the tile-free map (latitude, longitude),
# chosen to stay clear of the node labels.
_WATERWAY_LABEL_AT = {
    "River Thames": (51.463, -0.320),
    "River Lea": (51.610, -0.045),
    "River Wandle": (51.400, -0.165),
    "Regent's Canal": (51.530, -0.078),
}

# Label placement for the tile-free map: nodes that sit close together get
# labels on different sides so the names do not overlap.
_LABEL_POS = {
    "HYDE-PARK": "bottom center", "CENTRAL-LDN": "bottom right",
    "REGENTS-CANAL": "top left", "CAMDEN": "top center",
    "CANARY-WHARF": "bottom right", "GREENWICH": "bottom center",
    "STRATFORD": "top right", "VICTORIA-PARK": "top left",
    "RIVER-LEA": "top right", "WALTHAMSTOW": "top center",
    "THAMES-BARRIER": "top center", "ILFORD": "top center",
    "LEWISHAM": "bottom center", "DULWICH": "bottom center",
    "BRIXTON": "bottom left", "PUTNEY": "bottom center",
    "RIVER-WANDLE": "bottom right", "WIMBLEDON": "bottom center",
    "RICHMOND-PARK": "bottom center", "HAMPSTEAD": "top center",
}


def _short_name(name: str) -> str:
    """'Regent's Canal (Little Venice)' -> \"Regent's Canal\" for map labels."""
    return short_name(name)


def _offline_map(df: pd.DataFrame):
    """Tile-free map: labelled nodes over the main waterways, no internet needed.

    Plotly's map traces cannot draw text without a glyph server, so this is a
    plain scatter with latitude/longitude axes, scaled so that a kilometre is
    the same length north-south and east-west at London's latitude.
    """
    fig = go.Figure()
    for name, pts in _WATERWAYS.items():
        fig.add_trace(go.Scatter(
            x=[p[1] for p in pts], y=[p[0] for p in pts], mode="lines",
            line=dict(width=7 if name == "River Thames" else 3.5, color="#a9cde6",
                      shape="spline", smoothing=0.6),
            hoverinfo="skip", showlegend=False, name=name))
        # Name the waterway away from the node that shares its name.
        lat, lon = _WATERWAY_LABEL_AT.get(name, pts[0])
        fig.add_annotation(x=lon, y=lat, text=name, showarrow=False,
                           font=dict(size=10, color="#5b8db8", family="sans-serif"),
                           xanchor="left", yanchor="bottom", xshift=4, yshift=2, opacity=0.9)
    fig.add_trace(go.Scatter(
        x=df["longitude"], y=df["latitude"], mode="markers+text",
        text=[_short_name(n) for n in df["node_name"]],
        textposition=[_LABEL_POS.get(n, "top center") for n in df["node_id"]],
        textfont=dict(size=11, color="#2d3748", family="sans-serif"),
        marker=dict(
            size=12 + df["score"].clip(lower=0, upper=100) * 0.2,
            color=df["score"], cmin=0, cmax=100,
            colorscale=[[0, "#2ecc71"], [0.33, "#f1c40f"], [0.66, "#e67e22"], [1, "#e74c3c"]],
            colorbar=dict(title="score", thickness=14, len=0.7),
            line=dict(width=1.5, color="white"), opacity=0.92),
        customdata=list(zip(df["node_id"], df["level"], df["score"].round(0), df["source"],
                            _column(df, "dominant_hazard", "risk"))),
        hovertemplate="<b>%{text}</b> (%{customdata[0]})<br>risk %{customdata[2]}/100 · "
                      "<b>%{customdata[1]}</b><br>main hazard: %{customdata[4]}"
                      "<br>source: %{customdata[3]}<extra></extra>",
        showlegend=False))
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.01, showarrow=False,
                       text="Offline basemap · waterways approximate · nodes are illustrative landmarks",
                       font=dict(size=9, color="#8a94a6"), xanchor="left", yanchor="bottom")
    lat0 = 51.5
    fig.update_xaxes(visible=False, range=[-0.335, 0.125], fixedrange=False)
    fig.update_yaxes(visible=False, range=[51.385, 51.625],
                     scaleanchor="x", scaleratio=1 / math.cos(math.radians(lat0)))
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0),
                      plot_bgcolor="#f6f8fb", paper_bgcolor="white", hovermode="closest")
    return fig

st.set_page_config(page_title="Climate Mesh", page_icon="🌍", layout="wide")
init_db()

LEVEL_ICON = {"SAFE": "🟢", "MODERATE": "🟡", "WARNING": "🟠", "CRITICAL": "🔴"}
# The two bands that mean somebody should do something.
ACTING_LEVELS = ("WARNING", "CRITICAL")


def _write_scenario(scenario: str) -> None:
    DEMO_CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_CONTROL_PATH.write_text(json.dumps({"scenario": scenario}))


def _active_scenario() -> str:
    """Read the active scenario from the control file, or fall back to normal.

    Only an object whose "scenario" names something we actually know is
    honoured, so a stale or hand-edited control file cannot put an unknown
    scenario in front of the picker, or crash the tab that reads it.
    """
    try:
        if DEMO_CONTROL_PATH.exists():
            control = json.loads(DEMO_CONTROL_PATH.read_text())
            if isinstance(control, dict):
                scenario = control.get("scenario")
                if isinstance(scenario, str) and scenario in SCENARIOS:
                    return scenario
    except (json.JSONDecodeError, OSError):
        pass
    return "normal"


def _local_hms(ts: str) -> str:
    """Render a stored UTC ISO timestamp as local wall-clock HH:MM:SS.

    Rows are stored in UTC; a judge in the UK during BST would otherwise see
    every alert stamped an hour early with nothing to explain why.
    """
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return str(ts)


def _column(df: pd.DataFrame, name: str, default):
    """``df[name]`` if the column survived the merge, else a constant column."""
    if name in df.columns:
        return df[name].fillna(default)
    return pd.Series([default] * len(df), index=df.index)


def _corroboration_line(row) -> str:
    """:func:`corroboration_line` for a risk row from the database."""
    return corroboration_line(row.get("corroboration"),
                              row.get("correlated_count"), row.get("mesh_degree"))


def _act_now(merged: pd.DataFrame, alerts: list[dict]) -> None:
    """The answer to "so what do I do?", on the first screen rather than the third.

    Every alert already carries an action playbook and the engine has always
    stored one; until now nothing in the dashboard displayed it, so a reader
    who found the red node still had nowhere to go.
    """
    acting = merged[merged["level"].isin(ACTING_LEVELS)].sort_values(
        "score", ascending=False)
    if acting.empty:
        st.success("**Nothing to act on.** No node is at WARNING or CRITICAL. "
                   "The map below shows the current score at every node.")
        return
    panel = st.container(border=True)
    top = acting.iloc[0]
    node_id = top["node_id"]
    latest = next((a for a in alerts if a["node_id"] == node_id), None)
    hazard = str((latest or {}).get("alert_type")
                 or top.get("dominant_hazard") or "risk")
    icon = LEVEL_ICON.get(top["level"], "⚪")
    box = panel.error if top["level"] == "CRITICAL" else panel.warning
    box(f"{icon}  **Act now — {_node_name(node_id)} · "
        f"{top['score']:.0f}/100 {top['level']} · {hazard}**")
    if top.get("explanation"):
        panel.markdown(f"**Why:** {top['explanation']}")
    note = _corroboration_line(top)
    if note:
        panel.markdown(note)
    steps = playbook_for(hazard)
    if steps:
        panel.markdown("**What to do**\n\n"
                    + "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)))
    others = acting.iloc[1:]
    if not others.empty:
        names = ", ".join(f"{_node_name(r['node_id'])} ({r['score']:.0f} {r['level']})"
                          for _, r in others.head(5).iterrows())
        more = "" if len(others) <= 5 else f", and {len(others) - 5} more"
        panel.caption(f"Also above the action threshold: {names}{more}. "
                      "Open **Node Detail** for any node's full breakdown.")


def _scatter_map(df: pd.DataFrame, offline: bool = False):
    """Build a risk-coloured map, tolerating both old and new plotly APIs.

    ``offline=True`` returns the tile-free labelled map from
    :func:`_offline_map`, so the map works with no internet at all (the
    street-map tiles are the only part of the dashboard that ever needs a
    connection).
    """
    if offline:
        return _offline_map(df)
    style = "carto-positron-nolabels"
    common = dict(
        lat="latitude", lon="longitude", color="score", size="size",
        color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
        range_color=[0, 100], size_max=22, zoom=9,
        center={"lat": 51.50, "lon": -0.11}, hover_name="node_name",
        hover_data={"node_id": True, "level": True, "score": ":.0f",
                    "dominant_hazard": True,
                    "source": True, "latitude": False, "longitude": False, "size": False},
        labels={"dominant_hazard": "main hazard", "level": "band"},
    )
    try:  # plotly >= 5.24 (maplibre)
        fig = px.scatter_map(df, map_style=style, **common)
    except AttributeError:  # older plotly (mapbox)
        fig = px.scatter_mapbox(df, mapbox_style=style, **common)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0))
    return fig


# --- Load data ------------------------------------------------------------
readings = get_latest_readings_per_node()
risks = get_risk_scores()
alerts = get_alerts(limit=40)
run_meta = get_latest_run_meta() or {}

readings_df = pd.DataFrame(readings) if readings else pd.DataFrame()
risks_df = pd.DataFrame(risks) if risks else pd.DataFrame()

merged = pd.DataFrame()
if not readings_df.empty and not risks_df.empty:
    merged = readings_df.merge(
        risks_df[[c for c in
                  ["node_id", "score", "level", "anomaly_score", "ai_multiplier",
                   "mesh_multiplier", "correlated", "corroboration", "dominant_hazard",
                   "mesh_degree", "correlated_count",
                   "temp_sub", "humidity_sub", "aqi_sub", "water_sub", "wind_sub",
                   "pressure_sub", "explanation", "top_factors"]
                  if c in risks_df.columns]],
        on="node_id", how="left",
    )
    merged["size"] = merged["score"].clip(lower=8)

sources_present = sorted(readings_df["source"].unique()) if not readings_df.empty else []
mode = run_meta.get("mode", "simulation")
configured_source = run_meta.get("source", "simulation")
active_scenario = _active_scenario()

# --- Header + mode banner -------------------------------------------------
st.title("🌍 Climate Mesh")
st.caption("Decentralised climate monitoring & AI-powered early-warning mesh — Greater London")

banner = st.container()
with banner:
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    c1.metric("Mode", mode.upper())
    # The first question anyone with a building to look after asks is "how bad
    # is it, and where?". The configured source is still reported, in the
    # provenance line below, which reads it from the rows actually on screen.
    if not risks_df.empty:
        _worst = risks_df.iloc[0]
        c2.metric(f"Highest risk · {_worst['score']:.0f}/100 {_worst['level']}",
                  _node_name(_worst["node_id"]))
    else:
        c2.metric("Highest risk", "—")
    c3.metric("Active scenario", active_scenario.upper())
    c4.metric("Nodes online", f"{len(readings_df)}/20" if not readings_df.empty else "0/20")
    if not readings_df.empty:
        _newest = max(readings_df["timestamp"], default=None)
        _age = age_seconds(_newest) if _newest else None
        if _age is not None:
            _line = (f"Configured source: `{configured_source}` · readings updated "
                     f"**{_local_hms(_newest)}** ({age_phrase(_age)})")
            if _age > 120:
                st.warning(_line + " — this is older than two minutes. Check the "
                           "engine (`run.py`) is still running before acting on it.")
            else:
                st.caption(_line)
    if sources_present:
        st.markdown(
            "**Data source(s) in view:** " + sources_legend_html(sources_present),
            unsafe_allow_html=True)
        quality_present = (sorted(readings_df["quality_flag"].unique())
                           if not readings_df.empty else [])
        if quality_present:
            st.markdown(
                "**Reading quality in view:** "
                + "".join(quality_badge_html(q) for q in quality_present),
                unsafe_allow_html=True)
        st.caption("📡 Physical Sensor = real hardware · 🌐 Live API = Open-Meteo · "
                   "🎬 Digital Twin (Demo) = deterministic demo · 💻 Offline Simulation "
                   "= generated. Quality: ✅ ok · ≈ estimated/proxy · 🕒 stale · ⚠️ missing.")

if readings_df.empty:
    st.warning("No data yet. Start the engine in another terminal:  "
               "`python run.py --mode demo --scenario flood --judge-mode`")

# --- Sidebar --------------------------------------------------------------
with st.sidebar:
    st.header("Scenario controls")
    st.caption("Scenario deltas apply in **simulation / demo** modes only. In "
               "**api / hardware** modes the dashboard shows live values "
               "unmodified — the scenario is recorded as a label, not applied "
               "as a delta, and real values are never replaced with invented ones.")
    cols = st.columns(2)
    for i, sc in enumerate(SCENARIOS):
        if cols[i % 2].button(SCENARIO_INFO[sc]["label"], use_container_width=True,
                              type="primary" if sc == active_scenario else "secondary"):
            _write_scenario(sc)
            st.rerun()
    st.divider()
    st.header("Nodes")
    if not risks_df.empty:
        _src_by_node = (dict(zip(readings_df["node_id"], readings_df["source"]))
                        if not readings_df.empty else {})
        for _, row in risks_df.iterrows():
            icon = LEVEL_ICON.get(row["level"], "⚪")
            badge = source_badge_html(_src_by_node.get(row["node_id"], "simulation"))
            # The band word is deliberately redundant with the coloured dot:
            # red and green are exactly the pair a red-green colour-blind
            # reader cannot separate, and "62/100" on its own does not say
            # whether 62 is fine or not.
            st.markdown(
                f"{icon} **{_node_name(row['node_id'])}** — "
                f"{row['score']:.0f}/100 · {row['level']}<br>"
                f"<span style='font-size:0.75rem;color:#8a94a6'>{row['node_id']}</span>"
                f" {badge}",
                unsafe_allow_html=True)
    else:
        st.info("Waiting for data…")
    st.divider()
    offline_map = st.checkbox("Offline basemap (no map tiles)", value=False, key="offline_map",
                              help="Tick when the Pi has no internet: the Live Map then draws the "
                                   "20 labelled nodes over the main waterways instead of street tiles.")
    refresh = st.checkbox("Auto-refresh (2s)", value=True, key="auto_refresh")
    st.caption("Climate Mesh · honest by design")

# --- Tabs -----------------------------------------------------------------
tabs = st.tabs([
    "🗺️ Live Map", "📊 Network Overview", "🔬 Node Detail", "🤖 AI Explainability",
    "🧾 Evidence & Validation", "🔌 Hardware Readiness", "🏆 Competition Pitch",
])

# === LIVE MAP =============================================================
with tabs[0]:
    info = SCENARIO_INFO.get(active_scenario, {})
    st.subheader(f"Live risk map — scenario: {info.get('label', active_scenario)}")
    if info.get("blurb"):
        st.caption(info["blurb"])
    if not merged.empty:
        _act_now(merged, alerts)
        st.markdown("**Provenance of mapped nodes:** "
                    + sources_legend_html(sorted(merged["source"].unique())),
                    unsafe_allow_html=True)
        # A key that changes with the scenario/basemap remounts the chart, so the
        # WebGL map is drawn fresh instead of patched in place (an in-place
        # update after a scenario switch can leave the map canvas blank).
        st.plotly_chart(_scatter_map(merged, offline=offline_map), use_container_width=True,
                        key=f"live-map-{active_scenario}-{'offline' if offline_map else 'tiles'}")
        st.caption("Marker colour & size = risk score (green safe → red critical). "
                   "Hover a node to see its name and data source. Street tiles need "
                   "internet; tick **Offline basemap** in the sidebar for a labelled map over "
                   "the main waterways that needs no connection.")
    else:
        st.info("Map appears once the engine is running.")

# === NETWORK OVERVIEW =====================================================
with tabs[1]:
    if not merged.empty:
        avg_risk = risks_df["score"].mean()
        highest = risks_df.iloc[0]
        # "Active" = nodes currently at WARNING or CRITICAL, not a count of the
        # alert log (which grows every cooldown window while a scenario runs).
        active_alerts = int(risks_df["level"].isin(["WARNING", "CRITICAL"]).sum())
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Average risk", f"{avg_risk:.1f}/100")
        m2.metric("Highest-risk node", highest["node_id"], f"{highest['score']:.0f}/100")
        m3.metric("Active alerts", active_alerts)
        m4.metric("Avg temp / AQI", f"{readings_df['temperature'].mean():.1f}°C / "
                                    f"{readings_df['air_quality'].mean():.0f}")
        st.markdown("**Network data provenance:** "
                    + sources_legend_html(sorted(readings_df["source"].unique()))
                    + "&nbsp;&nbsp;"
                    + "".join(quality_badge_html(q)
                              for q in sorted(readings_df["quality_flag"].unique())),
                    unsafe_allow_html=True)

        cc1, cc2 = st.columns(2)
        with cc1:
            st.subheader("Risk by node")
            bar = px.bar(risks_df.sort_values("score"), x="score", y="node_id",
                         orientation="h", color="score", range_color=[0, 100],
                         color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"])
            bar.add_vline(x=60, line_dash="dash", line_color="orange",
                          annotation_text="WARNING 60", annotation_position="top",
                          annotation_font=dict(size=10, color="#c2670a"))
            bar.add_vline(x=80, line_dash="dash", line_color="red",
                          annotation_text="CRITICAL 80", annotation_position="top",
                          annotation_font=dict(size=10, color="#c0392b"))
            bar.update_layout(height=460, margin=dict(t=10, b=10))
            st.plotly_chart(bar, use_container_width=True)
        with cc2:
            st.subheader("Risk distribution")
            counts = risks_df["level"].value_counts().reindex(
                ["SAFE", "MODERATE", "WARNING", "CRITICAL"], fill_value=0)
            pie = px.pie(values=counts.values, names=counts.index,
                         color=counts.index,
                         color_discrete_map={"SAFE": "#2ecc71", "MODERATE": "#f1c40f",
                                             "WARNING": "#e67e22", "CRITICAL": "#e74c3c"})
            pie.update_layout(height=300, margin=dict(t=10, b=10))
            st.plotly_chart(pie, use_container_width=True)
            st.subheader("Weather / AQI summary")
            s1, s2, s3 = st.columns(3)
            s1.metric("Humidity", f"{readings_df['humidity'].mean():.0f}%")
            s2.metric("Wind", f"{readings_df['wind_speed'].mean():.1f} m/s")
            s3.metric("Pressure", f"{readings_df['barometric_pressure'].mean():.0f} hPa")

        st.subheader("Recent alerts")
        if alerts:
            st.caption("Each alert opens to the action playbook the engine "
                       "attached to it.")
            for a in alerts[:12]:
                icon = "🔴" if a["severity"] == "critical" else "🟠"
                ts = _local_hms(a["timestamp"])
                st.markdown(f"{icon} **[{ts}]** {_node_name(a['node_id'])} — "
                            f"{a['message']}")
                steps = playbook_for(a["alert_type"])
                if steps:
                    with st.expander(f"What to do about this {a['alert_type']} alert"):
                        for i, step in enumerate(steps, 1):
                            st.markdown(f"{i}. {step}")
        else:
            st.success("No active alerts — all nodes within safe parameters.")
    else:
        st.info("Waiting for readings…")

# === NODE DETAIL ==========================================================
with tabs[2]:
    if not readings_df.empty:
        node_id = st.selectbox("Select node", sorted(readings_df["node_id"]))
        row = readings_df[readings_df["node_id"] == node_id].iloc[0]
        rrow = risks_df[risks_df["node_id"] == node_id]
        st.markdown(f"### {row.get('node_name', node_id)}  ·  `{node_id}`")
        st.markdown(
            "**Data source:** " + source_badge_html(row["source"])
            + "&nbsp; **Quality:** " + quality_badge_html(row["quality_flag"])
            + f"&nbsp; **Scenario:** `{row['scenario']}`",
            unsafe_allow_html=True)
        if row["source"] != "hardware":
            st.caption(f"This node's values are {source_label(row['source']).lower()} — "
                       "not a physical-sensor measurement.")
        elif row["quality_flag"] == "estimated":
            st.caption("Physical sensor reading. Note: air quality and water level are "
                       "non-measured placeholders on this device, so the row is flagged "
                       "`estimated` rather than `ok`.")

        c = st.columns(4)
        c[0].metric("Temperature", f"{row['temperature']:.1f}°C")
        c[1].metric("Humidity", f"{row['humidity']:.0f}%")
        c[2].metric("Air quality", f"{row['air_quality']:.0f} AQI")
        c[3].metric("Water level", f"{row['water_level']:.2f} m")
        c = st.columns(4)
        c[0].metric("Wind speed", f"{row['wind_speed']:.1f} m/s")
        c[1].metric("Wind chill", f"{row['wind_chill']:.1f}°C")
        c[2].metric("Heat index", f"{row['heat_index']:.1f}°C")
        c[3].metric("Pressure", f"{row['barometric_pressure']:.0f} hPa")

        if not rrow.empty:
            r = rrow.iloc[0]
            st.metric("Risk score", f"{r['score']:.0f}/100", r["level"], delta_color="off")
            st.markdown(f"**Why:** {r['explanation']}")
            _note = _corroboration_line(r)
            if _note:
                st.markdown(_note)
            if r["level"] in ACTING_LEVELS:
                _hazard = str(r.get("dominant_hazard") or "risk")
                _steps = playbook_for(_hazard)
                if _steps:
                    st.markdown(f"**What to do ({_hazard})**\n\n"
                                + "\n".join(f"{i}. {step}"
                                             for i, step in enumerate(_steps, 1)))
            subs = {"Temperature": r["temp_sub"], "Humidity": r["humidity_sub"],
                    "Air quality": r["aqi_sub"], "Water level": r["water_sub"],
                    "Wind": r["wind_sub"], "Pressure": r["pressure_sub"]}
            sub_fig = px.bar(x=list(subs.keys()), y=list(subs.values()),
                             range_y=[0, 100], title="Risk breakdown by factor (0–100)",
                             labels={"x": "Factor", "y": "Sub-score (0–100)"})
            sub_fig.update_layout(height=280, margin=dict(t=40, b=10))
            st.plotly_chart(sub_fig, use_container_width=True)

        history = get_node_history(node_id, minutes=10)
        if len(history) > 1:
            hist = pd.DataFrame(history)
            hist["timestamp"] = (pd.to_datetime(hist["timestamp"], utc=True)
                                 .dt.tz_convert(datetime.now().astimezone().tzinfo))
            st.subheader("Recent history (last 10 min, local time)")
            for ch, unit in [("temperature", "°C"), ("water_level", "m"),
                             ("air_quality", "AQI"), ("barometric_pressure", "hPa")]:
                line = px.line(hist, x="timestamp", y=ch, title=f"{ch.replace('_', ' ').title()} ({unit})")
                line.update_layout(height=200, margin=dict(t=30, b=10))
                st.plotly_chart(line, use_container_width=True)
        else:
            st.caption("History accumulates as the engine runs.")
    else:
        st.info("Waiting for readings…")

# === AI EXPLAINABILITY ====================================================
with tabs[3]:
    st.subheader("Isolation Forest anomaly detection")
    _training_mode = run_meta.get("training_mode")
    if _training_mode == "historical":
        _train_desc = (
            "real ~30-day **Open-Meteo historical archive** (ERA5) hourly weather "
            "for one representative central-London point")
    elif _training_mode == "synthetic_fallback":
        _train_desc = (
            "a **deterministic synthetic** normal distribution (historical archive "
            "was requested but unavailable, so it fell back offline)")
    else:
        _train_desc = "a **deterministic synthetic** normal distribution (offline)"
    st.markdown(
        f"The model learns the *normal* multivariate shape of the data from {_train_desc}, "
        "then flags readings that are easy to isolate — catching unusual "
        "**combinations** of values before any single channel crosses a hard "
        "limit. Each alert says **why** it fired.")
    if not merged.empty:
        anomalous = merged[merged["ai_multiplier"] > 1.0].sort_values("anomaly_score", ascending=False)
        st.subheader("Nodes flagged as anomalous")
        if not anomalous.empty:
            for _, row in anomalous.head(12).iterrows():
                tags = ", ".join(row["top_factors"]) if isinstance(row["top_factors"], list) else ""
                mesh = {
                    "corroborated": f" · 🔗 corroborated by {row.get('correlated_count', 0)}"
                                    f" of {row.get('mesh_degree', 0)} neighbours",
                    "partial": f" · ◐ {row.get('correlated_count', 0)} of"
                               f" {row.get('mesh_degree', 0)} neighbours agree",
                    "uncorroborated": f" · ⚠ uncorroborated — no neighbour of"
                                      f" {row.get('mesh_degree', 0)} agrees (check the sensor)",
                    "unavailable": " · ○ cannot be corroborated (fewer than two neighbours in range)",
                }.get(row.get("corroboration"), " · isolated")
                st.markdown(
                    f"**{row['node_id']}** — anomaly {row['anomaly_score']:.2f} · "
                    f"AI ×{row['ai_multiplier']:.2f}{mesh}  \n"
                    f"<span style='color:gray'>Contributors: {tags or 'n/a'}</span>",
                    unsafe_allow_html=True)
        else:
            st.success("No anomalies detected — all readings within learned baseline.")

        st.subheader("Anomaly score distribution")
        hist = px.histogram(merged, x="anomaly_score", nbins=20,
                            color_discrete_sequence=["#6c5ce7"])
        hist.update_layout(height=280, margin=dict(t=10, b=10))
        st.plotly_chart(hist, use_container_width=True)
    else:
        st.info("Waiting for risk data…")

# === EVIDENCE & VALIDATION ================================================
with tabs[4]:
    st.subheader("Evidence & validation")
    st.markdown("Reproducible evidence for judges — every row keeps its data "
                "source and quality flag, so nothing is overstated.")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Run mode", str(run_meta.get("mode", "—")).upper())
    e2.metric("Run scenario", str(run_meta.get("scenario", "—")).upper())
    e3.metric("Judge mode", "ON" if run_meta.get("judge_mode") else "off")
    started = run_meta.get("started_at", "—")
    e4.metric("Run started", started.split("T")[0] if "T" in str(started) else str(started))

    from data.database import count_rows
    t1, t2, t3 = st.columns(3)
    t1.metric("Total readings", count_rows("sensor_readings"))
    t2.metric("Total risk scores", count_rows("risk_scores"))
    t3.metric("Total alerts", count_rows("alerts"))

    st.markdown("**Export evidence (CSV + JSON):**")
    st.code("python scripts/export_evidence.py", language="bash")
    st.caption("Writes readings.csv, risk_scores.csv, alerts.csv, source_summary.csv, "
               "run_summary.json to ./evidence/")
    st.markdown("**Run a one-command validation:**")
    st.code("python scripts/run_validation.py --mode demo --scenario flood", language="bash")

# === HARDWARE READINESS ===================================================
with tabs[5]:
    st.subheader("Hardware readiness")
    status = detect()
    # Provenance is derived from ACTUAL DATA, not driver-library presence. A
    # library being importable does NOT mean a device was read, so the badge is
    # "hardware" ONLY when a live reading actually carries source=="hardware".
    _sources_in_view = readings_df["source"].tolist() if not readings_df.empty else []
    _hardware_reading_present = "hardware" in set(_sources_in_view)
    _effective_source = effective_source_from_readings(_sources_in_view)
    st.markdown("**Current node provenance:** " + source_badge_html(_effective_source),
                unsafe_allow_html=True)
    if _hardware_reading_present:
        st.success("📡 A live reading with `source=\"hardware\"` is present — a physical "
                   "device has actually opened and returned data.")
    elif status["any_physical_sensor_detected"]:
        st.info("Driver library present — **no device read yet.** The Vernier/ADC driver "
                "library is importable, but no current reading has `source=\"hardware\"`, "
                "so the live data is still clearly-labelled simulation. A node only emits "
                "`source=\"hardware\"` once a device actually opens and returns a reading.")
    else:
        st.warning("No physical sensor detected — fallback simulation active. "
                   "The full pipeline still runs.")
    # "platform" is deliberately not shown: the full host platform string (OS
    # build, kernel, libc) is of no use to a judge and is host detail the
    # dashboard has no reason to publish. looks_like_raspberry_pi answers the
    # only question this panel actually asks.
    st.json({
        "looks_like_raspberry_pi": status["looks_like_raspberry_pi"],
        "vernier_weather_library": status["gdx_weather_available"],
        "adc_air_quality_library": status["adc_air_quality_available"],
    })
    st.markdown(
        "### Vernier adapter pathway (implemented, awaiting a device)\n"
        "- `sensors/vernier_adapter.py` already implements the hardware path. When a "
        "Vernier Go Direct Weather sensor is connected over USB, its node emits "
        "`source=\"hardware\"` readings while the rest of the mesh stays simulated.\n"
        "- Every adapter returns the **same canonical reading shape**, so no other "
        "module changes when sensors arrive.\n\n"
        "### Exact next steps when sensors arrive\n"
        "1. `pip install godirect`, then add the Vernier `gdx` helper module so "
        "`from gdx import gdx` works (see `docs/hardware_driver_setup.md`).\n"
        "2. Connect the GDX-WTHR over USB and power it on.\n"
        "3. Run `python scripts/test_hardware_read.py` to confirm a real read, then "
        "`python run.py --mode hardware` (or `--mode auto`).\n"
        "4. The configured hardware node (`CENTRAL-LDN` by default; see "
        "`data/sensor_config.json`) switches to live hardware data; compare it "
        "against the simulated/API digital twin for the same location.")

# === COMPETITION PITCH ====================================================
with tabs[6]:
    st.subheader("Climate Mesh — competition pitch")
    st.markdown(
        "**1. Real-world problem.** Official flood-zone maps say a neighbourhood is at risk, "
        "but the nearest official gauge can be kilometres away — the places most at risk "
        "are the least watched. The WMO reports that countries with limited early-warning "
        "coverage suffer nearly six times the disaster mortality of those with substantial "
        "coverage (WMO/UNDRR, *Global Status of Multi-Hazard Early Warning Systems*, 2023).\n\n"
        "**2. Technical innovation.** A decentralised mesh of 20 London nodes, an "
        "explainable Isolation Forest anomaly model, mesh correlation (nearby nodes "
        "confirming a trend escalate risk), and plain-English alerts with action playbooks.\n\n"
        "**3. Impact.** Plain-language warnings a receptionist or site manager can act on; "
        "runs offline on a single Raspberry Pi 5 with no cloud subscription.\n\n"
        "**4. What works now.** The complete pipeline — simulation, optional live "
        "Open-Meteo API data, risk scoring, alerts, dashboard, and reproducible evidence "
        "— runs today **without any physical sensors**.\n\n"
        "**5. What sensor validation adds next.** The architecture is sensor-ready: any "
        "device that outputs the standard reading format joins the mesh. Physical Vernier "
        "readings will be compared against the digital twin to validate the model.")
    st.info("Honest positioning: **sensor-ready, not sensor-dependent.** Until sensors "
            "are connected, Climate Mesh uses clearly-labelled simulated and/or API data.")

# --- Auto-refresh ---------------------------------------------------------
if refresh:
    time.sleep(2)
    st.rerun()
