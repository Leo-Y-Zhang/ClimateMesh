"""One-command judge validation for Climate Mesh.

A single command a judge can run from a clean clone to prove the whole project
works. It runs, in order:

  1. smoke test             (scripts/smoke_test.py)
  2. pytest suite           (python -m pytest -q)
  3. one *normal* demo cycle (run.py --mode demo --scenario normal --once)
  4. one *flood*  demo cycle (run.py --mode demo --scenario flood  --once)
  5. evidence export        (scripts/export_evidence.py)

then prints a compact PASS/FAIL summary table that is easy to screenshot. The
process exits non-zero if any step fails, so it doubles as a CI gate.

Steps 3-5 share an isolated throwaway database (set via ``CLIMATE_MESH_DB``) so
the run never touches the live demo DB, yet the evidence export still sees the
exact data the demo cycles produced. The smoke test and pytest each pin their
own isolated database internally, so they are unaffected.

    python scripts/judge_validate.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
# Dedicated DB for the demo cycles + export so the live demo DB is never touched.
JUDGE_DB = Path(tempfile.gettempdir()) / "climate_mesh_judge.db"


# --- Pure helpers (unit-tested; no subprocess) ----------------------------

def summarize_smoke(output: str) -> str:
    m = re.search(r"RESULT:\s*(\d+/\d+)\s*checks passed", output)
    return f"{m.group(1)} checks" if m else ""


def summarize_pytest(output: str) -> str:
    # Prefer the canonical "N passed" / "N failed" summary line.
    passed = re.search(r"(\d+)\s+passed", output)
    failed = re.search(r"(\d+)\s+failed", output)
    parts = []
    if passed:
        parts.append(f"{passed.group(1)} passed")
    if failed:
        parts.append(f"{failed.group(1)} failed")
    return ", ".join(parts)


def summarize_once(output: str) -> str:
    m = re.search(r"nodes=(\d+)\s+avg_risk=([\d.]+)\s+alerts=(\d+)", output)
    if m:
        return f"nodes={m.group(1)} avg_risk={m.group(2)} alerts={m.group(3)}"
    return ""


def summarize_export(output: str) -> str:
    m = re.search(r"\[evidence\]\s*Wrote\s*(\d+)\s*files", output)
    return f"{m.group(1)} files" if m else ""


def overall_ok(results) -> bool:
    """True only if every step passed. ``results`` = iterable of (name, ok, detail)."""
    results = list(results)
    return bool(results) and all(ok for _name, ok, _detail in results)


def render_summary_table(results) -> str:
    """Render a compact, screenshot-friendly PASS/FAIL table from step results.

    ``results`` is an iterable of ``(name, ok, detail)`` tuples.
    """
    results = list(results)
    line = "=" * 64
    thin = "-" * 64
    rows = [line, "  Climate Mesh — Judge Validation", line,
            f"  {'Step':<30} {'Result':<8} {'Detail'}", thin]
    for name, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        rows.append(f"  {name:<30} {tag:<8} {detail}")
    rows.append(thin)
    n_pass = sum(1 for _n, ok, _d in results if ok)
    verdict = "PASS" if overall_ok(results) else "FAIL"
    rows.append(f"  RESULT: {verdict}  ({n_pass}/{len(results)} steps passed)")
    rows.append(line)
    return "\n".join(rows)


# --- Subprocess orchestration ---------------------------------------------

def _child_env() -> dict:
    env = dict(os.environ)
    env["CLIMATE_MESH_DB"] = str(JUDGE_DB)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(argv, env) -> tuple[int, str]:
    proc = subprocess.run(
        argv, cwd=str(ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _reset_judge_db() -> None:
    for f in (JUDGE_DB, Path(str(JUDGE_DB) + "-wal"), Path(str(JUDGE_DB) + "-shm")):
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass


def main() -> int:
    env = _child_env()
    _reset_judge_db()

    steps = [
        ("1. Smoke test", [PYTHON, "scripts/smoke_test.py"], summarize_smoke),
        # No extra -q: pytest.ini already sets addopts=-q; a second -q would
        # suppress the "N passed" summary line this step parses for its detail.
        ("2. Pytest suite", [PYTHON, "-m", "pytest"], summarize_pytest),
        ("3. Demo cycle (normal)",
         [PYTHON, "run.py", "--mode", "demo", "--scenario", "normal", "--once"],
         summarize_once),
        ("4. Demo cycle (flood)",
         [PYTHON, "run.py", "--mode", "demo", "--scenario", "flood", "--once"],
         summarize_once),
        ("5. Evidence export", [PYTHON, "scripts/export_evidence.py"], summarize_export),
    ]

    results: list[tuple[str, bool, str]] = []
    for name, argv, summarize in steps:
        print(f"\n>>> {name}: {' '.join(argv[1:]) or argv[0]}")
        print("-" * 64)
        code, output = _run(argv, env)
        # Stream a trimmed tail so the judge can see each step actually ran.
        tail = output.strip().splitlines()[-12:]
        for ln in tail:
            print("    " + ln)
        ok = code == 0
        detail = summarize(output) or (f"exit {code}" if not ok else "ok")
        results.append((name, ok, detail))

    print("\n")
    print(render_summary_table(results))
    return 0 if overall_ok(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
