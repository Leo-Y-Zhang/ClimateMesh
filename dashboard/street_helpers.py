"""Pure street-display decisions; database access stays in the page loaders."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dashboard.formatting import age_seconds


def join_nodes(readings: list[dict], risks: list[dict]) -> list[dict]:
    by_id = {r["node_id"]: r for r in risks}
    return [
        {
            **r,
            **by_id[r["node_id"]],
            "timestamp": r.get("timestamp"),
            "risk_timestamp": by_id[r["node_id"]].get("timestamp"),
        }
        for r in readings
        if r["node_id"] in by_id
    ]


def data_age(row: dict, now: datetime | None = None) -> float | None:
    """The older of the reading and score; missing timestamps fail closed."""
    ages = []
    for key in ("timestamp", "risk_timestamp"):
        stamp = row.get(key)
        if now is None:
            age = age_seconds(stamp)
        else:
            try:
                dt = datetime.fromisoformat(stamp)
                age = (
                    now - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
                ).total_seconds()
            except (TypeError, ValueError):
                age = None
        if age is None:
            return None
        ages.append(max(0.0, age))
    return max(ages)


def is_fresh(row: dict, now: datetime | None = None) -> bool:
    age = data_age(row, now)
    return (
        age is not None
        and age <= 30
        and row.get("quality_flag") not in ("stale", "missing")
    )


def rotation_order(rows: list[dict], node: str | None = None) -> list[dict]:
    if node:
        return [r for r in rows if r["node_id"] == node]
    ordered = sorted(rows, key=lambda r: (-float(r["score"]), r["node_id"]))
    return ordered[:3] if any(r["level"] != "SAFE" for r in ordered) else ordered


def select_node(
    rows: list[dict], elapsed: float, node: str | None = None
) -> dict | None:
    ordered = rotation_order(rows, node)
    if not ordered:
        return None
    interval = rotation_interval(ordered)
    return ordered[int(max(0, elapsed) // interval) % len(ordered)]


def mesh_status(state: str, agreeing: int = 0) -> str:
    if state == "uncorroborated":
        return "No neighbour agrees: check this sensor"
    if state == "unavailable":
        return "Not enough neighbours to confirm"
    if state in ("corroborated", "partial"):
        return f"{agreeing} neighbour{' agrees' if agreeing == 1 else 's agree'}"
    return "No raised trend at this site"


# All neutral text pairs are shared by the page and contrast tests. Band and
# source-badge ink is chosen independently from their own background colour.
THEMES = {
    "dark": {
        "background": "#101820", "surface": "#1b2834", "ink": "#f6f7f8",
        "muted": "#c2ced8", "line": "#8195a5", "track": "#435465",
    },
    "light": {
        "background": "#eef2f5", "surface": "#ffffff", "ink": "#142330",
        "muted": "#415568", "line": "#65788a", "track": "#d9e1e8",
    },
}


def london_time(now: datetime | None = None) -> str:
    """UK wall-clock time, independent of the host's OS timezone names."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ZoneInfo("Europe/London")).strftime("%H:%M %Z")


def environment_label(value: str | None) -> str:
    return str(value or "").strip().capitalize()


def rotation_interval(rows: list[dict]) -> int:
    return 20 if all(r["level"] == "SAFE" for r in rows) else 8


def site_position(rows: list[dict], row: dict, pinned: bool = False) -> str:
    """Rotation position, or the pinned site's index in the full score order."""
    ordered = (
        sorted(rows, key=lambda r: (-float(r["score"]), r["node_id"]))
        if pinned else rotation_order(rows)
    )
    index = next(i for i, r in enumerate(ordered) if r["node_id"] == row["node_id"])
    return f"Site {index + 1} of {len(ordered)}"


def _number(value, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


HAZARD_FACTORS = (("water_sub", "Water"), ("wind_sub", "Wind"),
                  ("temp_sub", "Temperature"), ("aqi_sub", "Air quality"))
# The risk engine lets these add to a score but never select the hazard, so
# the display lists them after the hazard drivers, never as the top driver.
SUPPORTING_FACTORS = (("pressure_sub", "Pressure"), ("humidity_sub", "Humidity"))
SUPPORTING_LABELS = frozenset(label for _key, label in SUPPORTING_FACTORS)


def subscore_bars(row: dict) -> list[tuple[str, float | None]]:
    """Hazard drivers then supporting signals, each in descending order;
    NULL is unavailable, not zero."""
    def ranked(factors):
        bars = []
        for key, label in factors:
            value = _number(row.get(key), -1)
            bars.append((label, min(100.0, value) if value >= 0 else None))
        return sorted(bars, key=lambda bar: -(bar[1] if bar[1] is not None else -1))
    return ranked(HAZARD_FACTORS) + ranked(SUPPORTING_FACTORS)


def multiplier_sentences(row: dict) -> tuple[str, str]:
    """Describe stored multipliers, without recalculating or inferring risk."""
    ai = _number(row.get("ai_multiplier"), -1)
    ai_line = (
        (f"AI: unusual pattern x{ai:g}" if ai > 1 else "AI: nothing unusual")
        if ai >= 0 else "AI: multiplier unavailable"
    )
    multiplier = _number(row.get("mesh_multiplier"), -1)
    count = int(_number(row.get("correlated_count")))
    state = row.get("corroboration")
    if state == "uncorroborated":
        words = "No neighbour agrees: damped"
    elif state in ("corroborated", "partial"):
        words = f"Mesh: {count} neighbour{' agrees' if count == 1 else 's agree'}"
    elif state == "unavailable":
        words = "Mesh: not enough neighbours to confirm"
    elif state == "quiet":
        words = "Mesh: nothing to confirm"
    else:
        words = "Mesh: agreement unavailable"
    mesh_line = (
        words if state == "quiet" and multiplier == 1
        else f"{words} x{multiplier:g}" if multiplier >= 0
        else f"{words}; multiplier unavailable"
    )
    return ai_line, mesh_line


def sparkline_svg(history: list[dict], now: datetime | None = None) -> str:
    """A fixed ten-minute UTC time axis using stored scores, never sensor values.

    The caller supplies a windowed score query. Invalid or out-of-window rows
    are omitted; a lone reading is a dot rather than an invented flat trend.
    SVG geometry is numeric only, so stored strings cannot become markup.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    points = []
    for row in history:
        try:
            stamp = datetime.fromisoformat(row["timestamp"])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = (now - stamp).total_seconds()
            score = float(row["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= age <= 600 and math.isfinite(score):
            points.append((age, max(0, min(100, score))))
    if not points:
        return ""
    points.sort(reverse=True)
    coords = [(8 + (600 - age) / 600 * 584, 112 - score) for age, score in points]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    guides = "".join(
        f'<line class="trend-guide" x1="8" x2="592" y1="{112 - band}" '
        f'y2="{112 - band}" />' for band in (0, 30, 60, 80, 100)
    )
    x, y = coords[-1]
    label = (
        f"Score over the last 10 minutes: {points[0][1]:g} to {points[-1][1]:g} "
        "out of 100. Band guides at 30, 60 and 80."
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 124" '
        f'preserveAspectRatio="none" role="img" aria-label="{label}">'
        f'<title>{label}</title>{guides}'
        f'<polyline class="trend-line" points="{path}" />'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="currentColor" /></svg>'
    )
