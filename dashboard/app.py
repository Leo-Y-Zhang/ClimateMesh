"""Streamlit dashboard for Climate Mesh.

Seven tabs (Live Map, Network Overview, Node Detail, AI Explainability,
Evidence & Validation, Hardware Readiness, Competition Pitch). The dashboard is
a pure *reader* of the shared SQLite database — the engine process (``run.py``)
writes; this displays. Data-source labels and the active mode are shown
prominently so nobody mistakes simulated or API data for physical-sensor data.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.playbooks import playbook_for
from config.nodes import NODES
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

st.set_page_config(page_title="Climate Mesh", page_icon="🌍", layout="wide")
init_db()

LEVEL_ICON = {"SAFE": "🟢", "MODERATE": "🟡", "WARNING": "🟠", "CRITICAL": "🔴"}


def _write_scenario(scenario: str) -> None:
    DEMO_CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_CONTROL_PATH.write_text(json.dumps({"scenario": scenario}))


def _active_scenario() -> str:
    try:
        if DEMO_CONTROL_PATH.exists():
            return json.loads(DEMO_CONTROL_PATH.read_text()).get("scenario") or "normal"
    except (json.JSONDecodeError, OSError):
        pass
    return "normal"


def _scatter_map(df: pd.DataFrame):
    """Build a risk-coloured map, tolerating both old and new plotly APIs."""
    common = dict(
        lat="latitude", lon="longitude", color="score", size="size",
        color_continuous_scale=["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"],
        range_color=[0, 100], size_max=22, zoom=9,
        center={"lat": 51.50, "lon": -0.11}, hover_name="node_name",
        hover_data={"node_id": True, "level": True, "score": ":.0f",
                    "source": True, "latitude": False, "longitude": False, "size": False},
    )
    try:  # plotly >= 5.24 (maplibre)
        fig = px.scatter_map(df, map_style="carto-positron-nolabels", **common)
    except AttributeError:  # older plotly (mapbox)
        fig = px.scatter_mapbox(df, mapbox_style="carto-positron-nolabels", **common)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=0, b=0))
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
        risks_df[["node_id", "score", "level", "anomaly_score", "ai_multiplier",
                  "mesh_multiplier", "correlated", "temp_sub", "humidity_sub",
                  "aqi_sub", "water_sub", "wind_sub", "pressure_sub",
                  "explanation", "top_factors"]],
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
    c2.metric("Data source", configured_source.upper())
    c3.metric("Active scenario", active_scenario.upper())
    c4.metric("Nodes online", f"{len(readings_df)}/20" if not readings_df.empty else "0/20")
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
            st.markdown(
                f"{icon} **{row['node_id']}** — {row['score']:.0f}/100<br>{badge}",
                unsafe_allow_html=True)
    else:
        st.info("Waiting for data…")
    st.divider()
    refresh = st.checkbox("Auto-refresh (2s)", value=True)
    st.caption("Climate Mesh v2.0 · honest by design")

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
        st.markdown("**Provenance of mapped nodes:** "
                    + sources_legend_html(sorted(merged["source"].unique())),
                    unsafe_allow_html=True)
        st.plotly_chart(_scatter_map(merged), use_container_width=True)
        st.caption("Marker colour & size = risk score (green safe → red critical). "
                   "Hover a node to see its data source.")
    else:
        st.info("Map appears once the engine is running.")

# === NETWORK OVERVIEW =====================================================
with tabs[1]:
    if not merged.empty:
        avg_risk = risks_df["score"].mean()
        highest = risks_df.iloc[0]
        active_alerts = len([a for a in alerts if a["severity"] in ("warning", "critical")])
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
            bar.add_vline(x=60, line_dash="dash", line_color="orange")
            bar.add_vline(x=80, line_dash="dash", line_color="red")
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
            for a in alerts[:12]:
                icon = "🔴" if a["severity"] == "critical" else "🟠"
                ts = a["timestamp"].split("T")[1][:8] if "T" in a["timestamp"] else a["timestamp"]
                st.markdown(f"{icon} **[{ts}]** `{a['node_id']}` — {a['message']}")
        else:
            st.success("No active alerts — all nodes within safe parameters.")
    else:
        st.info("Waiting for sensor data…")

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
            st.metric("Risk score", f"{r['score']:.0f}/100", r["level"])
            st.markdown(f"**Why:** {r['explanation']}")
            subs = {"Temperature": r["temp_sub"], "Humidity": r["humidity_sub"],
                    "Air quality": r["aqi_sub"], "Water level": r["water_sub"],
                    "Wind": r["wind_sub"], "Pressure": r["pressure_sub"]}
            sub_fig = px.bar(x=list(subs.keys()), y=list(subs.values()),
                             range_y=[0, 100], title="Risk breakdown by factor (0–100)")
            sub_fig.update_layout(height=280, margin=dict(t=40, b=10))
            st.plotly_chart(sub_fig, use_container_width=True)

        history = get_node_history(node_id, minutes=10)
        if len(history) > 1:
            hist = pd.DataFrame(history)
            hist["timestamp"] = pd.to_datetime(hist["timestamp"])
            st.subheader("Recent history (last 10 min)")
            for ch, unit in [("temperature", "°C"), ("water_level", "m"),
                             ("air_quality", "AQI"), ("barometric_pressure", "hPa")]:
                line = px.line(hist, x="timestamp", y=ch, title=f"{ch.replace('_', ' ').title()} ({unit})")
                line.update_layout(height=200, margin=dict(t=30, b=10))
                st.plotly_chart(line, use_container_width=True)
        else:
            st.caption("History accumulates as the engine runs.")
    else:
        st.info("Waiting for sensor data…")

# === AI EXPLAINABILITY ====================================================
with tabs[3]:
    st.subheader("Isolation Forest anomaly detection")
    _training_mode = run_meta.get("training_mode")
    if _training_mode == "historical":
        _train_desc = (
            "real ~30-day **Open-Meteo historical archive** (ERA5) hourly weather "
            "for the Greater London area")
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
                mesh = " · 🔗 mesh-correlated" if row.get("correlated") else " · isolated"
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
    _sources_in_view = readings_df["source"] if not readings_df.empty else []
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
    st.json({
        "platform": status["platform"],
        "looks_like_raspberry_pi": status["looks_like_raspberry_pi"],
        "vernier_weather_library": status["gdx_weather_available"],
        "adc_air_quality_library": status["adc_air_quality_available"],
    })
    st.markdown(
        "### Planned Vernier adapter pathway\n"
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
        "**1. Real-world problem.** Flood-zone maps put the local area at risk, but the nearest "
        "official gauge is kilometres away — the areas most at risk aren't being watched. "
        "Over 90% of weather-related deaths since 1970 occurred where early-warning "
        "coverage was inadequate (WMO; figure not independently verified).\n\n"
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
