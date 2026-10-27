"""Render recorded replay evidence at 200 dpi, without network access."""
from __future__ import annotations

import argparse
import json
import math
import sys
import textwrap
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from dashboard.accessibility import PALETTES
from dashboard.offline_map import BANDS
from simulation.replay import EVENT_IDS, ROOT

BLUE = PALETTES["colour-blind safe"]["SAFE"]
ORANGE = PALETTES["colour-blind safe"]["WARNING"]
STATE_COLOURS = {"quiet": "#eeeeee", "corroborated": "#56B4E9", "partial": "#F0E442",
                 "uncorroborated": "#D55E00", "unavailable": "#999999"}


def load(path):
    return json.loads(path.read_text())


def guides(ax):
    for band, lo, _, _ in BANDS[1:]:
        ax.axhline(lo, color="#bbbbbb", linewidth=0.6, zorder=0)
        ax.text(0.995, lo + 1, band, transform=ax.get_yaxis_transform(),
                ha="right", fontsize=7, color="#777777")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Risk score / 100")


def finish(fig, axes, title, path, *, gauges=False):
    fig.suptitle(title, fontsize=13, y=0.995)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
        ax.tick_params(labelsize=8)
        ax.set_xlabel("Local time (Europe/London)", fontsize=8)
    footer = "Recorded data: Open-Meteo archive (CC BY 4.0)"
    if gauges:
        footer += " · Environment Agency data (OGL v3)"
    fig.text(0.5, 0.008, footer, ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.04 if len(axes) < 6 else 0.015, 1, 0.97))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Wrote {path.relative_to(ROOT)}")


def series(payload, node_id, field):
    return [next(r[field] for r in h["nodes"] if r["node_id"] == node_id)
            for h in payload["per_hour"]]


def weather_figure(event, out):
    payload = load(out / f"{event}-grid.json")
    fixture = load(ROOT / "data" / "history" / f"{event}.json")
    times = [datetime.fromisoformat(h) for h in fixture["hours"]]
    heat = event.startswith("heat")
    channel = "temperature_2m" if heat else "wind_speed_10m"
    highlighted = max(fixture["nodes"], key=lambda n: max(fixture["nodes"][n][channel]))
    fig, axes = plt.subplots(2, 1, figsize=(8.27, 7.3), sharex=True)
    for node in fixture["nodes"]:
        axes[0].plot(times, series(payload, node, "score"), color=BLUE, alpha=0.24, lw=0.65)
        axes[1].plot(times, fixture["nodes"][node][channel], color=BLUE, alpha=0.24, lw=0.65)
    axes[0].plot(times, series(payload, highlighted, "score"), color=ORANGE, lw=2,
                 label=f"{'Hottest' if heat else 'Windiest'} grid node: {highlighted}")
    axes[1].plot(times, fixture["nodes"][highlighted][channel], color=ORANGE, lw=2,
                 label=f"{highlighted} {'temperature' if heat else 'sustained wind'}")
    guides(axes[0])
    axes[0].legend(fontsize=8, loc="upper left")
    axes[1].set_ylabel("Temperature (°C)" if heat else "Sustained wind (m/s)")
    if not heat:
        pressure = axes[1].twinx()
        pressure.plot(times, fixture["nodes"][highlighted]["pressure_msl"],
                      color="#000000", ls="--", lw=1.5, label="Mean sea-level pressure")
        pressure.set_ylabel("Pressure (hPa)")
        pressure.legend(fontsize=8, loc="upper right")
    axes[1].legend(fontsize=8, loc="upper left")
    finish(fig, axes, payload["title"] + " — all 20 grid nodes", out / "figures" / f"{event}.png")


def flood_figure(out):
    event = EVENT_IDS[0]
    grid = load(out / f"{event}-grid.json")
    gauges = load(out / f"{event}-gauges.json")
    fixture = load(ROOT / "data" / "history" / f"{event}.json")
    reports = gauges["summary"]["gauges"]
    used_nodes = sorted({g["nearest_node"] for g in reports if g["used"]})
    rows = math.ceil(len(reports) / 2)
    score_rows = max(1, len(used_nodes))
    fig = plt.figure(figsize=(8.27, max(7.0, rows * 2.15 + score_rows * 2.8)))
    layout = fig.add_gridspec(rows + score_rows, 2)
    times = [datetime.fromisoformat(h) for h in fixture["hours"]]
    axes = []
    for index, report in enumerate(reports):
        ax = fig.add_subplot(layout[index // 2, index % 2])
        axes.append(ax)
        ax.step(times, [v if count else float("nan") for v, count in
                        zip(report["hourly_mm"], report["readings_per_hour"])],
                where="mid", color=ORANGE,
                ls="-" if report["used"] else "--", label="EA gauge")
        ax.step(times, fixture["nodes"][report["nearest_node"]]["precipitation"],
                where="mid", color=BLUE, lw=1, label=f"Grid: {report['nearest_node']}")
        reason = "USED" if report["used"] else "EXCLUDED: " + report["reason"]
        ax.set_title(report["label"] + "\n" + textwrap.fill(reason, 48), fontsize=8, wrap=True)
        ax.set_ylabel("Rain (mm/hour)", fontsize=8)
        ax.legend(fontsize=6, loc="upper left")
        if 0 in report["readings_per_hour"]:
            ax.text(0.98, 0.95, "Empty UTC-boundary hour ≠ measured zero", ha="right", va="top",
                    fontsize=6, transform=ax.transAxes)
    for index, node in enumerate(used_nodes):
        ax = fig.add_subplot(layout[rows + index, :])
        axes.append(ax)
        ax.plot(times, series(grid, node, "score"), color=BLUE, label="Grid variant")
        ax.plot(times, series(gauges, node, "score"), color=ORANGE, label="Gauges variant")
        states = series(gauges, node, "corroboration")
        for i, (t, state) in enumerate(zip(times, states)):
            # Shading is the gauges variant's exact engine state at this hour.
            end = times[i + 1] if i + 1 < len(times) else t + (times[1] - times[0])
            ax.axvspan(t, end, facecolor=STATE_COLOURS[state], alpha=0.22, zorder=0)
        guides(ax)
        from matplotlib.patches import Patch
        handles, labels = ax.get_legend_handles_labels()
        handles += [Patch(facecolor=STATE_COLOURS[s], alpha=0.4, label=s) for s in sorted(set(states))]
        ax.legend(handles=handles, fontsize=7, loc="upper left", ncol=3)
        ax.set_title(node + " — shading: gauges-variant corroboration", fontsize=10)
    if not used_nodes:
        ax = fig.add_subplot(layout[rows, :])
        axes.append(ax)
        ax.text(0.5, 0.5, "No gauges qualified; gauges and grid scores are identical.",
                ha="center", transform=ax.transAxes)
    finish(fig, axes, fixture["title"] + " — each returned gauge and its nearest node",
           out / "figures" / f"{event}.png", gauges=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "replay")
    args = parser.parse_args()
    for event in EVENT_IDS[1:]:
        weather_figure(event, args.out)
    flood_figure(args.out)


if __name__ == "__main__":
    main()
