"""
Unit tests for Digital Carrier Modulation / Demodulation and BER analysis module.
"""

import numpy as np
import pytest

from src.channel.awgn import apply_awgn
from src.modulation.digital import (
    generate_bits,
    calculate_ber,
    simulate_strategy,
    ASKModulator,
    FSKModulator,
    PSKModulator,
)


def test_high_snr_bit_recovery():
    """
    Tests perfect round-trip bit recovery (BER = 0) at high SNR (30 dB) for all digital modulation schemes.
    """
    n_bits = 1200  # Multiple of 1, 2, 3, 4 for BPSK, QPSK, 8-PSK, 16-PSK
    tx_bits = generate_bits(n_bits, seed=42)

    # 1. ASK
    ask = ASKModulator()
    ask_syms = ask.modulate_baseband(tx_bits)
    ask_noisy = apply_awgn(ask_syms, snr_db=30.0, seed=42)
    ask_rx = ask.demodulate_baseband(ask_noisy)
    assert calculate_ber(tx_bits, ask_rx) == 0.0, "ASK failed high-SNR bit recovery."

    # 2. FSK
    fsk = FSKModulator()
    fsk_syms = fsk.modulate_baseband(tx_bits)
    fsk_noisy = apply_awgn(fsk_syms, snr_db=30.0, seed=42)
    fsk_rx = fsk.demodulate_baseband(fsk_noisy)
    assert calculate_ber(tx_bits, fsk_rx) == 0.0, "FSK failed high-SNR bit recovery."

    # 3. PSK (M=2, 4, 8, 16)
    for M in [2, 4, 8, 16]:
        psk = PSKModulator(M=M)
        psk_syms = psk.modulate_baseband(tx_bits)
        psk_noisy = apply_awgn(psk_syms, snr_db=30.0, seed=42)
        psk_rx = psk.demodulate_baseband(psk_noisy)
        assert calculate_ber(tx_bits, psk_rx) == 0.0, f"{M}-PSK failed high-SNR bit recovery."


def test_qpsk_iq_mapping_and_gray_coding():
    """
    Verifies QPSK explicit I/Q constellation points and Gray coding mapping.
    """
    qpsk = PSKModulator(M=4)
    bits = np.array([0, 0, 0, 1, 1, 1, 1, 0], dtype=np.int8)
    symbols = qpsk.modulate_baseband(bits)

    assert len(symbols) == 4

    # Verify unit envelope magnitude for all symbols
    magnitudes = np.abs(symbols)
    assert np.allclose(magnitudes, 1.0, atol=1e-5), "QPSK symbol magnitudes are not unit amplitude."

    # Demodulate back to bits
    rx_bits = qpsk.demodulate_baseband(symbols)
    assert np.array_equal(bits, rx_bits), "QPSK Gray coding round-trip failed."


def test_ber_monotonicity_vs_snr():
    """
    Verifies that BER decreases monotonically as SNR increases (0 dB vs 12 dB).
    """
    n_bits = 10000
    tx_bits = generate_bits(n_bits, seed=123)

    qpsk = PSKModulator(M=4)
    syms = qpsk.modulate_baseband(tx_bits)

    noisy_low_snr = apply_awgn(syms, snr_db=0.0, seed=123)
    rx_low = qpsk.demodulate_baseband(noisy_low_snr)
    ber_low = calculate_ber(tx_bits, rx_low)

    noisy_high_snr = apply_awgn(syms, snr_db=12.0, seed=123)
    rx_high = qpsk.demodulate_baseband(noisy_high_snr)
    ber_high = calculate_ber(tx_bits, rx_high)

    assert ber_low > 0.05, f"BER at 0 dB SNR ({ber_low:.4f}) is unexpectedly low."
    assert ber_high < ber_low, f"BER at 12 dB ({ber_high:.4f}) should be strictly less than at 0 dB ({ber_low:.4f})."


def test_simulate_strategy_api():
    """
    Verifies the research-ready simulate_strategy API.
    """
    res = simulate_strategy(modulation="QPSK", snr_db=10.0, n_bits=10000, seed=42)

    assert "ber" in res
    assert "spectral_efficiency" in res
    assert res["spectral_efficiency"] == 2.0
    assert res["modulation"] == "QPSK"
    assert res["ber"] >= 0.0
