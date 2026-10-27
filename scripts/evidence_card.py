"""Measure this checkout and machine, then render A4 evidence cards offline."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from config.nodes import NODES
from scripts import evaluate
from scripts.replay_animation import ROOT, load_json, replay_paths
from sensors.base import MEASUREMENT_FIELDS, VALID_SOURCES


def collected_test_count(root=ROOT):
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
    # pytest.ini adds -q too, so pytest may print per-file counts instead of IDs.
    summary = re.search(r"(\d+) tests? collected", result.stdout)
    if summary:
        return int(summary.group(1))
    counts = re.findall(r"^tests/.*?: (\d+)\s*$", result.stdout, re.MULTILINE)
    if counts:
        return sum(map(int, counts))
    ids = [line for line in result.stdout.splitlines() if line.startswith("tests/") and "::" in line]
    if ids:
        return len(ids)
    raise ValueError("Could not read pytest's collected test count:\n" + result.stdout)


def source_line_count(root=ROOT):
    excluded = {"tests", "venv", ".venv", "env", ".git", ".cache", ".tmp", "__pycache__"}
    total = 0
    for directory, folders, files in os.walk(root):
        folders[:] = [folder for folder in folders if folder not in excluded]
        total += sum(len((Path(directory) / name).read_text(encoding="utf-8").splitlines())
                     for name in files if name.endswith(".py"))
    return total


def test_file_count(root=ROOT):
    return len(list((Path(root) / "tests").rglob("test_*.py")))


def replay_counts(directory=ROOT / "evidence/replay"):
    payloads = [load_json(path) for path in replay_paths(directory)]
    if not payloads:
        raise ValueError("No recorded event replay outputs found")
    # Include labels: some EA stations have no reference, so it alone is not a key.
    gauges = {(g["reference"], g["label"]) for p in payloads for g in p["summary"]["gauges"]}
    used = {(g["reference"], g["label"]) for p in payloads for g in p["summary"]["gauges"] if g["used"]}
    return {"events": len({p["event_id"] for p in payloads}), "variants": len(payloads),
            "hours": sum(len(p["per_hour"]) for p in payloads),
            "unique_hours": len({(p["event_id"], h["hour"]) for p in payloads for h in p["per_hour"]}),
            "node_hours": sum(len(h["nodes"]) for p in payloads for h in p["per_hour"]),
            "gauges_fetched": len(gauges), "gauges_used": len(used),
            **heldout_counts(directory)}


def heldout_counts(directory=ROOT / "evidence/replay"):
    """Final held-out week replays (2023 development + 2024 test), as scored."""
    payloads = [load_json(path) for path in sorted(Path(directory).glob("holdout-*-grid.json*"))]
    payloads = [p for p in payloads if p.get("per_hour")]  # replays only, not placeholders
    return {"heldout_weeks": len(payloads),
            "heldout_node_hours": sum(len(h["nodes"]) for p in payloads for h in p["per_hour"])}


def fresh_benchmark(root=ROOT):
    """Subprocess isolates the benchmark's DB/environment from this renderer."""
    temporary = Path(root) / ".tmp"
    temporary.mkdir(exist_ok=True)
    result = subprocess.run([sys.executable, "scripts/pi_benchmark.py"], cwd=root,
                            env={**os.environ, "TMPDIR": str(temporary)},
                            capture_output=True, text=True, check=True)
    match = re.search(r"Full \d+-node cycle\s*:\s*median ([\d.]+) ms over (\d+) cycles", result.stdout)
    if not match:
        raise ValueError("Could not read benchmark median:\n" + result.stdout)
    return {"median_ms": float(match.group(1)), "cycles": int(match.group(2)),
            "platform": platform.platform(), "output": result.stdout}


def git_commit(root=ROOT):
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                          capture_output=True, text=True, check=True).stdout.strip()


def collect_numbers():
    """Every displayed measurement has a runtime source, easy to replace in tests."""
    return {"tests": collected_test_count(), "source_lines": source_line_count(),
            "test_files": test_file_count(), "nodes": len(NODES),
            "channels": len(MEASUREMENT_FIELDS), "sources": len(VALID_SOURCES),
            "replay": replay_counts(), "evaluation": evaluate.evaluation_frame_counts(),
            "benchmark": fresh_benchmark(), "commit": git_commit(),
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def tiles(numbers):
    replay, bench = numbers["replay"], numbers["benchmark"]
    return [(f"{numbers['tests']:,}", "Collected tests"),
            (f"{numbers['source_lines']:,}", "Python lines · tests/venvs excluded"),
            (f"{replay['heldout_weeks']:,}", "Held-out real weeks · 2023 + untouched 2024"),
            (f"{numbers['nodes']:,}", "Illustrative London nodes"),
            (f"{numbers['channels']:,}", "Channels per reading"),
            (f"{numbers['sources']:,}", "Supported data provenances"),
            (f"{replay['events']:,}", f"Recorded events · {replay['variants']:,} variants"),
            (f"{replay['hours']:,}", "Replayed hours · variants counted"),
            (f"{replay['node_hours'] + replay['heldout_node_hours']:,}",
             "Node-hours of recorded London scored"),
            (f"{replay['gauges_fetched']:,} / {replay['gauges_used']:,}", "Rain gauges · fetched / used"),
            (f"{sum(numbers['evaluation'].values()):,}", "Synthetic evaluation frames"),
            (f"{bench['median_ms']:g} ms", f"Median cycle · {bench['cycles']:,} fresh runs")]


def render_card(numbers, path=None, *, theme="dark"):
    """Return figure and its actual rendered text list for offline verification."""
    dark = theme == "dark"
    bg, panel = ("#101923", "#1d2d3c") if dark else ("#f4f6fa", "#ffffff")
    ink, muted = ("#f6f8fc", "#b5c6d8") if dark else ("#142535", "#465e72")
    accent = "#71c7f2" if dark else "#0072B2"
    fig = plt.figure(figsize=(2480 / 300, 3508 / 300), dpi=300, facecolor=bg)
    text = []

    def write(x, y, value, size, colour=ink, **kwargs):
        artist = fig.text(x, y, value, fontsize=size, color=colour, **kwargs)
        text.append(artist.get_text())

    write(0.065, 0.946, "CLIMATE MESH", 15, accent, weight="bold")
    write(0.065, 0.894, "by the numbers", 37, weight="bold")
    write(0.065, 0.858, "Measured from this checkout. Replayed from recorded data.", 11, muted)
    for index, (value, caption) in enumerate(tiles(numbers)):
        col, row = index % 3, index // 3
        x, y = 0.065 + col * 0.296, 0.677 - row * 0.167
        fig.patches.append(FancyBboxPatch((x, y), 0.274, 0.143,
                                          boxstyle="round,pad=0.008,rounding_size=0.008",
                                          transform=fig.transFigure, facecolor=panel,
                                          edgecolor=accent if index == 11 else panel, linewidth=0.8))
        write(x + 0.015, y + 0.075, value, 29, accent, weight="bold")
        write(x + 0.015, y + 0.025, caption, 8.1, muted)
    benchmark = numbers["benchmark"]
    write(0.065, 0.134, "BENCHMARK MACHINE / " + benchmark["platform"], 8.3, muted)
    write(0.065, 0.110, "Read → AI scoring → risk → alerts → database. Measured here; not a Pi estimate.",
          8.5, muted)
    replay = numbers["replay"]
    write(0.065, 0.087, f"Event replays only; held-out weeks excluded. {replay['unique_hours']:,} unique recorded hours.",
          8.5, muted)
    write(0.065, 0.059, "Recorded data. Not a forecast. Not a field validation.", 10, weight="bold")
    write(0.065, 0.037, f"Git {numbers['commit']} (working tree) · Generated {numbers['generated']}", 8, muted)
    # Keep arbitrarily long platform strings inside the A4 page.
    machine_artist = next(t for t in fig.texts if t.get_text().startswith("BENCHMARK MACHINE"))
    machine_artist.set_text(textwrap.fill(machine_artist.get_text(), 113))
    text = [artist.get_text() for artist in fig.texts]
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=300, facecolor=bg)
        print(f"Wrote {path}: {Path(path).stat().st_size:,} bytes", flush=True)
    return fig, text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/replay/figures")
    args = parser.parse_args()
    numbers = collect_numbers()
    print(numbers["benchmark"]["output"])
    for theme in ("dark", "light"):
        fig, _ = render_card(numbers, args.out / f"evidence-card-{theme}.png", theme=theme)
        plt.close(fig)
    (args.out / "evidence-card-numbers.json").write_text(json.dumps(numbers, indent=2) + "\n")
    print(json.dumps({k: v for k, v in numbers.items() if k != "benchmark"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
