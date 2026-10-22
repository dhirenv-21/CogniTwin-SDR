"""
GNU Radio I/Q export: one NPZ per run, using the SAME variable names as the
Simulink MAT schema (docs/DATA_SCHEMA_PROVENANCE.md), so the existing bridge
validation (validate_mat_dict) and pipeline consume it unchanged. GNU Radio-only
metadata is added under extra keys; no competing schema is introduced.

    np.savez(..)  ->  load_export(path)  ->  validate_gnuradio_dict(d)  ->  to_measurement(d)

Every export carries content_sha256, a hash over every other variable, and the
runner appends (experiment_id, content_sha256) to a run ledger. Provenance
(src/gnuradio_phy/validation.py) is decided from that evidence, never from the
source label alone.
"""

import datetime as _dt
import hashlib
import json
import os
import zipfile
from typing import Any, Dict, Optional

import numpy as np

from src.simulink_bridge.validation import MeasurementValidationError

from .config import FLOWGRAPH_VERSION, GRPhyConfig
from .receiver import TIMING_RESOLVABLE_Z

SCHEMA_VERSION = "cognitwin-gr-export-1"
SOURCE_LABEL = "gnuradio"
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_LEDGER = os.path.join(_ROOT, "results", "gnuradio", "run_ledger.jsonl")

# experiment_id -> content_sha256 of exports produced by run_flowgraph IN THIS PROCESS
# (src/gnuradio_phy/runner.py). Lets an in-memory closed loop prove its episodes came
# straight from the flowgraph without writing every episode to disk.
IN_PROCESS_RUNS: Dict[str, str] = {}

# keys every GNU Radio export must have (beyond the bridge's own required keys)
REQUIRED_GR_KEYS = (
    "schema_version", "simulator", "gnuradio_version", "flowgraph_version", "flowgraph_sha256",
    "config_json", "config_hash", "experiment_id", "fading_mode", "channel_gain_iq",
    "reference_bits", "receiver_settings", "timing_ok", "gain_capture_ok", "content_sha256",
    "created_utc", "tx_iq", "noise_iq", "interference_iq", "bit_errors", "bits_compared",
)


def content_sha256(d: Dict[str, Any]) -> str:
    """Hash over every variable except content_sha256, in key order, dtype- and shape-aware."""
    h = hashlib.sha256()
    for key in sorted(k for k in d if k != "content_sha256" and not k.startswith("__")):
        a = np.asarray(d[key])
        if a.dtype.kind == "U":
            payload = "\x1f".join(map(str, a.reshape(-1).tolist())).encode("utf-8")
        else:
            payload = np.ascontiguousarray(a).tobytes()
        h.update(key.encode())
        h.update(str(a.dtype.str if a.dtype.kind != "U" else "U").encode())
        h.update(str(a.shape).encode())
        h.update(payload)
    return h.hexdigest()


def build_export(cfg: GRPhyConfig, capture: Dict[str, np.ndarray], info: Dict[str, Any],
                 rx: Dict[str, Any], timestamp: float = 0.0) -> Dict[str, Any]:
    """Assemble the export dict from a flowgraph capture and the receiver output."""
    ex = rx["export"]
    tx, iq = np.asarray(ex["tx"], np.complex128), np.asarray(ex["rx"], np.complex128)
    n = int(iq.size)
    fs = float(cfg.symbol_rate)
    gain = np.asarray(ex["gain"], np.complex128)
    d: Dict[str, Any] = {
        # ---- bridge schema (same names and units as the Simulink MAT export) ----
        "iq_samples": iq,
        "tx_iq": tx,
        "noise_iq": np.asarray(ex["noise"], np.complex128),
        "interference_iq": np.asarray(ex["jam"], np.complex128),
        "snr_db": float(cfg.snr_db),
        "measured_snr_db": float(rx["measured_snr_db"]),
        "ber": float(rx["ber"]),
        "bit_errors": int(rx["bit_errors"]),
        "bits_compared": int(rx["bits_compared"]),
        "modulation": cfg.modulation,
        "interference_power": float(cfg.interference_power),
        "channel_type": cfg.channel,
        "timestamp": float(timestamp),
        "sample_rate": fs,
        "time_vector": float(timestamp) + np.arange(n) / fs,
        "num_samples": n,
        "source": SOURCE_LABEL,
        "run_id": cfg.experiment_id(),
        "model_version": FLOWGRAPH_VERSION,
        "noise_source": "gnuradio analog.noise_source_c GR_GAUSSIAN",
        "noise_seed": int(cfg.noise_seed),
        # ---- GNU Radio metadata ----
        "schema_version": SCHEMA_VERSION,
        "simulator": "GNU Radio",
        "gnuradio_version": str(info["gnuradio_version"]),
        "flowgraph_version": str(info["flowgraph_version"]),
        "flowgraph_sha256": str(info["flowgraph_sha256"]),
        "flowgraph_blocks": np.array(list(info.get("blocks", [])), dtype=str),
        "config_json": json.dumps(cfg.identity(), sort_keys=True),
        "config_hash": cfg.config_hash(),
        "experiment_id": cfg.experiment_id(),
        "seed": int(cfg.seed),
        "fading_mode": cfg.fading_mode,
        "channel_gain_iq": gain,
        "reference_bits": np.asarray(rx["ref_bits"], np.uint8),
        "measured_interference_power": float(rx["measured_interference_power"]),
        "per": float(rx["per"]),
        "packets": int(rx["packets"]),
        "ber_theory": float(rx["ber_theory"]),
        "waveform_sample_rate": float(cfg.waveform_sample_rate),
        "receiver_settings": json.dumps({
            "timing": "known filter delay, verified by correlation search",
            "equaliser": "genie one-tap (true captured gain)",
            "decisions": "hard, minimum distance",
            "ofdm": "CP removal + 64-pt FFT, genie timing/CSI; not a full OFDM receiver"
                    if cfg.modulation == "OFDM-QPSK" else "n/a",
            "sps": cfg.sps if cfg.modulation != "OFDM-QPSK" else 1,
            "rolloff": cfg.rolloff if cfg.modulation != "OFDM-QPSK" else None,
        }, sort_keys=True),
        "timing_ok": bool(rx["timing_ok"]),
        "timing_peak_z": float(rx["timing_peak_z"]),
        "timing_resolvable": bool(rx["timing_peak_z"] >= TIMING_RESOLVABLE_Z),
        "timing_lag_found": int(rx["timing_lag_found"]),
        "timing_lag_expected": int(rx["timing_lag_expected"]),
        "gain_capture_ok": bool(info["gain_capture_ok"]),
        "gain_capture_error": float(info["gain_capture_error"]),
        "wall_time_s": float(info.get("wall_time_s", float("nan"))),
        "python_version": str(info.get("python_version", "")),
        "platform": str(info.get("platform", "")),
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    # A constant channel also gets the scalar gain, which switches on the bridge's
    # non-skippable rx_power_matches_configuration check.
    if cfg.fading_mode in ("none", "block"):
        h0 = complex(gain[0])
        d["channel_gain_real"], d["channel_gain_imag"] = h0.real, h0.imag
    d["content_sha256"] = content_sha256(d)
    return d


def write_export(d: Dict[str, Any], path: str, ledger_path: Optional[str] = DEFAULT_LEDGER) -> str:
    """Write the NPZ (never overwriting) and append it to the run ledger."""
    if os.path.exists(path):
        raise FileExistsError(f"refusing to overwrite existing export {path}")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    arrays = {k: np.asarray(v) for k, v in d.items()}
    with open(path, "wb") as fh:
        np.savez(fh, **arrays)
    if ledger_path:
        os.makedirs(os.path.dirname(os.path.abspath(ledger_path)) or ".", exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "experiment_id": d["experiment_id"], "content_sha256": d["content_sha256"],
                "path": os.path.relpath(os.path.abspath(path)).replace("\\", "/"),
                "gnuradio_version": d["gnuradio_version"], "created_utc": d["created_utc"],
            }, sort_keys=True) + "\n")
    return path


def _unwrap(a: np.ndarray) -> Any:
    if a.ndim == 0:
        v = a.item()
        return v
    return a


def load_export(path: str) -> Dict[str, Any]:
    """Load an export NPZ. Pickled objects are never allowed. Raises MeasurementValidationError."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"GNU Radio export not found: '{path}'")
    if os.path.getsize(path) == 0:
        raise MeasurementValidationError(f"'{path}' is empty")
    try:
        with np.load(path, allow_pickle=False) as z:
            d = {k: _unwrap(z[k]) for k in z.files}
    except (zipfile.BadZipFile, ValueError, EOFError, OSError, KeyError) as exc:
        raise MeasurementValidationError(f"'{path}' is not a readable NPZ export: {type(exc).__name__}: {exc}") from exc
    if not d:
        raise MeasurementValidationError(f"'{path}' contains no variables")
    return d


def read_ledger(ledger_path: str) -> Dict[str, str]:
    """experiment_id -> content_sha256 for every ledger line (later lines win)."""
    out: Dict[str, str] = {}
    if not ledger_path or not os.path.exists(ledger_path):
        return out
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                out[str(rec["experiment_id"])] = str(rec["content_sha256"])
            except (ValueError, KeyError):
                continue
    return out

