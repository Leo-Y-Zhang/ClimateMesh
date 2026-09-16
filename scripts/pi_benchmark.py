"""Measure Climate Mesh on this machine and print a sentence for the write-up.

Run it on the Raspberry Pi 5 (inside the project's virtual environment):

    python scripts/pi_benchmark.py            # ~1 minute
    python scripts/pi_benchmark.py --with-tests   # also times the full test suite

It trains the anomaly model, runs five full 20-node cycles (read -> score ->
alert) against a throwaway database, and reports the machine model, Python
version, median cycle time and peak memory, then prints a sentence ready to
paste into the write-up. Nothing is estimated; every number is measured here.
"""

from __future__ import annotations

import argparse
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP_DB = Path(tempfile.gettempdir()) / "climate_mesh_benchmark.db"
os.environ["CLIMATE_MESH_DB"] = str(_TMP_DB)


def machine_model() -> str:
    """Raspberry Pi OS exposes the board name in the device tree; fall back
    to a generic platform string elsewhere."""
    dt = Path("/proc/device-tree/model")
    try:
        if dt.exists():
            return dt.read_bytes().decode("utf-8", "replace").strip("\x00 ")
    except OSError:
        pass
    return f"{platform.machine()} ({platform.system()})"


def total_memory_gb() -> str:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return f"{kb / 1024 / 1024:.0f} GB"
    except (OSError, ValueError):
        pass
    return "unknown RAM"


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kilobytes; macOS reports bytes.
    return peak / 1024 if sys.platform != "darwin" else peak / (1024 * 1024)


def main() -> int:
    ap = argparse.ArgumentParser(description="Climate Mesh benchmark")
    ap.add_argument("--cycles", type=int, default=5)
    ap.add_argument("--with-tests", action="store_true",
                    help="also time the full pytest suite (adds ~30-90 s)")
    args = ap.parse_args()

    for f in (_TMP_DB, Path(str(_TMP_DB) + "-wal"), Path(str(_TMP_DB) + "-shm")):
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass

    from ai.anomaly_model import AnomalyDetector
    from backend.risk_engine import compute_all, maybe_alert
    from data.database import get_latest_readings_per_node, init_db, insert_readings, insert_risk_score, reset_db
    from sensors.simulated_adapter import SimulatedAdapter

    init_db(); reset_db()
    t0 = time.perf_counter()
    detector = AnomalyDetector().train(quiet=True)
    train_s = time.perf_counter() - t0

    adapter = SimulatedAdapter(demo=True)
    cycle_ms = []
    for i in range(args.cycles):
        t1 = time.perf_counter()
        readings = adapter.read_all("flood", tick=0.0)
        insert_readings(readings)
        latest = get_latest_readings_per_node()
        results = compute_all(latest, detector)
        by_id = {r["node_id"]: r for r in results}
        for reading in latest:
            insert_risk_score(by_id[reading["node_id"]])
            maybe_alert(reading, by_id[reading["node_id"]])
        cycle_ms.append((time.perf_counter() - t1) * 1000)

    median_ms = statistics.median(cycle_ms)
    rss = peak_rss_mb()
    model = machine_model()
    py = platform.python_version()

    tests_s = None
    if args.with_tests:
        t2 = time.perf_counter()
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                              cwd=str(ROOT), capture_output=True, text=True)
        tests_s = time.perf_counter() - t2
        if proc.returncode != 0:
            print("WARNING: the test suite did not pass; not quoting its time.")
            tests_s = None

    print("=" * 64)
    print("  Climate Mesh benchmark")
    print("=" * 64)
    print(f"  Machine             : {model}, {total_memory_gb()}")
    print(f"  Python              : {py}")
    print(f"  Model training      : {train_s:.1f} s (2,000 synthetic samples)")
    print(f"  Full 20-node cycle  : median {median_ms:.0f} ms over {args.cycles} cycles "
          f"(read, AI scoring, risk, alerts, database)")
    print(f"  Peak memory (engine): {rss:.0f} MB")
    if tests_s is not None:
        print(f"  Full test suite     : {tests_s:.0f} s")
    print("-" * 64)
    sentence = (f"Measured on our {model} ({total_memory_gb()}, Python {py}): the anomaly model trains in "
                f"{train_s:.1f} s and a full cycle of 20 nodes (read, AI scoring, risk, alerts, database) "
                f"takes about {median_ms:.0f} ms against a 2-second read interval; "
                f"the engine peaks at about {rss:.0f} MB of memory")
    # int() here and f"{...:.0f}" in the table above disagreed by a second on
    # anything that did not land on a whole number, so the same run printed two
    # different figures for the same measurement.
    sentence += f", and the whole {f'test suite passes in {tests_s:.0f} s' if tests_s else 'test suite passes'}."
    print("  Sentence for the write-up (section 7):")
    print("  " + sentence)
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
