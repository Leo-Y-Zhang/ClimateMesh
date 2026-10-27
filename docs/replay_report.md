# Recorded replay: as found → round 1 → round 2

Round 2 makes barometric pressure a supporting factor, with wind selecting storms. It meets the three-event first-six-hour zero-alert regression target and retains the recorded heat and Eunice peaks. It does **not** establish accurate operational calibration: the untouched 2024 weeks still produce **1,992 alert-hours, 384 node episodes and 29 London-wide episodes**, and **1,987** alerts have a driving hazard sub-score below WARNING. The 2023 development totals are **7,691 → 4,681 → 4,185 alert-hours**, **1,305 → 816 → 816 node episodes**, and **74 → 48 → 46 London-wide episodes**. Some individual episode and hazard counts worsen.

## Method, stages and the untouched year

The three original events and four 2023 weeks are development evidence. Round 1 had already inspected the 2023 outcomes; they are no longer an unbiased test. The fresh test rule was fixed before round 2: the first full Monday–Sunday week of March, June, September and December 2024, specifically **4–10 March, 3–9 June, 2–8 September and 2–8 December**. Every week contains 168 hourly samples at all 20 illustrative nodes (3,360 node-hours), fitted on its own preceding 30 London local dates (720 hours). All eleven fixtures were fetched or rechecked with `scripts/fetch_history.py`; the final `--check` reports all unchanged.

The round-2 scoring and feature-path hashes were saved in [round-2-lock.json](../evidence/replay/round-2-lock.json) before running the 2024 scores. Events and 2023 replays ran first, focused production regressions passed, then 2024 ran last. No scoring, model, or adapter changes followed inspection of 2024 results. Fetching the raw 2024 fixtures preceded scoring; they were not used to select changes. The 2024 comparisons below are reported as measured, including poor results.

**As found** means humidity and pressure could select hazards, with hourly-rain urban-only training water and training `surface_pressure`. **Round 1** removed humidity from hazard selection and aligned historical water proxies, environments, sea-level pressure and local midnight. **Round 2** only removes pressure from hazard selection. Smog mapping (EAQI ×2.5), cold curve, all sub-score curves, bands, thresholds, AI multiplier formula, contamination 0.05, 120 trees, random state 42, mesh multipliers and 6 km radius are unchanged in round 2. Synthetic training is unchanged.

The adapter, model, risk engine, mesh, SQL alert and cooldown paths run offline in a private in-memory database. One cycle uses each sample's UTC clock; the 900-second cooldown expires between sampled hours. These are sampled alert-hours, not inferred three-second alerts. “Quiet hours” always means the first six recorded hours, a fixed diagnostic slice rather than an independently established benign-weather label.

## Preserved baseline and reproduction

All three stages retain complete per-hour scores. Round-1 payloads were preserved before editing. As-found observations and scores were preserved, with storage converted to compact deterministic gzip and derived summary diagnostics added. The original raw-file hash manifest remains alongside a new manifest of current stored bytes.

So that nobody needs the project's Git history to check the baseline, a self-contained [source snapshot](../evidence/replay/as-found/source.tar.gz) restores the original humidity hazard selection and archive matrix conversion using the available round-1 sources. All **eight existing as-found replay payloads reproduce byte for byte** after the same compact serialization/reporting enrichment. This verifies behavioral restoration on the preserved inputs; it does not claim recovery of the missing Git source object. The restored source then generated the four 2024 as-found comparisons using identical test observations and fetched training `surface_pressure`. Final fitting uses the simultaneously fetched `pressure_msl`. All **twelve** baseline outputs now reproduce offline without Git history or network. Existing baseline artifacts are never overwritten by reproduction.

## Round 1: evidence and changes

Humidity was eligible to be the worst term and label a flood: RH 95% gave `humidity_sub=55`. AI and mesh could amplify routine damp nights into CRITICAL flood alerts. Training water used 0.20 m plus hourly rain ×0.05, while serving used each environment's baseline and rain accumulated since London midnight. Training used surface rather than sea-level pressure (median paired difference 1.9–2.0 hPa). These were clear training/serving mismatches.

Round 1 made humidity secondary only, shared the running-total water helper across archive/live/replay, represented all five supported environments in training, sliced training at London day boundaries and requested `pressure_msl`. Live rainfall excludes future forecast hours and rejects missing elapsed rain. Its cache schema invalidates the old historical matrix. Flood quiet-hour alerts fell **119 → 0 grid**, **117 → 0 gauges**; quiet AI flags fell **92 → 0 grid**, **88 → 0 gauges**. The four quiet river nodes, previously all flagged, have proxy levels 1.00–1.72 m that are now normal to the preceding-month model.

Training humidity and pressure prevalence were measured from the existing windows **before the round-2 scoring edit**:

| Existing window | RH ≥85% /720 | pressure_msl ≤1000 hPa /720 |
|---|---|---|
| flood-2021-07-12 | 307 (42.64%) | 14 (1.94%) |
| heat-2022-07-19 | 118 (16.39%) | 0 (0.00%) |
| storm-2022-02-18 | 374 (51.94%) | 50 (6.94%) |
| holdout-2023-03-06 | 400 (55.56%) | 0 (0.00%) |
| holdout-2023-06-05 | 228 (31.67%) | 0 (0.00%) |
| holdout-2023-09-04 | 282 (39.17%) | 0 (0.00%) |
| holdout-2023-12-04 | 494 (68.61%) | 125 (17.36%) |

## Round 2: pressure, episodes and AI audit

Round-1 2023 storm alerts numbered **1,504**, with median wind **4.49 m/s** and pressure **981.1–1000.5 hPa**. Those pressure-selected labels motivated the narrowly scoped second change.

Pressure now contributes **only through the existing 20% secondary term**. It cannot be `worst`, choose `dominant_hazard`, lead the factor ranking or select storm agreement. Wind drives a storm. Explanations show pressure alongside humidity as support, including SAFE readings. The regression at 950 hPa with all other channels calm stays SAFE and labels no storm. No live cooldown, notification or episode-suppression behavior changed.

A **node episode** is a maximal consecutive hourly run delivering the same alert type to one node. A nonalert hour, hazard change, missing hour or missing node breaks it. A **London-wide episode**, independently per hazard, continues while at least one node alerts in consecutive hours, even if the alerting node changes. `sensor-check` is its own delivered type; its underlying hazard remains in the alert listing for diagnosis. Week totals sum these independent per-hazard runs, so simultaneous different hazards count separately. Runs cannot bridge the gaps between quarterly windows. These are readable notification units, not independently adjudicated weather incidents. Every replay summary includes alert-hours, both episode totals, by-hazard counts and AI rates. The CSV includes stable node/London episode IDs and start flags; summing start flags recovers the summary totals. A hand-built regression covers handoffs, hazard switches, dry gaps and missing samples.

AI firing means `is_anomaly=True`, divided by **all** node-hours, with the first six hours reported separately. The new replay rows expose the flag directly; on older payloads it is recovered exactly from `ai_multiplier>1` under the unchanged formula. The contamination parameter is a fitted-training quantile, not a promise that 5% of future data will fire.

The audit found **no remaining clear feature conversion mismatch**: feature order, °C, percent RH, m/s, hPa, EAQI conversion, environment water baselines/sensitivities, local midnight, and weather/air time axes agree. The database passes those same channels through. There are no synthetic node offsets in the historical adapter. Training remains one central archive location replicated across five environments, while serving uses 20 actual gridded locations; different spatial coverage and unknown future weather remain limitations, not a demonstrated unit or offset bug to patch. No further AI change was made.

There is measurable temporal distribution shift: in March 2023 training pressure spans 1010.7–1046.0 hPa versus 981.1–1011.6 in replay; **95.12%** of node-hours are outside that training range. June has **19.32%** of temperatures and **15.71%** of AQI outside fitted ranges. September has **29.46%** of temperatures and **47.05%** of AQI outside them. These checks do not explain every multivariate flag or establish weather truth. [Feature-range diagnostics](../evidence/replay/ai-feature-diagnostics.json) retain every window's ranges and outside shares. AI sees pressure as before, so routine lows can remain anomalous even though they no longer select a storm score.

Each cell below is **full-window flagged/total (share); quiet flagged/120 (share)**. Round-2 rates equal round 1 because the model and its inputs are unchanged:

| Window | As found | Round 1 | Round 2 |
|---|---|---|---|
| flood-2021-07-12-gauges | 440/480 (91.67%); 88/120 (73.33%) | 74/480 (15.42%); 0/120 (0.00%) | 74/480 (15.42%); 0/120 (0.00%) |
| flood-2021-07-12 | 452/480 (94.17%); 92/120 (76.67%) | 66/480 (13.75%); 0/120 (0.00%) | 66/480 (13.75%); 0/120 (0.00%) |
| heat-2022-07-19 | 797/960 (83.02%); 72/120 (60.00%) | 583/960 (60.73%); 0/120 (0.00%) | 583/960 (60.73%); 0/120 (0.00%) |
| storm-2022-02-18 | 436/480 (90.83%); 76/120 (63.33%) | 273/480 (56.88%); 2/120 (1.67%) | 273/480 (56.88%); 2/120 (1.67%) |
| holdout-2023-03-06 | 3128/3360 (93.10%); 83/120 (69.17%) | 1556/3360 (46.31%); 36/120 (30.00%) | 1556/3360 (46.31%); 36/120 (30.00%) |
| holdout-2023-06-05 | 2370/3360 (70.54%); 72/120 (60.00%) | 999/3360 (29.73%); 0/120 (0.00%) | 999/3360 (29.73%); 0/120 (0.00%) |
| holdout-2023-09-04 | 2638/3360 (78.51%); 85/120 (70.83%) | 1445/3360 (43.01%); 24/120 (20.00%) | 1445/3360 (43.01%); 24/120 (20.00%) |
| holdout-2023-12-04 | 2689/3360 (80.03%); 112/120 (93.33%) | 287/3360 (8.54%); 12/120 (10.00%) | 287/3360 (8.54%); 12/120 (10.00%) |
| holdout-2024-03-04 | 2379/3360 (70.80%); 74/120 (61.67%) | — | 96/3360 (2.86%); 1/120 (0.83%) |
| holdout-2024-06-03 | 2239/3360 (66.64%); 72/120 (60.00%) | — | 7/3360 (0.21%); 0/120 (0.00%) |
| holdout-2024-09-02 | 2956/3360 (87.98%); 72/120 (60.00%) | — | 727/3360 (21.64%); 5/120 (4.17%) |
| holdout-2024-12-02 | 2501/3360 (74.43%); 72/120 (60.00%) | — | 394/3360 (11.73%); 0/120 (0.00%) |

## Original events across all three stages

All sequences are **as found → round 1 → round 2**. Full-window peak scores remain **100.0 → 100.0 → 100.0** for every event/variant. The volume columns count all delivered types, including sensor-checks.

| Event / variant | Alert-hours | Node episodes | London episodes | Quiet alerts | Quiet peak | Event-hazard alerts |
|---|---|---|---|---|---|---|
| flood-2021-07-12-gauges | 310 → 44 → 44 | 48 → 13 → 13 | 4 → 3 → 3 | 117 → 0 → 0 | 99.1 → 28.1 → 28.1 | 306 → 20 → 20 |
| flood-2021-07-12 | 311 → 36 → 36 | 50 → 12 → 12 | 4 → 5 → 5 | 119 → 0 → 0 | 99.1 → 28.1 → 28.1 | 306 → 4 → 4 |
| heat-2022-07-19 | 546 → 491 → 491 | 115 → 103 → 103 | 8 → 8 → 8 | 0 → 0 → 0 | 59.7 → 45.6 → 45.6 | 399 → 396 → 396 |
| storm-2022-02-18 | 244 → 220 → 129 | 31 → 21 → 21 | 2 → 1 → 2 | 23 → 2 → 0 | 76.2 → 72.6 → 28.8 | 232 → 220 → 129 |

| Event / variant | As found delivered alerts | Round 1 | Round 2 |
|---|---|---|---|
| flood-2021-07-12-gauges | flood: 306; sensor-check: 4 | flood: 20; sensor-check: 24 | flood: 20; sensor-check: 24 |
| flood-2021-07-12 | flood: 306; sensor-check: 5 | flood: 4; sensor-check: 32 | flood: 4; sensor-check: 32 |
| heat-2022-07-19 | heatwave: 399; sensor-check: 5; smog: 142 | heatwave: 396; sensor-check: 4; smog: 91 | heatwave: 396; sensor-check: 4; smog: 91 |
| storm-2022-02-18 | flood: 12; storm: 232 | storm: 220 | storm: 129 |

The three events now have **zero quiet alerts**, including zero below-WARNING-hazard alerts. Eunice's two round-1 alerts at 05:00 (winds 9.71/9.94 m/s and pressure 995.8/996.0 hPa) disappear. Its quiet peak falls **76.2 → 72.6 → 28.8**. **Reduced coverage/fragmentation:** full-window storm alert-hours fall **232 → 220 → 129**, while London storm episodes change **1 → 1 → 2** (the as-found total of two also included a flood episode). The remaining storm alerts have median wind **14.84 m/s**, minimum **11.21**, maximum **19.38**; previously the round-1 median was **12.57**. Only two final storm alerts reach a wind sub-score of 60 alone. This is less alerting and more fragmentation, not evidence of better recall.

The recorded heat peak remains **38.0°C at CAMDEN, 2022-07-19 12:00 London time**, CRITICAL heatwave score **100.0**. The recorded Eunice sustained-wind peak remains **19.38 m/s at CAMDEN, 2022-02-18 12:00 London time**, CRITICAL storm score **100.0**. These are grid peaks, not national station records or forecasting skill.

Putney Heath is eligible within **1.410 km** of PUTNEY; Wanstead → ILFORD is the only other all-Good gauge within 3 km. Putney Heath records **47.25 mm** in the requested UTC day, **47.21 mm** within the available local replay window, and **33.24 mm at 16:00**; Mitcham records **2.22 mm**. PUTNEY's grid cell totals **16.0 mm**, Mitcham's nearest node cell **16.8 mm**. Holland Park's **59.4 mm** is shown but not substituted because its readings are not all Good. Pinner Cemetery has **96 Missing** readings and no measured total.

PUTNEY's 16:00 score is **82.7 → 67.3 → 67.3**, changing from CRITICAL to WARNING with partial corroboration. Both calibrated stages first reach CRITICAL at **18:00**, score **85.6**, partial, and peak at **19:00**, score **100.0**, partial. The grid variant's full-window PUTNEY peak is **95.0 → 53.4 → 53.4**, now MODERATE at **20:00**. This weaker first band remains pinned as measured; the localized gauge-fed flood is still detected without full mesh corroboration.

## 2023 development weeks: three-stage comparison

In this table each stage is **alert-hours / node episodes / London-wide episodes**.

| 2023 week | As found | Round 1 | Round 2 |
|---|---|---|---|
| 2023-03-06 | 2489 / 422 / 29 | 1968 / 282 / 19 | 1715 / 331 / 21 |
| 2023-06-05 | 678 / 142 / 8 | 524 / 81 / 5 | 524 / 81 / 5 |
| 2023-09-04 | 2242 / 417 / 19 | 1428 / 294 / 10 | 1428 / 294 / 10 |
| 2023-12-04 | 2282 / 324 / 18 | 761 / 159 / 14 | 518 / 110 / 10 |
| Total | 7691 / 1305 / 74 | 4681 / 816 / 48 | 4185 / 816 / 46 |

| 2023 week | Quiet alerts | Hazard-alone alerts | Below-WARNING hazard alerts |
|---|---|---|---|
| 2023-03-06 | 120 → 120 → 120 | 395 → 400 → 140 | 2094 → 1568 → 1575 |
| 2023-06-05 | 63 → 0 → 0 | 177 → 177 → 177 | 501 → 347 → 347 |
| 2023-09-04 | 117 → 31 → 31 | 150 → 150 → 150 | 2092 → 1278 → 1278 |
| 2023-12-04 | 67 → 1 → 0 | 0 → 0 → 0 | 2282 → 761 → 518 |

The fixed diagnostic calls an alert **hazard-alone** when the driving hazard sub-score is ≥60, otherwise **multiplier-dependent**. Secondary terms can already lift a base above WARNING, so the latter is not necessarily a literal dependence on a multiplier, nor a ground-truth false-alarm label. Flood uses water, never humidity; final storms use wind only. Historical stages retain their then-eligible max(wind, pressure), preserving the old counts. Sensor-check rows retain their underlying dominant hazard for this rule.

By delivered type, including increases hidden by the smaller totals:

| 2023 week | Type | As found | Round 1 | Round 2 |
|---|---|---|---|---|
| 2023-03-06 | cold | 320 | 513 | 1018 |
| 2023-03-06 | flood | 1437 | 0 | 0 |
| 2023-03-06 | risk | 0 | 0 | 3 |
| 2023-03-06 | sensor-check | 20 | 13 | 47 |
| 2023-03-06 | smog | 226 | 274 | 647 |
| 2023-03-06 | storm | 486 | 1168 | 0 |
| 2023-06-05 | flood | 173 | 0 | 0 |
| 2023-06-05 | smog | 505 | 524 | 524 |
| 2023-09-04 | flood | 793 | 0 | 0 |
| 2023-09-04 | heatwave | 60 | 58 | 58 |
| 2023-09-04 | sensor-check | 1 | 0 | 0 |
| 2023-09-04 | smog | 1388 | 1370 | 1370 |
| 2023-12-04 | cold | 0 | 77 | 77 |
| 2023-12-04 | flood | 1898 | 0 | 0 |
| 2023-12-04 | sensor-check | 1 | 3 | 3 |
| 2023-12-04 | smog | 104 | 345 | 438 |
| 2023-12-04 | storm | 279 | 336 | 0 |

**Worse:** March cold alerts rise **320 → 513 → 1,018**, smog **226 → 274 → 647**, and sensor-checks **20 → 13 → 47**. March's node episodes rise **282 → 331** and London episodes **19 → 21** from round 1, despite fewer alert-hours. Three generic `risk` alert-hours (one London episode) remain when supporting factors and low individual hazards combine. December smog rises **104 → 345 → 438**. June smog remains **505 → 524 → 524**. September heat alerts remain **60 → 58 → 58**. These changes include hazard relabelling as pressure stops dominating; no claim of improved correctness follows without truth labels.

Below-WARNING hazard alerts total **6,969 → 3,954 → 3,718**. The broad zero target still fails in every development week. March's first six hours still deliver **120 cold alerts**; September still delivers **31 smog alerts** there. September's grid temperature reaches **31.5°C** and its 58 heat alerts are all below the fixed sub-score rule; that is not proof that the real heatwave was absent.

## Untouched 2024 test-year result — reported as is

No round-1 2024 scores were generated: the predeclared comparison is as found versus final. Each cell is **alert-hours / node episodes / London-wide episodes**.

| Fixed Monday–Sunday week | As found | Final round 2 |
|---|---|---|
| 2024-03-04 | 2123 / 366 / 21 | 1070 / 211 / 15 |
| 2024-06-03 | 371 / 107 / 10 | 41 / 15 / 1 |
| 2024-09-02 | 1604 / 272 / 16 | 501 / 110 / 9 |
| 2024-12-02 | 1461 / 199 / 10 | 380 / 48 / 4 |
| Total | 5559 / 944 / 57 | 1992 / 384 / 29 |

All delivered hazards, with zero final counts shown explicitly; each cell again uses **hours / node episodes / London episodes**:

| 2024 week | Delivered hazard | As found | Final |
|---|---|---|---|
| 2024-03-04 | cold | 0 / 0 / 0 | 137 / 26 / 1 |
| 2024-03-04 | flood | 1424 / 167 / 8 | 0 / 0 / 0 |
| 2024-03-04 | sensor-check | 1 / 1 / 1 | 0 / 0 / 0 |
| 2024-03-04 | smog | 336 / 140 / 9 | 933 / 185 / 14 |
| 2024-03-04 | storm | 362 / 58 / 3 | 0 / 0 / 0 |
| 2024-06-03 | flood | 310 / 81 / 7 | 0 / 0 / 0 |
| 2024-06-03 | smog | 61 / 26 / 3 | 41 / 15 / 1 |
| 2024-09-02 | flood | 1465 / 207 / 11 | 0 / 0 / 0 |
| 2024-09-02 | smog | 139 / 65 / 5 | 501 / 110 / 9 |
| 2024-12-02 | flood | 754 / 105 / 5 | 0 / 0 / 0 |
| 2024-12-02 | sensor-check | 3 / 2 / 1 | 0 / 0 / 0 |
| 2024-12-02 | smog | 395 / 72 / 3 | 380 / 48 / 4 |
| 2024-12-02 | storm | 309 / 20 / 1 | 0 / 0 / 0 |

There are **no final flood, storm, heatwave, risk or sensor-check alerts** in the test weeks. Final cold totals **137 hours / 26 node episodes / 1 London episode**; smog totals **1,855 hours / 358 node episodes / 28 London episodes**. The final by-hazard episode counts, rather than the number of nodes or sampled hours, are the notification-scale result.

| 2024 week | Quiet alerts, as found → final | Hazard-alone, as found → final | Below-WARNING, as found → final |
|---|---|---|---|
| 2024-03-04 | 120 → 119 | 0 → 0 | 2123 → 1070 |
| 2024-06-03 | 91 → 0 | 0 → 0 | 371 → 41 |
| 2024-09-02 | 116 → 5 | 0 → 0 | 1604 → 501 |
| 2024-12-02 | 111 → 0 | 48 → 5 | 1413 → 375 |

**The calibration concern persists:** only **5/1,992** final alerts meet the hazard-alone rule; all five are December smog. March still raises **119 alerts in its first six hours**, September **5**, June/December zero. At 2024-03-04 00:00, BRIXTON raises CRITICAL cold **82.3** at **0.1°C**: temperature sub-score **49.2**, AQI sub-score **39.0**, humidity sub-score **58.0**, pressure sub-score **0**, AI **1.0**, mesh **1.2**. AI overfiring cannot explain that example: multiple moderate terms and the fixed mesh multiplier suffice.

**Worse than as found:** March smog rises **336 → 933** and cold **0 → 137**; September smog rises **139 → 501**. Other labels disappear, so smaller overall totals obscure these increases. No independent event labels establish whether these are appropriate warnings. Final test-year AI rates range **0.21%–21.64%**, with March **2.86%**, June **0.21%**, September **21.64%**, December **11.73%**. This unevenness also contradicts interpreting contamination 0.05 as a guaranteed future 5% rate.

## What drives the smog and cold alerts

The distributions below use **delivered smog/cold alerts**, excluding sensor-checks, at all alerting node-hours (not episode-weighted). Smog values are EAQI, reversing the unchanged ×2.5 conversion; archived raw EAQI is also retained directly in the CSV. No smog alert uses a missing-AQI fallback. Cold values are °C. Each row reports **minimum / 25th percentile / median / 75th percentile / maximum** for the final stage; all three stages' distributions are retained in the machine-readable summary.

| Week | Driver | Alert-hours | Min / P25 / median / P75 / max |
|---|---|---|---|
| 2023-03-06 | cold (°C) | 1018 | -3.6 / -0.9 / 1 / 1.9 / 3.5 |
| 2023-03-06 | smog (EAQI) | 647 | 31 / 42 / 47 / 50 / 70 |
| 2023-06-05 | smog (EAQI) | 524 | 42 / 53 / 65 / 71 / 79 |
| 2023-09-04 | smog (EAQI) | 1370 | 42 / 52 / 58 / 63 / 78 |
| 2023-12-04 | cold (°C) | 77 | -0.4 / 0.1 / 0.7 / 1.1 / 2.1 |
| 2023-12-04 | smog (EAQI) | 438 | 37 / 47 / 50 / 53 / 60 |
| 2024-03-04 | cold (°C) | 137 | -0.9 / -0.3 / 0.1 / 0.3 / 1.6 |
| 2024-03-04 | smog (EAQI) | 933 | 38 / 48 / 52 / 57 / 67 |
| 2024-06-03 | smog (EAQI) | 41 | 49 / 50 / 53 / 54 / 56 |
| 2024-09-02 | smog (EAQI) | 501 | 37 / 46 / 48 / 52 / 59 |
| 2024-12-02 | smog (EAQI) | 380 | 42 / 55 / 61 / 66 / 70 |

At 2024-09-08 23:00 HYDE-PARK reaches WARNING **60.0** with EAQI **37** (mapped AQI **92.5**, `aqi_sub=25.5`), RH **96%** (`humidity_sub=58`), pressure **1003.9 hPa** (`pressure_sub=12.8`), AI **1.26**, mesh **1.2**. This is a concrete moderate-air-quality warning under the protected scoring terms. March 2023's real cold snap remains in the data, but final cold alerts also extend to **3.5°C**. The unchanged curves and combined factors need external validation; no mapping, cold curve or multiplier was adjusted to improve these results.

[Every alert and episode marker](../evidence/replay/held-out-alerts.csv.gz) is retained as a gzip CSV: **24,108 rows** across the three 2023 stages and two 2024 stages. It includes version, week, local hour, node, delivered/underlying hazard, fixed class, all channels and sub-scores, raw EAQI, anomaly flag, multipliers, corroboration, hourly/running rain and both episode IDs/start flags. There is no filtering of unwanted results. [calibration-summary.json](../evidence/replay/calibration-summary.json) contains all counts, rates and distributions; each replay retains every nonalert row too.

## Synthetic evaluation, demo tour and ablation

All comparisons below use the same seeded synthetic data; the generator and model are unchanged. Quiet false-alarm frames remain **0/30 → 0/30 → 0/30** in every configuration. Stuck 9 m water-sensor false flood alerts remain **90/90** for sub-scores and AI alone and **0/90** for the full system. Full-intensity detection remains **120/120** in all configurations/stages.

**Worse than as found:** full-system 90% detection first occurs at **0.80 → 1.00 → 1.00** intensity; sub-scores and AI alone remain **0.80**. Full-system detection by intensity (all three stages):

| Intensity | As found | Round 1 | Round 2 |
|---|---|---|---|
| 0.10 | 0.0% | 0.0% | 0.0% |
| 0.20 | 0.0% | 0.0% | 0.0% |
| 0.30 | 0.0% | 0.0% | 0.0% |
| 0.40 | 25.0% | 25.0% | 25.0% |
| 0.50 | 35.0% | 35.0% | 35.0% |
| 0.60 | 50.0% | 50.0% | 50.0% |
| 0.70 | 61.7% | 50.8% | 50.8% |
| 0.80 | 100.0% | 75.0% | 75.0% |
| 0.90 | 100.0% | 75.0% | 75.0% |
| 1.00 | 100.0% | 100.0% | 100.0% |

Round 2 matches round 1 at intensity 0.70 (**50.8% → 50.8%** from its as-found **61.7%**); 0.80/0.90 stay **100.0% → 75.0% → 75.0%**. No claim of restored synthetic sensitivity is made. Sub-score/AI-only intensity curves remain unchanged; full text is retained for every stage.

Demo tour averages / maxima / alert counts:

| Scenario | As found | Round 1 | Round 2 |
|---|---|---|---|
| normal | 3.9 / 11.4 / 0 | 3.9 / 11.4 / 0 | 3.9 / 11.4 / 0 |
| flood | 50.8 / 100.0 / 10 | 43.0 / 100.0 / 4 | 44.2 / 100.0 / 4 |
| heatwave | 78.8 / 100.0 / 12 | 78.8 / 100.0 / 12 | 78.8 / 100.0 / 12 |
| smog | 82.7 / 100.0 / 15 | 82.7 / 100.0 / 15 | 82.7 / 100.0 / 15 |
| storm | 98.1 / 100.0 / 20 | 98.1 / 100.0 / 20 | 98.1 / 100.0 / 20 |

Flood tour average is **50.8 → 43.0 → 44.2**, alerts **10 → 4 → 4**: sensitivity is still lower than as found. HYDE-PARK changes **69.6 WARNING (flood) → 46.9 MODERATE (pressure-selected storm) → 49.2 MODERATE (water-selected flood)**. It now has four agreeing neighbours and mesh 1.2, previously one and mesh 1.0. REGENTS-CANAL's explanation changes **three agreeing neighbours → one of four → three agreeing neighbours** as humidity and then pressure cease selecting hazards. The final explanation correctly puts humidity and pressure in supporting clauses. No tour scenario becomes worse than round 1 on its aggregate alert count, but as-found flood detection was stronger.

Band ablation (S SAFE, M MODERATE, W WARNING, C CRITICAL), again all three stages:

| Scenario | Sub-score bands, as found → round 1 → round 2 | Full-system bands, as found → round 1 → round 2 |
|---|---|---|
| normal | S:20 → S:20 → S:20 | S:20 → S:20 → S:20 |
| flood | S:8, M:8, C:4 → S:8, M:8, C:4 → S:8, M:8, C:4 | S:8, M:2, W:6, C:4 → S:8, M:8, C:4 → S:8, M:8, C:4 |
| heatwave | M:8, W:4, C:8 → M:8, W:4, C:8 → M:8, W:4, C:8 | M:8, W:1, C:11 → M:8, W:1, C:11 → M:8, W:1, C:11 |
| smog | M:8, C:12 → M:8, C:12 → M:8, C:12 | M:5, W:3, C:12 → M:5, W:3, C:12 → M:5, W:3, C:12 |
| storm | W:15, C:5 → W:15, C:5 → W:15, C:5 | W:1, C:19 → W:1, C:19 → W:1, C:19 |

## Storage, figures and validation

All replay JSON is sorted, compact (`separators=(",", ":")`, no indentation), UTF-8 with LF and a final newline. Held-out weeks, round-1 snapshots and every as-found copy use deterministic `.json.gz`: gzip mtime 0, no embedded filename. Plain event JSON remains available. Dashboard, figure, report, replay-fixture and reproduction readers accept plain or gzip JSON. The full CSV also uses deterministic gzip so the complete evidence fits the size limit. The baseline source snapshot is local and compressed. No observations were discarded to meet the budget.

The comparison figure uses **London-wide episodes as bar height**, with alert-hours as secondary labels: all three stages for events/2023, as found versus final for 2024. All other replay figures were regenerated from final outputs. The flood hero shows gauge-vs-grid rain, risk and corroboration; the map retains all gauges and actual returned grid centres with approximate footprints, no invented rainfall interpolation. Heat/storm figures show the peak node and other-node envelope. All figures use 200 dpi, an A4-width layout, attribution footers and the colour-blind-safe palette.

The final evidence directory is **8,054,696 bytes (8.055 MB decimal; 7.682 MiB)** by `du -sb evidence`, below the **12,000,000-byte** limit. All 53 stored JSON artifacts were checked for compact sorted formatting, LF and deterministic gzip headers. The replay bytes match across both hash seeds, all 32 preserved-baseline manifest entries match, the pre-2024 source hashes remain unchanged, and the complete CSV reconciles to every summary. Artifact generation succeeding does not mean the residual calibration concern passed.

## Remaining limitations

The three original quiet-event regressions pass, but the broader zero-below-WARNING target remains unmet on both development and test weeks. There is no independent meteorological truth set for these alerts, no measured precision/recall on recorded weeks and no forecast-skill claim. Episode counting does not turn a false warning into a correct one and can increase when runs fragment or labels change. Cold/smog warnings persist with moderate driving values and even without AI amplification.

A 30-day single-location archive baseline cannot cover all future or spatial weather/air combinations; environment replication is not independent spatial training. Five-percent training contamination does not bound future firing. Shared grid cells make mesh agreement dependent evidence. EU-AQI conversion and cold severity remain unvalidated. Water is an **estimated rain-to-water proxy**, not measured river depth. Only two gauges satisfy all-Good/3 km substitution; nearest wins without blending. The UTC gauge request omits the first BST hour and includes an hour outside the replay window; empty buckets represent gaps, not measured dryness, and coverage/outside totals remain explicit. Gridded rainfall smooths convective extremes; wind scoring uses sustained wind, not gusts. Numerical byte equality is verified in the recorded dependency environment, not promised across library upgrades.

## Commands and output tails

All final project commands in [commands.json](../evidence/replay/checks/commands.json) exited **0**. The suite is **360 tests**, up from round 1's 345 (the earlier as-found report recorded 313). One exploratory full-suite run exposed a stale flood-tour pin after the score changed to 44.2; the pin and README were updated from the real tour output, and the final full suite and judge suite both passed. No scoring change followed the test-year results. Initial commands also exposed missing dependencies; the environment was installed with the project's requirements and the preserved numerical versions before the recorded successful runs.

The new fixtures were fetched with the following loop, then all eleven fixtures passed the final all-fixture check:

```bash
for event in holdout-2024-03-04 holdout-2024-06-03 holdout-2024-09-02 holdout-2024-12-02; do
  python scripts/fetch_history.py --event "$event" || exit 1
done
python scripts/fetch_history.py --check
```

The first round-2 run scored flood grid/gauges, heat, Eunice and the four 2023 weeks, followed by the four 2024 weeks after freezing the scoring/feature hashes. These complete runs then verified all twelve final outputs twice:

```bash
PYTHONHASHSEED=1 python scripts/replay_event.py --all --out out/replay-seed-1
PYTHONHASHSEED=987654 python scripts/replay_event.py --all --out out/replay-seed-987654
python scripts/reproduce_as_found.py --out out/as-found-check
python scripts/calibration_report.py
python scripts/replay_figures.py
python scripts/evaluate.py
python scripts/demo_tour.py
python -m pytest -q
.venv/bin/ruff check --select F,E9 .
python scripts/judge_validate.py
git diff --check
du -sb evidence
```

The report command regenerates ablation and feature diagnostics as well as summary JSON and CSV. All four regenerated artifacts were additionally checked byte-identical on repetition. Temporary seed comparison directories were removed after verification; complete command outputs remain under `evidence/replay/checks/`. The preserved round-1 outputs and command logs are under `round-1/`.

Selected actual final tails:

`fetch-all.txt`:

```text
flood-2021-07-12: unchanged
heat-2022-07-19: unchanged
storm-2022-02-18: unchanged
holdout-2023-03-06: unchanged
holdout-2023-06-05: unchanged
holdout-2023-09-04: unchanged
holdout-2023-12-04: unchanged
holdout-2024-03-04: unchanged
holdout-2024-06-03: unchanged
holdout-2024-09-02: unchanged
holdout-2024-12-02: unchanged
```

`determinism.txt`:

```text
PASS: 12 replay outputs byte-identical in both runs (PYTHONHASHSEED=1 and 987654) and final evidence; scoring/feature hashes still match the pre-2024 lock.
```

`as-found-final.txt`:

```text
PASS: 12 original-code replays reproduce the preserved JSONs byte for byte
```

`pytest.txt`:

```text
........................................................................ [ 80%]
........................................................................ [100%]
```

`ruff.txt`:

```text
All checks passed!
```

`judge.txt`:

```text
  Climate Mesh — Judge Validation
================================================================
  Step                           Result   Detail
----------------------------------------------------------------
  1. Smoke test                  PASS     10/10 checks
  2. Pytest suite                PASS     360 passed
  3. Demo cycle (normal)         PASS     nodes=20 avg_risk=3.9 alerts=0
  4. Demo cycle (flood)          PASS     nodes=20 avg_risk=44.2 alerts=4
  5. Evidence export             PASS     5 files
----------------------------------------------------------------
  RESULT: PASS  (5/5 steps passed)
================================================================
```

`evaluate.txt`:

```text
       1.00            100.0%          100.0%          100.0%

  Intensity at which each configuration first reaches 90 % detection
  --------------------------------------------------------------
  sub-scores              0.80
  + AI                    0.80
  + AI + mesh             1.00
============================================================================
```

`demo-tour.txt`:

```text
  Sample explanation (flood, Regent's Canal (Little Venice)):
    Flood risk rising near Regent's Canal (Little Venice). Same trend seen across 3 nearby nodes. Risk score 100/100. Main contributors: critical water level (4.8 m). Supporting factor: very high humidity (99%). Supporting factor: falling pressure (996 hPa).

  RESULT: PASS (5/5 scenarios, deterministic, offline)
```

`figures.txt`:

```text
Wrote evidence/replay/figures/heat-2022-07-19.png
Wrote evidence/replay/figures/storm-2022-02-18.png
Wrote evidence/replay/figures/flood-2021-07-12-all-gauges.png
Wrote evidence/replay/figures/flood-2021-07-12-hero.png
Wrote evidence/replay/figures/flood-2021-07-12-gauge-map.png
Wrote evidence/replay/figures/calibration-before-after.png
```
