"""
OFDM Transmitter & Receiver Engine.

Implements 64-subcarrier OFDM modulation with Cyclic Prefix (CP) insertion/removal,
subcarrier mapping, IFFT/FFT processing, 1-tap frequency-domain equalization, and QPSK demapping.
"""

from typing import Optional, Tuple
import numpy as np

from src.modulation.digital.psk import PSKModulator


class OFDMTransmitterReceiver:
    """
    Orthogonal Frequency Division Multiplexing (OFDM) Transceiver.
    """

    def __init__(
        self,
        n_fft: int = 64,
        cp_len: int = 16,
        modulation_order: int = 4,
    ):
        """
        Args:
            n_fft: Number of FFT subcarriers (default 64).
            cp_len: Cyclic Prefix length in samples (default 16).
            modulation_order: Symbol constellation order M (default 4 for QPSK).
        """
        self.n_fft = n_fft
        self.cp_len = cp_len
        self.M = modulation_order
        self.modulator = PSKModulator(M=self.M)
        self.k = self.modulator.k  # Bits per symbol

    def modulate(self, bits: np.ndarray) -> Tuple[np.ndarray, int]:
        """
        Modulates bits into OFDM time-domain waveform with Cyclic Prefix.

        Args:
            bits: 1D binary vector.

        Returns:
            Tuple of (time_domain_waveform, num_ofdm_symbols).
        """
        b = np.asarray(bits, dtype=np.int8)

        # Ensure bit length aligns with (k * n_fft)
        bits_per_ofdm_symbol = self.k * self.n_fft
        remainder = len(b) % bits_per_ofdm_symbol
        if remainder != 0:
            pad_len = bits_per_ofdm_symbol - remainder
            b = np.pad(b, (0, pad_len), mode="constant")

        num_ofdm_symbols = len(b) // bits_per_ofdm_symbol

        # 1. QPSK Map bits to complex symbols
        qpsk_symbols = self.modulator.modulate_baseband(b)

        # 2. Reshape into subcarrier matrix of shape (num_ofdm_symbols, n_fft)
        freq_grid = qpsk_symbols.reshape(num_ofdm_symbols, self.n_fft)

        # 3. IFFT transform subcarriers to time domain
        time_syms = np.fft.ifft(freq_grid, axis=1) * np.sqrt(self.n_fft)

        # 4. Insert Cyclic Prefix (prepend last cp_len samples)
        if self.cp_len > 0:
            cp = time_syms[:, -self.cp_len :]
            time_syms_cp = np.hstack([cp, time_syms])
        else:
            time_syms_cp = time_syms

        # Flatten to 1D transmit waveform
        tx_waveform = time_syms_cp.ravel()
        return tx_waveform, num_ofdm_symbols

    def demodulate(
        self,
        waveform: np.ndarray,
        num_ofdm_symbols: int,
        channel_response: Optional[np.ndarray] = None,
        use_cp: bool = True,
    ) -> np.ndarray:
        """
        Demodulates OFDM time-domain waveform back into bits.

        Args:
            waveform: Received 1D time-domain waveform.
            num_ofdm_symbols: Expected number of OFDM symbols.
            channel_response: Frequency response H[k] of length n_fft for 1-tap equalization.
            use_cp: Whether CP was included in the received waveform.

        Returns:
            1D binary vector.
        """
        w = np.asarray(waveform, dtype=np.complex128)
        cp_l = self.cp_len if use_cp else 0
        sym_len = self.n_fft + cp_l

        total_expected = num_ofdm_symbols * sym_len
        w = w[:total_expected]

        # 1. Reshape into 2D blocks
        blocks = w.reshape(num_ofdm_symbols, sym_len)

        # 2. Remove Cyclic Prefix
        if cp_l > 0:
            blocks_no_cp = blocks[:, cp_l:]
        else:
            blocks_no_cp = blocks

        # 3. FFT transform to frequency domain subcarriers
        freq_grid_rx = np.fft.fft(blocks_no_cp, axis=1) / np.sqrt(self.n_fft)

        # 4. 1-tap Frequency Domain Equalization if channel response H[k] provided
        if channel_response is not None:
            H = np.asarray(channel_response, dtype=np.complex128)
            # Avoid division by zero
            H_safe = np.where(H == 0, 1e-12, H)
            freq_grid_equalized = freq_grid_rx / H_safe[np.newaxis, :]
        else:
            freq_grid_equalized = freq_grid_rx

        # Flatten subcarriers to 1D complex symbol vector
        rx_qpsk_symbols = freq_grid_equalized.ravel()

        # 5. QPSK Demap symbols back to bits
        rx_bits = self.modulator.demodulate_baseband(rx_qpsk_symbols)
        return rx_bits
