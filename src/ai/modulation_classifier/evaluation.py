"""
Model Evaluation Module.

Evaluates trained classifier on unseen test set, generating confusion matrix plots,
classification reports, and Accuracy vs SNR degradation curves.
"""

import os
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

from .dataset import MODULATION_CLASSES


def evaluate_model(
    model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    snr_test: np.ndarray,
    output_dir: str = "results/ai/modulation_classifier",
) -> Dict[str, float]:
    """
    Evaluates classifier on unseen test dataset and outputs figures/reports.

    Args:
        model: Trained scikit-learn model.
        X_test: Test feature matrix.
        y_test: Test target labels.
        snr_test: SNR values for test samples.
        output_dir: Output folder path.

    Returns:
        Dict containing {'accuracy': float, 'macro_f1': float}.
    """
    os.makedirs(output_dir, exist_ok=True)

    y_pred = model.predict(X_test)
    overall_acc = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro"))

    # 1. Save Classification Report Text File
    report_str = classification_report(y_test, y_pred, labels=MODULATION_CLASSES, digits=4)
    report_path = os.path.join(output_dir, "classification_report.txt")
    with open(report_path, "w") as f:
        f.write("COGNITWIN-SDR MODULATION CLASSIFIER TEST REPORT\n")
        f.write("=" * 60 + "\n")
        f.write(f"Overall Accuracy : {overall_acc * 100:.2f}%\n")
        f.write(f"Macro F1 Score   : {macro_f1:.4f}\n")
        f.write("-" * 60 + "\n\n")
        f.write(report_str)

    # 2. Generate Confusion Matrix Plot
    cm = confusion_matrix(y_test, y_pred, labels=MODULATION_CLASSES)
    cm_norm = cm.astype("float") / (cm.sum(axis=1)[:, np.newaxis] + 1e-12)

    fig, ax = plt.subplots(figsize=(9, 7.5), dpi=300)
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    im = ax.imshow(cm_norm, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)

    color_text = "#f8fafc"
    ax.set_xticks(np.arange(len(MODULATION_CLASSES)))
    ax.set_yticks(np.arange(len(MODULATION_CLASSES)))
    ax.set_xticklabels(MODULATION_CLASSES, rotation=45, ha="right", color=color_text)
    ax.set_yticklabels(MODULATION_CLASSES, color=color_text)
    ax.tick_params(colors=color_text)

    # Annotate cell values
    for i in range(len(MODULATION_CLASSES)):
        for j in range(len(MODULATION_CLASSES)):
            val = cm_norm[i, j]
            ax.text(
                j,
                i,
                f"{val:.2f}",
                ha="center",
                va="center",
                color="white" if val > 0.5 else "black",
                fontsize=9,
            )

    ax.set_title("Modulation Classifier: Confusion Matrix (Test Set)", fontsize=13, fontweight="bold", color=color_text, pad=12)
    ax.set_xlabel("Predicted Class", fontsize=11, color=color_text)
    ax.set_ylabel("True Class", fontsize=11, color=color_text)
    plt.tight_layout()

    cm_path = os.path.join(output_dir, "confusion_matrix.png")
    plt.savefig(cm_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    # 3. Generate Accuracy vs SNR Curve
    unique_snrs = np.sort(np.unique(snr_test))
    acc_per_snr = []

    for snr_val in unique_snrs:
        mask = snr_test == snr_val
        if np.sum(mask) > 0:
            acc_val = accuracy_score(y_test[mask], y_pred[mask])
            acc_per_snr.append(acc_val)
        else:
            acc_per_snr.append(0.0)

    fig, ax = plt.subplots(figsize=(8.5, 6), dpi=300)
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    color_grid = "#334155"
    ax.tick_params(colors=color_text)
    ax.xaxis.label.set_color(color_text)
    ax.yaxis.label.set_color(color_text)
    ax.title.set_color(color_text)
    ax.grid(True, linestyle="--", alpha=0.4, color=color_grid)
    for spine in ax.spines.values():
        spine.set_color("#475569")

    ax.plot(unique_snrs, [a * 100 for a in acc_per_snr], color="#38bdf8", marker="o", linewidth=2.0, markersize=7, label="Random Forest Accuracy")
    ax.set_title("Classification Accuracy vs. SNR Level", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Signal-to-Noise Ratio (SNR in dB)", fontsize=11)
    ax.set_ylabel("Classification Accuracy (%)", fontsize=11)
    ax.set_ylim([0, 105])
    ax.set_xticks(unique_snrs)
    ax.legend(facecolor="#0f172a", labelcolor=color_text, loc="lower right")

    plt.tight_layout()
    snr_path = os.path.join(output_dir, "accuracy_vs_snr.png")
    plt.savefig(snr_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    return {"accuracy": overall_acc, "macro_f1": macro_f1}
