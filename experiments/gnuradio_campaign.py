"""
GNU RADIO CLOSED-LOOP CAMPAIGN (episode-based sequential reconfiguration).

Policies (src/gnuradio_phy/closed_loop.py): acwra, no_adaptation, fixed_BPSK,
fixed_QPSK, fixed_OFDM-QPSK, sinr_threshold. For each (condition, seed) every policy
sees the same per-episode SNR / J / channel and the same noise, jammer and fade
seeds (paired design). Each flowgraph execution has its own experiment_id.

Conditions
    static_*  24 schedules: Es/N0 {4, 8, 12, 16} dB x J {0, 0.05, 0.2} x {AWGN, block Rayleigh},
              constant over the episodes
    step_*    3 schedules that change mid-run (good -> jammed -> good, a fade-in, an SNR ramp)

Statistics (as protocol CL-2, docs/EXPERIMENT_PROTOCOL.md): episodes are NOT
independent samples. Per (condition, policy) the seeds are averaged; paired
differences between policies are taken per condition; 95 % bootstrap CI over
conditions and a Wilcoxon signed-rank test; wins / ties / losses per condition.

Metrics: goodput = (1 - measured PER) x payload rate (BPSK 100 kb/s, QPSK 200 kb/s,
OFDM-QPSK 160 kb/s); SE = goodput / occupied bandwidth; BER bit-weighted.
These are GNU Radio software-simulation results, not over-the-air measurements.

    python experiments/gnuradio_campaign.py [--seeds 5] [--episodes 6] [--n-symbols 4096] [--run-id ID]
    python experiments/gnuradio_campaign.py --smoke          # 2 conditions x 1 seed, for a first check

Outputs results/gnuradio/campaign/<run_id>/ {episodes_steps.csv, runs.csv, summary.csv,
paired.csv, report.md, config.json}.
"""

import argparse
import csv
import os
from collections import defaultdict

from gnuradio_common import blocked_or_none, new_run_dir, run_metadata, write_json


def conditions(n_episodes):
    from src.gnuradio_phy.closed_loop import EpisodeCondition as E
    out = {}
    for ch, fm in (("AWGN", "none"), ("RAYLEIGH", "block")):
        for snr in (4.0, 8.0, 12.0, 16.0):
            for j in (0.0, 0.05, 0.2):
                out[f"static_{ch.lower()}_snr{snr:g}_J{j:g}"] = [E(snr, j, ch, fm)] * n_episodes
    h = n_episodes // 3
    out["step_jammer"] = [E(14.0)] * h + [E(14.0, 0.3)] * h + [E(14.0)] * (n_episodes - 2 * h)
    out["step_fade"] = [E(12.0)] * h + [E(12.0, 0.0, "RAYLEIGH", "block")] * (n_episodes - h)
    out["ramp_snr"] = [E(16.0 - 12.0 * k / max(n_episodes - 1, 1)) for k in range(n_episodes)]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--episodes", type=int, default=6)
    ap.add_argument("--n-symbols", type=int, default=4096)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)
    blocked = blocked_or_none()
    if blocked is not None:
        return blocked

    import numpy as np
    import closed_loop_evaluation as cle
    from src.gnuradio_phy import GRPhyConfig
    from src.gnuradio_phy.closed_loop import POLICIES, run_closed_loop, summarise_episode

    conds = conditions(args.episodes)
    seeds = list(range(1, args.seeds + 1))
    if args.smoke:
        conds = {k: conds[k] for k in ("static_awgn_snr8_J0.05", "step_jammer")}
        seeds = [1]
    out = new_run_dir("campaign", args.run_id or ("smoke" if args.smoke else ""))
    base = GRPhyConfig(n_symbols=args.n_symbols)
    write_json(os.path.join(out, "config.json"), run_metadata({
        "protocol": "GR-CL-1 (episode-based, paired, condition-level statistics)", "policies": POLICIES,
        "seeds": seeds, "episodes": args.episodes, "n_symbols": args.n_symbols,
        "conditions": {k: [c.__dict__ for c in v] for k, v in conds.items()}}))

    steps, runs = [], []
    for ci, (name, sched) in enumerate(conds.items()):
        for s in seeds:
            for pol in POLICIES:
                rows = run_closed_loop(sched, pol, seed=1000 * ci + s, base=base, condition_name=name)
                steps.extend(rows)
                summ = summarise_episode(rows)
                summ["seed"] = s
                runs.append(summ)
        print(f"[{ci + 1}/{len(conds)}] {name}")

    def write(path, rows):
        keys = sorted({k for r in rows for k in r})
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)

    write(os.path.join(out, "episodes_steps.csv"), steps)
    write(os.path.join(out, "runs.csv"), runs)

    agg = defaultdict(list)
    for r in runs:
        agg[r["policy"]].append(r)
    summary = [{"policy": p, "runs": len(v), "goodput_bps": float(np.mean([x["goodput_bps"] for x in v])),
                "ber": float(np.mean([x["ber"] for x in v])), "per": float(np.mean([x["per"] for x in v])),
                "spectral_efficiency": float(np.mean([x["spectral_efficiency"] for x in v])),
                "switches": float(np.mean([x["switches"] for x in v]))} for p, v in agg.items()]
    write(os.path.join(out, "summary.csv"), summary)
    paired = []
    for b in POLICIES:
        if b == "acwra":
            continue
        for metric in ("goodput_bps", "ber", "spectral_efficiency"):
            res = cle.paired_comparison(runs, "acwra", b, metric, list(conds))
            if res:
                paired.append(res)
    write(os.path.join(out, "paired.csv"), paired)
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("# GNU Radio closed-loop campaign\n\nData: GNU Radio software simulation; episode-based "
                 "sequential reconfiguration (decision from episode e applied to episode e+1).\n\n")
        fh.write(f"Conditions {len(conds)}, seeds {len(seeds)}, episodes {args.episodes}, "
                 f"flowgraph runs {len(steps)}.\n\n| policy | goodput kb/s | BER | PER | SE b/s/Hz | switches |\n"
                 "|---|---|---|---|---|---|\n")
        for r in sorted(summary, key=lambda r: -r["goodput_bps"]):
            fh.write(f"| {r['policy']} | {r['goodput_bps'] / 1e3:.1f} | {r['ber']:.4f} | {r['per']:.3f} | "
                     f"{r['spectral_efficiency']:.3f} | {r['switches']:.2f} |\n")
        fh.write("\n## ACWRA - baseline, condition-level paired\n\n| baseline | metric | mean diff | 95 % CI | W/T/L | p |\n"
                 "|---|---|---|---|---|---|\n")
        for r in paired:
            fh.write(f"| {r['b']} | {r['metric']} | {r['mean_diff']:.4g} | [{r['ci95_low']:.4g}, {r['ci95_high']:.4g}] | "
                     f"{r['wins']}/{r['ties']}/{r['losses']} | {r['wilcoxon_p']:.2g} |\n")
        provs = sorted({str(r.get("provenance", "")) for r in steps})
        fh.write(f"\nProvenance of every episode (validator): {provs}\n")
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
