"""
Episode-based closed loop: actuation timing, pairing and provenance bookkeeping.

Category: fixture integration (no GNU Radio needed). The PHY here is the NumPy
stand-in (tests/gr_test_helpers.labelled_fixture); every row it produces is
recorded as provenance 'python_fixture', which is what these tests check. They
test the LOOP, not the physical layer.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gr_test_helpers import labelled_fixture  # noqa: E402
from src.gnuradio_phy import GNURadioUnavailable, GRPhyConfig, gnuradio_available  # noqa: E402
from src.gnuradio_phy.closed_loop import (  # noqa: E402
    POLICIES, EpisodeCondition, episode_seed, run_closed_loop, summarise_episode,
)
from src.gnuradio_phy.export import content_sha256  # noqa: E402
from src.simulink_bridge.validation import MeasurementValidationError  # noqa: E402

BASE = GRPhyConfig(n_symbols=1024)
SCHED = [EpisodeCondition(14.0), EpisodeCondition(14.0), EpisodeCondition(2.0, 0.2),
         EpisodeCondition(2.0, 0.2), EpisodeCondition(14.0)]


class RecordingPHY:
    """Wraps the stand-in and records each configuration at the moment it runs."""

    def __init__(self):
        self.configs = []

    def __call__(self, cfg):
        self.configs.append(cfg)
        return labelled_fixture(cfg)


@pytest.mark.parametrize("policy", ["acwra", "sinr_threshold"])
def test_decision_applies_to_the_next_episode_only(policy):
    phy = RecordingPHY()
    rows = run_closed_loop(SCHED, policy, seed=2, base=BASE, phy=phy)
    assert rows[0]["decision_from_episode"] is None
    for e in range(1, len(rows)):
        assert rows[e]["decision_from_episode"] == e - 1
        assert rows[e]["modulation_applied"] == rows[e - 1]["next_modulation"]
        assert phy.configs[e].modulation == rows[e - 1]["next_modulation"]
    # the configuration that ran is the one recorded (no retroactive change)
    assert [c.modulation for c in phy.configs] == [r["modulation_applied"] for r in rows]


def test_sinr_rule_switches_on_measured_conditions():
    rows = run_closed_loop(SCHED, "sinr_threshold", seed=2, base=BASE, phy=labelled_fixture)
    assert [r["next_modulation"] for r in rows] == ["QPSK", "QPSK", "BPSK", "BPSK", "QPSK"]


def test_no_adaptation_decides_but_never_actuates():
    rows = run_closed_loop(SCHED, "no_adaptation", seed=2, base=BASE, phy=labelled_fixture)
    assert {r["modulation_applied"] for r in rows} == {"QPSK"}
    assert all(r["acwra_modulation"] for r in rows)


def test_policies_are_paired_on_seeds_and_conditions():
    recs = {}
    for pol in ("acwra", "fixed_BPSK", "fixed_OFDM-QPSK"):
        phy = RecordingPHY()
        run_closed_loop(SCHED, pol, seed=4, base=BASE, phy=phy)
        recs[pol] = [(c.seed, c.snr_db, c.interference_power, c.channel) for c in phy.configs]
    assert recs["acwra"] == recs["fixed_BPSK"] == recs["fixed_OFDM-QPSK"]
    assert [r[0] for r in recs["acwra"]] == [episode_seed(4, e) for e in range(len(SCHED))]


def test_provenance_of_stand_in_rows_is_fixture_never_gnuradio():
    for pol in POLICIES:
        rows = run_closed_loop(SCHED[:2], pol, seed=1, base=BASE, phy=labelled_fixture)
        assert {r["provenance"] for r in rows} == {"python_fixture"}, pol
        assert summarise_episode(rows)["provenance"] == "python_fixture"


def test_invalid_episode_stops_the_loop():
    def broken(cfg):
        d = labelled_fixture(cfg)
        d["iq_samples"] = d["iq_samples"].copy()
        d["iq_samples"][5] = np.nan
        d["content_sha256"] = content_sha256(d)
        return d

    for pol in ("acwra", "fixed_QPSK"):
        with pytest.raises(MeasurementValidationError):
            run_closed_loop(SCHED, pol, seed=1, base=BASE, phy=broken)


def test_require_gnuradio_rejects_stand_in():
    with pytest.raises(MeasurementValidationError, match="not a GNU Radio export"):
        run_closed_loop(SCHED[:1], "fixed_QPSK", seed=1, base=BASE, phy=labelled_fixture, require_gnuradio=True)


def test_summary_metrics():
    rows = run_closed_loop(SCHED, "fixed_BPSK", seed=1, base=BASE, phy=labelled_fixture)
    s = summarise_episode(rows)
    assert s["switches"] == 0 and s["episodes"] == 5
    assert s["goodput_bps"] == pytest.approx(np.mean([r["goodput_bps"] for r in rows]))
    assert s["ber"] == pytest.approx(sum(r["ber"] * r["bits"] for r in rows) / sum(r["bits"] for r in rows))


@pytest.mark.skipif(gnuradio_available(), reason="GNU Radio is installed: the default PHY would really run")
def test_default_phy_without_gnuradio_raises_not_substitutes():
    with pytest.raises(GNURadioUnavailable, match="GNU Radio is not importable"):
        run_closed_loop(SCHED[:1], "fixed_QPSK", seed=1, base=BASE)
