"""Render recorded replay evidence at 200 dpi, without network access."""
from __future__ import annotations

import argparse
import math
import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from dashboard.accessibility import PALETTES
from dashboard.offline_map import BANDS
from simulation.replay import EVENT_IDS, ROOT
from simulation.replay_io import read_json

BLUE = PALETTES["colour-blind safe"]["SAFE"]
ORANGE = PALETTES["colour-blind safe"]["WARNING"]
STATE_COLOURS = {"quiet": "#eeeeee", "corroborated": BLUE,
                 "partial": PALETTES["colour-blind safe"]["MODERATE"],
                 "uncorroborated": ORANGE,
                 "unavailable": PALETTES["colour-blind safe"]["CRITICAL"]}


def load(path):
    return read_json(path)


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
        ax.set_xlabel("Local time (Europe/London)" if ax is axes[-1]
                      or not ax.get_shared_x_axes().joined(ax, axes[-1]) else "", fontsize=8)
    footer = "Weather data by Open-Meteo.com (CC BY 4.0)"
    if gauges:
        footer += " · Contains Environment Agency data (OGL v3)"
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
    others = [n for n in fixture["nodes"] if n != highlighted]
    for ax, values in zip(axes, (
            [series(payload, n, "score") for n in others],
            [fixture["nodes"][n][channel] for n in others])):
        ax.fill_between(times, np.min(values, axis=0), np.max(values, axis=0),
                        color=BLUE, alpha=0.16, label="Other 19 nodes: min–max")
    axes[0].plot(times, series(payload, highlighted, "score"), color=ORANGE, lw=2,
                 label=f"{'Hottest' if heat else 'Windiest'} grid node: {highlighted}")
    axes[1].plot(times, fixture["nodes"][highlighted][channel], color=ORANGE, lw=2,
                 label=f"{highlighted} {'temperature' if heat else 'sustained wind'}")
    peak_values = fixture["nodes"][highlighted][channel]
    peak = max(range(len(peak_values)), key=peak_values.__getitem__)
    axes[1].annotate(f"{highlighted}: {peak_values[peak]:g} {'°C' if heat else 'm/s'}\n"
                     f"{times[peak]:%d %b %H:%M}", (times[peak], peak_values[peak]),
                     xytext=(-85, -45), textcoords="offset points", fontsize=9,
                     arrowprops=dict(arrowstyle="->", color=ORANGE),
                     bbox=dict(facecolor="white", edgecolor="none", alpha=0.9))
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
           out / "figures" / f"{event}-all-gauges.png", gauges=True)


def flood_hero(out):
    event = EVENT_IDS[0]
    grid = load(out / f"{event}-grid.json")
    gauges = load(out / f"{event}-gauges.json")
    fixture = load(ROOT / "data" / "history" / f"{event}.json")
    reports = gauges["summary"]["gauges"]
    putney = next(g for g in reports if g["label"] == "Putney Heath")
    mitcham = next(g for g in reports if g["label"] == "Mitcham")
    times = [datetime.fromisoformat(h) for h in fixture["hours"]]
    fig, axes = plt.subplots(3, 1, figsize=(8.27, 9), sharex=True)
    for ax, report in zip(axes[:2], (putney, mitcham)):
        rain = fixture["nodes"][report["nearest_node"]]["precipitation"]
        observed = [v if count else float("nan") for v, count in
                    zip(report["hourly_mm"], report["readings_per_hour"])]
        ax.bar(times, observed, width=0.032, color=ORANGE, label="Measured EA gauge")
        ax.plot(times, rain, color=BLUE, marker="o", ms=3, label="Nearest node's grid cell")
        ax.set_ylabel("Rain (mm/hour)")
        ax.set_title(f"{report['label']}: gauge {report['window_total_mm']:g} mm in local window; "
                     f"grid {sum(rain):.1f} mm", loc="left", fontsize=10)
        ax.legend(fontsize=8, loc="upper left")
        ax.text(0.99, 0.88, f"UTC-day gauge total: {report['total_mm']:g} mm\n"
                "00:00 unobserved (UTC request boundary)",
                transform=ax.transAxes, ha="right", va="top", fontsize=7)
    node = putney["nearest_node"]
    axes[2].plot(times, series(gauges, node, "score"), color=ORANGE, lw=2, label="Gauge-fed risk")
    axes[2].plot(times, series(grid, node, "score"), color=BLUE, lw=2, label="Grid-fed risk")
    states = series(gauges, node, "corroboration")
    for t, state in zip(times, states):
        axes[2].axvspan(t, t + timedelta(hours=1), color=STATE_COLOURS[state], alpha=0.18, zorder=0)
    from matplotlib.patches import Patch
    handles, _ = axes[2].get_legend_handles_labels()
    handles += [Patch(facecolor=STATE_COLOURS[s], alpha=0.4, label=s) for s in sorted(set(states))]
    axes[2].legend(handles=handles, fontsize=7, ncol=2, loc="upper left")
    axes[2].set_title(f"{node}: calibrated risk; shading shows gauge-fed corroboration", loc="left", fontsize=10)
    guides(axes[2])
    wetter, drier = sorted((putney, mitcham), key=lambda g: g["window_total_mm"], reverse=True)
    ratio = wetter["window_total_mm"] / drier["window_total_mm"]
    title = (f"{wetter['label']} recorded {ratio:.0f} times {drier['label']}'s rain\n"
             f"Available local window: {wetter['window_total_mm']:g} mm versus "
             f"{drier['window_total_mm']:g} mm · 12 July 2021")
    finish(fig, axes, title, out / "figures" / f"{event}-hero.png", gauges=True)


def flood_map(out):
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    from dashboard.offline_map import WATERWAYS, ASPECT, LAT_RANGE, LON_RANGE
    from config.nodes import NODES

    event = EVENT_IDS[0]
    fixture = load(ROOT / "data" / "history" / f"{event}.json")
    gauges = load(out / f"{event}-gauges.json")["summary"]["gauges"]
    fig = plt.figure(figsize=(8.27, 8.4))
    ax = fig.add_axes((0.10, 0.23, 0.84, 0.60))
    cells = {}
    for node, cell in fixture["grid_cells"].items():
        position = (cell["latitude"], cell["longitude"])
        total = sum(fixture["nodes"][node]["precipitation"])
        if position in cells and abs(cells[position] - total) > 0.001:
            raise ValueError("one grid position returned inconsistent rainfall totals")
        cells[position] = total
    lats = sorted({p[0] for p in cells})
    # Longitude spacing varies slightly by latitude on the returned grid.
    # Approximate cell footprints from centre spacing, without filling cells
    # that were not sampled by any of the 20 requests.
    spacings = [b - a for lat in lats
                for a, b in zip(sorted(lon for y, lon in cells if y == lat),
                                sorted(lon for y, lon in cells if y == lat)[1:])]
    width, height = float(np.median(spacings)), float(np.median(np.diff(lats)))
    grid_cmap = LinearSegmentedColormap.from_list("grid_rain", ["white", ORANGE])
    grid_norm = Normalize(0, max(cells.values()))
    for (lat, lon), total in cells.items():
        ax.add_patch(Rectangle((lon - width / 2, lat - height / 2), width, height,
                               facecolor=grid_cmap(grid_norm(total)), alpha=0.18, zorder=0))
    bg = matplotlib.cm.ScalarMappable(norm=grid_norm, cmap=grid_cmap)
    for name, pts in WATERWAYS.items():
        ax.plot([p[1] for p in pts], [p[0] for p in pts], color=BLUE,
                lw=2 if name == "River Thames" else 0.9, alpha=0.45, zorder=1)
    positions = {str(g["reference"]): g for g in fixture["gauges"]}
    valid = [g for g in gauges if g["total_mm"] is not None]
    cmap = LinearSegmentedColormap.from_list("gauge_rain", ["#ffffff", BLUE, "#000000"])
    norm = Normalize(0, max(g["total_mm"] for g in valid))
    for g in gauges:
        pos = positions[str(g["reference"])]
        total = g["total_mm"]
        ax.scatter(pos["lon"], pos["lat"], s=25 + (total or 0) * 6,
                   c=[cmap(norm(total))] if total is not None else ["white"],
                   edgecolors="black", linewidths=0.7, zorder=3,
                   marker="o" if total is not None else "X")
    selected = sorted(valid, key=lambda g: (g["total_mm"], g["label"]))
    labelled = selected[-6:] + selected[:3]
    for i, g in enumerate(labelled):
        pos = positions[str(g["reference"])]
        offset = (-7 if pos["lon"] > 0.15 or g["label"] == "North Mymms" else 7,
                  -17 if pos["lat"] > 51.69 or i % 3 else 15)
        label = textwrap.fill(g["label"], 18) + f"\n{g['total_mm']:g} mm"
        ax.annotate(label, (pos["lon"], pos["lat"]),
                    xytext=offset, textcoords="offset points", fontsize=7,
                    ha="left" if offset[0] > 0 else "right",
                    bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=1),
                    arrowprops=dict(arrowstyle="-", color="#555555", lw=0.5), zorder=5)
    ax.scatter([n["longitude"] for n in NODES], [n["latitude"] for n in NODES],
               marker="+", c=ORANGE, s=30, linewidths=1.2, zorder=4)
    gauge_lats = [g["lat"] for g in fixture["gauges"]]
    gauge_lons = [g["lon"] for g in fixture["gauges"]]
    ax.set_xlim(min(LON_RANGE[0], min(gauge_lons) - 0.025), max(LON_RANGE[1], max(gauge_lons) + 0.025))
    ax.set_ylim(min(LAT_RANGE[0], min(gauge_lats) - 0.02), max(LAT_RANGE[1], max(gauge_lats) + 0.02))
    ax.set_aspect(ASPECT)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    fig.suptitle("Rain varied sharply across London · 12 July 2021\n"
                 "Gauge totals for the requested UTC day; grid totals for the local day", fontsize=12, y=0.98)
    keys = [Line2D([], [], marker="o", color="black", ls="", markersize=8,
                   label="Rain gauge: larger / darker = more rain"),
            Line2D([], [], marker="+", color=ORANGE, ls="", markersize=8, label="Illustrative node (20)"),
            Line2D([], [], marker="X", color="black", ls="", label="Gauge total unknown"),
            Rectangle((0, 0), 1, 1, color="#bbbbbb", alpha=0.4, label="Faint cells: sampled grid rainfall (approx. footprint)")]
    fig.legend(handles=keys, loc="upper center", bbox_to_anchor=(0.5, 0.91),
               ncol=2, fontsize=7, frameon=False)
    fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap),
                 cax=fig.add_axes((0.12, 0.12, 0.32, 0.014)), orientation="horizontal",
                 label="Gauge rain total (mm)").ax.tick_params(labelsize=7)
    fig.colorbar(bg, cax=fig.add_axes((0.60, 0.12, 0.28, 0.014)), orientation="horizontal",
                 label="Grid rain total (mm)").ax.tick_params(labelsize=7)
    fig.text(0.5, 0.02, "Weather data by Open-Meteo.com (CC BY 4.0) · Contains Environment Agency data (OGL v3)\n"
             "Offline waterways: illustrative orientation lines from dashboard/offline_map.py",
             ha="center", fontsize=7)
    path = out / "figures" / f"{event}-gauge-map.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Wrote {path.relative_to(ROOT)}")


def calibration_figure(out):
    report = load(out / "calibration-summary.json")
    fig, axes = plt.subplots(3, 1, figsize=(8.27, 10.8))
    groups = [([k for k in report if not k.startswith('holdout')], "Recorded events (full windows)"),
              ([k for k in report if '2023' in k], "2023 development weeks — all three stages"),
              ([k for k in report if '2024' in k], "2024 untouched test weeks — reported as measured")]
    stages = [('as_found', BLUE, 'As found'), ('round_1', '#999999', 'Round 1'),
              ('calibrated', ORANGE, 'Round 2')]
    for ax, (keys, title) in zip(axes, groups):
        x = np.arange(len(keys))
        selected = [stage for stage in stages if all(stage[0] in report[k] for k in keys)]
        width = 0.8 / len(selected)
        for i, (version, colour, label) in enumerate(selected):
            values = [report[k][version]['london_episodes'] for k in keys]
            bars = ax.bar(x + (i - (len(selected) - 1) / 2) * width, values,
                          width * 0.95, color=colour, label=label)
            labels = [f"{v}\n({report[k][version]['alert_hours']} h)" for k, v in zip(keys, values)]
            ax.bar_label(bars, labels=labels, fontsize=7, padding=3)
        labels = [k.replace('-grid', '').replace('-gauges', '\ngauges').replace('holdout-', '')
                  for k in keys]
        ax.set_xticks(x, labels, fontsize=8)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel('London-wide episodes')
        ax.spines[['top', 'right']].set_visible(False)
        ax.margins(y=0.3)
        ax.grid(axis='y', alpha=0.15)
        ax.set_axisbelow(True)
    axes[0].legend(fontsize=8, ncols=3)
    fig.suptitle('Delivered alert episodes across calibration stages', fontsize=13)
    fig.text(0.5, 0.015, 'Weather data by Open-Meteo.com (CC BY 4.0) · EA rainfall (OGL v3)\n'
             'Per hazard: consecutive sampled hours with any node alerting; parentheses: node alert-hours.\n'
             'Sensor-check is a separate delivered type. Episodes are not adjudicated weather incidents.',
             ha='center', fontsize=7)
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    path = out / 'figures' / 'calibration-before-after.png'
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Wrote {path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "replay")
    args = parser.parse_args()
    for event in EVENT_IDS[1:3]:
        weather_figure(event, args.out)
    flood_figure(args.out)
    flood_hero(args.out)
    flood_map(args.out)
    calibration_figure(args.out)


if __name__ == "__main__":
    main()
