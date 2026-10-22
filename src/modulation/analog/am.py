"""
Amplitude Modulation (AM) Module.

Combines Double Sideband Suppressed Carrier (DSB-SC) and Double Sideband Transmitted Carrier (DSB-TC).
Imports filtering and signal processing components from src.signal.
"""

from typing import Any, Optional
import numpy as np

from src.signal.filters import design_fir_lowpass, apply_filter
from src.signal.generator import to_iq
from .common import AnalogModulator


class AMDSBSCModulator(AnalogModulator):
    """
    AM Double Sideband Suppressed Carrier (DSB-SC) Modulator & Demodulator.
    """

    def modulate(
        self,
        message: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        amplitude: float = 1.0,
        initial_phase: float = 0.0,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Modulates message onto carrier: s(t) = A_c * m(t) * cos(2*pi*f_c*t + phase).

        Args:
            message: Baseband message 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            amplitude: Carrier peak amplitude A_c.
            initial_phase: Initial carrier phase in radians.

        Returns:
            Modulated DSB-SC passband signal array.
        """
        m = np.asarray(message, dtype=np.float64)
        t = np.arange(len(m)) / sample_rate
        carrier = amplitude * np.cos(2.0 * np.pi * carrier_freq * t + initial_phase)
        return m * carrier

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
        Demodulates DSB-SC signal using coherent product detection + Low-pass Filter.

        Args:
            signal: Modulated DSB-SC passband signal array.
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

        # 1. Multiply by local carrier: v(t) = s(t) * cos(2*pi*f_c*t + phase)
        local_carrier = np.cos(2.0 * np.pi * carrier_freq * t + initial_phase)
        product = s * local_carrier

        # 2. Apply FIR Low-Pass Filter
        if lpf_cutoff is None:
            # Default cutoff at half carrier frequency or Nyquist fraction
            lpf_cutoff = min(carrier_freq / 2.0, (sample_rate / 2.0) * 0.4)

        b = design_fir_lowpass(cutoff_freq=lpf_cutoff, sampling_rate=sample_rate, numtaps=numtaps)
        filtered = apply_filter(b, product, zero_phase=True)

        # 3. Scale by 2.0 to compensate for 1/2 factor from cos^2 product
        recovered = 2.0 * filtered
        return recovered


class AMDSTCModulator(AnalogModulator):
    """
    AM Double Sideband Transmitted Carrier (DSB-TC / Standard AM) Modulator & Demodulator.
    """

    def modulate(
        self,
        message: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        mod_index: float = 0.8,
        amplitude: float = 1.0,
        initial_phase: float = 0.0,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Modulates message onto carrier: s(t) = A_c * [1 + mu * m_norm(t)] * cos(2*pi*f_c*t + phase).

        Args:
            message: Baseband message 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            mod_index: Modulation index mu (0 < mu <= 1.0).
            amplitude: Carrier peak amplitude A_c.
            initial_phase: Initial carrier phase in radians.

        Returns:
            Modulated DSB-TC passband signal array.
        """
        m = np.asarray(message, dtype=np.float64)
        max_m = np.max(np.abs(m))
        m_norm = m / max_m if max_m > 0 else m

        t = np.arange(len(m)) / sample_rate
        envelope = amplitude * (1.0 + mod_index * m_norm)
        carrier = np.cos(2.0 * np.pi * carrier_freq * t + initial_phase)
        return envelope * carrier

    def demodulate(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        lpf_cutoff: Optional[float] = None,
        numtaps: int = 101,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Demodulates DSB-TC signal using envelope detection via Hilbert transform.

        Args:
            signal: Modulated DSB-TC passband signal array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            lpf_cutoff: Optional LPF cutoff frequency for envelope smoothing.
            numtaps: FIR taps for smoothing filter.

        Returns:
            Recovered baseband message signal array.
        """
        s = np.asarray(signal, dtype=np.float64)

        # 1. Analytic signal magnitude gives instantaneous envelope e(t)
        analytic = to_iq(s, method="hilbert")
        envelope = np.abs(analytic)

        # 2. Remove DC component (carrier offset)
        recovered_ac = envelope - np.mean(envelope)

        # 3. Optional LPF smoothing
        if lpf_cutoff is not None:
            b = design_fir_lowpass(cutoff_freq=lpf_cutoff, sampling_rate=sample_rate, numtaps=numtaps)
            recovered_ac = apply_filter(b, recovered_ac, zero_phase=True)

        return recovered_ac
