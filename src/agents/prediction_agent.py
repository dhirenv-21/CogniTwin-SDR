"""
Prediction Agent Module.

Uses Digital Twin trend forecasting to compute risk scores (0.0 to 1.0) and risk levels (LOW, MEDIUM, HIGH, CRITICAL).
"""

from typing import Dict, Any
import numpy as np

from src.digital_twin.twin import DigitalTwin
from .base_agent import BaseAgent
from .messages import PredictionResult


class PredictionAgent(BaseAgent):
    """
    Specialized agent for short-horizon degradation prediction and threat risk scoring.
    """

    def __init__(self):
        super().__init__(name="PredictionAgent")

    def process(self, digital_twin: DigitalTwin, horizon_seconds: float = 0.1) -> PredictionResult:
        """
        Queries Digital Twin trend predictor and calculates risk scores.

        Args:
            digital_twin: DigitalTwin instance mirroring environment state.
            horizon_seconds: Short-horizon prediction step.

        Returns:
            PredictionResult dataclass.
        """
        self.status = "PREDICTING_TRENDS"

        trend = digital_twin.predict_next(horizon_seconds=horizon_seconds)
        status_str = trend.get("prediction_status", "INSUFFICIENT_HISTORY")

        if status_str == "INSUFFICIENT_HISTORY":
            result = PredictionResult(
                predicted_timestamp_s=digital_twin.state.timestamp_s + horizon_seconds,
                next_snr_db=digital_twin.state.snr_db,
                next_ber=digital_twin.state.ber,
                next_interference_power=digital_twin.state.interference_power,
                risk_score=0.0,
                risk_level="LOW",
                prediction_status="INSUFFICIENT_HISTORY",
            )
            self._last_output = result
            self.status = "IDLE"
            return result

        pred_t = trend["predicted_timestamp_s"]
        next_snr = trend["next_snr_db"]
        next_ber = trend["next_ber"]
        next_interf = trend["next_interference_power"]

        # Risk Scoring Math
        ber_term = float(np.clip(next_ber / 0.1, 0.0, 1.0))
        snr_term = float(np.clip((20.0 - next_snr) / 20.0, 0.0, 1.0))
        interf_term = float(np.clip(next_interf / 2.0, 0.0, 1.0))

        raw_risk = 0.5 * ber_term + 0.3 * snr_term + 0.2 * interf_term
        risk_score = float(np.clip(raw_risk, 0.0, 1.0))

        if risk_score < 0.25:
            risk_level = "LOW"
        elif risk_score < 0.50:
            risk_level = "MEDIUM"
        elif risk_score < 0.75:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"

        self.confidence = 0.90 if status_str == "SUCCESS" else 0.50

        result = PredictionResult(
            predicted_timestamp_s=pred_t,
            next_snr_db=next_snr,
            next_ber=next_ber,
            next_interference_power=next_interf,
            risk_score=risk_score,
            risk_level=risk_level,
            prediction_status=status_str,
        )

        self._last_output = result
        self.status = "IDLE"
        return result
