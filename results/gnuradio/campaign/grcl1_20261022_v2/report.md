# GNU Radio closed-loop campaign

Data: GNU Radio software simulation; episode-based sequential reconfiguration (decision from episode e applied to episode e+1).

Conditions 27, seeds 5, episodes 6, flowgraph runs 4860.

| policy | goodput kb/s | BER | PER | SE b/s/Hz | switches |
|---|---|---|---|---|---|
| sinr_threshold | 77.1 | 0.0361 | 0.495 | 0.571 | 0.78 |
| acwra | 70.0 | 0.0422 | 0.610 | 0.518 | 0.47 |
| no_adaptation | 69.3 | 0.0520 | 0.653 | 0.514 | 0.00 |
| fixed_QPSK | 69.3 | 0.0520 | 0.653 | 0.514 | 0.00 |
| fixed_OFDM-QPSK | 55.5 | 0.0521 | 0.653 | 0.555 | 0.00 |
| fixed_BPSK | 55.5 | 0.0264 | 0.445 | 0.411 | 0.00 |

## ACWRA - baseline, condition-level paired

| baseline | metric | mean diff | 95 % CI | W/T/L | p |
|---|---|---|---|---|---|
| no_adaptation | goodput_bps | 625 | [-2014, 3071] | 10/12/5 | 0.32 |
| no_adaptation | ber | -0.009834 | [-0.01562, -0.004815] | 2/11/14 | 0.00043 |
| no_adaptation | spectral_efficiency | 0.00463 | [-0.01492, 0.02275] | 10/12/5 | 0.32 |
| fixed_BPSK | goodput_bps | 1.444e+04 | [-2739, 3.185e+04] | 13/3/11 | 0.15 |
| fixed_BPSK | ber | 0.01584 | [0.01219, 0.0195] | 26/1/0 | 3e-08 |
| fixed_BPSK | spectral_efficiency | 0.107 | [-0.02029, 0.2359] | 13/3/11 | 0.15 |
| fixed_QPSK | goodput_bps | 625 | [-2014, 3071] | 10/12/5 | 0.32 |
| fixed_QPSK | ber | -0.009834 | [-0.01562, -0.004815] | 2/11/14 | 0.00043 |
| fixed_QPSK | spectral_efficiency | 0.00463 | [-0.01492, 0.02275] | 10/12/5 | 0.32 |
| fixed_OFDM-QPSK | goodput_bps | 1.441e+04 | [9835, 1.929e+04] | 24/2/1 | 1.6e-05 |
| fixed_OFDM-QPSK | ber | -0.009927 | [-0.01579, -0.004822] | 6/2/19 | 0.0031 |
| fixed_OFDM-QPSK | spectral_efficiency | -0.03726 | [-0.06599, -0.009419] | 9/2/16 | 0.054 |
| sinr_threshold | goodput_bps | -7168 | [-1.538e+04, 262.3] | 6/9/12 | 0.13 |
| sinr_threshold | ber | 0.006073 | [0.003541, 0.008892] | 17/8/2 | 5.3e-05 |
| sinr_threshold | spectral_efficiency | -0.0531 | [-0.1139, 0.001943] | 6/9/12 | 0.13 |

Provenance of every episode (validator): ['gnuradio_export']
