"""
Analog Modulation Base Class and Utilities.

Defines the standard abstract interface for analog modulators and demodulators.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import numpy as np


class AnalogModulator(ABC):
    """
    Abstract base class for all analog modulation and demodulation schemes.
    """

    @abstractmethod
    def modulate(
        self,
        message: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Modulates a message signal onto a carrier.

        Args:
            message: Baseband message signal 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            **kwargs: Additional scheme-specific parameters.

        Returns:
            Modulated passband signal 1D array.
        """
        pass

    @abstractmethod
    def demodulate(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Demodulates a passband signal back into baseband message.

        Args:
            signal: Modulated passband signal 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            **kwargs: Additional scheme-specific parameters.

        Returns:
            Recovered baseband message signal 1D array.
        """
        pass
