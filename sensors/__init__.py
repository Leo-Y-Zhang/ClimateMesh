"""Sensor adapter factory.

Maps an operating mode to a concrete adapter. All fallback decisions live here
so the launcher, smoke test, and dashboard agree on behaviour. Every path
returns an adapter plus a list of human-readable notes describing exactly what
happened (e.g. "API unreachable — fell back to simulation"), which the launcher
prints and the dashboard surfaces.
"""

from __future__ import annotations

from sensors.base import SensorAdapter
from sensors.hardware_status import detect, has_hardware
from sensors.simulated_adapter import SimulatedAdapter


def create_adapter(mode: str, *, demo: bool = False, seed: int = 1234) -> tuple[SensorAdapter, list[str]]:
    """Return ``(adapter, notes)`` for the requested mode.

    Modes: simulation, demo, api, hardware, auto. ``demo``/judge use a
    deterministic simulated adapter. ``api`` and ``hardware`` fall back to
    simulation (with a recorded note) when their backing source is unavailable,
    so the system always runs.
    """
    notes: list[str] = []
    mode = (mode or "simulation").lower()

    if mode == "simulation":
        return SimulatedAdapter(demo=False, seed=seed), ["Offline simulation — no internet or sensors required."]

    if mode == "demo":
        return SimulatedAdapter(demo=True, seed=seed), ["Deterministic demo data — stable for screenshots and video."]

    if mode == "api":
        return _make_api(seed)

    if mode == "hardware":
        from sensors.vernier_adapter import VernierAdapter
        adapter = VernierAdapter(seed=seed)
        if adapter.hardware_ready:
            notes.append("Physical Vernier sensor active — hardware node live over simulated mesh.")
        else:
            notes.append("No physical sensor available — fallback simulation active (system still runs).")
        return adapter, notes

    if mode == "auto":
        if has_hardware():
            # has_hardware() is library-level; the device may still not open,
            # so build the adapter and report its *effective* readiness.
            from sensors.vernier_adapter import VernierAdapter
            adapter = VernierAdapter(seed=seed)
            if adapter.hardware_ready:
                notes.append("Auto: physical Vernier sensor active — hardware node over simulated mesh.")
            else:
                notes.append("Auto: Vernier driver present but no device opened — simulation fallback.")
            return adapter, notes
        adapter, n = _make_api(seed)
        if adapter.source == "api":
            notes.append("Auto: no sensors — live API mode selected.")
        else:
            notes.append("Auto: no sensors and API unreachable — simulation selected.")
        notes.extend(n)
        return adapter, notes

    return SimulatedAdapter(demo=False, seed=seed), [f"Unknown mode {mode!r} — defaulted to simulation."]


def _make_api(seed: int) -> tuple[SensorAdapter, list[str]]:
    """Build the API adapter, probing connectivity once; fall back if offline."""
    from sensors.api_adapter import ApiAdapter, ApiUnavailable
    adapter = ApiAdapter()
    try:
        adapter.read_all()  # connectivity probe
        return adapter, ["Live Open-Meteo API data across 20 real London locations."]
    except ApiUnavailable as e:
        return (SimulatedAdapter(demo=False, seed=seed),
                [f"API unreachable ({e}) — fell back to offline simulation."])


__all__ = ["create_adapter", "detect", "SimulatedAdapter", "SensorAdapter"]
