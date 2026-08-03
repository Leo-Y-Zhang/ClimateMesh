#!/bin/bash
# Climate Mesh - Raspberry Pi 5 setup script.
#
# This sets up the full pipeline so it runs WITHOUT any physical sensors.
# Hardware support (Vernier Go Direct) is optional and only needed later.
#
# Run:  chmod +x setup_pi.sh && ./setup_pi.sh

set -e

echo "=================================================="
echo "  Climate Mesh - Raspberry Pi setup"
echo "=================================================="

# 1. Python virtual environment + core dependencies.
echo "[1/4] Creating virtual environment and installing core dependencies..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. Quick verification that the system runs with no sensors.
echo "[2/4] Running smoke test (no sensors required)..."
python scripts/smoke_test.py

# 3. Optional hardware extras (safe to skip if you have no sensors yet).
echo "[3/4] Hardware sensors are OPTIONAL."
echo "      To enable a physical Vernier Go Direct Weather sensor later, run:"
echo "         pip install godirect adafruit-blinka adafruit-circuitpython-ads1x15"
echo "         git clone --depth 1 https://github.com/VernierST/godirect-examples.git /tmp/gdx-src"
echo "         cp -r /tmp/gdx-src/python/gdx ./gdx"
echo "      and (for the MQ-7 air-quality channel) enable I2C:  sudo raspi-config nonint do_i2c 0"

# 4. Done.
echo "[4/4] Setup complete."
echo ""
echo "=================================================="
echo "  Ready. To run the demo:"
echo "=================================================="
echo "  Terminal 1:  source .venv/bin/activate && python run.py --mode demo --scenario flood --judge-mode"
echo "  Terminal 2:  source .venv/bin/activate && python -m streamlit run dashboard/app.py"
echo ""
echo "  Other scenarios: normal | flood | heatwave | smog | storm"
echo "  Export evidence: python scripts/export_evidence.py"
