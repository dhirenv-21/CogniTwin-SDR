"""
SPECTRUM AGENT EVALUATION (synthetic Python signals, as served by analyze_iq).

Independent test signals: every window has its own seed >= 1_000_000. The training
data (experiments/retrain_modulation_classifier.py) draws per-window seeds from
[0, 1_000_000), so no test window shares a generator seed with training.

Measures
  * 8-class confusion matrix, per-class precision / recall / F1, UNKNOWN rate,
    expected calibration error (ECE, 10 bins) of the reported confidence
  * blind SNR estimate (estimate_snr_blind) error vs the TRUE SINR, by signal type,
    SINR and estimator method; below-resolution fraction
  * false SNR_DROP rate of the Spectrum Agent on STATIONARY captures (no real drop)

    python experiments/spectrum_agent_eval.py [--per-cell 40]

Outputs: results/ai/spectrum_eval/ {metrics.json, report.md, confusion.png, snr_error.png}.
Synthetic, in-distribution with respect to the generator family; not field accuracy.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.agents.spectrum_agent import SpectrumAgent
from src.ai.modulation_classifier.dataset import MODULATION_CLASSES, generate_single_signal
from src.ai.modulation_classifier.inference import analyze_iq
from src.ai.modulation_classifier.model import load_model

OUT = os.path.join(project_root, "results", "ai", "spectrum_eval")
SEED_BASE = 1_000_000
SINRS = (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0)
IMPAIRMENTS = ("awgn", "block_fade", "jammer")
SNR_TYPES = ("BPSK", "QPSK", "OFDM-QPSK")


def window(mod, sinr_db, impairment, seed):
    """Unit-power clean window + impairment with a KNOWN true SINR."""
    rng = np.random.default_rng(seed)
    x = generate_single_signal(mod, 300.0, seed=seed, repeating=False)   # effectively clean
    x = x / np.sqrt(np.mean(np.abs(x) ** 2))
    n = x.size
    total = 10 ** (-sinr_db / 10)
    if impairment == "block_fade":
        h = (rng.standard_normal() + 1j * rng.standard_normal()) / np.sqrt(2)
        x = h * x                                   # SINR referenced to the received power
        total *= abs(h) ** 2
    if impairment == "jammer":
        jam, noise = 0.5 * total, 0.5 * total       # half the impairment is a Gaussian jammer
    else:
        jam, noise = 0.0, total
    y = x + np.sqrt(noise / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    if jam:
        y = y + np.sqrt(jam / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return y


def ece(conf, correct, bins=10):
    conf, correct = np.asarray(conf), np.asarray(correct, float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Spectrum Agent evaluation")
    ap.add_argument("--per-cell", type=int, default=40, help="windows per (class, SINR, impairment)")
    ap.add_argument("--out-dir", default=None, help="output folder (default: the committed results folder)")
    args = ap.parse_args(argv)
    global OUT
    if args.out_dir:
        OUT = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(project_root, args.out_dir)
    os.makedirs(OUT, exist_ok=True)
    model = load_model()
    seed = SEED_BASE

    recs = []
    for mod in MODULATION_CLASSES:
        for s in SINRS:
            for imp in IMPAIRMENTS:
                for _ in range(args.per_cell):
                    seed += 1
                    r = analyze_iq(window(mod, s, imp, seed), model=model)
                    recs.append({"true": mod, "sinr": s, "imp": imp, "pred": r["predicted_modulation"],
                                 "conf": r["confidence"], "snr_est": r["snr_db"], "method": r["snr_method"]})

    labels = list(MODULATION_CLASSES) + ["UNKNOWN"]
    cm = np.zeros((len(MODULATION_CLASSES), len(labels)), int)
    for r in recs:
        cm[MODULATION_CLASSES.index(r["true"]), labels.index(r["pred"])] += 1
    per_class = {}
    for i, c in enumerate(MODULATION_CLASSES):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i].sum() - tp
        p = tp / (tp + fp) if tp + fp else float("nan")
        rc = tp / (tp + fn) if tp + fn else float("nan")
        per_class[c] = {"precision": p, "recall": rc,
                        "f1": 2 * p * rc / (p + rc) if p and rc and (p + rc) else float("nan"),
                        "unknown_rate": cm[i, -1] / cm[i].sum()}
    acc_by = defaultdict(list)
    for r in recs:
        acc_by[(r["sinr"], r["imp"])].append(r["pred"] == r["true"])
    known = [r for r in recs if r["pred"] != "UNKNOWN"]
    calib = ece([r["conf"] for r in known], [r["pred"] == r["true"] for r in known])

    snr_rows = defaultdict(list)
    for r in recs:
        if r["true"] in SNR_TYPES:
            snr_rows[(r["true"], r["sinr"], r["imp"])].append(r)
    snr_table = []
    for (t, s, imp), rs in sorted(snr_rows.items()):
        res = [x for x in rs if x["method"] != "below_resolution"]
        err = np.array([x["snr_est"] - s for x in res])
        snr_table.append({"type": t, "sinr_db": s, "impairment": imp, "n": len(rs),
                          "resolved_frac": len(res) / len(rs),
                          "bias_db": float(err.mean()) if err.size else float("nan"),
                          "mae_db": float(np.abs(err).mean()) if err.size else float("nan")})

    # false SNR_DROP on stationary captures: the agent sees 40 consecutive windows at a fixed SINR
    false_drop = {}
    for t in SNR_TYPES:
        for s in SINRS:
            agent = SpectrumAgent()
            flags = []
            for _ in range(40):
                seed += 1
                flags.append(agent.process(window(t, s, "awgn", seed)).anomaly_flag == "SNR_DROP")
            false_drop[f"{t}@{s:g}dB"] = float(np.mean(flags[1:]))

    metrics = {"n_windows": len(recs), "seed_range": [SEED_BASE + 1, seed], "per_cell": args.per_cell,
               "overall_accuracy": float(np.mean([r["pred"] == r["true"] for r in recs])),
               "unknown_rate": float(np.mean([r["pred"] == "UNKNOWN" for r in recs])),
               "ece_known": calib, "per_class": per_class,
               "accuracy_by_sinr_impairment": {f"{s:g}dB/{i}": float(np.mean(v)) for (s, i), v in acc_by.items()},
               "confusion_labels": labels, "confusion": cm.tolist(), "snr_estimation": snr_table,
               "false_snr_drop_rate_stationary": false_drop}
    with open(os.path.join(OUT, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    lines = ["# Spectrum Agent evaluation (synthetic, as served)", "",
             f"{len(recs)} windows ({args.per_cell} per class x SINR x impairment), seeds "
             f"{SEED_BASE + 1}-{seed} (disjoint from training). Impairments: awgn, block_fade (one complex "
             "gain per window, SINR referenced to received power), jammer (half the impairment power is a "
             "Gaussian jammer).", "",
             f"Overall accuracy {metrics['overall_accuracy']:.3f}; UNKNOWN rate {metrics['unknown_rate']:.3f}; "
             f"ECE of confidence on non-UNKNOWN predictions {calib:.3f}.", "",
             "| class | precision | recall | F1 | UNKNOWN rate |", "|---|---|---|---|---|"]
    for c, v in per_class.items():
        lines.append(f"| {c} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['unknown_rate']:.3f} |")
    lines += ["", "Accuracy by SINR (rows) and impairment (columns):", "",
              "| SINR dB | " + " | ".join(IMPAIRMENTS) + " |", "|---|" + "---|" * len(IMPAIRMENTS)]
    for s in SINRS:
        lines.append(f"| {s:g} | " + " | ".join(f"{np.mean(acc_by[(s, i)]):.3f}" for i in IMPAIRMENTS) + " |")
    lines += ["", "Blind SNR estimate vs true SINR (resolved windows only):", "",
              "| type | impairment | SINR dB | resolved | bias dB | MAE dB |", "|---|---|---|---|---|---|"]
    for r in snr_table:
        lines.append(f"| {r['type']} | {r['impairment']} | {r['sinr_db']:g} | {r['resolved_frac']:.2f} | "
                     f"{r['bias_db']:+.2f} | {r['mae_db']:.2f} |")
    lines += ["", "False SNR_DROP rate of the Spectrum Agent on stationary captures (39 window pairs each):", ""]
    lines += [f"- {k}: {v:.3f}" for k, v in false_drop.items()]
    with open(os.path.join(OUT, "report.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    fig, ax = plt.subplots(figsize=(8, 6))
    norm = cm / cm.sum(axis=1, keepdims=True)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(MODULATION_CLASSES)))
    ax.set_yticklabels(MODULATION_CLASSES, fontsize=8)
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            if cm[i, j]:
                ax.text(j, i, f"{norm[i, j]:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title(f"Confusion (row-normalised), {len(recs)} synthetic windows, all SINRs/impairments", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "confusion.png"), dpi=120)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, t in zip(axes, SNR_TYPES):
        for imp in IMPAIRMENTS:
            rows = [r for r in snr_table if r["type"] == t and r["impairment"] == imp]
            ax.plot([r["sinr_db"] for r in rows], [r["bias_db"] for r in rows], "o-", label=f"{imp} bias")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_title(t)
        ax.set_xlabel("true SINR (dB)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("estimate - truth (dB), resolved windows")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "snr_error.png"), dpi=120)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
