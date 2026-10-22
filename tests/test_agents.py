"""
Unit tests for Multi-Agent Cognitive Wireless Intelligence Layer.
"""

import pytest
import numpy as np

from src.virtual_rf.environment import VirtualRFEnvironment
from src.digital_twin.twin import DigitalTwin
from src.agents.spectrum_agent import SpectrumAgent
from src.agents.prediction_agent import PredictionAgent
from src.agents.cyber_defense_agent import CyberDefenseAgent
from src.agents.orchestrator import MultiAgentOrchestrator
from src.agents.messages import (
    SpectrumIntelligenceResult,
    PredictionResult,
    DefenseCandidate,
    MultiAgentSnapshot,
)


def test_spectrum_agent():
    """
    Verifies SpectrumAgent I/Q processing and anomaly flagging.
    """
    agent = SpectrumAgent(sample_rate=100000.0)

    # Generate synthetic complex I/Q signal
    t = np.linspace(0, 0.005, 512)
    iq = np.cos(2 * np.pi * 10000 * t) + 1j * np.sin(2 * np.pi * 10000 * t)

    res = agent.process(iq_samples=iq, timestamp_s=0.5, env_interference_power=0.0)

    assert isinstance(res, SpectrumIntelligenceResult)
    assert res.timestamp_s == 0.5
    assert res.anomaly_flag in ["NONE", "SNR_DROP", "HIGH_INTERFERENCE"]
    assert res.classifier_confidence >= 0.0


def test_prediction_agent_risk_scoring():
    """
    Verifies PredictionAgent risk score calculation and risk level categorization.
    """
    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env)
    pred_agent = PredictionAgent()

    # Step environment 6 times to provide sufficient history for predictor
    for _ in range(6):
        env_state, _ = env.step(0.1)
        dt.update(env_state)

    res = pred_agent.process(digital_twin=dt, horizon_seconds=0.1)

    assert isinstance(res, PredictionResult)
    assert 0.0 <= res.risk_score <= 1.0
    assert res.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert res.prediction_status == "SUCCESS"


def test_cyber_defense_agent_candidates():
    """
    Verifies CyberDefenseAgent candidate strategy generation matches Task 7 sandbox names.
    """
    agent = CyberDefenseAgent()

    spec_res = SpectrumIntelligenceResult(snr_db=20.0, anomaly_flag="NONE")
    pred_res = PredictionResult(risk_score=0.1, risk_level="LOW")
    dt_state = dt = DigitalTwinState = None

    def_res = agent.process(spec_res, pred_res, dt_state)

    assert isinstance(def_res, DefenseCandidate)
    assert "Keep Current" in def_res.candidate_strategies

    # Test high risk trigger
    pred_res_high = PredictionResult(risk_score=0.8, risk_level="CRITICAL")
    def_res_high = agent.process(spec_res, pred_res_high, dt_state)

    assert "BPSK" in def_res_high.candidate_strategies
    assert "OFDM-QPSK" in def_res_high.candidate_strategies


def test_multi_agent_orchestrator_pipeline():
    """
    Verifies MultiAgentOrchestrator end-to-end multi-agent execution pipeline.
    """
    orchestrator = MultiAgentOrchestrator(sample_rate=100000.0)

    # Execute 3 steps
    for step_i in range(3):
        snapshot, env_state, iq = orchestrator.step(duration_seconds=0.1)

        assert isinstance(snapshot, MultiAgentSnapshot)
        assert snapshot.spectrum_result is not None
        assert snapshot.prediction_result is not None
        assert snapshot.defense_candidates is not None
        assert len(iq) == 10000
