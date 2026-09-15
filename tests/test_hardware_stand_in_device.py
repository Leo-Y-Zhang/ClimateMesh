"""The Vernier hardware path driven end to end with a stand-in device.

No physical sensor is involved. These tests plant a fake ``gdx`` helper module
that behaves like Vernier's (open / select_sensors / start / read / stop /
close) and make the driver probe report it as present, then check what the
adapter does with a device that answers, one that answers badly and one that
refuses to open. They validate our code on either side of the driver, not the
driver or the sensor themselves; the write-up says exactly that.
"""
from __future__ import annotations

import sys
import types

import pytest

from config.nodes import NODES_BY_ID
from sensors import vernier_adapter as va
from sensors.vernier_adapter import VernierAdapter
from scripts.test_hardware_read import FALLBACK, REAL, classify_reading, probe

# Order follows the adapter's select_sensors([1, 3, 4, 5, 7, 10]):
# wind speed, wind chill, temperature, heat index, humidity, pressure.
SAMPLE = [3.2, 11.0, 12.5, 12.5, 81.0, 1003.0]
NODE = "CENTRAL-LDN"


class FakeDevice:
    def __init__(self, samples=SAMPLE, *, fail_open=False):
        self.samples = samples
        self.fail_open = fail_open
        self.calls: list[tuple] = []

    def open(self, connection="usb"):
        self.calls.append(("open", connection))
        if self.fail_open:
            raise OSError("no USB device")

    def select_sensors(self, ids):
        self.calls.append(("select_sensors", tuple(ids)))

    def start(self, period):
        self.calls.append(("start", period))

    def read(self):
        return self.samples

    def stop(self):
        self.calls.append(("stop",))

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def stand_in(monkeypatch):
    """Install a fake ``gdx`` module and make detect() report it present.

    Returns a function that builds an adapter around a given FakeDevice.
    """
    def build(device: FakeDevice) -> VernierAdapter:
        package = types.ModuleType("gdx")
        helper = types.ModuleType("gdx.gdx")
        helper.gdx = lambda: device          # ``gdx_module.gdx()`` in the adapter
        package.gdx = helper
        monkeypatch.setitem(sys.modules, "gdx", package)
        monkeypatch.setitem(sys.modules, "gdx.gdx", helper)
        monkeypatch.setattr(va, "detect", lambda: {
            "any_physical_sensor_detected": True,
            "summary": "stand-in device for tests",
        })
        return VernierAdapter(hardware_node_id=NODE)
    return build


def _node_reading(readings, node_id=NODE):
    return next(r for r in readings if r["node_id"] == node_id)


def test_open_device_yields_a_hardware_reading_flagged_estimated(stand_in):
    device = FakeDevice()
    adapter = stand_in(device)
    assert adapter.hardware_ready is True
    assert adapter.source == "hardware"
    assert ("select_sensors", (1, 3, 4, 5, 7, 10)) in device.calls
    assert ("start", 2000) in device.calls

    readings = adapter.read_all("flood", tick=0.0)
    assert len(readings) == len(NODES_BY_ID)
    r = _node_reading(readings)
    assert r["source"] == "hardware"
    assert r["is_simulated"] is False
    assert r["quality_flag"] == "estimated"      # two channels are placeholders
    assert r["scenario"] == "observed"           # live values, no scenario delta
    assert r["temperature"] == 12.5
    assert r["humidity"] == 81.0
    assert r["wind_speed"] == 3.2
    assert r["wind_chill"] == 11.0
    assert r["heat_index"] == 12.5
    assert r["barometric_pressure"] == 1003.0
    # Every other node stays simulated and says so.
    others = [x for x in readings if x["node_id"] != NODE]
    assert others and all(x["source"] == "simulation" and x["is_simulated"] for x in others)

    adapter.cleanup()
    assert ("stop",) in device.calls and ("close",) in device.calls


def test_probe_reports_real_hardware_for_the_stand_in_device(stand_in):
    adapter = stand_in(FakeDevice())
    result = probe(adapter)
    assert result["effective_source"] == "hardware"
    assert result["is_real_hardware"] is True
    assert result["classification"] == REAL
    assert classify_reading(result["reading"]) == REAL


@pytest.mark.parametrize("bad", [None, [], [3.2, 11.0]], ids=["none", "empty", "short"])
def test_a_device_that_answers_badly_is_flagged_missing_not_hardware(stand_in, bad):
    adapter = stand_in(FakeDevice(samples=bad))
    assert adapter.source == "hardware"          # it did open ...
    r = _node_reading(adapter.read_all("none", tick=0.0))
    assert r["source"] == "simulation"           # ... but nothing real was read
    assert r["is_simulated"] is True
    assert r["quality_flag"] == "missing"
    assert classify_reading(r) == FALLBACK


def test_a_device_that_refuses_to_open_falls_back_honestly(stand_in):
    adapter = stand_in(FakeDevice(fail_open=True))
    assert adapter.hardware_ready is False
    assert adapter.source == "simulation"
    r = _node_reading(adapter.read_all("none", tick=0.0))
    assert r["source"] == "simulation"
    assert r["quality_flag"] == "missing"
    assert probe(adapter)["is_real_hardware"] is False


def test_hardware_reading_scores_like_any_other(stand_in):
    """The engine scores a hardware reading exactly like a simulated one."""
    from ai.anomaly_model import AnomalyDetector
    from backend.risk_engine import compute_all

    adapter = stand_in(FakeDevice())
    readings = adapter.read_all("none", tick=0.0)
    detector = AnomalyDetector().train(quiet=True)
    results = {x["node_id"]: x for x in compute_all(readings, detector)}
    assert set(results) == set(NODES_BY_ID)
    hw = results[NODE]
    assert 0 <= hw["risk_score"] <= 100
    assert hw["level"] in {"SAFE", "MODERATE", "WARNING", "CRITICAL"}
