"""Tests that hardware/auto modes never crash on a machine without sensors."""

from __future__ import annotations

import json

import pytest

from sensors import create_adapter, vernier_adapter
from sensors.hardware_status import detect, has_hardware
from sensors.vernier_adapter import DEFAULT_HARDWARE_NODE, VernierAdapter

# sensor_config.json contents that must never select a hardware node: an
# unknown id, the wrong type, or a top level that is not an object at all.
_UNUSABLE_CONFIG = [
    pytest.param('{"hardware_node_id": "NOT-A-NODE"}', id="unknown-node"),
    pytest.param('{"hardware_node_id": null}', id="null-node"),
    pytest.param('{"hardware_node_id": ["CENTRAL-LDN"]}', id="wrong-type"),
    pytest.param('{"something_else": "CENTRAL-LDN"}', id="missing-key"),
    pytest.param("{not json at all", id="malformed"),
    pytest.param("5", id="bare-number"),
    pytest.param('"CENTRAL-LDN"', id="bare-string-naming-a-node"),
    pytest.param("null", id="bare-null"),
    pytest.param("[1, 2]", id="bare-list"),
]


def test_hardware_status_detect_never_raises():
    status = detect()
    assert "summary" in status
    assert isinstance(status["any_physical_sensor_detected"], bool)


def test_vernier_adapter_runs_without_hardware():
    adapter = VernierAdapter()
    readings = adapter.read_all("normal", tick=0.0)
    adapter.cleanup()
    # Full mesh still produced even with no physical device attached.
    assert len(readings) == 20


def test_vernier_marks_missing_when_no_hardware():
    adapter = VernierAdapter()
    if has_hardware():
        return  # On a real Pi with sensors this assertion would differ.
    readings = adapter.read_all("normal", tick=0.0)
    hw_node = next(r for r in readings if r["node_id"] == adapter.hardware_node_id)
    # No hardware -> fall back to simulated values, flagged so it's never
    # mistaken for a real measurement.
    assert hw_node["quality_flag"] == "missing"
    assert hw_node["is_simulated"] is True


def test_factory_modes_return_adapters():
    for mode in ("simulation", "demo", "hardware"):
        adapter, notes = create_adapter(mode)
        assert adapter is not None
        assert isinstance(notes, list) and notes
        readings = adapter.read_all("normal", tick=0.0)
        assert len(readings) == 20
        adapter.cleanup()


def test_unknown_mode_defaults_to_simulation():
    adapter, notes = create_adapter("banana")
    assert adapter.source == "simulation"


@pytest.fixture
def sensor_config(tmp_path, monkeypatch):
    """Point the hardware-node reader at an isolated config file."""
    path = tmp_path / "sensor_config.json"
    monkeypatch.setattr(vernier_adapter, "CONFIG_PATH", path)
    return path


def test_configured_node_honours_a_known_node(sensor_config):
    sensor_config.write_text(json.dumps({"hardware_node_id": "RIVER-LEA"}))
    assert vernier_adapter._configured_node(DEFAULT_HARDWARE_NODE) == "RIVER-LEA"


def test_configured_node_missing_file_uses_the_default(sensor_config):
    assert not sensor_config.exists()
    assert vernier_adapter._configured_node(DEFAULT_HARDWARE_NODE) == DEFAULT_HARDWARE_NODE


@pytest.mark.parametrize("raw", _UNUSABLE_CONFIG)
def test_configured_node_falls_back_on_an_unusable_config(sensor_config, raw):
    # Every unusable shape lands in the same place: the default node, no
    # exception. A top level that is not an object used to raise AttributeError
    # out of the reader, which would take the whole run down at construction.
    sensor_config.write_text(raw)
    node = vernier_adapter._configured_node(DEFAULT_HARDWARE_NODE)
    assert node == DEFAULT_HARDWARE_NODE


@pytest.mark.parametrize("raw", _UNUSABLE_CONFIG)
def test_adapter_still_builds_on_an_unusable_config(sensor_config, raw):
    # The reader runs inside VernierAdapter.__init__, so a crash there is a
    # crash of --mode hardware itself, not just of a config lookup.
    sensor_config.write_text(raw)
    adapter = VernierAdapter()
    readings = adapter.read_all("normal", tick=0.0)
    adapter.cleanup()
    assert adapter.hardware_node_id == DEFAULT_HARDWARE_NODE
    assert len(readings) == 20
