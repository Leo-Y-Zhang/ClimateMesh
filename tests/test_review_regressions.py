"""Regression tests for the pre-submission review fixes.

Each test pins a behaviour a judge could otherwise catch on screen: the wording
of explanations, the direction-aware hazard names, the NOAA heat index, NaN
safety, score/band agreement, honest API fallbacks, the auto-mode chain, judge
mode's determinism, the stale-reading path, and the exact demo-tour numbers the
README quotes. No network and no hardware are used.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

import run
from backend import playbooks
from backend.risk_engine import (
    HAZARDS, _contributor_phrase, calculate_base, compute_all, maybe_alert, risk_level,
)
from sensors import api_adapter, create_adapter
from sensors.api_adapter import ApiAdapter, ApiUnavailable
from sensors.simulated_adapter import SimulatedAdapter
from simulation.engine import _heat_index

ROOT = Path(__file__).resolve().parent.parent


def _reading(node_id="CENTRAL-LDN", **overrides):
    r = {
        "node_id": node_id,
        "temperature": 15.0, "humidity": 60.0, "air_quality": 40.0,
        "water_level": 0.3, "wind_speed": 4.0, "barometric_pressure": 1013.0,
        "scenario": "demo", "source": "demo", "is_simulated": True,
    }
    r.update(overrides)
    return r


# --- Explanation wording ------------------------------------------------------

def test_warm_temperatures_are_never_called_low():
    for t in (24.0, 26.5, 28.0, 29.9):
        phrase = _contributor_phrase("temperature", {"temperature": t})
        assert "low temperature" not in phrase, phrase
        assert phrase.startswith("warm temperature")


def test_heatwave_demo_never_prints_low_temperature(detector):
    # The exact judge-mode frame: every explanation must read sensibly.
    results = compute_all(SimulatedAdapter(demo=True).read_all("heatwave", tick=0.0), detector)
    for r in results:
        assert "low temperature" not in r["explanation"], r["explanation"]


# --- Direction-aware hazards ------------------------------------------------

def test_cold_snap_is_a_cold_hazard_not_a_heatwave(detector):
    base = calculate_base(_reading(temperature=-5.0), detector)
    assert base["dominant_hazard"] == "cold"
    result = compute_all([_reading(temperature=-5.0)], detector)[0]
    assert result["explanation"].startswith("Cold risk rising")
    assert maybe_alert(_reading(temperature=-5.0), result) is True


def test_very_dry_air_is_not_a_flood_signal(detector):
    base = calculate_base(_reading(humidity=8.0), detector)
    assert base["dominant_hazard"] != "flood"


def test_every_hazard_has_a_playbook_and_headline():
    for hazard in HAZARDS:
        assert playbooks.playbook_for(hazard), hazard
        assert playbooks.playbook_text(hazard).startswith("(1)")


# --- Heat index --------------------------------------------------------------

@pytest.mark.parametrize("temp,rh,lo,hi", [
    (26.0, 65.0, 26.0, 27.5),   # a mild day must not "feel like" 40 °C
    (30.0, 40.0, 29.0, 31.0),
    (36.0, 35.0, 36.5, 38.5),
    (40.0, 60.0, 55.0, 66.0),   # genuinely dangerous humidity + heat
])
def test_heat_index_matches_noaa_scale(temp, rh, lo, hi):
    assert lo <= _heat_index(temp, rh) <= hi


def test_heat_index_never_below_air_temperature():
    for t, rh in ((20.0, 90.0), (26.0, 10.0), (33.0, 20.0)):
        assert _heat_index(t, rh) >= t


# --- NaN safety --------------------------------------------------------------

def test_non_finite_values_score_zero_not_critical(detector):
    nan_reading = _reading(temperature=float("nan"), humidity=float("nan"))
    base = calculate_base(nan_reading, detector)
    assert base["temp_sub"] == 0.0
    assert base["humidity_sub"] == 0.0
    result = compute_all([nan_reading], detector)[0]
    assert result["level"] != "CRITICAL"
    assert "nan" not in result["explanation"]


# --- Score / band / text agreement ------------------------------------------

def test_stored_score_band_and_text_agree(detector):
    for scenario in ("normal", "flood", "heatwave", "smog", "storm"):
        for r in compute_all(SimulatedAdapter(demo=True).read_all(scenario, tick=0.0), detector):
            assert r["level"] == risk_level(r["score"])
            printed = int(r["explanation"].rsplit("Risk score ", 1)[1].split("/")[0])
            assert printed == math.floor(r["score"])
            assert risk_level(printed) == r["level"]


# --- Mesh correlation is same-hazard ----------------------------------------

def test_mesh_correlation_requires_the_same_hazard(detector):
    smog_node = _reading("CENTRAL-LDN", air_quality=180.0)
    flooding_neighbours = [_reading("HYDE-PARK", water_level=3.5),
                           _reading("CAMDEN", water_level=3.5)]
    results = {r["node_id"]: r for r in compute_all([smog_node, *flooding_neighbours], detector)}
    assert results["CENTRAL-LDN"]["correlated"] is False
    assert results["CENTRAL-LDN"]["mesh_multiplier"] == 1.0


# --- Honest API fallbacks -----------------------------------------------------

def test_non_json_response_falls_back_instead_of_crashing(monkeypatch):
    class _Portal:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<html>Please log in to the school Wi-Fi</html>"

    monkeypatch.setattr(api_adapter.urllib.request, "urlopen", lambda *a, **k: _Portal())
    with pytest.raises(ApiUnavailable):
        ApiAdapter().read_all()
    adapter, notes = create_adapter("api")
    assert adapter.source == "simulation"
    assert any("fell back" in n.lower() for n in notes)


def test_short_response_is_never_padded_with_another_location(monkeypatch):
    good = {"current": {"temperature_2m": 15.0, "relative_humidity_2m": 60.0,
                        "wind_speed_10m": 3.0, "pressure_msl": 1012.0,
                        "apparent_temperature": 15.0}}
    monkeypatch.setattr(api_adapter, "_http_get_json",
                        lambda url, params, timeout=8.0: [good] * 7)  # only 7 of 20 nodes
    with pytest.raises(ApiUnavailable):
        ApiAdapter().read_all()


def test_auto_mode_tries_the_api_when_driver_present_but_no_device(monkeypatch):
    import sensors
    from sensors import vernier_adapter

    monkeypatch.setattr(sensors, "has_hardware", lambda: True)
    def _no_device(self):
        self.hardware_ready = False  # what the real method does when open() fails
        return None

    monkeypatch.setattr(vernier_adapter.VernierAdapter, "_try_open_device", _no_device)
    monkeypatch.setattr(vernier_adapter, "detect", lambda: {
        "any_physical_sensor_detected": True, "summary": "driver present (test)"})
    calls = []

    def _fake_api(seed):
        calls.append(seed)
        return SimulatedAdapter(demo=False, seed=seed), ["API unreachable (test) — fell back to offline simulation."]

    monkeypatch.setattr(sensors, "_make_api", _fake_api)
    adapter, notes = create_adapter("auto")
    assert calls, "auto mode must fall through to the API step"
    assert adapter.source != "hardware"
    assert any("trying live API" in n for n in notes)


# --- Launcher ----------------------------------------------------------------

def test_simulation_mode_with_judge_flag_uses_the_seeded_generator():
    adapter, notes = create_adapter("simulation", demo=True)
    assert adapter.source == "demo"
    a = adapter.read_all("normal", tick=0.0)
    b = create_adapter("simulation", demo=True)[0].read_all("normal", tick=0.0)
    assert [r["temperature"] for r in a] == [r["temperature"] for r in b]
    assert any("judge mode" in n.lower() for n in notes)
    # Without the flag, plain simulation stays live/noisy and labelled as such.
    assert create_adapter("simulation", demo=False)[0].source == "simulation"


def test_judge_mode_implies_deterministic_data():
    assert run.wants_deterministic_data("simulation", True) is True
    assert run.wants_deterministic_data("demo", False) is True
    assert run.wants_deterministic_data("simulation", False) is False
    assert run.wants_deterministic_data("api", True) is False
    assert run.wants_deterministic_data("hardware", True) is False


def test_sensor_loop_marks_readings_stale_when_a_live_read_fails(monkeypatch, tmp_path):
    import asyncio
    from data.database import get_latest_readings_per_node

    monkeypatch.setattr(run, "DEMO_CONTROL_PATH", tmp_path / "demo_control.json")

    class _Flaky:
        source = "api"

        def __init__(self):
            self.calls = 0

        def read_all(self, scenario="none", tick=0.0):
            self.calls += 1
            if self.calls == 1:
                return SimulatedAdapter(demo=True).read_all("normal", tick=0.0)
            raise ApiUnavailable("connection dropped")

    sleeps = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError  # stop the infinite loop after two ticks

    monkeypatch.setattr(run.asyncio, "sleep", _fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run._sensor_loop(_Flaky(), "normal", judge=False, interval=0.0))

    latest = get_latest_readings_per_node()
    assert len(latest) == 20
    assert all(r["quality_flag"] == "stale" for r in latest)
    assert all(r["source"] == "demo" for r in latest)  # never relabelled as live


# --- The README's demo-tour numbers ------------------------------------------

def _load_tour_module():
    path = ROOT / "scripts" / "demo_tour.py"
    spec = importlib.util.spec_from_file_location("demo_tour_numbers_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_demo_tour_numbers_match_the_readme():
    rows = {r["scenario"]: r for r in _load_tour_module().run_tour()}
    expected = {
        "normal":   (3.9, 11.4, "Greenwich", "SAFE", 0),
        "flood":    (50.8, 100.0, "Regent's Canal (Little Venice)", "CRITICAL", 10),
        "heatwave": (78.8, 100.0, "Brixton", "CRITICAL", 12),
        "smog":     (82.7, 100.0, "Brixton", "CRITICAL", 15),
        "storm":    (98.1, 100.0, "Brixton", "CRITICAL", 20),
    }
    for scenario, (avg, mx, worst, level, alerts) in expected.items():
        row = rows[scenario]
        assert (row["avg_risk"], row["max_risk"], row["worst_node"],
                row["worst_level"], row["alerts"]) == (avg, mx, worst, level, alerts), scenario
    assert rows["flood"]["worst_explanation"] == (
        "Flood risk rising near Regent's Canal (Little Venice). Same trend seen across "
        "3 nearby nodes. Risk score 100/100. Main contributors: critical water level "
        "(4.8 m), very high humidity (99%), falling pressure (996 hPa).")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert rows["flood"]["worst_explanation"].split(". Same trend")[0] in readme
