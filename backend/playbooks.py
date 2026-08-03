"""Community action playbooks.

Every alert carries a plain-English suggested action so a non-technical user (a
school receptionist, a site manager) knows what to *do*, not just that a number
went up. Keyed by alert type.
"""

from __future__ import annotations

PLAYBOOKS: dict[str, list[str]] = {
    "flood": [
        "Check and clear nearby drains and gullies.",
        "Inspect low-lying paths and entrances for standing water.",
        "Review the evacuation route and move valuables off the ground floor.",
    ],
    "heatwave": [
        "Open designated cooling spaces and provide drinking water.",
        "Check on vulnerable students and staff.",
        "Reduce or reschedule outdoor sports and PE.",
    ],
    "smog": [
        "Reduce outdoor activity, especially strenuous exercise.",
        "Close windows on the road-facing side of the building.",
        "Notify the site team and any asthmatic / vulnerable individuals.",
    ],
    "storm": [
        "Secure loose outdoor equipment and signage.",
        "Keep clear of trees, scaffolding, and temporary structures.",
        "Monitor for power interruptions and check the building perimeter.",
    ],
    "air_quality": [
        "Limit time outdoors and avoid strenuous activity outside.",
        "Keep windows closed near busy roads.",
    ],
    "temperature": [
        "Hydrate, seek shade or cooling, and check on vulnerable people.",
    ],
    "risk": [
        "Review the affected nodes on the dashboard and follow the most "
        "relevant hazard playbook above.",
    ],
}


def playbook_for(alert_type: str) -> list[str]:
    """Return the suggested-action steps for an alert type (empty if unknown)."""
    return PLAYBOOKS.get(alert_type, PLAYBOOKS.get("risk", []))


def playbook_text(alert_type: str) -> str:
    """One-line joined version of the playbook for compact display/storage."""
    steps = playbook_for(alert_type)
    return " ".join(f"({i+1}) {s}" for i, s in enumerate(steps))
