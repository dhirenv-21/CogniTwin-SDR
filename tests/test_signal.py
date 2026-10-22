"""
Unit tests for signal foundation modules (generator, analysis, filters).
"""

import numpy as np
import pytest

from src.signal.generator import generate_sinusoid, to_iq, add_awgn
from src.signal.analysis import estimate_frequency, calculate_snr, compute_fft, calculate_power
from src.signal.filters import design_fir_lowpass, apply_filter


def test_frequency_estimation_accuracy():
    """
    Tests that frequency estimation accuracy is within +/- 1% tolerance.
    """
    target_freq = 1000.0  # Hz
    sampling_rate = 20000.0  # Hz
    duration = 1.0  # seconds

    _, signal = generate_sinusoid(
        freq=target_freq,
        sampling_rate=sampling_rate,
        duration=duration,
        amplitude=1.0,
    )

    est_freq = estimate_frequency(signal, sampling_rate)
    relative_error = abs(est_freq - target_freq) / target_freq

    assert relative_error <= 0.01, (
        f"Estimated frequency {est_freq:.2f} Hz exceeds 1% tolerance of target {target_freq} Hz."
    )


def test_iq_generation_orthogonality_and_phase():
    """
    Tests I/Q generation orthogonality (I and Q dot product ~ 0) and magnitude stability.
    """
    freq = 500.0  # Hz
    sampling_rate = 10000.0  # Hz
    duration = 0.5  # seconds

    _, real_signal = generate_sinusoid(
        freq=freq,
        sampling_rate=sampling_rate,
        duration=duration,
        amplitude=1.0,
    )

    iq_signal = to_iq(real_signal, method="hilbert")
    I = iq_signal.real
    Q = iq_signal.imag

    # Trim Hilbert edge transient samples
    trim = 100
    I_trim = I[trim:-trim]
    Q_trim = Q[trim:-trim]

    # Orthogonality: normalized correlation < 0.05
    correlation = np.abs(np.dot(I_trim, Q_trim)) / (np.linalg.norm(I_trim) * np.linalg.norm(Q_trim))
    assert correlation < 0.05, f"I and Q components are not orthogonal. Normalized dot product = {correlation:.4f}"

    # Envelope magnitude should be ~ 1.0
    magnitude = np.abs(iq_signal[trim:-trim])
    assert np.allclose(magnitude, 1.0, atol=0.05), "I/Q envelope magnitude significantly deviates from signal amplitude."


def test_snr_calculation():
    """
    Tests SNR calculation against known AWGN noise injection power.
    """
    target_snr_db = 15.0
    sampling_rate = 10000.0
    duration = 1.0

    _, clean_signal = generate_sinusoid(
        freq=400.0,
        sampling_rate=sampling_rate,
        duration=duration,
        amplitude=1.0,
    )

    noisy_signal = add_awgn(clean_signal, snr_db=target_snr_db, seed=12345)
    measured_snr = calculate_snr(clean_signal, noisy_signal)

    assert abs(measured_snr - target_snr_db) < 0.5, (
        f"Measured SNR {measured_snr:.2f} dB differs from target SNR {target_snr_db} dB."
    )


def test_filter_attenuation():
    """
    Tests FIR lowpass filter stopband attenuation (> 20 dB attenuation in stopband).
    """
    sampling_rate = 10000.0  # Hz
    duration = 0.5  # seconds
    inband_freq = 500.0  # Hz (passband)
    stopband_freq = 3500.0  # Hz (stopband)

    t = np.arange(int(sampling_rate * duration)) / sampling_rate
    composite_signal = np.cos(2.0 * np.pi * inband_freq * t) + np.cos(2.0 * np.pi * stopband_freq * t)

    # Design lowpass filter with cutoff at 1000 Hz
    b = design_fir_lowpass(cutoff_freq=1000.0, sampling_rate=sampling_rate, numtaps=101)
    filtered_signal = apply_filter(b, composite_signal, zero_phase=True)

    # Compute FFT magnitude spectrum before and after filtering
    freqs, mag_before = compute_fft(composite_signal, sampling_rate)
    _, mag_after = compute_fft(filtered_signal, sampling_rate)

    # Locate stopband peak (around 3500 Hz)
    stopband_mask = np.abs(freqs - stopband_freq) < 50.0
    stopband_mag_before = np.max(mag_before[stopband_mask])
    stopband_mag_after = np.max(mag_after[stopband_mask])

    attenuation_db = 20.0 * np.log10(stopband_mag_before / stopband_mag_after)

    assert attenuation_db > 20.0, (
        f"Stopband attenuation of {attenuation_db:.2f} dB is below required 20 dB threshold."
    )
