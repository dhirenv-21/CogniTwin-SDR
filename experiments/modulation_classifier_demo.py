"""
AI Radio Signal & Modulation Classifier Demonstration Script.

Generates synthetic I/Q dataset, trains Random Forest model, evaluates performance on unseen test set,
saves confusion matrix and accuracy vs SNR plots, and runs live analyze_iq inference demonstrations.
"""

import os
import sys

# Ensure project root is in sys.path when script is executed directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib.pyplot as plt

from src.ai.modulation_classifier.dataset import (
    generate_dataset,
    get_train_val_test_splits,
    generate_single_signal,
    MODULATION_CLASSES,
)
from src.ai.modulation_classifier.model import train_classifier, save_model
from src.ai.modulation_classifier.evaluation import evaluate_model
from src.ai.modulation_classifier.inference import analyze_iq


def run_classifier_demo():
    print("=" * 80)
    print("  COGNITWIN-SDR: AI RADIO SIGNAL / MODULATION CLASSIFICATION LAB")
    print("=" * 80)

    sample_rate = 100000.0  # 100 kHz
    output_dir = os.path.join("results", "ai", "modulation_classifier")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Dataset Generation
    print("\n[1] Generating Synthetic Dataset Across 8 Modulation Classes and 5 SNR Levels...")
    snr_levels = [0.0, 5.0, 10.0, 15.0, 20.0]
    X, y, snrs, meta = generate_dataset(
        samples_per_class_per_snr=100,
        snr_levels=snr_levels,
        sample_rate=sample_rate,
        seed=42,
    )

    print(f"    Total Samples      : {len(y):,}")
    print(f"    Feature Vector Dim : {X.shape[1]}")
    print(f"    Classes            : {', '.join(MODULATION_CLASSES)}")

    # 2. Split Dataset (Train 70%, Val 15%, Test 15%)
    (X_tr, y_tr, snr_tr), (X_v, y_v, snr_v), (X_te, y_te, snr_te) = get_train_val_test_splits(X, y, snrs, seed=42)
    print(f"    Train Samples      : {len(y_tr):,} (70%)")
    print(f"    Val Samples        : {len(y_v):,} (15%)")
    print(f"    Test Samples       : {len(y_te):,} (15%)")

    # 3. Model Training
    print("\n[2] Training Baseline Random Forest Classifier (100 Trees)...")
    clf = train_classifier(X_tr, y_tr, n_estimators=100, random_state=42)

    model_file = os.path.join(output_dir, "rf_model.joblib")
    save_model(clf, model_file)
    print(f"    Trained model serialized to: '{model_file}'")

    # 4. Evaluation on Unseen Test Set
    print("\n[3] Evaluating Classifier on Unseen Test Set...")
    metrics = evaluate_model(clf, X_te, y_te, snr_te, output_dir=output_dir)

    print("-" * 65)
    print(f"  TEST SET OVERALL ACCURACY : {metrics['accuracy'] * 100:.2f}%")
    print(f"  TEST SET MACRO F1 SCORE   : {metrics['macro_f1']:.4f}")
    print("-" * 65)

    # 5. Live Spectrum Intelligence Inference Demo (analyze_iq)
    print("\n[4] Running Live Spectrum Intelligence Inference Demo (analyze_iq)...")
    demo_samples = [
        {"true_mod": "QPSK", "snr": 15.0},
        {"true_mod": "BPSK", "snr": 10.0},
        {"true_mod": "FM", "snr": 20.0},
        {"true_mod": "OFDM-QPSK", "snr": 15.0},
        {"true_mod": "AM-DSB-SC", "snr": 5.0},
        {"true_mod": "ASK", "snr": -10.0},  # Low SNR noise -> should trigger UNKNOWN threshold
    ]

    print("-" * 80)
    print(f" {'TRUE CLASS':<12} | {'SNR':<7} | {'PREDICTED CLASS':<15} | {'CONFIDENCE':<11} | {'DOM FREQ':<10} | {'BANDWIDTH':<10}")
    print("-" * 80)

    fig, axs = plt.subplots(2, 3, figsize=(14, 8), dpi=300)
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

    for i, item in enumerate(demo_samples):
        true_class = item["true_mod"]
        snr_val = item["snr"]

        if true_class in MODULATION_CLASSES:
            test_iq = generate_single_signal(true_class, snr_db=snr_val, sample_rate=sample_rate, n_samples=512, seed=100 + i)
        else:
            test_iq = np.random.randn(512) + 1j * np.random.randn(512)

        res = analyze_iq(test_iq, sample_rate=sample_rate, model=clf, confidence_threshold=0.60)

        pred_class = res["predicted_modulation"]
        conf = res["confidence"]
        dom_freq = res["dominant_frequency"]
        bw = res["bandwidth_hz"]

        print(f" {true_class:<12} | {snr_val:<7.1f} | {pred_class:<15} | {conf:<11.4f} | {dom_freq:<10.1f} | {bw:<10.1f}")

        # Plot I/Q Scatter
        row, col = divmod(i, 3)
        ax = axs[row, col]
        ax.scatter(test_iq.real, test_iq.imag, color="#38bdf8" if pred_class != "UNKNOWN" else "#ef4444", alpha=0.6, s=15)
        ax.set_title(f"True: {true_class} (SNR={snr_val:.0f}dB)\nPred: {pred_class} (Conf={conf:.2f})", fontsize=10, fontweight="bold")
        ax.set_xlabel("I")
        ax.set_ylabel("Q")

    plt.suptitle("CogniTwin-SDR Live Spectrum Intelligence Inference Demo", fontsize=15, fontweight="bold", color=color_text, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    demo_path = os.path.join(output_dir, "demo_predictions.png")
    plt.savefig(demo_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print("-" * 80)
    print(f"\n[Success] Demo prediction visualization saved to: '{demo_path}'")
    print("AI Modulation Classifier lab completed cleanly!\n")


if __name__ == "__main__":
    run_classifier_demo()
