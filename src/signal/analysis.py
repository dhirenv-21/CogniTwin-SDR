"""
Signal Analysis Module.

Provides functions for FFT spectral analysis, PSD calculation, peak frequency estimation,
bandwidth estimation (-3dB and occupied bandwidth), power, RMS, and SNR calculation.
"""

from typing import Optional, Tuple
import numpy as np
from scipy.signal import welch


def compute_fft(
    signal: np.ndarray,
    sampling_rate: float,
    nfft: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes the FFT magnitude spectrum and mapped frequency axis.

    Args:
        signal: Input 1D signal (real or complex).
        sampling_rate: Sampling frequency in Hz.
        nfft: Number of FFT points (defaults to signal length).

    Returns:
        Tuple of (freqs, magnitude_spectrum), sorted by frequency.
    """
    sig = np.asarray(signal)
    N = len(sig) if nfft is None else int(nfft)

    if np.iscomplexobj(sig):
        fft_vals = np.fft.fft(sig, n=N)
        freqs = np.fft.fftfreq(N, d=1.0 / sampling_rate)
        # Shift zero frequency to center
        freqs = np.fft.fftshift(freqs)
        fft_vals = np.fft.fftshift(fft_vals)
        magnitude = np.abs(fft_vals) / N
    else:
        # Real signal: compute full shifted FFT or positive spectrum
        fft_vals = np.fft.fft(sig, n=N)
        freqs = np.fft.fftfreq(N, d=1.0 / sampling_rate)
        freqs = np.fft.fftshift(freqs)
        fft_vals = np.fft.fftshift(fft_vals)
        magnitude = np.abs(fft_vals) / N

    return freqs, magnitude


def compute_psd(
    signal: np.ndarray,
    sampling_rate: float,
    nperseg: int = 256,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes Power Spectral Density (PSD) using Welch's method.

    Args:
        signal: Input 1D signal.
        sampling_rate: Sampling frequency in Hz.
        nperseg: Length of each segment for Welch estimate.

    Returns:
        Tuple of (freqs, psd_values).
    """
    sig = np.asarray(signal)
    nperseg_actual = min(len(sig), nperseg)
    freqs, psd = welch(
        sig,
        fs=sampling_rate,
        nperseg=nperseg_actual,
        return_onesided=not np.iscomplexobj(sig),
    )
    return freqs, psd


def estimate_frequency(signal: np.ndarray, sampling_rate: float) -> float:
    """
    Estimates the dominant frequency component using peak spectral detection.

    Args:
        signal: Input 1D signal.
        sampling_rate: Sampling frequency in Hz.

    Returns:
        Estimated peak frequency in Hz.
    """
    sig = np.asarray(signal)
    freqs, magnitude = compute_fft(sig, sampling_rate)

    if not np.iscomplexobj(sig):
        # For real signal, restrict search to positive frequencies
        pos_mask = freqs >= 0
        freqs_search = freqs[pos_mask]
        mag_search = magnitude[pos_mask]
    else:
        freqs_search = freqs
        mag_search = magnitude

    peak_idx = np.argmax(mag_search)
    return float(np.abs(freqs_search[peak_idx]))


def estimate_bandwidth(
    signal: np.ndarray,
    sampling_rate: float,
    method: str = "3db",
    power_ratio: float = 0.99,
) -> float:
    """
    Estimates signal bandwidth using -3dB or occupied bandwidth (99% power) method.

    Args:
        signal: Input 1D signal.
        sampling_rate: Sampling frequency in Hz.
        method: '3db' for half-power bandwidth, or 'occupied' for fractional energy.
        power_ratio: Target power fraction for occupied bandwidth (e.g., 0.99).

    Returns:
        Estimated bandwidth in Hz.
    """
    sig = np.asarray(signal)
    freqs, mag = compute_fft(sig, sampling_rate)

    # Restrict to positive spectrum for real signals
    if not np.iscomplexobj(sig):
        pos_mask = freqs >= 0
        freqs = freqs[pos_mask]
        mag = mag[pos_mask]

    power_spec = mag ** 2
    if np.sum(power_spec) == 0:
        return 0.0

    if method == "3db":
        peak_power = np.max(power_spec)
        half_power = peak_power / 2.0
        above_3db_indices = np.where(power_spec >= half_power)[0]
        if len(above_3db_indices) == 0:
            return 0.0
        bw = freqs[above_3db_indices[-1]] - freqs[above_3db_indices[0]]
        # Handle single-bin peak case
        if bw == 0.0 and len(freqs) > 1:
            df = freqs[1] - freqs[0]
            bw = float(df)
        return float(bw)

    elif method == "occupied":
        total_power = np.sum(power_spec)
        cum_power = np.cumsum(power_spec) / total_power
        tail = (1.0 - power_ratio) / 2.0
        low_idx = np.searchsorted(cum_power, tail)
        high_idx = np.searchsorted(cum_power, 1.0 - tail)
        high_idx = min(high_idx, len(freqs) - 1)
        bw = freqs[high_idx] - freqs[low_idx]
        return float(max(0.0, bw))
    else:
        raise ValueError(f"Unknown bandwidth method '{method}'. Use '3db' or 'occupied'.")


def calculate_power(signal: np.ndarray) -> float:
    """
    Calculates average signal power P = (1/N) * sum(|s[n]|^2).

    Args:
        signal: Input 1D array.

    Returns:
        Average signal power.
    """
    sig = np.asarray(signal)
    if len(sig) == 0:
        return 0.0
    return float(np.mean(np.abs(sig) ** 2))


def calculate_rms(signal: np.ndarray) -> float:
    """
    Calculates Root Mean Square (RMS) value of signal.

    Args:
        signal: Input 1D array.

    Returns:
        RMS value.
    """
    return float(np.sqrt(calculate_power(signal)))


def calculate_snr(clean_signal: np.ndarray, noisy_signal: np.ndarray) -> float:
    """
    Calculates Signal-to-Noise Ratio (SNR) in dB given clean and noisy signals.

    Args:
        clean_signal: Original clean 1D signal.
        noisy_signal: Signal with noise added.

    Returns:
        SNR in decibels (dB).
    """
    p_clean = calculate_power(clean_signal)
    noise = np.asarray(noisy_signal) - np.asarray(clean_signal)
    p_noise = calculate_power(noise)

    if p_noise == 0:
        return float("inf")
    if p_clean == 0:
        return float("-inf")

    snr_db = 10.0 * np.log10(p_clean / p_noise)
    return float(snr_db)


# Resolution limits of estimate_snr_blind(), in dB.
BLIND_SNR_FLOOR_DB = -10.0
BLIND_SNR_CEIL_DB = 40.0
# Upper edge of the "below resolution" region: PSK is resolved from about +0.3 dB at
# N = 512, and a floored estimate therefore means "SNR <= ~1 dB", not "-10 dB".
BLIND_SNR_RESOLUTION_DB = 1.0
# Threshold on the normalised cyclic-prefix correlation. Non-OFDM signals and
# noise peak at ~0.28 (99th percentile, 512 samples); OFDM-QPSK reaches ~0.5 at
# 0 dB and ~0.9 at 10 dB.
BLIND_SNR_CP_THRESHOLD = 0.45
# Envelope kurtosis k = M4/M2^2 is 1 for constant modulus and 2 for complex
# Gaussian noise. Under pure noise its sample std is 2/sqrt(N) (measured: 1.94-2.02
# x 1/sqrt(N) for N = 128..10000), so a constant-envelope component is accepted only
# when k < 2 - Z * 2/sqrt(N). Z = 3 gives ~0.1 % false acceptance on pure noise;
# at N = 512 PSK is resolved from about +0.3 dB SNR.
BLIND_SNR_NULL_Z = 3.0


def estimate_snr_blind(
    iq: np.ndarray,
    n_fft: int = 64,
    cp_len: int = 16,
) -> dict:
    """
    Blind (no reference) SNR estimate of a complex baseband capture, in dB.

    Two classical estimators, chosen from the data itself:

    * ``ofdm_cp``  - if the capture shows cyclic-prefix structure for an
      (n_fft, cp_len) OFDM frame, at any timing offset: the CP samples repeat
      the symbol tail, so  N = E|y[n] - y[n+n_fft]|^2 / 2  over the CP slots
      (the signal cancels) and  SNR = (M2 - N) / N.
    * ``m2m4``     - otherwise, for constant-envelope (PSK) signals:
      with M2 = E|y|^2, M4 = E|y|^4 and complex Gaussian noise,
      S = sqrt(2 M2^2 - M4),  N = M2 - S.
    * ``below_resolution`` - Gaussian-like envelope and no CP structure: no
      signal component can be separated from noise without a reference. The
      floor value is returned, NOT a random estimate.

    Gaussian interference counts as noise, so this is a blind SINR. Results are
    clipped to [BLIND_SNR_FLOOR_DB, BLIND_SNR_CEIL_DB]. The estimate is scale
    invariant, so unit-power normalisation upstream does not affect it.

    Measured accuracy (512 samples): PSK bias <= 0.1 dB, std <= 0.5 dB for
    SNR >= 5 dB; OFDM-QPSK bias <= 0.5 dB, std <= 2.8 dB for SNR >= 5 dB. Below
    ~+0.3 dB (PSK, N = 512) the floor is returned. See
    tests/test_spectrum_agent_validation.py.

    Returns:
        {"snr_db": float, "method": str, "kurtosis": float, "cp_correlation": float}
    """
    y = np.asarray(iq, dtype=np.complex128).reshape(-1)
    out = {"snr_db": BLIND_SNR_FLOOR_DB, "method": "below_resolution",
           "kurtosis": float("nan"), "cp_correlation": 0.0}
    if y.size < 4:
        return out
    p = np.abs(y) ** 2
    m2 = float(np.mean(p))
    if not np.isfinite(m2) or m2 <= 0.0:
        return out
    m4 = float(np.mean(p ** 2))
    kurt = m4 / m2 ** 2
    out["kurtosis"] = kurt

    # ---- cyclic-prefix scan over all timing offsets -------------------------
    sym = n_fft + cp_len
    rho_best, noise_cp = 0.0, None
    if y.size >= sym + n_fft:
        n_sym = (y.size - n_fft) // sym + 1
        base = np.arange(n_sym)[:, None] * sym + np.arange(cp_len)[None, :]
        for off in range(sym):
            idx = (off + base).ravel()
            idx = idx[idx + n_fft < y.size]
            if idx.size == 0:
                continue
            a, b = y[idx], y[idx + n_fft]
            rho = float(np.real(np.mean(a * np.conj(b)))) / m2
            if rho > rho_best:
                rho_best = rho
                noise_cp = float(np.mean(np.abs(a - b) ** 2)) / 2.0
    out["cp_correlation"] = rho_best

    if noise_cp is not None and rho_best >= BLIND_SNR_CP_THRESHOLD:
        snr = 10.0 * np.log10(max(m2 - noise_cp, 1e-12) / max(noise_cp, 1e-12))
        method = "ofdm_cp"
    elif kurt < 2.0 - BLIND_SNR_NULL_Z * 2.0 / np.sqrt(y.size) and 2.0 * m2 ** 2 - m4 > 0.0:
        s = float(np.sqrt(2.0 * m2 ** 2 - m4))
        snr = 10.0 * np.log10(max(s, 1e-12) / max(m2 - s, 1e-12))
        method = "m2m4"
    else:
        return out

    out["snr_db"] = float(np.clip(snr, BLIND_SNR_FLOOR_DB, BLIND_SNR_CEIL_DB))
    out["method"] = method
    return out
