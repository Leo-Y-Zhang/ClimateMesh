"""Neighbour agreement as a two-sided trust signal.

The entry's first claim is that a single glitching sensor cannot cry wolf.
These tests are that claim: the same extreme reading must produce a hazard
alert when neighbours agree and a sensor-check when none does.
"""

from __future__ import annotations

import pytest

from ai.anomaly_model import AnomalyDetector
from backend.risk_engine import (CORROBORATED, PARTIAL, UNAVAILABLE,
                                 UNCORROBORATED, compute_all, maybe_alert)
from config.nodes import NEIGHBOURS, NODES_BY_ID
from data.database import get_alerts
from sensors.base import make_reading

STUCK_WATER = 9.0
CANAL = "REGENTS-CANAL"


@pytest.fixture(scope="module")
def detector():
    return AnomalyDetector().train(quiet=True)


def _reading(node_id: str, **over):
    values = dict(temperature=15.0, humidity=60.0, air_quality=40.0,
                  water_level=1.0, wind_speed=4.0, wind_chill=15.0,
                  heat_index=15.0, barometric_pressure=1013.0)
    values.update(over)
    return make_reading(NODES_BY_ID[node_id], source="simulation", **values)


def _mesh(stuck: set[str]):
    """A calm 20-node mesh, with `stuck` nodes reporting a flooded canal."""
    return [_reading(n, water_level=STUCK_WATER) if n in stuck else _reading(n)
            for n in NODES_BY_ID]


def test_one_stuck_sensor_does_not_raise_a_flood_alert(detector):
    result = {r["node_id"]: r for r in compute_all(_mesh({CANAL}), detector)}[CANAL]
    assert result["corroboration"] == UNCORROBORATED
    assert result["mesh_multiplier"] == 0.75
    assert result["explanation"].startswith("Check the sensor at")
    assert "possible sensor fault" in result["explanation"]
    # It is damped, not silenced: a real local event can still reach WARNING.
    assert result["score"] < 100.0


def test_the_same_reading_with_agreeing_neighbours_is_a_flood_alert(detector):
    agreeing = {CANAL, *NEIGHBOURS[CANAL][:2]}
    result = {r["node_id"]: r for r in compute_all(_mesh(agreeing), detector)}[CANAL]
    assert result["corroboration"] == CORROBORATED
    assert result["mesh_multiplier"] == 1.2
    assert result["explanation"].startswith("Flood risk rising")
    assert result["score"] > compute_all(_mesh({CANAL}), detector)[0]["score"]


def test_one_agreeing_neighbour_is_neither_escalated_nor_damped(detector):
    result = {r["node_id"]: r
              for r in compute_all(_mesh({CANAL, NEIGHBOURS[CANAL][0]}), detector)}[CANAL]
    assert result["corroboration"] == PARTIAL
    assert result["mesh_multiplier"] == 1.0


def test_an_uncorroborated_reading_alerts_as_a_sensor_check_not_the_hazard(detector):
    readings = _mesh({CANAL})
    risk = {r["node_id"]: r for r in compute_all(readings, detector)}[CANAL]
    reading = next(r for r in readings if r["node_id"] == CANAL)
    assert maybe_alert(reading, risk) is True
    alert = get_alerts(limit=5)[0]
    assert alert["alert_type"] == "sensor-check"
    assert alert["severity"] == "warning"
    assert "clear" not in alert["playbook"].lower()   # never the flood playbook
    assert "check the node" in alert["playbook"].lower()


def test_a_node_that_cannot_be_corroborated_says_so_rather_than_being_damped(detector):
    """Ilford has one neighbour within 6 km, so agreement is impossible there.

    Damping it would permanently understate a node for the accident of its
    geography, so the engine leaves it alone and reports the reason instead.
    """
    lonely = [n for n in NODES_BY_ID if len(NEIGHBOURS.get(n, [])) < 2]
    assert lonely, "the mesh no longer has a node that cannot be corroborated"
    node = lonely[0]
    result = {r["node_id"]: r
              for r in compute_all(_mesh({node}), detector)}[node]
    assert result["corroboration"] == UNAVAILABLE
    assert result["mesh_multiplier"] == 1.0
    assert result["mesh_degree"] < 2


def test_quiet_nodes_are_untouched_by_the_mesh_layer(detector):
    for result in compute_all(_mesh(set()), detector):
        assert result["corroboration"] == "quiet"
        assert result["mesh_multiplier"] == 1.0
