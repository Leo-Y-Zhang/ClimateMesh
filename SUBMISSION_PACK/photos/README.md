# Real-world photos

Put the team's photos in this folder with these exact file names, so the
write-up's figure links resolve:

| File name | What to photograph |
|---|---|
| `photo-1-pi-running.jpg` | The Raspberry Pi 5 with the engine or dashboard visible on a screen next to it (run `python run.py --mode demo --scenario flood --judge-mode` on the Pi for the shot). Used as Figure 1 in the write-up. |
| `photo-2-team.jpg` | Luis and Leo working on the project at the Pi. |
| `photo-3-sensor.jpg` | Only if you have one: the Vernier Go Direct Weather sensor plugged into the Pi. Do not stage a sensor you do not have. |

Landscape orientation, good light, phone camera is fine. Keep each file under
about 3 MB (resize to roughly 2000 px wide if needed).

One command does all of this for you, from the phone files, wherever they
are:

```bash
python SUBMISSION_PACK/_build/add_photos.py --pi PI.jpg --team TEAM.jpg
```

It strips each photo's metadata (phone cameras embed GPS coordinates, the
device name and a date), resizes it, saves it here under the right name,
writes the real caption into the write-up and rebuilds `WRITEUP.docx` and
`WRITEUP.pdf`. Either photo can be given on its own.

By hand instead: copy the files here under the names above, then change the
pictures inside `WRITEUP.docx` too (right-click the Figure 1 placeholder →
Change Picture; insert `photo-2-team.jpg` in §9). Copying files into this
folder only updates the Markdown version.
