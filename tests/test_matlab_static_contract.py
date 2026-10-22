"""
STATIC contracts between the MATLAB sources and the Python consumers.

These read the .m files as text. They prove the sources AGREE with each other and
with the Python bridge; they do NOT prove the MATLAB code runs. Runtime behaviour
(D1-D18, the Simulink exports) is only established by simulink/matlab/run_v4_validation.m
on a MATLAB machine.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _code(src):
    """Strip full-line comments."""
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("%"))


def _exported_fields():
    return set(re.findall(r"^\s*m\.(\w+)\s*=", _read("simulink", "matlab", "run_simulink_case.m"), re.M))


# ------------------------------------------------------------- export schema
def test_every_field_the_python_side_reads_is_exported():
    exported = _exported_fields() | {"__header__"}
    readers = {
        "verifier": (_read("experiments", "verify_simulink_mat.py"),
                     [r'_(?:scalar|text)\(mat, "(\w+)"', r'"(\w+)" in mat\b', r'mat\["(\w+)"\]']),
        "validation": (_read("src", "simulink_bridge", "validation.py"),
                       [r'mat\.get\("(\w+)"\)', r'"(\w+)" in mat\b', r'mat\["(\w+)"\]']),
        "receiver": (_read("src", "simulink_bridge", "receiver.py"),
                     [r'mat_data\.get\("(\w+)"', r'"(\w+)" in mat_data', r'mat_data\["(\w+)"\]']),
    }
    for name, (src, pats) in readers.items():
        read = set()
        for p in pats:
            read |= set(re.findall(p, src))
        missing = sorted(read - exported)
        assert not missing, f"{name} reads fields run_simulink_case never exports: {missing}"


def test_d18_required_fields_are_exactly_exported_fields():
    d = _read("simulink", "matlab", "diagnose_simulink_phy.m")
    req = set(re.findall(r"'(\w+)'", re.search(r"required = \{(.*?)\};", d, re.S).group(1)))
    assert req, "D18 required list not found"
    assert not (req - _exported_fields()), sorted(req - _exported_fields())


# ------------------------------------------------------------- noise source
def test_default_noise_source_is_consistent_everywhere():
    gen = _read("simulink", "create_cognitwin_model.m")
    runner = _read("simulink", "matlab", "run_v4_validation.m")
    drv = _read("simulink", "matlab", "run_simulink_case.m")
    dia = _read("simulink", "matlab", "diagnose_simulink_phy.m")

    assert "NoiseSource = 'random_number_blocks';" in gen
    assert "noiseSource = 'random_number_blocks'; end" in runner

    names = re.search(r"rnNames = \{([^}]*)\};", gen).group(1)
    assert names == "'NOISE_I','NOISE_Q','JAM_I','JAM_Q'"
    for src in (drv, dia):
        assert "{'NOISE_I','NOISE_Q','JAM_I','JAM_Q'}" in src
        assert "'Name', 'NOISE_SEED'" in src            # block_rng detection


def test_random_number_blocks_feed_the_documented_ports_in_order():
    gen = _code(_read("simulink", "create_cognitwin_model.m"))
    sig = re.search(r"'function \[y, jam, noise, x\] = fcn\(([^)]*ni, nq, ji, jq)\)'", gen).group(1)
    inputs = [s.strip() for s in sig.split(",")]
    assert inputs == ["xi", "xq", "snr_db", "interf_power", "h_re", "h_im", "ni", "nq", "ji", "jq"]

    fixed = dict((int(p), b) for b, p in re.findall(r"add_line\(modelName,'(\w+)/1','PHY_Channel/(\d+)'", gen))
    assert fixed == {1: "INPUT_I", 2: "INPUT_Q", 3: "SNR_PARAMETER", 4: "INTERFERENCE_PARAMETER",
                     5: "CHANNEL_GAIN_RE", 6: "CHANNEL_GAIN_IM", 7: "NOISE_SEED"}
    # RN loop: rnNames{k} -> port 6+k, so NOISE_I->7, NOISE_Q->8, JAM_I->9, JAM_Q->10
    assert "sprintf('PHY_Channel/%d', 6+k)" in gen

    outs = dict((int(p), b) for p, b in re.findall(r"add_line\(modelName,'PHY_Channel/(\d+)','(\w+)/1'", gen))
    assert outs[2] == "INTERFERENCE_TO_WORKSPACE" and outs[3] == "NOISE_TO_WORKSPACE"
    assert outs[4] == "TX_ECHO_TO_WORKSPACE"


def test_generator_saves_next_to_itself_and_surfaces_compile_errors():
    gen = _code(_read("simulink", "create_cognitwin_model.m"))
    i_cd = gen.index("cd(generatorDir);")
    i_backup = gen.index("copyfile([modelName '.slx'], backupName);")
    i_update = gen.index("set_param(modelName,'SimulationCommand','update');")
    i_save = gen.index("save_system(modelName);")
    assert i_cd < i_backup < i_update < i_save
    # the update is inside try/catch that RE-RAISES (does not swallow)
    block = gen[i_update:i_save]
    assert "error('create_cognitwin_model:UpdateFailed'" in block


# ------------------------------------------------------------- runbook
def test_runbook_archives_before_any_step_that_overwrites():
    rb = _code(_read("simulink", "matlab", "run_v4_validation.m"))
    i_arch = rb.index("copyfile(fullfile(simDir, 'results'), fullfile(archive, 'results'));")
    for later in ("run(''%s'');", "diagnose_simulink_phy(true)",
                  "run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')", "run_baseline_tests()"):
        assert i_arch < rb.index(later), later
    # archive failure aborts before anything is overwritten
    assert "error('run_v4_validation:ArchiveFailed'" in rb
    # archive lives OUTSIDE results/ so it is never re-archived or verified as new
    assert "fullfile(simDir, 'results_archive'" in rb


def test_runbook_records_each_step_independently():
    rb = _code(_read("simulink", "matlab", "run_v4_validation.m"))
    steps = re.findall(r"local_add\(st, '(\w+)'", rb)
    for s in ("environment", "preserve", "create_cognitwin_model", "diagnose_simulink_phy",
              "rayleigh_case", "run_baseline_tests", "manifest"):
        assert s in steps, s
    # diagnose, rayleigh and baseline each have their own try/catch
    for call in ("diagnose_simulink_phy(true)", "run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')",
                 "run_baseline_tests()"):
        i = rb.index(call)
        i_try = rb.rfind("\n    try\n", 0, i)
        assert i_try >= 0, f"{call}: no try before it"
        # no catch between that try and the call -> the call is inside the try
        assert rb.find("catch", i_try, i) == -1, f"{call}: not inside its own try"
        i_catch = rb.index("catch err", i)
        # the catch records a FAIL for this step instead of re-throwing
        assert "local_add(st," in rb[i_catch:i_catch + 400], call
    assert "diary(fullfile(logDir, 'matlab_console.log'));" in rb
    assert "manifest.csv" in rb and "written_this_run" in rb


def test_runbook_uses_real_signatures():
    """Every function the runbook calls exists with a compatible signature."""
    rb = _read("simulink", "matlab", "run_v4_validation.m")
    sigs = {
        "diagnose_simulink_phy": r"function report = diagnose_simulink_phy\(verbose\)",
        "run_simulink_case": r"function \[outFile, m\] = run_simulink_case\(modulation, snrDb, interferencePower, channelType, opts\)",
        "run_baseline_tests": r"function results = run_baseline_tests\(opts\)",
    }
    for fn, pat in sigs.items():
        src = _read("simulink", "matlab", f"{fn}.m")
        assert re.search(pat, src), fn
        assert fn in rb
    assert os.path.exists(os.path.join(ROOT, "simulink", "create_cognitwin_model.m"))
    # fields the runbook prints from the Rayleigh export exist in the export
    used = set(re.findall(r"m4\.(\w+)", rb))
    assert used <= _exported_fields(), sorted(used - _exported_fields())


# ------------------------------------------------------------- MATLAB structure
def _lint(path):
    """Light structural lint (NOT a parser): block/end balance at statement level."""
    depth, stmt = 0, ""
    opens = {"if", "for", "while", "switch", "try", "parfor", "function"}
    with open(path, encoding="utf-8", errors="replace") as fh:
        source_lines = fh.read().splitlines()
    for raw in source_lines:
        line, out, in_str, prev, nest = raw, [], False, "", 0
        i = 0
        while i < len(line):
            c = line[i]
            if in_str:
                if c == "'" and line[i + 1:i + 2] == "'":
                    i += 2
                    continue
                if c == "'":
                    in_str = False
                i += 1
                continue
            if c == "%":
                break
            nest += c in "[{"
            nest -= c in "]}"
            if c == "'":
                after_space = i > 0 and line[i - 1].isspace()
                if prev and (prev.isalnum() or prev in ")]}_.'") and not (nest > 0 and after_space):
                    out.append(c)
                else:
                    in_str = True
                    out.append("S")
                prev = "S"
                i += 1
                continue
            out.append(c)
            if not c.isspace():
                prev = c
            i += 1
        if in_str:
            return f"unterminated char literal: {raw.strip()[:60]}"
        code = "".join(out)
        if code.rstrip().endswith("..."):
            stmt += code.rstrip()[:-3] + " "
            continue
        stmt += code
        par = 0
        for m in re.finditer(r"[A-Za-z_]\w*|[(){}]", stmt):
            t = m.group(0)
            if t in "({":
                par += 1
            elif t in ")}":
                par -= 1
            elif par == 0 and t in opens:
                depth += 1
            elif par == 0 and t == "end":
                depth -= 1
        stmt = ""
    return None if depth == 0 else f"block/end imbalance {depth:+d}"


MFILES = sorted(
    os.path.relpath(os.path.join(d, f), ROOT)
    for d, _, fs in os.walk(os.path.join(ROOT, "simulink"))
    if "slprj" not in d and "results" not in d
    for f in fs if f.endswith(".m")
)


@pytest.mark.parametrize("rel", MFILES)
def test_matlab_file_structure(rel):
    problem = _lint(os.path.join(ROOT, rel))
    assert problem is None, f"{rel}: {problem}"


def test_lint_detects_a_broken_file(tmp_path):
    p = tmp_path / "bad.m"
    p.write_text("function f(x)\nif x\n  y = [x '/' 'a];\nend\n")
    assert _lint(str(p)) is not None
