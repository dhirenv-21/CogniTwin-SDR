"""
GNU Radio export format, validation, provenance and bridge ingestion.

Category: bridge / validation (no GNU Radio needed). Every export here is built from
the NumPy stand-in in tests/gr_test_helpers.py. They are either labelled
'python-fixture' or deliberately FORGED to claim GNU Radio provenance, to prove the
validator does not trust the label.
"""

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gr_test_helpers import forged_gnuradio, labelled_fixture  # noqa: E402
from src.gnuradio_phy import (  # noqa: E402
    PROVENANCE_GNURADIO, PROVENANCE_GNURADIO_UNVERIFIED, GRPhyConfig, load_and_validate_gnuradio,
    load_export, validate_gnuradio_dict, write_export,
)
from src.gnuradio_phy.export import content_sha256  # noqa: E402
from src.gnuradio_phy.runner import decide_on_export  # noqa: E402
from src.simulink_bridge.pipeline import SimulinkACWRAPipeline  # noqa: E402
from src.simulink_bridge.validation import PROVENANCE_FIXTURE, MeasurementValidationError  # noqa: E402

CFG = GRPhyConfig(modulation="QPSK", snr_db=10.0, interference_power=0.05, n_symbols=2048, seed=5)


def _rehash(d):
    d["content_sha256"] = content_sha256(d)
    return d


def _ledger(tmp_path, d):
    p = tmp_path / "ledger.jsonl"
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"experiment_id": d["experiment_id"], "content_sha256": d["content_sha256"]}) + "\n")
    return str(p)


# ------------------------------------------------------------------ fixtures are never GNU Radio

@pytest.mark.parametrize("cfg", [
    CFG, CFG.replace(modulation="BPSK"), CFG.replace(modulation="OFDM-QPSK"),
    CFG.replace(channel="RAYLEIGH", fading_mode="block"),
])
def test_fixture_roundtrip_valid_and_labelled_fixture(tmp_path, cfg):
    d = labelled_fixture(cfg, gain=(0.7 - 0.4j) if cfg.fading_mode == "block" else None)
    path = write_export(d, str(tmp_path / "x.npz"), ledger_path=None)
    meas, rep = load_and_validate_gnuradio(path, ledger_path=None)
    assert rep.ok, rep.errors
    assert rep.facts["provenance"] == PROVENANCE_FIXTURE
    assert meas.provenance == PROVENANCE_FIXTURE and meas.source == "python-fixture"
    assert rep.checks["rx_power_matches_configuration"] == "PASS"       # scalar gain -> bridge check on
    with pytest.raises(MeasurementValidationError, match="not a GNU Radio export"):
        load_and_validate_gnuradio(path, require_gnuradio=True, ledger_path=None)


def test_relabelled_fixture_is_not_gnuradio():
    d = labelled_fixture(CFG)
    d["source"] = "gnuradio"                       # label changed after export: hash breaks
    rep = validate_gnuradio_dict(d, ledger_path=None)
    assert rep.facts["provenance"] == PROVENANCE_GNURADIO_UNVERIFIED
    assert rep.checks["gr_content_hash"] == "FAIL"
    _rehash(d)                                     # even with a fresh hash: version / flowgraph wrong
    rep = validate_gnuradio_dict(d, ledger_path=None)
    assert rep.facts["provenance"] == PROVENANCE_GNURADIO_UNVERIFIED
    assert rep.checks["gr_version_wellformed"] == "FAIL"


def test_forgery_without_ledger_is_unverified(tmp_path):
    d = forged_gnuradio(CFG)
    rep = validate_gnuradio_dict(d, ledger_path=str(tmp_path / "empty.jsonl"))
    assert rep.facts["provenance"] == PROVENANCE_GNURADIO_UNVERIFIED
    assert rep.checks["gr_in_run_ledger"] == "WARN"
    rep = validate_gnuradio_dict(d, require_gnuradio=True, ledger_path=str(tmp_path / "empty.jsonl"))
    assert not rep.ok


def test_wrong_flowgraph_hash_is_unverified(tmp_path):
    d = forged_gnuradio(CFG, sha="0" * 64)
    led = _ledger(tmp_path, d)
    rep = validate_gnuradio_dict(d, ledger_path=led)
    assert rep.facts["provenance"] == PROVENANCE_GNURADIO_UNVERIFIED
    assert not validate_gnuradio_dict(d, require_gnuradio=True, ledger_path=led).ok


def test_complete_forgery_passes_documented_limitation(tmp_path):
    """The evidence is consistency, not cryptography: a COMPLETE forgery (hash, version,
    flowgraph hash, ledger line) is accepted. Documented in docs/GNURADIO_SETUP.md."""
    d = forged_gnuradio(CFG)
    rep = validate_gnuradio_dict(d, ledger_path=_ledger(tmp_path, d))
    assert rep.ok and rep.facts["provenance"] == PROVENANCE_GNURADIO


# ------------------------------------------------------------------ tampering / inconsistency

def test_edited_samples_break_content_hash():
    d = labelled_fixture(CFG)
    d["iq_samples"] = d["iq_samples"].copy()
    d["iq_samples"][10] += 0.5
    rep = validate_gnuradio_dict(d, ledger_path=None)
    assert not rep.ok and rep.checks["gr_content_hash"] == "FAIL"


def test_edited_bit_errors_detected_even_with_fresh_hash():
    d = labelled_fixture(CFG.replace(snr_db=4.0))
    d["bit_errors"] = 0
    d["ber"] = 0.0
    rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
    assert not rep.ok and rep.checks["gr_decisions_reproduce_ber"] == "FAIL"


def test_config_disagreeing_with_fields_rejected():
    d = labelled_fixture(CFG)
    d["snr_db"] = 20.0
    rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
    assert not rep.ok and rep.checks["gr_config_consistent"] == "FAIL"


def test_failed_self_checks_rejected():
    for key in ("timing_ok", "gain_capture_ok"):
        d = labelled_fixture(CFG)
        d[key] = False
        rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
        assert not rep.ok, key


def test_incompatible_schema_version_rejected():
    d = labelled_fixture(CFG)
    d["schema_version"] = "cognitwin-gr-export-0"
    assert not validate_gnuradio_dict(_rehash(d), ledger_path=None).ok


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_non_finite_samples_rejected(bad):
    d = labelled_fixture(CFG)
    d["iq_samples"] = d["iq_samples"].copy()
    d["iq_samples"][7] = bad
    rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
    assert not rep.ok and rep.checks["iq_finite_values"] == "FAIL"


def test_missing_keys_rejected():
    d = labelled_fixture(CFG)
    del d["reference_bits"]
    rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
    assert not rep.ok and rep.checks["gr_required_keys"] == "FAIL"


def test_power_inconsistent_with_configuration_rejected():
    d = labelled_fixture(CFG)
    d["noise_iq"] = d["noise_iq"] * 3.0            # declared SNR no longer matches the noise
    rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
    assert not rep.ok and rep.checks["gr_measured_snr_matches_config"] == "FAIL"


# ------------------------------------------------------------------ file-level robustness

def test_empty_truncated_and_garbage_files(tmp_path):
    good = write_export(labelled_fixture(CFG), str(tmp_path / "good.npz"), ledger_path=None)
    blob = open(good, "rb").read()
    (tmp_path / "empty.npz").write_bytes(b"")
    (tmp_path / "trunc.npz").write_bytes(blob[: len(blob) // 2])
    (tmp_path / "text.npz").write_text("not an npz")
    for name in ("empty.npz", "trunc.npz", "text.npz"):
        with pytest.raises(MeasurementValidationError):
            load_export(str(tmp_path / name))
    with pytest.raises(FileNotFoundError):
        load_export(str(tmp_path / "absent.npz"))


def test_pickled_objects_refused(tmp_path):
    p = tmp_path / "obj.npz"
    np.savez(p, iq_samples=np.array([object()], dtype=object))
    with pytest.raises(MeasurementValidationError):
        load_export(str(p))


def test_write_refuses_overwrite_and_appends_ledger(tmp_path):
    d = labelled_fixture(CFG)
    led = tmp_path / "led.jsonl"
    p = write_export(d, str(tmp_path / "a.npz"), ledger_path=str(led))
    with pytest.raises(FileExistsError):
        write_export(d, p, ledger_path=str(led))
    rec = json.loads(led.read_text().strip())
    assert rec["content_sha256"] == d["content_sha256"]


# ------------------------------------------------------------------ bridge / agents

def test_valid_export_reaches_acwra_with_provenance_and_measured_twin_snr():
    res = decide_on_export(labelled_fixture(CFG), SimulinkACWRAPipeline(), ledger_path=None)
    assert res.validation.facts["provenance"] == PROVENANCE_FIXTURE
    assert res.decision.selected_strategy
    assert {w.twin_snr_source for w in res.windows} == {"measured_noise_iq"}
    # noise-only SNR handed to the twin is close to the configured Es/N0 (jammer excluded)
    assert np.mean([w.twin_snr_db for w in res.windows]) == pytest.approx(CFG.snr_db, abs=0.6)


def test_invalid_export_never_becomes_a_decision():
    d = labelled_fixture(CFG)
    d["iq_samples"] = d["iq_samples"].copy()
    d["iq_samples"][0] = np.nan
    with pytest.raises(MeasurementValidationError):
        decide_on_export(_rehash(d), SimulinkACWRAPipeline(), ledger_path=None)


def test_spectrum_agent_does_not_read_the_modulation_label():
    """Target-leakage guard: relabelling the measurement does not change the detection."""
    from src.gnuradio_phy.validation import to_measurement
    d = labelled_fixture(CFG.replace(interference_power=0.0, snr_db=15.0))
    rep = validate_gnuradio_dict(d, ledger_path=None)
    detected = []
    for label in ("QPSK", "BPSK"):
        m = to_measurement(d, rep.facts["provenance"])
        m.modulation = label
        pipe = SimulinkACWRAPipeline()
        res = pipe.run_measurement(m, rep)
        detected.append([w.spectrum_result.modulation for w in res.windows])
    assert detected[0] == detected[1]


def test_timing_check_skipped_only_when_uninformative():
    """Deep fade (as measured in campaign grcl1: |h| = 0.021, SINR -29 dB): the timing search
    cannot resolve, so the check is SKIPPED; the same timing mismatch on a resolvable link FAILS."""
    deep = CFG.replace(modulation="BPSK", snr_db=8.0, interference_power=0.2, channel="RAYLEIGH", fading_mode="block")
    d = labelled_fixture(deep, gain=0.021 + 0j)
    assert not d["timing_resolvable"] and d["timing_peak_z"] < 8
    d["timing_ok"] = False
    rep = validate_gnuradio_dict(_rehash(d), ledger_path=None)
    assert rep.ok and rep.checks["gr_timing_ok"] == "SKIP"
    good = labelled_fixture(CFG)
    assert good["timing_resolvable"]
    good["timing_ok"] = False
    rep = validate_gnuradio_dict(_rehash(good), ledger_path=None)
    assert not rep.ok and rep.checks["gr_timing_ok"] == "FAIL"


def test_export_without_resolvability_flag_is_checked_strictly():
    d = labelled_fixture(CFG.replace(snr_db=-20.0))
    del d["timing_resolvable"]
    d["timing_ok"] = False
    assert not validate_gnuradio_dict(_rehash(d), ledger_path=None).ok
