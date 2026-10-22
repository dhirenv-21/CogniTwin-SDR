# Experiment protocol — closed-loop adaptation (virtual RF)

Written **before** the sweep below was run (git history shows the order). Changing a
primary outcome after seeing results requires a new protocol version.

Protocol version: **CL-2** (2026-10-22). CL-1 = `results/evaluation/closed_loop/run_20261022_v1`
(the original evaluation, reproduced bit-for-bit as `repro_of_run_20261022_v1` before
any model change).

## Environment and what it can show

* Python `VirtualRFEnvironment` with the link abstraction in `src/virtual_rf/link_model.py`:
  SINR = g / (N0 + J) with a Gaussian-equivalent jammer, exact coherent BER, uncoded
  256-bit packets, and block fading. Each step draws one fading gain (Rayleigh: two paths,
  power split 0.8/0.2, matched-filter combining; Rician K = 2).
* The Digital Twin's sandbox uses the **expected** BER over the fading distribution. The
  environment's step outcome uses the **realised** gain. The twin therefore plans with a
  correct model but not with clairvoyance.
* **This is not a Simulink evaluation.** Results measure decision logic under a model the
  planner shares (except for the realised fade). No physical-layer claim follows from them.

## Units of analysis

* An **episode** is one (condition, policy, seed) run of N steps of 0.1 s. Steps inside an
  episode are correlated and are never treated as independent trials.
* The **independent unit** for statistics is the **condition**: the per-condition mean over
  seeds. Seeds vary the realised fading and the generated I/Q (agent observations). In AWGN
  conditions the outcome is deterministic given the decisions, so seeds add little there.
* Policies are **paired**: same condition, same seed, same fading realisation sequence (the
  environment's RNG draws do not depend on the modulation).

## Suites

* `original`: the six `config/scenarios/*.json` files (CL-1 conditions), 10 seeds.
* `sweep`: static conditions, 20 steps, 5 seeds. Channel ∈ {awgn, rayleigh} ×
  SNR ∈ {6, 12, 18} dB × broadband interference J ∈ {0, 0.03, 0.1, 0.3, 1.0}
  (relative to unit signal power): 30 conditions. The range was chosen a priori to span
  clean, recoverable and overwhelmed links. With uncoded 256-bit packets, the link is
  "overwhelmed" for every modulation at SINR ≲ 4 dB.

## Policies

| policy | description |
|---|---|
| `acwra` | full stack: Spectrum Agent → Digital Twin → Prediction Agent → Cyber Defense Agent → ACWRA; effective modulation applied next step |
| `fixed_BPSK`, `fixed_QPSK`, `fixed_OFDM-QPSK` | no adaptation (`fixed_QPSK` = keep the initial configuration, since every scenario starts in QPSK) |
| `snr_threshold` | rule (CL-1): BPSK if observed SNR < 8 dB or J > 0.5, else QPSK |
| `sinr_threshold` | rule: BPSK if SINR = 1/(N0+J) < 10 dB, else QPSK (threshold fixed a priori) |
| `oracle` | clairvoyant upper bound: best goodput under the **realised** gain of the step, no delay |
| ablations | `acwra_no_prediction` (risk = 0, status as insufficient), `acwra_no_history` (twin history cleared before every update), `acwra_no_confidence` (C = 1), `acwra_all_candidates` (Cyber Defense always proposes all four) |

## Outcomes (fixed in advance)

* **Primary:** episode mean goodput (kb/s), and episode mean BER.
* **Secondary:** regret against the oracle (kb/s), mean packet loss, mean spectral efficiency
  of the applied modulation, switches (changes of *effective* modulation), recovery steps
  after a keyframe change, decision time (ms), mean ACWRA utility, and the twin's 1-step SNR
  forecast MAE.
* **Comparisons:** ACWRA − baseline, paired per (condition, seed), averaged per condition.
  Reported as the mean of the condition-level differences, a 95 % bootstrap CI resampling
  conditions (10 000 resamples, seed 0), a Wilcoxon signed-rank test on the condition-level
  differences (two-sided, zero differences dropped), and the win/tie/loss count over
  conditions. With 30 conditions and many exact ties, p-values are descriptive; no
  multiple-comparison claim is made.

## Not measured

Real Simulink outcomes, coding gain, MAC/ARQ effects, and switching cost. A modulation
change is free in this model, so switch counts are reported but do not reduce goodput.
