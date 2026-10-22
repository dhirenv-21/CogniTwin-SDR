"""
Frequency Modulation (FM) Module.

Combines Narrowband FM (NBFM) and Wideband FM (WBFM).
Implements modulation via phase integration and demodulation using Hilbert-baseband downconversion,
mandatory phase unwrapping (np.unwrap), phase differentiation, and low-pass filtering.
"""

from typing import Any, Optional
import numpy as np

from src.signal.generator import to_iq
from src.signal.filters import design_fir_lowpass, apply_filter
from .common import AnalogModulator


class FMModulator(AnalogModulator):
    """
    Frequency Modulator & Demodulator for NBFM and WBFM.
    """

    def modulate(
        self,
        message: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        freq_dev: float = 1000.0,
        amplitude: float = 1.0,
        initial_phase: float = 0.0,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Modulates message onto carrier using phase integration.

        s(t) = A_c * cos(2*pi*f_c*t + 2*pi*k_f * integral(m(tau) dtau))

        Args:
            message: Baseband message 1D array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            freq_dev: Frequency deviation constant k_f (Hz/V or max frequency offset in Hz).
            amplitude: Carrier peak amplitude A_c.
            initial_phase: Initial carrier phase in radians.

        Returns:
            Modulated FM passband signal array.
        """
        m = np.asarray(message, dtype=np.float64)
        t = np.arange(len(m)) / sample_rate

        # Integrated phase offset: phi_m(t) = 2*pi*k_f * integral(m(t) dt)
        dt = 1.0 / sample_rate
        integrated_m = np.cumsum(m) * dt
        phase_m = 2.0 * np.pi * freq_dev * integrated_m

        total_phase = 2.0 * np.pi * carrier_freq * t + initial_phase + phase_m
        return amplitude * np.cos(total_phase)

    def demodulate(
        self,
        signal: np.ndarray,
        carrier_freq: float,
        sample_rate: float,
        freq_dev: float = 1000.0,
        lpf_cutoff: Optional[float] = None,
        numtaps: int = 101,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        Demodulates FM signal using phase baseband conversion, np.unwrap, differentiation, and LPF.

        Args:
            signal: Modulated FM passband signal array.
            carrier_freq: Carrier frequency in Hz.
            sample_rate: Sampling rate in Hz.
            freq_dev: Frequency deviation constant k_f used during modulation.
            lpf_cutoff: Cutoff frequency for baseband LPF in Hz.
            numtaps: FIR lowpass filter taps.

        Returns:
            Recovered baseband message signal array.
        """
        s = np.asarray(signal, dtype=np.float64)
        t = np.arange(len(s)) / sample_rate

        # 1. Obtain complex analytic signal
        x_a = to_iq(s, method="hilbert")

        # 2. Downconvert to complex baseband: y(t) = x_a(t) * exp(-j * 2*pi*f_c*t)
        baseband_iq = x_a * np.exp(-1j * 2.0 * np.pi * carrier_freq * t)

        # 3. Extract wrapped phase angle
        phase_wrapped = np.angle(baseband_iq)

        # 4. MANDATORY: Unwrap phase to prevent 2*pi wrapping jumps
        phase_unwrapped = np.unwrap(phase_wrapped)

        # 5. Differentiate phase w.r.t time to recover instantaneous frequency deviation
        # d/dt (2*pi*k_f * integral(m dt)) = 2*pi*k_f * m(t)
        dphi_dt = np.gradient(phase_unwrapped, 1.0 / sample_rate)
        recovered_raw = dphi_dt / (2.0 * np.pi * freq_dev)

        # 6. Apply LPF to attenuate high-frequency noise from numerical differentiation
        if lpf_cutoff is None:
            lpf_cutoff = (sample_rate / 2.0) * 0.2

        b = design_fir_lowpass(cutoff_freq=lpf_cutoff, sampling_rate=sample_rate, numtaps=numtaps)
        recovered = apply_filter(b, recovered_raw, zero_phase=True)

        return recovered
