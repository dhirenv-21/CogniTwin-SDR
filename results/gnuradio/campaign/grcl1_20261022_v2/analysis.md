# GR-CL-1 condition-level analysis (generated from runs.csv / episodes_steps.csv)

runs 810, conditions 27, flowgraph episodes 4860, provenance ['gnuradio_export']

Differences are ACWRA - baseline per condition (seeds averaged), 95 % bootstrap CI over conditions, Wilcoxon signed-rank. 'A>B/tie/A<B' counts conditions where ACWRA's value is higher / equal / lower (for BER, higher = worse).


## all (27 conditions)

| baseline | metric | mean diff | 95 % CI | A>B/tie/A<B | p |
|---|---|---|---|---|---|
| no_adaptation | goodput | +0.625 kb/s | [-1.968, +2.971] | 10/12/5 | 0.32 |
| no_adaptation | ber | -0.009834 | [-0.01534, -0.00477] | 2/11/14 | 0.00043 |
| fixed_BPSK | goodput | +14.44 kb/s | [-3.187, +32.24] | 13/3/11 | 0.15 |
| fixed_BPSK | ber | +0.01584 | [+0.0122, +0.0195] | 26/1/0 | 3e-08 |
| fixed_QPSK | goodput | +0.625 kb/s | [-1.968, +2.971] | 10/12/5 | 0.32 |
| fixed_QPSK | ber | -0.009834 | [-0.01534, -0.00477] | 2/11/14 | 0.00043 |
| fixed_OFDM-QPSK | goodput | +14.41 kb/s | [+9.735, +19.33] | 24/2/1 | 1.6e-05 |
| fixed_OFDM-QPSK | ber | -0.009927 | [-0.01548, -0.004774] | 6/2/19 | 0.0031 |
| sinr_threshold | goodput | -7.168 kb/s | [-15.36, +0.08546] | 6/9/12 | 0.13 |
| sinr_threshold | ber | +0.006073 | [+0.003561, +0.008875] | 17/8/2 | 5.3e-05 |

## static (24 conditions)

| baseline | metric | mean diff | 95 % CI | A>B/tie/A<B | p |
|---|---|---|---|---|---|
| no_adaptation | goodput | +0.9288 kb/s | [-1.832, +3.585] | 10/10/4 | 0.22 |
| no_adaptation | ber | -0.01105 | [-0.0172, -0.005549] | 2/9/13 | 0.00061 |
| fixed_BPSK | goodput | +9.983 kb/s | [-8.646, +28.95] | 10/3/11 | 0.41 |
| fixed_BPSK | ber | +0.01636 | [+0.0123, +0.02038] | 23/1/0 | 2.4e-07 |
| fixed_QPSK | goodput | +0.9288 kb/s | [-1.832, +3.585] | 10/10/4 | 0.22 |
| fixed_QPSK | ber | -0.01105 | [-0.0172, -0.005549] | 2/9/13 | 0.00061 |
| fixed_OFDM-QPSK | goodput | +13.42 kb/s | [+8.505, +18.79] | 21/2/1 | 5.3e-05 |
| fixed_OFDM-QPSK | ber | -0.01116 | [-0.01741, -0.00554] | 6/1/17 | 0.0049 |
| sinr_threshold | goodput | -7.873 kb/s | [-17.11, +0.4603] | 5/9/10 | 0.13 |
| sinr_threshold | ber | +0.006182 | [+0.003427, +0.009206] | 15/8/1 | 0.00015 |

## static_awgn (12 conditions)

| baseline | metric | mean diff | 95 % CI | A>B/tie/A<B | p |
|---|---|---|---|---|---|
| no_adaptation | goodput | +0.2604 kb/s | [+0, +0.6944] | 2/10/0 | nan |
| no_adaptation | ber | -0.009458 | [-0.0197, +0] | 0/9/3 | nan |
| fixed_BPSK | goodput | +6.337 kb/s | [-26.42, +41.23] | 4/1/7 | 0.97 |
| fixed_BPSK | ber | +0.01201 | [+0.00622, +0.01869] | 11/1/0 | 0.00098 |
| fixed_QPSK | goodput | +0.2604 kb/s | [+0, +0.6944] | 2/10/0 | nan |
| fixed_QPSK | ber | -0.009458 | [-0.0197, +0] | 0/9/3 | nan |
| fixed_OFDM-QPSK | goodput | +13.43 kb/s | [+4.455, +23.17] | 9/2/1 | 0.0059 |
| fixed_OFDM-QPSK | ber | -0.009333 | [-0.01961, +1.731e-05] | 4/1/7 | 0.41 |
| sinr_threshold | goodput | -15.1 kb/s | [-31.2, +0.1215] | 1/6/5 | 0.094 |
| sinr_threshold | ber | +0.005891 | [+0.001703, +0.01102] | 6/6/0 | 0.031 |

## static_rayleigh (12 conditions)

| baseline | metric | mean diff | 95 % CI | A>B/tie/A<B | p |
|---|---|---|---|---|---|
| no_adaptation | goodput | +1.597 kb/s | [-4.149, +6.667] | 8/0/4 | 0.34 |
| no_adaptation | ber | -0.01264 | [-0.01963, -0.005811] | 2/0/10 | 0.0049 |
| fixed_BPSK | goodput | +13.63 kb/s | [+0.7114, +29.9] | 6/2/4 | 0.084 |
| fixed_BPSK | ber | +0.0207 | [+0.01665, +0.02416] | 12/0/0 | 0.00049 |
| fixed_QPSK | goodput | +1.597 kb/s | [-4.149, +6.667] | 8/0/4 | 0.34 |
| fixed_QPSK | ber | -0.01264 | [-0.01963, -0.005811] | 2/0/10 | 0.0049 |
| fixed_OFDM-QPSK | goodput | +13.41 kb/s | [+9.368, +17.87] | 12/0/0 | 0.00049 |
| fixed_OFDM-QPSK | ber | -0.01298 | [-0.02029, -0.005873] | 2/0/10 | 0.0068 |
| sinr_threshold | goodput | -0.6424 kb/s | [-5.278, +3.299] | 4/3/5 | 1 |
| sinr_threshold | ber | +0.006473 | [+0.003302, +0.009764] | 9/2/1 | 0.0059 |

## dynamic (3 conditions)

| baseline | metric | mean diff | 95 % CI | A>B/tie/A<B | p |
|---|---|---|---|---|---|
| no_adaptation | goodput | -1.806 kb/s | [-5.417, +0] | 0/2/1 | nan |
| no_adaptation | ber | -0.0001091 | [-0.0003274, +0] | 0/2/1 | nan |
| fixed_BPSK | goodput | +50.14 kb/s | [+33.96, +61.46] | 3/0/0 | nan |
| fixed_BPSK | ber | +0.0117 | [+0.01061, +0.01266] | 3/0/0 | nan |
| fixed_QPSK | goodput | -1.806 kb/s | [-5.417, +0] | 0/2/1 | nan |
| fixed_QPSK | ber | -0.0001091 | [-0.0003274, +0] | 0/2/1 | nan |
| fixed_OFDM-QPSK | goodput | +22.35 kb/s | [+20, +26.46] | 3/0/0 | nan |
| fixed_OFDM-QPSK | ber | -0.0001037 | [-0.0001565, +3.469e-19] | 0/1/2 | nan |
| sinr_threshold | goodput | -1.528 kb/s | [-12.92, +13.75] | 1/0/2 | nan |
| sinr_threshold | ber | +0.005201 | [-0.0003274, +0.01089] | 2/0/1 | nan |

## Policy means over all runs

| policy | goodput kb/s | BER | PER | switches/run |
|---|---|---|---|---|
| sinr_threshold | 77.1 | 0.0361 | 0.495 | 0.78 |
| acwra | 70.0 | 0.0422 | 0.610 | 0.47 |
| no_adaptation | 69.3 | 0.0520 | 0.653 | 0.00 |
| fixed_QPSK | 69.3 | 0.0520 | 0.653 | 0.00 |
| fixed_OFDM-QPSK | 55.5 | 0.0521 | 0.653 | 0.00 |
| fixed_BPSK | 55.5 | 0.0264 | 0.445 | 0.00 |

## ACWRA decisions

selected strategies: {'BPSK': 132, 'Keep Current': 678}

modulations applied: {'QPSK': 549, 'BPSK': 261}

risk score: min 0.055, median 0.249, max 0.764

episodes where ACWRA chose a different modulation, by condition: {'static_awgn_snr4_J0': 5, 'static_awgn_snr4_J0.05': 5, 'static_awgn_snr4_J0.2': 5, 'static_rayleigh_snr4_J0': 5, 'static_rayleigh_snr4_J0.05': 5, 'static_rayleigh_snr4_J0.2': 5, 'static_rayleigh_snr8_J0': 4, 'static_rayleigh_snr8_J0.05': 4, 'static_rayleigh_snr8_J0.2': 5, 'static_rayleigh_snr12_J0': 3, 'static_rayleigh_snr12_J0.05': 4, 'static_rayleigh_snr12_J0.2': 5, 'static_rayleigh_snr16_J0': 1, 'static_rayleigh_snr16_J0.05': 3, 'static_rayleigh_snr16_J0.2': 4, 'step_fade': 3, 'ramp_snr': 5}

(applied, detected) modulation pairs in ACWRA episodes: {('QPSK', 'QPSK'): 526, ('BPSK', 'BPSK'): 246, ('QPSK', 'OFDM-QPSK'): 20, ('BPSK', 'OFDM-QPSK'): 12, ('BPSK', 'UNKNOWN'): 3, ('QPSK', 'UNKNOWN'): 3}
