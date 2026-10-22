"""
FIR Filter Module.

Provides SciPy-based FIR Low-pass and Band-pass filter design functions and
zero-phase / standard filtering.
"""

import numpy as np
from scipy.signal import firwin, filtfilt, lfilter


def design_fir_lowpass(
    cutoff_freq: float,
    sampling_rate: float,
    numtaps: int = 101,
    window: str = "hamming",
) -> np.ndarray:
    """
    Designs an FIR Low-pass filter using windowed time-domain design (scipy.signal.firwin).

    Args:
        cutoff_freq: Cutoff frequency (-6dB point) in Hz.
        sampling_rate: Sampling frequency in Hz.
        numtaps: Number of filter taps (filter order + 1). Must be odd for type-1 FIR.
        window: Window type (e.g., 'hamming', 'hann', 'blackman').

    Returns:
        1D array of FIR filter coefficients b.
    """
    nyquist = sampling_rate / 2.0
    if cutoff_freq <= 0 or cutoff_freq >= nyquist:
        raise ValueError(f"Cutoff frequency must be in range (0, Nyquist={nyquist} Hz).")

    # Ensure odd number of taps for symmetric FIR
    if numtaps % 2 == 0:
        numtaps += 1

    coefficients = firwin(
        numtaps=numtaps,
        cutoff=cutoff_freq,
        fs=sampling_rate,
        pass_zero="lowpass",
        window=window,
    )
    return coefficients


def design_fir_bandpass(
    low_cutoff: float,
    high_cutoff: float,
    sampling_rate: float,
    numtaps: int = 101,
    window: str = "hamming",
) -> np.ndarray:
    """
    Designs an FIR Band-pass filter using scipy.signal.firwin.

    Args:
        low_cutoff: Lower cutoff frequency in Hz.
        high_cutoff: Upper cutoff frequency in Hz.
        sampling_rate: Sampling frequency in Hz.
        numtaps: Number of filter taps.
        window: Window type.

    Returns:
        1D array of FIR filter coefficients b.
    """
    nyquist = sampling_rate / 2.0
    if low_cutoff <= 0 or low_cutoff >= high_cutoff or high_cutoff >= nyquist:
        raise ValueError(
            f"Cutoffs must satisfy 0 < low_cutoff < high_cutoff < Nyquist ({nyquist} Hz)."
        )

    if numtaps % 2 == 0:
        numtaps += 1

    coefficients = firwin(
        numtaps=numtaps,
        cutoff=[low_cutoff, high_cutoff],
        fs=sampling_rate,
        pass_zero=False,
        window=window,
    )
    return coefficients


def apply_filter(
    coefficients: np.ndarray,
    signal: np.ndarray,
    zero_phase: bool = True,
) -> np.ndarray:
    """
    Applies FIR filter coefficients to input signal.

    Args:
        coefficients: 1D filter coefficient array (b).
        signal: Input 1D signal (real or complex).
        zero_phase: If True, uses zero-phase filtfilt; if False, uses causal lfilter.

    Returns:
        Filtered 1D signal.
    """
    b = np.asarray(coefficients, dtype=np.float64)
    sig = np.asarray(signal)

    if len(sig) == 0:
        return sig.copy()

    if zero_phase:
        # filtfilt handles complex signals component-wise if needed or natively
        if np.iscomplexobj(sig):
            filtered_real = filtfilt(b, [1.0], sig.real)
            filtered_imag = filtfilt(b, [1.0], sig.imag)
            return filtered_real + 1j * filtered_imag
        else:
            return filtfilt(b, [1.0], sig)
    else:
        if np.iscomplexobj(sig):
            filtered_real = lfilter(b, [1.0], sig.real)
            filtered_imag = lfilter(b, [1.0], sig.imag)
            return filtered_real + 1j * filtered_imag
        else:
            return lfilter(b, [1.0], sig)
