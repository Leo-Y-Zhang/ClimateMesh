"""Street display decisions are offline and independent of the browser."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard.accessibility import PALETTES, contrast_ratio, text_on
from dashboard.street_helpers import (
    data_age,
    is_fresh,
    join_nodes,
    mesh_status,
    rotation_order,
    select_node,
)
from data.database import (
    get_latest_readings_per_node,
    get_risk_scores,
    insert_readings,
    insert_risk_score,
)
from backend.risk_engine import compute_all
from sensors.simulated_adapter import SimulatedAdapter


@pytest.mark.parametrize("palette", PALETTES.values())
@pytest.mark.parametrize("band", ["SAFE", "MODERATE", "WARNING", "CRITICAL"])
def test_band_text_meets_aa(palette, band):
    assert contrast_ratio(text_on(palette[band]), palette[band]) >= 4.5


def test_empty_and_stale_data():
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    assert join_nodes([], []) == []
    assert select_node([], 0) is None
    assert join_nodes([{"node_id": "A"}], []) == []
    row = {"timestamp": stamp, "risk_timestamp": stamp}
    assert is_fresh(row, now)
    assert data_age(row, now) == 0
    for key in ("timestamp", "risk_timestamp"):
        assert not is_fresh(
            {**row, key: (now - timedelta(seconds=31)).isoformat()}, now
        )
        assert not is_fresh({**row, key: None}, now)
    assert is_fresh(row, now + timedelta(seconds=30))
    assert not is_fresh({**row, "quality_flag": "stale"}, now)


def test_rotation_prioritizes_top_three_and_pins():
    rows = [
        {"node_id": name, "score": score, "level": "WARNING"}
        for name, score in [("A", 65), ("D", 80), ("B", 70), ("C", 70)]
    ]
    assert [r["node_id"] for r in rotation_order(rows)] == ["D", "B", "C"]
    assert [select_node(rows, t)["node_id"] for t in (0, 7, 8, 16, 24)] == [
        "D",
        "D",
        "B",
        "C",
        "D",
    ]
    assert select_node(rows, 100, "A")["node_id"] == "A"
    assert select_node(rows, 0, "missing") is None


def test_all_safe_nodes_rotate_slowly():
    rows = [{"node_id": str(i), "score": i, "level": "SAFE"} for i in range(5)]
    assert len(rotation_order(rows)) == 5
    assert select_node(rows, 19)["node_id"] == "4"
    assert select_node(rows, 20)["node_id"] == "3"


@pytest.mark.parametrize(
    "state,count,expected",
    [
        ("corroborated", 2, "2 neighbours agree"),
        ("partial", 1, "1 neighbour agrees"),
        ("uncorroborated", 0, "No neighbour agrees: check this sensor"),
        ("unavailable", 1, "Not enough neighbours to confirm"),
        ("quiet", 0, "No raised trend at this site"),
    ],
)
def test_mesh_words(state, count, expected):
    assert mesh_status(state, count) == expected


@pytest.mark.parametrize("state", ["empty", "fresh", "stale"])
def test_street_apptest_smoke(state, detector):
    from streamlit.testing.v1 import AppTest

    if state != "empty":
        insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
        for risk in compute_all(get_latest_readings_per_node(), detector):
            insert_risk_score(risk)
        rows = join_nodes(get_latest_readings_per_node(), get_risk_scores())
        assert all(is_fresh(row) for row in rows)
        if state == "stale":
            # Fresh readings cannot disguise a stopped scoring loop.
            with sqlite3.connect(os.environ["CLIMATE_MESH_DB"]) as db:
                db.execute(
                    "UPDATE risk_scores SET timestamp='2000-01-01T00:00:00+00:00'"
                )
    app = Path(__file__).resolve().parents[1] / "dashboard/street.py"
    at = AppTest.from_file(str(app), default_timeout=30)
    at.session_state["auto_refresh"] = False
    at.query_params["palette"] = "cb"
    at.query_params["large"] = "1"
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    page = " ".join(m.value for m in at.markdown)
    if state == "fresh":
        assert "Digital Twin (Demo)" in page
        assert "CRITICAL" in page
        assert "updated " in page
        assert page.count("<li>") == 3
    else:
        assert "No fresh data: is the engine running?" in page
        assert "python run.py --mode auto" in page
        assert "<h1>CRITICAL</h1>" not in page
