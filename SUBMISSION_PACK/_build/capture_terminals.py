"""Re-render the terminal evidence screenshots from real command output.

    python SUBMISSION_PACK/_build/capture_terminals.py            # all of them
    python SUBMISSION_PACK/_build/capture_terminals.py pytest     # just one

Each picture is produced by actually running the command and drawing exactly
what it printed -- nothing is typed in by hand. That matters because the
write-up points a judge at these as evidence, and a screenshot that has drifted
from the suite it claims to show (192 passed against a 227-test suite, say) is
worse than no screenshot at all.

Needs Pillow only; no browser, no network.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "docs" / "screenshots"

BG = (30, 30, 46)          # sampled from the originals, so new and old match
PROMPT = (137, 220, 235)
BODY = (205, 214, 244)
MUTED = (108, 112, 134)
PAD, LINE, SIZE = 48, 38, 26
HEADER = "ClimateMesh · real terminal output · data source: demo (simulated)"

MONO = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono%s.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-%s.ttf")

# name -> (prompt shown, argv). Kept to the commands the documents cite.
COMMANDS = {
    # No extra -q: pytest.ini already sets it, and a second one becomes -qq,
    # which suppresses the "N passed" line this picture exists to show.
    "pytest": ("pytest", [sys.executable, "-m", "pytest"]),
    "judge_validate": ("python scripts/judge_validate.py",
                       [sys.executable, "scripts/judge_validate.py"]),
    "demo_tour": ("python scripts/demo_tour.py",
                  [sys.executable, "scripts/demo_tour.py"]),
    "smoke": ("python scripts/smoke_test.py",
              [sys.executable, "scripts/smoke_test.py"]),
    "hardware_read": ("python scripts/test_hardware_read.py",
                      [sys.executable, "scripts/test_hardware_read.py"]),
}


def _font(bold: bool = False):
    for template in MONO:
        for suffix in (("-Bold", "Bold") if bold else ("", "Regular")):
            try:
                return ImageFont.truetype(template % suffix, SIZE)
            except OSError:
                continue
    return ImageFont.load_default()


def _strip_ansi(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        if text[i] == "\x1b":
            while i < len(text) and text[i] not in "mK":
                i += 1
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def render(name: str, prompt: str, lines: list[str]) -> Path:
    regular, bold = _font(), _font(bold=True)
    body = [f"$ {prompt}", ""] + lines
    width = max(2016, PAD * 2 + int(max(
        (regular.getlength(line) for line in body), default=0)) + 40)
    height = PAD * 2 + LINE * len(body)
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.text((width - PAD - regular.getlength(HEADER), PAD + 4), HEADER,
              font=regular, fill=MUTED)
    for row, line in enumerate(body):
        draw.text((PAD, PAD + row * LINE), line,
                  font=bold if row == 0 else regular,
                  fill=PROMPT if row == 0 else BODY)
    out = OUT / f"terminal-{name}.png"
    image.save(out)
    return out


def main() -> int:
    wanted = sys.argv[1:] or list(COMMANDS)
    unknown = [w for w in wanted if w not in COMMANDS]
    if unknown:
        print(f"unknown: {', '.join(unknown)}. Known: {', '.join(COMMANDS)}",
              file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUNBUFFERED="1", COLUMNS="100", NO_COLOR="1")
    for name in wanted:
        prompt, argv = COMMANDS[name]
        done = subprocess.run(argv, cwd=ROOT, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines = [_strip_ansi(line).rstrip()
                 for line in done.stdout.splitlines() if line.strip()]
        if not lines:
            print(f"  {name}: produced no output; left alone", file=sys.stderr)
            continue
        out = render(name, prompt, lines)
        print(f"  wrote {out.relative_to(ROOT)} ({len(lines)} lines, "
              f"exit {done.returncode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
