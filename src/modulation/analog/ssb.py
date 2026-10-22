"""
Single Sideband (SSB) Modulation Module.

Implements Upper Sideband (USB) and Lower Sideband (LSB) modulation using
the Hilbert-transform based analytic signal method, and coherent demodulation.
"""

from typing import Any, Optional
import numpy as np

from src.signal.generator import to_iq
from src.signal.filters import design_fir_lowpass, apply_filter
from .common import AnalogModulator


class SSBModulator(AnalogModulator):
    """
    Single Sideband (SSB) Modulator & Demodulator (supports USB and LSB).
    """

    def modulate(
        self,
        message: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        sideband: str = "usb",
        amplitude: float = 1.0,
        initial_phase: float = 0.0,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Modulates message using Hilbert-transform based SSB modulation.

        USB: s(t) = m(t)*cos(2*pi*f_c*t) - H{m(t)}*sin(2*pi*f_c*t)
        LSB: s(t) = m(t)*cos(2*pi*f_c*t) + H{m(t)}*sin(2*pi*f_c*t)

        Args:
            message: Baseband message 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            sideband: Sideband selection ('usb' or 'lsb').
            amplitude: Carrier peak amplitude A_c.
            initial_phase: Initial carrier phase in radians.

        Returns:
            Modulated SSB passband signal array.
        """
        m = np.asarray(message, dtype=np.float64)
        sideband_lower = sideband.lower()
        if sideband_lower not in ("usb", "lsb"):
            raise ValueError(f"Invalid sideband '{sideband}'. Must be 'usb' or 'lsb'.")

        # Compute Hilbert transform H{m(t)}
        m_analytic = to_iq(m, method="hilbert")
        m_hat = m_analytic.imag  # Quadrature component is Hilbert transform of m(t)

        t = np.arange(len(m)) / sample_rate
        cos_carrier = amplitude * np.cos(2.0 * np.pi * carrier_freq * t + initial_phase)
        sin_carrier = amplitude * np.sin(2.0 * np.pi * carrier_freq * t + initial_phase)

        if sideband_lower == "usb":
            return m * cos_carrier - m_hat * sin_carrier
        else:  # 'lsb'
            return m * cos_carrier + m_hat * sin_carrier

    def demodulate(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        lpf_cutoff: Optional[float] = None,
        initial_phase: float = 0.0,
        numtaps: int = 101,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Demodulates SSB signal using coherent product detection + Low-pass Filter.

        Args:
            signal: Modulated SSB passband signal array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            lpf_cutoff: Cutoff frequency for low-pass filter in Hz.
            initial_phase: Coherent carrier phase in radians.
            numtaps: Number of FIR filter taps.

        Returns:
            Recovered baseband message signal array.
        """
        s = np.asarray(signal, dtype=np.float64)
        t = np.arange(len(s)) / sample_rate

        # 1. Product detection: v(t) = s(t) * cos(2*pi*f_c*t + phase)
        local_carrier = np.cos(2.0 * np.pi * carrier_freq * t + initial_phase)
        product = s * local_carrier

        # 2. FIR Low-Pass Filter
        if lpf_cutoff is None:
            lpf_cutoff = min(carrier_freq / 2.0, (sample_rate / 2.0) * 0.4)

        b = design_fir_lowpass(cutoff_freq=lpf_cutoff, sampling_rate=sample_rate, numtaps=numtaps)
        filtered = apply_filter(b, product, zero_phase=True)

        # 3. Scale by 2.0 to recover original baseband amplitude
        return 2.0 * filtered
