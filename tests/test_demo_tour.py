"""Tests for the one-command demo tour (scripts/demo_tour.py).

Pure helpers are tested with fabricated results (no DB). The integration
tests exercise ``run_tour`` against the per-test temp database that
``conftest.py`` pins via ``CLIMATE_MESH_DB``, so nothing touches the live
demo DB. ``scripts/`` is not a package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_tour_module():
    path = ROOT / "scripts" / "demo_tour.py"
    spec = importlib.util.spec_from_file_location("demo_tour_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dt = _load_tour_module()

_NAMES = {"n1": "Alpha Park", "n2": "Beta Brook"}


def _result(node_id: str, score: float, level: str, explanation: str = "") -> dict:
    return {"node_id": node_id, "score": score, "level": level,
            "explanation": explanation}


# --- Pure helpers -----------------------------------------------------------

def test_summarize_scenario_basic():
    results = [_result("n1", 20.0, "SAFE"),
               _result("n2", 80.0, "CRITICAL", "Flood risk rising.")]
    row = dt.summarize_scenario("flood", results, _NAMES, alerts_fired=1)
    assert row["scenario"] == "flood"
    assert row["nodes"] == 2
    assert row["avg_risk"] == 50.0
    assert row["max_risk"] == 80.0
    assert row["worst_node"] == "Beta Brook"
    assert row["worst_level"] == "CRITICAL"
    assert row["alerts"] == 1
    assert row["worst_explanation"] == "Flood risk rising."


def test_summarize_scenario_level_counts_ordered():
    results = [_result("n1", 10.0, "SAFE"), _result("n2", 65.0, "WARNING")]
    row = dt.summarize_scenario("storm", results, _NAMES, alerts_fired=0)
    assert row["levels"] == "SAFE:1 WARNING:1"


def test_summarize_scenario_empty():
    row = dt.summarize_scenario("normal", [], {}, alerts_fired=0)
    assert row["nodes"] == 0
    assert row["avg_risk"] == 0.0
    assert row["worst_node"] == ""


def test_summarize_scenario_unknown_node_falls_back_to_id():
    row = dt.summarize_scenario("smog", [_result("nX", 5.0, "SAFE")], {}, 0)
    assert row["worst_node"] == "nX"


def test_render_tour_table_contains_rows():
    rows = [dt.summarize_scenario("flood",
                                  [_result("n2", 80.0, "CRITICAL")],
                                  _NAMES, alerts_fired=2)]
    table = dt.render_tour_table(rows)
    assert "Demo Tour" in table
    assert "flood" in table
    assert "Beta Brook" in table
    assert "CRITICAL" in table
    assert "is_simulated=True" in table


def test_rows_ok():
    good = [{"nodes": 20, "avg_risk": 10.0, "max_risk": 40.0}] * 5
    assert dt.rows_ok(good, expected_scenarios=5, expected_nodes=20) is True
    assert dt.rows_ok(good, expected_scenarios=4, expected_nodes=20) is False
    bad_nodes = [{"nodes": 19, "avg_risk": 10.0, "max_risk": 40.0}] * 5
    assert dt.rows_ok(bad_nodes, expected_scenarios=5, expected_nodes=20) is False
    bad_score = [{"nodes": 20, "avg_risk": 101.0, "max_risk": 40.0}] * 5
    assert dt.rows_ok(bad_score, expected_scenarios=5, expected_nodes=20) is False
    # An empty tour must never pass when scenarios are expected.
    assert dt.rows_ok([], expected_scenarios=5, expected_nodes=20) is False


# --- Integration (uses the conftest per-test temp DB) -----------------------

def test_run_tour_covers_all_scenarios_and_stays_in_bounds():
    from simulation.scenarios import SCENARIOS

    rows = dt.run_tour()
    assert [r["scenario"] for r in rows] == list(SCENARIOS)
    for row in rows:
        assert row["nodes"] == 20
        assert 0.0 <= row["avg_risk"] <= 100.0
        assert 0.0 <= row["max_risk"] <= 100.0
        assert row["alerts"] >= 0
    assert dt.rows_ok(rows, expected_scenarios=len(SCENARIOS), expected_nodes=20)


def test_run_tour_emergency_scenarios_score_above_normal():
    rows = {r["scenario"]: r for r in dt.run_tour()}
    for scenario in ("flood", "heatwave", "smog", "storm"):
        assert rows[scenario]["avg_risk"] > rows["normal"]["avg_risk"]
        assert rows[scenario]["alerts"] >= 1


def test_run_tour_is_deterministic():
    first = dt.run_tour()
    second = dt.run_tour()
    assert first == second
