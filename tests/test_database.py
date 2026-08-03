"""Tests for database insert/read round-trips and helpers."""

from __future__ import annotations

from data.database import (
    count_rows, fetch_all, get_alerts, get_latest_readings_per_node,
    get_node_history, get_risk_scores, insert_alert, insert_reading,
    insert_risk_score,
)
from sensors.simulated_adapter import SimulatedAdapter
from backend.risk_engine import compute_all


def test_insert_and_read_reading_roundtrip():
    reading = SimulatedAdapter(demo=True).read_all("normal", tick=0.0)[0]
    insert_reading(reading)
    latest = get_latest_readings_per_node()
    assert len(latest) == 1
    stored = latest[0]
    assert stored["node_id"] == reading["node_id"]
    assert stored["source"] == reading["source"]
    assert stored["is_simulated"] == 1
    assert abs(stored["temperature"] - reading["temperature"]) < 1e-6


def test_latest_reading_per_node_returns_one_per_node():
    adapter = SimulatedAdapter(demo=True)
    for tick in range(3):
        for r in adapter.read_all("normal", tick=float(tick)):
            insert_reading(r)
    latest = get_latest_readings_per_node()
    assert len(latest) == 20  # one row per node despite 3 inserts each
    assert count_rows("sensor_readings") == 60


def test_insert_and_read_risk_score(detector):
    readings = SimulatedAdapter(demo=True).read_all("flood", tick=0.0)
    for r in readings:
        insert_reading(r)
    for risk in compute_all(get_latest_readings_per_node(), detector):
        insert_risk_score(risk)
    scores = get_risk_scores()
    assert len(scores) == 20
    assert all(isinstance(s["top_factors"], list) for s in scores)
    assert all(0 <= s["score"] <= 100 for s in scores)


def test_alerts_insert_and_fetch():
    insert_alert("CENTRAL-LDN", "flood", "test message", "critical",
                 scenario="flood", playbook="(1) do thing")
    alerts = get_alerts()
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "flood"
    assert alerts[0]["playbook"]


def test_alert_carries_provenance():
    # Each alert self-labels its provenance (source + is_simulated) like a
    # reading, so a screenshot/export never mistakes a simulated alert for a
    # physical-sensor event. Defaults are the safe (simulated) ones.
    insert_alert("CENTRAL-LDN", "flood", "default provenance", "warning")
    insert_alert("THAMES-BARRIER", "flood", "explicit hardware", "critical",
                 scenario="observed", playbook="(1) act", source="hardware",
                 is_simulated=False)
    alerts = {a["node_id"]: a for a in get_alerts()}
    assert alerts["CENTRAL-LDN"]["source"] == "simulation"
    assert alerts["CENTRAL-LDN"]["is_simulated"] == 1
    assert alerts["THAMES-BARRIER"]["source"] == "hardware"
    assert alerts["THAMES-BARRIER"]["is_simulated"] == 0


def test_node_history_returns_inserted_rows():
    adapter = SimulatedAdapter(demo=True)
    for tick in range(4):
        insert_reading(adapter.read_all("normal", tick=float(tick))[0])
    node_id = adapter.read_all("normal", tick=0.0)[0]["node_id"]
    history = get_node_history(node_id, minutes=60)
    assert len(history) == 4


def test_fetch_all_rejects_unknown_table():
    import pytest
    with pytest.raises(ValueError):
        fetch_all("drop_me")
