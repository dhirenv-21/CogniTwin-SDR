"""
Cyber Defense Agent Module.

Generates candidate cyber-defense strategies based on observations, threat predictions, and risk levels.
"""

from typing import List
from src.digital_twin.state import DigitalTwinState
from .base_agent import BaseAgent
from .messages import SpectrumIntelligenceResult, PredictionResult, DefenseCandidate


class CyberDefenseAgent(BaseAgent):
    """
    Specialized agent for cyber-defense strategy candidate generation.
    """

    def __init__(self):
        super().__init__(name="CyberDefenseAgent")

    def process(
        self,
        spectrum_res: SpectrumIntelligenceResult,
        prediction_res: PredictionResult,
        dt_state: DigitalTwinState,
    ) -> DefenseCandidate:
        """
        Evaluates evidence messages and outputs candidate defense strategies.

        Args:
            spectrum_res: SpectrumIntelligenceResult from SpectrumAgent.
            prediction_res: PredictionResult from PredictionAgent.
            dt_state: Current DigitalTwinState snapshot.

        Returns:
            DefenseCandidate dataclass.
        """
        self.status = "FORMULATING_DEFENSE"

        risk_level = prediction_res.risk_level
        anomaly = spectrum_res.anomaly_flag

        if risk_level == "LOW" and anomaly == "NONE":
            candidates = ["Keep Current"]
            rationale = "Link operating nominally under clear RF conditions."
        elif risk_level == "MEDIUM" and anomaly == "NONE":
            candidates = ["Keep Current", "QPSK"]
            rationale = "Moderate RF degradation predicted; recommending QPSK assessment."
        else:  # HIGH, CRITICAL, or Anomaly flagged
            candidates = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"]
            rationale = f"Elevated threat detected (Risk: {risk_level}, Anomaly: {anomaly}); recommending robust candidate mitigation suite."

        self.confidence = 0.95

        result = DefenseCandidate(
            candidate_strategies=candidates,
            rationale=rationale,
            risk_level=risk_level,
        )

        self._last_output = result
        self.status = "IDLE"
        return result
