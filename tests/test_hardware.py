"""Tests that hardware/auto modes never crash on a machine without sensors."""

from __future__ import annotations

from sensors import create_adapter
from sensors.hardware_status import detect, has_hardware
from sensors.vernier_adapter import VernierAdapter


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
