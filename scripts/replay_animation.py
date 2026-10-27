"""Animate recorded event replay JSON, without running the scoring engine."""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matplotlib
matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from matplotlib.figure import Figure
from PIL import Image

from config.nodes import NODES_BY_ID
from dashboard.accessibility import PALETTES
from dashboard.offline_map import (ASPECT, LABEL_POS, LAT_RANGE, LON_RANGE,
                                   WATERWAYS, WATERWAY_LABEL_AT, mesh_links)

ROOT = Path(__file__).resolve().parent.parent
# The dark frame needs the standard bands: the colour-blind palette draws
# CRITICAL in black, which disappears on a dark background.
COLOURS = PALETTES["standard"]
BG, PANEL, INK, MUTED = "#101923", "#1b2938", "#f4f6fa", "#b5c6d8"
DISCLAIMER = ("Recorded data, replayed through the unchanged Climate Mesh engine. "
              "Not a forecast. Not a field validation.")


class HourCachedFigure(Figure):
    """Cache the hourly text/basemap raster; redraw only moving marker artists.

    Matplotlib's movie writers redraw the canvas for every encoded frame. Text
    and geometry are fixed within an hour, so Agg background restoration avoids
    repeatedly laying out and rasterising all the same labels.
    """

    background_token = None
    draw_dynamic = False
    dynamic_artists = ()
    _background = None
    _background_key = None

    def draw(self, renderer):
        if not hasattr(renderer, "copy_from_bbox"):
            return super().draw(renderer)
        key = (self.background_token, renderer.width, renderer.height, self.dpi)
        if self._background is None or key != self._background_key:
            visibility = [artist.get_visible() for artist in self.dynamic_artists]
            try:
                for artist in self.dynamic_artists:
                    artist.set_visible(False)
                super().draw(renderer)
                self._background = renderer.copy_from_bbox(self.bbox)
                self._background_key = key
            finally:
                for artist, visible in zip(self.dynamic_artists, visibility):
                    artist.set_visible(visible)
        renderer.restore_region(self._background)
        if self.draw_dynamic:
            for artist in self.dynamic_artists:
                artist.draw(renderer)
        self.stale = False


def load_json(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def replay_paths(directory):
    """Top-level event outputs only; prefer plain JSON if both encodings exist."""
    paths = {}
    for pattern in ("*.json.gz", "*.json"):
        for path in sorted(Path(directory).glob(pattern)):
            stem = path.name.removesuffix(".gz").removesuffix(".json")
            if stem.startswith(("flood-", "heat-", "storm-")) and stem.endswith(("-grid", "-gauges")):
                paths[stem] = path
    return [paths[key] for key in sorted(paths)]


@dataclass(frozen=True)
class Frame:
    hour_index: int
    fraction: float
    hour: str
    readings: list[dict]
    visual_scores: dict[str, float]


def generate_frames(payload, frames_per_hour=15):
    """Hold each recorded sample for exactly N frames, including the final hour.

    Only marker sizes interpolate towards the next sample. All text, bands,
    ranking, channels and alerts use the current recorded sample unchanged.
    """
    if frames_per_hour < 1:
        raise ValueError("frames_per_hour must be positive")
    hours = payload["per_hour"]
    for index, step in enumerate(hours):
        following = {r["node_id"]: r for r in hours[min(index + 1, len(hours) - 1)]["nodes"]}
        for subframe in range(frames_per_hour):
            fraction = subframe / frames_per_hour
            scores = {r["node_id"]: r["score"] + fraction *
                      (following[r["node_id"]]["score"] - r["score"]) for r in step["nodes"]}
            yield Frame(index, fraction, step["hour"], step["nodes"], scores)


def clock_label(hour, timezone):
    local = datetime.fromisoformat(hour)
    zone = ZoneInfo(timezone)
    local = local.replace(tzinfo=zone) if local.tzinfo is None else local.astimezone(zone)
    return local.strftime("%a %d %b %Y %H:%M %Z")


def outcome(payload):
    """Measured end-card values, exclusively from the replay's summary."""
    summary = payload["summary"]
    first = {}
    for band in ("WARNING", "CRITICAL"):
        hours = [bands[band] for bands in summary["first_band_per_node"].values() if bands[band]]
        first[band] = min(hours) if hours else None
    peak = max(summary["peak_per_node"], key=lambda n: summary["peak_per_node"][n]["score"])
    return {"first": first, "peak_node": peak, "peak_score": summary["peak_score"],
            "peak_hour": summary["peak_per_node"][peak]["hour"],
            "alerts_by_type": summary["alerts_by_type"],
            "sensor_checks": summary["alerts_by_type"].get("sensor-check", 0),
            "damped_nodes": summary["damped_nodes"]}


def outcome_text(payload):
    values = outcome(payload)
    first = [f"First {band}: " + (clock_label(hour, payload["timezone"]) if hour else "not reached")
             for band, hour in values["first"].items()]
    alerts = ", ".join(f"{kind}: {count}" for kind, count in values["alerts_by_type"].items()) or "none"
    return [*first, f"Peak: {values['peak_node']}  {values['peak_score']:g}/100",
            clock_label(values["peak_hour"], payload["timezone"]),
            f"Alerts by type (sampled node-hours): {alerts}",
            f"Sensor-check alerts: {values['sensor_checks']} · damped nodes: {len(values['damped_nodes'])}"]


def alert_text(payload, index):
    """List every alert at the latest firing hour, grouped to fit the ticker."""
    for step in reversed(payload["per_hour"][:index + 1]):
        groups = {}
        for row in step["nodes"]:
            if row["alert"]:
                groups.setdefault(row["alert"], []).append(row["node_id"])
        if groups:
            lines = ["LATEST ALERTS · " + step["hour"].replace("T", " ")]
            for kind, nodes in sorted(groups.items()):
                lines.extend(textwrap.wrap(f"{kind}: " + ", ".join(nodes), 72))
            return "\n".join(lines)
    return "EVENT TICKER\nNo alerts raised yet."


class ReplayFigure:
    """Static basemap plus reusable artists: no network, tiles or engine calls."""

    def __init__(self, payload, gauge_payload=None, grid_rain=None):
        self.payload = payload
        self.last_hour = None
        self.grid_rain = grid_rain
        reports = (gauge_payload or payload)["summary"]["gauges"]
        used = [g for g in reports if g["used"]]
        self.gauge = max(used, key=lambda g: g["window_total_mm"]) if used else None
        self.fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=BG,
                              FigureClass=HourCachedFigure)
        self.map = self.fig.add_axes((0.025, 0.17, 0.56, 0.65), facecolor=PANEL)
        self.map.set(xlim=LON_RANGE, ylim=LAT_RANGE, aspect=ASPECT)
        self.map.set_axis_off()
        for name, points in WATERWAYS.items():
            self.map.plot([p[1] for p in points], [p[0] for p in points],
                          color="#487eaa", lw=5 if name == "River Thames" else 2, zorder=1)
            lat, lon, anchor = WATERWAY_LABEL_AT[name]
            self.map.text(lon, lat, name, color="#90b9d9", fontsize=10, ha=anchor)
        for a, b in mesh_links():
            nodes = [NODES_BY_ID[a], NODES_BY_ID[b]]
            self.map.plot([n["longitude"] for n in nodes], [n["latitude"] for n in nodes],
                          color="#708296", alpha=0.35, lw=1, zorder=0)
        self.ids = [r["node_id"] for r in payload["per_hour"][0]["nodes"]]
        x = [NODES_BY_ID[n]["longitude"] for n in self.ids]
        y = [NODES_BY_ID[n]["latitude"] for n in self.ids]
        self.markers = self.map.scatter(x, y, s=100, edgecolors=INK, linewidths=1.7, zorder=4)
        self.pulses = self.map.scatter(x, y, s=100, facecolors="none", edgecolors=INK, zorder=3)
        self.checks = self.map.scatter(x, y, s=380, facecolors="none", edgecolors=INK,
                                       linewidths=1.5, linestyles="dashed", zorder=5)
        self.fig.dynamic_artists = (self.pulses, self.markers, self.checks)
        self.node_labels = []
        self.check_labels = []
        for node, lon, lat in zip(self.ids, x, y):
            position = LABEL_POS.get(node, "top center").split()
            dx = {"left": -9, "center": 0, "right": 9}[position[1]]
            dy = {"top": 12, "middle": 0, "bottom": -15}[position[0]]
            ha = {"left": "right", "center": "center", "right": "left"}[position[1]]
            va = {"top": "bottom", "middle": "center", "bottom": "top"}[position[0]]
            name = node.replace("-", " ").title()
            self.node_labels.append(self.map.annotate(
                name, (lon, lat), xytext=(dx, dy), textcoords="offset points",
                fontsize=10, color=INK, ha=ha, va=va))
            label = self.map.annotate(name + "\ncheck sensor", (lon, lat), xytext=(dx, dy),
                                      textcoords="offset points", fontsize=10, color=INK, ha=ha, va=va,
                                      bbox=dict(facecolor=PANEL, edgecolor="none", pad=1))
            self.check_labels.append(label)
        self.text(0.03, 0.94, "CLIMATE MESH / RECORDED EVENTS", 16, colour=MUTED)
        self.text(0.03, 0.88, "London, hour by hour", 30, weight="bold")
        self.text(0.03, 0.16, "Offline basemap · approximate waterways · illustrative node locations", 12,
                  colour=MUTED)
        self.text(0.03, 0.12, "Size animates between samples; readings and bands change on the hour.", 12,
                  colour=MUTED)
        for i, (band, colour) in enumerate(COLOURS.items()):
            left = 0.03 + i * 0.14
            self.fig.patches.append(Rectangle((left, 0.205), 0.012, 0.017,
                                              transform=self.fig.transFigure, facecolor=colour,
                                              edgecolor=INK, linewidth=1))
            self.text(left + 0.017, 0.213, band, 11)
        self.text(0.615, 0.94, textwrap.fill(payload["title"], 43), 21, weight="bold", va="top")
        self.text(0.615, 0.845, "Variant: " + payload["variant"] + " · archive / estimated", 13, colour=MUTED)
        self.clock = self.text(0.615, 0.80, "", 22, weight="bold")
        self.text(0.615, 0.75, "HIGHEST RISK / RECORDED SCORE", 13, colour=MUTED)
        self.rank_labels, self.bars = [], []
        for i in range(5):
            y0 = 0.701 - i * 0.051
            self.rank_labels.append(self.text(0.615, y0 + 0.007, "", 13))
            self.fig.patches.append(Rectangle((0.615, y0 - 0.017), 0.35, 0.009,
                                              transform=self.fig.transFigure, facecolor=PANEL))
            bar = Rectangle((0.615, y0 - 0.017), 0, 0.009, transform=self.fig.transFigure,
                            edgecolor=MUTED, linewidth=0.6)
            self.fig.patches.append(bar)
            self.bars.append(bar)
        self.channel = self.fig.add_axes((0.615, 0.325, 0.35, 0.135), facecolor=BG)
        self.channel.set_axis_off()
        self.ticker = self.text(0.615, 0.28, "", 11, va="top", family="monospace")
        self.text(0.03, 0.062, DISCLAIMER, 12)
        attribution = "Open-Meteo CC BY 4.0"
        if payload["variant"] == "gauges" or self.gauge:
            attribution += " · Environment Agency OGL v3"
        self.text(0.03, 0.032, attribution, 11, colour=MUTED)
        self.overlay = Rectangle((0.02, 0.095), 0.96, 0.885, transform=self.fig.transFigure,
                                 facecolor=BG, zorder=50)
        self.fig.patches.append(self.overlay)
        self.card_heading = self.text(0.08, 0.84, "", 37, weight="bold", zorder=51)
        self.card_body = self.text(0.08, 0.71, "", 22, va="top", linespacing=1.7, zorder=51)

    def text(self, x, y, value, size, colour=INK, **kwargs):
        return self.fig.text(x, y, value, fontsize=size, color=colour, **kwargs)

    def card(self, end=False):
        self.fig.background_token = ("card", end)
        self.fig.draw_dynamic = False
        for artist in (self.overlay, self.card_heading, self.card_body):
            artist.set_visible(True)
        self.card_heading.set_text("Measured replay outcome" if end else "Climate Mesh / recorded replay")
        lines = [textwrap.fill(self.payload["title"], 65), "Variant: " + self.payload["variant"],
                 *outcome_text(self.payload)]
        self.card_body.set_text("\n".join(lines))

    def draw_channel(self, frame):
        ax = self.channel
        ax.clear()
        ax.set_axis_off()
        rows = frame.readings
        if self.payload["event_id"].startswith("flood"):
            ax.text(0, 1, "DRIVING CHANNEL / RAIN mm/h", color=MUTED, fontsize=12, va="top")
            if self.gauge:
                index = frame.hour_index
                observed = bool(self.gauge["readings_per_hour"][index])
                gauge = self.gauge["hourly_mm"][index] if observed else None
                grid = (self.grid_rain["nodes"][self.gauge["nearest_node"]]["precipitation"][index]
                        if self.grid_rain else None)
                maximum = max(1, max(self.gauge["hourly_mm"]),
                              max(self.grid_rain["nodes"][self.gauge["nearest_node"]]["precipitation"])
                              if self.grid_rain else 0)
                gauge_label = "EA gauge" if self.payload["variant"] == "gauges" else "EA reference"
                for y, label, value, colour in ((0.50, gauge_label, gauge, COLOURS["WARNING"]),
                                                 (0.13, "Grid", grid, COLOURS["SAFE"])):
                    ax.barh(y, (value or 0) / maximum * 0.55, left=0.2, height=0.16,
                            color=colour, edgecolor=MUTED, linewidth=0.5)
                    ax.text(0, y, label, color=INK, fontsize=12, va="center")
                    label_value = f"{value:g}" if value is not None else "unavailable"
                    ax.text(0.78, y, label_value, color=INK, fontsize=14, va="center")
                ax.text(0, 0.74, self.gauge["label"] + " / " + self.gauge["nearest_node"],
                        color=INK, fontsize=11)
                ax.set(xlim=(0, 1), ylim=(-0.15, 1.1))
            else:
                ax.text(0, 0.50, "Hourly rain is not retained in this replay JSON.", color=INK, fontsize=12)
        elif self.payload["event_id"].startswith("heat"):
            hottest = max(rows, key=lambda r: r["temperature"])
            ax.text(0, 0.90, "DRIVING CHANNEL / TEMPERATURE", color=MUTED, fontsize=12)
            ax.text(0, 0.42, f"{hottest['temperature']:g} °C", color=INK, fontsize=30, weight="bold")
            ax.text(0, 0.08, "Hottest recorded node: " + hottest["node_id"], color=INK, fontsize=12)
        else:
            windiest = max(rows, key=lambda r: r["wind_speed"])
            ax.text(0, 0.90, "DRIVING CHANNEL / SUSTAINED WIND + PRESSURE", color=MUTED, fontsize=12)
            ax.text(0, 0.42, f"{windiest['wind_speed']:g} m/s   {windiest['barometric_pressure']:g} hPa",
                    color=INK, fontsize=25, weight="bold")
            ax.text(0, 0.08, "Windiest recorded node: " + windiest["node_id"], color=INK, fontsize=12)

    def update(self, frame):
        self.fig.background_token = ("hour", frame.hour)
        self.fig.draw_dynamic = True
        for artist in (self.overlay, self.card_heading, self.card_body):
            artist.set_visible(False)
        rows = {r["node_id"]: r for r in frame.readings}
        sizes = np.array([90 + frame.visual_scores[n] * 5 for n in self.ids])
        self.markers.set_sizes(sizes)
        self.markers.set_facecolors([COLOURS[rows[n]["band"]] for n in self.ids])
        self.pulses.set_sizes(sizes + 1200 * frame.fraction)
        self.pulses.set_edgecolors([matplotlib.colors.to_rgba(
            INK, (1 - frame.fraction) if rows[n]["alert"] else 0) for n in self.ids])
        checking = [rows[n]["corroboration"] == "uncorroborated" for n in self.ids]
        self.checks.set_sizes(sizes + 260)
        self.checks.set_edgecolors([matplotlib.colors.to_rgba(INK, float(visible)) for visible in checking])
        for label, visible in zip(self.check_labels, checking):
            label.set_visible(visible)
        for label, visible in zip(self.node_labels, checking):
            label.set_visible(not visible)
        if self.last_hour != frame.hour:
            self.clock.set_text(clock_label(frame.hour, self.payload["timezone"]))
            for label, bar, row in zip(self.rank_labels, self.bars,
                                       sorted(frame.readings, key=lambda r: (-r["score"], r["node_id"]))[:5]):
                label.set_text(f"{row['node_id']}   {row['band']}   {row['score']:g}")
                bar.set_width(0.35 * row["score"] / 100)
                bar.set_facecolor(COLOURS[row["band"]])
            self.draw_channel(frame)
            self.ticker.set_text(alert_text(self.payload, frame.hour_index))
            self.last_hour = frame.hour


class CompactPillowWriter(animation.PillowWriter):
    """Palette frames keep GIF memory and size small; ffmpeg is never needed."""

    def grab_frame(self, **savefig_kwargs):
        super().grab_frame(**savefig_kwargs)
        self._frames[-1] = self._frames[-1].convert("RGB").quantize(
            colors=96, dither=Image.Dither.NONE)

    def finish(self):
        for colours in (96, 64, 32):
            if colours != 96:
                self._frames = [f.convert("RGB").quantize(colors=colours, dither=Image.Dither.NONE)
                                for f in self._frames]
            self._frames[0].save(self.outfile, save_all=True, append_images=self._frames[1:],
                                 duration=round(1000 / self.fps), loop=0, optimize=True, disposal=1)
            if Path(self.outfile).stat().st_size < 8_000_000:
                return
        raise RuntimeError(f"GIF exceeds 8 MB: {self.outfile}")


def render(payload, out, *, gauge_payload=None, grid_rain=None, formats=("mp4", "gif")):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for extension in formats:
        if extension == "mp4" and not animation.writers.is_available("ffmpeg"):
            print("ffmpeg unavailable: skipping MP4; GIF rendering remains available.")
            continue
        fps = 30 if extension == "mp4" else 10
        # 19.2–20 seconds of event time plus the two- and three-second cards.
        gif_frames_per_hour = max(1, round(200 / len(payload["per_hour"])))
        frames_per_hour = gif_frames_per_hour * (fps // 10)
        samples = list(generate_frames(payload, frames_per_hour))
        title_frames, end_frames = 2 * fps, 3 * fps
        figure = ReplayFigure(payload, gauge_payload, grid_rain)
        # Keep the animation canvas and writer at the same DPI, including GIF;
        # otherwise the two draw passes would invalidate each other's cache.
        dpi = 100 if extension == "mp4" else 50
        figure.fig.set_dpi(dpi)

        def update(index):
            if index < title_frames:
                figure.card()
            elif index >= title_frames + len(samples):
                figure.card(end=True)
            else:
                figure.update(samples[index - title_frames])
            return []

        movie = animation.FuncAnimation(figure.fig, update,
                                       frames=title_frames + len(samples) + end_frames,
                                       interval=1000 / fps, blit=False, cache_frame_data=False)
        path = out / f"{payload['event_id']}-{payload['variant']}.{extension}"
        writer = (animation.FFMpegWriter(fps=fps, codec="libx264", bitrate=2500,
                                        extra_args=["-pix_fmt", "yuv420p", "-threads", "2", "-movflags", "+faststart"])
                  if extension == "mp4" else CompactPillowWriter(fps=fps))
        try:
            movie.save(path, writer=writer, dpi=dpi)
        finally:
            plt.close(figure.fig)
        paths.append(path)
        print(f"Wrote {path}: {path.stat().st_size:,} bytes, {fps} fps, "
              f"{(title_frames + len(samples) + end_frames) / fps:g} s", flush=True)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replays", type=Path, default=ROOT / "evidence/replay")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/replay/animations")
    parser.add_argument("--event", help="optional single event ID")
    parser.add_argument("--variant", choices=("grid", "gauges"))
    parser.add_argument("--format", choices=("mp4", "gif", "both"), default="both")
    parser.add_argument("--ffmpeg", help="optional path to an installed ffmpeg executable")
    parser.add_argument("--grid-rain-fixtures", type=Path,
                        help="optional history directory: exact grid rain is absent from replay JSON")
    args = parser.parse_args()
    if args.ffmpeg:
        matplotlib.rcParams["animation.ffmpeg_path"] = args.ffmpeg
    payloads = [load_json(path) for path in replay_paths(args.replays)]
    if not payloads:
        parser.error("no event replay JSON outputs found")
    selected = [p for p in payloads if (not args.event or p["event_id"] == args.event)
                and (not args.variant or p["variant"] == args.variant)]
    if not selected:
        parser.error("no event replay matches the requested event/variant")
    for payload in selected:
        gauge = next((p for p in payloads if p["event_id"] == payload["event_id"]
                      and p["variant"] == "gauges"), None)
        rain = None
        if args.grid_rain_fixtures and payload["event_id"].startswith("flood"):
            base = args.grid_rain_fixtures / (payload["event_id"] + ".json")
            rain = load_json(base if base.exists() else Path(str(base) + ".gz"))
        render(payload, args.out, gauge_payload=gauge, grid_rain=rain,
               formats=("mp4", "gif") if args.format == "both" else (args.format,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
