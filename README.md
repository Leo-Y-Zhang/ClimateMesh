# 🌍 Climate Mesh

**Decentralised climate monitoring & AI-powered early-warning mesh — runs on a Raspberry Pi 5.**

**The problem.** Flood and heat warnings fail exactly where they matter: the
nearest official flood gauge can be kilometres from the stream that actually
overflows, so by the time a warning reaches a community, the water is already
rising. There is a gap between where climate events happen and where they are
measured.

**The solution.** Climate Mesh is a network of 20 environmental "nodes" across
Greater London. It scores each location's climate risk 0–100 in real
time, uses an explainable AI anomaly model plus *mesh correlation* (nearby
nodes confirming a trend) to escalate genuine events, and raises plain-English
alerts with community action playbooks — all on a single Raspberry Pi, offline,
with no cloud subscription.

**What is genuinely novel here.**

- **A canonical reading contract:** physical sensor, live API, and simulation
  all emit the *same* reading shape, so the system is **sensor-ready without
  being sensor-dependent** — a real node joins the mesh by adding one adapter,
  and nothing downstream changes.
- **Mesh agreement as a two-sided trust signal:** a 1.2× escalation fires
  only when **2+ adjacent nodes** agree for the same hazard, and a node that
  is elevated while *no* neighbour agrees is damped (0.75×) and reported as a
  **sensor-check**, not as the hazard — so a single glitching node cannot cry
  wolf. Both directions are tested (`tests/test_corroboration.py`).
- **Provenance-first honesty:** every reading, dashboard panel, alert, and
  export carries its data source (`hardware / api / demo / simulation / archive`) and a
  quality flag — honesty is a designed-in feature, not a disclaimer.
- **One-command reproducibility:** judges can prove the whole system works
  from a clean clone with a single command.

**Measured results** *(from this repo's deterministic simulation/demo pipeline —
not field measurements; no physical sensor has been validated yet)*:

- **313/313 automated tests pass** on Python 3.11 in the recorded-event verification. The project also provides CI for Python 3.11/3.13 and 64-bit Arm Linux, plus `python scripts/judge_validate.py`.
- The demo tour (`python scripts/demo_tour.py`, a few seconds) discriminates
  correctly across scenarios: **normal stays SAFE** (avg risk 3.9, 0 alerts)
  while **flood escalates the right nodes** (Regent's Canal → CRITICAL
  100.0, 10 alerts), and heatwave/smog/storm each escalate their own hazard
  profile. Output is deterministic — repeated runs print identical numbers.
- Runs fully offline on any computer or a Raspberry Pi 5.

> **Honest by design — sensor-ready, not sensor-dependent.**
> Physical sensor support is hardware-ready but **not required** for the current
> demo. Until sensors are connected, Climate Mesh uses clearly-labelled
> **simulated** and/or **live API** data. Every reading shows its source
> (`simulation` / `demo` / `api` / `hardware` / `archive`) so nothing is ever overstated.

Built by a team of two sixth-form students (years 12–13
category), for the PA Raspberry Pi Competition 2026/27 — theme *Building a
Positive Human Future* (Safer Societies & Sustainable World).

---

## The dashboard

A 8-tab Streamlit dashboard reads the same SQLite database the engine writes:

- **Live Map** — the 20 nodes on a Greater London map, coloured by band and
  sized by risk score, with the mesh links between neighbours and a
  provenance badge on hover. It draws its own basemap, so it needs no internet.
- **Network Overview** — average risk, highest-risk node, active alerts, and
  risk-by-node / risk-distribution charts.
- **Node Detail** — one node's readings, its six risk sub-scores, and a
  10-minute history.
- **AI Explainability** — which nodes the Isolation Forest flagged and why,
  plus the anomaly-score distribution.
- **Evidence & Validation** — run metadata, row counts, and the export commands.
- **Hardware Readiness** — live driver/device detection, with provenance
  derived from actual data, never from a library merely being importable.
- **Competition Pitch** — the summary pitch.
- **Real events** — committed hourly London event replays, separate from the live database.

Every panel carries its data source and a quality flag, which is the point: in
demo mode the badges read *Digital Twin (Demo)*, so nothing is passed off as a
real measurement. See it yourself from a clean clone:

```bash
python run.py --mode demo --scenario flood --judge-mode   # terminal 1
python -m streamlit run dashboard/app.py                  # terminal 2, opens http://localhost:8501
```

## What works right now

- ✅ 20 named Greater London nodes on a live risk map (an illustrative layout
  of well-known public landmarks — see `config/nodes.py`; no node marks a
  deployed sensor).
- ✅ Five demo scenarios: **normal, flood, heatwave, smog, storm**.
- ✅ 0–100 risk scores with **SAFE / MODERATE / WARNING / CRITICAL** levels.
- ✅ Explainable AI (Isolation Forest) + **mesh correlation** across adjacent nodes.
- ✅ Plain-English alerts with **community action playbooks**.
- ✅ A 8-tab Streamlit dashboard with **source + quality badges on every panel**.
- ✅ Reproducible **evidence export** (CSV + JSON) with a **data-source summary table**.
- ✅ `pytest` test suite and a **one-command judge validation** (`scripts/judge_validate.py`).
- ✅ Runs **fully offline, with no sensors**, on a Raspberry Pi 5.

### One command for judges

```bash
python scripts/judge_validate.py
```

Runs the smoke test, the full `pytest` suite, a normal demo cycle, a flood demo
cycle, and the evidence export, then prints a compact PASS/FAIL table you can
screenshot. Exit code is non-zero if anything fails.

### See it work in 30 seconds (no hardware, no internet)

```bash
python scripts/demo_tour.py
```

Runs one deterministic cycle of **all five scenarios** against an isolated
throwaway database and prints a per-scenario summary. Real observed output:

```
==============================================================================
  Climate Mesh - Demo Tour (deterministic, synthetic data, no hardware)
==============================================================================
  Scenario     Avg   Max  Worst node             Level     Alerts
------------------------------------------------------------------------------
  normal       3.9  11.4  Greenwich              SAFE           0
  flood       50.8 100.0  Regent's Canal (Little Venice) CRITICAL      10
  heatwave    78.8 100.0  Brixton                CRITICAL      12
  smog        82.7 100.0  Brixton                CRITICAL      15
  storm       98.1 100.0  Brixton                CRITICAL      20
------------------------------------------------------------------------------
  Risk is 0-100. Every reading above is source=demo, is_simulated=True.
==============================================================================

  Sample explanation (flood, Regent's Canal (Little Venice)):
    Flood risk rising near Regent's Canal (Little Venice). Same trend seen across 3 nearby nodes. Risk score 100/100. Main contributors: critical water level (4.8 m), very high humidity (99%), falling pressure (996 hPa).

  RESULT: PASS (5/5 scenarios, deterministic, offline)
```

Normal conditions stay quiet; each emergency escalates the nodes its hazard
should hit — and every line self-labels as simulation.

## What is simulated vs real

| Mode | Data source | Internet? | Sensors? |
|------|-------------|-----------|----------|
| `simulation` | Realistic generated data (default) | No | No |
| `demo` | Deterministic, screenshot-stable data | No | No |
| `api` | **Live Open-Meteo** weather + air quality | Yes (falls back to simulation) | No |
| `hardware` | **Physical Vernier sensor** for one node, simulated mesh for the rest | No | Yes (falls back if absent) |
| `auto` | Detect hardware → else API → else simulation | Optional | Optional |

## What happens when physical sensors are added

The architecture is **sensor-ready**: every data source emits the *same* canonical
reading shape, so the risk engine, AI, dashboard, and database never change. When a
Vernier Go Direct Weather sensor is connected over USB, that node switches to
`source="hardware"` and its real readings are compared against the simulated/API
"digital twin" for the same location. See
[docs/hardware_integration_plan.md](docs/hardware_integration_plan.md).

---

## Quick start (any computer)

**Prerequisites:** Python **3.11, 3.12 or 3.13** and `git`. The recorded-event
replay and current 313-test suite were verified here on Python 3.11.2.
CI runs 3.11 (what Raspberry Pi OS Bookworm
ships) and 3.13 (what the Trixie-based release ships) on x86-64, plus 3.11 on
a 64-bit Arm runner that installs prebuilt wheels only. Nothing else is needed
— no compiler, database, solver, cloud account or API key. Every requirement
publishes a prebuilt wheel for Linux, Windows and macOS, so the install needs
no build toolchain, and the demo runs entirely offline. The recorded-event workflow targets Python 3.11+. The download is dominated by scikit-learn, pandas and
numpy.

> **Got this as a zip?** Unzip it and `cd` into the folder — skip the
> `git clone` line below. Everything else is identical.

```bash
git clone https://github.com/Leo-Y-Zhang/ClimateMesh.git
cd ClimateMesh

python3 -m venv .venv              # Windows: py -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# Sanity check (no sensors / no internet needed)
python scripts/smoke_test.py
pytest
```

`pytest` is installed by `requirements.txt` — there is no separate dev-extras
step. One command runs everything a reviewer needs:

```bash
python scripts/judge_validate.py   # smoke test + all 313 tests + 2 demo cycles + export
python scripts/evaluate.py         # detection and false-alarm rates vs a thresholds-only baseline
```

**One-click (Windows):** double-click **`start.bat`** — it installs deps, starts the
deterministic demo engine, and opens the dashboard automatically. Pick scenarios
from the sidebar. (Or run the two terminals manually below.)

**Run the demo — two terminals:**

```bash
# Terminal 1 — engine (best mode for screenshots/video)
python run.py --mode demo --scenario flood --judge-mode

# Terminal 2 — dashboard
python -m streamlit run dashboard/app.py
```

Then open the local Streamlit URL it prints (usually <http://localhost:8501>).

## Raspberry Pi 5 setup

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip
git clone https://github.com/Leo-Y-Zhang/ClimateMesh.git
cd ClimateMesh

# One-command setup (creates .venv, installs deps, runs smoke test)
chmod +x setup_pi.sh && ./setup_pi.sh
```

Or do it manually with the Quick start steps above. Physical sensors are **not**
required — the demo runs on simulation. To connect a real Vernier Go Direct
Weather sensor later, follow [docs/hardware_driver_setup.md](docs/hardware_driver_setup.md)
(it covers the exact `godirect` + `gdx` install and a "sensor not detected"
troubleshooting guide).

The dashboard has no login, so it listens on `127.0.0.1` only and is never put
on the LAN. To watch it from a laptop, forward the port over SSH:

```bash
ssh -L 8501:localhost:8501 pi@<host>
```

then open <http://localhost:8501> on the laptop.

## Run commands

```bash
python run.py --mode simulation                         # offline, default
python run.py --mode demo --scenario normal             # deterministic demo
python run.py --mode demo --scenario flood   --judge-mode
python run.py --mode demo --scenario heatwave --judge-mode
python run.py --mode demo --scenario smog    --judge-mode
python run.py --mode demo --scenario storm   --judge-mode
python run.py --mode api                                # live Open-Meteo data
python run.py --mode hardware                           # physical sensor (falls back)
python run.py --mode auto                               # detect hardware/API/sim
python run.py --mode demo --scenario flood --once       # one cycle, for CI
python run.py --mode api --ai-training historical       # train AI on real ERA5 archive
```

The `--ai-training` flag selects the anomaly model's training data:
`synthetic` (default, offline), `historical` (real Open-Meteo ERA5 archive), or
`auto` (historical with a deterministic synthetic fallback when offline).

Scenarios can also be switched live from the dashboard sidebar while the engine
runs — in every mode, `--judge-mode` included (judge mode freezes the simulation
clock so each scenario shows the same deterministic frame; it does not lock the
picker). In `simulation` mode, `--judge-mode` switches to the same seeded
generator as `demo`, so "screenshot-stable" is exactly what you get.

## Replaying real London events

The repository includes public recorded fixtures in `data/history/`, four replay
JSON files in `evidence/replay/`, and three figures in `evidence/replay/figures/`.
The appended **Real events** dashboard tab reads those JSON files, independently
of the live database. Every recorded reading carries `source="archive"`, badge
**Recorded (archive)**, `quality_flag="estimated"` and `is_simulated=True` (the
existing contract defines everything except physical hardware as simulated).

```bash
# Network required only to fetch/recheck public fixtures; no generated numbers:
python scripts/fetch_history.py
python scripts/fetch_history.py --check  # ignores retrieved_utc only; exits 1 on differences

# Offline, deterministic, uses only the committed fixtures:
python scripts/replay_event.py --all
python scripts/replay_event.py --event flood-2021-07-12 --variant gauges
python scripts/replay_event.py --event heat-2022-07-19 --out evidence/replay
python scripts/replay_figures.py
python -m streamlit run dashboard/app.py
```

Weather and air-quality arrays come from the Open-Meteo archive and air-quality
APIs (**CC BY 4.0**, **Weather data by Open-Meteo.com**). Flood gauges come from
the Environment Agency Hydrology API (**Open Government Licence v3.0**,
**Contains Environment Agency data**). Each fixture records the exact request
URLs, licences, attributions and UTC retrieval times. Null AQI stays null in the
fixture and uses the live adapter's 50.0 fallback in canonical readings.
Missing EA rainfall values remain null; unknown totals and peaks are reported
as null, with available subtotals and missing-record counts alongside them.
No station without readings is included.

Each event fits the existing Isolation Forest (120 trees, contamination 0.05,
random state 42) on the preceding 30 local dates, using the historical path's
single London location, UTC requests, variables, m/s units and
`_rows_from_archive`. Raw UTC arrays are sliced at local-day boundaries to
retain exactly 720 hours without including the event's local midnight. The
same scaler, feature baselines, risk engine, mesh adjacency, `maybe_alert` and
`alert_type_for` run unchanged. The historical training water proxy uses hourly
rain, as before; the recorded adapter accumulates rain since local midnight.
That mismatch is preserved and can affect AI anomaly decisions.

Replay uses a private in-memory SQLite database and one engine cycle per
recorded hour. The database clock follows that hour's UTC instant, so the live
900-second cooldown expires between hourly cycles; same-cycle duplicates are
still suppressed. Alert counts are counts at these sampled hours, not inferred
counts from continuously running the three-second live loop. The JSON includes
all per-hour readings and risk fields, observed first membership in each band,
node peaks, alert types, damped nodes, and scores for the first six hours.

Measured results from the included outputs (values quoted exactly):

| Event / variant | Peak score | Alerts by type | First-six-hours peak | AI-amplified node-hours in first six |
|---|---:|---|---:|---:|
| Flood / grid | 100.0 | flood: 306; sensor-check: 5 | 99.1 | 92 |
| Flood / gauges | 100.0 | flood: 306; sensor-check: 4 | 99.1 | 88 |
| Heat / grid | 100.0 | heatwave: 399; sensor-check: 5; smog: 142 | 59.7 | 72 |
| Storm / grid | 100.0 | flood: 12; storm: 232 | 76.2 | 76 |

The quiet-hours check is poor for the flood: the first six hours already raise
119 flood alerts on grid data and 117 with gauge substitution. The storm's
first six hours raise 12 flood and 11 storm alerts; heat's first six raise none,
even though AI amplifies 72 node-hours. These are retrospective scores, without
independent per-hour ground-truth labels; they do not establish alert accuracy.
The AI can amplify quiet-period readings, and the mesh can agree on the same
misleading humidity-driven flood signal.

Only two of 34 returned gauges qualify: Putney Heath substitutes PUTNEY and
Wanstead substitutes ILFORD. Putney Heath's recorded UTC-day total is
47.24999999999998 mm and its peak local-hour sum is 33.239999999999995 mm at
2021-07-12T16:00; Wanstead's total is 8.0 mm and peak is 2.6 mm at
2021-07-12T17:00. At 2021-07-12T16:00, PUTNEY scores 82.7 with gauges versus
42.6 on the grid; its full-window peak is 100.0 versus 95.0. The larger
Holland Park total, 59.4 mm, is excluded because
its readings are not all Good. No quality exception is made to obtain a more
dramatic result. All exclusions, distances and hourly coverage counts are in
the gauges replay JSON. If several qualifying gauges map to one node, the
closest wins (stable label/reference tie break), without blending totals.
The requested UTC gauge day omits local 00:00–00:59 during BST and includes an
hour after the local event ends. Empty local-hour buckets sum to zero for the
override, **not measured dryness**; figures leave those gaps blank. Outside-window
rainfall is separately reported. Pinner Cemetery's 96 Missing records have no
rain values, so its total and peak are unknown and it is excluded.

Sensor-check damping also happens on real recorded inputs. Flood/grid damps
BRIXTON, PUTNEY, REGENTS-CANAL, RICHMOND-PARK, RIVER-LEA, RIVER-WANDLE and
THAMES-BARRIER; flood/gauges damps BRIXTON, REGENTS-CANAL, RIVER-LEA,
RIVER-WANDLE, THAMES-BARRIER and WIMBLEDON. Heat damps BRIXTON, DULWICH,
RICHMOND-PARK, RIVER-WANDLE and THAMES-BARRIER; storm damps DULWICH, PUTNEY
and RICHMOND-PARK. A damped node need not remain above the alert threshold.

**Limitations:** gridded reanalysis at roughly **9–11 km smooths convective
storms**; neighbouring nodes can share grid cells, so mesh agreement is not
independent sensor corroboration. **Water level is still a rainfall proxy**,
not measured river depth. **Gauge-to-node substitution within 3 km is a modelling
choice**, not proof that rainfall was identical at the node. The risk engine
uses sustained wind, not archived gusts. This is **not a forecast and not a
field validation**. Saturating at 100.0, early flood alerts and sensor-check
damping are findings of the unchanged model, not evidence that it predicted
these disasters correctly. Repeat-byte determinism is checked within the same
Python/scikit-learn environment; dependency upgrades may change forest results.

## Screenshots

Captured from this exact tree in **demo / judge mode** (flood scenario unless
stated). Every panel self-labels its data source — here **🎬 Digital Twin
(Demo)** — so nothing is passed off as a real measurement. The full set,
including the terminal evidence, is in [`docs/screenshots/`](docs/screenshots/).

| | |
|---|---|
| **Live Map (flood)** — the 20 nodes coloured by band and sized by risk, on the tile-free **Offline basemap**: grey lines are the mesh links between neighbours, blue lines the waterways | **Live Map (heatwave)** — after clicking *Heatwave* in the sidebar: the urban nodes light up instead of the river nodes |
| ![Live Map, flood, demo data, offline basemap](docs/screenshots/live-map-flood-demo.png) | ![Live Map, heatwave, demo data, offline basemap](docs/screenshots/live-map-heatwave-demo.png) |
| **Network Overview** — fleet risk, highest node, active alerts, risk-by-node and distribution charts | **Node Detail** — Regent's Canal: readings, provenance badges, the plain-English *Why:* line and the six sub-scores |
| ![Network Overview, flood, demo data](docs/screenshots/network-overview-flood-demo.png) | ![Node Detail, flood, demo data](docs/screenshots/node-detail-flood-demo.png) |
| **AI Explainability** — which nodes the Isolation Forest flagged and why | **Hardware Readiness** — honest "no physical sensor detected" state |
| ![AI Explainability, flood, demo data](docs/screenshots/ai-explainability-flood-demo.png) | ![Hardware Readiness, demo data](docs/screenshots/hardware-readiness-flood-demo.png) |
| **Evidence & Validation** — run metadata, row counts, export commands | **Competition Pitch** |
| ![Evidence and Validation, demo data](docs/screenshots/evidence-validation-flood-demo.png) | ![Competition Pitch](docs/screenshots/competition-pitch-flood-demo.png) |
| **Network Overview after clicking *Heatwave* in the sidebar** — live scenario switching | **`python scripts/judge_validate.py`** — the one-command PASS table |
| ![Network Overview, heatwave, demo data](docs/screenshots/network-overview-heatwave-demo.png) | ![judge_validate.py terminal output](docs/screenshots/terminal-judge_validate.png) |

Terminal evidence for `demo_tour.py`, `pytest`, `smoke_test.py` and
`test_hardware_read.py` (FALLBACK SIMULATION, no sensor attached) is in the
same folder. With internet, untick **Offline basemap** and the same nodes sit
on a street map.

### What the screenshots show (and how to retake them)

The dashboard's 8 tabs are all screenshot-worthy — see
[docs/evidence_checklist.md](docs/evidence_checklist.md). In short:
**Live Map** (risk-coloured London nodes), **Network Overview** (KPIs + charts),
**Node Detail** (per-node readings, source/quality badges, risk breakdown), **AI
Explainability**, **Evidence & Validation**, **Hardware Readiness**, **Competition
Pitch**, and **Real events**. Every panel carries a provenance badge — **📡 Physical Sensor**, **🌐 Live
API**, **🎬 Digital Twin (Demo)**, **💻 Offline Simulation** or **Recorded (archive)** — plus a quality
badge (✅ ok · ≈ estimated · 🕒 stale · ⚠️ missing), so each shot self-labels its
data source. Two terminal screenshots round out the evidence:

- `python scripts/judge_validate.py` → the compact PASS/FAIL validation table.
- `python scripts/test_hardware_read.py` → **REAL HARDWARE** vs **FALLBACK
  SIMULATION** proof for the physical node path.

---

## Architecture

Every data source emits the **same canonical reading**, which flows through one
pipeline into SQLite (the message bus) and out to the dashboard, alerts, and
evidence export:

```mermaid
flowchart TD
    HW["📡 Physical Sensor<br/>(Vernier GDX-WTHR)"]
    API["🌐 Live API<br/>(Open-Meteo)"]
    DT["🎬 Digital Twin / Demo<br/>+ 💻 Offline Simulation"]

    HW --> CR["Canonical reading<br/>(one fixed shape + source + quality_flag)"]
    API --> CR
    DT --> CR

    CR --> DB[("SQLite (WAL)<br/>message bus")]
    DB --> AI["AI anomaly model<br/>(Isolation Forest)"]
    DB --> RE["Risk engine<br/>6 sub-scores → 0–100<br/>× AI × mesh correlation"]
    AI --> RE
    RE --> DASH["Streamlit dashboard<br/>(8 tabs, source/quality badges)"]
    RE --> ALERT["Alerts + community<br/>action playbooks"]
    DASH --> EV["Evidence export<br/>(CSV + JSON + source table)"]
    ALERT --> EV
```

<details><summary>Text fallback (if Mermaid doesn't render)</summary>

```
Sensor / API / Digital-Twin → canonical reading → SQLite
   → AI anomaly model + risk engine → dashboard → alert/playbook → evidence export
```

</details>

## File structure

```
ClimateMesh/
  run.py                     # launcher: modes, scenarios, judge-mode, --once
  config/nodes.py            # 20 named London nodes + mesh neighbour map
  sensors/
    base.py                  # canonical reading shape + adapter base class
    simulated_adapter.py     # offline / demo data
    api_adapter.py           # live Open-Meteo data (falls back if offline)
    vernier_adapter.py       # physical Vernier sensor (falls back if absent)
    hardware_status.py       # sensor detection (never crashes)
  simulation/
    engine.py                # data generation: daily cycle, noise, scenarios
    scenarios.py             # flood / heatwave / smog / storm deltas
  ai/anomaly_model.py        # explainable Isolation Forest
  backend/
    risk_engine.py           # explainable scoring + mesh correlation + alerts
    playbooks.py             # community action playbooks per hazard
  data/database.py           # SQLite storage (readings, risk, alerts, runs)
  dashboard/app.py           # 8-tab Streamlit dashboard
  dashboard/offline_map.py   # tile-free Live Map: nodes, mesh links, waterways (pure, unit-tested)
  dashboard/badges.py        # provenance + quality badge wording (pure, unit-tested)
  data/sensor_config.json    # optional: which node the physical sensor represents
  scripts/
    judge_validate.py        # ONE command: smoke + pytest + demos + export + table
    demo_tour.py             # ONE command: all 5 scenarios, deterministic summary table
    test_hardware_read.py    # safe one-shot Vernier read: REAL HARDWARE vs FALLBACK
    reset_demo_db.py         # wipe DB to a clean state
    export_evidence.py       # CSV + JSON evidence export + source-count table
    run_validation.py        # one-command pass/fail validation
    smoke_test.py            # fast end-to-end check
    pi_benchmark.py          # measures cycle time + memory on this machine, prints a sentence
  tests/                     # pytest suite
  docs/                      # hardware driver setup, integration plan, evidence checklist, screenshots
```

## Known limitations (honest by design)

We label exactly what this is and is not, so judges never have to guess:

- **The node layout is illustrative.** The 20 demo nodes sit at well-known
  Greater London public landmarks, chosen to exercise the environment types
  the layout uses (river, residential, urban, park) and the mesh-neighbour logic (`config/nodes.py`). They are not deployment
  sites, and no reading in this repository was measured at any of them.
- **One physical node, only when connected.** Hardware support is implemented and
  tested end to end with a stand-in device object that mimics Vernier's helper
  (`tests/test_hardware_stand_in_device.py`; see `sensors/vernier_adapter.py`,
  `docs/hardware_driver_setup.md`), but **not yet validated against a physical
  device**. A node emits `source="hardware"` **only** after a Vernier device
  actually opens and is read. With no device attached, that node falls back to
  clearly-labelled simulation (`quality_flag="missing"`). Verify with
  `python scripts/test_hardware_read.py`.
- **Hardware mode never measures air quality or water level.** The GDX-WTHR senses
  temperature, humidity, wind and pressure only — it does **not** sense air quality
  or water level. In `hardware` mode those two channels are conservative
  placeholders, so the whole reading is flagged `quality_flag="estimated"` (never
  `"ok"`): a `hardware`/`ok` label must never cover a non-measured channel.
- **API water level is a proxy, not a river gauge.** In `api`/historical modes the
  `water_level` channel is derived from precipitation, so it is flagged
  `quality_flag="estimated"` — it is an indicator, not a measured gauge reading.
- **Emergency scenarios are simulated for safe judging.** Flood / heatwave / smog /
  storm apply calibrated deltas **in simulation and demo modes only**
  (`simulation/engine.py`). In `api`/`hardware` modes the live values are shown
  **unmodified** — the scenario is recorded as a label (`scenario="observed"`),
  not applied as a delta. The scenarios are labelled demo / digital-twin, never
  real events, and never overwrite real values with invented ones silently.
- **The AI is anomaly *support*, not an official warning.** The Isolation Forest
  flags unusual combinations to escalate risk and explain *why*; it is a
  decision-support signal, not an accredited meteorological warning system.

## Safety & privacy

- **No personal data.** The system stores environmental measurements only —
  no names, accounts, cameras, microphones, or location tracking of people.
- **Local-first.** Everything runs on the local machine/Pi; nothing is
  uploaded anywhere. The only outbound calls are the *optional* `api` /
  `historical` modes fetching public Open-Meteo weather data (no API key, no
  account), and they fall back to offline simulation.
- **Not an official warning system.** Alerts are decision support for a
  community; they advise practical low-risk actions and always defer to
  official emergency guidance.
- **Safe demos.** Emergency scenarios are simulated and labelled as such —
  judging never depends on (or misrepresents) a real emergency.

## How the AI works

`ai/anomaly_model.py` trains an **Isolation Forest** with two honest, selectable
training paths (`run.py --ai-training ...`):

- **`synthetic` (default):** 2000 deterministic synthetic *normal* samples — no
  internet, used by CI, the smoke test, and `--once`. Fully reproducible.
- **`historical` / `auto`:** ~30 days of **real** hourly Open-Meteo *archive*
  (ERA5) weather + air quality for one representative central-London point
  (the CENTRAL-LDN node). The first fetch is
  cached to `ai/_archive_cache.json`, so repeat runs train offline. If the
  archive is unreachable it **falls back deterministically to synthetic** and
  records that as `training_mode = "synthetic_fallback"` — synthetic data is
  never silently presented as historical.

The active `training_mode` is recorded in the run metadata, shown on the
dashboard's **AI Explainability** tab, and printed when training. For each
reading the model returns an anomaly score (0–1), whether it is anomalous, and
the channels deviating most from the **fitted** baseline. Unlike fixed
thresholds, it flags an unusual **combination** of values *before* any single
channel crosses a hard limit. A confirmed anomaly multiplies a node's risk by up
to **1.5×** (measured range 1.25×–1.36×).

## How the risk score works

For each node the engine computes six 0–100 hazard sub-scores — temperature,
humidity, air quality, water level, wind, pressure — and combines them
(worst hazard + 20% of the rest) into a 0–100 **base score**. Temperature and
humidity are two-sided: a frosty morning is filed as a **cold** hazard with its
own playbook, never as a "heatwave". It then applies:

- **AI multiplier** (design ceiling 1.5×; measured range 1.25×–1.36× once the
  Isolation Forest confirms an anomaly, and exactly 1.0× otherwise), and
- **Mesh multiplier** (1.2×) when **2+ adjacent nodes** show the same trend — a
  single spike is trusted less than a correlated regional event.

| Score | Level | Meaning |
|------:|-------|---------|
| 0–30  | SAFE | Within normal baseline |
| 30–60 | MODERATE | One factor drifting; advisory |
| 60–80 | WARNING | Confirmed anomaly on a node / correlated moderate readings |
| 80–100 | CRITICAL | Correlated anomaly across adjacent nodes |

Example alert (from the deterministic flood demo):
> *Flood risk rising near Regent's Canal (Little Venice). Same trend seen across
> 3 nearby nodes. Risk score 100/100. Main contributors: critical water level
> (4.8 m), very high humidity (99%), falling pressure (996 hPa).*
> **Suggested actions:** check and clear nearby drains; inspect low-lying paths;
> review the evacuation route.

## How to export evidence

```bash
# After running a demo for a little while:
python scripts/export_evidence.py
# -> evidence/readings.csv, risk_scores.csv, alerts.csv, source_summary.csv, run_summary.json
```

Each row keeps its `source` and `quality_flag`, so simulated/API/hardware data is
never confused. See [docs/evidence_checklist.md](docs/evidence_checklist.md).

## Troubleshooting

- **Dashboard says "No data yet"** → start the engine in another terminal:
  `python run.py --mode demo --scenario flood --judge-mode`.
- **`api` mode shows a fallback note** → no internet; it automatically uses
  simulation. This is expected and clearly labelled.
- **Map doesn't render** → the bundled Streamlit/Plotly versions use free
  OpenStreetMap-based tiles (no API key). Ensure `pip install -r requirements.txt`
  completed. The street tiles are the one thing that needs internet, so the
  **Offline basemap** in the sidebar is ticked by default: the Live Map draws
  the 20 labelled nodes, the mesh links between neighbours and the Thames, Lea,
  Wandle and Regent's Canal, fully offline. Untick it for street tiles.
- **`pytest: command not found`** → use `python -m pytest`.
- **Reset everything** → `python scripts/reset_demo_db.py`.

## Competition notes

Climate Mesh was built for the PA Raspberry Pi Competition 2026/27. Its
competition strengths: an **evidence mode** for reproducible judging,
**explainable alerts**, a **sensor-ready-without-sensors** pipeline, **community
action playbooks**, **mesh correlation**, a **local digital twin**, and
**offline-first** operation.

## Tests

```bash
python scripts/judge_validate.py     # one command: smoke + pytest + demos + export
python scripts/demo_tour.py          # one command: all 5 scenarios, deterministic
pytest                               # the full unit-test suite (313 tests)
python scripts/smoke_test.py
python scripts/run_validation.py --mode demo --scenario flood
python scripts/test_hardware_read.py # REAL HARDWARE vs FALLBACK SIMULATION
python scripts/pi_benchmark.py       # cycle time, training time, peak memory on this machine
```

## Roadmap

In priority order — each item is *not done yet* until it is moved into the
sections above with evidence:

1. **Validate one physical node.** Read a real Vernier GDX-WTHR through the
   existing adapter and compare it against the digital twin for the same
   location (`scripts/test_hardware_read.py` is the entry point).
2. **Calibrate against history.** Use the evidence export to compare risk
   scores with recorded local flood/heat events, and tune thresholds from
   data instead of by hand.
3. **Physical mesh links.** Two or more real Pi nodes exchanging readings
   (Wi-Fi first, LoRa later) so mesh correlation runs across actual devices.
4. **Node cost pack.** A priced, tested bill of materials for a minimal
   community node — published only once a real node has run on it.

## Credits

Built by a team of two sixth-form students.

## Licence

MIT; the copyright notice is in [LICENSE](LICENSE). Anyone may run,
study, copy and adapt it, with attribution.
