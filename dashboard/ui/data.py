"""
Cached access to backend results and the session state shared by all views.

The caches key on file modification times, so a new or changed result file is
re-read; nothing here computes values the runs did not record.
"""

import os
from typing import Any, Dict, Optional

import streamlit as st

import backend as B

ss = st.session_state


@st.cache_data(show_spinner=False)
def gr_status() -> Dict[str, Any]:
    return B.gnuradio_status()


@st.cache_data(show_spinner=False)
def export(run_dir: str, episode: int, mtime: float):
    d, rep = B.load_episode_export(run_dir, episode)
    return d, {"ok": rep.ok, "summary": rep.summary(), "provenance": rep.facts.get("provenance"),
               "errors": rep.errors[:5]}


@st.cache_data(show_spinner=False)
def npz(path: str, mtime: float):
    from src.gnuradio_phy.export import load_export
    from src.gnuradio_phy.validation import validate_gnuradio_dict
    d = load_export(path)
    rep = validate_gnuradio_dict(d)
    return d, {"ok": rep.ok, "summary": rep.summary(), "provenance": rep.facts.get("provenance"),
               "errors": rep.errors[:5]}


@st.cache_data(show_spinner=False)
def signal_products(key: str, _d: Dict[str, Any]):
    return B.signal_products(_d)


@st.cache_data(show_spinner=False)
def curves(key: int):
    return B.ber_curves()


@st.cache_data(show_spinner=False)
def comparison(path: str, mtime: float, conditions: Optional[tuple] = None):
    return B.campaign_comparison(path, list(conditions) if conditions is not None else None)


@st.cache_data(show_spinner=False)
def condition_table(path: str, mtime: float):
    return B.campaign_condition_table(path)


@st.cache_data(show_spinner=False, ttl=5)
def overview_stats():
    return B.overview_stats()


@st.cache_data(show_spinner=False, ttl=3)
def history():
    return B.run_history()


@st.cache_data(show_spinner=False)
def campaign_steps(path: str, mtime: float):
    import csv
    f = os.path.join(path, "episodes_steps.csv")
    if not os.path.exists(f):
        return []
    with open(f, newline="") as fh:
        return list(csv.DictReader(fh))


@st.cache_data(show_spinner=False)
def text_file(path: str, mtime: float) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def runs_mtime(path: str) -> float:
    return mtime(os.path.join(path, "runs.csv"))


# ------------------------------------------------------------------ shared state

def init_state() -> None:
    ss.setdefault("selected", None)          # {"kind": dash_run|npz|mat|campaign|aborted, "path": ...}
    ss.setdefault("active", None)            # folder of the job this session launched
    ss.setdefault("confirm_smoke", False)
    ss.setdefault("pref_wave_n", 160)
    ss.setdefault("pref_const_n", 4000)
    ss.setdefault("pref_refresh", 1.0)
    ss.setdefault("pref_show_tx", True)
    # widget values survive page switches (Streamlit drops state of widgets that are not rendered)
    for k in list(ss.keys()):
        if isinstance(k, str) and k.startswith(("in_", "c_", "h_", "pc_", "ag_", "pref_")):
            ss[k] = ss[k]


def selected_run() -> Optional[Dict[str, str]]:
    """The run views show: explicit selection, else the newest dashboard run with episodes."""
    sel = ss.get("selected")
    if sel and os.path.exists(sel["path"]):
        return sel
    p = B.latest_run_with_episodes()
    return {"kind": "dash_run", "path": p} if p else None


def select(kind: str, path: str) -> None:
    ss["selected"] = {"kind": kind, "path": path}


def demo_export_path() -> Optional[str]:
    """Newest repository GNU Radio demo export (read only), if any."""
    demo = os.path.join(B.ROOT, "results", "gnuradio", "demo")
    if not os.path.isdir(demo):
        return None
    for rid in sorted(os.listdir(demo), reverse=True):
        p = os.path.join(demo, rid)
        f = [x for x in os.listdir(p) if x.endswith(".npz")] if os.path.isdir(p) else []
        if f:
            return os.path.join(p, f[0])
    return None
