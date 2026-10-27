# Recorded replay animations and evidence cards

Both tools run offline. Install the project's `requirements.txt` first; Pillow
is installed with matplotlib. Neither tool runs a replay, changes scoring or
rewrites recorded fixtures or replay JSON. README.md is maintained separately.

## Animate the event outputs

```bash
python scripts/replay_animation.py
python scripts/replay_animation.py --event flood-2021-07-12 --variant gauges
python scripts/replay_animation.py --format gif
```

Inputs default to the top level of `evidence/replay/`. Plain `.json` and gzip
`.json.gz` files are accepted; plain JSON wins if both represent the same output.
Only flood, heat and storm event outputs are selected, including both flood
variants. Held-out weeks and the `as-found/` archive are excluded.
Use `--replays DIRECTORY` and `--out DIRECTORY` to override the paths.

Outputs are `evidence/replay/animations/<event_id>-<variant>.mp4` and `.gif`.
MP4 uses H.264, 1920 × 1080, 30 fps. GIF uses 960 × 540, 10 fps and a compact
palette, checked against an 8,000,000-byte limit. The recorded events run for
about 24–25 seconds, including a two-second title and three-second outcome card.
The cards take all measured outcomes from the JSON summary.
An hourly raster cache keeps static text and basemap drawing out of the frame
loop; markers and pulse rings still redraw for every frame.

Matplotlib's `FuncAnimation` drives both writers. MP4 needs an installed ffmpeg
with `libx264`; use `--ffmpeg /path/to/ffmpeg` for a nonstandard installation.
If ffmpeg is unavailable, the script prints a skip message and still writes GIF.
An optional package that supplies a local executable is `imageio-ffmpeg`:

```bash
python scripts/replay_animation.py --ffmpeg "$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
```

The map ports the Live Map's exact waterway points, extent, aspect, label
positions and neighbour links into matplotlib. Its nodes are illustrative
locations, not deployed instruments. Marker sizes interpolate linearly; all
numbers, bands, rankings, channels and alert text hold the current recorded hour.
The clock uses Europe/London with the correct weekday and BST/GMT. Pulses last
the firing sample; dashed rings and `check sensor` denote uncorroborated nodes.
The ticker lists every alert at its latest firing hour, grouped by type. Alert
totals count sampled node-hours, not independent incidents.

Hourly grid rainfall is absent from replay JSON: it retains only an accumulated,
rounded and potentially capped water-level proxy. The default replay-only view
shows the gauge bars from the flood gauge replay's summary, and labels grid
rain unavailable. Missing gauge coverage is also labelled unavailable, never
zero. Both flood variants use the same gauge comparison for context; only the
gauges variant uses gauge rain for its engine scores. An explicit optional
`--grid-rain-fixtures data/history` supplies the exact recorded grid rainfall
for the comparison bars from the history fixture. This option never supplies
scores, alerts or outcomes and never attempts to invert the proxy.

The footer is visible through both cards and the event: recorded data, unchanged
engine, not a forecast or field validation; Open-Meteo CC BY 4.0 and Environment
Agency OGL v3 wherever gauge data is displayed.

## Measure and render the evidence cards

```bash
python scripts/evidence_card.py
python scripts/evidence_card.py --out evidence/replay/figures
```

Writes `evidence-card-dark.png` and `evidence-card-light.png`, each 2480 × 3508
pixels at 300 dpi, plus `evidence-card-numbers.json` with the measurements, date,
commit and fresh benchmark transcript. Twelve tiles show:

- Tests collected by `python -m pytest --collect-only -q`.
- Physical Python source lines, excluding tests, virtual environments and caches.
- Registry nodes, canonical measurement fields and supported source provenances.
- Unique recorded events, replay variant count and hours across variants. The
  footer also reports unique recorded event-hours, so the flood's two variants do
  not imply two different days of weather.
- Held-out real weeks (the 2023 development weeks and the untouched 2024 test
  weeks), and node-hours of recorded London scored: event replays plus held-out
  weeks, counted from the replay outputs.
- Unique gauge reference/label pairs fetched and used, from the replay reports
  (labels disambiguate stations without a reference).
- Synthetic evaluation frames imported from `scripts.evaluate`'s shared inventory
  (quiet + stuck-sensor + intensity/scenario frames; configurations reuse frames).
- The median reported by a fresh `scripts/pi_benchmark.py` subprocess, labelled
  with this machine's `platform.platform()` string and actual cycle count.

The benchmark uses a disposable database under `.tmp/`, never the dashboard
database. Both themes share the same fresh measurements. The git hash identifies
the base commit and is explicitly labelled as a working tree; it does not imply
that uncommitted changes belong to that commit. Collection requires a working
pytest environment and fails visibly if collection or benchmarking fails.

## Verification

```bash
python -m pytest -q tests/test_replay_media.py
python -m pytest -q
ruff check --select F,E9 .
```

The presentation tests use committed replay outputs, small in-memory frame
sequences and monkeypatched measurement functions. They do not fetch weather,
run the benchmark or encode full videos.
