# Climate Mesh — Vernier Hardware Driver Setup

This is the exact, reproducible setup for the **one physical node** (a Vernier
**Go Direct Weather** sensor, model **GDX-WTHR**, over USB). Climate Mesh is
**sensor-ready, not sensor-dependent** — the full pipeline runs without any of
this. Follow it only when you actually connect a sensor.

> **Honesty note:** installing these libraries does *not* make the dashboard
> claim hardware data. A node emits `source="hardware"` **only** after
> `VernierAdapter` opens a real device and reads it. Verify with
> `python scripts/test_hardware_read.py`, which prints **REAL HARDWARE** or
> **FALLBACK SIMULATION**.

## Which package and which module (the part that confuses people)

There are **two different things** with similar names, and you need both:

| Thing | What it is | How you get it |
|-------|-----------|----------------|
| **`godirect`** | The low-level Vernier Go Direct driver. A real PyPI package. | `pip install godirect` |
| **`gdx`** | Vernier's high-level helper *module* (`gdx.py`) that wraps `godirect`. **Not on PyPI.** | Copied from Vernier's `godirect-examples` repo |

The adapter (`sensors/vernier_adapter.py`) imports the **helper**:

```python
from gdx import gdx as gdx_module
```

So you need a `gdx/` package folder (containing `gdx.py`) importable on the
Python path — i.e. placed in the project root — **and** the `godirect` package
it depends on installed via pip. Installing only `godirect` is not enough; the
`from gdx import gdx` import will fail until the `gdx/` helper is present.

## Tested Raspberry Pi 5 install (exact commands)

These are the commands `setup_pi.sh` prints, run from the repository root inside
your virtual environment:

```bash
# 1. Low-level Vernier driver + (optional) MQ-7 ADC stack for air quality.
pip install godirect adafruit-blinka adafruit-circuitpython-ads1x15

# 2. The gdx helper module (NOT on PyPI) — copy it into the project root.
git clone --depth 1 https://github.com/VernierST/godirect-examples.git /tmp/gdx-src
cp -r /tmp/gdx-src/python/gdx ./gdx

# 3. (Only for the MQ-7 air-quality channel) enable the I2C bus.
sudo raspi-config nonint do_i2c 0
```

After this, `from gdx import gdx` resolves to `./gdx/gdx.py`, and
`sensors/hardware_status.py` will report the driver library as available. The
`gdx/` folder is intentionally git-ignored (it is a vendored third-party helper,
re-fetched per machine).

## Connect and verify

```bash
# Plug the GDX-WTHR into a USB port and power it on, then:
python scripts/test_hardware_read.py     # prints REAL HARDWARE vs FALLBACK SIMULATION
python run.py --mode hardware            # one physical node over a simulated mesh
```

In the dashboard's **Hardware Readiness** tab the node provenance badge flips to
**📡 Physical Sensor** once a device is actually read.

## "Sensor not detected" troubleshooting

Work through these in order:

1. **`ModuleNotFoundError: No module named 'gdx'`**
   The `gdx/` helper is missing. Re-run step 2 above and confirm `./gdx/gdx.py`
   exists. Run the command from the **project root** so `gdx` is importable.

2. **`No module named 'godirect'`**
   Run `pip install godirect` inside the **same** virtual environment you launch
   `run.py` from (`which python` should point at `.venv/bin/python`).

3. **Driver imports, but no device opens (stays FALLBACK SIMULATION)**
   - Check the USB cable and that the sensor's LED is on (charged/powered).
   - `lsusb` should list the Vernier device.
   - Try a different USB port / cable; some cables are charge-only.
   - On Linux you may need udev permissions: add your user to the `plugdev`
     group, or run once with `sudo` to confirm it is a permissions issue.

4. **`Bluetooth`/`GoDirect` errors**
   This setup uses **USB** (`device.open(connection="usb")`). Bluetooth is not
   required; ignore BLE backend warnings.

5. **Air-quality channel (MQ-7 + ADS1115) not found**
   - Enable I2C (`sudo raspi-config nonint do_i2c 0`) and reboot.
   - `i2cdetect -y 1` should show the ADS1115 (commonly `0x48`).
   - The weather sensor works **without** this; air quality simply stays an
     `estimated` placeholder on the hardware node.

6. **It still falls back — and that is fine.**
   A missing or unreadable sensor is a *supported, honest* state. The pipeline
   keeps running on clearly-labelled simulated data; nothing is ever presented
   as a physical reading that was not measured.

## What the hardware node measures (and what it does not)

The GDX-WTHR senses **temperature, humidity, barometric pressure, wind speed**
(and derived wind chill / heat index). It does **not** sense **air quality** or
**water level** — those two channels remain conservative placeholders, which is
exactly why a genuine hardware reading is flagged `quality_flag="estimated"`
rather than `"ok"`. See `docs/hardware_integration_plan.md` for the optional
MQ-7 air-quality and future water-quality channels.

## Reconciliation summary (so all docs agree)

- **`requirements.txt`** lists `godirect`, `adafruit-blinka`,
  `adafruit-circuitpython-ads1x15` as commented, optional extras.
- **`sensors/vernier_adapter.py`** imports `from gdx import gdx` (the helper).
- **This document** is the single source of truth for getting both pieces in
  place. README and the dashboard Hardware Readiness tab link here.
