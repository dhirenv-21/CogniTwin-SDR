"""
CogniTwin-SDR control dashboard (Streamlit).

    streamlit run dashboard/app.py        (from the repository root, in the cognitwin-dash env)

Inputs -> RUN -> a worker process executes GNU Radio through the existing backend ->
the dashboard reads back what the run wrote. Nothing runs when the page opens.
"""

import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import backend as B  # noqa: E402

st.set_page_config(page_title="CogniTwin-SDR Control", page_icon="📡", layout="wide",
                   initial_sidebar_state="collapsed")

CYAN, BLUE, GREEN, AMBER, RED, MUTED = "#22d3ee", "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#94a3b8"
SRC_COLOR = {B.SRC_GNURADIO: GREEN, B.SRC_MATLAB: BLUE, B.SRC_FIXTURE: MUTED, B.SRC_ABORTED: AMBER,
             B.SRC_INVALID: RED, B.SRC_STOPPED: AMBER, B.SRC_RUNNING: CYAN}

st.markdown(f"""
<style>
  header[data-testid="stHeader"] {{display:none}}
  .block-container {{padding-top: 1rem; padding-bottom: 1rem; max-width: 100%;}}
  .ct-bar {{display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; margin-bottom:.4rem}}
  .ct-title {{font-size:1.25rem; font-weight:700; color:#e2e8f0; margin-right:1rem; letter-spacing:.02em}}
  .ct-title span {{color:{CYAN}}}
  .chip {{border:1px solid #1e3a5f; background:#0b1730; border-radius:999px; padding:.18rem .7rem;
          font-size:.78rem; color:#cbd5e1; white-space:nowrap}}
  .dot {{display:inline-block; width:.55rem; height:.55rem; border-radius:50%; margin-right:.4rem}}
  .card {{background:linear-gradient(180deg,#0e1b36,#0a1429); border:1px solid #1e3a5f; border-radius:10px;
          padding:.55rem .75rem; margin-bottom:.5rem}}
  .card .k {{font-size:.68rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.08em}}
  .card .v {{font-size:1.25rem; font-weight:700; color:#e2e8f0; font-variant-numeric:tabular-nums}}
  .card .s {{font-size:.72rem; color:{MUTED}}}
  .pipe {{display:flex; flex-wrap:wrap; gap:.25rem; align-items:stretch; margin:.2rem 0 .6rem}}
  .blk {{flex:1 1 120px; background:#0b1730; border:1px solid #1e3a5f; border-top:3px solid var(--c);
         border-radius:8px; padding:.35rem .5rem; min-width:110px}}
  .blk .n {{font-size:.66rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.06em}}
  .blk .o {{font-size:.8rem; color:#e2e8f0; line-height:1.25}}
  .arrow {{align-self:center; color:{CYAN}; font-weight:700}}
  .err {{color:{RED}; font-size:.75rem; margin-top:-.6rem; margin-bottom:.4rem}}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ helpers

def chip(text, color):
    return f'<span class="chip"><span class="dot" style="background:{color}"></span>{text}</span>'


def card(col, key, value, sub="", color="#e2e8f0"):
    col.markdown(f'<div class="card"><div class="k">{key}</div><div class="v" style="color:{color}">{value}</div>'
                 f'<div class="s">{sub}</div></div>', unsafe_allow_html=True)


def fig(height=300, **layout):
    f = go.Figure()
    f.update_layout(template="plotly_dark", height=height, margin=dict(l=45, r=10, t=30, b=40),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a1429", font=dict(size=11),
                    legend=dict(orientation="h", y=1.12, x=0), **layout)
    f.update_xaxes(gridcolor="#1e293b", zerolinecolor="#334155")
    f.update_yaxes(gridcolor="#1e293b", zerolinecolor="#334155")
    return f


def fmt(x, spec=".4g", none="—"):
    try:
        if x is None or x == "" or (isinstance(x, float) and not np.isfinite(x)):
            return none
        return format(float(x), spec)
    except (TypeError, ValueError):
        return str(x)


def errline(errors, key):
    if key in errors:
        st.markdown(f'<div class="err">⚠ {errors[key]}</div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def gr_status():
    return B.gnuradio_status()


@st.cache_data(show_spinner=False)
def cached_export(run_dir, episode, mtime):
    d, rep = B.load_episode_export(run_dir, episode)
    return d, {"ok": rep.ok, "summary": rep.summary(), "provenance": rep.facts.get("provenance"),
               "errors": rep.errors[:5]}


@st.cache_data(show_spinner=False)
def cached_npz(path, mtime):
    from src.gnuradio_phy.export import load_export
    from src.gnuradio_phy.validation import validate_gnuradio_dict
    d = load_export(path)
    rep = validate_gnuradio_dict(d)
    return d, {"ok": rep.ok, "summary": rep.summary(), "provenance": rep.facts.get("provenance"),
               "errors": rep.errors[:5]}


@st.cache_data(show_spinner=False)
def cached_curves(key):
    return B.ber_curves()


@st.cache_data(show_spinner=False)
def cached_comparison(path, mtime):
    return B.campaign_comparison(path)


DEFAULTS = B.SimInputs()
ss = st.session_state
# number input + slider pairs share a value through two synced keys
for _k, _v in (("in_snr", DEFAULTS.snr_db), ("in_snr_s", DEFAULTS.snr_db), ("in_jam", DEFAULTS.jammer),
               ("in_jam_s", DEFAULTS.jammer)):
    ss.setdefault(_k, _v)


def _sync(src, dst):
    ss[dst] = ss[src]

ss.setdefault("selected", None)          # {"kind":..., "path":...}
ss.setdefault("active", None)            # folder of the job this session launched
ss.setdefault("confirm_smoke", False)

status = gr_status()
GR_OK = status["available"]

# ------------------------------------------------------------------ top bar

active = [p for p in B.active_jobs()]
cur = ss["active"] if ss["active"] else (active[0] if active else None)
cur_state = B.job_status(cur).get("state") if cur else None
bar = [f'<span class="ct-title">COGNI<span>TWIN</span>-SDR · CONTROL</span>',
       chip("System ready", GREEN),
       chip(f"GNU Radio {status['version']}" if GR_OK else "GNU Radio unavailable", GREEN if GR_OK else RED)]
if cur:
    bar.append(chip(f"{os.path.basename(cur)} · {cur_state}", CYAN if cur_state in ("running", "queued") else MUTED))
else:
    bar.append(chip("No active job", MUTED))
st.markdown('<div class="ct-bar">' + "".join(bar) + "</div>", unsafe_allow_html=True)
if not GR_OK:
    st.error(f"Execution disabled: {status['detail']}", icon="⛔")

tab_sim, tab_camp, tab_hist = st.tabs(["Simulation", "Campaign", "Run history"])


# ------------------------------------------------------------------ job monitor

@st.fragment(run_every=1.0)
def job_monitor():
    p = ss.get("active")
    if not p:
        return
    s = B.job_status(p)
    state = s.get("state", "?")
    total, done = int(s.get("total") or 0), int(s.get("done") or 0)
    color = {"running": CYAN, "queued": CYAN, "done": GREEN, "done_with_failures": AMBER}.get(state, RED)
    st.markdown(chip(f"{os.path.basename(p)} · {state} · {done}/{total or '?'}"
                     + (f" · failed {s['failed']}" if s.get("failed") else "")
                     + f" · {fmt(s.get('elapsed_s'), '.1f')} s", color), unsafe_allow_html=True)
    if total:
        st.progress(min(done / total, 1.0))
    if state in ("blocked", "invalid", "failed"):
        st.error(s.get("message", state))
    if state not in ("running", "queued") and not ss.get(f"seen_{p}"):
        ss[f"seen_{p}"] = True
        if os.path.dirname(p) == B.RUNS:
            ss["selected"] = {"kind": "dash_run", "path": p}
        st.rerun()


# ------------------------------------------------------------------ simulation tab

with tab_sim:
    left, center, right = st.columns([1.05, 2.5, 1.25], gap="medium")

    with left:
        st.markdown("**TRANSMITTER**")
        modulation = st.selectbox("Modulation", list(B.MODULATIONS), index=list(B.MODULATIONS).index(DEFAULTS.modulation),
                                  key="in_mod", help="Initial modulation; Fixed policies override it")
        c1, c2 = st.columns(2)
        seed = c1.number_input("Seed", 1, 2**31 - 64, DEFAULTS.seed, key="in_seed")
        n_symbols = c2.number_input("Symbols / episode", 256, 262144, DEFAULTS.n_symbols, step=64, key="in_nsym")
        with st.expander("Pulse shaping (PSK)"):
            c1, c2 = st.columns(2)
            sps = c1.number_input("Samples/symbol", 2, 16, DEFAULTS.sps, key="in_sps")
            rolloff = c2.number_input("RRC roll-off", 0.05, 1.0, DEFAULTS.rolloff, step=0.05, key="in_roll")

        st.markdown("**CHANNEL**")
        channel = st.selectbox("Channel model", list(B.CHANNELS), key="in_chan")
        c1, c2 = st.columns([1, 1.4])
        snr_db = c1.number_input("SNR (dB)", -30.0, 60.0, step=0.5, key="in_snr", on_change=_sync,
                                 args=("in_snr", "in_snr_s"))
        c2.slider("SNR slider", -30.0, 60.0, step=0.5, key="in_snr_s", label_visibility="hidden", on_change=_sync,
                  args=("in_snr_s", "in_snr"))
        c1, c2 = st.columns([1, 1.4])
        jammer = c1.number_input("Jammer J", 0.0, 5.0, step=0.01, format="%.3f", key="in_jam", on_change=_sync,
                                 args=("in_jam", "in_jam_s"))
        c2.slider("Jammer slider", 0.0, 5.0, step=0.01, key="in_jam_s", label_visibility="hidden", on_change=_sync,
                  args=("in_jam_s", "in_jam"))
        doppler, rician_k = DEFAULTS.doppler_fdts, DEFAULTS.rician_k
        if "changing" in channel:
            doppler = st.number_input("Doppler fD·Ts", 1e-6, 0.49, DEFAULTS.doppler_fdts, format="%.6f", key="in_dop")
        if channel.startswith("Rician"):
            rician_k = st.number_input("Rician K", 0.0, 100.0, DEFAULTS.rician_k, step=0.5, key="in_k")

        st.markdown("**AI DEFENSE**")
        policy = st.selectbox("Policy", list(B.POLICY_LABELS), format_func=B.POLICY_LABELS.get, key="in_pol")
        adaptation = st.toggle("Apply decisions (adaptation)", True, key="in_adapt", disabled=policy != "acwra")
        episodes = st.number_input("Episodes", 1, 50, DEFAULTS.episodes, key="in_eps")

        inp = B.SimInputs(modulation=modulation, seed=int(seed), n_symbols=int(n_symbols), sps=int(sps),
                          rolloff=float(rolloff), channel=channel, snr_db=float(snr_db), jammer=float(jammer),
                          doppler_fdts=float(doppler), rician_k=float(rician_k), policy=policy,
                          adaptation=bool(adaptation), episodes=int(episodes))
        cfg, errors = B.validate_inputs(inp)
        for k in errors:
            errline(errors, k)

        busy = bool(B.active_jobs())
        b1, b2 = st, st
        if b1.button("▶ RUN SIMULATION", type="primary", width="stretch",
                     disabled=not GR_OK or bool(errors) or busy):
            rid, path, _ = B.launch("simulation", B.spec_from_inputs(inp))
            ss["active"] = path
            st.rerun()
        if b2.button("RUN SMOKE TEST", width="stretch", disabled=not GR_OK or busy):
            ss["confirm_smoke"] = True
        if ss["confirm_smoke"]:
            st.warning("Smoke test: 2 conditions × 6 policies × 6 episodes = 72 GNU Radio runs.")
            c1, c2 = st.columns(2)
            if c1.button("Confirm", width="stretch"):
                ss["confirm_smoke"] = False
                _, path, _ = B.launch("smoke", {})
                ss["active"] = path
                st.rerun()
            if c2.button("Cancel", width="stretch"):
                ss["confirm_smoke"] = False
                st.rerun()
        b3, b4 = st.columns(2)
        own = ss.get("active")
        if b3.button("■ STOP JOB", width="stretch",
                     disabled=not (own and B.job_status(own).get("state") in ("running", "queued"))):
            B.stop_job(own)
            st.rerun()
        if b4.button("RESET INPUTS", width="stretch"):
            for k in [k for k in ss.keys() if str(k).startswith("in_")]:
                del ss[k]
            st.rerun()
        job_monitor()

    # ---- load the selected run
    sel = ss.get("selected")
    eps, decs, export, vinfo, mat = [], [], None, None, None
    if sel and sel["kind"] == "dash_run" and os.path.isdir(sel["path"]):
        eps, decs = B.load_episodes(sel["path"]), B.load_decisions(sel["path"])
    elif sel and sel["kind"] == "npz":
        export, vinfo = cached_npz(sel["path"], os.path.getmtime(sel["path"]))
    elif sel and sel["kind"] == "mat":
        mat = B.mat_summary(sel["path"])

    with center:
        title = os.path.basename(sel["path"]) if sel else "no run selected"
        ep_idx = 0
        if eps:
            h1, h2 = st.columns([3, 1.2])
            h1.markdown(f"**RUN** `{title}`")
            ep_idx = h2.selectbox("Episode", list(range(len(eps))), index=len(eps) - 1, key=f"ep_{title}",
                                  label_visibility="collapsed", format_func=lambda i: f"Episode {i}")
            npz = os.path.join(sel["path"], f"ep{ep_idx}.npz")
            if os.path.exists(npz):
                export, vinfo = cached_export(sel["path"], ep_idx, os.path.getmtime(npz))
        else:
            st.markdown(f"**RUN** `{title}`")
        if export is not None:
            sp = B.signal_products(export)
            t1, t2, t3, t4 = st.tabs(["I/Q waveform", "Constellation", "Spectrum", "PSD"])
            n = min(120, sp["iq"].size)
            with t1:
                f = fig(330, xaxis_title="exported sample", yaxis_title="amplitude")
                f.add_scatter(y=sp["iq"][:n].real, name="rx I", line=dict(color=CYAN, width=1.3))
                f.add_scatter(y=sp["iq"][:n].imag, name="rx Q", line=dict(color=BLUE, width=1.3))
                f.add_scatter(y=sp["tx"][:n].real, name="tx I", line=dict(color=MUTED, width=1, dash="dot"))
                st.plotly_chart(f, width="stretch")
            with t2:
                c1, c2 = st.columns(2)
                m = min(4000, sp["iq"].size)
                for col, z, nm in ((c1, sp["iq"][:m], "received"), (c2, sp["eq"][:m], "equalised")):
                    f = fig(330, title=dict(text=nm, font=dict(size=12)))
                    f.add_scattergl(x=z.real, y=z.imag, mode="markers", marker=dict(size=3, color=CYAN, opacity=.5),
                                    showlegend=False)
                    f.update_yaxes(scaleanchor="x", scaleratio=1)
                    col.plotly_chart(f, width="stretch")
            with t3:
                f = fig(330, xaxis_title="frequency (kHz)", yaxis_title="|FFT|² (dB rel. peak)")
                f.add_scatter(x=sp["f_spec"] / 1e3, y=sp["spec_db"], line=dict(color=CYAN, width=1.2), showlegend=False)
                st.plotly_chart(f, width="stretch")
            with t4:
                f = fig(330, xaxis_title="frequency (kHz)", yaxis_title="PSD (dB/Hz)")
                f.add_scatter(x=sp["f_psd"] / 1e3, y=sp["psd_db"], line=dict(color=GREEN, width=1.2), showlegend=False)
                st.plotly_chart(f, width="stretch")
            st.caption(f"Validation: {vinfo['summary']} · provenance `{vinfo['provenance']}` · "
                       f"{export['experiment_id']}")
        elif mat is not None:
            st.info(f"Historical MATLAB export · provenance `{mat.get('provenance', '?')}` · "
                    f"{mat.get('summary', mat.get('error', ''))}")
            if mat.get("iq") is not None:
                z = np.asarray(mat["iq"])[:4000]
                f = fig(330, title=dict(text="received constellation (MATLAB export)", font=dict(size=12)))
                f.add_scattergl(x=z.real, y=z.imag, mode="markers", marker=dict(size=3, color=BLUE, opacity=.5))
                f.update_yaxes(scaleanchor="x", scaleratio=1)
                st.plotly_chart(f, width="stretch")
        elif sel and sel["kind"] in ("campaign", "aborted"):
            st.info("Campaign selected: see the Campaign tab.")
        else:
            st.markdown(f'<div class="card"><div class="s">Set inputs → RUN SIMULATION. '
                        f'Or select a run in Run history.</div></div>', unsafe_allow_html=True)

    # ---- right: result cards
    with right:
        e = eps[ep_idx] if eps else None
        dec = decs[ep_idx] if decs and ep_idx < len(decs) else None
        c1, c2 = st.columns(2)
        if e is not None or export is not None:
            ber = float(e["ber"]) if e else float(export["ber"])
            per = float(e["per"]) if e else float(export["per"])
            card(c1, "BER", fmt(ber, ".3e"), f"theory {fmt(e['ber_theory'] if e else export['ber_theory'], '.2e')}",
                 GREEN if ber < 1e-3 else AMBER if ber < 1e-2 else RED)
            card(c2, "PER", fmt(per, ".3f"), "256-bit packets", GREEN if per < .1 else AMBER if per < .5 else RED)
            card(c1, "SINR", f"{fmt(B.sinr_db(export), '.2f')} dB" if export is not None else "—",
                 f"Es/N0 {fmt(e['snr_db_measured'] if e else export['measured_snr_db'], '.2f')} dB")
            card(c2, "Goodput", f"{fmt(float(e['goodput_bps']) / 1e3, '.1f')} kb/s" if e else "—",
                 f"applied {e['modulation_applied'] if e else export['modulation']}")
            det = e.get("detected_modulation") if e else ""
            card(c1, "Detected", det or "—", f"conf {fmt(e.get('detected_confidence'), '.2f')}" if det else "agent not run")
            act = (e.get("selected_strategy") or e.get("next_modulation")) if e else "—"
            card(c2, "Action", act or "—", f"next: {e['next_modulation']}" if e else "")
            gate = B.risk_gate(dec)
            card(c1, "Risk gate", gate.split(" ")[0], gate[len(gate.split(' ')[0]):].strip(" ()"),
                 RED if gate.startswith("CLOSED") else GREEN if gate.startswith("OPEN") else MUTED)
            dur = B.job_status(sel["path"]).get("elapsed_s") if eps else export.get("wall_time_s")
            card(c2, "Duration", f"{fmt(dur, '.2f')} s", "job wall time" if eps else "flowgraph")
            ok = vinfo["ok"] if vinfo else None
            card(st, "Validation", "VALID" if ok else "INVALID" if ok is False else "—",
                 vinfo["provenance"] if vinfo else "", GREEN if ok else RED)
        else:
            for c, k in ((c1, "BER"), (c2, "PER"), (c1, "SINR"), (c2, "Goodput"), (c1, "Detected"), (c2, "Action"),
                         (c1, "Risk gate"), (c2, "Duration")):
                card(c, k, "—")

    # ---- pipeline blocks
    if eps:
        e = eps[ep_idx]
        dec = decs[ep_idx] if ep_idx < len(decs) else None
        has = dec is not None and "spectrum" in dec
        blocks = [
            ("GNU Radio", f"{e['modulation_applied']} · {e['channel']}/{e['fading_mode']}", GREEN),
            ("I/Q", f"{e['bits']} bits · {e['provenance']}", GREEN if e["provenance"] == "gnuradio_export" else RED),
            ("Spectrum Agent", f"{dec['spectrum']['modulation']} ({fmt(dec['spectrum']['confidence'], '.2f')}) · "
                               f"{fmt(dec['spectrum']['blind_snr_db'], '.1f')} dB" if has else "not used", CYAN if has else MUTED),
            ("Digital Twin", f"SNR {fmt(dec['twin']['snr_db'], '.1f')} dB · {dec['twin']['condition']}" if has else "not used",
             CYAN if has else MUTED),
            ("Prediction", f"risk {fmt(dec['prediction']['risk'], '.2f')} {dec['prediction']['level']}" if has else "not used",
             (RED if has and dec["prediction"]["level"] in ("HIGH", "CRITICAL") else AMBER
              if has and dec["prediction"]["level"] == "MEDIUM" else CYAN) if has else MUTED),
            ("Cyber Defense", ", ".join(dec["candidates"]) if has else "not used", CYAN if has else MUTED),
            ("ACWRA", f"{dec['selected']} · U {fmt(dec['utility'], '+.3f')}" if has else
             (dec or {}).get("rule", "—"), CYAN if has else MUTED),
            ("Next episode", e["next_modulation"], GREEN),
        ]
        html = []
        for i, (name, out, col) in enumerate(blocks):
            html.append(f'<div class="blk" style="--c:{col}"><div class="n">{name}</div><div class="o">{out}</div></div>')
            if i < len(blocks) - 1:
                html.append('<div class="arrow">›</div>')
        st.markdown('<div class="pipe">' + "".join(html) + "</div>", unsafe_allow_html=True)
        if has:
            with st.expander("Candidate utility scores · prediction"):
                c1, c2 = st.columns([2, 1])
                c1.dataframe([{"strategy": s["strategy"], "modulation": s["modulation"],
                               "pred BER": s["predicted_ber"], "T_norm": s["t_norm"], "SE_norm": s["se_norm"],
                               "K_c": s["complexity_prior"], "utility": s["utility_score"],
                               "selected": "✔" if s["strategy"] == dec["selected"] else ""} for s in dec["scores"]],
                             hide_index=True, width="stretch")
                c2.dataframe([{"field": k, "value": fmt(v, '.4g') if isinstance(v, (int, float)) else str(v)}
                              for k, v in dec["prediction"].items()], hide_index=True, width="stretch")

    # ---- bottom row
    b1, b2, b3 = st.columns(3, gap="medium")
    with b1:
        st.markdown("**DECISION TIMELINE**")
        if eps:
            x = [int(r["episode"]) for r in eps]
            order = {"BPSK": 0, "QPSK": 1, "OFDM-QPSK": 2}
            f = fig(260, yaxis=dict(tickvals=[0, 1, 2], ticktext=list(order), title="modulation"),
                    yaxis2=dict(overlaying="y", side="right", range=[0, 1], title="risk", showgrid=False))
            f.add_scatter(x=x, y=[order[r["modulation_applied"]] for r in eps], mode="lines+markers", name="applied",
                          line=dict(color=CYAN, shape="hv"))
            f.add_scatter(x=x, y=[order[r["next_modulation"]] for r in eps], mode="markers", name="decided → next",
                          marker=dict(color=AMBER, symbol="triangle-right", size=10))
            risks = [float(r["risk_score"]) if r.get("risk_score") not in ("", None) else None for r in eps]
            if any(v is not None for v in risks):
                f.add_scatter(x=x, y=risks, yaxis="y2", name="risk", line=dict(color=RED, dash="dot"))
            f.update_xaxes(title="episode", dtick=1)
            st.plotly_chart(f, width="stretch")
        else:
            st.caption("No episodes for the selected run.")
    curves = cached_curves(len(B.campaign_dirs()))
    with b2:
        st.markdown("**BER vs SNR** · GNU Radio")
        bv = curves["ber_validation"]
        if len({r["snr_db"] for r in bv}) >= 3:
            f = fig(260, xaxis_title="Es/N0 (dB)", yaxis=dict(type="log", title="BER", exponentformat="e"))
            for mod, col in zip(("BPSK", "QPSK", "OFDM-QPSK"), (CYAN, BLUE, GREEN)):
                rr = [r for r in bv if r["modulation"] == mod]
                if rr:
                    f.add_scatter(x=[r["snr_db"] for r in rr], y=[max(r["ber"], 1e-7) for r in rr], mode="markers",
                                  name=mod, marker=dict(color=col, size=7),
                                  error_y=dict(type="data", symmetric=False, array=[r["hi"] - r["ber"] for r in rr],
                                               arrayminus=[r["ber"] - r["lo"] for r in rr]))
                    f.add_scatter(x=[r["snr_db"] for r in rr], y=[r["theory"] for r in rr], mode="lines",
                                  line=dict(color=col, dash="dot", width=1), showlegend=False)
            st.plotly_chart(f, width="stretch")
        else:
            st.caption("Insufficient BER-validation data.")
    with b3:
        st.markdown("**PER vs SNR** · GNU Radio AWGN episodes")
        pc = curves["campaign_per"]
        if len({r["snr_db"] for r in pc}) >= 3:
            f = fig(260, xaxis_title="Es/N0 (dB)", yaxis_title="PER")
            for mod, col in zip(("BPSK", "QPSK", "OFDM-QPSK"), (CYAN, BLUE, GREEN)):
                rr = [r for r in pc if r["modulation"] == mod]
                if rr:
                    f.add_scatter(x=[r["snr_db"] for r in rr], y=[r["per"] for r in rr], mode="lines+markers",
                                  name=mod, line=dict(color=col),
                                  customdata=[r["episodes"] for r in rr],
                                  hovertemplate="%{x} dB: PER %{y:.3f} (%{customdata} episodes)")
            st.plotly_chart(f, width="stretch")
        else:
            st.caption("Insufficient campaign data.")


# ------------------------------------------------------------------ campaign tab

with tab_camp:
    cl, cr = st.columns([1, 2.4], gap="medium")
    with cl:
        st.markdown("**CAMPAIGN CONFIGURATION**")
        chans = st.multiselect("Channel conditions", list(B.CHANNELS), default=["AWGN", "Rayleigh (block)"], key="c_ch")
        snrs_txt = st.text_input("SNR values (dB)", "4, 8, 12, 16", key="c_snr")
        jams_txt = st.text_input("Jammer values", "0, 0.05, 0.2", key="c_jam")
        init_mod = st.selectbox("Initial modulation", list(B.MODULATIONS), index=1, key="c_mod")
        seeds_txt = st.text_input("Random seeds", "1, 2, 3", key="c_seeds")
        pols = st.multiselect("Policies", list(B.POLICY_LABELS), default=list(B.POLICY_LABELS),
                              format_func=B.POLICY_LABELS.get, key="c_pol")
        c1, c2 = st.columns(2)
        reps = c1.number_input("Episodes per run", 1, 50, 6, key="c_eps")
        nsym = c2.number_input("Symbols / episode", 256, 65536, 4096, step=64, key="c_nsym")

        def parse(txt, typ):
            try:
                return [typ(x) for x in txt.replace(";", ",").split(",") if x.strip()], None
            except ValueError:
                return [], "comma-separated numbers"

        snrs, e1 = parse(snrs_txt, float)
        jams, e2 = parse(jams_txt, float)
        seeds, e3 = parse(seeds_txt, int)
        cin = B.CampaignInputs(channels=chans, snrs=snrs, jammers=jams, initial_modulation=init_mod, seeds=seeds,
                               policies=pols, episodes=int(reps), n_symbols=int(nsym))
        cerr = B.validate_campaign(cin)
        for k, v in (("snrs", e1), ("jammers", e2), ("seeds", e3)):
            if v:
                cerr[k] = v
        for k, v in cerr.items():
            st.markdown(f'<div class="err">⚠ {k}: {v}</div>', unsafe_allow_html=True)
        st.markdown(chip(f"{cin.n_runs()} runs · {cin.n_flowgraphs()} GNU Radio flowgraphs", CYAN), unsafe_allow_html=True)
        if ss.pop("c_confirm_reset", False):
            ss["c_confirm"] = False
        confirm = st.checkbox(f"Confirm launch of {cin.n_flowgraphs()} flowgraph runs", key="c_confirm")
        if st.button("▶ RUN CAMPAIGN", type="primary", width="stretch",
                     disabled=not GR_OK or bool(cerr) or not confirm or bool(B.active_jobs())):
            from dataclasses import asdict
            _, path, _ = B.launch("campaign", asdict(cin))
            ss["active"] = path
            ss["c_confirm_reset"] = True
            st.rerun()
        own = ss.get("active")
        if own and os.path.dirname(own) == B.CAMPAIGNS:
            s = B.job_status(own)
            st.markdown(chip(f"{os.path.basename(own)} · {s.get('state')} · {s.get('done', 0)}/{s.get('total', 0)} "
                             f"done · {s.get('failed', 0)} failed", CYAN), unsafe_allow_html=True)
            if s.get("total"):
                st.progress(min(int(s.get("done", 0)) / int(s["total"]), 1.0))
            if st.button("■ STOP CAMPAIGN", width="stretch",
                         disabled=s.get("state") not in ("running", "queued")):
                B.stop_job(own)
                st.rerun()

    with cr:
        dirs = B.campaign_dirs()
        if not dirs:
            st.caption("No completed campaign.")
        else:
            labels = {os.path.basename(p): p for p in dirs}
            default = "grcl1_20261022_v2" if "grcl1_20261022_v2" in labels else list(labels)[-1]
            pick = st.selectbox("Campaign results", list(labels), index=list(labels).index(default), key="c_pick")
            path = labels[pick]
            comp = cached_comparison(path, os.path.getmtime(os.path.join(path, "runs.csv")))
            st.markdown(chip(f"{comp['runs']} runs · {comp['conditions']} conditions", GREEN) +
                        chip("condition-level paired · 95 % bootstrap CI · Wilcoxon", MUTED), unsafe_allow_html=True)
            m = sorted(comp["means"], key=lambda r: -r["goodput_kbps"])
            c1, c2 = st.columns(2)
            colors = [CYAN if r["policy"] == "acwra" else BLUE for r in m]
            names = [B.POLICY_LABELS.get(r["policy"], r["policy"]) for r in m]
            f = fig(280, yaxis_title="goodput (kb/s)")
            f.add_bar(x=names, y=[r["goodput_kbps"] for r in m], marker_color=colors, showlegend=False)
            c1.plotly_chart(f, width="stretch")
            f = fig(280, yaxis_title="BER")
            f.add_bar(x=names, y=[r["ber"] for r in m], marker_color=colors, showlegend=False)
            c2.plotly_chart(f, width="stretch")
            if comp["paired"]:
                for metric, unit, scale, c in (("goodput_bps", "kb/s", 1e-3, c1), ("ber", "", 1.0, c2)):
                    rr = [r for r in comp["paired"] if r["metric"] == metric]
                    f = fig(260, xaxis_title=f"ACWRA − baseline ({metric.replace('_bps', '')}{', ' + unit if unit else ''})")
                    f.add_scatter(x=[r["mean_diff"] * scale for r in rr], y=[B.POLICY_LABELS.get(r["b"], r["b"]) for r in rr],
                                  mode="markers", marker=dict(color=CYAN, size=9), showlegend=False,
                                  error_x=dict(type="data", symmetric=False,
                                               array=[(r["ci95_high"] - r["mean_diff"]) * scale for r in rr],
                                               arrayminus=[(r["mean_diff"] - r["ci95_low"]) * scale for r in rr]),
                                  customdata=[f"p={r['wilcoxon_p']:.2g} · {r['wins']}/{r['ties']}/{r['losses']}" for r in rr],
                                  hovertemplate="%{y}: %{x:.4g} (%{customdata})")
                    f.add_vline(x=0, line=dict(color=MUTED, dash="dot"))
                    c.plotly_chart(f, width="stretch")
                st.dataframe([{"baseline": B.POLICY_LABELS.get(r["b"], r["b"]), "metric": r["metric"],
                               "mean diff": r["mean_diff"], "CI low": r["ci95_low"], "CI high": r["ci95_high"],
                               "A>B/tie/A<B": f"{r['wins']}/{r['ties']}/{r['losses']}", "p": r["wilcoxon_p"]}
                              for r in comp["paired"]], hide_index=True, width="stretch")


# ------------------------------------------------------------------ history tab

with tab_hist:
    rows = B.run_history()
    srcs = sorted({r["Source"] for r in rows})
    keep = st.multiselect("Source", srcs, default=srcs, key="h_src")
    shown = [r for r in rows if r["Source"] in keep]
    st.markdown("".join(chip(f"{s}: {sum(1 for r in rows if r['Source'] == s)}", SRC_COLOR.get(s, MUTED)) for s in srcs),
                unsafe_allow_html=True)
    num = {"BER": ".3e", "SNR": ".1f", "Jammer": ".3f"}
    view = [{k: (fmt(v, num[k]) if k in num else str(v)) for k, v in r.items() if not k.startswith("_")} for r in shown]
    ev = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      height=420, key="h_table")
    picked = ev.selection.rows if ev and getattr(ev, "selection", None) else []
    if picked:
        r = shown[picked[0]]
        if ss.get("selected") != {"kind": r["_kind"], "path": r["_path"]}:
            ss["selected"] = {"kind": r["_kind"], "path": r["_path"]}
            st.rerun()                     # the Simulation tab rendered before this selection
        st.markdown(chip(f"Loaded {r['Run ID']} ({r['Source']}) → Simulation tab", SRC_COLOR.get(r["Source"], MUTED)),
                    unsafe_allow_html=True)
