"""
Validation and provenance for GNU Radio exports.

validate_gnuradio_dict() runs the EXISTING bridge battery (validate_mat_dict: schema,
finiteness, BER bookkeeping, noise/interference arrays, received power versus the
configuration) and then the GNU Radio checks below on the same ValidationReport.

Provenance is decided from evidence, not from the 'source' label:

    gnuradio_export            source='gnuradio' AND content hash intact AND a
                               well-formed GNU Radio version AND flowgraph_sha256
                               equal to this repository's flowgraph.py AND the
                               config hash reproduces AND the decisions recomputed
                               from the exported samples reproduce bit_errors AND
                               timing / gain-capture self-checks passed AND the
                               (experiment_id, content hash) pair is in the run ledger
    gnuradio_claim_unverified  labelled 'gnuradio' but at least one item above is
                               missing or wrong
    (anything else)            the bridge's own classes (python_fixture, ...)

This is consistency evidence, not cryptographic proof: someone who reproduces the
whole export, its hashes and a ledger line could forge it. What it does rule out is
a file being accepted as GNU Radio data because it says so, a stale export from
another flowgraph version, and a file edited after it was written.
"""

import json
import math
import os
import re
from typing import Any, Dict, Optional

import numpy as np

from src.simulink_bridge.protocol import SimulinkMeasurement
from src.simulink_bridge.validation import (
    PROVENANCE_FIXTURE,
    MeasurementValidationError,
    ValidationReport,
    classify_provenance,
    flatten_matlab_iq,
    validate_mat_dict,
)

from .config import FLOWGRAPH_VERSION, OFDM_CP_LEN, OFDM_N_FFT, GRPhyConfig, source_sha256
from .export import (
    DEFAULT_LEDGER, IN_PROCESS_RUNS, REQUIRED_GR_KEYS, SCHEMA_VERSION, SOURCE_LABEL, content_sha256, load_export, read_ledger,
)
from .receiver import hard_decide_bits

PROVENANCE_GNURADIO = "gnuradio_export"
PROVENANCE_GNURADIO_UNVERIFIED = "gnuradio_claim_unverified"

FLOWGRAPH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flowgraph.py")
_VERSION_RE = re.compile(r"^v?3\.\d+\.\d+(\.\d+)?")


def repo_flowgraph_sha256() -> str:
    return source_sha256(FLOWGRAPH_PATH)


def _text(v: Any) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, np.ndarray) and v.dtype.kind in "US" and v.size == 1:
        return str(v.reshape(-1)[0])
    return str(v) if isinstance(v, str) else ""


def _recompute_bits(d: Dict[str, Any]) -> np.ndarray:
    """Hard decisions recomputed from the EXPORTED samples and gains alone."""
    mod = _text(d.get("modulation")).upper()
    iq = flatten_matlab_iq(d["iq_samples"])
    h = np.asarray(d["channel_gain_iq"], dtype=np.complex128).reshape(-1)
    if h.size != iq.size:
        raise MeasurementValidationError(f"channel_gain_iq has {h.size} samples, iq has {iq.size}")
    if mod == "OFDM-QPSK":
        sym_len = OFDM_N_FFT + OFDM_CP_LEN
        n = iq.size // sym_len
        y = np.fft.fft(iq[: n * sym_len].reshape(n, sym_len)[:, OFDM_CP_LEN:], axis=1) / math.sqrt(OFDM_N_FFT)
        hs = h[: n * sym_len].reshape(n, sym_len)[:, OFDM_CP_LEN:].mean(axis=1)
        z = (y / np.where(np.abs(hs) > 0, hs, 1.0)[:, None]).reshape(-1)
    else:
        with np.errstate(invalid="ignore", divide="ignore"):   # non-finite input is rejected elsewhere
            z = iq / np.where(np.abs(h) > 0, h, 1.0)
    return hard_decide_bits(z, mod)


def validate_gnuradio_dict(
    d: Dict[str, Any],
    *,
    require_gnuradio: bool = False,
    ledger_path: Optional[str] = DEFAULT_LEDGER,
) -> ValidationReport:
    """Full validation of a loaded export. require_gnuradio: FAIL unless gnuradio_export."""
    rep = validate_mat_dict(d)
    source = _text(d.get("source")).strip().lower()
    evidence: Dict[str, bool] = {}

    missing = [k for k in REQUIRED_GR_KEYS if k not in d]
    is_gr_file = source == SOURCE_LABEL or "schema_version" in d
    if is_gr_file:
        rep.require("gr_required_keys", not missing, f"missing GNU Radio export keys: {missing}")
    evidence["keys"] = not missing
    if missing:
        return _finish(rep, d, source, evidence, require_gnuradio)

    rep.require("gr_schema_version", _text(d["schema_version"]) == SCHEMA_VERSION,
                f"schema_version={_text(d['schema_version'])!r}, this reader supports {SCHEMA_VERSION!r}")

    stored = _text(d["content_sha256"])
    evidence["integrity"] = stored == content_sha256(d)
    rep.require("gr_content_hash", evidence["integrity"],
                "content_sha256 does not match the file contents (edited or corrupted after export)")

    ver = _text(d["gnuradio_version"])
    evidence["version"] = bool(_VERSION_RE.match(ver))
    fg_ok = _text(d["flowgraph_sha256"]) == repo_flowgraph_sha256() \
        and _text(d["flowgraph_version"]) == FLOWGRAPH_VERSION
    evidence["flowgraph"] = fg_ok
    if source == SOURCE_LABEL:
        rep.require("gr_version_wellformed", evidence["version"], f"gnuradio_version={ver!r} is not a 3.x.y version")
        (rep.require if require_gnuradio else rep.prefer)(
            "gr_flowgraph_matches_repository", fg_ok,
            f"exported by flowgraph {_text(d['flowgraph_version'])} sha {_text(d['flowgraph_sha256'])[:12]}, "
            f"repository has {FLOWGRAPH_VERSION} sha {repo_flowgraph_sha256()[:12]}")
    else:
        rep.skip("gr_version_wellformed", f"source={source!r}: not a GNU Radio claim")
        rep.skip("gr_flowgraph_matches_repository", f"source={source!r}: not a GNU Radio claim")

    # configuration: hash reproduces, and the top-level fields agree with it
    try:
        ident = json.loads(_text(d["config_json"]))
        ident.pop("flowgraph_version", None)
        cfg = GRPhyConfig(**ident)
        cfg_ok = cfg.config_hash() == _text(d["config_hash"]) \
            and cfg.modulation == _text(d["modulation"]).upper() \
            and cfg.channel == _text(d["channel_type"]).upper() \
            and math.isclose(cfg.snr_db, float(d["snr_db"]), abs_tol=1e-12) \
            and math.isclose(cfg.interference_power, float(d["interference_power"]), abs_tol=1e-12) \
            and cfg.fading_mode == _text(d["fading_mode"]) \
            and cfg.experiment_id() == _text(d["experiment_id"])
        detail = "config_json, config_hash and the top-level fields disagree"
    except (TypeError, ValueError) as exc:
        cfg, cfg_ok, detail = None, False, f"config_json does not parse into a GRPhyConfig: {exc}"
    evidence["config"] = cfg_ok
    rep.require("gr_config_consistent", cfg_ok, detail)

    # decisions recomputed from the exported samples must give the stored BER
    try:
        ref = np.asarray(d["reference_bits"], dtype=np.uint8).reshape(-1)
        bits = _recompute_bits(d)
        n = min(ref.size, bits.size)
        recomputed = int(np.sum(ref[:n] != bits[:n]))
        dec_ok = ref.size == bits.size == int(d["bits_compared"]) and recomputed == int(d["bit_errors"])
        dec_detail = f"recomputed {recomputed} errors in {bits.size} bits; export says " \
                     f"{int(d['bit_errors'])} in {int(d['bits_compared'])} (reference has {ref.size})"
    except (MeasurementValidationError, ValueError, TypeError) as exc:
        dec_ok, dec_detail = False, f"decisions could not be recomputed: {exc}"
    evidence["decisions"] = dec_ok
    rep.require("gr_decisions_reproduce_ber", dec_ok, dec_detail)

    # An export without timing_resolvable (older writer) is treated as resolvable: strict.
    resolvable = bool(d.get("timing_resolvable", True))
    evidence["selfchecks"] = (bool(d["timing_ok"]) or not resolvable) and bool(d["gain_capture_ok"])
    if resolvable:
        rep.require("gr_timing_ok", bool(d["timing_ok"]),
                    f"symbol timing lag {d.get('timing_lag_found')} != expected {d.get('timing_lag_expected')}")
    else:
        rep.skip("gr_timing_ok", f"uninformative: timing peak only {float(d.get('timing_peak_z', 0.0)):.1f} sigma "
                                 f"above noise (deep fade / very low SINR); found lag {d.get('timing_lag_found')}")
    rep.require("gr_gain_capture_ok", bool(d["gain_capture_ok"]),
                f"captured channel gain does not reproduce the channel output (error {d.get('gain_capture_error')})")

    # received power vs configuration for a time-varying channel (the bridge's
    # check needs a scalar gain, which a time-varying channel does not have)
    try:
        iq = flatten_matlab_iq(d["iq_samples"])
        tx = flatten_matlab_iq(d["tx_iq"])
        g2 = np.abs(np.asarray(d["channel_gain_iq"], np.complex128).reshape(-1)) ** 2
        if iq.size == tx.size == g2.size and iq.size >= 256:
            exp_p = float(np.mean(g2 * np.abs(tx) ** 2)) + 10 ** (-float(d["snr_db"]) / 10) \
                + max(float(d["interference_power"]), 0.0)
            err_db = abs(10 * math.log10(max(float(np.mean(np.abs(iq) ** 2)), 1e-300) / max(exp_p, 1e-300)))
            rep.facts["gr_rx_power_error_db"] = err_db
            rep.require("gr_rx_power_matches_gain", err_db < 1.0,
                        f"P_rx is {err_db:.2f} dB from mean|h|^2 P_tx + N0 + J")
        # measured noise power vs configured SNR: 5-sigma bound for N samples
        noise = flatten_matlab_iq(d["noise_iq"])
        p_tx = float(np.mean(np.abs(tx) ** 2))
        p_n = float(np.mean(np.abs(noise) ** 2))
        if p_n > 0 and noise.size >= 256:
            meas = 10 * math.log10(p_tx / p_n)
            tol = 5 * 10 / math.log(10) / math.sqrt(noise.size)
            rep.facts["gr_measured_snr_db"] = meas
            rep.require("gr_measured_snr_matches_config", abs(meas - float(d["snr_db"])) < tol + 0.05,
                        f"measured Es/N0 {meas:.2f} dB vs configured {float(d['snr_db']):.2f} dB (tol {tol:.2f})")
    except MeasurementValidationError as exc:
        rep.require("gr_rx_power_matches_gain", False, str(exc))

    if source != SOURCE_LABEL:
        evidence["ledger"] = False
        rep.skip("gr_in_run_ledger", f"source={source!r}: not a GNU Radio claim")
    elif IN_PROCESS_RUNS.get(_text(d["experiment_id"])) == stored:
        evidence["ledger"] = True
        rep.require("gr_in_run_ledger", True)
        rep.facts["ledger"] = "in-process (produced by run_flowgraph in this Python process)"
    elif ledger_path:
        evidence["ledger"] = read_ledger(ledger_path).get(_text(d["experiment_id"])) == stored
        (rep.require if require_gnuradio else rep.prefer)(
            "gr_in_run_ledger", evidence["ledger"],
            f"(experiment_id, content_sha256) not found in {ledger_path} or in this process's runs")
        rep.facts["ledger"] = ledger_path
    else:
        evidence["ledger"] = False
        why = "no ledger supplied and not produced in this process"
        if require_gnuradio:
            rep.require("gr_in_run_ledger", False, why)
        else:
            rep.skip("gr_in_run_ledger", why)

    return _finish(rep, d, source, evidence, require_gnuradio)


def _finish(rep, d, source, evidence, require_gnuradio):
    if source == SOURCE_LABEL:
        failed = [k for k in ("keys", "integrity", "version", "flowgraph", "config", "decisions",
                              "selfchecks", "ledger") if not evidence.get(k, False)]
        kind = PROVENANCE_GNURADIO if not failed and rep.ok else PROVENANCE_GNURADIO_UNVERIFIED
        why = "all GNU Radio evidence present" if kind == PROVENANCE_GNURADIO else \
            f"labelled 'gnuradio' but evidence missing/failed: {failed or ['validation errors']}"
    else:
        kind, why = classify_provenance(d)
    rep.facts["provenance"] = kind
    rep.facts["provenance_detail"] = why
    rep.facts["provenance_evidence"] = evidence
    if require_gnuradio:
        rep.require("provenance_real_gnuradio", kind == PROVENANCE_GNURADIO, f"not a GNU Radio export: {why}")
    for key in ("experiment_id", "gnuradio_version", "flowgraph_version", "config_hash"):
        if key in d:
            rep.facts[key] = _text(d[key])
    rep.facts["model_version"] = _text(d.get("model_version")) or rep.facts.get("model_version", "")
    rep.facts["run_id"] = _text(d.get("run_id")) or rep.facts.get("run_id", "")
    return rep


def load_and_validate_gnuradio(path: str, *, strict: bool = True, require_gnuradio: bool = False,
                               ledger_path: Optional[str] = DEFAULT_LEDGER):
    """Load + validate an NPZ export -> (SimulinkMeasurement, ValidationReport)."""
    d = load_export(path)
    rep = validate_gnuradio_dict(d, require_gnuradio=require_gnuradio, ledger_path=ledger_path)
    rep.facts["filepath"] = os.path.abspath(path)
    if strict:
        rep.raise_if_invalid(context=f"Invalid GNU Radio export '{path}'")
    return to_measurement(d, rep.facts.get("provenance", "unknown")), rep


def to_measurement(d: Dict[str, Any], provenance: str) -> SimulinkMeasurement:
    """The bridge's measurement container (named for Simulink; the schema is shared)."""
    reserved = {"iq_samples", "snr_db", "ber", "modulation", "interference_power", "channel_type",
                "timestamp", "sample_rate", "time_vector", "tx_iq", "source"}
    return SimulinkMeasurement(
        iq_samples=flatten_matlab_iq(d["iq_samples"]),
        snr_db=float(d["snr_db"]),
        ber=float(d.get("ber", 0.0)),
        modulation=_text(d["modulation"]),
        interference_power=float(d.get("interference_power", 0.0)),
        channel_type=_text(d.get("channel_type")) or "AWGN",
        timestamp=float(d.get("timestamp", 0.0)),
        sample_rate=float(d.get("sample_rate", 0.0)),
        time_vector=np.asarray(d["time_vector"]) if "time_vector" in d else None,
        tx_iq=flatten_matlab_iq(d["tx_iq"]) if "tx_iq" in d else None,
        source=_text(d.get("source")) or "unknown",
        extras={k: v for k, v in d.items() if k not in reserved},
        provenance=provenance,
    )


__all__ = [
    "PROVENANCE_GNURADIO", "PROVENANCE_GNURADIO_UNVERIFIED", "PROVENANCE_FIXTURE",
    "validate_gnuradio_dict", "load_and_validate_gnuradio", "to_measurement", "repo_flowgraph_sha256",
]
