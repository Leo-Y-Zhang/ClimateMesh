"""Optional local demo PNGs; skips cleanly without Playwright/Chromium installed."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIZES = ((800, 480), (720, 1280), (1280, 720), (1920, 1080))


def main() -> int:
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        print("SKIPPED: Playwright is not installed; no screenshots produced.")
        return 0
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error:
            print(
                "SKIPPED: Playwright Chromium is not installed; no screenshots produced."
            )
            return 0
        control = ROOT / "data/demo_control.json"
        previous = control.read_bytes() if control.exists() else None
        processes = []
        try:
            with (
                tempfile.TemporaryDirectory(prefix="climate-mesh-street-") as tmp,
                tempfile.TemporaryFile() as log,
            ):
                env = dict(os.environ, CLIMATE_MESH_DB=str(Path(tmp) / "demo.db"))
                # Choose an unused loopback port rather than interrupt an existing kiosk.
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "run.py",
                            "--mode",
                            "demo",
                            "--scenario",
                            "flood",
                            "--judge-mode",
                        ],
                        cwd=ROOT,
                        env=env,
                        stdout=log,
                        stderr=log,
                    )
                )
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "streamlit",
                            "run",
                            "dashboard/street.py",
                            "--server.headless",
                            "true",
                            "--server.address",
                            "127.0.0.1",
                            "--server.port",
                            str(port),
                        ],
                        cwd=ROOT,
                        env=env,
                        stdout=log,
                        stderr=log,
                    )
                )
                url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 60
                while True:
                    try:
                        with urllib.request.urlopen(
                            url + "/_stcore/health", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        pass
                    if time.monotonic() > deadline or any(
                        p.poll() is not None for p in processes
                    ):
                        raise RuntimeError("Demo engine or street server did not start")
                    time.sleep(0.25)
                output = ROOT / "docs/screenshots"
                output.mkdir(parents=True, exist_ok=True)
                for width, height in SIZES:
                    page = browser.new_page(
                        viewport={"width": width, "height": height},
                        device_scale_factor=1,
                    )
                    page.goto(
                        url + "/?node=REGENTS-CANAL", wait_until="domcontentloaded"
                    )
                    page.locator(".band h1").wait_for(timeout=60000)
                    # Capture exactly the physical screen, and detect horizontal overflow.
                    if page.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth"
                    ):
                        raise RuntimeError(f"Horizontal overflow at {width}x{height}")
                    target = output / f"street-{width}x{height}-demo.png"
                    page.screenshot(path=str(target))
                    print(target.relative_to(ROOT))
                    page.close()
        finally:
            for proc in processes:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if previous is None:
                control.unlink(missing_ok=True)
            else:
                control.write_bytes(previous)
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
