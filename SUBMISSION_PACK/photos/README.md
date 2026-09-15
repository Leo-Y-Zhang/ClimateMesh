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
| Figure 5 (`--pi`) | The Raspberry Pi 5 with the engine or dashboard visible on a screen next to it. Run `python run.py --mode demo --scenario flood --judge-mode` on the Pi for the shot. |
| Figure 6 (`--team`) | Luis and Leo working on the project at the Pi. |
| Optional | The Vernier Go Direct Weather sensor plugged into the Pi, only if you have one. Do not stage a sensor you do not have. |

Good light, phone camera is fine. Landscape frames a little better on the
page, but portrait works: the tool sizes either to the same height.

## How to take them so they look professional

A judge reads the caption against the picture, so the first rule is accuracy:
the screen must be showing what the caption says it is. Set the scene up for
real, then photograph it.

**Before you shoot.** On the Pi, start the deterministic flood demo so the
numbers on screen are the ones the write-up quotes:

```bash
python run.py --mode demo --scenario flood --judge-mode      # terminal 1
python -m streamlit run dashboard/app.py                     # terminal 2
```

Open the Live Map (the four river nodes go red) or Node Detail for Regent's
Canal (the "Why:" sentence and the sub-score bars — the single most
impressive screen, because it shows the explanation, not just a number). The
purple **Digital Twin (Demo)** badge should be visible: being seen to label
your own data is the whole argument of the entry.

**Photo 1, the Pi.**

- Put the Pi in the foreground, close enough to fill a third of the frame, with
  the screen behind or beside it. Both need to be sharp, so keep them roughly
  the same distance from the camera and step back rather than leaning in.
- Turn portrait mode and flash **off**. Portrait mode blurs whichever one it
  decides is background; flash puts a white hotspot on the screen.
- Screens photograph badly: wipe the screen, set its brightness to about 70 %
  rather than maximum, dim any lamp that is reflecting in it, and shoot from
  slightly off-axis so you are not mirrored in the glass. Tap the screen to
  focus, check the text is readable when you zoom into the shot, and retake if
  it is not.
- Show the USB-C power lead and the case fan — small details that tell a judge
  this is a real board doing real work, not a stock photo.
- Tidy the desk. Anything with your school's name, a letter, a timetable or a
  name label should be out of frame.

**Photo 2, the two of you.**

- Be doing something: one of you typing, the other pointing at a reading on the
  screen. Two people smiling at the lens reads as staged; the Inspiration Award
  is about endeavour, so let the picture show work happening.
- Frame from about the waist up, camera at the seated person's eye level, with
  the Pi or the dashboard clearly in shot so it is obviously this project.
- Light your faces from the front. A window behind you turns you into
  silhouettes.
- If you do not want the school identifiable, keep crested blazers, lanyards
  and name badges out of the frame. Nothing else in this pack names it.

**Both.** Landscape, clean the lens first, brace your elbows on the desk, and
take eight or ten of each so you can pick the sharpest. Send them straight
off the phone: do not crop, filter or resize, because the tool does all of
that and editing apps add metadata of their own.

**Do not stage what is not true.** No sensor you do not own, and no screen
showing a scenario the caption does not claim. The entry wins on being honest
about exactly this.

## By hand instead

Copy the files into this folder as `photo-1-pi-running.jpg` and
`photo-2-team.jpg`, then open `WRITEUP.docx`, right-click each grey box →
*Change Picture*, and replace the caption text (which currently spells out the
instructions) with the wording printed inside the box. Copying files into this
folder only updates the Markdown version, so the Word step is not optional.
Strip the photos' metadata first if you go this way: on a phone, share the
photo with location turned off; on a computer, "Remove properties and personal
information" (Windows) or export a copy (macOS Preview).
