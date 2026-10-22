# Task 11 — Simulink ↔ CogniTwin-SDR End-to-End Integration & Validation

**Date:** 2026-08-16
**Checkpoint before any change:** git commit `6ba32c1` ("Checkpoint: pre-Task-11 state of Cognitwin-SDR")

---

## 1. Files changed

| File | Change |
|---|---|
| `src/simulink_bridge/protocol.py` | **Additive only.** New optional fields `sample_rate`, `time_vector`, `tx_iq`, `source`, `extras`; new read-only properties `num_samples`, `measured_power`, `duration_s`. All defaults preserve the previous constructor signature and behaviour. |
| `src/simulink_bridge/receiver.py` | **Additive only.** `load_mat_measurement()` now uses shape-safe `flatten_matlab_iq()` and carries the new metadata; original signature and return type unchanged. New `load_and_validate()` and `measure()` classmethods. |
| `src/simulink_bridge/__init__.py` | Re-exports the new validation and pipeline symbols. |
| `simulink/create_cognitwin_model.m` | Rewritten as v2 (see §17/§18). Original preserved verbatim as `create_cognitwin_model_v1_backup.m`. |
| `simulink/README.md` | Rewritten to document the v2 model, the new drivers and the sample-count fix. |

**Not touched, as required:** `src/acwra/scoring.py`, `src/acwra/engine.py`, `src/acwra/decision.py`,
`src/acwra/trace.py`, all of `src/digital_twin/`, all of `src/agents/`, `src/virtual_rf/`,
`src/evaluation/metrics.py`, every pre-existing test, every pre-existing experiment,
`simulink/matlab/{init_cognitwin,configure_scenario,export_results,run_validation}.m`.

## 2. Files created

**Python bridge**

- `src/simulink_bridge/validation.py` — MAT-file validation battery, shape-safe I/Q flattening, pure measurement helpers.
- `src/simulink_bridge/pipeline.py` — the integration layer (`SimulinkACWRAPipeline`).
- `src/simulink_bridge/reference_phy.py` — Python fixture generator, always tagged `source="python-fixture"`.

**Entry points**

- `experiments/simulink_acwra_demo.py` — the single end-to-end command.
- `experiments/simulink_acwra_campaign.py` — Parts 9/11/12 campaign, results table and plots.

**Tests**

- `tests/test_acwra_stress.py` — deterministic ACWRA stress scenarios A/B/C (Part 8).
- `tests/test_simulink_acwra_integration.py` — integrity, I/Q and end-to-end tests (Parts 9-G/H/I).

**MATLAB**

- `simulink/matlab/cognitwin_waveform.m` — BPSK / QPSK / OFDM-QPSK transmit waveforms.
- `simulink/matlab/cognitwin_measure_ber.m` — hard-decision demapper, true bit-error count.
- `simulink/matlab/cognitwin_gray2bin.m`, `cognitwin_bin2gray.m` — Gray mapping identical to the Python side.
- `simulink/matlab/run_simulink_case.m` — run one simulation, export a MAT file.
- `simulink/matlab/run_simulink_campaign.m` — batch the validation matrix.
- `simulink/create_cognitwin_model_v1_backup.m` — the original model generator.

**Outputs**

- `simulink/results/campaign_report/results_fixture.csv`, `summary_fixture.md`, six PNG plots.
- `docs/task11_simulink_acwra_integration.md` (this file).

## 3. Architecture before integration

```
VirtualRFEnvironment.step()          <- synthesises its own I/Q internally
        |
MultiAgentOrchestrator.step()
        |-- SpectrumAgent.process()
        |-- DigitalTwin.update()
        |-- PredictionAgent.process()
        |-- CyberDefenseAgent.process()
        +-> MultiAgentSnapshot
                |
        ACWRAEngine.evaluate_and_decide()
                |-- DigitalTwin.evaluate_counterfactuals()
                |-- ACWRAScoringEngine.score_candidates()
                +-> ACWRADecision + DecisionTrace

SimulinkReceiver.load_mat_measurement()  -> SpectrumAgent only
                                            (experiments/simulink_validation.py)
```

Two disconnected halves. The Simulink bridge stopped at the Spectrum Agent and never
reached the orchestrator, the Digital Twin or ACWRA. Worse,
`experiments/simulink_validation.py` **regenerates its own MAT files in Python** before
"loading" them, so the "Simulink" measurements it validated were synthetic. The three
MAT files shipped in `simulink/results/` were written by SciPy, not MATLAB (confirmed
from the MAT header and from reading the script).

## 4. Architecture after integration

```
MATLAB / Simulink
  cognitwin_waveform.m  -> iq_input = [t, complex IQ]
        |
  cognitwin_sdr_phy.slx   y = h*x + jam + noise
        |
  run_simulink_case.m   -> measures BER, |h|, SINR -> MAT export (source='simulink')
        |
=========================== simulink/results/*.mat ===========================
        |
  SimulinkReceiver.load_and_validate()      <- strict validation, no fallback data
        |
  SimulinkACWRAPipeline.run_measurement()   <- the only new glue
        |
        |  per 512-sample window of the REAL capture:
        |     SpectrumAgent.process()          (existing instance, unmodified)
        |     VirtualRFEnvironment.simulate()  (existing, to fill throughput/latency)
        |     DigitalTwin.update()             (existing)
        |
        |-- PredictionAgent.process()          (existing)
        |-- CyberDefenseAgent.process()        (existing)
        +-> MultiAgentSnapshot                 (existing dataclass)
                |
        ACWRAEngine.evaluate_and_decide()      (existing, untouched)
                |-- DigitalTwin.evaluate_counterfactuals()
                |-- ACWRAScoringEngine.score_candidates()
                +-> ACWRADecision + DecisionTrace
```

The adapter exists because `MultiAgentOrchestrator.step()` *begins* by calling
`VirtualRFEnvironment.step()`, which synthesises I/Q. Task 11 requires the I/Q to come
from Simulink instead. `SimulinkACWRAPipeline` therefore reuses the orchestrator's **own
agent instances** and runs the orchestrator's steps 2–6 verbatim, replacing only step 1.
No agent is duplicated; no decision equation is re-implemented.

**Windowing.** A single capture is split into consecutive 512-sample windows. This is not
cosmetic: the existing `TrendPredictor` needs ≥ 5 `DigitalTwinState` entries or it returns
`INSUFFICIENT_HISTORY` and the risk score is pinned to 0.0, which would make ACWRA's
`(1+R)` term dead. Every window carries real, non-overlapping samples from the capture —
nothing is synthesised or repeated. A 10000-sample capture yields 19 windows.

## 5. Exact data path

```
user waveform choice + SNR/interference/channel
  → cognitwin_waveform.m           unit-power baseband symbols, N samples
  → iq_input = [t, tx]             From Workspace, t = (0:N-1)'/Fs
  → cognitwin_sdr_phy.slx          y = h·x + jam + noise, fixed-step 1/Fs
  → rx_iq (To Workspace)           N logged complex samples
  → run_simulink_case.m            LS channel estimate, equalise, demap, count bit errors
  → <name>.mat                     iq_samples, tx_iq, time_vector, snr_db, ber,
                                   modulation, interference_power, channel_type,
                                   sample_rate, source='simulink', measured_*
  → SimulinkReceiver.load_and_validate()
  → SimulinkACWRAPipeline
       → per window: convert_for_spectrum_agent() → SpectrumAgent.process()
       → EnvironmentState (measured SINR, measured BER, measured power)
       → DigitalTwin.update()
     → PredictionAgent.process()   → risk R, risk level
     → CyberDefenseAgent.process() → candidate strategy list
     → MultiAgentSnapshot
  → ACWRAEngine.evaluate_and_decide(snapshot, digital_twin)
       → DigitalTwin.evaluate_counterfactuals(candidates)
       → ACWRAScoringEngine.score_candidates(cf, R, C)
       → argmax U(c)
  → ACWRADecision + human-readable trace
```

## 6. Real Simulink end-to-end result

**NOT RUN — MATLAB/Simulink is not reachable from this session.**

This session executes in an isolated Linux cloud container. The device bridge to the
Windows machine transfers files but does not execute Windows programs, and `device_bash`
runs in a Linux VM where MATLAB is not installed. No MATLAB success is claimed anywhere in
this report.

The MATLAB half is written, complete and documented, and the Python half has been executed
end-to-end 125 times against fixture data that mirrors the Simulink signal chain exactly.
The command to produce the real result is in §21.

## 7–10. Test counts

| | Count |
|---|---:|
| Checks executed (campaign) | 402 |
| Passed | 396 |
| Failed | 0 |
| Inconclusive | 2 |
| Not run | 4 |
| pytest tests executed | 95 |
| pytest passed | 95 |
| pytest failed | 0 |
| **Total executed checks** | **497** |

The 4 NOT RUN are campaign checks A1–A4 (model loads / compiles / simulation runs /
simulation completes) — all four require MATLAB.

The 2 INCONCLUSIVE are B001 and B002: the Spectrum Agent reported `OFDM-QPSK` for BPSK and
QPSK waveforms. The pipeline completed and ACWRA decided in both cases; the mismatch is a
pre-existing classifier limitation, diagnosed in §17.

Campaign breakdown:

| Group | Pass | Inconclusive | Fail | Not run |
|---|---:|---:|---:|---:|
| A basic Simulink | 8 | 0 | 0 | 4 |
| B modulation | 1 | 2 | 0 | 0 |
| C SNR sweep (13 points) | 13 | 0 | 0 | 0 |
| D interference sweep (13 points) | 13 | 0 | 0 | 0 |
| E channel | 6 | 0 | 0 | 0 |
| F stress matrix (90 points) | 90 | 0 | 0 | 0 |
| G I/Q validation | 125 | 0 | 0 | 0 |
| H data integrity | 15 | 0 | 0 | 0 |
| I Python end-to-end | 125 | 0 | 0 | 0 |

## 11. Existing pytest result

```
$ python -m pytest -q
95 passed in 12.57s
```

Baseline before Task 11 in this environment: **46 passed**. (The task statement quotes 43;
the difference is environment-dependent parametrisation, not a change — nothing was
deleted or weakened.) 49 new tests were added: 7 in `test_acwra_stress.py`, 42 in
`test_simulink_acwra_integration.py`. No existing test was modified, skipped or removed.

## 12. MATLAB/Simulink result

**MATLAB execution unavailable — not run.** See §6.

Every MATLAB file was written to be self-contained and defensive: `run_simulink_case.m`
falls back between `sim()` signatures, accepts `Structure With Time` / `Structure` /
`Array` / `timeseries` logging formats, reads To Workspace variables from either the
`SimulationOutput` object or the base workspace, and warns loudly (never silently trims)
if the logged sample count differs from the input count.

## 13. Python bridge result

**PASS.** 402 campaign checks and 42 integration tests exercised it.

- N×1, 1×N, N×2 real `[I Q]`, and native MATLAB complex arrays all load correctly.
- The imaginary component is never discarded — asserted directly.
- Round-trip through `savemat`/`loadmat` is bit-exact (`np.array_equal`).
- Malformed input is rejected cleanly and never replaced with fabricated data: empty I/Q,
  NaN, Inf, non-finite SNR, missing required variables, corrupt files, missing files, and
  sample-count mismatches all raise or fail validation.
- Measured SIR matches theory across the whole sweep (Part 9-D table):

| Interference power | Expected SIR | Measured (SIR+N) |
|---:|---:|---:|
| 0.01 | 20.00 dB | 19.62 dB |
| 0.1 | 10.00 dB | 9.90 dB |
| 0.25 | 6.02 dB | 5.99 dB |
| 0.5 | 3.01 dB | 3.09 dB |
| 1 | 0.00 dB | 0.14 dB |
| 2 | −3.01 dB | −3.06 dB |
| 4 | −6.02 dB | −6.07 dB |
| 10 | −10.00 dB | −9.85 dB |

(The small positive bias at low interference is the thermal noise floor at SNR = 30 dB,
which the acceptance rule accounts for explicitly.)

## 14. Spectrum Agent result

**PASS for integration, INCONCLUSIVE for detection accuracy.**

The existing `SpectrumAgent` was used unmodified. It accepted the real I/Q from every one
of the 125 cases and produced a full `SpectrumIntelligenceResult` — modulation,
confidence, estimated SNR, bandwidth, interference power, anomaly flag — every time.
`HIGH_INTERFERENCE` and `SNR_DROP` anomalies fire correctly under jamming.

Detection accuracy on non-repeating symbol streams is a pre-existing limitation: see §17.

## 15. MultiAgentSnapshot result

**PASS.** All 125 snapshots carried a populated `spectrum_result`, `prediction_result` and
`defense_candidates`. The `TrendPredictor` returned `SUCCESS` (not `INSUFFICIENT_HISTORY`)
in every case thanks to windowing. Risk levels distributed across the whole range —
LOW 35, MEDIUM 21, HIGH 16, CRITICAL 53 — proving the snapshot tracks the measurement
rather than being fixed.

## 16. ACWRA result

**PASS.** The four weights are asserted unchanged (`w_t=0.4`, `w_se=0.2`, `w_b=0.6`,
`lambda_c=1.0`), and `U(c)` is recomputed from the published closed form and required to
match the engine to `1e-12` — both on synthetic stress scenarios and on real pipeline
output. The selected strategy is verified to be the arg-max of the counterfactual
utilities, never a shortcut from the Spectrum Agent's detected modulation.

The decision is demonstrably reactive, not hard-coded:

- Interference sweep: `Keep Current` up to P = 0.1, then `QPSK` from P = 0.25 onward.
- SNR sweep: `QPSK` below ~5 dB, `Keep Current` from 8 dB up.
- Across all 125 scenarios: `QPSK` selected 90×, `Keep Current` 35×.

## 17. Bugs found

**BUG-1 (critical, pre-existing): `experiments/simulink_validation.py` fabricates its own
"Simulink" data.** `generate_matlab_validation_mat_files()` writes the three MAT files with
SciPy and then "loads" them, so nothing in that experiment ever touched MATLAB. The three
files in `simulink/results/` carry a SciPy MAT header, confirming they were produced this
way. *Not modified* — it is an existing Task-10 artefact and Task 11 says to preserve
existing functionality. It is superseded by `experiments/simulink_acwra_demo.py`, which
refuses to present fixture data as real (`--require-real`).

**BUG-2 (high, pre-existing): the modulation classifier only recognises repeating
waveforms.** `generate_single_signal()` builds each 512-sample training block from 32
unique symbols tiled 16×. That periodicity dominates the spectral features
(`spectral_flatness`, `spectral_entropy`, `bandwidth_3db_hz`). Reproduction:

| Waveform | Tiled 32-symbol pattern (training style) | Non-repeating stream (real data) |
|---|---|---|
| BPSK @ 10–30 dB | BPSK, conf 0.99–1.00 | **OFDM-QPSK**, conf 0.76 |
| QPSK @ 10–30 dB | QPSK, conf 0.90 | **OFDM-QPSK**, conf 0.88 |

The confidence stays well above the 0.60 `UNKNOWN` threshold, so the misclassification is
not caught. *Not fixed* — the classifier and the agents' detection equations are protected.
Mitigation supplied: `opts.patternSymbols = 32` (MATLAB) / `pattern_symbols=32` (Python)
reproduces the training representation and restores correct detection, verified at
BPSK 0.87, QPSK 0.82, OFDM-QPSK 1.00.

**BUG-3 (medium, pre-existing): v1 Simulink interference did not interfere.** The v1 model
wired `INPUT_IQ → Interference_Gain(sqrt(P)) → PHY_Channel`, so the "interference" was a
coherent scaled copy of the wanted signal: `y = (1+√P)·x + noise`. That re-scales the link
instead of degrading it, and the Spectrum Agent's unit-power adapter then normalises the
scaling away entirely — interference had literally no effect. *Fixed* in the v2 model: the
jammer is now independent complex Gaussian with power exactly `InterferencePower`.

**BUG-4 (medium, pre-existing): the 10000/10001 sample discrepancy.** Diagnosed in full in
§18. *Fixed at the source.*

**BUG-5 (low, pre-existing): v1 model had no channel-type input.** `ChannelType` was
assigned to the base workspace but never reached the model, so Rayleigh/Rician were
unreachable from Simulink. *Fixed* via the `CHANNEL_PARAMETER` constant and `ChannelCode`.

## 18. Required fixes — the sample-count investigation (Part 15)

**Cause: simulation stop time interacting with the fixed-step solver. Not logging, not
interpolation, not the time-vector construction.**

A `FixedStepDiscrete` solver executes at `t = 0, Ts, 2Ts, …, StopTime` inclusive, i.e.
`StopTime/Ts + 1` steps. The v1 model hard-coded `StopTime = 0.1` with
`FixedStep = 1/Fs = 1e-5`, giving **10001** steps. A 10000-sample `iq_input` only spans
`t = 0 … 9999/Fs = 0.09999 s`. At `t = 0.1` the `From Workspace` block had no data left and
emitted its `OutputAfterFinalValue` value.

So the 10001st sample was a *real solver step carrying an unphysical input value*, not a
logging artefact — which is exactly why trimming it without explanation would have been
wrong. Ruled out by inspection: `Decimation` is 1; `MaxDataPoints` is now `inf`; the time
vector is constructed directly from the solver clock; `Interpolate` is `off`.

**Fix (at the source, in three places):**

1. `create_cognitwin_model.m` sets `StopTime` to the workspace variable `SimStopTime`
   rather than a literal.
2. `run_simulink_case.m` sets `SimStopTime = (N-1)/Fs`, so solver steps == input samples
   == logged samples.
3. `From Workspace` now uses `Interpolate = 'off'` and
   `OutputAfterFinalValue = 'Holding final value'`, so even a mis-set stop time cannot
   inject an extrapolated sample.

`run_simulink_case.m` still issues an explicit `warning` (never a silent trim) if the
counts ever disagree, printing `numel(rx)`, `N`, `StopTime` and `Ts` so the cause is
immediately visible.

## 19. Optional improvements

1. **Retrain the modulation classifier on non-repeating symbol streams** (BUG-2). This is
   the single highest-value follow-up: it is the only reason the observation stage is
   inconclusive on real data.
2. Feed the Spectrum Agent's per-window SNR estimate through a short moving average — the
   current single-window estimate is noisy enough to trigger spurious `SNR_DROP` anomalies.
3. Let `CyberDefenseAgent` propose the full candidate set whenever confidence is low, not
   only when risk is high — at present a low-confidence/low-risk state offers ACWRA only
   `Keep Current`, so the utility comparison is degenerate.
4. Export per-symbol BER from MATLAB (not just an aggregate) so the Digital Twin can be
   updated with a genuinely time-varying BER across windows.
5. Add a Rician `K`-factor parameter to the model instead of the fixed `K = 2`.
6. Support `sps > 1` with proper pulse shaping (root-raised-cosine) for a more realistic
   spectrum — the scaffolding is already in `cognitwin_waveform.m`.

## 20. Remaining limitations

- **No MATLAB execution was performed.** Every MATLAB file is untested against a live
  MATLAB session. The Python half is fully exercised.
- Campaign rows tagged `FIXTURE` come from the Python reference PHY, not from `.slx`. They
  are never presented as real; `--require-real` refuses fixture data outright.
- Modulation detection on non-repeating streams is unreliable (BUG-2). The ACWRA decision
  still functions, but `Keep Current` inherits the *detected* modulation, so its complexity
  prior `K_c` can be wrong when detection is wrong.
- Rayleigh/Rician are modelled as **block** fading (one gain per simulation run), not as a
  time-varying Doppler process.
- The Digital Twin's counterfactual BER model is the existing analytic
  `VirtualRFEnvironment._compute_congestion_metrics()`, not a second Simulink run per
  candidate. This is by design — Task 11 requires the existing sandbox to be used, not
  replaced.
- `git` operations inside the OneDrive-synced project folder leave stale
  `.git/*.lock` files when driven from the mounted filesystem (see §21 note).

## 21. Commands

**The one command that demonstrates the full chain:**

```bash
python experiments/simulink_acwra_demo.py --mat simulink/results/<your_export>.mat --require-real
```

**Full workflow from MATLAB:**

```matlab
cd simulink
create_cognitwin_model                                   % once, rebuilds the .slx
cd matlab
run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')          % change these freely
```

```bash
python experiments/simulink_acwra_demo.py --require-real   % picks the newest export
```

**Everything else:**

```bash
python -m pytest -q                                                    # 95 tests
python experiments/simulink_acwra_campaign.py --source fixture         # no MATLAB needed
python experiments/simulink_acwra_campaign.py --source matlab          # after run_simulink_campaign.m
python experiments/simulink_acwra_demo.py --list                       # list available exports
```

> **Note on git:** a pre-change checkpoint commit `6ba32c1` was created in the project
> folder. Because the folder is written through a mount that cannot delete files, git left
> stale `.git/index.lock`, `.git/HEAD.lock` and `.git/objects/maintenance.lock` behind.
> Delete those three files from Windows before running further git commands.
