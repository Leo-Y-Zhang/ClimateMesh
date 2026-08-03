"""Tests for the canonical reading shape and the simulated adapter."""

from __future__ import annotations

import pytest

from config.nodes import NODES
from sensors.base import (
    MEASUREMENT_FIELDS, make_reading, validate_reading, VALID_SOURCES,
)
from sensors.simulated_adapter import SimulatedAdapter
from simulation.scenarios import SCENARIOS


def test_simulated_adapter_produces_20_nodes():
    readings = SimulatedAdapter(demo=True).read_all("normal", tick=0.0)
    assert len(readings) == 20
    assert {r["node_id"] for r in readings} == {n["node_id"] for n in NODES}


def test_every_reading_matches_canonical_shape():
    readings = SimulatedAdapter(demo=True).read_all("flood", tick=1.0)
    for r in readings:
        validate_reading(r)  # raises if malformed
        for field in MEASUREMENT_FIELDS:
            assert isinstance(r[field], (int, float))


def test_simulated_source_is_labelled_and_flagged():
    sim = SimulatedAdapter(demo=False).read_all("normal", tick=0.0)
    assert all(r["source"] == "simulation" for r in sim)
    assert all(r["is_simulated"] is True for r in sim)

    demo = SimulatedAdapter(demo=True).read_all("normal", tick=0.0)
    assert all(r["source"] == "demo" for r in demo)
    assert all(r["is_simulated"] is True for r in demo)


def test_demo_mode_is_deterministic():
    a = SimulatedAdapter(demo=True).read_all("flood", tick=0.0)
    b = SimulatedAdapter(demo=True).read_all("flood", tick=0.0)
    assert [r["temperature"] for r in a] == [r["temperature"] for r in b]


def test_make_reading_rejects_bad_source():
    node = NODES[0]
    with pytest.raises(ValueError):
        make_reading(node, temperature=15, humidity=60, air_quality=40,
                     water_level=0.3, wind_speed=4, wind_chill=15, heat_index=15,
                     barometric_pressure=1013, source="not_a_source")


def test_all_scenarios_generate_full_mesh():
    for scenario in SCENARIOS:
        readings = SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)
        assert len(readings) == 20, scenario


def test_valid_sources_constant():
    assert set(VALID_SOURCES) == {"simulation", "demo", "api", "hardware"}
