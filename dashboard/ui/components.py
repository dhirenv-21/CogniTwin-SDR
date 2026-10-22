"""
Reusable HTML components (metric cards, chips, badges, section headers, empty states,
agent pipeline, key/value lists) and Lucide icons, all styled by ui/theme.py.

Components only format values they are given; "—" is shown for anything missing.
"""

import html
import math
from typing import Iterable, Optional, Sequence, Tuple
from urllib.parse import quote

import streamlit as st

from ui import theme as T

# ------------------------------------------------------------------ Lucide icons (ISC licence), 24x24 stroke paths
ICONS = {
    "overview": '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/>'
                '<rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    "radio": '<path d="M4.9 16.1C1 12.2 1 5.8 4.9 1.9"/><path d="M7.8 4.7a6.14 6.14 0 0 0-.8 7.5"/>'
             '<circle cx="12" cy="9" r="2"/><path d="M16.2 4.8c2 2 2.26 5.11.8 7.47"/>'
             '<path d="M19.1 1.9a9.96 9.96 0 0 1 0 14.1"/><path d="M9.5 18h5"/><path d="m8 22 4-11 4 11"/>',
    "flask": '<path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45'
             'l-5.069-10.127A2 2 0 0 1 14 9.527V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/>',
    "bot": '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/>'
           '<path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
    "scale": '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>'
             '<path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/>'
             '<path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "cpu": '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/>'
           '<path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/>'
           '<path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    "settings": '<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "wave": '<path d="M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0v-4'
            'a2 2 0 0 1 2-2"/>',
    "iq": '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/>'
          '<path d="M22 10v3"/>',
    "radar": '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/>'
             '<path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/>'
             '<circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/>',
    "twin": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
            '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "trend": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 '
              '6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "next": '<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" x2="19" y1="5" y2="19"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/>'
             '<path d="M12 17h.01"/>',
    "x": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "signal": '<path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V8"/><path d="M22 4v16"/>',
    "zap": '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 '
           '.78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    "layers": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9'
              'a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
              '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
            '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4'
              'a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "chevron": '<path d="m9 18 6-6-6-6"/>',
    "terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
    "drive": '<line x1="22" x2="2" y1="12" y2="12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6'
             'l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" x2="6.01" y1="16" y2="16"/>'
             '<line x1="10" x2="10.01" y1="16" y2="16"/>',
}


def icon(name: str, size: int = 15, stroke: float = 1.9) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS[name]}</svg>')


def icon_mask_css(selector: str, name: str) -> str:
    """CSS that draws a Lucide icon as a currentColor mask before `selector` (used for sidebar links)."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="1.9" '
           f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    url = "data:image/svg+xml;utf8," + quote(svg)
    return (f'{selector}::before{{content:"";width:16px;height:16px;flex:none;margin-right:10px;background:currentColor;'
            f'-webkit-mask:url("{url}") no-repeat center/contain;mask:url("{url}") no-repeat center/contain;}}')


# ------------------------------------------------------------------ formatting

def esc(x) -> str:
    return html.escape(str(x), quote=True)


def fmt(x, spec: str = ".4g", none: str = "—") -> str:
    """Format a number; None, '', NaN and inf become `none` (never a fabricated 0)."""
    try:
        if x is None or x == "" or (isinstance(x, float) and not math.isfinite(x)):
            return none
        v = float(x)
        if not math.isfinite(v):
            return none
        return format(v, spec)
    except (TypeError, ValueError):
        return str(x) if x not in (None, "") else none


def md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


# ------------------------------------------------------------------ building blocks

def chip(text: str, tone: str = "muted", mono: Optional[str] = None, running: bool = False) -> str:
    c = T.TONES.get(tone, tone)
    tail = f' <span class="mono">{esc(mono)}</span>' if mono else ""
    return f'<span class="chip{" run" if running else ""}" style="--c:{c}"><span class="dot"></span>{esc(text)}{tail}</span>'


def badge(text: str, tone: str = "muted") -> str:
    return f'<span class="badge" style="--c:{T.TONES.get(tone, tone)}">{esc(text)}</span>'


def section(title: str, ic: Optional[str] = None, right: str = "") -> None:
    md(f'<div class="ct-sec"><div class="h">{icon(ic, 14) if ic else ""}{esc(title)}</div><div class="r">{right}</div></div>')


def metric(label: str, value: str, sub: str = "", tone: Optional[str] = None, ic: Optional[str] = None,
           unit: str = "", value_tone: Optional[str] = None, compact: bool = False) -> str:
    """One metric card (HTML string); combine several with metrics()."""
    c = T.TONES.get(tone, tone) if tone else "transparent"
    vc = f"--vc:{T.TONES.get(value_tone, value_tone)};" if value_tone else ""
    u = f"<small>{esc(unit)}</small>" if unit and value != "—" else ""
    return (f'<div class="ct-metric{" compact" if compact else ""}" style="--c:{c};{vc}">'
            f'<div class="k">{icon(ic, 14) if ic else ""}{esc(label)}</div>'
            f'<div class="v{" long" if len(value) > 9 else ""}" title="{esc(value)}">{esc(value)}{u}</div>'
            f'<div class="s" title="{esc(sub)}">{esc(sub) if sub else "&nbsp;"}</div></div>')


def metrics(cards: Iterable[str], min_width: int = 170) -> None:
    md(f'<div class="ct-metrics" style="--min:{min_width}px">{"".join(cards)}</div>')


def empty(title: str, body: str = "", ic: str = "info") -> None:
    md(f'<div class="ct-empty"><div class="ic">{icon(ic, 20)}</div><div class="t">{esc(title)}</div>'
       f'<div class="b">{esc(body)}</div></div>')


def kv(rows: Sequence[Tuple[str, object]]) -> None:
    md('<div class="ct-kv">' + "".join(f'<div class="k">{esc(k)}</div><div class="v">{esc(v if v not in (None, "") else "—")}</div>'
                                       for k, v in rows) + "</div>")


def pipeline(nodes: Sequence[dict], selected: Optional[str] = None) -> None:
    """nodes: {name, icon, state (badge text), tone, out (str or None)}; None output -> 'not recorded'."""
    parts = []
    for i, n in enumerate(nodes):
        c = T.TONES.get(n.get("tone", "muted"), n.get("tone"))
        out = n.get("out")
        o = (f'<div class="o">{esc(out)}</div>' if out not in (None, "")
             else f'<div class="o na">{esc(n.get("na", "not recorded"))}</div>')
        parts.append(f'<div class="ct-node{" sel" if selected == n["name"] else ""}" style="--c:{c}">'
                     f'<div class="n">{icon(n.get("icon", "info"), 13)}{esc(n["name"])}</div>'
                     f'<div class="st">{badge(n.get("state", ""), n.get("tone", "muted"))}</div>{o}</div>')
        if i < len(nodes) - 1:
            parts.append('<div class="ct-link"></div>')
    md('<div class="ct-pipe">' + "".join(parts) + "</div>")


def activity(rows: Sequence[Tuple[str, str, str, str]]) -> None:
    """rows: (badge html, id, meta, right meta)."""
    md('<div class="ct-list">' + "".join(
        f'<div class="ct-row">{b}<span class="id">{esc(i)}</span><span class="m">{esc(m)}</span>'
        f'<span class="m">{esc(r)}</span></div>' for b, i, m, r in rows) + "</div>")


def err(msg: str) -> None:
    md(f'<div class="ct-err">{icon("alert", 13)}{esc(msg)}</div>')


def note(text: str) -> None:
    md(f'<div class="ct-note">{text}</div>')


def styled(rows: Sequence[dict], formats: Optional[dict] = None):
    """DataFrame Styler: numeric columns stay numeric (sortable); missing values render as an em dash, not 'None'."""
    import pandas as pd
    df = pd.DataFrame(list(rows))
    return df.style.format(formatter=formats or {}, na_rep="—")


def gr_banner(status: dict) -> None:
    """Shown on views that execute: why execution is disabled (recorded results stay available)."""
    if not status.get("available"):
        st.warning("Execution disabled: GNU Radio is not importable from this Python interpreter. Recorded results "
                   "stay browsable; launch the dashboard from the GNU Radio environment to run (README → Dashboard).",
                   icon=":material/block:")


SOURCE_TONE = {"GNU Radio": "ok", "MATLAB (historical)": "accent", "Fixture": "muted", "Aborted": "warn",
               "Invalid": "err", "Stopped": "warn", "Running": "run"}
STATE_TONE = {"done": "ok", "running": "run", "queued": "run", "done_with_failures": "warn", "stopped": "warn",
              "failed": "err", "blocked": "err", "invalid": "err", "aborted": "warn", "historical": "accent",
              "fixture": "muted"}
