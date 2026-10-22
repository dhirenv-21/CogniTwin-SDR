"""
COGNITWIN-SDR: SIMULINK -> ACWRA END-TO-END ENTRY POINT  (Task 11, Part 6)

Single command that takes a real MATLAB/Simulink physical-layer export and drives it
through the complete existing CogniTwin-SDR decision stack:

    REAL SIMULINK MEASUREMENT (.mat)
            |
        SimulinkReceiver  (load + strict validation)
            |
        SpectrumAgent     (existing, unmodified)
            |
        DigitalTwin / PredictionAgent / CyberDefenseAgent  (existing, unmodified)
            |
        MultiAgentSnapshot
            |
        DigitalTwin.evaluate_counterfactuals()   <- sandbox, never bypassed
            |
        ACWRAEngine.evaluate_and_decide()        <- U(c) mathematics, untouched
            |
        ACWRADecision + explainability trace

Usage
-----
    python experiments/simulink_acwra_demo.py
    python experiments/simulink_acwra_demo.py --mat simulink/results/measurement_case.mat
    python experiments/simulink_acwra_demo.py --mat <file> --require-real
    python experiments/simulink_acwra_demo.py --list

--require-real makes the run FAIL if the MAT file was not produced by MATLAB/Simulink
(i.e. if it carries source="python-fixture"). That is the guard used for the
"REAL SIMULINK END-TO-END TEST" in Part 10.
"""

import argparse
import glob
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np

from src.simulink_bridge.pipeline import PipelineResult, SimulinkACWRAPipeline
from src.simulink_bridge.reference_phy import FIXTURE_SOURCE_TAG
from src.simulink_bridge.validation import PROVENANCE_SIMULINK, MeasurementValidationError

RESULTS_DIR = os.path.join("simulink", "results")
BAR = "=" * 78


# --------------------------------------------------------------------------- utils


def discover_mat_files(results_dir: str = RESULTS_DIR):
    """Return MAT files under simulink/results/, newest first."""
    pattern = os.path.join(results_dir, "**", "*.mat")
    files = [f for f in glob.glob(pattern, recursive=True)]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def classify_source(measurement) -> str:
    """Label the provenance of a measurement for honest reporting."""
    src = (measurement.source or "unknown").lower()
    kind = getattr(measurement, "provenance", "unknown")
    if src == FIXTURE_SOURCE_TAG:
        return "PYTHON FIXTURE (not Simulink)"
    if kind == PROVENANCE_SIMULINK:
        return "REAL SIMULINK MODEL OUTPUT"
    if src.startswith("simulink"):
        return "CLAIMS SIMULINK BUT NOT WRITTEN BY MATLAB (untrusted label)"
    if kind == "matlab_unlabelled" or src.startswith("matlab"):
        return "MATLAB SCRIPT OUTPUT (no .slx in the loop)"
    if kind == "legacy_python_mat":
        return "LEGACY PYTHON-WRITTEN MAT FILE (not Simulink)"
    return "UNKNOWN PROVENANCE (no 'source' variable in MAT file)"


def _fmt(value, spec="{:.4f}", missing="n/a"):
    try:
        if value is None:
            return missing
        v = float(value)
        if not np.isfinite(v):
            return missing
        return spec.format(v)
    except (TypeError, ValueError):
        return missing


# ------------------------------------------------------------------------- report


def print_report(result: PipelineResult):
    m = result.measurement
    stats = result.iq_statistics
    spec = result.snapshot.spectrum_result
    pred = result.snapshot.prediction_result
    cand = result.snapshot.defense_candidates
    dec = result.decision

    print(BAR)
    print("COGNITWIN-SDR SIMULINK -> ACWRA END-TO-END")
    print(BAR)
    print(f"MAT file      : {result.source_path}")
    print(f"Provenance    : {classify_source(m)}")
    print(f"Validation    : {result.validation.summary() if result.validation else 'n/a'}")
    if result.validation and result.validation.warnings:
        for w in result.validation.warnings[:6]:
            print(f"                warn: {w}")
    print()

    print("[SIMULINK INPUT]")
    print(f"  Samples        : {m.num_samples}")
    print(f"  Sample Rate    : {_fmt(result.sample_rate, '{:.1f}')} Hz"
          f"  ({_fmt(m.duration_s * 1000.0, '{:.3f}')} ms capture)")
    print(f"  Modulation     : {m.modulation}")
    print(f"  SNR (nominal)  : {_fmt(m.snr_db, '{:.2f}')} dB")
    print(f"  Interference   : {_fmt(m.interference_power, '{:.4f}')}"
          f"   (SIR = {_fmt(-10.0 * np.log10(m.interference_power), '{:.2f}') if m.interference_power > 0 else 'inf'} dB)")
    print(f"  Channel        : {m.channel_type}")
    print(f"  Timestamp      : {_fmt(m.timestamp, '{:.4f}')} s")
    print()

    print("[RECEIVED IQ]")
    print(f"  Samples        : {int(stats['num_samples'])}")
    print(f"  Complex        : dtype={m.iq_samples.dtype}, "
          f"non-zero imaginary = {bool(np.any(np.abs(m.iq_samples.imag) > 0))}")
    print(f"  Measured Power : {_fmt(stats['measured_power'])}"
          f"  (RMS {_fmt(stats['rms_magnitude'])}, PAPR {_fmt(stats['papr_db'], '{:.2f}')} dB)")
    print(f"  var(I)/var(Q)  : {_fmt(stats['var_i'])} / {_fmt(stats['var_q'])}")
    print(f"  Dominant Freq  : {_fmt(stats['dominant_frequency_hz'], '{:.1f}')} Hz")
    if "measured_snr_db" in stats:
        print(f"  Measured SINR  : {_fmt(stats['measured_snr_db'], '{:.2f}')} dB"
              f"  (EVM {_fmt(stats.get('evm_percent'), '{:.2f}')} %)  [vs tx reference]")
    else:
        print("  Measured SINR  : n/a (MAT file carried no tx_iq reference)")
    print(f"  BER            : {_fmt(m.ber, '{:.6f}')}"
          + ("" if m.ber > 0 else "   (0 errors measured over the capture)"))
    print()

    print("[SPECTRUM AGENT]   (existing SpectrumAgent, unmodified)")
    print(f"  Analysis windows    : {len(result.windows)} x {result.window_size} samples")
    print(f"  Detected Modulation : {spec.modulation}")
    print(f"  Confidence          : {_fmt(spec.classifier_confidence * 100.0, '{:.1f}')} %")
    print(f"  Anomaly             : {spec.anomaly_flag}")
    print(f"  Evidence            : est SNR {_fmt(spec.snr_db, '{:.2f}')} dB | "
          f"BW {_fmt(spec.bandwidth_hz, '{:.0f}')} Hz | "
          f"interference {_fmt(spec.interference_power)} | t={_fmt(spec.timestamp_s, '{:.5f}')} s")
    match = "MATCH" if spec.modulation.upper() == m.modulation.upper() else "MISMATCH"
    print(f"  vs Simulink truth   : {match} (truth = {m.modulation})")
    print()

    print("[MULTI-AGENT SNAPSHOT]")
    print(f"  Prediction status   : {pred.prediction_status}")
    print(f"  Risk                : {_fmt(pred.risk_score)}  ({pred.risk_level})")
    print(f"  Confidence          : {_fmt(spec.classifier_confidence)}")
    print(f"  Forecast            : SNR {_fmt(pred.next_snr_db, '{:.2f}')} dB | "
          f"BER {_fmt(pred.next_ber, '{:.5f}')} | interference {_fmt(pred.next_interference_power)}")
    print(f"  Defense Candidates  : {cand.candidate_strategies}")
    print(f"  Rationale           : {cand.rationale}")
    print()

    print("[DIGITAL TWIN SANDBOX]   (DigitalTwin.evaluate_counterfactuals - never bypassed)")
    print(f"  {'Candidate':<16} | {'BER':>10} | {'Throughput':>12} | {'SE':>6} | {'Utility':>10}")
    print("  " + "-" * 66)
    util_by_strategy = {cs.strategy: cs for cs in dec.candidate_scores}
    for cf in result.counterfactuals:
        cs = util_by_strategy.get(cf["strategy"])
        se = _fmt(cs.theoretical_se, "{:.2f}") if cs else "n/a"
        util = f"{cs.utility_score:+.4f}" if cs else "n/a"
        marker = "*" if cs and cs.strategy == dec.selected_strategy else " "
        print(f" {marker}{cf['strategy']:<16} | {cf['predicted_ber']:>10.6f} | "
              f"{cf['predicted_throughput_bps']:>12.1f} | {se:>6} | {util:>10}")
    print()

    print("[ACWRA DECISION]   (existing ACWRAEngine; U(c) weights w_t=0.4 w_se=0.2 w_b=0.6 lambda_c=1.0)")
    print(f"  Selected Strategy : {dec.selected_strategy}")
    print(f"  Expected Utility  : {dec.expected_utility:+.6f}")
    print(f"  Risk R            : {_fmt(dec.risk_score)}")
    print(f"  Confidence C      : {_fmt(dec.agent_confidence)}")
    print()

    print("[TRACE]")
    for line in dec.decision_trace.splitlines():
        print("  " + line)
    print(BAR)


# --------------------------------------------------------------------------- main


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a real Simulink measurement through the CogniTwin-SDR ACWRA stack."
    )
    parser.add_argument("--mat", default=None, help="Path to the MATLAB/Simulink MAT export.")
    parser.add_argument("--list", action="store_true", help="List discovered MAT files and exit.")
    parser.add_argument(
        "--require-real",
        action="store_true",
        help="Abort unless the MAT file was produced by MATLAB/Simulink (not a Python fixture).",
    )
    parser.add_argument("--window", type=int, default=512, help="Analysis window size (samples).")
    parser.add_argument("--max-windows", type=int, default=24, help="Max analysis windows.")
    parser.add_argument(
        "--expected-samples", type=int, default=None, help="Assert the received sample count."
    )
    parser.add_argument(
        "--expected-fs", type=float, default=None, help="Assert the reported sample rate (Hz)."
    )
    parser.add_argument(
        "--sample-tolerance", type=int, default=0, help="Allowed sample-count deviation."
    )
    args = parser.parse_args(argv)

    candidates = discover_mat_files()

    if args.list:
        if not candidates:
            print(f"No MAT files found under '{RESULTS_DIR}'.")
            return 1
        print(f"MAT files under '{RESULTS_DIR}' (newest first):")
        for f in candidates:
            print(f"  {f}")
        return 0

    mat_path = args.mat
    if mat_path is None:
        if not candidates:
            print(BAR)
            print("NO SIMULINK MEASUREMENT FOUND")
            print(BAR)
            print(f"Expected a MAT export under '{RESULTS_DIR}'.")
            print("Produce one from MATLAB with:")
            print("    cd simulink/matlab")
            print("    run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')")
            print("Then re-run this script.")
            return 2
        mat_path = candidates[0]
        print(f"[auto] No --mat given; using most recent export: {mat_path}\n")

    pipeline = SimulinkACWRAPipeline(window_size=args.window, max_windows=args.max_windows)

    try:
        result = pipeline.run_from_mat(
            mat_path,
            expected_samples=args.expected_samples,
            expected_sample_rate=args.expected_fs,
            sample_count_tolerance=args.sample_tolerance,
            strict=True,
        )
    except (FileNotFoundError, MeasurementValidationError) as exc:
        print(BAR)
        print("MEASUREMENT REJECTED - PIPELINE NOT RUN")
        print(BAR)
        print(f"  {exc}")
        print("\nNo fallback data was substituted. Fix the export and re-run.")
        return 3

    # The `source` label alone is self-declared; provenance also requires the MAT
    # header to show MATLAB wrote the file (see validation.classify_provenance).
    if args.require_real and result.measurement.provenance != PROVENANCE_SIMULINK:
        print(BAR)
        print("REAL SIMULINK END-TO-END TEST: ABORTED")
        print(BAR)
        src = result.measurement.source or "<absent>"
        print(f"  '{mat_path}' has source='{src}', provenance='{result.measurement.provenance}':")
        print(f"  {result.validation.facts.get('provenance_detail', '')}")
        if src.lower() == FIXTURE_SOURCE_TAG:
            print("  This file came from the Python reference PHY, not from the .slx model.")
        else:
            print("  This file carries no Simulink provenance, so it cannot be certified")
            print("  as real .slx output. Legacy exports written before Task 11 land here.")
        print("  --require-real refuses to present non-Simulink data as a real result.")
        print("\n  Produce a real export with:")
        print("      cd simulink/matlab")
        print("      run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')")
        return 4

    print_report(result)

    if args.require_real:
        print("\nREAL SIMULINK END-TO-END TEST: COMPLETED")
        print("  Every stage above ran on the actual .slx simulation output.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
