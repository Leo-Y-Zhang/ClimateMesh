"""Export reproducible evidence from the current Climate Mesh database.

Writes, into an ``evidence/`` folder:
    readings.csv       every sensor reading captured this run
    risk_scores.csv    every risk score computed
    alerts.csv         every alert raised (with its action playbook)
    source_summary.csv counts of readings by data source (provenance table)
    run_summary.json   headline stats + reproducibility metadata for judges

Run this after a demo (``python run.py --mode demo --scenario flood
--judge-mode`` for a while) so judges can inspect exactly what the system
produced. Honest by construction: each row keeps its ``source`` and
``quality_flag`` so simulated/API/hardware data is never confused, and the
source-count table makes the physical/live/demo/simulated split explicit.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.database import (
    count_rows, fetch_all, get_latest_run_meta, get_risk_scores, init_db,
)

OUT_DIR = Path(__file__).parent.parent / "evidence"

# Plain-English meaning of each provenance, shown next to its count so a judge
# can immediately see what is physical, live, demo, or generated.
SOURCE_MEANING = {
    "hardware": "real physical sensor",
    "api": "live Open-Meteo data",
    "demo": "deterministic demo / digital-twin data",
    "simulation": "generated offline data",
}


def _git_commit_hash() -> str | None:
    """Current git commit hash, or None. Local-only; never touches the network."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")  # still create the file so its absence isn't ambiguous
        return
    # Union of keys preserves any column that appears in any row.
    fieldnames: list[str] = []
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    init_db()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    readings = fetch_all("sensor_readings")
    risks = fetch_all("risk_scores")
    alerts = fetch_all("alerts")

    _write_csv(OUT_DIR / "readings.csv", readings)
    _write_csv(OUT_DIR / "risk_scores.csv", risks)
    _write_csv(OUT_DIR / "alerts.csv", alerts)

    latest_risks = get_risk_scores()
    avg_risk = round(sum(r["score"] for r in latest_risks) / len(latest_risks), 1) if latest_risks else 0.0
    max_risk = max((r["score"] for r in latest_risks), default=0.0)
    sources = sorted({r["source"] for r in readings}) if readings else []
    run_meta = get_latest_run_meta() or {}

    # --- Provenance summary table (2.2): counts by source and quality flag ---
    source_counts = Counter(r["source"] for r in readings)
    quality_counts = Counter(r.get("quality_flag", "ok") for r in readings)
    # Stable order: known sources first (even at 0), then any unexpected extras.
    ordered_sources = list(SOURCE_MEANING) + [
        s for s in source_counts if s not in SOURCE_MEANING]
    source_table = [
        {"source": s, "meaning": SOURCE_MEANING.get(s, "unknown source"),
         "count": int(source_counts.get(s, 0))}
        for s in ordered_sources
    ]
    _write_csv(OUT_DIR / "source_summary.csv", source_table)

    num_nodes = len({r["node_id"] for r in readings})
    num_alerts = count_rows("alerts")
    # Reproducibility metadata (2.4): prefer what the run recorded; fall back to
    # computing the commit hash here so exports from older runs still carry it.
    commit_hash = run_meta.get("commit_hash") or _git_commit_hash()

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run": {
            "mode": run_meta.get("mode"),
            "scenario": run_meta.get("scenario"),
            "judge_mode": bool(run_meta.get("judge_mode")),
            "source": run_meta.get("source"),
            "seed": run_meta.get("seed"),
            "commit_hash": commit_hash,
            "training_mode": run_meta.get("training_mode"),
            "timestamp": run_meta.get("started_at"),
            "num_nodes": num_nodes,
            "num_alerts": num_alerts,
            "max_risk": max_risk,
            "avg_risk": avg_risk,
            "notes": run_meta.get("notes"),
            "started_at": run_meta.get("started_at"),
        },
        "totals": {
            "readings": count_rows("sensor_readings"),
            "risk_scores": count_rows("risk_scores"),
            "alerts": num_alerts,
            "nodes_online": num_nodes,
        },
        "source_counts": dict(source_counts),
        "quality_counts": dict(quality_counts),
        "latest": {
            "average_risk": avg_risk,
            "max_risk": max_risk,
            "highest_risk_node": (latest_risks[0]["node_id"] if latest_risks else None),
            "highest_risk_score": (latest_risks[0]["score"] if latest_risks else None),
            "data_sources_present": sources,
        },
    }
    (OUT_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"[evidence] Wrote 5 files to {OUT_DIR}")
    print(f"           readings={summary['totals']['readings']} "
          f"risk_scores={summary['totals']['risk_scores']} "
          f"alerts={num_alerts} nodes_online={num_nodes}")
    print(f"           avg_risk={avg_risk} max_risk={max_risk} "
          f"training_mode={run_meta.get('training_mode')} "
          f"seed={run_meta.get('seed')} commit={(commit_hash or 'n/a')[:8]}")
    print("           data source summary:")
    print(f"             {'Source':<12} {'Meaning':<38} {'Count':>5}")
    for row in source_table:
        print(f"             {row['source']:<12} {row['meaning']:<38} {row['count']:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
