"""
Experience Memory Module V1.

Stores historical transition records and retrieves closest matching prior experiences using Euclidean distance.
"""

from typing import Any, Dict, List, Optional
import numpy as np

from .state import DigitalTwinState


class ExperienceMemory:
    """
    Experience Memory database storing past environmental transitions and outcome metrics.
    """

    def __init__(self):
        self.records: List[Dict[str, Any]] = []

    def store_experience(
        self,
        initial_state: DigitalTwinState,
        threat: str,
        strategy: str,
        outcome_ber: float,
        outcome_throughput: float,
    ):
        """Stores an experience transition record."""
        record = {
            "snr_db": initial_state.snr_db,
            "ber": initial_state.ber,
            "threat": threat,
            "strategy": strategy,
            "outcome_ber": outcome_ber,
            "outcome_throughput": outcome_throughput,
        }
        self.records.append(record)

    def search_similar_experiences(
        self, target_state: DigitalTwinState, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top_k nearest past experiences using normalized Euclidean distance on (SNR, BER).
        """
        if not self.records:
            return []

        target_vec = np.array([target_state.snr_db / 30.0, target_state.ber], dtype=np.float64)

        distances = []
        for rec in self.records:
            rec_vec = np.array([rec["snr_db"] / 30.0, rec["ber"]], dtype=np.float64)
            dist = float(np.linalg.norm(target_vec - rec_vec))
            distances.append((dist, rec))

        distances.sort(key=lambda x: x[0])
        return [rec for _, rec in distances[:top_k]]

    def __len__(self) -> int:
        return len(self.records)
