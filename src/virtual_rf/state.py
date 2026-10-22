"""
Environment State Dataclass for Virtual RF System.

Represents a structured snapshot of environmental, physical, and network performance metrics at a discrete timestamp.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class EnvironmentState:
    """
    Structured snapshot of the Virtual RF Environment state at a given timestamp.
    """
    timestamp_s: float = 0.0
    modulation: str = "QPSK"
    snr_db: float = 20.0
    signal_power: float = 1.0
    interference_power: float = 0.0
    bandwidth_hz: float = 100000.0
    channel_type: str = "awgn"
    ber: float = 0.0
    packet_loss: float = 0.0
    throughput_bps: float = 200000.0
    latency_ms: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        """Converts dataclass state to dictionary."""
        return asdict(self)
