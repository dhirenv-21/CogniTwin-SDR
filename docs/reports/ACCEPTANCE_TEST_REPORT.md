# Acceptance test report — CogniTwin-SDR dashboard

Date: 2026-10-23 · Branch `main` (start `4f57f89`, clean tree) · GNU Radio 3.10.12.0 (conda-forge,
`D:\micromamba\envs\cognitwin-gr`) · Windows 11. Software simulation only; no SDR hardware.

Every test below actually ran. New runs went to new folders under `results/gnuradio/dashboard/runs/`
(git-ignored). Failure tests used copies in a temporary `COGNITWIN_DASH_DIR`. All 16 files of
`results/gnuradio/campaign/` were SHA-256 identical before and after testing.

## A. Historical campaign integrity — PASS

| ID | Check | Result | Evidence |
|---|---|---|---|
| A1 | Completion | PASS | `grcl1_20261022_v2`: runs.csv, episodes_steps.csv, summary/paired/analysis/report present; no ABORTED.md |
| A2 | Configuration | PASS | config.json: 27 conditions, seeds 1–5, 6 policies, 6 episodes, 4096 symbols, GR 3.10.12.0 |
| A3 | Counts | PASS | 810 runs (27×5×6, no duplicates); every run 6 episodes; 4,860 episode rows, all `gnuradio_export` |
| A4 | Aggregates vs report | PASS | Recomputed from runs.csv = summary.csv exactly; vs reference (rounded): SINR Threshold 77.13/0.0361/0.495, ACWRA 69.96/0.0422/0.610, Fixed QPSK 69.34/0.0520/0.653, Fixed OFDM-QPSK 55.55/0.0521/0.653, Fixed BPSK 55.52/0.0264/0.445 |
| A5 | Dashboard loads it | PASS | backend: 810 runs, 27 conditions, 6 policies, 10 paired rows; Policy Comparison shows "810 runs · 27 of 27"; history labels it "GNU Radio · done", `grcl1_20261022` "Aborted" |

## B. Real GNU Radio execution — PASS

Launched through the dashboard job path (`backend.launch` → `worker.py` → `run_gnuradio`). Each episode is revalidated
(content hash + run ledger); CSV metrics equal the NPZ values.

| ID | Configuration | Ran | Result | Run folder | Evidence |
|---|---|---|---|---|---|
| A | BPSK, AWGN, 16 dB, J 0, seed 101, 4096 sym, Fixed BPSK, 1 ep | yes | PASS | `sim_20261023T074322308` | VALID gnuradio_export; 0/4096 errors; Es/N0 meas. 15.91 dB |
| B | BPSK, AWGN, 4 dB, J 0, seed 102, 4096, Fixed BPSK, 1 ep | yes | PASS | `sim_20261023T074324443` | VALID; BER 1.66e-2 (theory 1.25e-2); 4.05 dB meas. |
| C | QPSK, Rayleigh block, 8 dB, J 0, seed 103, 4096, ACWRA, 1 ep | yes | PASS | `sim_20261023T074326380` | VALID; BER 1.22e-3; post-fade SINR 9.82 dB; ACWRA Keep Current |
| D | QPSK, AWGN, 12 dB, J 0.2, seed 104, 4096, SINR Threshold, 1 ep | yes | PASS | `sim_20261023T074329233` | VALID; J meas. 0.197; SINR 5.88 dB < 10 → next BPSK (rule) |
| A/B trend | as A and B, 5 episodes each (independent seeds) | yes | PASS | `…074331241`, `…074333313` | 16 dB: 0 errors in 5/5; 4 dB: mean BER 1.23e-2 vs theory 1.25e-2 |

## C. Dashboard functionality — PASS (27/27 browser checks, Playwright + Edge, live server)

Startup and all 8 pages without exceptions · GNU Radio state "3.10.12.0 · ready" · Live KPIs (BER, PER, goodput) equal
the saved episodes.csv · validation VALID/provenance shown · waveform, constellation, spectrum, PSD tabs rendered ·
input validation (OFDM-QPSK + 1000 symbols → error, Run disabled) · **Run simulation clicked in the UI** executed
`sim_20261023T074636798` (2 GNU Radio episodes) and the page showed its own BER (1.099e-03 = file) · page refresh
reloads results from disk · AI Agents shows the recorded decision; **decision JSON export identical to decisions.jsonl** ·
Policy Comparison from the campaign (SINR Threshold 77.1 kb/s; "ACWRA significantly worse" card) · Campaign Lab
artifact download byte-identical (`analysis.md`) · Run History search + row selection opens that run's detail ·
Diagnostics.

## D. Adaptive closed loop — PASS (backend); dashboard launch of dynamic schedules NOT AVAILABLE

`run_closed_loop` supports per-episode schedules (used by the campaign's `ramp_snr`, `step_jammer`, `step_fade`).
Run Simulation in the dashboard builds a constant schedule only, so the dynamic test used the backend with the
dashboard worker's recorder (`sim_20261023T074428023`, viewable in the dashboard): QPSK start, AWGN, SNR 16,16,8,8,4,4 dB,
J 0,0,0.05,0.05,0.2,0.2, seed 105, ACWRA, 6 × 4096 symbols, all episodes VALID gnuradio_export.

| Ep | SNR/J | Applied | BER | Risk | Gate / candidates | Selected → next |
|---|---|---|---|---|---|---|
| 0 | 16/0 | QPSK | 0 | 0.062 LOW | CLOSED · Keep Current | Keep Current → QPSK |
| 1 | 16/0 | QPSK | 0 | 0.058 LOW | CLOSED | Keep Current → QPSK |
| 2 | 8/0.05 | QPSK | 1.45e-2 | 0.263 MEDIUM | OPEN · Keep Current, QPSK | Keep Current → QPSK |
| 3 | 8/0.05 | QPSK | 1.23e-2 | 0.244 LOW | CLOSED | Keep Current → QPSK |
| 4 | 4/0.2 | QPSK | 1.03e-1 | 0.764 CRITICAL | OPEN · all 4 | **BPSK** (U +0.380) → BPSK |
| 5 | 4/0.2 | BPSK | 2.95e-2 | 0.406 MEDIUM | OPEN · Keep Current, QPSK | Keep Current (U +0.376) → BPSK |

Per-episode measurements, spectrum/twin/prediction outputs, candidate scores and gate are recorded; each decision was
applied to the next episode (ep4 decided BPSK, ep5 ran BPSK); Keep Current keeps the modulation.

**Why OFDM-QPSK is never selected** (evidence, algorithm unchanged): the gate offers OFDM-QPSK only at HIGH/CRITICAL
risk or an anomaly, always together with QPSK. The twin's link model gives OFDM-QPSK the same predicted BER as QPSK
(`virtual_rf/link_model.py`), while ACWRA scores it with lower spectral efficiency (CP factor 64/80, SE_norm 0.6 vs 1.0)
and a higher complexity prior (K_c 0.50 vs 0.25), e.g. ep4: QPSK U −0.881, OFDM-QPSK U −0.969. OFDM-QPSK is therefore
dominated by QPSK on every term. Campaign: ACWRA selected Keep Current 678× and BPSK 132× in 810 episodes, never OFDM-QPSK.

## E. Invalid input and failure handling — PASS (21/21)

SNR 99 / −45 dB rejected (`outside [-30, 60] dB`) · jammer −0.5 rejected · modulation QAM16 rejected · OFDM symbols not
a multiple of 64 rejected · an invalid spec submitted directly to the worker ends `invalid`, no exports · worker without
GNU Radio ends `blocked`, no exports, listed in alerts/diagnostics · two rapid Run clicks → one job · missing
episodes.csv → no episodes, labelled Invalid · missing NPZ → "No I/Q export" · corrupt NPZ → rejected and reported ·
malformed decisions line skipped · **forged BER in an NPZ → validator fails (content hash, bit counts), never shown
VALID** · no page crashes with damaged runs present.

## F. Research-data integrity — PASS after fix

43 MATLAB exports labelled "MATLAB (historical)", none as GNU Radio · fixture runs labelled Fixture (test suite) ·
aborted campaign labelled Aborted · unvalidated/tampered exports not shown as VALID · no result values hardcoded in the
UI · `src/acwra`, `src/agents`, `src/digital_twin`, `src/virtual_rf` identical to the baseline commit `a7477d4`; the only
`src/` change is the Windows ledger-path string in `gnuradio_phy/export.py`. Incomplete analyses: see G2.

## G. Bugs found and fixed

1. **Run with no recorded episodes read as complete.** A run whose `episodes.csv` was missing showed the heading
   "Run done" / "complete". Now: "This run produced no episodes", with job state and the missing file named.
   (`dashboard/views/live.py`; regression test added.)
2. **Incomplete campaigns shown as complete analyses.** A stopped/running dashboard campaign (e.g. 120 of 810 runs) was
   shown on Policy Comparison with means, paired statistics and findings and no warning. Now
   `backend.campaign_completion()` marks it, Policy Comparison shows "Incomplete campaign — state stopped, 120 of 810
   runs recorded… not a complete analysis", and the Overview card gets an "incomplete" badge.
   (`dashboard/backend.py`, `ui/components.py`, `views/comparison.py`, `views/overview.py`; regression test added.)

Tests after fixes: 561 passed / 7 skipped (GNU Radio environment); 553 passed / 15 skipped (Python 3.10 without GNU Radio).
Skips are environment-specific by design.

## H. Remaining limitations

- Run Simulation launches constant-condition runs only; dynamic (changing SNR/jammer) closed loops run through the
  backend/campaign scripts, not from a dashboard form.
- `worker.log` and `status.json` are written per run and listed under Run History → Artifacts, but there is no in-UI log
  viewer; job status/messages and failures are shown (top bar, alerts, Diagnostics).
- Sortable tables show missing values as a grey "None" (Streamlit grid), cards use "—".
- Visiting `/overview` directly shows "Page not found" (the Overview is served at `/`); sidebar navigation is unaffected.
- GNU Radio Companion GUI demo and SDR hardware were not tested (out of scope; no hardware).

## I. Verdict — COMPLETE FOR DEMONSTRATION

The core workflow works end to end: historical data loads and matches the report, real GNU Radio simulations run from
the dashboard and validate, and dashboard values match the saved backend files. Research caveat: the measured campaign
does not show ACWRA superiority — the SINR-threshold baseline had higher goodput and significantly lower BER.
