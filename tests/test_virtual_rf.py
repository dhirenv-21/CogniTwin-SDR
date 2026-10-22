"""
Unit tests for Virtual RF Environment package.
"""

import os
import numpy as np
import pytest

from src.virtual_rf.state import EnvironmentState
from src.virtual_rf.scenario import ScenarioEngine
from src.virtual_rf.interference import InterferenceGenerator
from src.virtual_rf.environment import VirtualRFEnvironment


def test_environment_discrete_time_step():
    """
    Verifies discrete-time clock advancement and sample buffer length.
    """
    env = VirtualRFEnvironment(sample_rate=100000.0, seed=42)

    assert env.current_time_s == 0.0
    state, iq = env.step(duration_seconds=0.1)

    assert env.current_time_s == 0.1
    assert state.timestamp_s == 0.0  # State timestamp before step increment
    assert len(iq) == 10000  # 0.1s * 100,000 Hz = 10,000 samples
    assert np.iscomplexobj(iq)


def test_observe_state_and_iq():
    """
    Verifies observe_state() and observe_iq() APIs.
    """
    env = VirtualRFEnvironment(sample_rate=100000.0, seed=42)
    env.step(duration_seconds=0.05)

    state = env.observe_state()
    iq = env.observe_iq()

    assert isinstance(state, EnvironmentState)
    assert len(iq) == 5000
    assert state.snr_db == 20.0


def test_counterfactual_simulate_api():
    """
    Verifies pure counterfactual simulate API does not advance environment time.
    """
    env = VirtualRFEnvironment(sample_rate=100000.0, seed=42)
    initial_time = env.current_time_s

    current_state = env.observe_state()
    pred_state = env.simulate(current_state, strategy={"modulation": "BPSK", "snr_db": 10.0})

    assert env.current_time_s == initial_time  # Clock unchanged
    assert pred_state.modulation == "BPSK"
    assert pred_state.snr_db == 10.0
    assert pred_state.ber >= current_state.ber  # Lower SNR yields higher BER


def test_interference_generation():
    """
    Verifies narrowband, broadband, and swept jamming signal generators.
    """
    gen = InterferenceGenerator(sample_rate=100000.0, seed=42)

    nb = gen.generate_narrowband_tone(freq_offset_hz=1000.0, power=2.0, n_samples=512)
    assert len(nb) == 512
    assert np.isclose(np.mean(np.abs(nb) ** 2), 2.0, rtol=1e-2)

    bb = gen.generate_broadband_noise(power=1.5, n_samples=512)
    assert len(bb) == 512
    assert np.isclose(np.mean(np.abs(bb) ** 2), 1.5, rtol=0.2)

    sw = gen.generate_swept_jamming(start_freq_hz=-5000, end_freq_hz=5000, power=3.0, n_samples=512)
    assert len(sw) == 512
    assert np.isclose(np.mean(np.abs(sw) ** 2), 3.0, rtol=1e-2)


def test_scenario_loading():
    """
    Verifies scenario keyframe loading from JSON file.
    """
    json_path = os.path.join("config", "scenarios", "broadband_jamming.json")
    engine = ScenarioEngine.load_from_file(json_path)

    assert engine.name == "Broadband Jamming Scenario"
    kf0 = engine.get_keyframe_at(0.5)
    kf1 = engine.get_keyframe_at(1.5)
    kf2 = engine.get_keyframe_at(2.5)

    assert kf0["snr_db"] == 20.0
    assert kf1["snr_db"] == 10.0
    assert kf2["snr_db"] == 0.0
