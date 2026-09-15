# Climate Mesh — submission pack

**Entry:** Climate Mesh, by Luis Yu and Leo Zhang (Years 12–13),
PA Raspberry Pi Competition 2026/27.

This folder is everything needed to submit the entry. The rest of the zip is
the working project itself (code, tests, documentation, screenshots).

## What is in this folder

| File | What it is |
|---|---|
| `WRITEUP.docx` | The written entry, editable in Word or Google Docs. About 2,300 words (excluding the ► boxes) with six figures and four tables. ► Check the competition's word limit; if you must cut, drop the Appendix first, then §12, then the ablation table in §6. |
| `WRITEUP.pdf` | The same entry as a fixed-layout PDF (10 pages), for reading or printing. Regenerate it from the Word file (File → Save As → PDF) after editing. |
| `WRITEUP.md` | The same text in plain Markdown (the source; renders on GitHub). |
| `ENTRY_FORM_ANSWERS.md` | Ready-to-paste answers for the usual entry-form questions, in several lengths. |
| `figures/` | The cropped dashboard figures used in the write-up. |
| `photos/` | The team's real-world photos of the Pi (see the README inside). |

The full set of dashboard screenshots and terminal evidence is in
`../docs/screenshots/`.

## Before submitting: the ► boxes

The write-up contains five marked boxes (►) that only the team can complete
truthfully. Search the Word file for "►" to find them all.

1. **Replace the placeholder photo inside WRITEUP.docx.** Figure 1 is
   currently a grey "PHOTO 1 GOES HERE" box. Open `WRITEUP.docx`, right-click
   the Figure 1 image → *Change Picture* → choose the real photo of the Pi,
   then replace the caption with "Figure 1 — The Raspberry Pi 5 running
   Climate Mesh." Copying the photo into `photos/` only fixes the Markdown
   version. Do not submit while the grey box is there.
2. **§1, the personal reason** for choosing this project (one or two
   sentences, in the students' words).
3. **§7, measurements from the team's own Pi 5** (or an honest note that a
   full run on the Pi has not been completed yet).
4. **§9, Teamwork**: who did what, in the first person; add
   `photos/photo-2-team.jpg` there.
5. **§12, help received**: mentors, tutorials and any AI-assisted tools,
   declared whether or not the form asks.

School and teacher details go only where the entry form itself requires them.
Nothing in this pack names the school or any adult, deliberately. After
editing, save the Word file and re-export the PDF (File → Save As → PDF).

## Ten-minute verification (optional, any computer)

```bash
cd ClimateMesh
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/judge_validate.py
```

The `pip install` line is most of that time (it downloads about 200 MB); the
check itself takes about two minutes. The last command prints a PASS/FAIL
table; the expected result is **PASS (5/5 steps passed)** with **173 passed**
tests, a normal demo cycle at average risk 3.9 with 0 alerts, and a flood
cycle at 50.8 with 10 alerts. `python
scripts/demo_tour.py` shows all five scenarios in about thirty seconds. Both
work with no internet and no sensors. To see the dashboard, run the two
commands at the end of the main `README.md`.

## Honesty note

The project is explicit that no physical sensor has yet been validated and
that all demo data is simulated and labelled as such. That is a deliberate
design feature and is stated in the write-up, on every dashboard panel and in
the README. Please keep it that way in anything submitted.
