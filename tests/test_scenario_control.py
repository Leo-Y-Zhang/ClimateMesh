"""Tests that the demo-control file can only select a known scenario.

``data/demo_control.json`` is written by the dashboard and read back by the
engine, so the scenario name is a value that crosses a trust boundary on disk.
Both readers must treat it as untrusted: a name is honoured only when it is one
of ``SCENARIOS``, and anything else -- unknown name, wrong case, null, wrong
type, malformed file -- falls back to the caller's default instead of being
passed on. This mirrors the guard ``sensors/vernier_adapter.py`` already applies
to the configured hardware node id.
"""

from __future__ import annotations

import json

import pytest

import run
from dashboard import app as dashboard_app
from simulation.scenarios import SCENARIOS

# Values that must never come back out of the control file.
_REJECTED = [
    pytest.param("wipe_everything", id="unknown-name"),
    pytest.param("", id="empty-string"),
    pytest.param("NORMAL", id="wrong-case"),
    pytest.param("../../etc/passwd", id="path-shaped"),
    pytest.param(["flood"], id="list"),
    pytest.param({"nested": "flood"}, id="dict"),
    pytest.param(7, id="number"),
    pytest.param(None, id="null"),
]


@pytest.fixture
def control_file(tmp_path, monkeypatch):
    """Point both readers at an isolated control file."""
    path = tmp_path / "demo_control.json"
    monkeypatch.setattr(run, "DEMO_CONTROL_PATH", path)
    monkeypatch.setattr(dashboard_app, "DEMO_CONTROL_PATH", path)
    return path


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_known_scenario_is_honoured(control_file, scenario):
    control_file.write_text(json.dumps({"scenario": scenario}))
    assert run._read_scenario("normal") == scenario
    assert dashboard_app._active_scenario() == scenario


@pytest.mark.parametrize("value", _REJECTED)
def test_unknown_scenario_falls_back_to_the_default(control_file, value):
    control_file.write_text(json.dumps({"scenario": value}))
    assert run._read_scenario("storm") == "storm"
    assert dashboard_app._active_scenario() == "normal"


def test_missing_scenario_key_falls_back_to_the_default(control_file):
    control_file.write_text(json.dumps({"something_else": "flood"}))
    assert run._read_scenario("heatwave") == "heatwave"
    assert dashboard_app._active_scenario() == "normal"


def test_missing_control_file_uses_the_default(control_file):
    assert not control_file.exists()
    assert run._read_scenario("heatwave") == "heatwave"
    assert dashboard_app._active_scenario() == "normal"


def test_malformed_control_file_uses_the_default(control_file):
    control_file.write_text("{not json at all")
    assert run._read_scenario("smog") == "smog"
    assert dashboard_app._active_scenario() == "normal"


@pytest.mark.parametrize("value", _REJECTED)
def test_readers_always_return_a_str(control_file, value):
    # Both signatures promise str; a wrong-typed value in the file must not
    # escape as one.
    control_file.write_text(json.dumps({"scenario": value}))
    assert isinstance(run._read_scenario("normal"), str)
    assert isinstance(dashboard_app._active_scenario(), str)


def test_written_scenario_round_trips(control_file):
    # Whatever the writers put in the file must still be readable back, so the
    # guard cannot break the dashboard's own scenario picker.
    for scenario in SCENARIOS:
        run._write_scenario(scenario)
        assert run._read_scenario("normal") == scenario
        dashboard_app._write_scenario(scenario)
        assert dashboard_app._active_scenario() == scenario
