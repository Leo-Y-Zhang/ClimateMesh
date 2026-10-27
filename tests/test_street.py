"""Street display decisions are offline and independent of the browser."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from dashboard.accessibility import PALETTES, contrast_ratio, text_on
from dashboard.street_helpers import (
    THEMES,
    data_age,
    environment_label,
    is_fresh,
    join_nodes,
    london_time,
    mesh_status,
    multiplier_sentences,
    rotation_order,
    select_node,
    site_position,
    sparkline_svg,
    subscore_bars,
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


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("state", ["empty", "fresh", "stale"])
def test_street_apptest_smoke(state, theme, detector):
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
    at.query_params["theme"] = theme
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
        assert "What is driving it" in page
        assert "What to do" in page
        assert "Score · last 10 minutes" in page
        assert "<svg " in page
        assert "Site 1 of 3" in page
        assert 'class="rotation"' in page
        assert "GMT Standard Time" not in page
        assert 'class="chip"' in page
        assert f"--background:{THEMES[theme]['background']}" in page
        # A pinned node outside the top three keeps its full-list index.
        last = sorted(rows, key=lambda r: (-float(r["score"]), r["node_id"]))[-1]
        at.query_params["node"] = last["node_id"]
        at.run()
        assert not at.exception
        page = " ".join(m.value for m in at.markdown)
        assert f"Site {len(rows)} of {len(rows)}" in page
        assert 'class="rotation"' not in page
    else:
        assert "No fresh data: is the engine running?" in page
        assert "python run.py --mode auto" in page
        assert "<h1>CRITICAL</h1>" not in page


@pytest.mark.parametrize(
    "month,expected", [(1, "15:29 GMT"), (7, "16:29 BST")]
)
def test_london_zone_abbreviation(month, expected):
    assert london_time(datetime(2026, month, 15, 15, 29, tzinfo=timezone.utc)) == expected
    # Legacy naive timestamps are UTC, never the OS local timezone.
    assert london_time(datetime(2026, month, 15, 15, 29)) == expected


@pytest.mark.parametrize(
    "value,expected", [("river", "River"), (" URBAN ", "Urban"),
                       ("park", "Park"), (None, ""), ("", "")]
)
def test_environment_capitalisation(value, expected):
    assert environment_label(value) == expected


def test_subscore_order_and_labels():
    row = {
        "water_sub": 42, "wind_sub": 90, "pressure_sub": 35,
        "temp_sub": 60, "aqi_sub": 12, "humidity_sub": 0,
        "score": 99, "base_score": 100,
    }
    assert subscore_bars(row) == [
        ("Wind", 90), ("Temperature", 60), ("Water", 42),
        ("Pressure", 35), ("Air quality", 12), ("Humidity", 0),
    ]
    # Ties retain the documented label order, and missing channels are honest.
    assert subscore_bars({}) == [
        (label, None) for label in
        ("Water", "Wind", "Pressure", "Temperature", "Air quality", "Humidity")
    ]
    assert subscore_bars({"water_sub": 0, "wind_sub": None})[0] == ("Water", 0)


@pytest.mark.parametrize(
    "state,count,multiplier,expected",
    [
        ("corroborated", 3, 1.2, "Mesh: 3 neighbours agree x1.2"),
        ("partial", 1, 1, "Mesh: 1 neighbour agrees x1"),
        ("uncorroborated", 0, 0.75, "No neighbour agrees: damped x0.75"),
        ("unavailable", 1, 1, "Mesh: not enough neighbours to confirm x1"),
        ("quiet", 0, 1, "Mesh: nothing to confirm"),
        (None, 0, None, "Mesh: agreement unavailable; multiplier unavailable"),
    ],
)
def test_multiplier_sentences(state, count, multiplier, expected):
    row = {"ai_multiplier": 1.3, "corroboration": state,
           "correlated_count": count, "mesh_multiplier": multiplier}
    assert multiplier_sentences(row) == ("AI: unusual pattern x1.3", expected)
    assert multiplier_sentences({**row, "ai_multiplier": 1})[0] == "AI: nothing unusual"
    assert multiplier_sentences({**row, "ai_multiplier": None})[0] == "AI: multiplier unavailable"
    # Do not substitute a hardcoded multiplier for the stored one.
    assert multiplier_sentences({**row, "mesh_multiplier": 1.17})[1].endswith("x1.17")


def test_site_position_uses_rotation_or_full_pinned_order():
    rows = [{"node_id": str(i), "score": i, "level": "WARNING"} for i in range(20)]
    assert site_position(rows, rows[17]) == "Site 3 of 3"
    assert site_position(rows, rows[0], pinned=True) == "Site 20 of 20"


def test_sparkline_from_stored_score_history():
    now = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
    history = [
        {"timestamp": (now - timedelta(seconds=age)).isoformat(), "score": score}
        for age, score in [(600, 10), (300, 45), (0, 85)]
    ]
    svg = sparkline_svg(list(reversed(history)), now)
    root = ElementTree.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    assert root.attrib["role"] == "img"
    assert "10 to 85 out of 100" in root.attrib["aria-label"]
    assert root.find("svg:polyline", ns).attrib["points"] == "8.0,102.0 300.0,67.0 592.0,27.0"
    assert [line.attrib["y1"] for line in root.findall("svg:line", ns)] == [
        "112", "82", "52", "32", "12",
    ]
    assert root.find("svg:circle", ns).attrib["cx"] == "592.0"
    assert sparkline_svg([], now) == ""
    assert sparkline_svg([
        {"timestamp": "<script>", "score": 50},
        {"timestamp": now.isoformat(), "score": float("nan")},
        {"timestamp": (now - timedelta(seconds=601)).isoformat(), "score": 60},
        {"timestamp": (now + timedelta(seconds=1)).isoformat(), "score": 60},
        {"timestamp": now.isoformat(), "temperature": 50},
    ], now) == ""
    assert "<circle " in sparkline_svg(history[:1], now)


@pytest.mark.parametrize("theme", THEMES.values(), ids=THEMES.keys())
def test_theme_text_meets_aa(theme):
    for background in (theme["background"], theme["surface"]):
        for ink in (theme["ink"], theme["muted"]):
            assert contrast_ratio(ink, background) >= 4.5


def test_score_history_query_is_windowed_and_node_specific(detector):
    from dashboard.street import get_score_history

    insert_readings(SimulatedAdapter(demo=True).read_all("flood", tick=0.0))
    risks = compute_all(get_latest_readings_per_node(), detector)
    for risk in risks:
        insert_risk_score(risk)
    node_id = risks[0]["node_id"]
    now = datetime.now(timezone.utc)
    assert get_score_history(node_id, now)[0]["score"] == risks[0]["score"]
    assert get_score_history("missing", now) == []
    with sqlite3.connect(os.environ["CLIMATE_MESH_DB"]) as db:
        # A sensor history alone cannot supply the score trend.
        db.execute("UPDATE risk_scores SET timestamp=?", ((now - timedelta(minutes=11)).isoformat(),))
    assert get_score_history(node_id, now) == []
