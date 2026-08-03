"""Self-contained validation run for Climate Mesh.

Spins up a throwaway database, generates several cycles of data for a chosen
mode/scenario, scores them, and prints a pass/fail validation report. Designed
to give judges a one-command sanity check that the whole pipeline works without
needing the dashboard or a long-running process.

    python scripts/run_validation.py
    python scripts/run_validation.py --mode demo --scenario flood --cycles 5
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

# Use an isolated database so validation never touches the demo DB.
_TMP_DB = Path(tempfile.gettempdir()) / "climate_mesh_validation.db"
os.environ["CLIMATE_MESH_DB"] = str(_TMP_DB)

from ai.anomaly_model import AnomalyDetector            # noqa: E402
from backend.risk_engine import compute_all             # noqa: E402
from data.database import (                             # noqa: E402
    count_rows, get_latest_readings_per_node, get_risk_scores, init_db,
    insert_alert, insert_reading, insert_risk_score, reset_db,
)
from backend.risk_engine import maybe_alert             # noqa: E402
from sensors import create_adapter                      # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Climate Mesh validation run")
    p.add_argument("--mode", default="simulation")
    p.add_argument("--scenario", default="flood")
    p.add_argument("--cycles", type=int, default=5)
    args = p.parse_args()

    for f in (_TMP_DB, Path(str(_TMP_DB) + "-wal"), Path(str(_TMP_DB) + "-shm")):
        if f.exists():
            f.unlink()

    init_db()
    reset_db()
    detector = AnomalyDetector().train(quiet=True)
    # Validation always uses deterministic simulated data (no network needed).
    adapter, notes = create_adapter("demo" if args.mode in ("demo", "simulation") else args.mode,
                                    demo=True)

    errors: list[str] = []
    for i in range(args.cycles):
        try:
            readings = adapter.read_all(args.scenario, tick=0.0)
            for r in readings:
                insert_reading(r)
            latest = get_latest_readings_per_node()
            results = compute_all(latest, detector)
            by_id = {r["node_id"]: r for r in results}
            for reading in latest:
                insert_risk_score(by_id[reading["node_id"]])
                maybe_alert(reading, by_id[reading["node_id"]])
        except Exception as e:  # noqa: BLE001
            errors.append(f"cycle {i}: {e}")

    readings = get_latest_readings_per_node()
    risks = get_risk_scores()
    nodes_online = len({r["node_id"] for r in readings})
    avg_risk = round(sum(r["score"] for r in risks) / len(risks), 1) if risks else 0.0
    n_alerts = count_rows("alerts")
    in_bounds = all(0 <= r["score"] <= 100 for r in risks)

    checks = {
        "20 nodes online": nodes_online == 20,
        "risk scores within 0-100": in_bounds,
        "readings generated": count_rows("sensor_readings") > 0,
        "no runtime errors": not errors,
        "scenario raised alerts": n_alerts > 0,
    }

    print("=" * 56)
    print("  Climate Mesh — Validation Report")
    print("=" * 56)
    for n in notes:
        print(f"  note: {n}")
    print(f"  mode={args.mode} scenario={args.scenario} cycles={args.cycles}")
    print("-" * 56)
    print(f"  readings generated : {count_rows('sensor_readings')}")
    print(f"  nodes online       : {nodes_online}/20")
    print(f"  average risk       : {avg_risk}/100")
    print(f"  alerts             : {n_alerts}")
    print(f"  errors             : {len(errors)}")
    for e in errors:
        print(f"     - {e}")
    print("-" * 56)
    ok = True
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("=" * 56)
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
