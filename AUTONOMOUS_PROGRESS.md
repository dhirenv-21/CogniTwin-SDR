# Autonomous Progress — CogniTwin-SDR

Branch `autonomous-completion`; `master` untouched at `6ba32c1`. Tags/checkpoints:
`0819109` (first session start), `checkpoint-pre-final-completion` = `bae5701` (start of the
final-completion phase). Final report: [`FINAL_COMPLETION_REPORT.md`](FINAL_COMPLETION_REPORT.md).

## Current phase
GNU Radio integration phase (2026-10-22): everything independent of GNU Radio is done
([`GNURADIO_INTEGRATION_REPORT.md`](GNURADIO_INTEGRATION_REPORT.md)). GNU Radio 3.10.12.0 is
installed (radioconda, env `cognitwin-gr`). The execution tests pass 12/12 and the BER
validation passes 18/18. The MATLAB/Simulink v4
validation is still BLOCKED as well.

## Next action
GNU Radio: in env `cognitwin-gr`, run `gnuradio_spectrum_eval.py`, `gnuradio_demo.py`,
the full `gnuradio_campaign.py --run-id grcl1_<date>` and the GRC GUI (smoke test, demo and Spectrum eval done). MATLAB: `cd simulink/matlab; logDir =
run_v4_validation`, return the artifacts in `MATLAB_HANDOFF.md` §4, then
`python experiments/handoff_check.py post`.

## GNU Radio phase

| phase | status | key evidence |
|---|---|---|
| 0 audit | PASS | 432 passed at `6d9d9a4`; GNU Radio, conda and WSL absent; no SDR |
| 1 flowgraph | PASS (executed, GNU Radio 3.10.12.0) | `src/gnuradio_phy/flowgraph.py` (BPSK, QPSK, OFDM-QPSK; AWGN, block, time-varying fading; jammer) |
| 2 signal correctness | PASS | 18/18 BER points; `results/gnuradio/ber_validation/ber_20261022_v1/` |
| 3 export / provenance | PASS | `tests/test_gnuradio_export_validation.py` |
| 4 Spectrum Agent | PASS (executed) | accuracy 0.859, ECE 0.051; `results/gnuradio/spectrum_eval/spec_20261022_v1/` |
| 5–6 agents / ACWRA | PASS on stand-in | unchanged pipeline; ACWRA untouched |
| 7 closed loop | PASS (logic) / NOT RUN | `tests/test_gnuradio_closed_loop.py` |
| 8 campaign | PASS (executed): smoke + full `grcl1_20261022_v2` (4,860 runs); SINR threshold beats ACWRA on BER | `results/gnuradio/campaign/smoke/`; ACWRA never switched (risk gate) |
| 9 GRC demo | static only | `grc/cognitwin_phy_demo.grc`, `experiments/gnuradio_demo.py` |
| 10 tests | PASS | 507 passed, 12 skipped (GNU Radio execution) |
| 11 docs | PASS | `docs/GNURADIO_SETUP.md`, ARCHITECTURE, DATA_SCHEMA_PROVENANCE, README |

## Completed (final phase)

| phase | status | key evidence |
|---|---|---|
| 0 audit | PASS | branch/commit/tests matched the report (bae5701, 377); MATLAB still absent |
| 1 handoff | PASS (static) | derived baseline expectations (43), path-safety tests, `pre` READY |
| 2 MATLAB execution | BLOCKED | no `matlab.exe` |
| 3 bridge / provenance | PASS | SNR-unit fix; v2 exports now rejected (`rx_power_matches_configuration`) |
| 4 Spectrum Agent | PASS (synthetic) | `results/ai/spectrum_eval/`; resolution-aware SNR_DROP (false alarms 20–26 % → 0) |
| 5 Digital Twin | PASS (finding) | alternatives evaluated; trend < persistence on steps; predictor unchanged |
| 6 agents | PASS | covered by the integration, robustness and demo tests; threat label documented as a heuristic |
| 7 ACWRA | PASS | spec + hand-calculated tests; empty-candidate error |
| 8 closed loop | PASS (virtual RF) / NOT RUN (Simulink) | one-step delay, paired fades, orchestrator equivalence; MATLAB loop + `acwra_decide.py` implemented |
| 9 virtual-RF model | PASS | `link_model.py`; saturation root-caused and fixed; regimes tested |
| 10 fair evaluation | PASS | CL-1 reproduced; protocol CL-2 committed first; `cl2_20261022` |
| 11 ablations | PASS | four ablations; confidence inert, prediction lowers BER, gating costs goodput |
| 12 reproducibility | PASS | `requirements-lock.txt`, `--out-dir`, `--check`, `reproduce_python_results.py` (4/4 MATCH) |
| 13 tests | PASS | 432/432 |
| 14 docs | PASS | ARCHITECTURE, DATA_SCHEMA_PROVENANCE, EXPERIMENT_PROTOCOL, REPRODUCIBILITY, ACWRA spec, README, final report |
| 15 demo | PASS | `experiments/review_demo.py` |

## Research findings (honest)
* ACWRA is BER-averse by construction (w_b(1+R) ≥ w_t + w_se).
* In CL-2 an a-priori SINR-threshold rule beats ACWRA on goodput **and** BER in the sweep.
* The twin's linear trend forecast loses to persistence on step scenarios.
* Historical Simulink v3 QPSK BER matches theory; v4 is unverified.

## Outstanding external requirements
MATLAB with licensed Simulink (R2025a or later recommended). For the Simulink closed loop,
Python with `requirements-lock.txt` on the same machine.

## Commands executed this phase (main ones)
`pytest -q` (repeatedly; final 432) · `closed_loop_evaluation.py --run-id repro_of_run_20261022_v1`
· `closed_loop_evaluation.py --suite all --run-id cl2_20261022` · `spectrum_agent_eval.py` ·
`digital_twin_forecast_eval.py` · `simulink_acwra_campaign.py --source fixture` ·
`retrain_modulation_classifier.py --check` · `reproduce_python_results.py --quick` ·
`acwra_decide.py` on real v3 exports · `review_demo.py` · `handoff_check.py pre/post`.
