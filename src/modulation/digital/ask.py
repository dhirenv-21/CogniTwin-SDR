"""
Amplitude Shift Keying (ASK) Module.

Supports binary ASK (OOK) complex baseband (I/Q symbols) and passband carrier waveforms.
"""

from typing import Tuple
import numpy as np


class ASKModulator:
    """
    Binary Amplitude Shift Keying (2-ASK / OOK) Modulator and Demodulator.
    """

    def __init__(self, amplitude0: float = 0.0, amplitude1: float = 1.0):
        self.a0 = amplitude0
        self.a1 = amplitude1
        self.threshold = (self.a0 + self.a1) / 2.0

    def modulate_baseband(self, bits: np.ndarray) -> np.ndarray:
        """
        Modulates bits into complex baseband I/Q symbols.

        Args:
            bits: 1D binary array (0s and 1s).

        Returns:
            1D complex array of baseband symbols (I + j*0).
        """
        b = np.asarray(bits, dtype=np.int8)
        symbols_real = np.where(b == 1, self.a1, self.a0)
        return symbols_real.astype(np.complex128)

    def demodulate_baseband(self, iq_symbols: np.ndarray) -> np.ndarray:
        """
        Demodulates complex baseband I/Q symbols into bits.

        Args:
            iq_symbols: 1D complex array of received symbols.

        Returns:
            1D binary NumPy array (np.int8).
        """
        syms = np.asarray(iq_symbols)
        # Decision boundary based on real component I
        bits = np.where(syms.real >= self.threshold, 1, 0)
        return bits.astype(np.int8)

    def modulate_passband(
        self,
        bits: np.ndarray,
        carrier_freq: float,
        samples_per_symbol: int,
        sample_rate: float,
    ) -> np.ndarray:
        """
        Modulates bits into a passband carrier waveform.

        Args:
            bits: 1D binary array.
            carrier_freq: Carrier frequency in Hz.
            samples_per_symbol: Number of samples per bit symbol.
            sample_rate: Sampling frequency in Hz.

        Returns:
            1D float array of passband signal.
        """
        b = np.asarray(bits, dtype=np.int8)
        num_bits = len(b)
        total_samples = num_bits * samples_per_symbol
        t = np.arange(total_samples) / sample_rate

        # Repeat bit amplitudes across symbol duration
        bit_amps = np.repeat(np.where(b == 1, self.a1, self.a0), samples_per_symbol)
        carrier = np.cos(2.0 * np.pi * carrier_freq * t)
        return bit_amps * carrier

    def demodulate_passband(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        samples_per_symbol: int,
        sample_rate: float,
    ) -> np.ndarray:
        """
        Demodulates passband ASK signal back into bits via coherent correlation.

        Args:
            signal: 1D passband signal array.
            carrier_freq: Carrier frequency in Hz.
            samples_per_symbol: Number of samples per bit symbol.
            sample_rate: Sampling frequency in Hz.

        Returns:
            1D binary array.
        """
        s = np.asarray(signal, dtype=np.float64)
        total_samples = len(s)
        t = np.arange(total_samples) / sample_rate

        local_carrier = np.cos(2.0 * np.pi * carrier_freq * t)
        product = s * local_carrier

        # Integrate energy per symbol interval
        num_bits = total_samples // samples_per_symbol
        product_reshaped = product[: num_bits * samples_per_symbol].reshape(num_bits, samples_per_symbol)
        symbol_energy = np.mean(product_reshaped, axis=1) * 2.0  # Factor 2 for cos^2 integration

        bits = np.where(symbol_energy >= self.threshold, 1, 0)
        return bits.astype(np.int8)
