"""
2x2 MIMO-OFDM System & Spatial Multiplexing Equalization Engine.

Implements 2 TX x 2 RX spatial multiplexing and per-subcarrier Zero-Forcing (ZF) equalization.
"""

from typing import List, Optional, Tuple
import numpy as np

from src.signal.generator import add_awgn
from .ofdm import OFDMTransmitterReceiver
from .channel import MultipathChannel


class MIMO2x2System:
    """
    2x2 MIMO-OFDM Spatial Multiplexing Communication System.
    """

    def __init__(
        self,
        n_fft: int = 64,
        cp_len: int = 16,
        modulation_order: int = 4,
        channels: Optional[List[List[MultipathChannel]]] = None,
    ):
        """
        Args:
            n_fft: Number of subcarriers.
            cp_len: Cyclic Prefix length.
            modulation_order: Symbol constellation order M (default 4 for QPSK).
            channels: 2x2 grid of MultipathChannel instances [[h11, h12], [h21, h22]].
        """
        self.n_fft = n_fft
        self.cp_len = cp_len
        self.M = modulation_order
        self.ofdm = OFDMTransmitterReceiver(n_fft=n_fft, cp_len=cp_len, modulation_order=modulation_order)

        if channels is None:
            # Default 2x2 spatial channel paths
            h11 = MultipathChannel(taps=[1.0, 0.3 * np.exp(1j * np.pi / 6)], delays=[0, 2])
            h12 = MultipathChannel(taps=[0.5 * np.exp(1j * np.pi / 4), 0.2], delays=[0, 3])
            h21 = MultipathChannel(taps=[0.4 * np.exp(-1j * np.pi / 3), 0.2], delays=[0, 1])
            h22 = MultipathChannel(taps=[0.9, 0.4 * np.exp(1j * np.pi / 3)], delays=[0, 2])
            self.channels = [[h11, h12], [h21, h22]]
        else:
            self.channels = channels

    def get_channel_matrix_freq(self) -> np.ndarray:
        """
        Computes 2x2 frequency response matrix H[k] for each subcarrier k=0..n_fft-1.
        Shape: (n_fft, 2, 2) where H_freq[k] is [[H11[k], H12[k]], [H21[k], H22[k]]].
        """
        H11 = self.channels[0][0].get_frequency_response(self.n_fft)
        H12 = self.channels[0][1].get_frequency_response(self.n_fft)
        H21 = self.channels[1][0].get_frequency_response(self.n_fft)
        H22 = self.channels[1][1].get_frequency_response(self.n_fft)
        
        H_freq = np.zeros((self.n_fft, 2, 2), dtype=np.complex128)
        H_freq[:, 0, 0] = H11
        H_freq[:, 0, 1] = H12
        H_freq[:, 1, 0] = H21
        H_freq[:, 1, 1] = H22
        return H_freq

    def transmit_and_equalize(
        self,
        bits: np.ndarray,
        snr_db: Optional[float] = 15.0,
        equalizer: str = "ZF",
        seed: Optional[int] = 42,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Executes end-to-end 2x2 MIMO spatial multiplexing:
        1. Split bits into Stream 1 and Stream 2.
        2. OFDM modulate both streams.
        3. Pass through 2x2 spatial channel matrix + AWGN.
        4. Remove CP, compute FFT per RX antenna.
        5. Apply per-subcarrier 2x2 ZF matrix equalization.
        6. QPSK Demap and combine streams.

        Args:
            bits: 1D binary vector.
            snr_db: SNR in dB.
            equalizer: 'ZF' for Zero-Forcing.
            seed: Random seed.

        Returns:
            Tuple of (rx_bits, equalized_stream1_iq, equalized_stream2_iq).
        """
        b = np.asarray(bits, dtype=np.int8)

        # 1. Split bits evenly into Stream 1 and Stream 2
        half_len = len(b) // 2
        bits1 = b[:half_len]
        bits2 = b[half_len:]

        # 2. OFDM Modulate TX1 and TX2 streams
        tx1_wave, num_syms1 = self.ofdm.modulate(bits1)
        tx2_wave, num_syms2 = self.ofdm.modulate(bits2)
        num_syms = max(num_syms1, num_syms2)

        # Ensure equal length waveforms
        min_len = min(len(tx1_wave), len(tx2_wave))
        tx1_wave = tx1_wave[:min_len]
        tx2_wave = tx2_wave[:min_len]

        # 3. Channel Transmission (2 TX -> 2 RX)
        # rx1 = h11 * tx1 + h12 * tx2 + noise
        # rx2 = h21 * tx1 + h22 * tx2 + noise
        rx1_faded = self.channels[0][0].filter_signal(tx1_wave) + self.channels[0][1].filter_signal(tx2_wave)
        rx2_faded = self.channels[1][0].filter_signal(tx1_wave) + self.channels[1][1].filter_signal(tx2_wave)

        if snr_db is not None:
            rx1 = add_awgn(rx1_faded, snr_db=snr_db, seed=seed)
            # Use different seed for second antenna noise stream
            rx2 = add_awgn(rx2_faded, snr_db=snr_db, seed=seed + 1 if seed is not None else None)
        else:
            rx1, rx2 = rx1_faded, rx2_faded

        # 4. Receiver processing: CP removal + FFT
        sym_len = self.n_fft + self.cp_len
        rx1_blocks = rx1[: num_syms * sym_len].reshape(num_syms, sym_len)[:, self.cp_len :]
        rx2_blocks = rx2[: num_syms * sym_len].reshape(num_syms, sym_len)[:, self.cp_len :]

        Y1 = np.fft.fft(rx1_blocks, axis=1) / np.sqrt(self.n_fft)  # (num_syms, n_fft)
        Y2 = np.fft.fft(rx2_blocks, axis=1) / np.sqrt(self.n_fft)  # (num_syms, n_fft)

        # 5. Build 2x2 Channel Matrix per subcarrier H[k]
        H11 = self.channels[0][0].get_frequency_response(self.n_fft)
        H12 = self.channels[0][1].get_frequency_response(self.n_fft)
        H21 = self.channels[1][0].get_frequency_response(self.n_fft)
        H22 = self.channels[1][1].get_frequency_response(self.n_fft)

        # Equalized symbol matrices
        X1_hat = np.zeros((num_syms, self.n_fft), dtype=np.complex128)
        X2_hat = np.zeros((num_syms, self.n_fft), dtype=np.complex128)

        # Per-subcarrier 2x2 Matrix Inversion (Zero-Forcing)
        for k in range(self.n_fft):
            H_k = np.array([[H11[k], H12[k]], [H21[k], H22[k]]], dtype=np.complex128)
            det = H_k[0, 0] * H_k[1, 1] - H_k[0, 1] * H_k[1, 0]

            if np.abs(det) < 1e-12:
                W_zf = np.linalg.pinv(H_k)
            else:
                inv_det = 1.0 / det
                W_zf = inv_det * np.array([[H_k[1, 1], -H_k[0, 1]], [-H_k[1, 0], H_k[0, 0]]], dtype=np.complex128)

            # Received vector Y_k for all OFDM symbols: shape (2, num_syms)
            Y_k = np.vstack([Y1[:, k], Y2[:, k]])
            X_k_hat = np.dot(W_zf, Y_k)  # (2, num_syms)

            X1_hat[:, k] = X_k_hat[0, :]
            X2_hat[:, k] = X_k_hat[1, :]

        # 6. QPSK Demapping
        s1_iq = X1_hat.ravel()
        s2_iq = X2_hat.ravel()

        rx_bits1 = self.ofdm.modulator.demodulate_baseband(s1_iq)
        rx_bits2 = self.ofdm.modulator.demodulate_baseband(s2_iq)

        # Truncate to original transmitted length
        rx_bits1 = rx_bits1[:len(bits1)]
        rx_bits2 = rx_bits2[:len(bits2)]

        rx_bits = np.concatenate([rx_bits1, rx_bits2])
        return rx_bits, s1_iq, s2_iq
