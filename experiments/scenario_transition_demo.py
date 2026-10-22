"""
Dynamic Scenario Transition Demonstration Script.

Simulates time-varying wireless combat environment (Normal -> Interference -> Fading -> Severe Jamming),
tracking metrics over time and saving a 3-panel plot to 'results/virtual_rf/scenario_transition.png'.
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
from src.virtual_rf.scenario import ScenarioEngine


def run_scenario_transition_demo():
    print("=" * 80)
    print("  COGNITWIN-SDR: DYNAMIC SCENARIO TRANSITION DEMONSTRATION")
    print("=" * 80)

    scenario_path = os.path.join("config", "scenarios", "dynamic_combat_environment.json")
    scenario = ScenarioEngine.load_from_file(scenario_path)

    env = VirtualRFEnvironment(scenario=scenario, sample_rate=100000.0, seed=42)

    step_duration = 0.1
    total_time = scenario.duration_seconds
    num_steps = int(round(total_time / step_duration))

    timestamps = []
    snr_history = []
    ber_history = []
    interf_history = []
    loss_history = []

    print(f"\n[1] Stepping Virtual RF Environment over {total_time:.1f}s ({num_steps} discrete steps)...")
    print("-" * 75)
    print(f" {'TIME (s)':<10} | {'CHANNEL':<12} | {'SNR (dB)':<10} | {'INTERF POWER':<14} | {'BER':<10} | {'LOSS':<8}")
    print("-" * 75)

    for step_i in range(num_steps):
        t_current = env.current_time_s
        state, _ = env.step(duration_seconds=step_duration)

        timestamps.append(t_current)
        snr_history.append(state.snr_db)
        ber_history.append(state.ber)
        interf_history.append(state.interference_power)
        loss_history.append(state.packet_loss)

        if step_i % 5 == 0:
            print(
                f" {t_current:<10.2f} | {state.channel_type:<12} | {state.snr_db:<10.1f} | "
                f"{state.interference_power:<14.2f} | {state.ber:<10.4f} | {state.packet_loss * 100:<7.1f}%"
            )

    print("-" * 75)

    # Save 3-panel plot
    output_dir = os.path.join("results", "virtual_rf")
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "scenario_transition.png")

    fig, axs = plt.subplots(3, 1, figsize=(11, 9), dpi=300, sharex=True)
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
        for spine in ax.spines.values():
            spine.set_color("#475569")

    # Panel 1: SNR Over Time
    axs[0].plot(timestamps, snr_history, color="#38bdf8", linewidth=2.0, marker="o", markersize=4)
    axs[0].set_title("Panel 1: Signal-to-Noise Ratio (SNR) Over Time", fontsize=11, fontweight="bold")
    axs[0].set_ylabel("SNR (dB)")
    axs[0].axvspan(0.0, 1.0, color="#10b981", alpha=0.15, label="Normal QPSK")
    axs[0].axvspan(1.0, 2.0, color="#f59e0b", alpha=0.15, label="Narrowband Interf")
    axs[0].axvspan(2.0, 3.0, color="#ec4899", alpha=0.15, label="Rayleigh Fading")
    axs[0].axvspan(3.0, 4.0, color="#ef4444", alpha=0.15, label="Severe Jamming")
    axs[0].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right", fontsize=8)

    # Panel 2: BER Over Time
    axs[1].semilogy(timestamps, [max(b, 1e-4) for b in ber_history], color="#ef4444", linewidth=2.0, marker="s", markersize=4)
    axs[1].set_title("Panel 2: Bit Error Rate (BER) Over Time (Log Scale)", fontsize=11, fontweight="bold")
    axs[1].set_ylabel("Bit Error Rate (BER)")

    # Panel 3: Interference Power Over Time
    axs[2].plot(timestamps, interf_history, color="#f59e0b", linewidth=2.0, marker="^", markersize=4)
    axs[2].set_title("Panel 3: Jamming / Interference Power Over Time", fontsize=11, fontweight="bold")
    axs[2].set_xlabel("Simulation Time (Seconds)")
    axs[2].set_ylabel("Power")

    plt.suptitle("CogniTwin-SDR Dynamic Scenario Transition (Normal -> Interference -> Fading -> Jamming)", fontsize=14, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"\n[Success] Scenario transition plot saved to: '{plot_path}'")
    print("Virtual RF scenario transition demo completed cleanly!\n")


if __name__ == "__main__":
    run_scenario_transition_demo()
