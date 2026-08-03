"""Climate Mesh data generation engine.

Produces realistic environmental readings for every node: a smooth daily
cycle, per-node random noise, gradual scenario onset, and correlated anomalies
across geographically adjacent nodes (so a flood shows up on several nearby
river nodes at once, not just one). The same engine powers both ``simulation``
mode (live, mildly random) and ``demo``/``judge`` mode (deterministic and
screenshot-stable).

This module only knows how to make *numbers*. Wrapping them into canonical
readings is the job of ``sensors/simulated_adapter.py``.
"""

from __future__ import annotations

import math
import random

from config.nodes import NEIGHBOURS, NODES_BY_ID
from simulation.scenarios import scenario_delta

# Realistic London-area baselines per environment. Values are deliberately
# calm so a "normal" scenario sits firmly in the SAFE band.
BASE_VALUES: dict[str, dict[str, float]] = {
    "school":      {"temperature": 15.0, "humidity": 65, "air_quality": 45, "water_level": 0.30, "wind_speed": 4.0, "barometric_pressure": 1013},
    "river":       {"temperature": 14.0, "humidity": 78, "air_quality": 30, "water_level": 1.20, "wind_speed": 4.0, "barometric_pressure": 1011},
    "residential": {"temperature": 15.0, "humidity": 68, "air_quality": 50, "water_level": 0.35, "wind_speed": 4.5, "barometric_pressure": 1013},
    "urban":       {"temperature": 16.0, "humidity": 60, "air_quality": 65, "water_level": 0.25, "wind_speed": 5.0, "barometric_pressure": 1013},
    "park":        {"temperature": 14.0, "humidity": 72, "air_quality": 30, "water_level": 0.40, "wind_speed": 5.0, "barometric_pressure": 1012},
}

# How a channel responds to the compressed daily cycle (amplitude of the sine
# term) plus the standard deviation of its random noise.
_CYCLE = {
    "temperature":         {"amp": 3.0,  "noise": 0.4},
    "humidity":            {"amp": -6.0, "noise": 1.2},
    "air_quality":         {"amp": 6.0,  "noise": 2.5},
    "water_level":         {"amp": 0.05, "noise": 0.02},
    "wind_speed":          {"amp": 1.5,  "noise": 0.6},
    "barometric_pressure": {"amp": 2.0,  "noise": 0.8},
}

# Hard clamps so no channel ever leaves a physically plausible range.
_CLAMP = {
    "temperature": (-15, 55),
    "humidity": (0, 100),
    "air_quality": (0, 500),
    "water_level": (0, 12),
    "wind_speed": (0, 60),
    "barometric_pressure": (940, 1060),
}

# Daily cycle compressed to ~120s so demos show a visible rhythm quickly.
_CYCLE_SECONDS = 120.0
# Scenario ramp-up duration (seconds) — events develop, they don't teleport.
_RAMP_SECONDS = 12.0


def _heat_index(temp: float, humidity: float) -> float:
    """Approximate apparent ('feels like') temperature for warm conditions."""
    if temp < 26:
        return temp
    t = temp
    rh = humidity
    # Simplified Rothfusz regression (metric-adapted, good enough for a demo).
    hi = (-8.0 + 1.07 * t + 0.2 * rh + 0.004 * t * rh)
    return max(temp, hi)


def _wind_chill(temp: float, wind_speed: float) -> float:
    """Approximate wind-chill apparent temperature for cold, windy conditions."""
    if temp > 12 or wind_speed < 1.5:
        return temp
    v = wind_speed * 3.6  # m/s -> km/h
    wc = 13.12 + 0.6215 * temp - 11.37 * (v ** 0.16) + 0.3965 * temp * (v ** 0.16)
    return min(temp, wc)


def _ramp(tick: float, deterministic: bool) -> float:
    """Scenario intensity 0..1. Fully ramped immediately in deterministic mode."""
    if deterministic:
        return 1.0
    return max(0.0, min(1.0, tick / _RAMP_SECONDS))


def _rng_for(node_id: str, tick: float, deterministic: bool, seed: int) -> random.Random:
    """Per-node RNG. Deterministic mode keys only on node_id so repeated reads
    of the same node yield the same value — ideal for stable screenshots."""
    if deterministic:
        return random.Random(f"{seed}:{node_id}")
    return random.Random()


def generate_channels(
    node: dict,
    tick: float,
    scenario: str = "none",
    *,
    deterministic: bool = False,
    seed: int = 1234,
) -> dict[str, float]:
    """Generate the eight measurement channels for one node at time ``tick``."""
    env = node["environment"]
    base = BASE_VALUES[env]
    rng = _rng_for(node["node_id"], tick, deterministic, seed)
    phase = math.sin(tick * 2 * math.pi / _CYCLE_SECONDS)
    ramp = _ramp(tick, deterministic) if scenario and scenario != "none" else 0.0

    values: dict[str, float] = {}
    for channel, base_val in base.items():
        spec = _CYCLE.get(channel, {"amp": 0.0, "noise": 0.5})
        cyclic = spec["amp"] * phase
        noise = rng.gauss(0, spec["noise"])
        delta = scenario_delta(scenario, env, channel) * ramp if ramp else 0.0
        val = base_val + cyclic + noise + delta
        lo, hi = _CLAMP[channel]
        values[channel] = max(lo, min(hi, val))

    # Derived apparent-temperature channels.
    values["heat_index"] = _heat_index(values["temperature"], values["humidity"])
    values["wind_chill"] = _wind_chill(values["temperature"], values["wind_speed"])
    return values


def generate_all(
    tick: float,
    scenario: str = "none",
    *,
    deterministic: bool = False,
    seed: int = 1234,
) -> dict[str, dict[str, float]]:
    """Generate channels for every node, then apply mesh correlation.

    Mesh correlation: when a scenario is active, nodes nudge their neighbours
    slightly toward the same anomaly. This makes adjacent nodes move together
    — the signal the risk engine's mesh multiplier rewards — without making
    any single node's values implausible.
    """
    raw = {
        nid: generate_channels(node, tick, scenario,
                               deterministic=deterministic, seed=seed)
        for nid, node in NODES_BY_ID.items()
    }
    if not scenario or scenario == "none":
        return raw

    ramp = _ramp(tick, deterministic)
    correlated: dict[str, dict[str, float]] = {}
    for nid, channels in raw.items():
        node = NODES_BY_ID[nid]
        env = node["environment"]
        adjusted = dict(channels)
        neigh = NEIGHBOURS.get(nid, [])
        if neigh:
            for channel in ("water_level", "air_quality", "temperature", "barometric_pressure", "humidity"):
                # Pull 15% toward the average neighbour delta for this channel.
                neighbour_deltas = [
                    scenario_delta(scenario, NODES_BY_ID[n]["environment"], channel)
                    for n in neigh
                ]
                if neighbour_deltas:
                    avg = sum(neighbour_deltas) / len(neighbour_deltas)
                    adjusted[channel] = adjusted[channel] + 0.15 * avg * ramp
                    lo, hi = _CLAMP[channel]
                    adjusted[channel] = max(lo, min(hi, adjusted[channel]))
        correlated[nid] = adjusted
    return correlated
