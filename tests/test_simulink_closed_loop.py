"""
Simulink-in-the-loop bridge: STATIC checks of run_simulink_closed_loop.m and
FIXTURE-BASED tests of experiments/acwra_decide.py. Nothing here runs MATLAB.
"""

import json
import os
import re
import subprocess
import sys

import pytest
import scipy.io as sio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "experiments")):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.simulink_bridge.reference_phy import write_reference_mat  # noqa: E402

import acwra_decide  # noqa: E402

LOOP = os.path.join(ROOT, "simulink", "matlab", "run_simulink_closed_loop.m")


def _src(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------------ static MATLAB
def test_loop_passes_only_options_run_simulink_case_knows():
    case = _src(os.path.join(ROOT, "simulink", "matlab", "run_simulink_case.m"))
    defaults = set(re.findall(r"'(\w+)',", re.search(r"def = struct\((.*?)\);", case, re.S).group(1)))
    call = re.search(r"run_simulink_case\(current,.*?struct\((.*?)\)\);", _src(LOOP), re.S).group(1)
    used = set(re.findall(r"'(\w+)',", call))
    assert used and used <= defaults, used - defaults


def test_loop_reads_only_fields_the_decider_writes():
    fields = set(re.findall(r"\bd\.(\w+)", _src(LOOP)))
    assert fields <= set(acwra_decide.DECISION_FIELDS), fields - set(acwra_decide.DECISION_FIELDS)


def test_loop_applies_the_decision_on_the_next_step_and_never_invents_one():
    src = _src(LOOP)
    assert "current = d.next_modulation;" in src
    i_case = src.index("run_simulink_case(current,")
    i_apply = src.index("current = d.next_modulation;")
    assert i_case < i_apply                              # step k simulated with the step k-1 choice
    assert src.count("break;") >= 2                      # simulation or decision failure stops the loop
    assert "--require-real" in src
    assert "'timestamp', (k-1) * stepDur" in src         # monotonic twin time across steps


# ------------------------------------------------------------------ decider (fixtures)
def _mat(tmp_path, name, **kw):
    return write_reference_mat(str(tmp_path / name), **kw)


def test_decider_writes_a_complete_decision_and_persists_twin_history(tmp_path):
    state = tmp_path / "twin_state.json"
    for k, snr in enumerate((20.0, 12.0, 6.0)):
        mat = _mat(tmp_path, f"s{k}.mat", modulation="QPSK", snr_db=snr, interference_power=0.1,
                   seed=k, timestamp=0.1 * k)
        out = tmp_path / f"d{k}.json"
        assert acwra_decide.main(["--mat", mat, "--state", str(state), "--out", str(out)]) == 0
        d = json.loads(out.read_text())
        assert set(acwra_decide.DECISION_FIELDS) <= set(d)
        assert d["next_modulation"] in ("BPSK", "QPSK", "OFDM-QPSK")
        assert d["provenance"] == "python_fixture"
    st = json.loads(state.read_text())
    ts = [s["timestamp_s"] for s in st["history"]]
    assert len(ts) > 3 and all(b > a for a, b in zip(ts, ts[1:]))       # carried across calls


def test_decider_require_real_refuses_fixtures(tmp_path, capsys):
    mat = _mat(tmp_path, "f.mat", modulation="QPSK", snr_db=10.0, seed=1)
    out = tmp_path / "d.json"
    rc = acwra_decide.main(["--mat", mat, "--state", str(tmp_path / "s.json"), "--out", str(out),
                            "--require-real"])
    assert rc != 0 and not out.exists()
    assert "not a real Simulink export" in capsys.readouterr().out


def test_decider_runs_as_a_subprocess_like_matlab_calls_it(tmp_path):
    mat = _mat(tmp_path, "m.mat", modulation="BPSK", snr_db=8.0, seed=2)
    out = tmp_path / "d.json"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "experiments", "acwra_decide.py"), "--mat", mat,
                        "--state", str(tmp_path / "s.json"), "--out", str(out)],
                       capture_output=True, text=True, timeout=300, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(out.read_text())["selected_strategy"]


def test_decider_rejects_a_broken_export(tmp_path):
    p = tmp_path / "bad.mat"
    sio.savemat(str(p), {"iq_samples": [[1.0, float("nan")]], "snr_db": 10.0, "modulation": "QPSK"})
    rc = acwra_decide.main(["--mat", str(p), "--state", str(tmp_path / "s.json"), "--out", str(tmp_path / "d.json")])
    assert rc != 0 and not (tmp_path / "d.json").exists()
