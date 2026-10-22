# GNU Radio closed-loop campaign

Data: GNU Radio software simulation; episode-based sequential reconfiguration (decision from episode e applied to episode e+1).

Conditions 2, seeds 1, episodes 6, flowgraph runs 72.

| policy | goodput kb/s | BER | PER | SE b/s/Hz | switches |
|---|---|---|---|---|---|
| sinr_threshold | 92.7 | 0.0069 | 0.331 | 0.687 | 1.50 |
| fixed_BPSK | 71.9 | 0.0019 | 0.281 | 0.532 | 0.00 |
| acwra | 71.4 | 0.0144 | 0.643 | 0.529 | 0.00 |
| no_adaptation | 71.4 | 0.0144 | 0.643 | 0.529 | 0.00 |
| fixed_QPSK | 71.4 | 0.0144 | 0.643 | 0.529 | 0.00 |
| fixed_OFDM-QPSK | 54.2 | 0.0140 | 0.661 | 0.542 | 0.00 |

## ACWRA - baseline, condition-level paired

| baseline | metric | mean diff | 95 % CI | W/T/L | p |
|---|---|---|---|---|---|
| no_adaptation | goodput_bps | 0 | [0, 0] | 0/2/0 | nan |
| no_adaptation | ber | 0 | [0, 0] | 0/2/0 | nan |
| no_adaptation | spectral_efficiency | 0 | [0, 0] | 0/2/0 | nan |
| fixed_BPSK | goodput_bps | -520.8 | [-6.458e+04, 6.354e+04] | 1/0/1 | nan |
| fixed_BPSK | ber | 0.01251 | [0.01184, 0.01318] | 2/0/0 | nan |
| fixed_BPSK | spectral_efficiency | -0.003858 | [-0.4784, 0.4707] | 1/0/1 | nan |
| fixed_QPSK | goodput_bps | 0 | [0, 0] | 0/2/0 | nan |
| fixed_QPSK | ber | 0 | [0, 0] | 0/2/0 | nan |
| fixed_QPSK | spectral_efficiency | 0 | [0, 0] | 0/2/0 | nan |
| fixed_OFDM-QPSK | goodput_bps | 1.719e+04 | [7708, 2.667e+04] | 2/0/0 | nan |
| fixed_OFDM-QPSK | ber | 0.0004171 | [0.0003459, 0.0004883] | 2/0/0 | nan |
| fixed_OFDM-QPSK | spectral_efficiency | -0.01312 | [-0.07901, 0.05278] | 1/0/1 | nan |
| sinr_threshold | goodput_bps | -2.135e+04 | [-5.729e+04, 1.458e+04] | 1/0/1 | nan |
| sinr_threshold | ber | 0.007493 | [0.005111, 0.009876] | 2/0/0 | nan |
| sinr_threshold | spectral_efficiency | -0.1582 | [-0.4244, 0.108] | 1/0/1 | nan |

Provenance of every episode (validator): ['gnuradio_export']
