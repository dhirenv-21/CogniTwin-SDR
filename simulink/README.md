# CogniTwin-SDR: MATLAB/Simulink Physical Layer & Python Ingest Bridge

MATLAB/Simulink physical-layer simulation and the export pipeline that feeds the
Python CogniTwin-SDR agent stack (`src/simulink_bridge`).

> **Rebuild required — v4 has never been executed.** The generator is **v4**. The
> `cognitwin_sdr_phy.slx` in this folder is a **v3** build (saved by MATLAB R2025a,
> user `dhire`, 2026-08-17T05:02Z; its `PHY_Channel` has no seed input), and every MAT
> file in `results/` predates v4. `run_simulink_case` refuses that `.slx`. On a machine
> with MATLAB + Simulink run, from `simulink/matlab`:
>
> ```matlab
> logDir = run_v4_validation
> ```
>
> It archives the current model and results first, then builds, diagnoses, runs the
> Rayleigh case and the baseline suite, and logs everything to `simulink/run_logs/<stamp>/`.
> Its `manifest.csv` lists every MAT file under `results/` with `written_this_run` 0/1 and
> its `model_version`, so stale exports cannot be mistaken for new ones. Full procedure:
> [`../MATLAB_HANDOFF.md`](../docs/reports/MATLAB_HANDOFF.md).

---

## Directory layout

```
simulink/
├── cognitwin_sdr_phy.slx              # Simulink PHY model (built by create_cognitwin_model.m)
├── create_cognitwin_model.m           # v4 model generator
├── create_cognitwin_model_v3_backup.m # v3 generator (real I/Q inputs, unseeded noise)
├── matlab/
│   ├── cognitwin_waveform.m           # BPSK / QPSK / OFDM-QPSK transmit waveforms
│   ├── cognitwin_check_modulation.m   # proves from the samples that tx is the labelled scheme
│   ├── cognitwin_measure_ber.m        # hard-decision demapper + true bit-error count
│   ├── cognitwin_gray2bin.m           # Gray -> binary (matches the Python mapping)
│   ├── cognitwin_bin2gray.m           # binary -> Gray
│   ├── diagnose_simulink_phy.m        # D1-D18 node-by-node PHY diagnostic (run first)
│   ├── run_simulink_case.m            # run ONE simulation, verify it, export a MAT file
│   ├── run_baseline_tests.m           # acceptance suite, criteria fixed before running
│   ├── run_simulink_campaign.m        # batch validation matrix for the ACWRA campaign
│   ├── run_v4_validation.m            # archive -> build -> D1-D18 -> Rayleigh case -> baseline, logged
│   ├── run_simulink_closed_loop.m     # Simulink in the loop: step k uses the ACWRA decision from step k-1
│   ├── run_simulink_case_v2_backup.m  # older drivers, kept for reference
│   ├── run_simulink_case_v3_backup.m
│   ├── init_cognitwin.m               # legacy parameter init          (unchanged)
│   ├── configure_scenario.m           # legacy NORMAL/MODERATE/SEVERE  (unchanged)
│   ├── export_results.m               # legacy MAT exporter            (unchanged)
│   └── run_validation.m               # legacy pure-MATLAB batch       (unchanged, no Simulink)
├── run_logs/<stamp>/                  # run_v4_validation: matlab_console.log, summary.txt, status.mat
├── results_archive/pre_v4_<stamp>/    # run_v4_validation: copy of results/ and the .slx before the run
└── results/
    ├── baseline/                      # run_baseline_tests output (currently v3 exports)
    ├── verification/                  # Python verifier reports
    ├── campaign/                      # run_simulink_campaign output
    └── campaign_report/               # Python campaign report (fixture data, not Simulink)
```

The v1/v2 generator backups mentioned in older notes are **not** in the repository;
only the v3 generator backup is.

---

## The model

```
iq_input_i (From Workspace, REAL [t, I]) --\
iq_input_q (From Workspace, REAL [t, Q]) ---\
SNR_dB, InterferencePower (Constant) --------> PHY_Channel (MATLAB Function)
ChannelGainRe, ChannelGainIm (Constant) ----/     x     = complex(xi, xq)
NOISE_I, NOISE_Q, JAM_I, JAM_Q -------------/      h     = complex(h_re, h_im)
  (Random Number, seeded, v4 default)              noise = sqrt(10^(-SNR/10)/2)*(n_I + j n_Q)
                                                   jam   = sqrt(P/2)*(j_I + j j_Q)
                                                   y     = h*x + jam + noise
      +--> rx_iq                (To Workspace)   received waveform
      +--> interference_signal  (To Workspace)   jammer on its own
      +--> noise_signal         (To Workspace)   AWGN on its own
      +--> tx_echo              (To Workspace)   x as PHY_Channel saw it
      +--> IQ_SCOPE
```

What is actually implemented (and what is not):

| Feature | Status |
|---|---|
| BPSK, QPSK (1 sample/symbol, Gray mapped) | implemented, generated in MATLAB, passed through the Simulink model |
| OFDM-QPSK (64 subcarriers, 16-sample CP) | implemented |
| AWGN | implemented inside `PHY_Channel` |
| Rayleigh, Rician (K = 2) | **block fading only**: one complex gain `h` per run, drawn in the driver, `E|h|^2 = 1`. No Doppler / time variation, no multipath delay spread |
| Interference | independent complex Gaussian jammer of power `InterferencePower` (not a tone, not swept) |
| Equalisation for BER | single-tap, by the **known** `h` (genie channel knowledge, not an estimate) |
| Pulse shaping / timing / carrier recovery | not modelled; sample-aligned baseband (`sps = 1` default) |

### SNR definition

`snr_db` is configured against the **unit-power transmit waveform, before fading
and interference**: `P_noise = 10^(-snr_db/10)`. Interference never enters SNR.

| exported field | definition | reference point |
|---|---|---|
| `snr_db` | configured value | — |
| `measured_snr_tx_ref_db` (v4) | `10 log10(P_tx / P_noise)` | pre-fading; compare with `snr_db` |
| `measured_snr_db` | `10 log10(|h|² P_tx / P_noise)` | post-fading (received SNR) |
| `measured_sir_db` | `10 log10(|h|² P_tx / P_jam)` | post-fading |
| `measured_sinr_db` | `10 log10(|h|² P_tx / (P_noise + P_jam))` | post-fading; BER theory uses this |

All powers are means over the logged arrays. The achieved noise power must be within
0.5 dB of `10^(-snr_db/10)` or the run is not exported. For AWGN `measured_snr_db`
equals `measured_snr_tx_ref_db`.

BER references (coherent, Gray mapped): QPSK and OFDM-QPSK `Q(√SINR)`, BPSK
`Q(√(2·SINR))`.

### v4: seeded noise

`randn` inside a MATLAB Function block uses the block's **own** generator, which
restarts from the same state on every simulation. The driver's `rng(...)` never
reached it. Measured from the v3 exports in `results/baseline/`:

* `noise_iq` is bit-identical for seeds 11, 23 and 37 (max difference `0.0`);
* `noise_iq` at 0 dB is exactly 10× the 20 dB draw; the P = 4 jammer is exactly 2× the P = 1 draw;
* `verify_simulink_mat.py --dir results/baseline` reports 343 different-seed pairs sharing one realisation.

Each v3 run is still internally consistent (power, SNR, BER versus theory all pass),
but the "multi-seed" results varied only the bits and `h`, never the noise.

v4 makes the noise source explicit. Choose it with `NoiseSource` before building:

| `NoiseSource` | noise source | seed control |
|---|---|---|
| `'random_number_blocks'` (**default**) | four Simulink *Random Number* blocks `NOISE_I`, `NOISE_Q`, `JAM_I`, `JAM_Q` (mean 0, variance 1, sample time `1/Fs`) feeding `PHY_Channel` inputs 7–10 | each block's own `Seed = mod(4*NoiseSeed + k, 4294967291)`, k = 0..3, so consecutive run seeds never share a stream |
| `'block_rng'` | `randn` inside `PHY_Channel` | `rng(noise_seed)` once per simulation behind a persistent guard; relies on `rng` support in MATLAB Function blocks |

```matlab
NoiseSource = 'block_rng';   % optional; omit for the default
create_cognitwin_model
```

The driver sets `NoiseSeed = opts.seed + 1000`, detects which build is loaded and
exports it as `noise_source`. **Neither variant has been run yet.** D13 measures
whether the seed really controls the noise, so don't trust either source until D13
passes. The `y = h·x + jam + noise` equation is unchanged, and the generator now
compiles the model (`SimulationCommand update`) before saving, so a
`PHY_Channel` error stops the build with its own message instead of producing an
unusable `.slx`.

### Sample count

`StopTime = SimStopTime = (N-1)/Fs` and the fixed-step discrete solver runs
`t = 0 … StopTime`, so solver steps = input samples = logged samples = N. A mismatch is
a hard error.

---

## Running it

All commands from MATLAB, starting at the repository root.

### 1. Build the model (once, and after any generator change)

```matlab
cd simulink
create_cognitwin_model           % backs the old .slx up to cognitwin_sdr_phy_backup_<timestamp>.slx
```

### 2. Diagnose before trusting anything

```matlab
cd matlab
report = diagnose_simulink_phy;  % prints D1-D18 PASS/FAIL; exports nothing except D18's temp file
```

| check | proves |
|---|---|
| D1-D3b | model exists, loads, is v3+ (real I/Q inputs) and v4 (seeded Random Number blocks or `NOISE_SEED`) |
| D4 | From Workspace input contract (real inputs accepted, complex rejected) |
| D5, D9 | `PHY_Channel` saw the exact tx; `rx = h·tx + jam + noise` sample for sample |
| D6 | noise power = `10^(-SNR/10)` at 0/10/20/40 dB |
| D7, D8 | jammer power and independence; `h` applied as supplied |
| D10 | sample count, time vector, Fs |
| D11 | noiseless loopback (SNR 200 dB): `rx == tx` |
| D12 | QPSK BER sanity at 30 dB and 0 dB |
| **D13** | same seed reproduces noise exactly; a different seed decorrelates it |
| **D14** | noise is circular and independent of the jammer |
| **D15** | interference P = 0→1 raises P_rx by ≈ 1 and raises BER |
| **D16** | a known fade scales signal power by `|h|²` and raises BER |
| **D17** | BPSK / QPSK / OFDM-QPSK are actually transmitted and decode error-free at 30 dB |
| **D18** | a `run_simulink_case` export contains every field the Python side reads |

### 3. Run a single case

```matlab
[outFile, m] = run_simulink_case('QPSK', 10, 0.25, 'Rayleigh');
```

Signature: `run_simulink_case(modulation, snrDb, interferencePower, channelType, opts)`

| argument | values | default |
|---|---|---|
| `modulation` | `'BPSK'`, `'QPSK'`, `'OFDM-QPSK'` | `'QPSK'` |
| `snrDb` | any real (dB, transmit-referenced) | `20` |
| `interferencePower` | `>= 0` (linear, relative to unit tx power) | `0` |
| `channelType` | `'AWGN'`, `'Rayleigh'`, `'Rician'` | `'AWGN'` |

`opts` fields: `Fs` (100e3), `nSamples` (10000), `seed` (42), `sps` (1),
`patternSymbols` (0), `name`, `outDir` (`simulink/results`), `timestamp`, `verbose`,
`strict` (true).

Every run passes a 13-check battery before it is written: tx echo, model-equation
residual, noise power vs SNR, jammer power, jammer/tx independence, signal presence,
LS vs true `h`, finiteness, time vector, complex rx, **tx matches modulation**,
**noise/jammer independence**, **noise circularity**. With `strict = true` (default)
any failure raises `run_simulink_case:PhysicsCheckFailed` and nothing is exported; a
Simulink error raises `run_simulink_case:SimulationFailed`.

### 4. Acceptance suite and campaign

```matlab
results = run_baseline_tests;            % sections 1-7, writes results/baseline/*.mat + CSV
files   = run_simulink_campaign('quick'); % or 'all' | 'modulation' | 'snr' | 'interference' | 'channel' | 'stress'
```

`run_baseline_tests` sections: 1 cases A–F, 2 SNR ladder × 3 seeds, 3 interference
sweep, 4 SINR monotonicity, 5 multi-seed, **6 BPSK and OFDM-QPSK coverage**, **7 noise
independence across seeds**.

---

## Simulink in the closed loop (implemented, NOT yet executed)

```matlab
loop = run_simulink_closed_loop                          % 10-step default schedule, AWGN
loop = run_simulink_closed_loop(struct('channel', 'Rayleigh'))
```

Step k runs `run_simulink_case` with the modulation chosen at step k-1. MATLAB then calls
`python experiments/acwra_decide.py --require-real` on the export, which validates it, runs
the agents and ACWRA, and keeps the Digital Twin history in `twin_state.json`. A failed
simulation or a rejected export stops the loop; no decision is ever invented. Outputs go to
`results/closed_loop/<stamp>/`. Needs Python with `requirements-lock.txt` on the MATLAB
machine.

## Measurement files

`run_simulink_case` writes `simulink/results/<stem>.mat` (MAT v7), stem
`sim_<mod>_snr<x>_int<p>_<channel>` unless `opts.name` is given. Fields:

| group | fields |
|---|---|
| I/Q (complex N×1) | `iq_samples` (rx), `tx_iq`, `noise_iq`, `interference_iq`, `time_vector` |
| configuration | `modulation`, `channel_type`, `snr_db`, `interference_power`, `sample_rate`, `num_samples`, `samples_per_symbol`, `pattern_symbols`, `seed`, `noise_seed`*, `sim_stop_time`, `fixed_step`, `timestamp` |
| provenance | `source` = `'simulink'`, `model_name`, `model_version`* = `'v4'`, `noise_source`*, `run_id`*, `snr_definition`* |
| measured | `measured_signal_power`, `measured_noise_power`, `measured_interference_power`, `measured_power`, `measured_tx_power`, `measured_snr_db`, `measured_snr_tx_ref_db`*, `measured_sir_db`, `measured_sinr_db` |
| channel | `channel_gain_real/imag/mag`, `channel_gain_ls_real/imag`, `channel_estimate_rel_error` |
| BER | `ber`, `bit_errors`, `bits_compared` |
| evidence | `checks_passed`, `check_*` values, `check_names`*, `sim_wall_seconds` |

\* added in v4. All earlier fields keep their names and meaning.

## Python consumption

```bash
python experiments/verify_simulink_mat.py --dir simulink/results/baseline   # independent recomputation
python experiments/simulink_acwra_demo.py --mat simulink/results/<file>.mat --require-real
python experiments/simulink_acwra_campaign.py --source matlab
```

* `SimulinkReceiver.load_and_validate()` (`src/simulink_bridge/receiver.py`) runs
  `validate_mat_dict()` and, in strict mode, refuses the file on any failed check. Options:
  `require_real=True` (only a MATLAB-written `source='simulink'` file passes),
  `require_model_version="v4"`, and `not_before=<POSIX time>`, which rejects files older
  than the run. The measurement's `provenance` field is one of `simulink_export`,
  `simulink_claim_unverified`, `matlab_unlabelled`, `legacy_python_mat`, `python_fixture`,
  `synthetic_demo` or `unknown`.
  New in v4: a file with `checks_passed = 0` is rejected, and a `source = 'simulink'`
  file whose `tx_iq` is not the labelled modulation is rejected (Python fixtures only
  warn).
* `verify_simulink_mat.py` recomputes every power, SNR, SIR and SINR from the arrays.
  It re-demodulates BPSK, QPSK **and OFDM-QPSK** in Python, using bits re-derived from
  `tx_iq`. It checks the power budget `P_rx ≈ |h|²P_tx + P_noise + P_jam`, noise
  circularity and modulation identity. In directory mode it fails if runs with
  different seeds share a noise or jammer realisation. Results tables such as
  `baseline_results.mat` are skipped, not failed.

---

## Known limitations / unverified

* **v4 has not been executed.** No working MATLAB install exists on the machine where
  it was written (the `R2026a` folder there is partial: no `matlab.exe`, no Simulink).
  Its correctness rests on static review, a structural lint of every `.m` file and
  the Python tests. D13 is the decisive runtime check.
* `results/` also holds pre-v3 evidence: `sim_qpsk_snr10_int0_rayleigh.mat` and
  `sim_qpsk_snr10_int0p25_rayleigh.mat` are v2 zero-signal exports (|h| ≈ 0.004,
  BER ≈ 0.496), correctly rejected by the verifier. `run_simulink_case('QPSK', 10,
  0.25, 'Rayleigh')` overwrites the second one, which is why `run_v4_validation`
  archives `results/` first.
* Fading is block (one `h` per run). There is no Doppler, no time variation and no
  frequency selectivity. OFDM therefore never sees a frequency-selective channel.
* BER uses the known `h` (perfect CSI) and sample-aligned symbols. No synchronisation,
  pulse shaping or channel estimation is exercised.
* The jammer is wideband Gaussian; tone, swept or pulsed jammers from
  `config/scenarios/*.json` are **not** reproduced in Simulink.
* The modulation classifier limitation below is unchanged.

## Note on the modulation classifier

The Task-5 classifier (`results/ai/modulation_classifier/rf_model.joblib`, still on disk,
`ORIGINAL_MODEL_PATH`) was trained only on tiled 32-symbol patterns and labelled every
non-repeating BPSK/QPSK window `OFDM-QPSK` (measured: 0 % on those classes). The default
model is now `rf_model_mixed.joblib`, trained by `experiments/retrain_modulation_classifier.py`
on tiled + non-repeating, unit-power-normalised, phase-rotated and partly jammed windows. So
`opts.patternSymbols = 32` is no longer needed for correct detection. Synthetic held-out
accuracy, inputs as served: 0.95 tiled, 0.95 non-repeating, 0.94 impaired. In the 402-check
fixture campaign the pipeline now detects BPSK 33/33, QPSK 46/59 and OFDM-QPSK 32/33 windows.
Real-Simulink accuracy is unmeasured.

## Legacy files

`init_cognitwin.m`, `configure_scenario.m`, `export_results.m` and `run_validation.m`
are unchanged. `run_validation.m` is a **pure MATLAB script** and never opens the
`.slx`. The `results/measurement_*.mat` files in the repository have the MAT header
`Platform: nt`. That is the signature of SciPy's `savemat`, not of MATLAB
(`PCWIN64`), so these copies were written by Python, not by MATLAB or Simulink.
