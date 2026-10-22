"""
Digital Twin State Dataclass.

Represents the internal state model maintained by the Cognitive Digital Twin (CDT).
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class DigitalTwinState:
    """
    Structured snapshot of the Cognitive Digital Twin state.
    """
    timestamp_s: float = 0.0
    modulation: str = "QPSK"
    snr_db: float = 20.0
    ber: float = 0.0
    interference_power: float = 0.0
    threat_condition: str = "NOMINAL"
    channel_type: str = "awgn"
    throughput_bps: float = 200000.0
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Converts dataclass state to dictionary."""
        return asdict(self)
