# CogniTwin-SDR — final completion report

**Overall status: PARTIAL.** Every Python-side component is implemented, tested, evaluated and
reproducible. The real MATLAB/Simulink v4 validation is **BLOCKED**: no machine with MATLAB +
Simulink was available. It is prepared and checked statically, but it has never executed.
The project is not complete until it runs.

Branch `autonomous-completion` (`master` untouched at `6ba32c1`). Checkpoint tag before this phase:
`checkpoint-pre-final-completion` (= `bae5701`). Final test run: **432 passed, 0 failed, 0 skipped**.

## Abstract

CogniTwin-SDR couples a MATLAB/Simulink baseband physical layer (BPSK, QPSK, OFDM-QPSK over
AWGN / block Rayleigh / Rician with a Gaussian jammer) to a Python agent stack. Exported I/Q
measurements are validated (schema, physics consistency, MATLAB-vs-Python provenance) and
passed through a Spectrum Agent (Random-Forest modulation classifier plus a blind M2M4 /
cyclic-prefix SNR estimator). The stack continues through a Digital Twin (state history,
linear trend forecast, counterfactual sandbox), a Prediction Agent (risk score), a Cyber Defense
Agent (risk-gated candidate actions) and the ACWRA multi-objective decision rule, which selects
the next modulation. In a closed loop over a Python virtual-RF environment, ACWRA is
consistently more BER-averse than throughput-oriented baselines. A simple a-priori SINR
threshold rule nevertheless achieves both higher goodput and lower BER across a 30-condition
sweep. All physical-layer statements rest on historical Simulink v3 exports; the seeded v4
model has not been executed.

**Contribution statement (scope-limited).** This repository contributes an implemented and
tested reference pipeline from Simulink I/Q exports to an explainable adaptation decision. It
has explicit provenance control, a reproducible closed-loop evaluation protocol with ablations,
and documented negative results. No literature search was performed in this work, so **no
novelty claim is made**.

## MATLAB / Simulink levels (each assessed separately)

| level | status | evidence |
|---|---|---|
| 1 static source inspection | **PASS** | `tests/test_matlab_static_contract.py` (28), `tests/test_handoff_check.py` (10): call graph, export schema ↔ Python readers, port order, archive-before-overwrite, per-step try/catch, path quoting, structural lint of every `.m` |
| 2 MATLAB parsing | **NOT RUN** | no MATLAB on this machine (`C:\Program Files\MATLAB\R2026a` has no `matlab.exe`, no `toolbox/matlab`) |
| 3 Simulink model compilation (v4) | **NOT RUN** | — |
| 4 simulation, D1–D18, **D13** | **NOT RUN** | — |
| 5 valid v4 exports | **NOT RUN** | no file with `model_version = 'v4'` exists |
| 6 Python ingestion of exports | **PASS for historical v3 / NOT RUN for v4** | 37 healthy v3 exports pass validation (power error < 0.3 dB); the 2 broken v2 exports are rejected; `acwra_decide.py --require-real` produced decisions from real v3 files |
| 7 Simulink closed loop | **NOT RUN** | `run_simulink_closed_loop.m` + `acwra_decide.py` implemented; Python side tested on fixtures and real v3 files |
| 8 scientific evaluation on Simulink | **PARTIAL** | v3 QPSK BER matches theory over −10 … +11 dB SINR (historical); BPSK/OFDM and v4 not evaluated |

Rayleigh in Simulink is **one complex gain per run** (a static realisation per export; block
fading across runs). In virtual RF it is **one gain per 0.1 s block**. Neither is time-varying
within a block. The research claims below do not depend on intra-block fading. Doppler fading
is listed as future work rather than implemented unverifiably.

## Acceptance criteria

| | criterion | status | evidence |
|---|---|---|---|
| A | clean repo, master untouched, deps documented, no secrets / big caches | **PASS** | `git log master` = `6ba32c1`; `requirements-lock.txt`; 87 MB fixtures git-ignored; generated step logs gzipped |
| B | Python tests pass, no known critical integration defect, error handling tested, reproducibility verified | **PASS** | 432/432; reproduction `results/reproductions/20261022T172510/REPRODUCTION.md`: all MATCH; CL-1 reproduced bit-for-bit (180 episodes); classifier `--check` exact |
| C | ACWRA equations match docs, hand-calculated tests, units documented, invalid inputs rejected, tie/switch rules documented | **PASS** | `docs/acwra_algorithm.md` specification + worked example; `tests/test_acwra_validation.py` (25) |
| D | Simulink builds/runs, D1–D18 + D13 evidence, valid exports, baselines, Python consumption | **BLOCKED** | see table above |
| E | signal → decision demonstrated, action affects the next step, provenance kept, full trace recorded | **PASS (virtual RF and historical Simulink exports) / NOT RUN (live Simulink loop)** | `experiments/review_demo.py`; `tests/test_closed_loop.py` (one-step delay, paired fades, orchestrator equivalence) |
| F | fair baselines, reproducible metrics, limitations disclosed, no fabricated claims | **PASS** | `docs/EXPERIMENT_PROTOCOL.md` committed before the sweep; `results/evaluation/RESEARCH_EVALUATION.md` |
| G | documentation complete, instructions work, demo reproducible, completion report | **PASS** | README quick-start commands executed (pytest, `review_demo.py` with and without `--fixture`, `reproduce_python_results.py --quick`); `pip install -r requirements-lock.txt` not re-run here (versions verified installed); `docs/`, `MATLAB_HANDOFF.md`, this report |

## Defects found and fixed in this phase (each with a regression test)

1. **Virtual-RF jammer / fading model (root cause of saturation).** BER + 0.15·J, packet loss + 0.10·J,
   BER × 3.5 for any fading. Replaced by `src/virtual_rf/link_model.py`: SINR = g/(N0+J), exact
   BER, expected BER over the true fading distributions, realised block fades per step.
   (`tests/test_link_model.py`, 26 tests: analytical, numerical-integration and Monte-Carlo
   references.)
2. **SNR double counting in the bridge.** The twin received the measured SINR, and the sandbox
   then added J again. It now receives P_tx/P_noise from `noise_iq`, or the configured SNR,
   labelled `nominal`.
3. **Broken v2 exports accepted as real.** Their self-declared |h| made the signal-presence
   check skip itself. New required `rx_power_matches_configuration` check (12.8 / 8.0 dB
   mismatch).
4. **False `SNR_DROP` alarms.** 20–26 % on stationary PSK at 0 dB, from estimates flipping
   between ~0 dB and the −10 dB floor. Comparison now clipped at the 1 dB resolution limit →
   0 %.
5. **ACWRA with no candidates.** Raised `IndexError` deep inside; now a clear `ValueError`.
6. **Hard-coded handoff expectations.** Now derived from `run_baseline_tests.m` (43 exports
   today).
7. **Non-portable run manifest and apostrophe-unsafe build path** (earlier this session).
8. **`runner` aggregation bug**, found by the smoke test before the main run.

## Evaluation results (all PYTHON; provenance per line)

* **Spectrum Agent** (synthetic, 5,760 seed-disjoint windows; `results/ai/spectrum_eval/`):
  accuracy 0.944, ECE 0.017, QPSK recall 0.811 (confused with OFDM-QPSK). Blind SNR at
  ≥ 5 dB: PSK |bias| ≤ 0.12 dB; OFDM ≤ 0.75 dB. Unresolved below ~0 dB by design (floor).
* **Classifier retraining** (synthetic): as served, 0.950 / 0.950 / 0.942 against the
  original 0.677 / 0.519 / 0.316 (tiled / stream / impaired).
* **Digital Twin forecasting** (virtual RF; `results/digital_twin/forecast_eval/`): on step
  scenarios the twin trend MAE is 4.06 dB, persistence 2.14 dB and change-point trend 2.27 dB.
  On the ramp: twin 0.57 dB, persistence 1.64 dB. Alternatives reported, not adopted.
* **Closed loop CL-1** (old model, `run_20261022_v1`, reproduced exactly): ACWRA against the
  best fixed modulation: 0 W / 20 T / 10 L.
* **Closed loop CL-2** (new model, `cl2_20261022`, commit `2a38917`, 2,310 episodes,
  condition-level paired statistics):

| suite | ACWRA − baseline | Δ goodput kb/s [95 % CI], W/T/L | Δ BER |
|---|---|---|---|
| original (6 cond × 10 seeds) | fixed QPSK | −10.6 [−18.1, −3.7], 0/0/6 | −0.026 (ACWRA lower) |
| original | SINR threshold | −10.5 [−17.6, −3.8], 0/0/6 | −0.0008 |
| sweep (30 cond × 5 seeds) | fixed QPSK | −4.5 [−10.7, +0.5], 11/10/9 | −0.021 (ACWRA lower) |
| sweep | SINR threshold | −12.2 [−19.7, −5.5], 1/3/26, p = 8·10⁻⁶ | +0.011 (ACWRA higher) |
| sweep | oracle | −16.9 [−24.1, −10.7], 0/4/26 | +0.013 |

  **Conclusion supported by the data:** ACWRA trades goodput for BER relative to fixed QPSK,
  but in the sweep it is dominated by an a-priori SINR threshold rule on both primary outcomes.
  No superiority claim is made.
* **Ablations** (CL-2):
  * The confidence terms change no decision (0 differences in 36 conditions).
  * Prediction (and history) lowers BER in the sweep (−0.0156, 0/16/14), at no significant
    goodput change.
  * The risk-gated candidate set costs goodput in the original suite (−3.9 kb/s, 0/0/6) and
    raises BER in the sweep.
* **Historical Simulink v3**: QPSK BER on theory across −10 … +11 dB measured SINR. The
  noise was identical across seeds.

## Remaining limitations

* v4 Simulink never executed: D1–D18, D13, the v4 baseline (sections 6–7: BPSK, OFDM-QPSK,
  cross-seed noise) and the Simulink loop are all NOT RUN.
* Closed-loop metrics use the twin's own link model: decision logic only, with no physical
  validation and no switching cost.
* AWGN conditions are deterministic given the decisions, so seeds add variance only through
  fading and observations.
* The classifier and the SNR estimator are evaluated on synthetic signals from the training
  generator family.
* `DigitalTwinState.threat_condition` is a heuristic label on interference power, not attack
  attribution.
* No literature review; no novelty claim.

## Reproduce

```bash
pip install -r requirements-lock.txt
python -m pytest -q                                   # 432 passed
python experiments/review_demo.py                     # demo (historical real v3 export + virtual RF loop)
python experiments/reproduce_python_results.py        # full re-run into new folders, MATCH/DIFFER
python experiments/research_evaluation.py             # report from saved outputs
python experiments/handoff_check.py pre               # READY
```

## On the MATLAB machine (`MATLAB_HANDOFF.md`)

```matlab
cd <repo>/simulink/matlab
logDir = run_v4_validation          % archive -> build v4 -> D1-D18 -> QPSK/10 dB/0.25/Rayleigh -> baseline -> manifest
loop   = run_simulink_closed_loop   % optional; needs Python + requirements-lock.txt on that machine
```

Return `simulink/run_logs/<stamp>/`, `simulink/results/`, `simulink/results_archive/pre_v4_<stamp>/`
and `simulink/cognitwin_sdr_phy.slx` (plus `simulink/results/closed_loop/<stamp>/` if run), then:

```bash
python experiments/handoff_check.py post
```

## Single highest-priority next action

Run `run_v4_validation` on a machine with MATLAB + licensed Simulink, return the artifacts, and
run `python experiments/handoff_check.py post`. D13 decides whether the v4 noise seeding works.
