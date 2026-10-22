"""
Multicarrier & Wireless Channel Models.

Provides Multipath Fading channel modeling with configurable delay taps and complex gains.
"""

from typing import List, Optional, Tuple
import numpy as np
from src.signal.generator import add_awgn


class MultipathChannel:
    """
    Multipath Fading Channel with configurable impulse response delay taps and complex gains.
    """

    def __init__(
        self,
        taps: Optional[List[complex]] = None,
        delays: Optional[List[int]] = None,
    ):
        """
        Args:
            taps: Complex gains for each tap (default 3-tap multipath).
            delays: Integer sample delays for each tap.
        """
        if taps is None:
            # Default 3-tap frequency-selective channel
            self.taps = [1.0 + 0.0j, 0.4 * np.exp(1j * np.pi / 4), 0.2 * np.exp(-1j * np.pi / 3)]
        else:
            self.taps = [complex(t) for t in taps]

        if delays is None:
            self.delays = [0, 2, 5]
        else:
            self.delays = list(delays)

        if len(self.taps) != len(self.delays):
            raise ValueError("Length of taps must match length of delays.")

        # Construct time-domain impulse response array h[n]
        max_delay = max(self.delays)
        self.h = np.zeros(max_delay + 1, dtype=np.complex128)
        for tap, delay in zip(self.taps, self.delays):
            self.h[delay] += tap

        # Normalize total power to 1.0
        power = np.sum(np.abs(self.h) ** 2)
        if power > 0:
            self.h /= np.sqrt(power)

    def get_impulse_response(self) -> np.ndarray:
        """
        Returns time-domain channel impulse response h[n].
        """
        return self.h.copy()

    def get_frequency_response(self, n_fft: int) -> np.ndarray:
        """
        Returns frequency-domain channel response H[k] over n_fft subcarriers.
        """
        return np.fft.fft(self.h, n=n_fft)

    def filter_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        Applies multipath channel impulse response convolution to input signal.

        Args:
            signal: 1D complex or real time-domain array.

        Returns:
            Filtered 1D array of same length as input.
        """
        sig = np.asarray(signal, dtype=np.complex128)
        conv_out = np.convolve(sig, self.h)
        return conv_out[: len(sig)]

    def transmit(self, signal: np.ndarray, snr_db: Optional[float] = None, seed: Optional[int] = None) -> np.ndarray:
        """
        Transmits signal through multipath fading channel and optional AWGN noise.

        Args:
            signal: Transmitted signal array.
            snr_db: Optional SNR in dB for AWGN noise.
            seed: Optional random seed for noise.

        Returns:
            Received noisy faded signal array.
        """
        faded = self.filter_signal(signal)
        if snr_db is not None:
            return add_awgn(faded, snr_db=snr_db, seed=seed)
        return faded
