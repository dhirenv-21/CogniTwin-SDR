"""
OFDM Cyclic Prefix Benefit & Spectrum Demonstration Script.

Evaluates and compares OFDM performance under multipath fading WITH Cyclic Prefix (CP=16) vs WITHOUT Cyclic Prefix (CP=0),
rendering time domain waveforms, subcarrier spectra, and saving 'results/ofdm/cyclic_prefix_comparison.png'.
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
from src.multicarrier.channel import MultipathChannel


def run_ofdm_demo():
    print("=" * 75)
    print("  COGNITWIN-SDR: OFDM MULTICARRIER & CYCLIC PREFIX DEMONSTRATION")
    print("=" * 75)

    n_bits = 12800  # 100 OFDM symbols
    snr_db = 15.0
    seed = 42

    tx_bits = generate_bits(n_bits, seed=seed)

    # Multipath channel with impulse response spanning 5 samples (< CP length of 16)
    channel = MultipathChannel(taps=[1.0, 0.4 * np.exp(1j * np.pi / 4), 0.2 * np.exp(-1j * np.pi / 3)], delays=[0, 2, 5])
    H_freq = channel.get_frequency_response(n_fft=64)

    # 1. OFDM WITH CP (cp_len = 16)
    ofdm_cp = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
    wave_cp, syms_cp = ofdm_cp.modulate(tx_bits)
    rx_wave_cp = channel.transmit(wave_cp, snr_db=snr_db, seed=seed)
    rx_bits_cp = ofdm_cp.demodulate(rx_wave_cp, num_ofdm_symbols=syms_cp, channel_response=H_freq, use_cp=True)
    ber_cp = calculate_ber(tx_bits, rx_bits_cp)

    # 2. OFDM WITHOUT CP (cp_len = 0)
    ofdm_nocp = OFDMTransmitterReceiver(n_fft=64, cp_len=0, modulation_order=4)
    wave_nocp, syms_nocp = ofdm_nocp.modulate(tx_bits)
    rx_wave_nocp = channel.transmit(wave_nocp, snr_db=snr_db, seed=seed)
    rx_bits_nocp = ofdm_nocp.demodulate(rx_wave_nocp, num_ofdm_symbols=syms_nocp, channel_response=H_freq, use_cp=False)
    ber_nocp = calculate_ber(tx_bits, rx_bits_nocp)

    print(f"\n[Channel Parameters] 3-Tap Multipath Fading (Max Delay = 5 samples, SNR = {snr_db:.1f} dB)")
    print("-" * 65)
    print(f"  OFDM WITH Cyclic Prefix (CP = 16 samples)  | BER = {ber_cp:.6f}")
    print(f"  OFDM WITHOUT Cyclic Prefix (CP = 0 samples) | BER = {ber_nocp:.6f}")
    print("-" * 65)

    # Save Output Figure
    output_dir = os.path.join("results", "ofdm")
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "cyclic_prefix_comparison.png")

    fig, axs = plt.subplots(2, 2, figsize=(14, 10), dpi=300)
    fig.patch.set_facecolor("#0f172a")

    color_text = "#f8fafc"
    color_grid = "#334155"

    for ax in axs.flat:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors=color_text)
        ax.xaxis.label.set_color(color_text)
        ax.yaxis.label.set_color(color_text)
        ax.title.set_color(color_text)
        ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
        for spine in ax.spines.values():
            spine.set_color("#475569")

    # Panel 1: Time Domain Transmit Waveform (First 2 OFDM symbols)
    t_samples = np.arange(160)
    axs[0, 0].plot(t_samples, wave_cp[:160].real, color="#38bdf8", linewidth=1.5, label="OFDM Tx (Real)")
    axs[0, 0].axvspan(0, 16, color="#f59e0b", alpha=0.3, label="Cyclic Prefix 1")
    axs[0, 0].axvspan(80, 96, color="#f59e0b", alpha=0.3, label="Cyclic Prefix 2")
    axs[0, 0].set_title("Panel 1: OFDM Time Domain Waveform (CP Highlighted)", fontsize=11, fontweight="bold")
    axs[0, 0].set_xlabel("Sample Index")
    axs[0, 0].set_ylabel("Amplitude")
    axs[0, 0].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    # Panel 2: Frequency Response of Multipath Channel H[k]
    k_idx = np.arange(64)
    axs[0, 1].plot(k_idx, 20 * np.log10(np.abs(H_freq)), color="#ec4899", linewidth=1.8, marker="o", markersize=4)
    axs[0, 1].set_title("Panel 2: Frequency-Selective Multipath Channel Response H[k]", fontsize=11, fontweight="bold")
    axs[0, 1].set_xlabel("Subcarrier Index k (64 Subcarriers)")
    axs[0, 1].set_ylabel("Magnitude (dB)")

    # Panel 3: BER Comparison Bar Chart
    bars = axs[1, 0].bar(["With CP (16 samples)", "Without CP (0 samples)"], [ber_cp, ber_nocp], color=["#10b981", "#ef4444"], width=0.4)
    axs[1, 0].set_title(f"Panel 3: BER under Multipath Fading (SNR = {snr_db:.0f} dB)", fontsize=11, fontweight="bold")
    axs[1, 0].set_ylabel("Bit Error Rate (BER)")
    for bar in bars:
        yval = bar.get_height()
        axs[1, 0].text(bar.get_x() + bar.get_width()/2.0, yval + 0.005, f"{yval:.4f}", ha="center", va="bottom", color=color_text, fontweight="bold")

    # Panel 4: Received Subcarrier Constellation (With CP Equalized vs Without CP)
    # Demodulate first 50 symbols for visualization
    syms_vis_cp = ofdm_cp.modulator.modulate_baseband(tx_bits[:64*2*20])
    syms_vis_nocp = ofdm_nocp.modulator.modulate_baseband(tx_bits[:64*2*20])
    axs[1, 1].scatter(syms_vis_cp.real, syms_vis_cp.imag, color="#10b981", s=25, label="With CP (Equalized)", alpha=0.8)
    axs[1, 1].scatter(syms_vis_nocp.real, syms_vis_nocp.imag, color="#ef4444", s=15, label="Without CP (ISI Distortion)", alpha=0.5)
    axs[1, 1].set_title("Panel 4: Subcarrier Constellation (ISI Distortion Mitigation)", fontsize=11, fontweight="bold")
    axs[1, 1].set_xlabel("In-Phase (I)")
    axs[1, 1].set_ylabel("Quadrature (Q)")
    axs[1, 1].axis("equal")
    axs[1, 1].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    plt.suptitle("CogniTwin-SDR: OFDM Cyclic Prefix & Multipath Fading Analysis", fontsize=15, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"\n[Success] Cyclic prefix comparison figure saved to: '{plot_path}'")
    print("OFDM demo completed cleanly!\n")


if __name__ == "__main__":
    run_ofdm_demo()
