# GNU Radio BER validation

Data: GNU Radio software simulation (no hardware).

Judged points: 18/18 PASS.

| mod | Es/N0 dB | bits | errors | BER | 99.9 % CI | theory | result |
|---|---|---|---|---|---|---|---|
| BPSK | -2.0 | 196608 | 25435 | 1.294e-01 | [1.27e-01, 1.32e-01] | 1.306e-01 | PASS |
| BPSK | 0.0 | 196608 | 15278 | 7.771e-02 | [7.57e-02, 7.97e-02] | 7.865e-02 | PASS |
| BPSK | 2.0 | 196608 | 7286 | 3.706e-02 | [3.57e-02, 3.85e-02] | 3.751e-02 | PASS |
| BPSK | 4.0 | 196608 | 2434 | 1.238e-02 | [1.16e-02, 1.32e-02] | 1.250e-02 | PASS |
| BPSK | 6.0 | 196608 | 461 | 2.345e-03 | [2.01e-03, 2.73e-03] | 2.388e-03 | PASS |
| BPSK | 8.0 | 196608 | 39 | 1.984e-04 | [1.18e-04, 3.34e-04] | 1.909e-04 | PASS |
| QPSK | 0.0 | 393216 | 62253 | 1.583e-01 | [1.56e-01, 1.60e-01] | 1.587e-01 | PASS |
| QPSK | 2.0 | 393216 | 40954 | 1.042e-01 | [1.03e-01, 1.06e-01] | 1.040e-01 | PASS |
| QPSK | 4.0 | 393216 | 22321 | 5.677e-02 | [5.56e-02, 5.80e-02] | 5.650e-02 | PASS |
| QPSK | 6.0 | 393216 | 9207 | 2.341e-02 | [2.26e-02, 2.42e-02] | 2.301e-02 | PASS |
| QPSK | 8.0 | 393216 | 2313 | 5.882e-03 | [5.49e-03, 6.30e-03] | 6.004e-03 | PASS |
| QPSK | 10.0 | 393216 | 342 | 8.698e-04 | [7.28e-04, 1.04e-03] | 7.827e-04 | PASS |
| OFDM-QPSK | 0.0 | 393216 | 62144 | 1.580e-01 | [1.56e-01, 1.60e-01] | 1.587e-01 | PASS |
| OFDM-QPSK | 2.0 | 393216 | 40751 | 1.036e-01 | [1.02e-01, 1.05e-01] | 1.040e-01 | PASS |
| OFDM-QPSK | 4.0 | 393216 | 22152 | 5.634e-02 | [5.51e-02, 5.76e-02] | 5.650e-02 | PASS |
| OFDM-QPSK | 6.0 | 393216 | 8971 | 2.281e-02 | [2.20e-02, 2.36e-02] | 2.301e-02 | PASS |
| OFDM-QPSK | 8.0 | 393216 | 2296 | 5.839e-03 | [5.45e-03, 6.25e-03] | 6.004e-03 | PASS |
| OFDM-QPSK | 10.0 | 393216 | 311 | 7.909e-04 | [6.57e-04, 9.53e-04] | 7.827e-04 | PASS |

```json
{
  "same_seed_identical": true,
  "different_seed_noise_corr": 0.009036630212578993,
  "different_seed_independent": true,
  "jammer_measured_power": 0.10025513937195529,
  "rayleigh_time_varying_gain_capture_ok": true,
  "rayleigh_time_varying_gain_std": 0.45307580059903196,
  "rayleigh_time_varying_ber_vs_conditional_theory": [
    0.0035400390625,
    0.002836777196500803
  ],
  "rician_time_varying_gain_capture_ok": true,
  "rician_time_varying_gain_std": 0.4091513943853951,
  "rician_time_varying_ber_vs_conditional_theory": [
    0.005126953125,
    0.005374867366871356
  ],
  "ber_points_judged": 18,
  "ber_points_pass": 18
}
```
