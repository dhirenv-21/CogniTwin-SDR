"""
Test-only helpers for the GNU Radio integration tests.

numpy_capture() builds arrays with the SAME layout as a GNU Radio flowgraph capture,
using NumPy, so the receiver arithmetic, export format and validator can be tested
on machines without GNU Radio. These arrays are NOT GNU Radio output:
labelled_fixture() relabels every export built from them as source='python-fixture',
and forged_gnuradio() exists only to prove that a file claiming GNU Radio
provenance is rejected unless all the evidence agrees.
"""

import math

import numpy as np

from src.gnuradio_phy.config import OFDM_CP_LEN, OFDM_N_FFT, GRPhyConfig
from src.gnuradio_phy.export import build_export, content_sha256
from src.gnuradio_phy.receiver import (
    bits_to_indices, constellation_points, demodulate_ofdm, demodulate_psk, psk_delay,
)
from src.gnuradio_phy.validation import repo_flowgraph_sha256


def _rrc(cfg):
    """Unit-energy RRC (closed form) - stands in for firdes.root_raised_cosine."""
    sps, span, a = cfg.sps, cfg.span_symbols, cfg.rolloff
    t = (np.arange(span * sps + 1) - span * sps / 2) / sps
    h = np.empty_like(t)
    for i, x in enumerate(t):
        if abs(x) < 1e-12:
            h[i] = 1 - a + 4 * a / math.pi
        elif abs(abs(x) - 1 / (4 * a)) < 1e-12:
            h[i] = a / math.sqrt(2) * ((1 + 2 / math.pi) * math.sin(math.pi / (4 * a))
                                       + (1 - 2 / math.pi) * math.cos(math.pi / (4 * a)))
        else:
            h[i] = (math.sin(math.pi * x * (1 - a)) + 4 * a * x * math.cos(math.pi * x * (1 + a))) / \
                   (math.pi * x * (1 - (4 * a * x) ** 2))
    return h / math.sqrt(np.sum(h ** 2))


def numpy_capture(cfg: GRPhyConfig, gain=None):
    """NumPy stand-in with the flowgraph's capture layout (see module docstring)."""
    rng = np.random.default_rng(cfg.seed + 7919)
    sigma = math.sqrt(10 ** (-cfg.snr_db / 10))
    sj = math.sqrt(cfg.interference_power)

    def cn(n, s):
        return s * (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / math.sqrt(2)

    pts = constellation_points(cfg.modulation)
    if cfg.modulation == "OFDM-QPSK":
        bits = np.random.default_rng(cfg.bit_seed).integers(0, 2, cfg.n_symbols * 2).astype(np.uint8)
        f = pts[bits_to_indices(bits, "QPSK")]
        x = np.fft.ifft(f.reshape(-1, OFDM_N_FFT), axis=1) * math.sqrt(OFDM_N_FFT)
        t = np.hstack([x[:, -OFDM_CP_LEN:], x]).reshape(-1)
        m = t.size
        g = np.full(m, 1.0 + 0j) if gain is None else np.broadcast_to(gain, (m,)).astype(complex)
        n, j = cn(m, sigma), cn(m, sj)
        rx = g * t + n + j
        return {"tx_freq": f, "tx_time": t, "faded_os": g * t, "rx_time": rx, "rx_os": rx,
                "noise_time": n, "jam_time": j, "gain": g, "tx_os": t}
    span, sps = cfg.span_symbols, cfg.sps
    n_tot = cfg.n_symbols + span
    bits = np.random.default_rng(cfg.bit_seed).integers(0, 2, n_tot * cfg.bits_per_symbol).astype(np.uint8)
    s = pts[bits_to_indices(bits, cfg.modulation)]
    h = _rrc(cfg)
    up = np.zeros(n_tot * sps, complex)
    up[::sps] = s
    tx_os = np.convolve(up, h)[: n_tot * sps]
    g = np.full(tx_os.size, 1.0 + 0j) if gain is None else np.broadcast_to(gain, tx_os.shape).astype(complex)
    n, j = cn(tx_os.size, sigma), cn(tx_os.size, sj)
    rx_os = g * tx_os + n + j

    def mf(v):
        return np.convolve(v, h)[: v.size]

    return {"tx_symbols": s, "tx_os": tx_os, "faded_os": g * tx_os, "rx_os": rx_os, "rx_mf": mf(rx_os),
            "noise_mf": mf(n), "jam_mf": mf(j), "gain": g}


def _info(version="not-gnuradio", sha="not-a-flowgraph"):
    return {"gnuradio_version": version, "flowgraph_version": "gr-phy-1", "flowgraph_sha256": sha,
            "blocks": ["numpy test stand-in"], "wall_time_s": 0.0, "gain_capture_ok": True,
            "gain_capture_error": 0.0}


def demod(cfg, cap):
    return demodulate_ofdm(cfg, cap) if cfg.modulation == "OFDM-QPSK" else demodulate_psk(cfg, cap)


def labelled_fixture(cfg: GRPhyConfig, gain=None):
    """An export dict from NumPy arrays, honestly labelled source='python-fixture'."""
    cap = numpy_capture(cfg, gain)
    d = build_export(cfg, cap, _info(), demod(cfg, cap))
    d["source"] = "python-fixture"
    d["simulator"] = "NumPy test stand-in (not GNU Radio)"
    d["content_sha256"] = content_sha256(d)
    return d


def forged_gnuradio(cfg: GRPhyConfig, gain=None, version="3.10.12.0", sha=None):
    """A NumPy export that CLAIMS GNU Radio provenance (for rejection tests only)."""
    cap = numpy_capture(cfg, gain)
    d = build_export(cfg, cap, _info(version, sha or repo_flowgraph_sha256()), demod(cfg, cap))
    return d


__all__ = ["numpy_capture", "labelled_fixture", "forged_gnuradio", "demod", "psk_delay"]
