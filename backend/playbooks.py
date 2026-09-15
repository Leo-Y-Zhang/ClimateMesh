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
    "cold": [
        "Grit or close icy paths, steps and entrances.",
        "Check heating is working and keep vulnerable students and staff warm.",
        "Check on elderly neighbours and anyone sleeping outdoors.",
    ],
    "risk": [
        "Review the affected node on the dashboard and follow the playbook "
        "for the hazard shown as its main contributor.",
    ],
}


def playbook_for(alert_type: str) -> list[str]:
    """Return the suggested-action steps for an alert type (empty if unknown)."""
    return PLAYBOOKS.get(alert_type, PLAYBOOKS.get("risk", []))


def playbook_text(alert_type: str) -> str:
    """One-line joined version of the playbook for compact display/storage."""
    steps = playbook_for(alert_type)
    return " ".join(f"({i+1}) {s}" for i, s in enumerate(steps))
