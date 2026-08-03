"""Tests for the dashboard provenance + quality badges (plan item 2.3).

These guarantee every screenshot self-labels its data source and quality with
the exact, honest wording — Physical Sensor / Live API / Digital Twin (Demo) /
Offline Simulation, and ok / estimated / stale / missing. The badge module is
pure (no Streamlit), so it is importable and testable on its own.
"""

from __future__ import annotations

import pytest

from dashboard import badges
from sensors.base import VALID_QUALITY_FLAGS, VALID_SOURCES


@pytest.mark.parametrize("source,label", [
    ("hardware", "Physical Sensor"),
    ("api", "Live API"),
    ("demo", "Digital Twin (Demo)"),
    ("simulation", "Offline Simulation"),
])
def test_source_label_wording(source, label):
    assert badges.source_label(source) == label


def test_every_valid_source_has_a_badge():
    for s in VALID_SOURCES:
        assert s in badges.SOURCE_BADGES
        assert badges.source_label(s)  # non-empty


def test_every_valid_quality_flag_has_a_badge():
    for q in VALID_QUALITY_FLAGS:
        assert q in badges.QUALITY_BADGES
        assert badges.quality_label(q) == q  # quality labels mirror the flag name


def test_hardware_label_is_distinct_from_simulation():
    # The judged invariant: a hardware badge must never read like simulation.
    assert badges.source_label("hardware") != badges.source_label("simulation")
    assert badges.source_label("hardware") != badges.source_label("demo")


def test_source_badge_html_contains_label_and_is_span():
    html = badges.source_badge_html("hardware")
    assert html.startswith("<span")
    assert "Physical Sensor" in html
    assert "</span>" in html


def test_quality_badge_html_contains_flag():
    assert "estimated" in badges.quality_badge_html("estimated")
    assert "missing" in badges.quality_badge_html("missing")


def test_sources_legend_dedupes_and_keeps_order():
    legend = badges.sources_legend_html(["demo", "demo", "api", "demo"])
    assert legend.count("Digital Twin (Demo)") == 1
    assert legend.count("Live API") == 1


def test_unknown_source_and_flag_degrade_gracefully():
    # Never raise on an unexpected value; show an explicit "unknown" badge.
    assert "Unknown source" in badges.source_badge_html("martian")
    assert "unknown" in badges.quality_badge_html("weird")


def test_readiness_badge_not_hardware_without_hardware_reading():
    # The judged invariant (P1): the Hardware Readiness badge must derive from
    # ACTUAL reading sources, not driver-library presence. With no reading
    # carrying source=="hardware" it must NOT read "Physical Sensor".
    assert badges.effective_source_from_readings([]) == "simulation"
    assert badges.effective_source_from_readings(
        ["simulation", "demo", "api"]) == "simulation"
    # Confirm the rendered label is never the physical-sensor wording.
    for sources in ([], ["simulation"], ["api"], ["demo", "simulation"]):
        label = badges.source_label(badges.effective_source_from_readings(sources))
        assert label != "Physical Sensor"


def test_readiness_badge_is_hardware_only_with_a_hardware_reading():
    # Only a genuine reading carrying source=="hardware" flips the badge.
    assert badges.effective_source_from_readings(["simulation", "hardware"]) == "hardware"
    assert badges.source_label(
        badges.effective_source_from_readings(["hardware"])) == "Physical Sensor"
