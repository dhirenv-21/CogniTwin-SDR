"""Condition-level analysis of a GNU Radio campaign (reads saved CSVs only).

    python experiments/gnuradio_campaign_analysis.py <repo_root> [run_id | run_dir]   -> <run>/analysis.md
"""
import csv
import os
import sys
from collections import Counter, defaultdict

import numpy as np

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_arg = sys.argv[2] if len(sys.argv) > 2 else "grcl1_20261022_v2"
RUN = _arg if os.path.isdir(_arg) else os.path.join(ROOT, "results", "gnuradio", "campaign", _arg)
sys.path.insert(0, os.path.join(ROOT, "experiments"))
sys.path.insert(0, ROOT)
import closed_loop_evaluation as cle  # noqa: E402

runs = list(csv.DictReader(open(os.path.join(RUN, "runs.csv"))))
for r in runs:
    for k in ("goodput_bps", "ber", "per", "spectral_efficiency", "switches"):
        r[k] = float(r[k])
    r["seed"] = int(r["seed"])
steps = list(csv.DictReader(open(os.path.join(RUN, "episodes_steps.csv"))))
conds = sorted({r["condition"] for r in runs})
groups = {"all": conds, "static": [c for c in conds if c.startswith("static")],
          "static_awgn": [c for c in conds if c.startswith("static_awgn")],
          "static_rayleigh": [c for c in conds if c.startswith("static_rayleigh")],
          "dynamic": [c for c in conds if not c.startswith("static")]}
pols = ["no_adaptation", "fixed_BPSK", "fixed_QPSK", "fixed_OFDM-QPSK", "sinr_threshold"]
out = []
w = out.append
w("# GR-CL-1 condition-level analysis (generated from runs.csv / episodes_steps.csv)\n")
w(f"runs {len(runs)}, conditions {len(conds)}, flowgraph episodes {len(steps)}, "
  f"provenance {sorted({s['provenance'] for s in steps})}\n")
w("Differences are ACWRA - baseline per condition (seeds averaged), 95 % bootstrap CI over conditions, "
  "Wilcoxon signed-rank. 'A>B/tie/A<B' counts conditions where ACWRA's value is higher / equal / lower "
  "(for BER, higher = worse).\n")
for g, cs in groups.items():
    w(f"\n## {g} ({len(cs)} conditions)\n\n| baseline | metric | mean diff | 95 % CI | A>B/tie/A<B | p |\n|---|---|---|---|---|---|")
    for b in pols:
        for m, scale in (("goodput_bps", 1e-3), ("ber", 1.0)):
            res = cle.paired_comparison(runs, "acwra", b, m, cs)
            if not res:
                continue
            unit = " kb/s" if m == "goodput_bps" else ""
            w(f"| {b} | {m.replace('_bps', '')} | {res['mean_diff'] * scale:+.4g}{unit} | "
              f"[{res['ci95_low'] * scale:+.4g}, {res['ci95_high'] * scale:+.4g}] | "
              f"{res['wins']}/{res['ties']}/{res['losses']} | {res['wilcoxon_p']:.2g} |")
w("\n## Policy means over all runs\n\n| policy | goodput kb/s | BER | PER | switches/run |\n|---|---|---|---|---|")
by = defaultdict(list)
for r in runs:
    by[r["policy"]].append(r)
for p, v in sorted(by.items(), key=lambda kv: -np.mean([x["goodput_bps"] for x in kv[1]])):
    w(f"| {p} | {np.mean([x['goodput_bps'] for x in v]) / 1e3:.1f} | {np.mean([x['ber'] for x in v]):.4f} | "
      f"{np.mean([x['per'] for x in v]):.3f} | {np.mean([x['switches'] for x in v]):.2f} |")
ac = [s for s in steps if s["policy"] == "acwra"]
if not ac:                      # campaign without ACWRA: policy means only
    open(os.path.join(RUN, "analysis.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("\n".join(out))
    sys.exit(0)
w("\n## ACWRA decisions\n")
w(f"selected strategies: {dict(Counter(s['selected_strategy'] for s in ac))}")
w(f"\nmodulations applied: {dict(Counter(s['modulation_applied'] for s in ac))}")
risk = np.array([float(s["risk_score"]) for s in ac])
w(f"\nrisk score: min {risk.min():.3f}, median {np.median(risk):.3f}, max {risk.max():.3f}")
sw = Counter(s["condition"] for s in ac if s["acwra_modulation"] != s["modulation_applied"])
w(f"\nepisodes where ACWRA chose a different modulation, by condition: {dict(sw) or 'none'}")
det = Counter((s["modulation_applied"], s["detected_modulation"]) for s in ac)
w(f"\n(applied, detected) modulation pairs in ACWRA episodes: {dict(det)}")
txt = "\n".join(out) + "\n"
open(os.path.join(RUN, "analysis.md"), "w", encoding="utf-8").write(txt)
print(txt)
