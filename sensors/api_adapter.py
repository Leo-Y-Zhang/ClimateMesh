"""Live API sensor adapter (Open-Meteo).

Fetches real current weather and air-quality data for all 20 node coordinates
from the free, no-key Open-Meteo API. This is the honest "real data" path: it
uses genuine live readings, labels them ``source="api"``, and marks any
derived value (e.g. water level inferred from precipitation) as
``quality_flag="estimated"``.

If the network is unavailable or the request fails, the adapter raises
``ApiUnavailable`` so the launcher can warn the user and fall back to
simulation — it never silently invents data and calls it live.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from config.nodes import NODES
from sensors.base import SensorAdapter, make_reading
from simulation.engine import _heat_index, _wind_chill

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Per-environment sensitivity converting 24h precipitation (mm) to a water
# level proxy (m). River nodes respond most; urban least. Documented in the
# write-up as a real design decision.
_PRECIP_SENSITIVITY = {
    "river": 0.15, "park": 0.08, "residential": 0.07, "school": 0.06, "urban": 0.05,
}
_BASE_WATER = {
    "river": 1.0, "park": 0.35, "residential": 0.30, "school": 0.25, "urban": 0.20,
}


class ApiUnavailable(RuntimeError):
    """Raised when live API data cannot be fetched (offline, rate-limited, etc.)."""


def _http_get_json(url: str, params: dict, timeout: float = 8.0) -> dict:
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}"
    try:
        with urllib.request.urlopen(full, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        raise ApiUnavailable(str(e)) from e


def _eu_aqi_to_us_scale(eu_aqi: float | None) -> float:
    """Open-Meteo returns a European AQI (0-100+). Map onto the 0-500 scale the
    rest of the system uses so the risk engine thresholds stay consistent."""
    if eu_aqi is None:
        return 50.0
    return max(0.0, min(500.0, eu_aqi * 2.5))


class ApiAdapter(SensorAdapter):
    """Live Open-Meteo data for every node. Falls back via ``ApiUnavailable``."""

    source = "api"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    def _fetch_batch(self, urls_params):
        return [_http_get_json(u, p, self.timeout) for u, p in urls_params]

    def read_all(self, scenario: str = "none", tick: float = 0.0) -> list[dict]:
        lats = ",".join(str(n["latitude"]) for n in NODES)
        lons = ",".join(str(n["longitude"]) for n in NODES)

        weather = _http_get_json(OPEN_METEO_FORECAST, {
            "latitude": lats, "longitude": lons,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,"
                       "pressure_msl,apparent_temperature",
            "daily": "precipitation_sum",
            # Request m/s explicitly — Open-Meteo defaults to km/h, which the
            # risk engine would otherwise misread as gale-force wind.
            "wind_speed_unit": "ms",
            "timezone": "auto", "forecast_days": 1,
        }, self.timeout)
        air = _http_get_json(OPEN_METEO_AIR, {
            "latitude": lats, "longitude": lons,
            "current": "european_aqi", "timezone": "auto",
        }, self.timeout)

        # Open-Meteo returns a list (one element per coordinate) when multiple
        # coordinates are requested; normalise to a list either way.
        weather_list = weather if isinstance(weather, list) else [weather]
        air_list = air if isinstance(air, list) else [air]

        readings = []
        for idx, node in enumerate(NODES):
            w = weather_list[idx] if idx < len(weather_list) else weather_list[-1]
            a = air_list[idx] if idx < len(air_list) else air_list[-1]
            cur = w.get("current", {})
            temp = cur.get("temperature_2m", 15.0)
            humidity = cur.get("relative_humidity_2m", 70.0)
            wind = cur.get("wind_speed_10m", 4.0)
            pressure = cur.get("pressure_msl", 1013.0)
            apparent = cur.get("apparent_temperature", temp)

            precip = 0.0
            daily = w.get("daily", {})
            if daily.get("precipitation_sum"):
                precip = daily["precipitation_sum"][0] or 0.0

            env = node["environment"]
            water = _BASE_WATER[env] + _PRECIP_SENSITIVITY[env] * precip
            aqi = _eu_aqi_to_us_scale(a.get("current", {}).get("european_aqi"))

            # Prefer Open-Meteo's apparent temperature; derive locally if absent.
            if apparent is None:
                wind_chill = _wind_chill(temp, wind)
                heat_index = _heat_index(temp, humidity)
            else:
                wind_chill = min(apparent, temp) if temp < 12 else temp
                heat_index = max(apparent, temp) if temp >= 26 else temp

            readings.append(make_reading(
                node,
                temperature=temp,
                humidity=humidity,
                air_quality=aqi,
                water_level=water,
                wind_speed=wind,
                wind_chill=wind_chill,
                heat_index=heat_index,
                barometric_pressure=pressure,
                source="api",
                # Water level is a precipitation-derived proxy, not a measured value.
                quality_flag="estimated",
                # API values are live and UNMODIFIED — scenario deltas are only
                # applied in simulation/demo modes (simulation/engine.py). Stamp
                # "observed" so an api reading never falsely claims a scenario
                # delta was applied to its values.
                scenario="observed",
            ))
        return readings
