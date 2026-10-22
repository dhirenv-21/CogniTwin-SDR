"""
Analog Modulation and Demodulation Package.

Provides classes and functional wrappers for AM (DSB-SC, DSB-TC), SSB (USB, LSB), FM (NBFM, WBFM), and PM.
"""

from .common import AnalogModulator
from .am import AMDSBSCModulator, AMDSTCModulator
from .ssb import SSBModulator
from .fm import FMModulator
from .pm import PMModulator

__all__ = [
    "AnalogModulator",
    "AMDSBSCModulator",
    "AMDSTCModulator",
    "SSBModulator",
    "FMModulator",
    "PMModulator",
]
