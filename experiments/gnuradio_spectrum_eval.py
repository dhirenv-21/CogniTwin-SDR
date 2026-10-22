"""
SPECTRUM AGENT ON GNU RADIO I/Q (existing agent, unchanged).

Independent test data: every capture is a fresh GNU Radio run with seed >= 500000
(the classifier was trained on Python-generated signals, never on GNU Radio output).
Each capture is split into the bridge pipeline's 512-sample windows.

Inputs the agent sees: the I/Q window only (classification and SNR are blind).
NOT estimated: interference power - the existing SpectrumAgent passes the value it is
given through (env_interference_power), so this script passes 0 and does not report
an interference-estimation accuracy.

    python experiments/gnuradio_spectrum_eval.py [--seeds 4] [--run-id ID]

Outputs results/gnuradio/spectrum_eval/<run_id>/ {windows.csv, metrics.json, report.md, config.json}.
"""

import argparse
import csv
import math
import os
from collections import defaultdict

from gnuradio_common import blocked_or_none, new_run_dir, run_metadata, write_json

SNRS = (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0)
IMPAIRMENTS = {"awgn": dict(), "block_rayleigh": dict(channel="RAYLEIGH", fading_mode="block"),
               "tv_rayleigh": dict(channel="RAYLEIGH", fading_mode="time_varying", doppler_fdts=1e-4),
               "jammer": dict(interference_power=0.1)}
MODS = ("BPSK", "QPSK", "OFDM-QPSK")
SEED_BASE = 500000


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--run-id", default="")
    args = ap.parse_args(argv)
    blocked = blocked_or_none()
    if blocked is not None:
        return blocked

    import numpy as np
    import spectrum_agent_eval as sae
    from src.gnuradio_phy import GRPhyConfig
    from src.gnuradio_phy.runner import run_gnuradio
    from src.simulink_bridge.pipeline import SimulinkACWRAPipeline
    from src.simulink_bridge.protocol import SimulinkMeasurement
    from src.simulink_bridge.receiver import SimulinkReceiver

    out = new_run_dir("spectrum_eval", args.run_id)
    rows = []
    agent = SimulinkACWRAPipeline().orchestrator.spectrum_agent
    for mod in MODS:
        n_sym = 9984 if mod == "OFDM-QPSK" else 12288        # ~24 windows of 512 samples
        for imp, kw in IMPAIRMENTS.items():
            for snr in SNRS:
                for s in range(args.seeds):
                    cfg = GRPhyConfig(modulation=mod, snr_db=snr, n_symbols=n_sym, seed=SEED_BASE + s, **kw)
                    d = run_gnuradio(cfg)
                    iq = np.asarray(d["iq_samples"])
                    g2 = np.abs(np.asarray(d["channel_gain_iq"])) ** 2
                    p_n = np.abs(np.asarray(d["noise_iq"])) ** 2
                    p_j = np.abs(np.asarray(d["interference_iq"])) ** 2
                    p_tx = np.abs(np.asarray(d["tx_iq"])) ** 2
                    agent.prev_snr_db = None
                    for w, lo in enumerate(range(0, iq.size - 511, 512)):
                        sl = slice(lo, lo + 512)
                        m = SimulinkMeasurement(iq_samples=iq[sl], snr_db=0.0, ber=0.0, modulation="UNKNOWN",
                                                sample_rate=cfg.symbol_rate, source="gnuradio")
                        x, t, _ = SimulinkReceiver.convert_for_spectrum_agent(m)
                        r = agent.process(iq_samples=x, timestamp_s=t, env_interference_power=0.0)
                        true_sinr = 10 * math.log10(np.mean(g2[sl] * p_tx[sl]) / np.mean(p_n[sl] + p_j[sl]))
                        rows.append({"modulation": mod, "impairment": imp, "snr_db": snr, "seed": cfg.seed,
                                     "window": w, "predicted": r.modulation, "confidence": r.classifier_confidence,
                                     "snr_est_db": r.snr_db, "true_sinr_db": true_sinr,
                                     "anomaly": r.anomaly_flag, "experiment_id": d["experiment_id"]})
                print(f"{mod:9s} {imp:15s} done")

    labels = sorted({r["predicted"] for r in rows} | set(MODS))
    conf = {a: {b: 0 for b in labels} for a in MODS}
    for r in rows:
        conf[r["modulation"]][r["predicted"]] += 1
    prf = {}
    for c in MODS:
        tp = conf[c][c]
        fp = sum(conf[a][c] for a in MODS if a != c)
        fn = sum(v for k, v in conf[c].items() if k != c)
        p = tp / (tp + fp) if tp + fp else float("nan")
        rc = tp / (tp + fn) if tp + fn else float("nan")
        prf[c] = {"precision": p, "recall": rc, "f1": 2 * p * rc / (p + rc) if p + rc else float("nan")}
    correct = [r["predicted"] == r["modulation"] for r in rows]
    acc_by = defaultdict(list)
    snr_err = defaultdict(list)
    for r, ok in zip(rows, correct):
        acc_by[(r["impairment"], r["snr_db"])].append(ok)
        if r["true_sinr_db"] >= 5:
            snr_err[(r["modulation"], r["impairment"])].append(r["snr_est_db"] - r["true_sinr_db"])
    metrics = {
        "windows": len(rows), "accuracy": float(np.mean(correct)),
        "ece_10bin": sae.ece([r["confidence"] for r in rows], correct),
        "confusion": conf, "per_class": prf,
        "accuracy_by_impairment_snr": {f"{k[0]}@{k[1]:+.0f}dB": float(np.mean(v)) for k, v in sorted(acc_by.items())},
        "snr_bias_db_true_sinr_ge_5dB": {f"{k[0]}/{k[1]}": float(np.mean(v)) for k, v in sorted(snr_err.items())},
        "snr_mae_db_true_sinr_ge_5dB": {f"{k[0]}/{k[1]}": float(np.mean(np.abs(v))) for k, v in sorted(snr_err.items())},
        "false_snr_drop_rate": float(np.mean([r["anomaly"] == "SNR_DROP" for r in rows if r["impairment"] == "awgn"])),
        "interference_estimation": "NOT EVALUATED: the SpectrumAgent passes interference power through",
    }
    with open(os.path.join(out, "windows.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_json(os.path.join(out, "metrics.json"), metrics)
    write_json(os.path.join(out, "config.json"), run_metadata({"seeds": args.seeds, "seed_base": SEED_BASE,
                                                               "snrs": SNRS, "impairments": IMPAIRMENTS}))
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("# Spectrum Agent on GNU Radio I/Q\n\nData: GNU Radio software simulation, "
                 f"{len(rows)} windows.\n\nAccuracy {metrics['accuracy']:.3f}, ECE {metrics['ece_10bin']:.3f}.\n\n")
        fh.write("```json\n" + __import__("json").dumps(metrics, indent=2) + "\n```\n")
    print(f"accuracy {metrics['accuracy']:.3f}  ECE {metrics['ece_10bin']:.3f}  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
