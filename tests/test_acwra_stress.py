"""
Deterministic ACWRA stress scenarios (Task 11, Part 8).

These are pure mathematics tests: no Simulink, no MATLAB, no I/O, no randomness in the
decision path. They pin the three reference operating points

    A. CLEAR CHANNEL              R = 0.10, C = 0.95
    B. MODERATE DEGRADATION       R = 0.85, C = 1.00
    C. SEVERE JAMMING + LOW CONF  R = 0.95, C = 0.40

against the untouched ACWRA utility equation

    U(c) = [C * (w_t*T_norm + w_se*SE_norm)]
         - [(1 + R) * w_b * BER_norm]
         - [lambda_c * (1 - C) * K_c]

    w_t = 0.4   w_se = 0.2   w_b = 0.6   lambda_c = 1.0

They exist alongside (not instead of) the Simulink integration tests, so a regression in
the decision mathematics is caught even when no measurement data is available.
"""

import numpy as np
import pytest

from src.acwra.decision import ACWRADecision
from src.acwra.engine import ACWRAEngine
from src.acwra.scoring import ACWRAScoringEngine
from src.agents.messages import (
    DefenseCandidate,
    MultiAgentSnapshot,
    PredictionResult,
    SpectrumIntelligenceResult,
)
from src.digital_twin.twin import DigitalTwin
from src.virtual_rf.environment import VirtualRFEnvironment

ALL_CANDIDATES = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"]

SCENARIOS = {
    "A_CLEAR_CHANNEL": dict(risk=0.10, confidence=0.95, snr_db=25.0, modulation="QPSK"),
    "B_MODERATE_DEGRADATION": dict(risk=0.85, confidence=1.00, snr_db=8.0, modulation="QPSK"),
    "C_SEVERE_JAMMING_LOW_CONF": dict(risk=0.95, confidence=0.40, snr_db=2.0, modulation="OFDM-QPSK"),
}


def _snapshot(risk: float, confidence: float, modulation: str, snr_db: float):
    return MultiAgentSnapshot(
        timestamp_s=1.0,
        spectrum_result=SpectrumIntelligenceResult(
            modulation=modulation, snr_db=snr_db, classifier_confidence=confidence
        ),
        prediction_result=PredictionResult(risk_score=risk, risk_level="TEST"),
        defense_candidates=DefenseCandidate(candidate_strategies=list(ALL_CANDIDATES)),
    )


def _twin(snr_db: float, modulation: str, interference: float = 0.0):
    env = VirtualRFEnvironment(seed=42)
    twin = DigitalTwin(environment=env)
    twin.state.snr_db = snr_db
    twin.state.modulation = modulation
    twin.state.interference_power = interference
    return twin


def test_acwra_weights_are_unchanged():
    """The four ACWRA weights must remain exactly as specified."""
    scoring = ACWRAScoringEngine()
    assert scoring.w_t == 0.4
    assert scoring.w_se == 0.2
    assert scoring.w_b == 0.6
    assert scoring.lambda_c == 1.0

    engine = ACWRAEngine()
    assert engine.scoring_engine.w_t == 0.4
    assert engine.scoring_engine.w_se == 0.2
    assert engine.scoring_engine.w_b == 0.6
    assert engine.scoring_engine.lambda_c == 1.0


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_stress_scenario_produces_deterministic_decision(name):
    """Each stress scenario must be exactly reproducible across repeated evaluations."""
    cfg = SCENARIOS[name]

    decisions = []
    for _ in range(3):
        twin = _twin(cfg["snr_db"], cfg["modulation"])
        engine = ACWRAEngine()
        snap = _snapshot(cfg["risk"], cfg["confidence"], cfg["modulation"], cfg["snr_db"])
        decisions.append(engine.evaluate_and_decide(snap, twin))

    first = decisions[0]
    assert isinstance(first, ACWRADecision)
    assert first.selected_strategy in ALL_CANDIDATES
    assert len(first.candidate_scores) == len(ALL_CANDIDATES)
    assert first.risk_score == pytest.approx(cfg["risk"])
    assert first.agent_confidence == pytest.approx(cfg["confidence"])

    for other in decisions[1:]:
        assert other.selected_strategy == first.selected_strategy
        assert other.expected_utility == first.expected_utility
        for a, b in zip(first.candidate_scores, other.candidate_scores):
            assert a.strategy == b.strategy
            assert a.utility_score == b.utility_score


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_stress_scenario_utility_matches_closed_form(name):
    """
    Recompute U(c) from the published formula and require an exact match with the
    engine's own candidate scores. This is the guard against any silent change to
    the ACWRA mathematics.
    """
    cfg = SCENARIOS[name]
    twin = _twin(cfg["snr_db"], cfg["modulation"])
    engine = ACWRAEngine()
    snap = _snapshot(cfg["risk"], cfg["confidence"], cfg["modulation"], cfg["snr_db"])
    decision = engine.evaluate_and_decide(snap, twin)

    C = cfg["confidence"]
    R = cfg["risk"]
    w_t, w_se, w_b, lam = 0.4, 0.2, 0.6, 1.0

    for cs in decision.candidate_scores:
        expected = (
            C * (w_t * cs.t_norm + w_se * cs.se_norm)
            - (1.0 + R) * w_b * cs.ber_norm
            - lam * (1.0 - C) * cs.complexity_prior
        )
        assert cs.utility_score == pytest.approx(expected, abs=1e-12), (
            f"{name}/{cs.strategy}: engine U={cs.utility_score}, closed form={expected}"
        )

    # The winner is the arg-max of utility (ties broken by strategy name ascending).
    best = max(decision.candidate_scores, key=lambda cs: (cs.utility_score, -ord(cs.strategy[0])))
    assert decision.expected_utility == pytest.approx(
        max(cs.utility_score for cs in decision.candidate_scores)
    )
    assert decision.selected_strategy == sorted(
        decision.candidate_scores, key=lambda cs: (-cs.utility_score, cs.strategy)
    )[0].strategy
    assert best is not None


def test_low_confidence_activates_complexity_penalty():
    """
    Scenario C has C = 0.40, so the lambda_c*(1-C)*K_c term must actively penalise
    complex waveforms (K_c: BPSK 0.00 < QPSK 0.25 < OFDM-QPSK 0.50).
    """
    cfg = SCENARIOS["C_SEVERE_JAMMING_LOW_CONF"]
    twin = _twin(cfg["snr_db"], cfg["modulation"])
    decision = ACWRAEngine().evaluate_and_decide(
        _snapshot(cfg["risk"], cfg["confidence"], cfg["modulation"], cfg["snr_db"]), twin
    )
    by_strategy = {cs.strategy: cs for cs in decision.candidate_scores}

    assert by_strategy["BPSK"].complexity_prior == 0.0
    assert by_strategy["QPSK"].complexity_prior == 0.25
    assert by_strategy["OFDM-QPSK"].complexity_prior == 0.50

    penalty = lambda cs: 1.0 * (1.0 - cfg["confidence"]) * cs.complexity_prior
    assert penalty(by_strategy["OFDM-QPSK"]) > penalty(by_strategy["QPSK"]) > penalty(by_strategy["BPSK"])
    assert penalty(by_strategy["OFDM-QPSK"]) == pytest.approx(0.30)


def test_risk_amplifies_ber_penalty():
    """A higher risk score must strictly increase the BER penalty for the same candidate."""
    scoring = ACWRAScoringEngine()
    cf = [
        {"strategy": "BPSK", "modulation": "BPSK", "predicted_ber": 0.001,
         "predicted_throughput_bps": 100000.0},
        {"strategy": "QPSK", "modulation": "QPSK", "predicted_ber": 0.100,
         "predicted_throughput_bps": 200000.0},
    ]
    low = scoring.score_candidates(cf, risk_score=0.10, confidence=1.0)
    high = scoring.score_candidates(cf, risk_score=0.95, confidence=1.0)

    low_qpsk = next(c for c in low if c.strategy == "QPSK")
    high_qpsk = next(c for c in high if c.strategy == "QPSK")

    assert low_qpsk.ber_norm == pytest.approx(1.0)
    assert high_qpsk.ber_norm == pytest.approx(1.0)
    # Same normalised inputs, larger (1 + R) multiplier -> strictly lower utility.
    assert high_qpsk.utility_score < low_qpsk.utility_score
    assert (low_qpsk.utility_score - high_qpsk.utility_score) == pytest.approx(
        (0.95 - 0.10) * 0.6 * 1.0
    )


def test_scenario_ordering_is_sane():
    """
    Across the three scenarios the engine must always return a valid candidate and a
    non-empty trace, and never produce NaN/Inf utilities.
    """
    for name, cfg in SCENARIOS.items():
        twin = _twin(cfg["snr_db"], cfg["modulation"])
        decision = ACWRAEngine().evaluate_and_decide(
            _snapshot(cfg["risk"], cfg["confidence"], cfg["modulation"], cfg["snr_db"]), twin
        )
        assert decision.selected_strategy in ALL_CANDIDATES, name
        assert "ACWRA DECISION TRACE" in decision.decision_trace, name
        utils = np.array([cs.utility_score for cs in decision.candidate_scores])
        assert np.all(np.isfinite(utils)), name
