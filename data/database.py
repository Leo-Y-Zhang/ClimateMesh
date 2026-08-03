"""SQLite storage for Climate Mesh.

SQLite (in WAL mode) is the message bus between the engine process and the
dashboard process. This module is the *only* place that knows the table shapes.
It stores full canonical readings (including provenance and quality flags),
explainable risk scores (with sub-scores, multipliers, contributing factors,
and plain-English text), alerts (with the action playbook), and per-run
metadata used for evidence export.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow tests / scripts to point at a throwaway DB via env var.
DB_PATH = Path(os.environ.get("CLIMATE_MESH_DB", Path(__file__).parent / "climate_mesh.db"))
_local = threading.local()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn() -> sqlite3.Connection:
    """Thread-local SQLite connection in WAL mode."""
    path = Path(os.environ.get("CLIMATE_MESH_DB", DB_PATH))
    if getattr(_local, "conn", None) is None or getattr(_local, "path", None) != str(path):
        conn = sqlite3.connect(str(path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
        _local.path = str(path)
    return _local.conn


def init_db() -> None:
    """Create all tables and indexes if they don't already exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            node_name TEXT,
            environment TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            temperature REAL,
            humidity REAL,
            air_quality REAL,
            water_level REAL,
            wind_speed REAL,
            wind_chill REAL,
            heat_index REAL,
            barometric_pressure REAL,
            source TEXT NOT NULL,
            is_simulated INTEGER NOT NULL,
            quality_flag TEXT NOT NULL,
            scenario TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS risk_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            score REAL NOT NULL,
            level TEXT NOT NULL,
            temp_sub REAL, humidity_sub REAL, aqi_sub REAL, water_sub REAL,
            wind_sub REAL, pressure_sub REAL,
            anomaly_score REAL,
            ai_multiplier REAL,
            mesh_multiplier REAL,
            correlated INTEGER DEFAULT 0,
            top_factors TEXT,
            explanation TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL,
            scenario TEXT,
            playbook TEXT,
            source TEXT,
            is_simulated INTEGER,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            scenario TEXT,
            judge_mode INTEGER DEFAULT 0,
            source TEXT,
            notes TEXT,
            started_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_readings_node ON sensor_readings(node_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_risk_node ON risk_scores(node_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(timestamp);
    """)
    # Lightweight forward migration: CREATE TABLE IF NOT EXISTS won't add new
    # columns to a pre-existing run_meta, so add reproducibility columns here.
    # (Each ALTER is a no-op once the column exists.)
    for _col, _decl in (("seed", "INTEGER"), ("commit_hash", "TEXT"),
                        ("training_mode", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE run_meta ADD COLUMN {_col} {_decl}")
        except sqlite3.OperationalError:
            pass  # column already present
    # Same forward migration for the alerts table: carry the originating
    # reading's provenance so each alert row self-labels (like readings do).
    for _col, _decl in (("source", "TEXT"), ("is_simulated", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE alerts ADD COLUMN {_col} {_decl}")
        except sqlite3.OperationalError:
            pass  # column already present
    conn.commit()


# --- Writes ---------------------------------------------------------------

def insert_reading(reading: dict) -> None:
    """Insert one canonical reading (the dict produced by ``make_reading``)."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO sensor_readings
           (node_id, node_name, environment, latitude, longitude, temperature,
            humidity, air_quality, water_level, wind_speed, wind_chill,
            heat_index, barometric_pressure, source, is_simulated, quality_flag,
            scenario, timestamp)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (reading["node_id"], reading.get("node_name"), reading["environment"],
         reading.get("latitude"), reading.get("longitude"), reading["temperature"],
         reading["humidity"], reading["air_quality"], reading["water_level"],
         reading["wind_speed"], reading["wind_chill"], reading["heat_index"],
         reading["barometric_pressure"], reading["source"],
         1 if reading["is_simulated"] else 0, reading["quality_flag"],
         reading.get("scenario", "none"), reading.get("timestamp") or _now()),
    )
    conn.commit()


def insert_risk_score(risk: dict) -> None:
    """Insert one risk result (the dict produced by the risk engine)."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO risk_scores
           (node_id, score, level, temp_sub, humidity_sub, aqi_sub, water_sub,
            wind_sub, pressure_sub, anomaly_score, ai_multiplier, mesh_multiplier,
            correlated, top_factors, explanation, timestamp)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (risk["node_id"], risk["score"], risk["level"], risk["temp_sub"],
         risk["humidity_sub"], risk["aqi_sub"], risk["water_sub"],
         risk.get("wind_sub", 0.0), risk.get("pressure_sub", 0.0),
         risk.get("anomaly_score", 0.0), risk.get("ai_multiplier", 1.0),
         risk.get("mesh_multiplier", 1.0), 1 if risk.get("correlated") else 0,
         json.dumps(risk.get("top_factors", [])), risk.get("explanation", ""),
         _now()),
    )
    conn.commit()


def insert_alert(node_id: str, alert_type: str, message: str, severity: str,
                 scenario: str = "none", playbook: str = "",
                 source: str = "simulation", is_simulated: bool = True) -> None:
    """Insert one alert. ``source``/``is_simulated`` carry the provenance of the
    reading that triggered the alert, so each alert row self-labels (like
    readings do) and nothing is mistaken for a physical-sensor event."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO alerts (node_id, alert_type, message, severity, scenario, "
        "playbook, source, is_simulated, timestamp) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (node_id, alert_type, message, severity, scenario, playbook,
         source, 1 if is_simulated else 0, _now()),
    )
    conn.commit()


def record_run_start(mode: str, scenario: str, judge_mode: bool,
                     source: str, notes: str, *, seed: int | None = None,
                     commit_hash: str | None = None,
                     training_mode: str | None = None) -> None:
    """Record per-run metadata for reproducible evidence export.

    ``seed``/``commit_hash``/``training_mode`` are captured here so a judge can
    tie a screenshot or evidence bundle back to the exact run that produced it.
    """
    conn = _get_conn()
    conn.execute(
        "INSERT INTO run_meta (mode, scenario, judge_mode, source, notes, "
        "started_at, seed, commit_hash, training_mode) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (mode, scenario, 1 if judge_mode else 0, source, notes, _now(),
         seed, commit_hash, training_mode),
    )
    conn.commit()


# --- Reads ----------------------------------------------------------------

def get_latest_readings_per_node() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT s.* FROM sensor_readings s
        INNER JOIN (
            SELECT node_id, MAX(id) AS max_id
            FROM sensor_readings GROUP BY node_id
        ) latest ON s.id = latest.max_id
        ORDER BY s.node_id
    """).fetchall()
    return [dict(r) for r in rows]


def get_risk_scores() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT r.* FROM risk_scores r
        INNER JOIN (
            SELECT node_id, MAX(id) AS max_id
            FROM risk_scores GROUP BY node_id
        ) latest ON r.id = latest.max_id
        ORDER BY r.score DESC
    """).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["top_factors"] = json.loads(d.get("top_factors") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["top_factors"] = []
        out.append(d)
    return out


def get_alerts(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_alert(node_id: str, alert_type: str, within_seconds: int) -> dict | None:
    """Most recent alert for (node, type) within a window — powers alert cooldown."""
    conn = _get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
    row = conn.execute(
        "SELECT * FROM alerts WHERE node_id=? AND alert_type=? AND timestamp>? "
        "ORDER BY id DESC LIMIT 1",
        (node_id, alert_type, cutoff),
    ).fetchone()
    return dict(row) if row else None


def get_node_history(node_id: str, minutes: int = 10) -> list[dict]:
    conn = _get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    rows = conn.execute(
        "SELECT * FROM sensor_readings WHERE node_id=? AND timestamp>? ORDER BY id",
        (node_id, cutoff),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_run_meta() -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM run_meta ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def count_rows(table: str) -> int:
    if table not in ("sensor_readings", "risk_scores", "alerts", "run_meta"):
        raise ValueError(f"unknown table {table!r}")
    conn = _get_conn()
    return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def fetch_all(table: str) -> list[dict]:
    """Return every row of a whitelisted table (used by evidence export)."""
    if table not in ("sensor_readings", "risk_scores", "alerts", "run_meta"):
        raise ValueError(f"unknown table {table!r}")
    conn = _get_conn()
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# --- Maintenance ----------------------------------------------------------

def clear_old_data(minutes: int = 30) -> None:
    conn = _get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    conn.execute("DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff,))
    conn.execute("DELETE FROM risk_scores WHERE timestamp < ?", (cutoff,))
    conn.execute("DELETE FROM alerts WHERE timestamp < ?", (cutoff,))
    conn.commit()


def reset_db() -> None:
    """Drop all rows from every table (keeps schema). Used by reset_demo_db."""
    conn = _get_conn()
    for table in ("sensor_readings", "risk_scores", "alerts", "run_meta"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def close() -> None:
    """Close the thread-local connection (mainly for tests)."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
        _local.path = None
