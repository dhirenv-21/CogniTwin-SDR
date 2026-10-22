# grcl1_20261022: ABORTED (no results)

Aborted at condition 17/27 (`static_rayleigh_snr8_J0.05`, seed 2). The validator rejected
the GNU Radio export `gr-BPSK-RAYLEIGH-block-snr+8.0-J0.200-s17001002-18f86a127c` with
`gr_timing_ok: symbol timing lag 10 != expected 44` (log: `aborted_run.log`).

Diagnosis (re-run of that exact configuration): the block fade was |h| = 0.021
(-33.6 dB; P = 0.04 %), effective SINR -29 dB, BER 0.49. The timing correlation
peak was only 2.2 sigma above noise, so the self-check was uninformative, not a
flowgraph delay error. Fix: the timing check is skipped when the expected peak is
below 8 sigma (`receiver.TIMING_RESOLVABLE_Z`), as the bridge does for
wanted_signal_present; it still fails on resolvable links. Regression tests:
`test_timing_check_skipped_only_when_uninformative`,
`test_deep_fade_episode_from_campaign_validates`.

The campaign was re-run from scratch as `grcl1_20261022_v2`. This folder is kept as evidence and was not overwritten.
