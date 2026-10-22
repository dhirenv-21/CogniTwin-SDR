"""
MATLAB/Simulink Physical-Layer Ingest Bridge Package for CogniTwin-SDR.
"""

from .protocol import SimulinkMeasurement
from .receiver import SimulinkReceiver
from .validation import (
    KNOWN_CHANNELS,
    KNOWN_MODULATIONS,
    MeasurementValidationError,
    ValidationReport,
    check_modulation_signature,
    find_shared_noise_realisations,
    flatten_matlab_iq,
    measure_iq_statistics,
    validate_mat_dict,
    validate_measurement,
)
from .pipeline import (
    PipelineResult,
    SimulinkACWRAPipeline,
    WindowObservation,
    matlab_channel_to_internal,
)

__all__ = [
    "SimulinkMeasurement",
    "SimulinkReceiver",
    # validation
    "ValidationReport",
    "MeasurementValidationError",
    "validate_mat_dict",
    "validate_measurement",
    "flatten_matlab_iq",
    "measure_iq_statistics",
    "check_modulation_signature",
    "find_shared_noise_realisations",
    "KNOWN_MODULATIONS",
    "KNOWN_CHANNELS",
    # pipeline
    "SimulinkACWRAPipeline",
    "PipelineResult",
    "WindowObservation",
    "matlab_channel_to_internal",
]
