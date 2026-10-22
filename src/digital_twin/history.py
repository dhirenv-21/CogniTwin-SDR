"""
History Buffer Module for Cognitive Digital Twin.

Maintains a bounded chronological window of Digital Twin states and calculates rates of change.
"""

from collections import deque
from typing import List, Optional
import numpy as np

from .state import DigitalTwinState


class HistoryBuffer:
    """
    Bounded FIFO chronological history buffer for DigitalTwinState instances.
    """

    def __init__(self, max_len: int = 50):
        self.max_len = max_len
        self.buffer = deque(maxlen=max_len)

    def append(self, state: DigitalTwinState):
        """Appends a new state to the chronological buffer."""
        self.buffer.append(state)

    def get_history(self) -> List[DigitalTwinState]:
        """Returns chronological list of stored states."""
        return list(self.buffer)

    def clear(self):
        """Clears stored history."""
        self.buffer.clear()

    def __len__(self) -> int:
        return len(self.buffer)

    def calculate_rate_of_change(self, metric_name: str = "snr_db") -> float:
        """
        Calculates instantaneous rate of change d(metric)/dt using the last two states.

        Returns:
            Rate of change in metric/sec, or 0.0 if history is too short.
        """
        if len(self.buffer) < 2:
            return 0.0

        s_prev = self.buffer[-2]
        s_curr = self.buffer[-1]
        dt = s_curr.timestamp_s - s_prev.timestamp_s

        if dt <= 0:
            return 0.0

        v_prev = getattr(s_prev, metric_name, 0.0)
        v_curr = getattr(s_curr, metric_name, 0.0)
        return float((v_curr - v_prev) / dt)
