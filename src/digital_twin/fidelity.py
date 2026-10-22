"""
Fidelity Evaluator Module.

Calculates Mean Absolute Error (MAE) between Digital Twin predictions and environment ground truth.
"""

from typing import Dict, List
import numpy as np


class FidelityEvaluator:
    """
    Evaluates prediction fidelity of the Cognitive Digital Twin against environment ground truth.
    """

    def __init__(self):
        self.predicted_snrs: List[float] = []
        self.actual_snrs: List[float] = []
        self.predicted_bers: List[float] = []
        self.actual_bers: List[float] = []

    def record_step(
        self, pred_snr: float, actual_snr: float, pred_ber: float, actual_ber: float
    ):
        """Records a prediction-actual pair for fidelity tracking."""
        self.predicted_snrs.append(pred_snr)
        self.actual_snrs.append(actual_snr)
        self.predicted_bers.append(pred_ber)
        self.actual_bers.append(actual_ber)

    def compute_mae(self) -> Dict[str, float]:
        """
        Computes Mean Absolute Error (MAE) for SNR and BER predictions.
        """
        if not self.predicted_snrs:
            return {"mae_snr_db": 0.0, "mae_ber": 0.0}

        mae_snr = float(np.mean(np.abs(np.array(self.predicted_snrs) - np.array(self.actual_snrs))))
        mae_ber = float(np.mean(np.abs(np.array(self.predicted_bers) - np.array(self.actual_bers))))

        return {"mae_snr_db": mae_snr, "mae_ber": mae_ber}

    def reset(self):
        """Resets recorded fidelity tracking data."""
        self.predicted_snrs.clear()
        self.actual_snrs.clear()
        self.predicted_bers.clear()
        self.actual_bers.clear()
