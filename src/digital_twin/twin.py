"""
Main Cognitive Digital Twin (CDT) Class.

Mirrors Virtual RF Environment, tracks state history, predicts degradation, supports counterfactual sandbox simulation,
stores experience memory, and exposes cloning.
"""

import copy
import math
from typing import Any, Dict, List, Optional

from src.virtual_rf.state import EnvironmentState
from src.virtual_rf.environment import VirtualRFEnvironment
from .state import DigitalTwinState
from .history import HistoryBuffer
from .predictor import TrendPredictor
from .counterfactual import CounterfactualSandbox
from .experience import ExperienceMemory
from .fidelity import FidelityEvaluator


class DigitalTwin:
    """
    Cognitive Digital Twin (CDT) core engine.
    """

    def __init__(
        self,
        environment: Optional[VirtualRFEnvironment] = None,
        max_history_len: int = 50,
        history_window: int = 5,
    ):
        self.env = environment if environment is not None else VirtualRFEnvironment()
        self.state = DigitalTwinState()
        self.history = HistoryBuffer(max_len=max_history_len)
        self.predictor = TrendPredictor(history_window=history_window)
        self.sandbox = CounterfactualSandbox(environment=self.env)
        self.experience = ExperienceMemory()
        self.fidelity = FidelityEvaluator()

    def update(
        self,
        env_state: EnvironmentState,
        ai_result: Optional[Dict[str, Any]] = None,
    ) -> DigitalTwinState:
        """
        Updates the Digital Twin state mirroring the Virtual RF Environment.

        Args:
            env_state: EnvironmentState dataclass from VirtualRFEnvironment.
            ai_result: Optional dict from Task 5 ML analyze_iq().

        Returns:
            Updated DigitalTwinState snapshot.
        """
        # Reject non-finite inputs at the source. Before this check a NaN SNR or an
        # Inf BER flowed through the linear predictor into the Prediction Agent as
        # risk_score = NaN, which its banding reports as 'CRITICAL' with
        # prediction_status 'SUCCESS' - a plausible-looking alarm from invalid data.
        for name in ("timestamp_s", "snr_db", "ber", "interference_power", "throughput_bps"):
            value = getattr(env_state, name, 0.0)
            if not math.isfinite(float(value)):
                raise ValueError(f"DigitalTwin.update: env_state.{name} is not finite ({value})")

        mod_type = env_state.modulation
        conf = 1.0

        if ai_result is not None:
            pred_mod = ai_result.get("predicted_modulation", "UNKNOWN")
            conf = float(ai_result.get("confidence", 1.0))
            if pred_mod != "UNKNOWN":
                mod_type = pred_mod

        # Determine threat condition heuristic
        if env_state.interference_power > 2.0:
            threat = "BROADBAND_JAMMING"
        elif env_state.interference_power > 0.1:
            threat = "NARROWBAND_JAMMING"
        elif env_state.channel_type in ["rayleigh", "rician"]:
            threat = "FADING"
        else:
            threat = "NOMINAL"

        self.state = DigitalTwinState(
            timestamp_s=env_state.timestamp_s,
            modulation=mod_type,
            snr_db=env_state.snr_db,
            ber=env_state.ber,
            interference_power=env_state.interference_power,
            threat_condition=threat,
            channel_type=env_state.channel_type,
            throughput_bps=env_state.throughput_bps,
            confidence=conf,
        )

        self.history.append(self.state)
        return self.state

    def get_rate_of_snr_change(self) -> float:
        """Calculates instantaneous d(SNR)/dt in dB/sec."""
        return self.history.calculate_rate_of_change("snr_db")

    def predict_next(self, horizon_seconds: float = 0.1) -> Dict[str, Any]:
        """Predicts short-horizon environmental trend metrics."""
        return self.predictor.predict_next_state(
            self.history.get_history(), horizon_seconds=horizon_seconds
        )

    def evaluate_counterfactuals(
        self, candidate_strategies: List[str] = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"]
    ) -> List[Dict[str, Any]]:
        """
        Evaluates candidate strategies in stateless counterfactual sandbox (NO clock advance).
        """
        return self.sandbox.simulate_counterfactuals(self.state, candidate_strategies)

    def clone(self) -> "DigitalTwin":
        """Creates an independent deep copy of the DigitalTwin instance."""
        return copy.deepcopy(self)
