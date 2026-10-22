"""Smoke tests for experiments/review_demo.py (fixture input; virtual-RF loop)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "experiments")):
    if p not in sys.path:
        sys.path.insert(0, p)

import review_demo  # noqa: E402


def test_demo_labels_a_fixture_as_a_fixture(capsys):
    assert review_demo.main(["--fixture", "--skip-loop"]) == 0
    out = capsys.readouterr().out
    assert "PYTHON FIXTURE (synthetic, reference PHY)" in out
    assert "REAL SIMULINK" not in out
    assert "ACWRA DECISION TRACE" in out


def test_demo_labels_historical_simulink_and_the_loop_as_virtual(capsys):
    if not os.path.exists(review_demo.DEFAULT_MAT):
        return
    assert review_demo.main([]) == 0
    out = capsys.readouterr().out
    assert "REAL SIMULINK EXPORT" in out and "HISTORICAL export from the pre-v4 model" in out
    assert "VIRTUAL RF (NOT Simulink)" in out


def test_demo_reports_a_rejected_input_without_a_decision(tmp_path, capsys):
    import scipy.io as sio
    p = str(tmp_path / "bad.mat")
    sio.savemat(p, {"iq_samples": [[1.0]], "snr_db": 10.0, "modulation": "QPSK"})
    assert review_demo.main(["--mat", p, "--skip-loop"]) == 2
    out = capsys.readouterr().out
    assert "INPUT REJECTED" in out and "ACWRA DECISION TRACE" not in out
