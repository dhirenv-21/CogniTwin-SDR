# Closed-loop evaluation `cl2_20261022` (protocol CL-2)

Commit `2a38917`; 2310 episodes, 53900 steps; environment: Python virtual RF (NOT Simulink). Mean (std over seeds).

## Suite `original` - paired comparisons (ACWRA - baseline, condition-level)

| baseline | metric | n cond | mean diff | 95% CI | W/T/L | Wilcoxon p |
|---|---|---|---|---|---|---|
| acwra_no_prediction | mean_goodput_kbps | 6 | -0.4593 | [-1.913, +0.5352] | 1/4/1 | nan |
| acwra_no_prediction | mean_ber | 6 | -0.00024 | [-0.0005265, +0] | 0/4/2 | nan |
| acwra_no_prediction | mean_regret_kbps | 6 | +0.4593 | [-0.5352, +1.913] | 1/4/1 | nan |
| acwra_no_prediction | switches | 6 | -0.01667 | [-0.05, +0] | 0/5/1 | nan |
| acwra_no_history | mean_goodput_kbps | 6 | -0.4593 | [-1.913, +0.5352] | 1/4/1 | nan |
| acwra_no_history | mean_ber | 6 | -0.00024 | [-0.0005265, +0] | 0/4/2 | nan |
| acwra_no_history | mean_regret_kbps | 6 | +0.4593 | [-0.5352, +1.913] | 1/4/1 | nan |
| acwra_no_history | switches | 6 | -0.01667 | [-0.05, +0] | 0/5/1 | nan |
| acwra_no_confidence | mean_goodput_kbps | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | mean_ber | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | mean_regret_kbps | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_no_confidence | switches | 6 | +0 | [+0, +0] | 0/6/0 | nan |
| acwra_all_candidates | mean_goodput_kbps | 6 | -3.865 | [-7.647, -1.633] | 0/0/6 | 0.0312 |
| acwra_all_candidates | mean_ber | 6 | +5.538e-05 | [-0.0001881, +0.0004281] | 1/1/4 | 0.625 |
| acwra_all_candidates | mean_regret_kbps | 6 | +3.865 | [+1.633, +7.647] | 6/0/0 | 0.0312 |
| acwra_all_candidates | switches | 6 | +0.15 | [+0, +0.35] | 2/4/0 | nan |
| fixed_BPSK | mean_goodput_kbps | 6 | +42.87 | [+29.82, +62.15] | 6/0/0 | 0.0312 |
| fixed_BPSK | mean_ber | 6 | +0.001064 | [+0.0003453, +0.001783] | 5/1/0 | 0.0625 |
| fixed_BPSK | mean_regret_kbps | 6 | -42.87 | [-62.15, -29.82] | 0/0/6 | 0.0312 |
| fixed_BPSK | switches | 6 | +0.9833 | [+0.65, +1.3] | 6/0/0 | 0.0312 |
| fixed_QPSK | mean_goodput_kbps | 6 | -10.6 | [-18.1, -3.688] | 0/0/6 | 0.0312 |
| fixed_QPSK | mean_ber | 6 | -0.02623 | [-0.03935, -0.01193] | 0/1/5 | 0.0625 |
| fixed_QPSK | mean_regret_kbps | 6 | +10.6 | [+3.688, +18.1] | 6/0/0 | 0.0312 |
| fixed_QPSK | switches | 6 | +0.9833 | [+0.65, +1.3] | 6/0/0 | 0.0312 |
| fixed_OFDM-QPSK | mean_goodput_kbps | 6 | -10.6 | [-18.1, -3.688] | 0/0/6 | 0.0312 |
| fixed_OFDM-QPSK | mean_ber | 6 | -0.02623 | [-0.03935, -0.01193] | 0/1/5 | 0.0625 |
| fixed_OFDM-QPSK | mean_regret_kbps | 6 | +10.6 | [+3.688, +18.1] | 6/0/0 | 0.0312 |
| fixed_OFDM-QPSK | switches | 6 | +0.9833 | [+0.65, +1.3] | 6/0/0 | 0.0312 |
| snr_threshold | mean_goodput_kbps | 6 | -10.6 | [-18.11, -3.695] | 0/0/6 | 0.0312 |
| snr_threshold | mean_ber | 6 | -0.007459 | [-0.01421, -0.001742] | 0/1/5 | 0.0625 |
| snr_threshold | mean_regret_kbps | 6 | +10.6 | [+3.695, +18.11] | 6/0/0 | 0.0312 |
| snr_threshold | switches | 6 | +0.3167 | [+0, +0.85] | 2/4/0 | nan |
| sinr_threshold | mean_goodput_kbps | 6 | -10.49 | [-17.58, -3.763] | 0/0/6 | 0.0312 |
| sinr_threshold | mean_ber | 6 | -0.0007905 | [-0.001702, -0.0001251] | 0/1/5 | 0.0625 |
| sinr_threshold | mean_regret_kbps | 6 | +10.49 | [+3.763, +17.58] | 6/0/0 | 0.0312 |
| sinr_threshold | switches | 6 | +0.15 | [+0, +0.35] | 2/4/0 | nan |
| oracle | mean_goodput_kbps | 6 | -12.31 | [-22.65, -3.771] | 0/0/6 | 0.0312 |
| oracle | mean_ber | 6 | +0.001003 | [+0.0002433, +0.001765] | 4/1/1 | 0.125 |
| oracle | mean_regret_kbps | 6 | +12.31 | [+3.771, +22.65] | 6/0/0 | 0.0312 |
| oracle | switches | 6 | -1 | [-3.15, +0.15] | 1/4/1 | nan |

### Suite `original` - policy means over conditions

| policy | goodput kb/s | BER | regret kb/s | switches | oracle agree | decide ms |
|---|---|---|---|---|---|---|
| acwra | 103.2 | 0.0544 | 12.3 | 0.98 | 0.84 | 0.16 |
| acwra_no_prediction | 103.7 | 0.0547 | 11.8 | 1.00 | 0.85 | 0.18 |
| acwra_no_history | 103.7 | 0.0547 | 11.8 | 1.00 | 0.85 | 0.26 |
| acwra_no_confidence | 103.2 | 0.0544 | 12.3 | 0.98 | 0.84 | 0.15 |
| acwra_all_candidates | 107.1 | 0.0544 | 8.4 | 0.83 | 0.88 | 0.16 |
| fixed_BPSK | 60.4 | 0.0534 | 55.2 | 0.00 | 0.42 | 0.00 |
| fixed_QPSK | 113.8 | 0.0807 | 1.7 | 0.00 | 0.86 | 0.00 |
| fixed_OFDM-QPSK | 113.8 | 0.0807 | 1.7 | 0.00 | 0.86 | 0.00 |
| snr_threshold | 113.8 | 0.0619 | 1.7 | 0.67 | 0.86 | 0.00 |
| sinr_threshold | 113.7 | 0.0552 | 1.8 | 0.83 | 0.96 | 0.00 |
| oracle | 115.6 | 0.0534 | 0.0 | 1.98 | 1.00 | 0.00 |

## Suite `sweep` - paired comparisons (ACWRA - baseline, condition-level)

| baseline | metric | n cond | mean diff | 95% CI | W/T/L | Wilcoxon p |
|---|---|---|---|---|---|---|
| acwra_no_prediction | mean_goodput_kbps | 30 | +0.5968 | [-0.5786, +1.803] | 12/16/2 | 0.0676 |
| acwra_no_prediction | mean_ber | 30 | -0.01562 | [-0.02397, -0.008163] | 0/16/14 | 0.000122 |
| acwra_no_prediction | mean_regret_kbps | 30 | -0.5968 | [-1.803, +0.5786] | 2/16/12 | 0.0676 |
| acwra_no_prediction | switches | 30 | +0.2333 | [-0.006667, +0.48] | 12/14/4 | 0.0732 |
| acwra_no_history | mean_goodput_kbps | 30 | +0.5968 | [-0.5786, +1.803] | 12/16/2 | 0.0676 |
| acwra_no_history | mean_ber | 30 | -0.01562 | [-0.02397, -0.008163] | 0/16/14 | 0.000122 |
| acwra_no_history | mean_regret_kbps | 30 | -0.5968 | [-1.803, +0.5786] | 2/16/12 | 0.0676 |
| acwra_no_history | switches | 30 | +0.2333 | [-0.006667, +0.48] | 12/14/4 | 0.0732 |
| acwra_no_confidence | mean_goodput_kbps | 30 | +0 | [+0, +0] | 0/30/0 | nan |
| acwra_no_confidence | mean_ber | 30 | +0 | [+0, +0] | 0/30/0 | nan |
| acwra_no_confidence | mean_regret_kbps | 30 | +0 | [+0, +0] | 0/30/0 | nan |
| acwra_no_confidence | switches | 30 | +0 | [+0, +0] | 0/30/0 | nan |
| acwra_all_candidates | mean_goodput_kbps | 30 | +3.666 | [-6.654, +14.36] | 8/3/19 | 0.611 |
| acwra_all_candidates | mean_ber | 30 | +0.01124 | [+0.007906, +0.01496] | 29/1/0 | 3.73e-09 |
| acwra_all_candidates | mean_regret_kbps | 30 | -3.666 | [-14.36, +6.654] | 19/3/8 | 0.611 |
| acwra_all_candidates | switches | 30 | +0.1333 | [-0.1933, +0.4733] | 14/5/11 | 0.402 |
| fixed_BPSK | mean_goodput_kbps | 30 | +7.767 | [-4.121, +20.16] | 10/3/17 | 0.897 |
| fixed_BPSK | mean_ber | 30 | +0.01263 | [+0.008992, +0.01661] | 29/1/0 | 3.73e-09 |
| fixed_BPSK | mean_regret_kbps | 30 | -7.767 | [-20.16, +4.121] | 17/3/10 | 0.897 |
| fixed_BPSK | switches | 30 | +1.1 | [+0.7667, +1.447] | 23/7/0 | 2.6e-05 |
| fixed_QPSK | mean_goodput_kbps | 30 | -4.489 | [-10.75, +0.4594] | 11/10/9 | 0.409 |
| fixed_QPSK | mean_ber | 30 | -0.02145 | [-0.03023, -0.01308] | 0/8/22 | 4.77e-07 |
| fixed_QPSK | mean_regret_kbps | 30 | +4.489 | [-0.4594, +10.75] | 9/10/11 | 0.409 |
| fixed_QPSK | switches | 30 | +1.1 | [+0.7667, +1.447] | 23/7/0 | 2.6e-05 |
| fixed_OFDM-QPSK | mean_goodput_kbps | 30 | -4.489 | [-10.75, +0.4594] | 11/10/9 | 0.409 |
| fixed_OFDM-QPSK | mean_ber | 30 | -0.02145 | [-0.03023, -0.01308] | 0/8/22 | 4.77e-07 |
| fixed_OFDM-QPSK | mean_regret_kbps | 30 | +4.489 | [-0.4594, +10.75] | 9/10/11 | 0.409 |
| fixed_OFDM-QPSK | switches | 30 | +1.1 | [+0.7667, +1.447] | 23/7/0 | 2.6e-05 |
| snr_threshold | mean_goodput_kbps | 30 | -9.292 | [-15.99, -3.606] | 3/7/20 | 0.00112 |
| snr_threshold | mean_ber | 30 | +0.003934 | [-0.001343, +0.008929] | 14/5/11 | 0.101 |
| snr_threshold | mean_regret_kbps | 30 | +9.292 | [+3.606, +15.99] | 20/7/3 | 0.00112 |
| snr_threshold | switches | 30 | +0.6333 | [+0.2867, +0.9933] | 19/8/3 | 0.00199 |
| sinr_threshold | mean_goodput_kbps | 30 | -12.21 | [-19.66, -5.548] | 1/3/26 | 7.99e-06 |
| sinr_threshold | mean_ber | 30 | +0.01067 | [+0.007154, +0.01457] | 22/1/7 | 7.58e-06 |
| sinr_threshold | mean_regret_kbps | 30 | +12.21 | [+5.548, +19.66] | 26/3/1 | 7.99e-06 |
| sinr_threshold | switches | 30 | +0.3667 | [+0.02667, +0.6933] | 19/4/7 | 0.0308 |
| oracle | mean_goodput_kbps | 30 | -16.94 | [-24.09, -10.67] | 0/4/26 | 2.98e-08 |
| oracle | mean_ber | 30 | +0.0125 | [+0.008828, +0.01653] | 25/2/3 | 1.04e-07 |
| oracle | mean_regret_kbps | 30 | +16.94 | [+10.67, +24.09] | 26/4/0 | 2.98e-08 |
| oracle | switches | 30 | -0.4 | [-1.407, +0.44] | 18/7/5 | 0.315 |

### Suite `sweep` - policy means over conditions

| policy | goodput kb/s | BER | regret kb/s | switches | oracle agree | decide ms |
|---|---|---|---|---|---|---|
| acwra | 53.7 | 0.0450 | 16.9 | 1.10 | 0.63 | 0.13 |
| acwra_no_prediction | 53.1 | 0.0607 | 17.5 | 0.87 | 0.53 | 0.13 |
| acwra_no_history | 53.1 | 0.0607 | 17.5 | 0.87 | 0.53 | 0.13 |
| acwra_no_confidence | 53.7 | 0.0450 | 16.9 | 1.10 | 0.63 | 0.13 |
| acwra_all_candidates | 50.0 | 0.0338 | 20.6 | 0.97 | 0.73 | 0.15 |
| fixed_BPSK | 45.9 | 0.0324 | 24.7 | 0.00 | 0.70 | 0.00 |
| fixed_QPSK | 58.2 | 0.0665 | 12.5 | 0.00 | 0.55 | 0.00 |
| fixed_OFDM-QPSK | 58.2 | 0.0665 | 12.5 | 0.00 | 0.55 | 0.00 |
| snr_threshold | 63.0 | 0.0411 | 7.6 | 0.47 | 0.77 | 0.00 |
| sinr_threshold | 65.9 | 0.0344 | 4.7 | 0.73 | 0.89 | 0.00 |
| oracle | 70.6 | 0.0325 | 0.0 | 1.50 | 1.00 | 0.00 |

