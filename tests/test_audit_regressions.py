"""One test per defect found by the final pre-submission audit.

Each of these was reproduced against the running dashboard before it was
fixed. Three of them took the whole page down -- every tab, replaced by a
traceback -- and one told a reader to run a flood evacuation on a sensor the
same screen had just called broken.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from backend.playbooks import playbook_for
from backend.risk_engine import alert_type_for, compute_all
from config.nodes import NODES_BY_ID, neighbours_of
from dashboard.formatting import corroboration_line, score_text
from data.database import (
    _get_conn, get_latest_readings_per_node, get_risk_scores, insert_readings,
    insert_risk_score,
)
from sensors.simulated_adapter import SimulatedAdapter

APP = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
pytest.importorskip("streamlit.testing.v1")


def _render():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["auto_refresh"] = False
    at.session_state["offline_map"] = True
    at.run()
    return at


def _page(at) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [w.value for w in at.warning] + [e.value for e in at.error]
    parts += [s.value for s in at.success]
    return " ".join(str(p) for p in parts)


def _stuck_frame(node_id: str, scenario: str = "normal", metres: float = 9.0):
    """Seed one node whose water sensor is jammed, everything else calm."""
    from ai.anomaly_model import AnomalyDetector
    from backend.risk_engine import maybe_alert

    readings = SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)
    for reading in readings:
        if reading["node_id"] == node_id:
            reading["water_level"] = metres
    insert_readings(readings)
    stored = get_latest_readings_per_node()
    for risk in compute_all(stored, AnomalyDetector().train(quiet=True)):
        insert_risk_score(risk)
        maybe_alert(next(r for r in stored if r["node_id"] == risk["node_id"]), risk)


# --- 1. the playbook a broken sensor gets --------------------------------

def test_one_decision_about_which_playbook_a_node_gets():
    """The engine, the Live Map and Node Detail must not disagree."""
    assert alert_type_for({"corroboration": "uncorroborated",
                           "dominant_hazard": "flood"}) == "sensor-check"
    assert alert_type_for({"corroboration": "corroborated",
                           "dominant_hazard": "flood"}) == "flood"
    assert alert_type_for({"corroboration": "quiet",
                           "dominant_hazard": "nonsense"}) == "risk"
    assert alert_type_for({}) == "risk"


def test_node_detail_never_sends_a_reader_to_the_river_for_a_broken_sensor():
    """The default-selected node is the one the audit caught this on."""
    first_alphabetically = sorted(NODES_BY_ID)[0]
    _stuck_frame(first_alphabetically)
    risk = next(r for r in get_risk_scores() if r["node_id"] == first_alphabetically)
    assert risk["corroboration"] == "uncorroborated", risk["corroboration"]
    page = _page(_render())
    assert "check the equipment" in page
    # The flood playbook's evacuation step must appear nowhere on this page.
    assert playbook_for("flood")[2] not in page
    assert playbook_for("sensor-check")[0] in page


def test_the_act_now_panel_ignores_a_full_alert_log():
    """A storm elsewhere must not push this node's sensor-check out of view.

    The panel used to read the newest 40 alert rows and fall back to the
    hazard when it could not find one, which is the hazard it had just damped.
    """
    from data.database import insert_alert

    node_id = sorted(NODES_BY_ID)[0]
    _stuck_frame(node_id)
    for i in range(60):
        insert_alert("GREENWICH", "storm", f"filler {i}", "warning", source="demo")
    page = _page(_render())
    assert "sensor-check" in page
    assert playbook_for("flood")[2] not in page


# --- 3 and 4. states that used to replace the page with a traceback -------

def test_readings_without_risk_rows_do_not_kill_the_page():
    """The database is in this state for the first seconds of every run."""
    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    at = _render()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.tabs) == 7


def test_a_half_written_risk_frame_does_not_kill_the_page(detector):
    """Plotly refuses a NaN marker size and takes every tab with it."""
    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    stored = get_latest_readings_per_node()
    for risk in compute_all(stored, detector)[:7]:   # only 7 of 20 scored
        insert_risk_score(risk)
    at = _render()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.tabs) == 7


def test_rows_written_before_the_mesh_columns_existed_do_not_kill_the_page(detector):
    """NaN is truthy, so `value or 0` never fired and int(NaN) raised."""
    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    stored = get_latest_readings_per_node()
    for risk in compute_all(stored, detector):
        insert_risk_score(risk)
    conn = _get_conn()
    conn.execute("UPDATE risk_scores SET corroboration=NULL, mesh_degree=NULL, "
                 "correlated_count=NULL, dominant_hazard=NULL")
    conn.commit()
    at = _render()
    assert not at.exception, [e.message for e in at.exception]


# --- 5. two sentences about the same fact --------------------------------

def test_a_node_with_one_neighbour_is_described_truthfully(detector):
    """Ilford has exactly one neighbour, so "no other node" was false."""
    lonely = [n for n in NODES_BY_ID if len(neighbours_of(n)) == 1]
    assert lonely, "no single-neighbour node to test"
    line = corroboration_line("unavailable", 0, 1)
    assert "1 other node lies within 6 km" in line, line
    assert "node(s)" not in line
    assert corroboration_line("unavailable", 0, 0).startswith(
        "ℹ️ **Cannot be corroborated** — no other node lies")


# --- 7. the digits shown must match the digits the band came from --------

@pytest.mark.parametrize("score,shown", [
    (79.8, "79/100"), (80.0, "80/100"), (59.99, "59/100"), (0.0, "0/100"),
    (100.0, "100/100"), (3.9, "3/100"),
])
def test_a_score_is_never_displayed_above_its_own_band_boundary(score, shown):
    assert score_text(score) == shown
    assert math.floor(score) == int(shown.split("/")[0])


def test_score_text_survives_a_missing_score():
    assert score_text(None) == "—/100"


# --- 8. the header and the panel describe the same set of nodes ----------

def test_the_header_and_the_act_now_panel_never_name_different_nodes(detector):
    """They read the same frame, so a node in one is a node in the other."""
    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    stored = get_latest_readings_per_node()
    for risk in compute_all(stored, detector):
        insert_risk_score(risk)
    # Lose one node's reading, keeping its (top) risk row: the header used to
    # read risk rows and the panel the join, so they named different nodes.
    conn = _get_conn()
    top = get_risk_scores()[0]["node_id"]
    conn.execute("DELETE FROM sensor_readings WHERE node_id=?", (top,))
    conn.commit()
    at = _render()
    assert not at.exception, [e.message for e in at.exception]
    header = next(m for m in at.metric if str(m.label).startswith("Highest risk"))
    named_in_panel = [e.value for e in at.error] + [w.value for w in at.warning]
    acting = " ".join(str(v) for v in named_in_panel)
    if "Act now" in acting:
        assert header.value in acting, (header.value, acting)


# --- the AI claim a judge will attack first ------------------------------

def test_the_ai_catches_combinations_no_single_channel_threshold_would():
    """§3's claim that the model is not reducible to a per-channel threshold.

    A judge's first question about any "AI" in a schools entry is whether it
    earns its place or is a threshold in a hat. This draws readings whose every
    channel sits inside 2.5 standard deviations of the learned normal -- that
    is, nothing any per-channel rule would ever flag -- and asserts the
    Isolation Forest still finds unusual *combinations* among them.
    """
    import numpy as np

    from ai.anomaly_model import AnomalyDetector, FEATURES

    model = AnomalyDetector().train(quiet=True)
    mean, spread = model._feat_mean, model._feat_std
    rng = np.random.default_rng(11)
    grid = rng.normal(mean, spread * 1.15, size=(20000, len(FEATURES)))
    inside = grid[(np.abs((grid - mean) / spread) < 2.5).all(axis=1)]
    assert len(inside) > 5000, len(inside)

    verdicts = model.predict_many([dict(zip(FEATURES, row)) for row in inside])
    flagged = sum(1 for v in verdicts if v["is_anomaly"])
    assert flagged > 0, (
        "every anomaly the model found also broke a 2.5-sigma per-channel "
        "bound, which would make the Isolation Forest decorative"
    )
    # Not a fluke of one draw, and not so trigger-happy it flags normality.
    assert 0.001 < flagged / len(inside) < 0.25, flagged / len(inside)
