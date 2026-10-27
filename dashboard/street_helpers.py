"""Pure street-display decisions; database access stays in the shared loaders."""

from __future__ import annotations

from datetime import datetime, timezone

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
    interval = 20 if all(r["level"] == "SAFE" for r in ordered) else 8
    return ordered[int(max(0, elapsed) // interval) % len(ordered)]


def mesh_status(state: str, agreeing: int = 0) -> str:
    if state == "uncorroborated":
        return "No neighbour agrees: check this sensor"
    if state == "unavailable":
        return "Not enough neighbours to confirm"
    if state in ("corroborated", "partial"):
        return f"{agreeing} neighbour{' agrees' if agreeing == 1 else 's agree'}"
    return "No raised trend at this site"
