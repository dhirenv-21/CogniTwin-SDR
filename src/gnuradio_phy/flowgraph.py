"""
CogniTwin-SDR GNU Radio physical layer (flowgraph version FLOWGRAPH_VERSION).

Requires GNU Radio 3.10 (gr, blocks, digital, filter, analog, channels, fft). This
module imports GNU Radio at the top on purpose: if it imports, the samples it
returns came out of GNU Radio blocks.

PSK chain (BPSK / QPSK), all in one gr.top_block:

    vector_source_b(symbol indices) -> chunks_to_symbols_bc -+-> vector_sink (tx_symbols)
                                                             |
    interp_fir_filter_ccf(sps, RRC) -+-> vector_sink (tx_os)
                                     |
            [channel: multiply_const_cc(h)  |  fading_model  |  nothing]
                                     |
    noise_source_c(sigma) -> head -+-> add_vcc <- head <- noise_source_c(sqrt(J))   (jammer)
                                   |      |                      |
                       fir(RRC) -> sink   +-> fir_filter_ccf(1, RRC) -> vector_sink (rx_mf)
                       (noise_mf)         +-> vector_sink (rx_os)        fir(RRC) -> sink (jam_mf)

    gain capture (time-varying only): vector_source_c(ones) -> fading_model(same seed) -> sink

OFDM-QPSK chain:

    vector_source_b -> chunks_to_symbols_bc -> stream_to_vector(64) -> fft_vcc(64, inverse)
      -> multiply_const_vcc(1/8) -> ofdm_cyclic_prefixer(64, 80) -> [channel] -> add_vcc(noise, jammer)

The symbol indices, the per-run block-fading gain and the seeds are drawn from the
configuration in NumPy (they are parameters of the experiment, like the SNR). All
signal processing - mapping, pulse shaping, IFFT, cyclic prefix, fading, noise,
jamming, matched filtering - is done by the GNU Radio blocks above.
"""

import math
import platform
import sys
import time
from typing import Dict, Tuple

import numpy as np
from gnuradio import analog, blocks, channels, digital, fft, filter, gr

from .config import FLOWGRAPH_VERSION, OFDM_CP_LEN, OFDM_N_FFT, GRPhyConfig, source_sha256
from .receiver import bits_to_indices, constellation_points

N_SINUSOIDS = 8


def flowgraph_source_sha256() -> str:
    """Hash of this file: identifies the exact flowgraph code that produced an export."""
    return source_sha256(__file__)


def rrc_taps(cfg: GRPhyConfig) -> np.ndarray:
    """GNU Radio's RRC design, rescaled to unit energy (sum h^2 = 1)."""
    ntaps = int(cfg.span_symbols) * int(cfg.sps) + 1
    taps = np.asarray(filter.firdes.root_raised_cosine(1.0, float(cfg.sps), 1.0, float(cfg.rolloff), ntaps),
                      dtype=np.float64)
    return taps / math.sqrt(float(np.sum(taps ** 2)))


def block_fading_gain(cfg: GRPhyConfig) -> complex:
    """One complex gain per run (E|h|^2 = 1), from the fading seed."""
    if cfg.fading_mode != "block":
        return 1.0 + 0j
    rng = np.random.default_rng(cfg.fading_seed)
    scatter = complex(rng.standard_normal(), rng.standard_normal()) / math.sqrt(2.0)
    if cfg.channel == "RICIAN":
        k = float(cfg.rician_k)
        return math.sqrt(k / (k + 1.0)) + math.sqrt(1.0 / (k + 1.0)) * scatter
    return scatter


def draw_bits(cfg: GRPhyConfig, n_bits: int) -> np.ndarray:
    return np.random.default_rng(cfg.bit_seed).integers(0, 2, n_bits, dtype=np.uint8)


class _Channel:
    """Builds the channel stage and, for time-varying fading, its gain-capture twin."""

    def __init__(self, tb: gr.top_block, cfg: GRPhyConfig, n: int):
        self.cfg, self.n = cfg, n
        self.h_block = block_fading_gain(cfg)
        self.gain_sink = None
        if cfg.fading_mode == "time_varying":
            los = cfg.channel == "RICIAN"
            self.block = channels.fading_model(N_SINUSOIDS, float(cfg.doppler_fdts), los,
                                               float(cfg.rician_k), int(cfg.fading_seed))
            twin = channels.fading_model(N_SINUSOIDS, float(cfg.doppler_fdts), los,
                                         float(cfg.rician_k), int(cfg.fading_seed))
            ones = blocks.vector_source_c([1.0 + 0j] * n, False)
            self.gain_sink = blocks.vector_sink_c()
            tb.connect(ones, twin, self.gain_sink)
        else:
            self.block = blocks.multiply_const_cc(complex(self.h_block))

    def gain(self) -> np.ndarray:
        if self.gain_sink is not None:
            return np.asarray(self.gain_sink.data(), dtype=np.complex128)
        return np.full(self.n, self.h_block, dtype=np.complex128)


def _noise(tb, amplitude: float, seed: int, n: int):
    src = analog.noise_source_c(analog.GR_GAUSSIAN, float(amplitude), int(seed))
    head = blocks.head(gr.sizeof_gr_complex, int(n))
    tb.connect(src, head)
    return head


def _sigma(cfg: GRPhyConfig) -> float:
    # complex noise_source_c(ampl) has total power ampl^2 (I and Q each ampl^2/2)
    return math.sqrt(10.0 ** (-cfg.snr_db / 10.0))


def _run_psk(cfg: GRPhyConfig) -> Tuple[Dict[str, np.ndarray], Dict[str, object]]:
    sps, span = int(cfg.sps), int(cfg.span_symbols)
    n_tot = int(cfg.n_symbols) + span                 # tail symbols flush the filters
    bits = draw_bits(cfg, n_tot * cfg.bits_per_symbol)
    idx = bits_to_indices(bits, cfg.modulation)
    n_os = n_tot * sps
    taps = rrc_taps(cfg).tolist()

    tb = gr.top_block("cognitwin_phy_psk")
    src = blocks.vector_source_b(idx.tolist(), False)
    mapper = digital.chunks_to_symbols_bc(constellation_points(cfg.modulation).tolist(), 1)
    tx_sym = blocks.vector_sink_c()
    shaper = filter.interp_fir_filter_ccf(sps, taps)
    tx_os = blocks.vector_sink_c()
    chan = _Channel(tb, cfg, n_os)
    faded = blocks.vector_sink_c()
    noise = _noise(tb, _sigma(cfg), cfg.noise_seed, n_os)
    jam = _noise(tb, math.sqrt(cfg.interference_power), cfg.jammer_seed, n_os)
    add = blocks.add_vcc(1)
    rx_os = blocks.vector_sink_c()
    mf_rx, mf_n, mf_j = (filter.fir_filter_ccf(1, taps) for _ in range(3))
    rx_mf, noise_mf, jam_mf = (blocks.vector_sink_c() for _ in range(3))

    tb.connect(src, mapper, shaper, chan.block)
    tb.connect(mapper, tx_sym)
    tb.connect(shaper, tx_os)
    tb.connect(chan.block, faded)
    tb.connect(chan.block, (add, 0))
    tb.connect(noise, (add, 1))
    tb.connect(jam, (add, 2))
    tb.connect(add, rx_os)
    tb.connect(add, mf_rx, rx_mf)
    tb.connect(noise, mf_n, noise_mf)
    tb.connect(jam, mf_j, jam_mf)

    t0 = time.perf_counter()
    tb.run()
    wall = time.perf_counter() - t0

    cap = {
        "tx_symbols": np.asarray(tx_sym.data(), dtype=np.complex128),
        "tx_os": np.asarray(tx_os.data(), dtype=np.complex128),
        "faded_os": np.asarray(faded.data(), dtype=np.complex128),
        "rx_os": np.asarray(rx_os.data(), dtype=np.complex128),
        "rx_mf": np.asarray(rx_mf.data(), dtype=np.complex128),
        "noise_mf": np.asarray(noise_mf.data(), dtype=np.complex128),
        "jam_mf": np.asarray(jam_mf.data(), dtype=np.complex128),
        "gain": chan.gain(),
    }
    info = _info(tb, cfg, wall, chan, ["vector_source_b", "chunks_to_symbols_bc", "interp_fir_filter_ccf",
                                      _chan_name(cfg), "noise_source_c x2", "head x2", "add_vcc",
                                      "fir_filter_ccf x3", "vector_sink_c"])
    info["rrc_taps"] = len(taps)
    return cap, info


def _run_ofdm(cfg: GRPhyConfig) -> Tuple[Dict[str, np.ndarray], Dict[str, object]]:
    n_ofdm = int(cfg.n_symbols) // OFDM_N_FFT
    sym_len = OFDM_N_FFT + OFDM_CP_LEN
    m = n_ofdm * sym_len
    bits = draw_bits(cfg, int(cfg.n_symbols) * 2)
    idx = bits_to_indices(bits, "QPSK")

    tb = gr.top_block("cognitwin_phy_ofdm")
    src = blocks.vector_source_b(idx.tolist(), False)
    mapper = digital.chunks_to_symbols_bc(constellation_points("QPSK").tolist(), 1)
    tx_freq = blocks.vector_sink_c()
    s2v = blocks.stream_to_vector(gr.sizeof_gr_complex, OFDM_N_FFT)
    ifft = fft.fft_vcc(OFDM_N_FFT, False, [], False)
    scale = blocks.multiply_const_vcc([1.0 / math.sqrt(OFDM_N_FFT)] * OFDM_N_FFT)
    cp = digital.ofdm_cyclic_prefixer(OFDM_N_FFT, sym_len)
    tx_time = blocks.vector_sink_c()
    chan = _Channel(tb, cfg, m)
    faded = blocks.vector_sink_c()
    noise = _noise(tb, _sigma(cfg), cfg.noise_seed, m)
    jam = _noise(tb, math.sqrt(cfg.interference_power), cfg.jammer_seed, m)
    add = blocks.add_vcc(1)
    rx_time, noise_time, jam_time = (blocks.vector_sink_c() for _ in range(3))

    tb.connect(src, mapper, s2v, ifft, scale, cp, chan.block)
    tb.connect(mapper, tx_freq)
    tb.connect(cp, tx_time)
    tb.connect(chan.block, faded)
    tb.connect(chan.block, (add, 0))
    tb.connect(noise, (add, 1))
    tb.connect(jam, (add, 2))
    tb.connect(add, rx_time)
    tb.connect(noise, noise_time)
    tb.connect(jam, jam_time)

    t0 = time.perf_counter()
    tb.run()
    wall = time.perf_counter() - t0

    cap = {
        "tx_freq": np.asarray(tx_freq.data(), dtype=np.complex128),
        "tx_time": np.asarray(tx_time.data(), dtype=np.complex128),
        "faded_os": np.asarray(faded.data(), dtype=np.complex128),
        "rx_time": np.asarray(rx_time.data(), dtype=np.complex128),
        "rx_os": np.asarray(rx_time.data(), dtype=np.complex128),
        "noise_time": np.asarray(noise_time.data(), dtype=np.complex128),
        "jam_time": np.asarray(jam_time.data(), dtype=np.complex128),
        "gain": chan.gain(),
    }
    cap["tx_os"] = cap["tx_time"]
    info = _info(tb, cfg, wall, chan, ["vector_source_b", "chunks_to_symbols_bc", "stream_to_vector",
                                      "fft_vcc(inverse)", "multiply_const_vcc", "ofdm_cyclic_prefixer",
                                      _chan_name(cfg), "noise_source_c x2", "head x2", "add_vcc",
                                      "vector_sink_c"])
    return cap, info


def _chan_name(cfg: GRPhyConfig) -> str:
    return "fading_model" if cfg.fading_mode == "time_varying" else "multiply_const_cc"


def _info(tb, cfg, wall, chan, block_list):
    return {
        "gnuradio_version": str(gr.version()),
        "flowgraph_version": FLOWGRAPH_VERSION,
        "flowgraph_sha256": flowgraph_source_sha256(),
        "top_block": tb.name(),
        "blocks": block_list,
        "wall_time_s": wall,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "block_fading_gain": complex(chan.h_block),
        "noise_amplitude": _sigma(cfg),
        "jammer_amplitude": math.sqrt(cfg.interference_power),
    }


def run_flowgraph(cfg: GRPhyConfig) -> Tuple[Dict[str, np.ndarray], Dict[str, object]]:
    """Execute the flowgraph for one configuration; return (captures, run info)."""
    cap, info = _run_ofdm(cfg) if cfg.modulation == "OFDM-QPSK" else _run_psk(cfg)
    # Self-check: the channel stage must be exactly 'gain x input'. This verifies
    # that the captured gain (constant, or the twin fading_model) is the one applied.
    n = min(cap["faded_os"].size, cap["tx_os"].size, cap["gain"].size)
    ref = cap["gain"][:n] * cap["tx_os"][:n]
    scale = max(float(np.max(np.abs(ref))) if n else 0.0, 1e-12)
    info["gain_capture_error"] = float(np.max(np.abs(cap["faded_os"][:n] - ref)) / scale) if n else float("inf")
    info["gain_capture_ok"] = bool(info["gain_capture_error"] < 1e-4)   # complex64 arithmetic
    return cap, info
