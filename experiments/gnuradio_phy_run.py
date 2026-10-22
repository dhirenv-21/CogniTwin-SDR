"""
ONE GNU RADIO RUN -> validated NPZ export (+ run ledger line).

    python experiments/gnuradio_phy_run.py --modulation QPSK --snr 10 --jammer 0.05 \
        [--channel RAYLEIGH --fading block|time_varying] [--seed 1] [--n-symbols 4096] [--out DIR]

Writes <out>/<experiment_id>.npz (default results/gnuradio/runs/) and appends it to
results/gnuradio/run_ledger.jsonl. Exit 2 = BLOCKED (GNU Radio not importable).
"""

import argparse
import os

from gnuradio_common import DEFAULT_LEDGER_PATH, RESULTS, blocked_or_none, project_root


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modulation", default="QPSK")
    ap.add_argument("--snr", type=float, default=10.0)
    ap.add_argument("--jammer", type=float, default=0.0)
    ap.add_argument("--channel", default="AWGN")
    ap.add_argument("--fading", default="none")
    ap.add_argument("--doppler", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n-symbols", type=int, default=4096)
    ap.add_argument("--out", default=os.path.join(RESULTS, "runs"))
    args = ap.parse_args(argv)
    blocked = blocked_or_none()
    if blocked is not None:
        return blocked

    from src.gnuradio_phy import GRPhyConfig, load_and_validate_gnuradio
    from src.gnuradio_phy.runner import run_and_export

    cfg = GRPhyConfig(modulation=args.modulation, snr_db=args.snr, interference_power=args.jammer,
                      channel=args.channel, fading_mode=args.fading, doppler_fdts=args.doppler,
                      seed=args.seed, n_symbols=args.n_symbols)
    path = run_and_export(cfg, args.out, ledger_path=DEFAULT_LEDGER_PATH)
    _, rep = load_and_validate_gnuradio(path, strict=False, ledger_path=DEFAULT_LEDGER_PATH)
    print(f"export     : {os.path.relpath(path, project_root)}")
    print(f"validation : {rep.summary()}")
    print(f"provenance : {rep.facts['provenance']}")
    for e in rep.errors:
        print(f"  ERROR {e}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
