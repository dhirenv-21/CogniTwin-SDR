"""
Python Reference PHY - FIXTURE GENERATOR ONLY.

=============================================================================
THIS MODULE DOES NOT PRODUCE SIMULINK DATA.
=============================================================================
Everything it writes is tagged  source = "python-fixture"  in the MAT file and is
rejected by the "REAL SIMULINK END-TO-END TEST" guard in
experiments/simulink_acwra_demo.py. It exists for exactly two reasons:

  1. pytest must run on machines without MATLAB (Task 11, Part 9-H / Part 9-I).
  2. the validation campaign must still exercise every SNR / interference / channel
     combination when MATLAB is unavailable, with every row explicitly labelled
     FIXTURE rather than REAL.

It is a bit-exact Python mirror of the signal chain implemented by the Simulink model
(simulink/cognitwin_sdr_phy.slx via simulink/create_cognitwin_model.m):

    tx  = unit-power baseband symbols  (BPSK / QPSK / OFDM-QPSK)
    h   = 1                            (AWGN)  |  (randn + 1j*randn)/sqrt(2)  (Rayleigh)
    jam = sqrt(P_int/2) * (randn + 1j*randn)          -> jammer power = P_int
    n   = sqrt(10^(-SNR/10)/2) * (randn + 1j*randn)   -> noise power  = 10^(-SNR/10)
    rx  = h*tx + jam + n

so that for unit-power tx the signal-to-interference ratio is exactly
SIR_dB = -10*log10(P_int), matching the tolerances asserted in Part 9-D.
"""

from typing import Any, Dict, Optional, Tuple

import numpy as np
import scipy.io as sio

from src.modulation.digital.common import calculate_ber, generate_bits
from src.modulation.digital.psk import PSKModulator
from src.multicarrier.ofdm import OFDMTransmitterReceiver

FIXTURE_SOURCE_TAG = "python-fixture"
SUPPORTED_MODULATIONS = ("BPSK", "QPSK", "OFDM-QPSK")


def _make_tx(
    modulation: str,
    n_samples: int,
    rng: np.random.Generator,
    pattern_symbols: int = 0,
) -> Tuple[np.ndarray, np.ndarray, Any]:
    """
    Build a unit-power transmit waveform plus the bits that produced it.

    pattern_symbols > 0 generates that many unique symbols and repeats them to fill
    the capture (a repeating training/pilot pattern). pattern_symbols = 0 (default)
    generates a genuinely non-repeating random symbol stream, which is what a real
    link carries. See the note in the module docstring of
    experiments/simulink_acwra_campaign.py about how this affects the existing
    Task-5 modulation classifier.
    """
    mod = modulation.upper()

    if mod in ("BPSK", "QPSK"):
        M = 2 if mod == "BPSK" else 4
        k = 1 if mod == "BPSK" else 2
        psk = PSKModulator(M=M)
        n_unique = int(pattern_symbols) if pattern_symbols and pattern_symbols > 0 else n_samples
        bits = generate_bits(n_unique * k, seed=int(rng.integers(0, 10**6)))
        syms = psk.modulate_baseband(bits)
        if syms.size < n_samples:
            reps = int(np.ceil(n_samples / syms.size))
            tx = np.tile(syms, reps)[:n_samples]
            bits_full = np.tile(bits, reps)[: n_samples * k]
        else:
            tx = syms[:n_samples]
            bits_full = bits[: n_samples * k]
        return tx, bits_full, psk

    if mod in ("OFDM-QPSK", "OFDM_QPSK", "OFDM"):
        ofdm = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
        # 80 time samples per OFDM symbol, 128 bits per OFDM symbol.
        n_syms = int(np.ceil(n_samples / 80.0))
        bits = generate_bits(n_syms * 128, seed=int(rng.integers(0, 10**6)))
        wave, _ = ofdm.modulate(bits)
        tx = wave[:n_samples]
        return tx, bits, ofdm

    raise ValueError(
        f"reference_phy supports {SUPPORTED_MODULATIONS}, got '{modulation}'"
    )


def _measure_ber(
    modulation: str,
    rx_eq: np.ndarray,
    bits_tx: np.ndarray,
    demod: Any,
    n_samples: int,
) -> float:
    """Hard-decision demodulate the equalised waveform and count real bit errors."""
    mod = modulation.upper()
    try:
        if mod in ("BPSK", "QPSK"):
            bits_rx = demod.demodulate_baseband(rx_eq)
            k = 1 if mod == "BPSK" else 2
            n_bits = min(len(bits_rx), len(bits_tx), rx_eq.size * k)
            return float(calculate_ber(bits_tx[:n_bits], bits_rx[:n_bits]))

        # OFDM: only whole (n_fft + cp_len) = 80-sample symbols can be demodulated.
        sym_len = demod.n_fft + demod.cp_len
        n_syms = int(rx_eq.size // sym_len)
        if n_syms == 0:
            return 0.0
        bits_rx = demod.demodulate(rx_eq[: n_syms * sym_len], num_ofdm_symbols=n_syms)
        if isinstance(bits_rx, tuple):
            bits_rx = bits_rx[0]
        n_bits = min(len(bits_rx), len(bits_tx))
        return float(calculate_ber(bits_tx[:n_bits], bits_rx[:n_bits]))
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            f"reference PHY could not demodulate '{modulation}' to measure BER: {exc}"
        ) from exc


def generate_reference_measurement(
    modulation: str = "QPSK",
    snr_db: float = 20.0,
    interference_power: float = 0.0,
    channel_type: str = "AWGN",
    n_samples: int = 10000,
    sample_rate: float = 100000.0,
    timestamp: float = 0.0,
    seed: int = 42,
    pattern_symbols: int = 0,
) -> Dict[str, Any]:
    """
    Produce a MAT-schema dict identical in structure to the MATLAB export.

    Returns a dict ready for scipy.io.savemat, always tagged source="python-fixture".
    """
    rng = np.random.default_rng(seed)

    tx, bits_tx, demod = _make_tx(modulation, n_samples, rng, pattern_symbols=pattern_symbols)
    if tx.size < n_samples:  # tile only to reach the requested capture length
        reps = int(np.ceil(n_samples / tx.size))
        tx = np.tile(tx, reps)[:n_samples]
    tx = tx[:n_samples]

    # Channel gain (block fading, matching the Simulink PHY_Channel implementation).
    if str(channel_type).upper() == "RAYLEIGH":
        h = complex((rng.normal() + 1j * rng.normal()) / np.sqrt(2.0))
    elif str(channel_type).upper() == "RICIAN":
        k_factor = 2.0
        scatter = (rng.normal() + 1j * rng.normal()) / np.sqrt(2.0)
        h = complex((np.sqrt(k_factor) + scatter) / np.sqrt(k_factor + 1.0))
    else:
        h = 1.0 + 0.0j

    noise_power = 10.0 ** (-float(snr_db) / 10.0)
    noise = np.sqrt(noise_power / 2.0) * (
        rng.normal(size=n_samples) + 1j * rng.normal(size=n_samples)
    )
    p_int = max(0.0, float(interference_power))
    if p_int > 0:
        jam = np.sqrt(p_int / 2.0) * (
            rng.normal(size=n_samples) + 1j * rng.normal(size=n_samples)
        )
    else:
        jam = np.zeros(n_samples, dtype=np.complex128)

    rx = h * tx + jam + noise

    # Coherent single-tap equalisation before demodulation (receiver-side, not a
    # channel model change) so the measured BER reflects the true link quality.
    rx_eq = rx / h if abs(h) > 1e-12 else rx
    ber = _measure_ber(modulation, rx_eq, bits_tx, demod, n_samples)

    t = np.arange(n_samples, dtype=np.float64) / float(sample_rate)

    p_sig = float(np.mean(np.abs(h * tx) ** 2))
    p_noise = float(np.mean(np.abs(noise) ** 2))
    p_jam = float(np.mean(np.abs(jam) ** 2))

    return {
        "iq_samples": rx.reshape(-1, 1),  # MATLAB-style column vector
        "tx_iq": tx.reshape(-1, 1),
        # Logged separately so signal / noise / interference powers can be measured
        # independently rather than inferred - same schema as the MATLAB export.
        "noise_iq": noise.reshape(-1, 1),
        "interference_iq": jam.reshape(-1, 1),
        "time_vector": t.reshape(-1, 1),
        "measured_signal_power": p_sig,
        "measured_noise_power": p_noise,
        "measured_interference_power": p_jam,
        "measured_snr_db": float(10.0 * np.log10(p_sig / max(p_noise, 1e-300))),
        "measured_sinr_db": float(
            10.0 * np.log10(p_sig / max(p_noise + p_jam, 1e-300))
        ),
        "sim_stop_time": float((n_samples - 1) / float(sample_rate)),
        "samples_per_symbol": 1.0,
        "snr_db": float(snr_db),
        "ber": float(ber),
        "modulation": str(modulation),
        "interference_power": float(p_int),
        "channel_type": str(channel_type),
        "timestamp": float(timestamp),
        "sample_rate": float(sample_rate),
        "num_samples": float(n_samples),
        "source": FIXTURE_SOURCE_TAG,
        "channel_gain_real": float(np.real(h)),
        "channel_gain_imag": float(np.imag(h)),
        "pattern_symbols": float(pattern_symbols),
    }


def write_reference_mat(path: str, **kwargs) -> str:
    """Write a fixture MAT file to `path` and return the path."""
    import os

    mat = generate_reference_measurement(**kwargs)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    sio.savemat(path, mat)
    return path
