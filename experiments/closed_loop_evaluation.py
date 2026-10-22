"""
CLOSED-LOOP ADAPTATION EVALUATION: ACWRA vs baselines and ablations (virtual RF, Python).

Protocol: docs/EXPERIMENT_PROTOCOL.md (CL-2). Each step the environment transmits
the modulation chosen at the PREVIOUS step (one-step actuation delay) via
VirtualRFEnvironment.modulation_override.

Policies
    acwra                 Spectrum Agent -> Digital Twin -> Prediction Agent -> Cyber Defense
                          Agent -> ACWRAEngine; the EFFECTIVE modulation of the selected
                          candidate is applied ("Keep Current" = no change)
    acwra_no_prediction   ablation: risk 0 / status DISABLED instead of the Prediction Agent
    acwra_no_history      ablation: Digital Twin history cleared before every update
    acwra_no_confidence   ablation: classifier confidence forced to 1 before ACWRA
    acwra_all_candidates  ablation: Cyber Defense always proposes all four candidates
    fixed_BPSK / fixed_QPSK / fixed_OFDM-QPSK      no adaptation
    snr_threshold         BPSK if observed SNR < 8 dB or interference > 0.5, else QPSK (CL-1 rule)
    sinr_threshold        BPSK if 1/(N0 + J) < 10 dB, else QPSK
    oracle                clairvoyant: best goodput under the REALISED fade of the step, no delay

IMPORTANT. Outcomes come from the same link abstraction the Digital Twin's sandbox uses
(src/virtual_rf/link_model.py); the sandbox sees the EXPECTED fade, the step the REALISED
one. This measures decision logic, not physical-layer performance, and is no
substitute for Simulink measurements.

    python experiments/closed_loop_evaluation.py                       # suite 'all'
    python experiments/closed_loop_evaluation.py --suite original --seeds 1 2 3
    python experiments/closed_loop_evaluation.py --suite sweep --policies acwra oracle fixed_QPSK

Outputs: results/evaluation/closed_loop/<run_id>/ {steps.csv.gz, episodes.csv, summary.csv,
paired_comparisons.csv, summary.md, config.json, *.png}; LATEST points at the newest run.
"""

import argparse
import copy
import csv
import dataclasses
import glob
import gzip
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

from src.acwra.engine import ACWRAEngine
from src.acwra.scoring import ACWRAScoringEngine
from src.agents.messages import DefenseCandidate, MultiAgentSnapshot, PredictionResult
from src.agents.orchestrator import MultiAgentOrchestrator
from src.virtual_rf.environment import VirtualRFEnvironment
from src.virtual_rf.link_model import FADING_CHANNELS, link_metrics
from src.virtual_rf.scenario import ScenarioEngine

PROTOCOL = "CL-2"
OUT_ROOT = os.path.join(project_root, "results", "evaluation", "closed_loop")
DT = 0.1
MODS = ("BPSK", "QPSK", "OFDM-QPSK")
ALL_CANDIDATES = ["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"]
ACWRA_VARIANTS = {"acwra": None, "acwra_no_prediction": "no_prediction", "acwra_no_history": "no_history",
                  "acwra_no_confidence": "no_confidence", "acwra_all_candidates": "all_candidates"}
BASELINES = ("fixed_BPSK", "fixed_QPSK", "fixed_OFDM-QPSK", "snr_threshold", "sinr_threshold", "oracle")
POLICIES = tuple(ACWRA_VARIANTS) + BASELINES
SWEEP = {"channels": ("awgn", "rayleigh"), "snr_db": (6.0, 12.0, 18.0),
         "interference": (0.0, 0.03, 0.1, 0.3, 1.0), "duration_s": 2.0}


def _git_commit():
    """Short HEAD hash, suffixed '-dirty' if tracked code differs from it."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=project_root,
                              capture_output=True, text=True, timeout=20).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "experiments"],
                               cwd=project_root, capture_output=True, text=True, timeout=20).stdout.strip()
        return head + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- conditions
def original_suite():
    configs = {}
    for f in sorted(glob.glob(os.path.join(project_root, "config", "scenarios", "*.json"))):
        with open(f) as fh:
            cfg = json.load(fh)
        cfg["name"] = os.path.splitext(os.path.basename(f))[0]
        configs[cfg["name"]] = cfg
    return configs


def sweep_suite():
    configs = {}
    for ch in SWEEP["channels"]:
        for snr in SWEEP["snr_db"]:
            for j in SWEEP["interference"]:
                name = f"sweep_{ch}_snr{snr:g}_j{j:g}"
                configs[name] = {"name": name, "duration_seconds": SWEEP["duration_s"], "keyframes": [{
                    "time_s": 0.0, "modulation": "QPSK", "snr_db": snr, "channel_type": ch,
                    "interference_type": "broadband" if j > 0 else "none", "interference_power": j}]}
    return configs


# ---------------------------------------------------------------- oracle
def peek_step_gain(env, channel):
    """Power gain the NEXT env.step() will realise, without consuming env.rng."""
    if channel not in FADING_CHANNELS:
        return None
    step_seed = int(copy.deepcopy(env.rng).integers(0, 1000000))
    r = np.random.default_rng(step_seed)              # same draws as _apply_channel
    if channel == "rayleigh":
        g = (r.normal(0, 1, 2) + 1j * r.normal(0, 1, 2)) / np.sqrt(2)
        return float((abs(g[0]) ** 2 + 0.25 * abs(g[1]) ** 2) / 1.25)
    s = (r.normal(0, 1) + 1j * r.normal(0, 1)) / np.sqrt(2)
    return float(abs((np.sqrt(2.0) + s) / np.sqrt(3.0)) ** 2)


def _goodput(kf, mod, gain=None):
    return link_metrics(mod, float(kf.get("snr_db", 20.0)), kf.get("channel_type", "awgn"),
                        float(kf.get("interference_power", 0.0)), channel_gain=gain)[3]


def oracle_set(kf, gain=None, tol_bps=1.0):
    """All modulations within 1 b/s of the best goodput for this step's conditions."""
    g = {m: _goodput(kf, m, gain) for m in MODS}
    best = max(g.values())
    return [m for m in MODS if g[m] >= best - tol_bps]


# ---------------------------------------------------------------- agent step
def agent_step(orch, ablation=None):
    """
    MultiAgentOrchestrator.step() with ablation hooks. With ablation=None it is
    exactly equivalent (tests/test_closed_loop.py checks this); agent code is untouched.
    """
    env_state, iq = orch.env.step(duration_seconds=DT)
    t = orch.env.current_time_s
    spec = orch.spectrum_agent.process(iq_samples=iq, timestamp_s=t,
                                       env_interference_power=env_state.interference_power)
    if ablation == "no_history":
        orch.digital_twin.history.clear()
    dt_state = orch.digital_twin.update(env_state, ai_result={
        "predicted_modulation": spec.modulation, "confidence": spec.classifier_confidence,
        "snr_db": spec.snr_db})
    if ablation == "no_prediction":
        pred = PredictionResult(predicted_timestamp_s=dt_state.timestamp_s + DT, next_snr_db=dt_state.snr_db,
                                next_ber=dt_state.ber, next_interference_power=dt_state.interference_power,
                                risk_score=0.0, risk_level="LOW", prediction_status="DISABLED")
    else:
        pred = orch.prediction_agent.process(digital_twin=orch.digital_twin, horizon_seconds=DT)
    defense = orch.cyber_defense_agent.process(spectrum_res=spec, prediction_res=pred, dt_state=dt_state)
    if ablation == "all_candidates":
        defense = DefenseCandidate(candidate_strategies=list(ALL_CANDIDATES),
                                   rationale="ablation: all candidates", risk_level=defense.risk_level)
    if ablation == "no_confidence":
        spec = dataclasses.replace(spec, classifier_confidence=1.0)
    return MultiAgentSnapshot(timestamp_s=t, spectrum_result=spec, prediction_result=pred,
                              defense_candidates=defense), env_state


# ---------------------------------------------------------------- episode
def run_episode(config, policy, seed):
    env = VirtualRFEnvironment(scenario=ScenarioEngine(config), seed=seed)
    n_steps = int(round(float(config.get("duration_seconds", 3.0)) / DT))
    initial = config["keyframes"][0].get("modulation", "QPSK")
    current = {"fixed_BPSK": "BPSK", "fixed_QPSK": "QPSK", "fixed_OFDM-QPSK": "OFDM-QPSK"}.get(policy, initial)
    is_acwra = policy in ACWRA_VARIANTS
    orch = MultiAgentOrchestrator(environment=env) if is_acwra else None
    engine = ACWRAEngine() if is_acwra else None
    rows, pending_forecast = [], None
    for k in range(n_steps):
        t = env.current_time_s
        kf = env.scenario.get_keyframe_at(t)
        gain = peek_step_gain(env, kf.get("channel_type", "awgn"))
        best = oracle_set(kf, gain)
        if policy == "oracle":
            current = best[0]                                  # zero delay, realised conditions
        env.modulation_override = current
        t0 = time.perf_counter()
        utility, forecast_err, risk, detected, selected = float("nan"), float("nan"), float("nan"), "", ""
        if is_acwra:
            snapshot, state = agent_step(orch, ACWRA_VARIANTS[policy])
            if pending_forecast is not None:
                forecast_err = abs(pending_forecast - state.snr_db)
            t1 = time.perf_counter()
            decision = engine.evaluate_and_decide(snapshot, orch.digital_twin)
            decide_ms = (time.perf_counter() - t1) * 1e3
            nxt = next(c.modulation for c in decision.candidate_scores if c.strategy == decision.selected_strategy)
            utility, selected = decision.expected_utility, decision.selected_strategy
            pred = orch.digital_twin.predict_next(horizon_seconds=DT)
            pending_forecast = pred["next_snr_db"] if pred["prediction_status"] == "SUCCESS" else None
            risk, detected = snapshot.prediction_result.risk_score, snapshot.spectrum_result.modulation
        else:
            state, _ = env.step(DT)
            t1 = time.perf_counter()
            if policy == "snr_threshold":
                nxt = "BPSK" if (state.snr_db < 8.0 or state.interference_power > 0.5) else "QPSK"
            elif policy == "sinr_threshold":
                sinr_db = -10.0 * np.log10(10 ** (-state.snr_db / 10.0) + max(state.interference_power, 0.0))
                nxt = "BPSK" if sinr_db < 10.0 else "QPSK"
            else:
                nxt = current
            decide_ms = (time.perf_counter() - t1) * 1e3
            selected = nxt
        if gain is not None:
            assert abs(env.last_channel_gain - gain) < 1e-12, "oracle peek diverged from the realised fade"
        step_ms = (time.perf_counter() - t0) * 1e3
        oracle_goodput = _goodput(kf, best[0], gain)
        rows.append({
            "condition": config.get("name", ""), "policy": policy, "seed": seed, "step": k, "t_s": round(t, 6),
            "snr_db": state.snr_db, "interference_power": state.interference_power,
            "channel_type": state.channel_type, "channel_gain": env.last_channel_gain,
            "modulation_applied": state.modulation, "oracle_set": "|".join(best),
            "ber": state.ber, "goodput_bps": state.throughput_bps, "packet_loss": state.packet_loss,
            "latency_ms": state.latency_ms, "oracle_goodput_bps": oracle_goodput,
            "goodput_regret_bps": oracle_goodput - state.throughput_bps,
            "spectral_efficiency": ACWRAScoringEngine.get_theoretical_spectral_efficiency(state.modulation),
            "next_modulation": nxt, "selected_strategy": selected, "expected_utility": utility,
            "risk_score": risk, "modulation_detected": detected,
            "twin_forecast_abs_err_db": forecast_err, "decide_ms": decide_ms, "step_ms": step_ms,
        })
        current = nxt
    return rows


def recovery_steps(rows, keyframe_times):
    """Steps after each keyframe transition until the applied modulation is in the oracle set."""
    out = []
    for kt in keyframe_times:
        seg = [r for r in rows if r["t_s"] >= kt - 1e-9]
        nxt_kts = [x for x in keyframe_times if x > kt + 1e-9]
        if nxt_kts:
            seg = [r for r in seg if r["t_s"] < nxt_kts[0] - 1e-9]
        if not seg:
            continue
        out.append(next((i for i, r in enumerate(seg) if r["modulation_applied"] in r["oracle_set"].split("|")),
                        len(seg)))
    return out


# ---------------------------------------------------------------- aggregation
def summarise(rows, keyframe_times):
    g = defaultdict(list)
    for r in rows:
        g[(r["condition"], r["policy"], r["seed"])].append(r)
    eps = []
    for (cond, pol, seed), rs in g.items():
        mods = [r["modulation_applied"] for r in rs]
        rec = recovery_steps(rs, keyframe_times.get(cond, []))
        fe = [r["twin_forecast_abs_err_db"] for r in rs if np.isfinite(r["twin_forecast_abs_err_db"])]
        eps.append({
            "condition": cond, "policy": pol, "seed": seed, "steps": len(rs),
            "mean_goodput_kbps": float(np.mean([r["goodput_bps"] for r in rs])) / 1e3,
            "mean_ber": float(np.mean([r["ber"] for r in rs])),
            "mean_regret_kbps": float(np.mean([r["goodput_regret_bps"] for r in rs])) / 1e3,
            "mean_packet_loss": float(np.mean([r["packet_loss"] for r in rs])),
            "mean_latency_ms": float(np.mean([r["latency_ms"] for r in rs])),
            "mean_spectral_eff": float(np.mean([r["spectral_efficiency"] for r in rs])),
            "switches": int(sum(a != b for a, b in zip(mods, mods[1:]))),
            "oracle_agreement": float(np.mean([r["modulation_applied"] in r["oracle_set"].split("|") for r in rs])),
            "mean_recovery_steps": float(np.mean(rec)) if rec else float("nan"),
            "mean_utility": float(np.nanmean([r["expected_utility"] for r in rs])) if pol in ACWRA_VARIANTS else float("nan"),
            "twin_mae_db": float(np.mean(fe)) if fe else float("nan"),
            "decide_ms": float(np.mean([r["decide_ms"] for r in rs])),
            "step_ms": float(np.mean([r["step_ms"] for r in rs])),
        })
    return eps


def aggregate(eps):
    g = defaultdict(list)
    for e in eps:
        g[(e["condition"], e["policy"])].append(e)
    keys = [k for k in eps[0] if k not in ("condition", "policy", "seed", "steps", "suite")]
    out = []
    for (cond, pol), es in g.items():
        row = {"condition": cond, "policy": pol, "n_seeds": len(es), "steps_per_episode": es[0]["steps"]}
        for k in keys:
            v = np.array([e[k] for e in es], dtype=float)
            fin = np.isfinite(v)
            row[f"{k}_mean"] = float(np.mean(v[fin])) if fin.any() else float("nan")
            row[f"{k}_std"] = float(np.std(v[fin])) if fin.any() else float("nan")
        out.append(row)
    return out


def paired_comparison(eps, a, b, metric, conditions, n_boot=10000):
    """Condition-level paired differences a - b (seeds averaged within a condition)."""
    by = defaultdict(dict)
    for e in eps:
        by[(e["condition"], e["policy"])][e["seed"]] = e[metric]
    diffs = []
    for c in conditions:
        da, db = by.get((c, a)), by.get((c, b))
        if not da or not db:
            continue
        common = sorted(set(da) & set(db))
        diffs.append(float(np.mean([da[s] - db[s] for s in common])))
    d = np.array(diffs)
    if d.size == 0:
        return None
    rng = np.random.default_rng(0)
    boots = d[rng.integers(0, d.size, (n_boot, d.size))].mean(axis=1)
    tol = 1e-9 * max(1.0, float(np.max(np.abs(d))))
    nz = d[np.abs(d) > tol]
    p = float(stats.wilcoxon(nz).pvalue) if nz.size >= 5 else float("nan")
    return {"a": a, "b": b, "metric": metric, "n_conditions": int(d.size), "mean_diff": float(d.mean()),
            "ci95_low": float(np.percentile(boots, 2.5)), "ci95_high": float(np.percentile(boots, 97.5)),
            "wins": int(np.sum(d > tol)), "ties": int(np.sum(np.abs(d) <= tol)), "losses": int(np.sum(d < -tol)),
            "wilcoxon_p": p, "nonzero_pairs": int(nz.size)}


def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Closed-loop ACWRA vs baselines and ablations (protocol CL-2)")
    ap.add_argument("--suite", choices=("original", "sweep", "all"), default="all")
    ap.add_argument("--seeds", type=int, nargs="+", default=None,
                    help="default: 1..10 for 'original', 1..5 for 'sweep'")
    ap.add_argument("--scenarios", nargs="+", default=None, help="restrict to these condition names")
    ap.add_argument("--policies", nargs="+", default=list(POLICIES))
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    suites = {}
    if args.suite in ("original", "all"):
        suites["original"] = (original_suite(), args.seeds or list(range(1, 11)))
    if args.suite in ("sweep", "all"):
        suites["sweep"] = (sweep_suite(), args.seeds or list(range(1, 6)))
    for name, (cfgs, _) in suites.items():
        if args.scenarios:
            for k in [k for k in cfgs if k not in args.scenarios]:
                del cfgs[k]
    if not any(cfgs for cfgs, _ in suites.values()):
        print("no conditions selected")
        return 2

    run_id = args.run_id or time.strftime("run_%Y%m%dT%H%M%S")
    out_dir = os.path.join(OUT_ROOT, run_id)
    os.makedirs(out_dir, exist_ok=False)

    rows, cond_suite, kf_times = [], {}, {}
    t_start = time.time()
    for sname, (cfgs, seeds) in suites.items():
        for cname, cfg in cfgs.items():
            cond_suite[cname] = sname
            kf_times[cname] = [float(k["time_s"]) for k in cfg["keyframes"][1:]]
            for pol in args.policies:
                for seed in seeds:
                    rows.extend(run_episode(cfg, pol, seed))
    elapsed = time.time() - t_start

    eps = summarise(rows, kf_times)
    for e in eps:
        e["suite"] = cond_suite[e["condition"]]
    agg = aggregate(eps)
    for a in agg:
        a["suite"] = cond_suite[a["condition"]]

    with gzip.open(os.path.join(out_dir, "steps.csv.gz"), "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    write_csv(os.path.join(out_dir, "episodes.csv"), eps)
    write_csv(os.path.join(out_dir, "summary.csv"), agg)

    comps = []
    if "acwra" in args.policies:
        for sname in suites:
            conds = [c for c, s in cond_suite.items() if s == sname]
            for b in [p for p in args.policies if p != "acwra"]:
                for metric in ("mean_goodput_kbps", "mean_ber", "mean_regret_kbps", "switches"):
                    r = paired_comparison(eps, "acwra", b, metric, conds)
                    if r:
                        r["suite"] = sname
                        comps.append(r)
    if comps:
        write_csv(os.path.join(out_dir, "paired_comparisons.csv"), comps)

    cfg_out = {"run_id": run_id, "protocol": PROTOCOL, "git_commit": _git_commit(), "dt_s": DT,
               "suites": {s: {"conditions": list(c), "seeds": sd} for s, (c, sd) in suites.items()},
               "sweep_grid": SWEEP, "policies": args.policies, "n_steps_total": len(rows),
               "n_episodes": len(eps), "wall_seconds": round(elapsed, 1),
               "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_start)),
               "acwra_weights": {"w_t": 0.4, "w_se": 0.2, "w_b": 0.6, "lambda_c": 1.0},
               "python": sys.version.split()[0], "numpy": np.__version__,
               "environment": "Python VirtualRFEnvironment + link_model (NOT Simulink)",
               "caveat": "sandbox plans with the expected fade, steps realise one fade per block; "
                         "decision logic only, not physical-layer performance"}
    with open(os.path.join(out_dir, "config.json"), "w") as fh:
        json.dump(cfg_out, fh, indent=2)

    lines = [f"# Closed-loop evaluation `{run_id}` (protocol {PROTOCOL})", "",
             f"Commit `{cfg_out['git_commit']}`; {len(eps)} episodes, {len(rows)} steps; "
             f"environment: Python virtual RF (NOT Simulink). Mean (std over seeds).", ""]
    for sname in suites:
        conds = [c for c, s in cond_suite.items() if s == sname]
        lines += [f"## Suite `{sname}` - paired comparisons (ACWRA - baseline, condition-level)", "",
                  "| baseline | metric | n cond | mean diff | 95% CI | W/T/L | Wilcoxon p |",
                  "|---|---|---|---|---|---|---|"]
        for r in [c for c in comps if c["suite"] == sname]:
            lines.append(f"| {r['b']} | {r['metric']} | {r['n_conditions']} | {r['mean_diff']:+.4g} | "
                         f"[{r['ci95_low']:+.4g}, {r['ci95_high']:+.4g}] | {r['wins']}/{r['ties']}/{r['losses']} | "
                         f"{r['wilcoxon_p']:.3g} |")
        lines += ["", f"### Suite `{sname}` - policy means over conditions", "",
                  "| policy | goodput kb/s | BER | regret kb/s | switches | oracle agree | decide ms |",
                  "|---|---|---|---|---|---|---|"]
        for p in args.policies:
            sel = [a for a in agg if a["policy"] == p and a["condition"] in conds]
            if not sel:
                continue

            def f(k):
                return float(np.nanmean([a[f"{k}_mean"] for a in sel]))
            lines.append(f"| {p} | {f('mean_goodput_kbps'):.1f} | {f('mean_ber'):.4f} | {f('mean_regret_kbps'):.1f} | "
                         f"{f('switches'):.2f} | {f('oracle_agreement'):.2f} | {f('decide_ms'):.2f} |")
        lines.append("")
    with open(os.path.join(out_dir, "summary.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    if "sweep" in suites and suites["sweep"][0]:
        fig, axes = plt.subplots(len(SWEEP["channels"]), len(SWEEP["snr_db"]), figsize=(14, 7),
                                 sharey=True, squeeze=False)
        show = [p for p in ("acwra", "fixed_BPSK", "fixed_QPSK", "sinr_threshold", "oracle") if p in args.policies]
        for i, ch in enumerate(SWEEP["channels"]):
            for j, snr in enumerate(SWEEP["snr_db"]):
                ax = axes[i][j]
                for p in show:
                    xs, ys, es = [], [], []
                    for jam in SWEEP["interference"]:
                        name = f"sweep_{ch}_snr{snr:g}_j{jam:g}"
                        a = next((a for a in agg if a["condition"] == name and a["policy"] == p), None)
                        if a:
                            xs.append(max(jam, 0.003))
                            ys.append(a["mean_goodput_kbps_mean"])
                            es.append(a["mean_goodput_kbps_std"])
                    ax.errorbar(xs, ys, yerr=es, marker="o", ms=3, capsize=2, label=p)
                ax.set_xscale("log")
                ax.set_title(f"{ch}, SNR {snr:g} dB", fontsize=9)
                ax.grid(alpha=0.3)
                if i == len(SWEEP["channels"]) - 1:
                    ax.set_xlabel("interference power J (J = 0 plotted at 0.003)")
                if j == 0:
                    ax.set_ylabel("goodput (kb/s)")
        axes[0][0].legend(fontsize=7)
        fig.suptitle(f"{run_id}: goodput vs interference (virtual RF, NOT Simulink)", fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "sweep_goodput.png"), dpi=120)

    with open(os.path.join(OUT_ROOT, "LATEST"), "w") as fh:
        fh.write(run_id + "\n")
    print("\n".join(lines))
    print(f"\nwritten to {out_dir}  ({elapsed:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
