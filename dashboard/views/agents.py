"""AI Agents: the recorded output of each pipeline stage, per episode, with the ACWRA decision timeline."""

import csv
import json
import os

import streamlit as st

import backend as B
from ui import components as C
from ui import data as D
from ui import theme as T

ss = st.session_state
AGENTS = ["GNU Radio", "I/Q Signal", "Spectrum Agent", "Digital Twin", "Prediction Agent", "Cyber Defense",
          "ACWRA", "Next Episode"]
ICON = dict(zip(AGENTS, ["radio", "iq", "radar", "twin", "trend", "shield", "target", "next"]))

dash = [p for p in B.dashboard_runs(("done", "stopped", "failed", "done_with_failures", "running"))
        if B.load_decisions(p)]
camps = B.campaign_dirs()
demo_dir = os.path.join(B.ROOT, "results", "gnuradio", "demo")
demos = [os.path.join(demo_dir, d) for d in sorted(os.listdir(demo_dir), reverse=True)
         if os.path.exists(os.path.join(demo_dir, d, "closed_loop.csv"))] if os.path.isdir(demo_dir) else []

sources = [s for s, ok in (("Dashboard run", dash), ("Campaign episodes", camps), ("Repository demo", demos)) if ok]
if not sources:
    C.empty("No recorded agent decisions", "Run an ACWRA simulation on Live Simulation; its per-episode agent outputs "
            "are shown here.", "bot")
    st.stop()

sel = ss.get("selected")
if "ag_src" not in ss or ss["ag_src"] not in sources:
    ss["ag_src"] = "Dashboard run" if "Dashboard run" in sources else sources[0]
c1, c2, c3, c4 = st.columns([1.9, 1.5, 1.1, 0.8], vertical_alignment="bottom")
src = c1.segmented_control("Source", sources, required=True, key="ag_src", width="stretch")

rows, decs, title, prov_note = [], [], "", ""
if src == "Dashboard run":
    cur = sel["path"] if sel and sel["path"] in dash else dash[0]
    if ss.get("ag_run") not in dash:
        ss["ag_run"] = cur
    run = c2.selectbox("Run", dash, format_func=os.path.basename, key="ag_run")
    rows, decs = B.load_episodes(run), B.load_decisions(run)
    title = os.path.basename(run)
    prov_note = "full agent trace recorded by the dashboard worker (decisions.jsonl)"
elif src == "Campaign episodes":
    if ss.get("ag_camp") not in camps:
        ss["ag_camp"] = next((p for p in camps if p.endswith("grcl1_20261022_v2")), camps[0])
    camp = c2.selectbox("Campaign", camps, format_func=os.path.basename, key="ag_camp")
    steps = D.campaign_steps(camp, D.mtime(os.path.join(camp, "episodes_steps.csv")))
    acw = [r for r in steps if r.get("policy") == "acwra"]
    conds = sorted({r["condition"] for r in acw})
    if not conds:
        C.empty("No ACWRA episodes in this campaign", "", "bot")
        st.stop()
    if ss.get("ag_cond") not in conds:
        ss["ag_cond"] = conds[0]
    cond = c3.selectbox("Condition", conds, key="ag_cond")
    seeds = sorted({r["seed"] for r in acw if r["condition"] == cond}, key=int)
    if ss.get("ag_seed") not in seeds:
        ss["ag_seed"] = seeds[0]
    seed = c4.selectbox("Seed", seeds, key="ag_seed")
    rows = sorted([r for r in acw if r["condition"] == cond and r["seed"] == seed], key=lambda r: int(r["episode"]))
    title = f"{os.path.basename(camp)} · {cond} · seed {seed}"
    prov_note = ("campaign files record each agent's headline output; candidate sets, utility breakdowns and the risk "
                 "gate were not recorded")
else:
    if ss.get("ag_demo") not in demos:
        ss["ag_demo"] = demos[0]
    d = c2.selectbox("Demo", demos, format_func=os.path.basename, key="ag_demo")
    with open(os.path.join(d, "closed_loop.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    title = f"demo {os.path.basename(d)}"
    prov_note = "repository demo closed_loop.csv; the last decision's full trace is in decision_trace.txt"

if not rows:
    C.empty("No episodes", "The selected source has no recorded episodes.", "bot")
    st.stop()

if ss.get("ag_ep_key") != title or ss.get("ag_ep", -1) >= len(rows):      # new source: start at its last episode
    ss["ag_ep_key"], ss["ag_ep"] = title, len(rows) - 1
ep = st.select_slider("Episode", options=list(range(len(rows))), key="ag_ep") if len(rows) > 1 else 0
e = rows[ep]
dec = decs[ep] if ep < len(decs) else None
full = dec is not None and "spectrum" in dec
nxt = rows[ep + 1] if ep + 1 < len(rows) else None


def _applied(k):
    """Was episode k's decision applied to episode k+1? From the recorded rows only."""
    if k + 1 >= len(rows):
        return "— (last episode)"
    return "yes" if rows[k + 1]["modulation_applied"] == rows[k]["next_modulation"] else "no"


# ------------------------------------------------------------------ pipeline
if full:
    gate = B.risk_gate(dec)
    nodes = [
        ("GNU Radio", "executed", "ok", f"{e['modulation_applied']} · {e['channel']}/{e['fading_mode']} · "
                                        f"SNR {C.fmt(e['snr_db_configured'], '.1f')} dB"),
        ("I/Q Signal", e["provenance"], "ok" if e["provenance"] == "gnuradio_export" else "warn",
         f"{e['bits']} bits · BER {C.fmt(e['ber'], '.2e')}"),
        ("Spectrum Agent", "classified", "info", f"{dec['spectrum']['modulation']} · conf "
                                                 f"{C.fmt(dec['spectrum']['confidence'], '.2f')}"),
        ("Digital Twin", "updated", "info", f"{dec['twin']['condition']} · SNR {C.fmt(dec['twin']['snr_db'], '.1f')} dB"),
        ("Prediction Agent", dec["prediction"]["level"], "err" if dec["prediction"]["level"] in ("HIGH", "CRITICAL")
         else "warn" if dec["prediction"]["level"] == "MEDIUM" else "info",
         f"risk {C.fmt(dec['prediction']['risk'], '.3f')}"),
        ("Cyber Defense", gate.split(" ")[0], "err" if gate.startswith("CLOSED") else "ok",
         ", ".join(dec["candidates"])),
        ("ACWRA", "selected", "accent", f"{dec['selected']} · U {C.fmt(dec['utility'], '+.3f')}"),
        ("Next Episode", f"applied: {_applied(ep).split(' ')[0]}", "ok" if _applied(ep) == "yes" else "muted",
         e["next_modulation"]),
    ]
elif dec is not None:                      # baseline policy in a dashboard run: rule only
    nodes = [("GNU Radio", "executed", "ok", f"{e['modulation_applied']} · {e['channel']}"),
             ("I/Q Signal", e["provenance"], "ok" if e["provenance"] == "gnuradio_export" else "warn", f"{e['bits']} bits")] + \
            [(a, "not used", "muted", None) for a in AGENTS[2:6]] + \
            [("ACWRA", "rule", "muted", dec.get("rule")), ("Next Episode", "applied", "ok", e["next_modulation"])]
else:                                      # campaign / demo rows: headline outputs only
    nodes = [
        ("GNU Radio", "executed", "ok", f"{e['modulation_applied']} · {e['channel']}/{e['fading_mode']}"),
        ("I/Q Signal", e.get("provenance") or "?", "ok" if e.get("provenance") == "gnuradio_export" else "warn",
         f"{e['bits']} bits · BER {C.fmt(e['ber'], '.2e')}"),
        ("Spectrum Agent", "classified", "info", f"{e['detected_modulation']} · conf {C.fmt(e['detected_confidence'], '.2f')}"
         if e.get("detected_modulation") else None),
        ("Digital Twin", "updated", "info", f"est. SNR {C.fmt(e.get('estimated_snr_db'), '.2f')} dB"
         if e.get("estimated_snr_db") else None),
        ("Prediction Agent", "scored", "info", f"risk {C.fmt(e.get('risk_score'), '.3f')}" if e.get("risk_score") else None),
        ("Cyber Defense", "not recorded", "muted", None),
        ("ACWRA", "selected", "accent", f"{e['selected_strategy']} · U {C.fmt(e.get('expected_utility'), '+.3f')}"
         if e.get("selected_strategy") else None),
        ("Next Episode", f"applied: {_applied(ep).split(' ')[0]}", "ok" if _applied(ep) == "yes" else "muted",
         e["next_modulation"]),
    ]

if ss.get("ag_agent") not in AGENTS:
    ss["ag_agent"] = "ACWRA"
pick = ss["ag_agent"]
with st.container(border=True, key="panel_flow"):
    C.section("Pipeline", "bot", f'<span class="mono">{C.esc(title)}</span> · episode {ep} · '
                                 f'{C.badge(src, "info")}')
    C.pipeline([{"name": n, "icon": ICON[n], "state": s, "tone": t, "out": o} for n, s, t, o in nodes], selected=pick)
    C.note(C.esc(prov_note))

# ------------------------------------------------------------------ agent detail
a, b = st.columns([1.15, 1], gap="medium")
with a:
    with st.container(border=True, key="panel_agent"):
        pick = st.segmented_control("Agent", AGENTS, required=True, key="ag_agent", width="stretch")
        C.section(f"{pick} · recorded output", ICON[pick], f"episode {ep}")
        raw = None
        if full:
            raw = {"GNU Radio": {k: e[k] for k in ("experiment_id", "modulation_applied", "channel", "fading_mode",
                                                    "snr_db_configured", "snr_db_measured", "interference_power",
                                                    "interference_power_measured", "wall_time_s") if k in e},
                   "I/Q Signal": {k: e[k] for k in ("provenance", "content_sha256", "bits", "ber", "ber_theory", "per",
                                                     "goodput_bps", "sinr_db_post_fade") if k in e},
                   "Spectrum Agent": dec["spectrum"], "Digital Twin": dec["twin"], "Prediction Agent": dec["prediction"],
                   "Cyber Defense": {"risk_gate": B.risk_gate(dec), "candidates": dec["candidates"],
                                     "rationale": dec.get("defense_rationale")},
                   "ACWRA": {"selected": dec["selected"], "expected_utility": dec["utility"],
                             "agent_confidence": dec.get("confidence"), "applied_next": dec.get("applied_next")},
                   "Next Episode": {"next_modulation": e["next_modulation"], "applied_to_next_episode": _applied(ep),
                                    "next_episode_modulation": nxt["modulation_applied"] if nxt else None}}[pick]
        else:
            keys = {"GNU Radio": ("experiment_id", "modulation_applied", "channel", "fading_mode", "snr_db_configured",
                                  "snr_db_measured", "interference_power", "interference_power_measured"),
                    "I/Q Signal": ("provenance", "content_sha256", "bits", "ber", "ber_theory", "per", "goodput_bps"),
                    "Spectrum Agent": ("detected_modulation", "detected_confidence"),
                    "Digital Twin": ("estimated_snr_db",), "Prediction Agent": ("risk_score",),
                    "Cyber Defense": (), "ACWRA": ("selected_strategy", "expected_utility", "acwra_modulation"),
                    "Next Episode": ("next_modulation",)}[pick]
            raw = {k: e[k] for k in keys if e.get(k) not in (None, "")}
            if dec is not None and pick == "ACWRA":
                raw = dict(raw, **{k: v for k, v in dec.items() if k in ("rule", "policy", "sinr_db_measured")})
            if pick == "Next Episode":
                raw["applied_to_next_episode"] = _applied(ep)
        if raw:
            C.kv([(k, C.fmt(v, ".6g") if isinstance(v, float) else
                   ", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in raw.items() if k != "rationale"])
            if isinstance(raw.get("rationale"), str) and raw["rationale"]:
                C.note(f"<b>Rationale:</b> {C.esc(raw['rationale'])}")
        else:
            C.empty("Not recorded", "This source does not record this agent's output.", ICON[pick])
        if full and pick == "ACWRA" and dec.get("trace"):
            with st.expander("ACWRA decision trace"):
                st.code(str(dec["trace"]), language=None)
        if src == "Repository demo" and pick == "ACWRA":
            tf = os.path.join(ss["ag_demo"], "decision_trace.txt")
            if os.path.exists(tf):
                with st.expander("decision_trace.txt (last decision of the demo)"):
                    st.code(D.text_file(tf, D.mtime(tf)), language=None)

with b:
    with st.container(border=True, key="panel_scores"):
        C.section("Candidate utility scores", "target", f"episode {ep}")
        if full and dec.get("scores"):
            import plotly.graph_objects as go  # noqa: F401
            sc = dec["scores"]
            f = T.fig(230, xaxis_title="expected utility", bargap=.35)
            f.add_bar(y=[s["strategy"] for s in sc], x=[s["utility_score"] for s in sc], orientation="h",
                      marker=dict(color=[T.CYAN if s["strategy"] == dec["selected"] else T.BORDER for s in sc]),
                      customdata=[[s["modulation"], s["predicted_ber"]] for s in sc],
                      hovertemplate="%{y} (%{customdata[0]})<br>U = %{x:+.4f}<br>pred. BER %{customdata[1]:.2e}"
                                    "<extra></extra>")
            f.update_yaxes(autorange="reversed")
            st.plotly_chart(f, width="stretch", config=T.PLOT_CONFIG)
            st.dataframe([{"strategy": s["strategy"], "modulation": s["modulation"], "pred. BER": s["predicted_ber"],
                           "T_norm": s["t_norm"], "SE_norm": s["se_norm"], "K_c": s["complexity_prior"],
                           "utility": s["utility_score"], "selected": s["strategy"] == dec["selected"]} for s in sc],
                         hide_index=True, width="stretch",
                         column_config={"pred. BER": st.column_config.NumberColumn(format="%.3e"),
                                        "utility": st.column_config.NumberColumn(format="%+.4f"),
                                        "T_norm": st.column_config.NumberColumn(format="%.3f"),
                                        "SE_norm": st.column_config.NumberColumn(format="%.3f"),
                                        "selected": st.column_config.CheckboxColumn()})
        elif full:
            C.empty("No candidate scores", "The risk gate left a single candidate.", "target")
        else:
            C.empty("Not recorded for this source",
                    "Candidate sets and utility breakdowns are recorded by dashboard ACWRA runs only.", "target")

# ------------------------------------------------------------------ decision timeline
with st.container(border=True, key="panel_tl"):
    C.section("Decision timeline", "clock", "all episodes of this source")
    tl = []
    for k, r in enumerate(rows):
        d = decs[k] if k < len(decs) else None
        fd = d is not None and "spectrum" in d
        tl.append({
            "episode": k, "applied": r["modulation_applied"],
            "candidates": ", ".join(d["candidates"]) if fd else "not recorded",
            "top utility": C.fmt(max((s["utility_score"] for s in d["scores"]), default=None), "+.4f") if fd
            else "not recorded",
            "risk": float(d["prediction"]["risk"]) if fd else (float(r["risk_score"]) if r.get("risk_score") else None),
            "risk level": d["prediction"]["level"] if fd else "—",
            "risk gate": B.risk_gate(d).split(" ")[0] if fd else "not recorded",
            "selected": d["selected"] if fd else (r.get("selected_strategy") or (d or {}).get("rule") or "—"),
            "next": r["next_modulation"], "applied to next": _applied(k),
        })
    st.dataframe(tl, hide_index=True, width="stretch", height=min(38 + 35 * len(tl), 420),
                 column_config={"risk": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.3f")})
    if full:
        st.download_button("Download decisions (JSON)", json.dumps(decs, indent=2, default=str),
                           file_name=f"{title}_decisions.json", mime="application/json", icon=":material/download:")
