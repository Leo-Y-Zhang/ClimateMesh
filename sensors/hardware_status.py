"""Physical-sensor detection for Climate Mesh.

Hardware support is *optional and future-facing*. This module probes for the
libraries and devices a physical node would need, and reports what it finds in
plain language. It must never raise on a machine without sensors — detection
failure is the normal case and is reported, not crashed on.
"""

from __future__ import annotations

import platform

# --- Optional hardware library probes (all failures are expected/normal) ---
_GDX_AVAILABLE = False
_GDX_ERROR = ""
try:  # Vernier Go Direct weather sensor library
    from gdx import gdx as _gdx_module  # noqa: F401
    _GDX_AVAILABLE = True
except Exception as e:  # ImportError on any machine without the helper module
    _GDX_ERROR = str(e)

_ADC_AVAILABLE = False
_ADC_ERROR = ""
try:  # Adafruit Blinka / ADS1115 stack (Raspberry Pi only)
    import board  # noqa: F401
    import busio  # noqa: F401
    import adafruit_ads1x15.ads1115 as _ADS  # noqa: F401
    _ADC_AVAILABLE = True
except Exception as e:  # ImportError or NotImplementedError off-Pi
    _ADC_ERROR = str(e)


def detect() -> dict:
    """Return a structured hardware-detection report (never raises)."""
    machine = platform.machine().lower()
    looks_like_pi = machine.startswith("aarch64") or machine.startswith("arm")
    any_sensor = _GDX_AVAILABLE or _ADC_AVAILABLE
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "looks_like_raspberry_pi": looks_like_pi,
        "gdx_weather_available": _GDX_AVAILABLE,
        "adc_air_quality_available": _ADC_AVAILABLE,
        "any_physical_sensor_detected": any_sensor,
        "gdx_error": None if _GDX_AVAILABLE else _GDX_ERROR,
        "adc_error": None if _ADC_AVAILABLE else _ADC_ERROR,
        # NOTE: these probes detect the driver *library*, not a plugged-in
        # device. The summary therefore talks about library availability; the
        # Vernier adapter only emits source="hardware" once a device truly opens.
        "summary": (
            "Vernier/ADC driver library available — will attempt a real device read."
            if any_sensor else
            "No sensor driver library detected — simulation fallback active."
        ),
    }


def has_hardware() -> bool:
    """True if at least one sensor *driver library* is importable.

    This is a library-presence check, not a device-presence check: it gates
    whether it is worth *attempting* a real device open. Whether a physical
    sensor actually responds is decided by ``VernierAdapter`` when it opens the
    device, which is the only place ``source="hardware"`` can originate.
    """
    return _GDX_AVAILABLE or _ADC_AVAILABLE
