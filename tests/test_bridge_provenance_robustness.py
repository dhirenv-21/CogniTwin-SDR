"""
Data-bridge hardening: provenance classes, stale-file guard, malformed input.

Categories (never conflated):
  A  real MATLAB/Simulink export      -> PROVENANCE_SIMULINK
  B  legacy Python-written MAT file   -> PROVENANCE_LEGACY_PYTHON
  C  Python test fixture              -> PROVENANCE_FIXTURE
  D  synthetic demonstration data     -> PROVENANCE_SYNTHETIC

Unit tests here build MAT dicts / SciPy files (fixture-based). The tests marked
"real file" read the genuine MATLAB-written exports in simulink/results/ and are
skipped if those are absent.
"""

import os
import sys
import time

import numpy as np
import pytest
import scipy.io as sio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.simulink_bridge.receiver import SimulinkReceiver  # noqa: E402
from src.simulink_bridge.reference_phy import write_reference_mat  # noqa: E402
from src.simulink_bridge.validation import (  # noqa: E402
    PROVENANCE_FIXTURE,
    PROVENANCE_LEGACY_PYTHON,
    PROVENANCE_MATLAB_UNLABELLED,
    PROVENANCE_SIMULINK,
    PROVENANCE_SIMULINK_UNVERIFIED,
    PROVENANCE_SYNTHETIC,
    PROVENANCE_UNKNOWN,
    MeasurementValidationError,
    classify_provenance,
    mat_writer,
    validate_mat_dict,
)

MATLAB_HDR = b"MATLAB 5.0 MAT-file, Platform: PCWIN64, Created on: Mon Aug 17 02:48:16 2026"
SCIPY_HDR = b"MATLAB 5.0 MAT-file Platform: nt, Created on: Thu Oct 22 13:59:51 2026"
REAL_DIR = os.path.join(ROOT, "simulink", "results")


def _qpsk(n, seed=0):
    rng = np.random.default_rng(seed)
    return np.exp(1j * (np.pi / 2 * rng.integers(0, 4, n) + np.pi / 4))


def _good(n=2000, seed=1, **extra):
    rng = np.random.default_rng(seed)
    tx = _qpsk(n, seed)
    noise = np.sqrt(0.05) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    d = {
        "iq_samples": (tx + noise).reshape(-1, 1),
        "tx_iq": tx.reshape(-1, 1),
        "noise_iq": noise.reshape(-1, 1),
        "snr_db": 10.0,
        "modulation": "QPSK",
        "sample_rate": 100e3,
        "fixed_step": 1e-5,
        "num_samples": float(n),
        "time_vector": (np.arange(n) / 100e3).reshape(-1, 1),
        "ber": 0.001,
        "bit_errors": 4.0,
        "bits_compared": 4000.0,
    }
    d.update(extra)
    return d


# ================================================================ provenance
@pytest.mark.parametrize("header,source,kind", [
    (MATLAB_HDR, "simulink", PROVENANCE_SIMULINK),
    (SCIPY_HDR, "simulink", PROVENANCE_SIMULINK_UNVERIFIED),
    (None, "simulink", PROVENANCE_SIMULINK_UNVERIFIED),
    (SCIPY_HDR, "python-fixture", PROVENANCE_FIXTURE),
    (MATLAB_HDR, "python-fixture", PROVENANCE_FIXTURE),
    (SCIPY_HDR, "synthetic-demo", PROVENANCE_SYNTHETIC),
    (None, "demo", PROVENANCE_SYNTHETIC),
    (SCIPY_HDR, None, PROVENANCE_LEGACY_PYTHON),
    (MATLAB_HDR, None, PROVENANCE_MATLAB_UNLABELLED),
    (None, None, PROVENANCE_UNKNOWN),
])
def test_classify_provenance(header, source, kind):
    mat = {}
    if header is not None:
        mat["__header__"] = header
    if source is not None:
        mat["source"] = source
    assert classify_provenance(mat)[0] == kind


def test_only_a_matlab_written_simulink_label_is_category_a():
    """B, C and D are never labelled A, whatever their source string says."""
    for hdr in (SCIPY_HDR, None):
        for src in ("simulink", "Simulink", "simulink-v4", "python-fixture", "demo", ""):
            mat = {"source": src}
            if hdr:
                mat["__header__"] = hdr
            assert classify_provenance(mat)[0] != PROVENANCE_SIMULINK, (hdr, src)


def test_mat_writer_reads_the_header_scipy_actually_writes(tmp_path):
    p = tmp_path / "x.mat"
    sio.savemat(str(p), {"a": 1.0})
    assert mat_writer(sio.loadmat(str(p))) == "scipy"
    assert mat_writer({"__header__": MATLAB_HDR}) == "matlab"


def test_scipy_file_claiming_simulink_is_rejected_under_require_real(tmp_path):
    p = tmp_path / "fake_real.mat"
    sio.savemat(str(p), _good(source="simulink"))
    m, rep = SimulinkReceiver.load_and_validate(str(p))          # default: warn only
    assert rep.checks["provenance_consistent"] == "WARN"
    assert m.provenance == PROVENANCE_SIMULINK_UNVERIFIED
    with pytest.raises(MeasurementValidationError, match="not a real Simulink export"):
        SimulinkReceiver.load_and_validate(str(p), require_real=True)


def test_reference_fixture_is_labelled_fixture_and_rejected_as_real(tmp_path):
    p = write_reference_mat(str(tmp_path / "fx.mat"), modulation="QPSK", snr_db=12.0)
    m, rep = SimulinkReceiver.load_and_validate(p)
    assert m.provenance == PROVENANCE_FIXTURE
    with pytest.raises(MeasurementValidationError):
        SimulinkReceiver.load_and_validate(p, require_real=True)


def test_real_file_v3_export_is_category_a_but_not_v4():
    """real file: a genuine MATLAB-written Simulink export from the v3 model."""
    p = os.path.join(REAL_DIR, "sim_qpsk_snr10_int0p4_awgn.mat")
    if not os.path.exists(p):
        pytest.skip("real Simulink export not present")
    m, rep = SimulinkReceiver.load_and_validate(p, require_real=True)
    assert m.provenance == PROVENANCE_SIMULINK
    assert rep.facts["model_version"] == "pre-v4"
    with pytest.raises(MeasurementValidationError, match="model_version"):
        SimulinkReceiver.load_and_validate(p, require_model_version="v4")


def test_real_file_legacy_measurement_is_python_written():
    """real file: simulink/results/measurement_*.mat carry SciPy's header."""
    p = os.path.join(REAL_DIR, "measurement_normal.mat")
    if not os.path.exists(p):
        pytest.skip("legacy measurement file not present")
    m = SimulinkReceiver.load_mat_measurement(p)
    assert m.provenance == PROVENANCE_LEGACY_PYTHON
    with pytest.raises(MeasurementValidationError):
        SimulinkReceiver.load_and_validate(p, require_real=True)


def test_real_file_v2_broken_export_is_genuine_but_physically_rejected():
    """Provenance is not validity: a real Simulink file can still be broken."""
    p = os.path.join(REAL_DIR, "sim_qpsk_snr10_int0_rayleigh.mat")
    if not os.path.exists(p):
        pytest.skip("v2 export not present")
    rep = validate_mat_dict(sio.loadmat(p))
    assert rep.facts["provenance"] == PROVENANCE_SIMULINK
    assert rep.facts["ber"] > 0.45
    # Before 2026-10-22 this file PASSED validation: its declared |h| ~ 0.004 made
    # wanted_signal_present skip itself. The received-power consistency check rejects it.
    assert rep.checks["rx_power_matches_configuration"] == "FAIL" and not rep.ok
    with pytest.raises(MeasurementValidationError, match="rx_power_matches_configuration"):
        SimulinkReceiver.load_and_validate(p, require_real=True)


def test_real_file_every_valid_historical_export_passes_the_power_check():
    """real files: the check must not reject any genuine, healthy export."""
    import glob
    files = [f for f in glob.glob(os.path.join(REAL_DIR, "baseline", "*.mat"))
             if not f.endswith("baseline_results.mat")]
    if not files:
        pytest.skip("no historical baseline exports")
    for f in files:
        rep = validate_mat_dict(sio.loadmat(f))
        assert rep.checks.get("rx_power_matches_configuration") == "PASS", f
        assert rep.facts["rx_power_error_db"] < 0.3, f


# ================================================================ stale files
def test_stale_file_guard(tmp_path):
    p = tmp_path / "run.mat"
    sio.savemat(str(p), _good())
    SimulinkReceiver.load_and_validate(str(p), not_before=time.time() - 3600)
    with pytest.raises(MeasurementValidationError, match="stale"):
        SimulinkReceiver.load_and_validate(str(p), not_before=time.time() + 3600)


def test_identity_facts_are_reported(tmp_path):
    p = tmp_path / "run.mat"
    sio.savemat(str(p), _good(run_id="sim_x_seed3_20261022T120000", model_version="v4",
                              noise_source="random_number_blocks", noise_seed=1003.0))
    _, rep = SimulinkReceiver.load_and_validate(str(p), require_model_version="v4")
    assert rep.facts["run_id"] == "sim_x_seed3_20261022T120000"
    assert rep.facts["noise_source"] == "random_number_blocks"
    assert rep.facts["noise_seed"] == 1003.0


# ================================================================ malformed
def test_baseline_good_dict_is_valid():
    rep = validate_mat_dict(_good())
    assert rep.ok, rep.errors


def test_minimal_legacy_dict_remains_valid():
    """Backward compatibility: iq + snr + modulation only."""
    rep = validate_mat_dict({"iq_samples": _qpsk(256), "snr_db": 5.0, "modulation": "QPSK"})
    assert rep.ok, rep.errors


def test_non_mat_file_is_rejected(tmp_path):
    p = tmp_path / "junk.mat"
    p.write_bytes(b"this is not a MAT file at all" * 10)
    with pytest.raises(MeasurementValidationError, match="could not be parsed"):
        SimulinkReceiver.load_and_validate(str(p))


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        SimulinkReceiver.load_and_validate(str(tmp_path / "absent.mat"))


@pytest.mark.parametrize("drop", ["iq_samples", "snr_db", "modulation"])
def test_missing_required_field(drop):
    d = _good()
    d.pop(drop)
    rep = validate_mat_dict(d)
    assert not rep.ok and rep.checks["required_variables_present"] == "FAIL"


def _bad(mutator):
    d = _good()
    mutator(d)
    return validate_mat_dict(d)


@pytest.mark.parametrize("name,mutator,check", [
    ("empty iq", lambda d: d.update(iq_samples=np.zeros((0, 1))), "iq_dimensions"),
    ("3-column iq", lambda d: d.update(iq_samples=np.ones((100, 3))), "iq_dimensions"),
    ("NaN in iq", lambda d: d["iq_samples"].__setitem__((5, 0), np.nan), "iq_finite_values"),
    ("Inf in noise", lambda d: d["noise_iq"].__setitem__((7, 0), np.inf), "noise_iq_valid"),
    ("short noise", lambda d: d.update(noise_iq=d["noise_iq"][:-3]), "noise_iq_valid"),
    ("tx length", lambda d: d.update(tx_iq=d["tx_iq"][:-1]), "tx_iq_length"),
    ("num_samples", lambda d: d.update(num_samples=1999.0), "num_samples_consistent"),
    ("time length", lambda d: d.update(time_vector=d["time_vector"][:-1]), "time_vector_length"),
    ("time order", lambda d: d.update(time_vector=d["time_vector"][::-1]), "time_vector_monotonic"),
    ("ber vs bits", lambda d: d.update(ber=0.5), "ber_consistent_with_bit_counts"),
    ("bits non-int", lambda d: d.update(bit_errors=3.5), "ber_consistent_with_bit_counts"),
    ("errors > bits", lambda d: d.update(bit_errors=5000.0, ber=1.25), "ber_consistent_with_bit_counts"),
    ("ber > 1", lambda d: d.update(ber=1.5), "ber_in_range"),
    ("step vs Fs", lambda d: d.update(fixed_step=2e-5), "fixed_step_matches_sample_rate"),
    ("Fs <= 0", lambda d: d.update(sample_rate=0.0), "sample_rate_valid"),
    ("snr NaN", lambda d: d.update(snr_db=np.nan), "snr_finite"),
    ("snr vector", lambda d: d.update(snr_db=np.array([1.0, 2.0])), "snr_is_scalar"),
    ("modulation numeric", lambda d: d.update(modulation=3.0), "modulation_is_text"),
    ("negative interference", lambda d: d.update(interference_power=-1.0), "interference_power_valid"),
    ("gain NaN", lambda d: d.update(channel_gain_real=np.nan), "channel_gain_real_valid"),
    ("measured snr NaN", lambda d: d.update(measured_snr_db=np.nan), "measured_snr_db_valid"),
    ("checks failed", lambda d: d.update(checks_passed=0.0), "matlab_checks_passed"),
])
def test_malformed_or_inconsistent_input_is_rejected(name, mutator, check):
    rep = _bad(mutator)
    assert not rep.ok, f"{name}: accepted"
    assert rep.checks.get(check) == "FAIL", f"{name}: {check} = {rep.checks.get(check)}; {rep.errors}"


def test_errors_name_the_offending_field(tmp_path):
    p = tmp_path / "bad.mat"
    sio.savemat(str(p), _good(num_samples=5.0))
    with pytest.raises(MeasurementValidationError) as exc:
        SimulinkReceiver.load_and_validate(str(p))
    assert "num_samples=5.0" in str(exc.value)


# ================================================================ demo guard
def test_demo_require_real_refuses_a_python_file_labelled_simulink(tmp_path, capsys):
    """The old guard checked only source.startswith('simulink')."""
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import simulink_acwra_demo as demo

    p = write_reference_mat(str(tmp_path / "fx.mat"), modulation="QPSK", snr_db=15.0)
    mat = sio.loadmat(p)
    mat = {k: v for k, v in mat.items() if not k.startswith("__")}
    mat["source"] = "simulink"
    sio.savemat(p, mat)
    rc = demo.main(["--mat", p, "--require-real"])
    out = capsys.readouterr().out
    assert rc == 4, out
    assert "simulink_claim_unverified" in out
