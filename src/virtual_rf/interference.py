"""
Interference and Jamming Signal Generator.

Generates complex I/Q samples for narrowband tone jamming, broadband noise jamming, and swept-frequency chirp jamming.
"""

from typing import Optional
import numpy as np


class InterferenceGenerator:
    """
    Generates synthetic complex I/Q interference signals.
    """

    def __init__(self, sample_rate: float = 100000.0, seed: Optional[int] = 42):
        self.sample_rate = sample_rate
        self.rng = np.random.default_rng(seed)

    def generate_narrowband_tone(
        self,
        freq_offset_hz: float = 1000.0,
        power: float = 1.0,
        n_samples: int = 512,
        phase: float = 0.0,
    ) -> np.ndarray:
        """
        Generates complex single-tone CW narrowband interference at specified frequency offset.

        Args:
            freq_offset_hz: Offset frequency in Hz from baseband.
            power: Desired interference signal power.
            n_samples: Number of I/Q samples.
            phase: Initial phase shift.

        Returns:
            1D complex array of narrowband tone I/Q samples.
        """
        t = np.arange(n_samples) / self.sample_rate
        amp = np.sqrt(power)
        return amp * np.exp(1j * (2.0 * np.pi * freq_offset_hz * t + phase))

    def generate_broadband_noise(
        self,
        power: float = 1.0,
        n_samples: int = 512,
    ) -> np.ndarray:
        """
        Generates complex Gaussian white noise broadband jamming signal.

        Args:
            power: Desired total interference power.
            n_samples: Number of I/Q samples.

        Returns:
            1D complex array of broadband noise I/Q samples.
        """
        # Complex noise with variance = power
        noise = (self.rng.normal(0, 1, n_samples) + 1j * self.rng.normal(0, 1, n_samples)) / np.sqrt(2)
        return np.sqrt(power) * noise

    def generate_swept_jamming(
        self,
        start_freq_hz: float = -20000.0,
        end_freq_hz: float = 20000.0,
        sweep_rate_hz_per_sec: float = 100000.0,
        power: float = 1.0,
        n_samples: int = 512,
        t_start: float = 0.0,
    ) -> np.ndarray:
        """
        Generates linear swept-frequency chirp jamming signal.

        Args:
            start_freq_hz: Starting sweep frequency offset in Hz.
            end_freq_hz: Ending sweep frequency offset in Hz.
            sweep_rate_hz_per_sec: Linear frequency sweep rate in Hz/sec.
            power: Desired interference power.
            n_samples: Number of I/Q samples.
            t_start: Starting time index offset.

        Returns:
            1D complex array of swept chirp I/Q samples.
        """
        t = t_start + np.arange(n_samples) / self.sample_rate
        # Linear frequency chirp: f(t) = f0 + (k/2)*t -> phase phi(t) = 2*pi*(f0*t + 0.5*k*t^2)
        amp = np.sqrt(power)
        phase = 2.0 * np.pi * (start_freq_hz * t + 0.5 * sweep_rate_hz_per_sec * (t ** 2))
        return amp * np.exp(1j * phase)
