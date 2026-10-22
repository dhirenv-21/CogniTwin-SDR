"""
Short-Horizon Trend Predictor Module.

Extrapolates future environmental metrics (SNR, BER, Interference) using degree-1 linear regression.
"""

from typing import Any, Dict, List
import numpy as np

from .state import DigitalTwinState


class TrendPredictor:
    """
    Lightweight short-horizon trend predictor using degree-1 linear extrapolation.
    """

    def __init__(self, history_window: int = 5):
        self.history_window = history_window

    def predict_next_state(
        self, history: List[DigitalTwinState], horizon_seconds: float = 0.1
    ) -> Dict[str, Any]:
        """
        Forecasts environmental metrics at t_next = t_current + horizon_seconds.

        Args:
            history: List of recent DigitalTwinState instances.
            horizon_seconds: Time horizon into the future.

        Returns:
            Dictionary containing predicted metrics or INSUFFICIENT_HISTORY status.
        """
        if len(history) < self.history_window:
            return {
                "prediction_status": "INSUFFICIENT_HISTORY",
                "next_snr_db": None,
                "next_ber": None,
                "next_interference_power": None,
            }

        recent_states = history[-self.history_window :]
        t = np.array([s.timestamp_s for s in recent_states], dtype=np.float64)
        snrs = np.array([s.snr_db for s in recent_states], dtype=np.float64)
        bers = np.array([s.ber for s in recent_states], dtype=np.float64)
        interf = np.array([s.interference_power for s in recent_states], dtype=np.float64)

        # Horizon is measured from the NEWEST observation. With t[-1] a late-arriving
        # older state would push the forecast time into the past. The degree-1 fit
        # itself does not depend on the order of the points.
        t_next = float(np.max(t)) + horizon_seconds

        # Degree-1 linear extrapolation with zero-variance safety
        if np.std(t) < 1e-9:
            next_snr = float(snrs[-1])
            next_ber = float(bers[-1])
            next_interf = float(interf[-1])
        else:
            p_snr = np.polyfit(t, snrs, 1)
            p_ber = np.polyfit(t, bers, 1)
            p_interf = np.polyfit(t, interf, 1)

            next_snr = float(np.polyval(p_snr, t_next))
            next_ber = float(np.clip(np.polyval(p_ber, t_next), 0.0, 0.5))
            next_interf = float(max(0.0, np.polyval(p_interf, t_next)))

        return {
            "prediction_status": "SUCCESS",
            "predicted_timestamp_s": t_next,
            "next_snr_db": next_snr,
            "next_ber": next_ber,
            "next_interference_power": next_interf,
        }
