# Real-world photos

## The easy way

One command takes the photos straight from the phone files, wherever they are:

```bash
pip install -r SUBMISSION_PACK/_build/requirements-build.txt   # once
playwright install chromium                                    # once, ~130 MB
python SUBMISSION_PACK/_build/add_photos.py --pi PI.jpg --team TEAM.jpg
```

It renames, rotates, resizes and compresses each photo for you, strips its
metadata (phone cameras embed GPS coordinates, the device model, a serial
number and a timestamp), writes the real caption into the write-up, sizes the
picture to fit the page, and rebuilds `WRITEUP.docx` and `WRITEUP.pdf`. Either
photo can be given on its own, and it prints exactly what it removed.

JPEG and PNG always work. iPhone `.HEIC` files work once `pillow-heif` is
installed (it is in that requirements file); if it is not, the command says so
and tells you how to export a JPEG instead.

## What to photograph

| Figure | What to photograph |
|---|---|
| Figure 1 (`--pi`) | The Raspberry Pi 5 with the engine or dashboard visible on a screen next to it. Run `python run.py --mode demo --scenario flood --judge-mode` on the Pi for the shot. |
| Figure 6 (`--team`) | Luis and Leo working on the project at the Pi. |
| Optional | The Vernier Go Direct Weather sensor plugged into the Pi, only if you have one. Do not stage a sensor you do not have. |

Good light, phone camera is fine. Landscape frames a little better on the
page, but portrait works: the tool sizes either to the same height.

## By hand instead

Copy the files into this folder as `photo-1-pi-running.jpg` and
`photo-2-team.jpg`, then open `WRITEUP.docx`, right-click each grey box →
*Change Picture*, and replace the caption text (which currently spells out the
instructions) with the wording printed inside the box. Copying files into this
folder only updates the Markdown version, so the Word step is not optional.
Strip the photos' metadata first if you go this way: on a phone, share the
photo with location turned off; on a computer, "Remove properties and personal
information" (Windows) or export a copy (macOS Preview).
