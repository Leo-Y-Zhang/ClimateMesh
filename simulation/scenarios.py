"""Demo scenario definitions for Climate Mesh.

Each scenario applies environment-specific deltas on top of the normal
baseline. Deltas are applied with a gradual ramp by the engine so events
develop over time rather than jumping instantly — this is both more realistic
and more convincing on screen. River nodes feel floods most; urban nodes feel
heatwaves and smog most; storms hit everywhere via pressure and wind.
"""

from __future__ import annotations

# Per-scenario, per-environment additive deltas for each measurement channel.
# Channels omitted default to 0. Environments: school, river, residential,
# urban, park.
SCENARIO_DELTAS: dict[str, dict[str, dict[str, float]]] = {
    "normal": {},  # baseline; no deltas
    "flood": {
        "river":       {"water_level": 3.5, "humidity": 18, "temperature": -2.0, "barometric_pressure": -14, "wind_speed": 3, "air_quality": -5},
        "residential": {"water_level": 1.5, "humidity": 18, "temperature": -1.5, "barometric_pressure": -12, "wind_speed": 2},
        "school":      {"water_level": 1.2, "humidity": 18, "temperature": -1.5, "barometric_pressure": -12, "wind_speed": 2},
        "urban":       {"water_level": 0.6, "humidity": 10, "temperature": -1.0, "barometric_pressure": -8,  "wind_speed": 2},
        "park":        {"water_level": 1.2, "humidity": 18, "temperature": -1.5, "barometric_pressure": -12, "wind_speed": 2},
    },
    "heatwave": {
        "urban":       {"temperature": 20, "humidity": -25, "air_quality": 90, "barometric_pressure": 6, "wind_speed": -2, "water_level": -0.1},
        "school":      {"temperature": 16, "humidity": -22, "air_quality": 55, "barometric_pressure": 5, "wind_speed": -2},
        "residential": {"temperature": 16, "humidity": -22, "air_quality": 60, "barometric_pressure": 5, "wind_speed": -2},
        "river":       {"temperature": 13, "humidity": -15, "air_quality": 30, "barometric_pressure": 4, "wind_speed": -2, "water_level": -0.3},
        "park":        {"temperature": 14, "humidity": -18, "air_quality": 35, "barometric_pressure": 4, "wind_speed": -2},
    },
    "smog": {
        "urban":       {"air_quality": 260, "wind_speed": -4, "temperature": 2, "humidity": -3, "barometric_pressure": -6},
        "school":      {"air_quality": 180, "wind_speed": -3, "temperature": 2},
        "residential": {"air_quality": 200, "wind_speed": -3, "temperature": 2},
        "river":       {"air_quality": 90,  "wind_speed": -3, "temperature": 1},
        "park":        {"air_quality": 80,  "wind_speed": -3, "temperature": 1},
    },
    "storm": {
        "river":       {"barometric_pressure": -20, "wind_speed": 16, "humidity": 12, "water_level": 1.5, "temperature": -3},
        "urban":       {"barometric_pressure": -18, "wind_speed": 16, "humidity": 8,  "water_level": 0.4, "temperature": -3},
        "school":      {"barometric_pressure": -18, "wind_speed": 14, "humidity": 10, "water_level": 0.3, "temperature": -3},
        "residential": {"barometric_pressure": -18, "wind_speed": 14, "humidity": 10, "water_level": 0.4, "temperature": -3},
        "park":        {"barometric_pressure": -19, "wind_speed": 15, "humidity": 11, "water_level": 0.5, "temperature": -3},
    },
}

# Human-facing metadata for each scenario, used by the dashboard and docs.
SCENARIO_INFO: dict[str, dict] = {
    "normal":   {"label": "Normal",   "blurb": "Calm baseline conditions across the mesh.",
                 "primary_factors": []},
    "flood":    {"label": "Flood",    "blurb": "Rising water levels and humidity, falling pressure near rivers.",
                 "primary_factors": ["water_level", "humidity", "barometric_pressure"]},
    "heatwave": {"label": "Heatwave", "blurb": "Temperatures spike, humidity drops, air quality worsens — urban heat island.",
                 "primary_factors": ["temperature", "air_quality", "humidity"]},
    "smog":     {"label": "Smog",     "blurb": "Air quality degrades sharply as wind drops and pollution accumulates.",
                 "primary_factors": ["air_quality", "wind_speed"]},
    "storm":    {"label": "Storm",    "blurb": "Sharp pressure drop and high winds signal an approaching storm.",
                 "primary_factors": ["barometric_pressure", "wind_speed", "humidity"]},
}

SCENARIOS = tuple(SCENARIO_DELTAS.keys())


def scenario_delta(scenario: str, environment: str, channel: str) -> float:
    """Return the additive delta for a (scenario, environment, channel)."""
    return SCENARIO_DELTAS.get(scenario, {}).get(environment, {}).get(channel, 0.0)
