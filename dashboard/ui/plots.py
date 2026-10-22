"""
Scientific plots. Every function draws only the arrays/rows it is given; axis titles
carry units. Figures use the shared template in ui/theme.py.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import plotly.graph_objects as go

import backend as B
from ui import theme as T

MOD_ORDER = {"BPSK": 0, "QPSK": 1, "OFDM-QPSK": 2}


def waveform(sp: Dict[str, Any], n: int = 160, show_tx: bool = True, height: int = 340) -> go.Figure:
    n = int(min(n, sp["iq"].size))
    x = np.arange(n)
    f = T.fig(height, xaxis_title="exported sample index", yaxis_title="amplitude (normalised)")
    f.add_scatter(x=x, y=sp["iq"][:n].real, name="Rx I", line=dict(color=T.CYAN, width=1.4),
                  hovertemplate="n=%{x}<br>I=%{y:.4f}<extra>Rx I</extra>")
    f.add_scatter(x=x, y=sp["iq"][:n].imag, name="Rx Q", line=dict(color=T.INDIGO, width=1.4),
                  hovertemplate="n=%{x}<br>Q=%{y:.4f}<extra>Rx Q</extra>")
    if show_tx:
        f.add_scatter(x=x, y=sp["tx"][:n].real, name="Tx I (reference)", line=dict(color=T.SLATE, width=1, dash="dot"),
                      hovertemplate="n=%{x}<br>I=%{y:.4f}<extra>Tx I</extra>")
    return f


def constellation(z: np.ndarray, title: str, color: str = T.CYAN, height: int = 340) -> go.Figure:
    f = T.fig(height, title=title, xaxis_title="in-phase (I)", yaxis_title="quadrature (Q)")
    f.add_scattergl(x=z.real, y=z.imag, mode="markers", marker=dict(size=3.2, color=color, opacity=.45),
                    showlegend=False, hovertemplate="I=%{x:.3f}<br>Q=%{y:.3f}<extra></extra>")
    f.update_yaxes(scaleanchor="x", scaleratio=1)
    return f


def spectrum(sp: Dict[str, Any], height: int = 340) -> go.Figure:
    f = T.fig(height, xaxis_title="frequency (kHz)", yaxis_title="|FFT|² (dB rel. peak)")
    f.add_scatter(x=sp["f_spec"] / 1e3, y=sp["spec_db"], line=dict(color=T.CYAN, width=1.3), showlegend=False,
                  fill="tozeroy", fillcolor="rgba(56,217,255,.06)",
                  hovertemplate="%{x:.2f} kHz<br>%{y:.1f} dB<extra></extra>")
    f.update_yaxes(range=[max(float(np.min(sp["spec_db"])), -90), 3])
    return f


def psd(sp: Dict[str, Any], height: int = 340) -> go.Figure:
    f = T.fig(height, xaxis_title="frequency (kHz)", yaxis_title="PSD (dB/Hz)")
    f.add_scatter(x=sp["f_psd"] / 1e3, y=sp["psd_db"], line=dict(color=T.SUCCESS, width=1.3), showlegend=False,
                  hovertemplate="%{x:.2f} kHz<br>%{y:.1f} dB/Hz<extra></extra>")
    return f


def _num(v) -> Optional[float]:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def episode_metrics(eps: List[Dict[str, Any]], height: int = 280) -> go.Figure:
    """Measured BER (log, left) and goodput (right) per episode of one run."""
    x = [int(e["episode"]) for e in eps]
    ber = [_num(e.get("ber")) for e in eps]
    f = T.fig(height, yaxis=dict(type="log", title="BER", exponentformat="e"),
              yaxis2=dict(overlaying="y", side="right", title="goodput (kb/s)", showgrid=False, rangemode="tozero",
                          tickfont=dict(family=T.FONT_MONO, size=10.5, color=T.TEXT_2), linecolor=T.BORDER))
    gp = [(_num(e.get("goodput_bps")) or 0.0) / 1e3 if _num(e.get("goodput_bps")) is not None else None for e in eps]
    f.add_bar(x=x, y=gp, name="goodput", yaxis="y2", marker=dict(color="rgba(129,140,248,.35)",
              line=dict(color=T.INDIGO, width=1)), hovertemplate="ep %{x}: %{y:.1f} kb/s<extra>goodput</extra>")
    # BER = 0 cannot be drawn on a log axis: those episodes are marked separately, not clipped to a fake value
    pos = [(xi, b) for xi, b in zip(x, ber) if b is not None and b > 0]
    zero = [xi for xi, b in zip(x, ber) if b == 0]
    if pos:
        f.add_scatter(x=[p[0] for p in pos], y=[p[1] for p in pos], name="BER", mode="lines+markers",
                      line=dict(color=T.CYAN, width=1.6), marker=dict(size=7),
                      hovertemplate="ep %{x}: BER %{y:.3e}<extra></extra>")
    if zero:
        for xi in zero:
            f.add_annotation(x=xi, y=0, yref="paper", text="0 errors", showarrow=False, yshift=10,
                             font=dict(size=10, color=T.SUCCESS))
    f.update_xaxes(title="episode", dtick=1)
    return f


def decision_timeline(eps: List[Dict[str, Any]], height: int = 280) -> go.Figure:
    x = [int(e["episode"]) for e in eps]
    f = T.fig(height, yaxis=dict(tickvals=list(MOD_ORDER.values()), ticktext=list(MOD_ORDER), title="modulation",
                                 range=[-.4, 2.4]),
              yaxis2=dict(overlaying="y", side="right", range=[0, 1], title="risk score", showgrid=False,
                          tickfont=dict(family=T.FONT_MONO, size=10.5, color=T.TEXT_2), linecolor=T.BORDER))
    f.add_scatter(x=x, y=[MOD_ORDER.get(e["modulation_applied"]) for e in eps], mode="lines+markers",
                  name="applied", line=dict(color=T.CYAN, shape="hv", width=1.8), marker=dict(size=7))
    f.add_scatter(x=x, y=[MOD_ORDER.get(e["next_modulation"]) for e in eps], mode="markers", name="decided for next",
                  marker=dict(color=T.WARNING, symbol="triangle-right", size=10))
    risks = [_num(e.get("risk_score")) for e in eps]
    if any(r is not None for r in risks):
        f.add_scatter(x=x, y=risks, yaxis="y2", name="risk", mode="lines+markers",
                      line=dict(color=T.ERROR, dash="dot", width=1.3), marker=dict(size=5))
    f.update_xaxes(title="episode", dtick=1)
    return f


def ber_validation(bv: List[Dict[str, Any]], height: int = 300) -> go.Figure:
    f = T.fig(height, xaxis_title="Es/N0 (dB)", yaxis=dict(type="log", title="BER", exponentformat="e"))
    for mod, col in T.MOD_COLORS.items():
        rr = [r for r in bv if r["modulation"] == mod and r["ber"] > 0]
        if rr:
            f.add_scatter(x=[r["snr_db"] for r in rr], y=[r["ber"] for r in rr], mode="markers", name=mod,
                          marker=dict(color=col, size=7),
                          error_y=dict(type="data", symmetric=False, array=[r["hi"] - r["ber"] for r in rr],
                                       arrayminus=[r["ber"] - r["lo"] for r in rr], thickness=1, width=3),
                          hovertemplate="%{x} dB: BER %{y:.2e}<extra>" + mod + " measured</extra>")
        th = [r for r in bv if r["modulation"] == mod]
        if th:
            f.add_scatter(x=[r["snr_db"] for r in th], y=[r["theory"] for r in th], mode="lines",
                          line=dict(color=col, dash="dot", width=1), showlegend=False,
                          hovertemplate="%{x} dB: %{y:.2e}<extra>" + mod + " theory</extra>")
    return f


def per_curve(pc: List[Dict[str, Any]], height: int = 300) -> go.Figure:
    f = T.fig(height, xaxis_title="Es/N0 (dB)", yaxis=dict(title="PER", range=[-.03, 1.03]))
    for mod, col in T.MOD_COLORS.items():
        rr = [r for r in pc if r["modulation"] == mod]
        if rr:
            f.add_scatter(x=[r["snr_db"] for r in rr], y=[r["per"] for r in rr], mode="lines+markers", name=mod,
                          line=dict(color=col, width=1.6), customdata=[r["episodes"] for r in rr],
                          hovertemplate="%{x} dB: PER %{y:.3f} (%{customdata} episodes)<extra>" + mod + "</extra>")
    return f


def policy_bars(means: List[Dict[str, Any]], metric: str, title: str, height: int = 300, log: bool = False) -> go.Figure:
    """Horizontal bars, best policy on top (highest goodput / lowest BER, PER)."""
    m = sorted(means, key=lambda r: r[metric], reverse=metric == "goodput_kbps")
    names = [B.POLICY_LABELS.get(r["policy"], r["policy"]) for r in m]
    f = T.fig(height, xaxis=dict(title=title, type="log" if log else "linear"), bargap=.3)
    f.add_bar(y=names, x=[r[metric] for r in m], orientation="h", showlegend=False,
              marker=dict(color=[T.POLICY_COLORS.get(r["policy"], T.SLATE) for r in m], line=dict(width=0)),
              customdata=[r["runs"] for r in m], hovertemplate="%{y}<br>%{x:.4g} (%{customdata} runs)<extra></extra>")
    f.update_yaxes(autorange="reversed", ticks="", tickfont=dict(family=T.FONT_UI, size=11, color=T.TEXT))
    f.update_layout(margin=dict(l=118, r=16, t=12, b=44))
    return f


def paired_forest(rows: List[Dict[str, Any]], scale: float, xtitle: str, height: int = 280) -> go.Figure:
    """ACWRA − baseline mean difference with the recorded 95 % bootstrap CI, one row per baseline."""
    f = T.fig(height, xaxis_title=xtitle)
    names = [B.POLICY_LABELS.get(r["b"], r["b"]) for r in rows]
    f.add_scatter(x=[r["mean_diff"] * scale for r in rows], y=names, mode="markers", showlegend=False,
                  marker=dict(color=T.CYAN, size=9, symbol="diamond"),
                  error_x=dict(type="data", symmetric=False, thickness=1.4, width=4, color=T.CYAN,
                               array=[(r["ci95_high"] - r["mean_diff"]) * scale for r in rows],
                               arrayminus=[(r["mean_diff"] - r["ci95_low"]) * scale for r in rows]),
                  customdata=[[fmt_p(r["wilcoxon_p"]), f"{r['wins']}/{r['ties']}/{r['losses']}", r["n_conditions"]]
                              for r in rows],
                  hovertemplate="%{y}: %{x:.4g}<br>p = %{customdata[0]} · ACWRA higher/tie/lower "
                                "%{customdata[1]} · %{customdata[2]} conditions<extra></extra>")
    f.add_vline(x=0, line=dict(color=T.TEXT_3, dash="dot", width=1))
    f.update_yaxes(autorange="reversed")
    return f


def fmt_p(p) -> str:
    try:
        return "n/a" if p is None or not np.isfinite(float(p)) else f"{float(p):.2g}"
    except (TypeError, ValueError):
        return "n/a"


def heatmap(rows: List[Dict[str, Any]], metric: str, title: str, height: int = 420, reverse: bool = False) -> go.Figure:
    conds = sorted({r["condition"] for r in rows}, key=lambda c: (B.parse_condition(c)["kind"] != "static", c))
    pols = [p for p in B.POLICY_LABELS if any(r["policy"] == p for r in rows)]
    val = {(r["condition"], r["policy"]): r[metric] for r in rows}
    z = [[val.get((c, p)) for c in conds] for p in pols]
    scale = [[0, "#0F1B2E"], [.5, "#245C7A"], [1, T.CYAN]]
    f = T.fig(height)
    f.add_heatmap(z=z, x=conds, y=[B.POLICY_LABELS[p] for p in pols], colorscale=scale, reversescale=reverse,
                  colorbar=dict(title=dict(text=title, side="right", font=dict(size=11, color=T.TEXT_2)), thickness=10,
                                outlinewidth=0, tickfont=dict(family=T.FONT_MONO, size=10, color=T.TEXT_2)),
                  hovertemplate="%{y}<br>%{x}<br>" + title + ": %{z:.4g}<extra></extra>", xgap=1, ygap=1)
    f.update_xaxes(tickangle=-40, tickfont=dict(size=9.5), showgrid=False)
    f.update_yaxes(showgrid=False)
    f.update_layout(margin=dict(l=110, r=16, t=16, b=130))
    return f
