"""
RETRAIN + EVALUATE THE MODULATION CLASSIFIER ON NON-REPEATING DATA.

The Task-5 model (results/ai/modulation_classifier/rf_model.joblib) was trained only
on windows that tile a short random pattern. On genuinely non-repeating windows,
which is what a real link and the Simulink PHY produce, it labels BPSK and QPSK as
OFDM-QPSK with confidence ~0.8-0.9.

This script:
  1. trains a candidate model on the SAME 17 features with "mixed" data (one tiled +
     one non-repeating window per sample index), normalised to unit power exactly
     as analyze_iq() does at inference, with deployment-like augmentation (random
     carrier phase; Gaussian jammer on half the windows), SNR -5..30 dB;
  2. evaluates the ORIGINAL and the CANDIDATE model, as served (normalised input),
     on fresh held-out test sets (different seed): tiled, non-repeating, and
     non-repeating + impairments, per SNR and per class;
  3. writes the candidate to rf_model_mixed.joblib - the original file is never
     overwritten - plus a CSV, a Markdown report and a figure.

    python experiments/retrain_modulation_classifier.py
    python experiments/retrain_modulation_classifier.py --per-class 60 --test-per-class 40

Everything is synthetic (Python generators); no Simulink data is involved.
"""

import argparse
import csv
import json
import os
import sys
import time

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.ai.modulation_classifier.dataset import MODULATION_CLASSES, generate_dataset
from src.ai.modulation_classifier.model import load_model, save_model, train_classifier

OUT_DIR = os.path.join(project_root, "results", "ai", "modulation_classifier")
ORIGINAL = os.path.join(OUT_DIR, "rf_model.joblib")
CANDIDATE = os.path.join(OUT_DIR, "rf_model_mixed.joblib")
REPORT_DIR = os.path.join(OUT_DIR, "retrain_eval")
SNRS = [-5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 30.0]
TEST_SETS = {
    "tiled": dict(representation="tiled", augment=False),
    "stream": dict(representation="stream", augment=False),
    "stream+impaired": dict(representation="stream", augment=True),
}


def accuracy_table(model, X, y, snrs, threshold=0.60):
    """Accuracy with the inference threshold applied (below it -> UNKNOWN = wrong)."""
    proba = model.predict_proba(X)
    pred = np.asarray(model.classes_)[np.argmax(proba, axis=1)]
    pred = np.where(np.max(proba, axis=1) < threshold, "UNKNOWN", pred)
    rows = {}
    for s in sorted(set(snrs.tolist())):
        m = snrs == s
        rows[s] = float(np.mean(pred[m] == y[m]))
    per_class = {c: float(np.mean(pred[y == c] == c)) for c in MODULATION_CLASSES}
    return float(np.mean(pred == y)), rows, per_class, pred


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--per-class", type=int, default=100, help="train samples per class per SNR per representation")
    ap.add_argument("--test-per-class", type=int, default=50)
    ap.add_argument("--train-seed", type=int, default=2026)
    ap.add_argument("--test-seed", type=int, default=777)
    ap.add_argument("--check", action="store_true",
                    help="retrain in memory and compare with the committed evaluation.json; writes nothing")
    args = ap.parse_args(argv)

    if not args.check:
        os.makedirs(REPORT_DIR, exist_ok=True)
    t0 = time.time()
    X, y, s, _ = generate_dataset(args.per_class, SNRS, seed=args.train_seed, representation="mixed",
                                  normalize=True, augment=True)
    candidate = train_classifier(X, y, n_estimators=100, random_state=42)
    if not args.check:
        save_model(candidate, CANDIDATE)
    train_s = time.time() - t0

    original = load_model(ORIGINAL)
    if original is None:
        print(f"original model not found at {ORIGINAL}")
        return 2

    results = {}
    for rep, kw in TEST_SETS.items():
        Xt, yt, st, _ = generate_dataset(args.test_per_class, SNRS, seed=args.test_seed,
                                         normalize=True, **kw)
        for name, model in (("original", original), ("mixed", candidate)):
            acc, by_snr, by_cls, pred = accuracy_table(model, Xt, yt, st)
            results[(name, rep)] = {"overall": acc, "by_snr": by_snr, "by_class": by_cls}

    if args.check:
        with open(os.path.join(REPORT_DIR, "evaluation.json")) as fh:
            committed = json.load(fh)["results"]
        ok = True
        for (name, rep), r in results.items():
            ref = committed.get(f"{name}/{rep}", {}).get("overall")
            same = ref is not None and abs(ref - r["overall"]) < 1e-12
            ok &= same
            print(f"{name:>9} / {rep:<16} committed {ref}  reproduced {r['overall']:.6f}  "
                  f"{'MATCH' if same else 'DIFFER'}")
        return 0 if ok else 1

    # ---------------------------------------------------------------- outputs
    csv_path = os.path.join(REPORT_DIR, "accuracy_by_snr.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "test_representation", "snr_db", "accuracy"])
        for (name, rep), r in results.items():
            for snr, a in r["by_snr"].items():
                w.writerow([name, rep, snr, f"{a:.4f}"])
            w.writerow([name, rep, "all", f"{r['overall']:.4f}"])

    meta = {
        "train": {"representation": "mixed", "normalize": True, "augment": True,
                  "per_class_per_snr_per_rep": args.per_class,
                  "snr_levels": SNRS, "seed": args.train_seed, "n_windows": int(len(y)),
                  "seconds": round(train_s, 1)},
        "test": {"per_class_per_snr": args.test_per_class, "seed": args.test_seed,
                 "n_windows_per_representation": int(args.test_per_class * len(SNRS) * len(MODULATION_CLASSES))},
        "threshold": 0.60,
        "original_model": os.path.relpath(ORIGINAL, project_root),
        "candidate_model": os.path.relpath(CANDIDATE, project_root),
        "results": {f"{k[0]}/{k[1]}": v for k, v in results.items()},
    }
    with open(os.path.join(REPORT_DIR, "evaluation.json"), "w") as fh:
        json.dump(meta, fh, indent=2)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, rep in zip(axes, TEST_SETS):
        for name, style in (("original", "o--"), ("mixed", "s-")):
            r = results[(name, rep)]["by_snr"]
            ax.plot(list(r.keys()), list(r.values()), style, label=f"{name} model")
        ax.set_title(f"test: {rep} ({args.test_per_class}/class/SNR, 8 classes)", fontsize=10)
        ax.set_xlabel("SNR (dB)")
        ax.grid(alpha=0.3)
        ax.set_ylim(0, 1.02)
    axes[0].set_ylabel("accuracy (UNKNOWN counted wrong)")
    axes[0].legend()
    fig.suptitle("Modulation classifier: original (tiled-only) vs retrained (mixed) - synthetic data")
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "accuracy_vs_snr.png"), dpi=130)

    lines = ["# Modulation classifier retraining evaluation", "",
             "Synthetic Python data only (no Simulink). Accuracy counts below-threshold "
             "(`UNKNOWN`) predictions as wrong. All inputs are normalised to unit power, "
             "as analyze_iq() serves them. `stream+impaired` adds a random carrier phase and, "
             "on half the windows, a Gaussian jammer (power 0.05-1), so its SNR axis is the "
             "noise-only SNR; the effective SINR is lower.", "",
             f"Train: mixed representation, {len(y)} windows, seed {args.train_seed}. "
             f"Test: fresh seed {args.test_seed}, {meta['test']['n_windows_per_representation']} windows per representation.", "",
             "| model | test data | overall | " + " | ".join(f"{s:g} dB" for s in SNRS) + " |",
             "|---|---|---|" + "---|" * len(SNRS)]
    for (name, rep), r in results.items():
        lines.append(f"| {name} | {rep} | {r['overall']:.3f} | "
                     + " | ".join(f"{r['by_snr'][s]:.3f}" for s in SNRS) + " |")
    lines += ["", "Per-class accuracy:", "",
              "| model | test data | " + " | ".join(MODULATION_CLASSES) + " |",
              "|---|---|" + "---|" * len(MODULATION_CLASSES)]
    for (name, rep), r in results.items():
        lines.append(f"| {name} | {rep} | " + " | ".join(f"{r['by_class'][c]:.2f}" for c in MODULATION_CLASSES) + " |")
    with open(os.path.join(REPORT_DIR, "report.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\ncandidate saved to {CANDIDATE}; original untouched at {ORIGINAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
