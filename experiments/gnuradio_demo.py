"""
GNU RADIO DEMO (headless): one GNU Radio run through every stage, then a short
paired closed loop. Everything printed comes from the executed run; nothing is
precomputed. The visual GRC version is grc/cognitwin_phy_demo.grc.

    python experiments/gnuradio_demo.py [--modulation QPSK] [--snr 8] [--jammer 0.05]
                                        [--channel AWGN|RAYLEIGH|RICIAN] [--fading none|block|time_varying]
                                        [--seed 1] [--no-loop]

Writes results/gnuradio/demo/<stamp>/ {<experiment_id>.npz, decision_trace.txt,
waveform.png, spectrum.png, constellation.png, closed_loop.csv}; the NPZ is also
appended to results/gnuradio/run_ledger.jsonl.
"""

import argparse
import csv
import os

from gnuradio_common import DEFAULT_LEDGER_PATH, blocked_or_none, new_run_dir, project_root

BAR = "=" * 78


def _plots(out, d, cap_rx, fs):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    iq = np.asarray(d["iq_samples"])
    tx = np.asarray(d["tx_iq"])
    fig, ax = plt.subplots(2, 1, figsize=(8, 4.5), sharex=True)
    n = min(200, iq.size)
    ax[0].plot(tx[:n].real, label="tx I")
    ax[0].plot(iq[:n].real, ".", ms=3, label="rx I")
    ax[1].plot(tx[:n].imag, label="tx Q")
    ax[1].plot(iq[:n].imag, ".", ms=3, label="rx Q")
    for a in ax:
        a.legend(fontsize=7)
        a.grid(alpha=0.3)
    ax[1].set_xlabel("exported sample")
    fig.suptitle(f"GNU Radio {d['gnuradio_version']}: {d['experiment_id']}", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "waveform.png"), dpi=120)
    plt.close(fig)

    x = np.asarray(cap_rx)
    nfft = 1024
    seg = x[: (x.size // nfft) * nfft].reshape(-1, nfft) * np.hanning(nfft)
    psd = np.mean(np.abs(np.fft.fftshift(np.fft.fft(seg, axis=1), axes=1)) ** 2, axis=0)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(f / 1e3, 10 * np.log10(psd / psd.max() + 1e-15))
    ax.set_xlabel("frequency [kHz]")
    ax.set_ylabel("PSD [dB rel. peak]")
    ax.set_title("received spectrum (flowgraph rate)", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "spectrum.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4, 4))
    if str(d["modulation"]) == "OFDM-QPSK":
        sym = iq[: (iq.size // 80) * 80].reshape(-1, 80)[:, 16:]
        h = np.asarray(d["channel_gain_iq"])[: (iq.size // 80) * 80].reshape(-1, 80)[:, 16:].mean(axis=1)
        z = (np.fft.fft(sym, axis=1) / 8.0 / h[:, None]).reshape(-1)
    else:
        z = iq / np.asarray(d["channel_gain_iq"])
    ax.plot(z.real[:3000], z.imag[:3000], ".", ms=2)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_title("equalised constellation", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "constellation.png"), dpi=120)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modulation", default="QPSK")
    ap.add_argument("--snr", type=float, default=8.0)
    ap.add_argument("--jammer", type=float, default=0.05)
    ap.add_argument("--channel", default="AWGN")
    ap.add_argument("--fading", default="none")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-loop", action="store_true")
    args = ap.parse_args(argv)
    blocked = blocked_or_none()
    if blocked is not None:
        return blocked

    from src.gnuradio_phy import GRPhyConfig, load_and_validate_gnuradio
    from src.gnuradio_phy.closed_loop import EpisodeCondition, run_closed_loop, summarise_episode
    from src.gnuradio_phy.flowgraph import run_flowgraph
    from src.gnuradio_phy.receiver import demodulate_ofdm, demodulate_psk, goodput_bps
    from src.gnuradio_phy.export import IN_PROCESS_RUNS, build_export, write_export
    from src.simulink_bridge.pipeline import SimulinkACWRAPipeline

    cfg = GRPhyConfig(modulation=args.modulation, snr_db=args.snr, interference_power=args.jammer,
                      channel=args.channel, fading_mode=args.fading, seed=args.seed)
    out = new_run_dir("demo")
    print(BAR + "\nPART 1 - GNU Radio flowgraph -> export -> agents -> Digital Twin -> ACWRA\n" + BAR)
    cap, info = run_flowgraph(cfg)
    rx = demodulate_ofdm(cfg, cap) if cfg.modulation == "OFDM-QPSK" else demodulate_psk(cfg, cap)
    d = build_export(cfg, cap, info, rx)
    IN_PROCESS_RUNS[d["experiment_id"]] = d["content_sha256"]
    path = write_export(d, os.path.join(out, f"{d['experiment_id']}.npz"), ledger_path=DEFAULT_LEDGER_PATH)
    meas, rep = load_and_validate_gnuradio(path, ledger_path=DEFAULT_LEDGER_PATH)
    print(f"simulator   : GNU Radio {d['gnuradio_version']} (software simulation, no SDR hardware)")
    print(f"flowgraph   : {d['flowgraph_version']} sha {d['flowgraph_sha256'][:12]}, blocks: {', '.join(info['blocks'])}")
    print(f"export      : {os.path.relpath(path, project_root)}")
    print(f"provenance  : {rep.facts['provenance']} ({rep.facts['provenance_detail']})")
    print(f"validation  : {rep.summary()}")
    print(f"configured  : {cfg.modulation}, {cfg.channel}/{cfg.fading_mode}, Es/N0 {cfg.snr_db:g} dB, J {cfg.interference_power:g}")
    print(f"measured    : Es/N0 {d['measured_snr_db']:.2f} dB (noise branch), J {d['measured_interference_power']:.4f}")
    print(f"PHY result  : BER {d['ber']:.5f} ({d['bit_errors']}/{d['bits_compared']}), theory {d['ber_theory']:.5f}, "
          f"PER {d['per']:.3f}, goodput {goodput_bps(cfg, d['per']) / 1e3:.1f} kb/s")

    res = SimulinkACWRAPipeline().run_measurement(meas, rep, source_path=path)
    w = res.windows[-1]
    s, t, p = w.spectrum_result, w.twin_state, res.snapshot.prediction_result
    print("\n-- Spectrum Agent (last window; blind: sees I/Q only)")
    print(f"   estimated modulation {s.modulation} (confidence {s.classifier_confidence:.2f}), blind SNR {s.snr_db:.2f} dB, "
          f"anomaly {s.anomaly_flag}; interference power is passed through, not estimated")
    print("\n-- Digital Twin")
    print(f"   modulation {t.modulation}, SNR {t.snr_db:.2f} dB [{w.twin_snr_source}], BER {t.ber:.5f}, "
          f"interference {t.interference_power:g}, condition {t.threat_condition} (heuristic label, observed "
          f"condition - not an inferred attack)")
    nxt = "n/a" if p.next_snr_db is None else f"{p.next_snr_db:.2f} dB"
    print("\n-- Prediction Agent")
    print(f"   status {p.prediction_status}, next SNR {nxt}, risk {p.risk_score:.2f} ({p.risk_level})")
    dc = res.snapshot.defense_candidates
    print("\n-- Cyber Defense Agent")
    print(f"   candidates {dc.candidate_strategies}: {dc.rationale}")
    print("\n-- ACWRA")
    print(res.decision.decision_trace)
    with open(os.path.join(out, "decision_trace.txt"), "w", encoding="utf-8") as fh:
        fh.write(res.decision.decision_trace)
    _plots(out, d, cap["rx_os"], cfg.waveform_sample_rate)

    if not args.no_loop:
        print("\n" + BAR + "\nPART 2 - closed loop on GNU Radio (episode-based; decision of episode e "
              "applied to e+1), paired seeds\n" + BAR)
        sched = [EpisodeCondition(14.0)] * 2 + [EpisodeCondition(14.0, 0.3)] * 2 + [EpisodeCondition(14.0)] * 2
        rows_all = []
        print(f"{'policy':<17}{'goodput kb/s':>13}{'BER':>10}{'PER':>8}{'switches':>9}  modulations")
        for pol in ("acwra", "sinr_threshold", "fixed_QPSK", "fixed_BPSK", "no_adaptation"):
            rows = run_closed_loop(sched, pol, seed=args.seed, base=cfg.replace(n_symbols=4096))
            rows_all.extend(rows)
            sm = summarise_episode(rows)
            print(f"{pol:<17}{sm['goodput_bps'] / 1e3:>13.1f}{sm['ber']:>10.4f}{sm['per']:>8.3f}{sm['switches']:>9}  "
                  f"{' '.join(r['modulation_applied'] for r in rows)}")
        with open(os.path.join(out, "closed_loop.csv"), "w", newline="") as fh:
            keys = sorted({k for r in rows_all for k in r})
            wr = csv.DictWriter(fh, fieldnames=keys)
            wr.writeheader()
            wr.writerows(rows_all)
        print(f"episode provenance: {sorted({r['provenance'] for r in rows_all})}")
        print("One condition and one seed: an illustration, not evidence. See gnuradio_campaign.py.")
    print(f"\nartifacts: {os.path.relpath(out, project_root)}  (mean values printed above came from this run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
