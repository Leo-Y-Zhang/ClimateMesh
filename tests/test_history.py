"""Recorded fixtures and production replay stay honest, offline and deterministic."""
from __future__ import annotations

import copy
import json
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from config.nodes import NODES, NODES_BY_ID
from dashboard.badges import source_label
from scripts.fetch_history import EVENTS, fetch_event, without_retrieved
from sensors.api_adapter import ApiUnavailable, _BASE_WATER, _PRECIP_SENSITIVITY
from sensors.base import validate_reading
from sensors.history_adapter import HistoryAdapter
from simulation.replay_io import read_json
from simulation.replay import ROOT, local_gauge_hours, replay, select_gauges, write_replay


def fixture(event):
    return json.loads((ROOT / "data" / "history" / f"{event}.json").read_text())


@pytest.mark.parametrize("event", EVENTS)
def test_fixture_integrity(event):
    data = fixture(event)
    assert set(data["nodes"]) == set(NODES_BY_ID)
    assert len(data["hours"]) == (168 if event.startswith("holdout") else 48 if event.startswith("heat") else 24)
    for arrays in data["nodes"].values():
        assert all(len(a) == len(data["hours"]) for a in arrays.values())
    for kind in ("grid", "air", "training"):
        assert data["provenance"][kind]["licence"] == "CC BY 4.0"
        assert data["provenance"][kind]["url"].startswith("https://")
    for gauge in data["gauges"]:
        assert gauge["readings"]
        assert all(r["quality"] for r in gauge["readings"])
    if data["gauges"]:
        assert data["provenance"]["gauges"]["licence"] == "Open Government Licence v3.0"
    training = data["training"]
    start = datetime.fromisoformat(data["hours"][0]).replace(tzinfo=ZoneInfo("Europe/London"))
    for kind in ("weather", "air"):
        times = training[kind]["hourly"]["time"]
        assert all(datetime.fromisoformat(t).replace(tzinfo=timezone.utc) < start for t in times)
    assert training["window"][1] < data["window"][0]


@pytest.mark.parametrize("event", EVENTS)
def test_archive_adapter_contract_and_running_total(event):
    data = fixture(event)
    adapter = HistoryAdapter(ROOT / "data" / "history" / f"{event}.json")
    for i in range(len(data["hours"])):
        for reading in adapter.read_hour(i):
            validate_reading(reading)
            assert reading["source"] == "archive"
            assert reading["is_simulated"] is True
            assert reading["scenario"] == "none"
            assert reading["quality_flag"] == "estimated"
            node = NODES_BY_ID[reading["node_id"]]
            arrays = data["nodes"][node["node_id"]]
            day = data["hours"][i][:10]
            total = sum(arrays["precipitation"][j] for j in range(i + 1)
                        if data["hours"][j][:10] == day)
            assert reading["water_level"] == round(
                _BASE_WATER[node["environment"]] + _PRECIP_SENSITIVITY[node["environment"]] * total, 3)
            if arrays["european_aqi"][i] is None:
                assert reading["air_quality"] == 50.0
    assert source_label("archive") == "Recorded (archive)"


def test_override_and_midnight_reset():
    path = ROOT / "data" / "history" / "heat-2022-07-19.json"
    adapter = HistoryAdapter(path, {"THAMES-BARRIER": [1.0] * 48})
    assert adapter.read_hour(2)[0]["water_level"] == 1.45
    assert adapter.read_hour(24)[0]["water_level"] == 1.15
    with pytest.raises(ValueError):
        HistoryAdapter(path, {"THAMES-BARRIER": [1.0]})


@pytest.mark.parametrize("event,variant", [(e, v) for e in EVENTS
                         for v in (("grid", "gauges") if e.startswith("flood") else ("grid",))])
def test_replay_offline_and_byte_identical(monkeypatch, tmp_path, event, variant):
    def no_network(*args, **kwargs):
        pytest.fail("replay attempted network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    one = replay(event, variant)
    path = write_replay(one, tmp_path)
    before = path.read_bytes()
    two = replay(event, variant)
    write_replay(two, tmp_path)
    assert path.read_bytes() == before
    assert len(one["per_hour"]) == len(fixture(event)["hours"])
    assert all(len(s["nodes"]) == 20 for s in one["per_hour"])
    assert one["training"]["training_mode"] == "historical"
    assert one["training"]["n_train"] >= 700
    committed = ROOT / "evidence" / "replay" / path.name
    assert read_json(committed) == one


def test_gauge_selection_and_utc_to_bst():
    data = fixture("flood-2021-07-12")
    overrides, reports = select_gauges(data)
    for gauge, report in zip(data["gauges"], reports):
        if report["used"]:
            assert all(r["quality"] == "Good" for r in gauge["readings"])
            assert report["distance_km"] <= 3.0
            assert overrides[report["nearest_node"]] == report["hourly_mm"]
        else:
            assert report["reason"]
    # Synthetic inputs here test routing, never become fixture observations.
    node = NODES[0]
    gauge = {"label": "test", "reference": None, "lat": node["latitude"], "lon": node["longitude"],
             "readings": [{"t_utc": "2021-07-12T14:15:00", "mm": 2.0, "quality": "Good"}]}
    test = {"hours": data["hours"], "gauges": [gauge]}
    overrides, reports = select_gauges(test)
    assert overrides[node["node_id"]][15] == 2.0
    assert reports[0]["used"]
    bad = copy.deepcopy(test)
    bad["gauges"][0]["readings"][0]["quality"] = "Suspect"
    assert not select_gauges(bad)[0]
    assert "Good" in select_gauges(bad)[1][0]["reason"]
    far = copy.deepcopy(test)
    far["gauges"][0]["lat"] = 52.5
    assert not select_gauges(far)[0]
    assert "3.0 km" in select_gauges(far)[1][0]["reason"]
    hourly, counts, outside = local_gauge_hours(gauge, data["hours"])
    assert hourly[15] == 2 and counts[0] == 0 and outside == 0


def test_fetch_failure_is_explicit(monkeypatch):
    def fail(*args, **kwargs):
        raise ApiUnavailable("offline test")
    monkeypatch.setattr("scripts.fetch_history._http_get_json", fail)
    with pytest.raises(ApiUnavailable, match="flood-2021-07-12 grid.*offline test"):
        fetch_event("flood-2021-07-12")


def test_check_ignores_only_retrieval_time():
    assert without_retrieved({"a": [{"retrieved_utc": "old", "v": 1}]}) == {"a": [{"v": 1}]}
    assert without_retrieved({"v": 1}) != without_retrieved({"v": 2})


def test_recorded_training_matches_live_historical_fit(monkeypatch):
    import numpy as np
    from ai import anomaly_model
    training = fixture("heat-2022-07-19")["training"]
    matrix = anomaly_model._rows_from_archive(training["weather"], training["air"])
    monkeypatch.setattr(anomaly_model, "fetch_archive_training_data", lambda: matrix)
    live = anomaly_model.AnomalyDetector().train("historical", quiet=True)
    recorded = anomaly_model.AnomalyDetector().train_archive(training["weather"], training["air"])
    readings = HistoryAdapter(ROOT / "data" / "history" / "heat-2022-07-19.json").read_hour(14)
    assert live.predict_many(readings) == recorded.predict_many(readings)
    assert np.array_equal(live._feat_mean, recorded._feat_mean)
    assert live.model.get_params() == recorded.model.get_params()


def test_replay_alerts_use_cycle_clock_and_preserve_live_db(monkeypatch):
    from backend import risk_engine
    from data import database
    before = database.count_rows("sensor_readings")
    original = risk_engine.maybe_alert
    raised_at = []

    def check_same_cycle(reading, risk):
        raised = original(reading, risk)
        if raised:
            raised_at.append(reading["timestamp"])
            assert original(reading, risk) is False  # same-cycle duplicate suppressed
        return raised

    monkeypatch.setattr(risk_engine, "maybe_alert", check_same_cycle)
    result = replay("heat-2022-07-19", "grid")
    assert len(set(raised_at)) > 1  # cooldown expires on later recorded hours
    assert len(raised_at) == sum(result["summary"]["alerts_by_type"].values())
    assert database.count_rows("sensor_readings") == before


def test_archive_roundtrips_database_and_export(monkeypatch, tmp_path):
    import csv
    from data import database
    from scripts import export_evidence
    reading = HistoryAdapter(ROOT / "data" / "history" / "heat-2022-07-19.json").read_hour(0)[0]
    database.insert_reading(reading)
    stored = database.get_latest_readings_per_node()[0]
    validate_reading(stored)
    assert stored["source"] == "archive"
    monkeypatch.setattr(export_evidence, "OUT_DIR", tmp_path)
    assert export_evidence.main() == 0
    with (tmp_path / "source_summary.csv").open() as f:
        rows = {r["source"]: r for r in csv.DictReader(f)}
    assert int(rows["archive"]["count"]) == 1
    assert "recorded" in rows["archive"]["meaning"]


def test_null_aqi_and_apparent_temperature_use_live_fallbacks():
    from simulation.engine import _heat_index, _wind_chill
    adapter = HistoryAdapter(ROOT / "data" / "history" / "storm-2022-02-18.json")
    data = adapter.fixture["nodes"][NODES[0]["node_id"]]
    data["european_aqi"][0] = None
    data["apparent_temperature"][0] = None
    reading = adapter.read_hour(0)[0]
    assert reading["air_quality"] == 50.0
    assert reading["quality_flag"] == "estimated"
    assert reading["wind_chill"] == round(_wind_chill(data["temperature_2m"][0], data["wind_speed_10m"][0]), 2)
    assert reading["heat_index"] == round(_heat_index(data["temperature_2m"][0], data["relative_humidity_2m"][0]), 2)


def test_fetch_check_reports_changes_and_never_writes(monkeypatch, tmp_path, capsys):
    from scripts import fetch_history
    event = "flood-2021-07-12"
    path = tmp_path / "data" / "history" / f"{event}.json"
    path.parent.mkdir(parents=True)
    original = fixture(event)
    path.write_text(fetch_history.json_text(original))
    before = path.read_bytes()
    fetched = copy.deepcopy(original)
    fetched["provenance"]["grid"]["retrieved_utc"] = "new retrieval"
    monkeypatch.setattr(fetch_history, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_history, "fetch_event", lambda _: fetched)
    monkeypatch.setattr("sys.argv", ["fetch_history.py", "--check", "--event", event])
    assert fetch_history.main() == 0
    fetched["nodes"][NODES[0]["node_id"]]["precipitation"][0] += 1
    assert fetch_history.main() == 1
    assert "DIFFERENT" in capsys.readouterr().out
    assert path.read_bytes() == before


def test_failed_fetch_leaves_existing_fixture_untouched(monkeypatch, tmp_path):
    from scripts import fetch_history
    event = "flood-2021-07-12"
    path = tmp_path / "data" / "history" / f"{event}.json"
    path.parent.mkdir(parents=True)
    original = fixture(event)
    path.write_text(fetch_history.json_text(original))
    before = path.read_bytes()

    def partial(url, params, timeout):
        if "archive-api" in url:
            return [{"hourly": {"time": original["hours"], **original["nodes"][n["node_id"]]}}
                    for n in NODES]
        raise ApiUnavailable("air fetch failed")

    monkeypatch.setattr(fetch_history, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_history, "_http_get_json", partial)
    monkeypatch.setattr("sys.argv", ["fetch_history.py", "--event", event])
    with pytest.raises(ApiUnavailable, match="air fetch failed"):
        fetch_history.main()
    assert path.read_bytes() == before
    assert not path.with_suffix(".json.tmp").exists()
