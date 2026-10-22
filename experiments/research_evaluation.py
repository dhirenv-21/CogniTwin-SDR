"""
RESEARCH EVALUATION REPORT - built ONLY from saved experiment outputs.

Reads (never regenerates):
  simulink/results/baseline/baseline_results.csv                  REAL Simulink v3 exports
  results/ai/spectrum_eval/metrics.json                           synthetic signals
  results/ai/modulation_classifier/retrain_eval/evaluation.json   synthetic signals
  results/digital_twin/forecast_eval/{forecast_metrics,alternatives}.csv   virtual RF
  results/evaluation/closed_loop/{run_20261022_v1, repro_of_run_20261022_v1, cl2_20261022}/
  simulink/results/campaign_report/results_fixture.csv            Python fixtures

Writes results/evaluation/RESEARCH_EVALUATION.md (+ figure). Every section states its
source files and data class. Run ids are fixed below, not taken from LATEST, so the
report cannot silently switch to a different run.

    python experiments/research_evaluation.py
"""

import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(project_root, "results", "evaluation")
CL = os.path.join(project_root, "results", "evaluation", "closed_loop")
CL1, CL1_REPRO, CL2 = "run_20261022_v1", "repro_of_run_20261022_v1", "cl2_20261022"


def rel(p):
    return os.path.relpath(p, project_root).replace("\\", "/")


def read_csv(p):
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


def section_simulink(lines):
    p = os.path.join(project_root, "simulink", "results", "baseline", "baseline_results.csv")
    if not os.path.exists(p):
        lines += ["## 1. Physical layer (real Simulink)", "", "_No baseline_results.csv._", ""]
        return
    rows = [r for r in read_csv(p) if r["modulation"] not in ("-", "")]
    v = Counter(r["verdict"] for r in read_csv(p))
    lines += ["## 1. Physical layer — REAL Simulink exports, HISTORICAL v3 model", "",
              f"Source: `{rel(p)}` (MATLAB R2025a, 2026-08-17, `cognitwin_sdr_phy.slx` v3). "
              f"{len(rows)} QPSK runs; verdicts in the file: {dict(v)}. Measured BER follows "
              "`Q(sqrt(SINR))` at the SINR measured from the logged arrays (figure).", "",
              "Caveats: (1) v3 noise was identical for every seed (max |diff| = 0 between seeds 11/23/37), "
              "so multi-seed rows are not independent noise trials. (2) Only QPSK was exercised. "
              "(3) **No v4 run exists**: D1–D18, D13, BPSK/OFDM baseline sections 6–7 are NOT RUN.", ""]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    sinr = np.array([float(r["sinr_meas_db"]) for r in rows])
    ber = np.array([float(r["ber"]) for r in rows])
    nz = ber > 0
    ax.semilogy(sinr[nz], ber[nz], "o", label="measured (Simulink v3)")
    xs = np.linspace(-11, 21, 200)
    ax.semilogy(xs, 0.5 * np.vectorize(math.erfc)(np.sqrt(10 ** (xs / 10)) / math.sqrt(2)), "k-",
                label="QPSK theory Q(sqrt(SINR))")
    ax.semilogy(sinr[~nz], np.full((~nz).sum(), 2.5e-5), "v", color="tab:gray", label="0 errors (of 20000 bits)")
    ax.set_xlabel("measured SINR (dB)")
    ax.set_ylabel("BER")
    ax.set_ylim(1e-5, 1)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    ax.set_title("Real Simulink v3 exports: BER vs measured SINR", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "simulink_v3_ber_vs_sinr.png"), dpi=130)
    lines += ["![](simulink_v3_ber_vs_sinr.png)", ""]


def section_link_model(lines):
    lines += ["## 2. Virtual-RF link model — PYTHON (changed 2026-10-22)", "",
              "Before: BER of BPSK used for QPSK, ×3.5 for any fading, + 0.15 J for any jammer, packet loss "
              "+ 0.10 J; every modulation lost all packets under any jammer. After "
              "(`src/virtual_rf/link_model.py`): SINR = g/(N0 + J), exact coherent BER, expected BER over the "
              "actual fading distributions, realised block fades per step, uncoded 256-bit packets. Validated in "
              "`tests/test_link_model.py`: analytical values, closed form vs numerical integration (≤ 0.1 %), "
              "Monte-Carlo agreement, unit-mean fades, monotonicity in J, and two regimes "
              "(e.g. SNR 18 dB: J = 0.3 → only BPSK delivers; J = 1 → nothing does). "
              "All closed-loop numbers below CL-1 use this model; CL-1 used the old one.", ""]


def section_spectrum(lines):
    p = os.path.join(project_root, "results", "ai", "spectrum_eval", "metrics.json")
    if not os.path.exists(p):
        return
    with open(p) as fh:
        m = json.load(fh)
    lines += ["## 3. Spectrum Agent — PYTHON SYNTHETIC signals, as served", "",
              f"Source: `{rel(p)}`. {m['n_windows']} windows, seeds {m['seed_range'][0]}–{m['seed_range'][1]} "
              "(disjoint from training seeds). Same generator family as training: in-distribution accuracy, "
              "not field accuracy.", "",
              f"Accuracy {m['overall_accuracy']:.3f}, UNKNOWN rate {m['unknown_rate']:.3f}, ECE {m['ece_known']:.3f}.", "",
              "| class | precision | recall | F1 |", "|---|---|---|---|"]
    for c, v in m["per_class"].items():
        lines.append(f"| {c} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} |")
    good = [r for r in m["snr_estimation"] if r["sinr_db"] >= 5 and r["type"] != "OFDM-QPSK"]
    ofdm = [r for r in m["snr_estimation"] if r["sinr_db"] >= 5 and r["type"] == "OFDM-QPSK"]
    lines += ["", f"Blind SNR at SINR ≥ 5 dB: PSK |bias| ≤ {max(abs(r['bias_db']) for r in good):.2f} dB, "
              f"MAE ≤ {max(r['mae_db'] for r in good):.2f} dB; OFDM-QPSK |bias| ≤ "
              f"{max(abs(r['bias_db']) for r in ofdm):.2f} dB, MAE ≤ {max(r['mae_db'] for r in ofdm):.2f} dB. "
              "At 0 dB PSK is resolved in ~35 % of windows (floor otherwise); at −5 dB in none.",
              "Stationary false SNR_DROP rate after the resolution-aware comparison: "
              + ", ".join(f"{k} {v:.3f}" for k, v in m["false_snr_drop_rate_stationary"].items() if v > 0)
              + " (all others 0).", ""]


def section_classifier(lines):
    p = os.path.join(project_root, "results", "ai", "modulation_classifier", "retrain_eval", "evaluation.json")
    if not os.path.exists(p):
        return
    with open(p) as fh:
        ev = json.load(fh)
    lines += ["## 4. Modulation classifier retraining — PYTHON SYNTHETIC", "",
              f"Source: `{rel(p)}` (reproduced exactly by `retrain_modulation_classifier.py --check`).", "",
              "| model | test set | overall accuracy |", "|---|---|---|"]
    for k, r in ev["results"].items():
        m, s = k.split("/")
        lines.append(f"| {m} | {s} | {r['overall']:.3f} |")
    lines.append("")


def section_twin(lines):
    p = os.path.join(project_root, "results", "digital_twin", "forecast_eval", "alternatives.csv")
    if not os.path.exists(p):
        return
    rows = read_csv(p)
    fs = [k[4:-3] for k in rows[0] if k.startswith("mae_")]
    wins = Counter()
    for r in rows:
        vals = {f: float(r[f"mae_{f}_db"]) for f in fs}
        b = min(vals.values())
        for f, v in vals.items():
            if abs(v - b) < 1e-9:
                wins[f] += 1
    step = [r for r in rows if r["scenario"] not in ("synthetic_ramp", "clear_channel")]
    ramp = [r for r in rows if r["scenario"] == "synthetic_ramp"]
    lines += ["## 5. Digital Twin forecasting — PYTHON virtual RF", "",
              f"Source: `{rel(p)}` (causal; forecast at t from data ≤ t, scored at t+h).", "",
              f"Best-or-tied counts over {len(rows)} (scenario, noise, horizon) rows: "
              + ", ".join(f"{f} {wins[f]}" for f in fs) + ".",
              f"Step scenarios: twin trend mean MAE {np.mean([float(r['mae_twin_trend_db']) for r in step]):.2f} dB vs "
              f"persistence {np.mean([float(r['mae_persistence_db']) for r in step]):.2f} dB vs change-point trend "
              f"{np.mean([float(r['mae_changepoint_trend_db']) for r in step]):.2f} dB. Ramp: twin trend "
              f"{np.mean([float(r['mae_twin_trend_db']) for r in ramp]):.2f} dB vs persistence "
              f"{np.mean([float(r['mae_persistence_db']) for r in ramp]):.2f} dB.",
              "The twin's predictor is unchanged; the alternatives are reported, not adopted.", ""]


def _paired(path, suite, b, metric):
    for r in read_csv(path):
        if r["suite"] == suite and r["b"] == b and r["metric"] == metric:
            return r
    return None


def section_closed_loop(lines):
    d1, dr, d2 = (os.path.join(CL, x) for x in (CL1, CL1_REPRO, CL2))
    lines += ["## 6. Closed-loop adaptation — PYTHON virtual RF (NOT Simulink)", ""]
    if os.path.exists(os.path.join(d1, "episodes.csv")):
        e1 = read_csv(os.path.join(d1, "episodes.csv"))
        by = defaultdict(list)
        gp = {(e["scenario"], e["policy"], e["seed"]): float(e["mean_goodput_kbps"]) for e in e1}
        for e in e1:
            by[e["policy"]].append(float(e["mean_goodput_kbps"]))
        wtl = Counter()
        for (scen, pol, seed), v in gp.items():
            if pol != "acwra":
                continue
            fixed = {p: np.mean([gp[k] for k in gp if k[0] == scen and k[1] == p])
                     for p in ("fixed_BPSK", "fixed_QPSK", "fixed_OFDM-QPSK")}
            best = gp[(scen, max(fixed, key=fixed.get), seed)]
            wtl["W" if v > best + 1e-6 else "L" if v < best - 1e-6 else "T"] += 1
        lines += [f"### CL-1 (original evaluation, OLD link model): `{rel(d1)}`", "",
                  f"Reproduced bit-for-bit in all {len(e1)} episodes by `{rel(dr)}` before any change. Mean goodput "
                  "(kb/s) over its 6 scenarios: "
                  + ", ".join(f"{p} {np.mean(v):.1f}" for p, v in by.items()) + ". ACWRA vs the best fixed "
                  f"modulation per scenario-seed: {wtl['W']} W / {wtl['T']} T / {wtl['L']} L.", ""]
    p2 = os.path.join(d2, "paired_comparisons.csv")
    if not os.path.exists(p2):
        return
    with open(os.path.join(d2, "config.json")) as fh:
        cfg = json.load(fh)
    lines += [f"### CL-2 (protocol `docs/EXPERIMENT_PROTOCOL.md`, NEW link model): `{rel(d2)}`", "",
              f"Commit `{cfg['git_commit']}`, {cfg['n_episodes']} episodes, {cfg['n_steps_total']} steps. "
              "Statistics are condition-level (seeds averaged within a condition), paired, with a bootstrap "
              "95 % CI over conditions and a Wilcoxon signed-rank test; p-values descriptive.", "",
              "| suite | ACWRA − baseline | Δ goodput kb/s [95 % CI] | W/T/L | p | Δ BER [95 % CI] | W/T/L |",
              "|---|---|---|---|---|---|---|"]
    for suite in ("original", "sweep"):
        for b in ("fixed_BPSK", "fixed_QPSK", "snr_threshold", "sinr_threshold", "oracle"):
            g = _paired(p2, suite, b, "mean_goodput_kbps")
            r = _paired(p2, suite, b, "mean_ber")
            if not g or not r:
                continue
            lines.append(f"| {suite} | {b} | {float(g['mean_diff']):+.1f} [{float(g['ci95_low']):+.1f}, "
                         f"{float(g['ci95_high']):+.1f}] | {g['wins']}/{g['ties']}/{g['losses']} | "
                         f"{float(g['wilcoxon_p']):.2g} | {float(r['mean_diff']):+.4f} [{float(r['ci95_low']):+.4f}, "
                         f"{float(r['ci95_high']):+.4f}] | {r['wins']}/{r['ties']}/{r['losses']} |")
    lines += ["", "(For BER, a negative Δ and *losses* mean ACWRA has the LOWER BER.)", "",
              "**Ablations** (ACWRA − ablated variant; same table convention):", "",
              "| suite | ablation | Δ goodput kb/s [95 % CI] | W/T/L | Δ BER [95 % CI] | W/T/L |",
              "|---|---|---|---|---|---|"]
    for suite in ("original", "sweep"):
        for b in ("acwra_no_prediction", "acwra_no_history", "acwra_no_confidence", "acwra_all_candidates"):
            g = _paired(p2, suite, b, "mean_goodput_kbps")
            r = _paired(p2, suite, b, "mean_ber")
            if not g or not r:
                continue
            lines.append(f"| {suite} | {b} | {float(g['mean_diff']):+.2f} [{float(g['ci95_low']):+.2f}, "
                         f"{float(g['ci95_high']):+.2f}] | {g['wins']}/{g['ties']}/{g['losses']} | "
                         f"{float(r['mean_diff']):+.4f} [{float(r['ci95_low']):+.4f}, {float(r['ci95_high']):+.4f}] | "
                         f"{r['wins']}/{r['ties']}/{r['losses']} |")
    lines += ["", f"Figures and per-policy means: `{rel(d2)}/summary.md`, `{rel(d2)}/sweep_goodput.png`.", ""]


def section_campaign(lines):
    p = os.path.join(project_root, "simulink", "results", "campaign_report", "results_fixture.csv")
    if not os.path.exists(p):
        return
    rows = read_csv(p)
    v = Counter(r["verdict"] for r in rows)
    sel = Counter(r["selected_strategy"] for r in rows if r["selected_strategy"])
    acc = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["modulation"] in ("BPSK", "QPSK", "OFDM-QPSK"):
            acc[r["modulation"]][0] += r["modulation_detected"] == r["modulation"]
            acc[r["modulation"]][1] += 1
    lines += ["## 7. Bridge → agents → ACWRA campaign — PYTHON FIXTURES", "",
              f"Source: `{rel(p)}` (402 checks on `reference_phy.py` fixture MAT files, never Simulink).", "",
              f"Verdicts: {dict(v)}. Selected strategies: {dict(sel)}. Detection: "
              + ", ".join(f"{m} {a[0]}/{a[1]}" for m, a in acc.items()) + ".", ""]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    lines = ["# CogniTwin-SDR research evaluation", "",
             "Generated by `experiments/research_evaluation.py` from saved outputs only. Data classes: "
             "**REAL SIMULINK (historical v3)**, **PYTHON SYNTHETIC**, **PYTHON VIRTUAL RF**, **PYTHON FIXTURES**. "
             "No v4 Simulink result exists; nothing here is a v4 measurement, and no virtual-RF number is a "
             "physical-layer result.", ""]
    for section in (section_simulink, section_link_model, section_spectrum, section_classifier, section_twin,
                    section_closed_loop, section_campaign):
        section(lines)
    with open(os.path.join(OUT, "RESEARCH_EVALUATION.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    # Windows consoles default to cp1252, which lacks e.g. '≤'; replace instead of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
