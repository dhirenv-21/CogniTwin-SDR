# Closed-loop evaluation `repro_20261022T172510` (protocol CL-2)

Commit `3c9752c`; 132 episodes, 4180 steps; environment: Python virtual RF (NOT Simulink). Mean (std over seeds).

## Suite `original` - paired comparisons (ACWRA - baseline, condition-level)

| baseline | metric | n cond | mean diff | 95% CI | W/T/L | Wilcoxon p |
|---|---|---|---|---|---|---|
| acwra_no_prediction | mean_goodput_kbps | 6 | +0.2545 | [+0, +0.7635] | 1/5/0 | nan |
| acwra_no_prediction | mean_ber | 6 | -0.0007113 | [-0.002134, +0] | 0/5/1 | nan |
| acwra_no_prediction | mean_regret_kbps | 6 | -0.2545 | [-0.7635, +0] | 0/5/1 | nan |
| acwra_no_prediction | switches | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_history | mean_goodput_kbps | 6 | +0.2545 | [+0, +0.7635] | 1/5/0 | nan |
| acwra_no_history | mean_ber | 6 | -0.0007113 | [-0.002134, +0] | 0/5/1 | nan |
| acwra_no_history | mean_regret_kbps | 6 | -0.2545 | [-0.7635, +0] | 0/5/1 | nan |
| acwra_no_history | switches | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | mean_goodput_kbps | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | mean_ber | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | mean_regret_kbps | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | switches | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_all_candidates | mean_goodput_kbps | 6 | -0.2024 | [-0.6072, +0] | 0/5/1 | nan |
| acwra_all_candidates | mean_ber | 6 | +0.0002589 | [+0, +0.0007766] | 1/5/0 | nan |
| acwra_all_candidates | mean_regret_kbps | 6 | +0.2024 | [+0, +0.6072] | 1/5/0 | nan |
| acwra_all_candidates | switches | 6 | +0.1667 | [+0, +0.5] | 1/5/0 | nan |
| fixed_BPSK | mean_goodput_kbps | 6 | +46.51 | [+31.22, +69.77] | 6/0/0 | 0.0312 |
| fixed_BPSK | mean_ber | 6 | +0.001268 | [+0.000465, +0.002056] | 5/1/0 | 0.0625 |
| fixed_BPSK | mean_regret_kbps | 6 | -46.51 | [-69.77, -31.22] | 0/0/6 | 0.0312 |
| fixed_BPSK | switches | 6 | +1 | [+0.5, +1.5] | 5/1/0 | 0.0625 |
| fixed_QPSK | mean_goodput_kbps | 6 | -6.348 | [-12.91, +0.1612] | 2/2/2 | nan |
| fixed_QPSK | mean_ber | 6 | -0.02617 | [-0.03808, -0.01247] | 0/1/5 | 0.0625 |
| fixed_QPSK | mean_regret_kbps | 6 | +6.348 | [-0.1612, +12.91] | 2/2/2 | nan |
| fixed_QPSK | switches | 6 | +1 | [+0.5, +1.5] | 5/1/0 | 0.0625 |
| fixed_OFDM-QPSK | mean_goodput_kbps | 6 | -6.348 | [-12.91, +0.1612] | 2/2/2 | nan |
| fixed_OFDM-QPSK | mean_ber | 6 | -0.02617 | [-0.03808, -0.01247] | 0/1/5 | 0.0625 |
| fixed_OFDM-QPSK | mean_regret_kbps | 6 | +6.348 | [-0.1612, +12.91] | 2/2/2 | nan |
| fixed_OFDM-QPSK | switches | 6 | +1 | [+0.5, +1.5] | 5/1/0 | 0.0625 |
| snr_threshold | mean_goodput_kbps | 6 | -6.362 | [-12.91, +0.1321] | 2/2/2 | nan |
| snr_threshold | mean_ber | 6 | -0.007845 | [-0.01457, -0.002131] | 0/2/4 | nan |
| snr_threshold | mean_regret_kbps | 6 | +6.362 | [-0.1321, +12.91] | 2/2/2 | nan |
| snr_threshold | switches | 6 | +0.3333 | [+0, +1] | 1/5/0 | nan |
| sinr_threshold | mean_goodput_kbps | 6 | -6.079 | [-12.46, +0] | 0/4/2 | nan |
| sinr_threshold | mean_ber | 6 | -0.0007555 | [-0.001722, +0] | 0/4/2 | nan |
| sinr_threshold | mean_regret_kbps | 6 | +6.079 | [+0, +12.46] | 2/4/0 | nan |
| sinr_threshold | switches | 6 | +0.1667 | [+0, +0.5] | 1/5/0 | nan |
| oracle | mean_goodput_kbps | 6 | -8.165 | [-18.1, -0.007379] | 0/2/4 | nan |
| oracle | mean_ber | 6 | +0.001219 | [+0.0003675, +0.002045] | 4/1/1 | 0.125 |
| oracle | mean_regret_kbps | 6 | +8.165 | [+0.007379, +18.1] | 4/2/0 | nan |
| oracle | switches | 6 | -1.167 | [-3.5, +0] | 0/5/1 | nan |

### Suite `original` - policy means over conditions

| policy | goodput kb/s | BER | regret kb/s | switches | oracle agree | decide ms |
|---|---|---|---|---|---|---|
| acwra | 106.2 | 0.0572 | 8.2 | 1.00 | 0.88 | 0.13 |
| acwra_no_prediction | 106.0 | 0.0579 | 8.4 | 1.00 | 0.87 | 0.13 |
| acwra_no_history | 106.0 | 0.0579 | 8.4 | 1.00 | 0.87 | 0.13 |
| acwra_no_confidence | 106.2 | 0.0572 | 8.2 | 1.00 | 0.88 | 0.12 |
| acwra_all_candidates | 106.4 | 0.0569 | 8.0 | 0.83 | 0.89 | 0.14 |
| fixed_BPSK | 59.7 | 0.0559 | 54.7 | 0.00 | 0.43 | 0.00 |
| fixed_QPSK | 112.6 | 0.0833 | 1.8 | 0.00 | 0.85 | 0.00 |
| fixed_OFDM-QPSK | 112.6 | 0.0833 | 1.8 | 0.00 | 0.85 | 0.00 |
| snr_threshold | 112.6 | 0.0650 | 1.8 | 0.67 | 0.86 | 0.00 |
| sinr_threshold | 112.3 | 0.0579 | 2.1 | 0.83 | 0.96 | 0.00 |
| oracle | 114.4 | 0.0559 | 0.0 | 2.17 | 1.00 | 0.00 |

