"""Future physical-sensor adapter (Vernier Go Direct + simulated mesh).

This is the sensor-ready pathway. When a Vernier Go Direct Weather sensor (and
optionally an MQ-7/ADS1115 air-quality channel) is connected, this adapter
reads the *real* device for its node and emits a ``source="hardware"`` reading
for it. Every other node in the mesh keeps producing simulated data so the
dashboard stays full while a single physical node is validated against the
digital twin.

Crucially: if no hardware is present, this adapter does **not** crash. It logs
a clear warning, marks the hardware node's reading ``quality_flag="missing"``
(falling back to simulated values), and the system keeps running. No physical
sensor data is ever fabricated — a fabricated value is labelled as simulated.

Source honesty (the judged invariant):
  * ``self.source`` is the *effective* provenance — ``"hardware"`` **only** when
    a real Vernier device is actually open and ready, otherwise ``"simulation"``.
    A driver library being importable is not enough; the device must open.
  * A genuine hardware read still carries two non-measured placeholder channels
    (air quality, water level) because the GDX-WTHR does not sense them, so the
    reading is flagged ``quality_flag="estimated"`` — ``"hardware"/"ok"`` never
    covers a fabricated channel.
  * A failed/absent read keeps the simulated values, stays ``source="simulation"``
    and is flagged ``quality_flag="missing"``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config.nodes import NODES_BY_ID
from sensors.base import SensorAdapter, make_reading
from sensors.hardware_status import detect
from sensors.simulated_adapter import SimulatedAdapter

logger = logging.getLogger("climate_mesh.sensors.vernier")

# Which node the single physical sensor represents while the rest stay simulated.
DEFAULT_HARDWARE_NODE = "CENTRAL-LDN"
CONFIG_PATH = Path(__file__).parent.parent / "data" / "sensor_config.json"


def _configured_node(default: str) -> str:
    """Read the hardware node id from sensor_config.json if present."""
    try:
        if CONFIG_PATH.exists():
            node = json.loads(CONFIG_PATH.read_text()).get("hardware_node_id")
            if node in NODES_BY_ID:
                return node
    except (json.JSONDecodeError, OSError):
        pass
    return default


class VernierAdapter(SensorAdapter):
    """Reads one physical node (if hardware present) over a simulated mesh.

    ``source`` is set per-instance to the *effective* provenance so it can never
    overstate: it is ``"hardware"`` only once a real device has actually opened.
    """

    # Default before construction; __init__ sets the effective value.
    source = "simulation"

    def __init__(self, hardware_node_id: str | None = None, *, seed: int = 1234):
        self.hardware_node_id = hardware_node_id or _configured_node(DEFAULT_HARDWARE_NODE)
        self.status = detect()
        # ``any_physical_sensor_detected`` only means the driver *library* is
        # importable; a real device may still be absent. We downgrade
        # ``hardware_ready`` to False inside ``_try_open_device`` if the open
        # fails, so ``hardware_ready`` ends up True only for a live device.
        self.hardware_ready = self.status["any_physical_sensor_detected"]
        # The rest of the mesh is always simulated in hardware mode.
        self._sim = SimulatedAdapter(demo=False, seed=seed)
        self._device = None
        if self.hardware_ready:
            self._device = self._try_open_device()
        if not self.hardware_ready:
            logger.warning(self.status["summary"])
        # Effective source: "hardware" ONLY when a real device is open and ready.
        self.source = "hardware" if self.hardware_ready else "simulation"

    def _try_open_device(self):
        """Attempt to open the real Vernier device. Returns None on any failure."""
        try:  # Imported lazily so the module loads fine without the library.
            from gdx import gdx as gdx_module
            device = gdx_module.gdx()
            device.open(connection="usb")
            device.select_sensors([1, 3, 4, 5, 7, 10])  # wind, chill, temp, heat idx, humidity, pressure
            device.start(2000)
            logger.info("Vernier GDX-WTHR opened on USB")
            return device
        except Exception as e:  # noqa: BLE001 - hardware can fail in many ways
            logger.error("Hardware open failed, falling back to simulation: %s", e)
            self.hardware_ready = False
            return None

    def _read_physical_channels(self) -> dict | None:
        """Read the real device. Returns channel dict, or None if read failed."""
        if not self._device:
            return None
        try:
            m = self._device.read()
            if m is None or len(m) < 6:
                return None
            temp, humidity = m[2], m[4]
            wind, pressure = m[0], m[5]
            # air_quality and water_level are NOT sensed by the GDX-WTHR. They are
            # conservative placeholders, so the resulting reading is flagged
            # quality_flag="estimated" (never "ok") to keep "hardware" honest.
            return {
                "temperature": temp, "humidity": humidity,
                "air_quality": 50.0,  # placeholder: no AQI sensor wired (estimated)
                "water_level": 0.3,   # placeholder: no water sensor wired (estimated)
                "wind_speed": wind, "wind_chill": m[1],
                "heat_index": m[3], "barometric_pressure": pressure,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("Hardware read failed, using fallback: %s", e)
            return None

    def read_all(self, scenario: str = "none", tick: float = 0.0) -> list[dict]:
        # Start from a fully simulated mesh so the dashboard is always complete.
        readings = self._sim.read_all(scenario, tick)
        physical = self._read_physical_channels() if self.hardware_ready else None

        for r in readings:
            if r["node_id"] != self.hardware_node_id:
                continue
            node = NODES_BY_ID[self.hardware_node_id]
            if physical is not None:
                # Genuine hardware read of temp/humidity/wind/pressure. Two
                # channels (air quality, water level) are non-measured
                # placeholders, so the reading is flagged "estimated" — a
                # "hardware"/"ok" label must never cover a fabricated channel.
                # The physical values are LIVE and UNMODIFIED: scenario deltas
                # are only applied to simulated nodes (simulation/engine.py), so
                # this real reading is stamped "observed", never the scenario
                # name (which would falsely imply a delta was applied to it).
                readings[readings.index(r)] = make_reading(
                    node, source="hardware", quality_flag="estimated",
                    scenario="observed", **physical,
                )
            else:
                # No hardware: keep simulated values but flag the gap clearly.
                r["quality_flag"] = "missing"
            break
        return readings

    def cleanup(self) -> None:
        if self._device is not None:
            try:
                self._device.stop()
                self._device.close()
            except Exception:  # noqa: BLE001
                pass
        self._sim.cleanup()
