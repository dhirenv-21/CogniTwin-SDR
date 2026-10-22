"""
BER vs SNR Performance Evaluation Experiment Script.

Simulates Bit Error Rate (BER) across Signal-to-Noise Ratios (0 dB to 20 dB) for ASK, FSK, BPSK, QPSK, and 8-PSK
using vectorized complex baseband I/Q simulation for fast, memory-efficient execution.
Saves logarithmic performance plot to 'results/digital/ber_vs_snr.png'.
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


def run_ber_experiment():
    print("=" * 80)
    print("  COGNITWIN-SDR: DIGITAL MODULATION BER VS SNR PERFORMANCE EVALUATION")
    print("=" * 80)

    n_bits = 120000  # 120,000 bits per point for smooth Monte Carlo statistics
    snr_range_db = np.arange(0, 22, 2)  # 0, 2, 4, ..., 20 dB
    seed = 42

    print(f"\n[Parameters] Bit Count per Point: {n_bits:,} bits | SNR Range: {snr_range_db[0]} dB to {snr_range_db[-1]} dB\n")

    schemes = [
        {"name": "ASK (2-ASK / OOK)", "key": "ASK", "modulator": ASKModulator()},
        {"name": "FSK (2-FSK)", "key": "FSK", "modulator": FSKModulator()},
        {"name": "BPSK", "key": "BPSK", "modulator": PSKModulator(M=2)},
        {"name": "QPSK", "key": "QPSK", "modulator": PSKModulator(M=4)},
        {"name": "8-PSK", "key": "8PSK", "modulator": PSKModulator(M=8)},
    ]

    tx_bits = generate_bits(n_bits, seed=seed)

    # Store BER results dict
    ber_results = {scheme["name"]: [] for scheme in schemes}

    # Print Table Header
    snr_headers = " ".join([f"{snr:6d}dB" for snr in snr_range_db])
    print("-" * 115)
    print(f" {'MODULATION SCHEME':<25} | {snr_headers}")
    print("-" * 115)

    for scheme in schemes:
        name = scheme["name"]
        mod = scheme["modulator"]

        # Modulate baseband
        symbols = mod.modulate_baseband(tx_bits)

        ber_list = []
        for snr in snr_range_db:
            noisy_symbols = apply_awgn(symbols, snr_db=float(snr), seed=seed)
            rx_bits = mod.demodulate_baseband(noisy_symbols)
            ber = calculate_ber(tx_bits, rx_bits)
            # Clip 0 BER to minimum display threshold for log plotting
            ber_list.append(max(ber, 1e-6))

        ber_results[name] = ber_list

        ber_str = " ".join([f"{b:8.2e}" if b > 1e-6 else f"{'<1e-6':>8}" for b in ber_list])
        print(f" {name:<25} | {ber_str}")

    print("-" * 115)

    # Generate Logarithmic BER vs SNR Plot
    output_dir = os.path.join("results", "digital")
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "ber_vs_snr.png")

    fig, ax = plt.subplots(figsize=(10, 7), dpi=300)
    fig.patch.set_facecolor("#0f172a")

    color_text = "#f8fafc"
    color_grid = "#334155"

    ax.set_facecolor("#1e293b")
    ax.tick_params(colors=color_text)
    ax.xaxis.label.set_color(color_text)
    ax.yaxis.label.set_color(color_text)
    ax.title.set_color(color_text)
    ax.grid(True, which="both", linestyle="--", alpha=0.4, color=color_grid)
    for spine in ax.spines.values():
        spine.set_color("#475569")

    styles = [
        {"color": "#ef4444", "marker": "o", "ls": "-"},   # Red (ASK)
        {"color": "#f59e0b", "marker": "s", "ls": "-"},   # Amber (FSK)
        {"color": "#38bdf8", "marker": "^", "ls": "-"},   # Cyan (BPSK)
        {"color": "#10b981", "marker": "d", "ls": "-"},   # Emerald (QPSK)
        {"color": "#a855f7", "marker": "v", "ls": "-"},   # Purple (8-PSK)
    ]

    for i, scheme in enumerate(schemes):
        name = scheme["name"]
        st = styles[i]
        ax.semilogy(
            snr_range_db,
            ber_results[name],
            label=name,
            color=st["color"],
            marker=st["marker"],
            linestyle=st["ls"],
            linewidth=2.0,
            markersize=6,
        )

    ax.set_title("Digital Carrier Modulation: BER vs. SNR Performance (AWGN Channel)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Signal-to-Noise Ratio (SNR in dB)", fontsize=11)
    ax.set_ylabel("Bit Error Rate (BER)", fontsize=11)
    ax.set_ylim([1e-5, 1.0])
    ax.set_xlim([0, 20])
    ax.legend(facecolor="#0f172a", labelcolor=color_text, loc="lower left", fontsize=10)

    plt.tight_layout()
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"\n[Success] BER vs SNR plot saved to: '{plot_path}'")
    print("Experiment completed cleanly!\n")


if __name__ == "__main__":
    run_ber_experiment()
