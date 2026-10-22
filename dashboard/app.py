"""
CogniTwin-SDR dashboard (Streamlit): application shell.

    python dashboard/run_dashboard.py        (or: streamlit run dashboard/app.py from the repository root)

Sidebar navigation + top bar + live job monitor; the views live in dashboard/views/.
Inputs -> RUN -> a worker process executes GNU Radio through the existing backend ->
the views read back what the run wrote. Nothing runs when a page opens.
"""

import os
import sys

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import backend as B  # noqa: E402
from ui import components as C  # noqa: E402
from ui import data as D  # noqa: E402
from ui import theme as T  # noqa: E402

st.set_page_config(page_title="CogniTwin-SDR", page_icon=os.path.join(HERE, "static", "mark.svg"), layout="wide",
                   initial_sidebar_state="expanded")
D.init_state()
ss = st.session_state

# (script, title, icon, url, subtitle)
NAV = [
    ("views/overview.py", "Overview", "overview", "overview", "System status and recent activity"),
    ("views/live.py", "Live Simulation", "radio", "live", "Configure, execute and inspect a GNU Radio closed-loop run"),
    ("views/campaign.py", "Campaign Lab", "flask", "campaign", "Design and monitor multi-condition experiments"),
    ("views/agents.py", "AI Agents", "bot", "agents", "Recorded outputs of the cognitive pipeline, episode by episode"),
    ("views/comparison.py", "Policy Comparison", "scale", "comparison", "ACWRA against baselines on recorded campaign data"),
    ("views/history.py", "Run History", "history", "history", "Every run the dashboard can show, labelled by data class"),
    ("views/diagnostics.py", "System Diagnostics", "cpu", "diagnostics", "Runtime, data validation and artifacts"),
    ("views/settings.py", "Settings", "settings", "settings", "Display preferences for this session"),
]
pages = [st.Page(path, title=title, url_path=url, default=i == 0) for i, (path, title, _, url, _) in enumerate(NAV)]
pg = st.navigation(pages, position="sidebar")
st.logo(os.path.join(HERE, "static", "logo.svg"), size="large", icon_image=os.path.join(HERE, "static", "mark.svg"))

nav_css = "".join(C.icon_mask_css(f'[data-testid="stSidebarNavItems"] li:nth-child({i + 1}) a', ic)
                  for i, (_, _, ic, _, _) in enumerate(NAV))
st.markdown(T.CSS + f"<style>{nav_css}</style>", unsafe_allow_html=True)

status = D.gr_status()
active = B.active_jobs()

# ------------------------------------------------------------------ sidebar status
with st.sidebar:
    label, level, _ = B.gnuradio_state(status, bool(active))
    stats = D.overview_stats()
    C.md(f'<div class="ct-side-status">'
         f'<div class="row" style="--c:{T.TONES[level]}"><span class="dot"></span>{C.esc(label)}</div>'
         f'<div class="row" style="--c:{T.CYAN if active else T.TEXT_3}"><span class="dot"></span>'
         f'{"1 job running" if len(active) == 1 else f"{len(active)} jobs running" if active else "No active job"}</div>'
         f'<div class="row" style="--c:{T.INDIGO}"><span class="dot"></span>{stats["campaigns"]} campaigns · '
         f'{stats["validated_episodes"]:,} validated episodes</div></div>'
         f'<div class="ct-side-foot">GNU Radio software simulation · no SDR hardware</div>')


# ------------------------------------------------------------------ top bar
def _top_status():
    act = B.active_jobs()
    own = ss.get("active")
    cur = own if own else (act[0] if act else None)
    s = B.job_status(cur) if cur else {}
    state = s.get("state")
    label, level, detail = B.gnuradio_state(status, bool(act))
    chips = [C.chip(label, level, running=level == "run")]
    if cur:
        total, done = int(s.get("total") or 0), int(s.get("done") or 0)
        chips.append(C.chip(f"{state} · {done}/{total or '?'}", C.STATE_TONE.get(state, "muted"),
                            mono=os.path.basename(cur), running=state in ("running", "queued")))
    else:
        sel = D.selected_run()
        chips.append(C.chip("Run", "muted", mono=os.path.basename(sel["path"]) if sel else "none selected"))
    probs = B.recent_problems(10)
    C.md(f'<div class="ct-status" style="justify-content:flex-end">{"".join(chips)}</div>')
    if cur and int(s.get("total") or 0) and state in ("running", "queued"):
        st.progress(min(int(s.get("done") or 0) / int(s["total"]), 1.0),
                    text=f"{s.get('message', '')} · {C.fmt(s.get('elapsed_s'), '.1f')} s")
    if probs:
        with st.popover(f"{len(probs)} alert{'s' if len(probs) > 1 else ''}", icon=":material/notifications:"):
            for p in probs:
                C.md(f'{C.badge(p["state"], C.STATE_TONE.get(p["state"], "err"))} '
                     f'<span class="mono" style="font-size:.76rem">{C.esc(p["job"])}</span>'
                     f'<div class="ct-note">{C.esc(p["when"])} · {C.esc(p["message"][:220])}</div>')
    # a job this session started has just finished: show its result once and refresh every view
    if own and state not in ("running", "queued") and not ss.get(f"seen_{own}"):
        ss[f"seen_{own}"] = True
        if os.path.dirname(own) == B.RUNS:
            D.select("dash_run", own)
        st.toast(f"{os.path.basename(own)}: {state} — {s.get('message', '')}",
                 icon=":material/check_circle:" if state == "done" else ":material/error:")
        st.rerun()


title = pg.title
sub = next((n[4] for n in NAV if n[1] == title), "")
left, right = st.columns([1.35, 1], vertical_alignment="bottom")
with left:
    C.md(f'<div class="ct-crumb">CogniTwin-SDR {C.icon("chevron", 11)} <b>{C.esc(title)}</b></div>'
         f'<div class="ct-title">{C.esc(title)}</div><div class="ct-sub">{C.esc(sub)}</div>')
with right:
    running = bool(active) or (ss.get("active") and B.job_status(ss["active"]).get("state") in ("running", "queued"))
    st.fragment(_top_status, run_every=float(ss["pref_refresh"]) if running else None)()
C.md('<div style="height:1px;background:var(--border-soft);margin:10px 0 18px"></div>')

pg.run()
