# GNU Radio physical layer: setup, execution and limitations

**Status (2026-10-22): executed.** radioconda 2025.03.14 (installer SHA-256 verified) was
installed just for the user at `%UserProfile%\radioconda`, not registered as the system Python.
The project runs in the `cognitwin-gr` environment: Python 3.12.15, GNU Radio 3.10.12.0, NumPy 2.2.6,
SciPy 1.15.2, scikit-learn 1.7.2, OpenBLAS. All 12 GNU Radio execution tests pass, and the BER
validation `results/gnuradio/ber_validation/ber_20261022_v1/` passes 18/18 points. The Spectrum Agent
evaluation, campaign and GRC GUI have **not** been run yet.

## 1. What is used

| item | value |
|---|---|
| GNU Radio | 3.10.x (API checked against `maint-3.10` sources: `ofdm_cyclic_prefixer(input_size, output_size)`, `noise_source_c` amplitude = sqrt(total power), `fading_model(N, fDTs, LOS, K, seed)`) |
| modules | `gr`, `blocks`, `digital`, `filter`, `analog`, `channels`, `fft`; `qtgui` for the GRC demo only |
| Python side | same packages as `requirements-lock.txt` (NumPy, SciPy, scikit-learn 1.7.2 for the saved classifier, joblib, matplotlib, pytest) |
| hardware | none (software simulation only; no SDR device, nothing over the air) |

## 2. Installation (separate environment, existing Python untouched)

GNU Radio's Windows distribution is conda-based (official route: radioconda or the
conda-forge `gnuradio` package). Do **not** `pip install` GNU Radio into the existing
Python 3.10 install: there is no supported wheel.

**Option A: radioconda (recommended on Windows).**
1. Download `radioconda-<version>-Windows-x86_64.exe` from
   <https://github.com/radioconda/radioconda-installer/releases> (graphical installer, about
   1 GB installed). Install "Just Me", without registering it as the system Python.
2. Start **radioconda Prompt** from the Start menu, then:

```bash
mamba create -n cognitwin-gr -c conda-forge python=3.12 numpy=2.2 scipy=1.15 "libblas=*=*openblas" gnuradio=3.10.12 scikit-learn=1.7.2 matplotlib joblib pytest pyyaml
mamba activate cognitwin-gr
python -c "from gnuradio import gr; print(gr.version())"
```

(Option A's base environment already includes GNU Radio. The separate `cognitwin-gr`
environment keeps the project's packages apart from radioconda's.)

**Option B: Miniforge + conda-forge.** Install Miniforge from
<https://github.com/conda-forge/miniforge>, open "Miniforge Prompt" and run the same
`mamba create ...` line.

**Option C: Linux / WSL2 Ubuntu 24.04.** `sudo apt install gnuradio` (3.10.9), then
`pip install -r requirements-lock.txt` in a venv created with `--system-site-packages`.
Installing WSL changes the Windows system configuration, so the user must decide on it
and run it.

If NumPy in the GNU Radio environment differs from `requirements-lock.txt`, that is
expected. Check the classifier still reproduces with
`python experiments/retrain_modulation_classifier.py --check`.

## 3. Resume commands (in the GNU Radio environment, from the repository root)

```bash
python -c "from src.gnuradio_phy import gnuradio_available, gnuradio_version; print(gnuradio_available(), gnuradio_version())"
python -m pytest -q -rs                                         # the 12 GNU Radio execution tests now run
python experiments/gnuradio_phy_run.py --modulation QPSK --snr 10 --jammer 0.05
python experiments/gnuradio_ber_validation.py                   # BER vs theory, reproducibility (~10-20 min)
python experiments/gnuradio_spectrum_eval.py                    # Spectrum Agent on GNU Radio I/Q
python experiments/gnuradio_demo.py                             # headless demo, prints every stage
python experiments/gnuradio_campaign.py --smoke                 # first: 2 conditions x 1 seed
python experiments/gnuradio_campaign.py --run-id grcl1_<date>   # full campaign (27 conditions x 5 seeds x 6 policies)
gnuradio-companion grc/cognitwin_phy_demo.grc              # visual demo (QT GUI)
```

Order matters: the BER validation is the PHY acceptance test. If it fails, do not run
the campaign; report the failure.

## 4. Flowgraph (`src/gnuradio_phy/flowgraph.py`, version `gr-phy-1`)

PSK (BPSK / QPSK): `vector_source_b` (symbol indices) → `chunks_to_symbols_bc` →
`interp_fir_filter_ccf` (unit-energy RRC, α = 0.35, 11 symbols, 4 sps) → channel →
`add_vcc` with `noise_source_c` and a second `noise_source_c` (the jammer), each limited by
`head` → `fir_filter_ccf` matched filter. The noise and jammer branches are matched
filtered separately as well, so SNR and J are measured, not assumed.

OFDM-QPSK: `chunks_to_symbols_bc` → `stream_to_vector(64)` → `fft_vcc(64, inverse)` →
`multiply_const_vcc(1/8)` → `ofdm_cyclic_prefixer(64, 80)` → channel → noise + jammer. There is
no pulse shaping.

Channel (`fading_mode`):

| mode | block | meaning |
|---|---|---|
| `none` | `multiply_const_cc(1)` | AWGN |
| `block` | `multiply_const_cc(h)` | one complex gain per run, drawn from the fading seed (static within a run, block fading across runs, as in Simulink v4) |
| `time_varying` | `channels.fading_model` (8 sinusoids, fD·Ts per flowgraph sample) | gain changes within the run; a second `fading_model` with the same seed fed with ones records the gain, and the run checks `faded == gain × input` (`gain_capture_ok`) |

NumPy draws only experiment parameters: the bits and the one-per-run block gain. All
signal processing is done by GNU Radio blocks (`tests/test_gnuradio_static.py` checks this).

Conventions are those of the Simulink bridge: `snr_db` = Es/N0 per exported sample
without jammer and fade; `J` = jammer power relative to the unit-energy symbol; with
unit-energy RRC filters the per-symbol noise variance after the matched filter equals the
oversampled per-sample variance, so Es/N0 = 1/σ².

Receiver (`src/gnuradio_phy/receiver.py`, Python on the GNU Radio captures): known filter
delay checked by a correlation search over all lags (`timing_ok`), genie one-tap
equaliser with the true captured gain, hard decisions, BER, PER over 256-bit packets.
For OFDM this is CP removal + FFT + one-tap equaliser on a known frame: **not a full OFDM
receiver** (no synchronisation, pilots or channel estimation).

Analytical reference: BPSK Q(√(2|h|²γ)), QPSK / OFDM-QPSK Q(√(|h|²γ)), γ = 1/(N0 + J),
conditional on the realised gains (`theoretical_ber`). QPSK at Es/N0 = BPSK at Eb/N0 + 3.01 dB.

## 5. Export, provenance, bridge

One NPZ per run in the bridge schema (`docs/DATA_SCHEMA_PROVENANCE.md` §2b), a
`content_sha256` over every variable, and a line in `results/gnuradio/run_ledger.jsonl`.
`validate_gnuradio_dict` runs the existing `validate_mat_dict` battery and then the GNU
Radio checks. Provenance classes are `gnuradio_export` and `gnuradio_claim_unverified`. The
label alone never qualifies. A complete forgery would pass, because this is consistency
evidence, not a signature.

`src/gnuradio_phy/runner.decide_on_export` feeds a validated export to the **unchanged**
`SimulinkACWRAPipeline.run_measurement` (Spectrum Agent → Digital Twin → Prediction → Cyber
Defense → ACWRA). An invalid export raises before any agent sees it. The twin gets the
noise-only SNR from `noise_iq`. The Spectrum Agent sees only the I/Q. Interference power is
passed through as metadata by the existing agent, not estimated.

## 6. Closed loop and campaign

`src/gnuradio_phy/closed_loop.py` runs episodes. Each episode is one complete flowgraph
run, and the decision from episode e sets episode e + 1 (sequential reconfiguration, not
streaming). Policies: `acwra`, `no_adaptation` (decides, never applies), `fixed_BPSK`,
`fixed_QPSK`, `fixed_OFDM-QPSK`, `sinr_threshold` (on measured SINR). Seeds are paired
across policies. Goodput = (1 − measured PER) × payload rate (100 / 200 / 160 kb/s); SE =
goodput / occupied bandwidth ((1 + α)·Rs for PSK, Rs for OFDM). Statistics are condition
level, as in protocol CL-2.

The prior virtual-RF findings stand until GNU Radio data says otherwise: in CL-2 the
SINR-threshold rule beat ACWRA on goodput and BER in the 30-condition sweep, and the twin's
trend forecast lost to persistence on steps.

## 7. GNU Radio Companion demo

`grc/cognitwin_phy_demo.grc` (QT GUI): QPSK with the same constellation, RRC and
noise conventions; sliders for Es/N0 and jammer power; time, frequency and constellation
sinks. It visualises the chain only. Decisions come from `experiments/gnuradio_demo.py`,
which runs the measurement flowgraph and the full agent pipeline and writes
waveform/spectrum/constellation PNGs: this is the headless fallback. The `.grc` file has
been checked statically (YAML structure, connections, constellation table); it has
**not** been opened in GNU Radio Companion.

## 8. Troubleshooting

* **Pin the environment as in section 2.** Unpinned, conda-forge resolved Python 3.14.9 and NumPy 2.5.4 with
  MKL 2026.2, whose cached package was reported invalid. `numpy.polyfit` then crashed the interpreter
  with `Windows fatal exception: code 0xc06d007f` (DLL delay-load failure in LAPACK). The pinned
  environment (Python 3.12, NumPy 2.2, OpenBLAS) does not crash. If it happens anyway, run
  `mamba clean --tarballs` and recreate the environment.

* `ModuleNotFoundError: gnuradio`: the wrong interpreter. Run from the activated conda
  environment; `python -c "import sys; print(sys.executable)"` must point into it.
* `ImportError: DLL load failed` on Windows: GNU Radio was started outside its conda
  environment (PATH lacks `Library\bin`). Use the radioconda/Miniforge prompt.
* `qt.qpa.plugin: Could not load the Qt platform plugin`: run GRC from the same
  environment; for headless machines use `gnuradio_demo.py` instead.
* Classifier load warning / scikit-learn version error: install `scikit-learn=1.7.2` in
  the GNU Radio environment.
* `gr_flowgraph_matches_repository` warning: the export came from a different version of
  `flowgraph.py`. Re-run instead of mixing versions.
* `timing_ok = False`: the filter delay assumption failed (different RRC length or a
  changed GNU Radio filter convention). Report it; do not adjust the delay by hand.

## 9. Limitations

* Not executed: no GNU Radio run, BER validation, Spectrum Agent evaluation, closed loop
  or campaign result exists yet. The code was written against the 3.10 API without
  running it, so first execution may surface API mistakes; the tests will show them.
* Software simulation only: no hardware, no over-the-air claim, no synchronisation,
  no carrier/timing recovery, genie CSI.
* GNU Radio results do not validate the unexecuted Simulink v4 model. Each is its own data
  class: historical Simulink v3, unexecuted Simulink v4, GNU Radio, virtual RF, synthetic.
* Time-varying fading comes only from `fading_model` (flat, sum of sinusoids). No
  frequency-selective channel.
* No literature review was done, and no novelty claim is made.
