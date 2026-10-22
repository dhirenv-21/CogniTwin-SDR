"""
Simulink Receiver & Loader Module.

Parses MATLAB-exported MAT files or binary measurements into strongly-typed SimulinkMeasurement objects,
and formats complex I/Q vectors for ingestion into SpectrumAgent using a deterministic representation adapter.
"""

import os
from typing import Tuple, Dict, Any, Optional
import numpy as np
import scipy.io as sio

from .protocol import SimulinkMeasurement
from .validation import (
    ValidationReport,
    MeasurementValidationError,
    classify_provenance,
    flatten_matlab_iq,
    validate_mat_dict,
    measure_iq_statistics,
)


class SimulinkReceiver:
    """
    Loader, validator, and adapter reading MATLAB physical-layer MAT-file outputs.
    """

    @staticmethod
    def _unwrap_scalar(val: Any, default: Any) -> Any:
        """Helper to unwrap scalar variables loaded via scipy.io.loadmat."""
        if val is None:
            return default
        if isinstance(val, np.ndarray):
            if val.size == 1:
                return val.item()
            elif val.dtype.kind in ['U', 'S']:
                return str(val.squeeze())
        return val

    @classmethod
    def load_mat_measurement(cls, filepath: str) -> SimulinkMeasurement:
        """
        Loads a MATLAB MAT-file and constructs a SimulinkMeasurement instance.

        Args:
            filepath: Path to exported MAT file.

        Returns:
            SimulinkMeasurement object.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"MATLAB measurement file not found at: '{filepath}'")

        mat_data = sio.loadmat(filepath)

        if "iq_samples" not in mat_data:
            raise KeyError(f"MAT file '{filepath}' missing required 'iq_samples' key.")

        iq_raw = mat_data["iq_samples"]
        snr_raw = mat_data.get("snr_db", 0.0)
        ber_raw = mat_data.get("ber", 0.0)
        mod_raw = mat_data.get("modulation", "UNKNOWN")
        interf_raw = mat_data.get("interference_power", 0.0)
        chan_raw = mat_data.get("channel_type", "AWGN")
        t_raw = mat_data.get("timestamp", 0.0)

        # Process strings and scalars
        mod_str = cls._unwrap_scalar(mod_raw, "UNKNOWN")
        chan_str = cls._unwrap_scalar(chan_raw, "AWGN")

        if isinstance(mod_str, np.ndarray):
            mod_str = "".join(mod_str.tolist())
        if isinstance(chan_str, np.ndarray):
            chan_str = "".join(chan_str.tolist())

        snr_val = float(cls._unwrap_scalar(snr_raw, 0.0))
        ber_val = float(cls._unwrap_scalar(ber_raw, 0.0))
        interf_val = float(cls._unwrap_scalar(interf_raw, 0.0))
        t_val = float(cls._unwrap_scalar(t_raw, 0.0))

        # Shape-safe conversion: handles N x 1, 1 x N, N x 2 [I Q] and MATLAB complex
        # arrays without ever discarding the imaginary component.
        iq_samples = flatten_matlab_iq(iq_raw)

        # --- Task 11 additive metadata (absent in older MAT files -> harmless defaults) ---
        fs_val = float(cls._unwrap_scalar(mat_data.get("sample_rate", 0.0), 0.0) or 0.0)

        time_vector = None
        if "time_vector" in mat_data:
            tv = np.asarray(mat_data["time_vector"], dtype=np.float64).flatten()
            if tv.size:
                time_vector = tv

        tx_iq = None
        if "tx_iq" in mat_data:
            try:
                tx_iq = flatten_matlab_iq(mat_data["tx_iq"])
            except MeasurementValidationError:
                tx_iq = None

        src_str = cls._unwrap_scalar(mat_data.get("source", "unknown"), "unknown")
        if isinstance(src_str, np.ndarray):
            src_str = "".join(src_str.tolist())

        reserved = {
            "iq_samples", "snr_db", "ber", "modulation", "interference_power",
            "channel_type", "timestamp", "sample_rate", "time_vector", "tx_iq", "source",
        }
        extras = {
            k: v for k, v in mat_data.items()
            if not k.startswith("__") and k not in reserved
        }

        provenance, _ = classify_provenance(mat_data)

        return SimulinkMeasurement(
            iq_samples=iq_samples,
            snr_db=snr_val,
            ber=ber_val,
            modulation=str(mod_str),
            interference_power=interf_val,
            channel_type=str(chan_str),
            timestamp=t_val,
            sample_rate=fs_val,
            time_vector=time_vector,
            tx_iq=tx_iq,
            source=str(src_str),
            extras=extras,
            provenance=provenance,
        )

    @classmethod
    def load_and_validate(
        cls,
        filepath: str,
        *,
        expected_samples: Optional[int] = None,
        expected_sample_rate: Optional[float] = None,
        sample_count_tolerance: int = 0,
        strict: bool = True,
        require_real: bool = False,
        require_model_version: Optional[str] = None,
        not_before: Optional[float] = None,
    ) -> Tuple[SimulinkMeasurement, ValidationReport]:
        """
        Load a MAT file AND run the full Task 11 Part 1 validation battery on it.

        This is the entry point used by the real Simulink -> ACWRA pipeline. Unlike
        load_mat_measurement() it never returns a silently-degraded measurement: if
        strict=True and any required check fails, MeasurementValidationError is raised.

        Args:
            filepath: Path to the MATLAB-exported MAT file.
            expected_samples: Optional expected received sample count.
            expected_sample_rate: Optional expected Fs in Hz.
            sample_count_tolerance: Allowed |actual - expected| sample difference.
            strict: Raise on validation failure instead of returning an invalid report.
            require_real: Accept only a MATLAB-written, source='simulink' export.
            require_model_version: e.g. "v4"; reject exports from older models.
            not_before: POSIX time; reject a file last modified before it, so a
                stale export left over from an earlier run is never read as new.

        Returns:
            Tuple of (SimulinkMeasurement, ValidationReport).
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"MATLAB measurement file not found at: '{filepath}'")

        try:
            mat_data = sio.loadmat(filepath)
        except Exception as exc:  # corrupt / non-MAT file
            raise MeasurementValidationError(
                f"'{filepath}' could not be parsed as a MAT file: {exc}"
            ) from exc

        report = validate_mat_dict(
            mat_data,
            expected_samples=expected_samples,
            expected_sample_rate=expected_sample_rate,
            sample_count_tolerance=sample_count_tolerance,
            require_real=require_real,
            require_model_version=require_model_version,
        )
        report.facts["filepath"] = os.path.abspath(filepath)
        mtime = os.path.getmtime(filepath)
        report.facts["file_mtime"] = mtime
        if not_before is not None:
            report.require(
                "file_not_stale",
                mtime >= float(not_before),
                f"file last modified at {mtime:.0f}, before the required {float(not_before):.0f} "
                f"(stale export from an earlier run?)",
            )
        report.facts["mat_header"] = str(mat_data.get("__header__", b""))

        if strict:
            report.raise_if_invalid(context=f"Invalid Simulink measurement '{filepath}'")

        measurement = cls.load_mat_measurement(filepath)
        return measurement, report

    @staticmethod
    def measure(measurement: SimulinkMeasurement) -> Dict[str, float]:
        """
        Compute measured (not assumed) statistics of the received I/Q vector.

        Uses the transmitted reference when MATLAB exported one, which yields a true
        measured SNR and EVM rather than the nominal SNR parameter.
        """
        fs = measurement.sample_rate if measurement.sample_rate > 0 else 100000.0
        return measure_iq_statistics(
            measurement.iq_samples, sample_rate=fs, tx_iq=measurement.tx_iq
        )

    @classmethod
    def adapt_representation_for_classifier(cls, iq_samples: np.ndarray, target_length: int = 512) -> np.ndarray:
        """
        Deterministic Representation Adapter:
        Converts MATLAB complex I/Q array into the exact format expected by SpectrumAgent / analyze_iq().

        Operations:
        1. Ensures 1D complex128 array.
        2. Applies power normalization if power deviates significantly from unit power: x_norm = x / sqrt(P_signal).
        3. Pads or crops to target window size (default 512 samples).

        Args:
            iq_samples: Input 1D complex array.
            target_length: Window size for feature extraction (default 512).

        Returns:
            1D complex128 NumPy array.
        """
        x = np.asarray(iq_samples, dtype=np.complex128).flatten()
        if len(x) == 0:
            return np.zeros(target_length, dtype=np.complex128)

        # 1. Window Size Adjustment (target_length = 512)
        if len(x) < target_length:
            repeats = int(np.ceil(target_length / len(x)))
            x_window = np.tile(x, repeats)[:target_length]
        else:
            x_window = x[:target_length]

        # 2. Power Normalization (exact unit signal power for target window)
        p_signal = float(np.mean(np.abs(x_window) ** 2))
        if p_signal > 1e-12:
            x_adapted = x_window / np.sqrt(p_signal)
        else:
            x_adapted = x_window.copy()

        return x_adapted

    @classmethod
    def convert_for_spectrum_agent(cls, measurement: SimulinkMeasurement) -> Tuple[np.ndarray, float, float]:
        """
        Formats measurement for SpectrumAgent.process() using representation adapter.

        Returns:
            Tuple of (iq_samples_adapted, timestamp_s, interference_power).
        """
        iq_adapted = cls.adapt_representation_for_classifier(measurement.iq_samples, target_length=512)
        return iq_adapted, measurement.timestamp, measurement.interference_power
