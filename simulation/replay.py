"""Offline event replay through the live model, mesh and SQLite alert path.

One cycle per recorded hour. The database clock is the sample's UTC instant;
900-second cooldowns expire between hourly cycles. We do not invent the 3s
samples a continuously running engine would have seen between these hours.
The private in-memory database never touches the live database.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ai.anomaly_model import AnomalyDetector
from backend import risk_engine
from config.nodes import NODES, haversine_km
from data import database
from sensors.history_adapter import HistoryAdapter
from scripts.fetch_history import EVENTS
from simulation.replay_io import alert_metrics, read_json, write_json

ROOT = Path(__file__).resolve().parent.parent
EVENT_IDS = tuple(EVENTS)


def local_gauge_hours(gauge, hours):
    """Sum UTC-labelled 15min totals into local clock hours, without interpolation.

    EA's requested UTC day lacks the first BST hour, and includes one hour
    outside the local window. Counts and outside totals are reported explicitly.
    """
    totals = dict.fromkeys(hours, 0.0)
    counts = dict.fromkeys(hours, 0)
    outside = 0.0
    for r in gauge["readings"]:
        if r["mm"] is None:
            continue
        t = datetime.fromisoformat(r["t_utc"].replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)  # EA hydrology times are UTC
        local = t.astimezone(ZoneInfo("Europe/London")).replace(minute=0, second=0, microsecond=0)
        key = local.replace(tzinfo=None).isoformat(timespec="minutes")
        if key in totals:
            totals[key] += r["mm"]
            counts[key] += 1
        else:
            outside += r["mm"]
    # Round to the gauge resolution scale so float summation order cannot change the output.
    return [round(v, 3) for v in totals.values()], list(counts.values()), round(outside, 3)


def select_gauges(fixture):
    reports = []
    for gauge in fixture["gauges"]:
        distances = [(haversine_km(gauge["lat"], gauge["lon"], n["latitude"], n["longitude"]),
                      n["node_id"]) for n in NODES]
        distance, node_id = min(distances)
        hourly, counts, outside = local_gauge_hours(gauge, fixture["hours"])
        reasons = []
        if not gauge["readings"] or any(r["quality"] != "Good" for r in gauge["readings"]):
            reasons.append("not all readings are Good")
        missing = sum(r["mm"] is None for r in gauge["readings"])
        if missing:
            reasons.append("missing rainfall values")
        if distance > 3.0:
            reasons.append("nearest node is farther than 3.0 km")
        reports.append({"label": gauge["label"], "reference": gauge["reference"],
                        "nearest_node": node_id, "distance_km": distance,
                        "total_mm": None if missing else round(sum(r["mm"] for r in gauge["readings"]), 3),
                        "available_total_mm": round(sum(r["mm"] for r in gauge["readings"] if r["mm"] is not None), 3),
                        "missing_readings": missing,
                        "window_total_mm": round(sum(hourly), 3), "outside_window_mm": outside,
                        "peak_hour": fixture["hours"][hourly.index(max(hourly))] if any(counts) else None,
                        "peak_hour_mm": max(hourly) if any(counts) else None, "hourly_mm": hourly,
                        "readings_per_hour": counts, "used": not reasons,
                        "reason": "; ".join(reasons) if reasons else "all Good and within 3.0 km"})
    # Multiple qualifying gauges for one node: nearest wins; never add or blend.
    overrides = {}
    for report in sorted(reports, key=lambda r: (r["distance_km"], r["label"], str(r["reference"]))):
        if not report["used"]:
            continue
        node_id = report["nearest_node"]
        if node_id in overrides:
            report["used"] = False
            report["reason"] = "a closer qualifying gauge already overrides this node"
        else:
            overrides[node_id] = report["hourly_mm"]
    return overrides, reports


def replay(event_id, variant="grid"):
    if event_id not in EVENT_IDS:
        raise ValueError(f"unknown event: {event_id}")
    if variant not in ("grid", "gauges") or (variant == "gauges" and not event_id.startswith("flood")):
        raise ValueError("gauges variant is available only for the flood event")
    path = ROOT / "data" / "history" / f"{event_id}.json"
    fixture = read_json(path)
    overrides, gauge_reports = select_gauges(fixture)
    adapter = HistoryAdapter(path, overrides if variant == "gauges" else None)
    training = fixture["training"]
    cutoff = datetime.fromisoformat(fixture["hours"][0]).replace(tzinfo=ZoneInfo("Europe/London"))
    if any(datetime.fromisoformat(t).replace(tzinfo=timezone.utc) >= cutoff
           for t in training["weather"]["hourly"]["time"]):
        raise ValueError("training includes event data")
    detector = AnomalyDetector().train_archive(training["weather"], training["air"])
    per_hour = []
    clock = None

    class ReplayDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz) if tz else clock.replace(tzinfo=None)

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        with patch.object(database, "_get_conn", return_value=connection), \
                patch.object(database, "datetime", ReplayDateTime):
            database.init_db()
            for i, hour in enumerate(fixture["hours"]):
                readings = adapter.read_hour(i)
                clock = datetime.fromisoformat(readings[0]["timestamp"])
                database.insert_readings(readings)
                latest = database.get_latest_readings_per_node()
                results = risk_engine.compute_all(latest, detector)
                by_id = {r["node_id"]: r for r in results}
                originals = {r["node_id"]: r for r in readings}
                rows = []
                for reading in latest:
                    risk = by_id[reading["node_id"]]
                    database.insert_risk_score(risk)
                    raised = risk_engine.maybe_alert(reading, risk)
                    rows.append({**originals[reading["node_id"]], **risk, "band": risk["level"],
                                 "alert": risk_engine.alert_type_for(risk) if raised else None})
                per_hour.append({"hour": hour, "nodes": rows})
    finally:
        connection.close()
    all_rows = [r for step in per_hour for r in step["nodes"]]
    peaks, first_bands = {}, {}
    for node in NODES:
        node_id = node["node_id"]
        entries = [(s["hour"], next(r for r in s["nodes"] if r["node_id"] == node_id))
                   for s in per_hour]
        hour, peak = max(entries, key=lambda pair: pair[1]["score"])
        peaks[node_id] = {"score": peak["score"], "hour": hour, "band": peak["band"]}
        # First observed membership in each band (no inferred intermediate bands).
        first_bands[node_id] = {band: next((h for h, r in entries if r["band"] == band), None)
                                for band in ("SAFE", "MODERATE", "WARNING", "CRITICAL")}
    quiet = per_hour[:6]
    quiet_rows = [r for step in quiet for r in step["nodes"]]
    summary = {"peak_score": max(r["score"] for r in all_rows),
               "peak_per_node": peaks, "first_band_per_node": first_bands,
               "alerts_by_type": dict(sorted(Counter(r["alert"] for r in all_rows if r["alert"]).items())),
               "damped_nodes": sorted({r["node_id"] for r in all_rows
                                       if r["corroboration"] == "uncorroborated"}),
               "quiet_hours": {"hours": [s["hour"] for s in quiet],
                               "scores": {n["node_id"]: [next(r["score"] for r in s["nodes"]
                                                            if r["node_id"] == n["node_id"])
                                                         for s in quiet] for n in NODES},
                               "peak_score": max(r["score"] for r in quiet_rows),
                               "ai_amplified_node_hours": sum(r["ai_multiplier"] > 1 for r in quiet_rows),
                               "alerts_by_type": dict(sorted(Counter(r["alert"] for r in quiet_rows
                                                                      if r["alert"]).items()))},
               "gauges": gauge_reports if variant == "gauges" else []}
    return {"event_id": event_id, "variant": variant, "title": fixture["title"],
            "timezone": fixture["timezone"], "window": fixture["window"],
            "training": detector.status(), "source": "archive", "quality_flag": "estimated",
            "clock_policy": "One cycle per recorded hour; UTC sample clock; 900s cooldown expires between hours. "
                            "No interpolated cycles or claims about alerts between samples.",
            "gauge_policy": "All Good, within 3.0 km; closest qualifying gauge wins per node. "
                            "UTC-day request omits first BST hour: empty buckets sum to zero, not measured dryness. "
                            "See readings_per_hour and outside_window_mm.",
            "summary": {**summary, **alert_metrics(per_hour)}, "per_hour": per_hour}


def write_replay(payload, out):
    suffix = ".json.gz" if payload['event_id'].startswith('holdout') else ".json"
    path = Path(out) / f"{payload['event_id']}-{payload['variant']}{suffix}"
    return write_json(payload, path)
