"""
REAL GNU Radio flowgraph execution.

Category: GNU Radio execution. Every test here runs src/gnuradio_phy/flowgraph.py in
GNU Radio. Without an importable GNU Radio the whole module is SKIPPED with the
import error as the reason; nothing is substituted. A skip here is reported as
NOT RUN, never as a pass.
"""

import math

import numpy as np
import pytest

from src.gnuradio_phy.availability import gnuradio_available, unavailable_reason

pytestmark = pytest.mark.skipif(not gnuradio_available(), reason=f"GNU Radio NOT RUN: {unavailable_reason()}")

from src.gnuradio_phy import PROVENANCE_GNURADIO, GRPhyConfig, load_and_validate_gnuradio  # noqa: E402
from src.gnuradio_phy.closed_loop import EpisodeCondition, run_closed_loop  # noqa: E402
from src.gnuradio_phy.receiver import wilson_interval  # noqa: E402
from src.gnuradio_phy.runner import decide_on_export, run_and_export, run_gnuradio  # noqa: E402


@pytest.mark.parametrize("mod", ["BPSK", "QPSK", "OFDM-QPSK"])
def test_flowgraph_runs_and_self_checks(mod):
    d = run_gnuradio(GRPhyConfig(modulation=mod, snr_db=12.0, n_symbols=2048))
    assert d["simulator"] == "GNU Radio" and d["gnuradio_version"].startswith(("3.", "v3."))
    assert d["timing_ok"] and d["gain_capture_ok"]
    assert d["measured_snr_db"] == pytest.approx(12.0, abs=0.4)


@pytest.mark.parametrize("mod,snrs", [("BPSK", (0.0, 4.0, 7.0)), ("QPSK", (3.0, 7.0, 10.0)),
                                      ("OFDM-QPSK", (3.0, 7.0, 10.0))])
def test_awgn_ber_matches_theory(mod, snrs):
    """Measured BER inside the 99.9 % Wilson interval around theory, widened by 10 %
    relative for RRC truncation ISI (span 11 symbols, rolloff 0.35)."""
    for snr in snrs:
        d = run_gnuradio(GRPhyConfig(modulation=mod, snr_db=snr, n_symbols=65536, seed=11))
        lo, hi = wilson_interval(int(d["bit_errors"]), int(d["bits_compared"]), z=3.29)
        th = d["ber_theory"]
        assert lo * 0.9 <= th <= hi * 1.1, (mod, snr, d["ber"], th)


def test_jammer_reduces_effective_sinr():
    d = run_gnuradio(GRPhyConfig(modulation="QPSK", snr_db=12.0, interference_power=0.1, n_symbols=65536))
    lo, hi = wilson_interval(int(d["bit_errors"]), int(d["bits_compared"]), z=3.29)
    assert lo * 0.9 <= d["ber_theory"] <= hi * 1.1
    assert d["measured_interference_power"] == pytest.approx(0.1, rel=0.05)


def test_same_seed_reproduces_and_different_seed_does_not():
    a = run_gnuradio(GRPhyConfig(seed=21, n_symbols=4096))
    b = run_gnuradio(GRPhyConfig(seed=21, n_symbols=4096))
    c = run_gnuradio(GRPhyConfig(seed=22, n_symbols=4096))
    assert np.array_equal(a["iq_samples"], b["iq_samples"])
    na, nc = a["noise_iq"], c["noise_iq"]
    corr = abs(np.vdot(na, nc)) / math.sqrt(np.vdot(na, na).real * np.vdot(nc, nc).real)
    assert corr < 5 / math.sqrt(na.size)


@pytest.mark.parametrize("chan", ["RAYLEIGH", "RICIAN"])
def test_block_and_time_varying_fading(chan):
    blk = run_gnuradio(GRPhyConfig(channel=chan, fading_mode="block", snr_db=20.0))
    assert np.ptp(np.abs(blk["channel_gain_iq"])) == 0.0
    tv = run_gnuradio(GRPhyConfig(channel=chan, fading_mode="time_varying", doppler_fdts=1e-3, snr_db=20.0))
    assert tv["gain_capture_ok"] and np.std(np.abs(tv["channel_gain_iq"])) > 0.01


def test_export_validates_as_gnuradio_and_reaches_acwra(tmp_path):
    led = str(tmp_path / "ledger.jsonl")
    path = run_and_export(GRPhyConfig(modulation="QPSK", snr_db=10.0), str(tmp_path), ledger_path=led)
    meas, rep = load_and_validate_gnuradio(path, require_gnuradio=True, ledger_path=led)
    assert rep.facts["provenance"] == PROVENANCE_GNURADIO
    from src.gnuradio_phy.export import load_export
    res = decide_on_export(load_export(path), require_gnuradio=True, ledger_path=led)
    assert res.decision.selected_strategy and res.validation.facts["provenance"] == PROVENANCE_GNURADIO


def test_closed_loop_on_gnuradio():
    rows = run_closed_loop([EpisodeCondition(14.0), EpisodeCondition(2.0, 0.2), EpisodeCondition(2.0, 0.2)],
                           "acwra", seed=1, base=GRPhyConfig(n_symbols=2048))
    # in-memory episodes: proven by the in-process run record, not by the label
    assert {r["provenance"] for r in rows} == {PROVENANCE_GNURADIO}
    assert rows[1]["modulation_applied"] == rows[0]["next_modulation"]


def test_deep_fade_episode_from_campaign_validates():
    """Regression: grcl1 aborted on this exact run (|h| = 0.021). It must validate, with the
    uninformative timing check skipped and BER ~ 0.5 reported as measured."""
    from src.gnuradio_phy import validate_gnuradio_dict
    d = run_gnuradio(GRPhyConfig(modulation="BPSK", snr_db=8.0, interference_power=0.2, channel="RAYLEIGH",
                                 fading_mode="block", seed=17001002))
    rep = validate_gnuradio_dict(d, ledger_path=None)
    assert rep.ok, rep.errors
    assert not d["timing_resolvable"] and rep.checks["gr_timing_ok"] == "SKIP"
    assert d["ber"] > 0.4
