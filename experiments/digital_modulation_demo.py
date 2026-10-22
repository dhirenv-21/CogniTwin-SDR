"""
Digital Modulation Visual Demonstration & I/Q Constellation Experiment Script.

Generates passband waveform demonstrations (bits, modulated wave, noisy wave, recovered bits)
and renders before-and-after AWGN I/Q constellation diagrams for BPSK, QPSK, and 8-PSK.
Saves figure outputs to 'results/digital/'.
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib.pyplot as plt

from src.channel.awgn import apply_awgn
from src.modulation.digital import (
    generate_bits,
    calculate_ber,
    ASKModulator,
    FSKModulator,
    PSKModulator,
)


def run_digital_demo():
    print("=" * 75)
    print("  COGNITWIN-SDR: DIGITAL CARRIER MODULATION DEMONSTRATION LAB")
    print("=" * 75)

    output_dir = os.path.join("results", "digital")
    os.makedirs(output_dir, exist_ok=True)

    n_bits = 50
    sample_rate = 100000.0  # 100 kHz
    carrier_freq = 10000.0  # 10 kHz
    samples_per_symbol = 20
    seed = 42

    tx_bits = generate_bits(n_bits, seed=seed)

    print(f"\n[1] Generated {n_bits} Random Input Bits:")
    print(f"    {''.join(map(str, tx_bits[:30]))}...\n")

    # -------------------------------------------------------------------------
    # PART 1: Passband Waveform Demonstrations
    # -------------------------------------------------------------------------
    demo_schemes = [
        {"name": "ASK (2-ASK / OOK)", "modulator": ASKModulator(), "passband_kwargs": {"carrier_freq": carrier_freq}},
        {"name": "FSK (2-FSK)", "modulator": FSKModulator(f0=5000.0, f1=10000.0), "passband_kwargs": {}},
        {"name": "BPSK", "modulator": PSKModulator(M=2), "passband_kwargs": {"carrier_freq": carrier_freq}},
        {"name": "QPSK", "modulator": PSKModulator(M=4), "passband_kwargs": {"carrier_freq": carrier_freq}},
    ]

    fig, axs = plt.subplots(len(demo_schemes), 2, figsize=(14, 12), dpi=300)
    fig.patch.set_facecolor("#0f172a")

    color_text = "#f8fafc"
    color_grid = "#334155"
    color_clean = "#38bdf8"
    color_noisy = "#ef4444"

    for ax in axs.flat:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors=color_text)
        ax.xaxis.label.set_color(color_text)
        ax.yaxis.label.set_color(color_text)
        ax.title.set_color(color_text)
        ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
        for spine in ax.spines.values():
            spine.set_color("#475569")

    for i, item in enumerate(demo_schemes):
        name = item["name"]
        mod = item["modulator"]
        pb_kwargs = item["passband_kwargs"]

        # Modulate passband
        passband_sig = mod.modulate_passband(tx_bits, samples_per_symbol=samples_per_symbol, sample_rate=sample_rate, **pb_kwargs)

        # Add AWGN channel noise
        noisy_sig = apply_awgn(passband_sig, snr_db=15.0, seed=seed)

        # Demodulate passband
        rx_bits = mod.demodulate_passband(noisy_sig, samples_per_symbol=samples_per_symbol, sample_rate=sample_rate, **pb_kwargs)

        ber = calculate_ber(tx_bits, rx_bits)

        t_wave = np.arange(len(passband_sig[:200])) / sample_rate * 1000  # first 10 bits

        # Left Subplot: Clean Modulated Waveform
        axs[i, 0].plot(t_wave, passband_sig[:200], color=color_clean, linewidth=1.2)
        axs[i, 0].set_title(f"{name}: Clean Passband Modulated Waveform s(t) [First 10 Bits]", fontsize=10, fontweight="bold")
        axs[i, 0].set_xlabel("Time (ms)")
        axs[i, 0].set_ylabel("Amplitude")

        # Right Subplot: Noisy Waveform & Demodulation Result
        axs[i, 1].plot(t_wave, noisy_sig[:200], color=color_noisy, alpha=0.7, linewidth=1.0)
        axs[i, 1].set_title(f"{name}: Noisy Signal at 15 dB SNR (Recovered BER = {ber:.4f})", fontsize=10, fontweight="bold")
        axs[i, 1].set_xlabel("Time (ms)")
        axs[i, 1].set_ylabel("Amplitude")

    plt.suptitle("CogniTwin-SDR Digital Modulation Passband Waveform Demo", fontsize=15, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    waveform_plot_path = os.path.join(output_dir, "digital_waveforms_demo.png")
    plt.savefig(waveform_plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"[Success] Passband waveforms plot saved to: '{waveform_plot_path}'")

    # -------------------------------------------------------------------------
    # PART 2: Before & After AWGN I/Q Constellation Plots
    # -------------------------------------------------------------------------
    psk_schemes = [
        {"name": "BPSK", "M": 2, "filename": "constellation_bpsk.png"},
        {"name": "QPSK", "M": 4, "filename": "constellation_qpsk.png"},
        {"name": "8-PSK", "M": 8, "filename": "constellation_8psk.png"},
    ]

    const_bits = generate_bits(1200, seed=seed)

    for item in psk_schemes:
        name = item["name"]
        M = item["M"]
        filename = item["filename"]

        mod = PSKModulator(M=M)
        clean_symbols = mod.modulate_baseband(const_bits)
        noisy_symbols = apply_awgn(clean_symbols, snr_db=12.0, seed=seed)

        fig, axs = plt.subplots(1, 2, figsize=(12, 5.5), dpi=300)
        fig.patch.set_facecolor("#0f172a")

        for ax in axs:
            ax.set_facecolor("#1e293b")
            ax.tick_params(colors=color_text)
            ax.xaxis.label.set_color(color_text)
            ax.yaxis.label.set_color(color_text)
            ax.title.set_color(color_text)
            ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
            ax.axis("equal")
            for spine in ax.spines.values():
                spine.set_color("#475569")

        # Plot 1: Clean Ideal Constellation
        axs[0].scatter(clean_symbols.real, clean_symbols.imag, color="#38bdf8", s=60, edgecolors="white", linewidth=1.0, label="Ideal Symbol")
        axs[0].set_title(f"{name}: Ideal Clean Constellation (No Noise)", fontsize=11, fontweight="bold")
        axs[0].set_xlabel("In-Phase (I)")
        axs[0].set_ylabel("Quadrature (Q)")
        axs[0].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

        # Plot 2: Noisy Received Constellation (12 dB SNR)
        axs[1].scatter(noisy_symbols.real, noisy_symbols.imag, color="#ef4444", alpha=0.5, s=20, label="Received Noisy")
        axs[1].scatter(clean_symbols.real, clean_symbols.imag, color="#10b981", s=70, marker="x", linewidth=2.0, label="Target Symbol")
        axs[1].set_title(f"{name}: Received Constellation at 12 dB SNR", fontsize=11, fontweight="bold")
        axs[1].set_xlabel("In-Phase (I)")
        axs[1].set_ylabel("Quadrature (Q)")
        axs[1].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

        plt.suptitle(f"CogniTwin-SDR I/Q Constellation Diagram: {name}", fontsize=14, fontweight="bold", color=color_text, y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.95])

        const_path = os.path.join(output_dir, filename)
        plt.savefig(const_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close()

        print(f"[Success] Constellation plot for {name} saved to: '{const_path}'")

    print("\nDemonstration lab completed cleanly!\n")


if __name__ == "__main__":
    run_digital_demo()
