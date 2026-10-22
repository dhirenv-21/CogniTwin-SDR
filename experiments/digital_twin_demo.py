"""
Cognitive Digital Twin State Tracking & Prediction Demonstration Script.

Simulates time-varying wireless environment, updating the Digital Twin at each step,
forecasting short-horizon trend metrics, evaluating fidelity error, and saving 'results/digital_twin/prediction_vs_actual.png'.
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
from src.digital_twin.twin import DigitalTwin


def run_digital_twin_demo():
    print("=" * 80)
    print("  COGNITWIN-SDR: COGNITIVE DIGITAL TWIN TRACKING & TREND PREDICTION LAB")
    print("=" * 80)

    scenario_path = os.path.join("config", "scenarios", "dynamic_combat_environment.json")
    scenario = ScenarioEngine.load_from_file(scenario_path)

    env = VirtualRFEnvironment(scenario=scenario, sample_rate=100000.0, seed=42)
    dt = DigitalTwin(environment=env, max_history_len=50, history_window=5)

    step_duration = 0.1
    total_time = scenario.duration_seconds
    num_steps = int(round(total_time / step_duration))

    timestamps = []
    actual_snrs = []
    pred_snrs = []
    actual_bers = []
    pred_bers = []

    print(f"\n[1] Executing Digital Twin State Tracking & Prediction over {total_time:.1f}s...")
    print("-" * 80)
    print(f" {'TIME (s)':<10} | {'ACTUAL SNR':<12} | {'PRED SNR':<12} | {'ACTUAL BER':<12} | {'PRED BER':<12} | {'STATUS':<18}")
    print("-" * 80)

    # A forecast made at step k is for step k+1, so it is scored when step k+1's
    # true state arrives. (This loop used to score it against step k's own state,
    # which the twin had just been given, so the reported MAE measured how far the
    # forecast strayed from the latest observation rather than forecast error.)
    pending_forecast = None

    for step_i in range(num_steps):
        t_curr = env.current_time_s
        env_state, _ = env.step(duration_seconds=step_duration)

        if pending_forecast is not None:
            dt.fidelity.record_step(pending_forecast[0], env_state.snr_db,
                                    pending_forecast[1], env_state.ber)

        dt_state = dt.update(env_state)
        pred = dt.predict_next(horizon_seconds=step_duration)

        timestamps.append(t_curr)
        actual_snrs.append(env_state.snr_db)
        actual_bers.append(env_state.ber)

        pred_status = pred["prediction_status"]
        if pred_status == "SUCCESS":
            p_snr = pred["next_snr_db"]
            p_ber = pred["next_ber"]
            pred_snrs.append(p_snr)
            pred_bers.append(p_ber)
            pending_forecast = (p_snr, p_ber)
        else:
            pending_forecast = None
            p_snr = env_state.snr_db
            p_ber = env_state.ber
            pred_snrs.append(p_snr)
            pred_bers.append(p_ber)

        if step_i % 5 == 0:
            print(
                f" {t_curr:<10.2f} | {env_state.snr_db:<12.1f} | {p_snr:<12.1f} | "
                f"{env_state.ber:<12.4f} | {p_ber:<12.4f} | {pred_status:<18}"
            )

    print("-" * 80)

    # Fidelity Evaluation
    mae_metrics = dt.fidelity.compute_mae()
    print(f"\n[Fidelity Evaluation]")
    print(f"  SNR Prediction MAE : {mae_metrics['mae_snr_db']:.2f} dB")
    print(f"  BER Prediction MAE : {mae_metrics['mae_ber']:.6f}\n")

    # Save Output Plot
    output_dir = os.path.join("results", "digital_twin")
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "prediction_vs_actual.png")

    fig, axs = plt.subplots(2, 1, figsize=(11, 7.5), dpi=300, sharex=True)
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

    # Panel 1: SNR Prediction vs Actual
    axs[0].plot(timestamps, actual_snrs, label="Actual Ground Truth SNR", color="#38bdf8", linewidth=2.0, marker="o", markersize=4)
    axs[0].plot(timestamps, pred_snrs, label="Digital Twin Forecast SNR", color="#f59e0b", linestyle="--", linewidth=2.0, marker="x", markersize=4)
    axs[0].set_title("Panel 1: SNR Ground Truth vs Digital Twin Forecast", fontsize=11, fontweight="bold")
    axs[0].set_ylabel("SNR (dB)")
    axs[0].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    # Panel 2: BER Prediction vs Actual
    axs[1].semilogy(timestamps, [max(b, 1e-4) for b in actual_bers], label="Actual Ground Truth BER", color="#ef4444", linewidth=2.0, marker="s", markersize=4)
    axs[1].semilogy(timestamps, [max(b, 1e-4) for b in pred_bers], label="Digital Twin Forecast BER", color="#10b981", linestyle="--", linewidth=2.0, marker="^", markersize=4)
    axs[1].set_title("Panel 2: BER Ground Truth vs Digital Twin Forecast", fontsize=11, fontweight="bold")
    axs[1].set_xlabel("Simulation Time (Seconds)")
    axs[1].set_ylabel("Bit Error Rate (BER)")
    axs[1].legend(facecolor="#0f172a", labelcolor=color_text, loc="upper left")

    plt.suptitle("CogniTwin-SDR Digital Twin Ground Truth vs Trend Forecast", fontsize=14, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"[Success] Prediction vs Actual plot saved to: '{plot_path}'")
    print("Digital twin tracking demo completed cleanly!\n")


if __name__ == "__main__":
    run_digital_twin_demo()
