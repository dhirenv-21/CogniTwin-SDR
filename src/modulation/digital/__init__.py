"""
Digital Modulation & Demodulation Package.

Provides classes and helper functions for ASK, FSK, BPSK, QPSK, and M-PSK schemes.
"""

from .common import generate_bits, calculate_ber, binary_to_gray, gray_to_binary, simulate_strategy
from .ask import ASKModulator
from .fsk import FSKModulator
from .psk import PSKModulator

__all__ = [
    "generate_bits",
    "calculate_ber",
    "binary_to_gray",
    "gray_to_binary",
    "simulate_strategy",
    "ASKModulator",
    "FSKModulator",
    "PSKModulator",
]
