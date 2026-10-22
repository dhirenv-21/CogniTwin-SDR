"""
2x2 MIMO Spatial Multiplexing Demonstration Script.

Generates before and after Zero-Forcing (ZF) equalization I/Q constellation diagrams for Stream 1 and Stream 2,
saving 'results/mimo/mimo_constellations.png'.
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib.pyplot as plt

from src.modulation.digital import generate_bits, calculate_ber
from src.multicarrier.mimo import MIMO2x2System


def run_mimo_demo():
    print("=" * 75)
    print("  COGNITWIN-SDR: 2x2 MIMO SPATIAL MULTIPLEXING & ZF EQUALIZATION LAB")
    print("=" * 75)

    n_bits = 5120  # 20 OFDM symbols per stream
    snr_db = 16.0
    seed = 42

    tx_bits = generate_bits(n_bits, seed=seed)

    mimo = MIMO2x2System(n_fft=64, cp_len=16, modulation_order=4)
    rx_bits, s1_iq, s2_iq = mimo.transmit_and_equalize(tx_bits, snr_db=snr_db, equalizer="ZF", seed=seed)

    ber = calculate_ber(tx_bits, rx_bits)

    print(f"\n[MIMO Parameters] 2 TX x 2 RX Spatial Multiplexing | QPSK | SNR = {snr_db:.1f} dB")
    print(f"  Total Transmitted Bits : {n_bits:,}")
    print(f"  Recovered BER          : {ber:.6f}\n")

    # Generate Constellation Figure
    output_dir = os.path.join("results", "mimo")
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "mimo_constellations.png")

    fig, axs = plt.subplots(1, 2, figsize=(12, 5.5), dpi=300)
    fig.patch.set_facecolor("#0f172a")

    color_text = "#f8fafc"
    color_grid = "#334155"

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

    # Stream 1 Constellation
    axs[0].scatter(s1_iq.real, s1_iq.imag, color="#38bdf8", s=25, alpha=0.6, label="ZF Equalized Stream 1")
    axs[0].set_title(f"Stream 1 Constellation (Equalized, SNR={snr_db:.0f} dB)", fontsize=11, fontweight="bold")
    axs[0].set_xlabel("In-Phase (I)")
    axs[0].set_ylabel("Quadrature (Q)")
    axs[0].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    # Stream 2 Constellation
    axs[1].scatter(s2_iq.real, s2_iq.imag, color="#10b981", s=25, alpha=0.6, label="ZF Equalized Stream 2")
    axs[1].set_title(f"Stream 2 Constellation (Equalized, SNR={snr_db:.0f} dB)", fontsize=11, fontweight="bold")
    axs[1].set_xlabel("In-Phase (I)")
    axs[1].set_ylabel("Quadrature (Q)")
    axs[1].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    plt.suptitle("CogniTwin-SDR: 2x2 MIMO Spatial Multiplexing Equalized Constellations", fontsize=14, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"[Success] 2x2 MIMO constellation plot saved to: '{plot_path}'")
    print("MIMO demo completed cleanly!\n")


if __name__ == "__main__":
    run_mimo_demo()
