# Autonomous Test Report — CogniTwin-SDR

Latest run: `python -m pytest -q -rs` → **507 passed, 0 failed, 12 skipped** (2026-10-22,
branch `autonomous-completion`, GNU Radio phase). The 12 skips are
`tests/test_gnuradio_execution.py`: GNU Radio is not importable here, and the skip reason
carries the import error. They are **NOT RUN**, not passes. In the GNU Radio environment (`cognitwin-gr`, see
`docs/GNURADIO_SETUP.md`): **513 passed, 6 skipped**. The 6 skips are the checks that only apply
when GNU Radio is absent; all 12 execution tests pass. History: 181 → 369 → 377 → 432 → 507.

## GNU Radio phase additions (75 tests + 12 skipped)

| file | n | category | proves | does NOT prove |
|---|---|---|---|---|
| test_gnuradio_units | 30 | unit | config/seed/hash rules, Gray mapping, analytical BER (BPSK 1e-5 at 9.59 dB, QPSK = BPSK + 3.01 dB), receiver timing/equaliser/BER arithmetic on a NumPy stand-in | anything about GNU Radio blocks |
| test_gnuradio_export_validation | 23 | bridge / validation | NPZ round trip; corrupted, truncated, empty, pickled, NaN/Inf, edited, inconsistent and incompatible files rejected; label-only and partial forgeries never `gnuradio_export`; invalid export never reaches ACWRA; no modulation-label leakage | that real GNU Radio exports validate |
| test_gnuradio_closed_loop | 10 | fixture integration | one-episode actuation delay, nothing retroactive, paired seeds, no-adaptation never actuates, provenance recorded as fixture, invalid episode stops the loop, no silent substitution without GNU Radio | GNU Radio loop results |
| test_gnuradio_static | 12 | static | only `flowgraph.py` imports GNU Radio; the signal chain uses GNU Radio blocks; scripts compile and exit BLOCKED; GRC structure and constellation match Python; no folder shadows `gnuradio` | that GRC opens the file |
| test_gnuradio_execution | 12 | **GNU Radio execution** | in env `cognitwin-gr` (GNU Radio 3.10.12.0): **12/12 PASS**. Flowgraphs run for 3 modulations; AWGN BER inside 99.9 % Wilson of theory; jammer; seed reproducibility; block + time-varying fading; export validates as `gnuradio_export` and reaches ACWRA; closed loop | Spectrum Agent accuracy, campaign results |
With `-W default` there are 4 `ResourceWarning`s, all in the pre-existing
`tests/test_phy_regression.py`; that file is left untouched.

## By category

| category | status | tests | proves | does NOT prove |
|---|---|---|---|---|
| Python unit | PASS | 161 | components behave as specified on synthetic inputs; ACWRA hand-calculated; link model vs analytical / quadrature / Monte Carlo | anything about Simulink |
| Bridge / validation (in-memory & fixture MAT) | PASS | 143 | malformed, inconsistent, stale and mislabelled input rejected; provenance from header + label | that v4 exports are valid |
| Fixture-based integration | PASS | 90 | signal → agents → twin → ACWRA wiring, time alignment, one-step actuation, paired episodes, demo labelling, decider CLI | that a live Simulink loop ran |
| Static MATLAB | PASS | 38 (+12 source checks in other files) | `.m` sources agree with each other and with Python; runbook ordering; derived handoff expectations; path quoting; structural lint | that MATLAB parses or runs them |
| Real Simulink export (pytest) | PASS | 6 (inside the categories above) | historical v3 exports are MATLAB-written, physically consistent, ingested and decided on; v2 exports rejected | anything about v4 |
| **Actual MATLAB / Simulink execution** | **BLOCKED** | 0 | — | — |

161 + 143 + 90 + 38 = 432.

## Per file

| file | n | category |
|---|---|---|
| test_signal / test_analog_modulation / test_digital_modulation / test_ofdm_mimo / test_modulation_classifier / test_virtual_rf / test_digital_twin / test_agents / test_acwra | 4/6/4/4/4/5/5/4/4 | unit (pre-existing) |
| test_acwra_stress | 10 | unit (pre-existing) |
| test_acwra_validation | 25 | unit |
| test_digital_twin_validation | 22 | unit |
| test_spectrum_agent_validation | 38 | unit |
| test_link_model | 26 | unit |
| test_simulink_bridge | 6 | bridge (pre-existing) |
| test_phy_regression | 47 | bridge + 5 static (pre-existing) |
| test_phy_v4_validation | 39 | bridge + 7 static + 1 real-file |
| test_bridge_provenance_robustness | 51 | bridge + 4 real-file |
| test_simulink_acwra_integration | 39 | fixture integration (pre-existing) |
| test_pipeline_alignment_integration | 15 | fixture integration |
| test_closed_loop | 13 | fixture integration (virtual RF) |
| test_robustness | 13 | fixture integration |
| test_simulink_closed_loop | 7 | 3 static MATLAB + 4 fixture (decider CLI) |
| test_review_demo | 3 | fixture integration + 1 real-file |
| test_matlab_static_contract | 28 | static MATLAB |
| test_handoff_check | 10 | static MATLAB + handoff checker |

## Executed experiments (not tests)

| run | result | data class |
|---|---|---|
| `verify_simulink_mat.py` on the real exports | 981 pass / 13 fail / 107 skip (the 13 failures are the expected v2, legacy and shared-noise cases) | real Simulink v3 |
| closed loop CL-1 reproduction `repro_of_run_20261022_v1` | 180/180 episodes identical | virtual RF |
| closed loop CL-2 `cl2_20261022` | 2,310 episodes, 53,900 steps | virtual RF |
| `simulink_acwra_campaign.py --source fixture` (new model) | 398 PASS / 0 FAIL / 4 NOT RUN (MATLAB-only) | Python fixtures |
| `spectrum_agent_eval.py` | 5,760 windows | synthetic |
| `digital_twin_forecast_eval.py` | 42 rows × 5 forecasters | virtual RF |
| `retrain_modulation_classifier.py --check` | 6/6 accuracies identical | synthetic |
| `reproduce_python_results.py --quick` | 4/4 MATCH | all of the above |
| `handoff_check.py pre` / `post` | READY / NOT VERIFIED (nothing returned) | static |

## Test-design notes

* Statistical assertions use explicit bounds: |corr| < 5/√N for independent noise, 4σ binomial
  BER tolerances, and Monte Carlo only where it converges (deterministic quadrature at high SNR).
* Tests I wrote and then corrected for a stated reason, never to hide a defect:
  * the Rayleigh Monte-Carlo test at 20 dB was replaced by numerical integration, because MC
    didn't converge;
  * a regime test used the wrong J for the "BPSK-only" regime;
  * `test_jamming_*` pinned the old saturating model, so it was rewritten for the new one;
  * the count in `test_expected_baseline_names_*` was arithmetic, so I corrected it.
* One existing assertion was **strengthened**: the v2-export test now requires rejection.
* No pre-existing test was weakened or deleted.
