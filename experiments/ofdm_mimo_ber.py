"""
OFDM & 2x2 MIMO-OFDM BER vs SNR Experiment Script.

Evaluates BER across SNR (0 dB to 20 dB) for Single-Stream OFDM and 2x2 MIMO-OFDM Zero-Forcing systems over AWGN channel.
Saves logarithmic plot to 'results/mimo/mimo_ber_vs_snr.png'.
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
from src.multicarrier.ofdm import OFDMTransmitterReceiver
from src.multicarrier.mimo import MIMO2x2System
from src.multicarrier.channel import MultipathChannel


def run_mimo_ber_experiment():
    print("=" * 80)
    print("  COGNITWIN-SDR: OFDM & 2x2 MIMO-OFDM BER VS SNR PERFORMANCE EVALUATION")
    print("=" * 80)

    n_bits = 20480  # 20,480 bits per point for fast execution in seconds
    snr_range_db = np.arange(0, 22, 2)  # 0, 2, ..., 20 dB
    seed = 42

    tx_bits = generate_bits(n_bits, seed=seed)

    print(f"\n[Parameters] Bit Count per Point: {n_bits:,} bits | SNR Range: 0 dB to 20 dB\n")

    # 1. Single-Stream OFDM Transceiver (AWGN)
    ofdm_single = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
    wave_single, num_syms_single = ofdm_single.modulate(tx_bits)

    # 2. 2x2 MIMO-OFDM System (AWGN)
    h_direct = MultipathChannel(taps=[1.0], delays=[0])
    h_zero = MultipathChannel(taps=[0.0], delays=[0])
    awgn_mimo_channels = [[h_direct, h_zero], [h_zero, h_direct]]
    mimo_awgn = MIMO2x2System(n_fft=64, cp_len=16, modulation_order=4, channels=awgn_mimo_channels)

    ber_ofdm_single = []
    ber_mimo_zf = []

    print("-" * 75)
    print(f" {'SNR (dB)':<10} | {'OFDM Single-Stream BER':<25} | {'2x2 MIMO-OFDM ZF BER':<25}")
    print("-" * 75)

    for snr in snr_range_db:
        # Single-Stream OFDM over AWGN
        from src.signal.generator import add_awgn
        noisy_wave_single = add_awgn(wave_single, snr_db=float(snr), seed=seed)
        H_ideal = np.ones(64, dtype=np.complex128)
        rx_single = ofdm_single.demodulate(noisy_wave_single, num_ofdm_symbols=num_syms_single, channel_response=H_ideal, use_cp=True)
        ber_single = calculate_ber(tx_bits, rx_single)
        ber_ofdm_single.append(max(ber_single, 1e-5))

        # 2x2 MIMO-OFDM ZF over AWGN
        rx_mimo, _, _ = mimo_awgn.transmit_and_equalize(tx_bits, snr_db=float(snr), equalizer="ZF", seed=seed)
        ber_mimo = calculate_ber(tx_bits, rx_mimo)
        ber_mimo_zf.append(max(ber_mimo, 1e-5))

        print(f" {snr:<10d} | {ber_single:<25.6e} | {ber_mimo:<25.6e}")

    print("-" * 75)

    # Save Logarithmic Plot
    output_dir = os.path.join("results", "mimo")
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "mimo_ber_vs_snr.png")

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

    ax.semilogy(snr_range_db, ber_ofdm_single, label="Single-Stream OFDM (QPSK, AWGN)", color="#38bdf8", marker="o", linewidth=2.0, markersize=6)
    ax.semilogy(snr_range_db, ber_mimo_zf, label="2x2 MIMO-OFDM (QPSK, ZF Equalizer, AWGN)", color="#10b981", marker="s", linestyle="--", linewidth=2.0, markersize=6)

    ax.set_title("OFDM & 2x2 MIMO-OFDM BER vs. SNR Performance (AWGN Channel)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Signal-to-Noise Ratio (SNR in dB)", fontsize=11)
    ax.set_ylabel("Bit Error Rate (BER)", fontsize=11)
    ax.set_ylim([1e-5, 1.0])
    ax.set_xlim([0, 20])
    ax.legend(facecolor="#0f172a", labelcolor=color_text, loc="lower left", fontsize=10)

    plt.tight_layout()
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"\n[Success] BER vs SNR plot saved to: '{plot_path}'")
    print("MIMO-OFDM BER experiment completed cleanly!\n")


if __name__ == "__main__":
    run_mimo_ber_experiment()
