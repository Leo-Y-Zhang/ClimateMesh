"""Climate Mesh node registry — 20 named Greater London-area locations.

Every data source (simulation, API, hardware) maps onto these nodes so the
risk engine, AI model, dashboard, and database never need to know where a
reading came from. Environment type drives the baseline values used by the
simulator and the risk weighting.

The node layout is an illustrative demonstration set: each node sits at a
well-known Greater London public landmark or district centre. No node marks a
deployed sensor, and none corresponds to anyone's home, school, or workplace.
A real deployment would replace this list with its own surveyed locations.
"""

from __future__ import annotations

import math

# Environment types the simulator and risk weighting support. ("school" is a
# supported environment class for community deployments; the demo layout below
# does not place a node in it.)
ENVIRONMENTS = ("school", "river", "residential", "urban", "park")

# 20 named nodes. node_id is stable and human-readable; it is the primary key
# used everywhere else in the system.
NODES: list[dict] = [
    {"node_id": "THAMES-BARRIER", "node_name": "Thames Barrier",               "environment": "river",       "latitude": 51.4950, "longitude": 0.0370},
    {"node_id": "RIVER-LEA",      "node_name": "River Lea (Hackney Marshes)",  "environment": "river",       "latitude": 51.5560, "longitude": -0.0230},
    {"node_id": "REGENTS-CANAL",  "node_name": "Regent's Canal (Little Venice)", "environment": "river",     "latitude": 51.5230, "longitude": -0.1840},
    {"node_id": "RIVER-WANDLE",   "node_name": "River Wandle (Wandsworth)",    "environment": "river",       "latitude": 51.4570, "longitude": -0.1910},
    {"node_id": "WALTHAMSTOW",    "node_name": "Walthamstow",                  "environment": "residential", "latitude": 51.5860, "longitude": -0.0200},
    {"node_id": "LEWISHAM",       "node_name": "Lewisham",                     "environment": "residential", "latitude": 51.4620, "longitude": -0.0100},
    {"node_id": "CAMDEN",         "node_name": "Camden",                       "environment": "residential", "latitude": 51.5390, "longitude": -0.1430},
    {"node_id": "PUTNEY",         "node_name": "Putney",                       "environment": "residential", "latitude": 51.4610, "longitude": -0.2160},
    {"node_id": "CENTRAL-LDN",    "node_name": "Central London",               "environment": "urban",       "latitude": 51.5070, "longitude": -0.1280},
    {"node_id": "CANARY-WHARF",   "node_name": "Canary Wharf",                 "environment": "urban",       "latitude": 51.5050, "longitude": -0.0230},
    {"node_id": "STRATFORD",      "node_name": "Stratford",                    "environment": "urban",       "latitude": 51.5410, "longitude": -0.0030},
    {"node_id": "GREENWICH",      "node_name": "Greenwich",                    "environment": "urban",       "latitude": 51.4830, "longitude": -0.0050},
    {"node_id": "DULWICH",        "node_name": "Dulwich",                      "environment": "urban",       "latitude": 51.4450, "longitude": -0.0860},
    {"node_id": "WIMBLEDON",      "node_name": "Wimbledon",                    "environment": "urban",       "latitude": 51.4220, "longitude": -0.2080},
    {"node_id": "ILFORD",         "node_name": "Ilford",                       "environment": "urban",       "latitude": 51.5590, "longitude": 0.0740},
    {"node_id": "BRIXTON",        "node_name": "Brixton",                      "environment": "urban",       "latitude": 51.4630, "longitude": -0.1150},
    {"node_id": "HYDE-PARK",      "node_name": "Hyde Park",                    "environment": "park",        "latitude": 51.5070, "longitude": -0.1650},
    {"node_id": "RICHMOND-PARK",  "node_name": "Richmond Park",                "environment": "park",        "latitude": 51.4420, "longitude": -0.2750},
    {"node_id": "HAMPSTEAD",      "node_name": "Hampstead Heath",              "environment": "park",        "latitude": 51.5600, "longitude": -0.1630},
    {"node_id": "VICTORIA-PARK",  "node_name": "Victoria Park",                "environment": "park",        "latitude": 51.5360, "longitude": -0.0390},
]

NODES_BY_ID: dict[str, dict] = {n["node_id"]: n for n in NODES}

# Two nodes count as mesh neighbours when within this distance (km).
NEIGHBOUR_RADIUS_KM = 6.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def neighbours_of(node_id: str, radius_km: float = NEIGHBOUR_RADIUS_KM) -> list[str]:
    """Return node_ids within ``radius_km`` of the given node (excluding itself)."""
    base = NODES_BY_ID.get(node_id)
    if not base:
        return []
    out = []
    for other in NODES:
        if other["node_id"] == node_id:
            continue
        d = haversine_km(base["latitude"], base["longitude"],
                         other["latitude"], other["longitude"])
        if d <= radius_km:
            out.append(other["node_id"])
    return out


# Pre-computed adjacency map used by the mesh-correlation logic in the risk engine.
NEIGHBOURS: dict[str, list[str]] = {n["node_id"]: neighbours_of(n["node_id"]) for n in NODES}
