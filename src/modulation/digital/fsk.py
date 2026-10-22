"""
Frequency Shift Keying (FSK) Module.

Supports binary FSK (2-FSK) complex baseband representation and passband carrier waveforms
with coherent and non-coherent envelope detection.
"""

from typing import Tuple
import numpy as np


class FSKModulator:
    """
    Binary Frequency Shift Keying (2-FSK) Modulator and Demodulator.
    """

    def __init__(self, f0: float = 5000.0, f1: float = 10000.0):
        """
        Args:
            f0: Frequency for bit 0 in Hz.
            f1: Frequency for bit 1 in Hz.
        """
        self.f0 = f0
        self.f1 = f1

    def modulate_baseband(self, bits: np.ndarray) -> np.ndarray:
        """
        Modulates bits into orthogonal complex baseband I/Q symbols.

        Bit 0 maps to 1.0 + 0.0j (Channel 0).
        Bit 1 maps to 0.0 + 1.0j (Channel 1).

        Args:
            bits: 1D binary array (0s and 1s).

        Returns:
            1D complex array of baseband symbols.
        """
        b = np.asarray(bits, dtype=np.int8)
        symbols = np.where(b == 1, 0.0 + 1.0j, 1.0 + 0.0j)
        return symbols.astype(np.complex128)

    def demodulate_baseband(self, iq_symbols: np.ndarray) -> np.ndarray:
        """
        Demodulates complex baseband symbols back into bits.

        Args:
            iq_symbols: 1D complex array of received symbols.

        Returns:
            1D binary array.
        """
        syms = np.asarray(iq_symbols)
        # Compare real power vs imag power (Channel 0 vs Channel 1)
        bits = np.where(np.abs(syms.imag) > np.abs(syms.real), 1, 0)
        return bits.astype(np.int8)

    def modulate_passband(
        self,
        bits: np.ndarray,
        samples_per_symbol: int,
        sample_rate: float,
        carrier_freq: float = 0.0,  # Unused if f0 and f1 specified
    ) -> np.ndarray:
        """
        Modulates bits into passband 2-FSK waveform using f0 and f1.

        Args:
            bits: 1D binary array.
            samples_per_symbol: Number of samples per symbol interval.
            sample_rate: Sampling frequency in Hz.

        Returns:
            1D float array of passband FSK signal.
        """
        b = np.asarray(bits, dtype=np.int8)
        num_bits = len(b)
        total_samples = num_bits * samples_per_symbol
        t = np.arange(total_samples) / sample_rate

        # Assign frequency per sample
        freqs_per_sample = np.repeat(np.where(b == 1, self.f1, self.f0), samples_per_symbol)
        phase = 2.0 * np.pi * freqs_per_sample * t
        return np.cos(phase)

    def demodulate_passband(
        self,
        signal: np.ndarray,
        samples_per_symbol: int,
        sample_rate: float,
        carrier_freq: float = 0.0,
    ) -> np.ndarray:
        """
        Demodulates passband FSK signal using non-coherent envelope detection at f0 and f1.

        Args:
            signal: 1D passband signal array.
            samples_per_symbol: Samples per symbol.
            sample_rate: Sampling rate in Hz.

        Returns:
            1D binary array.
        """
        s = np.asarray(signal, dtype=np.float64)
        num_bits = len(s) // samples_per_symbol
        recovered_bits = np.zeros(num_bits, dtype=np.int8)

        t_sym = np.arange(samples_per_symbol) / sample_rate

        cos_f0 = np.cos(2.0 * np.pi * self.f0 * t_sym)
        sin_f0 = np.sin(2.0 * np.pi * self.f0 * t_sym)

        cos_f1 = np.cos(2.0 * np.pi * self.f1 * t_sym)
        sin_f1 = np.sin(2.0 * np.pi * self.f1 * t_sym)

        for i in range(num_bits):
            sym_slice = s[i * samples_per_symbol : (i + 1) * samples_per_symbol]

            # Non-coherent envelope detection for f0
            i0 = np.sum(sym_slice * cos_f0)
            q0 = np.sum(sym_slice * sin_f0)
            e0 = i0 ** 2 + q0 ** 2

            # Non-coherent envelope detection for f1
            i1 = np.sum(sym_slice * cos_f1)
            q1 = np.sum(sym_slice * sin_f1)
            e1 = i1 ** 2 + q1 ** 2

            recovered_bits[i] = 1 if e1 > e0 else 0

        return recovered_bits
