"""
Robustness: extreme channels, seed behaviour, agent failures, unsupported
configurations. FIXTURE-BASED (src/simulink_bridge/reference_phy.py); none of this
exercises the real Simulink model.
"""

import math
import os
import sys
import warnings

import numpy as np
import pytest
import scipy.io as sio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.ai.modulation_classifier.inference as inference  # noqa: E402
from src.simulink_bridge.pipeline import SimulinkACWRAPipeline  # noqa: E402
from src.simulink_bridge.reference_phy import (  # noqa: E402
    generate_reference_measurement,
    write_reference_mat,
)


def _run(tmp_path, **kw):
    return SimulinkACWRAPipeline().run_from_mat(write_reference_mat(str(tmp_path / "r.mat"), **kw))


@pytest.mark.parametrize("kw", [
    dict(snr_db=-30.0),
    dict(snr_db=80.0),
    dict(snr_db=10.0, interference_power=50.0),
    dict(snr_db=-10.0, interference_power=10.0, channel_type="Rayleigh"),
    dict(snr_db=40.0, channel_type="Rician"),
])
def test_extreme_conditions_complete_with_a_valid_decision(tmp_path, kw):
    res = _run(tmp_path, modulation="QPSK", seed=3, **kw)
    d = res.decision
    assert d.selected_strategy in res.snapshot.defense_candidates.candidate_strategies
    assert all(math.isfinite(c.utility_score) for c in d.candidate_scores)
    assert 0.0 <= d.risk_score <= 1.0


def test_same_seed_is_bit_identical_and_gives_the_same_decision(tmp_path):
    a = generate_reference_measurement(modulation="QPSK", snr_db=6.0, interference_power=0.3, seed=17)
    b = generate_reference_measurement(modulation="QPSK", snr_db=6.0, interference_power=0.3, seed=17)
    for k in ("iq_samples", "tx_iq", "noise_iq", "interference_iq"):
        assert np.array_equal(a[k], b[k]), k
    pa = str(tmp_path / "a.mat")
    pb = str(tmp_path / "b.mat")
    sio.savemat(pa, a)
    sio.savemat(pb, b)
    ra, rb = SimulinkACWRAPipeline().run_from_mat(pa), SimulinkACWRAPipeline().run_from_mat(pb)
    assert ra.decision.selected_strategy == rb.decision.selected_strategy
    assert ra.decision.expected_utility == rb.decision.expected_utility


def test_different_seeds_give_independent_noise():
    """
    Independent complex Gaussian vectors have |corr| ~ 1/sqrt(N); require < 5/sqrt(N)
    for every pair (false-failure probability per pair ~ exp(-25)). Zero correlation
    is neither expected nor required.
    """
    draws = [np.asarray(generate_reference_measurement(snr_db=0.0, interference_power=0.5, seed=s)[k]).ravel()
             for s in (1, 2, 3, 4) for k in ("noise_iq",)]
    n = draws[0].size
    for i in range(len(draws)):
        for j in range(i + 1, len(draws)):
            a, b = draws[i], draws[j]
            c = abs(np.vdot(a, b)) / math.sqrt(np.vdot(a, a).real * np.vdot(b, b).real)
            assert c < 5 / math.sqrt(n), (i, j, c)


def test_missing_classifier_degrades_visibly_not_silently(tmp_path, monkeypatch):
    """No model: a RuntimeWarning, every window UNKNOWN, and the twin keeps the TRUE modulation."""
    monkeypatch.setattr(inference, "load_model",
                        lambda *a, **k: warnings.warn("model missing (test)", RuntimeWarning))
    with pytest.warns(RuntimeWarning):
        res = _run(tmp_path, modulation="BPSK", snr_db=12.0, seed=4)
    assert all(w.spectrum_result.modulation == "UNKNOWN" for w in res.windows)
    assert res.windows[-1].twin_state.modulation == "BPSK"
    assert res.decision.agent_confidence == 0.0


def test_a_failing_agent_raises_instead_of_returning_a_decision(tmp_path, monkeypatch):
    pipe = SimulinkACWRAPipeline()

    def boom(*a, **k):
        raise RuntimeError("prediction agent failure (injected)")

    monkeypatch.setattr(pipe.orchestrator.prediction_agent, "process", boom)
    p = write_reference_mat(str(tmp_path / "r.mat"), modulation="QPSK", snr_db=10.0, seed=5)
    with pytest.raises(RuntimeError, match="injected"):
        pipe.run_from_mat(p)


@pytest.mark.parametrize("modulation", ["16QAM", "8PSK", ""])
def test_unsupported_modulation_is_refused_by_the_reference_phy(modulation):
    with pytest.raises(ValueError):
        generate_reference_measurement(modulation=modulation)


def test_minimal_legacy_mat_still_runs_end_to_end(tmp_path):
    """Backward compatibility: only iq_samples, snr_db, modulation."""
    rng = np.random.default_rng(6)
    iq = np.exp(1j * (np.pi / 2 * rng.integers(0, 4, 4096) + np.pi / 4)) \
        + 0.1 * (rng.standard_normal(4096) + 1j * rng.standard_normal(4096))
    p = str(tmp_path / "legacy.mat")
    sio.savemat(p, {"iq_samples": iq.reshape(-1, 1), "snr_db": 17.0, "modulation": "QPSK"})
    res = SimulinkACWRAPipeline().run_from_mat(p)
    assert res.measurement.provenance == "legacy_python_mat"
    assert res.decision.selected_strategy
