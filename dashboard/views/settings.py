"""Settings: display preferences for this browser session (nothing here changes simulations or results)."""

import streamlit as st

import backend as B
from ui import components as C

ss = st.session_state

a, b = st.columns([1.2, 1], gap="medium")
with a:
    with st.container(border=True, key="panel_prefs"):
        C.section("Plots", "wave", "this session")
        st.slider("Waveform samples shown", 32, 2048, step=16, key="pref_wave_n",
                  help="Leading samples of the exported I/Q drawn in the waveform plot.")
        st.slider("Constellation points (max)", 500, 20000, step=500, key="pref_const_n",
                  help="Leading samples drawn in constellation plots.")
        st.toggle("Show transmitted I reference on the waveform", key="pref_show_tx")
        C.section("Live updates", "clock")
        st.select_slider("Refresh interval while a job runs (s)", [0.5, 1.0, 2.0, 5.0], key="pref_refresh",
                         help="How often job progress and partial results are re-read. Nothing polls when idle.")
        if st.button("Restore defaults", icon=":material/restart_alt:", key="btn_prefs_reset"):
            for k in ("pref_wave_n", "pref_const_n", "pref_refresh", "pref_show_tx"):
                del ss[k]
            st.rerun()
with b:
    with st.container(border=True, key="panel_fixed"):
        C.section("Fixed configuration", "settings", "read only")
        C.kv([("Theme", "dark (.streamlit/config.toml)"), ("Dashboard output", B.rel(B.DASH)),
              ("Concurrency", "one job at a time"), ("Repository results", "read only"),
              ("Policies", ", ".join(B.POLICY_LABELS.values())), ("Channels", ", ".join(B.CHANNELS))])
        C.note("Preferences last for this browser session. Server options (port, theme) are set at launch — "
               "see README → Dashboard.")
