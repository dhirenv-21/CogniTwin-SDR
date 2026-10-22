"""
Signal Generator Module.

Provides clean, modular, vectorized NumPy/SciPy functions for sinusoid generation,
complex I/Q representation, and AWGN noise injection with fixed-seed support.
"""

from typing import Optional, Tuple
import numpy as np
from scipy.signal import hilbert


def generate_sinusoid(
    freq: float,
    sampling_rate: float,
    duration: float,
    amplitude: float = 1.0,
    phase: float = 0.0,
    dc_offset: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates a real-valued sinusoidal signal.

    Args:
        freq: Frequency of the sinusoid in Hz.
        sampling_rate: Sampling frequency in Hz.
        duration: Duration of the signal in seconds.
        amplitude: Peak amplitude of the sinusoid.
        phase: Initial phase offset in radians.
        dc_offset: DC offset added to the signal.

    Returns:
        Tuple of (time_axis, signal_array).
    """
    if sampling_rate <= 0:
        raise ValueError("Sampling rate must be positive.")
    if duration <= 0:
        raise ValueError("Duration must be positive.")

    num_samples = int(round(sampling_rate * duration))
    t = np.arange(num_samples) / sampling_rate
    signal = amplitude * np.cos(2.0 * np.pi * freq * t + phase) + dc_offset
    return t, signal


def generate_complex_sinusoid(
    freq: float,
    sampling_rate: float,
    duration: float,
    amplitude: float = 1.0,
    phase: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates a complex exponential sinusoid s(t) = A * exp(j*(2*pi*f*t + phase)).

    Args:
        freq: Frequency of the complex exponential in Hz.
        sampling_rate: Sampling frequency in Hz.
        duration: Duration of the signal in seconds.
        amplitude: Peak amplitude.
        phase: Initial phase offset in radians.

    Returns:
        Tuple of (time_axis, complex_signal_array).
    """
    if sampling_rate <= 0:
        raise ValueError("Sampling rate must be positive.")
    if duration <= 0:
        raise ValueError("Duration must be positive.")

    num_samples = int(round(sampling_rate * duration))
    t = np.arange(num_samples) / sampling_rate
    complex_signal = amplitude * np.exp(1j * (2.0 * np.pi * freq * t + phase))
    return t, complex_signal


def to_iq(real_signal: np.ndarray, method: str = "hilbert") -> np.ndarray:
    """
    Converts a real-valued signal into a complex I/Q representation (analytic signal).

    Args:
        real_signal: Real-valued 1D signal array.
        method: Method for I/Q conversion ('hilbert' or 'quadrature').

    Returns:
        Complex 1D NumPy array representing I + j*Q.
    """
    signal = np.asarray(real_signal, dtype=np.float64)
    if method == "hilbert":
        # Returns analytic signal x_a(t) = x(t) + j * H{x(t)}
        return hilbert(signal)
    elif method == "quadrature":
        # Hilbert transform gives standard orthogonal quadrature component
        h_sig = hilbert(signal)
        return h_sig
    else:
        raise ValueError(f"Unsupported method '{method}'. Use 'hilbert' or 'quadrature'.")


def add_awgn(
    signal: np.ndarray,
    snr_db: float,
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    Injects Additive White Gaussian Noise (AWGN) into a real or complex signal
    for a target Signal-to-Noise Ratio (SNR) in dB.

    Args:
        signal: Input 1D array (real or complex).
        snr_db: Target SNR in decibels.
        seed: Random seed for reproducible noise generation.

    Returns:
        Noisy signal array of the same shape and complex/real dtype as input.
    """
    rng = np.random.default_rng(seed)
    signal_arr = np.asarray(signal)

    # Compute average signal power P_s = (1/N) * sum(|s|^2)
    p_signal = np.mean(np.abs(signal_arr) ** 2)

    if p_signal == 0:
        return signal_arr.copy()

    # Calculate required noise power P_n = P_s / (10^(SNR_dB / 10))
    snr_linear = 10.0 ** (snr_db / 10.0)
    p_noise = p_signal / snr_linear

    if np.iscomplexobj(signal_arr):
        # Noise power divided equally between I and Q channels
        std_iq = np.sqrt(p_noise / 2.0)
        noise_real = rng.normal(0.0, std_iq, size=signal_arr.shape)
        noise_imag = rng.normal(0.0, std_iq, size=signal_arr.shape)
        noise = noise_real + 1j * noise_imag
    else:
        std_dev = np.sqrt(p_noise)
        noise = rng.normal(0.0, std_dev, size=signal_arr.shape)

    return signal_arr + noise
