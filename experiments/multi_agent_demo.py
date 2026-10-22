"""
Multi-Agent Cognitive Wireless Intelligence Layer Demonstration Script.

Runs dynamic time-varying combat environment scenario (Normal -> Interference -> Fading -> Jamming),
orchestrating SpectrumAgent, DigitalTwin, PredictionAgent, and CyberDefenseAgent at each step,
printing structured agent evidence and rationale, and saving diagnostic plots:
  - 'results/agents/agent_risk_timeline.png'
  - 'results/agents/agent_confidence_timeline.png'
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
from src.agents.orchestrator import MultiAgentOrchestrator


def run_multi_agent_demo():
    print("=" * 90)
    print("  COGNITWIN-SDR: MULTI-AGENT COGNITIVE WIRELESS INTELLIGENCE DEMO")
    print("=" * 90)

    scenario_path = os.path.join("config", "scenarios", "dynamic_combat_environment.json")
    scenario = ScenarioEngine.load_from_file(scenario_path)

    env = VirtualRFEnvironment(scenario=scenario, sample_rate=100000.0, seed=42)
    orchestrator = MultiAgentOrchestrator(environment=env, sample_rate=100000.0)

    step_duration = 0.1
    total_time = scenario.duration_seconds
    num_steps = int(round(total_time / step_duration))

    timestamps = []
    snr_history = []
    risk_history = []
    spec_conf_history = []
    pred_conf_history = []

    print(f"\n[1] Executing Multi-Agent Pipeline over {total_time:.1f}s ({num_steps} discrete steps)...")
    print("-" * 90)
    print(f" {'TIME':<6} | {'OBSERVED MOD':<12} | {'SNR (dB)':<9} | {'ANOMALY':<16} | {'RISK':<6} | {'LEVEL':<8} | {'PROPOSED CANDIDATES'}")
    print("-" * 90)

    for step_i in range(num_steps):
        snapshot, env_state, iq = orchestrator.step(duration_seconds=step_duration)

        t_curr = snapshot.timestamp_s
        spec = snapshot.spectrum_result
        pred = snapshot.prediction_result
        defense = snapshot.defense_candidates

        timestamps.append(t_curr)
        snr_history.append(spec.snr_db)
        risk_history.append(pred.risk_score)
        spec_conf_history.append(spec.classifier_confidence)
        pred_conf_history.append(orchestrator.prediction_agent.confidence)

        if step_i % 4 == 0:
            cand_str = ", ".join(defense.candidate_strategies)
            print(
                f" {t_curr:<6.2f} | {spec.modulation:<12} | {spec.snr_db:<9.1f} | "
                f"{spec.anomaly_flag:<16} | {pred.risk_score:<6.2f} | {pred.risk_level:<8} | [{cand_str}]"
            )

    print("-" * 90)

    # Detailed Numerical Evidence Rationale
    print("\n[2] Agent Numerical Rationale & Evidence Sample (Step t = 2.0s):")
    snapshot_sample, env_sample, _ = orchestrator.step(duration_seconds=0.1)
    print(f"  • Spectrum Agent      : Observed '{snapshot_sample.spectrum_result.modulation}' at {snapshot_sample.spectrum_result.snr_db:.1f} dB SNR (Confidence: {snapshot_sample.spectrum_result.classifier_confidence * 100:.1f}%, Anomaly: '{snapshot_sample.spectrum_result.anomaly_flag}')")
    print(f"  • Prediction Agent    : Forecasted next SNR = {snapshot_sample.prediction_result.next_snr_db:.1f} dB, BER = {snapshot_sample.prediction_result.next_ber:.4f} -> Risk Score = {snapshot_sample.prediction_result.risk_score:.2f} ({snapshot_sample.prediction_result.risk_level})")
    print(f"  • Cyber Defense Agent : Rationale -> '{snapshot_sample.defense_candidates.rationale}'")
    print(f"                         Proposed Candidates -> {snapshot_sample.defense_candidates.candidate_strategies}\n")

    # Save Output Plots
    output_dir = os.path.join("results", "agents")
    os.makedirs(output_dir, exist_ok=True)

    color_text = "#f8fafc"
    color_grid = "#334155"

    # Plot 1: Risk Timeline (SNR vs. Predicted Risk Score)
    plot1_path = os.path.join(output_dir, "agent_risk_timeline.png")
    fig, ax1 = plt.subplots(figsize=(10, 5.5), dpi=300)
    fig.patch.set_facecolor("#0f172a")
    ax1.set_facecolor("#1e293b")
    ax1.tick_params(colors=color_text)
    ax1.xaxis.label.set_color(color_text)
    ax1.yaxis.label.set_color(color_text)
    ax1.title.set_color(color_text)
    ax1.grid(True, linestyle="--", alpha=0.4, color=color_grid)
    for spine in ax1.spines.values():
        spine.set_color("#475569")

    line1 = ax1.plot(timestamps, snr_history, color="#38bdf8", linewidth=2.0, marker="o", markersize=4, label="Environment SNR (dB)")
    ax1.set_xlabel("Simulation Time (Seconds)")
    ax1.set_ylabel("SNR (dB)", color="#38bdf8")

    ax2 = ax1.twinx()
    ax2.tick_params(colors=color_text)
    ax2.yaxis.label.set_color(color_text)
    line2 = ax2.plot(timestamps, risk_history, color="#ef4444", linestyle="--", linewidth=2.0, marker="s", markersize=4, label="Prediction Agent Risk Score")
    ax2.set_ylabel("Risk Score (0.0 to 1.0)", color="#ef4444")
    ax2.set_ylim(0.0, 1.05)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    plt.title("Multi-Agent Intelligence: Environment SNR vs. Predicted Risk Score", fontsize=12, fontweight="bold", color=color_text, pad=12)
    plt.tight_layout()
    plt.savefig(plot1_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    # Plot 2: Confidence Timeline
    plot2_path = os.path.join(output_dir, "agent_confidence_timeline.png")
    fig, ax = plt.subplots(figsize=(10, 5.0), dpi=300)
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")
    ax.tick_params(colors=color_text)
    ax.xaxis.label.set_color(color_text)
    ax.yaxis.label.set_color(color_text)
    ax.title.set_color(color_text)
    ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
    for spine in ax.spines.values():
        spine.set_color("#475569")

    ax.plot(timestamps, [c * 100 for c in spec_conf_history], color="#10b981", linewidth=2.0, marker="^", label="Spectrum Agent Classifier Confidence (%)")
    ax.plot(timestamps, [c * 100 for c in pred_conf_history], color="#f59e0b", linestyle="--", linewidth=2.0, marker="d", label="Prediction Agent Risk Confidence (%)")
    ax.set_xlabel("Simulation Time (Seconds)")
    ax.set_ylabel("Agent Confidence (%)")
    ax.set_ylim(0, 105)
    ax.legend(facecolor="#0f172a", labelcolor=color_text, loc="lower right")

    plt.title("Multi-Agent Intelligence Layer Confidence Timeline", fontsize=12, fontweight="bold", color=color_text, pad=12)
    plt.tight_layout()
    plt.savefig(plot2_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"[Success] Agent risk timeline plot saved to: '{plot1_path}'")
    print(f"[Success] Agent confidence timeline plot saved to: '{plot2_path}'")
    print("Multi-agent intelligence demo completed cleanly!\n")


if __name__ == "__main__":
    run_multi_agent_demo()
