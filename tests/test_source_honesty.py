"""Tests that data provenance is never overstated.

The judged invariant: source="hardware" appears ONLY for a genuine physical
read; a failed/absent read falls back to a non-hardware source with a
missing/estimated quality flag; an API fallback is never labelled "api"; and the
database preserves whatever source/quality a reading was created with.
"""

from __future__ import annotations

from data.database import get_latest_readings_per_node, insert_reading
from sensors import create_adapter
from sensors.api_adapter import ApiAdapter, ApiUnavailable
from sensors.simulated_adapter import SimulatedAdapter
from sensors.vernier_adapter import VernierAdapter

# A complete physical-channel dict (the shape _read_physical_channels returns).
_FAKE_PHYSICAL = {
    "temperature": 21.0, "humidity": 55.0, "air_quality": 50.0,
    "water_level": 0.3, "wind_speed": 3.0, "wind_chill": 21.0,
    "heat_index": 21.0, "barometric_pressure": 1011.0,
}


def test_failed_hardware_read_never_labels_hardware(monkeypatch):
    adapter = VernierAdapter()
    # Simulate "driver/device looked ready, but the actual read returned nothing".
    adapter.hardware_ready = True
    monkeypatch.setattr(adapter, "_read_physical_channels", lambda: None)

    readings = adapter.read_all("normal", tick=0.0)
    assert all(r["source"] != "hardware" for r in readings)

    hw = next(r for r in readings if r["node_id"] == adapter.hardware_node_id)
    assert hw["source"] == "simulation"
    assert hw["quality_flag"] == "missing"
    assert hw["is_simulated"] is True


def test_genuine_hardware_read_is_labelled_hardware_estimated(monkeypatch):
    adapter = VernierAdapter()
    adapter.hardware_ready = True
    monkeypatch.setattr(adapter, "_read_physical_channels", lambda: dict(_FAKE_PHYSICAL))

    readings = adapter.read_all("normal", tick=0.0)
    hw = next(r for r in readings if r["node_id"] == adapter.hardware_node_id)
    assert hw["source"] == "hardware"
    assert hw["is_simulated"] is False
    # air_quality / water_level are non-measured placeholders, so the genuine
    # hardware reading is "estimated" — never "hardware"/"ok" over fabrication.
    assert hw["quality_flag"] == "estimated"
    # Every other node stays simulated.
    others = [r for r in readings if r["node_id"] != adapter.hardware_node_id]
    assert all(r["source"] == "simulation" for r in others)


def test_no_hardware_adapter_effective_source_not_hardware():
    # On a machine with no physical sensor the adapter's *effective* source must
    # not claim hardware (honesty fix #1: no run-level "HARDWARE" with 0 rows).
    adapter = VernierAdapter()
    if adapter.hardware_ready:  # pragma: no cover - only on a real Pi with a device
        return
    assert adapter.source == "simulation"
    readings = adapter.read_all("normal", tick=0.0)
    assert all(r["source"] != "hardware" for r in readings)


def test_api_fallback_is_never_labelled_api(monkeypatch):
    def _raise(self, scenario="none", tick=0.0):
        raise ApiUnavailable("offline")

    monkeypatch.setattr(ApiAdapter, "read_all", _raise)
    adapter, notes = create_adapter("api")
    # Fell back to simulation; must NOT pretend to be live API data.
    assert adapter.source == "simulation"
    assert isinstance(adapter, SimulatedAdapter)
    assert any("fell back" in n.lower() or "simulation" in n.lower() for n in notes)


def test_database_preserves_source_and_quality():
    reading = SimulatedAdapter(demo=False).read_all("normal", tick=0.0)[0]
    assert reading["source"] == "simulation"
    insert_reading(reading)
    stored = get_latest_readings_per_node()[0]
    assert stored["source"] == "simulation"
    assert stored["quality_flag"] == reading["quality_flag"]
    assert stored["is_simulated"] == 1


def test_demo_source_label_is_demo():
    demo = SimulatedAdapter(demo=True).read_all("flood", tick=0.0)
    assert all(r["source"] == "demo" for r in demo)
    assert all(r["is_simulated"] is True for r in demo)
