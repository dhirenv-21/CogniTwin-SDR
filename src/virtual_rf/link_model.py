"""
Link-level abstraction for the Virtual RF Environment (and therefore for the Digital
Twin's counterfactual sandbox, which calls VirtualRFEnvironment.simulate()).

Conventions
-----------
* Signal power is 1 (unit-power waveform). ``snr_db`` is the per-sample Es/N0 of the
  link without interference: N0 = 10^(-snr_db/10). This is the convention of the
  environment's own add_awgn() waveforms and of the Simulink PHY.
* Interference of power J (relative to the unit signal) is treated as additional
  Gaussian noise:  SINR = g / (N0 + J),  g = channel power gain (1 for AWGN).
  This Gaussian approximation is exact for the broadband jammer and an
  approximation for the narrowband tone and swept jammers.
* Coherent, Gray-mapped, perfect-CSI bit error rate at SINR gamma:
      BPSK                 Q(sqrt(2 gamma))
      QPSK, OFDM-QPSK      Q(sqrt(gamma))      (OFDM: per-subcarrier SINR = per-sample SINR)
      other labels         Q(sqrt(gamma))      (unchanged legacy fallback)
* Fading. ``expected`` metrics average the BER over the channel's power-gain
  distribution (E[g] = 1):
      rayleigh   two Rayleigh paths with power split 0.8 / 0.2 (the environment's
                 1 : 0.25 two-tap channel), matched-filter (diversity) combining:
                 g = 0.8 E1 + 0.2 E2, E1, E2 ~ Exp(1)  -> closed form
      rician     single path, K = 2 (the environment's (sqrt(2) LOS + scatter)/sqrt(3))
                 -> numerical integration over the non-central chi-square pdf
  ``realised`` metrics use the gain actually drawn for the current block (block fading:
  one gain per environment step).
* Packets: 256 uncoded bits, independent errors: PER = 1 - (1 - BER)^256.
  Uncoded packets are fragile: BER 1e-2 already loses ~92 % of packets. That
  saturation is physical, not a modelling artefact; see docs/EXPERIMENT_PROTOCOL.md.
* Latency is an unchanged heuristic congestion model: 5 + 15 J + 12 PER  (ms).
* Throughput (goodput) = (1 - PER) * bits/symbol * 100 ksym/s.

History: before 2026-10-22 BER was 0.5 erfc(sqrt(snr)) for BPSK *and* QPSK, x3.5
for any fading, + 0.15 J for any interference, and packet loss + 0.10 J. Those
additive terms drove every modulation to 100 % packet loss under any jammer.
"""

import math
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np
from scipy import integrate
from scipy.special import erfc, i0e

PACKET_BITS = 256
SYMBOL_RATE = 100000.0
RAYLEIGH_PATH_POWERS = (0.8, 0.2)
RICIAN_K = 2.0
FADING_CHANNELS = ("rayleigh", "rician")


def q_function(x: float) -> float:
    return 0.5 * float(erfc(x / math.sqrt(2.0)))


def _ber_scale(modulation: str) -> float:
    """c in BER = Q(sqrt(c * gamma))."""
    return 2.0 if str(modulation).upper() == "BPSK" else 1.0


def bits_per_symbol(modulation: str) -> float:
    return 2.0 if str(modulation).upper() in ("QPSK", "OFDM-QPSK") else 1.0


def ber_awgn(modulation: str, sinr_linear: float) -> float:
    """Coherent BER at a fixed SINR."""
    return q_function(math.sqrt(_ber_scale(modulation) * max(sinr_linear, 0.0)))


def _avg_q_exponential(c: float, gamma: float, mean_gain: float) -> float:
    """E[Q(sqrt(c gamma x))] for x ~ Exp(mean_gain)  (Rayleigh power gain)."""
    a = 0.5 * c * gamma * mean_gain
    return 0.5 * (1.0 - math.sqrt(a / (1.0 + a)))


@lru_cache(maxsize=4096)
def _avg_q_rician(c: float, gamma: float, k: float) -> float:
    """E[Q(sqrt(c gamma x))] for the Rician power gain with E[x] = 1."""
    def pdf(x):
        z = 2.0 * math.sqrt(k * (k + 1.0) * x)
        # (K+1) e^{-K} e^{-(K+1)x} I0(z), with I0(z) = i0e(z) e^{z} for stability
        return (k + 1.0) * math.exp(-k - (k + 1.0) * x + z) * float(i0e(z))

    val, _ = integrate.quad(lambda x: q_function(math.sqrt(c * gamma * x)) * pdf(x),
                            0.0, 60.0, limit=200)
    return float(val)


def ber_expected(modulation: str, mean_sinr_linear: float, channel: str) -> float:
    """BER averaged over the channel's power-gain distribution."""
    c = _ber_scale(modulation)
    g = max(mean_sinr_linear, 0.0)
    ch = str(channel).lower()
    if ch == "rayleigh":
        a, b = RAYLEIGH_PATH_POWERS
        # hypoexponential pdf = (a f_a - b f_b)/(a - b)  ->  same mixture of averages
        return (a * _avg_q_exponential(c, g, a) - b * _avg_q_exponential(c, g, b)) / (a - b)
    if ch == "rician":
        return _avg_q_rician(c, round(g, 12), RICIAN_K)
    return ber_awgn(modulation, g)


def link_metrics(
    modulation: str,
    snr_db: float,
    channel: str,
    interference_power: float,
    channel_gain: Optional[float] = None,
) -> Tuple[float, float, float, float, float]:
    """
    Returns (ber, packet_loss, latency_ms, throughput_bps, sinr_db).

    channel_gain: realised power gain of the current block (block fading). None ->
    expected metrics over the fading distribution (what a planner can know).
    """
    n0 = 10.0 ** (-float(snr_db) / 10.0)
    jam = max(float(interference_power), 0.0)
    ch = str(channel).lower()
    if ch in FADING_CHANNELS and channel_gain is None:
        mean_sinr = 1.0 / (n0 + jam)
        ber = ber_expected(modulation, mean_sinr, ch)
        sinr = mean_sinr
    else:
        g = 1.0 if ch not in FADING_CHANNELS else max(float(channel_gain), 0.0)
        sinr = g / (n0 + jam)
        ber = ber_awgn(modulation, sinr)
    ber = float(min(max(ber, 0.0), 0.5))
    packet_loss = float(1.0 - (1.0 - ber) ** PACKET_BITS)
    latency_ms = float(5.0 + 15.0 * jam + 12.0 * packet_loss)
    throughput = float((1.0 - packet_loss) * bits_per_symbol(modulation) * SYMBOL_RATE)
    sinr_db = float(10.0 * np.log10(sinr)) if sinr > 0 else float("-inf")
    return ber, packet_loss, latency_ms, throughput, sinr_db
