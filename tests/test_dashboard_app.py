"""The dashboard must render every tab, with and without data, with no error.

Runs ``dashboard/app.py`` in Streamlit's in-process test harness against the
isolated test database. This is the check that would have caught the
Hardware Readiness tab crashing on a pandas Series whenever the engine was
running -- the two tabs after it then never rendered for a judge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.risk_engine import compute_all
from dashboard.accessibility import PALETTES, band_scale
from data.database import (
    get_latest_readings_per_node, insert_alert, insert_readings, insert_risk_score,
    record_run_start,
)
from sensors.simulated_adapter import SimulatedAdapter

APP = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
pytest.importorskip("streamlit.testing.v1")


def _render(**state):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["auto_refresh"] = False  # otherwise the page reruns forever
    at.session_state["offline_map"] = True    # tile-free map, like a Pi with no internet
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    return at


def test_dashboard_renders_with_an_empty_database():
    at = _render()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.tabs) == 7
    assert any("No data yet" in w.value for w in at.warning)


def test_dashboard_renders_every_tab_with_live_data(detector, tmp_path, monkeypatch):
    readings = SimulatedAdapter(demo=True).read_all("heatwave", tick=0.0)
    insert_readings(readings)
    results = compute_all(get_latest_readings_per_node(), detector)
    for risk in results:
        insert_risk_score(risk)
    insert_alert("BRIXTON", "heatwave", "Heat risk rising near Brixton.", "critical",
                 scenario="heatwave", playbook="(1) Open cooling spaces", source="demo")
    record_run_start("demo", "heatwave", True, "demo", "dashboard test",
                     seed=1234, commit_hash=None, training_mode="synthetic")

    at = _render()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.tabs) == 7
    page = " ".join(m.value for m in at.markdown)
    assert "Why:" in page                       # Node Detail rendered
    assert "Current node provenance" in page    # Hardware Readiness rendered
    subheaders = " ".join(h.value for h in at.subheader).lower()
    assert "competition pitch" in subheaders     # Competition Pitch rendered
    assert "low temperature" not in page
    labels = {m.label for m in at.metric}
    assert {"Mode", "Average risk", "Total readings"} <= labels


@pytest.mark.parametrize("offline", [True, False])
def test_dashboard_renders_with_accessibility_and_data(detector, offline):
    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    for risk in compute_all(get_latest_readings_per_node(), detector):
        insert_risk_score(risk)

    at = _render(cb_safe=True, large_text=True, offline_map=offline)
    assert not at.exception, [e.message for e in at.exception]
    assert at.checkbox(key="cb_safe").value
    assert at.checkbox(key="large_text").value
    assert any("font-size: 120%" in m.value for m in at.markdown)
    assert any(e.label == "Text-message alert (preview)" for e in at.expander)
    assert any("Nothing is sent" in c.value for c in at.caption)
    assert any("characters out of 160" in c.value for c in at.caption)
    assert any("Climate Mesh:" in c.value for c in at.code)

    palette = PALETTES["colour-blind safe"]
    figures = [json.loads(chart.proto.spec) for chart in at.get("plotly_chart")]
    map_figure = figures[0]
    if offline:
        markers = next(t for t in map_figure["data"] if t.get("mode") == "markers+text")
        assert markers["marker"]["colorscale"] == band_scale(palette)
    else:
        assert map_figure["layout"]["coloraxis"]["colorscale"] == band_scale(palette)
    # Node Detail also has bars for sensor factors, which are not risk bands.
    risk_chart = next(fig for fig in figures if fig["layout"].get("xaxis", {}).get(
        "title", {}).get("text") == "risk score (0–100)")
    bars = [t for t in risk_chart["data"] if t["type"] == "bar"]
    assert bars
    assert all(t["marker"]["color"] == palette[t["name"]] for t in bars)
    pie = next(t for fig in figures for t in fig["data"] if t["type"] == "pie")
    assert pie["marker"]["colors"] == [palette[band] for band in pie["labels"]]
