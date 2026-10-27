"""Offline alternatives to colour and dense text, kept pure for direct testing.

The page only selects a palette and renders these strings. Hazard advice comes
from the engine's decision, so an unconfirmed sensor never prompts flood action.
"""

from __future__ import annotations

import html
import json
import string
import unicodedata

from backend.playbooks import playbook_for
from backend.risk_engine import alert_type_for
from dashboard.formatting import node_name, score_text
from dashboard.offline_map import BAND_COLOURS, BANDS

PALETTES: dict[str, dict[str, str]] = {
    "standard": BAND_COLOURS,
    # Orange and vermilion are too close under deuteranopia. Black is also
    # part of Okabe-Ito and separates CRITICAL from every other band.
    "colour-blind safe": {
        "SAFE": "#0072B2", "MODERATE": "#F0E442",
        "WARNING": "#D55E00", "CRITICAL": "#000000",
    },
}


def band_scale(colours: dict[str, str]) -> list:
    """Keep the engine's hard band boundaries when changing map colours."""
    return [stop for band, lo, hi, _ in BANDS
            for stop in ([lo / 100, colours[band]], [hi / 100, colours[band]])]


def _linear_rgb(hex_colour: str) -> tuple[float, float, float]:
    """Decode sRGB before luminance or colour-vision maths, which need light."""
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                 for v in rgb)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.x contrast measures light, rather than encoded RGB differences."""
    weights = (0.2126, 0.7152, 0.0722)
    fg = sum(w * v for w, v in zip(weights, _linear_rgb(fg_hex)))
    bg = sum(w * v for w, v in zip(weights, _linear_rgb(bg_hex)))
    return (max(fg, bg) + 0.05) / (min(fg, bg) + 0.05)


def text_on(bg_hex: str) -> str:
    """Choose readable ink without assuming that a band is light or dark."""
    return max(("#000000", "#ffffff"), key=lambda fg: contrast_ratio(fg, bg_hex))


def simulate_deuteranopia(hex_colour: str) -> tuple[float, float, float]:
    """Machado et al. (2009), deuteranopia severity 1.0, in linear RGB.

    Clip to the display gamut before encoding back to sRGB in [0, 1], so tests
    compare the colours a display can actually show. This is a palette check,
    not a claim that RGB distance models every reader's colour perception.
    """
    matrix = ((0.367322, 0.860646, -0.227968),
              (0.280085, 0.672501, 0.047413),
              (-0.011820, 0.042940, 0.968881))
    linear = _linear_rgb(hex_colour)
    simulated = [max(0.0, min(1.0, sum(a * b for a, b in zip(row, linear))))
                 for row in matrix]
    return tuple(12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
                 for v in simulated)


def _plain_text(text: str) -> str:
    """Use a small GSM-7 subset so speech and SMS avoid decorative symbols."""
    text = str(text).translate(str.maketrans({"’": "'", "‘": "'", "–": "-", "—": "-"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    allowed = string.ascii_letters + string.digits + " .,;:!?'-()/"
    return " ".join("".join(c if c in allowed else " " for c in text).split())


def _hazard_words(row: dict) -> str:
    """Say sensor check plainly, without suggesting an unconfirmed hazard."""
    hazard = alert_type_for(row)
    return {"sensor-check": "sensor check", "risk": "climate risk"}.get(hazard, f"{hazard} risk")


def spoken_summary(rows: list[dict]) -> str:
    """Give listeners the urgent places and one first action in short sentences.

    Limit named places to three to keep the spoken overview easy to remember.
    Scores use the dashboard's flooring rule, so speech cannot change a band.
    """
    acting = sorted((r for r in rows if r.get("level") in ("WARNING", "CRITICAL")),
                    key=lambda r: (-float(r["score"]), str(r.get("node_id", ""))))
    watched = f"{len(rows)} {'place is' if len(rows) == 1 else 'places are'} being watched."
    if not acting:
        return f"Nothing needs action now. {watched}"
    sentences = [watched]
    for row in acting[:3]:
        name = _plain_text(node_name(row["node_id"]))
        score = score_text(row["score"]).replace("/", " out of ")
        sentences.append(f"{name} has {row['level']} {_hazard_words(row)}. Score {score}.")
    if len(acting) > 3:
        sentences.append(f"These places and {len(acting) - 3} more need action.")
    first_step = playbook_for(alert_type_for(acting[0]))[0]
    # The generic risk step joins two instructions; separate them so each is
    # easy to follow aloud while preserving the first step's full advice.
    first_step = _plain_text(first_step).replace(" and follow ", ". Follow ")
    sentences.append("First action for the most urgent place.")
    sentences.append(first_step)
    return _plain_text(" ".join(sentences).replace("/", " out of "))


def sms_alert(row: dict) -> str:
    """Keep a receptionist's preview within one 160-septet GSM-7 message."""
    hazard = alert_type_for(row)
    message = _plain_text(
        f"Climate Mesh: {row['level']} {_hazard_words(row)} at {node_name(row['node_id'])} "
        f"({score_text(row['score'])}). {playbook_for(hazard)[0]}")
    if len(message) <= 160:
        return message
    return message[:157].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def read_aloud_html(text: str, label: str = "Read the situation aloud") -> str:
    """Use local browser speech, with safe script data and native keyboard buttons.

    Escaping '<' after JSON encoding prevents the HTML parser ending the script
    or treating a user-supplied comment opener as script markup.
    """
    payload = json.dumps(text).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
body {{ font: 16px "Source Sans Pro", "Source Sans 3", system-ui, sans-serif; margin: 0; color: #31333f; }}
/* matches Streamlit's secondary buttons so the control looks part of the page */
button {{ font: inherit; padding: 0.4rem 0.9rem; margin-right: 0.4rem; cursor: pointer; color: inherit;
          background: #fff; border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.5rem; }}
button:hover {{ border-color: #ff4b4b; color: #ff4b4b; }}
button:disabled {{ cursor: not-allowed; opacity: 0.5; }}
button:focus-visible {{ outline: 3px solid #0072B2; outline-offset: 2px; }}
#status {{ margin-left: 0.4rem; }}
</style></head><body>
<button id="read" type="button">{html.escape(label)}</button>
<button id="stop" type="button" aria-label="Stop reading aloud">Stop</button>
<span id="status" role="status" aria-live="polite"></span>
<script>
const text = {payload};
const read = document.getElementById('read');
const stop = document.getElementById('stop');
const status = document.getElementById('status');
if ('speechSynthesis' in window && 'SpeechSynthesisUtterance' in window) {{
    // Browsers may load their voice list asynchronously before the first click.
    window.speechSynthesis.getVoices();
    read.addEventListener('click', () => {{
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-GB';
        // A remote voice could silently need internet. Only use a local voice.
        const voice = window.speechSynthesis.getVoices().find(v =>
            v.localService && v.lang.toLowerCase().startsWith('en'));
        if (!voice) {{
            status.textContent = 'No offline English voice is available. Install a local browser voice.';
            return;
        }}
        utterance.voice = voice;
        utterance.onerror = () => {{ status.textContent = 'Speech is unavailable. Please read the dashboard text.'; }};
        window.speechSynthesis.speak(utterance);
    }});
    stop.addEventListener('click', () => window.speechSynthesis.cancel());
    window.addEventListener('pagehide', () => window.speechSynthesis.cancel());
}} else {{
    read.disabled = true;
    stop.disabled = true;
    status.textContent = 'This browser has no speech synthesis. Please read the dashboard text.';
}}
</script></body></html>"""
