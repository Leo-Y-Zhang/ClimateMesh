"""Idempotent desktop kiosk files, called by setup_pi.sh (standard library only)."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEGIN = "# BEGIN climate-mesh-street"
END = "# END climate-mesh-street"
UNITS = ("climate-mesh-engine.service", "climate-mesh-street.service")


def remove_block(text: str) -> str:
    return re.sub(
        r"\n" + re.escape(BEGIN) + r"\n.*?" + re.escape(END) + r"\n",
        "",
        text,
        flags=re.DOTALL,
    )


def add_block(text: str, command: str, wayfire: bool = False) -> str:
    text = remove_block(text)
    block = f"\n{BEGIN}\n{command}\n{END}\n"
    if wayfire:
        match = re.search(r"^\[autostart\][ \t]*\r?$", text, re.MULTILINE)
        if match:
            return text[: match.end()] + block + text[match.end() :]
        block = f"\n{BEGIN}\n[autostart]\n{command}\n{END}\n"
    return text + block


def systemd_quote(path: Path) -> str:
    # systemd expands percent specifiers even inside quotes.
    return (
        '"'
        + str(path).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        + '"'
    )


def configure(*, uninstall: bool = False, dry_run: bool = False) -> None:
    home = Path.home()
    config = home / ".config"
    state_dir = config / "climate-mesh"
    state_file = state_dir / "kiosk-state.json"
    launcher = state_dir / "street-kiosk.sh"
    unit_dir = config / "systemd/user"
    labwc = config / "labwc/autostart"
    wayfire = config / "wayfire.ini"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}

    def write(path, contents, executable=False):
        print(f"WRITE {path}")
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
            if executable:
                path.chmod(0o755)

    def delete(path):
        print(f"REMOVE {path}")
        if not dry_run:
            path.unlink(missing_ok=True)

    def command(*args):
        print("RUN " + shlex.join(args))
        if not dry_run:
            subprocess.run(args, check=True)

    if uninstall:
        if not state:
            print("No managed kiosk installation found.")
            return
        command("systemctl", "--user", "disable", "--now", *UNITS)
        for path in (unit_dir / UNITS[0], unit_dir / UNITS[1], launcher):
            previous = state["generated"].get(str(path))
            if previous is None:
                delete(path)
            else:
                write(path, previous["text"])
                if not dry_run:
                    path.chmod(previous["mode"])
        for path in (labwc, wayfire):
            if path.exists():
                cleaned = remove_block(path.read_text())
                if not cleaned and not state["existing"][str(path)]:
                    delete(path)
                else:
                    write(path, cleaned)
        delete(state_file)
        command("systemctl", "--user", "daemon-reload")
        return

    if not state:
        state = {
            "existing": {str(p): p.exists() for p in (labwc, wayfire)},
            "generated": {
                str(p): {"text": p.read_text(), "mode": p.stat().st_mode & 0o777}
                if p.exists()
                else None
                for p in (unit_dir / UNITS[0], unit_dir / UNITS[1], launcher)
            },
        }
    write(state_file, json.dumps(state, indent=2) + "\n")
    python = systemd_quote(ROOT / ".venv/bin/python")
    working = systemd_quote(ROOT)
    write(
        unit_dir / UNITS[0],
        f"""[Unit]
Description=Climate Mesh engine

[Service]
WorkingDirectory={working}
ExecStart={python} run.py --mode auto
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
""",
    )
    write(
        unit_dir / UNITS[1],
        f"""[Unit]
Description=Climate Mesh street display
After={UNITS[0]}
Wants={UNITS[0]}

[Service]
WorkingDirectory={working}
ExecStart={python} -m streamlit run dashboard/street.py --server.headless true --server.address 127.0.0.1 --server.port 8502
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
""",
    )
    browser = shutil.which("chromium-browser") or shutil.which("chromium") or "chromium"
    flags = (
        "--kiosk --noerrdialogs --disable-infobars --incognito "
        "--check-for-update-interval=31536000 http://127.0.0.1:8502"
    )
    write(
        launcher,
        f"""#!/bin/bash
set -euo pipefail
# Wait at most 60 seconds; do not open an error page before Streamlit starts.
for ((attempt=0; attempt<60; attempt++)); do
    if (echo > /dev/tcp/127.0.0.1/8502) 2>/dev/null; then
        exec {shlex.quote(browser)} {flags}
    fi
    sleep 1
done
echo 'Climate Mesh street display did not open port 8502 within 60 seconds.' >&2
exit 1
""",
        executable=True,
    )
    write(
        labwc,
        add_block(
            labwc.read_text() if labwc.exists() else "",
            shlex.quote(str(launcher)) + " &",
        ),
    )
    # Wayfire invokes autostart commands through a shell.
    write(
        wayfire,
        add_block(
            wayfire.read_text() if wayfire.exists() else "",
            "climate_mesh_street = " + shlex.quote(str(launcher)),
            True,
        ),
    )
    command("systemctl", "--user", "daemon-reload")
    command("systemctl", "--user", "enable", "--now", *UNITS)
    print(
        "Desktop autologin is required. Run: sudo raspi-config nonint do_boot_behaviour B4"
    )
    print("Disable screen blanking: sudo raspi-config nonint do_blanking 1")
    print("No loginctl enable-linger is needed for desktop autologin.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    configure(uninstall=args.uninstall, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
