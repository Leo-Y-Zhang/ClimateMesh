# Climate Mesh — Hardware Integration Plan

Climate Mesh is **sensor-ready, not sensor-dependent**. The full pipeline runs
today on simulated and live-API data; physical sensors are a clean drop-in for
the future. **No physical sensors are connected yet.** This document explains why
adding them is straightforward and exactly what we will do when they arrive.

## The canonical-reading contract (why it's a drop-in)

Every data source — simulated, live-API or physical — emits the **same canonical
reading shape**:

```text
node_id, node_name, environment, latitude, longitude,
temperature, humidity, air_quality, water_level, wind_speed,
wind_chill, heat_index, barometric_pressure,
source, is_simulated, quality_flag, scenario, timestamp
```

Because the risk engine, dashboard and evidence scripts only ever see this
shape, the source behind it is interchangeable. The `source`, `is_simulated` and
`quality_flag` fields keep us honest about where each number came from. Adapters
live in `sensors/`: `base.py` (the contract), `simulated_adapter.py`,
`api_adapter.py`, `vernier_adapter.py` and `hardware_status.py`.

## The Vernier USB pathway (already implemented)

The physical pathway is already written in `sensors/vernier_adapter.py` for the
**Vernier Go Direct Weather sensor (GDX-WTHR)** over USB. It reads temperature,
humidity, barometric pressure and wind, and maps them into the canonical fields.
Until a device is present, `hardware` mode runs this single physical node over a
**simulated mesh** and falls back gracefully if no sensor is detected.

### Optional air-quality channel
For air quality we plan an **MQ-7 carbon-monoxide sensor via an ADS1115 ADC**
(I²C) feeding the canonical `air_quality` field, giving the river/urban nodes a
genuine pollution reading.

## Steps when the sensors arrive

1. Install the driver: `pip install godirect`.
2. Place the `gdx/` helper module alongside the adapter.
3. Connect the GDX-WTHR to the Raspberry Pi 5 over **USB**.
4. (Optional) Wire the MQ-7 + ADS1115 on the I²C bus.
5. Run:
   ```bash
   python run.py --mode hardware
   ```
6. Confirm the **Hardware Readiness** dashboard tab shows the device as detected
   and emitting canonical readings.

## Validation against the digital twin

The physical node does not replace the simulation — it is checked against it. We
run the live hardware node alongside its simulated **digital twin** for the same
location and compare readings using `python scripts/run_validation.py`. Close
agreement validates the sensor; large divergence flags a fault or a real
environmental event worth investigating.

## The sensor-swap promise

**Any device that emits the standard canonical reading shape can join the mesh.**
We are not locked to one vendor: future **GDX-CO2** (carbon dioxide) and
**GDX-WQ** (water-quality) Vernier sensors are simply further channels — write a
small adapter that outputs the canonical fields, and the new node appears on the
map, scores through the same risk engine and exports through the same evidence
scripts. No changes to the core are required.
