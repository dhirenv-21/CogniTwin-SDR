"""
Digital Modulation Common Utilities and Strategy Simulation API.

Provides bit generation, BER computation, Gray coding conversions, and research-ready strategy simulation API.
"""

from typing import Any, Dict, Optional
import numpy as np


def generate_bits(n_bits: int, seed: Optional[int] = None) -> np.ndarray:
    """
    Generates a pseudo-random binary sequence of 0s and 1s.

    Args:
        n_bits: Number of bits to generate.
        seed: Random seed for reproducibility.

    Returns:
        1D NumPy array of binary values (0 or 1) with dtype np.int8.
    """
    if n_bits <= 0:
        raise ValueError("n_bits must be positive.")
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2, size=n_bits, dtype=np.int8)


def calculate_ber(bits_tx: np.ndarray, bits_rx: np.ndarray) -> float:
    """
    Calculates Bit Error Rate (BER) between transmitted and received bit vectors.

    Args:
        bits_tx: Transmitted binary array.
        bits_rx: Received binary array.

    Returns:
        Bit Error Rate as a float in range [0.0, 1.0].
    """
    tx = np.asarray(bits_tx, dtype=np.int8)
    rx = np.asarray(bits_rx, dtype=np.int8)
    if len(tx) != len(rx):
        raise ValueError(f"Length mismatch: bits_tx ({len(tx)}) vs bits_rx ({len(rx)})")
    if len(tx) == 0:
        return 0.0
    bit_errors = np.sum(tx != rx)
    return float(bit_errors / len(tx))


def binary_to_gray(n: int) -> int:
    """
    Converts a binary integer to its Gray code equivalent.
    """
    return n ^ (n >> 1)


def gray_to_binary(g: int) -> int:
    """
    Converts a Gray code integer back to binary.
    """
    b = g
    mask = g >> 1
    while mask != 0:
        b ^= mask
        mask >>= 1
    return b


def simulate_strategy(
    modulation: str = "QPSK",
    snr_db: float = 8.0,
    channel: str = "AWGN",
    n_bits: int = 100000,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Research-Ready API for future Digital Twin strategy selection.

    Simulates specified digital modulation scheme over AWGN channel and computes BER
    and spectral efficiency.

    Args:
        modulation: Scheme name ('ASK', 'FSK', 'BPSK', 'QPSK', '8PSK', '16PSK').
        snr_db: Channel SNR in dB.
        channel: Channel model name (default 'AWGN').
        n_bits: Number of bits for simulation.
        seed: Random seed for bit and noise generation.

    Returns:
        Dictionary containing {'ber': float, 'spectral_efficiency': float, 'modulation': str, 'snr_db': float}.
    """
    from src.channel.awgn import apply_awgn
    from .ask import ASKModulator
    from .fsk import FSKModulator
    from .psk import PSKModulator

    mod_upper = modulation.upper()

    # Map spectral efficiencies (bits/sec/Hz)
    spectral_efficiencies = {
        "ASK": 1.0,
        "FSK": 1.0,
        "BPSK": 1.0,
        "QPSK": 2.0,
        "4PSK": 2.0,
        "8PSK": 3.0,
        "16PSK": 4.0,
    }

    eta = spectral_efficiencies.get(mod_upper, 1.0)

    # Adjust n_bits to align with symbol size k = log2(M)
    k = int(eta)
    if n_bits % k != 0:
        n_bits = (n_bits // k) * k

    tx_bits = generate_bits(n_bits, seed=seed)

    if mod_upper == "ASK":
        mod = ASKModulator()
        symbols = mod.modulate_baseband(tx_bits)
        noisy_symbols = apply_awgn(symbols, snr_db=snr_db, seed=seed)
        rx_bits = mod.demodulate_baseband(noisy_symbols)

    elif mod_upper == "FSK":
        mod = FSKModulator()
        symbols = mod.modulate_baseband(tx_bits)
        noisy_symbols = apply_awgn(symbols, snr_db=snr_db, seed=seed)
        rx_bits = mod.demodulate_baseband(noisy_symbols)

    elif mod_upper in ("BPSK", "QPSK", "4PSK", "8PSK", "16PSK"):
        M = 2 if mod_upper == "BPSK" else (4 if mod_upper in ("QPSK", "4PSK") else (8 if mod_upper == "8PSK" else 16))
        mod = PSKModulator(M=M)
        symbols = mod.modulate_baseband(tx_bits)
        noisy_symbols = apply_awgn(symbols, snr_db=snr_db, seed=seed)
        rx_bits = mod.demodulate_baseband(noisy_symbols)
    else:
        raise ValueError(f"Unsupported modulation strategy '{modulation}'.")

    ber = calculate_ber(tx_bits, rx_bits)

    return {
        "ber": ber,
        "spectral_efficiency": eta,
        "modulation": mod_upper,
        "snr_db": float(snr_db),
        "channel": channel,
    }
