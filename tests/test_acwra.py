"""
Unit tests for ACWRA decision engine and scoring module.
"""

import pytest
import numpy as np

from src.virtual_rf.environment import VirtualRFEnvironment
from src.digital_twin.twin import DigitalTwin
from src.agents.messages import (
    MultiAgentSnapshot,
    SpectrumIntelligenceResult,
    PredictionResult,
    DefenseCandidate,
)
from src.acwra.scoring import ACWRAScoringEngine
from src.acwra.engine import ACWRAEngine
from src.acwra.decision import ACWRADecision, CandidateScore


def test_zero_division_prevention():
    """
    CRITICAL TEST: Verifies min-max normalization prevents ZeroDivisionError when max == min.
    """
    scoring = ACWRAScoringEngine()

    # Case 1: All values identical (e.g. all 0.0 bps)
    zero_vals = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    norm = scoring.min_max_normalize(zero_vals)

    assert len(norm) == 4
    assert np.all(norm == 0.0)  # No NaN or Inf

    # Case 2: All non-zero identical values
    same_vals = np.array([10.0, 10.0, 10.0], dtype=np.float64)
    norm_same = scoring.min_max_normalize(same_vals)
    assert np.all(norm_same == 0.0)


def test_acwra_determinism():
    """
    CRITICAL TEST: Verifies ACWRA produces exact identical utility scores given identical inputs.
    """
    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env)
    engine = ACWRAEngine()

    spec = SpectrumIntelligenceResult(modulation="QPSK", snr_db=8.0, classifier_confidence=0.95)
    pred = PredictionResult(risk_score=0.4, risk_level="MEDIUM")
    def_cand = DefenseCandidate(candidate_strategies=["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"])

    snapshot = MultiAgentSnapshot(
        timestamp_s=1.5,
        spectrum_result=spec,
        prediction_result=pred,
        defense_candidates=def_cand,
    )

    decision1 = engine.evaluate_and_decide(snapshot, dt)
    decision2 = engine.evaluate_and_decide(snapshot, dt)

    assert decision1.selected_strategy == decision2.selected_strategy
    assert decision1.expected_utility == decision2.expected_utility
    for cs1, cs2 in zip(decision1.candidate_scores, decision2.candidate_scores):
        assert cs1.strategy == cs2.strategy
        assert cs1.utility_score == cs2.utility_score


def test_acwra_scoring_math():
    """
    Verifies theoretical spectral efficiency, complexity priors, and utility calculation.
    """
    scoring = ACWRAScoringEngine()

    se_bpsk = scoring.get_theoretical_spectral_efficiency("BPSK")
    se_qpsk = scoring.get_theoretical_spectral_efficiency("QPSK")
    se_ofdm = scoring.get_theoretical_spectral_efficiency("OFDM-QPSK")

    assert se_bpsk == 1.0
    assert se_qpsk == 2.0
    assert np.isclose(se_ofdm, 1.6)  # 2.0 * (64 / 80)

    assert scoring.get_complexity_prior("BPSK") == 0.0
    assert scoring.get_complexity_prior("QPSK") == 0.25
    assert scoring.get_complexity_prior("OFDM-QPSK") == 0.50


def test_acwra_decision_trace():
    """
    Verifies human-readable decision trace formatting.
    """
    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env)
    engine = ACWRAEngine()

    spec = SpectrumIntelligenceResult(modulation="QPSK", snr_db=8.0, classifier_confidence=0.90)
    pred = PredictionResult(risk_score=0.3, risk_level="MEDIUM")
    def_cand = DefenseCandidate(candidate_strategies=["Keep Current", "BPSK", "QPSK"])

    snapshot = MultiAgentSnapshot(
        timestamp_s=1.0,
        spectrum_result=spec,
        prediction_result=pred,
        defense_candidates=def_cand,
    )

    decision = engine.evaluate_and_decide(snapshot, dt)

    assert isinstance(decision, ACWRADecision)
    assert len(decision.decision_trace) > 0
    assert "ACWRA DECISION TRACE" in decision.decision_trace
    assert decision.selected_strategy in ["Keep Current", "BPSK", "QPSK"]
