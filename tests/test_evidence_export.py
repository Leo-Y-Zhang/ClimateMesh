"""Tests for the evidence export: provenance source-count table + run metadata.

Runs a demo cycle into the isolated test DB, exports into a temp directory, and
asserts the CSV/JSON artifacts carry honest provenance and reproducibility
metadata. No network is used.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

from backend.risk_engine import compute_all
from data.database import (
    get_latest_readings_per_node, insert_alert, insert_reading,
    insert_risk_score, record_run_start,
)
from sensors.simulated_adapter import SimulatedAdapter

ROOT = Path(__file__).resolve().parent.parent


def _load_export_module():
    """Import scripts/export_evidence.py by path (scripts/ is not a package)."""
    path = ROOT / "scripts" / "export_evidence.py"
    spec = importlib.util.spec_from_file_location("export_evidence_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_demo_cycle(detector):
    readings = SimulatedAdapter(demo=True).read_all("flood", tick=0.0)
    for r in readings:
        insert_reading(r)
    latest = get_latest_readings_per_node()
    for risk in compute_all(latest, detector):
        insert_risk_score(risk)
    insert_alert("CENTRAL-LDN", "flood", "Flood risk rising", "critical",
                 scenario="flood", playbook="(1) Alert residents (2) Sandbags",
                 source="demo", is_simulated=True)
    record_run_start("demo", "flood", True, "demo", "test run",
                     seed=4242, commit_hash="deadbeefcafe", training_mode="synthetic")


def _read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_evidence_export_writes_provenance_and_metadata(monkeypatch, tmp_path, detector):
    export = _load_export_module()
    monkeypatch.setattr(export, "OUT_DIR", tmp_path)

    _seed_demo_cycle(detector)
    rc = export.main()
    assert rc == 0

    # --- readings.csv keeps node id, source, quality flag, scenario ---
    readings_rows = _read_csv(tmp_path / "readings.csv")
    assert readings_rows
    for col in ("node_id", "source", "quality_flag", "scenario"):
        assert col in readings_rows[0]
    assert all(row["source"] == "demo" for row in readings_rows)

    # --- risk_scores.csv keeps score, level, top_factors ---
    risk_rows = _read_csv(tmp_path / "risk_scores.csv")
    assert risk_rows
    for col in ("score", "level", "top_factors"):
        assert col in risk_rows[0]

    # --- alerts.csv keeps the action playbook + provenance (source/is_simulated) ---
    alert_rows = _read_csv(tmp_path / "alerts.csv")
    assert alert_rows
    assert "playbook" in alert_rows[0]
    assert alert_rows[0]["playbook"]
    # Each alert row self-labels its provenance, just like readings.
    assert "source" in alert_rows[0]
    assert "is_simulated" in alert_rows[0]
    assert alert_rows[0]["source"] == "demo"
    assert alert_rows[0]["is_simulated"] in ("1", "True")

    # --- source_summary.csv: provenance table with counts ---
    source_rows = _read_csv(tmp_path / "source_summary.csv")
    by_source = {row["source"]: row for row in source_rows}
    assert set(by_source) >= {"hardware", "api", "demo", "simulation"}
    assert int(by_source["demo"]["count"]) == 20
    assert int(by_source["hardware"]["count"]) == 0
    assert by_source["hardware"]["meaning"] == "real physical sensor"


def test_run_summary_json_has_source_counts_and_run_metadata(monkeypatch, tmp_path, detector):
    export = _load_export_module()
    monkeypatch.setattr(export, "OUT_DIR", tmp_path)

    _seed_demo_cycle(detector)
    export.main()

    summary = json.loads((tmp_path / "run_summary.json").read_text())

    # Provenance counts at the top level.
    assert summary["source_counts"] == {"demo": 20}
    assert "quality_counts" in summary

    # Reproducibility metadata (2.4).
    run = summary["run"]
    for key in ("mode", "scenario", "seed", "timestamp", "commit_hash",
                "training_mode", "num_nodes", "num_alerts", "max_risk", "avg_risk"):
        assert key in run, key
    assert run["mode"] == "demo"
    assert run["scenario"] == "flood"
    assert run["seed"] == 4242
    assert run["commit_hash"] == "deadbeefcafe"
    assert run["training_mode"] == "synthetic"
    assert run["num_nodes"] == 20
    assert run["num_alerts"] == 1
    assert 0 <= run["avg_risk"] <= 100
    assert run["max_risk"] >= run["avg_risk"]
