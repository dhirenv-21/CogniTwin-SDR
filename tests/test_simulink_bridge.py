"""
Unit tests for MATLAB/Simulink Physical Layer Ingest Bridge.
Runnable in pure Python environments without requiring MATLAB installation.
"""

import pytest
import numpy as np
import scipy.io as sio

from src.simulink_bridge.protocol import SimulinkMeasurement
from src.simulink_bridge.receiver import SimulinkReceiver
from src.agents.spectrum_agent import SpectrumAgent
from src.agents.messages import SpectrumIntelligenceResult
from src.ai.modulation_classifier.inference import analyze_iq
from src.ai.modulation_classifier.features import extract_features, FEATURE_NAMES


def test_simulink_measurement_dataclass_validation():
    """
    Verifies SimulinkMeasurement dataclass schema validation and complex float conversion.
    """
    iq = np.array([1.0 + 2.0j, 3.0 + 4.0j], dtype=np.complex128)
    meas = SimulinkMeasurement(
        iq_samples=iq,
        snr_db=15.5,
        ber=0.001,
        modulation="QPSK",
        interference_power=0.1,
        channel_type="AWGN",
        timestamp=1.0,
    )

    assert len(meas.iq_samples) == 2
    assert meas.iq_samples.dtype == np.complex128
    assert meas.snr_db == 15.5
    assert meas.modulation == "QPSK"

    # Test empty vector error
    with pytest.raises(ValueError, match="cannot be empty"):
        SimulinkMeasurement(iq_samples=[], snr_db=10.0, ber=0.0, modulation="BPSK")


def test_simulink_receiver_load_mat(tmp_path):
    """
    Verifies SimulinkReceiver loads MAT-file exported from MATLAB.
    Uses scipy.io.savemat to create pure Python synthetic test file.
    """
    mat_file = tmp_path / "test_measurement.mat"

    # Generate physical QPSK baseband symbols
    bits = np.array([0, 1, 1, 1, 0, 0, 1, 0] * 64, dtype=np.int8)
    symbols_m = bits[::2] * 2 + bits[1::2]
    phases = 2 * np.pi * symbols_m / 4 + np.pi / 4
    iq_synth = np.cos(phases) + 1j * np.sin(phases)

    mat_dict = {
        "iq_samples": iq_synth,
        "snr_db": 12.0,
        "ber": 0.005,
        "modulation": "QPSK",
        "interference_power": 0.2,
        "channel_type": "AWGN",
        "timestamp": 2.5,
    }

    sio.savemat(str(mat_file), mat_dict)

    # Load via SimulinkReceiver
    meas = SimulinkReceiver.load_mat_measurement(str(mat_file))

    assert isinstance(meas, SimulinkMeasurement)
    assert len(meas.iq_samples) == 256
    assert np.isclose(meas.snr_db, 12.0)
    assert np.isclose(meas.ber, 0.005)
    assert meas.modulation == "QPSK"
    assert meas.channel_type == "AWGN"
    assert np.isclose(meas.timestamp, 2.5)


def test_adapter_preserves_complex_iq():
    """
    TEST 1: Verifies adapter preserves MATLAB complex I/Q precision and values.
    """
    raw_iq = np.array([0.7071 + 0.7071j, -0.7071 + 0.7071j, -0.7071 - 0.7071j], dtype=np.complex128)
    adapted = SimulinkReceiver.adapt_representation_for_classifier(raw_iq, target_length=3)

    assert adapted.dtype == np.complex128
    assert np.allclose(adapted[:3], raw_iq / np.sqrt(np.mean(np.abs(raw_iq)**2)))


def test_adapter_output_compatibility_with_analyze_iq():
    """
    TEST 2 & 4: Verifies adapter output matches analyze_iq() input specifications deterministically.
    """
    raw_iq = (np.random.randn(1000) + 1j * np.random.randn(1000)) * 5.0
    adapted = SimulinkReceiver.adapt_representation_for_classifier(raw_iq, target_length=512)

    assert len(adapted) == 512
    assert adapted.dtype == np.complex128
    assert np.isclose(np.mean(np.abs(adapted) ** 2), 1.0)

    # Must extract valid 17-element feature vector without error
    feats = extract_features(adapted, sample_rate=100000.0)
    assert len(feats) == len(FEATURE_NAMES)
    assert not np.isnan(feats).any()


def test_adapter_deterministic_normalization():
    """
    TEST 3: Verifies adapter power normalization is 100% deterministic.
    """
    raw_iq = np.array([2.0 + 0.0j, 0.0 + 2.0j, -2.0 + 0.0j, 0.0 - 2.0j], dtype=np.complex128)
    adapted1 = SimulinkReceiver.adapt_representation_for_classifier(raw_iq, target_length=512)
    adapted2 = SimulinkReceiver.adapt_representation_for_classifier(raw_iq, target_length=512)

    assert np.array_equal(adapted1, adapted2)
    assert np.isclose(np.mean(np.abs(adapted1) ** 2), 1.0)


def test_simulink_spectrum_agent_ingestion(tmp_path):
    """
    TEST 5: Verifies end-to-end ingestion of Simulink MAT measurement into SpectrumAgent without classifier modification.
    """
    mat_file = tmp_path / "test_agent_ingest.mat"

    # Generate physical QPSK baseband symbols matching Task 5 dataset
    rng = np.random.default_rng(123)
    symbols_m = rng.integers(0, 4, size=32)
    phases = 2 * np.pi * symbols_m / 4 + np.pi / 4
    baseband_syms = np.cos(phases) + 1j * np.sin(phases)
    iq_synth = np.tile(baseband_syms, 16)

    sio.savemat(
        str(mat_file),
        {
            "iq_samples": iq_synth,
            "snr_db": 20.0,
            "ber": 0.0,
            "modulation": "QPSK",
            "interference_power": 0.0,
            "channel_type": "AWGN",
            "timestamp": 1.0,
        },
    )

    meas = SimulinkReceiver.load_mat_measurement(str(mat_file))
    iq_samples, t_curr, interf_pwr = SimulinkReceiver.convert_for_spectrum_agent(meas)

    agent = SpectrumAgent(sample_rate=100000.0)
    result = agent.process(iq_samples=iq_samples, timestamp_s=t_curr, env_interference_power=interf_pwr)

    assert isinstance(result, SpectrumIntelligenceResult)
    assert result.timestamp_s == 1.0
    assert result.modulation == "QPSK"
    assert result.classifier_confidence >= 0.90
