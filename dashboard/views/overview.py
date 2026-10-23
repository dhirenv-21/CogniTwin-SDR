"""Overview: system status, latest results and recent activity (recorded data only)."""

import csv
import os

import streamlit as st

import backend as B
from ui import components as C
from ui import data as D
from ui import plots as P
from ui import theme as T

ss = st.session_state
status = D.gr_status()
active = B.active_jobs()
stats = D.overview_stats()
latest = B.latest_run_with_episodes()
eps = B.load_episodes(latest) if latest else []
last = eps[-1] if eps else None
camp_active = [p for p in active if os.path.dirname(p) == B.CAMPAIGNS]
camps = sorted(B.campaign_dirs(), key=lambda p: str(B.campaign_info(p).get("created") or ""))   # oldest first

# ------------------------------------------------------------------ metric cards
label, level, detail = B.gnuradio_state(status, bool(active))
gr_value = {"ok": "Ready", "run": "Executing", "err": "Not installed", "warn": "Import failed"}[level]
gr_sub = f"v{status['version']} · {'job running' if active else 'idle'}" if status["available"] else detail
if camp_active:
    cs = B.job_status(camp_active[0])
    camp_val, camp_sub, camp_tone = (f"{cs.get('done', 0)}/{cs.get('total') or '?'}",
                                     f"{os.path.basename(camp_active[0])} · {cs.get('state')}", "run")
else:
    camp_val, camp_sub, camp_tone = ("Idle", f"last completed: {os.path.basename(camps[-1])}" if camps
                                     else "no completed campaign", "muted")
ber_last = C.fmt(last["ber"], ".2e") if last else "—"
C.metrics([
    C.metric("GNU Radio", gr_value, gr_sub, level, "radio", value_tone=level if level != "ok" else None),
    C.metric("Completed runs", f"{stats['dashboard_runs'] + stats['campaign_runs']:,}",
             f"{stats['dashboard_runs']} dashboard · {stats['campaign_runs']:,} campaign", "info", "layers"),
    C.metric("Validated episodes", f"{stats['validated_episodes']:,}",
             f"provenance gnuradio_export · of {stats['episodes']:,}", "ok", "shield"),
    C.metric("Latest BER", ber_last, f"{os.path.basename(latest)} · ep {last['episode']}" if last
             else "no dashboard simulation yet", "accent", "activity"),
    C.metric("Latest goodput", C.fmt(float(last["goodput_bps"]) / 1e3, ".1f") if last else "—",
             f"{last['modulation_applied']} · {last['channel']}" if last else "no dashboard simulation yet",
             "accent", "gauge", unit="kb/s"),
    C.metric("Campaign", camp_val, camp_sub, camp_tone, "flask"),
], min_width=150)

# ------------------------------------------------------------------ latest signal + decision
c1, c2 = st.columns([1.75, 1], gap="medium")
with c1:
    with st.container(border=True, key="panel_sig"):
        src_path, ep_idx, export, vinfo, src_label = None, None, None, None, None
        if latest and eps:
            ep_idx = len(eps) - 1
            f = os.path.join(latest, f"ep{ep_idx}.npz")
            if os.path.exists(f):
                try:
                    export, vinfo = D.export(latest, ep_idx, D.mtime(f))
                    src_label = (f"{os.path.basename(latest)} · episode {ep_idx}", "Dashboard run")
                except Exception as exc:  # recorded as a problem, never replaced by other data
                    C.err(f"latest export unreadable: {exc}")
        if export is None and D.demo_export_path():
            f = D.demo_export_path()
            export, vinfo = D.npz(f, D.mtime(f))
            src_label = (os.path.basename(os.path.dirname(f)), "Repository demo")
        if export is not None:
            prov = vinfo["provenance"]
            C.section("Latest signal", "wave",
                      C.badge(src_label[1], "info") + " " + C.badge(prov, "ok" if prov == "gnuradio_export" else "warn"))
            sp = D.signal_products(f"{src_label[0]}:{D.mtime(f)}", export)
            a, b = st.columns(2)
            a.plotly_chart(P.constellation(sp["eq"][:int(ss["pref_const_n"])], "equalised constellation", height=290),
                           width="stretch", config=T.PLOT_CONFIG)
            b.plotly_chart(P.psd(sp, height=290), width="stretch", config=T.PLOT_CONFIG)
            C.note(f"<b>{C.esc(src_label[0])}</b> · {C.esc(export['modulation'])} · {C.esc(export['channel_type'])} · "
                   f"configured SNR {C.fmt(export['snr_db'], '.1f')} dB · J {C.fmt(export['interference_power'], '.3f')}"
                   f" · validation {C.esc(vinfo['summary'])}")
        else:
            C.section("Latest signal", "wave")
            C.empty("No signal recorded yet", "Run a simulation on the Live Simulation page to see its I/Q data here.",
                    "wave")

with c2:
    with st.container(border=True, key="panel_dec"):
        decs = B.load_decisions(latest) if latest else []
        dec = decs[-1] if decs else None
        demo_dir = os.path.join(B.ROOT, "results", "gnuradio", "demo")
        demo_rows = []
        if dec is None and os.path.isdir(demo_dir):
            for rid in sorted(os.listdir(demo_dir), reverse=True):
                f = os.path.join(demo_dir, rid, "closed_loop.csv")
                if os.path.exists(f):
                    with open(f, newline="") as fh:
                        demo_rows = [dict(r, _run=rid) for r in csv.DictReader(fh)]
                    break
        if dec is not None:
            C.section("Latest agent decision", "bot", C.badge("Dashboard run", "info"))
            gate = B.risk_gate(dec)
            if "scores" in dec:
                C.kv([("Run · episode", f"{os.path.basename(latest)} · {dec['episode']}"),
                      ("Detected", f"{dec['spectrum']['modulation']} ({C.fmt(dec['spectrum']['confidence'], '.2f')})"),
                      ("Risk", f"{C.fmt(dec['prediction']['risk'], '.3f')} · {dec['prediction']['level']}"),
                      ("Risk gate", gate), ("Selected", dec["selected"]),
                      ("Utility", C.fmt(dec["utility"], "+.4f")), ("Applied next", dec.get("applied_next"))])
            else:
                C.kv([("Run · episode", f"{os.path.basename(latest)} · {dec['episode']}"),
                      ("Policy", B.POLICY_LABELS.get(dec.get("policy"), dec.get("policy"))),
                      ("Rule", dec.get("rule")), ("Applied next", dec.get("next_modulation"))])
        elif demo_rows:
            r = demo_rows[-1]
            C.section("Latest agent decision", "bot", C.badge("Repository demo", "info"))
            C.kv([("Run · episode", f"{r['_run']} · {r['episode']}"),
                  ("Detected", f"{r['detected_modulation']} ({C.fmt(r['detected_confidence'], '.2f')})"),
                  ("Est. SNR", f"{C.fmt(r['estimated_snr_db'], '.2f')} dB"),
                  ("Risk score", C.fmt(r["risk_score"], ".3f")), ("Selected", r["selected_strategy"]),
                  ("Utility", C.fmt(r["expected_utility"], "+.4f")), ("Next modulation", r["next_modulation"]),
                  ("Risk gate", "not recorded in this export")])
        else:
            C.section("Latest agent decision", "bot")
            C.empty("No decision recorded", "Agent decisions appear after a closed-loop run.", "bot")
        if st.button("Open AI Agents", icon=":material/arrow_forward:", width="stretch", key="ov_to_agents"):
            st.switch_page("views/agents.py")

# ------------------------------------------------------------------ comparison + activity
c1, c2 = st.columns([1.75, 1], gap="medium")
with c1:
    with st.container(border=True, key="panel_cmp"):
        ref = next((p for p in camps if os.path.basename(p) == "grcl1_20261022_v2"), camps[-1] if camps else None)
        if ref:
            comp = D.comparison(ref, D.runs_mtime(ref))
            done = B.campaign_completion(ref)
            C.section("ACWRA vs baselines", "scale",
                      ("" if done["complete"] else C.badge(f"incomplete · {done['state']}", "warn") + " ")
                      + f'<span class="mono">{C.esc(os.path.basename(ref))}</span> · {comp["runs"]} runs · '
                      f'{comp["conditions"]} conditions')
            a, b = st.columns(2)
            a.plotly_chart(P.policy_bars(comp["means"], "goodput_kbps", "mean goodput (kb/s)", 250), width="stretch",
                           config=T.PLOT_CONFIG)
            b.plotly_chart(P.policy_bars(comp["means"], "ber", "mean BER", 250), width="stretch", config=T.PLOT_CONFIG)
            best_g = max(comp["means"], key=lambda r: r["goodput_kbps"])
            best_b = min(comp["means"], key=lambda r: r["ber"])
            C.note(f"Highest mean goodput: <b>{B.POLICY_LABELS[best_g['policy']]}</b> "
                   f"({C.fmt(best_g['goodput_kbps'], '.1f')} kb/s) · lowest mean BER: "
                   f"<b>{B.POLICY_LABELS[best_b['policy']]}</b> ({C.fmt(best_b['ber'], '.4f')}). "
                   f"Means over all runs; paired statistics on Policy Comparison.")
        else:
            C.section("ACWRA vs baselines", "scale")
            C.empty("No completed campaign", "Run a campaign in Campaign Lab to compare policies.", "scale")
with c2:
    with st.container(border=True, key="panel_act"):
        if camp_active:
            cs = B.job_status(camp_active[0])
            C.section("Campaign progress", "flask", C.badge(cs.get("state", "?"), C.STATE_TONE.get(cs.get("state"), "muted")))
            tot = int(cs.get("total") or 0)
            st.progress(min(int(cs.get("done") or 0) / tot, 1.0) if tot else 0.0,
                        text=f"{cs.get('done', 0)}/{tot or '?'} runs · {cs.get('failed', 0)} failed · "
                             f"{C.fmt(cs.get('elapsed_s'), '.0f')} s")
        C.section("Recent activity", "clock")
        rows = D.history()[:7]
        if rows:
            C.activity([(C.badge(r["Source"], C.SOURCE_TONE.get(r["Source"], "muted")), r["Run ID"],
                         r["Status"], r["Timestamp"]) for r in rows])
        else:
            C.empty("No activity yet", "", "clock")

# ------------------------------------------------------------------ recent runs table
with st.container(border=True, key="panel_recent"):
    C.section("Recent runs", "history", "all sources · newest first per source")
    rows = D.history()[:12]
    st.dataframe([{"Run ID": r["Run ID"], "Timestamp": r["Timestamp"], "Source": r["Source"],
                   "Policy": r["Policy"], "Modulation": r["Modulation"], "Channel": r["Channel"],
                   "BER": C.fmt(r["BER"], ".3e"), "Goodput (kb/s)": C.fmt((r["Goodput"] or 0) / 1e3, ".1f")
                   if r["Goodput"] is not None else "—", "Status": r["Status"]} for r in rows],
                 hide_index=True, width="stretch", height=min(38 + 35 * len(rows), 460))
    if st.button("Open Run History", icon=":material/arrow_forward:", key="ov_to_hist"):
        st.switch_page("views/history.py")
