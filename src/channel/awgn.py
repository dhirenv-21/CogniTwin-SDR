"""
AWGN Channel Module.

Wraps noise injection functions from src.signal for channel simulation.
"""

from typing import Optional
import numpy as np
from src.signal.generator import add_awgn


class AWGNChannel:
    """
    Simulates an Additive White Gaussian Noise (AWGN) channel.
    """

    def __init__(self, snr_db: float, seed: Optional[int] = None):
        """
        Args:
            snr_db: Channel Signal-to-Noise Ratio in dB.
            seed: Random seed for reproducible noise generation.
        """
        self.snr_db = snr_db
        self.seed = seed

    def transmit(self, signal: np.ndarray) -> np.ndarray:
        """
        Transmits a signal through the AWGN channel.

        Args:
            signal: Transmitted signal array.

        Returns:
            Noisy received signal array.
        """
        return add_awgn(signal, snr_db=self.snr_db, seed=self.seed)


def apply_awgn(signal: np.ndarray, snr_db: float, seed: Optional[int] = None) -> np.ndarray:
    """
    Functional wrapper for AWGN channel transmission.

    Args:
        signal: Input 1D signal.
        snr_db: SNR in dB.
        seed: Optional random seed.

    Returns:
        Noisy signal.
    """
    return add_awgn(signal, snr_db=snr_db, seed=seed)
