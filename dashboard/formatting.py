"""Small pure formatters shared by the dashboard, kept out of the page module.

``dashboard/app.py`` executes top to bottom the moment it is imported, so
anything defined inside it can only be tested by rendering the whole page.
These four functions decide things a reader acts on -- how old the data is,
what a node is called, and whether the mesh can vouch for a reading -- so they
live here where a unit test can reach them directly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from config.nodes import NODES_BY_ID


def short_name(name: str) -> str:
    """'Regent's Canal (Little Venice)' -> "Regent's Canal" for labels."""
    return re.sub(r"\s*\(.*\)\s*$", "", str(name))


def node_name(node_id: str) -> str:
    """Friendly place name for a node id, falling back to the id itself."""
    node = NODES_BY_ID.get(node_id)
    return short_name(node["node_name"]) if node else str(node_id)


def age_seconds(timestamp: str) -> float | None:
    """Seconds between a stored UTC timestamp and now, or None if unreadable.

    Rows written before the database stored timezones are treated as UTC,
    which is what they were.
    """
    try:
        stamped = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamped).total_seconds()


def age_phrase(seconds: float) -> str:
    """'4 s ago' / '3 min ago' / '1 h 05 min ago' -- how old a reading is.

    A dashboard with no clock on it is a dashboard nobody should act on: the
    first question anyone with a building to look after asks is whether the
    number in front of them is from now or from yesterday.
    """
    seconds = max(0.0, float(seconds))
    if seconds < 90:
        return f"{seconds:.0f} s ago"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min ago"
    hours, minutes = divmod(int(seconds // 60), 60)
    return f"{hours} h {minutes:02d} min ago"


def corroboration_line(corroboration: str, agreeing: int, neighbours: int) -> str:
    """One sentence on whether the mesh can vouch for a node's reading.

    Empty for a node that is not raised in the first place -- there is nothing
    to corroborate and nothing worth saying.
    """
    state = str(corroboration or "quiet")
    agreeing, neighbours = int(agreeing or 0), int(neighbours or 0)
    if state == "corroborated":
        return (f"✅ **Confirmed by the mesh** — {agreeing} of this node's "
                f"{neighbours} neighbours within 6 km report the same hazard.")
    if state == "uncorroborated":
        return ("⚠️ **No neighbour sees this.** None of this node's "
                f"{neighbours} neighbours within 6 km reports the same hazard, so "
                "the score is damped and the action is to check the equipment, "
                "not the hazard.")
    if state == "partial":
        return (f"🟡 **Partly corroborated** — {agreeing} of {neighbours} neighbours "
                "agree, which is not yet enough to escalate.")
    if state == "unavailable":
        return (f"ℹ️ **Cannot be corroborated** — only {neighbours} other node(s) lie "
                "within 6 km, so the mesh has no second opinion to offer here.")
    return ""
