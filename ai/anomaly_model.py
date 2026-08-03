"""Isolation Forest anomaly detection for Climate Mesh.

Unlike fixed thresholds, an Isolation Forest learns the normal multivariate
shape of the data and flags readings that are easy to isolate — catching
*developing* anomalies (an unusual combination of values) before any single
channel crosses a hard limit.

Training data — two honest paths
--------------------------------
* ``mode="historical"`` / ``"auto"``: train on ~30 days of **real** hourly
  weather for the Greater London area pulled from the free Open-Meteo *archive*
  (ERA5) API, plus the matching air-quality archive. The fetch is cached to
  disk, so the *first* run needs the network but every repeat run trains fully
  offline from the cache.
* ``mode="synthetic"`` (default): a deterministic synthetic normal distribution,
  needing no internet — used by CI, the smoke test, and the ``--once`` cycle.

If a historical/auto run cannot reach the archive (offline, rate-limited, no
cache), it **falls back deterministically to the synthetic distribution** and
records that fact in ``training_mode`` ("synthetic_fallback"). The active mode
is exposed via ``training_mode`` / ``training_window`` / ``n_train`` and printed
on training, so the claim in the dashboard/README always matches what actually
trained. Nothing ever silently presents synthetic data as historical.

The output is explainable: alongside the anomaly score it returns the channels
that deviate most from the learned baseline. Those per-feature mean/std values
are derived from the matrix that was actually fitted (synthetic OR historical),
so the explanation can never drift from what the forest learned.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Reuse the exact offline-safe HTTP helper and proxy constants from the live
# API adapter so historical fetching behaves identically (raises ApiUnavailable
# on any network/timeout/OS error, never invents data).
from sensors.api_adapter import (
    ApiUnavailable, _BASE_WATER, _PRECIP_SENSITIVITY, _eu_aqi_to_us_scale,
    _http_get_json,
)

# Feature order used everywhere in this module.
FEATURES = ("temperature", "humidity", "air_quality", "water_level",
            "wind_speed", "barometric_pressure")

# Means/spreads of the synthetic "normal" London-ish distribution. Spreads are
# wide enough that ordinary seasonal variation (a warm summer day, a breezy
# afternoon) is NOT flagged as anomalous, while genuine scenario extremes still
# sit well outside the learned envelope. Used for synthetic training and as the
# safe default for a missing channel.
_NORMAL = {
    "temperature": (16.0, 8.0),
    "humidity": (68.0, 15.0),
    "air_quality": (55.0, 30.0),
    "water_level": (0.7, 0.6),
    "wind_speed": (5.0, 3.0),
    "barometric_pressure": (1013.0, 9.0),
}
_HUMAN = {
    "temperature": "temperature",
    "humidity": "humidity",
    "air_quality": "air quality",
    "water_level": "water level",
    "wind_speed": "wind speed",
    "barometric_pressure": "pressure",
}

# --- Open-Meteo historical archive (ERA5) ---------------------------------
ARCHIVE_WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Representative Greater London coordinate (the CENTRAL-LDN node) and the
# environment used to derive the precipitation->water-level proxy, matching the
# live API adapter's documented design decision.
ARCHIVE_LAT = 51.5070
ARCHIVE_LON = -0.1280
_ARCHIVE_ENV = "urban"

# Archive has a few days' processing lag; step back so the window is complete.
_ARCHIVE_LAG_DAYS = 5
_ARCHIVE_DEFAULT_DAYS = 30
# Below this many usable hourly rows we treat the archive as unusable and fall
# back to synthetic rather than fitting on a near-empty matrix.
_MIN_ARCHIVE_ROWS = 100

_ARCHIVE_MODES = ("historical", "archive", "auto")


def generate_training_data(n_samples: int = 2000, seed: int = 42) -> np.ndarray:
    """Generate synthetic normal sensor data for training (deterministic)."""
    rng = np.random.default_rng(seed)
    cols = [rng.normal(_NORMAL[f][0], _NORMAL[f][1], n_samples) for f in FEATURES]
    data = np.column_stack(cols)
    clamps = [(-15, 55), (0, 100), (0, 500), (0, 12), (0, 60), (940, 1060)]
    for i, (lo, hi) in enumerate(clamps):
        data[:, i] = np.clip(data[:, i], lo, hi)
    return data


def _archive_cache_path() -> Path:
    """Cache file for fetched archive data (override via env var for tests)."""
    env = os.environ.get("CLIMATE_MESH_ARCHIVE_CACHE")
    return Path(env) if env else (Path(__file__).parent / "_archive_cache.json")


def _load_archive_cache(path: Path) -> np.ndarray | None:
    """Return a cached training matrix, or None if absent/invalid."""
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        matrix = np.asarray(payload.get("matrix", []), dtype=float)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if matrix.ndim != 2 or matrix.shape[1] != len(FEATURES) or matrix.shape[0] < _MIN_ARCHIVE_ROWS:
        return None
    return matrix


def _save_archive_cache(path: Path, matrix: np.ndarray, meta: dict) -> None:
    """Persist the fetched matrix so repeat runs train offline. Best-effort."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            **meta,
            "features": list(FEATURES),
            "n_rows": int(matrix.shape[0]),
            "matrix": matrix.tolist(),
        }))
    except OSError:
        pass


def _rows_from_archive(weather: dict, air: dict) -> np.ndarray:
    """Map Open-Meteo archive hourly arrays into the FEATURES matrix.

    Real measured channels: temperature, humidity, surface pressure, wind speed.
    Air quality comes from the air-quality archive (european_aqi -> 0-500 scale).
    Water level has no archive equivalent, so it reuses the same precipitation
    proxy as the live API adapter — documented, not presented as a gauge reading.
    """
    wh = (weather or {}).get("hourly", {}) or {}
    ah = (air or {}).get("hourly", {}) or {}
    temps = wh.get("temperature_2m") or []
    hums = wh.get("relative_humidity_2m") or []
    press = wh.get("surface_pressure") or []
    winds = wh.get("wind_speed_10m") or []
    precs = wh.get("precipitation") or []
    aqis = ah.get("european_aqi") or []

    n = min(len(temps), len(hums), len(press), len(winds))
    base_w = _BASE_WATER[_ARCHIVE_ENV]
    sens = _PRECIP_SENSITIVITY[_ARCHIVE_ENV]

    rows = []
    for i in range(n):
        t, h, p, w = temps[i], hums[i], press[i], winds[i]
        if t is None or h is None or p is None or w is None:
            continue
        precip = precs[i] if i < len(precs) and precs[i] is not None else 0.0
        aqi_raw = aqis[i] if i < len(aqis) else None
        rows.append([
            float(t), float(h), _eu_aqi_to_us_scale(aqi_raw),
            base_w + sens * float(precip), float(w), float(p),
        ])
    if not rows:
        return np.empty((0, len(FEATURES)), dtype=float)
    return np.asarray(rows, dtype=float)


def fetch_archive_training_data(
    *, latitude: float = ARCHIVE_LAT, longitude: float = ARCHIVE_LON,
    days: int = _ARCHIVE_DEFAULT_DAYS, timeout: float = 8.0,
    use_cache: bool = True, cache_path: Path | None = None,
) -> np.ndarray:
    """Fetch ~``days`` of real Open-Meteo archive weather as a training matrix.

    Returns an ``(n, len(FEATURES))`` array of genuine historical hourly data.
    A successful fetch is cached so subsequent runs train offline. Raises
    :class:`ApiUnavailable` on any network failure, an empty/short payload, or a
    malformed response — the caller (``train``) then falls back to synthetic.
    """
    path = Path(cache_path) if cache_path is not None else _archive_cache_path()
    if use_cache:
        cached = _load_archive_cache(path)
        if cached is not None:
            return cached

    end = datetime.now(timezone.utc).date() - timedelta(days=_ARCHIVE_LAG_DAYS)
    start = end - timedelta(days=days)
    common = {
        "latitude": latitude, "longitude": longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "timezone": "UTC",
    }
    weather = _http_get_json(ARCHIVE_WEATHER_URL, {
        **common,
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,"
                  "wind_speed_10m,precipitation",
        "wind_speed_unit": "ms",
    }, timeout)
    air = _http_get_json(ARCHIVE_AIR_URL, {
        **common, "hourly": "european_aqi",
    }, timeout)

    matrix = _rows_from_archive(weather, air)
    if matrix.shape[0] < _MIN_ARCHIVE_ROWS:
        raise ApiUnavailable(
            f"archive returned only {matrix.shape[0]} usable rows "
            f"(need >= {_MIN_ARCHIVE_ROWS})")
    _save_archive_cache(path, matrix, {
        "latitude": latitude, "longitude": longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
    })
    return matrix


class AnomalyDetector:
    """Wraps IsolationForest for explainable sensor anomaly detection."""

    def __init__(self):
        self.model = IsolationForest(n_estimators=120, contamination=0.05, random_state=42)
        self.scaler = StandardScaler()
        self.trained = False
        # Provenance of the training data (set by train()).
        self.training_mode = "untrained"
        self.training_window = ""
        self.n_train = 0
        self.fallback_reason: str | None = None
        # Per-feature baseline; replaced from the fitted matrix in train().
        self._feat_mean = np.array([_NORMAL[f][0] for f in FEATURES], dtype=float)
        self._feat_std = np.array([_NORMAL[f][1] for f in FEATURES], dtype=float)

    def train(self, mode: str = "synthetic", *, quiet: bool = False) -> "AnomalyDetector":
        """Fit the model. ``mode`` is one of ``synthetic``/``historical``/``auto``.

        ``historical``/``auto`` try the Open-Meteo archive and fall back to the
        deterministic synthetic distribution if it is unavailable, recording the
        outcome in ``training_mode`` ("historical" or "synthetic_fallback").
        """
        mode = (mode or "synthetic").lower()
        self.fallback_reason = None
        matrix: np.ndarray | None = None

        if mode in _ARCHIVE_MODES:
            try:
                matrix = fetch_archive_training_data()
                self.training_mode = "historical"
                self.training_window = (
                    f"Greater London {matrix.shape[0]}h Open-Meteo ERA5 archive (~{_ARCHIVE_DEFAULT_DAYS}d)")
            except ApiUnavailable as e:
                self.fallback_reason = str(e)
                matrix = None

        if matrix is None:
            matrix = generate_training_data()
            # synthetic_fallback => historical was requested but unreachable;
            # synthetic => an explicit offline choice (CI / --once / smoke test).
            self.training_mode = "synthetic_fallback" if mode in _ARCHIVE_MODES else "synthetic"
            self.training_window = "deterministic synthetic normal distribution"

        self.n_train = int(matrix.shape[0])
        self.scaler.fit(matrix)
        self.model.fit(self.scaler.transform(matrix))
        # Derive per-feature mean/std from the matrix actually fitted so
        # top_factors() stays consistent with the learned baseline.
        self._feat_mean = matrix.mean(axis=0)
        self._feat_std = matrix.std(axis=0)
        self.trained = True
        if not quiet:
            kind = ("Open-Meteo historical archive hourly"
                    if self.training_mode == "historical" else "synthetic normal")
            note = f" (fallback: {self.fallback_reason})" if self.fallback_reason else ""
            print(f"[AI] Isolation Forest trained on {self.n_train} {kind} samples "
                  f"[mode={self.training_mode}]{note}")
        return self

    def status(self) -> dict:
        """Machine-readable training status for evidence/status output."""
        return {
            "training_mode": self.training_mode,
            "training_window": self.training_window,
            "n_train": self.n_train,
            "fallback_reason": self.fallback_reason,
            "trained": self.trained,
        }

    def _feature_vector(self, reading: dict) -> np.ndarray:
        return np.array([[float(reading.get(f, _NORMAL[f][0])) for f in FEATURES]])

    def top_factors(self, reading: dict, k: int = 3) -> list[str]:
        """Channels deviating most from the learned baseline (in sigma units).

        Uses the mean/std of the matrix that was actually fitted (synthetic or
        historical), so the explanation matches what the forest learned.
        """
        devs = []
        for i, f in enumerate(FEATURES):
            mu = float(self._feat_mean[i])
            sd = float(self._feat_std[i])
            if sd < 1e-9:  # guard against a degenerate (constant) feature column
                sd = _NORMAL[f][1]
            z = abs(float(reading.get(f, mu)) - mu) / sd if sd else 0.0
            devs.append((z, _HUMAN[f]))
        devs.sort(reverse=True)
        return [name for z, name in devs[:k] if z > 1.0]

    def predict(self, reading: dict) -> dict:
        """Score one reading. Returns is_anomaly, score (0-1), explanation, factors."""
        if not self.trained:
            return {"is_anomaly": False, "score": 0.0,
                    "explanation": "model not trained", "factors": []}

        scaled = self.scaler.transform(self._feature_vector(reading))
        raw = float(self.model.decision_function(scaled)[0])  # >0 normal, <0 anomaly
        is_anomaly = self.model.predict(scaled)[0] == -1
        score = max(0.0, min(1.0, 0.5 - raw))  # higher = more anomalous

        factors = self.top_factors(reading)
        if is_anomaly and not factors:
            factors = ["an unusual combination of readings"]
        explanation = (", ".join(factors) if factors else "normal conditions")
        return {
            "is_anomaly": bool(is_anomaly),
            "score": round(score, 3),
            "explanation": explanation,
            "factors": factors,
        }
