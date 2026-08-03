"""Safe one-shot Vernier hardware read check for Climate Mesh.

Run this on the Raspberry Pi (or any machine) to find out, honestly, whether a
physical Vernier sensor is actually present and readable right now:

    python scripts/test_hardware_read.py

It (1) probes for a Vernier device, (2) attempts a single read through the real
``VernierAdapter`` pathway, (3) prints the canonical reading shape it produced,
and (4) states clearly whether that reading is **REAL HARDWARE** or **FALLBACK
SIMULATION**. It never crashes when no sensor is attached — that is the normal,
expected case and is reported plainly rather than hidden.

Despite the ``test_`` filename this is a human-facing diagnostic, not a pytest
module (it lives in ``scripts/``, which pytest does not collect). The pure
helpers below are unit-tested in ``tests/test_hardware_read.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sensors.base import MEASUREMENT_FIELDS
from sensors.hardware_status import detect

REAL = "REAL HARDWARE"
FALLBACK = "FALLBACK SIMULATION"


def classify_reading(reading: dict) -> str:
    """Return ``REAL HARDWARE`` iff the reading genuinely came from a device.

    The single source of truth is the reading's own ``source`` field: it is
    ``"hardware"`` only when ``VernierAdapter`` actually opened a device and read
    it. Anything else — including a simulated fallback for the hardware node — is
    ``FALLBACK SIMULATION``.
    """
    return REAL if reading.get("source") == "hardware" else FALLBACK


def probe(adapter=None) -> dict:
    """Probe for a device and take one read. Returns a structured result dict.

    Never raises for the no-hardware case. ``adapter`` may be injected for
    testing; otherwise a real :class:`VernierAdapter` is constructed.
    """
    status = detect()
    if adapter is None:
        from sensors.vernier_adapter import VernierAdapter
        adapter = VernierAdapter()

    node_id = getattr(adapter, "hardware_node_id", None)
    readings = adapter.read_all("none", tick=0.0)
    hw_reading = None
    if node_id is not None:
        hw_reading = next((r for r in readings if r["node_id"] == node_id), None)
    if hw_reading is None and readings:
        hw_reading = readings[0]

    classification = classify_reading(hw_reading) if hw_reading else FALLBACK
    return {
        "device_visible": bool(status["any_physical_sensor_detected"]),
        "effective_source": getattr(adapter, "source", "simulation"),
        "hardware_node_id": node_id,
        "reading": hw_reading,
        "classification": classification,
        "is_real_hardware": classification == REAL,
        "detect_summary": status["summary"],
    }


def format_reading(reading: dict | None) -> str:
    """Pretty-print the canonical reading shape for a screenshot."""
    if not reading:
        return "    (no reading produced)"
    lines = []
    for field in MEASUREMENT_FIELDS:
        lines.append(f"    {field:<22} {reading.get(field)}")
    for meta in ("source", "is_simulated", "quality_flag", "scenario"):
        lines.append(f"    {meta:<22} {reading.get(meta)}")
    return "\n".join(lines)


def main() -> int:
    print("=" * 60)
    print("  Climate Mesh — Vernier hardware read check")
    print("=" * 60)

    result = probe()
    adapter_cleanup = None  # adapter built inside probe(); nothing to close here

    print(f"  Driver library visible : {result['device_visible']}")
    print(f"  Detection summary       : {result['detect_summary']}")
    print(f"  Hardware node           : {result['hardware_node_id']}")
    print(f"  Effective source        : {result['effective_source']}")
    print("-" * 60)
    print("  Canonical reading produced:")
    print(format_reading(result["reading"]))
    print("-" * 60)

    if result["is_real_hardware"]:
        print(f"  RESULT: {REAL}")
        print("  A physical Vernier device was opened and read. The reading above")
        print("  is genuine sensor data (air quality / water level remain")
        print("  non-measured placeholders, hence quality_flag='estimated').")
    else:
        print(f"  RESULT: {FALLBACK}")
        print("  No physical Vernier device was read. The reading above is")
        print("  simulated and is honestly labelled source != 'hardware' with")
        print("  quality_flag='missing' — it is never presented as real data.")
    print("=" * 60)
    # Always exit 0: a missing sensor is a valid, expected outcome, not an error.
    del adapter_cleanup
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
