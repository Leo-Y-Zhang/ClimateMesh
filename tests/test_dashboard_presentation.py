"""Presentation invariants that protect legibility and provenance."""

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest

from dashboard.badges import (
    QUALITY_BADGES, SOURCE_BADGES, quality_badge_html, source_badge_html,
)

ROOT = Path(__file__).resolve().parent.parent
EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f]")


@pytest.mark.parametrize("path", sorted((ROOT / "dashboard").glob("*.py")),
                         ids=lambda p: p.name)
def test_dashboard_strings_have_no_emoji(path):
    source = path.read_text(encoding="utf-8")
    assert not EMOJI.search(source), path.name
    # Check decoded literals too, so a Unicode escape cannot hide an emoji.
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not EMOJI.search(node.value), (path.name, node.lineno)


@pytest.mark.parametrize("path", [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))],
                         ids=lambda p: p.name)
def test_documentation_has_no_emoji(path):
    assert not EMOJI.search(path.read_text(encoding="utf-8")), path.name


@pytest.mark.parametrize("key,label", [(key, values[0]) for key, values in SOURCE_BADGES.items()]
                         + [("unrecognised", "Unknown source")])
def test_source_badges_are_plain_labelled_text(key, label):
    markup = source_badge_html(key)
    assert label in markup
    assert "class='mesh-badge'" in markup
    assert not EMOJI.search(markup)


@pytest.mark.parametrize("key", [*QUALITY_BADGES, "unrecognised"])
def test_quality_badges_are_plain_labelled_text(key):
    markup = quality_badge_html(key)
    assert (key if key in QUALITY_BADGES else "unknown") in markup
    assert "class='mesh-badge'" in markup
    assert not EMOJI.search(markup)
