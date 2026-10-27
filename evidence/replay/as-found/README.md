# Preserved as-found evidence

The eight original replay payloads and seven raw fixtures were captured before round 1. Storage is now compact sorted JSON in deterministic gzip (zero timestamp, no embedded filename), with derived episode counts and AI rates added to replay summaries. The observations and scores have not been changed. `original-sha256.json` retains the previous raw-file manifest; `sha256.json` pins the current stored bytes.

The four 2024 test weeks were fixed by the task before round 2. Their fixture snapshots use the fetched `surface_pressure` for original-model training; final training uses `pressure_msl`. The event observations are identical. Twelve original-code outputs, including these four fresh comparisons, are retained.

`commit.txt` names the as-found commit in this repository's history. `source.tar.gz` is a self-contained snapshot of the same behaviour, so the baseline can be checked without Git: round-1 humidity hazard selection and historical matrix conversion were reversed, then **all eight existing replay payloads reproduced byte for byte after the identical compact serialization and reporting enrichment**. The snapshot includes the unchanged replay/adapter/database dependencies and needs no Git history or network.

`versions.txt`, `evaluate.txt`, `demo-tour.txt`, and `ablation.json.gz` retain the numerical environment and synthetic baseline. To reproduce all twelve saved replays offline, into a separate directory:

```bash
python scripts/reproduce_as_found.py --out out/as-found-check
```

The command compares deterministic compressed bytes for every replay and never overwrites existing baseline evidence. `--capture-new` only captures missing outputs when explicitly adding new snapshot fixtures; it was used once for the predeclared 2024 comparisons. See `docs/replay_report.md` for all three calibration stages and limitations.
