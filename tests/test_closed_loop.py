"""
Closed-loop actuation tests (virtual-RF, Python only).

VirtualRFEnvironment.modulation_override is the only change to the environment for
closed-loop operation; by default (None) the scenario controls the modulation as
before.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "experiments")):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.virtual_rf.environment import VirtualRFEnvironment  # noqa: E402
from src.virtual_rf.scenario import ScenarioEngine  # noqa: E402

import closed_loop_evaluation as cle  # noqa: E402


def _cfg(name):
    with open(os.path.join(ROOT, "config", "scenarios", f"{name}.json")) as fh:
        c = json.load(fh)
    c["name"] = name
    return c


def test_default_keeps_the_scenario_in_control():
    env = VirtualRFEnvironment(scenario=ScenarioEngine(_cfg("clear_channel")))
    assert env.modulation_override is None
    assert env.step(0.1)[0].modulation == "QPSK"


def test_override_changes_the_transmitted_modulation_and_its_outcome():
    a = VirtualRFEnvironment(scenario=ScenarioEngine(_cfg("multipath_fading")), seed=4)
    b = VirtualRFEnvironment(scenario=ScenarioEngine(_cfg("multipath_fading")), seed=4)
    b.modulation_override = "BPSK"
    sa, sb = a.step(0.1)[0], b.step(0.1)[0]
    assert (sa.modulation, sb.modulation) == ("QPSK", "BPSK")
    assert sb.throughput_bps == pytest.approx(sa.throughput_bps / 2)    # same clean link, 1 vs 2 bits/symbol


@pytest.mark.parametrize("policy", ["acwra", "snr_threshold", "fixed_BPSK"])
def test_each_decision_is_applied_on_the_next_step(policy):
    rows = cle.run_episode(_cfg("awgn_degradation"), policy, seed=1)
    assert len(rows) == 30
    for prev, cur in zip(rows, rows[1:]):
        assert cur["modulation_applied"] == prev["next_modulation"]


def test_oracle_is_applied_without_delay_and_has_no_regret():
    rows = cle.run_episode(_cfg("multipath_fading"), "oracle", seed=1)
    assert all(r["modulation_applied"] in r["oracle_set"].split("|") for r in rows)
    assert max(r["goodput_regret_bps"] for r in rows) <= 1.0
    assert min(r["goodput_regret_bps"] for r in rows) >= -1e-6     # nothing beats the oracle


def test_jamming_regimes_recoverable_then_overwhelmed():
    """
    broadband_jamming: J = 0.5 at SNR 10 dB (SINR 2.2 dB) leaves BPSK a unique,
    small advantage; J = 3 at SNR 0 dB (SINR -6 dB) overwhelms every modulation.
    (The old model, BER + 0.15 J, tied all 20 jammed steps at zero goodput.)
    """
    rows = cle.run_episode(_cfg("broadband_jamming"), "fixed_QPSK", seed=1)
    mid = [r for r in rows if r["interference_power"] == 0.5]
    hard = [r for r in rows if r["interference_power"] == 3.0]
    assert mid and all(r["oracle_set"] == "BPSK" for r in mid)
    assert hard and all(r["oracle_set"] == "BPSK|QPSK|OFDM-QPSK" and r["goodput_bps"] < 1.0 for r in hard)


def test_oracle_peek_equals_the_realised_fade():
    for ch in ("rayleigh", "rician"):
        cfg = {"duration_seconds": 1.0, "keyframes": [{"time_s": 0.0, "snr_db": 10.0, "channel_type": ch}]}
        env = VirtualRFEnvironment(scenario=ScenarioEngine(cfg), seed=9)
        for _ in range(10):
            g = cle.peek_step_gain(env, ch)
            env.step(0.1)
            assert g == pytest.approx(env.last_channel_gain, abs=1e-12)


def test_agent_step_without_ablation_equals_the_orchestrator():
    from src.agents.orchestrator import MultiAgentOrchestrator
    cfg = _cfg("dynamic_combat_environment")
    a = MultiAgentOrchestrator(environment=VirtualRFEnvironment(scenario=ScenarioEngine(cfg), seed=3))
    b = MultiAgentOrchestrator(environment=VirtualRFEnvironment(scenario=ScenarioEngine(cfg), seed=3))
    for _ in range(12):
        sa, _, _ = a.step(duration_seconds=cle.DT)
        sb, _ = cle.agent_step(b, None)
        assert sa == sb


def test_ablation_hooks_change_only_their_component():
    from src.agents.orchestrator import MultiAgentOrchestrator
    orch = MultiAgentOrchestrator(environment=VirtualRFEnvironment(
        scenario=ScenarioEngine(_cfg("dynamic_combat_environment")), seed=3))
    snap, _ = cle.agent_step(orch, "no_confidence")
    assert snap.spectrum_result.classifier_confidence == 1.0
    snap, _ = cle.agent_step(orch, "all_candidates")
    assert snap.defense_candidates.candidate_strategies == cle.ALL_CANDIDATES
    snap, _ = cle.agent_step(orch, "no_prediction")
    assert snap.prediction_result.prediction_status == "DISABLED" and snap.prediction_result.risk_score == 0.0
    cle.agent_step(orch, "no_history")
    assert len(orch.digital_twin.history) == 1


def test_episodes_are_paired_across_policies():
    """Same seed -> same realised fades whatever the policy (the env RNG ignores the modulation)."""
    cfg = _cfg("multipath_fading")
    g1 = [r["channel_gain"] for r in cle.run_episode(cfg, "fixed_BPSK", seed=4)]
    g2 = [r["channel_gain"] for r in cle.run_episode(cfg, "acwra", seed=4)]
    assert g1 == g2


def test_paired_comparison_statistics():
    eps = [{"condition": c, "policy": p, "seed": s, "m": v}
           for c, base in (("c1", 1.0), ("c2", 2.0), ("c3", 3.0)) for s in (1, 2)
           for p, v in (("acwra", base + 0.5), ("b", base))]
    r = cle.paired_comparison(eps, "acwra", "b", "m", ["c1", "c2", "c3"])
    assert r["mean_diff"] == pytest.approx(0.5) and (r["wins"], r["ties"], r["losses"]) == (3, 0, 0)
    assert r["ci95_low"] == pytest.approx(0.5) and r["ci95_high"] == pytest.approx(0.5)


def test_recovery_counts_steps_until_the_oracle_set_is_reached():
    rows = [{"t_s": 0.1 * i, "modulation_applied": m, "oracle_set": "BPSK"}
            for i, m in enumerate(["QPSK", "QPSK", "BPSK", "BPSK"])]
    assert cle.recovery_steps(rows, [0.0]) == [2]
