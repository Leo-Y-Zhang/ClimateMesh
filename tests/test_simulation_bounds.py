"""Regression guards for the generation engine's safety invariants.

These lock in two behaviours that must never silently break: every channel
stays inside its physical clamp, and an unrecognised scenario name is a no-op
(it never invents an effect or raises).
"""

from __future__ import annotations

import pytest

from simulation.engine import _CLAMP, generate_all
from simulation.scenarios import SCENARIOS


def test_generated_channels_respect_hard_clamps():
    # Sweep every scenario, a wide range of ticks, and all 20 nodes — including
    # the mesh-correlation pass — and assert no channel leaves its clamp.
    for scenario in SCENARIOS:
        for tick in (0.0, 3.0, 12.0, 40.0, 123.5):
            for channels in generate_all(tick, scenario, deterministic=True).values():
                for channel, (lo, hi) in _CLAMP.items():
                    assert lo <= channels[channel] <= hi, (scenario, tick, channel)


def test_unknown_scenario_applies_no_delta():
    # An unrecognised scenario name must behave exactly like the calm baseline:
    # no disaster delta, no exception, no invented effect.
    baseline = generate_all(0.0, "normal", deterministic=True)
    unknown = generate_all(0.0, "does-not-exist", deterministic=True)
    assert unknown.keys() == baseline.keys()
    for nid in baseline:
        for channel in _CLAMP:
            assert unknown[nid][channel] == pytest.approx(baseline[nid][channel])
