# Climate Mesh — Competition Evidence Checklist

A step-by-step, tickable checklist for capturing competition evidence on the
Raspberry Pi. **Label every screenshot with its data source** (simulation /
demo / API / hardware) so judges always know what is real. To date, all evidence
is produced with simulation or live-API data — physical sensors are not yet
connected.

## 0. Before you start
- [ ] `cd` into the repo and activate the Python environment.
- [ ] Reset to a clean, deterministic state: `python scripts/reset_demo_db.py`
- [ ] Run the test suite and screenshot the result: `pytest`
      *(expect the full suite to pass — currently 91 tests; label the screenshot
      "Tests: NN passing" to match the count it prints)*.
- [ ] Run the smoke test: `python scripts/smoke_test.py`

## 1. Capture terminal output (the engine)
- [ ] Start the system in the headline demo state:
      `python run.py --mode demo --scenario flood --judge-mode`
- [ ] Screenshot the startup banner showing the selected **mode** and
      **scenario** (label "demo / flood / judge-mode").
- [ ] Screenshot an explainable alert as it fires, including its plain-English
      explanation and the action playbook lines.

## 2. Run every scenario (one screenshot each)
For each, restart with the scenario flag and capture the alert state. Label each
with the scenario name and "demo, judge-mode".
- [ ] `--scenario normal`
- [ ] `--scenario flood`
- [ ] `--scenario heatwave`
- [ ] `--scenario smog`
- [ ] `--scenario storm`

## 3. Dashboard tabs (separate terminal)
Launch: `python -m streamlit run dashboard/app.py`. Capture each tab; label every
shot with the active data source.
- [ ] **Live Map** — the 20 Greater London nodes coloured by risk band.
- [ ] **Network Overview** — fleet-wide risk summary.
- [ ] **Node Detail** — a single node (e.g. Thames Barrier) with its sub-scores.
- [ ] **AI Explainability** — anomaly multiplier and the six hazard sub-scores.
- [ ] **Evidence & Validation** — validation results and export status.
- [ ] **Hardware Readiness** — the adapter/contract readiness panel.
- [ ] **Competition Pitch** — the summary pitch slide.

## 4. Show the modes work
- [ ] Capture `--mode api` startup (live Open-Meteo). If offline, capture the
      honest fallback message and label "API requested, fell back to simulation".
- [ ] Capture `--mode auto` showing the detection order (hardware → API →
      simulation) and which source it selected.

## 5. Export CSV / JSON evidence
- [ ] Run `python scripts/export_evidence.py`.
- [ ] Confirm and screenshot the five output files in `evidence/`:
      `readings.csv`, `risk_scores.csv`, `alerts.csv`, `source_summary.csv`,
      `run_summary.json`.
- [ ] Run `python scripts/run_validation.py` and screenshot the validation
      summary.

## 6. Labelling rule (apply to every artefact)
- [ ] Each screenshot filename / caption states the **data source**:
      `simulation`, `demo`, `API`, or `hardware`.
- [ ] Where the source is synthetic, note that the canonical reading carries
      `is_simulated = true` and a `quality_flag`.
- [ ] Never caption any artefact as coming from a physical sensor.
