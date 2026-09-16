"""Explainable risk engine for Climate Mesh.

For each node it computes six 0-100 hazard sub-scores (temperature, humidity,
air quality, water level, wind, pressure), combines them (worst hazard + 20% of
the rest) into a 0-100 base score, then amplifies that by an AI anomaly multiplier and a mesh-correlation
multiplier. A single isolated spike is treated with caution; the same anomaly
confirmed across adjacent nodes escalates the risk — that is the core mesh
idea. Every result carries its top contributing factors and a plain-English
explanation, and alerts are rate-limited so the log doesn't fill with
duplicates.
"""

from __future__ import annotations

import asyncio
import math

from ai.anomaly_model import AnomalyDetector
from backend.playbooks import playbook_text
from config.nodes import NEIGHBOURS, NODES_BY_ID
from data.database import (
    get_latest_readings_per_node, get_recent_alert, get_risk_scores,
    insert_alert, insert_risk_score,
)

# Risk bands (per spec): 0-30 SAFE, 30-60 MODERATE, 60-80 WARNING, 80-100 CRITICAL.
SAFE, MODERATE, WARNING, CRITICAL = "SAFE", "MODERATE", "WARNING", "CRITICAL"

# Don't re-fire the same alert type for the same node within this window unless
# its severity changes. Fifteen minutes, not seconds: the engine scores every
# three seconds, so a short window would put roughly 1,600 alerts an hour on
# screen during a storm -- the alert fatigue this project exists to prevent.
ALERT_COOLDOWN_SECONDS = 900

# A node counts as "elevated" (eligible for mesh correlation) at/above this base.
_ELEVATED_BASE = 30.0

# Neighbour agreement is a two-sided trust signal, not just an amplifier.
#
#   corroborated    elevated, and >=2 neighbours within 6 km see the same
#                   hazard             -> escalate
#   partial         elevated, exactly 1 neighbour agrees   -> leave alone
#   uncorroborated  elevated, and NO neighbour that could have agreed does
#                   -> damp, and report it as a possible sensor fault rather
#                      than as the hazard itself
#   unavailable     fewer than 2 neighbours in range, so corroboration is not
#                   possible here at all -> leave alone, and say so
#
# The damping is what stops one stuck sensor raising a full hazard alert. It is
# deliberately mild (a quarter off) because a real, genuinely local event that
# no neighbour can see must still be able to reach WARNING on its own severity.
_MESH_MULTIPLIER = 1.2
_UNCORROBORATED_MULTIPLIER = 0.75
_MIN_NEIGHBOURS_TO_CORROBORATE = 2

CORROBORATED = "corroborated"
PARTIAL = "partial"
UNCORROBORATED = "uncorroborated"
UNAVAILABLE = "unavailable"
QUIET = "quiet"


# --- Sub-scores ------------------------------------------------------------
# Each sub-score is a 0-100 *severity* for that single hazard. They are combined
# (below) so that one severe hazard alone can reach CRITICAL, while several
# moderate hazards together also escalate. 0 = comfortable/normal.

def _lin(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """Linear interpolation between (x0,y0) and (x1,y1)."""
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _finite(x: float) -> bool:
    """True for an ordinary number. NaN/inf compare False against every
    threshold, which would otherwise fall through to the *maximum* severity;
    a non-measured value must score 0, never CRITICAL."""
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _temp_sub(t: float) -> float:
    if not _finite(t): return 0.0
    if t >= 45:  return 100.0
    if t >= 40:  return _lin(t, 40, 90, 45, 100)
    if t >= 36:  return _lin(t, 36, 70, 40, 90)
    if t >= 30:  return _lin(t, 30, 40, 36, 70)
    if t >= 24:  return _lin(t, 24, 0, 30, 40)
    if t > 6:    return 0.0
    if t >= 0:   return _lin(t, 6, 0, 0, 50)
    if t >= -5:  return _lin(t, 0, 50, -5, 80)
    if t >= -10: return _lin(t, -5, 80, -10, 100)
    return 100.0


def _humidity_sub(h: float) -> float:
    if not _finite(h): return 0.0
    if h >= 100: return 70.0
    if h >= 85:  return _lin(h, 85, 25, 100, 70)
    if h > 25:   return 0.0
    if h >= 15:  return _lin(h, 25, 0, 15, 40)
    if h >= 10:  return _lin(h, 15, 40, 10, 60)
    return 60.0


def _aqi_sub(a: float) -> float:
    if not _finite(a): return 0.0
    if a >= 500: return 100.0
    if a >= 300: return _lin(a, 300, 90, 500, 100)
    if a >= 200: return _lin(a, 200, 70, 300, 90)
    if a >= 150: return _lin(a, 150, 50, 200, 70)
    if a >= 100: return _lin(a, 100, 30, 150, 50)
    if a >= 50:  return _lin(a, 50, 0, 100, 30)
    return 0.0


def _water_sub(w: float) -> float:
    if not _finite(w): return 0.0
    if w >= 8:   return 100.0
    if w >= 6:   return _lin(w, 6, 95, 8, 100)
    if w >= 4:   return _lin(w, 4, 75, 6, 95)
    if w >= 3:   return _lin(w, 3, 55, 4, 75)
    if w >= 2:   return _lin(w, 2, 30, 3, 55)
    if w >= 1.2: return _lin(w, 1.2, 0, 2, 30)
    return 0.0


def _wind_sub(v: float) -> float:
    if not _finite(v): return 0.0
    if v >= 35: return 100.0
    if v >= 25: return _lin(v, 25, 80, 35, 100)
    if v >= 15: return _lin(v, 15, 45, 25, 80)
    if v >= 8:  return _lin(v, 8, 0, 15, 45)
    return 0.0


def _pressure_sub(p: float) -> float:
    if not _finite(p): return 0.0
    if p <= 970:  return 100.0
    if p <= 980:  return _lin(p, 980, 80, 970, 100)
    if p <= 990:  return _lin(p, 990, 55, 980, 80)
    if p <= 1000: return _lin(p, 1000, 25, 990, 55)
    if p <= 1008: return _lin(p, 1008, 0, 1000, 25)
    return 0.0


def risk_level(score: float) -> str:
    if score >= 80: return CRITICAL
    if score >= 60: return WARNING
    if score >= 30: return MODERATE
    return SAFE


# Map each sub-score to a human label and the dominant hazard it implies.
_FACTOR_LABELS = {
    "water_sub": ("water level", "flood"),
    "humidity_sub": ("humidity", "flood"),
    "aqi_sub": ("air quality", "smog"),
    "temp_sub": ("temperature", "heatwave"),
    "wind_sub": ("wind speed", "storm"),
    "pressure_sub": ("pressure drop", "storm"),
}

# Hazards an alert can be filed under (each has a headline and a playbook).
HAZARDS = ("flood", "smog", "heatwave", "storm", "cold")


def _hazard_for(sub_key: str, reading: dict) -> str:
    """Dominant hazard for the top sub-score, taking the *direction* into
    account: temperature and humidity are two-sided scales, so a frosty
    morning is a cold hazard (not a 'heatwave') and very dry air is not a
    flood signal."""
    hazard = _FACTOR_LABELS[sub_key][1]
    if sub_key == "temp_sub" and float(reading.get("temperature", 15.0)) < 24:
        return "cold"
    if sub_key == "humidity_sub" and float(reading.get("humidity", 60.0)) < 85:
        return "risk"
    return hazard


def calculate_base(reading: dict, detector: AnomalyDetector, ai: dict | None = None) -> dict:
    """Compute the per-node base risk (no mesh correlation yet).

    ``ai`` is the detector's verdict for this reading; when omitted it is
    computed here. ``compute_all`` scores a whole cycle in one batch and
    passes the verdicts in, which is much cheaper on a Raspberry Pi.
    """
    subs = {
        "temp_sub": _temp_sub(reading["temperature"]),
        "humidity_sub": _humidity_sub(reading["humidity"]),
        "aqi_sub": _aqi_sub(reading["air_quality"]),
        "water_sub": _water_sub(reading["water_level"]),
        "wind_sub": _wind_sub(reading["wind_speed"]),
        "pressure_sub": _pressure_sub(reading["barometric_pressure"]),
    }
    # Combine: the worst single hazard drives the score, with a fractional
    # contribution from the others so co-occurring hazards escalate further.
    vals = list(subs.values())
    worst = max(vals)
    base_score = min(100.0, worst + 0.20 * (sum(vals) - worst))

    if ai is None:
        ai = detector.predict(reading)
    ai_multiplier = 1.0 + ai["score"] * 0.5 if ai["is_anomaly"] else 1.0

    # Top contributing factors, in order of contribution.
    ranked = sorted(subs.items(), key=lambda kv: kv[1], reverse=True)
    top_factors = [_FACTOR_LABELS[k][0] for k, v in ranked if v >= 15.0][:3]
    dominant_hazard = _hazard_for(ranked[0][0], reading) if ranked[0][1] >= 15.0 else "risk"

    return {
        "node_id": reading["node_id"],
        **{k: round(v, 1) for k, v in subs.items()},
        "base_score": round(base_score, 1),
        "anomaly_score": ai["score"],
        "is_anomaly": ai["is_anomaly"],
        "ai_multiplier": round(ai_multiplier, 2),
        "top_factors": top_factors,
        "dominant_hazard": dominant_hazard,
    }


def _contributor_phrase(label: str, reading: dict) -> str:
    """Render a top contributor as graded, value-embedded language, e.g.
    ``dangerous air quality (AQI 320)`` or ``critical water level (4.2 m)``.

    The severity word tracks how bad the reading actually is, and the real
    measured value is embedded — so the alert message and dashboard "Why?"
    read as plain English a non-expert can act on, rather than a bare channel
    name. Unknown labels fall back to themselves.
    """
    if label == "water level":
        w = float(reading.get("water_level", 0.0))
        word = ("severe flood water level" if w >= 6 else
                "critical water level" if w >= 4 else
                "high water level" if w >= 3 else "raised water level")
        return f"{word} ({w:.1f} m)"
    if label == "air quality":
        a = float(reading.get("air_quality", 0.0))
        word = ("hazardous air quality" if a >= 300 else
                "dangerous air quality" if a >= 200 else
                "unhealthy air quality" if a >= 150 else "poor air quality")
        return f"{word} (AQI {a:.0f})"
    if label == "temperature":
        t = float(reading.get("temperature", 0.0))
        word = ("extreme heat" if t >= 40 else
                "very high temperature" if t >= 36 else
                "high temperature" if t >= 30 else
                "warm temperature" if t >= 24 else
                "extreme cold" if t <= -5 else
                "freezing temperature" if t < 0 else "low temperature")
        return f"{word} ({t:.0f} °C)"
    if label == "humidity":
        h = float(reading.get("humidity", 0.0))
        word = ("very high humidity" if h >= 95 else
                "high humidity" if h >= 85 else
                "very low humidity" if h <= 10 else "low humidity")
        return f"{word} ({h:.0f}%)"
    if label == "wind speed":
        v = float(reading.get("wind_speed", 0.0))
        word = ("violent storm winds" if v >= 35 else
                "gale-force winds" if v >= 25 else "strong winds")
        return f"{word} ({v:.0f} m/s)"
    if label == "pressure drop":
        p = float(reading.get("barometric_pressure", 0.0))
        word = ("very low pressure" if p <= 970 else
                "low pressure" if p <= 980 else "falling pressure")
        return f"{word} ({p:.0f} hPa)"
    return label


def _explanation(reading: dict, base: dict, score: float,
                 corroboration: str, correlated_count: int,
                 mesh_degree: int = 0) -> str:
    name = NODES_BY_ID.get(reading["node_id"], {}).get("node_name", reading["node_id"])
    hazard = base["dominant_hazard"]
    factors = (", ".join(_contributor_phrase(f, reading) for f in base["top_factors"])
               if base["top_factors"] else "multiple factors")
    level = risk_level(score)
    if level == SAFE:
        return f"{name}: conditions normal. Risk score {math.floor(score)}/100."
    headline = {
        "flood": "Flood risk rising",
        "smog": "Air-quality risk rising",
        "heatwave": "Heat risk rising",
        "storm": "Storm risk rising",
        "cold": "Cold risk rising",
        "risk": "Risk rising",
    }.get(hazard, "Risk rising")
    if corroboration == UNCORROBORATED:
        # No neighbour that could have agreed does. Report it as what it most
        # likely is -- one faulty sensor -- rather than as the hazard.
        return (f"Check the sensor at {name}: it reports "
                f"{factors}, but none of its {mesh_degree} neighbours within "
                f"6 km sees the same thing. Treat as a possible sensor fault "
                f"and verify before acting. Risk score {math.floor(score)}/100.")
    mesh_clause = {
        CORROBORATED: f" Same trend seen across {correlated_count} nearby nodes.",
        PARTIAL: f" {correlated_count} of {mesh_degree} nearby nodes see the same trend.",
        # Count-aware: Ilford has exactly one neighbour, so a flat "no other
        # node is within 6 km" was false on the one node this branch exists
        # to describe.
        UNAVAILABLE: (" No other node is within 6 km, so this reading cannot be "
                      "corroborated." if mesh_degree == 0 else
                      f" Only {mesh_degree} other node{'' if mesh_degree == 1 else 's'} "
                      f"{'is' if mesh_degree == 1 else 'are'} within 6 km, which is "
                      "not enough to corroborate this reading."),
    }.get(corroboration, " Currently an isolated reading.")
    return (f"{headline} near {name}.{mesh_clause} "
            f"Risk score {math.floor(score)}/100. Main contributors: {factors}.")


def compute_all(readings: list[dict], detector: AnomalyDetector) -> list[dict]:
    """Compute full explainable risk for every reading, including mesh correlation."""
    verdicts = detector.predict_many(readings)
    bases = {r["node_id"]: calculate_base(r, detector, ai)
             for r, ai in zip(readings, verdicts)}
    reading_by_id = {r["node_id"]: r for r in readings}

    results = []
    for node_id, base in bases.items():
        reading = reading_by_id[node_id]
        # Mesh correlation: count neighbours that are also elevated/anomalous
        # for the SAME hazard -- "same trend", not merely "also busy".
        neighbours = NEIGHBOURS.get(node_id, [])
        elevated_neighbours = sum(
            1 for n in neighbours
            if n in bases
            and bases[n]["dominant_hazard"] == base["dominant_hazard"]
            and (bases[n]["base_score"] >= _ELEVATED_BASE or bases[n]["is_anomaly"])
        )
        self_elevated = base["base_score"] >= _ELEVATED_BASE or base["is_anomaly"]
        corroborable = len(neighbours) >= _MIN_NEIGHBOURS_TO_CORROBORATE
        if not self_elevated:
            corroboration = QUIET
        elif not corroborable:
            corroboration = UNAVAILABLE
        elif elevated_neighbours >= _MIN_NEIGHBOURS_TO_CORROBORATE:
            corroboration = CORROBORATED
        elif elevated_neighbours == 0:
            corroboration = UNCORROBORATED
        else:
            corroboration = PARTIAL
        correlated = corroboration == CORROBORATED
        mesh_multiplier = {CORROBORATED: _MESH_MULTIPLIER,
                           UNCORROBORATED: _UNCORROBORATED_MULTIPLIER}.get(corroboration, 1.0)

        # Round once, up front, so the stored score, the band and the text a
        # judge reads all agree (79.96 must not be WARNING with "80/100").
        score = round(min(100.0, base["base_score"] * base["ai_multiplier"] * mesh_multiplier), 1)
        level = risk_level(score)
        explanation = _explanation(reading, base, score, corroboration,
                                   elevated_neighbours, len(neighbours))

        results.append({
            "node_id": node_id,
            "score": score,
            "level": level,
            "temp_sub": base["temp_sub"],
            "humidity_sub": base["humidity_sub"],
            "aqi_sub": base["aqi_sub"],
            "water_sub": base["water_sub"],
            "wind_sub": base["wind_sub"],
            "pressure_sub": base["pressure_sub"],
            "anomaly_score": base["anomaly_score"],
            "ai_multiplier": base["ai_multiplier"],
            "mesh_multiplier": mesh_multiplier,
            "correlated": correlated,
            "correlated_count": elevated_neighbours,
            "corroboration": corroboration,
            "mesh_degree": len(neighbours),
            "top_factors": base["top_factors"],
            "dominant_hazard": base["dominant_hazard"],
            "explanation": explanation,
        })
    return results


def alert_type_for(risk: dict) -> str:
    """The one place that decides which playbook a scored node gets.

    An uncorroborated reading must not raise the hazard's playbook: the most
    likely explanation is a broken sensor, and telling a site team to clear
    drains on the word of one unconfirmed node is the failure this project
    exists to avoid. Every surface that shows a playbook -- the alert row, the
    Live Map panel, Node Detail -- calls this, so none of them can disagree
    with the others about the same node.
    """
    if risk.get("corroboration") == UNCORROBORATED:
        return "sensor-check"
    hazard = risk.get("dominant_hazard")
    return hazard if hazard in HAZARDS else "risk"


def maybe_alert(reading: dict, risk: dict) -> bool:
    """Create an alert if warranted, respecting cooldown and severity changes.

    Returns True if an alert was written. An alert fires only when there is no
    recent alert of the same type for this node, OR the severity has changed
    since the last one — preventing duplicate spam every loop.
    """
    if risk["level"] in (SAFE, MODERATE):
        return False

    alert_type = alert_type_for(risk)
    if alert_type == "sensor-check":
        severity = "warning"
    else:
        severity = "critical" if risk["level"] == CRITICAL else "warning"

    recent = get_recent_alert(reading["node_id"], alert_type, ALERT_COOLDOWN_SECONDS)
    if recent is not None and recent["severity"] == severity:
        return False  # within cooldown and severity unchanged -> suppress

    insert_alert(
        node_id=reading["node_id"],
        alert_type=alert_type,
        message=risk["explanation"],
        severity=severity,
        scenario=reading.get("scenario", "none"),
        playbook=playbook_text(alert_type),
        # Carry the triggering reading's provenance so each alert self-labels.
        source=reading.get("source", "simulation"),
        is_simulated=reading.get("is_simulated", True),
    )
    return True


async def run_risk_engine(detector: AnomalyDetector, interval: float = 3.0):
    """Async loop: compute risk for all nodes every ``interval`` seconds."""
    print("[Risk Engine] Started (explainable scoring + mesh correlation)")
    while True:
        readings = get_latest_readings_per_node()
        if readings:
            results = compute_all(readings, detector)
            by_id = {r["node_id"]: r for r in results}
            for reading in readings:
                risk = by_id[reading["node_id"]]
                insert_risk_score(risk)
                maybe_alert(reading, risk)
            scores = get_risk_scores()
            if scores:
                avg = sum(s["score"] for s in scores) / len(scores)
                print(f"[Risk Engine] {len(readings)} nodes | avg risk {avg:.1f}")
        await asyncio.sleep(interval)
