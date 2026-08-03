"""Simulated / demo sensor adapter.

Wraps the data-generation engine and emits canonical readings for all 20
nodes. Used by both ``simulation`` mode (source="simulation") and
``demo``/``judge`` mode (source="demo", deterministic output).
"""

from __future__ import annotations

from config.nodes import NODES_BY_ID
from sensors.base import SensorAdapter, make_reading
from simulation.engine import generate_all


class SimulatedAdapter(SensorAdapter):
    """Offline, realistic generated data for every node — no internet, no sensors."""

    def __init__(self, *, demo: bool = False, seed: int = 1234):
        # demo=True -> deterministic, screenshot-stable output and source="demo".
        self.demo = demo
        self.seed = seed
        self.source = "demo" if demo else "simulation"

    def read_all(self, scenario: str = "none", tick: float = 0.0) -> list[dict]:
        channels_by_node = generate_all(
            tick, scenario, deterministic=self.demo, seed=self.seed
        )
        readings = []
        for node_id, channels in channels_by_node.items():
            node = NODES_BY_ID[node_id]
            readings.append(make_reading(
                node,
                source=self.source,
                quality_flag="ok",
                scenario=scenario or "none",
                **channels,
            ))
        return readings
