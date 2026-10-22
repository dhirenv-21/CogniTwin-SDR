"""
Analog Modulation & Demodulation Laboratory Experiment Script.

Simulates 6 analog modulation schemes (AM DSB-SC, AM DSB-TC, SSB-USB/LSB, NBFM, WBFM, PM),
evaluates reconstruction metrics (Pearson correlation, MSE, NRE), and saves 4-panel figures
to 'results/analog/'.
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib.pyplot as plt

from src.signal.generator import generate_sinusoid

from src.signal.analysis import compute_fft
from src.evaluation.metrics import (
    mean_squared_error,
    normalized_reconstruction_error,
    pearson_correlation,
)
from src.modulation.analog import (
    AMDSBSCModulator,
    AMDSTCModulator,
    SSBModulator,
    FMModulator,
    PMModulator,
)


def run_demo():
    print("=" * 75)
    print("  COGNITWIN-SDR: ANALOG MODULATION & DEMODULATION LABORATORY DEMO")
    print("=" * 75)

    # Base Parameters
    sample_rate = 100000.0  # 100 kHz sampling rate
    carrier_freq = 10000.0  # 10 kHz carrier frequency
    msg_freq = 1000.0  # 1 kHz baseband message frequency
    duration = 0.1  # 100 ms duration

    np.random.seed(42)

    # Output directory
    output_dir = os.path.join("results", "analog")
    os.makedirs(output_dir, exist_ok=True)

    # Generate message signal
    t, message = generate_sinusoid(
        freq=msg_freq,
        sampling_rate=sample_rate,
        duration=duration,
        amplitude=1.0,
    )

    print(f"\n[Parameters] Sampling Rate: {sample_rate/1000:.0f} kHz | Carrier Freq: {carrier_freq/1000:.0f} kHz | Message Freq: {msg_freq/1000:.0f} kHz | Duration: {duration*1000:.0f} ms\n")

    # Define Modulation Experiments
    experiments = [
        {
            "name": "AM DSB-SC (Double Sideband Suppressed Carrier)",
            "file": "am_dsb_sc.png",
            "modulator": AMDSBSCModulator(),
            "mod_kwargs": {},
            "demod_kwargs": {"lpf_cutoff": 3000.0},
        },
        {
            "name": "AM DSB-TC (Double Sideband Transmitted Carrier)",
            "file": "am_dsb_tc.png",
            "modulator": AMDSTCModulator(),
            "mod_kwargs": {"mod_index": 0.8},
            "demod_kwargs": {"lpf_cutoff": 3000.0},
        },
        {
            "name": "SSB (Single Sideband Upper Sideband - USB)",
            "file": "ssb_usb.png",
            "modulator": SSBModulator(),
            "mod_kwargs": {"sideband": "usb"},
            "demod_kwargs": {"lpf_cutoff": 3000.0},
        },
        {
            "name": "SSB (Single Sideband Lower Sideband - LSB)",
            "file": "ssb_lsb.png",
            "modulator": SSBModulator(),
            "mod_kwargs": {"sideband": "lsb"},
            "demod_kwargs": {"lpf_cutoff": 3000.0},
        },
        {
            "name": "NBFM (Narrowband Frequency Modulation)",
            "file": "nbfm.png",
            "modulator": FMModulator(),
            "mod_kwargs": {"freq_dev": 200.0},
            "demod_kwargs": {"freq_dev": 200.0, "lpf_cutoff": 3000.0},
        },
        {
            "name": "WBFM (Wideband Frequency Modulation)",
            "file": "wbfm.png",
            "modulator": FMModulator(),
            "mod_kwargs": {"freq_dev": 5000.0},
            "demod_kwargs": {"freq_dev": 5000.0, "lpf_cutoff": 3000.0},
        },
        {
            "name": "PM (Phase Modulation)",
            "file": "pm.png",
            "modulator": PMModulator(),
            "mod_kwargs": {"phase_dev": 1.5},
            "demod_kwargs": {"phase_dev": 1.5, "lpf_cutoff": 3000.0},
        },
    ]

    print("-" * 75)
    print(f" {'MODULATION SCHEME':<45} | {'PEARSON r':<10} | {'MSE':<10} | {'NRE':<8}")
    print("-" * 75)

    for exp in experiments:
        name = exp["name"]
        filename = exp["file"]
        modulator = exp["modulator"]
        mod_kwargs = exp["mod_kwargs"]
        demod_kwargs = exp["demod_kwargs"]

        # Modulate and Demodulate
        modulated = modulator.modulate(message, carrier_freq=carrier_freq, sample_rate=sample_rate, **mod_kwargs)
        recovered = modulator.demodulate(modulated, carrier_freq=carrier_freq, sample_rate=sample_rate, **demod_kwargs)

        # Compute Metrics (trim edge transients)
        trim = 120
        m_trim = message[trim:-trim]
        r_trim = recovered[trim:-trim]

        # Normalize recovered signal amplitude for MSE/NRE scale matching
        r_norm = r_trim / np.max(np.abs(r_trim)) if np.max(np.abs(r_trim)) > 0 else r_trim
        m_norm = m_trim / np.max(np.abs(m_trim))

        r_corr = pearson_correlation(m_norm, r_norm)
        mse_val = mean_squared_error(m_norm, r_norm)
        nre_val = normalized_reconstruction_error(m_norm, r_norm)

        print(f" {name:<45} | {r_corr:<10.4f} | {mse_val:<10.6f} | {nre_val:<8.4f}")

        # Plot 4-subplot Figure
        fig, axs = plt.subplots(2, 2, figsize=(14, 10), dpi=300)
        fig.patch.set_facecolor("#0f172a")

        color_text = "#f8fafc"
        color_grid = "#334155"
        color_msg = "#38bdf8"
        color_mod = "#f59e0b"
        color_spec = "#ec4899"
        color_rec = "#10b981"

        for ax in axs.flat:
            ax.set_facecolor("#1e293b")
            ax.tick_params(colors=color_text)
            ax.xaxis.label.set_color(color_text)
            ax.yaxis.label.set_color(color_text)
            ax.title.set_color(color_text)
            ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
            for spine in ax.spines.values():
                spine.set_color("#475569")

        # 1) Original Message
        axs[0, 0].plot(t * 1000, message, color=color_msg, linewidth=1.5)
        axs[0, 0].set_title("1) Original Baseband Message m(t)", fontsize=11, fontweight="bold")
        axs[0, 0].set_xlabel("Time (ms)")
        axs[0, 0].set_ylabel("Amplitude")

        # 2) Modulated Waveform (Zoomed 10 ms window for clear carrier viewing)
        zoom_pts = int(sample_rate * 0.01)
        axs[0, 1].plot(t[:zoom_pts] * 1000, modulated[:zoom_pts], color=color_mod, linewidth=1.2)
        axs[0, 1].set_title(f"2) Modulated Passband Waveform s(t) [First 10 ms]", fontsize=11, fontweight="bold")
        axs[0, 1].set_xlabel("Time (ms)")
        axs[0, 1].set_ylabel("Amplitude")

        # 3) Frequency Spectrum
        freqs, mag = compute_fft(modulated, sample_rate)
        mag_db = 20 * np.log10(np.maximum(mag, 1e-6))
        pos_mask = (freqs >= 0) & (freqs <= 25000)
        axs[1, 0].plot(freqs[pos_mask] / 1000, mag_db[pos_mask], color=color_spec, linewidth=1.2)
        axs[1, 0].set_title("3) Modulated Signal Frequency Spectrum (FFT)", fontsize=11, fontweight="bold")
        axs[1, 0].set_xlabel("Frequency (kHz)")
        axs[1, 0].set_ylabel("Magnitude (dB)")

        # 4) Recovered Message vs Original
        axs[1, 1].plot(t[trim:-trim] * 1000, m_norm, label="Original m(t)", color=color_msg, linestyle="--", linewidth=1.5)
        axs[1, 1].plot(t[trim:-trim] * 1000, r_norm, label=f"Recovered m_hat(t) (r={r_corr:.3f})", color=color_rec, linewidth=1.5)
        axs[1, 1].set_title(f"4) Demodulated Recovered Message m_hat(t)", fontsize=11, fontweight="bold")
        axs[1, 1].set_xlabel("Time (ms)")
        axs[1, 1].set_ylabel("Normalized Amplitude")
        axs[1, 1].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

        plt.suptitle(f"CogniTwin-SDR Analog Lab: {name}", fontsize=15, fontweight="bold", color=color_text, y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.95])

        fig_path = os.path.join(output_dir, filename)
        plt.savefig(fig_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close()

    print("-" * 75)
    print(f"\n[Success] All modulation figures saved successfully to: '{output_dir}'")
    print("Lab experiment completed cleanly!\n")


if __name__ == "__main__":
    run_demo()
