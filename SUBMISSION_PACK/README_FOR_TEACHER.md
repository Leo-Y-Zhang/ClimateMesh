# Climate Mesh — submission pack

**Entry:** Climate Mesh, by Luis Yu and Leo Zhang (Years 12–13),
PA Raspberry Pi Competition 2026/27.

This folder is everything needed to submit the entry. The rest of the zip is
the working project itself (code, tests, documentation, screenshots).

## What is in this folder

| File | What it is |
|---|---|
| `WRITEUP.docx` | The written entry, editable in Word or Google Docs. About 2,900 words of body text (excluding tables, captions and the ► boxes) with six figures and four tables. ► Check the competition's word limit; if you must cut, drop the Appendix first, then the ablation table in §6, then the worked examples at the end of §3. Keep §12 (the declaration of help) whatever else goes. |
| `WRITEUP.pdf` | The same entry as a fixed-layout PDF (11 pages), for reading or printing. Regenerate it from the Word file (File → Save As → PDF) after editing. |
| `WRITEUP.md` | The same text in plain Markdown (the source; renders on GitHub). |
| `ENTRY_FORM_ANSWERS.md` | Ready-to-paste answers for the usual entry-form questions, in several lengths. |
| `figures/` | The cropped dashboard figures used in the write-up. |
| `photos/` | The team's real-world photos of the Pi (see the README inside). |
| `_build/` | Tooling that regenerates the Word and PDF files from `WRITEUP.md` (stylesheet, Word template, script). Not needed for submission; editing the Word file directly is fine. |

The full set of dashboard screenshots and terminal evidence is in
`../docs/screenshots/`.

## Before submitting: the ► boxes

The write-up contains three marked places (►) that only the team can complete
truthfully. Search the Word file for "►".

1. **Replace the placeholder photo inside WRITEUP.docx.** Figure 1 is
   currently a grey "PHOTO 1 GOES HERE" box. Open `WRITEUP.docx`, right-click
   the Figure 1 image → *Change Picture* → choose the real photo of the Pi,
   then replace the caption with "Figure 1 — The Raspberry Pi 5 running
   Climate Mesh." Copying the photo into `photos/` only fixes the Markdown
   version. Do not submit while the grey box is there.
2. **§1, the personal reason** for choosing this project (one or two
   sentences, in the students' words).
3. **§9, Figure 6**: replace the grey placeholder with the team photo
   (`photos/photo-2-team.jpg`) inside the Word file, as for Figure 1.

Nothing else in the write-up needs changing: §7 gives measured laptop figures
and a clearly labelled estimate for the Pi, and §12's declaration of help is
complete. If the team later runs `python scripts/pi_benchmark.py` on the Pi,
the sentence it prints can replace the estimate in §7.

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
cycle at 50.8 with 10 alerts. Running `python scripts/demo_tour.py` shows all
five scenarios in about thirty seconds. Both work with no internet and no
sensors. To see the dashboard, run the two
commands at the end of the main `README.md`.

## Honesty note

The project is explicit that no physical sensor has yet been validated and
that all demo data is simulated and labelled as such. That is a deliberate
design feature and is stated in the write-up, on every dashboard panel and in
the README. Please keep it that way in anything submitted.
