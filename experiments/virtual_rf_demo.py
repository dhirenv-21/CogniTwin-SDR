"""
Virtual RF Environment End-to-End Integration Demo.

Runs 1-second simulation step, extracts observe_iq(), passes I/Q samples into Task 5 analyze_iq() ML classifier,
and compares AI predicted modulation against true environment state.
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.virtual_rf.environment import VirtualRFEnvironment
from src.virtual_rf.scenario import ScenarioEngine
from src.ai.modulation_classifier.inference import analyze_iq


def run_virtual_rf_demo():
    print("=" * 80)
    print("  COGNITWIN-SDR: VIRTUAL RF ENVIRONMENT & ML CLASSIFIER INTEGRATION")
    print("=" * 80)

    # Load Clear Channel Scenario (QPSK at 20 dB SNR)
    scenario_path = os.path.join("config", "scenarios", "clear_channel.json")
    scenario = ScenarioEngine.load_from_file(scenario_path)

    env = VirtualRFEnvironment(scenario=scenario, sample_rate=100000.0, seed=42)

    print(f"\n[1] Initializing Virtual RF Environment (Scenario: '{scenario.name}')...")
    print(f"    Initial State Timestamp : {env.current_time_s:.2f} s")
    print(f"    Target Modulation       : {env.current_state.modulation}")
    print(f"    Target SNR              : {env.current_state.snr_db:.1f} dB")

    # Step 1-second simulation clock
    print("\n[2] Executing step(duration_seconds=1.0) Discrete Clock Advancement...")
    state, iq_samples = env.step(duration_seconds=1.0)

    print(f"    New Environment Time    : {env.current_time_s:.2f} s")
    print(f"    Generated I/Q Samples   : {len(iq_samples):,}")
    print(f"    Calculated BER          : {state.ber:.6f}")
    print(f"    Calculated Packet Loss  : {state.packet_loss * 100:.2f}%")
    print(f"    Calculated Latency      : {state.latency_ms:.2f} ms")

    # Extract observe_iq() and observe_state()
    observed_state = env.observe_state()
    observed_iq = env.observe_iq()

    # Pass observed I/Q into Task 5 ML Classifier (analyze_iq)
    print("\n[3] Passing observe_iq() into Task 5 Spectrum Intelligence Engine (analyze_iq)...")
    ml_result = analyze_iq(observed_iq[:512], sample_rate=100000.0, confidence_threshold=0.60)

    print("-" * 75)
    print(f"  ENVIRONMENT TRUE MODULATION : {observed_state.modulation}")
    print(f"  AI PREDICTED MODULATION    : {ml_result['predicted_modulation']}")
    print(f"  AI CLASSIFICATION CONFIDENCE: {ml_result['confidence'] * 100:.2f}%")
    print(f"  ESTIMATED SNR               : {ml_result['snr_db']:.2f} dB")
    print(f"  DOMINANT FREQUENCY          : {ml_result['dominant_frequency']:.1f} Hz")
    print(f"  BANDWIDTH                   : {ml_result['bandwidth_hz']:.1f} Hz")
    print("-" * 75)

    assert ml_result["predicted_modulation"] == observed_state.modulation, "AI prediction mismatch in clear channel."
    print("\n[Success] End-to-end Virtual RF environment & ML classifier pipeline verified!\n")


if __name__ == "__main__":
    run_virtual_rf_demo()
