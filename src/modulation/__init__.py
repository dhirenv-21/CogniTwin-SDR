"""
Modulation package for CogniTwin-SDR (Analog and Digital).
"""

from .analog import (
    AnalogModulator,
    AMDSBSCModulator,
    AMDSTCModulator,
    SSBModulator,
    FMModulator,
    PMModulator,
)
from .digital import (
    generate_bits,
    calculate_ber,
    binary_to_gray,
    gray_to_binary,
    simulate_strategy,
    ASKModulator,
    FSKModulator,
    PSKModulator,
)

__all__ = [
    "AnalogModulator",
    "AMDSBSCModulator",
    "AMDSTCModulator",
    "SSBModulator",
    "FMModulator",
    "PMModulator",
    "generate_bits",
    "calculate_ber",
    "binary_to_gray",
    "gray_to_binary",
    "simulate_strategy",
    "ASKModulator",
    "FSKModulator",
    "PSKModulator",
]
