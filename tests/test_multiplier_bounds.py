"""The published safety bound, pinned.

§3 claims the AI and mesh layers compose to at most 1.8x, so a node below
33.4/100 on its own sub-scores can never be pushed to WARNING and one below
44.5 can never reach CRITICAL. That is a property of the engine, so it is
tested as one rather than asserted in prose.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai.anomaly_model import AnomalyDetector
from backend.risk_engine import (_MESH_MULTIPLIER, _UNCORROBORATED_MULTIPLIER,
                                 CRITICAL, WARNING, risk_level)

DESIGN_AI_CEILING = 1.5
COMBINED_CEILING = DESIGN_AI_CEILING * _MESH_MULTIPLIER          # 1.8
WARNING_FLOOR = 60.0 / COMBINED_CEILING                          # 33.4
CRITICAL_FLOOR = 80.0 / COMBINED_CEILING                         # 44.5


@pytest.fixture(scope="module")
def detector():
    return AnomalyDetector().train(quiet=True)


def test_no_quiet_node_can_be_pushed_to_an_alert():
    """Sweep every base score: below the floor, no multiplier can reach a band."""
    for base in np.arange(0.0, 100.0, 0.1):
        worst = min(100.0, base * COMBINED_CEILING)
        if base < WARNING_FLOOR:
            assert risk_level(round(worst, 1)) not in (WARNING, CRITICAL), base
        if base < CRITICAL_FLOOR:
            assert risk_level(round(worst, 1)) != CRITICAL, base


def test_the_ai_multiplier_stays_inside_its_design_ceiling(detector):
    """Over a grid far wider than physically possible, never above 1.5x."""
    rng = np.random.default_rng(20260915)
    lo = np.array([-50, 0, -50, 0, 0, -60, -60, 850])
    hi = np.array([120, 100, 600, 15, 80, 120, 120, 1100])
    grid = rng.uniform(lo, hi, size=(4000, 8))
    readings = [dict(zip(("temperature", "humidity", "air_quality", "water_level",
                          "wind_speed", "wind_chill", "heat_index",
                          "barometric_pressure"), row)) for row in grid]
    verdicts = detector.predict_many(readings)
    multipliers = np.array([1.0 + v["score"] * 0.5 if v["is_anomaly"] else 1.0
                            for v in verdicts])
    assert multipliers.max() <= DESIGN_AI_CEILING
    flagged = multipliers[multipliers > 1.0]
    # The measured range quoted in §3.
    assert 1.20 <= flagged.min() <= 1.30
    assert 1.30 <= flagged.max() <= 1.40


def test_damping_is_mild_enough_to_leave_a_real_local_event_visible():
    """A genuinely severe lone reading must still be able to reach WARNING."""
    assert 100.0 * _UNCORROBORATED_MULTIPLIER >= 60.0
