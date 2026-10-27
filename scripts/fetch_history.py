"""Fetch unmodified public event arrays; never substitute invented data."""
from __future__ import annotations

import argparse
import difflib
import json
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai.anomaly_model import (
    ARCHIVE_AIR_URL, ARCHIVE_LAT, ARCHIVE_LON, ARCHIVE_WEATHER_HOURLY,
    ARCHIVE_WEATHER_URL,
)
from config.nodes import NODES
from sensors.api_adapter import ApiUnavailable, _http_get_json

ROOT = Path(__file__).resolve().parent.parent
EVENTS = {
    "flood-2021-07-12": ("2021-07-12", "2021-07-12", "London flash floods, 12 July 2021"),
    "heat-2022-07-19": ("2022-07-18", "2022-07-19", "UK record heat, 18-19 July 2022"),
    "storm-2022-02-18": ("2022-02-18", "2022-02-18", "Storm Eunice, 18 February 2022"),
}
GRID_HOURLY = ("temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,"
               "wind_gusts_10m,pressure_msl,apparent_temperature")
GAUGE_URL = "https://environment.data.gov.uk/hydrology/id/stations.json"
GAUGE_PARAMS = {"observedProperty": "rainfall", "lat": 51.51, "long": -0.12,
                "dist": 16, "_limit": 100}


def json_text(payload):
    return json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"


def without_retrieved(value):
    if isinstance(value, dict):
        return {k: without_retrieved(v) for k, v in value.items() if k != "retrieved_utc"}
    if isinstance(value, list):
        return [without_retrieved(v) for v in value]
    return value


def fetch_event(event_id):
    start, end, title = EVENTS[event_id]
    provenance = {}

    def get(kind, url, params, *, ea=False):
        full = url + "?" + urllib.parse.urlencode(params)
        try:
            result = _http_get_json(url, params, timeout=60)
        except ApiUnavailable as exc:
            raise ApiUnavailable(f"{event_id} {kind}: {full}: {exc}") from exc
        item = {"url": full,
                "licence": "Open Government Licence v3.0" if ea else "CC BY 4.0",
                "attribution": ("Contains Environment Agency data" if ea else
                                "Weather data by Open-Meteo.com"),
                "retrieved_utc": datetime.now(timezone.utc).isoformat()}
        if kind in provenance:
            old = provenance[kind]
            old.setdefault("requests", [old["url"]]).append(full)
        else:
            provenance[kind] = item
        return result

    common = {"latitude": ",".join(str(n["latitude"]) for n in NODES),
              "longitude": ",".join(str(n["longitude"]) for n in NODES),
              "start_date": start, "end_date": end, "timezone": "Europe/London"}
    weather = get("grid", ARCHIVE_WEATHER_URL,
                  {**common, "hourly": GRID_HOURLY, "wind_speed_unit": "ms"})
    air = get("air", ARCHIVE_AIR_URL, {**common, "hourly": "european_aqi"})
    if not isinstance(weather, list) or not isinstance(air, list):
        raise ValueError("multi-coordinate responses must be lists")
    if len(weather) != len(NODES) or len(air) != len(NODES):
        raise ValueError("multi-coordinate response missing nodes")
    hours = weather[0]["hourly"]["time"]
    nodes = {}
    for node, w, a in zip(NODES, weather, air):
        if w["hourly"]["time"] != hours or a["hourly"]["time"] != hours:
            raise ValueError("weather and air hourly axes differ")
        arrays = {k: w["hourly"][k] for k in GRID_HOURLY.split(",")}
        arrays["european_aqi"] = a["hourly"]["european_aqi"]
        if any(len(v) != len(hours) for v in arrays.values()):
            raise ValueError("incomplete hourly arrays")
        if any(v is None for k, values in arrays.items()
               if k not in ("european_aqi", "apparent_temperature") for v in values):
            raise ValueError("missing required weather observations")
        nodes[node["node_id"]] = arrays
    # Match historical training's UTC, single location, variables and m/s units.
    # Thirty inclusive dates; all finish before the local event begins.
    training_end = date.fromisoformat(start) - timedelta(days=1)
    training_start = training_end - timedelta(days=29)
    cutoff = datetime.fromisoformat(start).replace(tzinfo=ZoneInfo("Europe/London"))
    train_begin = datetime.fromisoformat(training_start.isoformat()).replace(
        tzinfo=ZoneInfo("Europe/London"))
    train_common = {"latitude": ARCHIVE_LAT, "longitude": ARCHIVE_LON,
                    "start_date": train_begin.astimezone(timezone.utc).date().isoformat(),
                    "end_date": training_end.isoformat(), "timezone": "UTC"}
    tw = get("training", ARCHIVE_WEATHER_URL,
             {**train_common, "hourly": ARCHIVE_WEATHER_HOURLY, "wind_speed_unit": "ms"})
    ta = get("training", ARCHIVE_AIR_URL, {**train_common, "hourly": "european_aqi"})
    # A UTC request for the preceding date includes local event midnight in BST.
    # Select exactly the preceding 30 local dates, preserving all raw values.
    for raw in (tw, ta):
        indices = [i for i, t in enumerate(raw["hourly"]["time"])
                   if train_begin <= datetime.fromisoformat(t).replace(tzinfo=timezone.utc) < cutoff]
        raw["hourly"] = {k: [v[i] for i in indices] for k, v in raw["hourly"].items()}
    if tw["hourly"]["time"] != ta["hourly"]["time"]:
        raise ValueError("training weather and air hourly axes differ")
    for raw in (tw, ta):
        if len(raw["hourly"]["time"]) != 720 or any(
                len(values) != 720 for values in raw["hourly"].values()):
            raise ValueError("training response does not cover the preceding 720 hours")
    # Retain the raw hourly values, excluding volatile API generation timings.
    training = {"weather": {"hourly": tw["hourly"]}, "air": {"hourly": ta["hourly"]},
                "window": [training_start.isoformat(), training_end.isoformat()],
                "timezone": "UTC", "latitude": ARCHIVE_LAT, "longitude": ARCHIVE_LON}
    gauges = []
    if event_id.startswith("flood"):
        stations = get("gauges", GAUGE_URL, GAUGE_PARAMS, ea=True)["items"]
        for station in sorted(stations, key=lambda s: s["@id"]):
            measures = sorted(m["@id"] for m in station.get("measures", [])
                              if "rainfall-t-900" in m["@id"])
            if not measures:
                continue
            url = measures[0].replace("http://", "https://") + "/readings.json"
            items = get("gauges", url, {"mineq-date": start, "max-date": "2021-07-13",
                                        "_limit": 200}, ea=True)["items"]
            if not items:
                continue
            if len(items) >= 200:
                raise ValueError("gauge readings may be truncated")
            gauges.append({"label": station["label"], "reference": station.get("stationReference"),
                           "lat": station["lat"], "lon": station["long"],
                           "readings": [{"t_utc": r["dateTime"], "mm": r.get("value"),
                                         "quality": r["quality"]}
                                        for r in sorted(items, key=lambda r: r["dateTime"])]})
    return {"event_id": event_id, "title": title, "timezone": "Europe/London",
            "window": [start, end], "provenance": provenance, "hours": hours,
            "nodes": nodes, "training": training, "gauges": gauges}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=EVENTS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    different = False
    for event in [args.event] if args.event else EVENTS:
        payload = fetch_event(event)  # finish/validate before touching any fixture
        path = ROOT / "data" / "history" / f"{event}.json"
        if args.check:
            old = json.loads(path.read_text()) if path.exists() else None
            changed = without_retrieved(old) != without_retrieved(payload)
            print(f"{event}: {'DIFFERENT' if changed else 'unchanged'}")
            if changed:
                sys.stdout.writelines(difflib.unified_diff(
                    json_text(without_retrieved(old)).splitlines(keepends=True),
                    json_text(without_retrieved(payload)).splitlines(keepends=True),
                    fromfile=str(path), tofile="refetched"))
            different |= changed
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json_text(payload))
            temporary.replace(path)
            print(f"{event}: wrote {len(payload['hours'])} hours, {len(payload['nodes'])} nodes, "
                  f"{len(payload['gauges'])} gauges to {path.relative_to(ROOT)}")
    return int(different)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApiUnavailable, ValueError, KeyError, OSError) as exc:
        raise SystemExit(f"History fetch failed; no partial fixture written: {exc}")
