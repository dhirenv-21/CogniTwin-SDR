"""
Simulink -> Bridge -> SpectrumAgent -> MultiAgentSnapshot -> ACWRA integration tests.

Task 11, Parts 9-G (I/Q validation), 9-H (data integrity) and 9-I (Python end-to-end).

These tests NEVER require MATLAB. They use fixture MAT files produced by
src/simulink_bridge/reference_phy.py, which is a Python mirror of the Simulink signal
chain and is always tagged source="python-fixture" so it can never be confused with a
real .slx export.
"""

import os

import numpy as np
import pytest
import scipy.io as sio

from src.acwra.decision import ACWRADecision
from src.agents.messages import (
    DefenseCandidate,
    MultiAgentSnapshot,
    PredictionResult,
    SpectrumIntelligenceResult,
)
from src.simulink_bridge.pipeline import SimulinkACWRAPipeline, matlab_channel_to_internal
from src.simulink_bridge.protocol import SimulinkMeasurement
from src.simulink_bridge.receiver import SimulinkReceiver
from src.simulink_bridge.reference_phy import (
    FIXTURE_SOURCE_TAG,
    generate_reference_measurement,
    write_reference_mat,
)
from src.simulink_bridge.validation import (
    MeasurementValidationError,
    flatten_matlab_iq,
    measure_iq_statistics,
    validate_mat_dict,
)


# --------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def qpsk_mat(tmp_path_factory):
    path = tmp_path_factory.mktemp("simulink") / "qpsk_case.mat"
    write_reference_mat(
        str(path), modulation="QPSK", snr_db=15.0, interference_power=0.1,
        channel_type="AWGN", n_samples=10000, sample_rate=100000.0, seed=1234,
    )
    return str(path)


@pytest.fixture(scope="module")
def jammed_mat(tmp_path_factory):
    path = tmp_path_factory.mktemp("simulink") / "jammed_case.mat"
    write_reference_mat(
        str(path), modulation="OFDM-QPSK", snr_db=3.0, interference_power=2.5,
        channel_type="Rayleigh", n_samples=10000, sample_rate=100000.0, seed=99,
    )
    return str(path)


# ----------------------------------------------------- H. data-integrity tests


def test_column_vector_accepted():
    iq = np.arange(8) + 1j * np.arange(8, 0, -1)
    out = flatten_matlab_iq(iq.reshape(-1, 1))
    assert out.shape == (8,)
    assert np.allclose(out, iq)


def test_row_vector_accepted():
    iq = np.arange(8) + 1j * np.arange(8, 0, -1)
    out = flatten_matlab_iq(iq.reshape(1, -1))
    assert out.shape == (8,)
    assert np.allclose(out, iq)


def test_real_iq_pair_matrix_accepted():
    iq = np.arange(6) + 1j * np.arange(6)[::-1]
    pair = np.column_stack([iq.real, iq.imag])
    out = flatten_matlab_iq(pair)
    assert np.allclose(out, iq)
    assert out.dtype == np.complex128


def test_imaginary_component_never_discarded():
    iq = np.array([0.7071 + 0.7071j, -0.7071 - 0.7071j], dtype=np.complex128)
    out = flatten_matlab_iq(iq.reshape(-1, 1))
    assert np.allclose(out.imag, iq.imag)
    assert np.any(np.abs(out.imag) > 0)


@pytest.mark.parametrize("n", [64, 100, 512, 1024, 10000])
def test_various_sample_lengths(n):
    iq = np.random.default_rng(n).normal(size=n) + 1j * np.random.default_rng(n + 1).normal(size=n)
    assert flatten_matlab_iq(iq.reshape(-1, 1)).size == n


def test_empty_iq_rejected():
    with pytest.raises(MeasurementValidationError):
        flatten_matlab_iq(np.array([], dtype=np.complex128))


def test_missing_required_fields_rejected():
    rep = validate_mat_dict({"iq_samples": np.ones(128, dtype=np.complex128)})
    assert not rep.ok
    assert any("missing required" in e for e in rep.errors)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nan_and_inf_in_iq_rejected(bad):
    iq = np.ones(256, dtype=np.complex128)
    iq[7] = bad
    rep = validate_mat_dict({"iq_samples": iq, "snr_db": 10.0, "modulation": "QPSK"})
    assert not rep.ok
    assert rep.checks["iq_finite_values"] == "FAIL"


def test_invalid_snr_rejected():
    iq = np.ones(256, dtype=np.complex128)
    rep = validate_mat_dict({"iq_samples": iq, "snr_db": np.nan, "modulation": "QPSK"})
    assert not rep.ok


def test_unknown_modulation_warns_but_does_not_crash():
    iq = np.ones(256, dtype=np.complex128)
    rep = validate_mat_dict({"iq_samples": iq, "snr_db": 10.0, "modulation": "WEIRD-MOD"})
    assert rep.checks["modulation_known"] == "WARN"
    assert rep.ok


def test_corrupt_mat_file_rejected(tmp_path):
    bad = tmp_path / "corrupt.mat"
    bad.write_bytes(b"definitely not a MAT file")
    with pytest.raises(MeasurementValidationError):
        SimulinkReceiver.load_and_validate(str(bad))


def test_missing_mat_file_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        SimulinkReceiver.load_and_validate(str(tmp_path / "nope.mat"))


def test_sample_count_mismatch_rejected(tmp_path):
    path = tmp_path / "short.mat"
    sio.savemat(str(path), {
        "iq_samples": np.ones((512, 1), dtype=np.complex128),
        "snr_db": 10.0, "ber": 0.0, "modulation": "QPSK",
        "interference_power": 0.0, "channel_type": "AWGN", "timestamp": 0.0,
        "sample_rate": 100000.0,
    })
    with pytest.raises(MeasurementValidationError):
        SimulinkReceiver.load_and_validate(str(path), expected_samples=10000)


def test_loader_does_not_fabricate_samples(tmp_path):
    """The bridge must return exactly what the MAT file contains."""
    iq = np.random.default_rng(5).normal(size=777) + 1j * np.random.default_rng(6).normal(size=777)
    path = tmp_path / "exact.mat"
    sio.savemat(str(path), {
        "iq_samples": iq.reshape(-1, 1), "snr_db": 12.0, "ber": 0.01,
        "modulation": "QPSK", "interference_power": 0.0, "channel_type": "AWGN",
        "timestamp": 0.0, "sample_rate": 100000.0,
    })
    meas, rep = SimulinkReceiver.load_and_validate(str(path))
    assert rep.ok
    assert meas.num_samples == 777
    assert np.allclose(meas.iq_samples, iq)


# ---------------------------------------------- backwards compatibility of API


def test_existing_receiver_api_unchanged(qpsk_mat):
    """load_mat_measurement() and convert_for_spectrum_agent() keep their contracts."""
    meas = SimulinkReceiver.load_mat_measurement(qpsk_mat)
    assert isinstance(meas, SimulinkMeasurement)
    iq, t, interf = SimulinkReceiver.convert_for_spectrum_agent(meas)
    assert iq.shape == (512,)
    assert iq.dtype == np.complex128
    assert np.isclose(np.mean(np.abs(iq) ** 2), 1.0)
    assert isinstance(t, float)
    assert interf == pytest.approx(0.1)


def test_measurement_optional_fields_default_safely():
    """A measurement built the old way must still work."""
    meas = SimulinkMeasurement(
        iq_samples=np.ones(16, dtype=np.complex128), snr_db=10.0, ber=0.0, modulation="BPSK"
    )
    assert meas.sample_rate == 0.0
    assert meas.time_vector is None
    assert meas.tx_iq is None
    assert meas.source == "unknown"
    assert meas.num_samples == 16
    assert meas.duration_s == 0.0


# --------------------------------------------------------- G. I/Q validation


def test_iq_integrity_of_reference_export(qpsk_mat):
    meas, rep = SimulinkReceiver.load_and_validate(qpsk_mat, expected_sample_rate=100000.0)
    iq = meas.iq_samples

    assert rep.ok, rep.errors
    assert iq.ndim == 1
    assert iq.dtype == np.complex128
    assert iq.size == 10000
    assert np.all(np.isfinite(iq.real)) and np.all(np.isfinite(iq.imag))
    assert np.any(np.abs(iq.imag) > 0)                      # imaginary part preserved
    assert np.all(np.isfinite(np.abs(iq)))                  # magnitude
    assert np.all(np.isfinite(np.angle(iq)))                # phase
    assert np.all(np.isfinite(np.fft.fft(iq)))              # spectrum
    assert meas.time_vector is not None and meas.time_vector.size == iq.size
    assert np.all(np.diff(meas.time_vector) > 0)
    assert np.isclose(1.0 / np.median(np.diff(meas.time_vector)), 100000.0, rtol=1e-6)


def test_matlab_to_python_conversion_is_lossless(tmp_path):
    """Round-tripping through savemat/loadmat must not alter a single sample."""
    rng = np.random.default_rng(2024)
    iq = rng.normal(size=4096) + 1j * rng.normal(size=4096)
    path = tmp_path / "roundtrip.mat"
    sio.savemat(str(path), {
        "iq_samples": iq.reshape(-1, 1), "snr_db": 7.5, "ber": 0.02,
        "modulation": "QPSK", "interference_power": 0.3, "channel_type": "Rayleigh",
        "timestamp": 1.5, "sample_rate": 100000.0,
    })
    meas = SimulinkReceiver.load_mat_measurement(str(path))
    assert np.array_equal(meas.iq_samples, iq)
    assert meas.channel_type == "Rayleigh"
    assert matlab_channel_to_internal(meas.channel_type) == "rayleigh"


def test_measured_sir_matches_interference_power():
    """
    For unit-power transmit and negligible thermal noise, the measured impairment power
    must equal the requested interference power (Part 9-D).
    """
    for p in (0.01, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0):
        mat = generate_reference_measurement(
            modulation="QPSK", snr_db=40.0, interference_power=p,
            channel_type="AWGN", n_samples=20000, seed=int(p * 1000) + 3,
        )
        stats = measure_iq_statistics(
            mat["iq_samples"].ravel(), sample_rate=100000.0, tx_iq=mat["tx_iq"].ravel()
        )
        expected_sir_db = -10.0 * np.log10(p + 10.0 ** (-40.0 / 10.0))
        assert stats["measured_snr_db"] == pytest.approx(expected_sir_db, abs=0.5), (
            f"P={p}: measured {stats['measured_snr_db']:.2f} dB, expected {expected_sir_db:.2f} dB"
        )


def test_ber_decreases_with_snr():
    """A monotone-ish BER/SNR relationship confirms the PHY chain is physically sane."""
    bers = [
        generate_reference_measurement(
            modulation="QPSK", snr_db=s, n_samples=20000, seed=17
        )["ber"]
        for s in (0.0, 5.0, 10.0, 20.0)
    ]
    assert bers[0] > bers[1] > bers[2] >= bers[3]
    assert bers[3] == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------- I. Python end-to-end tests


def test_end_to_end_every_stage_produces_output(qpsk_mat):
    pipeline = SimulinkACWRAPipeline()
    result = pipeline.run_from_mat(qpsk_mat, expected_sample_rate=100000.0)

    # Stage 1: measurement
    assert result.measurement.num_samples == 10000
    assert result.measurement.source == FIXTURE_SOURCE_TAG
    assert result.validation.ok

    # Stage 2: bridge statistics
    assert result.iq_statistics["measured_power"] > 0
    assert "measured_snr_db" in result.iq_statistics

    # Stage 3: SpectrumAgent
    spec = result.snapshot.spectrum_result
    assert isinstance(spec, SpectrumIntelligenceResult)
    assert 0.0 <= spec.classifier_confidence <= 1.0
    assert spec.anomaly_flag in ("NONE", "SNR_DROP", "HIGH_INTERFERENCE")
    assert len(result.windows) > 1

    # Stage 4/5: MultiAgentSnapshot
    snap = result.snapshot
    assert isinstance(snap, MultiAgentSnapshot)
    assert isinstance(snap.prediction_result, PredictionResult)
    assert isinstance(snap.defense_candidates, DefenseCandidate)
    assert 0.0 <= snap.prediction_result.risk_score <= 1.0
    assert len(snap.defense_candidates.candidate_strategies) >= 1

    # Stage 6: Digital Twin sandbox
    assert len(result.counterfactuals) == len(snap.defense_candidates.candidate_strategies)
    for cf in result.counterfactuals:
        assert {"strategy", "modulation", "predicted_ber", "predicted_throughput_bps"} <= set(cf)

    # Stage 7: ACWRA decision
    dec = result.decision
    assert isinstance(dec, ACWRADecision)
    assert dec.selected_strategy in snap.defense_candidates.candidate_strategies
    assert np.isfinite(dec.expected_utility)
    assert "ACWRA DECISION TRACE" in dec.decision_trace


def test_pipeline_uses_digital_twin_sandbox_not_a_shortcut(jammed_mat):
    """
    The selected strategy must be the arg-max of the counterfactual utilities, i.e. it
    comes from the Digital Twin sandbox + ACWRA scoring, never directly from the
    SpectrumAgent's detected modulation.
    """
    result = SimulinkACWRAPipeline().run_from_mat(jammed_mat)
    scores = result.decision.candidate_scores
    assert scores
    best = max(cs.utility_score for cs in scores)
    assert result.decision.expected_utility == pytest.approx(best)
    winner = next(cs for cs in scores if cs.strategy == result.decision.selected_strategy)
    assert winner.utility_score == pytest.approx(best)


def test_acwra_formula_holds_on_real_pipeline_output(jammed_mat):
    """U(c) recomputed from the published equation must match the engine exactly."""
    result = SimulinkACWRAPipeline().run_from_mat(jammed_mat)
    C = result.decision.agent_confidence
    R = result.decision.risk_score
    for cs in result.decision.candidate_scores:
        expected = (
            C * (0.4 * cs.t_norm + 0.2 * cs.se_norm)
            - (1.0 + R) * 0.6 * cs.ber_norm
            - 1.0 * (1.0 - C) * cs.complexity_prior
        )
        assert cs.utility_score == pytest.approx(expected, abs=1e-12)


def test_pipeline_is_deterministic(qpsk_mat):
    """Same MAT file in -> identical decision out."""
    a = SimulinkACWRAPipeline().run_from_mat(qpsk_mat)
    b = SimulinkACWRAPipeline().run_from_mat(qpsk_mat)
    assert a.decision.selected_strategy == b.decision.selected_strategy
    assert a.decision.expected_utility == pytest.approx(b.decision.expected_utility)
    assert a.snapshot.spectrum_result.modulation == b.snapshot.spectrum_result.modulation


def test_pipeline_reacts_to_channel_conditions(qpsk_mat, jammed_mat):
    """
    Different Simulink conditions must produce different agent evidence. The decision is
    not hard-coded anywhere in the integration layer.
    """
    clean = SimulinkACWRAPipeline().run_from_mat(qpsk_mat)
    jammed = SimulinkACWRAPipeline().run_from_mat(jammed_mat)

    assert jammed.snapshot.prediction_result.risk_score >= clean.snapshot.prediction_result.risk_score
    assert len(jammed.snapshot.defense_candidates.candidate_strategies) >= len(
        clean.snapshot.defense_candidates.candidate_strategies
    )
    assert jammed.iq_statistics["measured_snr_db"] < clean.iq_statistics["measured_snr_db"]


def test_pipeline_rejects_malformed_measurement_without_substituting_data(tmp_path):
    """No silent fallback: a bad MAT file stops the run."""
    bad = tmp_path / "bad.mat"
    sio.savemat(str(bad), {
        "iq_samples": np.array([[np.nan + 0j]]), "snr_db": 10.0, "modulation": "QPSK",
    })
    with pytest.raises(MeasurementValidationError):
        SimulinkACWRAPipeline().run_from_mat(str(bad))


@pytest.mark.parametrize("modulation", ["BPSK", "QPSK", "OFDM-QPSK"])
def test_all_modulations_traverse_the_pipeline(tmp_path, modulation):
    """Part 9-B: every supported waveform must reach an ACWRA decision."""
    path = tmp_path / f"{modulation}.mat"
    write_reference_mat(
        str(path), modulation=modulation, snr_db=10.0, interference_power=0.0,
        channel_type="AWGN", n_samples=8000, seed=55,
    )
    result = SimulinkACWRAPipeline().run_from_mat(str(path))
    assert result.decision.selected_strategy
    assert result.snapshot.spectrum_result is not None
    # Detection correctness is NOT asserted - the existing classifier does not
    # guarantee it, and Task 11 explicitly says to report rather than enforce.


@pytest.mark.parametrize("channel", ["AWGN", "Rayleigh"])
def test_channels_traverse_the_pipeline(tmp_path, channel):
    """Part 9-E."""
    path = tmp_path / f"chan_{channel}.mat"
    write_reference_mat(
        str(path), modulation="QPSK", snr_db=10.0, interference_power=0.0,
        channel_type=channel, n_samples=8000, seed=77,
    )
    result = SimulinkACWRAPipeline().run_from_mat(str(path))
    assert result.decision.selected_strategy
    assert result.measurement.channel_type == channel
    assert matlab_channel_to_internal(channel) in ("awgn", "rayleigh")


def test_windowing_populates_digital_twin_history(qpsk_mat):
    """
    A single capture must fill enough Digital Twin history for the existing
    TrendPredictor to return SUCCESS rather than INSUFFICIENT_HISTORY.
    """
    pipeline = SimulinkACWRAPipeline()
    result = pipeline.run_from_mat(qpsk_mat)
    assert len(result.windows) >= 5
    assert result.snapshot.prediction_result.prediction_status == "SUCCESS"
    assert len(pipeline.orchestrator.digital_twin.history) == len(result.windows)


def test_fixture_is_labelled_and_never_claims_to_be_simulink(qpsk_mat):
    meas = SimulinkReceiver.load_mat_measurement(qpsk_mat)
    assert meas.source == FIXTURE_SOURCE_TAG
    assert meas.source != "simulink"
