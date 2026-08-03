"""Climate Mesh launcher.

Starts the data source (per mode) and the risk engine. The dashboard runs
separately and reads the same SQLite database.

Operating modes
---------------
    simulation   Offline realistic generated data (default; no internet/sensors)
    demo         Deterministic, polished, screenshot-ready scenario data
    api          Live Open-Meteo data; warns and falls back to simulation if offline
    hardware     Physical Vernier sensor over a simulated mesh; falls back if absent
    auto         Detect hardware -> else API -> else simulation

Examples
--------
    python run.py --mode simulation
    python run.py --mode demo --scenario flood
    python run.py --mode demo --scenario flood --judge-mode
    python run.py --mode api
    python run.py --mode auto
    python run.py --mode demo --scenario heatwave --once   # one cycle, for CI
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Force UTF-8 console output so plain-English alerts (with °, —, etc.) render
# identically on Windows, macOS, and the Raspberry Pi.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).parent))

from ai.anomaly_model import AnomalyDetector
from backend.risk_engine import compute_all, maybe_alert, run_risk_engine
from data.database import (
    clear_old_data, get_latest_readings_per_node, init_db, insert_reading,
    insert_risk_score, record_run_start,
)
from sensors import create_adapter
from simulation.scenarios import SCENARIOS

DEMO_CONTROL_PATH = Path(__file__).parent / "data" / "demo_control.json"

# Judge mode freezes the simulation clock so every refresh shows the same state.
_JUDGE_TICK = 0.0


def git_commit_hash() -> str | None:
    """Return the current git commit hash, or None. Local-only, never networks."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).parent),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _write_scenario(scenario: str) -> None:
    DEMO_CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_CONTROL_PATH.write_text(json.dumps({"scenario": scenario}))


def _read_scenario(default: str) -> str:
    try:
        if DEMO_CONTROL_PATH.exists():
            return json.loads(DEMO_CONTROL_PATH.read_text()).get("scenario") or default
    except (json.JSONDecodeError, OSError):
        pass
    return default


def _banner(mode: str, scenario: str, judge: bool, source: str, notes: list[str]) -> None:
    print("=" * 60)
    print("  Climate Mesh — Decentralised Climate Early-Warning Mesh")
    print("=" * 60)
    print(f"  Mode:        {mode}")
    print(f"  Scenario:    {scenario}")
    print(f"  Judge mode:  {'on (deterministic, screenshot-stable)' if judge else 'off'}")
    print(f"  Data source: {source.upper()}")
    for n in notes:
        print(f"   - {n}")
    print("-" * 60)


def run_once(adapter, detector, scenario: str, tick: float) -> dict:
    """Run a single read -> risk -> alert cycle. Returns a small summary."""
    readings = adapter.read_all(scenario, tick)
    for r in readings:
        insert_reading(r)
    latest = get_latest_readings_per_node()
    results = compute_all(latest, detector)
    by_id = {r["node_id"]: r for r in results}
    alerts = 0
    for reading in latest:
        risk = by_id[reading["node_id"]]
        insert_risk_score(risk)
        if maybe_alert(reading, risk):
            alerts += 1
    avg = sum(r["score"] for r in results) / len(results) if results else 0.0
    return {"nodes": len(readings), "avg_risk": round(avg, 1), "alerts": alerts}


async def _sensor_loop(adapter, default_scenario: str, judge: bool, interval: float):
    import time
    start = time.time()
    while True:
        scenario = default_scenario if judge else _read_scenario(default_scenario)
        tick = _JUDGE_TICK if judge else (time.time() - start)
        readings = adapter.read_all(scenario, tick)
        for r in readings:
            insert_reading(r)
        await asyncio.sleep(interval)


async def _cleanup_loop():
    while True:
        await asyncio.sleep(300)
        clear_old_data(minutes=30)


async def main_async(args, adapter, detector, source: str, notes: list[str]):
    scenario = args.scenario or "normal"
    interval = 60.0 if source == "api" else 2.0
    _banner(args.mode, scenario, args.judge_mode, source, notes)
    print("[System] Open the dashboard in another terminal:")
    print("         python -m streamlit run dashboard/app.py")
    print("-" * 60)
    try:
        await asyncio.gather(
            _sensor_loop(adapter, scenario, args.judge_mode, interval),
            run_risk_engine(detector),
            _cleanup_loop(),
        )
    finally:
        adapter.cleanup()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Climate Mesh launcher")
    p.add_argument("--mode", default="simulation",
                   choices=["simulation", "demo", "api", "hardware", "auto"],
                   help="data source mode (default: simulation)")
    p.add_argument("--scenario", default="normal", choices=list(SCENARIOS),
                   help="demo scenario (default: normal)")
    p.add_argument("--judge-mode", action="store_true",
                   help="deterministic, screenshot-stable state for judges")
    p.add_argument("--once", action="store_true",
                   help="run a single read/risk cycle and exit (for CI/tests)")
    p.add_argument("--seed", type=int, default=1234, help="deterministic seed")
    p.add_argument("--ai-training", default="synthetic",
                   choices=["synthetic", "historical", "auto"],
                   help="AnomalyDetector training data source. 'synthetic' "
                        "(default) is offline/deterministic; 'historical'/'auto' "
                        "use the Open-Meteo archive and fall back to synthetic "
                        "if it is unavailable.")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # demo + judge both want deterministic data.
    demo = args.mode == "demo"
    init_db()

    detector = AnomalyDetector().train(mode=args.ai_training, quiet=args.once)
    adapter, notes = create_adapter(args.mode, demo=demo, seed=args.seed)
    source = getattr(adapter, "source", "simulation")
    scenario = args.scenario or "normal"
    _write_scenario(scenario)
    record_run_start(
        args.mode, scenario, args.judge_mode, source, " | ".join(notes),
        seed=args.seed, commit_hash=git_commit_hash(),
        training_mode=detector.training_mode,
    )

    if args.once:
        tick = _JUDGE_TICK if args.judge_mode else 5.0
        summary = run_once(adapter, detector, scenario, tick)
        adapter.cleanup()
        print(f"[once] mode={args.mode} scenario={scenario} source={source} "
              f"nodes={summary['nodes']} avg_risk={summary['avg_risk']} "
              f"alerts={summary['alerts']}")
        return 0

    try:
        asyncio.run(main_async(args, adapter, detector, source, notes))
    except KeyboardInterrupt:
        print("\n[System] Shutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
