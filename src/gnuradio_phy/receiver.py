"""
Post-processing of GNU Radio captures: symbol timing, genie equalisation, hard
decisions, BER / PER, measured SNR, and the analytical references.

Pure NumPy. Nothing here generates channel samples: it only operates on arrays
captured from a GNU Radio flowgraph (src/gnuradio_phy/flowgraph.py). Unit tests feed
it hand-built arrays to check the arithmetic; those arrays are never exported or
reported as GNU Radio output.

Receiver assumptions (stated in every export's receiver_settings):
  * symbol timing: known filter delay (span_symbols * sps samples), CHECKED by a
    correlation search over every lag in [0, 2 * delay]; a mismatch is reported,
    never silently corrected;
  * channel state: genie (the true gain captured from the flowgraph);
  * OFDM: genie timing, CP removal, 64-point FFT, one-tap genie equaliser. This is
    an OFDM demodulator for a known frame, NOT a full OFDM receiver (no
    synchronisation, no pilots, no channel estimation).
"""

import math
from typing import Dict, Optional, Tuple

import numpy as np

from src.virtual_rf.link_model import ber_awgn

from .config import OFDM_CP_LEN, OFDM_N_FFT, PACKET_BITS, GRPhyConfig

SQRT1_2 = 1.0 / math.sqrt(2.0)


# --------------------------------------------------------------- constellations

def constellation_points(modulation: str) -> np.ndarray:
    """Points indexed by symbol value. QPSK index = 2*b_I + b_Q (Gray by construction)."""
    mod = modulation.upper()
    if mod == "BPSK":
        return np.array([-1.0 + 0j, 1.0 + 0j])
    if mod in ("QPSK", "OFDM-QPSK"):
        return np.array([-1 - 1j, -1 + 1j, 1 - 1j, 1 + 1j]) * SQRT1_2
    raise ValueError(f"no constellation for {modulation!r}")


def bits_to_indices(bits: np.ndarray, modulation: str) -> np.ndarray:
    b = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if modulation.upper() == "BPSK":
        return b.copy()
    if b.size % 2:
        raise ValueError("QPSK needs an even number of bits")
    return (2 * b[0::2] + b[1::2]).astype(np.uint8)


def hard_decide_bits(z: np.ndarray, modulation: str) -> np.ndarray:
    """Minimum-distance decisions for the constellations above, as bits."""
    z = np.asarray(z, dtype=np.complex128).reshape(-1)
    if modulation.upper() == "BPSK":
        return (z.real > 0).astype(np.uint8)
    out = np.empty(2 * z.size, dtype=np.uint8)
    out[0::2] = z.real > 0
    out[1::2] = z.imag > 0
    return out


def packet_error_rate(errors: np.ndarray, packet_bits: int = PACKET_BITS) -> Tuple[float, int]:
    """Fraction of complete packets with at least one bit error, and the packet count."""
    e = np.asarray(errors, dtype=bool).reshape(-1)
    n_pkt = e.size // packet_bits
    if n_pkt == 0:
        return float("nan"), 0
    per_pkt = e[: n_pkt * packet_bits].reshape(n_pkt, packet_bits).any(axis=1)
    return float(per_pkt.mean()), int(n_pkt)


def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95 % Wilson score interval for a binomial proportion (valid at k = 0)."""
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


# --------------------------------------------------------------- theory

def theoretical_ber(modulation: str, snr_db: float, interference_power: float = 0.0,
                    gains: Optional[np.ndarray] = None) -> float:
    """
    Coherent BER for a Gaussian jammer treated as noise, conditional on the
    REALISED channel gains (one per decided symbol), or h = 1 if gains is None.

        BPSK                Q(sqrt(2 |h|^2 Es/(N0 + J)))     = Q(sqrt(2 Eb/N0)) at J = 0
        QPSK / OFDM-QPSK    Q(sqrt(  |h|^2 Es/(N0 + J)))     (Eb = Es/2, Gray)

    Uses src/virtual_rf/link_model.ber_awgn, the same formula as the closed loop.
    For OFDM the unitary FFT keeps the per-subcarrier noise variance equal to the
    time-domain one, so the QPSK expression applies per subcarrier.
    """
    sinr = 1.0 / (10.0 ** (-snr_db / 10.0) + max(interference_power, 0.0))
    mod = "QPSK" if modulation.upper() == "OFDM-QPSK" else modulation
    if gains is None:
        return ber_awgn(mod, sinr)
    g2 = np.abs(np.asarray(gains, dtype=np.complex128).reshape(-1)) ** 2
    return float(np.mean([ber_awgn(mod, sinr * x) for x in g2]))


# --------------------------------------------------------------- PSK

def psk_delay(cfg: GRPhyConfig) -> int:
    """Combined delay of the TX and RX RRC filters (ntaps - 1 = span * sps samples)."""
    return int(cfg.span_symbols) * int(cfg.sps)


def find_symbol_lag(mf: np.ndarray, tx_symbols: np.ndarray, sps: int, max_lag: int) -> Tuple[int, np.ndarray]:
    """Lag (oversampled samples) maximising |<tx, mf[lag::sps]>|; also the score per lag."""
    n = tx_symbols.size
    scores = np.zeros(max_lag + 1)
    for lag in range(max_lag + 1):
        seg = mf[lag::sps][:n]
        if seg.size < n:
            break
        scores[lag] = abs(np.vdot(tx_symbols, seg))
    return int(np.argmax(scores)), scores


def demodulate_psk(cfg: GRPhyConfig, capture: Dict[str, np.ndarray]) -> Dict[str, object]:
    """
    capture (all from the GNU Radio flowgraph):
        tx_symbols   chunks_to_symbols output, one per symbol (N + span tail symbols)
        rx_mf        matched-filter output of the received signal, oversampled
        noise_mf     matched-filter output of the noise branch alone, oversampled
        jam_mf       matched-filter output of the jammer branch alone (zeros if J = 0)
        gain         channel gain per oversampled sample (ones for AWGN)
    """
    n = int(cfg.n_symbols)
    sps = int(cfg.sps)
    delay = psk_delay(cfg)
    tx_all = np.asarray(capture["tx_symbols"], dtype=np.complex128)
    tx = tx_all[:n]
    mf = np.asarray(capture["rx_mf"], dtype=np.complex128)

    lag, _ = find_symbol_lag(mf, tx, sps, 2 * delay)
    idx = delay + sps * np.arange(n)
    if idx[-1] >= mf.size:
        raise ValueError(f"matched-filter capture too short ({mf.size} samples) for {n} symbols at delay {delay}")
    rx = mf[idx]
    noise = np.asarray(capture["noise_mf"], dtype=np.complex128)[idx]
    jam = np.asarray(capture["jam_mf"], dtype=np.complex128)[idx]
    # The gain that multiplied the pulse PEAK of symbol k (tx sample k*sps + delay/2).
    gain_full = np.asarray(capture["gain"], dtype=np.complex128)
    h = gain_full[sps * np.arange(n) + delay // 2]
    return _decide(cfg, tx, rx, noise, jam, h, lag_found=lag, lag_expected=delay)


# --------------------------------------------------------------- OFDM

def demodulate_ofdm(cfg: GRPhyConfig, capture: Dict[str, np.ndarray]) -> Dict[str, object]:
    """
    capture:
        tx_freq      QPSK subcarrier symbols fed to the IFFT (n_symbols)
        tx_time      cyclic-prefixed time-domain samples (n_symbols / 64 * 80)
        rx_time      received time-domain samples (same length)
        noise_time   noise branch alone; jam_time jammer branch alone
        gain         channel gain per time-domain sample
    """
    sym_len = OFDM_N_FFT + OFDM_CP_LEN
    n_ofdm = int(cfg.n_symbols) // OFDM_N_FFT
    m = n_ofdm * sym_len
    tx_freq = np.asarray(capture["tx_freq"], dtype=np.complex128)[: n_ofdm * OFDM_N_FFT]
    tx_t = np.asarray(capture["tx_time"], dtype=np.complex128)[:m]
    rx_t = np.asarray(capture["rx_time"], dtype=np.complex128)[:m]
    if rx_t.size < m:
        raise ValueError(f"OFDM capture has {rx_t.size} samples, need {m}")
    gain_t = np.asarray(capture["gain"], dtype=np.complex128)[:m]
    blocks = rx_t.reshape(n_ofdm, sym_len)[:, OFDM_CP_LEN:]
    y = np.fft.fft(blocks, axis=1) / math.sqrt(OFDM_N_FFT)
    # flat channel: one tap per OFDM symbol = mean gain over its useful samples
    h_sym = gain_t.reshape(n_ofdm, sym_len)[:, OFDM_CP_LEN:].mean(axis=1)
    h_sub = np.repeat(h_sym, OFDM_N_FFT)
    z = y.reshape(-1)

    lag = int(np.argmax([abs(np.vdot(tx_t[: m - d], rx_t[d:m])) for d in range(OFDM_CP_LEN + 1)]))
    noise_t = np.asarray(capture["noise_time"], dtype=np.complex128)[:m]
    jam_t = np.asarray(capture["jam_time"], dtype=np.complex128)[:m]
    out = _decide(cfg, tx_freq, z, None, None, h_sub, lag_found=lag, lag_expected=0)
    # SNR / J are measured in the time domain, where they are defined.
    p_tx = float(np.mean(np.abs(tx_t) ** 2))
    out["measured_snr_db"] = _db(p_tx / max(float(np.mean(np.abs(noise_t) ** 2)), 1e-300))
    out["measured_interference_power"] = float(np.mean(np.abs(jam_t) ** 2))
    out["tx_power"] = p_tx
    out["export"] = {"tx": tx_t, "rx": rx_t, "noise": noise_t, "jam": jam_t, "gain": gain_t}
    return out


# --------------------------------------------------------------- common

def _db(x: float) -> float:
    return 10.0 * math.log10(x) if x > 0 else float("-inf")


# The timing search (find_symbol_lag) can only confirm the filter delay when the
# correlation peak stands clear of the noise across all searched lags. Expected peak
# |h| N against a noise standard deviation sqrt(N (N0 + J)) gives a peak-to-noise
# ratio z = |h| sqrt(N) / sqrt(N0 + J). The max of ~90 noise-only lags is ~3 sigma,
# so below 8 sigma the check is uninformative (e.g. a -34 dB block fade, measured in
# campaign grcl1: z = 2.2, BER 0.49) and is skipped rather than failed, as the bridge
# does for wanted_signal_present.
TIMING_RESOLVABLE_Z = 8.0


def timing_peak_z(cfg: GRPhyConfig, h: np.ndarray, n: int) -> float:
    g = float(np.mean(np.abs(np.asarray(h, dtype=np.complex128))))
    return g * math.sqrt(max(n, 1)) / math.sqrt(10.0 ** (-cfg.snr_db / 10.0) + max(cfg.interference_power, 0.0))


def _decide(cfg, tx_sym, rx_sym, noise, jam, h, lag_found, lag_expected):
    ref_bits = hard_decide_bits(tx_sym, cfg.modulation)          # exact: tx is on the grid
    z = rx_sym / np.where(np.abs(h) > 0, h, 1.0)
    rx_bits = hard_decide_bits(z, cfg.modulation)
    err = rx_bits != ref_bits
    k, nb = int(err.sum()), int(err.size)
    per, n_pkt = packet_error_rate(err)
    lo, hi = wilson_interval(k, nb)
    out = {
        "ref_bits": ref_bits,
        "rx_bits": rx_bits,
        "bit_errors": k,
        "bits_compared": nb,
        "ber": k / nb,
        "ber_ci95": (lo, hi),
        "per": per,
        "packets": n_pkt,
        "ber_theory": theoretical_ber(cfg.modulation, cfg.snr_db, cfg.interference_power,
                                      None if cfg.fading_mode == "none" else h),
        "timing_lag_found": int(lag_found),
        "timing_lag_expected": int(lag_expected),
        "timing_ok": int(lag_found) == int(lag_expected),
        "timing_peak_z": timing_peak_z(cfg, h, nb // cfg.bits_per_symbol),
        "equaliser_gains": h,
        "decided_symbols": z,
    }
    if noise is not None:
        p_tx = float(np.mean(np.abs(tx_sym) ** 2))
        out["measured_snr_db"] = _db(p_tx / max(float(np.mean(np.abs(noise) ** 2)), 1e-300))
        out["measured_interference_power"] = float(np.mean(np.abs(jam) ** 2))
        out["tx_power"] = p_tx
        out["export"] = {"tx": tx_sym, "rx": rx_sym, "noise": noise, "jam": jam, "gain": h}
    return out


def goodput_bps(cfg: GRPhyConfig, per: float) -> float:
    """Correctly delivered payload bits per second: (1 - PER) * payload bit rate.

    PER is MEASURED from the bit errors in 256-bit packets (no coding, no ARQ).
    OFDM's payload rate includes the CP overhead (1.6 bit per sample at 64/80).
    """
    return (1.0 - per) * cfg.payload_bits_per_second


def spectral_efficiency(cfg: GRPhyConfig, per: float) -> float:
    """Goodput per occupied bandwidth, bit/s/Hz (bandwidth defined in config)."""
    return goodput_bps(cfg, per) / cfg.occupied_bandwidth_hz
