"""Exercise the actual shell entry point with offline setup/service stubs."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("bash"),
    reason="Pi kiosk requires bash on a Unix desktop; unavailable on Windows",
)


def run_setup(tmp_path, monkeypatch, *args):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return subprocess.run(
        ["bash", str(ROOT / "setup_pi.sh"), "--kiosk", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_kiosk_dry_run_writes_nothing(tmp_path, monkeypatch):
    result = run_setup(tmp_path, monkeypatch, "--dry-run")
    assert result.returncode == 0, result.stderr
    for name in (
        "systemd/user/climate-mesh-engine.service",
        "systemd/user/climate-mesh-street.service",
        "labwc/autostart",
        "wayfire.ini",
        "climate-mesh/street-kiosk.sh",
    ):
        assert name in result.stdout
    assert "systemctl --user enable --now" in result.stdout
    assert "do_boot_behaviour B4" in result.stdout
    assert not list((tmp_path / "home").iterdir())
    assert not (tmp_path / ".venv").exists()


@pytest.mark.parametrize(
    "original_wayfire",
    [
        "",
        "[autostart]\nother = keep\n[core]\nplugins = keep\n",
        "[core]\nplugins = keep",
    ],
)
def test_install_twice_uninstall_restores_files(
    tmp_path, monkeypatch, original_wayfire
):
    home = tmp_path / "home"
    (home / ".config/labwc").mkdir(parents=True)
    labwc = home / ".config/labwc/autostart"
    wayfire = home / ".config/wayfire.ini"
    original_labwc = "# existing desktop command\ntrue &"
    labwc.write_text(original_labwc)
    wayfire.write_text(original_wayfire)
    # Stubs perform no installations, no hardware probes, no service operations.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "python3": f"""#!/bin/bash
if [[ "$1" == "-m" ]]; then
    mkdir -p .venv/bin
    touch .venv/bin/activate
    exit 0
fi
exec {sys.executable} "$@"
""",
        "python": "#!/bin/bash\nexit 0\n",
        "pip": "#!/bin/bash\nexit 0\n",
        "systemctl": '#!/bin/bash\necho "$@" >> "$HOME/services.log"\n',
        "loginctl": "#!/bin/bash\nexit 99\n",
    }
    for name, script in stubs.items():
        path = bin_dir / name
        path.write_text(script)
        path.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    for _ in range(2):
        result = run_setup(tmp_path, monkeypatch)
        assert result.returncode == 0, result.stderr
    assert labwc.read_text().count("# BEGIN climate-mesh-street") == 1
    assert wayfire.read_text().count("climate_mesh_street =") == 1
    assert wayfire.read_text().count("[autostart]") == 1
    if "[autostart]" in original_wayfire:
        assert wayfire.read_text().index(
            "climate_mesh_street ="
        ) < wayfire.read_text().index("[core]")
    units = home / ".config/systemd/user"
    assert "--mode auto" in (units / "climate-mesh-engine.service").read_text()
    assert (
        "--server.address 127.0.0.1 --server.port 8502"
        in (units / "climate-mesh-street.service").read_text()
    )
    result = run_setup(tmp_path, monkeypatch, "--uninstall")
    assert result.returncode == 0, result.stderr
    assert labwc.read_text() == original_labwc
    assert wayfire.read_text() == original_wayfire
    assert not list(units.glob("climate-mesh-*.service"))
    assert not (home / ".config/climate-mesh/street-kiosk.sh").exists()
    assert "--user disable --now" in (home / "services.log").read_text()


def test_created_autostarts_removed_on_uninstall(tmp_path, monkeypatch):
    from scripts.pi_kiosk import configure

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    configure()
    configure()
    configure(uninstall=True)
    assert not (tmp_path / ".config/labwc/autostart").exists()
    assert not (tmp_path / ".config/wayfire.ini").exists()


def test_uninstall_restores_replaced_units_and_preserves_other_edits(
    tmp_path, monkeypatch
):
    from scripts.pi_kiosk import configure

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    unit = tmp_path / ".config/systemd/user/climate-mesh-engine.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("# original service\n")
    unit.chmod(0o640)
    configure()
    autostart = tmp_path / ".config/labwc/autostart"
    autostart.write_text(autostart.read_text() + "# added later\n")
    configure(uninstall=True)
    assert unit.read_text() == "# original service\n"
    assert unit.stat().st_mode & 0o777 == 0o640
    assert autostart.read_text() == "# added later\n"
