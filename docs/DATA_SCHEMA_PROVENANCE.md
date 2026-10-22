# Data schema and provenance

## 1. MAT export (`simulink/matlab/run_simulink_case.m`, MAT v7)

The source of truth is the `m.<field> = …` block in `run_simulink_case.m`.
`tests/test_matlab_static_contract.py` fails if the Python readers use a field that block
does not export.

| group | fields | v3 exports | v4 exports |
|---|---|---|---|
| I/Q (complex N×1) | `iq_samples` (rx), `tx_iq`, `noise_iq`, `interference_iq`, `time_vector` | ✓ | ✓ |
| configuration | `modulation`, `channel_type`, `snr_db`, `interference_power`, `sample_rate`, `num_samples`, `samples_per_symbol`, `pattern_symbols`, `seed`, `sim_stop_time`, `fixed_step`, `timestamp`, `model_name` | ✓ | ✓ |
| provenance | `source` = `'simulink'` | ✓ | ✓ |
| provenance (v4) | `model_version` = `'v4'`, `noise_seed`, `noise_source`, `run_id`, `snr_definition` | — | ✓ |
| measured | `measured_{signal,noise,interference,tx}_power`, `measured_power`, `measured_snr_db` (post-fade), `measured_sir_db`, `measured_sinr_db` | ✓ | ✓ |
| measured (v4) | `measured_snr_tx_ref_db` (pre-fade, comparable with `snr_db`) | — | ✓ |
| channel | `channel_gain_{real,imag,mag}`, `channel_gain_ls_{real,imag}`, `channel_estimate_rel_error` | ✓ | ✓ |
| BER | `ber`, `bit_errors`, `bits_compared` | ✓ | ✓ |
| evidence | `checks_passed`, `check_tx_echo_max_error`, `check_sum_residual`, `check_jam_tx_correlation`, `check_signal_present`, `check_estimator_margin_db`, `sim_wall_seconds` | ✓ | ✓ |
| evidence (v4) | `check_noise_jam_correlation`, `check_noise_iq_balance_db`, `check_tx_matches_modulation`, `check_names` | — | ✓ |

Missing v4 fields in a v3 file are **absent**; nothing fills them in.
`validate_mat_dict` records `model_version = "pre-v4"` for such files, as a fact derived
from the absence, not stored in the file.

**SNR definitions.** `snr_db`: configured, noise power 10^(−snr_db/10) against the unit-power
transmit waveform, before fading and interference. `measured_snr_db`: |h|²·P_tx/P_noise
(after fading). `measured_sinr_db`: |h|²·P_tx/(P_noise + P_jam). The bridge hands the
Digital Twin P_tx/P_noise per window (transmit-referenced, noise only); see
`docs/ARCHITECTURE.md`.

## 2. Provenance classes (`src/simulink_bridge/validation.py::classify_provenance`)

The MAT **header** records who wrote the file. MATLAB writes `Platform: PCWIN64` (or
GLNXA64, MACI64, …); SciPy writes `Platform: nt` (or posix). The `source` variable is a
user-controlled label and is never sufficient on its own.

| class | rule | example in this repository |
|---|---|---|
| `simulink_export` (A) | MATLAB-written **and** `source` starts with `simulink` | `simulink/results/baseline/*.mat` (v3, 2026-08-17) |
| `simulink_claim_unverified` | `source = simulink` but not MATLAB-written | a SciPy file relabelled; rejected by `require_real` |
| `matlab_unlabelled` | MATLAB-written, no Simulink label | `simulink/results/baseline/baseline_results.mat` (results table) |
| `legacy_python_mat` (B) | SciPy-written, no recognised label | `simulink/results/measurement_{normal,moderate,severe}.mat` |
| `python_fixture` (C) | `source = python-fixture` | files from `src/simulink_bridge/reference_phy.py` |
| `synthetic_demo` (D) | `source` starts with `synthetic` / `demo` | — |
| `unknown` | no header, no label | in-memory dicts |

GNU Radio exports (NPZ, `src/gnuradio_phy/validation.py`) add two classes. The
`source = gnuradio` label alone never qualifies:

| class | rule |
|---|---|
| `gnuradio_export` | `source = gnuradio` **and** content hash intact **and** GNU Radio 3.x.y version **and** `flowgraph_sha256` = this repository's `src/gnuradio_phy/flowgraph.py` **and** config hash reproduces **and** decisions recomputed from the samples reproduce `bit_errors` **and** timing / gain-capture self-checks passed **and** the (experiment_id, hash) pair is in `results/gnuradio/run_ledger.jsonl` or was produced by `run_flowgraph` in the current process |
| `gnuradio_claim_unverified` | labelled `gnuradio`, at least one item missing or wrong |

This is consistency evidence, not cryptographic proof: a complete forgery (all hashes plus
a ledger line) passes, and `tests/test_gnuradio_export_validation.py` documents that. No
GNU Radio export exists in this repository yet; GNU Radio has not been executed here.

Provenance is not validity. The two v2 exports
`simulink/results/sim_qpsk_snr10_int0{,p25}_rayleigh.mat` are genuine `simulink_export` files
from a broken model (|h| ≈ 0.004, BER ≈ 0.5) and fail the physics checks.

## 2b. GNU Radio NPZ export (`src/gnuradio_phy/export.py`, schema `cognitwin-gr-export-1`)

Same variable names and units as the MAT export above (`iq_samples`, `tx_iq`, `noise_iq`,
`interference_iq`, `snr_db`, `measured_snr_db`, `ber`, `bit_errors`, `bits_compared`,
`modulation`, `interference_power`, `channel_type`, `channel_gain_real/imag` for constant
channels, `sample_rate`, `time_vector`, `num_samples`, `source`, `run_id`, `model_version`,
`noise_seed`). Added: `schema_version`, `simulator`, `gnuradio_version`, `flowgraph_version`,
`flowgraph_sha256`, `flowgraph_blocks`, `config_json`, `config_hash`, `experiment_id`, `seed`,
`fading_mode`, `channel_gain_iq` (gain per exported sample), `reference_bits`,
`measured_interference_power`, `per`, `packets`, `ber_theory`, `waveform_sample_rate`,
`receiver_settings`, `timing_ok`, `timing_lag_*`, `gain_capture_ok/error`, `wall_time_s`,
`python_version`, `platform`, `created_utc`, `content_sha256`. Loaded with
`allow_pickle=False`; files are never overwritten.

PSK exports are symbol-rate samples after the matched filter (one per symbol, as the
Simulink export); OFDM-QPSK exports are the time-domain samples (64-point IFFT + 16 CP).

## 3. Historical vs new data

| dataset | class | model | status |
|---|---|---|---|
| `simulink/results/baseline/` (35 exports + table) | A | v3 | historical; noise identical across seeds (verified) |
| `simulink/results/sim_qpsk_snr10_int0_awgn.mat`, `..._int0p4_awgn.mat` | A | v3 | historical, valid |
| `simulink/results/sim_qpsk_snr10_int0{,p25}_rayleigh.mat` | A | v2 | historical, physically invalid (kept as evidence) |
| `simulink/results/measurement_*.mat` | B | — | legacy Python files, no tx reference |
| `simulink/results/campaign_fixture/` (git-ignored) | C | — | regenerable fixtures |
| v4 exports | A | v4 | **do not exist yet** |

Rules: historical files are never modified. `run_v4_validation.m` copies `simulink/results/`
to `simulink/results_archive/pre_v4_<stamp>/` before overwriting. Its `manifest.csv` marks
which files the run wrote (`written_this_run`).

## 4. Validation (`validate_mat_dict`, `SimulinkReceiver.load_and_validate`)

Always: required variables (`iq_samples`, `snr_db`, `modulation`); I/Q shape (N×1, 1×N,
N×2 real [I Q]); finite values; ≥ 64 samples; nonzero power; scalar finite SNR; BER in
[0, 1]; text modulation and channel; non-negative interference; time vector length and
monotonicity; tx length; wanted-signal presence; modulation signature (FAIL for
`simulink` files, WARN otherwise); `checks_passed = 1` if present; `num_samples` matches;
`noise_iq` / `interference_iq` length and finiteness; BER = bit_errors / bits_compared;
`fixed_step` = 1/Fs; finite channel gains and measured SNR.

Opt-in: `require_real=True` (class A only), `require_model_version="v4"`,
`not_before=<POSIX time>` (rejects files last modified before a run started).

## 5. Run artifacts written by Python experiments

Every run directory under `results/evaluation/closed_loop/<run_id>/` has a `config.json`
recording the protocol, the git commit (with `-dirty` if `src/` or `experiments/` differed),
suites, conditions, seeds, policies, weights, Python and numpy versions, start time (UTC),
wall time, and the environment label `"Python VirtualRFEnvironment + link_model (NOT
Simulink)"`.
