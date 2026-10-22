"""
Dashboard: input validation, job control, worker execution, result loading, UI render.

Category: dashboard. Job output is redirected to a temporary folder
(COGNITWIN_DASH_DIR), so tests never write into results/. Tests that need GNU Radio,
or Streamlit for the UI, skip with the reason; fixture-based runs are checked to be
labelled 'Fixture', never 'GNU Radio'.
"""

import os
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["COGNITWIN_DASH_DIR"] = tempfile.mkdtemp(prefix="cognitwin_dash_test_")
for p in (os.path.join(ROOT, "dashboard"), os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path:
        sys.path.insert(0, p)

import backend as B  # noqa: E402
from gr_test_helpers import labelled_fixture  # noqa: E402
from src.gnuradio_phy.availability import gnuradio_available  # noqa: E402

needs_gr = pytest.mark.skipif(not gnuradio_available(), reason="GNU Radio NOT RUN: not importable here")


def _wait(path, timeout=240):
    t0 = time.time()
    while B.job_status(path).get("state") in ("queued", "running"):
        assert time.time() - t0 < timeout, "job did not finish"
        time.sleep(0.3)
    return B.job_status(path)


# ------------------------------------------------------------------ configuration / validation

def test_output_redirected_to_temp():
    assert B.DASH == os.environ["COGNITWIN_DASH_DIR"]
    assert not B.DASH.startswith(os.path.join(ROOT, "results"))


def test_valid_inputs_build_the_backend_config():
    cfg, err = B.validate_inputs(B.SimInputs(modulation="BPSK", snr_db=7.5, jammer=0.1, channel="Rician (changing)",
                                             doppler_fdts=1e-3, rician_k=4.0, seed=9))
    assert not err
    assert (cfg.modulation, cfg.channel, cfg.fading_mode, cfg.snr_db, cfg.interference_power, cfg.seed) == \
        ("BPSK", "RICIAN", "time_varying", 7.5, 0.1, 9)
    assert cfg.rician_k == 4.0 and cfg.doppler_fdts == 1e-3


@pytest.mark.parametrize("label", list(B.CHANNELS))
def test_every_channel_option_is_supported_by_the_backend(label):
    assert not B.validate_inputs(B.SimInputs(channel=label))[1]


@pytest.mark.parametrize("kw,key", [
    (dict(snr_db=99.0), "snr_db"), (dict(jammer=-1.0), "jammer"), (dict(seed=0), "seed"),
    (dict(modulation="OFDM-QPSK", n_symbols=1000), "n_symbols"), (dict(policy="fixed_OFDM-QPSK", n_symbols=1000), "n_symbols"),
    (dict(n_symbols=10), "n_symbols"), (dict(episodes=0), "episodes"), (dict(policy="magic"), "policy"),
    (dict(channel="Ricean"), "channel"), (dict(rolloff=0.0), "rolloff"),
])
def test_invalid_inputs_report_the_field(kw, key):
    cfg, err = B.validate_inputs(B.SimInputs(**kw))
    assert cfg is None and key in err, err


def test_adaptation_toggle_maps_to_no_adaptation():
    assert B.SimInputs(policy="acwra", adaptation=False).effective_policy() == "no_adaptation"
    assert B.SimInputs(policy="fixed_QPSK", adaptation=False).effective_policy() == "fixed_QPSK"
    assert set(B.POLICY_LABELS) == set(B.POLICIES)


def test_campaign_validation_and_size():
    assert not B.validate_campaign(B.CampaignInputs())
    assert "policies" in B.validate_campaign(B.CampaignInputs(policies=[]))
    c = B.CampaignInputs(snrs=list(range(40)), jammers=[0, .1, .2, .3, .4], seeds=list(range(1, 11)))
    assert "size" in B.validate_campaign(c)
    assert B.CampaignInputs().n_flowgraphs() == 2 * 2 * 2 * 2 * 3 * 6


# ------------------------------------------------------------------ job control

@pytest.mark.skipif(gnuradio_available(), reason="GNU Radio installed: the job would really run")
def test_job_without_gnuradio_is_blocked_and_produces_nothing():
    _, path, _ = B.launch("simulation", B.spec_from_inputs(B.SimInputs(episodes=1)))
    st = _wait(path)
    assert st["state"] == "blocked" and "GNU Radio" in st["message"]
    assert not [f for f in os.listdir(path) if f.endswith(".npz")]


def test_stop_refuses_outside_dashboard_and_foreign_processes(tmp_path):
    with pytest.raises(PermissionError):
        B.stop_job(os.path.join(ROOT, "results", "gnuradio", "campaign", "grcl1_20261022_v2"))
    rid, path = B.new_job_dir("simulation")
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        B.write_json(os.path.join(path, "status.json"), {"state": "running", "pid": sleeper.pid})
        with pytest.raises(PermissionError, match="not a dashboard worker"):
            B.stop_job(path)
        assert sleeper.poll() is None                       # untouched
    finally:
        sleeper.kill()


def test_job_folders_are_never_reused():
    a = B.new_job_dir("simulation")[1]
    b = B.new_job_dir("simulation")[1]
    assert a != b and os.path.isdir(a) and os.path.isdir(b)


# ------------------------------------------------------------------ result loading (fixture data)

@pytest.fixture()
def fixture_run(monkeypatch):
    """A dashboard run produced by the worker with the NumPy stand-in instead of GNU Radio."""
    import worker
    import src.gnuradio_phy.runner as runner
    monkeypatch.setattr(runner, "run_gnuradio", labelled_fixture)
    inp = B.SimInputs(snr_db=3.0, jammer=0.1, episodes=3, n_symbols=1024)
    rid, path = B.new_job_dir("simulation")
    B.write_json(os.path.join(path, "job.json"), {"kind": "simulation", "run_id": rid, "spec": B.spec_from_inputs(inp)})
    assert worker.run_simulation(path, B.spec_from_inputs(inp), worker.Status(path)) == 0
    return path


def test_worker_records_episodes_decisions_and_exports(fixture_run):
    eps, decs = B.load_episodes(fixture_run), B.load_decisions(fixture_run)
    assert len(eps) == len(decs) == 3
    for k, (e, d) in enumerate(zip(eps, decs)):
        assert os.path.exists(os.path.join(fixture_run, f"ep{k}.npz"))
        assert d["episode"] == k and d["candidates"] and d["scores"] and "risk" in d["prediction"]
        if k:
            assert e["modulation_applied"] == eps[k - 1]["next_modulation"]
    assert B.job_status(fixture_run)["state"] == "done"


def test_fixture_run_is_labelled_fixture_never_gnuradio(fixture_run):
    row = next(r for r in B.run_history() if r["_path"] == fixture_run)
    assert row["Source"] == B.SRC_FIXTURE
    d, rep = B.load_episode_export(fixture_run, 0)
    assert rep.facts["provenance"] == "python_fixture"


def test_plot_products_come_from_the_export(fixture_run):
    d, _ = B.load_episode_export(fixture_run, 1)
    sp = B.signal_products(d)
    assert sp["iq"].size == d["iq_samples"].size and sp["f_psd"].size == sp["psd_db"].size
    assert abs(B.sinr_db(d) - (-10 * __import__("math").log10(10 ** -0.3 + 0.1))) < 1.0
    assert B.risk_gate(B.load_decisions(fixture_run)[0]).split()[0] in ("OPEN", "CLOSED")
    assert B.risk_gate(None) == "n/a"


def test_corrupted_export_is_reported_not_plotted(fixture_run):
    with open(os.path.join(fixture_run, "ep2.npz"), "wb") as fh:
        fh.write(b"corrupt")
    from src.simulink_bridge.validation import MeasurementValidationError
    with pytest.raises(MeasurementValidationError):
        B.load_episode_export(fixture_run, 2)


def test_history_classifies_repository_results():
    rows = B.run_history()
    by_id = {r["Run ID"]: r for r in rows}
    if "grcl1_20261022" in by_id:
        assert by_id["grcl1_20261022"]["Source"] == B.SRC_ABORTED
    if "grcl1_20261022_v2" in by_id:
        assert by_id["grcl1_20261022_v2"]["Source"] == B.SRC_GNURADIO
    assert all(r["Source"] == B.SRC_MATLAB for r in rows if r["_kind"] == "mat" and "campaign_fixture" not in r["_path"])


def test_campaign_comparison_and_curves_use_saved_results():
    path = os.path.join(ROOT, "results", "gnuradio", "campaign", "grcl1_20261022_v2")
    if not os.path.exists(os.path.join(path, "runs.csv")):
        pytest.skip("campaign grcl1_20261022_v2 not present")
    comp = B.campaign_comparison(path)
    assert comp["runs"] == 810 and comp["conditions"] == 27 and len(comp["means"]) == 6
    sinr = next(r for r in comp["paired"] if r["b"] == "sinr_threshold" and r["metric"] == "ber")
    assert sinr["mean_diff"] > 0                              # the negative finding is shown as recorded
    assert path not in [p for p in B.campaign_dirs() if os.path.exists(os.path.join(p, "ABORTED.md"))]
    curves = B.ber_curves()
    assert len(curves["ber_validation"]) >= 18 and curves["campaign_per"]


# ------------------------------------------------------------------ real GNU Radio execution

@needs_gr
def test_real_simulation_job_through_the_worker():
    inp = B.SimInputs(snr_db=6.0, jammer=0.05, channel="Rayleigh (block)", episodes=2, n_symbols=1024)
    _, path, _ = B.launch("simulation", B.spec_from_inputs(inp))
    st = _wait(path)
    assert st["state"] == "done", st
    eps = B.load_episodes(path)
    assert len(eps) == 2 and {e["provenance"] for e in eps} == {"gnuradio_export"}
    d, rep = B.load_episode_export(path, 1)
    assert rep.ok and rep.facts["provenance"] == "gnuradio_export"
    assert next(r for r in B.run_history() if r["_path"] == path)["Source"] == B.SRC_GNURADIO


@needs_gr
def test_stop_terminates_a_running_dashboard_job():
    inp = B.SimInputs(episodes=50, n_symbols=65536)
    _, path, pid = B.launch("simulation", B.spec_from_inputs(inp))
    t0 = time.time()
    while B.job_status(path).get("state") != "running":
        assert time.time() - t0 < 60
        time.sleep(0.2)
    assert B.stop_job(path)
    time.sleep(1.0)
    assert B.job_status(path)["state"] == "stopped" and not B._pid_alive(pid)


# ------------------------------------------------------------------ UI

def test_app_renders_without_launching_anything():
    pytest.importorskip("streamlit", reason="Streamlit not installed in this environment")
    from streamlit.testing.v1 import AppTest
    before = set(os.listdir(B.RUNS)) if os.path.isdir(B.RUNS) else set()
    at = AppTest.from_file(os.path.join(ROOT, "dashboard", "app.py"), default_timeout=120).run()
    assert not at.exception
    after = set(os.listdir(B.RUNS)) if os.path.isdir(B.RUNS) else set()
    assert after == before
    run = next(b for b in at.button if "RUN SIMULATION" in b.label)
    assert run.disabled == (not gnuradio_available())
    at.selectbox(key="in_mod").set_value("OFDM-QPSK")
    at.number_input(key="in_nsym").set_value(1000)
    at.run()
    assert next(b for b in at.button if "RUN SIMULATION" in b.label).disabled
    assert any("multiple of 64" in m.value for m in at.markdown)
