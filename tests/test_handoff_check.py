"""
Tests for experiments/handoff_check.py. Static and fixture-based: the 'post' cases use
temporary folders, never the repository's simulink/run_logs, and only check that
missing or non-MATLAB evidence can never be reported as PASS.
"""

import os
import re
import sys

import numpy as np
import scipy.io as sio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "experiments")):
    if p not in sys.path:
        sys.path.insert(0, p)

import handoff_check as hc  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def test_call_graph_is_the_audited_set():
    assert hc.matlab_call_graph(ROOT) == sorted([
        "simulink/create_cognitwin_model.m",
        "simulink/matlab/cognitwin_bin2gray.m",
        "simulink/matlab/cognitwin_check_modulation.m",
        "simulink/matlab/cognitwin_gray2bin.m",
        "simulink/matlab/cognitwin_measure_ber.m",
        "simulink/matlab/cognitwin_waveform.m",
        "simulink/matlab/diagnose_simulink_phy.m",
        "simulink/matlab/run_baseline_tests.m",
        "simulink/matlab/run_simulink_case.m",
        "simulink/matlab/run_v4_validation.m",
    ])


def test_expected_baseline_names_match_run_baseline_tests():
    src = _read("simulink", "matlab", "run_baseline_tests.m")
    for pat in ("'baseline_%s'", "'ladder_seed%d_snr%d'", "'seedrep_%s_%d'",
                "'mod_%s_snr%d_awgn'", "'mod_%s_snr10_rayleigh'", "sprintf('interf_p%s'"):
        assert pat in src, pat
    assert "snrLadder = [0 5 10 15 20];" in src and "[11 23 37]" in src
    assert "pList = [0.01 0.1 0.25 0.5 1 2 4 10];" in src
    assert "covSnr  = [0 5 10];" in src
    # 6 cases + 15 ladder + 8 interference + 6 seed-rep + 8 modulation coverage
    assert len(hc.BASELINE_EXPECTED) == len(set(hc.BASELINE_EXPECTED)) == 43


def test_expected_rayleigh_path_matches_the_driver_naming():
    src = _read("simulink", "matlab", "run_simulink_case.m")
    assert "stem = sprintf('sim_%s_snr%s_int%s_%s'" in src
    assert hc.RAYLEIGH_FILE == "results/sim_qpsk_snr10_int0p25_rayleigh.mat"


def test_summary_parser_matches_the_runbook_format():
    rb = _read("simulink", "matlab", "run_v4_validation.m")
    assert "fprintf(fid, '  %-24s %s\\n      %s\\n'" in rb
    assert "fprintf(fid, '  [%s] %-36s %s\\n'" in rb
    sample = ("STEPS\n  %-24s %s\n      detail\n" % ("environment", "PASS")
              + "  %-24s %s\n      boom\n" % ("rayleigh_case", "FAIL")
              + "\nDIAGNOSTICS\n  [%s] %-36s %s\n" % ("FAIL", "D13_noise_seed_control", "|corr| = 1.0"))
    steps, diags = hc.parse_summary(sample)
    assert steps == {"environment": "PASS", "rayleigh_case": "FAIL"}
    assert diags["D13_noise_seed_control"] == ("FAIL", "|corr| = 1.0")


def test_d_list_matches_the_diagnostic():
    names = re.findall(r"local_add\(report, '(D\w+)'", _read("simulink", "matlab", "diagnose_simulink_phy.m"))
    assert sorted(names) == sorted(hc.D_EXPECTED)


def test_manifest_paths_are_relative_to_simulink():
    rb = _read("simulink", "matlab", "run_v4_validation.m")
    assert "relPath = ['results/' strrep(f(numel(prefix)+1:end), '\\', '/')];" in rb


def test_post_without_returned_logs_is_not_verified(tmp_path, capsys):
    (tmp_path / "simulink").mkdir()
    assert hc.post(str(tmp_path)) == 1
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_post_never_passes_python_written_or_missing_evidence(tmp_path, capsys):
    log = tmp_path / "simulink" / "run_logs" / "20990101_000000"
    log.mkdir(parents=True)
    (log / "summary.txt").write_text("STEPS\n  %-24s %s\n" % ("environment", "PASS"))
    res = tmp_path / "simulink" / "results"
    res.mkdir()
    tx = np.exp(1j * np.pi / 4) * np.ones(512)
    sio.savemat(str(res / "sim_qpsk_snr10_int0p25_rayleigh.mat"),
                {"iq_samples": tx, "tx_iq": tx, "snr_db": 10.0, "modulation": "QPSK",
                 "source": "simulink", "model_version": "v4"})          # SciPy-written: not real
    (log / "manifest.csv").write_text(
        "path,bytes,modified,written_this_run,model_version,noise_source,run_id\n"
        '"results/sim_qpsk_snr10_int0p25_rayleigh.mat",1,2099-01-01T00:00:00,1,v4,random_number_blocks,x\n')
    assert hc.post(str(tmp_path), str(log)) == 1
    out = capsys.readouterr().out
    assert "| file results/sim_qpsk_snr10_int0p25_rayleigh.mat | **FAIL** |" in out
    assert "| **D13 seed control** | **NOT FOUND** |" in out
    assert "| returned: matlab_console.log | **NOT FOUND** |" in out
    assert "ALL PASS" not in out


def test_expected_exports_follow_the_script_not_a_fixed_count(tmp_path):
    """Metamorphic: change the SNR ladder in a copy of run_baseline_tests.m."""
    import shutil
    (tmp_path / "simulink" / "matlab").mkdir(parents=True)
    src = _read("simulink", "matlab", "run_baseline_tests.m")
    (tmp_path / "simulink" / "matlab" / "run_baseline_tests.m").write_text(
        src.replace("snrLadder = [0 5 10 15 20];", "snrLadder = [0 10];"), encoding="utf-8")
    stems = hc.expected_baseline_exports(str(tmp_path))
    assert len(stems) == 43 - 3 * 3                      # 3 seeds x 3 removed ladder points
    assert "ladder_seed11_snr5" not in stems and "ladder_seed37_snr10" in stems
    (tmp_path / "simulink" / "matlab" / "run_baseline_tests.m").write_text(
        src.replace("'ladder_seed%d_snr%d'", "'lad_%d_%d'"), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="pattern"):
        hc.expected_baseline_exports(str(tmp_path))


def test_runbook_and_loop_survive_spaces_and_apostrophes_in_paths():
    rb = _read("simulink", "matlab", "run_v4_validation.m")
    assert "genPath = strrep(fullfile(simDir, 'create_cognitwin_model.m'), '''', '''''');" in rb
    loop = _read("simulink", "matlab", "run_simulink_closed_loop.m")
    assert "'\"%s\" \"%s\" --mat \"%s\" --state \"%s\" --out \"%s\" --require-real'" in loop
