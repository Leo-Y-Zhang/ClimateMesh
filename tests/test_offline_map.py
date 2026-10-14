"""The Live Map's offline basemap: framed, true to the mesh, and stable.

The map used to zoom out every time the page was resized. Plotly kept a
kilometre the same length both ways by widening the axis range, and wrote the
wider range back into the figure, so each resize compounded the last: after a
few, the 20 nodes sat in a small cluster in the middle of an empty box. That
is the picture the Live Map screenshots shipped with.
"""

from __future__ import annotations

import pandas as pd

from backend.risk_engine import risk_level
from config.nodes import NEIGHBOURS, NODES
from dashboard import offline_map as om


def _frame(score: float = 50.0) -> pd.DataFrame:
    return pd.DataFrame([{**n, "score": score, "level": risk_level(score), "source": "demo"}
                         for n in NODES])


def test_the_map_shrinks_its_drawing_area_rather_than_widening_its_range():
    fig = om.offline_map(_frame())
    assert fig.layout.xaxis.constrain == "domain"
    assert fig.layout.yaxis.constrain == "domain"
    assert tuple(fig.layout.xaxis.range) == om.LON_RANGE
    assert tuple(fig.layout.yaxis.range) == om.LAT_RANGE
    # Still a true-shape map: a kilometre is as long north-south as east-west.
    assert fig.layout.yaxis.scaleanchor == "x"
    assert fig.layout.yaxis.scaleratio == om.ASPECT


def test_every_node_and_every_label_is_inside_the_window():
    def inside(lat: float, lon: float) -> bool:
        return (om.LAT_RANGE[0] < lat < om.LAT_RANGE[1]
                and om.LON_RANGE[0] < lon < om.LON_RANGE[1])

    for node in NODES:
        assert inside(node["latitude"], node["longitude"]), node["node_id"]
        assert node["node_id"] in om.LABEL_POS, node["node_id"]
    assert set(om.WATERWAY_LABEL_AT) == set(om.WATERWAYS)
    for name, (lat, lon, _anchor) in om.WATERWAY_LABEL_AT.items():
        assert inside(lat, lon), name


def test_the_mesh_links_drawn_are_exactly_the_engines_neighbours():
    links = om.mesh_links()
    assert len(links) == len(set(links))
    assert set(links) == {tuple(sorted((a, b))) for a, nbrs in NEIGHBOURS.items() for b in nbrs}
    # Ilford has one neighbour in range, so the mesh can never vouch for it in
    # either direction; the map has to show it hanging off a single link.
    assert sum("ILFORD" in link for link in links) == 1


def test_a_marker_colour_is_its_band():
    for band, lo, hi, _colour in om.BANDS:
        assert risk_level(lo) == band
        assert risk_level(hi - 0.01) == band
    assert om.BANDS[0][1] == 0 and om.BANDS[-1][2] == 100


def test_every_node_is_drawn_once_with_its_name():
    fig = om.offline_map(_frame())
    markers = [t for t in fig.data if t.mode == "markers+text"]
    assert len(markers) == 1
    assert len(markers[0].x) == len(NODES)
    assert "Regent's Canal" in markers[0].text      # short names, not ids
    assert "REGENTS-CANAL" not in markers[0].text


def test_a_missing_or_garbled_score_draws_as_safe_rather_than_crashing():
    frame = _frame()
    frame["score"] = frame["score"].astype(object)
    frame.loc[0, "score"] = None
    frame.loc[1, "score"] = "n/a"
    fig = om.offline_map(frame)
    markers = next(t for t in fig.data if t.mode == "markers+text")
    assert list(markers.marker.color[:2]) == [0, 0]
