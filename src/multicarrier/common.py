"""
Multicarrier Simulation Common Utilities and Research-Ready API.

Provides simulate_ofdm_mimo function for candidate strategy evaluation by future Digital Twin engines.
"""

from typing import Any, Dict, Optional
import numpy as np

from src.modulation.digital import generate_bits, calculate_ber
from .ofdm import OFDMTransmitterReceiver
from .mimo import MIMO2x2System
from .channel import MultipathChannel


def simulate_ofdm_mimo(
    modulation: str = "QPSK",
    snr_db: float = 10.0,
    channel_condition: str = "multipath",
    equalizer: str = "ZF",
    n_bits: int = 20000,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Research-Ready API for future Digital Twin strategy selection.

    Simulates 2x2 MIMO-OFDM communication system under specified channel and equalization settings.

    Args:
        modulation: Symbol modulation scheme ('QPSK').
        snr_db: Signal-to-Noise Ratio in dB.
        channel_condition: Channel model ('awgn' or 'multipath').
        equalizer: Equalization algorithm ('ZF').
        n_bits: Number of bits to simulate.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary containing {'ber': float, 'throughput': float, 'spectral_efficiency': float, 'snr_db': float}.
    """
    if n_bits <= 0:
        raise ValueError("n_bits must be positive.")

    # Ensure n_bits is even for 2x2 spatial multiplexing split
    if n_bits % 2 != 0:
        n_bits += 1

    tx_bits = generate_bits(n_bits, seed=seed)

    if channel_condition.lower() == "awgn":
        # AWGN channel matrix: 2x2 identity matrix (direct uncoupled links)
        h_direct = MultipathChannel(taps=[1.0], delays=[0])
        h_zero = MultipathChannel(taps=[0.0], delays=[0])
        channels = [[h_direct, h_zero], [h_zero, h_direct]]
    else:
        # Frequency-selective multipath channel grid
        channels = None

    mimo_system = MIMO2x2System(n_fft=64, cp_len=16, modulation_order=4, channels=channels)
    rx_bits, _, _ = mimo_system.transmit_and_equalize(
        tx_bits,
        snr_db=snr_db,
        equalizer=equalizer,
        seed=seed,
    )

    ber = calculate_ber(tx_bits, rx_bits)

    # 2x2 Spatial Multiplexing QPSK gives spectral efficiency = 2 (streams) * 2 (bits/symbol) = 4 bits/sec/Hz
    spectral_eff = 4.0
    throughput = (1.0 - ber) * spectral_eff * 1e6  # Estimated throughput in bps/MHz

    return {
        "ber": ber,
        "throughput": float(throughput),
        "spectral_efficiency": spectral_eff,
        "snr_db": float(snr_db),
        "channel_condition": channel_condition,
        "equalizer": equalizer,
    }
