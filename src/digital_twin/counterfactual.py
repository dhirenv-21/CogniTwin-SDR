"""
Counterfactual Sandbox Simulation Module.

Evaluates candidate communication strategies in an isolated sandbox without advancing environment clock.
"""

from typing import Any, Dict, List, Optional
from src.virtual_rf.environment import VirtualRFEnvironment
from src.virtual_rf.state import EnvironmentState
from .state import DigitalTwinState


class CounterfactualSandbox:
    """
    Stateless sandbox for counterfactual strategy evaluation.
    """

    def __init__(self, environment: Optional[VirtualRFEnvironment] = None):
        self.env = environment if environment is not None else VirtualRFEnvironment()

    def simulate_counterfactuals(
        self,
        dt_state: DigitalTwinState,
        candidate_strategies: List[str] = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"],
    ) -> List[Dict[str, Any]]:
        """
        Evaluates candidate communication strategies counterfactually.

        Args:
            dt_state: Current DigitalTwinState snapshot.
            candidate_strategies: List of modulation scheme names or strategy strings.

        Returns:
            List of dictionary results for each candidate strategy.
        """
        # Convert DT state to VirtualRF EnvironmentState
        env_state = EnvironmentState(
            timestamp_s=dt_state.timestamp_s,
            modulation=dt_state.modulation,
            snr_db=dt_state.snr_db,
            interference_power=dt_state.interference_power,
            channel_type=dt_state.channel_type,
            ber=dt_state.ber,
            throughput_bps=dt_state.throughput_bps,
        )

        results = []
        for strat in candidate_strategies:
            mod_name = dt_state.modulation if strat == "Keep Current" else strat
            strategy_dict = {"modulation": mod_name, "snr_db": dt_state.snr_db}

            # Stateless simulation call (NO clock advance)
            pred_env_state = self.env.simulate(env_state, strategy_dict)

            results.append(
                {
                    "strategy": strat,
                    "modulation": mod_name,
                    "predicted_ber": pred_env_state.ber,
                    "predicted_packet_loss": pred_env_state.packet_loss,
                    "predicted_throughput_bps": pred_env_state.throughput_bps,
                    "predicted_latency_ms": pred_env_state.latency_ms,
                }
            )

        return results
