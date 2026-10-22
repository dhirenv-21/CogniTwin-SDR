"""
ACWRA Adaptive Stress Evaluation Demonstration Script.

Sequentially evaluates ACWRA under three controlled stress scenarios to prove dynamic adaptation:
  - Scenario A: CLEAR CHANNEL (Low Risk R=0.10, High Confidence C=0.95)
  - Scenario B: MODERATE DEGRADATION (High Risk R=0.85, High Confidence C=1.00)
  - Scenario C: SEVERE JAMMING + AI CONFUSION (High Risk R=0.95, Low Confidence C=0.40)

Prints clear sequential decision dashboards and decision traces, and saves:
  - 'results/acwra/adaptive_stress_test.png'
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib.pyplot as plt

from src.acwra.engine import ACWRAEngine
from src.acwra.scoring import ACWRAScoringEngine
from src.agents.messages import (
    MultiAgentSnapshot,
    SpectrumIntelligenceResult,
    PredictionResult,
    DefenseCandidate,
)


class MockDigitalTwin:
    """Mock Digital Twin supplying hard-coded counterfactual sandbox results for edge-case stress testing."""

    def __init__(self, cf_results):
        self.cf_results = cf_results

    def evaluate_counterfactuals(self, candidate_strategies):
        return [r for r in self.cf_results if r["strategy"] in candidate_strategies]


def run_acwra_stress_demo():
    print("=" * 95)
    print("        COGNITWIN-SDR: ACWRA ADAPTIVE STRESS EVALUATION (PROVING ADAPTABILITY)")
    print("=" * 95)

    acwra = ACWRAEngine()
    output_dir = os.path.join("results", "acwra")
    os.makedirs(output_dir, exist_ok=True)

    candidates = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"]

    # Define the 3 Controlled Test Scenarios
    scenarios = [
        {
            "id": "A",
            "title": "SCENARIO A: CLEAR CHANNEL (Low Risk, High Confidence)",
            "snr_db": 20.0,
            "risk_score": 0.10,
            "confidence": 0.95,
            "cf_results": [
                {"strategy": "Keep Current", "modulation": "QPSK", "predicted_ber": 0.0, "predicted_throughput_bps": 80000.0},
                {"strategy": "BPSK", "modulation": "BPSK", "predicted_ber": 0.0, "predicted_throughput_bps": 50000.0},
                {"strategy": "QPSK", "modulation": "QPSK", "predicted_ber": 0.0, "predicted_throughput_bps": 140000.0},
                {"strategy": "OFDM-QPSK", "modulation": "OFDM-QPSK", "predicted_ber": 0.0, "predicted_throughput_bps": 180000.0},
            ],
        },
        {
            "id": "B",
            "title": "SCENARIO B: MODERATE DEGRADATION (High Risk, High Confidence)",
            "snr_db": 8.0,
            "risk_score": 0.85,
            "confidence": 1.00,
            "cf_results": [
                {"strategy": "Keep Current", "modulation": "QPSK", "predicted_ber": 0.2200, "predicted_throughput_bps": 0.0},
                {"strategy": "BPSK", "modulation": "BPSK", "predicted_ber": 0.0600, "predicted_throughput_bps": 0.0},
                {"strategy": "QPSK", "modulation": "QPSK", "predicted_ber": 0.0600, "predicted_throughput_bps": 0.0},
                {"strategy": "OFDM-QPSK", "modulation": "OFDM-QPSK", "predicted_ber": 0.2200, "predicted_throughput_bps": 0.0},
            ],
        },
        {
            "id": "C",
            "title": "SCENARIO C: SEVERE JAMMING WITH AI CONFUSION (High Risk, Low Confidence)",
            "snr_db": 3.0,
            "risk_score": 0.95,
            "confidence": 0.40,  # C < 0.70 activates (1 - C) * K_c penalty
            "cf_results": [
                {"strategy": "Keep Current", "modulation": "QPSK", "predicted_ber": 0.3500, "predicted_throughput_bps": 0.0},
                {"strategy": "BPSK", "modulation": "BPSK", "predicted_ber": 0.2500, "predicted_throughput_bps": 0.0},
                {"strategy": "QPSK", "modulation": "QPSK", "predicted_ber": 0.2800, "predicted_throughput_bps": 0.0},
                {"strategy": "OFDM-QPSK", "modulation": "OFDM-QPSK", "predicted_ber": 0.4000, "predicted_throughput_bps": 0.0},
            ],
        },
    ]

    all_scenario_data = []

    for sc in scenarios:
        print("\n" + "=" * 95)
        print(f"  {sc['title']}")
        print("=" * 95)
        print(f"  • Operating SNR   : {sc['snr_db']:.1f} dB")
        print(f"  • Prediction Risk : R = {sc['risk_score']:.2f}")
        print(f"  • Agent Confidence: C = {sc['confidence']*100:.1f}%\n")

        # Construct Mock Snapshot & Mock Twin
        mock_twin = MockDigitalTwin(sc["cf_results"])
        spec = SpectrumIntelligenceResult(modulation="QPSK", snr_db=sc["snr_db"], classifier_confidence=sc["confidence"])
        pred = PredictionResult(risk_score=sc["risk_score"], risk_level="HIGH" if sc["risk_score"] > 0.5 else "LOW")
        def_cand = DefenseCandidate(candidate_strategies=candidates)

        snapshot = MultiAgentSnapshot(timestamp_s=1.0, spectrum_result=spec, prediction_result=pred, defense_candidates=def_cand)

        # Run ACWRA Decision
        decision = acwra.evaluate_and_decide(snapshot, mock_twin)

        print(decision.decision_trace)

        # Record data for visualization
        sc_scores = {cs.strategy: cs.utility_score for cs in decision.candidate_scores}
        all_scenario_data.append({
            "id": sc["id"],
            "title": sc["title"],
            "winner": decision.selected_strategy,
            "scores": sc_scores,
        })

    # =========================================================================
    # VISUALIZATION PLOT: Grouped Bar Chart Across 3 Scenarios
    # =========================================================================
    plot_path = os.path.join(output_dir, "adaptive_stress_test.png")

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    fig.patch.set_facecolor("#0f172a")

    color_text = "#f8fafc"
    color_grid = "#334155"

    ax.set_facecolor("#1e293b")
    ax.tick_params(colors=color_text)
    ax.xaxis.label.set_color(color_text)
    ax.yaxis.label.set_color(color_text)
    ax.title.set_color(color_text)
    ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
    for spine in ax.spines.values():
        spine.set_color("#475569")

    x_labels = ["Scenario A\n(Clear: High Tput)", "Scenario B\n(Moderate: High Conf)", "Scenario C\n(Severe: Low Conf)"]
    x = np.arange(len(x_labels))
    width = 0.18

    strategy_colors = {
        "Keep Current": "#94a3b8",
        "BPSK": "#10b981",
        "QPSK": "#f59e0b",
        "OFDM-QPSK": "#38bdf8",
    }

    for idx, strat in enumerate(candidates):
        strat_utilities = [sc_data["scores"].get(strat, 0.0) for sc_data in all_scenario_data]
        offset_x = x + (idx - 1.5) * width
        rects = ax.bar(offset_x, strat_utilities, width, label=strat, color=strategy_colors[strat])

        for rect in rects:
            yval = rect.get_height()
            offset_y = 0.02 if yval >= 0 else -0.06
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                yval + offset_y,
                f"{yval:+.2f}",
                ha="center",
                va="bottom" if yval >= 0 else "top",
                color=color_text,
                fontsize=8,
                fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=10, fontweight="bold")
    ax.set_ylabel("Multi-Objective Utility Score U(c)", fontsize=11)
    ax.legend(facecolor="#0f172a", labelcolor=color_text, loc="upper right")

    plt.suptitle("CogniTwin-SDR ACWRA Adaptive Decision Shift Across 3 Controlled Scenarios", fontsize=13, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(plot_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print("\n" + "=" * 95)
    print(f"[Success] Adaptive stress test visual plot saved to: '{plot_path}'")
    print("ACWRA adaptive stress evaluation completed cleanly!\n")


if __name__ == "__main__":
    run_acwra_stress_demo()
