"""
GNU Radio integration - unit tests that need NO GNU Radio.

Category: Python unit (receiver arithmetic, configuration, analytical references).
The arrays used here come from tests/gr_test_helpers.numpy_capture (a NumPy stand-in
with the flowgraph's capture layout); nothing here is, or is reported as, GNU Radio
output. Real flowgraph execution is in tests/test_gnuradio_execution.py.
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gr_test_helpers import demod, numpy_capture  # noqa: E402
from src.gnuradio_phy.config import GRPhyConfig, source_sha256  # noqa: E402
from src.gnuradio_phy.receiver import (  # noqa: E402
    bits_to_indices, constellation_points, goodput_bps, hard_decide_bits, packet_error_rate,
    spectral_efficiency, theoretical_ber, wilson_interval,
)


# ------------------------------------------------------------------ config

@pytest.mark.parametrize("kw", [
    dict(modulation="8PSK"), dict(channel="AWGN", fading_mode="block"), dict(channel="RAYLEIGH"),
    dict(seed=0), dict(modulation="OFDM-QPSK", n_symbols=1000), dict(snr_db=float("nan")),
    dict(interference_power=-0.1), dict(n_symbols=10), dict(sps=1), dict(snr_db=99),
])
def test_config_rejects_invalid(kw):
    with pytest.raises(ValueError):
        GRPhyConfig(**kw)


def test_config_hash_identity():
    a = GRPhyConfig(seed=3)
    assert a.config_hash() == GRPhyConfig(seed=3).config_hash()
    assert a.config_hash() != GRPhyConfig(seed=4).config_hash()
    assert a.config_hash() != a.replace(snr_db=10.5).config_hash()
    # 'extra' is annotation only and never changes the identity
    assert a.config_hash() == GRPhyConfig(seed=3, extra={"note": "x"}).config_hash()
    ids = {GRPhyConfig(seed=s, snr_db=x).experiment_id() for s in (1, 2) for x in (0.0, 5.0)}
    assert len(ids) == 4


def test_seed_streams_distinct_and_nonzero():
    for s in (1, 2, 1000):
        c = GRPhyConfig(seed=s)
        seeds = {c.bit_seed, c.noise_seed, c.jammer_seed, c.fading_seed}
        assert len(seeds) == 4 and min(seeds) > 0       # 0 = clock seed in GNU Radio


def test_source_hash_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_bytes(b"x = 1\ny = 2\n")
    b.write_bytes(b"x = 1\r\ny = 2\r\n")
    assert source_sha256(str(a)) == source_sha256(str(b))


def test_rates_and_bandwidth_definitions():
    assert GRPhyConfig(modulation="BPSK").payload_bits_per_second == 1e5
    assert GRPhyConfig(modulation="QPSK").payload_bits_per_second == 2e5
    assert GRPhyConfig(modulation="OFDM-QPSK").payload_bits_per_second == pytest.approx(1.6e5)
    q = GRPhyConfig(modulation="QPSK", rolloff=0.35)
    assert goodput_bps(q, 0.25) == pytest.approx(1.5e5)
    assert spectral_efficiency(q, 0.0) == pytest.approx(2.0 / 1.35)


# ------------------------------------------------------------------ constellations

@pytest.mark.parametrize("mod", ["BPSK", "QPSK"])
def test_mapping_roundtrip_and_unit_energy(mod):
    pts = constellation_points(mod)
    assert np.allclose(np.abs(pts), 1.0)
    bits = np.random.default_rng(0).integers(0, 2, 1000).astype(np.uint8)
    assert np.array_equal(hard_decide_bits(pts[bits_to_indices(bits, mod)], mod), bits)


def test_qpsk_is_gray_coded():
    pts = constellation_points("QPSK")
    for i in range(4):
        for j in range(4):
            if i != j and math.isclose(abs(pts[i] - pts[j]), math.sqrt(2)):   # nearest neighbours
                assert bin(i ^ j).count("1") == 1


# ------------------------------------------------------------------ theory

def test_bpsk_theory_reference_point():
    # textbook: BPSK BER = 1e-5 near Eb/N0 = 9.59 dB
    assert theoretical_ber("BPSK", 9.59) == pytest.approx(1.0e-5, rel=0.03)


def test_qpsk_equals_bpsk_at_equal_ebn0():
    # QPSK Es = 2 Eb: QPSK at Es/N0 = x + 3.01 dB equals BPSK at Eb/N0 = x
    for x in (0.0, 4.0, 8.0):
        assert theoretical_ber("QPSK", x + 10 * math.log10(2)) == pytest.approx(theoretical_ber("BPSK", x), rel=1e-9)
    assert theoretical_ber("OFDM-QPSK", 7.0) == theoretical_ber("QPSK", 7.0)


def test_theory_with_jammer_and_gains():
    assert theoretical_ber("QPSK", 10, 0.1) > theoretical_ber("QPSK", 10, 0.0)
    assert theoretical_ber("QPSK", 10, 0.0, gains=np.ones(5)) == pytest.approx(theoretical_ber("QPSK", 10))
    assert theoretical_ber("QPSK", 10, gains=np.full(5, 0.5)) > theoretical_ber("QPSK", 10)


def test_wilson_interval_and_per():
    lo, hi = wilson_interval(0, 1000)
    assert lo == 0.0 and 0 < hi < 0.005
    lo, hi = wilson_interval(50, 1000)
    assert lo < 0.05 < hi
    e = np.zeros(1024, bool)
    e[3] = e[700] = True
    assert packet_error_rate(e) == (0.5, 4)
    assert math.isnan(packet_error_rate(np.zeros(10, bool))[0])


# ------------------------------------------------------------------ receiver arithmetic

@pytest.mark.parametrize("mod", ["BPSK", "QPSK", "OFDM-QPSK"])
def test_receiver_error_free_at_high_snr(mod):
    cfg = GRPhyConfig(modulation=mod, snr_db=40.0, n_symbols=1024)
    out = demod(cfg, numpy_capture(cfg))
    assert out["timing_ok"] and out["bit_errors"] == 0
    assert out["measured_snr_db"] == pytest.approx(40.0, abs=0.5)


@pytest.mark.parametrize("mod", ["QPSK", "OFDM-QPSK"])
def test_receiver_genie_equaliser_removes_block_fade(mod):
    cfg = GRPhyConfig(modulation=mod, snr_db=40.0, channel="RAYLEIGH", fading_mode="block", n_symbols=1024)
    out = demod(cfg, numpy_capture(cfg, gain=0.3 * np.exp(1j * 2.0)))
    assert out["bit_errors"] == 0
    assert np.allclose(out["equaliser_gains"], 0.3 * np.exp(1j * 2.0))


def test_receiver_detects_wrong_timing():
    cfg = GRPhyConfig(modulation="QPSK", snr_db=30.0, n_symbols=1024)
    cap = numpy_capture(cfg)
    for k in ("rx_mf", "noise_mf", "jam_mf"):
        cap[k] = np.concatenate([np.zeros(3, complex), cap[k]])     # 3-sample timing offset
    out = demod(cfg, cap)
    assert not out["timing_ok"] and out["timing_lag_found"] == out["timing_lag_expected"] + 3


@pytest.mark.parametrize("mod,snr", [("BPSK", 4.0), ("QPSK", 7.0), ("OFDM-QPSK", 7.0)])
def test_receiver_arithmetic_matches_theory_on_stand_in(mod, snr):
    """Receiver arithmetic only (NumPy stand-in, Gaussian noise): measured BER inside 99.9 % Wilson."""
    cfg = GRPhyConfig(modulation=mod, snr_db=snr, n_symbols=16384)
    out = demod(cfg, numpy_capture(cfg))
    lo, hi = wilson_interval(out["bit_errors"], out["bits_compared"], z=3.29)
    assert lo <= out["ber_theory"] <= hi, (out["ber"], out["ber_theory"])
