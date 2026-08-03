"""Fast smoke test for Climate Mesh.

Verifies the whole pipeline boots and behaves on a machine with no sensors and
(optionally) no internet. Uses an isolated database so it never touches the
demo DB. Exit code 0 = all good, 1 = a check failed.

    python scripts/smoke_test.py
"""

from __future__ import annotations

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

_TMP_DB = Path(tempfile.gettempdir()) / "climate_mesh_smoke.db"
os.environ["CLIMATE_MESH_DB"] = str(_TMP_DB)

from ai.anomaly_model import AnomalyDetector            # noqa: E402
from backend.risk_engine import compute_all             # noqa: E402
from config.nodes import NODES                          # noqa: E402
from data.database import (                             # noqa: E402
    get_latest_readings_per_node, get_risk_scores, init_db, insert_reading,
    insert_risk_score, reset_db,
)
from sensors.base import validate_reading               # noqa: E402
from sensors.hardware_status import detect              # noqa: E402
from sensors.simulated_adapter import SimulatedAdapter  # noqa: E402

_checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _checks.append((name, bool(condition), detail))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    for f in (_TMP_DB, Path(str(_TMP_DB) + "-wal"), Path(str(_TMP_DB) + "-shm")):
        if f.exists():
            f.unlink()

    print("Climate Mesh smoke test")
    print("-" * 40)

    # 1. Database creates.
    init_db()
    reset_db()
    check("database creates", True)

    # 2. 20 nodes generate readings with the canonical shape.
    adapter = SimulatedAdapter(demo=True)
    readings = adapter.read_all("flood", tick=0.0)
    check("20 nodes generate readings", len(readings) == 20, f"got {len(readings)}")
    shape_ok = True
    for r in readings:
        try:
            validate_reading(r)
        except ValueError as e:
            shape_ok = False
            print(f"        bad reading: {e}")
            break
    check("readings match canonical shape", shape_ok)

    # 3. Risk scores are within 0-100.
    for r in readings:
        insert_reading(r)
    detector = AnomalyDetector().train(quiet=True)
    results = compute_all(get_latest_readings_per_node(), detector)
    for risk in results:
        insert_risk_score(risk)
    in_bounds = all(0 <= r["score"] <= 100 for r in results)
    check("risk scores within 0-100", in_bounds)
    check("risk levels valid", all(r["level"] in ("SAFE", "MODERATE", "WARNING", "CRITICAL") for r in results))

    # 4. Dashboard data functions can read latest values.
    latest = get_latest_readings_per_node()
    scores = get_risk_scores()
    check("dashboard can read latest readings", len(latest) == 20)
    check("dashboard can read risk scores", len(scores) == 20)

    # 5. Simulation works without sensors / internet.
    sim = SimulatedAdapter(demo=False).read_all("normal", tick=3.0)
    check("simulation works without sensors", len(sim) == 20 and all(s["source"] == "simulation" for s in sim))

    # 6. Hardware mode does not crash without sensors.
    hw_ok = True
    hw_detail = ""
    try:
        from sensors.vernier_adapter import VernierAdapter
        vad = VernierAdapter()
        hw_readings = vad.read_all("normal", tick=0.0)
        vad.cleanup()
        hw_ok = len(hw_readings) == 20
        hw_detail = detect()["summary"]
    except Exception as e:  # noqa: BLE001
        hw_ok = False
        hw_detail = f"raised {e!r}"
    check("hardware mode does not crash without sensors", hw_ok, hw_detail)

    # 7. Node registry sanity.
    check("node registry has 20 nodes", len(NODES) == 20)

    print("-" * 40)
    passed = sum(1 for _, ok, _ in _checks if ok)
    total = len(_checks)
    ok = passed == total
    print(f"RESULT: {passed}/{total} checks passed — {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
