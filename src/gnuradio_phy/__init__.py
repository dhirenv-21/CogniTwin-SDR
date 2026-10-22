"""
GNU Radio physical layer for CogniTwin-SDR.

Importing this package does NOT import GNU Radio. Only src.gnuradio_phy.flowgraph
does, and every execution path goes through availability.require_gnuradio(), which
raises GNURadioUnavailable rather than substituting other data.
"""

from .availability import GNURadioUnavailable, gnuradio_available, gnuradio_version, unavailable_reason
from .config import CHANNELS, FADING_MODES, FLOWGRAPH_VERSION, MODULATIONS, GRPhyConfig
from .export import SCHEMA_VERSION, build_export, load_export, write_export
from .validation import (
    PROVENANCE_GNURADIO,
    PROVENANCE_GNURADIO_UNVERIFIED,
    load_and_validate_gnuradio,
    to_measurement,
    validate_gnuradio_dict,
)

__all__ = [
    "GNURadioUnavailable", "gnuradio_available", "gnuradio_version", "unavailable_reason",
    "GRPhyConfig", "MODULATIONS", "CHANNELS", "FADING_MODES", "FLOWGRAPH_VERSION",
    "SCHEMA_VERSION", "build_export", "load_export", "write_export",
    "PROVENANCE_GNURADIO", "PROVENANCE_GNURADIO_UNVERIFIED",
    "validate_gnuradio_dict", "load_and_validate_gnuradio", "to_measurement",
]
