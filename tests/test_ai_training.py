"""Tests for AnomalyDetector training modes (synthetic + historical archive).

No real network is ever used: the archive fetch is monkeypatched to either raise
(forcing the offline fallback) or return a small canned payload.
"""

from __future__ import annotations

import numpy as np

from ai import anomaly_model as am
from ai.anomaly_model import AnomalyDetector
from sensors.api_adapter import ApiUnavailable

_FIXED_READING = {
    "temperature": 41.0, "humidity": 18.0, "air_quality": 320.0,
    "water_level": 3.2, "wind_speed": 28.0, "barometric_pressure": 975.0,
}


def test_synthetic_training_is_deterministic():
    a = AnomalyDetector().train(mode="synthetic", quiet=True)
    b = AnomalyDetector().train(mode="synthetic", quiet=True)
    assert a.training_mode == "synthetic"
    assert a.n_train == 2000
    # Identical training data + fixed random_state => identical predictions.
    assert a.predict(_FIXED_READING) == b.predict(_FIXED_READING)
    assert a.top_factors(_FIXED_READING) == b.top_factors(_FIXED_READING)


def test_default_mode_is_offline_synthetic():
    # The no-argument default (used by CI / conftest / --once) must stay offline.
    d = AnomalyDetector().train(quiet=True)
    assert d.training_mode == "synthetic"
    assert d.trained is True


def test_untrained_predict_is_safe_default():
    # An untrained detector must never fabricate an anomaly: it returns a safe,
    # zero-score default so the risk engine degrades gracefully before training.
    out = AnomalyDetector().predict(_FIXED_READING)
    assert out["is_anomaly"] is False
    assert out["score"] == 0.0
    assert out["factors"] == []
    assert "not trained" in out["explanation"]


def test_historical_falls_back_to_synthetic_when_offline(monkeypatch):
    def _raise(**_kwargs):
        raise ApiUnavailable("network down")

    monkeypatch.setattr(am, "fetch_archive_training_data", _raise)
    d = AnomalyDetector().train(mode="historical", quiet=True)

    assert d.trained is True
    assert d.training_mode == "synthetic_fallback"
    assert d.fallback_reason == "network down"
    assert d.n_train == 2000  # the deterministic synthetic matrix


def test_auto_mode_also_falls_back_offline(monkeypatch):
    monkeypatch.setattr(
        am, "fetch_archive_training_data",
        lambda **_k: (_ for _ in ()).throw(ApiUnavailable("offline")))
    d = AnomalyDetector().train(mode="auto", quiet=True)
    assert d.training_mode == "synthetic_fallback"
    assert d.status()["training_mode"] == "synthetic_fallback"


def _canned_payload(n_hours: int = 120):
    weather = {"hourly": {
        "temperature_2m": [15.0 + (i % 12) for i in range(n_hours)],
        "relative_humidity_2m": [68.0 for _ in range(n_hours)],
        "surface_pressure": [1012.0 for _ in range(n_hours)],
        "wind_speed_10m": [4.5 for _ in range(n_hours)],
        "precipitation": [0.1 for _ in range(n_hours)],
    }}
    air = {"hourly": {"european_aqi": [25.0 for _ in range(n_hours)]}}
    return weather, air


def test_historical_uses_archive_when_available(monkeypatch, tmp_path):
    # Point the cache at a throwaway file so we never read/write the repo cache.
    monkeypatch.setenv("CLIMATE_MESH_ARCHIVE_CACHE", str(tmp_path / "cache.json"))
    weather, air = _canned_payload(120)

    def _fake_get(url, params, timeout=8.0):
        return weather if "archive-api" in url else air

    monkeypatch.setattr(am, "_http_get_json", _fake_get)
    d = AnomalyDetector().train(mode="historical", quiet=True)

    assert d.training_mode == "historical"
    assert d.n_train == 120
    assert "Open-Meteo" in d.training_window
    assert d.fallback_reason is None


def test_archive_fetch_caches_for_offline_repeat(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIMATE_MESH_ARCHIVE_CACHE", str(tmp_path / "cache.json"))
    weather, air = _canned_payload(110)
    monkeypatch.setattr(
        am, "_http_get_json",
        lambda url, params, timeout=8.0: weather if "archive-api" in url else air)
    first = am.fetch_archive_training_data()

    # Now break the network entirely: the cached matrix must be reused offline.
    def _boom(*_a, **_k):
        raise AssertionError("network must not be called once cache exists")

    monkeypatch.setattr(am, "_http_get_json", _boom)
    second = am.fetch_archive_training_data()
    assert np.array_equal(first, second)


def test_top_factors_uses_fitted_baseline(monkeypatch, tmp_path):
    # When trained on historical data, the deviation baseline must come from the
    # fitted matrix (not the hardcoded synthetic means).
    monkeypatch.setenv("CLIMATE_MESH_ARCHIVE_CACHE", str(tmp_path / "cache.json"))
    weather, air = _canned_payload(120)
    monkeypatch.setattr(
        am, "_http_get_json",
        lambda url, params, timeout=8.0: weather if "archive-api" in url else air)
    d = AnomalyDetector().train(mode="historical", quiet=True)
    # Pressure column is constant (1012) in the canned data -> std guarded, no crash.
    factors = d.top_factors(_FIXED_READING)
    assert isinstance(factors, list)
    # The fitted mean for temperature is ~ the canned mean, not 16.0.
    assert abs(float(d._feat_mean[0]) - np.mean(weather["hourly"]["temperature_2m"])) < 1e-6
