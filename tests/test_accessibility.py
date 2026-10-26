"""Offline accessibility: readable colours, concise advice and safe local speech."""

from __future__ import annotations

import json
import math
import re
from html.parser import HTMLParser
from itertools import combinations

import pandas as pd
import pytest

from backend.playbooks import PLAYBOOKS
from config.nodes import NODES
from dashboard import accessibility as a, badges
from dashboard.formatting import node_name
from dashboard.offline_map import BAND_COLOURS, BAND_SCALE, BANDS, offline_map


def _row(node_id="REGENTS-CANAL", score=86.9, level="CRITICAL", hazard="flood", **extra):
    return {"node_id": node_id, "score": score, "level": level,
            "dominant_hazard": hazard, **extra}


def test_palettes_keep_the_canonical_bands_and_standard_colours():
    assert a.PALETTES["standard"] is BAND_COLOURS
    for palette in a.PALETTES.values():
        assert palette.keys() == BAND_COLOURS.keys()
        scale = a.band_scale(palette)
        for i, (band, lo, hi, _) in enumerate(BANDS):
            assert scale[2 * i:2 * i + 2] == [[lo / 100, palette[band]],
                                             [hi / 100, palette[band]]]
    assert a.band_scale(a.PALETTES["standard"]) == BAND_SCALE


BACKGROUNDS = [colour for palette in a.PALETTES.values() for colour in palette.values()]
BACKGROUNDS += [badge[2] for badge in (*badges.SOURCE_BADGES.values(),
                                    *badges.QUALITY_BADGES.values(),
                                    badges._UNKNOWN_SOURCE, badges._UNKNOWN_QUALITY)]


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_text_contrast_is_at_least_wcag_aa(background):
    foreground = a.text_on(background)
    assert foreground in ("#000000", "#ffffff")
    assert a.contrast_ratio(foreground, background) >= 4.5
    other = "#ffffff" if foreground == "#000000" else "#000000"
    assert a.contrast_ratio(foreground, background) >= a.contrast_ratio(other, background)


def test_contrast_uses_wcag_luminance_and_is_symmetric():
    assert a.contrast_ratio("#000000", "#ffffff") == pytest.approx(21)
    assert a.contrast_ratio("#0072B2", "#0072B2") == pytest.approx(1)
    assert a.contrast_ratio("#000000", "#0a0a0a") == pytest.approx(
        ((10 / 255) / 12.92 + 0.05) / 0.05)
    assert a.contrast_ratio("#0072B2", "#F0E442") == a.contrast_ratio("#F0E442", "#0072B2")


def test_deuteranopia_palette_separation():
    simulated = [a.simulate_deuteranopia(c) for c in a.PALETTES["colour-blind safe"].values()]
    minimum = min(math.dist(c1, c2) for c1, c2 in combinations(simulated, 2))
    # In normalised simulated sRGB, 0.55 is about 32% of the cube diagonal.
    # This conservative regression floor leaves room below the chosen set's
    # 0.589 minimum, while the old SAFE/CRITICAL distance is only about 0.301.
    # It is a numerical separation check, not a clinical perceptual threshold.
    assert minimum > 0.55
    standard = a.PALETTES["standard"]
    old_distance = math.dist(a.simulate_deuteranopia(standard["SAFE"]),
                             a.simulate_deuteranopia(standard["CRITICAL"]))
    assert old_distance < minimum * 0.55
    assert all(0 <= channel <= 1 for colour in simulated for channel in colour)


def test_deuteranopia_decodes_linear_rgb_before_applying_the_matrix():
    # Pure red is the first matrix column; the sRGB encoder must run afterwards.
    expected = (1.055 * 0.367322 ** (1 / 2.4) - 0.055,
                1.055 * 0.280085 ** (1 / 2.4) - 0.055, 0)
    assert a.simulate_deuteranopia("#ff0000") == pytest.approx(expected)
    assert a.simulate_deuteranopia("#000000") == (0, 0, 0)
    assert a.simulate_deuteranopia("#ffffff") == pytest.approx((1, 1, 1), abs=1e-6)


def test_offline_map_accepts_the_selected_palette_without_changing_the_default():
    frame = pd.DataFrame([{**n, "score": 86, "level": "CRITICAL", "source": "demo"}
                          for n in NODES])
    palette = a.PALETTES["colour-blind safe"]
    for colours, expected in ((None, BAND_SCALE), (palette, a.band_scale(palette))):
        fig = offline_map(frame, colours=colours)
        markers = next(t for t in fig.data if t.mode == "markers+text")
        assert [list(stop) for stop in markers.marker.colorscale] == expected


# GSM 03.38's basic alphabet. Extended characters take two septets, so these
# previews deliberately avoid them to make the 160-character limit sufficient.
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")


@pytest.mark.parametrize("hazard", PLAYBOOKS)
def test_sms_is_one_gsm7_message_for_every_playbook(hazard):
    row = _row(hazard=hazard, corroboration="uncorroborated" if hazard == "sensor-check" else "corroborated")
    message = a.sms_alert(row)
    assert len(message) <= 160
    assert set(message) <= GSM7_BASIC
    assert "CRITICAL" in message
    assert "Regent's Canal" in message
    assert "86/100" in message
    assert ("sensor check" if hazard == "sensor-check" else hazard) in message
    if hazard == "flood":
        assert PLAYBOOKS[hazard][0] in message


def test_sms_truncates_a_long_unicode_place_at_a_word_boundary():
    name = "Café ’North’ 🌧 " + "Very long place name " * 30
    message = a.sms_alert(_row(node_id=name))
    assert len(message) <= 160
    assert set(message) <= GSM7_BASIC
    assert "Cafe 'North'" in message
    assert message.endswith("...")
    # The character after the retained prefix was a space, not half a word.
    full = a.sms_alert(_row(node_id="Short"))
    assert not full.endswith("...")
    assert ("Climate Mesh: CRITICAL flood risk at Cafe 'North' "
            + "Very long place name " * 30).startswith(message[:-3] + " ")


@pytest.mark.parametrize("rows", [[], [_row(score=12, level="SAFE")],
                                   [_row(level="MODERATE"), _row(level="SAFE")]])
def test_spoken_summary_says_plainly_when_nothing_needs_action(rows):
    summary = a.spoken_summary(rows)
    assert "Nothing needs action" in summary
    assert str(len(rows)) in summary
    assert "being watched" in summary
    assert node_name("REGENTS-CANAL") not in summary


def test_spoken_summary_gives_the_flood_score_and_first_action():
    summary = a.spoken_summary([_row()])
    assert "Regent's Canal has CRITICAL flood risk" in summary
    assert "86 out of 100" in summary
    assert PLAYBOOKS["flood"][0] in summary
    assert all(len(sentence.split()) < 20 for sentence in summary.split(".") if sentence)
    assert "/" not in summary
    assert summary.isascii()


def test_spoken_summary_limits_names_and_prioritises_the_highest_score():
    names = ["CAMDEN", "BRIXTON", "DULWICH", "GREENWICH", "REGENTS-CANAL"]
    rows = [_row(node_id=name, score=81 + i) for i, name in enumerate(names)]
    summary = a.spoken_summary(rows)
    for name in names[-3:]:
        assert node_name(name) in summary
    for name in names[:2]:
        assert node_name(name) not in summary
    assert summary.index(node_name(names[-1])) < summary.index(node_name(names[-2]))
    assert "and 2 more" in summary
    assert "/" not in summary
    assert summary.isascii()


def test_spoken_place_names_do_not_introduce_symbols_or_emoji():
    summary = a.spoken_summary([_row(node_id="Café / North 🌧")])
    assert "Cafe out of North" in summary
    assert "/" not in summary
    assert summary.isascii()


@pytest.mark.parametrize("hazard", PLAYBOOKS)
def test_spoken_advice_is_short_and_uses_the_engine_hazard(hazard):
    row = _row(hazard=hazard, corroboration="uncorroborated" if hazard == "sensor-check" else "corroborated")
    summary = a.spoken_summary([row])
    assert all(len(sentence.split()) < 20 for sentence in summary.split(".") if sentence)
    assert "/" not in summary
    assert summary.isascii()
    if hazard == "sensor-check":
        assert "sensor check" in summary
        assert PLAYBOOKS["sensor-check"][0] in summary
        assert "flood" not in summary


class _SnippetParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.starts = []
        self.ends = []
        self.script = ""
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        self.starts.append((tag, dict(attrs)))
        self.in_script = self.in_script or tag == "script"

    def handle_endtag(self, tag):
        self.ends.append(tag)
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.script += data


def test_read_aloud_html_safely_round_trips_script_markup_and_quotes():
    text = '</script><script>alert(1)</script><!-- "quoted" \'text\' & \u2028 next'
    snippet = a.read_aloud_html(text, label='Read "this" <script> safely')
    assert "</script><script>" not in snippet
    assert "<!--" not in snippet
    parser = _SnippetParser()
    parser.feed(snippet)
    parser.close()
    assert sum(tag == "script" for tag, _ in parser.starts) == 1
    assert parser.ends.count("script") == 1
    payload = re.search(r"const text = (.*);", parser.script).group(1)
    assert json.loads(payload) == text
    buttons = [attrs for tag, attrs in parser.starts if tag == "button"]
    assert {button["id"] for button in buttons} == {"read", "stop"}
    assert all(button["type"] == "button" for button in buttons)
    assert "window.speechSynthesis.speak(utterance)" in parser.script
    assert "v.localService" in parser.script
    assert "window.speechSynthesis.cancel()" in parser.script
    assert "This browser has no speech synthesis" in parser.script
    assert "16px" in snippet
    assert "https://" not in snippet


def test_read_aloud_has_an_accessible_default_button_name():
    assert ">Read the situation aloud</button>" in a.read_aloud_html("All quiet.")
