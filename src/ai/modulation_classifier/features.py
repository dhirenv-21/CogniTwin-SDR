"""
Feature Extraction Module for Modulation Classification.

Extracts vectorized time-domain, I/Q statistical, and spectral features from complex I/Q signal arrays.
"""

from typing import List
import numpy as np
from scipy.stats import skew, kurtosis

from src.signal.analysis import (
    compute_fft,
    estimate_frequency,
    estimate_bandwidth,
    calculate_power,
)


FEATURE_NAMES: List[str] = [
    "mean_I",
    "mean_Q",
    "var_I",
    "var_Q",
    "signal_power",
    "papr_db",
    "amp_mean",
    "amp_std",
    "amp_skewness",
    "amp_kurtosis",
    "phase_mean",
    "phase_std",
    "iq_correlation",
    "dominant_freq_hz",
    "bandwidth_3db_hz",
    "spectral_flatness",
    "spectral_entropy",
]


def extract_features(iq_samples: np.ndarray, sample_rate: float = 100000.0) -> np.ndarray:
    """
    Extracts a structured 1D numerical feature vector from a complex I/Q signal array.

    Args:
        iq_samples: 1D complex array of I/Q samples.
        sample_rate: Sampling frequency in Hz.

    Returns:
        1D NumPy float64 array of extracted features.
    """
    x = np.asarray(iq_samples, dtype=np.complex128)
    if len(x) == 0:
        return np.zeros(len(FEATURE_NAMES), dtype=np.float64)

    I = x.real
    Q = x.imag
    amp = np.abs(x)
    phase = np.angle(x)

    # 1. Time / IQ Statistics
    mean_I = float(np.mean(I))
    mean_Q = float(np.mean(Q))
    var_I = float(np.var(I))
    var_Q = float(np.var(Q))

    power = calculate_power(x)
    peak_power = float(np.max(amp ** 2)) if len(amp) > 0 else 0.0
    papr_db = 10.0 * np.log10(peak_power / (power + 1e-12)) if power > 0 else 0.0

    amp_mean = float(np.mean(amp))
    amp_std = float(np.std(amp))
    amp_skew = float(skew(amp)) if amp_std > 1e-12 else 0.0
    amp_kurt = float(kurtosis(amp)) if amp_std > 1e-12 else 0.0

    phase_mean = float(np.mean(phase))
    phase_std = float(np.std(phase))

    # IQ Correlation
    if var_I > 1e-12 and var_Q > 1e-12:
        cov_iq = np.mean((I - mean_I) * (Q - mean_Q))
        iq_corr = float(cov_iq / (np.sqrt(var_I) * np.sqrt(var_Q)))
        iq_corr = float(np.clip(iq_corr, -1.0, 1.0))
    else:
        iq_corr = 0.0

    # 2. Spectral Features
    dom_freq = estimate_frequency(x, sample_rate)
    bw_3db = estimate_bandwidth(x, sample_rate, method="3db")

    freqs, mag = compute_fft(x, sample_rate)
    psd = mag ** 2
    psd_sum = np.sum(psd)

    if psd_sum > 0:
        psd_norm = psd / psd_sum
        # Spectral Flatness: Geometric mean / Arithmetic mean
        geom_mean = np.exp(np.mean(np.log(psd + 1e-12)))
        arith_mean = np.mean(psd)
        spec_flatness = float(geom_mean / (arith_mean + 1e-12))

        # Spectral Entropy
        psd_nonzero = psd_norm[psd_norm > 1e-12]
        spec_entropy = float(-np.sum(psd_nonzero * np.log(psd_nonzero)))
    else:
        spec_flatness = 0.0
        spec_entropy = 0.0

    feature_vec = np.array(
        [
            mean_I,
            mean_Q,
            var_I,
            var_Q,
            power,
            papr_db,
            amp_mean,
            amp_std,
            amp_skew,
            amp_kurt,
            phase_mean,
            phase_std,
            iq_corr,
            dom_freq,
            bw_3db,
            spec_flatness,
            spec_entropy,
        ],
        dtype=np.float64,
    )

    # Clean any accidental NaNs or Infs
    feature_vec = np.nan_to_num(feature_vec, nan=0.0, posinf=0.0, neginf=0.0)
    return feature_vec
