"""Shared presentation for the operations dashboard."""

from __future__ import annotations

from html import escape

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

ACCENT = "#2b5a7a"
FONT = '"Source Sans Pro", "Source Sans 3", sans-serif'
BADGE_CSS = """
    .mesh-badge { display: inline-block; padding: 2px 6px; margin: 2px 4px 2px 0;
        border: 1px solid #cbd4dc; border-radius: 3px; font-size: 0.8rem;
        font-weight: 500; line-height: 1.5; white-space: nowrap; }
"""


def configure_charts() -> None:
    """Use the same quiet palette and typography for every Plotly chart."""
    template = go.layout.Template(pio.templates["plotly_white"].to_plotly_json())
    template.layout.update(
        font=dict(family=FONT, color="#263442", size=14),
        title=dict(font=dict(size=18)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=[ACCENT],
        xaxis=dict(gridcolor="#e5e9ed", zerolinecolor="#d5dce2"),
        yaxis=dict(gridcolor="#e5e9ed", zerolinecolor="#d5dce2"),
    )
    pio.templates["climate_mesh"] = template
    pio.templates.default = "climate_mesh"
    px.defaults.template = "climate_mesh"
    px.defaults.color_discrete_sequence = [ACCENT]


def band_html(band: str, colours: dict[str, str]) -> str:
    """A palette-aware marker with a band word for readers who cannot see colour."""
    colour = colours.get(band, "#697580")
    return (f'<span class="risk-band"><span class="band-dot" aria-hidden="true" '
            f'style="background:{colour}"></span>{escape(str(band))}</span>')


def dashboard_css(large_text: bool = False) -> str:
    """One style block, including the existing larger-text preference."""
    larger = """
        html { font-size: 120%; }
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
        [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
            font-size: 1rem;
        }
    """ if large_text else ""
    return """<style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1500px; }
        h1 { font-size: 2rem !important; letter-spacing: -0.02em; }
        h2 { font-size: 1.35rem !important; }
        h3 { font-size: 1.1rem !important; }
        h1, h2, h3 { font-weight: 600 !important; padding-bottom: 0.45rem; }
        [data-testid="stVerticalBlock"] { gap: 0.85rem; }
        [data-testid="stMetricValue"] { font-size: 1.65rem; }
        [data-testid="stDecoration"] { display: none; }
        [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
            color: #536271 !important; }
        [data-testid="stMarkdownContainer"] code, [data-testid="stCaptionContainer"] code {
            color: #334e63; background: #f1f4f6; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
        @media (min-width: 900px) {
            [data-testid="stSidebar"][aria-expanded="true"] {
                width: 400px !important; min-width: 400px !important; } }
        [data-testid="stAlert"] { background: #f1f4f6; color: #263442; }
        .risk-band { display: inline-flex; align-items: center; gap: 0.4rem;
            font-size: 0.85rem; font-weight: 600; white-space: nowrap; }
        .band-dot { display: inline-block; width: 0.6rem; height: 0.6rem;
            border-radius: 2px; flex-shrink: 0; }
    """ + BADGE_CSS + larger + "</style>"
