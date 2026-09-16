"""Re-capture the dashboard screenshots in docs/screenshots/ from the live app.

    python SUBMISSION_PACK/_build/capture_screenshots.py

Runs the engine and the dashboard headlessly, walks the tabs and writes a PNG
per tab, plus the cropped figures the write-up embeds, so every picture in the
entry can be regenerated from the code rather than being a one-off that quietly
goes out of date. Needs the
build extras (``pip install -r SUBMISSION_PACK/_build/requirements-build.txt``)
and Chromium; nothing here is needed to run Climate Mesh itself. Set
``CHROMIUM`` to an existing Chromium binary to use that instead of a
Playwright-managed download.

The terminal screenshots (``terminal-*.png``) are not produced here -- those
are captures of real command output and are left alone.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "docs" / "screenshots"
FIGURES_OUT = ROOT / "SUBMISSION_PACK" / "figures"
CONTROL = ROOT / "data" / "demo_control.json"
PORT = 8599
VIEWPORT = {"width": 1600, "height": 1400}

# (scenario, tab label, output file). The tab label is the visible text, minus
# its emoji, exactly as Streamlit renders it.
SHOTS = [
    ("flood", "Live Map", "live-map-flood-demo.png"),
    ("flood", "Network Overview", "network-overview-flood-demo.png"),
    ("flood", "Node Detail", "node-detail-flood-demo.png"),
    ("flood", "AI Explainability", "ai-explainability-flood-demo.png"),
    ("flood", "Evidence & Validation", "evidence-validation-flood-demo.png"),
    ("flood", "Hardware Readiness", "hardware-readiness-flood-demo.png"),
    ("flood", "Competition Pitch", "competition-pitch-flood-demo.png"),
    ("heatwave", "Live Map", "live-map-heatwave-demo.png"),
    ("heatwave", "Network Overview", "network-overview-heatwave-demo.png"),
]


# Figures for the write-up, cropped to one region of the page rather than the
# whole screen so they stay legible at 12 cm wide on A4.
#   (tab, output file, selector, index, extra element above, viewport width)
# A narrower viewport makes a text-heavy panel render fewer pixels wide, so the
# words come out larger once the figure is scaled to the page.
FIGURES = [
    # Addressed by what they contain: index alone picks up the sidebar, and
    # every tab stays in the DOM, so ":visible" does the rest.
    ("Live Map", "act-now-flood-demo.png",
     'xpath=(//div[@data-testid="stVerticalBlockBorderWrapper"]'
     '[.//*[contains(text(), "Act now")]])[last()]', 0, None, 1180),
    ("Live Map", "live-map-flood-demo-crop.png",
     'div[data-testid="stPlotlyChart"]:visible', 0, None, None),
    # The bar chart alone, not the whole two-column row: at 12 cm wide on A4
    # the row's node labels come out at about three point, which nobody can
    # read.
    ("Network Overview", "network-overview-flood-demo-crop.png",
     'div[data-testid="stPlotlyChart"]:visible', 0, "Risk by node", None),
    ("Node Detail", "node-detail-why-flood-demo.png",
     'div[data-testid="stPlotlyChart"]:visible', 0, "Risk score", 1180),
]

def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_for_port(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _free(port):
            return
        time.sleep(0.4)
    raise RuntimeError(f"nothing came up on port {port} within {timeout:.0f}s")


def _set_scenario(scenario: str) -> None:
    CONTROL.parent.mkdir(parents=True, exist_ok=True)
    CONTROL.write_text(json.dumps({"scenario": scenario}))


def _reset_scroll(page) -> None:
    page.evaluate(
        "document.querySelectorAll('section[data-testid=\"stSidebar\"] "
        "div').forEach(d => d.scrollTop = 0); window.scrollTo(0, 0);")
    page.wait_for_timeout(500)


def _crop(page, filename: str, box: dict) -> None:
    """Write one region of the page.

    Two traps here, both to do with Plotly drawing the map on a WebGL canvas:
    an element screenshot of a canvas comes back blank, and a full-page
    screenshot resizes the viewport, which makes Plotly re-lay-out and no
    longer match the box that was measured. So the figures pass uses a viewport
    tall enough to hold the whole page and clips inside it.
    """
    if box["width"] < 40 or box["height"] < 40:
        raise RuntimeError(f"{filename}: region came out empty ({box})")
    page.screenshot(path=str(FIGURES_OUT / filename), clip=box)


def _pick_node(page, node_id: str) -> None:
    """Choose a node in Node Detail's selectbox by typing its id."""
    page.locator('div[data-testid="stSelectbox"]').first.click()
    page.wait_for_timeout(900)
    page.keyboard.type(node_id, delay=25)
    page.wait_for_timeout(1200)
    page.keyboard.press("Enter")
    page.wait_for_timeout(4000)


def _capture_figures(page) -> None:
    """Crop the write-up's figures straight out of the running dashboard."""
    FIGURES_OUT.mkdir(parents=True, exist_ok=True)
    _set_scenario("flood")
    page.reload(wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(6000)
    page.get_by_text("Offline basemap", exact=False).first.click()
    page.wait_for_timeout(3000)
    # Tall enough for the whole page, so a clip never needs a full-page capture.
    page.set_viewport_size({"width": VIEWPORT["width"], "height": 3200})
    page.wait_for_timeout(3000)
    width = VIEWPORT["width"]
    for tab, filename, selector, index, include_from, narrow in FIGURES:
        wanted = narrow or VIEWPORT["width"]
        if wanted != width:
            page.set_viewport_size({"width": wanted, "height": 3200})
            page.wait_for_timeout(3000)
            width = wanted
        page.get_by_role("tab", name=tab, exact=False).first.click()
        page.wait_for_timeout(2500)
        if tab == "Node Detail":
            _pick_node(page, "REGENTS-CANAL")
        _reset_scroll(page)
        box = page.locator(selector).nth(index).bounding_box()
        if box is None:
            raise RuntimeError(f"{filename}: {selector}[{index}] has no box")
        if include_from:
            above = page.get_by_text(include_from, exact=True).first.bounding_box()
            if above and above["y"] < box["y"]:
                box = {"x": box["x"], "y": above["y"] - 10,
                       "width": box["width"],
                       "height": box["y"] + box["height"] - above["y"] + 20}
        _crop(page, filename, box)
        print(f"  wrote figures/{filename}"
              f"  ({box['width']:.0f}x{box['height']:.0f})")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed — see requirements-build.txt",
              file=sys.stderr)
        return 1
    if shutil.which("streamlit") is None and not (
            Path(sys.executable).parent / "streamlit").exists():
        print("streamlit is not installed in this interpreter", file=sys.stderr)
        return 1
    if not _free(PORT):
        print(f"port {PORT} is already in use", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    engine = subprocess.Popen(
        [sys.executable, "run.py", "--mode", "demo", "--scenario", "flood",
         "--judge-mode"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard/app.py",
         "--server.port", str(PORT), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    written: list[str] = []
    try:
        _wait_for_port(PORT)
        time.sleep(6)  # let the engine write a few frames before the first shot
        with sync_playwright() as pw:
            # CHROMIUM (the same variable build_writeup.py reads) lets a
            # machine with Chromium already on disk skip `playwright install`.
            exe = os.environ.get("CHROMIUM")
            browser = (pw.chromium.launch(executable_path=exe) if exe
                       else pw.chromium.launch())
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
            page.goto(f"http://127.0.0.1:{PORT}", wait_until="networkidle",
                      timeout=90_000)
            page.wait_for_timeout(4000)
            # Tile-free basemap: the map a Pi with no internet actually draws.
            page.get_by_text("Offline basemap", exact=False).first.click()
            page.wait_for_timeout(2500)
            # Clicking the checkbox scrolled the sidebar to the bottom; put it
            # back so the scenario buttons are in the picture.
            page.evaluate(
                "document.querySelectorAll('section[data-testid=\"stSidebar\"] "
                "div').forEach(d => d.scrollTop = 0); window.scrollTo(0, 0);")
            page.wait_for_timeout(800)
            current = "flood"
            for scenario, tab, filename in SHOTS:
                if scenario != current:
                    _set_scenario(scenario)
                    page.reload(wait_until="networkidle", timeout=90_000)
                    page.wait_for_timeout(6000)
                    current = scenario
                page.get_by_role("tab", name=tab, exact=False).first.click()
                page.wait_for_timeout(3500)
                page.evaluate(
                    "document.querySelectorAll('section[data-testid=\"stSidebar\"] "
                    "div').forEach(d => d.scrollTop = 0); window.scrollTo(0, 0);")
                page.wait_for_timeout(600)
                page.screenshot(path=str(OUT / filename), full_page=True)
                written.append(filename)
                print(f"  wrote {filename}")
            _capture_figures(page)
            browser.close()
    finally:
        for proc in (app, engine):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        _set_scenario("normal")
    print(f"\n{len(written)} screenshot(s) written to {OUT}")
    return 0 if len(written) == len(SHOTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
