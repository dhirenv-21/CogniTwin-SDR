"""Live Simulation: configure and execute a GNU Radio closed-loop run, then inspect exactly what it recorded."""

import os

import numpy as np
import streamlit as st

import backend as B
from ui import components as C
from ui import data as D
from ui import plots as P
from ui import theme as T

ss = st.session_state
status = D.gr_status()
GR_OK = status["available"]
DEFAULTS = B.SimInputs()
MODS = list(B.MODULATIONS)

# defaults live in session state (not in the widget calls) so values survive page switches without warnings;
# number input + slider pairs share a value through two synced keys
for _k, _v in (("in_mod", DEFAULTS.modulation), ("in_seed", DEFAULTS.seed), ("in_nsym", DEFAULTS.n_symbols),
               ("in_sps", DEFAULTS.sps), ("in_roll", DEFAULTS.rolloff), ("in_chan", DEFAULTS.channel),
               ("in_snr", DEFAULTS.snr_db), ("in_snr_s", DEFAULTS.snr_db), ("in_jam", DEFAULTS.jammer),
               ("in_jam_s", DEFAULTS.jammer), ("in_dop", DEFAULTS.doppler_fdts), ("in_k", DEFAULTS.rician_k),
               ("in_pol", DEFAULTS.policy), ("in_adapt", DEFAULTS.adaptation), ("in_eps", DEFAULTS.episodes)):
    ss.setdefault(_k, _v)


def _sync(src, dst):
    ss[dst] = ss[src]


C.gr_banner(status)
left, right = st.columns([1.12, 2.6], gap="medium")

# ------------------------------------------------------------------ inputs
with left:
    with st.container(border=True, key="panel_tx"):
        C.section("Transmitter", "radio")
        modulation = st.segmented_control("Initial modulation", MODS, required=True,
                                          key="in_mod", width="stretch",
                                          help="Modulation of episode 0. Fixed policies override it; ACWRA and the "
                                               "SINR threshold switch between BPSK and QPSK.")
        modulation = modulation or DEFAULTS.modulation
        c1, c2 = st.columns(2)
        seed = c1.number_input("Random seed", 1, 2**31 - 64, key="in_seed",
                               help="Seeds bits, noise, fading and jammer; episode k uses a derived seed.")
        n_symbols = c2.number_input("Symbols / episode", 256, 262144, step=64, key="in_nsym",
                                    help="OFDM-QPSK needs a multiple of 64.")
        with st.expander("Pulse shaping (PSK)"):
            c1, c2 = st.columns(2)
            sps = c1.number_input("Samples / symbol", 2, 16, key="in_sps")
            rolloff = c2.number_input("RRC roll-off", 0.05, 1.0, step=0.05, key="in_roll")

    with st.container(border=True, key="panel_ch"):
        C.section("Channel", "wave")
        channel = st.selectbox("Channel model", list(B.CHANNELS), key="in_chan",
                               help="Block fading: one gain per episode. Changing: Doppler-driven time-varying fade.")
        c1, c2 = st.columns([1, 1.5], vertical_alignment="bottom")
        snr_db = c1.number_input("SNR (dB)", -30.0, 60.0, step=0.5, key="in_snr", on_change=_sync,
                                 args=("in_snr", "in_snr_s"), help="Configured Es/N0 of the AWGN source.")
        c2.slider("SNR slider", -30.0, 60.0, step=0.5, key="in_snr_s", label_visibility="collapsed",
                  on_change=_sync, args=("in_snr_s", "in_snr"))
        c1, c2 = st.columns([1, 1.5], vertical_alignment="bottom")
        jammer = c1.number_input("Jammer power J", 0.0, 5.0, step=0.01, format="%.3f", key="in_jam", on_change=_sync,
                                 args=("in_jam", "in_jam_s"), help="Jammer power relative to unit signal power.")
        c2.slider("Jammer slider", 0.0, 5.0, step=0.01, key="in_jam_s", label_visibility="collapsed",
                  on_change=_sync, args=("in_jam_s", "in_jam"))
        doppler, rician_k = DEFAULTS.doppler_fdts, DEFAULTS.rician_k
        if "changing" in channel or channel.startswith("Rician"):
            c1, c2 = st.columns(2)
            if "changing" in channel:
                doppler = c1.number_input("Doppler fD·Ts", 1e-6, 0.49, format="%.6f",
                                          key="in_dop")
            if channel.startswith("Rician"):
                rician_k = c2.number_input("Rician K", 0.0, 100.0, step=0.5, key="in_k")

    with st.container(border=True, key="panel_def"):
        C.section("Defense", "shield")
        policy = st.selectbox("Policy", list(B.POLICY_LABELS), format_func=B.POLICY_LABELS.get, key="in_pol",
                              help="ACWRA runs the full agent pipeline; the others are the campaign baselines.")
        c1, c2 = st.columns([1.3, 1], vertical_alignment="bottom")
        adaptation = c1.toggle("Apply decisions", key="in_adapt", disabled=policy != "acwra",
                               help="Off: ACWRA still decides but nothing is applied (= Non-adaptive).")
        episodes = c2.number_input("Episodes", 1, 50, key="in_eps")

    inp = B.SimInputs(modulation=modulation, seed=int(seed), n_symbols=int(n_symbols), sps=int(sps),
                      rolloff=float(rolloff), channel=channel, snr_db=float(snr_db), jammer=float(jammer),
                      doppler_fdts=float(doppler), rician_k=float(rician_k), policy=policy,
                      adaptation=bool(adaptation), episodes=int(episodes))
    cfg, errors = B.validate_inputs(inp)

    with st.container(border=True, key="panel_exec"):
        C.section("Execution", "play")
        for k, v in errors.items():
            C.err(f"{k}: {v}")
        busy = bool(B.active_jobs())
        C.md(f'<div class="ct-summary" style="margin-bottom:10px"><span class="big">{int(episodes)}</span> '
             f'<span class="ct-note" style="display:inline">episode{"s" if int(episodes) > 1 else ""} × '
             f'{int(n_symbols):,} symbols · {C.esc(B.POLICY_LABELS[inp.effective_policy()])}</span></div>')
        if st.button("Run simulation", type="primary", width="stretch", icon=":material/play_arrow:", key="btn_run",
                     disabled=not GR_OK or bool(errors) or busy,
                     help=None if GR_OK else "GNU Radio is not importable here"):
            _, path, _ = B.launch("simulation", B.spec_from_inputs(inp))
            ss["active"] = path
            D.select("dash_run", path)
            st.toast("Simulation queued", icon=":material/rocket_launch:")
            st.rerun()
        if busy:
            C.note("A job is running — one job at a time.")
        if st.button("Run smoke test", width="stretch", icon=":material/science:", key="btn_smoke",
                     disabled=not GR_OK or busy):
            ss["confirm_smoke"] = True
        if ss["confirm_smoke"]:
            st.warning("Smoke test: 2 conditions × 6 policies × 6 episodes = 72 GNU Radio runs.")
            c1, c2 = st.columns(2)
            if c1.button("Confirm", width="stretch", type="primary", key="btn_smoke_ok"):
                ss["confirm_smoke"] = False
                _, path, _ = B.launch("smoke", {})
                ss["active"] = path
                st.rerun()
            if c2.button("Cancel", width="stretch", key="btn_smoke_cancel"):
                ss["confirm_smoke"] = False
                st.rerun()
        c1, c2 = st.columns(2)
        own = ss.get("active")
        if c1.button("Stop job", width="stretch", icon=":material/stop:", key="btn_stop",
                     disabled=not (own and B.job_status(own).get("state") in ("running", "queued")),
                     help="Terminates only a worker this dashboard started"):
            B.stop_job(own)
            st.rerun()
        if c2.button("Reset inputs", width="stretch", icon=":material/restart_alt:", key="btn_reset"):
            for k in [k for k in ss.keys() if str(k).startswith("in_")]:
                del ss[k]
            st.rerun()


# ------------------------------------------------------------------ results
def run_options():
    """Runs this page can display: dashboard simulations and repository GNU Radio demo exports."""
    opts = {}
    for p in B.dashboard_runs(("done", "running", "queued", "stopped", "failed", "done_with_failures", "blocked",
                               "invalid")):
        opts[p] = ("dash_run", f"{os.path.basename(p)} · {B.job_status(p).get('state', '?')}")
    demo = D.demo_export_path()
    if demo:
        opts[demo] = ("npz", f"demo {os.path.basename(os.path.dirname(demo))} · repository GNU Radio export")
    sel = ss.get("selected")
    if sel and sel["path"] not in opts and os.path.exists(sel["path"]) and sel["kind"] in ("npz", "mat"):
        opts[sel["path"]] = (sel["kind"], f"{os.path.basename(sel['path'])} · from Run History")
    return opts


def results():
    opts = run_options()
    sel = D.selected_run()
    if sel and sel["kind"] in ("campaign", "aborted"):
        C.empty("A campaign is selected", "Campaign results are shown in Campaign Lab and Policy Comparison.", "flask")
        return
    if not opts:
        C.empty("No simulation has been run yet",
                "Configure the transmitter, channel and defense on the left, then press Run simulation. "
                "Plots appear here from the run's own exported I/Q data.", "radio")
        return
    paths = list(opts)
    cur = sel["path"] if sel and sel["path"] in opts else paths[0]
    if ss.get("selected") is None or ss["selected"].get("path") != cur:
        D.select(opts[cur][0], cur)

    def _pick():
        p = ss["lv_run"]
        D.select(opts[p][0], p)

    h1, h2 = st.columns([2.4, 1], vertical_alignment="bottom")
    if ss.get("lv_run") != cur:              # the selection may have changed elsewhere (history, finished job)
        ss["lv_run"] = cur
    h1.selectbox("Run", paths, format_func=lambda p: opts[p][1], key="lv_run", on_change=_pick)
    kind = opts[cur][0]

    eps, decs, export, vinfo, mat, ep_idx = [], [], None, None, None, 0
    if kind == "dash_run":
        eps, decs = B.load_episodes(cur), B.load_decisions(cur)
        job = B.job_status(cur)
        if eps:
            ep_idx = h2.selectbox("Episode", list(range(len(eps))), index=len(eps) - 1, key=f"ep_{os.path.basename(cur)}",
                                  format_func=lambda i: f"Episode {i}  ·  {i + 1}/{len(eps)}")
            f = os.path.join(cur, f"ep{ep_idx}.npz")
            if os.path.exists(f):
                try:
                    export, vinfo = D.export(cur, ep_idx, D.mtime(f))
                except Exception as exc:  # shown, never replaced by other data
                    C.err(f"episode {ep_idx} export rejected: {exc}")
        elif job.get("state") in ("running", "queued"):
            C.empty("Running…", f"{job.get('message', '')} — the first episode appears here when GNU Radio finishes it.",
                    "clock")
            return
        else:
            # never let a job state such as "done" read as a complete result when no episode was recorded
            C.empty("This run produced no episodes",
                    f"Job state: {job.get('state', 'unknown')} — {str(job.get('message', ''))[:300]}. "
                    "episodes.csv is missing or empty in the run folder, so there is nothing to show.", "alert")
            return
    elif kind == "npz":
        export, vinfo = D.npz(cur, D.mtime(cur))
    elif kind == "mat":
        mat = B.mat_summary(cur)

    e = eps[ep_idx] if eps else None
    dec = decs[ep_idx] if decs and ep_idx < len(decs) else None

    # ---- KPI strip
    if e is not None or export is not None:
        ber = float(e["ber"]) if e else float(export["ber"])
        per = float(e["per"]) if e else float(export["per"])
        ber_th = e["ber_theory"] if e else export["ber_theory"]
        gate = B.risk_gate(dec)
        ok = vinfo["ok"] if vinfo else None
        dur = B.job_status(cur).get("elapsed_s") if eps else export.get("wall_time_s")
        det = e.get("detected_modulation") if e else ""
        act = (e.get("selected_strategy") or e.get("next_modulation")) if e else None
        C.metrics([
            C.metric("BER", C.fmt(ber, ".3e"), f"theory {C.fmt(ber_th, '.2e')}",
                     "ok" if ber < 1e-3 else "warn" if ber < 1e-2 else "err", compact=True),
            C.metric("PER", C.fmt(per, ".3f"), "256-bit packets", "ok" if per < .1 else "warn" if per < .5 else "err",
                     compact=True),
            C.metric("SINR (post-fade)", C.fmt(B.sinr_db(export), ".2f") if export is not None else "—",
                     f"Es/N0 meas. {C.fmt(e['snr_db_measured'] if e else export['measured_snr_db'], '.2f')} dB",
                     "info", unit="dB", compact=True),
            C.metric("Goodput", C.fmt(float(e["goodput_bps"]) / 1e3, ".1f") if e else "—",
                     f"applied {e['modulation_applied'] if e else export['modulation']}", "accent", unit="kb/s",
                     compact=True),
            C.metric("Detected", det or "—", f"conf. {C.fmt(e.get('detected_confidence'), '.2f')}" if det
                     else "agent not run for this policy", "info", compact=True),
            C.metric("Action", act or "—", f"next: {e['next_modulation']}" if e else "", "accent", compact=True),
            C.metric("Risk gate", gate.split(" ")[0], gate[len(gate.split(" ")[0]):].strip(" ()") or "no ACWRA trace",
                     "err" if gate.startswith("CLOSED") else "ok" if gate.startswith("OPEN") else "muted", compact=True),
            C.metric("Validation", "VALID" if ok else "INVALID" if ok is False else "—",
                     f"{vinfo['provenance']} · {C.fmt(dur, '.2f')} s" if vinfo else "",
                     ("ok" if vinfo["provenance"] == "gnuradio_export" else "warn") if ok
                     else "err" if ok is False else "muted",
                     value_tone=("ok" if vinfo["provenance"] == "gnuradio_export" else "warn") if ok
                     else "err" if ok is False else None, compact=True),
        ], min_width=128)

    # ---- signal plots
    with st.container(border=True, key="panel_plots"):
        if export is not None:
            sp = D.signal_products(f"{cur}:{ep_idx}:{D.mtime(cur)}", export)
            src = "Dashboard run" if kind == "dash_run" else "Repository demo"
            C.section("Signal", "wave", C.badge(src, "info") + " " +
                      C.badge(vinfo["provenance"], "ok" if vinfo["provenance"] == "gnuradio_export" else "warn") +
                      f' <span class="mono" style="font-size:.72rem">{C.esc(export["experiment_id"])}</span>')
            t1, t2, t3, t4 = st.tabs(["I/Q waveform", "Constellation", "Spectrum", "Power spectral density"])
            with t1:
                st.plotly_chart(P.waveform(sp, int(ss["pref_wave_n"]), bool(ss["pref_show_tx"])), width="stretch",
                                config=T.PLOT_CONFIG)
            with t2:
                m = int(min(ss["pref_const_n"], sp["iq"].size))
                a, b = st.columns(2)
                a.plotly_chart(P.constellation(sp["iq"][:m], "received (before equalisation)", T.INDIGO),
                               width="stretch", config=T.PLOT_CONFIG)
                b.plotly_chart(P.constellation(sp["eq"][:m], "equalised (exported channel gain)", T.CYAN),
                               width="stretch", config=T.PLOT_CONFIG)
            with t3:
                st.plotly_chart(P.spectrum(sp), width="stretch", config=T.PLOT_CONFIG)
            with t4:
                st.plotly_chart(P.psd(sp), width="stretch", config=T.PLOT_CONFIG)
            C.note(f"Validation: {C.esc(vinfo['summary'])} · fs {C.fmt(sp['fs'] / 1e3, '.0f')} kHz · "
                   f"{sp['iq'].size:,} samples exported · {C.esc(export['modulation'])} · {C.esc(export['channel_type'])}"
                   f"/{C.esc(export['fading_mode'])}")
        elif mat is not None:
            C.section("Signal", "wave", C.badge("MATLAB (historical)", "accent"))
            st.info(f"Historical MATLAB export · provenance `{mat.get('provenance', '?')}` · "
                    f"{mat.get('summary', mat.get('error', ''))}")
            if mat.get("iq") is not None:
                z = np.asarray(mat["iq"])[:int(ss["pref_const_n"])]
                st.plotly_chart(P.constellation(z, "received constellation (MATLAB export)", T.INDIGO), width="stretch",
                                config=T.PLOT_CONFIG)
        else:
            C.section("Signal", "wave")
            C.empty("No I/Q export for this episode", "The run did not write an export that passed loading.", "wave")


def episode_panels():
    """Full-width per-episode charts and pipeline for the run shown above (same selection, same episode)."""
    sel = ss.get("selected")
    if not sel or sel["kind"] != "dash_run" or not os.path.isdir(sel["path"]):
        return
    cur = sel["path"]
    eps, decs = B.load_episodes(cur), B.load_decisions(cur)
    if not eps:
        return
    ep_idx = min(int(ss.get(f"ep_{os.path.basename(cur)}", len(eps) - 1)), len(eps) - 1)
    e = eps[ep_idx]
    dec = decs[ep_idx] if ep_idx < len(decs) else None
    a, b = st.columns(2, gap="medium")
    with a:
        with st.container(border=True, key="panel_epm"):
            C.section("BER & goodput per episode", "activity", "measured")
            st.plotly_chart(P.episode_metrics(eps), width="stretch", config=T.PLOT_CONFIG)
    with b:
        with st.container(border=True, key="panel_tl"):
            C.section("Agent decision timeline", "target", "applied vs decided")
            st.plotly_chart(P.decision_timeline(eps), width="stretch", config=T.PLOT_CONFIG)

    has = dec is not None and "spectrum" in dec
    with st.container(border=True, key="panel_pipe"):
        C.section("Cognitive pipeline", "bot", f"episode {ep_idx}")
        C.pipeline([
            {"name": "GNU Radio", "icon": "radio", "state": "executed", "tone": "ok",
             "out": f"{e['modulation_applied']} · {e['channel']}/{e['fading_mode']}"},
            {"name": "I/Q", "icon": "iq", "state": e["provenance"] or "?",
             "tone": "ok" if e["provenance"] == "gnuradio_export" else "warn", "out": f"{e['bits']} bits"},
            {"name": "Spectrum", "icon": "radar", "state": "ran" if has else "not used", "tone": "info" if has else "muted",
             "out": f"{dec['spectrum']['modulation']} · {C.fmt(dec['spectrum']['blind_snr_db'], '.1f')} dB" if has else None,
             "na": "baseline policy"},
            {"name": "Twin", "icon": "twin", "state": "ran" if has else "not used", "tone": "info" if has else "muted",
             "out": f"{dec['twin']['condition']}" if has else None, "na": "baseline policy"},
            {"name": "Prediction", "icon": "trend", "state": dec["prediction"]["level"] if has else "not used",
             "tone": ("err" if dec["prediction"]["level"] in ("HIGH", "CRITICAL") else "warn"
                      if dec["prediction"]["level"] == "MEDIUM" else "info") if has else "muted",
             "out": f"risk {C.fmt(dec['prediction']['risk'], '.2f')}" if has else None, "na": "baseline policy"},
            {"name": "Defense", "icon": "shield", "state": B.risk_gate(dec).split(" ")[0] if has else "not used",
             "tone": ("err" if B.risk_gate(dec).startswith("CLOSED") else "ok") if has else "muted",
             "out": f"{len(dec['candidates'])} candidate(s)" if has else None, "na": "baseline policy"},
            {"name": "ACWRA", "icon": "target", "state": "selected" if has else "rule", "tone": "accent" if has else "muted",
             "out": f"{dec['selected']}" if has else (dec or {}).get("rule")},
            {"name": "Next", "icon": "next", "state": "applied", "tone": "ok", "out": e["next_modulation"]},
        ])
        if st.button("Inspect agent outputs", icon=":material/arrow_forward:", key="lv_to_agents"):
            D.select("dash_run", cur)
            st.switch_page("views/agents.py")



with right:
    sel_now = D.selected_run()
    live = bool(sel_now and sel_now["kind"] == "dash_run" and
                B.job_status(sel_now["path"]).get("state") in ("running", "queued"))
    # auto-refresh only while the shown run is executing; otherwise plain calls, so a widget change reruns both parts
    (st.fragment(results, run_every=float(ss["pref_refresh"])) if live else results)()
(st.fragment(episode_panels, run_every=float(ss["pref_refresh"])) if live else episode_panels)()

# ------------------------------------------------------------------ reference curves
with st.container(border=True, key="panel_ref"):
    C.section("Reference measurements", "signal", "GNU Radio BER validation runs · AWGN campaign episodes")
    curves = D.curves(len(B.campaign_dirs()))
    a, b = st.columns(2, gap="medium")
    with a:
        bv = curves["ber_validation"]
        if len({r["snr_db"] for r in bv}) >= 3:
            st.plotly_chart(P.ber_validation(bv), width="stretch", config=T.PLOT_CONFIG)
            C.note("Markers: measured BER with 95 % CI. Dotted: theory.")
        else:
            C.empty("Insufficient BER-validation data", "Needs at least three SNR points.", "signal")
    with b:
        pc = curves["campaign_per"]
        if len({r["snr_db"] for r in pc}) >= 3:
            st.plotly_chart(P.per_curve(pc), width="stretch", config=T.PLOT_CONFIG)
            C.note("Mean PER of AWGN campaign episodes by applied modulation and configured SNR.")
        else:
            C.empty("Insufficient campaign data", "Needs AWGN campaign episodes at three or more SNRs.", "signal")
