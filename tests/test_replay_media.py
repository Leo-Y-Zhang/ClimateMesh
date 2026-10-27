"""Fast offline checks on replay presentation and runtime evidence sources."""
from __future__ import annotations

import copy
import gzip
import json
from collections import Counter

import matplotlib.pyplot as plt
import numpy as np
import pytest

from scripts import evidence_card as card
from scripts import replay_animation as replay


@pytest.fixture
def payload():
    return replay.load_json(replay.ROOT / "evidence/replay/flood-2021-07-12-gauges.json")


@pytest.mark.parametrize("frames_per_hour", [1, 4, 15, 24])
def test_frame_count_and_hourly_readings(payload, frames_per_hour):
    frames = list(replay.generate_frames(payload, frames_per_hour))
    assert len(frames) == len(payload["per_hour"]) * frames_per_hour
    assert Counter(f.hour for f in frames) == {h["hour"]: frames_per_hour for h in payload["per_hour"]}
    for frame in frames:
        assert frame.readings is payload["per_hour"][frame.hour_index]["nodes"]
        assert frame.hour == payload["per_hour"][frame.hour_index]["hour"]
    # Interpolation is visual only; the final recorded hour holds at its score.
    start, between = frames[0], frames[min(1, frames_per_hour - 1)]
    for row in start.readings:
        next_row = next(r for r in payload["per_hour"][1]["nodes"] if r["node_id"] == row["node_id"])
        expected = row["score"] + between.fraction * (next_row["score"] - row["score"])
        assert between.visual_scores[row["node_id"]] == pytest.approx(expected)
    assert frames[-1].visual_scores == {r["node_id"]: r["score"] for r in frames[-1].readings}


def test_rendered_values_only_change_on_recorded_hours(payload):
    payload = copy.deepcopy(payload)
    payload["per_hour"] = payload["per_hour"][16:18]
    figure = replay.ReplayFigure(payload)
    try:
        texts = []
        marker_sizes = []
        for frame in replay.generate_frames(payload, 3):
            figure.update(frame)
            texts.append([t.get_text() for t in figure.fig.texts] +
                         [t.get_text() for t in figure.channel.texts])
            marker_sizes.append(figure.markers.get_sizes().copy())
        assert texts[0] == texts[1] == texts[2]
        assert texts[3] == texts[4] == texts[5]
        assert texts[2] != texts[3]
        assert (marker_sizes[0] != marker_sizes[1]).any()
        assert "Mon 12 Jul 2021 16:00 BST" in texts[0]
        checking = [r["corroboration"] == "uncorroborated" for r in payload["per_hour"][1]["nodes"]]
        assert [t.get_visible() for t in figure.check_labels] == checking
    finally:
        plt.close(figure.fig)


@pytest.mark.parametrize("path", replay.replay_paths(replay.ROOT / "evidence/replay"), ids=lambda p: p.stem)
def test_end_card_matches_json_summary(path):
    payload = replay.load_json(path)
    summary = payload["summary"]
    values = replay.outcome(payload)
    assert values["peak_score"] == summary["peak_score"]
    assert summary["peak_per_node"][values["peak_node"]]["score"] == values["peak_score"]
    assert values["alerts_by_type"] == summary["alerts_by_type"]
    assert values["sensor_checks"] == summary["alerts_by_type"].get("sensor-check", 0)
    for band in ("WARNING", "CRITICAL"):
        hours = [v[band] for v in summary["first_band_per_node"].values() if v[band]]
        assert values["first"][band] == (min(hours) if hours else None)
    figure = replay.ReplayFigure(payload)
    try:
        figure.card(end=True)
        assert figure.overlay.get_visible()
        assert figure.card_heading.get_text() == "Measured replay outcome"
        for line in replay.outcome_text(payload):
            assert line in figure.card_body.get_text()
    finally:
        plt.close(figure.fig)


def test_summary_is_authoritative_even_when_samples_differ(payload):
    payload["summary"]["peak_score"] = 98.765
    payload["summary"]["alerts_by_type"] = {"sensor-check": 123}
    values = replay.outcome(payload)
    assert values["peak_score"] == 98.765
    assert values["sensor_checks"] == 123
    assert any("98.765" in line for line in replay.outcome_text(payload))


@pytest.mark.parametrize("dpi", [50, 100])
def test_cached_hourly_text_and_cards_match_full_canvas_draw(payload, dpi):
    figure = replay.ReplayFigure(payload)
    figure.fig.set_dpi(dpi)
    try:
        frames = list(replay.generate_frames(payload, 2))
        for frame in (frames[32], frames[33], frames[34]):
            figure.update(frame)
            figure.fig.canvas.draw()
            cached = np.array(figure.fig.canvas.buffer_rgba())
            # Independent full Figure draw verifies the right-hand data panel.
            plt.Figure.draw(figure.fig, figure.fig.canvas.get_renderer())
            full = np.array(figure.fig.canvas.buffer_rgba())
            panel = round(cached.shape[1] * 0.615)
            assert np.array_equal(cached[:, panel:], full[:, panel:])
        figure.card(end=True)
        figure.fig.canvas.draw()
        cached = np.array(figure.fig.canvas.buffer_rgba())
        plt.Figure.draw(figure.fig, figure.fig.canvas.get_renderer())
        assert np.array_equal(cached, np.array(figure.fig.canvas.buffer_rgba()))
    finally:
        plt.close(figure.fig)


def test_json_gzip_discovery_and_deduplication(tmp_path, payload):
    name = "flood-2021-07-12-gauges.json"
    compressed = tmp_path / (name + ".gz")
    with gzip.open(compressed, "wt") as stream:
        json.dump(payload, stream)
    (tmp_path / "holdout-2023-03-06-grid.json").write_text("{}")
    assert replay.replay_paths(tmp_path) == [compressed]
    assert replay.load_json(compressed) == payload
    plain = tmp_path / name
    plain.write_text(json.dumps(payload))
    assert replay.replay_paths(tmp_path) == [plain]
    counts = card.replay_counts(tmp_path)
    assert counts["hours"] == len(payload["per_hour"])
    assert counts["node_hours"] == sum(len(h["nodes"]) for h in payload["per_hour"])
    assert counts["gauges_fetched"] == len(payload["summary"]["gauges"])
    assert counts["gauges_used"] == sum(g["used"] for g in payload["summary"]["gauges"])


def test_missing_ffmpeg_still_writes_gif(monkeypatch, tmp_path, payload, capsys):
    monkeypatch.setattr(replay.animation.writers, "is_available", lambda name: False)
    saved = []

    class Movie:
        def __init__(self, *args, **kwargs):
            pass

        def save(self, path, writer, dpi):
            assert isinstance(writer, replay.CompactPillowWriter)
            saved.append(path)
            path.write_bytes(b"test GIF writer called")

    monkeypatch.setattr(replay.animation, "FuncAnimation", Movie)
    paths = replay.render(payload, tmp_path)
    assert paths == saved
    assert [p.suffix for p in paths] == [".gif"]
    assert "skipping MP4" in capsys.readouterr().out


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_card_renders_numbers_from_functions(monkeypatch, theme):
    monkeypatch.setattr(card, "collected_test_count", lambda: 101)
    monkeypatch.setattr(card, "source_line_count", lambda: 10007)
    monkeypatch.setattr(card, "test_file_count", lambda: 103)
    monkeypatch.setattr(card, "NODES", [None] * 107)
    monkeypatch.setattr(card, "MEASUREMENT_FIELDS", [None] * 109)
    monkeypatch.setattr(card, "VALID_SOURCES", [None] * 113)
    monkeypatch.setattr(card, "replay_counts", lambda: {
        "events": 127, "variants": 131, "hours": 137, "unique_hours": 139,
        "node_hours": 149, "gauges_fetched": 151, "gauges_used": 157,
        "heldout_weeks": 8, "heldout_node_hours": 1000})
    monkeypatch.setattr(card.evaluate, "evaluation_frame_counts", lambda: {"quiet": 163, "event": 167})
    monkeypatch.setattr(card, "fresh_benchmark", lambda: {
        "median_ms": 173, "cycles": 179, "platform": "TEST MACHINE", "output": ""})
    monkeypatch.setattr(card, "git_commit", lambda: "testhash")
    numbers = card.collect_numbers()
    fig, texts = card.render_card(numbers, theme=theme)
    try:
        assert texts == [t.get_text() for t in fig.texts]
        for value in ("101", "10,007", "8", "107", "109", "113", "127", "137", "1,149",
                      "151 / 157", "330", "173 ms"):
            assert value in texts
        assert "Recorded events · 131 variants" in texts
        assert "Median cycle · 179 fresh runs" in texts
        assert any("TEST MACHINE" in t for t in texts)
        assert any("testhash" in t for t in texts)
        assert tuple(round(v) for v in fig.get_size_inches() * fig.dpi) == (2480, 3508)
    finally:
        plt.close(fig)


def test_evaluation_counts_use_its_inventory():
    counts = card.evaluate.evaluation_frame_counts()
    assert counts["quiet"] == card.evaluate.DEFAULT_SEEDS
    assert counts["stuck"] == card.evaluate.DEFAULT_SEEDS * len(card.evaluate.STUCK_NODES)
    assert counts["event"] == (card.evaluate.DEFAULT_SEEDS * len(card.evaluate.HAZARD_OF)
                               * round(1 / card.evaluate.DEFAULT_STEP))


def test_source_lines_exclude_tests_and_venvs(tmp_path):
    for folder in ("tests", "venv", ".venv", ".tmp", "app"):
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "test_example.py").write_text("first\nsecond\n")
    assert card.source_line_count(tmp_path) == 2
    assert card.test_file_count(tmp_path) == 1
