"""
REVIEW DEMO: one input through the whole pipeline, then a short closed-loop comparison.

    python experiments/review_demo.py                       # historical real Simulink v3 export
    python experiments/review_demo.py --mat <file.mat>      # any MAT export
    python experiments/review_demo.py --fixture             # Python reference-PHY fixture instead

Part 1 (measurement -> decision) prints the input's provenance class first, then the
Spectrum Agent's estimates, the Digital Twin state, the prediction, the candidate set and
the ACWRA decision trace. Part 2 runs a short closed loop in the Python virtual-RF
environment (NOT Simulink) and compares ACWRA with fixed modulations, a rule and the
clairvoyant oracle on the same seed. No number is invented: everything printed is
computed in this run.
"""

import argparse
import os
import sys
import tempfile

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (project_root, os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np

DEFAULT_MAT = os.path.join(project_root, "simulink", "results", "baseline", "baseline_D.mat")
LABEL = {
    "simulink_export": "REAL SIMULINK EXPORT (MATLAB-written)",
    "simulink_claim_unverified": "CLAIMS SIMULINK BUT NOT MATLAB-WRITTEN (untrusted)",
    "matlab_unlabelled": "MATLAB-WRITTEN, NOT A SIMULINK RUN",
    "legacy_python_mat": "LEGACY PYTHON-WRITTEN FILE",
    "python_fixture": "PYTHON FIXTURE (synthetic, reference PHY)",
    "synthetic_demo": "SYNTHETIC DEMO DATA",
    "unknown": "UNKNOWN PROVENANCE",
}
BAR = "=" * 78


def part1(mat_path):
    from src.simulink_bridge.pipeline import SimulinkACWRAPipeline
    from src.simulink_bridge.validation import MeasurementValidationError

    print(BAR + "\nPART 1 - measurement -> agents -> Digital Twin -> ACWRA\n" + BAR)
    try:
        res = SimulinkACWRAPipeline().run_from_mat(mat_path)
    except (FileNotFoundError, MeasurementValidationError) as exc:
        print(f"INPUT REJECTED (no decision produced): {exc}")
        return 2
    m, rep = res.measurement, res.validation
    print(f"input      : {os.path.relpath(mat_path, project_root)}")
    print(f"provenance : {LABEL.get(m.provenance, m.provenance)}  [{m.provenance}, "
          f"model {rep.facts.get('model_version', '?')}]")
    if m.provenance == "simulink_export" and rep.facts.get("model_version") != "v4":
        print("             HISTORICAL export from the pre-v4 model (noise not seeded); "
              "no v4 export exists yet")
    print(f"validation : {rep.summary()}")
    print(f"configured : {m.modulation}, SNR {m.snr_db:g} dB, interference {m.interference_power:g}, "
          f"{m.channel_type}, {m.num_samples} samples, BER (MATLAB) {m.ber:.5f}")
    w = res.windows[-1]
    s = w.spectrum_result
    print("\n-- Spectrum Agent (last window)")
    print(f"   detected modulation {s.modulation} (confidence {s.classifier_confidence:.2f}), "
          f"blind SNR {s.snr_db:.2f} dB, anomaly {s.anomaly_flag}")
    print(f"   measured SINR (vs tx reference) {w.measured_snr_db:.2f} dB; twin SNR "
          f"{w.twin_snr_db:.2f} dB [{w.twin_snr_source}]")
    t = w.twin_state
    print("\n-- Digital Twin")
    print(f"   modulation {t.modulation}, SNR {t.snr_db:.2f} dB, BER {t.ber:.5f}, interference "
          f"{t.interference_power:g}, channel {t.channel_type}, condition {t.threat_condition} "
          f"(heuristic label, not attack attribution)")
    p = res.snapshot.prediction_result
    print("\n-- Prediction Agent")
    print(f"   status {p.prediction_status}, next SNR {p.next_snr_db:.2f} dB, next BER {p.next_ber:.5f}, "
          f"risk {p.risk_score:.2f} ({p.risk_level})")
    dc = res.snapshot.defense_candidates
    print("\n-- Cyber Defense Agent")
    print(f"   candidates {dc.candidate_strategies}: {dc.rationale}")
    print("\n-- ACWRA")
    print(res.decision.decision_trace)
    return 0


def part2(seed=3):
    import closed_loop_evaluation as cle

    print(BAR + "\nPART 2 - closed loop, Python VIRTUAL RF (NOT Simulink), scenario "
          "dynamic_combat_environment, seed " + str(seed) + "\n" + BAR)
    cfg = cle.original_suite()["dynamic_combat_environment"]
    print(f"{'policy':<18}{'goodput kb/s':>14}{'mean BER':>11}{'regret kb/s':>13}{'switches':>10}")
    for pol in ("acwra", "fixed_BPSK", "fixed_QPSK", "sinr_threshold", "oracle"):
        rows = cle.run_episode(cfg, pol, seed)
        mods = [r["modulation_applied"] for r in rows]
        print(f"{pol:<18}{np.mean([r['goodput_bps'] for r in rows]) / 1e3:>14.1f}"
              f"{np.mean([r['ber'] for r in rows]):>11.4f}"
              f"{np.mean([r['goodput_regret_bps'] for r in rows]) / 1e3:>13.1f}"
              f"{sum(a != b for a, b in zip(mods, mods[1:])):>10d}")
    print("Same seed for every policy: identical channel realisations (paired). "
          "Full statistics: results/evaluation/closed_loop/<run>/summary.md")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CogniTwin-SDR review demo")
    ap.add_argument("--mat", default=None)
    ap.add_argument("--fixture", action="store_true", help="use a Python reference-PHY fixture")
    ap.add_argument("--skip-loop", action="store_true")
    args = ap.parse_args(argv)
    mat = args.mat
    if args.fixture:
        from src.simulink_bridge.reference_phy import write_reference_mat
        mat = write_reference_mat(os.path.join(tempfile.mkdtemp(), "fixture.mat"), modulation="QPSK",
                                  snr_db=12.0, interference_power=0.25, channel_type="Rayleigh", seed=7)
    elif mat is None:
        mat = DEFAULT_MAT
        if not os.path.exists(mat):
            print(f"Default input {mat} not found; use --mat <file> or --fixture.")
            return 2
    rc = part1(mat)
    if not args.skip_loop:
        part2()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
