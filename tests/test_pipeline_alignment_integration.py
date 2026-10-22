"""
FIXTURE-BASED integration tests: measurement -> Spectrum Agent -> Digital Twin ->
Prediction Agent -> Cyber Defense Agent -> ACWRA.

All MAT files here come from src/simulink_bridge/reference_phy.py (source =
'python-fixture'). Passing these tests says nothing about the real Simulink model;
that is established only by simulink/matlab/run_v4_validation.m.
"""

import math
import os
import sys

import numpy as np
import pytest
from scipy.special import erfc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.modulation.digital import PSKModulator, generate_bits  # noqa: E402
from src.multicarrier.ofdm import OFDMTransmitterReceiver  # noqa: E402
from src.signal.generator import add_awgn  # noqa: E402
from src.simulink_bridge.pipeline import SimulinkACWRAPipeline  # noqa: E402
from src.simulink_bridge.protocol import SimulinkMeasurement  # noqa: E402
from src.simulink_bridge.reference_phy import write_reference_mat  # noqa: E402
from src.simulink_bridge.validation import PROVENANCE_FIXTURE  # noqa: E402
from src.virtual_rf.environment import VirtualRFEnvironment  # noqa: E402
from src.virtual_rf.state import EnvironmentState  # noqa: E402


def _run(tmp_path, name="m.mat", **kw):
    p = write_reference_mat(str(tmp_path / name), **kw)
    return SimulinkACWRAPipeline().run_from_mat(p)


# ======================================================== Keep Current semantics
@pytest.mark.parametrize("modulation", ["BPSK", "QPSK", "OFDM-QPSK"])
def test_keep_current_is_the_transmitted_modulation(tmp_path, modulation):
    """
    Regression: with the Task-5 classifier every non-repeating BPSK/QPSK window was
    labelled OFDM-QPSK, the twin adopted it, and 'Keep Current' was scored as
    OFDM-QPSK on a QPSK link.
    """
    res = _run(tmp_path, modulation=modulation, snr_db=15.0, seed=21)
    assert res.windows[-1].twin_state.modulation == modulation
    keep = [c for c in res.decision.candidate_scores if c.strategy == "Keep Current"]
    for c in keep:
        assert c.modulation == modulation


# ======================================================== temporal alignment
def test_time_is_aligned_through_every_stage(tmp_path):
    res = _run(tmp_path, modulation="QPSK", snr_db=12.0, interference_power=0.3, seed=5)
    t_win = [w.timestamp_s for w in res.windows]
    assert all(b > a for a, b in zip(t_win, t_win[1:]))
    hist = [s.timestamp_s for s in SimulinkACWRAPipeline().orchestrator.digital_twin.history.get_history()]
    assert hist == []                                                # fresh pipelines start empty
    win_dur = res.window_size / res.sample_rate
    assert t_win[1] - t_win[0] == pytest.approx(win_dur)
    assert [w.twin_state.timestamp_s for w in res.windows] == t_win  # twin mirrors each window
    pred = res.snapshot.prediction_result
    if pred.prediction_status == "SUCCESS":
        assert pred.predicted_timestamp_s == pytest.approx(t_win[-1] + win_dur)
    assert res.decision.timestamp_s == res.snapshot.timestamp_s


def test_each_run_starts_from_an_empty_twin(tmp_path):
    pipe = SimulinkACWRAPipeline()
    a = write_reference_mat(str(tmp_path / "a.mat"), modulation="QPSK", snr_db=20.0, seed=1)
    b = write_reference_mat(str(tmp_path / "b.mat"), modulation="QPSK", snr_db=2.0, seed=2)
    r1 = pipe.run_from_mat(a)
    n1 = len(pipe.orchestrator.digital_twin.history)
    r2 = pipe.run_from_mat(b)
    assert len(pipe.orchestrator.digital_twin.history) == n1 == len(r1.windows) == len(r2.windows)


# ======================================================== decision uses current evidence
def test_decision_is_the_argmax_of_its_own_scores(tmp_path):
    res = _run(tmp_path, modulation="QPSK", snr_db=4.0, interference_power=0.5, seed=8)
    scores = res.decision.candidate_scores
    best = sorted(scores, key=lambda c: (-c.utility_score, c.strategy))[0]
    assert res.decision.selected_strategy == best.strategy
    assert {c.strategy for c in scores} == set(res.snapshot.defense_candidates.candidate_strategies)
    assert res.decision.risk_score == res.snapshot.prediction_result.risk_score
    assert res.decision.agent_confidence == res.snapshot.spectrum_result.classifier_confidence


def test_counterfactuals_use_the_twins_current_state(tmp_path):
    res = _run(tmp_path, modulation="QPSK", snr_db=9.0, seed=9)
    st = res.windows[-1].twin_state
    env = VirtualRFEnvironment()
    for c in res.decision.candidate_scores:
        expect = env.simulate(EnvironmentState(snr_db=st.snr_db, channel_type=st.channel_type,
                                               interference_power=st.interference_power,
                                               modulation=st.modulation),
                              {"modulation": c.modulation, "snr_db": st.snr_db})
        assert c.predicted_ber == pytest.approx(expect.ber)


def test_results_row_carries_provenance(tmp_path):
    row = _run(tmp_path, modulation="BPSK", snr_db=10.0, seed=3).to_row()
    assert row["provenance"] == PROVENANCE_FIXTURE
    assert row["source"] == "python-fixture"


# ======================================================== errors stay visible
def test_invalid_measurement_raises_instead_of_producing_a_decision():
    """Bypassing validation with NaN I/Q must fail loudly, not yield a plausible decision."""
    iq = np.exp(1j * np.pi / 4) * np.ones(4096)
    iq[100] = np.nan
    m = SimulinkMeasurement(iq_samples=iq, snr_db=10.0, ber=0.0, modulation="QPSK",
                            tx_iq=np.exp(1j * np.pi / 4) * np.ones(4096), sample_rate=100e3)
    with pytest.raises(ValueError, match="NaN|finite"):
        SimulinkACWRAPipeline().run_measurement(m)


# ======================================================== corrected link model
def _q(x):
    return 0.5 * erfc(x / math.sqrt(2.0))


def _binom_tol(p, n, z=4.0):
    """z-sigma binomial tolerance on a measured error rate (bit errors ~independent)."""
    return z * math.sqrt(p * (1.0 - p) / n) + 1.0 / n


@pytest.mark.parametrize("snr_db", [0.0, 5.0, 8.0])
def test_link_model_matches_its_own_waveforms(snr_db):
    """The sandbox BER must equal the BER of the waveform add_awgn() actually produces."""
    env = VirtualRFEnvironment()
    g = 10 ** (snr_db / 10)
    model = {m: env._compute_congestion_metrics(m, snr_db, "awgn", 0.0)[0]
             for m in ("BPSK", "QPSK", "OFDM-QPSK")}
    assert model["BPSK"] == pytest.approx(_q(math.sqrt(2 * g)))
    assert model["QPSK"] == pytest.approx(_q(math.sqrt(g)))
    assert model["OFDM-QPSK"] == pytest.approx(_q(math.sqrt(g)))

    bits = generate_bits(120000, seed=11)
    for m_order, name in ((2, "BPSK"), (4, "QPSK")):
        psk = PSKModulator(M=m_order)
        rx = add_awgn(psk.modulate_baseband(bits), snr_db=snr_db, seed=12)
        meas = float(np.mean(psk.demodulate_baseband(rx)[:bits.size] != bits))
        assert abs(meas - model[name]) <= _binom_tol(model[name], bits.size), name
    ofdm = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
    obits = generate_bits(128 * 900, seed=13)
    w, _ = ofdm.modulate(obits)
    out = ofdm.demodulate(add_awgn(w, snr_db=snr_db, seed=14), num_ofdm_symbols=900)
    out = out[0] if isinstance(out, tuple) else out
    meas = float(np.mean(np.asarray(out)[:obits.size] != obits))
    assert abs(meas - model["OFDM-QPSK"]) <= _binom_tol(model["OFDM-QPSK"], obits.size)


def test_bpsk_is_no_longer_dominated_by_construction():
    """At equal SNR the sandbox now gives BPSK a lower BER than QPSK."""
    env = VirtualRFEnvironment()
    for snr in (0.0, 4.0, 8.0):
        b = env._compute_congestion_metrics("BPSK", snr, "awgn", 0.0)[0]
        q = env._compute_congestion_metrics("QPSK", snr, "awgn", 0.0)[0]
        assert b < q


# ======================================================== SNR / SINR unit consistency
def test_twin_snr_is_noise_only_so_the_sandbox_sinr_matches_the_measurement(tmp_path):
    """
    Regression: the twin used to receive the LS-measured SINR (jammer included), and
    the sandbox then subtracted the jammer again. Now the twin gets P_tx/P_noise and
    the sandbox's SINR = 1/(N0 + J) reproduces the measured SINR.
    """
    from src.virtual_rf.link_model import link_metrics
    p = write_reference_mat(str(tmp_path / "j.mat"), modulation="QPSK", snr_db=15.0,
                            interference_power=0.3, seed=12)
    res = SimulinkACWRAPipeline().run_from_mat(p)
    w = res.windows[-1]
    assert w.twin_snr_source == "measured_noise_iq"
    assert w.twin_snr_db == pytest.approx(15.0, abs=0.6)          # noise-only, ~ configured
    sandbox_sinr = link_metrics("QPSK", w.twin_snr_db, "awgn", res.measurement.interference_power)[4]
    assert sandbox_sinr == pytest.approx(w.measured_snr_db, abs=0.6)   # measured SINR of the window
    assert w.measured_snr_db < 15.0 - 3.0                              # jammer really lowers it


def test_legacy_file_without_noise_array_uses_the_nominal_snr(tmp_path):
    import scipy.io as sio
    rng = np.random.default_rng(1)
    iq = np.exp(1j * (np.pi / 2 * rng.integers(0, 4, 4096) + np.pi / 4)) + 0.05 * rng.standard_normal(4096)
    p = str(tmp_path / "l.mat")
    sio.savemat(p, {"iq_samples": iq.reshape(-1, 1), "snr_db": 13.0, "modulation": "QPSK"})
    w = SimulinkACWRAPipeline().run_from_mat(p).windows[-1]
    assert (w.twin_snr_source, w.twin_snr_db) == ("nominal", 13.0)
