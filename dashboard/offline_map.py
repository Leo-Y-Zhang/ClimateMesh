"""The Live Map's tile-free basemap, kept out of the page module so it can be tested.

``dashboard/app.py`` executes top to bottom the moment it is imported, so the
map it drew could only be checked by rendering the whole page -- and the bug
that mattered here only showed once the page was resized. The figure is built
here instead, from the data frame the page already has.

The map is a plain scatter with latitude/longitude axes, scaled so that a
kilometre is the same length north-south and east-west at London's latitude.
Plotly's map traces cannot draw text without a glyph server, which is the one
thing a Pi with no internet does not have.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from config.nodes import NEIGHBOUR_RADIUS_KM, NEIGHBOURS, NODES_BY_ID
from dashboard.formatting import short_name

# Approximate courses of the main waterways, used only for orientation (traced
# by hand from bridge and lock positions, not surveyed). Each is a list of
# (latitude, longitude) points, upstream first.
WATERWAYS: dict[str, list[tuple[float, float]]] = {
    "River Thames": [
        (51.398, -0.435), (51.404, -0.405), (51.405, -0.372),
        (51.403, -0.343), (51.411, -0.311), (51.431, -0.322), (51.446, -0.323),
        (51.457, -0.308), (51.464, -0.316), (51.471, -0.320), (51.480, -0.305),
        (51.488, -0.287), (51.473, -0.270), (51.472, -0.252), (51.483, -0.240),
        (51.488, -0.230), (51.478, -0.220), (51.467, -0.213), (51.465, -0.188),
        (51.482, -0.172), (51.485, -0.150), (51.488, -0.127), (51.501, -0.122),
        (51.509, -0.115), (51.510, -0.104), (51.508, -0.088), (51.505, -0.075),
        (51.504, -0.060), (51.508, -0.040), (51.500, -0.029), (51.489, -0.021),
        (51.484, -0.009), (51.493, 0.002), (51.505, 0.004), (51.507, 0.009),
        (51.497, 0.015), (51.497, 0.037), (51.495, 0.068), (51.505, 0.087),
        (51.506, 0.115), (51.506, 0.140), (51.483, 0.180), (51.470, 0.205),
        (51.462, 0.245),
    ],
    "River Lea": [
        (51.612, -0.045), (51.585, -0.037), (51.560, -0.027), (51.545, -0.015),
        (51.530, -0.010), (51.517, -0.004), (51.508, 0.006),
    ],
    "River Wandle": [
        (51.462, -0.193), (51.452, -0.190), (51.440, -0.188), (51.425, -0.185),
        (51.412, -0.182), (51.398, -0.170),
    ],
    "Regent's Canal": [
        (51.523, -0.184), (51.531, -0.163), (51.541, -0.146), (51.536, -0.123),
        (51.533, -0.104), (51.536, -0.075), (51.535, -0.050), (51.524, -0.040),
        (51.511, -0.036),
    ],
}

# Where each waterway's name sits (latitude, longitude, x-anchor), chosen to
# stay clear of the node labels and of the node that shares its name.
WATERWAY_LABEL_AT: dict[str, tuple[float, float, str]] = {
    "River Thames": (51.497, -0.287, "center"),
    "River Lea": (51.612, -0.042, "left"),
    "River Wandle": (51.398, -0.166, "left"),
    "Regent's Canal": (51.5225, -0.093, "center"),
}

# Which side of its marker each node's name goes on. Nodes that sit close
# together get labels on different sides so the names never overlap.
LABEL_POS: dict[str, str] = {
    "HYDE-PARK": "bottom center", "CENTRAL-LDN": "top right",
    "REGENTS-CANAL": "top left", "CAMDEN": "top right",
    "CANARY-WHARF": "middle left", "GREENWICH": "bottom center",
    "STRATFORD": "middle right", "VICTORIA-PARK": "top center",
    "RIVER-LEA": "middle right", "WALTHAMSTOW": "middle right",
    "THAMES-BARRIER": "top right", "ILFORD": "top center",
    "LEWISHAM": "bottom center", "DULWICH": "bottom center",
    "BRIXTON": "top center", "PUTNEY": "top left",
    "RIVER-WANDLE": "bottom right", "WIMBLEDON": "bottom center",
    "RICHMOND-PARK": "bottom center", "HAMPSTEAD": "top center",
}

# The window the map shows: (south, north) latitude and (west, east)
# longitude. Fixed for good: see the note on ``constrain`` in offline_map().
LAT_RANGE = (51.392, 51.624)
LON_RANGE = (-0.432, 0.228)
_LAT0 = 51.5
# How many pixels a degree of latitude gets per pixel of a degree of longitude.
ASPECT = 1 / math.cos(math.radians(_LAT0))
_KM_PER_DEG_LON = 111.32 * math.cos(math.radians(_LAT0))

# A marker's colour is its band, the same four colours the sidebar's dots use,
# so the map and the band word next to a score can never disagree.
BANDS = (("SAFE", 0, 30, "#2ecc71"), ("MODERATE", 30, 60, "#f1c40f"),
         ("WARNING", 60, 80, "#e67e22"), ("CRITICAL", 80, 100, "#e74c3c"))
BAND_SCALE = [stop for _, lo, hi, colour in BANDS
              for stop in ([lo / 100, colour], [hi / 100, colour])]
BAND_COLOURS = {band: colour for band, _, _, colour in BANDS}

_WATER = "#a9cde6"
_LINK = "#b8c2d1"
_INK = "#2d3748"
_MUTED = "#8a94a6"


def mesh_links() -> list[tuple[str, str]]:
    """Every neighbour pair once, in a stable order: the mesh the engine uses."""
    return sorted({tuple(sorted((a, b))) for a, nbrs in NEIGHBOURS.items() for b in nbrs})


def _column(df: pd.DataFrame, name: str, default) -> pd.Series:
    if name in df.columns:
        return df[name].fillna(default)
    return pd.Series([default] * len(df), index=df.index)


def _scale_bar(fig: go.Figure, km: float = 5.0) -> None:
    """A ``km`` scale bar and north arrow in the bottom-right corner."""
    span = km / _KM_PER_DEG_LON
    lon1 = LON_RANGE[1] - 0.018
    lon0 = lon1 - span
    lat = LAT_RANGE[0] + 0.012
    tick = 0.0018
    for x0, y0, x1, y1 in ((lon0, lat, lon1, lat), (lon0, lat - tick, lon0, lat + tick),
                           (lon1, lat - tick, lon1, lat + tick)):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=dict(color=_MUTED, width=1.5))
    fig.add_annotation(x=(lon0 + lon1) / 2, y=lat, text=f"{km:g} km", showarrow=False,
                       yanchor="bottom", yshift=3, font=dict(size=10, color=_MUTED))
    fig.add_annotation(x=lon1, y=lat + 0.024, ax=0, ay=24, text="N", showarrow=True,
                       arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor=_MUTED,
                       font=dict(size=10, color=_MUTED), yanchor="bottom")


def _key(fig: go.Figure) -> None:
    """What the thin grey lines are, pinned to the map's top-left corner."""
    fig.add_shape(type="line", xref="x domain", yref="y domain", x0=0.012, x1=0.042,
                  y0=0.965, y1=0.965, line=dict(color=_LINK, width=1.5))
    fig.add_annotation(xref="x domain", yref="y domain", x=0.048, y=0.965, showarrow=False,
                       xanchor="left", yanchor="middle", font=dict(size=10, color=_MUTED),
                       text=f"mesh link: two nodes within {NEIGHBOUR_RADIUS_KM:g} km, "
                            "which can vouch for each other")


def offline_map(df: pd.DataFrame, height: int = 560) -> go.Figure:
    """Tile-free map: labelled nodes, mesh links and the main waterways.

    ``df`` needs ``node_id``, ``node_name``, ``latitude``, ``longitude``,
    ``score``, ``level`` and ``source``; ``dominant_hazard`` is used if present.
    """
    fig = go.Figure()
    for name, pts in WATERWAYS.items():
        fig.add_trace(go.Scatter(
            x=[p[1] for p in pts], y=[p[0] for p in pts], mode="lines",
            line=dict(width=7 if name == "River Thames" else 3.5, color=_WATER,
                      shape="spline", smoothing=0.7),
            hoverinfo="skip", showlegend=False, name=name))
        lat, lon, anchor = WATERWAY_LABEL_AT[name]
        fig.add_annotation(x=lon, y=lat, text=f"<i>{name}</i>", showarrow=False,
                           font=dict(size=10, color="#5b8db8"), xanchor=anchor,
                           yanchor="bottom", opacity=0.95)

    # The mesh itself: one faint line per pair of nodes close enough to vouch
    # for each other. A node with no line to anyone cannot be corroborated.
    xs: list[float | None] = []
    ys: list[float | None] = []
    for a, b in mesh_links():
        na, nb = NODES_BY_ID[a], NODES_BY_ID[b]
        xs += [na["longitude"], nb["longitude"], None]
        ys += [na["latitude"], nb["latitude"], None]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", line=dict(width=1, color=_LINK), hoverinfo="skip",
        name="mesh link", showlegend=False))

    score = pd.to_numeric(df["score"], errors="coerce").fillna(0).clip(0, 100)
    fig.add_trace(go.Scatter(
        x=df["longitude"], y=df["latitude"], mode="markers+text",
        text=[short_name(n) for n in df["node_name"]],
        textposition=[LABEL_POS.get(n, "top center") for n in df["node_id"]],
        textfont=dict(size=11, color=_INK),
        marker=dict(
            size=12 + score * 0.2, color=score, cmin=0, cmax=100,
            colorscale=BAND_SCALE,
            colorbar=dict(
                title=dict(text="risk", font=dict(size=11, color=_MUTED)),
                tickvals=[(lo + hi) / 2 for _, lo, hi, _ in BANDS],
                ticktext=[f"{band}<br><span style='font-size:9px'>{lo}–{hi}</span>"
                          for band, lo, hi, _ in BANDS],
                tickfont=dict(size=10, color=_INK), thickness=14, len=0.62, y=0.55,
                outlinewidth=0),
            line=dict(width=1.5, color="white"), opacity=0.95),
        customdata=list(zip(df["node_id"], df["level"], score.round(0), df["source"],
                            _column(df, "dominant_hazard", "risk"))),
        hovertemplate="<b>%{text}</b> (%{customdata[0]})<br>risk %{customdata[2]}/100 · "
                      "<b>%{customdata[1]}</b><br>main hazard: %{customdata[4]}"
                      "<br>source: %{customdata[3]}<extra></extra>",
        showlegend=False))

    _scale_bar(fig)
    _key(fig)
    fig.add_annotation(xref="x domain", yref="y domain", x=0.008, y=0.012, showarrow=False,
                       text="Offline basemap · waterways approximate · "
                            "nodes are illustrative landmarks",
                       font=dict(size=9, color=_MUTED), xanchor="left", yanchor="bottom")

    # constrain="domain" is the whole fix for a map that kept zooming out. With
    # the default ("range"), Plotly keeps the kilometre square by widening the
    # range, and writes the widened range back into the figure, so every
    # resize of the browser (or of a screenshot) zoomed the map out further
    # and left the nodes in a small cluster in the middle of an empty box.
    # "domain" shrinks the drawing area instead and never touches the range.
    axis = dict(visible=False, constrain="domain", constraintoward="center",
                fixedrange=False, showline=False)
    fig.update_xaxes(range=list(LON_RANGE), **axis)
    fig.update_yaxes(range=list(LAT_RANGE), scaleanchor="x", scaleratio=ASPECT, **axis)
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0),
        plot_bgcolor="#f3f6fa", paper_bgcolor="white", hovermode="closest",
        showlegend=False)
    return fig
