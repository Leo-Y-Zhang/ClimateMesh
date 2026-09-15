# Entry-form answers (copy and paste)

Competition entry forms tend to ask the same questions in different lengths.
Everything below is accurate to the submitted code, so it can be pasted as-is
or trimmed. Nothing here needs filling in; school and teacher details go on
the form itself.

**Project title:** Climate Mesh

**Team:** Luis Yu and Leo Zhang · Years 12–13 category (school and teacher
details go on the form itself; nothing in this pack names them).

**One-line summary (20 words):**
An £85 Raspberry Pi that tells a school, in plain English, when its street may
flood and what to do.

**Short description (about 100 words):**
Climate Mesh is a decentralised climate early-warning mesh that runs on a
single Raspberry Pi 5 with no internet and no cloud account. Twenty
environmental nodes across Greater London report temperature, humidity, air
quality, water level, wind and pressure every two seconds. A risk engine
scores each location 0–100, an explainable Isolation Forest flags unusual
combinations of readings, and *neighbour agreement* escalates risk only when
nearby nodes see the same hazard while damping a node that no neighbour
agrees with and reporting it as a sensor to check, so one faulty sensor cannot
cry wolf. Alerts are
written in plain English with community action playbooks. Every reading
carries its data source, and judges can prove the whole system works with one
command.

**Longer description (about 250 words):**
Flood and heat warnings fail where they matter most: the nearest official
gauge can be kilometres from the drain or stream that actually floods. Climate
Mesh closes that gap with a network of cheap nodes that a school or community
could own. Every data source, whether a physical Vernier weather sensor, the
live Open-Meteo weather service or our simulator, is converted into one
canonical reading shape with a source label and a quality flag, so the system
is sensor-ready without being sensor-dependent. For each node a risk engine
computes six hazard sub-scores and combines them into a 0–100 score with SAFE,
MODERATE, WARNING and CRITICAL bands. An Isolation Forest learns the normal
shape of the data and flags anomalous combinations while every channel is
still only moderately elevated, multiplying graded risk by up to 1.5× (the
measured range is 1.25× to 1.36×; it can
amplify risk, never create it) and reporting which channels deviate most. Two
nodes within 6 km are neighbours; a 1.2× mesh multiplier fires only when a node and at least two neighbours are elevated for
the same hazard. WARNING and CRITICAL results raise plain-English alerts with
practical playbooks (clear drains, open a cooling room, move outdoor PE). A
seven-tab dashboard shows a live risk map, network overview, per-node
explanations, AI explainability, evidence export, hardware readiness and the
pitch, and every panel carries a provenance badge so simulated data is never
mistaken for real. 189 automated tests pass on Python 3.11–3.13 and a single
command, `python scripts/judge_validate.py`, reproduces the evidence. No
physical sensor has been validated yet; the software is honest about that on
every screen.

**How does the project use the Raspberry Pi?**
The Pi 5 is the whole product. It runs the data source (simulator, live API or
a USB Vernier sensor), the scikit-learn anomaly model, the risk engine, the
SQLite database and the Streamlit web dashboard simultaneously, headless.
The 20 nodes are scored in one batch, so a full cycle takes 14 ms on the
64-bit Arm Linux machine in our continuous integration and about 23 ms on a
four-core x86-64 Linux machine; on the Pi 5 itself, which we run but have not
timed, that bounds a cycle at around 100 ms even if the Pi were eight times
slower, about 5 % of the 2-second read interval
(`python scripts/pi_benchmark.py` prints the measured figure for any
machine).

**What problem does it solve and who benefits?**
It helps the people who respond first: a school site manager, a receptionist,
a residents' group. For the streets that official gauges do not cover, it
gives them a risk score they can read at a glance, the reason it is rising,
and three practical things to do right now. It stores no personal data and
needs no subscription, so a school can adopt it without a cloud bill or a
data-protection review.

**What is innovative about it?**
(1) Neighbours as a two-sided trust signal: a cheap node's risk is escalated
(1.2×) only when it and at least two neighbours within 6 km are elevated for
the same hazard, and a node no neighbour agrees with is damped (0.75×) and
reported as a sensor to check rather than as the hazard — so a network of £85
nodes is harder to fool than one expensive sensor.
(2) A bounded, explainable AI layer: an Isolation Forest flags unusual
combinations of readings and names the channels responsible, but can only
amplify graded risk, never create it: with the mesh layer the two compose to
at most 1.8×, so nothing below 33.4/100 on its own sub-scores can ever be
pushed to an alert. (3) A canonical reading contract with provenance:
sensors, live APIs and simulation are interchangeable, and every reading,
panel, alert and exported row carries its source and quality flag, enforced in
code. (4) The whole pipeline, model included, runs offline on one Pi 5 and is
reproducible from a clean copy with a single command.

**What was the hardest part?**
Making an honest system rather than an impressive one: deciding that a reading
may only be called "hardware" after a device physically opens, flagging
derived values as estimated, and recording whether the AI trained on real or
synthetic data. Making the demo fully deterministic, and running the whole
dashboard through an automated test harness, were the other two.

**What did you learn?**
How anomaly detection differs from thresholds; why provenance matters in
safety tooling; how to design a project so a hardware adapter, a simulator and
a web API are drop-in replacements; how to write tests that pin published
claims; and how to run a full ML pipeline on a single-board computer.

**What would you do next?**
Validate one physical Vernier node against its digital twin; calibrate the
thresholds against recorded local flood and heat events; link two or more real
Pi nodes (Wi-Fi first, LoRa later); publish a priced node kit once a real node
has been built and run from it.

**Equipment used:**
Raspberry Pi 5 (4 GB), 27 W USB-C power supply, 32 GB microSD card, case,
all from the competition's starter kit at no cost to us (£85 to replace);
development and continuous integration also on x86-64 and 64-bit Arm Linux
machines. The kit also includes a Vernier Go Direct Weather sensor
(GDX-WTHR), which the code supports over USB; that adapter is tested with a
stand-in device and no reading from the physical sensor has been validated
yet. Software:
Python 3.11+, Streamlit, scikit-learn, pandas, NumPy, Plotly, SQLite.

**Safety statement:**
Low-voltage USB-powered equipment only. No personal data, cameras or
microphones. Emergency scenarios are simulated; alerts are decision support
and defer to official guidance.

**Is it working? What is simulated?**
The complete pipeline runs today. The 20 nodes are simulated or fed by live
Open-Meteo data; the physical-sensor path is implemented and tested but not
yet validated on a device. The dashboard labels the source of every value.

**Links:**
Source code, screenshots and this write-up are all in the submitted zip, which
is the definitive version. The project is also published at
https://github.com/Leo-Y-Zhang/ClimateMesh.

**Acknowledgements and help received:**
Streamlit, scikit-learn, pandas, NumPy, Plotly; Open-Meteo (free weather
data); Vernier godirect/gdx; WMO/UNDRR early-warning statistics; NOAA
heat-index formulation. During the final review of the entry we used an AI
coding assistant (Anthropic's Claude), under our direction, for code review
and bug fixes, new tests, the batched anomaly scoring, the offline basemap,
the benchmark script and the Arm CI job, the screenshots, and drafting the
write-up and these answers from the repository's history, which we then read
and corrected; the concept, design and original codebase are our own. No teacher, mentor or other adult wrote any part of the
code or the write-up.
