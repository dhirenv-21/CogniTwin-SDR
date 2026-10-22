"""
Multi-Agent Orchestrator Module.

Coordinates execution pipeline across SpectrumAgent, DigitalTwin, PredictionAgent, and CyberDefenseAgent,
producing unified MultiAgentSnapshot evidence objects.
"""

from typing import Optional, Dict, Any, Tuple
import numpy as np

from src.virtual_rf.environment import VirtualRFEnvironment
from src.virtual_rf.state import EnvironmentState
from src.digital_twin.twin import DigitalTwin
from .spectrum_agent import SpectrumAgent
from .prediction_agent import PredictionAgent
from .cyber_defense_agent import CyberDefenseAgent
from .messages import MultiAgentSnapshot, SpectrumIntelligenceResult, PredictionResult, DefenseCandidate


class MultiAgentOrchestrator:
    """
    Orchestrates step execution across specialized wireless intelligence agents.
    """

    def __init__(
        self,
        environment: Optional[VirtualRFEnvironment] = None,
        digital_twin: Optional[DigitalTwin] = None,
        sample_rate: float = 100000.0,
    ):
        self.env = environment if environment is not None else VirtualRFEnvironment(sample_rate=sample_rate)
        self.digital_twin = digital_twin if digital_twin is not None else DigitalTwin(environment=self.env)

        self.spectrum_agent = SpectrumAgent(sample_rate=sample_rate)
        self.prediction_agent = PredictionAgent()
        self.cyber_defense_agent = CyberDefenseAgent()

    def step(self, duration_seconds: float = 0.1) -> Tuple[MultiAgentSnapshot, EnvironmentState, np.ndarray]:
        """
        Executes multi-agent pipeline for a discrete simulation step.

        Pipeline Steps:
        1. Environment advances clock and generates I/Q buffer & true state.
        2. SpectrumAgent analyzes I/Q -> SpectrumIntelligenceResult.
        3. DigitalTwin updates state history based on environment & SpectrumAgent findings.
        4. PredictionAgent forecasts short-horizon trends & computes Risk Score.
        5. CyberDefenseAgent evaluates evidence & proposes Candidate Strategies.
        6. Constructs and returns MultiAgentSnapshot.

        Returns:
            Tuple of (MultiAgentSnapshot, EnvironmentState, iq_samples).
        """
        # Step 1: Environment Step
        env_state, iq_samples = self.env.step(duration_seconds=duration_seconds)
        t_curr = self.env.current_time_s

        # Step 2: Spectrum Intelligence Agent
        spectrum_res = self.spectrum_agent.process(
            iq_samples=iq_samples,
            timestamp_s=t_curr,
            env_interference_power=env_state.interference_power,
        )

        # Step 3: Digital Twin Update
        dt_ai_input = {
            "predicted_modulation": spectrum_res.modulation,
            "confidence": spectrum_res.classifier_confidence,
            "snr_db": spectrum_res.snr_db,
        }
        dt_state = self.digital_twin.update(env_state, ai_result=dt_ai_input)

        # Step 4: Prediction Agent
        prediction_res = self.prediction_agent.process(
            digital_twin=self.digital_twin,
            horizon_seconds=duration_seconds,
        )

        # Step 5: Cyber Defense Agent
        defense_candidates = self.cyber_defense_agent.process(
            spectrum_res=spectrum_res,
            prediction_res=prediction_res,
            dt_state=dt_state,
        )

        # Step 6: MultiAgentSnapshot
        snapshot = MultiAgentSnapshot(
            timestamp_s=t_curr,
            spectrum_result=spectrum_res,
            prediction_result=prediction_res,
            defense_candidates=defense_candidates,
        )

        return snapshot, env_state, iq_samples
