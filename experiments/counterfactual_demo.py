"""
Counterfactual Sandbox Strategy Evaluation Demonstration Script (Severe vs. Moderate Conditions).

Evaluates candidate strategies under both Severe Jamming (SNR = 3.0 dB) and Moderate Interference (SNR = 8.0 dB)
conditions in the isolated counterfactual sandbox without clock leakage, prints terminal comparison tables,
saves text report to 'results/digital_twin/counterfactual_moderate.txt', and saves a 2x2 comparison plot to
'results/digital_twin/counterfactual_comparison.png'.
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib.pyplot as plt

from src.virtual_rf.environment import VirtualRFEnvironment
from src.digital_twin.twin import DigitalTwin
from src.digital_twin.state import DigitalTwinState


def run_counterfactual_demo():
    print("=" * 85)
    print("  COGNITWIN-SDR: COUNTERFACTUAL SANDBOX EVALUATION (SEVERE VS. MODERATE)")
    print("=" * 85)

    env = VirtualRFEnvironment(seed=42)
    dt = DigitalTwin(environment=env)
    initial_clock = env.current_time_s

    output_dir = os.path.join("results", "digital_twin")
    os.makedirs(output_dir, exist_ok=True)
    report_file = os.path.join(output_dir, "counterfactual_moderate.txt")

    candidate_strategies = ["Keep Current (QPSK)", "BPSK", "QPSK", "OFDM-QPSK"]

    report_lines = []
    report_lines.append("COGNITWIN-SDR: COUNTERFACTUAL SANDBOX EVALUATION REPORT")
    report_lines.append("=" * 80 + "\n")

    # =========================================================================
    # EVALUATION BLOCK 1: SEVERE JAMMING SCENARIO
    # =========================================================================
    severe_state = DigitalTwinState(
        timestamp_s=2.5,
        modulation="QPSK",
        snr_db=3.0,
        ber=0.15,
        interference_power=2.5,
        threat_condition="BROADBAND_JAMMING",
        channel_type="rayleigh",
        throughput_bps=0.0,
    )
    dt.state = severe_state

    print("\n[BLOCK 1] Frozen Environment State: SEVERE BROADBAND JAMMING")
    print(f"    Modulation: {severe_state.modulation} | SNR: {severe_state.snr_db:.1f} dB | Interf Power: {severe_state.interference_power:.2f} | Channel: {severe_state.channel_type}")

    severe_results = dt.evaluate_counterfactuals(candidate_strategies=candidate_strategies)

    print("-" * 85)
    print(f" {'CANDIDATE STRATEGY':<22} | {'PRED BER':<12} | {'PKT LOSS':<12} | {'THROUGHPUT':<16} | {'LATENCY':<12}")
    print("-" * 85)

    report_lines.append("1. EVALUATION BLOCK 1: SEVERE BROADBAND JAMMING (SNR = 3.0 dB, Interf Power = 2.5)")
    report_lines.append("-" * 80)
    report_lines.append(f" {'STRATEGY':<22} | {'PRED BER':<12} | {'PKT LOSS':<12} | {'THROUGHPUT':<16} | {'LATENCY':<12}")
    report_lines.append("-" * 80)

    severe_names = []
    severe_bers = []
    severe_tputs = []

    for item in severe_results:
        strat = item["strategy"]
        ber = item["predicted_ber"]
        loss = item["predicted_packet_loss"]
        tput_kbps = item["predicted_throughput_bps"] / 1000.0
        lat = item["predicted_latency_ms"]

        severe_names.append(strat)
        severe_bers.append(ber)
        severe_tputs.append(tput_kbps)

        line = f" {strat:<22} | {ber:<12.4f} | {loss * 100:<11.1f}% | {tput_kbps:<13.1f} kbps | {lat:<10.1f} ms"
        print(line)
        report_lines.append(line)

    print("-" * 85)
    report_lines.append("\n")

    # =========================================================================
    # EVALUATION BLOCK 2: MODERATE INTERFERENCE SCENARIO
    # =========================================================================
    moderate_state = DigitalTwinState(
        timestamp_s=1.5,
        modulation="QPSK",
        snr_db=8.0,
        ber=0.02,
        interference_power=0.4,
        threat_condition="NARROWBAND_JAMMING",
        channel_type="awgn",
        throughput_bps=150000.0,
    )
    dt.state = moderate_state

    print("\n[BLOCK 2] Frozen Environment State: MODERATE NARROWBAND INTERFERENCE")
    print(f"    Modulation: {moderate_state.modulation} | SNR: {moderate_state.snr_db:.1f} dB | Interf Power: {moderate_state.interference_power:.2f} | Channel: {moderate_state.channel_type}")

    moderate_results = dt.evaluate_counterfactuals(candidate_strategies=candidate_strategies)

    print("-" * 85)
    print(f" {'CANDIDATE STRATEGY':<22} | {'PRED BER':<12} | {'PKT LOSS':<12} | {'THROUGHPUT':<16} | {'LATENCY':<12}")
    print("-" * 85)

    report_lines.append("2. EVALUATION BLOCK 2: MODERATE INTERFERENCE (SNR = 8.0 dB, Interf Power = 0.4)")
    report_lines.append("-" * 80)
    report_lines.append(f" {'STRATEGY':<22} | {'PRED BER':<12} | {'PKT LOSS':<12} | {'THROUGHPUT':<16} | {'LATENCY':<12}")
    report_lines.append("-" * 80)

    mod_names = []
    mod_bers = []
    mod_tputs = []

    for item in moderate_results:
        strat = item["strategy"]
        ber = item["predicted_ber"]
        loss = item["predicted_packet_loss"]
        tput_kbps = item["predicted_throughput_bps"] / 1000.0
        lat = item["predicted_latency_ms"]

        mod_names.append(strat)
        mod_bers.append(ber)
        mod_tputs.append(tput_kbps)

        line = f" {strat:<22} | {ber:<12.4f} | {loss * 100:<11.1f}% | {tput_kbps:<13.1f} kbps | {lat:<10.1f} ms"
        print(line)
        report_lines.append(line)

    print("-" * 85)
    report_lines.append("\n")

    # =========================================================================
    # CLOCK ISOLATION VERIFICATION
    # =========================================================================
    assert env.current_time_s == initial_clock, "CRITICAL ERROR: Counterfactual sandbox leaked clock advancement!"
    print(f"\n[Verification] Counterfactual Sandbox Clock Isolation Confirmed (Clock = {env.current_time_s:.2f} s).")
    report_lines.append(f"SANDBOX ISOLATION VERIFICATION: Environment clock = {env.current_time_s:.2f} s (0.0s leaked).\n")

    # Write report file
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"[Success] Text report written to: '{report_file}'")

    # =========================================================================
    # VISUAL COMPARISON PLOT (2x2 Grid)
    # =========================================================================
    plot_path = os.path.join(output_dir, "counterfactual_comparison.png")

    fig, axs = plt.subplots(2, 2, figsize=(14, 10), dpi=300)
    fig.patch.set_facecolor("#0f172a")

    color_text = "#f8fafc"
    color_grid = "#334155"
    bar_colors = ["#ef4444", "#10b981", "#f59e0b", "#38bdf8"]

    for ax in axs.flat:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors=color_text)
        ax.xaxis.label.set_color(color_text)
        ax.yaxis.label.set_color(color_text)
        ax.title.set_color(color_text)
        ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
        for spine in ax.spines.values():
            spine.set_color("#475569")

    # Panel 1: Severe Jamming - Predicted BER
    bars1 = axs[0, 0].bar(severe_names, severe_bers, color=bar_colors, width=0.45)
    axs[0, 0].set_title("Severe Jamming (SNR=3dB): Predicted BER", fontsize=11, fontweight="bold")
    axs[0, 0].set_ylabel("Predicted BER")
    axs[0, 0].tick_params(axis="x", rotation=12)
    for bar in bars1:
        yval = bar.get_height()
        axs[0, 0].text(bar.get_x() + bar.get_width()/2.0, yval + 0.005, f"{yval:.4f}", ha="center", va="bottom", color=color_text, fontsize=8, fontweight="bold")

    # Panel 2: Moderate Interference - Predicted BER
    bars2 = axs[0, 1].bar(mod_names, mod_bers, color=bar_colors, width=0.45)
    axs[0, 1].set_title("Moderate Interference (SNR=8dB): Predicted BER", fontsize=11, fontweight="bold")
    axs[0, 1].set_ylabel("Predicted BER")
    axs[0, 1].tick_params(axis="x", rotation=12)
    for bar in bars2:
        yval = bar.get_height()
        axs[0, 1].text(bar.get_x() + bar.get_width()/2.0, yval + 0.005, f"{yval:.4f}", ha="center", va="bottom", color=color_text, fontsize=8, fontweight="bold")

    # Panel 3: Severe Jamming - Predicted Throughput
    bars3 = axs[1, 0].bar(severe_names, severe_tputs, color=bar_colors, width=0.45)
    axs[1, 0].set_title("Severe Jamming (SNR=3dB): Throughput (kbps)", fontsize=11, fontweight="bold")
    axs[1, 0].set_ylabel("Throughput (kbps)")
    axs[1, 0].set_ylim(0, 200.0)
    axs[1, 0].tick_params(axis="x", rotation=12)
    for bar in bars3:
        yval = bar.get_height()
        axs[1, 0].text(bar.get_x() + bar.get_width()/2.0, yval + 5.0, f"{yval:.1f}k", ha="center", va="bottom", color=color_text, fontsize=8, fontweight="bold")

    # Panel 4: Moderate Interference - Predicted Throughput
    bars4 = axs[1, 1].bar(mod_names, mod_tputs, color=bar_colors, width=0.45)
    axs[1, 1].set_title("Moderate Interference (SNR=8dB): Throughput (kbps)", fontsize=11, fontweight="bold")
    axs[1, 1].set_ylabel("Throughput (kbps)")
    axs[1, 1].set_ylim(0, 200.0)
    axs[1, 1].tick_params(axis="x", rotation=12)
    for bar in bars4:
        yval = bar.get_height()
        axs[1, 1].text(bar.get_x() + bar.get_width()/2.0, yval + 5.0, f"{yval:.1f}k", ha="center", va="bottom", color=color_text, fontsize=8, fontweight="bold")

    plt.suptitle("CogniTwin-SDR Counterfactual Strategy Evaluation: Severe vs. Moderate Scenario", fontsize=14, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"[Success] Comparison plot saved to: '{plot_path}'")
    print("Task 7.1 counterfactual experiment completed cleanly!\n")


if __name__ == "__main__":
    run_counterfactual_demo()
