"""
Simulink Measurement Validation Module.

Provides strict, explicit validation of MATLAB/Simulink-exported MAT-file measurements
BEFORE they are allowed to enter the CogniTwin-SDR agent pipeline.

Design rules (Task 11, Part 1):
  * A malformed / incomplete MAT file is REJECTED with a precise reason.
  * The bridge NEVER silently substitutes synthetic data for a missing real measurement.
  * Validation is data-only: it performs no signal processing decisions and does not
    modify any ACWRA / Digital Twin / agent mathematics.

Nothing in this module imports the ACWRA engine, the Digital Twin or any agent, so it is
safe to use for pure data-integrity unit tests without MATLAB installed.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# Modulation labels the MATLAB PHY generator and the existing Python classifier share.
KNOWN_MODULATIONS = (
    "BPSK",
    "QPSK",
    "OFDM-QPSK",
    "ASK",
    "FSK",
    "FM",
    "AM-DSB-SC",
    "AM-DSB-TC",
)

KNOWN_CHANNELS = ("AWGN", "RAYLEIGH", "RICIAN")

# Margin (dB) by which |h_LS|^2 must exceed the pure-noise floor P_rx/N before a
# measurement is accepted as containing the transmitted signal. See the
# wanted_signal_present check in validate_mat_dict() for the derivation.
SIGNAL_PRESENCE_MARGIN_DB = 10.0

# Extra headroom required before the presence test is considered informative. If a
# perfectly healthy link could not clear MARGIN + HEADROOM given N, SNR and the
# interference power, the test is skipped instead of failed.
SIGNAL_PRESENCE_HEADROOM_DB = 6.0

# Required MAT variables for a measurement to be considered a real PHY export.
REQUIRED_MAT_KEYS = ("iq_samples", "snr_db", "modulation")

# Optional-but-expected MAT variables.
OPTIONAL_MAT_KEYS = (
    "ber",
    "interference_power",
    "channel_type",
    "timestamp",
    "sample_rate",
    "time_vector",
    "tx_iq",
    "num_samples",
    "source",
)


class MeasurementValidationError(ValueError):
    """Raised when a MAT-file / measurement fails strict validation."""


# --------------------------------------------------------------------- provenance
# Who WROTE the file is read from the MAT header, which the writer sets itself:
#   MATLAB : "MATLAB 5.0 MAT-file, Platform: PCWIN64, Created on: ..."
#   SciPy  : "MATLAB 5.0 MAT-file Platform: nt, Created on: ..."   (os.name)
# The `source` variable is only a label and can be set by anyone, so a file is a
# real Simulink export (A) only when BOTH say so.
PROVENANCE_SIMULINK = "simulink_export"                    # A: MATLAB-written, source=simulink
PROVENANCE_SIMULINK_UNVERIFIED = "simulink_claim_unverified"  # source=simulink, not MATLAB-written
PROVENANCE_MATLAB_UNLABELLED = "matlab_unlabelled"          # MATLAB-written, no simulink label
PROVENANCE_LEGACY_PYTHON = "legacy_python_mat"              # B: Python-written, no recognised label
PROVENANCE_FIXTURE = "python_fixture"                       # C: reference_phy / test fixtures
PROVENANCE_SYNTHETIC = "synthetic_demo"                     # D: source=synthetic* / demo*
PROVENANCE_UNKNOWN = "unknown"                              # in-memory dict, no header, no label

MATLAB_PLATFORMS = ("PCWIN64", "PCWIN", "GLNXA64", "GLNX86", "MACI64", "MACA64", "MACI")
FIXTURE_SOURCE_TAGS = ("python-fixture",)


def mat_writer(mat: Dict[str, Any]) -> str:
    """'matlab', 'scipy' or 'unknown', from the MAT-file header."""
    header = mat.get("__header__")
    if header is None:
        return "unknown"
    if isinstance(header, bytes):
        header = header.decode("latin-1", "replace")
    m = re.search(r"Platform:\s*([A-Za-z0-9_]+)", str(header))
    if not m:
        return "unknown"
    plat = m.group(1)
    if plat.upper() in MATLAB_PLATFORMS:
        return "matlab"
    if plat.lower() in ("nt", "posix", "java"):
        return "scipy"
    return "unknown"


def classify_provenance(mat: Dict[str, Any]) -> Tuple[str, str]:
    """
    Classify a loaded MAT dict as one of the PROVENANCE_* kinds.

    Returns (kind, explanation). Only PROVENANCE_SIMULINK is a real Simulink export.
    """
    writer = mat_writer(mat)
    source = (_as_text(mat.get("source")) or "").strip().lower()
    version = _as_text(mat.get("model_version")) or "pre-v4"

    if source in FIXTURE_SOURCE_TAGS:
        return PROVENANCE_FIXTURE, f"source='{source}' (Python reference PHY / test fixture), writer={writer}"
    if source.startswith("synthetic") or source.startswith("demo"):
        return PROVENANCE_SYNTHETIC, f"source='{source}' (synthetic demonstration data), writer={writer}"
    if source.startswith("simulink"):
        if writer == "matlab":
            return PROVENANCE_SIMULINK, f"MATLAB-written, source='{source}', model_version={version}"
        return (PROVENANCE_SIMULINK_UNVERIFIED,
                f"source='{source}' but the file was written by {writer}, not MATLAB: "
                f"the label cannot be trusted")
    if writer == "matlab":
        return (PROVENANCE_MATLAB_UNLABELLED,
                f"MATLAB-written with source='{source or '<absent>'}': not tagged as a Simulink run "
                f"(e.g. the pure-MATLAB run_validation.m)")
    if writer == "scipy":
        return (PROVENANCE_LEGACY_PYTHON,
                f"written by SciPy (Python) with source='{source or '<absent>'}'")
    return PROVENANCE_UNKNOWN, f"no MAT header and source='{source or '<absent>'}'"


@dataclass
class ValidationReport:
    """Structured outcome of validating a Simulink measurement."""

    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks: Dict[str, str] = field(default_factory=dict)  # check name -> PASS/FAIL/WARN/SKIP
    facts: Dict[str, Any] = field(default_factory=dict)

    def _record(self, name: str, passed: bool, message: str = "", warn_only: bool = False):
        if passed:
            self.checks[name] = "PASS"
            return
        if warn_only:
            self.checks[name] = "WARN"
            self.warnings.append(f"{name}: {message}")
        else:
            self.checks[name] = "FAIL"
            self.errors.append(f"{name}: {message}")
            self.ok = False

    def skip(self, name: str, message: str = ""):
        self.checks[name] = "SKIP"
        if message:
            self.warnings.append(f"{name}: SKIPPED - {message}")

    def require(self, name: str, passed: bool, message: str = ""):
        self._record(name, passed, message, warn_only=False)

    def prefer(self, name: str, passed: bool, message: str = ""):
        self._record(name, passed, message, warn_only=True)

    def summary(self) -> str:
        n_pass = sum(1 for v in self.checks.values() if v == "PASS")
        n_fail = sum(1 for v in self.checks.values() if v == "FAIL")
        n_warn = sum(1 for v in self.checks.values() if v == "WARN")
        n_skip = sum(1 for v in self.checks.values() if v == "SKIP")
        state = "VALID" if self.ok else "INVALID"
        return (
            f"{state} | checks: {n_pass} pass, {n_fail} fail, {n_warn} warn, {n_skip} skip"
        )

    def raise_if_invalid(self, context: str = ""):
        if not self.ok:
            prefix = f"{context}: " if context else ""
            raise MeasurementValidationError(prefix + "; ".join(self.errors))


def _as_scalar(value: Any) -> Optional[float]:
    """Best-effort conversion of a loadmat scalar/1x1 array to float."""
    if value is None:
        return None
    arr = np.asarray(value)
    if arr.size != 1:
        return None
    try:
        return float(np.real(arr.reshape(-1)[0]))
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> Optional[str]:
    """Best-effort conversion of a loadmat char/str variable to a Python str."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    arr = np.asarray(value)
    if arr.dtype.kind in ("U", "S"):
        flat = arr.reshape(-1)
        if flat.size == 0:
            return ""
        if flat.size == 1:
            item = flat[0]
            return (item.decode() if isinstance(item, bytes) else str(item)).strip()
        return "".join(
            (c.decode() if isinstance(c, bytes) else str(c)) for c in flat.tolist()
        ).strip()
    if arr.dtype == object and arr.size == 1:
        return _as_text(arr.reshape(-1)[0])
    return None


def flatten_matlab_iq(raw: Any) -> np.ndarray:
    """
    Safely convert a MATLAB I/Q variable into a 1-D complex128 vector.

    Accepts N x 1 (column), 1 x N (row), N x 2 real [I Q] pairs, and native
    MATLAB complex arrays. The imaginary component is never discarded.

    Raises:
        MeasurementValidationError: if the array cannot be interpreted as I/Q.
    """
    arr = np.asarray(raw)

    if arr.size == 0:
        raise MeasurementValidationError("iq_samples is empty")

    # Squeeze trivial singleton dimensions only (keeps N x 2 intact).
    if arr.ndim > 2:
        arr = np.squeeze(arr)
    if arr.ndim > 2:
        raise MeasurementValidationError(
            f"iq_samples has unsupported dimensionality {arr.shape}"
        )

    if arr.ndim == 2:
        rows, cols = arr.shape
        if rows == 1 or cols == 1:
            arr = arr.reshape(-1)
        elif cols == 2 and not np.iscomplexobj(arr):
            # Real N x 2 [I, Q] layout.
            arr = arr[:, 0].astype(np.float64) + 1j * arr[:, 1].astype(np.float64)
        elif rows == 2 and not np.iscomplexobj(arr):
            arr = arr[0, :].astype(np.float64) + 1j * arr[1, :].astype(np.float64)
        else:
            raise MeasurementValidationError(
                f"iq_samples shape {arr.shape} is not a vector or an [I Q] pair matrix"
            )

    if arr.dtype.kind not in ("c", "f", "i", "u"):
        raise MeasurementValidationError(
            f"iq_samples dtype '{arr.dtype}' is not numeric"
        )

    return np.asarray(arr, dtype=np.complex128).reshape(-1)


def validate_mat_dict(
    mat: Dict[str, Any],
    *,
    expect_complex: bool = True,
    min_samples: int = 64,
    expected_samples: Optional[int] = None,
    expected_sample_rate: Optional[float] = None,
    sample_count_tolerance: int = 0,
    require_real: bool = False,
    require_model_version: Optional[str] = None,
) -> ValidationReport:
    """
    require_real: only a MATLAB-written file labelled source='simulink' passes
        (PROVENANCE_SIMULINK). Fixtures, legacy Python MAT files, synthetic data and
        files whose label is not backed by a MATLAB header all FAIL.
    require_model_version: e.g. "v4"; files exported by an older model FAIL.

    Validate the raw dictionary returned by scipy.io.loadmat against the
    CogniTwin-SDR MAT-file convention.

    Checks performed (Task 11, Part 1 / Part 9-H):
      variable existence, dimensions, complex dtype, finite values, sample count,
      sample rate, SNR, BER, modulation label, interference power, channel type,
      time-vector consistency.
    """
    rep = ValidationReport()

    # ---- variable existence -------------------------------------------------
    missing = [k for k in REQUIRED_MAT_KEYS if k not in mat]
    rep.require(
        "required_variables_present",
        not missing,
        f"missing required MAT variables {missing}",
    )
    if missing:
        return rep

    for opt in OPTIONAL_MAT_KEYS:
        if opt not in mat:
            rep.warnings.append(f"optional MAT variable '{opt}' not present")

    # ---- I/Q vector ---------------------------------------------------------
    try:
        iq = flatten_matlab_iq(mat["iq_samples"])
        rep.require("iq_dimensions", True)
    except MeasurementValidationError as exc:
        rep.require("iq_dimensions", False, str(exc))
        return rep

    rep.facts["num_samples"] = int(iq.size)
    rep.facts["iq_shape_raw"] = tuple(np.asarray(mat["iq_samples"]).shape)

    raw_is_complex = bool(np.iscomplexobj(np.asarray(mat["iq_samples"])))
    has_imag = bool(np.any(np.abs(iq.imag) > 0))
    rep.facts["raw_complex_dtype"] = raw_is_complex
    rep.facts["nonzero_imaginary"] = has_imag

    if expect_complex:
        # BPSK is legitimately real-valued at baseband, so a purely real vector is a
        # warning rather than a hard failure; a non-complex *container* is the real risk.
        rep.prefer(
            "iq_complex_dtype",
            raw_is_complex or has_imag,
            "iq_samples contains no imaginary component (real-only export?)",
        )
    else:
        rep.skip("iq_complex_dtype", "expect_complex=False")

    rep.require(
        "iq_finite_values",
        bool(np.all(np.isfinite(iq.real)) and np.all(np.isfinite(iq.imag))),
        "iq_samples contains NaN or Inf",
    )
    rep.require(
        "iq_min_sample_count",
        iq.size >= min_samples,
        f"only {iq.size} samples (< min {min_samples})",
    )
    rep.require(
        "iq_nonzero_power",
        float(np.mean(np.abs(iq) ** 2)) > 0.0,
        "iq_samples has zero measured power",
    )
    rep.facts["measured_power"] = float(np.mean(np.abs(iq) ** 2))

    if expected_samples is not None:
        delta = abs(iq.size - int(expected_samples))
        rep.require(
            "iq_expected_sample_count",
            delta <= sample_count_tolerance,
            f"expected {expected_samples} samples (+/-{sample_count_tolerance}), got {iq.size}",
        )
        rep.facts["sample_count_delta"] = int(iq.size - int(expected_samples))
    else:
        rep.skip("iq_expected_sample_count", "no expected_samples supplied")

    # ---- SNR ----------------------------------------------------------------
    snr = _as_scalar(mat.get("snr_db"))
    rep.require("snr_is_scalar", snr is not None, "snr_db is not a real scalar")
    if snr is not None:
        rep.require("snr_finite", np.isfinite(snr), f"snr_db is not finite ({snr})")
        rep.prefer(
            "snr_plausible_range",
            -60.0 <= snr <= 120.0,
            f"snr_db={snr} outside plausible range [-60, 120] dB",
        )
        rep.facts["snr_db"] = snr

    # ---- BER ----------------------------------------------------------------
    if "ber" in mat:
        ber = _as_scalar(mat.get("ber"))
        rep.require("ber_is_scalar", ber is not None, "ber is not a real scalar")
        if ber is not None:
            rep.require(
                "ber_in_range",
                np.isfinite(ber) and 0.0 <= ber <= 1.0,
                f"ber={ber} outside [0, 1]",
            )
            rep.facts["ber"] = ber
    else:
        rep.skip("ber_is_scalar", "no 'ber' variable in MAT file")
        rep.skip("ber_in_range", "no 'ber' variable in MAT file")

    # ---- modulation ---------------------------------------------------------
    mod = _as_text(mat.get("modulation"))
    rep.require("modulation_is_text", bool(mod), "modulation is missing or not a char array")
    if mod:
        rep.prefer(
            "modulation_known",
            mod.upper() in KNOWN_MODULATIONS,
            f"modulation '{mod}' is not one of {KNOWN_MODULATIONS}",
        )
        rep.facts["modulation"] = mod

    # ---- interference power -------------------------------------------------
    if "interference_power" in mat:
        interf = _as_scalar(mat.get("interference_power"))
        rep.require(
            "interference_power_valid",
            interf is not None and np.isfinite(interf) and interf >= 0.0,
            f"interference_power={interf} is not a finite non-negative scalar",
        )
        if interf is not None:
            rep.facts["interference_power"] = interf
    else:
        rep.skip("interference_power_valid", "no 'interference_power' variable")

    # ---- channel type -------------------------------------------------------
    if "channel_type" in mat:
        chan = _as_text(mat.get("channel_type"))
        rep.require("channel_type_is_text", bool(chan), "channel_type is not a char array")
        if chan:
            rep.prefer(
                "channel_type_known",
                chan.upper() in KNOWN_CHANNELS,
                f"channel_type '{chan}' is not one of {KNOWN_CHANNELS}",
            )
            rep.facts["channel_type"] = chan
    else:
        rep.skip("channel_type_is_text", "no 'channel_type' variable")

    # ---- sample rate --------------------------------------------------------
    fs = _as_scalar(mat.get("sample_rate"))
    if fs is None:
        rep.skip("sample_rate_valid", "no 'sample_rate' variable in MAT file")
    else:
        rep.require(
            "sample_rate_valid",
            np.isfinite(fs) and fs > 0.0,
            f"sample_rate={fs} is not a positive finite scalar",
        )
        rep.facts["sample_rate"] = fs
        if expected_sample_rate is not None:
            rep.require(
                "sample_rate_matches_expected",
                np.isclose(fs, expected_sample_rate, rtol=1e-9),
                f"sample_rate={fs} != expected {expected_sample_rate}",
            )

    # ---- time vector --------------------------------------------------------
    if "time_vector" in mat:
        tv = np.asarray(mat["time_vector"]).reshape(-1).astype(np.float64)
        rep.require(
            "time_vector_length",
            tv.size == iq.size,
            f"time_vector length {tv.size} != iq length {iq.size}",
        )
        rep.require(
            "time_vector_monotonic",
            tv.size < 2 or bool(np.all(np.diff(tv) > 0)),
            "time_vector is not strictly increasing",
        )
        if tv.size > 2 and fs is not None:
            dt = float(np.median(np.diff(tv)))
            rep.prefer(
                "time_vector_matches_sample_rate",
                dt > 0 and np.isclose(1.0 / dt, fs, rtol=1e-3),
                f"time step {dt:.3e}s implies Fs={1.0/dt if dt else float('nan'):.1f} != {fs}",
            )
            rep.facts["time_step_s"] = dt
    else:
        rep.skip("time_vector_length", "no 'time_vector' variable")

    # ---- tx reference (optional, enables true measured SNR / EVM) ----------
    if "tx_iq" in mat:
        try:
            tx = flatten_matlab_iq(mat["tx_iq"])
            rep.require(
                "tx_iq_length",
                tx.size == iq.size,
                f"tx_iq length {tx.size} != rx length {iq.size}",
            )
            rep.require(
                "tx_iq_finite",
                bool(np.all(np.isfinite(tx.real)) and np.all(np.isfinite(tx.imag))),
                "tx_iq contains NaN or Inf",
            )

            # ---- wanted-signal presence -------------------------------------
            # A least-squares fit of a transmit reference to a received vector
            # that does NOT contain it produces |h_LS|^2 ~ P_rx/N, purely from
            # the random correlation between the reference and the noise.
            #
            # That is exactly what a broken PHY input path looks like, and it is
            # what the Simulink v2 build produced: |h_LS| ~ 0.0037 with
            # P_rx = 0.1, N = 10000  ->  sqrt(0.1/10000) = 0.0032.
            #
            # When the signal IS present, |h_LS|^2 sits N*SNR above that floor,
            # so a 10 dB margin separates the two cases with enormous slack even
            # at SNR = -20 dB. Requiring it here means a dead-signal measurement
            # can never reach the Spectrum Agent, the Digital Twin or ACWRA.
            if tx.size == iq.size and tx.size > 0:
                denom = complex(np.vdot(tx, tx))
                if abs(denom) > 0:
                    n_s = int(iq.size)
                    h_ls = complex(np.vdot(tx, iq) / denom)
                    p_rx = float(np.mean(np.abs(iq) ** 2))
                    noise_floor = p_rx / n_s
                    margin_db = 10.0 * np.log10(
                        max(abs(h_ls) ** 2, 1e-300) / max(noise_floor, 1e-300)
                    )
                    rep.facts["signal_margin_db"] = float(margin_db)
                    rep.facts["h_ls_mag"] = float(abs(h_ls))

                    # How large would the margin be if the signal WERE present?
                    #   margin_pred = 10 log10( N * P_sig / (P_sig + P_noise + P_jam) )
                    # Below a certain point the estimator simply cannot resolve the
                    # signal from the noise, and a low margin no longer implies a
                    # broken input path. In that regime the test is uninformative
                    # and is skipped rather than failed.
                    h_re = _as_scalar(mat.get("channel_gain_real"))
                    h_im = _as_scalar(mat.get("channel_gain_imag"))
                    p_sig_pred = (
                        (h_re or 0.0) ** 2 + (h_im or 0.0) ** 2
                        if h_re is not None
                        else 1.0
                    )
                    snr_val = _as_scalar(mat.get("snr_db"))
                    p_noise_pred = 10.0 ** (-snr_val / 10.0) if snr_val is not None else 0.0
                    p_jam_pred = max(_as_scalar(mat.get("interference_power")) or 0.0, 0.0)
                    denom_pred = max(p_sig_pred + p_noise_pred + p_jam_pred, 1e-300)
                    margin_pred_db = 10.0 * np.log10(
                        max(n_s * p_sig_pred / denom_pred, 1e-300)
                    )
                    rep.facts["signal_margin_predicted_db"] = float(margin_pred_db)

                    if margin_pred_db < SIGNAL_PRESENCE_MARGIN_DB + SIGNAL_PRESENCE_HEADROOM_DB:
                        rep.skip(
                            "wanted_signal_present",
                            (
                                f"test uninformative: even a perfectly healthy link would only "
                                f"reach {margin_pred_db:.1f} dB with N={n_s} at this SNR/"
                                f"interference (observed {margin_db:.1f} dB)"
                            ),
                        )
                    else:
                        rep.require(
                            "wanted_signal_present",
                            margin_db > SIGNAL_PRESENCE_MARGIN_DB,
                            (
                                f"|h_LS|^2={abs(h_ls)**2:.4g} is only {margin_db:.1f} dB above the "
                                f"pure-noise floor P_rx/N={noise_floor:.4g}, but a healthy link "
                                f"would reach {margin_pred_db:.1f} dB "
                                f"(need >{SIGNAL_PRESENCE_MARGIN_DB:.0f} dB). The received vector "
                                f"does not contain the transmitted signal - the PHY input path is "
                                f"probably dead."
                            ),
                        )

            # ---- modulation actually transmitted ---------------------------
            # A Simulink export is gated on this inside run_simulink_case, so a
            # mismatch there means the file is corrupt or mislabelled: FAIL.
            # Python fixtures only WARN, since they are not physical evidence.
            sig_ok, sig_detail = check_modulation_signature(tx, mod or "")
            if sig_ok is None:
                rep.skip("tx_matches_modulation", sig_detail)
            else:
                src = (_as_text(mat.get("source")) or "").lower()
                if src.startswith("simulink"):
                    rep.require("tx_matches_modulation", sig_ok, sig_detail)
                else:
                    rep.prefer("tx_matches_modulation", sig_ok, sig_detail)
        except MeasurementValidationError as exc:
            rep.require("tx_iq_length", False, str(exc))
    else:
        rep.skip("tx_iq_length", "no 'tx_iq' reference in MAT file")
        rep.skip("wanted_signal_present", "no 'tx_iq' reference to correlate against")
        rep.skip("tx_matches_modulation", "no 'tx_iq' reference in MAT file")

    # ---- MATLAB's own consistency battery -----------------------------------
    # run_simulink_case only writes checks_passed = 0 when called with
    # opts.strict = false. Such a file is diagnostic output, not a measurement.
    if "checks_passed" in mat:
        cp = _as_scalar(mat.get("checks_passed"))
        rep.require(
            "matlab_checks_passed",
            cp is not None and cp == 1.0,
            f"checks_passed={cp}: run_simulink_case recorded a failed PHY consistency "
            f"check for this run (exported with opts.strict = false)",
        )
    else:
        rep.skip("matlab_checks_passed", "no 'checks_passed' variable (pre-v3 export or fixture)")

    _check_metadata_consistency(rep, mat, iq)
    _check_provenance(rep, mat, require_real, require_model_version)
    return rep


def _check_metadata_consistency(rep: ValidationReport, mat: Dict[str, Any], iq: np.ndarray) -> None:
    """Cross-field consistency: declared counts, bit counts, companion arrays, step."""
    n = int(iq.size)

    if "num_samples" in mat:
        ns = _as_scalar(mat.get("num_samples"))
        rep.require(
            "num_samples_consistent",
            ns is not None and np.isfinite(ns) and int(round(ns)) == n,
            f"num_samples={ns} but iq_samples has {n} samples",
        )

    for key in ("noise_iq", "interference_iq"):
        if key not in mat:
            continue
        try:
            arr = flatten_matlab_iq(mat[key])
        except MeasurementValidationError as exc:
            rep.require(f"{key}_valid", False, str(exc))
            continue
        rep.require(
            f"{key}_valid",
            arr.size == n and bool(np.all(np.isfinite(arr.real)) and np.all(np.isfinite(arr.imag))),
            f"{key}: {arr.size} samples (rx has {n}), finite={bool(np.all(np.isfinite(arr)))}",
        )

    if "bit_errors" in mat or "bits_compared" in mat:
        e = _as_scalar(mat.get("bit_errors"))
        nb = _as_scalar(mat.get("bits_compared"))
        ber = _as_scalar(mat.get("ber"))
        ok = (
            e is not None and nb is not None and np.isfinite(e) and np.isfinite(nb)
            and e >= 0 and nb >= 0 and float(e).is_integer() and float(nb).is_integer() and e <= nb
        )
        if ok and ber is not None and nb > 0:
            ok = abs(ber - e / nb) <= 1e-9
        rep.require(
            "ber_consistent_with_bit_counts",
            bool(ok),
            f"ber={ber}, bit_errors={e}, bits_compared={nb}: need integer 0 <= errors <= "
            f"compared and ber == errors/compared",
        )
        if ok:
            rep.facts["bits_compared"] = int(nb)
            rep.facts["bit_errors"] = int(e)

    fs = _as_scalar(mat.get("sample_rate"))
    step = _as_scalar(mat.get("fixed_step"))
    if fs is not None and step is not None:
        rep.require(
            "fixed_step_matches_sample_rate",
            step > 0 and np.isclose(1.0 / step, fs, rtol=1e-9),
            f"fixed_step={step} implies Fs={1.0 / step if step else float('nan')}, sample_rate={fs}",
        )

    # Received power must match what the file's own configuration implies:
    #   P_rx ~ |h|^2 P_tx + 10^(-snr_db/10) + J      (signal, noise, jammer independent)
    # The v2 zero-signal exports declare |h| ~ 0.004 (a least-squares estimate of
    # noise), which made wanted_signal_present SKIP itself as "uninformative"; their
    # P_rx (~1.9) is 13 dB above the ~0.1 the configuration implies. A file must not
    # be able to switch off its own physics check, so this one is not skippable when
    # tx_iq, the channel gain and a finite SNR are present.
    h_re, h_im = _as_scalar(mat.get("channel_gain_real")), _as_scalar(mat.get("channel_gain_imag"))
    snr_cfg = _as_scalar(mat.get("snr_db"))
    if "tx_iq" in mat and h_re is not None and h_im is not None and snr_cfg is not None \
            and np.isfinite(snr_cfg) and n >= 256:
        try:
            tx = flatten_matlab_iq(mat["tx_iq"])
            if tx.size == n:
                jam_cfg = max(_as_scalar(mat.get("interference_power")) or 0.0, 0.0)
                expected = (h_re ** 2 + h_im ** 2) * float(np.mean(np.abs(tx) ** 2)) \
                    + 10.0 ** (-snr_cfg / 10.0) + jam_cfg
                p_rx = float(np.mean(np.abs(iq) ** 2))
                err_db = abs(10.0 * np.log10(max(p_rx, 1e-300) / max(expected, 1e-300)))
                rep.facts["rx_power_error_db"] = err_db
                rep.require(
                    "rx_power_matches_configuration",
                    err_db < 1.0,
                    f"P_rx = {p_rx:.4g} but |h|^2 P_tx + 10^(-snr/10) + J = {expected:.4g} "
                    f"({err_db:.1f} dB apart): the received signal is not what the export "
                    f"says was simulated",
                )
        except MeasurementValidationError:
            pass

    for key in ("channel_gain_real", "channel_gain_imag", "measured_snr_db"):
        if key in mat:
            v = _as_scalar(mat.get(key))
            # measured_snr_db may legitimately be +Inf only if noise were zero; never NaN
            rep.require(f"{key}_valid", v is not None and not np.isnan(v), f"{key}={v}")

    for key in ("run_id", "model_version", "noise_source"):
        txt = _as_text(mat.get(key)) if key in mat else None
        if txt:
            rep.facts[key] = txt
    seed = _as_scalar(mat.get("noise_seed"))
    if seed is not None:
        rep.facts["noise_seed"] = seed


def _check_provenance(
    rep: ValidationReport,
    mat: Dict[str, Any],
    require_real: bool,
    require_model_version: Optional[str],
) -> None:
    kind, why = classify_provenance(mat)
    rep.facts["provenance"] = kind
    rep.facts["provenance_detail"] = why
    rep.facts["mat_writer"] = mat_writer(mat)
    version = _as_text(mat.get("model_version")) or "pre-v4"
    rep.facts["model_version"] = version

    # A file that CLAIMS to be Simulink output but was not written by MATLAB is
    # suspicious in any mode; without require_real it is a warning, not a failure,
    # so in-memory and fixture paths keep working.
    if require_real:
        rep.require("provenance_real_simulink", kind == PROVENANCE_SIMULINK,
                    f"not a real Simulink export: {why}")
    else:
        rep.prefer("provenance_consistent", kind != PROVENANCE_SIMULINK_UNVERIFIED, why)

    if require_model_version is not None:
        rep.require(
            "model_version_matches",
            version == require_model_version,
            f"exported by model_version={version}, required {require_model_version}",
        )


# OFDM-QPSK framing used by simulink/matlab/cognitwin_waveform.m and
# src/multicarrier/ofdm.py.
OFDM_N_FFT = 64
OFDM_CP_LEN = 16


def check_modulation_signature(
    tx: np.ndarray,
    modulation: str,
    n_fft: int = OFDM_N_FFT,
    cp_len: int = OFDM_CP_LEN,
) -> Tuple[Optional[bool], str]:
    """
    Decide from the samples alone whether `tx` is the labelled modulation.

    Python mirror of simulink/matlab/cognitwin_check_modulation.m. Structural, so
    exact for the CogniTwin constellations:
        BPSK       |tx| = 1 and imag(tx) = 0
        QPSK       |tx| = 1 and angle(tx) in pi/4 + k*pi/2
        OFDM-QPSK  each full symbol's cyclic prefix equals its last cp_len samples,
                   and the envelope is not constant (PAPR > 3 dB)

    Returns (None, reason) when no signature is defined for the label.
    """
    x = np.asarray(tx, dtype=np.complex128).reshape(-1)
    mod = str(modulation).strip().upper()
    if x.size == 0:
        return False, "tx is empty"

    if mod == "BPSK":
        mag_err = float(np.max(np.abs(np.abs(x) - 1.0)))
        im_err = float(np.max(np.abs(x.imag)))
        return (
            mag_err < 1e-9 and im_err < 1e-9,
            f"BPSK: max||tx|-1| = {mag_err:.1e}, max|imag(tx)| = {im_err:.1e} (both must be ~0)",
        )

    if mod == "QPSK":
        mag_err = float(np.max(np.abs(np.abs(x) - 1.0)))
        ph = np.angle(x) - np.pi / 4
        ph_err = float(np.max(np.abs(ph - (np.pi / 2) * np.round(ph / (np.pi / 2)))))
        return (
            mag_err < 1e-9 and ph_err < 1e-9,
            f"QPSK: max||tx|-1| = {mag_err:.1e}, max phase error vs pi/4 + k*pi/2 = {ph_err:.1e}",
        )

    if mod in ("OFDM-QPSK", "OFDM_QPSK", "OFDM"):
        sym_len = n_fft + cp_len
        n_full = x.size // sym_len
        if n_full < 1:
            return False, f"OFDM: fewer than one full {sym_len}-sample symbol"
        blocks = x[: n_full * sym_len].reshape(n_full, sym_len)
        cp_err = float(np.max(np.abs(blocks[:, :cp_len] - blocks[:, -cp_len:])))
        p = np.abs(x) ** 2
        papr_db = float(10.0 * np.log10(np.max(p) / np.mean(p)))
        return (
            cp_err < 1e-12 and papr_db > 3.0,
            f"OFDM: {n_full} full symbols, max|CP - tail| = {cp_err:.1e}, PAPR {papr_db:.1f} dB "
            f"(single-carrier PSK would be 0 dB)",
        )

    return None, f"no modulation signature defined for '{modulation}'"


def find_shared_noise_realisations(
    records: List[Tuple[str, Optional[float], np.ndarray]],
    sigma: float = 5.0,
) -> List[Tuple[str, str, float]]:
    """
    Find pairs of runs with DIFFERENT seeds whose noise arrays are correlated.

    records: (label, seed, noise_iq) per run. Pairs with the same seed are not
    compared, because they legitimately share a realisation (e.g. an SNR ladder
    rescales one draw). Correlation is normalised, so a rescaled copy of the
    same draw is detected as readily as an identical one.

    Independent complex Gaussian vectors give |corr| ~ 1/sqrt(N); anything
    above sigma/sqrt(N) is flagged. This is what exposed the v3 Simulink build,
    where randn inside PHY_Channel ignored every seed.

    Returns [(label_a, label_b, |corr|), ...].
    """
    flagged: List[Tuple[str, str, float]] = []
    prepared = []
    for label, seed, noise in records:
        v = np.asarray(noise, dtype=np.complex128).reshape(-1)
        e = float(np.vdot(v, v).real)
        if v.size and e > 0:
            prepared.append((label, seed, v, e))

    for i in range(len(prepared)):
        la, sa, va, ea = prepared[i]
        for j in range(i + 1, len(prepared)):
            lb, sb, vb, eb = prepared[j]
            if sa is not None and sb is not None and sa == sb:
                continue
            m = min(va.size, vb.size)
            ea_m = float(np.vdot(va[:m], va[:m]).real)
            eb_m = float(np.vdot(vb[:m], vb[:m]).real)
            if ea_m <= 0 or eb_m <= 0:
                continue
            c = abs(complex(np.vdot(va[:m], vb[:m]))) / np.sqrt(ea_m * eb_m)
            if c > sigma / np.sqrt(m):
                flagged.append((la, lb, float(c)))
    return flagged



def validate_measurement(measurement: Any, **kwargs) -> ValidationReport:
    """
    Validate an already-constructed SimulinkMeasurement object.

    Rebuilds an equivalent MAT-style dict so the exact same checks run on both the
    file-level and the object-level path.
    """
    mat: Dict[str, Any] = {
        "iq_samples": measurement.iq_samples,
        "snr_db": measurement.snr_db,
        "ber": measurement.ber,
        "modulation": measurement.modulation,
        "interference_power": measurement.interference_power,
        "channel_type": measurement.channel_type,
        "timestamp": measurement.timestamp,
    }
    fs = getattr(measurement, "sample_rate", None)
    if fs:
        mat["sample_rate"] = fs
    tv = getattr(measurement, "time_vector", None)
    if tv is not None and np.asarray(tv).size:
        mat["time_vector"] = tv
    tx = getattr(measurement, "tx_iq", None)
    if tx is not None and np.asarray(tx).size:
        mat["tx_iq"] = tx
    return validate_mat_dict(mat, **kwargs)


def measure_iq_statistics(
    iq: np.ndarray,
    sample_rate: float = 100000.0,
    tx_iq: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """
    Pure measurement helper (no decisions, no thresholds).

    Returns measured power, peak/RMS magnitude, mean phase, dominant FFT bin frequency
    and - when a transmit reference is available - measured SNR and EVM.
    """
    x = np.asarray(iq, dtype=np.complex128).reshape(-1)
    n = x.size
    power = float(np.mean(np.abs(x) ** 2))
    mag = np.abs(x)

    spec = np.fft.fftshift(np.abs(np.fft.fft(x)))
    freqs = np.fft.fftshift(np.fft.fftfreq(n, d=1.0 / sample_rate))
    dom_freq = float(freqs[int(np.argmax(spec))])

    stats: Dict[str, float] = {
        "num_samples": float(n),
        "measured_power": power,
        "rms_magnitude": float(np.sqrt(power)),
        "peak_magnitude": float(np.max(mag)) if n else 0.0,
        "papr_db": float(10.0 * np.log10((np.max(mag) ** 2) / power)) if power > 0 else 0.0,
        "mean_phase_rad": float(np.mean(np.angle(x))),
        "phase_std_rad": float(np.std(np.angle(x))),
        "dominant_frequency_hz": dom_freq,
        "var_i": float(np.var(x.real)),
        "var_q": float(np.var(x.imag)),
    }

    if tx_iq is not None:
        tx = np.asarray(tx_iq, dtype=np.complex128).reshape(-1)
        m = min(tx.size, x.size)
        if m > 0:
            tx_m, rx_m = tx[:m], x[:m]
            p_tx = float(np.mean(np.abs(tx_m) ** 2))

            # Least-squares single-tap channel estimate. This is an ordinary receiver
            # measurement, not a channel model: it separates the deterministic channel
            # gain (fading / scaling) from the additive impairment power, so the
            # reported SINR is the post-equalisation link quality rather than a number
            # inflated by the fading gain.
            denom = float(np.sum(np.abs(tx_m) ** 2))
            h_hat = complex(np.sum(rx_m * np.conj(tx_m)) / denom) if denom > 0 else 1.0 + 0j

            err = rx_m - h_hat * tx_m
            p_err = float(np.mean(np.abs(err) ** 2))
            p_sig = float(abs(h_hat) ** 2 * p_tx)

            stats["tx_power"] = p_tx
            stats["error_power"] = p_err
            stats["channel_gain_mag"] = float(abs(h_hat))
            stats["channel_gain_phase_rad"] = float(np.angle(h_hat))
            if p_err > 0 and p_sig > 0:
                stats["measured_snr_db"] = float(10.0 * np.log10(p_sig / p_err))
                stats["evm_percent"] = float(100.0 * np.sqrt(p_err / p_sig))
            # Uncompensated error (includes the channel gain) kept for reference.
            p_raw = float(np.mean(np.abs(rx_m - tx_m) ** 2))
            if p_raw > 0 and p_tx > 0:
                stats["raw_evm_percent"] = float(100.0 * np.sqrt(p_raw / p_tx))
    return stats
