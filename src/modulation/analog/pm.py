"""
Phase Modulation (PM) Module.

Implements PM modulation and demodulation using Hilbert-baseband downconversion,
mandatory phase unwrapping (np.unwrap), and scale recovery.
"""

from typing import Any, Optional
import numpy as np

from src.signal.generator import to_iq
from src.signal.filters import design_fir_lowpass, apply_filter
from .common import AnalogModulator


class PMModulator(AnalogModulator):
    """
    Phase Modulator & Demodulator.
    """

    def modulate(
        self,
        message: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        phase_dev: float = 1.0,
        amplitude: float = 1.0,
        initial_phase: float = 0.0,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Modulates message onto carrier: s(t) = A_c * cos(2*pi*f_c*t + k_p * m(t) + initial_phase).

        Args:
            message: Baseband message 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            phase_dev: Phase sensitivity constant k_p in radians/V.
            amplitude: Carrier peak amplitude A_c.
            initial_phase: Initial carrier phase in radians.

        Returns:
            Modulated PM passband signal array.
        """
        m = np.asarray(message, dtype=np.float64)
        t = np.arange(len(m)) / sample_rate
        total_phase = 2.0 * np.pi * carrier_freq * t + initial_phase + phase_dev * m
        return amplitude * np.cos(total_phase)

    def demodulate(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        phase_dev: float = 1.0,
        lpf_cutoff: Optional[float] = None,
        numtaps: int = 101,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Demodulates PM signal using Hilbert baseband conversion, np.unwrap, and k_p scale recovery.

        Args:
            signal: Modulated PM passband signal array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            phase_dev: Phase sensitivity constant k_p used during modulation.
            lpf_cutoff: Optional LPF cutoff frequency in Hz.
            numtaps: FIR lowpass filter taps.

        Returns:
            Recovered baseband message signal array.
        """
        s = np.asarray(signal, dtype=np.float64)
        t = np.arange(len(s)) / sample_rate

        # 1. Obtain complex analytic signal
        x_a = to_iq(s, method="hilbert")

        # 2. Downconvert to complex baseband
        baseband_iq = x_a * np.exp(-1j * 2.0 * np.pi * carrier_freq * t)

        # 3. Extract wrapped phase angle
        phase_wrapped = np.angle(baseband_iq)

        # 4. MANDATORY: Unwrap phase before phase recovery
        phase_unwrapped = np.unwrap(phase_wrapped)

        # 5. Recover raw message by dividing phase by k_p
        recovered_raw = phase_unwrapped / phase_dev

        # 6. Remove mean offset
        recovered_ac = recovered_raw - np.mean(recovered_raw)

        # 7. Optional LPF smoothing
        if lpf_cutoff is not None:
            b = design_fir_lowpass(cutoff_freq=lpf_cutoff, sampling_rate=sample_rate, numtaps=numtaps)
            recovered_ac = apply_filter(b, recovered_ac, zero_phase=True)

        return recovered_ac
