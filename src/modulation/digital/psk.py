"""
Phase Shift Keying (PSK) Module.

Combines BPSK (M=2), QPSK (M=4), 8-PSK (M=8), and 16-PSK (M=16) with explicitly defined
In-Phase (I) and Quadrature (Q) components and Gray coding symbol mapping.
"""

from typing import Dict, Tuple
import numpy as np

from .common import binary_to_gray, gray_to_binary


class PSKModulator:
    """
    M-ary Phase Shift Keying Modulator and Demodulator (supports M=2, 4, 8, 16).
    """

    def __init__(self, M: int = 4):
        """
        Args:
            M: Constellation order (2 for BPSK, 4 for QPSK, 8 for 8-PSK, 16 for 16-PSK).
        """
        if M not in (2, 4, 8, 16):
            raise ValueError(f"Unsupported M={M}. Must be 2, 4, 8, or 16.")

        self.M = M
        self.k = int(np.log2(M))  # Bits per symbol

        # Phase offset for QPSK is pi/4 for standard diagonal constellation
        self.phase_offset = np.pi / self.M if self.M == 4 else 0.0

        # Build Constellation Table (I and Q components)
        self.constellation_iq = np.zeros(self.M, dtype=np.complex128)
        self.constellation_phases = np.zeros(self.M, dtype=np.float64)

        for m in range(self.M):
            phi = 2.0 * np.pi * m / self.M + self.phase_offset
            self.constellation_phases[m] = phi
            I_comp = np.cos(phi)
            Q_comp = np.sin(phi)
            self.constellation_iq[m] = I_comp + 1j * Q_comp

    def modulate_baseband(self, bits: np.ndarray) -> np.ndarray:
        """
        Modulates input bit vector into complex baseband I/Q symbols using Gray coding.

        Args:
            bits: 1D binary array (length must be multiple of k=log2(M)).

        Returns:
            1D complex NumPy array of baseband symbols (I + j*Q).
        """
        b = np.asarray(bits, dtype=np.int8)
        if len(b) % self.k != 0:
            raise ValueError(f"Bit vector length ({len(b)}) must be a multiple of k={self.k} bits/symbol.")

        num_symbols = len(b) // self.k
        symbols_iq = np.zeros(num_symbols, dtype=np.complex128)

        # Reshape bits into (num_symbols, k)
        bit_blocks = b.reshape(num_symbols, self.k)

        # Powers of 2 array for bit unpacking: [2^(k-1), 2^(k-2), ..., 1]
        powers = 1 << np.arange(self.k - 1, -1, -1)

        # Convert bit blocks to Gray integers g
        gray_indices = np.dot(bit_blocks, powers)

        # Convert Gray indices to binary symbol indices m
        for i in range(num_symbols):
            g = int(gray_indices[i])
            m = gray_to_binary(g)
            symbols_iq[i] = self.constellation_iq[m]

        return symbols_iq

    def demodulate_baseband(self, iq_symbols: np.ndarray) -> np.ndarray:
        """
        Demodulates received complex baseband I/Q symbols into bits using Gray decoding.

        Args:
            iq_symbols: 1D complex array of received I/Q symbols.

        Returns:
            1D binary NumPy array (np.int8).
        """
        syms = np.asarray(iq_symbols, dtype=np.complex128)
        num_symbols = len(syms)
        recovered_bits = np.zeros((num_symbols, self.k), dtype=np.int8)

        # Compute Euclidean distance to all M constellation points for minimum distance decision
        # Distance matrix shape: (num_symbols, M)
        diffs = syms[:, np.newaxis] - self.constellation_iq[np.newaxis, :]
        distances = np.abs(diffs)

        # Nearest symbol indices m
        best_m = np.argmin(distances, axis=1)

        for i in range(num_symbols):
            m = int(best_m[i])
            g = binary_to_gray(m)

            # Convert Gray integer g to k binary bits
            for j in range(self.k):
                recovered_bits[i, j] = (g >> (self.k - 1 - j)) & 1

        return recovered_bits.ravel()

    def modulate_passband(
        self,
        bits: np.ndarray,
        carrier_freq: float,
        samples_per_symbol: int,
        sample_rate: float,
    ) -> np.ndarray:
        """
        Modulates bits into passband carrier waveform: s(t) = I(t)*cos(2*pi*f_c*t) - Q(t)*sin(2*pi*f_c*t).

        Args:
            bits: 1D binary array.
            carrier_freq: Carrier frequency in Hz.
            samples_per_symbol: Samples per symbol.
            sample_rate: Sampling frequency in Hz.

        Returns:
            1D float array of passband signal.
        """
        iq_symbols = self.modulate_baseband(bits)
        num_symbols = len(iq_symbols)
        total_samples = num_symbols * samples_per_symbol
        t = np.arange(total_samples) / sample_rate

        I_wave = np.repeat(iq_symbols.real, samples_per_symbol)
        Q_wave = np.repeat(iq_symbols.imag, samples_per_symbol)

        carrier_cos = np.cos(2.0 * np.pi * carrier_freq * t)
        carrier_sin = np.sin(2.0 * np.pi * carrier_freq * t)

        return I_wave * carrier_cos - Q_wave * carrier_sin

    def demodulate_passband(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        samples_per_symbol: int,
        sample_rate: float,
    ) -> np.ndarray:
        """
        Demodulates passband PSK signal using quadrature coherent matched filtering.

        Args:
            signal: 1D passband signal.
            carrier_freq: Carrier frequency in Hz.
            samples_per_symbol: Samples per symbol.
            sample_rate: Sampling rate in Hz.

        Returns:
            1D binary array.
        """
        s = np.asarray(signal, dtype=np.float64)
        total_samples = len(s)
        t = np.arange(total_samples) / sample_rate

        carrier_cos = np.cos(2.0 * np.pi * carrier_freq * t)
        carrier_sin = np.sin(2.0 * np.pi * carrier_freq * t)

        product_i = s * carrier_cos * 2.0
        product_q = -s * carrier_sin * 2.0

        num_symbols = total_samples // samples_per_symbol
        i_reshaped = product_i[: num_symbols * samples_per_symbol].reshape(num_symbols, samples_per_symbol)
        q_reshaped = product_q[: num_symbols * samples_per_symbol].reshape(num_symbols, samples_per_symbol)

        i_symbols = np.mean(i_reshaped, axis=1)
        q_symbols = np.mean(q_reshaped, axis=1)

        demod_iq = i_symbols + 1j * q_symbols
        return self.demodulate_baseband(demod_iq)
