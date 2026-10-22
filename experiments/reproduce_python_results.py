"""
REPRODUCE THE COMMITTED PYTHON RESULTS INTO NEW FOLDERS AND COMPARE.

    python experiments/reproduce_python_results.py            # everything (~20 min)
    python experiments/reproduce_python_results.py --quick    # spectrum + forecast + 2-seed closed loop

Writes ONLY under results/reproductions/<stamp>/ (and a new closed-loop run folder);
committed results are never overwritten. For each committed artefact it compares the
deterministic numbers and prints MATCH / DIFFER / NOT COMPARED. Timing columns are never
compared. Python / virtual RF / synthetic only - nothing here is a Simulink result.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable
TIMING = {"decide_ms", "step_ms", "decide_ms_mean", "decide_ms_std", "step_ms_mean", "step_ms_std"}


def run(args):
    print("  $ python " + " ".join(args))
    r = subprocess.run([PY] + args, cwd=project_root, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:] + r.stderr[-2000:])
    return r.returncode


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def compare_csv(a, b, skip=TIMING, rel=1e-9):
    if not (os.path.exists(a) and os.path.exists(b)):
        return "NOT COMPARED (missing file)"
    ra, rb = _rows(a), _rows(b)
    if len(ra) != len(rb):
        return f"DIFFER (rows {len(ra)} vs {len(rb)})"
    for x, y in zip(ra, rb):
        for k in x:
            if k in skip:
                continue
            if x[k] == y.get(k):
                continue
            try:
                fx, fy = float(x[k]), float(y[k])
                if abs(fx - fy) <= rel * max(1.0, abs(fx)) or (fx != fx and fy != fy):
                    continue
            except (TypeError, ValueError):
                pass
            return f"DIFFER (first at {k}: {x[k]} vs {y.get(k)})"
    return "MATCH"


def compare_json(a, b, keys):
    if not (os.path.exists(a) and os.path.exists(b)):
        return "NOT COMPARED (missing file)"
    with open(a) as fa, open(b) as fb:
        ja, jb = json.load(fa), json.load(fb)
    for k in keys:
        if ja.get(k) != jb.get(k):
            return f"DIFFER ({k})"
    return "MATCH"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args(argv)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out = os.path.join("results", "reproductions", stamp)
    os.makedirs(os.path.join(project_root, out), exist_ok=False)
    verdicts = {}

    print("[1] Spectrum Agent evaluation")
    if run(["experiments/spectrum_agent_eval.py", "--out-dir", f"{out}/spectrum_eval"]) == 0:
        verdicts["spectrum_eval/metrics.json"] = compare_json(
            os.path.join(project_root, "results", "ai", "spectrum_eval", "metrics.json"),
            os.path.join(project_root, out, "spectrum_eval", "metrics.json"),
            ["overall_accuracy", "unknown_rate", "confusion", "snr_estimation", "false_snr_drop_rate_stationary"])

    print("[2] Digital Twin forecast evaluation")
    if run(["experiments/digital_twin_forecast_eval.py", "--out-dir", f"{out}/forecast_eval"]) == 0:
        for f in ("forecast_metrics.csv", "alternatives.csv"):
            verdicts[f"forecast_eval/{f}"] = compare_csv(
                os.path.join(project_root, "results", "digital_twin", "forecast_eval", f),
                os.path.join(project_root, out, "forecast_eval", f))

    print("[3] Closed-loop evaluation")
    ref_run = os.path.join(project_root, "results", "evaluation", "closed_loop", "cl2_20261022")
    rid = f"repro_{stamp}"
    cl_args = ["experiments/closed_loop_evaluation.py", "--run-id", rid]
    if args.quick:
        cl_args += ["--suite", "original", "--seeds", "1", "2"]
    if run(cl_args) == 0:
        new = os.path.join(project_root, "results", "evaluation", "closed_loop", rid, "episodes.csv")
        if args.quick:
            ref = {(r["condition"], r["policy"], r["seed"]): r for r in _rows(os.path.join(ref_run, "episodes.csv"))}
            sub = [r for r in _rows(new)]
            bad = [k for k in sub if any(
                k[c] != ref.get((k["condition"], k["policy"], k["seed"]), {}).get(c)
                for c in k if c not in TIMING)]
            verdicts["closed_loop episodes (subset)"] = "MATCH" if not bad else f"DIFFER ({len(bad)} episodes)"
        else:
            verdicts["closed_loop episodes"] = compare_csv(os.path.join(ref_run, "episodes.csv"), new)

    if not args.quick:
        print("[4] Classifier retraining check (in memory; committed model untouched)")
        verdicts["classifier retrain"] = "MATCH" if run(
            ["experiments/retrain_modulation_classifier.py", "--check"]) == 0 else "DIFFER"

    lines = [f"# Reproduction {stamp}", "", "| artefact | verdict |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in verdicts.items()]
    with open(os.path.join(project_root, out, "REPRODUCTION.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if verdicts and all(v == "MATCH" for v in verdicts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
