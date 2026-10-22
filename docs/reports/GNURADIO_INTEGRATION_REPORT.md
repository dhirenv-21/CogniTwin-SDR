# CogniTwin-SDR: GNU Radio physical-layer integration report

**Overall status: PARTIAL.** GNU Radio is now installed and executing. Results: the
flowgraph runs for BPSK, QPSK and OFDM-QPSK; all 12 execution tests pass; the BER validation
passes 18/18 points against theory. The Spectrum Agent evaluation, the headless demo and the campaign **smoke test** also ran. **Not yet run:** the
GRC GUI. The full campaign has now run (below).

Branch `autonomous-completion` (`master` untouched). Base commit of this phase: `6d9d9a4`.

## 1. Environment (Phase 0, measured)

| item | finding |
|---|---|
| OS | Windows 11 Home Single Language 10.0.26200, 64-bit, ~353 GB free |
| Python | 3.10.11 (user install, `%LOCALAPPDATA%\Programs\Python\Python310`) |
| GNU Radio / GRC / bindings | **absent**: `import gnuradio` → ModuleNotFoundError; no `gnuradio-companion`, `grcc`, `gnuradio-config-info` |
| package managers | no conda / mamba / micromamba / docker; `wsl.exe` present but WSL not installed |
| SDR hardware | none detected (not needed) |
| headless | yes (matplotlib Agg); QT GUI not testable without GNU Radio |
| tests at start | 432 passed |
| install route chosen | separate conda environment (radioconda or Miniforge + conda-forge `gnuradio=3.10`), per the radioconda / conda-forge distribution; not executed (download needs approval) |

## 2. Status per item

| # | item | status | evidence |
|---|---|---|---|
| 1 | flowgraph executed | **PASS** | GNU Radio 3.10.12.0 (radioconda 2025.03.14, env `cognitwin-gr`) |
| 2 | modulations | BPSK, QPSK, OFDM-QPSK **implemented** (`src/gnuradio_phy/flowgraph.py`); not executed | static checks: every signal-processing step is a GNU Radio block |
| 3 | channels | AWGN; block Rayleigh/Rician (`multiply_const_cc`); time-varying Rayleigh/Rician (`channels.fading_model` + gain-capture twin); Gaussian jammer; **implemented, not executed** | — |
| 4 | I/Q export | **PASS (format)**: NPZ in the bridge schema + GNU Radio metadata, content hash, ledger; tested on stand-ins | `tests/test_gnuradio_export_validation.py` (23) |
| 5 | SNR / BER validation vs theory | **PASS**: 18/18 points, reproducibility, jammer power | `results/gnuradio/ber_validation/ber_20261022_v1/` |
| 6 | bridge / provenance | **PASS** (logic): `gnuradio_export` requires 8 evidence items, and the label alone never counts; corrupted, truncated, empty, pickled, NaN/Inf, edited and incompatible files rejected | 23 tests; a complete forgery passes (documented limitation) |
| 7 | Spectrum Agent on GNU Radio I/Q | **PASS (executed)**: accuracy 0.859, ECE 0.051; PSK blind SNR biased about -4.9 dB under time-varying fading; target-leakage guard tested (label changes do not change detection); interference is passed through, not estimated (existing design, now documented) | `experiments/gnuradio_spectrum_eval.py` |
| 8 | agent integration | **PASS on stand-ins**: validation → Spectrum → Twin → Prediction → Cyber Defense → ACWRA, trace; invalid input raises before any agent | `test_valid_export_reaches_acwra…`, `test_invalid_export_never_becomes_a_decision` |
| 9 | ACWRA | **unchanged** (no edits to `src/acwra/`); units converted at the interface (noise-only Es/N0 from `noise_iq`) | existing 35 ACWRA tests still pass |
| 10 | baselines | fixed BPSK / QPSK / OFDM-QPSK, SINR threshold (measured SINR), no-adaptation (decides, never actuates) **implemented** | `tests/test_gnuradio_closed_loop.py` (10) |
| 11 | closed loop | **PASS (logic, stand-in PHY)**: decision of episode e applied to e + 1 only; nothing retroactive; paired seeds; provenance recorded per episode. **NOT RUN** on GNU Radio | same file |
| 12 | GRC demo | headless demo **executed**; GRC GUI **static only**: `grc/cognitwin_phy_demo.grc` (time, frequency and constellation sinks; SNR and jammer sliders); never opened in GRC. Headless fallback `experiments/gnuradio_demo.py` | `tests/test_gnuradio_static.py` |
| 13 | campaign | **executed**: smoke (72 runs) and GR-CL-1 full (4,860 runs, `grcl1_20261022_v2`); `experiments/gnuradio_campaign.py` (27 conditions × 5 seeds × 6 policies, distinct experiment IDs, condition-level paired statistics) | — |
| 14 | tests | system Python: **507 passed, 12 skipped**. GNU Radio env: **513 passed, 6 skipped** (the 6 'GNU Radio absent' checks); all 12 execution tests PASS | `python -m pytest -q -rs` |

## 3. Research results

**GNU Radio PHY validation (executed; `results/gnuradio/ber_validation/ber_20261022_v1/`).**
Data class: GNU Radio 3.10.12.0 software simulation, no hardware. Setup: AWGN, 3 seeds x 65,536
symbols per point.
* BER vs theory: 18/18 points PASS. Pass rule: theory inside the 99.9 % Wilson interval
  widened 10 % for RRC truncation ISI. The points cover BPSK at Es/N0 -2...8 dB and
  QPSK / OFDM-QPSK at 0...10 dB. Example: QPSK at 10 dB measured 8.70e-4
  [7.28e-4, 1.04e-3] vs theory 7.83e-4.
* Same seed gives identical samples. With different seeds, the noise correlation is 0.009,
  below the 5/sqrt(N) = 0.055 bound.
* Jammer: measured power 0.1003 for J = 0.1.
* Time-varying fading (`fading_model`, fD*Ts = 1e-3), gain capture OK:
  * Rayleigh: one run of 8,192 bits, BER 3.54e-3 vs conditional theory 2.84e-3.
  * Rician: BER 5.13e-3 vs 5.37e-3.
  * Not judged statistically: single runs with ~25-40 errors.

None of this validates Simulink v4.

**Spectrum Agent on GNU Radio I/Q (executed; `results/gnuradio/spectrum_eval/spec_20261022_v1/`).**
The existing agent was not changed. Inputs: 6,912 windows of 512 samples; GNU Radio seeds >= 500000, never used in
training; Es/N0 -5...20 dB; four impairments (AWGN, block Rayleigh, time-varying Rayleigh with fD*Ts 1e-4, jammer J 0.1).
* Accuracy 0.859, ECE 0.051. The previous synthetic evaluation gave 0.944 / 0.017; the GNU Radio data is out of
  distribution for the classifier.
* Per class (P / R / F1):
  * BPSK 0.999 / 0.911 / 0.953
  * QPSK 0.968 / 0.727 / 0.830
  * OFDM-QPSK 0.747 / 0.938 / 0.832
* Dominant error: QPSK labelled OFDM-QPSK (572 of 2,304 windows). This is the same confusion as on synthetic
  data, but larger.
* Accuracy by condition:
  * AWGN: 0.97-0.99 at >= 5 dB, 0.64 at -5 dB.
  * Block Rayleigh: 0.56 at 0 dB and 0.35 at -5 dB. Here the nominal Es/N0 overstates the faded SINR.
  * Time-varying Rayleigh: 0.91-0.93 at >= 10 dB.
* Blind SNR, windows with true SINR >= 5 dB:
  * Bias within +/-0.12 dB in AWGN, block fading and with the jammer (MAE: PSK 0.18-0.26 dB, OFDM 0.50-0.58 dB).
  * **New finding:** under time-varying fading the PSK estimate is biased by about -4.9 dB (MAE 4.9 dB). The M2M4
    estimator assumes a constant envelope within the window, so the gain variation reads as noise. The OFDM
    estimator (CP-based) is unaffected (-0.12 dB).
* False SNR_DROP rate on stationary AWGN: 0.46 %.
* Interference power is passed through by the agent, not estimated, so it is not evaluated.

**Headless demo (executed; `results/gnuradio/demo/20261022T213739/`).** QPSK, AWGN, Es/N0 8 dB, J 0.05.
* Export validated as `gnuradio_export` (44 pass, 0 fail).
* Measured Es/N0 8.15 dB, J 0.0507. BER 0.0129 (106/8,192) vs theory 0.0143. PER 0.906.
* Spectrum Agent: QPSK at confidence 1.00, blind SNR 6.53 dB (the SINR is 6.8 dB).
* Twin SNR 8.39 dB from `noise_iq`. Risk 0.25 (LOW). ACWRA: Keep Current.
* The 6-episode loop is illustrative only (one condition, one seed).

**Campaign smoke test (executed; `results/gnuradio/campaign/smoke/`).** 2 conditions x 1 seed x 6 policies x 6
episodes = 72 flowgraph runs; every episode validated as `gnuradio_export`. Too small for inference (Wilcoxon not
computed; 2 conditions).

| policy | goodput kb/s | BER | PER |
|---|---|---|---|
| sinr_threshold | 92.7 | 0.0069 | 0.331 |
| fixed_BPSK | 71.9 | 0.0019 | 0.281 |
| acwra | 71.4 | 0.0144 | 0.643 |
| fixed_QPSK / no_adaptation | 71.4 | 0.0144 | 0.643 |
| fixed_OFDM-QPSK | 54.2 | 0.0140 | 0.661 |

**ACWRA never switched, so it was identical to fixed QPSK.**
* Root cause, from the recorded episodes: under the jammer (J 0.3, BER 0.043) the Prediction Agent's risk stayed
  LOW (0.33-0.34).
* The Spectrum Agent compares SNR between consecutive windows within an episode, so it raised no SNR_DROP anomaly.
* The Cyber Defense Agent then offers only "Keep Current", so ACWRA had nothing else to choose.
* This is the risk-gating effect already found in the CL-2 ablation (`acwra_all_candidates`). The agents are left
  unchanged; this is reported, not tuned away.
* In this smoke test the SINR-threshold rule had the highest goodput, consistent with the virtual-RF finding.

**Full closed-loop campaign GR-CL-1 (executed; `results/gnuradio/campaign/grcl1_20261022_v2/`, commit `87b74b8`).**
27 conditions x 5 seeds x 6 policies x 6 episodes = 4,860 GNU Radio flowgraph runs, all validated as
`gnuradio_export`. Statistics are condition level (seeds averaged; 95 % bootstrap CI over conditions; Wilcoxon);
the full tables are in `analysis.md` (`experiments/gnuradio_campaign_analysis.py`). The first attempt
`grcl1_20261022` aborted on a deep-fade timing check (see its `ABORTED.md`).

| ACWRA - baseline (27 conditions) | goodput kb/s [95 % CI] | p | BER [95 % CI] | p |
|---|---|---|---|---|
| SINR threshold | -7.2 [-15.4, +0.1] | 0.13 | +0.0061 [+0.0036, +0.0089] (ACWRA worse, 17/8/2) | 5e-5 |
| fixed QPSK (= no_adaptation) | +0.6 [-2.0, +3.0] | 0.32 | -0.0098 [-0.0153, -0.0048] (ACWRA better) | 4e-4 |
| fixed BPSK | +14.4 [-3.2, +32.2] | 0.15 | +0.0158 (ACWRA worse, 26/1/0) | 3e-8 |
| fixed OFDM-QPSK | +14.4 [+9.7, +19.3] (24/2/1) | 2e-5 | -0.0099 (ACWRA better) | 0.003 |

Policy means: SINR threshold 77.1 kb/s / BER 0.036; ACWRA 70.0 / 0.042; fixed QPSK 69.3 / 0.052;
fixed BPSK 55.5 / 0.026; fixed OFDM-QPSK 55.5 / 0.052.

* **ACWRA does adapt on GNU Radio:** in 132 of 810 decisions it selected BPSK, at low SNR and under Rayleigh fading. It
  never chose OFDM-QPSK. "Keep Current" made up 678 decisions, because the risk gate stays shut at risk < MEDIUM
  (risk median 0.25, max 0.76).
* **The negative finding replicates on GNU Radio.** The a-priori SINR-threshold rule has lower BER than ACWRA
  (significant, p = 5e-5). It also has higher mean goodput, but that difference is not significant (CI crosses 0).
  ACWRA beats fixed QPSK on BER and fixed OFDM-QPSK on goodput. No superiority claim is made.
* `no_adaptation` equals `fixed_QPSK` exactly, as expected: the initial modulation is QPSK and is never changed.
* Classifier inside the loop: 772 of 810 ACWRA episodes were detected correctly; 32 were labelled OFDM-QPSK and 6 UNKNOWN.
* Only 3 dynamic schedules exist, too few for a Wilcoxon test.

Note: in `paired.csv`, wins / ties / losses count the sign of (ACWRA - baseline). For BER a "win" therefore means
ACWRA had the **higher** (worse) BER. The existing
results keep their provenance and their negative findings: virtual-RF CL-2 (an a-priori
SINR-threshold rule beat ACWRA on goodput **and** BER in the 30-condition sweep), the twin's
trend forecast losing to persistence on steps, and historical Simulink v3 QPSK BER matching
theory. GNU Radio results, when they exist, will not validate the unexecuted Simulink v4
model.

## 4. Defects found during this phase

**Environment.** The first, unpinned environment (Python 3.14.9, NumPy 2.5.4, MKL 2026.2 with a
cached package reported invalid) crashed the interpreter in `numpy.polyfit` (0xc06d007f) in a
pre-existing Digital Twin test. Recreating it with Python 3.12, NumPy 2.2 and OpenBLAS fixed it.
This was not a project defect, so no code changed.

**Folder shadowing.**

The `.grc` file was first placed in a top-level `gnuradio/` folder. On `sys.path` this
becomes a namespace package and hides the real GNU Radio: the full test run reported
"cannot import name 'gr' from 'gnuradio'". Renamed to `grc/`; regression test
`test_no_repository_folder_shadows_the_gnuradio_package`.

## 5. Changed / added files

* `src/gnuradio_phy/`: `__init__.py`, `availability.py`, `config.py`, `flowgraph.py` (the only
  module importing GNU Radio), `receiver.py`, `export.py`, `validation.py`, `runner.py`,
  `closed_loop.py`
* `experiments/`: `gnuradio_common.py`, `gnuradio_phy_run.py`, `gnuradio_ber_validation.py`,
  `gnuradio_spectrum_eval.py`, `gnuradio_campaign.py`, `gnuradio_demo.py`
* `grc/cognitwin_phy_demo.grc`
* `tests/`: `gr_test_helpers.py`, `test_gnuradio_units.py`, `test_gnuradio_export_validation.py`,
  `test_gnuradio_closed_loop.py`, `test_gnuradio_execution.py`, `test_gnuradio_static.py`
* docs: `docs/GNURADIO_SETUP.md` (new), `docs/ARCHITECTURE.md`, `docs/DATA_SCHEMA_PROVENANCE.md`,
  `README.md`, `AUTONOMOUS_PROGRESS.md`, `AUTONOMOUS_TEST_REPORT.md`, `.gitignore`
* not changed: ACWRA, Digital Twin, agents, Simulink bridge code, MATLAB sources and docs,
  `MATLAB_HANDOFF.md`, every historical result

## 6. Resume (external requirement: a GNU Radio 3.10 environment)

Done: radioconda installed, env created with:

```bash
mamba create -n cognitwin-gr -c conda-forge python=3.12 numpy=2.2 scipy=1.15 "libblas=*=*openblas" gnuradio=3.10.12 scikit-learn=1.7.2 matplotlib joblib pytest pyyaml
mamba activate cognitwin-gr
python -m pytest -q -rs
python experiments/gnuradio_ber_validation.py
python experiments/gnuradio_spectrum_eval.py
python experiments/gnuradio_demo.py
python experiments/gnuradio_campaign.py --smoke
python experiments/gnuradio_campaign.py --run-id grcl1_<date>
gnuradio-companion grc/cognitwin_phy_demo.grc
```

The code was written against the GNU Radio 3.10 API without being run. The first
execution may expose API mismatches; `tests/test_gnuradio_execution.py` and the BER
validation are the acceptance gates.
