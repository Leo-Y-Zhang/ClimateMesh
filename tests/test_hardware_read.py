"""Tests for the safe Vernier hardware-read diagnostic (plan item 2.5).

Confirms the script honestly classifies a read as REAL HARDWARE only when the
reading's source is genuinely "hardware", and as FALLBACK SIMULATION otherwise —
including for the real VernierAdapter on a machine with no device. No network or
device is required. scripts/ is not a package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sensors.hardware_status import has_hardware

ROOT = Path(__file__).resolve().parent.parent


def _load_hw_module():
    path = ROOT / "scripts" / "test_hardware_read.py"
    spec = importlib.util.spec_from_file_location("hw_read_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hw = _load_hw_module()


def _reading(node_id, source, quality_flag):
    return {
        "node_id": node_id, "source": source, "quality_flag": quality_flag,
        "is_simulated": source != "hardware",
        "temperature": 20.0, "humidity": 50.0, "air_quality": 50.0,
        "water_level": 0.3, "wind_speed": 3.0, "wind_chill": 20.0,
        "heat_index": 20.0, "barometric_pressure": 1010.0, "scenario": "none",
    }


class _FakeAdapter:
    """Stand-in for VernierAdapter with a controllable effective source."""

    def __init__(self, source: str, node_id: str = "CENTRAL-LDN"):
        self.source = source
        self.hardware_node_id = node_id

    def read_all(self, scenario="none", tick=0.0):
        if self.source == "hardware":
            hw_row = _reading(self.hardware_node_id, "hardware", "estimated")
        else:
            hw_row = _reading(self.hardware_node_id, "simulation", "missing")
        return [hw_row, _reading("OTHER-NODE", "simulation", "ok")]


def test_classify_reading_hardware():
    assert hw.classify_reading(_reading("X", "hardware", "estimated")) == hw.REAL


def test_classify_reading_simulation():
    assert hw.classify_reading(_reading("X", "simulation", "missing")) == hw.FALLBACK
    assert hw.classify_reading(_reading("X", "demo", "ok")) == hw.FALLBACK
    assert hw.classify_reading(_reading("X", "api", "estimated")) == hw.FALLBACK


def test_probe_reports_real_hardware_for_genuine_read():
    result = hw.probe(adapter=_FakeAdapter("hardware"))
    assert result["is_real_hardware"] is True
    assert result["classification"] == hw.REAL
    assert result["reading"]["source"] == "hardware"
    assert result["reading"]["node_id"] == "CENTRAL-LDN"


def test_probe_reports_fallback_for_simulated_read():
    result = hw.probe(adapter=_FakeAdapter("simulation"))
    assert result["is_real_hardware"] is False
    assert result["classification"] == hw.FALLBACK
    assert result["reading"]["source"] != "hardware"
    assert result["reading"]["quality_flag"] == "missing"


def test_probe_real_adapter_is_honest_without_hardware():
    # Using the genuine VernierAdapter: with no device attached this must be a
    # FALLBACK, and it must never crash. (Guarded so a real Pi+sensor still passes.)
    result = hw.probe()
    assert result["classification"] in (hw.REAL, hw.FALLBACK)
    assert "reading" in result and result["reading"] is not None
    if not has_hardware():
        assert result["is_real_hardware"] is False
        assert result["classification"] == hw.FALLBACK
        assert result["reading"]["source"] != "hardware"


def test_format_reading_includes_canonical_fields():
    text = hw.format_reading(_reading("X", "hardware", "estimated"))
    for field in ("temperature", "humidity", "barometric_pressure",
                  "source", "is_simulated", "quality_flag"):
        assert field in text


def test_format_reading_handles_none():
    assert "no reading" in hw.format_reading(None)
