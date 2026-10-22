"""
GNU RADIO PHY VALIDATION: BER vs SNR against theory, seed reproducibility, noise
independence, measured SNR / J, fading self-checks.

    python experiments/gnuradio_ber_validation.py [--seeds 3] [--n-symbols 65536] [--run-id ID]

Run from an environment where GNU Radio imports (docs/GNURADIO_SETUP.md); otherwise
prints BLOCKED and exits 2. Outputs results/gnuradio/ber_validation/<run_id>/
{ber.csv, checks.json, report.md, ber_vs_snr.png, config.json}.

Pass rule per point: theory inside the 99.9 % Wilson interval of the pooled measured
BER, widened 10 % relative for RRC truncation ISI. Points with < 20 expected errors
are reported but not judged (too few errors to resolve the BER).
"""

import argparse
import csv
import math
import os

from gnuradio_common import blocked_or_none, new_run_dir, run_metadata, write_json

GRID = {"BPSK": (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0), "QPSK": (0.0, 2.0, 4.0, 6.0, 8.0, 10.0),
        "OFDM-QPSK": (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-symbols", type=int, default=65536)
    ap.add_argument("--run-id", default="")
    args = ap.parse_args(argv)
    blocked = blocked_or_none()
    if blocked is not None:
        return blocked

    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src.gnuradio_phy import GRPhyConfig
    from src.gnuradio_phy.receiver import wilson_interval
    from src.gnuradio_phy.runner import run_gnuradio

    out = new_run_dir("ber_validation", args.run_id)
    rows, checks = [], {}
    for mod, snrs in GRID.items():
        for snr in snrs:
            k = n = 0
            meas_snr, th = [], None
            for s in range(1, args.seeds + 1):
                d = run_gnuradio(GRPhyConfig(modulation=mod, snr_db=snr, n_symbols=args.n_symbols, seed=s))
                k += int(d["bit_errors"])
                n += int(d["bits_compared"])
                meas_snr.append(float(d["measured_snr_db"]))
                th = float(d["ber_theory"])
                if not (d["timing_ok"] and d["gain_capture_ok"]):
                    checks.setdefault("self_check_failures", []).append(str(d["experiment_id"]))
            lo, hi = wilson_interval(k, n, z=3.29)
            judged = th * n >= 20
            ok = (lo * 0.9 <= th <= hi * 1.1) if judged else None
            rows.append({"modulation": mod, "snr_db": snr, "ebn0_db": snr - 10 * math.log10(1 if mod == "BPSK" else 2),
                         "bits": n, "errors": k, "ber": k / n, "ci_low": lo, "ci_high": hi, "ber_theory": th,
                         "judged": judged, "pass": ok, "measured_snr_db_mean": float(np.mean(meas_snr)),
                         "seeds": args.seeds})
            print(f"{mod:9s} Es/N0 {snr:5.1f} dB  BER {k / n:.3e} [{lo:.2e}, {hi:.2e}]  theory {th:.3e}  "
                  f"{'PASS' if ok else ('FAIL' if ok is False else 'not judged')}")

    # reproducibility and independence
    a = run_gnuradio(GRPhyConfig(seed=101, n_symbols=8192))
    b = run_gnuradio(GRPhyConfig(seed=101, n_symbols=8192))
    c = run_gnuradio(GRPhyConfig(seed=102, n_symbols=8192))
    na, nc = a["noise_iq"], c["noise_iq"]
    corr = abs(np.vdot(na, nc)) / math.sqrt(np.vdot(na, na).real * np.vdot(nc, nc).real)
    checks["same_seed_identical"] = bool(np.array_equal(a["iq_samples"], b["iq_samples"]))
    checks["different_seed_noise_corr"] = float(corr)
    checks["different_seed_independent"] = bool(corr < 5 / math.sqrt(na.size))
    j = run_gnuradio(GRPhyConfig(snr_db=12.0, interference_power=0.1, n_symbols=args.n_symbols))
    checks["jammer_measured_power"] = float(j["measured_interference_power"])
    for chan in ("RAYLEIGH", "RICIAN"):
        tv = run_gnuradio(GRPhyConfig(channel=chan, fading_mode="time_varying", doppler_fdts=1e-3, snr_db=20.0))
        checks[f"{chan.lower()}_time_varying_gain_capture_ok"] = bool(tv["gain_capture_ok"])
        checks[f"{chan.lower()}_time_varying_gain_std"] = float(np.std(np.abs(tv["channel_gain_iq"])))
        checks[f"{chan.lower()}_time_varying_ber_vs_conditional_theory"] = [float(tv["ber"]), float(tv["ber_theory"])]
    judged = [r for r in rows if r["judged"]]
    checks["ber_points_judged"] = len(judged)
    checks["ber_points_pass"] = sum(1 for r in judged if r["pass"])

    with open(os.path.join(out, "ber.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_json(os.path.join(out, "checks.json"), checks)
    write_json(os.path.join(out, "config.json"), run_metadata({"seeds": args.seeds, "n_symbols": args.n_symbols,
                                                               "grid": GRID}))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for mod in GRID:
        rr = [r for r in rows if r["modulation"] == mod]
        x = [r["snr_db"] for r in rr]
        ax.semilogy(x, [r["ber_theory"] for r in rr], "-", label=f"{mod} theory")
        ax.errorbar(x, [max(r["ber"], 1e-7) for r in rr],
                    yerr=[[max(r["ber"] - r["ci_low"], 0) for r in rr], [r["ci_high"] - r["ber"] for r in rr]],
                    fmt="o", ms=4, capsize=2, label=f"{mod} GNU Radio")
    ax.set_xlabel("Es/N0 per exported sample [dB]")
    ax.set_ylabel("BER")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7)
    ax.set_title("GNU Radio PHY: measured BER (99.9 % Wilson) vs theory, AWGN")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "ber_vs_snr.png"), dpi=130)
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("# GNU Radio BER validation\n\nData: GNU Radio software simulation (no hardware).\n\n")
        fh.write(f"Judged points: {checks['ber_points_pass']}/{checks['ber_points_judged']} PASS.\n\n")
        fh.write("| mod | Es/N0 dB | bits | errors | BER | 99.9 % CI | theory | result |\n|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            res = "PASS" if r["pass"] else ("FAIL" if r["pass"] is False else "not judged")
            fh.write(f"| {r['modulation']} | {r['snr_db']} | {r['bits']} | {r['errors']} | {r['ber']:.3e} | "
                     f"[{r['ci_low']:.2e}, {r['ci_high']:.2e}] | {r['ber_theory']:.3e} | {res} |\n")
        fh.write("\n```json\n" + __import__("json").dumps(checks, indent=2) + "\n```\n")
    print(f"\nwritten {out}")
    ok = checks["ber_points_pass"] == checks["ber_points_judged"] and checks["same_seed_identical"] \
        and checks["different_seed_independent"] and "self_check_failures" not in checks
    print("OVERALL", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
