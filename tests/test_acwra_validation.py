"""
ACWRA audit tests: input validation, ties, degenerate candidate sets and an
independent re-implementation of the documented objective (docs/acwra_algorithm.md).
The engine's equations, weights and normalisation are not modified.
"""

import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.acwra.engine import ACWRAEngine  # noqa: E402
from src.agents.messages import (  # noqa: E402
    DefenseCandidate,
    MultiAgentSnapshot,
    PredictionResult,
    SpectrumIntelligenceResult,
)
from src.digital_twin.twin import DigitalTwin  # noqa: E402
from src.virtual_rf.state import EnvironmentState  # noqa: E402

ALL = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"]


def _twin(mod="QPSK", snr=8.0, jam=0.5, chan="awgn"):
    t = DigitalTwin()
    t.update(EnvironmentState(timestamp_s=1.0, modulation=mod, snr_db=snr, ber=0.01,
                              interference_power=jam, channel_type=chan))
    return t


def _snap(risk=0.5, conf=0.9, cands=ALL):
    return MultiAgentSnapshot(
        timestamp_s=1.0,
        spectrum_result=SpectrumIntelligenceResult(classifier_confidence=conf),
        prediction_result=PredictionResult(risk_score=risk),
        defense_candidates=DefenseCandidate(candidate_strategies=list(cands)),
    )


@pytest.mark.parametrize("risk,conf", [(math.nan, 0.9), (0.5, math.nan), (math.inf, 0.9),
                                       (1.5, 0.9), (-0.1, 0.9), (0.5, 1.2), (0.5, -1.0)])
def test_invalid_risk_or_confidence_is_rejected(risk, conf):
    with pytest.raises(ValueError, match="must be a finite number in \\[0, 1\\]"):
        ACWRAEngine().evaluate_and_decide(_snap(risk, conf), _twin())


@pytest.mark.parametrize("risk,conf", [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)])
def test_boundary_values_are_accepted(risk, conf):
    d = ACWRAEngine().evaluate_and_decide(_snap(risk, conf), _twin())
    assert all(math.isfinite(c.utility_score) for c in d.candidate_scores)


def _utility_reference(cands, risk, conf, w_t=0.4, w_se=0.2, w_b=0.6, lam=1.0):
    """Independent implementation of U(c) from docs/acwra_algorithm.md."""
    def norm(v):
        v = np.asarray(v, float)
        return np.zeros_like(v) if np.isclose(v.max(), v.min()) else (v - v.min()) / (v.max() - v.min())
    se = {"BPSK": 1.0, "QPSK": 2.0, "OFDM-QPSK": 1.6}
    kc = {"BPSK": 0.0, "QPSK": 0.25, "OFDM-QPSK": 0.5}
    t = norm([c.predicted_throughput_bps for c in cands])
    b = norm([c.predicted_ber for c in cands])
    s = norm([se[c.modulation] for c in cands])
    return [conf * (w_t * t[i] + w_se * s[i]) - (1 + risk) * w_b * b[i] - lam * (1 - conf) * kc[c.modulation]
            for i, c in enumerate(cands)]


@pytest.mark.parametrize("mod,snr,jam,chan,risk,conf", [
    ("QPSK", 20.0, 0.0, "awgn", 0.1, 0.95),
    ("QPSK", 3.0, 0.0, "awgn", 0.8, 0.7),
    ("BPSK", 6.0, 0.4, "rayleigh", 0.6, 0.5),
    ("OFDM-QPSK", 10.0, 1.5, "awgn", 0.9, 0.3),
])
def test_selection_is_the_argmax_of_the_documented_objective(mod, snr, jam, chan, risk, conf):
    d = ACWRAEngine().evaluate_and_decide(_snap(risk, conf), _twin(mod, snr, jam, chan))
    ref = _utility_reference(d.candidate_scores, risk, conf)
    assert np.allclose([c.utility_score for c in d.candidate_scores], ref, atol=1e-12)
    assert d.expected_utility == pytest.approx(max(ref))
    winners = {c.strategy for c, u in zip(d.candidate_scores, ref) if np.isclose(u, max(ref))}
    assert d.selected_strategy == min(winners)             # documented name tie-break


def test_single_candidate_is_selected_with_finite_utility():
    d = ACWRAEngine().evaluate_and_decide(_snap(cands=["Keep Current"]), _twin())
    assert d.selected_strategy == "Keep Current" and math.isfinite(d.expected_utility)


def test_no_defense_message_defaults_to_keep_current():
    snap = _snap()
    snap.defense_candidates = None
    assert ACWRAEngine().evaluate_and_decide(snap, _twin()).selected_strategy == "Keep Current"


def test_tie_between_keep_current_and_its_own_modulation_is_by_name():
    """
    'Keep Current' and the current modulation score identically. The engine breaks
    ties by name, so for QPSK 'Keep Current' wins (K < Q) but for BPSK the label
    'BPSK' wins (B < K): a nominal switch to the waveform already in use. Switch
    statistics must therefore compare EFFECTIVE modulations (CandidateScore.modulation).
    """
    for mod in ("BPSK", "QPSK"):
        d = ACWRAEngine().evaluate_and_decide(_snap(cands=["Keep Current", mod]), _twin(mod))
        u = {c.strategy: c.utility_score for c in d.candidate_scores}
        assert u["Keep Current"] == u[mod]
        assert d.selected_strategy == min("Keep Current", mod)
        eff = next(c.modulation for c in d.candidate_scores if c.strategy == d.selected_strategy)
        assert eff == mod                                  # no actual waveform change


def test_decision_is_order_independent_over_candidates():
    a = ACWRAEngine().evaluate_and_decide(_snap(cands=ALL), _twin(snr=4.0))
    b = ACWRAEngine().evaluate_and_decide(_snap(cands=list(reversed(ALL))), _twin(snr=4.0))
    assert a.selected_strategy == b.selected_strategy
    assert a.expected_utility == pytest.approx(b.expected_utility)


# ====================================================== hand-calculated examples
def _cf(strategy, mod, tput, ber):
    return {"strategy": strategy, "modulation": mod, "predicted_ber": ber, "predicted_throughput_bps": tput}


def test_utility_matches_a_hand_calculation():
    """
    A: QPSK 200 kb/s BER 0.01   B: BPSK 100 kb/s BER 0.001   O: OFDM-QPSK 150 kb/s BER 0.0055
    R = 0.5, C = 0.8, w_t 0.4, w_se 0.2, w_b 0.6, lambda 1
    T_norm   A 1, B 0, O 0.5         BER_norm A 1, B 0, O 0.5
    SE       QPSK 2, BPSK 1, OFDM 1.6 -> SE_norm A 1, B 0, O 0.6
    K_c      QPSK 0.25, BPSK 0, OFDM 0.5
    U_A = 0.8(0.4 + 0.2)       - 1.5*0.6*1   - 0.2*0.25 = 0.48  - 0.9  - 0.05 = -0.47
    U_B = 0                    - 0           - 0        =  0
    U_O = 0.8(0.2 + 0.2*0.6)   - 1.5*0.6*0.5 - 0.2*0.5  = 0.256 - 0.45 - 0.1  = -0.294
    """
    from src.acwra.scoring import ACWRAScoringEngine
    s = ACWRAScoringEngine().score_candidates(
        [_cf("A", "QPSK", 200e3, 0.01), _cf("B", "BPSK", 100e3, 0.001), _cf("O", "OFDM-QPSK", 150e3, 0.0055)],
        risk_score=0.5, confidence=0.8)
    u = {c.strategy: c.utility_score for c in s}
    assert u["A"] == pytest.approx(-0.47, abs=1e-12)
    assert u["B"] == pytest.approx(0.0, abs=1e-12)
    assert u["O"] == pytest.approx(-0.294, abs=1e-12)
    norms = {c.strategy: (c.t_norm, c.ber_norm, c.se_norm) for c in s}
    assert norms["O"] == pytest.approx((0.5, 0.5, 0.6))


def test_boundary_confidence_and_risk_by_hand():
    from src.acwra.scoring import ACWRAScoringEngine
    cands = [_cf("A", "QPSK", 200e3, 0.01), _cf("B", "BPSK", 100e3, 0.001)]
    eng = ACWRAScoringEngine()
    # C = 0: no reward term, complexity penalty lambda*K_c = 0.25 for QPSK; R = 0
    u = {c.strategy: c.utility_score for c in eng.score_candidates(cands, risk_score=0.0, confidence=0.0)}
    assert u == pytest.approx({"A": -0.6 - 0.25, "B": 0.0})
    # C = 1, R = 1: reward 0.6, BER penalty 2*0.6, no complexity penalty
    u = {c.strategy: c.utility_score for c in eng.score_candidates(cands, risk_score=1.0, confidence=1.0)}
    assert u == pytest.approx({"A": 0.6 - 1.2, "B": 0.0})


def test_equal_metrics_normalise_to_zero_not_nan():
    from src.acwra.scoring import ACWRAScoringEngine
    s = ACWRAScoringEngine().score_candidates(
        [_cf("Keep Current", "QPSK", 1e5, 0.01), _cf("QPSK", "QPSK", 1e5, 0.01)], 0.5, 0.9)
    assert all(c.t_norm == c.ber_norm == c.se_norm == 0.0 for c in s)
    assert s[0].utility_score == s[1].utility_score == pytest.approx(-0.1 * 0.25)


def test_a_worse_proposal_does_not_replace_the_current_configuration():
    """Current BPSK at very low SNR: QPSK has the same SE gain but far worse BER."""
    d = ACWRAEngine().evaluate_and_decide(_snap(risk=0.9, conf=0.95, cands=["Keep Current", "QPSK"]),
                                          _twin(mod="BPSK", snr=3.0, jam=0.0))
    u = {c.strategy: c.utility_score for c in d.candidate_scores}
    assert u["Keep Current"] > u["QPSK"] and d.selected_strategy == "Keep Current"


def test_missing_prediction_defaults_to_zero_risk():
    snap = _snap(risk=0.7)
    snap.prediction_result = None
    d = ACWRAEngine().evaluate_and_decide(snap, _twin())
    assert d.risk_score == 0.0


def test_no_candidate_is_a_clear_error():
    with pytest.raises(ValueError, match="no candidate"):
        ACWRAEngine().evaluate_and_decide(_snap(cands=[]), _twin())
