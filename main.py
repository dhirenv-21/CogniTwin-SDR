"""
CogniTwin-SDR Signal Foundation End-to-End Demonstration Script.

Generates a test sinusoid, converts to analytic I/Q, injects AWGN noise,
filters out-of-band noise with an FIR lowpass filter, computes FFT spectrums,
prints diagnostic estimates, and outputs a 4-panel diagnostic plot to 'results/signal_foundation_demo.png'.
"""

import os
import numpy as np
import matplotlib.pyplot as plt

from src.signal.generator import generate_sinusoid, to_iq, add_awgn
from src.signal.analysis import (
    compute_fft,
    estimate_frequency,
    estimate_bandwidth,
    calculate_snr,
    calculate_power,
)
from src.signal.filters import design_fir_lowpass, apply_filter


def main():
    print("=" * 70)
    print("  COGNITWIN-SDR: AGENTIC COGNITIVE DIGITAL TWIN RESEARCH PROTOTYPE")
    print("  Signal Foundation Demonstration & Diagnostic Pipeline")
    print("=" * 70)

    # 1. Signal Generation Parameters
    target_freq = 1500.0  # Carrier frequency in Hz
    sampling_rate = 20000.0  # Sampling frequency in Hz
    duration = 0.05  # Signal duration in seconds (50 ms)
    target_snr_db = 12.0  # AWGN SNR in dB
    cutoff_freq = 3000.0  # LPF cutoff frequency in Hz

    print(f"\n[1] Generating Carrier Sinusoid:")
    print(f"    Frequency       : {target_freq:.1f} Hz")
    print(f"    Sampling Rate   : {sampling_rate:.1f} Hz")
    print(f"    Duration        : {duration * 1000:.1f} ms")

    t, clean_real_signal = generate_sinusoid(
        freq=target_freq,
        sampling_rate=sampling_rate,
        duration=duration,
        amplitude=1.0,
    )

    # 2. Convert to Complex I/Q Analytic Signal
    print(f"\n[2] Converting to Complex I/Q (Analytic Signal via Hilbert Transform)...")
    clean_iq_signal = to_iq(clean_real_signal, method="hilbert")

    # 3. Add AWGN Noise
    print(f"\n[3] Injecting AWGN (Target SNR = {target_snr_db:.1f} dB, Seed = 42)...")
    noisy_iq_signal = add_awgn(clean_iq_signal, snr_db=target_snr_db, seed=42)

    # 4. Apply FIR Low-Pass Filter
    print(f"\n[4] Designing FIR Low-pass Filter (Cutoff = {cutoff_freq:.1f} Hz, 101 Taps)...")
    lpf_coeff = design_fir_lowpass(
        cutoff_freq=cutoff_freq,
        sampling_rate=sampling_rate,
        numtaps=101,
    )
    filtered_iq_signal = apply_filter(lpf_coeff, noisy_iq_signal, zero_phase=True)

    # 5. Compute FFT Spectrums
    print(f"\n[5] Computing FFT Spectra (Before & After Filtering)...")
    freqs_unfiltered, mag_unfiltered = compute_fft(noisy_iq_signal, sampling_rate)
    freqs_filtered, mag_filtered = compute_fft(filtered_iq_signal, sampling_rate)

    # 6. Estimate Metrics
    est_freq = estimate_frequency(filtered_iq_signal, sampling_rate)
    measured_snr_before = calculate_snr(clean_iq_signal, noisy_iq_signal)
    measured_snr_after = calculate_snr(clean_iq_signal, filtered_iq_signal)
    est_bw_3db = estimate_bandwidth(filtered_iq_signal, sampling_rate, method="3db")
    est_bw_occ = estimate_bandwidth(filtered_iq_signal, sampling_rate, method="occupied", power_ratio=0.99)

    print("\n" + "-" * 70)
    print("  SIGNAL DIAGNOSTIC METRICS ESTIMATION")
    print("-" * 70)
    print(f"  Target Frequency          : {target_freq:.2f} Hz")
    print(f"  Estimated Frequency       : {est_freq:.2f} Hz (Error: {abs(est_freq - target_freq)/target_freq * 100:.2f}%)")
    print(f"  Unfiltered Measured SNR  : {measured_snr_before:.2f} dB")
    print(f"  Filtered Measured SNR    : {measured_snr_after:.2f} dB (Improvement: {measured_snr_after - measured_snr_before:+.2f} dB)")
    print(f"  Estimated -3dB Bandwidth  : {est_bw_3db:.2f} Hz")
    print(f"  Estimated 99% Occupied BW : {est_bw_occ:.2f} Hz")
    print("-" * 70)

    # 7. Generate 4-Panel Diagnostic Plot
    print(f"\n[6] Rendering 4-Panel Diagnostic Visualization Plot...")
    os.makedirs("results", exist_ok=True)
    plot_path = os.path.join("results", "signal_foundation_demo.png")

    fig, axs = plt.subplots(2, 2, figsize=(14, 10), dpi=300)
    plt.style.use("default")
    fig.patch.set_facecolor('#0f172a')  # Dark slate background

    # Theme colors
    color_text = '#f8fafc'
    color_grid = '#334155'
    color_clean = '#38bdf8'  # Cyan
    color_noisy = '#ef4444'  # Red
    color_filtered = '#10b981'  # Green/Emerald
    color_accent = '#f59e0b'  # Amber

    for ax in axs.flat:
        ax.set_facecolor('#1e293b')
        ax.tick_params(colors=color_text)
        ax.xaxis.label.set_color(color_text)
        ax.yaxis.label.set_color(color_text)
        ax.title.set_color(color_text)
        ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
        for spine in ax.spines.values():
            spine.set_color('#475569')

    # Panel 1: Time Domain Waveforms
    axs[0, 0].plot(t * 1000, clean_iq_signal.real, label="Clean I(t)", color=color_clean, linewidth=1.5)
    axs[0, 0].plot(t * 1000, noisy_iq_signal.real, label="Noisy I(t)", color=color_noisy, alpha=0.5, linewidth=1.0)
    axs[0, 0].plot(t * 1000, filtered_iq_signal.real, label="Filtered I(t)", color=color_filtered, linewidth=1.8)
    axs[0, 0].set_title("Panel 1: Time Domain Waveforms (In-Phase Component)", fontsize=12, fontweight="bold", pad=10)
    axs[0, 0].set_xlabel("Time (ms)")
    axs[0, 0].set_ylabel("Amplitude")
    axs[0, 0].legend(facecolor='#0f172a', labelcolor=color_text, loc="upper right")

    # Panel 2: I/Q Constellation / Trajectory Plot
    axs[0, 1].plot(noisy_iq_signal.real, noisy_iq_signal.imag, label="Noisy Trajectory", color=color_noisy, alpha=0.3, linewidth=0.8)
    axs[0, 1].plot(filtered_iq_signal.real, filtered_iq_signal.imag, label="Filtered Trajectory", color=color_filtered, linewidth=1.5)
    axs[0, 1].plot(clean_iq_signal.real, clean_iq_signal.imag, label="Clean Ideal Circle", color=color_clean, linestyle="--", linewidth=1.5)
    axs[0, 1].set_title("Panel 2: Complex I/Q Constellation / Trajectory", fontsize=12, fontweight="bold", pad=10)
    axs[0, 1].set_xlabel("In-Phase (I)")
    axs[0, 1].set_ylabel("Quadrature (Q)")
    axs[0, 1].axis("equal")
    axs[0, 1].legend(facecolor='#0f172a', labelcolor=color_text, loc="upper right")

    # Panel 3: FFT Spectrum Before Filtering
    mag_unfiltered_db = 20 * np.log10(np.maximum(mag_unfiltered, 1e-6))
    axs[1, 0].plot(freqs_unfiltered / 1000, mag_unfiltered_db, color=color_noisy, linewidth=1.2, label="Unfiltered Spectrum")
    axs[1, 0].axvline(target_freq / 1000, color=color_accent, linestyle="--", label=f"Target ({target_freq/1000:.1f} kHz)")
    axs[1, 0].set_title(f"Panel 3: Spectrum Before Filtering (SNR: {measured_snr_before:.1f} dB)", fontsize=12, fontweight="bold", pad=10)
    axs[1, 0].set_xlabel("Frequency (kHz)")
    axs[1, 0].set_ylabel("Magnitude (dB)")
    axs[1, 0].legend(facecolor='#0f172a', labelcolor=color_text, loc="upper right")

    # Panel 4: FFT Spectrum After Filtering
    mag_filtered_db = 20 * np.log10(np.maximum(mag_filtered, 1e-6))
    axs[1, 1].plot(freqs_filtered / 1000, mag_filtered_db, color=color_filtered, linewidth=1.5, label="Filtered Spectrum")
    axs[1, 1].axvline(target_freq / 1000, color=color_accent, linestyle="--", label=f"Target ({target_freq/1000:.1f} kHz)")
    axs[1, 1].axvline(cutoff_freq / 1000, color='#94a3b8', linestyle=":", label=f"LPF Cutoff ({cutoff_freq/1000:.1f} kHz)")
    axs[1, 1].set_title(f"Panel 4: Spectrum After Filtering (SNR: {measured_snr_after:.1f} dB)", fontsize=12, fontweight="bold", pad=10)
    axs[1, 1].set_xlabel("Frequency (kHz)")
    axs[1, 1].set_ylabel("Magnitude (dB)")
    axs[1, 1].legend(facecolor='#0f172a', labelcolor=color_text, loc="upper right")

    plt.suptitle("CogniTwin-SDR: Signal Foundation Diagnostic Dashboard", fontsize=16, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

    print(f"\n[7] Diagnostic visualization successfully saved to: {plot_path}")
    print("\nDemonstration complete cleanly!\n")


if __name__ == "__main__":
    main()
