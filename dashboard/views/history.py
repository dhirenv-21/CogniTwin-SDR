"""Run History: every run the dashboard can show, labelled by data class, with a detail view per run."""

import csv
import os

import streamlit as st

import backend as B
from ui import components as C
from ui import data as D
from ui import plots as P
from ui import theme as T

ss = st.session_state
rows = D.history()
if not rows:
    C.empty("No runs recorded", "Simulations, campaigns and exports appear here once they exist.", "history")
    st.stop()


def _opts(col):
    return sorted({str(r[col]) for r in rows if str(r[col])})


for k, col in (("h_src", "Source"), ("h_pol", "Policy"), ("h_mod", "Modulation"), ("h_ch", "Channel")):
    if not isinstance(ss.get(k), list) or not set(ss[k]) <= set(_opts(col)):
        ss[k] = []
ss.setdefault("h_q", "")

with st.container(border=True, key="panel_hfilters"):
    c0, c1, c2, c3, c4 = st.columns([1.6, 1.3, 1, 1, 1])
    q = c0.text_input("Search", key="h_q", placeholder="run id, policy, status…")
    src = c1.multiselect("Source", _opts("Source"), key="h_src", placeholder="all sources")
    pol = c2.multiselect("Policy", _opts("Policy"), key="h_pol", placeholder="all")
    mod = c3.multiselect("Modulation", _opts("Modulation"), key="h_mod", placeholder="all")
    ch = c4.multiselect("Channel", _opts("Channel"), key="h_ch", placeholder="all")
    counts = {s: sum(1 for r in rows if r["Source"] == s) for s in _opts("Source")}
    C.md('<div class="ct-status">' + "".join(C.chip(f"{s} · {n}", C.SOURCE_TONE.get(s, "muted"))
                                             for s, n in counts.items()) + "</div>")


def keep(r):
    if src and r["Source"] not in src or pol and r["Policy"] not in pol or mod and r["Modulation"] not in mod \
            or ch and r["Channel"] not in ch:
        return False
    return not q or q.lower() in " ".join(str(v) for k, v in r.items() if not k.startswith("_")).lower()


shown = [r for r in rows if keep(r)]


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


view = [{"Run ID": r["Run ID"], "Timestamp": r["Timestamp"], "Source": r["Source"], "Modulation": r["Modulation"],
         "Channel": r["Channel"], "SNR (dB)": _f(r["SNR"]), "Jammer": _f(r["Jammer"]), "Policy": r["Policy"],
         "BER": _f(r["BER"]), "Goodput (kb/s)": _f(r["Goodput"]) / 1e3 if _f(r["Goodput"]) is not None else None,
         "Status": r["Status"]} for r in shown]
with st.container(border=True, key="panel_htable"):
    C.section("Runs", "history", f"{len(shown)} of {len(rows)} · click a row for details · click a header to sort")
    cols = ["Run ID", "Timestamp", "Source", "Modulation", "Channel", "SNR (dB)", "Jammer", "Policy", "BER",
            "Goodput (kb/s)", "Status"]
    ev = st.dataframe(C.styled(view or [dict.fromkeys(cols)], {"SNR (dB)": "{:.1f}", "Jammer": "{:.3f}",
                                                               "BER": "{:.3e}", "Goodput (kb/s)": "{:.1f}"}),
                      hide_index=True, width="stretch", height=min(40 + 35 * max(len(view), 1), 440),
                      on_select="rerun", selection_mode="single-row", key="tbl_hist",
                      column_config={"Run ID": st.column_config.TextColumn(width="medium"),
                                     "Timestamp": st.column_config.TextColumn(width="small"),
                                     "Source": st.column_config.TextColumn(width="small"),
                                     "Modulation": st.column_config.TextColumn("Mod.", width="small"),
                                     "Channel": st.column_config.TextColumn(width="small"),
                                     "Policy": st.column_config.TextColumn(width="small"),
                                     "Status": st.column_config.TextColumn(width="small")})
    C.note("Data classes are never mixed: <b>GNU Radio</b> = validated GNU Radio exports · <b>MATLAB (historical)</b> "
           "= pre-v4 Simulink exports · <b>Fixture</b> = synthetic NumPy stand-in · <b>Aborted / Invalid / Stopped</b> "
           "= runs that did not complete validly. A grey None = not recorded (never a zero).")

picked = [i for i in (ev.selection.rows if ev and getattr(ev, "selection", None) else []) if i < len(shown)]
if not picked:
    C.empty("Select a run", "Its configuration, metrics, signals, agent decisions, provenance and artifacts appear here.",
            "file")
    st.stop()

r = shown[picked[0]]
path, kind = r["_path"], r["_kind"]

# ------------------------------------------------------------------ detail
with st.container(border=True, key="panel_detail"):
    h1, h2 = st.columns([2, 1.4], vertical_alignment="center")
    h1.markdown(f'<div class="ct-sec" style="margin:0"><div class="h">{C.icon("file", 14)}<span class="mono" '
                f'style="text-transform:none;letter-spacing:0;color:var(--text)">{C.esc(r["Run ID"])}</span></div></div>'
                + C.badge(r["Source"], C.SOURCE_TONE.get(r["Source"], "muted")) + " "
                + C.badge(r["Status"], C.STATE_TONE.get(r["Status"], "muted"))
                + f' <span class="ct-note" style="display:inline">{C.esc(r["Timestamp"])} · {C.esc(B.rel(path))}</span>',
                unsafe_allow_html=True)
    with h2:
        b1, b2 = st.columns(2)
        if kind in ("dash_run", "npz", "mat") and b1.button("Open in Live Simulation", width="stretch",
                                                             icon=":material/radio:", key="open_live_b"):
            D.select(kind, path)
            st.switch_page("views/live.py")
        if kind == "dash_run" and b2.button("Open in AI Agents", width="stretch", icon=":material/smart_toy:",
                                            key="open_agents_b"):
            D.select(kind, path)
            st.switch_page("views/agents.py")
        if kind == "campaign" and b1.button("Policy Comparison", width="stretch", icon=":material/balance:",
                                            key="open_cmp_b"):
            ss["pc_camp"] = path
            st.switch_page("views/comparison.py")

    if kind == "dash_run":
        job = B.read_json(os.path.join(path, "job.json"), {}) or {}
        s = B.job_status(path)
        eps, decs = B.load_episodes(path), B.load_decisions(path)
        t = st.tabs(["Configuration", "Metrics", "Signal", "Agent decisions", "Provenance", "Artifacts"])
        with t[0]:
            sp = job.get("spec", {})
            a, b = st.columns(2)
            with a:
                C.kv([("Initial modulation", sp.get("modulation")), ("Channel", sp.get("channel")),
                      ("SNR", f"{C.fmt(sp.get('snr_db'), '.2f')} dB"), ("Jammer J", C.fmt(sp.get("jammer"), ".3f")),
                      ("Doppler fD·Ts", C.fmt(sp.get("doppler_fdts"), ".2e")), ("Rician K", C.fmt(sp.get("rician_k")))])
            with b:
                C.kv([("Policy", B.POLICY_LABELS.get(sp.get("policy_effective"), sp.get("policy_effective"))),
                      ("Episodes", sp.get("episodes")), ("Symbols / episode", sp.get("n_symbols")),
                      ("Samples / symbol", sp.get("sps")), ("Roll-off", sp.get("rolloff")), ("Seed", sp.get("seed")),
                      ("Created", job.get("created")), ("Job state", f"{s.get('state')} · {s.get('message', '')}")])
        with t[1]:
            if eps:
                C.metrics([C.metric("Mean BER", C.fmt(sum(float(e["ber"]) for e in eps) / len(eps), ".3e"),
                                    f"{len(eps)} episodes", "accent", compact=True),
                           C.metric("Mean PER", C.fmt(sum(float(e["per"]) for e in eps) / len(eps), ".3f"), "",
                                    "accent", compact=True),
                           C.metric("Mean goodput", C.fmt(sum(float(e["goodput_bps"]) for e in eps) / len(eps) / 1e3,
                                                          ".1f"), "", "accent", unit="kb/s", compact=True),
                           C.metric("Duration", C.fmt(s.get("elapsed_s"), ".1f"), "job wall time", "muted", unit="s",
                                    compact=True)], min_width=140)
                st.plotly_chart(P.episode_metrics(eps, 260), width="stretch", config=T.PLOT_CONFIG)
                st.dataframe([{k: e.get(k) for k in ("episode", "modulation_applied", "snr_db_measured", "ber",
                                                     "ber_theory", "per", "goodput_bps", "sinr_db_post_fade",
                                                     "next_modulation", "provenance")} for e in eps],
                             hide_index=True, width="stretch")
            else:
                C.empty("No episodes recorded", str(s.get("message", "")), "activity")
        with t[2]:
            npzs = [k for k in range(len(eps)) if os.path.exists(os.path.join(path, f"ep{k}.npz"))]
            if npzs:
                k = st.selectbox("Episode", npzs, index=len(npzs) - 1, key="hist_ep")
                try:
                    d, v = D.export(path, k, D.mtime(os.path.join(path, f"ep{k}.npz")))
                    sp = D.signal_products(f"{path}:{k}", d)
                    a, b = st.columns(2)
                    a.plotly_chart(P.waveform(sp, int(ss["pref_wave_n"]), True, 300), width="stretch",
                                   config=T.PLOT_CONFIG)
                    b.plotly_chart(P.constellation(sp["eq"][:int(ss["pref_const_n"])], "equalised", height=300),
                                   width="stretch", config=T.PLOT_CONFIG)
                except Exception as exc:
                    C.err(f"export rejected: {exc}")
            else:
                C.empty("No waveform saved", "This run wrote no I/Q exports.", "wave")
        with t[3]:
            if decs:
                st.dataframe(C.styled([{"episode": d.get("episode"), "policy": d.get("policy"),
                                        "risk gate": B.risk_gate(d), "selected": d.get("selected") or d.get("rule"),
                                        "utility": d.get("utility"), "risk": (d.get("prediction") or {}).get("risk"),
                                        "next": d.get("next_modulation")} for d in decs],
                                      {"utility": "{:+.4f}", "risk": "{:.3f}"}), hide_index=True, width="stretch")
            else:
                C.empty("No decisions recorded", "", "bot")
        with t[4]:
            prov = sorted({e.get("provenance", "") for e in eps})
            C.kv([("Episode provenance", ", ".join(prov) or None), ("Ledger", B.rel(B.LEDGER)),
                  ("Classified as", r["Source"])])
            if eps and os.path.exists(os.path.join(path, f"ep{len(eps) - 1}.npz")):
                try:
                    _, v = D.export(path, len(eps) - 1, D.mtime(os.path.join(path, f"ep{len(eps) - 1}.npz")))
                    C.note(f"Last episode revalidated: <b>{C.esc(v['summary'])}</b>")
                    for x in v["errors"]:
                        C.err(x)
                except Exception as exc:
                    C.err(f"revalidation failed: {exc}")
        artifacts_tab = t[5]
    elif kind in ("campaign", "aborted"):
        info = B.campaign_info(path)
        t = st.tabs(["Configuration", "Metrics", "Provenance", "Artifacts"])
        with t[0]:
            C.kv([(k.replace("_", " ").capitalize(), ", ".join(map(str, v)) if isinstance(v, list) else v)
                  for k, v in info.items()])
        with t[1]:
            f = os.path.join(path, "summary.csv")
            if os.path.exists(f):
                with open(f, newline="") as fh:
                    st.dataframe(list(csv.DictReader(fh)), hide_index=True, width="stretch")
            elif os.path.exists(os.path.join(path, "ABORTED.md")):
                st.markdown(D.text_file(os.path.join(path, "ABORTED.md"), D.mtime(os.path.join(path, "ABORTED.md"))))
            else:
                C.empty("No summary recorded", "", "activity")
        with t[2]:
            steps = D.campaign_steps(path, D.mtime(os.path.join(path, "episodes_steps.csv")))
            prov = {}
            for s_ in steps:
                prov[s_.get("provenance", "")] = prov.get(s_.get("provenance", ""), 0) + 1
            C.kv([("Episodes", len(steps) or None)] + [(f"provenance: {k or '—'}", v) for k, v in prov.items()]
                 + [("Classified as", r["Source"])])
        artifacts_tab = t[3]
    elif kind == "npz":
        d, v = D.npz(path, D.mtime(path))
        t = st.tabs(["Metrics", "Signal", "Provenance", "Artifacts"])
        with t[0]:
            C.kv([(k, C.fmt(d[k], ".6g") if isinstance(d[k], float) else d[k]) for k in
                  ("experiment_id", "modulation", "channel_type", "fading_mode", "snr_db", "measured_snr_db",
                   "interference_power", "ber", "ber_theory", "per", "wall_time_s") if k in d])
        with t[1]:
            sp = D.signal_products(f"{path}:{D.mtime(path)}", d)
            a, b = st.columns(2)
            a.plotly_chart(P.waveform(sp, int(ss["pref_wave_n"]), True, 300), width="stretch", config=T.PLOT_CONFIG)
            b.plotly_chart(P.constellation(sp["eq"][:int(ss["pref_const_n"])], "equalised", height=300),
                           width="stretch", config=T.PLOT_CONFIG)
        with t[2]:
            C.kv([("Validation", v["summary"]), ("Provenance", v["provenance"]), ("Classified as", r["Source"])])
            for x in v["errors"]:
                C.err(x)
        artifacts_tab = t[3]
    else:                                   # MATLAB / fixture .mat
        m = B.mat_summary(path)
        t = st.tabs(["Metrics", "Provenance", "Artifacts"])
        with t[0]:
            C.kv([(k, C.fmt(m[k], ".6g") if isinstance(m.get(k), float) else m.get(k)) for k in
                  ("modulation", "channel", "snr_db", "interference_power", "ber", "samples") if k in m] or
                 [("error", m.get("error"))])
        with t[1]:
            C.kv([("Valid", m.get("valid")), ("Provenance", m.get("provenance")), ("Summary", m.get("summary")),
                  ("Classified as", r["Source"])])
            for x in m.get("errors", []):
                C.err(x)
        artifacts_tab = t[2]

    with artifacts_tab:
        arts = B.artifacts(path)
        st.dataframe([{"file": a["file"], "type": a["kind"], "size (kB)": round(a["bytes"] / 1024, 1), "path": a["path"]}
                      for a in arts], hide_index=True, width="stretch")
