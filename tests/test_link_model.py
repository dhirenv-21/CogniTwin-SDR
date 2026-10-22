"""
Link abstraction (src/virtual_rf/link_model.py): analytical values, Monte-Carlo
agreement, regimes, extremes. Pure Python; these validate the virtual-RF model only.
"""

import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.virtual_rf import link_model as lm  # noqa: E402
from src.virtual_rf.environment import VirtualRFEnvironment  # noqa: E402
from src.virtual_rf.scenario import ScenarioEngine  # noqa: E402


def q(x):
    return 0.5 * math.erfc(x / math.sqrt(2))


def _mc_avg(c, gamma, g):
    return float(np.mean([q(math.sqrt(c * gamma * x)) for x in g]))


@pytest.mark.parametrize("snr_db,jam", [(10.0, 0.0), (10.0, 0.1), (3.0, 0.5), (20.0, 1.0)])
def test_awgn_sinr_and_ber_are_analytical(snr_db, jam):
    sinr = 1.0 / (10 ** (-snr_db / 10) + jam)
    for mod, c in (("BPSK", 2.0), ("QPSK", 1.0), ("OFDM-QPSK", 1.0)):
        ber, pl, _, tput, sinr_db = lm.link_metrics(mod, snr_db, "awgn", jam)
        assert sinr_db == pytest.approx(10 * math.log10(sinr))
        assert ber == pytest.approx(q(math.sqrt(c * sinr)))
        assert pl == pytest.approx(1 - (1 - ber) ** 256)
        assert tput == pytest.approx((1 - pl) * lm.bits_per_symbol(mod) * 1e5)


@pytest.mark.parametrize("gamma_db", [0.0, 5.0, 10.0, 20.0, 30.0])
def test_rayleigh_closed_form_matches_numerical_integration(gamma_db):
    """Deterministic reference: the closed form against quadrature over the hypoexponential pdf."""
    from scipy import integrate
    gamma = 10 ** (gamma_db / 10)
    for mod, c in (("BPSK", 2.0), ("QPSK", 1.0)):
        ref, _ = integrate.quad(lambda x: q(math.sqrt(c * gamma * x)) * (math.exp(-x / 0.8) - math.exp(-x / 0.2)) / 0.6,
                                0, 80, limit=400, points=[1e-3, 1e-2, 1e-1])
        assert lm.ber_expected(mod, gamma, "rayleigh") == pytest.approx(ref, rel=1e-3)


@pytest.mark.parametrize("gamma_db", [0.0, 5.0, 10.0])
def test_rayleigh_expected_ber_matches_monte_carlo(gamma_db):
    """Monte Carlo only where it converges (at high SNR rare deep fades dominate the average)."""
    rng = np.random.default_rng(1)
    gamma = 10 ** (gamma_db / 10)
    g = 0.8 * rng.exponential(1.0, 100000) + 0.2 * rng.exponential(1.0, 100000)
    for mod, c in (("BPSK", 2.0), ("QPSK", 1.0)):
        assert lm.ber_expected(mod, gamma, "rayleigh") == pytest.approx(_mc_avg(c, gamma, g), rel=0.03)


def test_single_path_rayleigh_closed_form_is_the_textbook_one():
    for gdb in (0, 10, 20):
        g = 10 ** (gdb / 10)
        assert lm._avg_q_exponential(2.0, g, 1.0) == pytest.approx(0.5 * (1 - math.sqrt(g / (1 + g))))


@pytest.mark.parametrize("gamma_db", [0.0, 6.0, 12.0])
def test_rician_expected_ber_matches_monte_carlo(gamma_db):
    rng = np.random.default_rng(2)
    n = 100000
    h = (np.sqrt(2.0) + (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2)) / np.sqrt(3)
    gamma = 10 ** (gamma_db / 10)
    assert lm.ber_expected("QPSK", gamma, "rician") == pytest.approx(_mc_avg(1.0, gamma, np.abs(h) ** 2), rel=0.03)


def test_environment_fades_have_unit_mean_and_the_modelled_distribution():
    """The gains env.step() realises are the ones the expectation integrates over."""
    for ch, var in (("rayleigh", 0.8 ** 2 + 0.2 ** 2), ("rician", (1 + 2 * 2.0) / (1 + 2.0) ** 2)):
        env = VirtualRFEnvironment(scenario=ScenarioEngine(
            {"keyframes": [{"time_s": 0.0, "snr_db": 10.0, "channel_type": ch}]}), seed=5)
        gs = []
        for _ in range(2000):
            env.step(0.1)
            gs.append(env.last_channel_gain)
        gs = np.array(gs)
        assert gs.mean() == pytest.approx(1.0, abs=0.06)
        assert gs.var() == pytest.approx(var, rel=0.15)


def test_realised_steps_average_to_the_expected_ber():
    env = VirtualRFEnvironment(scenario=ScenarioEngine(
        {"keyframes": [{"time_s": 0.0, "snr_db": 8.0, "channel_type": "rayleigh", "modulation": "BPSK"}]}), seed=6)
    bers = [env.step(0.1)[0].ber for _ in range(2000)]
    assert np.mean(bers) == pytest.approx(lm.ber_expected("BPSK", 10 ** 0.8, "rayleigh"), rel=0.12)


def test_more_interference_never_helps():
    for ch in ("awgn", "rayleigh", "rician"):
        for mod in ("BPSK", "QPSK"):
            gp = [lm.link_metrics(mod, 12.0, ch, j)[3] for j in (0, 0.01, 0.03, 0.1, 0.3, 1, 3)]
            assert all(b <= a + 1e-9 for a, b in zip(gp, gp[1:]))


def test_regimes_recoverable_and_overwhelmed_are_both_present():
    """
    Clean link: full rate. J = 0.1 (SINR 9.4 dB): QPSK still delivers more than BPSK.
    J = 0.3 (SINR 5.0 dB): QPSK has collapsed and only BPSK gets packets through.
    J = 1 (SINR ~0 dB): everything lost.
    """
    assert lm.link_metrics("QPSK", 18.0, "awgn", 0.0)[3] == pytest.approx(2e5, rel=1e-6)
    assert lm.link_metrics("QPSK", 18.0, "awgn", 0.1)[3] > lm.link_metrics("BPSK", 18.0, "awgn", 0.1)[3]
    b = lm.link_metrics("BPSK", 18.0, "awgn", 0.3)[3]
    qp = lm.link_metrics("QPSK", 18.0, "awgn", 0.3)[3]
    assert b > 1e4 and qp < 1e-3 * b                  # QPSK ~11 b/s vs BPSK ~22 kb/s
    for mod in ("BPSK", "QPSK", "OFDM-QPSK"):
        assert lm.link_metrics(mod, 18.0, "awgn", 1.0)[3] < 1.0


@pytest.mark.parametrize("args", [("QPSK", -50.0, "awgn", 0.0), ("BPSK", 120.0, "rician", 0.0),
                                  ("QPSK", 10.0, "awgn", 1e6), ("BPSK", 10.0, "rayleigh", 0.0, 0.0),
                                  ("QPSK", 300.0, "rayleigh", 0.0)])
def test_extremes_are_finite_and_bounded(args):
    ber, pl, lat, tput, _ = lm.link_metrics(*args)
    assert 0.0 <= ber <= 0.5 and 0.0 <= pl <= 1.0 and math.isfinite(lat) and 0.0 <= tput <= 2e5


def test_sandbox_uses_expectation_and_step_uses_realisation():
    env = VirtualRFEnvironment()
    exp = env._compute_congestion_metrics("QPSK", 10.0, "rayleigh", 0.0)[0]
    assert exp == pytest.approx(lm.ber_expected("QPSK", 10.0, "rayleigh"))
    real = env._compute_congestion_metrics("QPSK", 10.0, "rayleigh", 0.0, channel_gain=0.1)[0]
    assert real == pytest.approx(q(1.0))
