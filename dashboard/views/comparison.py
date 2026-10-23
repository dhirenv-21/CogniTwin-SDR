"""Policy Comparison: recorded campaign means and condition-level paired ACWRA − baseline statistics."""

import math
import os

import streamlit as st

import backend as B
from ui import components as C
from ui import data as D
from ui import plots as P
from ui import theme as T

ss = st.session_state
camps = B.campaign_dirs()
if not camps:
    C.empty("No completed campaign", "Policy statistics come from campaign runs.csv files. Launch one in Campaign Lab.",
            "scale")
    st.stop()

if ss.get("pc_camp") not in camps:
    ss["pc_camp"] = next((p for p in camps if os.path.basename(p) == "grcl1_20261022_v2"), camps[-1])

with st.container(border=True, key="panel_filters"):
    c0, c1, c2, c3 = st.columns([1.2, 1.4, 1.2, 1.2])
    camp = c0.selectbox("Campaign", camps, format_func=os.path.basename, key="pc_camp")
    table = D.condition_table(camp, D.runs_mtime(camp))
    conds_all = sorted({r["condition"] for r in table})
    meta = {c: B.parse_condition(c) for c in conds_all}
    ch_opts = sorted({m["channel"] for m in meta.values()})
    snr_opts = sorted({m["snr_db"] for m in meta.values() if m["snr_db"] is not None})
    jam_opts = sorted({m["jammer"] for m in meta.values() if m["jammer"] is not None})
    for k, opts in (("pc_ch", ch_opts), ("pc_snr", snr_opts), ("pc_jam", jam_opts)):
        if not isinstance(ss.get(k), list) or not set(ss[k]) <= set(opts):
            ss[k] = list(opts)
    chs = c1.multiselect("Channel", ch_opts, key="pc_ch", help="'dynamic' = ramp/step schedules")
    snr = c2.multiselect("SNR (dB)", snr_opts, key="pc_snr", format_func=lambda v: f"{v:g}",
                         help="Static conditions only; dynamic schedules have no single SNR")
    jam = c3.multiselect("Jammer J", jam_opts, key="pc_jam", format_func=lambda v: f"{v:g}")
    C.note("Modulation filter: not applicable — runs are per policy, and adaptive policies change modulation "
           "between episodes. Applied modulations are visible per episode on AI Agents.")

incomplete = C.incomplete_campaign_banner(camp)
conds = [c for c in conds_all if meta[c]["channel"] in chs and
         (meta[c]["kind"] == "dynamic" or (meta[c]["snr_db"] in snr and meta[c]["jammer"] in jam))]
if not conds:
    C.empty("No condition matches the filters", "Widen the channel, SNR or jammer selection.", "scale")
    st.stop()

comp = D.comparison(camp, D.runs_mtime(camp), tuple(conds) if len(conds) < len(conds_all) else None)
means = comp["means"]
paired = comp["paired"]

# ------------------------------------------------------------------ findings (measured, not asserted)
best_g = max(means, key=lambda r: r["goodput_kbps"])
best_b = min(means, key=lambda r: r["ber"])
best_p = min(means, key=lambda r: r["per"])
acw = next((r for r in means if r["policy"] == "acwra"), None)


def _sig(r):
    p = r["wilcoxon_p"]
    return p is not None and math.isfinite(p) and p < 0.05 and (r["ci95_low"] > 0 or r["ci95_high"] < 0)


def _acwra_better(r):
    """+1 ACWRA better, -1 worse (BER: lower is better), 0 inconclusive."""
    if not _sig(r):
        return 0
    up = r["mean_diff"] > 0
    return (1 if up else -1) if r["metric"] != "ber" else (-1 if up else 1)


better = sum(1 for r in paired if r["metric"] in ("goodput_bps", "ber") and _acwra_better(r) > 0)
worse = sum(1 for r in paired if r["metric"] in ("goodput_bps", "ber") and _acwra_better(r) < 0)
incon = sum(1 for r in paired if r["metric"] in ("goodput_bps", "ber") and _acwra_better(r) == 0)
C.metrics([
    C.metric("Highest mean goodput", B.POLICY_LABELS[best_g["policy"]], f"{C.fmt(best_g['goodput_kbps'], '.1f')} kb/s",
             best_g["policy"] == "acwra" and "info" or "accent", "gauge", compact=True),
    C.metric("Lowest mean BER", B.POLICY_LABELS[best_b["policy"]], C.fmt(best_b["ber"], ".4f"), "accent", "activity",
             compact=True),
    C.metric("Lowest mean PER", B.POLICY_LABELS[best_p["policy"]], C.fmt(best_p["per"], ".3f"), "accent", "signal",
             compact=True),
    C.metric("ACWRA significantly better", f"{better}", "baseline × metric pairs (goodput, BER)", "ok", "check",
             compact=True),
    C.metric("ACWRA significantly worse", f"{worse}", "p < 0.05 and CI excludes 0", "err", "x", compact=True),
    C.metric("Inconclusive", f"{incon}", "CI spans 0, p ≥ 0.05, or too few pairs", "muted", "info", compact=True),
], min_width=165)
C.note(f'<span class="mono">{C.esc(os.path.basename(camp))}</span> · {comp["runs"]} runs · '
       f'{comp["conditions"]} of {len(conds_all)} conditions · means over runs; paired statistics over conditions '
       f'(seeds averaged), 95 % bootstrap CI, Wilcoxon signed-rank (n/a below 5 non-zero pairs).')

# ------------------------------------------------------------------ means
with st.container(border=True, key="panel_means"):
    C.section("Policy means", "scale", "lower BER / PER is better · higher goodput is better")
    a, b, c = st.columns(3)
    a.plotly_chart(P.policy_bars(means, "goodput_kbps", "goodput (kb/s)", 280), width="stretch", config=T.PLOT_CONFIG)
    b.plotly_chart(P.policy_bars(means, "ber", "BER", 280), width="stretch", config=T.PLOT_CONFIG)
    c.plotly_chart(P.policy_bars(means, "per", "packet error rate", 280), width="stretch", config=T.PLOT_CONFIG)
    st.dataframe([{"policy": B.POLICY_LABELS.get(r["policy"], r["policy"]), "runs": r["runs"],
                   "goodput (kb/s)": r["goodput_kbps"], "BER": r["ber"], "PER": r["per"]}
                  for r in sorted(means, key=lambda r: -r["goodput_kbps"])], hide_index=True, width="stretch",
                 column_config={"goodput (kb/s)": st.column_config.NumberColumn(format="%.2f"),
                                "BER": st.column_config.NumberColumn(format="%.5f"),
                                "PER": st.column_config.NumberColumn(format="%.4f")})

# ------------------------------------------------------------------ paired statistics
with st.container(border=True, key="panel_paired"):
    C.section("ACWRA − baseline (condition-level paired)", "target", "diamond = mean difference · bar = 95 % CI")
    if not paired:
        C.empty("Paired statistics unavailable", "ACWRA is not among the policies of the filtered runs.", "target")
    else:
        a, b = st.columns(2, gap="medium")
        for col, metric, scale, xt in ((a, "goodput_bps", 1e-3, "Δ goodput (kb/s) · right = ACWRA higher"),
                                       (b, "ber", 1.0, "Δ BER · right = ACWRA higher (worse)")):
            rr = [r for r in paired if r["metric"] == metric]
            if rr:
                col.plotly_chart(P.paired_forest(rr, scale, xt, 60 + 44 * len(rr)), width="stretch",
                                 config=T.PLOT_CONFIG)
        verdict = {1: "ACWRA better", -1: "ACWRA worse", 0: "inconclusive"}
        st.dataframe([{"baseline": B.POLICY_LABELS.get(r["b"], r["b"]), "metric": r["metric"].replace("_bps", ""),
                       "mean Δ": r["mean_diff"], "CI low": r["ci95_low"], "CI high": r["ci95_high"],
                       "ACWRA higher / tie / lower": f"{r['wins']} / {r['ties']} / {r['losses']}",
                       "conditions": r["n_conditions"], "Wilcoxon p": P.fmt_p(r["wilcoxon_p"]),
                       "result": verdict[_acwra_better(r)]} for r in paired],
                     hide_index=True, width="stretch",
                     column_config={"mean Δ": st.column_config.NumberColumn(format="%.4g"),
                                    "CI low": st.column_config.NumberColumn(format="%.4g"),
                                    "CI high": st.column_config.NumberColumn(format="%.4g")})
        C.note("For BER a positive Δ means ACWRA had more bit errors. 'n/a' = statistic not computable "
               "(fewer than five non-zero paired differences) — it is not a zero.")

# ------------------------------------------------------------------ per condition
with st.container(border=True, key="panel_heat"):
    C.section("Per condition", "layers", "seed-averaged values from runs.csv")
    rows = [r for r in table if r["condition"] in set(conds)]
    t1, t2, t3 = st.tabs(["Goodput", "BER", "PER"])
    h = 140 + 34 * len({r["policy"] for r in rows})
    with t1:
        st.plotly_chart(P.heatmap(rows, "goodput_kbps", "goodput kb/s", h + 120), width="stretch", config=T.PLOT_CONFIG)
    with t2:
        st.plotly_chart(P.heatmap(rows, "ber", "BER", h + 120, reverse=True), width="stretch", config=T.PLOT_CONFIG)
    with t3:
        st.plotly_chart(P.heatmap(rows, "per", "PER", h + 120, reverse=True), width="stretch", config=T.PLOT_CONFIG)
    C.note("Colour scale: brighter = better for every metric (reversed for BER and PER).")
