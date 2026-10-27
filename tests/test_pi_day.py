"""Measured evidence metadata and quick orchestration, with offline child results."""

import json
import os
import socket
import sqlite3
from contextlib import closing
import subprocess
import sys
from pathlib import Path

from scripts import pi_day


def fake_command(argv, **kwargs):
    if "scripts/pi_benchmark.py" in argv:
        assert "--with-tests" not in argv
        return 0, (
            "Full 20-node cycle  : median 42 ms over 5 cycles\n"
            "Peak memory (engine): 128 MB\nModel training : 1.2 s\n"
            "Sentence for the write-up (section 7):\nMeasured synthetic cycle: 42 ms.\n"
        )
    if "scripts/judge_validate.py" in argv:
        assert "--skip-tests" in argv
        return 0, "Pytest suite SKIPPED\nRESULT: PARTIAL  (4/5 steps passed)\n"
    assert "scripts/test_hardware_read.py" in argv
    return (
        0,
        f"RESULT: FALLBACK SIMULATION\n{socket.gethostname()}\n{Path.home()}/private/file\n",
    )


def fake_platform(tmp_path, monkeypatch):
    for key, content in {
        "MODEL": "Raspberry Pi 5 Model B Rev 1.0\x00",
        "OS_RELEASE": 'PRETTY_NAME="Test Bookworm"\n',
        "MEMINFO": "MemTotal: 8388608 kB\n",
        "THERMAL": "45123\n",
    }.items():
        path = tmp_path / key.lower()
        path.write_text(content)
        monkeypatch.setenv(f"PI_DAY_{key}_PATH", str(path))
    monkeypatch.setattr(pi_day.shutil, "which", lambda _: None)


def test_quick_writes_both_private_reports(tmp_path, monkeypatch):
    fake_platform(tmp_path, monkeypatch)
    monkeypatch.setattr(pi_day, "run_command", fake_command)
    output = tmp_path / "evidence/pi-day"
    assert pi_day.main(["--quick", "--output-dir", str(output)]) == 0
    files = list(output.iterdir())
    assert {p.suffix for p in files} == {".json", ".md"}
    report = json.loads(next(p for p in files if p.suffix == ".json").read_text())
    steps = {s["name"]: s for s in report["steps"]}
    assert steps["Full test suite"]["status"] == "SKIPPED"
    assert steps["Live run"]["status"] == "SKIPPED"
    assert steps["Benchmark"]["median_cycle_ms"] == 42
    assert steps["Judge validation"]["steps_skipped"] == 1
    platform = steps["Platform"]["values"]
    assert platform["model"] == "Raspberry Pi 5 Model B Rev 1.0"
    assert platform["os"] == "Test Bookworm"
    assert platform["ram_bytes"] == 8 * 1024**3
    assert platform["temperature_before"]["celsius"] == 45.123
    assert all(s["seconds"] >= 0 for s in report["steps"])
    for path in files:
        text = path.read_text()
        assert socket.gethostname() not in text
        assert str(Path.home()) not in text
        assert os.environ.get("USER", "unlikely-user-sentinel") not in text
    md = next(p for p in files if p.suffix == ".md").read_text()
    assert len(md.split("\n\n", 1)[0].splitlines()) == 5
    assert md.endswith("Send this file back\n")
    assert "tests passed" not in md.split("\n\n", 1)[0]


def test_quick_cli_with_fake_files(tmp_path, monkeypatch):
    fake_platform(tmp_path, monkeypatch)
    # Exercise the CLI parser in a subprocess; child diagnostics are fixture outputs.
    code = """from scripts import pi_day
from tests.test_pi_day import fake_command
pi_day.run_command = fake_command
raise SystemExit(pi_day.main())
"""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            "--quick",
            "--output-dir",
            str(tmp_path / "reports"),
        ],
        cwd=pi_day.ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Full test suite: SKIPPED" in proc.stdout
    assert len(list((tmp_path / "reports").glob("*"))) == 2


def test_step_failure_continues_and_no_invented_measurements(tmp_path, monkeypatch):
    fake_platform(tmp_path, monkeypatch)

    def fail_benchmark(argv, **kwargs):
        if "scripts/pi_benchmark.py" in argv:
            raise subprocess.TimeoutExpired(argv, 2, output="partial output")
        return fake_command(argv, **kwargs)

    monkeypatch.setattr(pi_day, "run_command", fail_benchmark)
    assert pi_day.main(["--quick", "--output-dir", str(tmp_path / "reports")]) == 1
    report = json.loads(next((tmp_path / "reports").glob("*.json")).read_text())
    steps = {s["name"]: s for s in report["steps"]}
    assert steps["Benchmark"]["status"] == "FAIL"
    assert steps["Hardware read"]["status"] == "PASS"
    assert "no cycle measurement available" in "\n".join(pi_day.summary_lines(report))


def test_db_live_round_counts_are_not_timing_estimates(tmp_path):
    path = tmp_path / "live.db"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE sensor_readings (node_id TEXT, source TEXT);
CREATE TABLE risk_scores (node_id TEXT);
INSERT INTO sensor_readings VALUES ('A', 'hardware'), ('B', 'simulation');
INSERT INTO risk_scores VALUES ('A'), ('B'), ('A'), ('B'), ('A');""")
    result = pi_day.live_db_summary(path)
    assert result["sources"] == {"hardware": 1, "simulation": 1}
    assert result["cycles_completed"] == 2
    assert result["median_cycle_ms"] is None
    assert "does not record" in result["cycle_time_reason"]


def test_missing_platform_and_thermal_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_DAY_MODEL_PATH", str(tmp_path / "missing"))
    monkeypatch.setenv("PI_DAY_THERMAL_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(pi_day.shutil, "which", lambda _: None)
    assert pi_day.platform_info()["model"].startswith("Not a Raspberry Pi: ")
    assert pi_day.temperature()["celsius"] is None


def test_pytest_counts_and_privacy(monkeypatch):
    assert pi_day.pytest_counts("2 failed, 290 passed, 3 skipped, 1 error in 41 s") == {
        "passed": 290,
        "failed": 2,
        "skipped": 3,
        "errors": 1,
    }
    monkeypatch.setenv("USER", "test-user-name")
    assert "test-user-name" not in pi_day.scrub(
        "test-user-name /home/someone/private/file"
    )
    assert "/home/someone" not in pi_day.scrub("/home/someone/private/file")


def test_live_run_stops_cleanly_and_reads_actual_sources(monkeypatch):
    import signal

    class Engine:
        def __init__(self, argv, *, cwd, env, stdout, stderr):
            assert argv[1:] == ["run.py", "--mode", "auto"]
            self.returncode = None
            with closing(sqlite3.connect(env["CLIMATE_MESH_DB"])) as db, db:
                db.executescript("""CREATE TABLE sensor_readings (node_id TEXT, source TEXT);
CREATE TABLE risk_scores (node_id TEXT);
INSERT INTO sensor_readings VALUES ('A', 'simulation');
INSERT INTO risk_scores VALUES ('A');""")
            stdout.write("measured engine output\n")

        def wait(self, timeout=None):
            if timeout == 60:
                raise subprocess.TimeoutExpired("engine", timeout)
            self.returncode = 0
            return 0

        def send_signal(self, sig):
            assert sig == signal.SIGINT

        def poll(self):
            return self.returncode

    monkeypatch.setattr(pi_day.subprocess, "Popen", Engine)
    result = pi_day.live_step()
    assert result["status"] == "PASS"
    assert result["sources"] == {"simulation": 1}
    assert result["cycles_completed"] == 1
    assert result["output"] == "measured engine output\n"
