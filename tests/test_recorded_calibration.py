"""Recorded evidence pins improvements and the residual failures without retuning."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pytest

from ai.anomaly_model import AnomalyDetector, _load_archive_cache, _rows_from_archive
from backend.risk_engine import calculate_base, compute_all
from config.nodes import ENVIRONMENTS, NODES
from scripts.calibration_report import alert_class
from sensors.api_adapter import ApiAdapter, ApiUnavailable, _water_level_proxy
from sensors.history_adapter import HistoryAdapter
from simulation.replay import ROOT, write_replay
from simulation.replay_io import read_json


def recorded(event, variant="grid"):
    return read_json(ROOT / "evidence" / "replay" / f"{event}-{variant}.json")


def test_as_found_evidence_is_unchanged():
    base = ROOT / "evidence" / "replay" / "as-found"
    manifest = json.loads((base / "sha256.json").read_text())
    for path, digest in manifest.items():
        assert hashlib.sha256((base / path).read_bytes()).hexdigest() == digest, path


@pytest.mark.parametrize("event,expected", [
    ("flood-2021-07-12", 0), ("heat-2022-07-19", 0), ("storm-2022-02-18", 0),
])
def test_recorded_quiet_hour_multiplier_alerts(event, expected):
    rows = [r for h in recorded(event)["per_hour"][:6] for r in h["nodes"]]
    assert sum(r["alert"] is not None and alert_class(r) == "multiplier-dependent"
               for r in rows) == expected
    assert not any(r["alert"] == "flood" for r in rows)


@pytest.mark.parametrize("event,expected", [
    ("holdout-2023-03-06", (140, 1575)),
    ("holdout-2023-06-05", (177, 347)),
    ("holdout-2023-09-04", (150, 1278)),
    ("holdout-2023-12-04", (0, 518)),
])
def test_fixed_held_out_rule_reports_residual_alerts(event, expected):
    counts = Counter(alert_class(r) for h in recorded(event)["per_hour"]
                     for r in h["nodes"] if r["alert"])
    assert (counts["hazard-alone"], counts["multiplier-dependent"]) == expected


def test_humidity_alone_is_safe_even_with_maximum_ai_multiplier():
    readings = HistoryAdapter(ROOT / "data/history/flood-2021-07-12.json").read_hour(0)
    for r in readings:
        r.update(temperature=18, humidity=100, air_quality=40, water_level=0.3,
                 wind_speed=2, barometric_pressure=1013)

    class MaximumAnomaly:
        def predict_many(self, rows):
            return [{"score": 1.0, "is_anomaly": True} for _ in rows]

    for result in compute_all(readings, MaximumAnomaly()):
        assert result["score"] <= 25.2  # 14 * 1.5 * 1.2, including mesh agreement
        assert result["level"] == "SAFE"
        assert result["dominant_hazard"] == "risk"
        assert result["top_factors"] == []
        assert "Supporting factor: very high humidity (100%)" in result["explanation"]


def test_hazard_ranking_precedes_supporting_humidity(detector):
    r = HistoryAdapter(ROOT / "data/history/flood-2021-07-12.json").read_hour(0)[0]
    r.update(temperature=18, humidity=100, air_quality=40, water_level=2,
             wind_speed=2, barometric_pressure=1013)
    base = calculate_base(r, detector)
    assert base["base_score"] == 44  # water 30 plus 20% of humidity 70
    assert base["dominant_hazard"] == "flood"
    assert base["top_factors"] == ["water level"]


def test_normal_recorded_river_levels_are_normal_to_preceding_month_model():
    path = ROOT / "data/history/flood-2021-07-12.json"
    data = json.loads(path.read_text())
    model = AnomalyDetector().train_archive(data["training"]["weather"], data["training"]["air"])
    rows = [r for i in range(6) for r in HistoryAdapter(path).read_hour(i)
            if r["environment"] == "river"]
    assert len(rows) == 24
    assert (min(r["water_level"] for r in rows), max(r["water_level"] for r in rows)) == (1.0, 1.72)
    assert not any(v["is_anomaly"] for v in model.predict_many(rows))
    assert model.n_train == 720 * len(ENVIRONMENTS)


@pytest.mark.parametrize("event,channel,hazard,peak_hour,peak_value", [
    ("heat-2022-07-19", "temperature", "heatwave", "2022-07-19T12:00", 38.0),
    ("storm-2022-02-18", "wind_speed", "storm", "2022-02-18T12:00", 19.38),
])
def test_recorded_peak_is_still_detected(event, channel, hazard, peak_hour, peak_value):
    pairs = [(h["hour"], r) for h in recorded(event)["per_hour"] for r in h["nodes"]]
    peak = max(r[channel] for _, r in pairs)
    assert peak == peak_value
    hottest = [(hour, r) for hour, r in pairs if r[channel] == peak]
    assert peak_hour in {hour for hour, _ in hottest}
    assert all(r["alert"] == hazard and r["band"] == "CRITICAL" for _, r in hottest)


def test_putney_heath_measured_rain_outcome():
    payload = recorded("flood-2021-07-12", "gauges")
    report = next(g for g in payload["summary"]["gauges"] if g["label"] == "Putney Heath")
    assert report["used"] and report["nearest_node"] == "PUTNEY"
    rows = [(h["hour"], r) for h in payload["per_hour"] for r in h["nodes"] if r["node_id"] == "PUTNEY"]
    first_hour, first = next((h, r) for h, r in rows if r["alert"])
    assert (first_hour, first["band"], first["score"], first["corroboration"], first["alert"]) == (
        "2021-07-12T16:00", "WARNING", 67.3, "partial", "flood")
    critical_hour, critical = next((h, r) for h, r in rows if r["band"] == "CRITICAL")
    assert (critical_hour, critical["score"], critical["corroboration"]) == (
        "2021-07-12T18:00", 85.6, "partial")
    assert payload["summary"]["peak_per_node"]["PUTNEY"] == {
        "hour": "2021-07-12T19:00", "score": 100.0, "band": "CRITICAL"}
    assert recorded("flood-2021-07-12")["summary"]["peak_per_node"]["PUTNEY"]["score"] == 53.4


def test_training_rain_uses_london_midnight_and_every_environment():
    # BST midnight is 23:00 UTC. The missing temperature still contributes rain.
    weather = {"hourly": {
        "time": ["2023-06-01T22:00", "2023-06-01T23:00", "2023-06-02T00:00", "2023-06-02T01:00"],
        "temperature_2m": [16, 16, None, 16], "relative_humidity_2m": [70] * 4,
        "pressure_msl": [1013] * 4, "surface_pressure": [990] * 4,
        "wind_speed_10m": [3] * 4, "precipitation": [2, 3, 4, 5],
    }}
    rows = _rows_from_archive(weather, {"hourly": {"european_aqi": [20] * 4}})
    assert rows.shape == (3 * len(ENVIRONMENTS), 6)
    for i, rain in enumerate((2, 3, 12)):
        for j, env in enumerate(ENVIRONMENTS):
            assert rows[i * len(ENVIRONMENTS) + j, 3] == _water_level_proxy(env, rain)
    assert np.all(rows[:, 5] == 1013)


def test_old_training_cache_is_invalidated(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"matrix": np.zeros((720, 6)).tolist()}))
    assert _load_archive_cache(path) is None


@pytest.mark.parametrize("missing", [False, True])
def test_live_rain_sums_elapsed_local_hours_only(monkeypatch, missing):
    calls = []
    start = datetime(2023, 6, 5)
    weather = {"current": {"time": "2023-06-05T02:30", "temperature_2m": 18,
                           "relative_humidity_2m": 60, "wind_speed_10m": 2, "pressure_msl": 1013},
               "hourly": {"time": [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(24)],
                          "precipitation": [1, None if missing else 2, 3] + [100] * 21}}

    def get(url, params, timeout):
        calls.append(params)
        return [weather if "forecast" in url else {"current": {"european_aqi": 20}} for _ in NODES]

    monkeypatch.setattr("sensors.api_adapter._http_get_json", get)
    if missing:
        with pytest.raises(ApiUnavailable, match="elapsed rainfall"):
            ApiAdapter().read_all()
    else:
        for r in ApiAdapter().read_all():
            assert r["water_level"] == round(_water_level_proxy(r["environment"], 6), 3)
            assert r["quality_flag"] == "estimated"
        assert calls[0]["hourly"] == "precipitation" and "daily" not in calls[0]
        assert calls[0]["timezone"] == "auto"


def test_replay_writes_literal_lf(tmp_path):
    path = write_replay({"event_id": "example", "variant": "grid", "lines": [1, 2]}, tmp_path)
    assert b"\r" not in path.read_bytes()
    assert path.read_bytes().endswith(b"\n")


def test_pressure_alone_cannot_drive_a_storm_or_exceed_safe(detector):
    readings = HistoryAdapter(ROOT / 'data/history/flood-2021-07-12.json').read_hour(0)
    for r in readings:
        r.update(temperature=18, humidity=60, air_quality=40, water_level=0.3,
                 wind_speed=2, barometric_pressure=950)
    for result in compute_all(readings, detector):
        assert result['level'] == 'SAFE'
        assert result['dominant_hazard'] == 'risk'
        assert result['top_factors'] == []
        assert 'Supporting factor: very low pressure (950 hPa)' in result['explanation']


def test_episode_counting_handles_changes_gaps_and_node_handoffs():
    from simulation.replay_io import alert_metrics, episode_annotations
    samples = [
        ('00', [('a', 'smog'), ('b', None)]),
        ('01', [('a', 'smog'), ('b', 'cold')]),
        ('02', [('a', None), ('b', 'smog')]),
        ('03', [('a', 'smog'), ('b', 'smog')]),
        ('04', [('a', None), ('b', None)]),
        ('05', [('a', 'smog'), ('b', None)]),
        # Missing 06 breaks both sorts of episode.
        ('07', [('a', 'smog'), ('b', None)]),
    ]
    steps = [{'hour': f'2024-01-01T{hour}:00',
              'nodes': [{'node_id': node, 'alert': hazard, 'ai_multiplier': 1} for node, hazard in pairs]}
             for hour, pairs in samples]
    metrics = alert_metrics(steps)
    assert metrics['by_hazard'] == {
        'smog': {'alert_hours': 7, 'node_episodes': 5, 'london_episodes': 3},
        'cold': {'alert_hours': 1, 'node_episodes': 1, 'london_episodes': 1}}
    annotations = episode_annotations(steps)
    assert annotations[('2024-01-01T01:00', 'a')]['node_episode_start'] == 0
    assert annotations[('2024-01-01T02:00', 'b')]['london_episode_start'] == 0


def test_compact_gzip_is_deterministic_and_both_formats_are_readable(tmp_path):
    import gzip
    from simulation.replay_io import read_json, write_json
    payload = {'z': [1, 2], 'a': 'line\nbreak'}
    plain, zipped, other = [tmp_path / name for name in ('one.json', 'one.json.gz', 'two.json.gz')]
    write_json(payload, plain)
    write_json(payload, zipped)
    write_json(payload, other)
    assert zipped.read_bytes() == other.read_bytes()
    assert zipped.read_bytes()[3:8] == b'\x00' * 5  # flags and mtime: no filename, zero timestamp
    assert gzip.decompress(zipped.read_bytes()) == plain.read_bytes() == b'{"a":"line\\nbreak","z":[1,2]}\n'
    assert read_json(plain) == read_json(zipped) == payload
    plain.unlink()
    assert read_json(plain) == payload
