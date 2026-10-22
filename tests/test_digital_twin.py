"""
Unit tests for Cognitive Digital Twin (CDT) module.
"""

import pytest
import numpy as np

from src.virtual_rf.environment import VirtualRFEnvironment
from src.virtual_rf.state import EnvironmentState
from src.digital_twin.state import DigitalTwinState
from src.digital_twin.twin import DigitalTwin
from src.digital_twin.history import HistoryBuffer
from src.digital_twin.predictor import TrendPredictor
from src.digital_twin.experience import ExperienceMemory
from src.digital_twin.fidelity import FidelityEvaluator


def test_digital_twin_state_and_history():
    """
    Verifies state updates, history buffering, and rate of change calculation.
    """
    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env, max_history_len=10)

    for step_idx in range(12):
        env_state, _ = env.step(duration_seconds=0.1)
        dt.update(env_state)

    assert len(dt.history) == 10  # Bounded to max_len=10
    assert np.isclose(dt.state.timestamp_s, 1.1)


def test_predictor_extrapolation_and_insufficient_history():
    """
    Verifies trend predictor INSUFFICIENT_HISTORY check and degree-1 linear extrapolation.
    """
    predictor = TrendPredictor(history_window=5)

    # 1. Insufficient history (< 5 states)
    history = [DigitalTwinState(timestamp_s=i * 0.1, snr_db=20.0 - i) for i in range(3)]
    res = predictor.predict_next_state(history, horizon_seconds=0.1)
    assert res["prediction_status"] == "INSUFFICIENT_HISTORY"

    # 2. Sufficient history (>= 5 states)
    history = [DigitalTwinState(timestamp_s=i * 0.1, snr_db=20.0 - 2.0 * i) for i in range(5)]
    res = predictor.predict_next_state(history, horizon_seconds=0.1)

    assert res["prediction_status"] == "SUCCESS"
    # Linear trend: SNR decreases by 2.0 dB per 0.1s -> next SNR at t=0.5s should be 10.0 dB
    assert np.isclose(res["next_snr_db"], 10.0, atol=1e-2)


def test_counterfactual_sandbox_isolation():
    """
    CRUCIAL SAFETY TEST: Verifies that evaluate_counterfactuals() does NOT leak state changes
    or advance the environment clock.
    """
    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env)

    env_state, _ = env.step(duration_seconds=0.1)
    dt.update(env_state)

    time_before = env.current_time_s

    # Run counterfactual simulation across 4 candidate strategies
    results = dt.evaluate_counterfactuals(candidate_strategies=["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"])

    assert len(results) == 4
    # Clock MUST remain completely unchanged
    assert env.current_time_s == time_before
    assert env.observe_state().timestamp_s == env_state.timestamp_s

    # Confirm candidate strategies produced valid predicted metrics
    strategies_evaluated = [r["strategy"] for r in results]
    assert "BPSK" in strategies_evaluated
    assert "OFDM-QPSK" in strategies_evaluated


def test_experience_memory():
    """
    Verifies experience storage and similarity search.
    """
    memory = ExperienceMemory()
    s1 = DigitalTwinState(snr_db=20.0, ber=0.0)
    s2 = DigitalTwinState(snr_db=5.0, ber=0.1)

    memory.store_experience(s1, threat="NOMINAL", strategy="QPSK", outcome_ber=0.0, outcome_throughput=200000.0)
    memory.store_experience(s2, threat="JAMMING", strategy="BPSK", outcome_ber=0.02, outcome_throughput=100000.0)

    target = DigitalTwinState(snr_db=4.0, ber=0.12)
    matches = memory.search_similar_experiences(target, top_k=1)

    assert len(matches) == 1
    assert matches[0]["strategy"] == "BPSK"  # Closer to s2


def test_twin_cloning():
    """
    Verifies deep copy cloning of DigitalTwin instance.
    """
    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env)
    env_state, _ = env.step(0.1)
    dt.update(env_state)

    cloned_dt = dt.clone()
    assert cloned_dt.state.snr_db == dt.state.snr_db

    # Mutate original, clone remains isolated
    dt.state.snr_db = 99.0
    assert cloned_dt.state.snr_db != 99.0
