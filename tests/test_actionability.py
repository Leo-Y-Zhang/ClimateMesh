"""The dashboard must answer "so what do I do?" on the screen a reader lands on.

A walkthrough of the Live Map as a non-technical first-time reader -- the kind
of person the playbooks were written for -- failed at the last step. The red
node was easy to find; the suggested actions were computed by the engine,
stored on every alert row, and displayed nowhere. These tests pin the fix: the
action, the band word and the age of the data must all be reachable without
knowing which tab to open.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.playbooks import PLAYBOOKS, playbook_for
from backend.risk_engine import HAZARDS, compute_all
from dashboard.formatting import age_phrase, corroboration_line, node_name
from data.database import (
    get_latest_readings_per_node, get_risk_scores, insert_alert, insert_readings,
    insert_risk_score, record_run_start,
)
from sensors.simulated_adapter import SimulatedAdapter

APP = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
pytest.importorskip("streamlit.testing.v1")


def _seed(scenario: str, stuck: str | None = None) -> None:
    """Put one full frame of readings, scores and alerts in the database."""
    from ai.anomaly_model import AnomalyDetector
    readings = SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)
    if stuck is not None:
        for reading in readings:
            if reading["node_id"] == stuck:
                reading["water_level"] = 9.0
    insert_readings(readings)
    detector = AnomalyDetector().train(quiet=True)
    from backend.risk_engine import maybe_alert
    stored = get_latest_readings_per_node()
    for risk in compute_all(stored, detector):
        insert_risk_score(risk)
        reading = next(r for r in stored if r["node_id"] == risk["node_id"])
        maybe_alert(reading, risk)
    record_run_start("demo", scenario, True, "demo", "actionability test",
                     seed=1234, commit_hash=None, training_mode="synthetic")


def _render():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["auto_refresh"] = False
    at.session_state["offline_map"] = True
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _page(at) -> str:
    """Everything the reader can see as one searchable string."""
    parts = [m.value for m in at.markdown]
    parts += [c.value for c in at.caption]
    parts += [w.value for w in at.warning]
    parts += [e.value for e in at.error]
    parts += [s.value for s in at.success]
    parts += [h.value for h in at.subheader]
    return " ".join(str(p) for p in parts)


# --- the playbooks exist and are reachable --------------------------------

def test_every_alert_type_the_engine_can_raise_has_its_own_action():
    """Nothing the engine can alert on may fall through to the generic text."""
    generic = PLAYBOOKS["risk"]
    for alert_type in (*HAZARDS, "sensor-check"):
        steps = playbook_for(alert_type)
        assert steps, alert_type
        assert steps != generic, f"{alert_type} has no playbook of its own"


def test_dominant_hazard_is_stored_so_the_dashboard_can_pick_the_playbook(detector):
    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    stored = get_latest_readings_per_node()
    results = compute_all(stored, detector)
    for risk in results:
        insert_risk_score(risk)
    by_node = {r["node_id"]: r for r in get_risk_scores()}
    assert by_node, "no risk rows were written"
    for risk in results:
        assert by_node[risk["node_id"]]["dominant_hazard"] == risk["dominant_hazard"]


# --- the reader is told what to do ----------------------------------------

def test_the_first_screen_says_what_to_do_about_the_worst_node():
    _seed("flood")
    page = _page(_render())
    assert "Act now" in page
    assert "What to do" in page
    # The actual flood playbook, verbatim, not a pointer to another tab.
    assert playbook_for("flood")[0] in page


def test_a_quiet_network_says_so_instead_of_showing_nothing():
    _seed("normal")
    page = _page(_render())
    assert "Nothing to act on" in page
    assert "Act now" not in page


def test_an_uncorroborated_node_sends_the_reader_to_the_sensor_not_the_river():
    """One stuck water sensor must read as equipment to check, not a flood."""
    _seed("normal", stuck="REGENTS-CANAL")
    page = _page(_render())
    assert "No neighbour sees this" in page
    assert playbook_for("sensor-check")[0] in page
    # It must not tell anyone to run a flood evacuation on one broken sensor.
    assert playbook_for("flood")[2] not in page


# --- severity is legible without relying on colour ------------------------

def test_the_band_word_appears_beside_every_score_in_the_sidebar():
    _seed("flood")
    at = _render()
    scores = [m.value for m in at.markdown
              if "/100" in str(m.value) and "<span" in str(m.value)]
    assert scores, "the sidebar node list did not render"
    for line in scores:
        assert any(band in line
                   for band in ("SAFE", "MODERATE", "WARNING", "CRITICAL")), line


def test_the_header_names_the_highest_risk_node_and_its_band():
    """The top of the page must answer "how bad is it, and where?"."""
    _seed("flood")
    at = _render()
    worst = next((m for m in at.metric
                  if str(m.label).startswith("Highest risk")), None)
    assert worst is not None, [m.label for m in at.metric]
    assert "/100" in worst.label
    assert any(band in worst.label
               for band in ("SAFE", "MODERATE", "WARNING", "CRITICAL")), worst.label
    # It must name a node that really is at the top score. Four nodes tie at
    # 100/100 in the flood frame, so pinning one of them would pin a tie-break,
    # not the behaviour; what matters is that the header and the Act-now panel
    # below it never name different nodes (see test_audit_regressions.py).
    top_score = max(r["score"] for r in get_risk_scores())
    named = {node_name(r["node_id"]) for r in get_risk_scores()
             if r["score"] == top_score}
    assert worst.value in named, (worst.value, named)


# --- the reader can tell how old the data is ------------------------------

def test_fresh_readings_are_timestamped_on_the_page():
    _seed("flood")
    page = _page(_render())
    assert "readings updated" in page


def test_stale_readings_are_flagged_rather_than_shown_as_current():
    _seed("flood")
    from data.database import _get_conn
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    conn = _get_conn()
    conn.execute("UPDATE sensor_readings SET timestamp=?", (old,))
    conn.commit()
    page = _page(_render())
    assert "older than two minutes" in page


@pytest.mark.parametrize("seconds,expected", [
    (0, "0 s ago"), (4.4, "4 s ago"), (89, "89 s ago"),
    (90, "2 min ago"), (600, "10 min ago"),
    (5400, "1 h 30 min ago"), (7500, "2 h 05 min ago"),
    (-3, "0 s ago"),          # a clock skewed the wrong way must not read "-3 s"
])
def test_age_phrase_reads_like_a_human_wrote_it(seconds, expected):
    assert age_phrase(seconds) == expected


def test_node_names_match_the_map_labels():
    assert node_name("REGENTS-CANAL") == "Regent's Canal"
    assert node_name("NOT-A-NODE") == "NOT-A-NODE"


def test_corroboration_line_is_silent_for_a_node_nobody_needs_to_look_at():
    assert corroboration_line("quiet", 0, 4) == ""
    assert "check the equipment" in corroboration_line("uncorroborated", 0, 4)
    assert "Confirmed by the mesh" in corroboration_line("corroborated", 3, 4)


def test_alerts_carry_their_playbook_into_the_overview():
    _seed("flood")
    insert_alert("BRIXTON", "smog", "Air quality falling near Brixton.", "warning",
                 scenario="flood", playbook="(1) Reduce outdoor activity", source="demo")
    page = _page(_render())
    assert playbook_for("smog")[0] in page
