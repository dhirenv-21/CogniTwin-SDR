"""Campaign Lab: configure, confirm, launch and monitor a campaign; browse recorded campaign results."""

import os
from dataclasses import asdict

import streamlit as st

import backend as B
from ui import components as C
from ui import data as D

ss = st.session_state
status = D.gr_status()
GR_OK = status["available"]
PROTECTED = "grcl1_20261022_v2"

for _k, _v in (("c_ch", ["AWGN", "Rayleigh (block)"]), ("c_snr", "4, 8, 12, 16"), ("c_jam", "0, 0.05, 0.2"),
               ("c_mod", "QPSK"), ("c_seeds", "1, 2, 3"), ("c_pol", list(B.POLICY_LABELS)), ("c_eps", 6),
               ("c_nsym", 4096), ("c_confirm", False)):
    ss.setdefault(_k, _v)
if ss.pop("c_confirm_reset", False):
    ss["c_confirm"] = False


def parse(txt, typ):
    try:
        return [typ(x) for x in txt.replace(";", ",").split(",") if x.strip()], None
    except ValueError:
        return [], "comma-separated numbers"


C.gr_banner(status)
cl, cr = st.columns([1, 1.55], gap="medium")

with cl:
    with st.container(border=True, key="panel_cfg"):
        C.section("Experiment design", "flask")
        chans = st.multiselect("Channel conditions", list(B.CHANNELS), key="c_ch")
        c1, c2 = st.columns(2)
        snrs_txt = c1.text_input("SNR values (dB)", key="c_snr", help="Comma-separated, e.g. 4, 8, 12")
        jams_txt = c2.text_input("Jammer values J", key="c_jam", help="Comma-separated, e.g. 0, 0.05, 0.2")
        c1, c2 = st.columns([1.6, 1])
        init_mod = c1.segmented_control("Initial modulation", list(B.MODULATIONS), required=True, key="c_mod",
                                        width="stretch")
        seeds_txt = c2.text_input("Random seeds", key="c_seeds")
        pols = st.pills("Policies to compare", list(B.POLICY_LABELS), selection_mode="multi",
                        format_func=B.POLICY_LABELS.get, key="c_pol")
        c1, c2 = st.columns(2)
        reps = c1.number_input("Episodes per run", 1, 50, key="c_eps")
        nsym = c2.number_input("Symbols / episode", 256, 65536, step=64, key="c_nsym")

    snrs, e1 = parse(snrs_txt, float)
    jams, e2 = parse(jams_txt, float)
    seeds, e3 = parse(seeds_txt, int)
    cin = B.CampaignInputs(channels=chans, snrs=snrs, jammers=jams, initial_modulation=init_mod or "QPSK",
                           seeds=seeds, policies=list(pols or []), episodes=int(reps), n_symbols=int(nsym))
    cerr = B.validate_campaign(cin)
    for k, v in (("snrs", e1), ("jammers", e2), ("seeds", e3)):
        if v:
            cerr[k] = v

with cr:
    with st.container(border=True, key="panel_sum"):
        C.section("Campaign summary", "layers", "computed from the grid above")
        n_cond = len(chans) * len(snrs) * len(jams)
        C.metrics([
            C.metric("Conditions", f"{n_cond}", f"{len(chans)} ch × {len(snrs)} SNR × {len(jams)} J", "info", compact=True),
            C.metric("Closed-loop runs", f"{cin.n_runs():,}", f"× {len(seeds)} seeds × {len(cin.policies)} policies",
                     "accent", compact=True),
            C.metric("GNU Radio flowgraphs", f"{cin.n_flowgraphs():,}", f"{int(reps)} episodes per run", "accent",
                     compact=True),
            C.metric("Symbols simulated", f"{cin.n_flowgraphs() * int(nsym):,}", f"{int(nsym):,} per episode", "muted",
                     compact=True),
        ], min_width=150)
        C.note("Wall-clock duration is not estimated: flowgraph time depends on the host and the channel model.")
        for k, v in cerr.items():
            C.err(f"{k}: {v}")
        busy = bool(B.active_jobs())
        big = cin.n_flowgraphs() > 500
        confirm = st.checkbox(f"I confirm launching {cin.n_flowgraphs():,} GNU Radio flowgraph runs"
                              + (" (large campaign)" if big else ""), key="c_confirm")
        C.note(f"Output: <b>results/gnuradio/dashboard/campaigns/&lt;new id&gt;</b> — a new folder every launch. "
               f"Repository campaigns (including <b>{PROTECTED}</b>) are read-only and never relaunched or modified.")
        if st.button("Launch campaign", type="primary", width="stretch", icon=":material/rocket_launch:",
                     key="btn_camp", disabled=not GR_OK or bool(cerr) or not confirm or busy):
            _, path, _ = B.launch("campaign", asdict(cin))
            ss["active"] = path
            ss["c_confirm_reset"] = True
            st.toast("Campaign queued", icon=":material/rocket_launch:")
            st.rerun()
        if busy:
            C.note("A job is already running — one job at a time.")

    own = ss.get("active")
    mine = [p for p in ([own] if own and os.path.dirname(own) == B.CAMPAIGNS else [])] or \
           [p for p in B.active_jobs() if os.path.dirname(p) == B.CAMPAIGNS]

    def monitor():
        with st.container(border=True, key="panel_mon"):
            if not mine:
                C.section("Execution monitor", "activity")
                C.empty("No campaign running", "Launch a campaign to follow its progress here.", "activity")
                return
            p = mine[0]
            s = B.job_status(p)
            state = s.get("state", "?")
            C.section("Execution monitor", "activity", C.badge(state, C.STATE_TONE.get(state, "muted")) +
                      f' <span class="mono">{C.esc(os.path.basename(p))}</span>')
            tot, done, failed = int(s.get("total") or 0), int(s.get("done") or 0), int(s.get("failed") or 0)
            st.progress(min((done + failed) / tot, 1.0) if tot else 0.0, text=str(s.get("message", "")))
            C.metrics([C.metric("Completed", f"{done}", f"of {tot or '?'} runs", "ok", compact=True),
                       C.metric("Failed", f"{failed}", "recorded in failures.json" if failed else "none",
                                "err" if failed else "muted", compact=True),
                       C.metric("Elapsed", C.fmt(s.get("elapsed_s"), ".0f"), "wall time", "info", unit="s", compact=True),
                       C.metric("State", state, "", C.STATE_TONE.get(state, "muted"), compact=True)], min_width=120)
            c1, c2 = st.columns(2)
            if c1.button("Stop campaign", width="stretch", icon=":material/stop:", key="btn_camp_stop",
                         disabled=state not in ("running", "queued")):
                B.stop_job(p)
                st.rerun()
            if state not in ("running", "queued") and os.path.exists(os.path.join(p, "runs.csv")):
                if c2.button("Open in Policy Comparison", width="stretch", icon=":material/arrow_forward:",
                             key="btn_camp_cmp"):
                    ss["pc_camp"] = p
                    st.switch_page("views/comparison.py")

    running = bool(mine) and B.job_status(mine[0]).get("state") in ("running", "queued")
    st.fragment(monitor, run_every=float(ss["pref_refresh"]) if running else None)()

# ------------------------------------------------------------------ results library
with st.container(border=True, key="panel_lib"):
    rows = [r for r in D.history() if r["_kind"] in ("campaign", "aborted")]
    C.section("Campaign results", "folder", f"{len(rows)} campaign folders · read only")
    if not rows:
        C.empty("No campaign results", "Completed campaigns appear here.", "folder")
    else:
        paths = [r["_path"] for r in rows]
        if ss.get("c_lib") not in paths:
            ss["c_lib"] = next((p for p in paths if os.path.basename(p) == PROTECTED), paths[0])
        c1, c2 = st.columns([1, 2.2], gap="medium")
        with c1:
            pick = st.radio("Campaign", paths, key="c_lib", label_visibility="collapsed",
                            format_func=lambda p: f"{os.path.basename(p)}  ·  "
                                                  f"{next(r['Source'] for r in rows if r['_path'] == p)}")
            r = next(r for r in rows if r["_path"] == pick)
            info = B.campaign_info(pick)
            C.md(C.badge(r["Source"], C.SOURCE_TONE.get(r["Source"], "muted")) + " " +
                 C.badge(r["Status"], C.STATE_TONE.get(r["Status"], "muted")))
            C.kv([("Created", r["Timestamp"]), ("Protocol", info.get("protocol")), ("Data", info.get("data_class")),
                  ("GNU Radio", info.get("gnuradio_version")), ("Episodes / run", info.get("episodes")),
                  ("Symbols / episode", info.get("n_symbols")),
                  ("Seeds", ", ".join(map(str, info.get("seeds") or [])) or None),
                  ("Policies", ", ".join(B.POLICY_LABELS.get(p, p) for p in info.get("policies") or []) or None),
                  ("Folder", B.rel(pick))])
            if os.path.exists(os.path.join(pick, "runs.csv")) and st.button(
                    "Compare policies", icon=":material/arrow_forward:", key="btn_lib_cmp", width="stretch"):
                ss["pc_camp"] = pick
                st.switch_page("views/comparison.py")
        with c2:
            docs = [f for f in ("ABORTED.md", "report.md", "analysis.md") if os.path.exists(os.path.join(pick, f))]
            tabs = st.tabs(docs + ["Artifacts"]) if docs else st.tabs(["Artifacts"])
            for t, f in zip(tabs, docs):
                with t:
                    fp = os.path.join(pick, f)
                    with st.container(height=420, border=False):
                        st.markdown(D.text_file(fp, D.mtime(fp)))
            with tabs[-1]:
                arts = B.artifacts(pick)
                st.dataframe([{"file": a["file"], "type": a["kind"], "size (kB)": round(a["bytes"] / 1024, 1),
                               "path": a["path"]} for a in arts], hide_index=True, width="stretch")
                small = [a for a in arts if a["kind"] in ("csv", "md", "json", "log") and a["bytes"] < 8e6]
                if small:
                    c_a, c_b = st.columns([2, 1], vertical_alignment="bottom")
                    fsel = c_a.selectbox("Download artifact", [a["file"] for a in small], key="c_dl")
                    a = next(a for a in small if a["file"] == fsel)
                    with open(a["_abs"], "rb") as fh:
                        c_b.download_button("Download", fh.read(), file_name=a["file"], icon=":material/download:",
                                            width="stretch", key="dl_camp")
