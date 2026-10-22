# MATLAB / Simulink handoff

**Status: BLOCKED. Waiting for a run on a machine with MATLAB and Simulink.**
No v4 Simulink output exists. D1–D18, including D13 seed control, have never executed. The
`cognitwin_sdr_phy.slx` in the repository is the **v3** build: saved by MATLAB R2025a, user
`dhire`, 2026-08-17. Its noise ignored every seed. The development machine has no usable
MATLAB: `C:\Program Files\MATLAB\R2026a` has no `matlab.exe` and no Simulink.

Everything below refers to files that exist at the commit containing this document
(branch `autonomous-completion`). `python experiments/handoff_check.py pre` prints that
commit and fails if any file to transfer is missing, untracked or uncommitted.

---

## 1. Requirements on the MATLAB machine

| need | detail |
|---|---|
| MATLAB + Simulink, licensed | The model was last saved with **R2025a**; a newer release should open it. |
| Toolboxes | **None beyond Simulink.** The call graph uses only Constant, From/To Workspace, Random Number, MATLAB Function and Scope blocks, plus base-MATLAB functions (`erfc`, `rng`, `randn`, `fft`). No Communications or DSP toolbox call. |
| Python | **Not needed there.** Verification runs back on the development machine. |
| Disk | About 25 MB of new outputs, plus the 18 MB archive copy of `simulink/results`. |

---

## 2. Transfer checklist (to the MATLAB machine)

The MATLAB code never references anything outside the `simulink/` folder.

**Option A (preferred): git.** On the MATLAB machine, `git clone <repo>` (or a
`git bundle create cognitwin.bundle autonomous-completion` file) and
`git checkout autonomous-completion`.

**Option B: copy the `simulink/` folder** with exactly these contents:

| # | path | why |
|---|---|---|
| 1 | `simulink/create_cognitwin_model.m` | v4 model generator |
| 2 | `simulink/matlab/run_v4_validation.m` | the one entry point |
| 3 | `simulink/matlab/diagnose_simulink_phy.m` | D1–D18 |
| 4 | `simulink/matlab/run_simulink_case.m` | single run + export |
| 5 | `simulink/matlab/run_baseline_tests.m` | acceptance suite |
| 6 | `simulink/matlab/cognitwin_waveform.m` | BPSK/QPSK/OFDM-QPSK waveforms |
| 7 | `simulink/matlab/cognitwin_measure_ber.m` | demodulation + BER |
| 8 | `simulink/matlab/cognitwin_check_modulation.m` | modulation identity check |
| 9 | `simulink/matlab/cognitwin_gray2bin.m` | Gray mapping |
| 10 | `simulink/matlab/cognitwin_bin2gray.m` | Gray mapping |
| 11 | `simulink/cognitwin_sdr_phy.slx` | v3 model; archived by step 1, then rebuilt |
| 12 | `simulink/results/` (56 files) | historical exports, archived by step 1 before being overwritten |

Items 1–10 are exactly the files reachable from `run_v4_validation.m`, derived from the code by
`handoff_check.py pre`. The other `.m` files in `simulink/matlab` (legacy scripts and v2/v3
backups) are harmless to include but are not used.

**Do not transfer:**
* `*.slxc` and `slprj/`: R2025a build caches, which Simulink regenerates.
* `simulink/results/campaign_fixture/`: 87 MB of git-ignored Python fixtures.

---

## 3. Commands on the MATLAB machine

```matlab
cd <repo>/simulink/matlab
logDir = run_v4_validation
```

The steps of `run_v4_validation` (signature: `logDir = run_v4_validation(noiseSource)`) are
below. Each step records PASS/FAIL on its own, and a failure in one does not hide the rest:

| step | action | aborts the run if it fails? |
|---|---|---|
| 0 | MATLAB version; Simulink installed **and** licensed | yes |
| 1 | **archive** `simulink/results/` and `cognitwin_sdr_phy.slx` → `simulink/results_archive/pre_v4_<stamp>/` | yes, so nothing is overwritten |
| 2 | `create_cognitwin_model` (compiles before saving) | yes, since nothing later can run |
| 3 | `diagnose_simulink_phy(true)`: D1–D18 | no |
| 4 | `run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')` | no |
| 5 | `run_baseline_tests()`: sections 1–7 | no |
| 6 | `manifest.csv`: every MAT under `results/` with `written_this_run` 0/1 | no |

If step 2 fails with a Random Number block error, run the alternative noise source:

```matlab
logDir = run_v4_validation('block_rng')
```

Do not edit `create_cognitwin_model.m` on the MATLAB machine. Return the log instead, so the
failure is reproduced from the committed sources.

### Optional: Simulink in the closed loop (after `run_v4_validation` passes)

```matlab
loop = run_simulink_closed_loop            % default 10-step schedule, AWGN; see `help run_simulink_closed_loop`
loop = run_simulink_closed_loop(struct('channel', 'Rayleigh', 'python', 'C:\path\to\venv\Scripts\python.exe'))
```

Each step simulates the modulation chosen at the previous step. MATLAB then calls
`python experiments/acwra_decide.py --require-real` on the new export: the Python agents
and ACWRA decide, and the Digital Twin's history is carried in `twin_state.json`. Unlike
the runbook, this step **needs Python on the MATLAB machine** with
`requirements-lock.txt` installed, plus the repository's `src/`, `experiments/` and
`results/ai/modulation_classifier/rf_model_mixed.joblib`. Option A (git) covers that.
Output: `simulink/results/closed_loop/<stamp>/` (`step_###.mat`, `decision_###.json`,
`twin_state.json`, `loop_log.csv`, `console.log`). Return that folder too.

---

## 4. Expected output files (to return)

`<stamp>` is the run's timestamp, `yyyymmdd_HHMMSS`, printed as `logDir`.

| path | content |
|---|---|
| `simulink/run_logs/<stamp>/matlab_console.log` | everything printed during the run |
| `simulink/run_logs/<stamp>/summary.txt` | step PASS/FAIL table + **D1–D18 table (D13)** |
| `simulink/run_logs/<stamp>/status.mat` | `st` (steps) and `report` (diagnostics) structs |
| `simulink/run_logs/<stamp>/manifest.csv` | every MAT under `results/` (paths relative to `simulink/`), `written_this_run`, `model_version`, `noise_source`, `run_id` |
| `simulink/results_archive/pre_v4_<stamp>/` | the copy of `results/` and the v3 `.slx` taken before anything was overwritten |
| `simulink/cognitwin_sdr_phy.slx` | the rebuilt v4 model |
| `simulink/cognitwin_sdr_phy_backup_<ts>.slx` | the generator's own backup of the v3 model |
| `simulink/results/sim_qpsk_snr10_int0p25_rayleigh.mat` | the QPSK / 10 dB / 0.25 / Rayleigh export |
| `simulink/results/baseline/*.mat` (43 exports) | 6 cases A–F, 15 ladder, 8 interference, 6 seed-rep, 8 modulation-coverage (`mod_*`) |
| `simulink/results/baseline/baseline_results.mat`, `.csv` | the baseline SUMMARY table |

If a step fails, some of these will not exist. Return whatever was produced, always
including the whole `run_logs/<stamp>/` folder.

Copying the returned `simulink/results/` over the development checkout replaces the v3 files
in the working tree. They remain recoverable from git and from
`results_archive/pre_v4_<stamp>/`.

---

## 5. Verification after return (development machine, repository root)

```bash
python experiments/handoff_check.py post
```
```bash
python experiments/verify_simulink_mat.py --dir simulink/results/baseline
```
```bash
python experiments/verify_simulink_mat.py --mat simulink/results/sim_qpsk_snr10_int0p25_rayleigh.mat
```
```bash
python experiments/simulink_acwra_demo.py --mat simulink/results/sim_qpsk_snr10_int0p25_rayleigh.mat --require-real
```
```bash
python -m pytest -q
```

`handoff_check.py post` reads the newest `simulink/run_logs/<stamp>/` (or `--log-dir`). For
every step, every D-check (D13 highlighted) and every file the manifest marks as written by
the run, it reports PASS / FAIL / NOT FOUND. Each such file must load with
`require_real=True, require_model_version="v4"` and pass the independent verifier. It also
checks noise independence across seeds. It writes `python_verification.md` into the log
folder and exits 0 only if everything passed.

Python requirements: `pip install -r requirements.txt`. The default classifier
(`rf_model_mixed.joblib`) was saved with scikit-learn 1.7.2; another version may warn
when loading it.

### Success criteria

| evidence | criterion |
|---|---|
| steps 0–6 | all PASS |
| **D13** | same seed reproduces noise and jammer exactly; a different seed gives \|corr\| < 5/√N |
| D1–D18 | all PASS |
| Rayleigh export | `checks_passed = 1`, `model_version = 'v4'`, MATLAB-written |
| baseline | no FAIL rows; sections 6 and 7 present and PASS |
| manifest | the Rayleigh file and all 43 baseline exports `written_this_run = 1`; no stale baseline file |
| `handoff_check.py post` | `RESULT: ALL PASS` |

---

## Not covered

* Simulink in the closed loop: ACWRA decisions are applied only in the Python virtual-RF
  environment.
* Time-varying (Doppler) fading: Simulink fading is one gain per run.
