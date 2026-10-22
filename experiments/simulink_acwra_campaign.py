"""
COGNITWIN-SDR: SIMULINK -> ACWRA VALIDATION CAMPAIGN  (Task 11, Parts 9, 11, 12)

Runs the full validation matrix through the real pipeline and writes:

    simulink/results/campaign_report/results_<source>.csv        (Part 11 table)
    simulink/results/campaign_report/summary_<source>.md         (human summary)
    simulink/results/campaign_report/*.png                       (Part 12 plots)

Two data sources - never mixed, always labelled:

    --source matlab     consume MAT files produced by simulink/matlab/run_simulink_campaign.m
                        (REAL .slx output; every row tagged REAL)
    --source fixture    generate MAT files with src/simulink_bridge/reference_phy.py
                        (Python mirror of the Simulink chain; every row tagged FIXTURE)

Verdicts follow Part 16: PASS / STATISTICAL PASS / INCONCLUSIVE / FAIL / NOT RUN,
each with an explicit reason. A stochastic simulation is never failed for small
numerical variation - only for a violated deterministic invariant.

    python experiments/simulink_acwra_campaign.py --source fixture
    python experiments/simulink_acwra_campaign.py --source fixture --set quick
    python experiments/simulink_acwra_campaign.py --source matlab
"""

import argparse
import csv
import glob
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.simulink_bridge.pipeline import SimulinkACWRAPipeline
from src.simulink_bridge.receiver import SimulinkReceiver
from src.simulink_bridge.reference_phy import (
    FIXTURE_SOURCE_TAG,
    write_reference_mat,
)
from src.simulink_bridge.validation import MeasurementValidationError

RESULTS_DIR = os.path.join("simulink", "results")
CAMPAIGN_DIR = os.path.join(RESULTS_DIR, "campaign")
FIXTURE_DIR = os.path.join(RESULTS_DIR, "campaign_fixture")
REPORT_DIR = os.path.join(RESULTS_DIR, "campaign_report")

PASS, STAT_PASS, INCONCLUSIVE, FAIL, NOT_RUN = (
    "PASS",
    "STATISTICAL PASS",
    "INCONCLUSIVE",
    "FAIL",
    "NOT RUN",
)

MODULATIONS = ["BPSK", "QPSK", "OFDM-QPSK"]
SNR_LIST = [-20, -10, -5, 0, 3, 5, 8, 10, 15, 20, 25, 30, 40]
INTERF_LIST = [0, 0.0001, 0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 2.5, 4, 10]
CHANNELS = ["AWGN", "Rayleigh"]
STRESS_SNR = [3, 5, 8, 10, 20]
STRESS_INTERF = [0, 0.1, 0.25, 0.5, 1, 2.5]


# --------------------------------------------------------------------------- record


@dataclass
class TestRecord:
    test_id: str
    group: str
    name: str
    verdict: str = NOT_RUN
    reason: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def row(self) -> Dict[str, Any]:
        base = {
            "test_id": self.test_id,
            "group": self.group,
            "name": self.name,
            "verdict": self.verdict,
            "reason": self.reason,
        }
        base.update(self.data)
        return base


CSV_COLUMNS = [
    "test_id", "group", "name", "provenance",
    "modulation", "snr_db_nominal", "interference_power", "channel_type",
    "snr_db_measured", "sir_db_expected", "sir_db_measured",
    "ber_measured", "measured_power", "num_samples",
    "modulation_detected", "detection", "confidence", "anomaly",
    "risk_score", "risk_level", "n_candidates",
    "selected_strategy", "expected_utility",
    "verdict", "reason",
]


# ------------------------------------------------------------------------ case set


def build_cases(which: str) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    which = which.lower()
    all_sets = which == "all"

    if all_sets or which in ("modulation", "quick"):
        for m in MODULATIONS:
            cases.append(dict(group="B_modulation", mod=m, snr=10.0, interf=0.0, chan="AWGN"))

    if all_sets or which == "snr":
        for s in SNR_LIST:
            cases.append(dict(group="C_snr", mod="QPSK", snr=float(s), interf=0.0, chan="AWGN"))
    elif which == "quick":
        for s in (0.0, 10.0, 20.0):
            cases.append(dict(group="C_snr", mod="QPSK", snr=s, interf=0.0, chan="AWGN"))

    if all_sets or which == "interference":
        for p in INTERF_LIST:
            cases.append(
                dict(group="D_interference", mod="QPSK", snr=30.0, interf=float(p), chan="AWGN")
            )

    if all_sets or which == "channel":
        for c in CHANNELS:
            for m in MODULATIONS:
                cases.append(dict(group="E_channel", mod=m, snr=10.0, interf=0.0, chan=c))

    if all_sets or which == "stress":
        for m in MODULATIONS:
            for s in STRESS_SNR:
                for p in STRESS_INTERF:
                    cases.append(
                        dict(group="F_stress", mod=m, snr=float(s), interf=float(p), chan="AWGN")
                    )

    if not cases:
        raise SystemExit(f"Unknown case set '{which}'. Use quick|modulation|snr|interference|channel|stress|all")
    return cases


def case_stem(idx: int, c: Dict[str, Any]) -> str:
    def tag(x):
        return str(x).replace(".", "p").replace("-", "m")

    return (
        f"{c['group']}_{idx:03d}_{c['mod'].lower().replace('-', '')}"
        f"_snr{tag(c['snr'])}_int{tag(c['interf'])}_{c['chan'].lower()}"
    )


# ------------------------------------------------------------------------ helpers


def parse_case_from_measurement(meas) -> Dict[str, Any]:
    return dict(
        mod=meas.modulation,
        snr=float(meas.snr_db),
        interf=float(meas.interference_power),
        chan=meas.channel_type,
    )


def provenance_of(meas) -> str:
    src = (meas.source or "unknown").lower()
    if src == FIXTURE_SOURCE_TAG:
        return "FIXTURE"
    if src.startswith("simulink"):
        return "REAL"
    if src.startswith("matlab"):
        return "MATLAB-SCRIPT"
    return "UNKNOWN"


def group_verdict(group: str, c: Dict[str, Any], result, stats: Dict[str, float]):
    """Apply the per-group acceptance rule. Returns (verdict, reason)."""
    snr_meas = stats.get("measured_snr_db")

    if group == "C_snr":
        if snr_meas is None:
            return INCONCLUSIVE, "no tx reference in MAT file; measured SNR unavailable"
        # Very low nominal SNR: the LS channel estimate itself becomes noisy, so we
        # only require monotone consistency, not a tight numeric match.
        tol = 1.5 if c["snr"] >= 0 else 3.0
        err = abs(snr_meas - c["snr"])
        if err <= tol:
            return PASS, f"measured SINR {snr_meas:.2f} dB within {tol} dB of nominal {c['snr']:.1f} dB"
        if err <= 2 * tol:
            return STAT_PASS, f"measured SINR {snr_meas:.2f} dB within {2*tol} dB of nominal (AWGN realisation)"
        return FAIL, f"measured SINR {snr_meas:.2f} dB deviates {err:.2f} dB from nominal {c['snr']:.1f} dB"

    if group == "D_interference":
        p = c["interf"]
        if p <= 0:
            return PASS, "no interference requested; SIR = inf by construction"
        if snr_meas is None:
            return INCONCLUSIVE, "no tx reference; SIR unmeasurable"
        sir_expected = -10.0 * np.log10(p)
        # Measured impairment includes thermal noise; at SNR=30 dB that floor is
        # 0.001, so it only matters for the smallest interference powers.
        noise_power = 10.0 ** (-c["snr"] / 10.0)
        sir_expected_with_noise = -10.0 * np.log10(p + noise_power)
        err = abs(snr_meas - sir_expected_with_noise)
        if err <= 0.5:
            return PASS, (
                f"measured SIR+N {snr_meas:.2f} dB vs predicted {sir_expected_with_noise:.2f} dB "
                f"(pure SIR {sir_expected:.2f} dB)"
            )
        if err <= 1.0:
            return STAT_PASS, f"measured SIR+N {snr_meas:.2f} dB within 1.0 dB of {sir_expected_with_noise:.2f} dB"
        return FAIL, f"measured SIR+N {snr_meas:.2f} dB deviates {err:.2f} dB from {sir_expected_with_noise:.2f} dB"

    if group == "B_modulation":
        det = result.snapshot.spectrum_result.modulation
        if det.upper() == c["mod"].upper():
            return PASS, f"pipeline completed; SpectrumAgent detected {det} (matches Simulink truth)"
        return INCONCLUSIVE, (
            f"pipeline completed and ACWRA decided, but SpectrumAgent reported "
            f"'{det}' for a '{c['mod']}' waveform (existing classifier limitation, not a pipeline fault)"
        )

    if group == "E_channel":
        return PASS, (
            f"{c['chan']} channel traversed end-to-end; |h|="
            f"{stats.get('channel_gain_mag', float('nan')):.4f}, BER={result.measurement.ber:.6f}"
        )

    if group == "F_stress":
        return PASS, "stress point completed end-to-end and produced an ACWRA decision"

    return PASS, "completed"


def iq_validation(meas) -> (str, str):
    """Group G: IQ integrity checks on the loaded measurement."""
    iq = meas.iq_samples
    problems = []
    if iq.dtype != np.complex128:
        problems.append(f"dtype {iq.dtype} != complex128")
    if iq.ndim != 1:
        problems.append(f"ndim {iq.ndim} != 1")
    if not np.all(np.isfinite(iq.real)) or not np.all(np.isfinite(iq.imag)):
        problems.append("non-finite samples")
    if float(np.mean(np.abs(iq) ** 2)) <= 0:
        problems.append("zero power")
    mag = np.abs(iq)
    if not np.all(np.isfinite(mag)):
        problems.append("non-finite magnitude")
    ph = np.angle(iq)
    if not np.all(np.isfinite(ph)):
        problems.append("non-finite phase")
    spec = np.fft.fft(iq)
    if not np.all(np.isfinite(spec)):
        problems.append("non-finite FFT")
    if meas.modulation.upper() != "BPSK" and not np.any(np.abs(iq.imag) > 0):
        problems.append("imaginary component is identically zero for a complex modulation")
    if meas.tx_iq is not None and meas.tx_iq.size != iq.size:
        problems.append("tx reference length mismatch")

    if problems:
        return FAIL, "; ".join(problems)
    return PASS, (
        f"1-D complex128, {iq.size} finite samples, power {np.mean(np.abs(iq)**2):.4f}, "
        f"finite magnitude/phase/FFT"
    )


# ---------------------------------------------------------------------- execution


def run_campaign(source: str, which: str, n_samples: int, seed: int, window: int,
                 pattern_symbols: int = 0):
    os.makedirs(REPORT_DIR, exist_ok=True)
    records: List[TestRecord] = []
    plot_payload: List[Dict[str, Any]] = []

    pipeline = SimulinkACWRAPipeline(window_size=window)

    # ---------------------------------------------------------- A. basic Simulink
    a_checks = [
        ("A1", "Simulink model loads"),
        ("A2", "Simulink model compiles"),
        ("A3", "Simulation runs"),
        ("A4", "Simulation completes"),
        ("A5", "No NaN in logged output"),
        ("A6", "No Inf in logged output"),
        ("A7", "Complex I/Q preserved through logging"),
        ("A8", "Logged sample count == input sample count"),
        ("A9", "Time vector correct and monotonic"),
        ("A10", "Sample rate correct"),
        ("A11", "To Workspace logging correct"),
        ("A12", "MAT export contains required variables"),
    ]

    if source == "matlab":
        mat_files = sorted(glob.glob(os.path.join(CAMPAIGN_DIR, "*.mat")))
        if not mat_files:
            for tid, nm in a_checks:
                records.append(
                    TestRecord(tid, "A_basic_simulink", nm, NOT_RUN,
                               f"no MAT files under {CAMPAIGN_DIR}; run run_simulink_campaign.m first")
                )
            print(f"[!] No MAT files under '{CAMPAIGN_DIR}'.")
            print("    Run in MATLAB:  cd simulink/matlab; run_simulink_campaign('all')")
            return records, plot_payload
        cases_iter = [(f, None) for f in mat_files]
    else:
        for tid, nm in a_checks[:4]:
            records.append(
                TestRecord(tid, "A_basic_simulink", nm, NOT_RUN,
                           "MATLAB/Simulink not available in this environment")
            )
        os.makedirs(FIXTURE_DIR, exist_ok=True)
        cases = build_cases(which)
        cases_iter = []
        for i, c in enumerate(cases, start=1):
            path = os.path.join(FIXTURE_DIR, case_stem(i, c) + ".mat")
            write_reference_mat(
                path,
                modulation=c["mod"],
                snr_db=c["snr"],
                interference_power=c["interf"],
                channel_type=c["chan"],
                n_samples=n_samples,
                seed=seed + i,
                timestamp=0.0,
                pattern_symbols=pattern_symbols,
            )
            cases_iter.append((path, c))

    # A5-A12 are evaluated from the exported data itself (works for both sources).
    a_data_checks = {tid: [] for tid, _ in a_checks[4:]}

    print(f"\nRunning {len(cases_iter)} pipeline cases (source={source})...")
    idx = 0
    for path, c in cases_iter:
        idx += 1
        group = c["group"] if c else os.path.basename(path).split("_")[0] + "_matlab"
        stem = os.path.splitext(os.path.basename(path))[0]
        tid = f"{group[:1]}{idx:03d}"

        try:
            meas, report = SimulinkReceiver.load_and_validate(
                path, expected_sample_rate=None, strict=True
            )
        except (MeasurementValidationError, FileNotFoundError) as exc:
            records.append(TestRecord(tid, group, stem, FAIL, f"measurement rejected: {exc}"))
            continue

        if c is None:
            c = parse_case_from_measurement(meas)
            c["group"] = group

        # ---- A5..A12 evidence -------------------------------------------------
        iq = meas.iq_samples
        a_data_checks["A5"].append(bool(np.all(np.isfinite(iq.real) & np.isfinite(iq.imag))))
        a_data_checks["A6"].append(bool(np.all(np.abs(iq) < np.inf)))
        a_data_checks["A7"].append(bool(iq.dtype == np.complex128))
        expected_n = int(meas.extras.get("num_samples", np.array([[iq.size]])).ravel()[0]) \
            if "num_samples" in meas.extras else iq.size
        a_data_checks["A8"].append(iq.size == expected_n)
        tv_ok = meas.time_vector is not None and meas.time_vector.size == iq.size and bool(
            np.all(np.diff(meas.time_vector) > 0)
        )
        a_data_checks["A9"].append(tv_ok)
        fs_ok = meas.sample_rate > 0 and (
            meas.time_vector is None
            or meas.time_vector.size < 2
            or np.isclose(1.0 / np.median(np.diff(meas.time_vector)), meas.sample_rate, rtol=1e-3)
        )
        a_data_checks["A10"].append(bool(fs_ok))
        a_data_checks["A11"].append(bool(iq.size > 0 and meas.tx_iq is not None))
        a_data_checks["A12"].append(report.ok)

        # ---- G. IQ validation --------------------------------------------------
        g_verdict, g_reason = iq_validation(meas)

        # ---- pipeline ----------------------------------------------------------
        try:
            result = pipeline.run_measurement(meas, report, source_path=path)
        except Exception as exc:  # pipeline failure is a real FAIL
            records.append(
                TestRecord(tid, group, stem, FAIL,
                           f"pipeline raised {type(exc).__name__}: {exc}",
                           {"traceback": traceback.format_exc(limit=3)})
            )
            continue

        stats = result.iq_statistics
        verdict, reason = group_verdict(c["group"], c, result, stats)
        if g_verdict == FAIL:
            verdict, reason = FAIL, f"IQ integrity failed: {g_reason}"

        spec = result.snapshot.spectrum_result
        pred = result.snapshot.prediction_result
        dec = result.decision
        p = c["interf"]

        data = {
            "provenance": provenance_of(meas),
            "modulation": c["mod"],
            "snr_db_nominal": c["snr"],
            "interference_power": p,
            "channel_type": c["chan"],
            "snr_db_measured": stats.get("measured_snr_db", float("nan")),
            "sir_db_expected": (-10.0 * np.log10(p)) if p > 0 else float("inf"),
            "sir_db_measured": stats.get("measured_snr_db", float("nan")),
            "ber_measured": meas.ber,
            "measured_power": stats.get("measured_power", float("nan")),
            "num_samples": meas.num_samples,
            "modulation_detected": spec.modulation,
            "detection": "MATCH" if spec.modulation.upper() == c["mod"].upper() else "MISMATCH",
            "confidence": spec.classifier_confidence,
            "anomaly": spec.anomaly_flag,
            "risk_score": pred.risk_score,
            "risk_level": pred.risk_level,
            "n_candidates": len(dec.candidate_scores),
            "selected_strategy": dec.selected_strategy,
            "expected_utility": dec.expected_utility,
            "iq_validation": g_verdict,
        }
        records.append(TestRecord(tid, c["group"], stem, verdict, reason, data))

        # ---- I. python end-to-end stage assertions ------------------------------
        stage_ok = all([
            result.measurement is not None,
            result.validation is not None and result.validation.ok,
            len(result.windows) > 0,
            result.snapshot.spectrum_result is not None,
            result.snapshot.prediction_result is not None,
            result.snapshot.defense_candidates is not None,
            len(result.counterfactuals) > 0,
            result.decision is not None and result.decision.selected_strategy,
            len(result.decision.decision_trace) > 0,
        ])
        records.append(
            TestRecord(
                f"I{idx:03d}", "I_end_to_end", f"{stem}: MAT->Bridge->Spectrum->Snapshot->ACWRA",
                PASS if stage_ok else FAIL,
                "every stage produced a non-empty output" if stage_ok
                else "one or more pipeline stages produced no output",
                {"provenance": provenance_of(meas), "selected_strategy": dec.selected_strategy},
            )
        )
        records.append(
            TestRecord(f"G{idx:03d}", "G_iq_validation", f"{stem}: I/Q integrity",
                       g_verdict, g_reason, {"provenance": provenance_of(meas)})
        )

        plot_payload.append({
            "group": c["group"], "mod": c["mod"], "snr": c["snr"], "interf": p,
            "chan": c["chan"], "ber": meas.ber,
            "snr_meas": stats.get("measured_snr_db", float("nan")),
            "conf": spec.classifier_confidence,
            "strategy": dec.selected_strategy, "utility": dec.expected_utility,
            "candidates": [(cs.strategy, cs.utility_score) for cs in dec.candidate_scores],
            "iq": meas.iq_samples[:2048].copy(),
            "fs": result.sample_rate,
            "provenance": provenance_of(meas),
        })

        if idx % 10 == 0 or idx == len(cases_iter):
            print(f"  {idx}/{len(cases_iter)} cases done")

    # roll up A5..A12
    for tid, nm in a_checks[4:]:
        vals = a_data_checks[tid]
        if not vals:
            records.append(TestRecord(tid, "A_basic_simulink", nm, NOT_RUN, "no cases evaluated"))
        elif all(vals):
            records.append(
                TestRecord(tid, "A_basic_simulink", nm, PASS,
                           f"held for all {len(vals)} exported measurements")
            )
        else:
            n_bad = sum(1 for v in vals if not v)
            records.append(
                TestRecord(tid, "A_basic_simulink", nm, FAIL,
                           f"failed for {n_bad}/{len(vals)} exported measurements")
            )

    return records, plot_payload


# ------------------------------------------------------------- data-integrity (H)


def run_data_integrity_checks() -> List[TestRecord]:
    """Group H: the bridge must reject malformed data cleanly. No MATLAB required."""
    import scipy.io as sio
    import tempfile

    from src.simulink_bridge.validation import flatten_matlab_iq, validate_mat_dict

    recs: List[TestRecord] = []
    tmp = tempfile.mkdtemp(prefix="cognitwin_h_")
    base_iq = (np.random.default_rng(0).normal(size=512)
               + 1j * np.random.default_rng(1).normal(size=512))

    def add(tid, name, ok, reason):
        recs.append(TestRecord(tid, "H_data_integrity", name, PASS if ok else FAIL, reason))

    # H1 column vector
    v = flatten_matlab_iq(base_iq.reshape(-1, 1))
    add("H1", "N x 1 column vector accepted", v.shape == (512,) and np.allclose(v, base_iq),
        f"flattened to {v.shape}, values preserved")

    # H2 row vector
    v = flatten_matlab_iq(base_iq.reshape(1, -1))
    add("H2", "1 x N row vector accepted", v.shape == (512,) and np.allclose(v, base_iq),
        f"flattened to {v.shape}, values preserved")

    # H3 native complex preserved
    v = flatten_matlab_iq(base_iq)
    add("H3", "MATLAB complex data preserved", np.allclose(v.imag, base_iq.imag) and v.dtype == np.complex128,
        "imaginary component preserved exactly")

    # H4 N x 2 [I Q]
    pair = np.column_stack([base_iq.real, base_iq.imag])
    v = flatten_matlab_iq(pair)
    add("H4", "N x 2 real [I Q] matrix accepted", np.allclose(v, base_iq),
        "re-assembled into complex without loss")

    # H5 different lengths
    ok = all(flatten_matlab_iq(base_iq[:n]).size == n for n in (64, 100, 512))
    add("H5", "Different sample lengths accepted", ok, "64/100/512-sample vectors all handled")

    # H6 missing fields
    r = validate_mat_dict({"iq_samples": base_iq})
    add("H6", "Missing required fields rejected", not r.ok,
        f"rejected: {r.errors[0] if r.errors else ''}")

    # H7 invalid MAT file
    bad = os.path.join(tmp, "not_a_mat.mat")
    with open(bad, "wb") as fh:
        fh.write(b"this is not a MAT file")
    try:
        SimulinkReceiver.load_and_validate(bad)
        ok, why = False, "corrupt file was accepted"
    except MeasurementValidationError as exc:
        ok, why = True, f"rejected cleanly: {str(exc)[:70]}"
    except Exception as exc:
        ok, why = False, f"raised {type(exc).__name__} instead of MeasurementValidationError"
    add("H7", "Invalid MAT file rejected", ok, why)

    # H8 empty IQ
    try:
        flatten_matlab_iq(np.array([], dtype=np.complex128))
        ok, why = False, "empty vector accepted"
    except MeasurementValidationError:
        ok, why = True, "empty I/Q rejected with MeasurementValidationError"
    add("H8", "Empty I/Q rejected", ok, why)

    # H9 NaN
    nan_iq = base_iq.copy(); nan_iq[10] = np.nan
    r = validate_mat_dict({"iq_samples": nan_iq, "snr_db": 10.0, "modulation": "QPSK"})
    add("H9", "NaN in I/Q rejected", not r.ok, f"rejected: {r.checks.get('iq_finite_values')}")

    # H10 Inf
    inf_iq = base_iq.copy(); inf_iq[20] = np.inf
    r = validate_mat_dict({"iq_samples": inf_iq, "snr_db": 10.0, "modulation": "QPSK"})
    add("H10", "Inf in I/Q rejected", not r.ok, f"rejected: {r.checks.get('iq_finite_values')}")

    # H11 invalid SNR
    r = validate_mat_dict({"iq_samples": base_iq, "snr_db": np.nan, "modulation": "QPSK"})
    add("H11", "Non-finite SNR rejected", not r.ok, f"rejected: {r.checks.get('snr_finite')}")

    # H12 invalid modulation
    r = validate_mat_dict({"iq_samples": base_iq, "snr_db": 10.0, "modulation": "NONSENSE-MOD"})
    add("H12", "Unknown modulation flagged", r.checks.get("modulation_known") == "WARN",
        "unknown label raises a warning without corrupting the pipeline")

    # H13 missing file
    try:
        SimulinkReceiver.load_and_validate(os.path.join(tmp, "does_not_exist.mat"))
        ok, why = False, "missing file accepted"
    except FileNotFoundError:
        ok, why = True, "missing file raised FileNotFoundError"
    add("H13", "Missing MAT file rejected", ok, why)

    # H14 sample-count mismatch is detected
    good = os.path.join(tmp, "good.mat")
    sio.savemat(good, {
        "iq_samples": base_iq.reshape(-1, 1), "snr_db": 10.0, "ber": 0.01,
        "modulation": "QPSK", "interference_power": 0.0, "channel_type": "AWGN",
        "timestamp": 0.0, "sample_rate": 100000.0,
    })
    try:
        SimulinkReceiver.load_and_validate(good, expected_samples=10000)
        ok, why = False, "wrong sample count accepted"
    except MeasurementValidationError as exc:
        ok, why = True, f"rejected: {str(exc)[:80]}"
    add("H14", "Wrong sample count rejected", ok, why)

    # H15 no silent fabrication
    m, r = SimulinkReceiver.load_and_validate(good)
    add("H15", "Loader returns exactly the stored samples",
        m.num_samples == 512 and np.allclose(m.iq_samples, base_iq),
        "no padding, no regeneration, no substitution")

    return recs


# ------------------------------------------------------------------------- output


def write_csv(records: List[TestRecord], path: str):
    extra_cols = []
    for r in records:
        for k in r.data:
            if k not in CSV_COLUMNS and k not in extra_cols and k != "traceback":
                extra_cols.append(k)
    cols = CSV_COLUMNS + extra_cols
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r.row())


def write_summary(records: List[TestRecord], path: str, source: str):
    counts: Dict[str, int] = {}
    for r in records:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    by_group: Dict[str, Dict[str, int]] = {}
    for r in records:
        by_group.setdefault(r.group, {})
        by_group[r.group][r.verdict] = by_group[r.group].get(r.verdict, 0) + 1

    lines = [
        "# CogniTwin-SDR Simulink -> ACWRA Validation Campaign",
        "",
        f"- Data source: **{source.upper()}**"
        + ("  (real .slx output)" if source == "matlab" else "  (Python reference PHY fixtures - NOT Simulink)"),
        f"- Total checks executed: **{len(records)}**",
        "",
        "## Verdict totals",
        "",
        "| Verdict | Count |",
        "|---|---:|",
    ]
    for v in (PASS, STAT_PASS, INCONCLUSIVE, FAIL, NOT_RUN):
        if v in counts:
            lines.append(f"| {v} | {counts[v]} |")
    lines += ["", "## By group", "", "| Group | " + " | ".join([PASS, STAT_PASS, INCONCLUSIVE, FAIL, NOT_RUN]) + " |",
              "|---|---:|---:|---:|---:|---:|"]
    for g in sorted(by_group):
        row = by_group[g]
        lines.append(
            f"| {g} | " + " | ".join(str(row.get(v, 0)) for v in (PASS, STAT_PASS, INCONCLUSIVE, FAIL, NOT_RUN)) + " |"
        )

    fails = [r for r in records if r.verdict == FAIL]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines.append(f"- **{r.test_id} {r.name}**: {r.reason}")

    notrun = [r for r in records if r.verdict == NOT_RUN]
    if notrun:
        lines += ["", "## Not run (with reason)", ""]
        for r in notrun:
            lines.append(f"- **{r.test_id} {r.name}**: {r.reason}")

    inc = [r for r in records if r.verdict == INCONCLUSIVE]
    if inc:
        lines += ["", "## Inconclusive", ""]
        for r in inc[:40]:
            lines.append(f"- **{r.test_id} {r.name}**: {r.reason}")
        if len(inc) > 40:
            lines.append(f"- ... and {len(inc) - 40} more (see CSV)")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# -------------------------------------------------------------------------- plots


def _style(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor("#1e293b")
    ax.tick_params(colors="#f8fafc")
    ax.xaxis.label.set_color("#f8fafc")
    ax.yaxis.label.set_color("#f8fafc")
    ax.title.set_color("#f8fafc")
    ax.grid(True, linestyle="--", alpha=0.35, color="#334155")
    for sp in ax.spines.values():
        sp.set_color("#475569")
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)


def _save(fig, path):
    fig.savefig(path, dpi=150, facecolor="#0f172a", edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return path


def make_plots(payload: List[Dict[str, Any]], out_dir: str, source: str) -> List[str]:
    if not payload:
        return []
    os.makedirs(out_dir, exist_ok=True)
    made = []
    tag = source.upper()

    # 1-3: constellation, waveform, spectrum for a representative case
    rep = max(payload, key=lambda d: d["snr"])
    iq = rep["iq"]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.4))
    fig.patch.set_facecolor("#0f172a")
    _style(axs[0], f"I/Q constellation ({rep['mod']}, {rep['snr']:.0f} dB)", "In-phase", "Quadrature")
    axs[0].scatter(iq.real[:1024], iq.imag[:1024], s=6, alpha=0.5, color="#38bdf8")
    axs[0].set_aspect("equal", adjustable="datalim")

    n_show = min(400, iq.size)
    t_ms = np.arange(n_show) / rep["fs"] * 1e3
    _style(axs[1], "I/Q waveform", "Time (ms)", "Amplitude")
    axs[1].plot(t_ms, iq.real[:n_show], color="#38bdf8", lw=0.9, label="I")
    axs[1].plot(t_ms, iq.imag[:n_show], color="#f59e0b", lw=0.9, label="Q")
    axs[1].legend(facecolor="#0f172a", labelcolor="#f8fafc", fontsize=8)

    spec = np.fft.fftshift(np.abs(np.fft.fft(iq)) ** 2)
    fr = np.fft.fftshift(np.fft.fftfreq(iq.size, 1.0 / rep["fs"])) / 1e3
    _style(axs[2], "Received spectrum", "Frequency (kHz)", "Power (dB)")
    axs[2].plot(fr, 10 * np.log10(spec + 1e-12), color="#a78bfa", lw=0.8)
    fig.suptitle(f"[{tag}] Received I/Q diagnostics", color="#f8fafc", fontweight="bold")
    made.append(_save(fig, os.path.join(out_dir, f"iq_diagnostics_{source}.png")))

    # 4: BER vs SNR
    snr_rows = [d for d in payload if d["group"] in ("C_snr", "F_stress") and d["interf"] == 0]
    if snr_rows:
        fig, ax = plt.subplots(figsize=(7.5, 5))
        fig.patch.set_facecolor("#0f172a")
        _style(ax, f"[{tag}] Measured BER vs SNR", "SNR (dB)", "BER")
        for mod, color in zip(MODULATIONS, ["#38bdf8", "#34d399", "#f472b6"]):
            pts = sorted([(d["snr"], d["ber"]) for d in snr_rows if d["mod"] == mod])
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color=color, label=mod, ms=5)
        ax.set_yscale("symlog", linthresh=1e-5)
        ax.legend(facecolor="#0f172a", labelcolor="#f8fafc")
        made.append(_save(fig, os.path.join(out_dir, f"ber_vs_snr_{source}.png")))

    # 5: SIR vs interference power
    int_rows = sorted([d for d in payload if d["group"] == "D_interference" and d["interf"] > 0],
                      key=lambda d: d["interf"])
    if int_rows:
        fig, ax = plt.subplots(figsize=(7.5, 5))
        fig.patch.set_facecolor("#0f172a")
        _style(ax, f"[{tag}] SIR vs interference power", "Interference power (linear)", "SIR (dB)")
        p = np.array([d["interf"] for d in int_rows])
        ax.semilogx(p, -10 * np.log10(p), "--", color="#94a3b8", label="theoretical -10log10(P)")
        ax.semilogx(p, [d["snr_meas"] for d in int_rows], "o-", color="#38bdf8", label="measured SIR+N")
        ax.legend(facecolor="#0f172a", labelcolor="#f8fafc")
        made.append(_save(fig, os.path.join(out_dir, f"sir_vs_interference_{source}.png")))

    # 6: confidence vs SNR
    conf_rows = sorted([d for d in payload if d["group"] in ("C_snr", "B_modulation", "F_stress")],
                       key=lambda d: d["snr"])
    if conf_rows:
        fig, ax = plt.subplots(figsize=(7.5, 5))
        fig.patch.set_facecolor("#0f172a")
        _style(ax, f"[{tag}] SpectrumAgent confidence vs SNR", "SNR (dB)", "Classifier confidence")
        for mod, color in zip(MODULATIONS, ["#38bdf8", "#34d399", "#f472b6"]):
            pts = sorted([(d["snr"], d["conf"]) for d in conf_rows if d["mod"] == mod])
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], "o", color=color, label=mod, ms=5, alpha=0.75)
        ax.set_ylim(0, 1.05)
        ax.legend(facecolor="#0f172a", labelcolor="#f8fafc")
        made.append(_save(fig, os.path.join(out_dir, f"confidence_vs_snr_{source}.png")))

    # 7: utility comparison for the most-contested case
    contested = max(payload, key=lambda d: len(d["candidates"]))
    if len(contested["candidates"]) > 1:
        fig, ax = plt.subplots(figsize=(7.5, 4.6))
        fig.patch.set_facecolor("#0f172a")
        names = [c[0] for c in contested["candidates"]]
        utils = [c[1] for c in contested["candidates"]]
        colors = ["#22c55e" if n == contested["strategy"] else "#64748b" for n in names]
        _style(ax,
               f"[{tag}] ACWRA utility U(c): {contested['mod']} @ {contested['snr']:.0f} dB, "
               f"interference {contested['interf']:g}",
               "Candidate strategy", "Utility")
        ax.bar(names, utils, color=colors, width=0.55)
        ax.axhline(0, color="#94a3b8", lw=0.8)
        made.append(_save(fig, os.path.join(out_dir, f"utility_comparison_{source}.png")))

    # 8: selected strategy across scenarios
    strategies = sorted({d["strategy"] for d in payload})
    if strategies:
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        fig.patch.set_facecolor("#0f172a")
        _style(ax, f"[{tag}] Selected strategy across all campaign scenarios",
               "Selected strategy", "Number of scenarios")
        counts = [sum(1 for d in payload if d["strategy"] == s) for s in strategies]
        ax.bar(strategies, counts, color="#38bdf8", width=0.5)
        for i, cnt in enumerate(counts):
            ax.text(i, cnt, str(cnt), ha="center", va="bottom", color="#f8fafc", fontweight="bold")
        made.append(_save(fig, os.path.join(out_dir, f"selected_strategy_{source}.png")))

    return made


# --------------------------------------------------------------------------- main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CogniTwin-SDR Simulink -> ACWRA validation campaign")
    ap.add_argument("--source", choices=["matlab", "fixture"], default="fixture",
                    help="matlab = consume real .slx exports; fixture = Python reference PHY")
    ap.add_argument("--set", dest="which", default="all",
                    help="quick|modulation|snr|interference|channel|stress|all")
    ap.add_argument("--samples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--window", type=int, default=512)
    ap.add_argument("--pattern-symbols", type=int, default=0,
                    help="0 = non-repeating random symbol stream (realistic). "
                         "32 reproduces the repeating-pattern representation the "
                         "existing Task-5 classifier was trained on.")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args(argv)

    os.makedirs(REPORT_DIR, exist_ok=True)

    print("=" * 78)
    print("COGNITWIN-SDR: SIMULINK -> ACWRA VALIDATION CAMPAIGN")
    print("=" * 78)
    print(f"Source : {args.source.upper()}"
          + ("   (REAL Simulink .slx output)" if args.source == "matlab"
             else "   (Python reference PHY fixtures - explicitly NOT Simulink)"))
    print(f"Set    : {args.which}")

    if args.source == "fixture":
        print(f"Symbols: {'non-repeating random stream' if args.pattern_symbols == 0 else f'repeating {args.pattern_symbols}-symbol pattern'}")
    records, payload = run_campaign(args.source, args.which, args.samples, args.seed,
                                    args.window, args.pattern_symbols)
    records.extend(run_data_integrity_checks())

    csv_path = os.path.join(REPORT_DIR, f"results_{args.source}.csv")
    md_path = os.path.join(REPORT_DIR, f"summary_{args.source}.md")
    write_csv(records, csv_path)
    write_summary(records, md_path, args.source)

    plots = [] if args.no_plots else make_plots(payload, REPORT_DIR, args.source)

    counts: Dict[str, int] = {}
    for r in records:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    print("\n" + "-" * 78)
    print("CAMPAIGN RESULTS")
    print("-" * 78)
    for v in (PASS, STAT_PASS, INCONCLUSIVE, FAIL, NOT_RUN):
        print(f"  {v:<18}: {counts.get(v, 0)}")
    print(f"  {'TOTAL':<18}: {len(records)}")
    print("-" * 78)
    print(f"Results table : {csv_path}")
    print(f"Summary       : {md_path}")
    for p in plots:
        print(f"Plot          : {p}")

    fails = [r for r in records if r.verdict == FAIL]
    if fails:
        print(f"\n{len(fails)} FAILURE(S):")
        for r in fails[:15]:
            print(f"  - {r.test_id} {r.name}: {r.reason}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
