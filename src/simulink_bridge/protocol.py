"""
Simulink Measurement Protocol Module.

Defines strongly typed SimulinkMeasurement dataclass schema for MATLAB-exported physical-layer measurements.
"""

from dataclasses import dataclass, field
import numpy as np
from typing import Dict, Any, Optional


@dataclass
class SimulinkMeasurement:
    """
    Strongly typed container holding physical-layer measurements exported from MATLAB/Simulink.
    """
    iq_samples: np.ndarray
    snr_db: float
    ber: float
    modulation: str
    interference_power: float = 0.0
    channel_type: str = "AWGN"
    timestamp: float = 0.0

    # --- Task 11 additive fields (all optional; defaults preserve the original API) ---
    # sample_rate : Fs reported by the MATLAB/Simulink export (Hz). 0.0 = not reported.
    # time_vector : Simulink logged time vector, same length as iq_samples.
    # tx_iq       : transmitted reference I/Q (enables measured SNR / EVM in Python).
    # source      : provenance label, e.g. "simulink" / "matlab-script" / "python-fixture".
    # extras      : any additional MAT variables carried through untouched.
    sample_rate: float = 0.0
    time_vector: Optional[np.ndarray] = None
    tx_iq: Optional[np.ndarray] = None
    source: str = "unknown"
    extras: Dict[str, Any] = field(default_factory=dict)
    # provenance: one of the validation.PROVENANCE_* kinds, derived from the MAT
    # header (who wrote the file) AND the source label. Only "simulink_export" is a
    # real Simulink run; "source" alone is a self-declared label.
    provenance: str = "unknown"

    def __post_init__(self):
        """
        Validates data schema and enforces strict typing rules.
        """
        if not isinstance(self.iq_samples, np.ndarray):
            self.iq_samples = np.array(self.iq_samples, dtype=np.complex128)
        else:
            self.iq_samples = self.iq_samples.astype(np.complex128).flatten()

        if len(self.iq_samples) == 0:
            raise ValueError("SimulinkMeasurement iq_samples vector cannot be empty.")

        self.snr_db = float(self.snr_db)
        self.ber = float(self.ber)
        self.interference_power = float(self.interference_power)
        self.timestamp = float(self.timestamp)
        self.modulation = str(self.modulation).strip()
        self.channel_type = str(self.channel_type).strip()

        self.sample_rate = float(self.sample_rate)
        self.source = str(self.source).strip()
        self.provenance = str(self.provenance).strip()

        if self.time_vector is not None:
            self.time_vector = np.asarray(self.time_vector, dtype=np.float64).flatten()
            if self.time_vector.size == 0:
                self.time_vector = None

        if self.tx_iq is not None:
            self.tx_iq = np.asarray(self.tx_iq, dtype=np.complex128).flatten()
            if self.tx_iq.size == 0:
                self.tx_iq = None

    @property
    def num_samples(self) -> int:
        """Number of received complex I/Q samples."""
        return int(self.iq_samples.size)

    @property
    def measured_power(self) -> float:
        """Mean measured power of the received I/Q vector."""
        return float(np.mean(np.abs(self.iq_samples) ** 2))

    @property
    def duration_s(self) -> float:
        """Signal duration in seconds derived from sample_rate (0.0 if Fs unknown)."""
        if self.sample_rate > 0:
            return float(self.num_samples / self.sample_rate)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converts metadata to dictionary format."""
        return {
            "num_iq_samples": len(self.iq_samples),
            "snr_db": self.snr_db,
            "ber": self.ber,
            "modulation": self.modulation,
            "interference_power": self.interference_power,
            "channel_type": self.channel_type,
            "timestamp": self.timestamp,
            "sample_rate": self.sample_rate,
            "source": self.source,
            "provenance": self.provenance,
            "has_time_vector": self.time_vector is not None,
            "has_tx_reference": self.tx_iq is not None,
        }
