"""
Digital Twin validation: input checking, ordering, horizons, causality, and the
forecast-evaluation harness. Synthetic virtual-RF data (Python only).

Defects pinned here:
  * NaN SNR / Inf BER flowed through the predictor and came out of the Prediction
    Agent as risk_score=NaN, risk_level='CRITICAL', status='SUCCESS';
  * the forecast time was t[-1] + h (last APPENDED state), not the newest one;
  * keyframes landed one step late when the float clock read 0.9999999999999999.
"""

import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "experiments")):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.agents.prediction_agent import PredictionAgent  # noqa: E402
from src.digital_twin.predictor import TrendPredictor  # noqa: E402
from src.digital_twin.state import DigitalTwinState  # noqa: E402
from src.digital_twin.twin import DigitalTwin  # noqa: E402
from src.virtual_rf.environment import VirtualRFEnvironment  # noqa: E402
from src.virtual_rf.scenario import ScenarioEngine  # noqa: E402
from src.virtual_rf.state import EnvironmentState  # noqa: E402

import digital_twin_forecast_eval as fev  # noqa: E402


def _feed(twin, points):
    for t, snr in points:
        twin.update(EnvironmentState(timestamp_s=t, snr_db=snr, ber=0.0))
    return twin


# ================================================================ input validation
@pytest.mark.parametrize("field,value", [
    ("snr_db", math.nan), ("snr_db", math.inf), ("ber", math.inf), ("ber", math.nan),
    ("interference_power", math.nan), ("timestamp_s", math.nan), ("throughput_bps", -math.inf),
])
def test_twin_rejects_non_finite_inputs(field, value):
    twin = DigitalTwin()
    s = EnvironmentState(timestamp_s=0.0, snr_db=10.0, ber=0.01)
    setattr(s, field, value)
    with pytest.raises(ValueError, match=field):
        twin.update(s)
    assert len(twin.history) == 0, "a rejected observation must not enter the history"


def test_invalid_input_can_no_longer_become_a_critical_alarm():
    twin = _feed(DigitalTwin(), [(0.1 * i, 20.0) for i in range(5)])
    with pytest.raises(ValueError):
        twin.update(EnvironmentState(timestamp_s=0.5, snr_db=math.nan, ber=0.0))
    r = PredictionAgent().process(twin, 0.1)
    assert r.prediction_status == "SUCCESS" and math.isfinite(r.risk_score)
    assert r.risk_level == "LOW"


# ================================================================ ordering / horizons
def test_forecast_time_is_measured_from_the_newest_observation():
    twin = _feed(DigitalTwin(), [(0.0, 20), (0.1, 19), (0.2, 18), (0.4, 16), (0.3, 17)])
    pred = twin.predict_next(0.1)
    assert pred["predicted_timestamp_s"] == pytest.approx(0.5)
    assert pred["next_snr_db"] == pytest.approx(15.0)


@pytest.mark.parametrize("h", [0.1, 0.2, 0.5, 1.0])
def test_linear_trend_is_exact_at_every_horizon(h):
    twin = _feed(DigitalTwin(), [(0.1 * i, 25.0 - 6.0 * 0.1 * i) for i in range(8)])
    pred = twin.predict_next(h)
    t_next = 0.7 + h
    assert pred["predicted_timestamp_s"] == pytest.approx(t_next)
    assert pred["next_snr_db"] == pytest.approx(25.0 - 6.0 * t_next)


def test_forecast_uses_only_the_last_history_window():
    """An old outlier outside the 5-state window must not affect the forecast."""
    pts = [(0.0, -50.0)] + [(0.1 * i, 20.0) for i in range(1, 7)]
    assert _feed(DigitalTwin(), pts).predict_next(0.1)["next_snr_db"] == pytest.approx(20.0)


def test_insufficient_history_is_explicit():
    twin = _feed(DigitalTwin(), [(0.1 * i, 20.0) for i in range(4)])
    assert twin.predict_next(0.1)["prediction_status"] == "INSUFFICIENT_HISTORY"
    r = PredictionAgent().process(twin, 0.1)
    assert r.prediction_status == "INSUFFICIENT_HISTORY" and r.risk_score == 0.0
    # a twin configured for a shorter window predicts sooner
    short = _feed(DigitalTwin(history_window=3), [(0.1 * i, 20.0 - i) for i in range(3)])
    assert short.predict_next(0.1)["prediction_status"] == "SUCCESS"


def test_identical_timestamps_fall_back_to_the_latest_values():
    p = TrendPredictor(history_window=3)
    hist = [DigitalTwinState(timestamp_s=1.0, snr_db=v) for v in (10.0, 12.0, 14.0)]
    assert p.predict_next_state(hist, 0.1)["next_snr_db"] == 14.0


def test_history_is_bounded_and_chronological():
    env = VirtualRFEnvironment(seed=1)
    twin = DigitalTwin(environment=env, max_history_len=7)
    for _ in range(20):
        twin.update(env.step(0.1)[0])
    ts = [s.timestamp_s for s in twin.history.get_history()]
    assert len(ts) == 7 and all(b > a for a, b in zip(ts, ts[1:]))


# ================================================================ causality
def test_forecasts_are_causal():
    """A forecast made at t equals one made by a fresh twin that saw only states <= t."""
    traj = fev.true_trajectory(fev.ramp_scenario(), seed=3)
    live = DigitalTwin()
    for k, (t, snr, ber, jam, chan, mod) in enumerate(traj[:20]):
        live.update(EnvironmentState(timestamp_s=t, snr_db=snr, ber=ber, interference_power=jam,
                                     channel_type=chan, modulation=mod))
        if k < 5:
            continue
        fresh = DigitalTwin()
        for (t2, s2, b2, j2, c2, m2) in traj[:k + 1]:
            fresh.update(EnvironmentState(timestamp_s=t2, snr_db=s2, ber=b2, interference_power=j2,
                                          channel_type=c2, modulation=m2))
        assert live.predict_next(0.2) == fresh.predict_next(0.2)


def test_counterfactuals_do_not_touch_history_or_state():
    env = VirtualRFEnvironment(seed=2)
    twin = DigitalTwin(environment=env)
    for _ in range(6):
        twin.update(env.step(0.1)[0])
    before = (len(twin.history), twin.state.to_dict(), env.current_time_s)
    twin.evaluate_counterfactuals(["Keep Current", "BPSK", "QPSK", "OFDM-QPSK"])
    assert (len(twin.history), twin.state.to_dict(), env.current_time_s) == before


# ================================================================ environment timing
def test_keyframes_apply_on_time_despite_float_clock_drift():
    env = VirtualRFEnvironment(scenario=ScenarioEngine.load_from_file(
        os.path.join(ROOT, "config", "scenarios", "awgn_degradation.json")))
    snrs = [env.step(0.1)[0].snr_db for _ in range(22)]
    assert snrs[9] == 20.0 and snrs[10] == 10.0       # clock 0.9999999999999999 -> 1.0 s keyframe
    assert snrs[19] == 10.0 and snrs[20] == 0.0


# ================================================================ evaluation harness
def test_evaluation_harness_scores_against_the_future_truth():
    traj = fev.true_trajectory(fev.ramp_scenario(), seed=1)
    for h in (1, 2, 5):
        et, ep, ins = fev.evaluate(traj, h, 0.0, np.random.default_rng(0))
        assert ins == 4                                 # first 4 steps: history < 5
        assert np.max(et) < 1e-9                        # exact trend on a ramp
        assert np.allclose(ep, 0.6 * h)                 # persistence lags by slope*h*dt


def test_persistence_error_on_a_step_is_the_jump():
    cfg = {"duration_seconds": 2.0, "keyframes": [
        {"time_s": 0.0, "snr_db": 20.0}, {"time_s": 1.0, "snr_db": 10.0}]}
    traj = fev.true_trajectory(cfg, seed=0)
    _, ep, _ = fev.evaluate(traj, 1, 0.0, np.random.default_rng(0))
    assert sorted(np.round(ep, 9))[-1] == 10.0 and np.count_nonzero(ep) == 1
