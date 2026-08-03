"""One-command, hardware-free demo tour of Climate Mesh.

A judge (or anyone) can see the whole system work in about thirty seconds,
with no sensors and no internet. The tour runs one deterministic (judge-mode,
seeded) read -> risk -> alert cycle for each of the five demo scenarios --
normal, flood, heatwave, smog, storm -- against an isolated throwaway
database, then prints:

  * a compact per-scenario summary table (average risk, worst node, level
    spread, alerts fired), and
  * the plain-English explanation for the worst node of the highest-risk
    scenario, exactly as it would appear in an alert.

Honesty notes (do not regress):
  * Synthetic data only. Every reading is source="demo", is_simulated=True.
  * The tour never touches the live demo database (it sets CLIMATE_MESH_DB to
    its own temp file, like scripts/judge_validate.py does).
  * The output is deterministic: same seed, frozen tick, fresh DB per
    scenario, so repeated runs print the same numbers.

    python scripts/demo_tour.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

_JUDGE_TICK = 0.0
_DEFAULT_SEED = 1234


# --- Pure helpers (unit-tested; no DB, no subprocess) ----------------------

def summarize_scenario(scenario: str, results: list[dict],
                       names_by_id: dict[str, str], alerts_fired: int) -> dict:
    """Reduce one scenario cycle's risk results to a single summary row."""
    if not results:
        return {"scenario": scenario, "nodes": 0, "avg_risk": 0.0,
                "max_risk": 0.0, "worst_node": "", "worst_level": "",
                "levels": "", "alerts": alerts_fired, "worst_explanation": ""}
    worst = max(results, key=lambda r: r["score"])
    counts = Counter(r["level"] for r in results)
    levels = " ".join(
        f"{lvl}:{counts[lvl]}"
        for lvl in ("SAFE", "MODERATE", "WARNING", "CRITICAL") if counts[lvl]
    )
    return {
        "scenario": scenario,
        "nodes": len(results),
        "avg_risk": round(sum(r["score"] for r in results) / len(results), 1),
        "max_risk": worst["score"],
        "worst_node": names_by_id.get(worst["node_id"], worst["node_id"]),
        "worst_level": worst["level"],
        "levels": levels,
        "alerts": alerts_fired,
        "worst_explanation": worst.get("explanation", ""),
    }


def render_tour_table(rows: list[dict]) -> str:
    """Render the screenshot-friendly per-scenario summary table."""
    line = "=" * 78
    thin = "-" * 78
    out = [line,
           "  Climate Mesh - Demo Tour (deterministic, synthetic data, no hardware)",
           line,
           f"  {'Scenario':<10} {'Avg':>5} {'Max':>5}  {'Worst node':<22} "
           f"{'Level':<9} {'Alerts':>6}",
           thin]
    for r in rows:
        out.append(
            f"  {r['scenario']:<10} {r['avg_risk']:>5} {r['max_risk']:>5}  "
            f"{r['worst_node']:<22} {r['worst_level']:<9} {r['alerts']:>6}"
        )
    out.append(thin)
    out.append("  Risk is 0-100. Every reading above is source=demo, is_simulated=True.")
    out.append(line)
    return "\n".join(out)


def rows_ok(rows: list[dict], expected_scenarios: int, expected_nodes: int) -> bool:
    """Light self-check so the tour doubles as a pass/fail gate."""
    if len(rows) != expected_scenarios:
        return False
    for r in rows:
        if r["nodes"] != expected_nodes:
            return False
        if not (0.0 <= r["avg_risk"] <= 100.0 and 0.0 <= r["max_risk"] <= 100.0):
            return False
    return True


# --- Orchestration (uses whatever CLIMATE_MESH_DB is configured) -----------

def run_tour(seed: int = _DEFAULT_SEED) -> list[dict]:
    """Run one deterministic demo cycle per scenario; return summary rows.

    Uses the currently configured database (CLIMATE_MESH_DB or the default)
    and resets it before each scenario, so alert cooldowns never leak from
    one scenario -- or one tour -- into the next.
    """
    from ai.anomaly_model import AnomalyDetector
    from backend.risk_engine import compute_all, maybe_alert
    from data.database import (
        get_latest_readings_per_node, init_db, insert_reading,
        insert_risk_score, reset_db,
    )
    from sensors.simulated_adapter import SimulatedAdapter
    from simulation.scenarios import SCENARIOS

    init_db()
    detector = AnomalyDetector().train(quiet=True)  # synthetic: offline, deterministic

    rows: list[dict] = []
    for scenario in SCENARIOS:
        reset_db()
        adapter = SimulatedAdapter(demo=True, seed=seed)
        readings = adapter.read_all(scenario, tick=_JUDGE_TICK)
        for r in readings:
            insert_reading(r)
        latest = get_latest_readings_per_node()
        names_by_id = {r["node_id"]: r["node_name"] for r in latest}
        results = compute_all(latest, detector)
        alerts = 0
        by_id = {r["node_id"]: r for r in results}
        for reading in latest:
            risk = by_id[reading["node_id"]]
            insert_risk_score(risk)
            if maybe_alert(reading, risk):
                alerts += 1
        rows.append(summarize_scenario(scenario, results, names_by_id, alerts))
    return rows


def main() -> int:
    # Isolated throwaway DB so the tour never touches the live demo DB.
    import tempfile

    tour_db = Path(tempfile.gettempdir()) / "climate_mesh_demo_tour.db"
    os.environ["CLIMATE_MESH_DB"] = str(tour_db)
    for f in (tour_db, Path(str(tour_db) + "-wal"), Path(str(tour_db) + "-shm")):
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass

    from config.nodes import NODES
    from simulation.scenarios import SCENARIOS

    rows = run_tour()
    print(render_tour_table(rows))

    spotlight = max(rows, key=lambda r: r["max_risk"])
    if spotlight["worst_explanation"]:
        print()
        print(f"  Sample explanation ({spotlight['scenario']}, "
              f"{spotlight['worst_node']}):")
        print(f"    {spotlight['worst_explanation']}")

    ok = rows_ok(rows, expected_scenarios=len(SCENARIOS),
                 expected_nodes=len(NODES))
    print()
    print(f"  RESULT: {'PASS' if ok else 'FAIL'} "
          f"({len(rows)}/{len(SCENARIOS)} scenarios, deterministic, offline)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
