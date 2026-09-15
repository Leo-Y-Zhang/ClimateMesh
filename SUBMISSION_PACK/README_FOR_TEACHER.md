# Climate Mesh — submission pack

**Entry:** Climate Mesh, by Luis Yu and Leo Zhang (Years 12–13),
PA Raspberry Pi Competition 2026/27.

This folder is everything needed to submit the entry. The rest of the zip is
the working project itself (code, tests, documentation, screenshots).

## What is in this folder

| File | What it is |
|---|---|
| `WRITEUP.docx` | The written entry, editable in Word or Google Docs. About 3,000 words of body text (excluding tables, captions and the ► boxes) with six figures and four tables. ► Check the competition's word limit; if you must cut, drop the Appendix first (and the words "its full output is reproduced in the Appendix" in §6), then the ablation table in §6 with the two sentences under it, then the worked examples at the end of §3 (and the "see the Hyde Park example above" clause in the Figure 3 caption). Keep §12 (the declaration of help) whatever else goes. |
| `WRITEUP.pdf` | The same entry as a fixed-layout PDF (about 12 pages; the last holds the demo tour's full output), for reading or printing. The command below rebuilds it; only fall back to Word's File → Save As → PDF if that tooling is not installed, accepting a different layout. |
| `WRITEUP.md` | The same text in plain Markdown (the source; renders on GitHub). |
| `ENTRY_FORM_ANSWERS.md` | Ready-to-paste answers for the usual entry-form questions, in several lengths. |
| `figures/` | The cropped dashboard figures used in the write-up. |
| `photos/` | Grey placeholders for the team's real-world photos; replace them before submitting (see the README inside). |
| `_build/` | Tooling that regenerates the Word and PDF files from `WRITEUP.md` (stylesheet, Word template, script). Not needed for submission; editing the Word file directly is fine. |

The full set of dashboard screenshots and terminal evidence is in
`../docs/screenshots/`.

## Before submitting: the ► boxes

The write-up contains two marked places (►), both of them photographs only
the team can take. Search the Word file for "►".

1. **The two photos.** Figures 5 and 6 are grey "PHOTO GOES HERE" boxes.
   The quickest way to replace them, straight from the phone files:

   ```bash
   pip install -r SUBMISSION_PACK/_build/requirements-build.txt   # once
   playwright install chromium                                    # once, ~130 MB
   python SUBMISSION_PACK/_build/add_photos.py --pi PI.jpg --team TEAM.jpg
   ```

   That rotates, resizes and strips each photo's metadata (phone photos carry
   GPS coordinates, the device model and a timestamp), writes the real
   captions, sizes the pictures to the page and rebuilds `WRITEUP.docx` and
   `WRITEUP.pdf`, so nothing needs doing by hand. Either photo can be given on
   its own, and iPhone `.HEIC` files are handled. Do the photos **before** any
   editing in Word: the command regenerates the Word file from `WRITEUP.md`
   (it copies anything newer to `WRITEUP.docx.bak` first). By hand instead:
   see `photos/README.md`. Do not submit while a grey box is there.
2. **§9, Figure 6**: the team photo, handled by the same command (or the
   same manual steps) as Figure 5 in §7.

Nothing else in the write-up needs changing. §1's paragraph on why the team
chose the project is drafted; read it once and change any word that is not
true for you, since it is the one place a judge expects your own voice. §7
gives measured figures from an x86-64 Linux machine and from a 64-bit Arm
Linux machine in the project's continuous integration, plus a clearly
labelled bound for the Pi itself, and §12's declaration of help is complete. If the team ever runs
`python scripts/pi_benchmark.py` on the Pi, the sentence it prints can replace
that bound.

School and teacher details go only where the entry form itself requires
them. Nothing in this pack names the school or any adult, deliberately. After
editing the Markdown, re-run `python SUBMISSION_PACK/_build/build_writeup.py`
to regenerate both files; after editing the Word file directly, re-export the
PDF from Word (File → Save As → PDF).

## Ten-minute verification (optional, any computer)

```bash
cd ClimateMesh
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/judge_validate.py
```

The `pip install` line is most of that time (it downloads about 200 MB); the
check itself takes about two minutes. The last command prints a PASS/FAIL
table; the expected result is **PASS (5/5 steps passed)** with **189 passed**
tests, a normal demo cycle at average risk 3.9 with 0 alerts, and a flood
cycle at 50.8 with 10 alerts. Running `python scripts/demo_tour.py` shows all
five scenarios in a few seconds. Both work with no internet and no
sensors. To see the dashboard, run the two
commands at the end of the main `README.md`.

## What this zip says about you

The only personal information anywhere in it is the two names on the cover.
Checked before packaging:

- No school, teacher, email address, username or handle appears in any file,
  and no machine name or file path from any computer used to build it.
- The Word file's properties carry only the title and the two names. The
  PDF's metadata fields are empty.
- Every image ships with its metadata stripped. Phone photos normally carry
  GPS coordinates, the device model and a timestamp;
  `_build/add_photos.py` removes all of that when it puts the team's photos
  in, and the screenshots were generated with none.
- The project stores no personal data at all: no accounts, no cameras, no
  microphones, no location tracking. Its only outbound call is to the free
  Open-Meteo weather service, which needs no key and no account.
- The dashboard has no login, so it listens on `127.0.0.1` only and is never
  put on a school network; watch it from another computer over an SSH tunnel
  (the main `README.md` gives the command).

School and teacher details belong on the entry form and nowhere else.

## Honesty note

The project is explicit that no physical sensor has yet been validated and
that all demo data is simulated and labelled as such. That is a deliberate
design feature and is stated in the write-up, on every dashboard panel and in
the README. Please keep it that way in anything submitted.
