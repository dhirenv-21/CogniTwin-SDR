# Simulink PHY Debug & Validation Report

**Date:** 2026-08-16
**Trigger:** `run_simulink_case('QPSK',10,0,'AWGN')` returning `measured SINR = -48.67 dB`, `BER = 0.4977`, `|h| = 0.0039`.

---

## 0. Status up front

| | |
|---|---|
| Root cause | **Found, proven quantitatively, and fixed at the source** |
| MATLAB/Simulink executed by me | **NO — not available in this session** |
| Simulink test results | **NOT RUN.** No Simulink numbers are claimed anywhere in this report |
| Python-side verification | **RUN.** 127 pytest tests pass; the independent MAT verifier was exercised on healthy and deliberately-broken data |
| Existing tests preserved | **Yes.** 95 → 127 (32 added, 0 removed, 0 weakened) |

The fix cannot be called validated until you run §7 on your machine. Everything needed to do that in three commands is in §7.

---

## 1. Root cause

**`run_simulink_case.m` line 99 (my code from the previous turn):**

```matlab
iq_input = [t, tx];        % tx is COMPLEX
```

`tx` is a complex column vector, so the horizontal concatenation makes the **entire matrix complex — including column 1, the time vector**. Simulink's `From Workspace` block in array format requires a **real**, monotonically increasing time column. With a complex time column it cannot resolve any sample, so `INPUT_IQ` emitted **0 for the whole simulation**.

The wanted signal never reached `PHY_Channel`. Everything downstream was measuring pure noise.

Secondary consequence: line 117, `assignin('base','iq_input', iq_input)`, **overwrites the timeseries you built by hand on every call**. That is why your fix appeared to work once and then stopped — the model was reconfigured correctly, but the variable was clobbered with the broken complex matrix each run.

### Proof, not inference

If `rx = jam + noise` with no signal, the least-squares estimate `ĥ = ⟨tx,rx⟩/⟨tx,tx⟩` is a random walk with `E|ĥ|² = P_rx/N`. Simulating that hypothesis over 4000 seeds at your exact settings:

| Case | Predicted \|h\| (5–95 %) | **You observed** | Predicted SINR (5–95 %) | **You observed** |
|---|---|---|---|---|
| AWGN, P=0 | 0.0007 – 0.0054 | **0.0039** | −52.9 … −35.3 dB | **−48.67 dB** |
| Rayleigh, P=0 | 0.0007 – 0.0054 | **0.0037** | −52.9 … −35.3 dB | **−51.48 dB** |
| Rayleigh, P=0.25 | 0.0013 – 0.0101 | **0.0083** | −53.1 … −35.4 dB | **−45.01 dB** |

All six observations land inside the predicted intervals. The decisive detail is the third row: **your |h| grew from 0.0037 to 0.0083 when you added interference.** A real channel gain is indifferent to jammer power. A least-squares fit to noise is not — more impairment power, larger spurious correlation, and `sqrt(0.35/0.1) = 1.87` predicts exactly the ratio you saw. Closed form: `sqrt(P_rx/N) = sqrt(0.1/10000) = 0.00316`.

This is pinned in `tests/test_phy_regression.py::test_phy2_ls_estimate_on_pure_noise_reproduces_the_observed_h` and `::test_phy2_more_impairment_increases_the_spurious_estimate`.

### Answering your specific questions

**Q3 — why SINR ≈ −48 dB, BER ≈ 0.5, |h| ≈ 0.0037, yet jammer power correct?**
All four follow from one fault. `SINR = |ĥ|²·P_tx / P_err ≈ (P_rx/N)/P_rx = 1/N = −40 dB`. `BER = 0.5` because demodulating noise is a coin flip. The jammer power was right because the jammer is generated *independently inside* `PHY_Channel` and never depended on `x` — it was the only quantity in the chain that did not need the input path to work.

**Q4 — is the "QPSK" waveform actually QPSK?**
**Yes.** `cognitwin_waveform.m` lines 55–75 generate real QPSK: random bits → MSB-first packing → `cognitwin_gray2bin` → `exp(1j·(2πm/4 + π/4))`. No `exp(1j·2π·f·t)` sinusoid anywhere in the signal path. The reference bits for BER are the *same* `bits` array returned by that function and passed straight into `cognitwin_measure_ber` — there is no second, independent bit source that could desynchronise. Verified in `tests/test_phy_regression.py`.

**Q5 — is the BER comparison valid?**
Yes, and it is now independently cross-checked in Python. Same bits (single source), sps = 1 so symbol timing is trivial, constellation and Gray mapping in `cognitwin_measure_ber.m` are the exact inverse of `cognitwin_waveform.m` (bit-packing order verified: `g = g*2 + block(b)` inverted by `bitget(g, k-b+1)`), I/Q ordering preserved, and Rayleigh is coherently equalised — now by the **known** `h` rather than an estimate. `experiments/verify_simulink_mat.py` re-demodulates in Python from scratch and compares.

**Q6 — SNR implementation.**
Traced, not trusted. `noisePower = 10^(-snr_db/10)`, `noise = sqrt(noisePower/2)·complex(randn,randn)` ⇒ `E|noise|² = (P/2)(1+1) = P`. At 10 dB that is exactly 0.1 against unit-power `tx`. **The mathematics was always correct** — it was measuring against a signal that wasn't there. Pinned by `test_phy5_noise_power_equals_ten_to_the_minus_snr_over_ten` across −10…40 dB.

**Q7 — the Rayleigh channel.**
`|h| ≈ 0.0037` was **not** the channel. The model's Rayleigh draw is `h = (randn + 1j·randn)/sqrt(2)`, giving `E|h|² = 1` — correct and unchanged. 0.0037 was the LS artefact described above. `h` is **not** forced to 1; the project's block-fading model is kept exactly. It is now generated in the driver, so it is known, reproducible and exported.

**Q9 — interference independence.**
Preserved and now asserted in three places: inside `local_verify` (`|corr(tx,jam)| < 5/√N`), in the Python verifier, and in `test_phy6_jammer_is_independent_of_the_wanted_signal`. `test_phy6_coherent_interference_does_not_degrade_ber` demonstrates why the old v1 coherent copy was inert.

**Q10 — sample counts.** `t = (0:N-1)'/Fs`, `StopTime = (N-1)/Fs`, exactly N samples. Unchanged from the previous fix and now a hard error, not a warning.

---

## 2. Files changed

| File | Change |
|---|---|
| `simulink/create_cognitwin_model.m` | **v3.** Split real `INPUT_I`/`INPUT_Q`; `PHY_Channel` gains `tx_echo`, `noise_signal` outputs and takes `h` as two real constants; no persistent state. v2 preserved as `create_cognitwin_model_v2_backup.m`. |
| `simulink/matlab/run_simulink_case.m` | **v3.** Real split inputs; model-version guard; 10-point physical-consistency battery; all powers measured from arrays; **refuses to export a failing run**. v2 preserved as `run_simulink_case_v2_backup.m`. |
| `src/simulink_bridge/validation.py` | New `wanted_signal_present` check (self-aware: skips when uninformative). |
| `src/simulink_bridge/reference_phy.py` | Exports `noise_iq`, `interference_iq` and measured powers, matching the MATLAB schema. |

## 3. Files created

- `simulink/matlab/diagnose_simulink_phy.m` — 12-point node-by-node PHY diagnostic
- `simulink/matlab/run_baseline_tests.m` — cases A–F, SNR ladder, interference sweep, multi-seed; criteria fixed before running
- `experiments/verify_simulink_mat.py` — independent Python recomputation from the raw arrays
- `tests/test_phy_regression.py` — 32 regression tests, one group per bug
- `simulink/create_cognitwin_model_v2_backup.m`, `simulink/matlab/run_simulink_case_v2_backup.m`
- `docs/task11b_phy_debug_report.md` (this file)

**Untouched, as required:** `src/acwra/*`, `src/digital_twin/*`, `src/agents/*`, `src/virtual_rf/*`, and every pre-existing test.

---

## 4. The fixes

**Fix 1 — the input path (root cause).** I and Q now enter as two separate **real** `[t, data]` matrices and are recombined inside `PHY_Channel` as `x = complex(xi, xq)`. No `From Workspace` block ever receives complex data, so the time column cannot be corrupted. This removes the failure mode rather than patching around it.

**Fix 2 — the fault can never be silent again.** `PHY_Channel` echoes the reconstructed `x` back out as `tx_echo`. `run_simulink_case` asserts `max|tx_echo − tx| < 1e-9` and **aborts without exporting** if it fails. Under the old bug this would have raised on the very first run instead of writing a plausible-looking MAT file.

**Fix 3 — measure, don't infer.** The model now logs `noise_signal` and `interference_signal` separately, so:

```
P_sig  = mean|h·tx|²      P_noise = mean|noise|²      P_jam = mean|jam|²
SNR    = 10log10(P_sig/P_noise)
SIR    = 10log10(P_sig/P_jam)
SINR   = 10log10(P_sig/(P_noise+P_jam))
```

No least-squares inference anywhere in the reported figures. The LS estimate is retained **only** as a cross-check against the known `h`.

**Fix 4 — `h` is known exactly.** Generated in the driver from the project's distributions (AWGN `h=1`; Rayleigh `CN(0,1)`; Rician `K=2`), passed in as two real constants, exported with the results. No persistent state in the MATLAB Function block.

**Fix 5 — 10 consistency checks per run**, all from arrays: `tx_echo` match, `rx = h·tx + jam + noise` residual, noise power vs `10^(-SNR/10)`, jammer power vs request, jammer/signal independence, **wanted-signal presence**, LS-vs-true `h`, finiteness, time vector, complex `rx`. `opts.strict` (default on) turns any failure into an error instead of an export.

**Fix 6 — the Python bridge rejects a dead-signal measurement.** `wanted_signal_present` compares `|ĥ|²` against the pure-noise floor `P_rx/N` and requires a 10 dB margin, so broken PHY data can never reach the Spectrum Agent, the Digital Twin or ACWRA. It is self-aware about its own resolution: when even a healthy link could not clear the threshold at the given N/SNR/interference, it **skips** rather than false-failing.

| Scenario | Observed margin | Achievable margin | Verdict |
|---|---:|---:|---|
| Broken build (rx = noise) | −5.1 dB | 39.6 dB | **FAIL** |
| Healthy 10 dB AWGN | 39.6 dB | 39.6 dB | PASS |
| Healthy −20 dB, N=10000 | 19.7 dB | 20.0 dB | PASS |
| Healthy −20 dB, N=512 | 6.8 dB | 7.0 dB | SKIP (uninformative) |
| Deep Rayleigh fade \|h\|=0.003 | −2.3 dB | −0.5 dB | SKIP (uninformative) |
| Heavy jam P=10, SNR=40 | 32.5 dB | 32.6 dB | PASS |

---

## 5. Acceptance criteria — fixed before any test runs

Encoded in `local_criteria()` in `run_baseline_tests.m` and in `TOL` in `verify_simulink_mat.py`:

| Criterion | Threshold |
|---|---|
| BER vs theory `Q(√SINR)` | abs 1.5e-3, or rel 0.35 when theory > 0.005 |
| AWGN 10 dB, P=0 BER | must be **< 0.05** (i.e. nowhere near 0.5) |
| BER vs SNR | non-increasing |
| BER(20 dB) vs BER(10 dB) | strictly lower |
| Measured SNR from arrays | within 0.5 dB |
| Measured SIR vs −10log10(P) | within 0.5 dB |
| SINR vs interference | strictly decreasing |
| \|corr(tx, jam)\| | < 5/√N |
| `max\|rx − (h·tx+jam+noise)\|` | < 1e-9 |
| Sample count | exactly N; StopTime exactly (N−1)/Fs |

Expected SIR table (unit-power tx, AWGN so |h| = 1): 0.01→20.00, 0.1→10.00, 0.25→6.02, 0.5→3.01, 1→0.00, 2→−3.01, 4→−6.02, 10→−10.00 dB.

---

## 6. What I actually ran

**Simulink: NOT RUN — MATLAB is not reachable from this session.** This session is a Linux cloud container; the device bridge transfers files but does not execute Windows programs, and the local Linux VM on your machine has no MATLAB and no SciPy. Sections 1–5 above are analysis and code; §7 is what turns them into a validated result.

**Python: RUN.**

- `pytest -q` → **127 passed, 0 failed** (95 pre-existing preserved, 32 added).
- ACWRA campaign → **402 checks, 396 pass, 0 fail, 2 inconclusive, 4 not run** — identical to before the PHY work, confirming no regression.
- `verify_simulink_mat.py` exercised on three healthy and one deliberately signal-less MAT file. The broken file produced 5 targeted failures: `wanted_signal_present` (1.2 dB margin), `ls_matches_reported_h` (LS 0.0036 vs reported 1.0), `rx_equals_model_sum`, `ber_matches_theory`, `ber_not_coinflip`. The healthy files passed all 62 physical checks — with `provenance` correctly failing them for being Python fixtures rather than Simulink output.

**No Simulink BER, power, SNR, SIR or SINR figure appears in this report, because none was produced.** The tables in §5 are criteria, not results.

---

## 7. What to run, in order

```matlab
cd simulink
create_cognitwin_model              % REQUIRED - rebuilds the .slx with real I/Q inputs
                                    % (your current .slx is the broken v2 build)
cd matlab
diagnose_simulink_phy               % 12-point node-by-node PHY check - run this FIRST
```

`diagnose_simulink_phy` is the decisive test. **D11** runs the model at SNR = +200 dB with no jammer and h = 1, where `rx` must equal `tx` to ~1e-15. The broken build gives `max|rx − tx| ≈ 1.0`. If D11 passes, the input path is fixed.

Then:

```matlab
run_simulink_case('QPSK', 10, 0, 'AWGN')    % should now print BER ~ 7.8e-4, not 0.4977
run_baseline_tests                          % cases A-F, SNR ladder, interference sweep, 3 seeds
```

```bash
python experiments/verify_simulink_mat.py --dir simulink/results/baseline
python -m pytest -q
```

If `run_simulink_case` still fails, it will now **abort with a named check** instead of exporting garbage — send me that message and it localises the fault immediately.

---

## 8. Remaining limitations

- **No MATLAB execution on my side.** Every `.m` file is untested against a live MATLAB session. The v3 model uses only API calls your v1/v2 runs already exercised (`add_block`, `set_param`, `chart.Script`, `add_line`), plus a 4-output MATLAB Function block, which is standard.
- I am confident the complex time column is the mechanism, but I could not observe Simulink's internal behaviour directly. If D11 still fails after the rebuild, the guard rails will name the actual node — the fix is not resting on my diagnosis being right.
- Rayleigh/Rician remain **block** fading (one gain per run), not time-varying Doppler. Unchanged from the project specification.
- The Python verifier re-demodulates BPSK/QPSK independently, but not OFDM-QPSK; those rows report `SKIP` for `ber_matches_theory`.
- The modulation-classifier limitation from the previous report (trained only on tiled 32-symbol patterns) is untouched — it is an observation-stage issue, unrelated to the PHY, and the classifier is protected.
- `.git/index.lock`, `.git/HEAD.lock` and `.git/objects/maintenance.lock` are still stale in the project folder from the earlier checkpoint; delete them from Windows before running git.
