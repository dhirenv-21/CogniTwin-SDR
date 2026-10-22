"""
MATLAB HANDOFF CHECKS (Python side; never runs or simulates MATLAB).

    python experiments/handoff_check.py pre
        Before transfer: every MATLAB file run_v4_validation.m can reach (derived
        from the call graph, not a hand list) plus the model and the historical
        results exist, are tracked by git and have no uncommitted changes.

    python experiments/handoff_check.py post [--log-dir simulink/run_logs/<stamp>]
        After the artifacts come back: reads the run's summary.txt / manifest.csv,
        and checks every MAT file the run wrote - real MATLAB provenance,
        model_version v4, the independent physics verifier, cross-seed noise
        independence. Reports PASS / FAIL / NOT FOUND per item; writes
        python_verification.md beside the MATLAB logs. Exit 0 only if all PASS.

Nothing here can turn missing evidence into a PASS.
"""

import argparse
import csv
import glob
import hashlib
import os
import re
import subprocess
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (project_root, os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path:
        sys.path.insert(0, p)

RUNBOOK = "run_v4_validation"
RAYLEIGH_FILE = "results/sim_qpsk_snr10_int0p25_rayleigh.mat"
def _num_list(src, pattern):
    m = re.search(pattern, src)
    if not m:
        raise ValueError(f"run_baseline_tests.m: cannot find {pattern!r}; update handoff_check.py")
    return [float(x) for x in m.group(1).split()]


def _g(x):
    """MATLAB sprintf('%g', x)."""
    return f"{x:g}"


def expected_baseline_exports(root):
    """
    Export stems run_baseline_tests() writes with its DEFAULT options, derived from the
    script itself (cases, SNR ladder, seeds, interference list, modulation coverage and
    the o.name patterns), so the expectation follows the script instead of a fixed count.
    """
    with open(os.path.join(root, "simulink", "matlab", "run_baseline_tests.m"), encoding="utf-8") as fh:
        src = fh.read()
    cases = re.findall(r"^\s*'([A-Z])',\s*'[A-Z-]+',", src, re.M)
    seeds = [int(x) for x in _num_list(src, r"opts\.seeds\s*=\s*\[([\d\s]+)\]")]
    ladder = _num_list(src, r"snrLadder = \[([-\d\s.]+)\];")
    plist = _num_list(src, r"pList = \[([-\d\s.]+)\];")
    cov_mods = re.findall(r"'([A-Z-]+)'", re.search(r"covMods = \{([^}]*)\};", src).group(1))
    cov_snr = _num_list(src, r"covSnr\s*=\s*\[([-\d\s.]+)\];")
    chans = re.findall(r"'(\w+)'", re.search(r"chans = \{([^}]*)\};", src).group(1))
    for pat in ("'baseline_%s'", "'ladder_seed%d_snr%d'", "sprintf('interf_p%s'", "'seedrep_%s_%d'",
                "'mod_%s_snr%d_awgn'", "'mod_%s_snr10_rayleigh'"):
        if pat not in src:
            raise ValueError(f"run_baseline_tests.m: export name pattern {pat} changed; update handoff_check.py")
    stems = [f"baseline_{c}" for c in cases]
    stems += [f"ladder_seed{s}_snr{int(k)}" for s in seeds for k in ladder]
    stems += [f"interf_p{_g(p).replace('.', 'p')}" for p in plist]
    stems += [f"seedrep_{c.lower()}_{s}" for c in chans for s in seeds]
    stems += [f"mod_{m.replace('-', '').lower()}_snr{int(k)}_awgn" for m in cov_mods for k in cov_snr]
    stems += [f"mod_{m.replace('-', '').lower()}_snr10_rayleigh" for m in cov_mods]
    return stems


BASELINE_EXPECTED = expected_baseline_exports(project_root)
TABLE_FILES = {"baseline_results"}                       # results tables, not exports
D_EXPECTED = ["D1_model_exists", "D2_model_loads", "D3_is_v3_build", "D3b_has_noise_seed_input",
              "D4_input_format_contract", "D6_noise_power_vs_snr", "D5_phy_reconstructs_x",
              "D7_jam_power_and_independence", "D8_channel_gain_applied", "D9_rx_equals_model_equation",
              "D10_sample_count_and_time", "D11_noiseless_loopback", "D12_ber_sanity",
              "D13_noise_seed_control", "D14_noise_circular_and_independent", "D15_interference_effect",
              "D16_fading_effect", "D17_modulation_identity", "D18_export_contract"]
STEPS = ["environment", "preserve", "create_cognitwin_model", "diagnose_simulink_phy",
         "rayleigh_case", "run_baseline_tests", "manifest"]


# ============================================================== pre-transfer
def matlab_call_graph(root):
    """User .m files reachable from run_v4_validation, by identifier search."""
    files = {os.path.splitext(os.path.basename(p))[0]: p
             for p in glob.glob(os.path.join(root, "simulink", "**", "*.m"), recursive=True)
             if "slprj" not in p}

    def code(p):
        with open(p, encoding="utf-8", errors="replace") as fh:
            return "\n".join(l.split("%")[0] for l in fh.read().splitlines() if not l.lstrip().startswith("%"))

    seen, todo = set(), [RUNBOOK]
    while todo:
        f = todo.pop()
        if f in seen or f not in files:
            continue
        seen.add(f)
        c = code(files[f])
        todo += [n for n in files if n != f and re.search(r"\b%s\b" % re.escape(n), c)]
    return sorted(os.path.relpath(files[f], root).replace("\\", "/") for f in seen)


def transfer_set(root):
    req = matlab_call_graph(root) + ["simulink/cognitwin_sdr_phy.slx"]
    hist = sorted(os.path.relpath(p, root).replace("\\", "/")
                  for p in glob.glob(os.path.join(root, "simulink", "results", "**", "*"), recursive=True)
                  if os.path.isfile(p) and "campaign_fixture" not in p)
    return req, hist


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)


def pre(root):
    req, hist = transfer_set(root)
    tracked = set(_git(root, "ls-files", "simulink").stdout.split())
    dirty = set(l[3:] for l in _git(root, "status", "--porcelain", "--", "simulink").stdout.splitlines())
    head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    branch = _git(root, "branch", "--show-current").stdout.strip()
    lines = [f"# Pre-transfer check - branch {branch} @ {head}", "",
             "| file | present | tracked | committed | sha256 (first 16) |", "|---|---|---|---|---|"]
    ok = True
    for f in req:
        p = os.path.join(root, f)
        present = os.path.isfile(p)
        tr, clean = f in tracked, f not in dirty
        ok &= present and tr and clean
        sha = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] if present else "-"
        lines.append(f"| {f} | {present} | {tr} | {clean} | {sha} |")
    missing_hist = [f for f in hist if f not in tracked]
    lines += ["", f"Historical result files under simulink/results (excluding regenerable fixtures): "
              f"{len(hist)}, untracked: {len(missing_hist)}"]
    ok &= not missing_hist
    lines += ["", f"MATLAB files reachable from {RUNBOOK}.m: {len(req) - 1}",
              f"RESULT: {'READY' if ok else 'NOT READY'}"]
    print("\n".join(lines))
    return 0 if ok else 1


# ============================================================== post-return
def parse_summary(text):
    steps, diags = {}, {}
    for line in text.splitlines():
        m = re.match(r"^  (\w+)\s+(PASS|FAIL)\s*$", line)
        if m:
            steps[m.group(1)] = m.group(2)
        m = re.match(r"^  \[(PASS|FAIL)\] (\S+)\s*(.*)$", line)
        if m:
            diags[m.group(2)] = (m.group(1), m.group(3))
    return steps, diags


def read_manifest(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def latest_log_dir(root):
    dirs = sorted(d for d in glob.glob(os.path.join(root, "simulink", "run_logs", "*")) if os.path.isdir(d))
    return dirs[-1] if dirs else None


def post(root, log_dir=None):
    from src.simulink_bridge.receiver import SimulinkReceiver
    from src.simulink_bridge.validation import MeasurementValidationError, find_shared_noise_realisations
    import numpy as np
    import scipy.io as sio
    import verify_simulink_mat as vsm

    out, ok = [], True

    def item(name, status, detail=""):
        nonlocal ok
        ok &= status == "PASS"
        out.append(f"| {name} | **{status}** | {detail} |")

    log_dir = log_dir or latest_log_dir(root)
    head = ["# Post-return verification (Python)", ""]
    if not log_dir or not os.path.isdir(log_dir):
        head += ["No `simulink/run_logs/<stamp>/` folder found. The MATLAB run has not been returned.", "",
                 "RESULT: NOT VERIFIED"]
        print("\n".join(head))
        return 1
    head += [f"Log folder: `{os.path.relpath(log_dir, root)}`", "", "| check | status | detail |", "|---|---|---|"]

    for f in ("matlab_console.log", "summary.txt", "status.mat", "manifest.csv"):
        item(f"returned: {f}", "PASS" if os.path.isfile(os.path.join(log_dir, f)) else "NOT FOUND")

    steps, diags = {}, {}
    sp = os.path.join(log_dir, "summary.txt")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8", errors="replace") as fh:
            steps, diags = parse_summary(fh.read())
    for s in STEPS:
        item(f"MATLAB step {s}", steps.get(s, "NOT FOUND"))
    for d in D_EXPECTED:
        st, det = diags.get(d, ("NOT FOUND", ""))
        item(("**D13 seed control**" if d.startswith("D13") else d), st, det[:160])

    mp = os.path.join(log_dir, "manifest.csv")
    new = []
    if os.path.isfile(mp):
        rows = read_manifest(mp)
        new = [r for r in rows if r["written_this_run"].strip() == "1"]
        listed = {r["path"].strip('"') for r in new}
        item("manifest: Rayleigh export written this run", "PASS" if RAYLEIGH_FILE in listed else "NOT FOUND")
        miss = [b for b in BASELINE_EXPECTED if f"results/baseline/{b}.mat" not in listed]
        item("manifest: all baseline exports written this run", "PASS" if not miss else "NOT FOUND",
             f"missing: {miss[:6]}{'...' if len(miss) > 6 else ''}" if miss else f"{len(BASELINE_EXPECTED)} files")
        stale = [r["path"] for r in rows if r["written_this_run"].strip() != "1"
                 and r["path"].strip('"').startswith("results/baseline/")]
        item("manifest: no stale file left in results/baseline", "PASS" if not stale else "FAIL",
             f"{len(stale)} stale" if stale else "")

    noise_recs = []
    for r in new:
        rel = r["path"].strip('"')
        stem = os.path.splitext(os.path.basename(rel))[0]
        if stem in TABLE_FILES:
            continue
        local = os.path.join(root, "simulink", *rel.split("/"))
        if not os.path.isfile(local):
            item(f"file {rel}", "NOT FOUND", "listed in manifest but not copied back")
            continue
        try:
            _, rep = SimulinkReceiver.load_and_validate(local, require_real=True, require_model_version="v4")
            phys = [c for c in vsm.verify_mat(local) if c.ok is False]
            item(f"file {rel}", "PASS" if not phys else "FAIL",
                 f"{rep.facts.get('provenance')}, {rep.facts.get('model_version')}, "
                 f"noise_source={rep.facts.get('noise_source', '?')}"
                 + (f"; verifier failed: {[c.name for c in phys]}" if phys else ""))
            mat = sio.loadmat(local)
            if "noise_iq" in mat:
                noise_recs.append((rel, vsm._scalar(mat, "noise_seed"), np.asarray(mat["noise_iq"]).ravel()))
        except MeasurementValidationError as exc:
            item(f"file {rel}", "FAIL", str(exc)[:200])
    if noise_recs:
        shared = find_shared_noise_realisations(noise_recs)
        item("cross-seed noise independence (the v3 defect)", "PASS" if not shared else "FAIL",
             f"{len(noise_recs)} exports; {len(shared)} different-seed pairs share a realisation")
    else:
        item("cross-seed noise independence (the v3 defect)", "NOT FOUND", "no v4 exports available")

    lines = head + out + ["", f"RESULT: {'ALL PASS' if ok else 'NOT VERIFIED / FAILED - see rows above'}"]
    with open(os.path.join(log_dir, "python_verification.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("pre")
    p = sub.add_parser("post")
    p.add_argument("--log-dir", default=None)
    ap.add_argument("--root", default=project_root, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.mode == "pre":
        return pre(args.root)
    return post(args.root, args.log_dir)


if __name__ == "__main__":
    raise SystemExit(main())
