"""Canonical readings from recorded hourly arrays; no network or scenario deltas."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config.nodes import NODES
from sensors.api_adapter import _BASE_WATER, _PRECIP_SENSITIVITY, _eu_aqi_to_us_scale
from sensors.base import SensorAdapter, make_reading
from simulation.engine import _heat_index, _wind_chill


class HistoryAdapter(SensorAdapter):
    source = "archive"

    def __init__(self, fixture_path, rain_override=None):
        self.fixture = json.loads(Path(fixture_path).read_text())
        self.rain_override = rain_override or {}
        for node_id, values in self.rain_override.items():
            if node_id not in self.fixture["nodes"] or len(values) != len(self.fixture["hours"]):
                raise ValueError("rain override must match an existing node and all event hours")

    def read_hour(self, i: int) -> list[dict]:
        hours = self.fixture["hours"]
        hour = hours[i]
        timestamp = datetime.fromisoformat(hour).replace(
            tzinfo=ZoneInfo(self.fixture["timezone"])).astimezone(timezone.utc).isoformat()
        day_start = i
        while day_start > 0 and hours[day_start - 1][:10] == hour[:10]:
            day_start -= 1
        readings = []
        for node in NODES:
            data = self.fixture["nodes"][node["node_id"]]
            temp = data["temperature_2m"][i]
            humidity = data["relative_humidity_2m"][i]
            wind = data["wind_speed_10m"][i]
            apparent = data["apparent_temperature"][i]
            if apparent is None:
                wind_chill, heat_index = _wind_chill(temp, wind), _heat_index(temp, humidity)
            else:
                wind_chill = min(apparent, temp) if temp < 12 else temp
                heat_index = max(apparent, temp) if temp >= 26 else temp
            rain = self.rain_override.get(node["node_id"], data["precipitation"])
            total = sum(rain[day_start:i + 1])
            env = node["environment"]
            readings.append(make_reading(
                node, temperature=temp, humidity=humidity,
                wind_speed=wind, barometric_pressure=data["pressure_msl"][i],
                wind_chill=wind_chill, heat_index=heat_index,
                water_level=_BASE_WATER[env] + _PRECIP_SENSITIVITY[env] * total,
                air_quality=_eu_aqi_to_us_scale(data["european_aqi"][i]),
                source=self.source, quality_flag="estimated", scenario="none", timestamp=timestamp,
            ))
        return readings

    def read_all(self, scenario: str = "none", tick: float = 0.0) -> list[dict]:
        """A tick is an integer hour index, starting at zero."""
        if int(tick) != tick or tick < 0:
            raise ValueError("history tick must be a nonnegative integer hour index")
        return self.read_hour(int(tick))
