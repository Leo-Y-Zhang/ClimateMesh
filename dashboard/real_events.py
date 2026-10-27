"""Display committed replay evidence independently of the live database."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.badges import source_quality_badges_html
from scripts.fetch_history import EVENTS
from simulation.replay_io import read_json

ROOT = Path(__file__).resolve().parent.parent
CAPTIONS = {
    "flood-2021-07-12": (
        "London flash floods, 12 July 2021. Hourly Open-Meteo gridded reanalysis "
        "(roughly 9–11 km) smooths local convective storms. The gauges variant substitutes "
        "EA 15-minute rainfall summed to local hours only for all-Good gauges within 3 km "
        "of a node; that distance rule is a modelling choice. Water level remains a rainfall "
        "proxy. The UTC gauge request omits the first BST hour; empty hourly sums are not "
        "evidence of dry weather. This is a retrospective replay, not a forecast or field validation."),
    "heat-2022-07-19": (
        "UK record heat, 18–19 July 2022. Recorded hourly Open-Meteo gridded reanalysis "
        "at roughly 9–11 km supplies weather and archived air quality where available. "
        "Grid-cell temperatures cannot establish a street-level or national station record. "
        "Water level remains a rainfall proxy, and unavailable AQI uses the live adapter's "
        "labelled estimate. This is a retrospective replay, not a forecast or field validation."),
    "storm-2022-02-18": (
        "Storm Eunice, 18 February 2022. Recorded hourly Open-Meteo gridded reanalysis "
        "at roughly 9–11 km supplies wind speed and pressure. The risk engine "
        "scores sustained 10 m wind, not the archived gusts; hourly grid values cannot resolve "
        "local gust damage. Water level remains a rainfall proxy and unavailable AQI uses "
        "the live fallback estimate. This is a retrospective replay, not a forecast or field validation."),
}

for event, (start, end, title) in EVENTS.items():
    if event.startswith("holdout"):
        CAPTIONS[event] = (f"{title}, {start} to {end}. Fixed before calibration: all 20 nodes, "
                           "with a separate preceding-30-day training window. Recorded gridded "
                           "weather, estimated rainfall-to-water proxy; retrospective, not field validation.")


def render_real_events(scatter_map, colours):
    st.subheader("Real events — recorded hourly replay")
    event = st.selectbox("Recorded event", list(CAPTIONS))
    variants = ("grid", "gauges") if event.startswith("flood") else ("grid",)
    variant = st.selectbox("Replay variant", variants)
    st.markdown(source_quality_badges_html("archive", "estimated"), unsafe_allow_html=True)
    st.caption(CAPTIONS[event])
    path = ROOT / "evidence" / "replay" / f"{event}-{variant}.json"
    if not path.exists() and not Path(str(path) + ".gz").exists():
        st.info("Generate the recorded replay outputs:")
        st.code("python scripts/replay_event.py --all\npython scripts/calibration_report.py\n"
                "python scripts/replay_figures.py", language="bash")
        return
    payload = read_json(path)
    i = st.slider("Recorded hour (Europe/London)", 0, len(payload["per_hour"]) - 1, 0)
    step = payload["per_hour"][i]
    st.write(step["hour"])
    frame = pd.DataFrame(step["nodes"])
    frame["size"] = frame["score"].clip(lower=8)
    st.plotly_chart(scatter_map(frame, offline=True, colours=colours), use_container_width=True,
                    key=f"recorded-map-{event}-{variant}-{i}")
    st.caption(payload["clock_policy"])
    figure_name = (f"{event}-hero.png" if event.startswith("flood") else
                   "calibration-before-after.png" if event.startswith("holdout") else f"{event}.png")
    figure = ROOT / "evidence" / "replay" / "figures" / figure_name
    if figure.exists():
        st.image(str(figure), use_container_width=True)
    else:
        st.code("python scripts/replay_figures.py", language="bash")
