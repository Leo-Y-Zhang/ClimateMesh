"""Collect local, measured Pi-day evidence; no uploads and no raw host identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import socket
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_file(env: str, default: str) -> str:
    try:
        return Path(os.environ.get(env, default)).read_text().strip("\x00 \n")
    except OSError:
        return ""


def temperature() -> dict:
    # An explicit file override also bypasses vcgencmd for offline tests.
    if "PI_DAY_THERMAL_PATH" not in os.environ and shutil.which("vcgencmd"):
        result = subprocess.run(
            ["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=5
        )
        match = re.search(r"temp=([\d.]+)", result.stdout)
        if result.returncode == 0 and match:
            return {"celsius": float(match[1]), "method": "vcgencmd measure_temp"}
    value = read_file("PI_DAY_THERMAL_PATH", "/sys/class/thermal/thermal_zone0/temp")
    try:
        return {"celsius": float(value) / 1000, "method": "thermal_zone0"}
    except ValueError:
        return {"celsius": None, "reason": "SoC temperature unavailable"}


def platform_info() -> dict:
    os_release = read_file("PI_DAY_OS_RELEASE_PATH", "/etc/os-release")
    pretty = next(
        (
            line.partition("=")[2].strip("\"'")
            for line in os_release.splitlines()
            if line.startswith("PRETTY_NAME=")
        ),
        "OS unavailable",
    )
    memory = read_file("PI_DAY_MEMINFO_PATH", "/proc/meminfo")
    ram = re.search(r"^MemTotal:\s+(\d+)\s+kB", memory, re.MULTILINE)
    throttling = "Unavailable: vcgencmd not installed"
    if shutil.which("vcgencmd"):
        proc = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5
        )
        throttling = (
            proc.stdout.strip()
            if proc.returncode == 0
            else "Unavailable: vcgencmd failed"
        )
    return {
        "model": read_file("PI_DAY_MODEL_PATH", "/proc/device-tree/model")
        or f"Not a Raspberry Pi: {platform.machine()}",
        "os": pretty,
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": int(ram[1]) * 1024 if ram else None,
        "temperature_before": temperature(),
        "throttling": throttling,
    }


def run_command(
    argv: list[str], *, env: dict | None = None, timeout: int = 1800
) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout + proc.stderr


def command_step(argv: list[str]) -> dict:
    code, output = run_command(argv)
    return {
        "status": "PASS" if code == 0 else "FAIL",
        "reason": f"exit {code}",
        "command": shlex.join(argv),
        "output": output,
    }


def pytest_counts(output: str) -> dict:
    return {
        key: int(match[1])
        if (
            match := re.search(
                rf"(\d+) {'errors?' if key == 'errors' else key}\b", output
            )
        )
        else 0
        for key in ("passed", "failed", "skipped", "errors")
    }


def tests_step() -> dict:
    # Clear the repository's default -q so exactly one -q still prints counts.
    result = command_step([sys.executable, "-m", "pytest", "-q", "-o", "addopts="])
    result.update(pytest_counts(result["output"]))
    return result


def benchmark_step(quick: bool) -> dict:
    args = [sys.executable, "scripts/pi_benchmark.py"]
    if not quick:
        args.append("--with-tests")  # same invocation as the Arm CI job
    result = command_step(args)
    output = result["output"]
    patterns = {
        "median_cycle_ms": r"Full 20-node cycle\s*: median ([\d.]+) ms",
        "cycles": r"median [\d.]+ ms over (\d+) cycles",
        "peak_memory_mb": r"Peak memory \(engine\): ([\d.]+) MB",
        "training_seconds": r"Model training\s*: ([\d.]+) s",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        result[key] = float(match[1]) if match else None
    sentence = re.search(r"Sentence for the write-up[^\n]*\n\s*([^\n]+)", output)
    result["measured_sentence"] = sentence[1] if sentence else None
    if result["status"] == "PASS" and result["median_cycle_ms"] is None:
        result.update(status="FAIL", reason="No measured benchmark cycle found")
    return result


def judge_step(quick: bool) -> dict:
    result = command_step(
        [sys.executable, "scripts/judge_validate.py"]
        + (["--skip-tests"] if quick else [])
    )
    match = re.search(
        r"RESULT: (PASS|FAIL|PARTIAL)\s+\((\d+)/(\d+) steps passed\)", result["output"]
    )
    result["steps_passed"] = int(match[2]) if match else None
    result["steps_total"] = int(match[3]) if match else None
    result["steps_skipped"] = 1 if quick and match else 0
    if not match or match[1] == "FAIL":
        result.update(
            status="FAIL", reason="Judge validation failed or summary missing"
        )
    elif quick:
        result["reason"] = (
            "Executed validation steps passed; full-suite substep SKIPPED (--quick)"
        )
    return result


def live_db_summary(path: Path) -> dict:
    """Count completed fleet scoring rounds, never mistake row cadence for duration."""
    # sqlite3's own context manager commits but never closes; Windows then
    # cannot delete the temporary database, so close it explicitly.
    with closing(sqlite3.connect(path)) as db:
        sources = dict(
            db.execute("SELECT source, COUNT(*) FROM sensor_readings GROUP BY source")
        )
        counts = list(
            db.execute("SELECT node_id, COUNT(*) FROM risk_scores GROUP BY node_id")
        )
        nodes = db.execute(
            "SELECT COUNT(DISTINCT node_id) FROM sensor_readings"
        ).fetchone()[0]
    return {
        "sources": sources,
        "cycles_completed": min((r[1] for r in counts), default=0)
        if len(counts) == nodes
        else 0,
        "median_cycle_ms": None,
        "cycle_time_reason": "Database does not record cycle durations",
    }


def live_step() -> dict:
    with tempfile.TemporaryDirectory(prefix="climate-mesh-pi-day-") as tmp:
        path = Path(tmp) / "live.db"
        env = dict(os.environ, CLIMATE_MESH_DB=str(path), PYTHONUNBUFFERED="1")
        argv = [sys.executable, "run.py", "--mode", "auto"]
        # A file avoids a full stdout pipe blocking the engine during the minute.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
            proc = subprocess.Popen(
                argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
            stopped = False
            try:
                try:
                    proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    stopped = True
                    proc.send_signal(signal.SIGINT)
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            log.seek(0)
            output = log.read()
        result = {
            "status": "FAIL",
            "reason": "Engine exited before 60 seconds or failed to stop cleanly",
            "command": shlex.join(argv),
            "output": output,
        }
        if path.exists():
            result.update(live_db_summary(path))
        if stopped and proc.returncode == 0 and result.get("cycles_completed", 0) > 0:
            result.update(
                status="PASS", reason="60-second auto run completed and stopped cleanly"
            )
        return result


def scrub(text: str) -> str:
    """Remove host/user identity and home-directory paths from every report field."""
    homes = {
        os.environ.get("HOME", ""),
        os.environ.get("USERPROFILE", ""),
        str(Path.home()),
    }
    for home in sorted(homes, key=len, reverse=True):
        if home and home != "/":
            text = text.replace(home, "[HOME]")
    text = re.sub(r'(?:/home/|/Users/)[^\s\'"<>]+', "[HOME]", text)
    for identity in (
        socket.gethostname(),
        os.environ.get("USER"),
        os.environ.get("USERNAME"),
    ):
        if identity:
            text = re.sub(
                r"(?<![\w])" + re.escape(identity) + r"(?![\w])", "[REDACTED]", text
            )
    return text


def sanitize(value):
    # Scrub decoded strings: JSON's escaped newline would hide a word boundary.
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {scrub(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def summary_lines(report: dict) -> list[str]:
    steps = {s["name"]: s for s in report["steps"]}
    info = steps["Platform"].get("values", {})
    tests, bench, live, hardware = (
        steps[k] for k in ("Full test suite", "Benchmark", "Live run", "Hardware read")
    )
    test_line = (
        f"Tests: {tests['status']}; {tests.get('passed', 0)} passed, {tests.get('failed', 0)} failed in {tests['seconds']:.1f} s."
        if tests["status"] != "SKIPPED"
        else "Full test suite: SKIPPED (--quick)."
    )
    measured = bench.get("median_cycle_ms")
    bench_line = (
        f"One 20-node cycle took a median of {measured:g} ms (benchmark, synthetic demo data)."
        if measured is not None
        else f"Benchmark: {bench['status']}; no cycle measurement available."
    )
    source_line = (
        f"60-second run: {live['status']}; {live.get('cycles_completed', 0)} scoring rounds; recorded sources: {', '.join(live.get('sources', {})) or 'none'}."
        if live["status"] != "SKIPPED"
        else "60-second live run: SKIPPED (--quick)."
    )
    classification = re.search(
        r"RESULT: (REAL HARDWARE|FALLBACK SIMULATION)", hardware.get("output", "")
    )
    return [
        f"Device: {info.get('model', 'unavailable')}; OS: {info.get('os', 'unavailable')}.",
        test_line,
        bench_line,
        source_line,
        f"Hardware read: {classification[1] if classification else hardware['status']}; evidence records measured results only.",
    ]


def markdown(report: dict) -> str:
    lines = summary_lines(report) + ["", f"UTC run: {report['utc']}", ""]
    for step in report["steps"]:
        lines += [
            f"## {step['name']}: {step['status']} ({step['seconds']:.2f} s)",
            "",
            step["reason"],
            "",
        ]
        details = {
            k: v
            for k, v in step.items()
            if k not in ("name", "status", "seconds", "reason", "output")
        }
        lines += ["```json", json.dumps(details, indent=2), "```", ""]
        if step.get("output"):
            lines += ["```text", step["output"].rstrip(), "```", ""]
    return "\n".join(lines + ["Send this file back", ""])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="skip full-suite invocations and the 60-second live run",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence/pi-day")
    args = parser.parse_args(argv)
    started = datetime.now(timezone.utc)
    report = {
        "utc": started.isoformat(),
        "hostname_hash": hashlib.sha256(socket.gethostname().encode()).hexdigest()[:8],
        "steps": [],
    }

    def record(name, action=None):
        t0 = time.perf_counter()
        try:
            result = action() if action else {"status": "SKIPPED", "reason": "--quick"}
        except Exception as exc:
            result = {"status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"}
            if isinstance(exc, subprocess.TimeoutExpired):
                result["output"] = str(exc.stdout or "") + str(exc.stderr or "")
        result.update(name=name, seconds=time.perf_counter() - t0)
        report["steps"].append(result)
        print(f"{name}: {result['status']} ({result['seconds']:.2f} s)")

    record(
        "Platform",
        lambda: {
            "status": "PASS",
            "reason": "Platform information measured; unavailable fields explicit",
            "values": platform_info(),
        },
    )
    record("Full test suite", None if args.quick else tests_step)
    record("Benchmark", lambda: benchmark_step(args.quick))
    record("Judge validation", lambda: judge_step(args.quick))
    record(
        "Hardware read",
        lambda: command_step([sys.executable, "scripts/test_hardware_read.py"]),
    )
    record("Live run", None if args.quick else live_step)
    record(
        "Final temperature",
        lambda: {
            "status": "PASS"
            if (t := temperature())["celsius"] is not None
            else "SKIPPED",
            "reason": "Measured after run" if t["celsius"] is not None else t["reason"],
            "values": t,
        },
    )
    # Sanitize every string, including exceptions and captured command output.
    report = sanitize(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.output_dir / f"{started:%Y-%m-%d}-{report['hostname_hash']}"
    stem.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    stem.with_suffix(".md").write_text(scrub(markdown(report)), encoding="utf-8")
    print("Reports written: " + scrub(str(stem)) + ".md and .json")
    return 1 if any(s["status"] == "FAIL" for s in report["steps"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
