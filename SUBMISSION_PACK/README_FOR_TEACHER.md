# Climate Mesh — submission pack

**Entry:** Climate Mesh, by Luis Yu and Leo Zhang (Years 12–13),
PA Raspberry Pi Competition 2026/27.

This folder is everything needed to submit the entry. The rest of the zip is
the working project itself (code, tests, documentation, screenshots).

## What is in this folder

| File | What it is |
|---|---|
| `WRITEUP.docx` | The written entry, editable in Word or Google Docs. About 1,800 words with five figures. |
| `WRITEUP.md` | The same text in plain Markdown (the source; renders on GitHub). |
| `ENTRY_FORM_ANSWERS.md` | Ready-to-paste answers for the usual entry-form questions, in several lengths. |
| `figures/` | The cropped dashboard figures used in the write-up. |
| `photos/` | The team's real-world photos of the Pi (see the README inside). |

The full set of dashboard screenshots and terminal evidence is in
`../docs/screenshots/`.

## Before submitting, please check the three ► markers

The write-up and the form answers contain three marked places that only the
team can complete truthfully:

1. **Teamwork section** (`WRITEUP.md` §9): who did what.
2. **Acknowledgements** (§12 and the form answers): any mentors, tutorials or
   AI-assisted tools, if the rules ask for that declaration.
3. **School/teacher details** where the entry form requires them. Nothing in
   this pack names the school or any adult, deliberately.

Also drop the real-world photos into `photos/` using the file names listed
there; Figure 1 of the write-up points at `photos/photo-1-pi-running.jpg`.

## Two-minute verification (optional, any computer)

```bash
cd ClimateMesh
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/judge_validate.py
```

The last command prints a PASS/FAIL table; the expected result is
**PASS (5/5 steps passed)** with **166 passed** tests. `python
scripts/demo_tour.py` shows all five scenarios in about thirty seconds. Both
work with no internet and no sensors. To see the dashboard, run the two
commands at the end of the main `README.md`.

## Honesty note

The project is explicit that no physical sensor has yet been validated and
that all demo data is simulated and labelled as such. That is a deliberate
design feature and is stated in the write-up, on every dashboard panel and in
the README. Please keep it that way in anything submitted.
