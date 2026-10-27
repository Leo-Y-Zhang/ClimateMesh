# Recorded London event replay — verification report

Implemented with the live risk thresholds, multipliers, bands and mesh unchanged. All fixtures were fetched from the specified public APIs; no observation numbers were hand-entered. Changes are left in the working tree; no commit, push or git configuration change was made.

## Files changed

- `scripts/fetch_history.py`: public multi-coordinate grid/air fetches, raw historical training arrays, EA gauges, atomic writes and read-only comparison mode.
- `data/history/flood-2021-07-12.json`, `data/history/heat-2022-07-19.json`, `data/history/storm-2022-02-18.json`: fetched fixtures with provenance, licences and raw observations.
- `sensors/history_adapter.py`: canonical recorded readings, local-midnight cumulative rainfall and optional gauge overrides.
- `sensors/base.py`, `dashboard/badges.py`, `scripts/export_evidence.py`: archive provenance validation, badge and export meaning.
- `ai/anomaly_model.py`: share historical weather-variable constant and fitting implementation; offline raw-archive entry point uses the existing row builder and identical model settings.
- `simulation/replay.py`, `scripts/replay_event.py`: hourly production scoring/alert sequence in private SQLite, recorded clock, gauge selection and deterministic summaries.
- `scripts/replay_figures.py`, `requirements.txt`: matplotlib figures at 200 dpi using the dashboard colour-blind-safe palette.
- `evidence/replay/flood-2021-07-12-grid.json`, `evidence/replay/flood-2021-07-12-gauges.json`, `evidence/replay/heat-2022-07-19-grid.json`, `evidence/replay/storm-2022-02-18-grid.json`: generated per-hour readings, risk and summary tables.
- `evidence/replay/figures/flood-2021-07-12.png`, `evidence/replay/figures/heat-2022-07-19.png`, `evidence/replay/figures/storm-2022-02-18.png`: generated figures; all 34 gauges are shown, with both overridden nodes compared below.
- `dashboard/real_events.py`, `dashboard/app.py`: appended Real events tab using the existing map function and committed JSON, with missing-output guidance.
- `tests/test_history.py`: fixture, adapter, no-look-ahead, offline determinism, live-fit parity, gauge rules, alert cooldown, export and fetch-failure/check coverage.
- `tests/test_dashboard_app.py`, `tests/test_audit_regressions.py`, `tests/test_readings.py`: eight-tab expectations, archive source and recorded-tab rendering/fallback checks.
- `.gitignore`, `README.md`, `docs/replay_report.md`: retain replay artifacts for review; commands, measured numbers, limitations and current test count.

## Measured headlines

Numbers below are quoted from the generated replay JSON without changing their rounding. Alerts count sampled hourly cycles, not hypothetical three-second cycles.

| Event / variant | Peak score | Alerts by type | First-six-hours peak | First-six-hours AI-amplified node-hours | First-six-hours alerts |
|---|---:|---|---:|---:|---|
| flood-2021-07-12 / gauges | 100.0 | {'flood': 306, 'sensor-check': 4} | 99.1 | 88 | {'flood': 117} |
| flood-2021-07-12 / grid | 100.0 | {'flood': 306, 'sensor-check': 5} | 99.1 | 92 | {'flood': 119} |
| heat-2022-07-19 / grid | 100.0 | {'heatwave': 399, 'sensor-check': 5, 'smog': 142} | 59.7 | 72 | {} |
| storm-2022-02-18 / grid | 100.0 | {'flood': 12, 'storm': 232} | 76.2 | 76 | {'flood': 12, 'storm': 11} |

The flood quiet-hours behaviour is poor: scores reach 99.1, with 119 grid flood alerts and 117 gauge flood alerts in the first six hours. These are not evidence of accurate prediction. Heat also produces 142 smog alerts and five sensor-check alerts across the window; storm produces 12 flood alerts, all in its first six hours. AI amplification occurs in every event’s quiet-hours check. There are no independent per-hour truth labels here to turn these observations into a measured false-positive rate.

Damped nodes (these are all nodes receiving the uncorroborated multiplier at least once; some never reach an alert threshold):

- flood-2021-07-12 / gauges: BRIXTON, REGENTS-CANAL, RIVER-LEA, RIVER-WANDLE, THAMES-BARRIER, WIMBLEDON.
- flood-2021-07-12 / grid: BRIXTON, PUTNEY, REGENTS-CANAL, RICHMOND-PARK, RIVER-LEA, RIVER-WANDLE, THAMES-BARRIER.
- heat-2022-07-19 / grid: BRIXTON, DULWICH, RICHMOND-PARK, RIVER-WANDLE, THAMES-BARRIER.
- storm-2022-02-18 / grid: DULWICH, PUTNEY, RICHMOND-PARK.

Only two of 34 gauges qualify; all other gauges and their reasons remain in the JSON.

- Putney Heath → PUTNEY: total 47.24999999999998 mm, peak local-hour sum 33.239999999999995 mm at 2021-07-12T16:00, distance 1.4097932123405217 km.
- Wanstead → ILFORD: total 8.0 mm, peak local-hour sum 2.6 mm at 2021-07-12T17:00, distance 2.8970109027808504 km.

Holland Park’s 59.4 mm total is excluded because its readings are not all Good. Pinner Cemetery has 96 Missing records with absent rainfall values: these remain null, and its total and peak are unknown. At 2021-07-12T16:00, PUTNEY scores 82.7 with gauges versus 42.6 with grid rainfall; its full-window peak is 100.0 versus 95.0.

## Commands and output tails

Environment: Python 3.11.2, scikit-learn 1.9.1, NumPy 2.4.6, matplotlib 3.11.2, Streamlit 1.41.1. The system Python initially lacked pip; `python -m venv /work/.venv` supplied it. Dependencies were installed with `/work/.venv/bin/python -m pip install -r requirements.txt 'matplotlib>=3.8,<4' ruff`. No tests were claimed for unexecuted Python versions.

```bash
.venv/bin/python scripts/fetch_history.py
```

Exit 0. Output tail:

```text
flood-2021-07-12: wrote 24 hours, 20 nodes, 34 gauges to data/history/flood-2021-07-12.json
heat-2022-07-19: wrote 48 hours, 20 nodes, 0 gauges to data/history/heat-2022-07-19.json
storm-2022-02-18: wrote 24 hours, 20 nodes, 0 gauges to data/history/storm-2022-02-18.json
```

```bash
.venv/bin/python scripts/fetch_history.py --check
```

Exit 0. Output tail:

```text
flood-2021-07-12: unchanged
heat-2022-07-19: unchanged
storm-2022-02-18: unchanged
```

```bash
.venv/bin/python scripts/replay_event.py --all
```

Exit 0. Output tail:

```text
flood-2021-07-12 / grid: peak 100.0; alerts {'flood': 306, 'sensor-check': 5}; damped nodes ['BRIXTON', 'PUTNEY', 'REGENTS-CANAL', 'RICHMOND-PARK', 'RIVER-LEA', 'RIVER-WANDLE', 'THAMES-BARRIER']
  First 6 hours: peak 99.1, AI amplified 92 node-hours, alerts {'flood': 119}. Wrote evidence/replay/flood-2021-07-12-grid.json
flood-2021-07-12 / gauges: peak 100.0; alerts {'flood': 306, 'sensor-check': 4}; damped nodes ['BRIXTON', 'REGENTS-CANAL', 'RIVER-LEA', 'RIVER-WANDLE', 'THAMES-BARRIER', 'WIMBLEDON']
  First 6 hours: peak 99.1, AI amplified 88 node-hours, alerts {'flood': 117}. Wrote evidence/replay/flood-2021-07-12-gauges.json
  Rain gauges: 2 used, 32 excluded; all totals, distances and exclusion reasons are in the JSON.
  Putney Heath -> PUTNEY: 47.24999999999998 mm, peak 33.239999999999995 mm at 2021-07-12T16:00; 1.4097932123405217 km.
  Wanstead -> ILFORD: 8.0 mm, peak 2.6 mm at 2021-07-12T17:00; 2.8970109027808504 km.
heat-2022-07-19 / grid: peak 100.0; alerts {'heatwave': 399, 'sensor-check': 5, 'smog': 142}; damped nodes ['BRIXTON', 'DULWICH', 'RICHMOND-PARK', 'RIVER-WANDLE', 'THAMES-BARRIER']
  First 6 hours: peak 59.7, AI amplified 72 node-hours, alerts {}. Wrote evidence/replay/heat-2022-07-19-grid.json
storm-2022-02-18 / grid: peak 100.0; alerts {'flood': 12, 'storm': 232}; damped nodes ['DULWICH', 'PUTNEY', 'RICHMOND-PARK']
  First 6 hours: peak 76.2, AI amplified 76 node-hours, alerts {'flood': 12, 'storm': 11}. Wrote evidence/replay/storm-2022-02-18-grid.json
```

```bash
.venv/bin/python scripts/replay_figures.py
```

Exit 0. Output tail:

```text
Wrote evidence/replay/figures/heat-2022-07-19.png
Wrote evidence/replay/figures/storm-2022-02-18.png
Wrote evidence/replay/figures/flood-2021-07-12.png
```

```bash
source .venv/bin/activate
python -m pytest -q -o addopts=''
```

Exit 0. Output tail:

```text
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
.........................                                                [100%]
313 passed in 42.68s
```

```bash
.venv/bin/python -m pytest --collect-only -q -o addopts=''
```

Exit 0. Output tail:

```text

313 tests collected in 20.23s
```

```bash
source .venv/bin/activate
ruff check --select F,E9 .
```

Exit 0. Output tail:

```text
All checks passed!
```

`python -m pytest -q` (via `.venv/bin/python`) was also run before the final three fetch/fallback tests were added: exit 0, 310 tests completed. The final 313-test run above overrides the repository’s existing quiet addopts only to display the pass count. `ruff check --select F,E9 .` also ran directly earlier with “All checks passed!”. `git diff --check` exited 0 with no output. Heat and flood figure sections were visually inspected.

## Limits and outstanding work

No requested implementation work remains. No field validation or forecast claim is made. Gridded reanalysis at roughly 9–11 km smooths convective storms; nearby nodes may share a cell and are not independent instruments. Water level is a rainfall proxy. Gauge substitution within 3 km is a modelling choice; closest eligible gauge wins if several target one node. The UTC gauge day omits the first BST hour: empty sums are used by the override, but are explicitly counted as unobserved and left blank in figures; outside-window rainfall is separately reported. Training is exactly the preceding 720 hours, with raw UTC arrays sliced at local boundaries to prevent look-ahead. Historical training retains its hourly rain/urban water proxy, while event readings use cumulative daily rain and node-specific environments. That mismatch affects AI and is preserved. Wind scoring uses sustained wind, not archived gusts.

The replay clock advances one hour per sample, expiring the live 900-second alert cooldown; duplicate alerts in the same cycle are suppressed by the unchanged SQL-backed logic. No intermediate live cycles are invented. Byte-identical repeat output is tested in the same dependency environment; newer scikit-learn versions may change model results.
