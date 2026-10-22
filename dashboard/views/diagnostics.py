"""System Diagnostics: runtime, execution, data validation, tests, problems and artifact locations.

Only versions and repository-relative paths are shown: no absolute user paths, no environment variables."""

import os

import streamlit as st

import backend as B
from ui import components as C
from ui import data as D

ss = st.session_state
status = D.gr_status()
active = B.active_jobs()
probs = B.recent_problems(30)
camps_all = [r for r in D.history() if r["_kind"] in ("campaign", "aborted")]
stats = D.overview_stats()
label, level, detail = B.gnuradio_state(status, bool(active))

C.metrics([
    C.metric("GNU Radio", {"ok": "Ready", "run": "Executing", "err": "Not installed", "warn": "Import failed"}[level],
             f"v{status['version']}" if status["available"] else "execution disabled", level, "radio"),
    C.metric("Execution backend", f"{len(active)} running" if active else "Idle",
             "worker subprocess · one job at a time", "run" if active else "muted", "cpu"),
    C.metric("Validated episodes", f"{stats['validated_episodes']:,}",
             f"{stats['validated_episodes'] / stats['episodes']:.1%} of {stats['episodes']:,}" if stats["episodes"]
             else "no episodes", "ok", "shield"),
    C.metric("Campaigns", f"{sum(r['Status'] == 'done' for r in camps_all)} done",
             f"{sum(r['_kind'] == 'aborted' for r in camps_all)} aborted (kept as evidence)", "info", "flask"),
    C.metric("Alerts", f"{len(probs)}", "failed / blocked / stopped jobs", "err" if probs else "ok", "bell"),
], min_width=170)

a, b = st.columns(2, gap="medium")
with a:
    with st.container(border=True, key="panel_gr"):
        C.section("GNU Radio", "radio", C.badge(label, level))
        shown = detail.split(" at ")[0] if status["available"] else detail     # drop the install path
        C.kv([("Importable", "yes" if status["available"] else "no"), ("Version", status.get("version")),
              ("Probe", shown), ("Execution", "enabled" if status["available"] else "disabled (buttons greyed out)")])
        if not status["available"]:
            C.note("Install GNU Radio in a separate conda environment and launch the dashboard from it "
                   "(docs/GNURADIO_SETUP.md, README → Dashboard).")
with b:
    with st.container(border=True, key="panel_env"):
        C.section("Python environment", "terminal")
        C.kv(list(B.environment_info().items()))

a, b = st.columns(2, gap="medium")
with a:
    with st.container(border=True, key="panel_val"):
        C.section("Data validation", "shield", "from the recorded files")
        rows = []
        for p in B.campaign_dirs():
            steps = D.campaign_steps(p, D.mtime(os.path.join(p, "episodes_steps.csv")))
            prov = sorted({s.get("provenance", "") for s in steps})
            rows.append({"dataset": os.path.basename(p), "episodes": len(steps),
                         "provenance": ", ".join(prov) or "—",
                         "status": "valid" if prov == ["gnuradio_export"] else "check"})
        bv_dir = os.path.join(B.ROOT, "results", "gnuradio", "ber_validation")
        for rid in sorted(os.listdir(bv_dir)) if os.path.isdir(bv_dir) else []:
            chk = B.read_json(os.path.join(bv_dir, rid, "checks.json"), {}) or {}
            if "ber_points_judged" in chk:
                rows.append({"dataset": rid, "episodes": chk["ber_points_judged"],
                             "provenance": f"{chk['ber_points_pass']}/{chk['ber_points_judged']} BER points within CI",
                             "status": "valid" if chk["ber_points_pass"] == chk["ber_points_judged"] else "check"})
        for r in camps_all:
            if r["_kind"] == "aborted":
                rows.append({"dataset": r["Run ID"], "episodes": None, "provenance": "aborted — no results",
                             "status": "aborted"})
        st.dataframe(C.styled(rows, {"episodes": "{:,.0f}"}), hide_index=True, width="stretch")
with b:
    with st.container(border=True, key="panel_tests"):
        C.section("Dashboard test suite", "check", "tests/test_dashboard.py")
        res = ss.get("diag_tests")
        if res:
            C.md(C.badge("passed" if res["ok"] else "failed", "ok" if res["ok"] else "err") +
                 f' <span class="mono" style="font-size:.8rem">{C.esc(res["summary"])}</span>'
                 f'<div class="ct-note">run {C.esc(res["when"])} in this session</div>')
            with st.expander("Output (last lines)"):
                st.code(res["tail"] or "(none)", language=None)
        else:
            C.note("Not run in this session. Tests write job output to a temporary folder, never into results/.")
        if st.button("Run dashboard tests", icon=":material/play_arrow:", key="btn_tests", disabled=bool(active),
                     help="Takes about 10–60 s; GNU Radio execution tests are skipped without GNU Radio"):
            with st.spinner("Running pytest…"):
                ss["diag_tests"] = B.run_dashboard_tests()
            st.rerun()

with st.container(border=True, key="panel_probs"):
    C.section("Recent errors and warnings", "alert", "dashboard jobs")
    if probs:
        st.dataframe([{"when": p["when"], "job": p["job"], "state": p["state"], "message": p["message"]} for p in probs],
                     hide_index=True, width="stretch")
    else:
        C.empty("No problems recorded", "No dashboard job has failed, been blocked, stopped or recorded failures.", "check")

with st.container(border=True, key="panel_dirs"):
    C.section("Output locations and artifacts", "drive", "repository-relative")
    locs = [("Campaigns (repository, read only)", os.path.join(B.ROOT, "results", "gnuradio", "campaign")),
            ("BER validation (read only)", os.path.join(B.ROOT, "results", "gnuradio", "ber_validation")),
            ("GNU Radio demo (read only)", os.path.join(B.ROOT, "results", "gnuradio", "demo")),
            ("Spectrum evaluation (read only)", os.path.join(B.ROOT, "results", "gnuradio", "spectrum_eval")),
            ("Simulink exports (historical)", os.path.join(B.ROOT, "simulink", "results")),
            ("Dashboard simulations", B.RUNS), ("Dashboard campaigns", B.CAMPAIGNS), ("Dashboard ledger", B.LEDGER)]
    out = []
    for name, p in locs:
        n = size = 0
        if os.path.isdir(p):
            for dp, _, fs in os.walk(p):
                n += len(fs)
                size += sum(os.path.getsize(os.path.join(dp, f)) for f in fs)
        elif os.path.isfile(p):
            n, size = 1, os.path.getsize(p)
        out.append({"location": name, "path": B.rel(p), "exists": os.path.exists(p), "files": n,
                    "size (MB)": round(size / 1e6, 2)})
    st.dataframe(out, hide_index=True, width="stretch")
