"""Sensor adapter base classes and the canonical Climate Mesh reading shape.

The whole point of this module is the *contract*: every data source —
simulation, live API, or physical hardware — produces a reading with exactly
the same keys. The risk engine, AI model, dashboard, and database therefore
never need to know or care where a reading came from. To add a new sensor you
write one adapter that returns ``make_reading(...)`` and nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

# The canonical set of measurement channels carried by every reading.
MEASUREMENT_FIELDS = (
    "temperature",          # °C
    "humidity",             # % relative humidity
    "air_quality",          # AQI-like 0-500 scale
    "water_level",          # metres
    "wind_speed",           # m/s
    "wind_chill",           # °C apparent
    "heat_index",           # °C perceived
    "barometric_pressure",  # hPa
)

# Valid values for the ``source`` field. These are the only data provenances
# the system recognises, and they are always shown to the user so nobody can
# mistake simulated or API data for physical-sensor data.
VALID_SOURCES = ("simulation", "demo", "api", "hardware")

# Valid quality flags. ``ok`` = trustworthy; ``estimated`` = derived/proxy
# value (e.g. API water level from precipitation); ``stale`` = last-known-good
# reused because a live read failed; ``missing`` = no value available.
VALID_QUALITY_FLAGS = ("ok", "estimated", "stale", "missing")


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp (timezone-aware)."""
    return datetime.now(timezone.utc).isoformat()


def make_reading(
    node: dict,
    *,
    temperature: float,
    humidity: float,
    air_quality: float,
    water_level: float,
    wind_speed: float,
    wind_chill: float,
    heat_index: float,
    barometric_pressure: float,
    source: str,
    quality_flag: str = "ok",
    scenario: str = "none",
    timestamp: str | None = None,
) -> dict:
    """Build a reading in the canonical shape from a ``node`` registry entry.

    ``is_simulated`` is derived from ``source`` so it can never disagree with
    it: anything that is not real ``hardware`` data is flagged as simulated.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"invalid source {source!r}; expected one of {VALID_SOURCES}")
    if quality_flag not in VALID_QUALITY_FLAGS:
        raise ValueError(f"invalid quality_flag {quality_flag!r}")

    return {
        "node_id": node["node_id"],
        "node_name": node["node_name"],
        "environment": node["environment"],
        "latitude": node["latitude"],
        "longitude": node["longitude"],
        "temperature": round(float(temperature), 2),
        "humidity": round(float(humidity), 2),
        "air_quality": round(float(air_quality), 2),
        "water_level": round(float(water_level), 3),
        "wind_speed": round(float(wind_speed), 2),
        "wind_chill": round(float(wind_chill), 2),
        "heat_index": round(float(heat_index), 2),
        "barometric_pressure": round(float(barometric_pressure), 2),
        "source": source,
        "is_simulated": source != "hardware",
        "quality_flag": quality_flag,
        "scenario": scenario or "none",
        "timestamp": timestamp or utc_now_iso(),
    }


def validate_reading(reading: dict) -> None:
    """Raise ``ValueError`` if a reading is missing required keys or malformed.

    Used by tests and the smoke test to guarantee the contract holds for every
    adapter, regardless of how the reading was produced.
    """
    required = (
        "node_id", "node_name", "environment", "latitude", "longitude",
        *MEASUREMENT_FIELDS,
        "source", "is_simulated", "quality_flag", "scenario", "timestamp",
    )
    missing = [k for k in required if k not in reading]
    if missing:
        raise ValueError(f"reading missing keys: {missing}")
    if reading["source"] not in VALID_SOURCES:
        raise ValueError(f"reading has invalid source {reading['source']!r}")
    if reading["quality_flag"] not in VALID_QUALITY_FLAGS:
        raise ValueError(f"reading has invalid quality_flag {reading['quality_flag']!r}")
    if reading["is_simulated"] != (reading["source"] != "hardware"):
        raise ValueError("is_simulated disagrees with source")


class SensorAdapter(ABC):
    """Base class for every Climate Mesh data source.

    Subclasses implement :meth:`read_all`, returning a list of canonical
    readings (one per node they are responsible for). ``source`` names the
    provenance shown to the user.
    """

    source: str = "simulation"

    @abstractmethod
    def read_all(self, scenario: str = "none", tick: float = 0.0) -> list[dict]:
        """Return one canonical reading per node this adapter covers."""
        raise NotImplementedError

    def cleanup(self) -> None:  # pragma: no cover - default no-op
        """Release any resources (hardware handles, sockets). Safe to call always."""
        return None
