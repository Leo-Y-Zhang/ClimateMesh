"""Tests for alert generation and cooldown anti-spam behaviour."""

from __future__ import annotations

from backend.risk_engine import ALERT_COOLDOWN_SECONDS, compute_all, maybe_alert
from data.database import count_rows, get_recent_alert
from sensors.simulated_adapter import SimulatedAdapter


def _flood_risk(detector):
    readings = SimulatedAdapter(demo=True).read_all("flood", tick=0.0)
    results = {r["node_id"]: r for r in compute_all(readings, detector)}
    # Pick the highest-scoring node so we know an alert is warranted.
    top_id = max(results, key=lambda k: results[k]["score"])
    reading = next(r for r in readings if r["node_id"] == top_id)
    return reading, results[top_id]


def test_alert_fires_for_critical(detector):
    reading, risk = _flood_risk(detector)
    assert risk["level"] in ("WARNING", "CRITICAL")
    assert maybe_alert(reading, risk) is True
    assert count_rows("alerts") == 1


def test_cooldown_suppresses_duplicate(detector):
    reading, risk = _flood_risk(detector)
    assert maybe_alert(reading, risk) is True
    # Immediately re-firing the same severity is suppressed by the cooldown.
    assert maybe_alert(reading, risk) is False
    assert count_rows("alerts") == 1


def test_severity_change_fires_new_alert(detector):
    reading, risk = _flood_risk(detector)
    warning = dict(risk, level="WARNING", score=65.0)
    assert maybe_alert(reading, warning) is True
    critical = dict(risk, level="CRITICAL", score=90.0)
    # Severity escalated within the cooldown window -> a new alert still fires.
    assert maybe_alert(reading, critical) is True
    assert count_rows("alerts") == 2


def test_safe_and_moderate_never_alert(detector):
    reading, risk = _flood_risk(detector)
    assert maybe_alert(reading, dict(risk, level="SAFE", score=10.0)) is False
    assert maybe_alert(reading, dict(risk, level="MODERATE", score=45.0)) is False
    assert count_rows("alerts") == 0


def test_recent_alert_window(detector):
    reading, risk = _flood_risk(detector)
    maybe_alert(reading, risk)
    found = get_recent_alert(reading["node_id"], risk["dominant_hazard"],
                             ALERT_COOLDOWN_SECONDS)
    assert found is not None
