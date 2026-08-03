"""Tests for the risk engine: bounds, thresholds, scenario effects, mesh."""

from __future__ import annotations

from backend.risk_engine import (
    CRITICAL, MODERATE, SAFE, WARNING, calculate_base, compute_all, risk_level,
)
from sensors.simulated_adapter import SimulatedAdapter


def _readings(scenario):
    return SimulatedAdapter(demo=True).read_all(scenario, tick=0.0)


def test_risk_scores_within_bounds(detector):
    for scenario in ("normal", "flood", "heatwave", "smog", "storm"):
        for r in compute_all(_readings(scenario), detector):
            assert 0.0 <= r["score"] <= 100.0


def test_risk_level_thresholds():
    assert risk_level(0) == SAFE
    assert risk_level(29.9) == SAFE
    assert risk_level(30) == MODERATE
    assert risk_level(59.9) == MODERATE
    assert risk_level(60) == WARNING
    assert risk_level(79.9) == WARNING
    assert risk_level(80) == CRITICAL
    assert risk_level(100) == CRITICAL


def test_normal_scenario_is_mostly_safe(detector):
    results = compute_all(_readings("normal"), detector)
    avg = sum(r["score"] for r in results) / len(results)
    assert avg < 15
    assert all(r["level"] == SAFE for r in results)


def test_flood_raises_water_risk(detector):
    normal = {r["node_id"]: r for r in compute_all(_readings("normal"), detector)}
    flood = {r["node_id"]: r for r in compute_all(_readings("flood"), detector)}
    # The river nodes' water sub-score and overall score must rise under flood.
    for node_id in ("THAMES-BARRIER", "RIVER-LEA", "RIVER-WANDLE"):
        assert flood[node_id]["water_sub"] > normal[node_id]["water_sub"]
        assert flood[node_id]["score"] > normal[node_id]["score"]


def test_heatwave_raises_temperature_risk(detector):
    normal = {r["node_id"]: r for r in compute_all(_readings("normal"), detector)}
    heat = {r["node_id"]: r for r in compute_all(_readings("heatwave"), detector)}
    hot_node = "CANARY-WHARF"
    assert heat[hot_node]["temp_sub"] > normal[hot_node]["temp_sub"]
    assert heat[hot_node]["score"] > normal[hot_node]["score"]


def test_smog_raises_air_quality_risk(detector):
    normal = {r["node_id"]: r for r in compute_all(_readings("normal"), detector)}
    smog = {r["node_id"]: r for r in compute_all(_readings("smog"), detector)}
    node = "CENTRAL-LDN"
    assert smog[node]["aqi_sub"] > normal[node]["aqi_sub"]


def test_storm_raises_wind_and_pressure_risk(detector):
    normal = {r["node_id"]: r for r in compute_all(_readings("normal"), detector)}
    storm = {r["node_id"]: r for r in compute_all(_readings("storm"), detector)}
    node = "RIVER-LEA"
    assert storm[node]["wind_sub"] > normal[node]["wind_sub"]
    assert storm[node]["pressure_sub"] > normal[node]["pressure_sub"]


def test_flood_triggers_mesh_correlation(detector):
    results = compute_all(_readings("flood"), detector)
    assert any(r["correlated"] for r in results)
    # A correlated node gets the mesh multiplier applied.
    correlated = [r for r in results if r["correlated"]]
    assert all(r["mesh_multiplier"] > 1.0 for r in correlated)


def test_results_carry_explanation_and_factors(detector):
    results = compute_all(_readings("flood"), detector)
    top = max(results, key=lambda r: r["score"])
    assert top["explanation"]
    assert "Risk score" in top["explanation"]
    assert isinstance(top["top_factors"], list)


def test_calculate_base_keys(detector):
    reading = _readings("normal")[0]
    base = calculate_base(reading, detector)
    for key in ("temp_sub", "humidity_sub", "aqi_sub", "water_sub",
                "wind_sub", "pressure_sub", "ai_multiplier", "anomaly_score"):
        assert key in base


def _reading(node_id, **overrides):
    r = {
        "node_id": node_id,
        "temperature": 15.0, "humidity": 60.0, "air_quality": 40.0,
        "water_level": 0.3, "wind_speed": 4.0, "barometric_pressure": 1013.0,
        "scenario": "demo", "source": "demo", "is_simulated": True,
    }
    r.update(overrides)
    return r


def test_explanation_uses_graded_severity_language(detector):
    # A dangerous AQI and a critical water level must surface graded,
    # value-embedded contributor language, not just the plain channel names.
    reading = _reading("CENTRAL-LDN", air_quality=250.0, water_level=4.2)
    explanation = compute_all([reading], detector)[0]["explanation"]
    assert "dangerous air quality (AQI 250)" in explanation
    assert "critical water level (4.2 m)" in explanation


def test_explanation_grades_extreme_heat_with_value(detector):
    reading = _reading("CANARY-WHARF", temperature=43.0, humidity=28.0)
    explanation = compute_all([reading], detector)[0]["explanation"]
    assert "extreme heat" in explanation
    assert "43" in explanation  # the actual temperature value is embedded
