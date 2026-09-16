"""The evaluation numbers quoted in §6, pinned.

The write-up's central measured claim is that thresholds alone raise a false
flood alert every time one water sensor jams, and the shipped system raises
none. Those two numbers are load-bearing, so they are a test rather than a
figure somebody once ran.
"""

from __future__ import annotations

import pytest

from ai.anomaly_model import AnomalyDetector
from backend.risk_engine import (UNCORROBORATED, CRITICAL, WARNING,
                                 calculate_base, compute_all, risk_level)
from config.nodes import NODES
from sensors.base import make_reading
from simulation.engine import generate_channels

STUCK_WATER_M = 9.0
ALERTING = (WARNING, CRITICAL)
STUCK_NODES = ("REGENTS-CANAL", "RIVER-LEA", "PUTNEY")
SEEDS = range(1000, 1010)


def _frame(seed: int, stuck: str):
    readings = []
    for node in NODES:
        values = generate_channels(node, 0.0, "none", deterministic=False, seed=seed)
        if node["node_id"] == stuck:
            values["water_level"] = STUCK_WATER_M
        readings.append(make_reading(node, source="simulation", **values))
    return readings


@pytest.fixture(scope="module")
def detector():
    return AnomalyDetector().train(quiet=True)


def test_thresholds_alone_cry_wolf_every_time_a_sensor_jams(detector):
    """The baseline the write-up compares against: 100 % false flood alerts."""
    cried = 0
    for seed in SEEDS:
        for stuck in STUCK_NODES:
            readings = _frame(seed, stuck)
            verdicts = detector.predict_many(readings)
            bases = [calculate_base(r, detector, v)
                     for r, v in zip(readings, verdicts)]
            if any(risk_level(round(b["base_score"], 1)) in ALERTING
                   and b["dominant_hazard"] == "flood" for b in bases):
                cried += 1
    assert cried == len(SEEDS) * len(STUCK_NODES)


def test_the_shipped_system_never_does(detector):
    """And the claim: 0 % — a sensor-check instead, every time."""
    cried, checks = 0, 0
    for seed in SEEDS:
        for stuck in STUCK_NODES:
            results = compute_all(_frame(seed, stuck), detector)
            if any(r["level"] in ALERTING and r["corroboration"] != UNCORROBORATED
                   and r["dominant_hazard"] == "flood" for r in results):
                cried += 1
            if any(r["corroboration"] == UNCORROBORATED
                   and r["node_id"] == stuck for r in results):
                checks += 1
    assert cried == 0
    assert checks == len(SEEDS) * len(STUCK_NODES)


def test_a_full_intensity_event_is_still_detected(detector):
    """The cost side: full-strength events must still be caught, every time."""
    from sensors.simulated_adapter import SimulatedAdapter

    adapter = SimulatedAdapter(demo=True)
    for scenario, hazard in (("flood", "flood"), ("heatwave", "heatwave"),
                             ("smog", "smog"), ("storm", "storm")):
        results = compute_all(adapter.read_all(scenario, tick=0.0), detector)
        assert any(r["level"] in ALERTING
                   and r["corroboration"] != UNCORROBORATED
                   and r["dominant_hazard"] == hazard for r in results), scenario
