"""
Signal foundation module: generation, I/Q conversion, noise injection, FFT analysis, and FIR filtering.
"""

from .generator import (
    generate_sinusoid,
    generate_complex_sinusoid,
    to_iq,
    add_awgn,
)
from .analysis import (
    compute_fft,
    compute_psd,
    estimate_frequency,
    estimate_bandwidth,
    calculate_power,
    calculate_rms,
    calculate_snr,
    estimate_snr_blind,
)
from .filters import (
    design_fir_lowpass,
    design_fir_bandpass,
    apply_filter,
)

__all__ = [
    "generate_sinusoid",
    "generate_complex_sinusoid",
    "to_iq",
    "add_awgn",
    "compute_fft",
    "compute_psd",
    "estimate_frequency",
    "estimate_bandwidth",
    "calculate_power",
    "calculate_rms",
    "calculate_snr",
    "estimate_snr_blind",
    "design_fir_lowpass",
    "design_fir_bandpass",
    "apply_filter",
]
