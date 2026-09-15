"""Pins what the AI and mesh layers add on the deterministic demo frames.

The write-up publishes, per scenario, how many nodes sit in each band with the
sub-scores alone and with the AI and mesh multipliers applied. Those counts
are the evidence that the layers only ever amplify a hazard the sub-scores
already see (normal stays 20 SAFE) and do hazard-specific work in emergencies.
"""

from __future__ import annotations

from collections import Counter

import pytest

from backend.risk_engine import calculate_base, compute_all, risk_level
from sensors.simulated_adapter import SimulatedAdapter

EXPECTED = {
    #             sub-scores only                                    with AI + mesh
    "normal":   ({"SAFE": 20},                                       {"SAFE": 20}),
    "flood":    ({"CRITICAL": 4, "MODERATE": 8, "SAFE": 8},          {"CRITICAL": 4, "WARNING": 6, "MODERATE": 2, "SAFE": 8}),
    "heatwave": ({"CRITICAL": 8, "WARNING": 4, "MODERATE": 8},       {"CRITICAL": 11, "WARNING": 1, "MODERATE": 8}),
    "smog":     ({"CRITICAL": 12, "MODERATE": 8},                    {"CRITICAL": 12, "WARNING": 3, "MODERATE": 5}),
    "storm":    ({"CRITICAL": 5, "WARNING": 15},                     {"CRITICAL": 19, "WARNING": 1}),
}


@pytest.mark.parametrize("scenario", list(EXPECTED))
def test_band_counts_with_and_without_the_layers(detector, scenario):
    readings = SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)
    subs_only = Counter(risk_level(calculate_base(r, detector)["base_score"]) for r in readings)
    with_layers = Counter(r["level"] for r in compute_all(readings, detector))
    expected_subs, expected_full = EXPECTED[scenario]
    assert dict(subs_only) == expected_subs
    assert dict(with_layers) == expected_full


def test_layers_never_lower_a_band(detector):
    order = ["SAFE", "MODERATE", "WARNING", "CRITICAL"]
    for scenario in EXPECTED:
        readings = SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)
        base = {r["node_id"]: risk_level(calculate_base(r, detector)["base_score"]) for r in readings}
        for r in compute_all(readings, detector):
            assert order.index(r["level"]) >= order.index(base[r["node_id"]])


def test_worked_examples_in_the_writeup(detector):
    flood = {r["node_id"]: r for r in compute_all(SimulatedAdapter(demo=True).read_all("flood", tick=0.0), detector)}
    hyde = flood["HYDE-PARK"]
    assert hyde["mesh_multiplier"] == 1.2 and hyde["correlated_count"] == 4
    assert hyde["score"] == 69.6 and hyde["level"] == "WARNING"
    canal = flood["REGENTS-CANAL"]
    assert canal["score"] == 100.0 and canal["level"] == "CRITICAL"
    heat = {r["node_id"]: r for r in compute_all(SimulatedAdapter(demo=True).read_all("heatwave", tick=0.0), detector)}
    lew = heat["LEWISHAM"]
    assert lew["ai_multiplier"] == 1.26 and lew["mesh_multiplier"] == 1.2
    assert lew["score"] == 99.5 and lew["level"] == "CRITICAL"
