"""
Unit tests for OFDM and 2x2 MIMO multicarrier module.
"""

import numpy as np
import pytest

from src.modulation.digital import generate_bits, calculate_ber
from src.multicarrier.ofdm import OFDMTransmitterReceiver
from src.multicarrier.mimo import MIMO2x2System
from src.multicarrier.channel import MultipathChannel
from src.multicarrier.common import simulate_ofdm_mimo


def test_ofdm_ifft_fft_roundtrip():
    """
    Tests clean OFDM IFFT -> FFT round-trip bit recovery (BER = 0) in ideal channel.
    """
    n_bits = 1280  # 10 OFDM symbols (128 bits per QPSK OFDM symbol)
    tx_bits = generate_bits(n_bits, seed=42)

    ofdm = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
    waveform, num_syms = ofdm.modulate(tx_bits)

    # Ideal channel (H[k] = 1.0)
    H_ideal = np.ones(64, dtype=np.complex128)
    rx_bits = ofdm.demodulate(waveform, num_ofdm_symbols=num_syms, channel_response=H_ideal, use_cp=True)

    assert len(rx_bits) == len(tx_bits)
    assert calculate_ber(tx_bits, rx_bits) == 0.0, "OFDM ideal roundtrip failed."


def test_cp_insertion_and_removal():
    """
    Verifies Cyclic Prefix (CP) insertion length and contents.
    """
    ofdm = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
    tx_bits = generate_bits(128, seed=42)

    waveform, num_syms = ofdm.modulate(tx_bits)
    # Total samples per OFDM symbol = 64 + 16 = 80
    assert len(waveform) == num_syms * 80

    # Verify first symbol CP matches last 16 samples of the 64-sample IFFT block
    symbol_block = waveform[:80]
    cp_part = symbol_block[:16]
    end_part = symbol_block[-16:]
    assert np.allclose(cp_part, end_part), "Cyclic Prefix content does not match tail of symbol."


def test_mimo_2x2_zf_recovery():
    """
    Tests 2x2 MIMO spatial multiplexing and Zero-Forcing stream recovery at high SNR (30 dB).
    """
    n_bits = 2560
    tx_bits = generate_bits(n_bits, seed=123)

    mimo = MIMO2x2System(n_fft=64, cp_len=16, modulation_order=4)
    rx_bits, s1_iq, s2_iq = mimo.transmit_and_equalize(tx_bits, snr_db=30.0, equalizer="ZF", seed=123)

    assert len(rx_bits) == len(tx_bits), "MIMO received bit vector length mismatch."

    ber = calculate_ber(tx_bits, rx_bits)
    assert ber == 0.0, f"2x2 MIMO ZF stream recovery failed at high SNR (BER = {ber})."


def test_simulate_ofdm_mimo_api():
    """
    Verifies research-ready simulate_ofdm_mimo API.
    """
    res = simulate_ofdm_mimo(modulation="QPSK", snr_db=15.0, channel_condition="multipath", equalizer="ZF", n_bits=2000, seed=42)

    assert "ber" in res
    assert "throughput" in res
    assert "spectral_efficiency" in res
    assert res["spectral_efficiency"] == 4.0
    assert res["ber"] >= 0.0
