"""Tests for the one-command judge-validation helpers (plan item 2.1).

Only the *pure* parsing/formatting helpers are exercised here — never the
subprocess orchestration — so this test does not (and must not) spawn another
pytest run. scripts/ is not a package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_judge_module():
    path = ROOT / "scripts" / "judge_validate.py"
    spec = importlib.util.spec_from_file_location("judge_validate_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


jv = _load_judge_module()


def test_summarize_smoke():
    assert jv.summarize_smoke("RESULT: 7/7 checks passed — PASS") == "7/7 checks"
    assert jv.summarize_smoke("nothing here") == ""


def test_summarize_pytest_passed_only():
    assert jv.summarize_pytest("48 passed in 12.3s") == "48 passed"


def test_summarize_pytest_with_failures():
    out = jv.summarize_pytest("2 failed, 46 passed in 9s")
    assert "46 passed" in out
    assert "2 failed" in out


def test_summarize_once():
    line = ("[once] mode=demo scenario=flood source=demo "
            "nodes=20 avg_risk=73.4 alerts=8")
    assert jv.summarize_once(line) == "nodes=20 avg_risk=73.4 alerts=8"


def test_summarize_export():
    assert jv.summarize_export("[evidence] Wrote 5 files to /x/evidence") == "5 files"


def test_overall_ok():
    assert jv.overall_ok([("a", True, ""), ("b", True, "")]) is True
    assert jv.overall_ok([("a", True, ""), ("b", False, "")]) is False
    assert jv.overall_ok([]) is False


def test_render_summary_table_pass():
    table = jv.render_summary_table([
        ("1. Smoke test", True, "7/7 checks"),
        ("2. Pytest suite", True, "48 passed"),
    ])
    assert "Judge Validation" in table
    assert "RESULT: PASS" in table
    assert "(2/2 steps passed)" in table
    assert "FAIL" not in table  # nothing failed


def test_render_summary_table_fail():
    table = jv.render_summary_table([
        ("1. Smoke test", True, "7/7 checks"),
        ("2. Pytest suite", False, "exit 1"),
    ])
    assert "RESULT: FAIL" in table
    assert "(1/2 steps passed)" in table
