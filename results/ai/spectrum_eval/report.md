# Spectrum Agent evaluation (synthetic, as served)

5760 windows (40 per class x SINR x impairment), seeds 1000001-1006480 (disjoint from training). Impairments: awgn, block_fade (one complex gain per window, SINR referenced to received power), jammer (half the impairment power is a Gaussian jammer).

Overall accuracy 0.944; UNKNOWN rate 0.026; ECE of confidence on non-UNKNOWN predictions 0.017.

| class | precision | recall | F1 | UNKNOWN rate |
|---|---|---|---|---|
| AM-DSB-SC | 0.986 | 0.960 | 0.973 | 0.028 |
| AM-DSB-TC | 1.000 | 1.000 | 1.000 | 0.000 |
| FM | 0.987 | 0.946 | 0.966 | 0.040 |
| ASK | 0.975 | 0.975 | 0.975 | 0.014 |
| FSK | 0.988 | 0.915 | 0.950 | 0.060 |
| BPSK | 0.999 | 0.999 | 0.999 | 0.000 |
| QPSK | 0.985 | 0.811 | 0.890 | 0.025 |
| OFDM-QPSK | 0.852 | 0.949 | 0.898 | 0.037 |

Accuracy by SINR (rows) and impairment (columns):

| SINR dB | awgn | block_fade | jammer |
|---|---|---|---|
| -5 | 0.719 | 0.759 | 0.734 |
| 0 | 0.956 | 0.956 | 0.966 |
| 5 | 0.994 | 0.988 | 0.984 |
| 10 | 0.984 | 0.991 | 0.997 |
| 15 | 0.994 | 0.997 | 0.994 |
| 20 | 0.991 | 0.997 | 0.997 |

Blind SNR estimate vs true SINR (resolved windows only):

| type | impairment | SINR dB | resolved | bias dB | MAE dB |
|---|---|---|---|---|---|
| BPSK | awgn | -5 | 0.00 | +nan | nan |
| BPSK | block_fade | -5 | 0.00 | +nan | nan |
| BPSK | jammer | -5 | 0.00 | +nan | nan |
| BPSK | awgn | 0 | 0.38 | +1.07 | 1.07 |
| BPSK | block_fade | 0 | 0.35 | +0.76 | 0.76 |
| BPSK | jammer | 0 | 0.33 | +0.85 | 0.85 |
| BPSK | awgn | 5 | 1.00 | +0.10 | 0.39 |
| BPSK | block_fade | 5 | 1.00 | +0.07 | 0.42 |
| BPSK | jammer | 5 | 1.00 | -0.05 | 0.36 |
| BPSK | awgn | 10 | 1.00 | +0.01 | 0.31 |
| BPSK | block_fade | 10 | 1.00 | -0.04 | 0.27 |
| BPSK | jammer | 10 | 1.00 | +0.06 | 0.22 |
| BPSK | awgn | 15 | 1.00 | -0.02 | 0.24 |
| BPSK | block_fade | 15 | 1.00 | -0.01 | 0.24 |
| BPSK | jammer | 15 | 1.00 | +0.01 | 0.17 |
| BPSK | awgn | 20 | 1.00 | -0.00 | 0.22 |
| BPSK | block_fade | 20 | 1.00 | -0.01 | 0.21 |
| BPSK | jammer | 20 | 1.00 | +0.03 | 0.25 |
| OFDM-QPSK | awgn | -5 | 0.00 | +nan | nan |
| OFDM-QPSK | block_fade | -5 | 0.00 | +nan | nan |
| OFDM-QPSK | jammer | -5 | 0.00 | +nan | nan |
| OFDM-QPSK | awgn | 0 | 0.72 | -0.05 | 0.71 |
| OFDM-QPSK | block_fade | 0 | 0.78 | +0.32 | 0.73 |
| OFDM-QPSK | jammer | 0 | 0.85 | +0.31 | 0.68 |
| OFDM-QPSK | awgn | 5 | 1.00 | -0.14 | 0.48 |
| OFDM-QPSK | block_fade | 5 | 1.00 | +0.11 | 0.52 |
| OFDM-QPSK | jammer | 5 | 1.00 | +0.05 | 0.45 |
| OFDM-QPSK | awgn | 10 | 1.00 | -0.11 | 0.41 |
| OFDM-QPSK | block_fade | 10 | 1.00 | +0.05 | 0.32 |
| OFDM-QPSK | jammer | 10 | 1.00 | -0.30 | 0.68 |
| OFDM-QPSK | awgn | 15 | 1.00 | -0.75 | 1.10 |
| OFDM-QPSK | block_fade | 15 | 1.00 | -0.49 | 0.87 |
| OFDM-QPSK | jammer | 15 | 1.00 | -0.31 | 0.65 |
| OFDM-QPSK | awgn | 20 | 1.00 | -0.72 | 1.24 |
| OFDM-QPSK | block_fade | 20 | 1.00 | -0.37 | 0.99 |
| OFDM-QPSK | jammer | 20 | 1.00 | -0.54 | 0.86 |
| QPSK | awgn | -5 | 0.00 | +nan | nan |
| QPSK | block_fade | -5 | 0.00 | +nan | nan |
| QPSK | jammer | -5 | 0.00 | +nan | nan |
| QPSK | awgn | 0 | 0.40 | +0.90 | 0.90 |
| QPSK | block_fade | 0 | 0.33 | +0.90 | 0.90 |
| QPSK | jammer | 0 | 0.38 | +0.89 | 0.89 |
| QPSK | awgn | 5 | 1.00 | -0.01 | 0.36 |
| QPSK | block_fade | 5 | 1.00 | -0.02 | 0.32 |
| QPSK | jammer | 5 | 1.00 | +0.04 | 0.35 |
| QPSK | awgn | 10 | 1.00 | +0.01 | 0.25 |
| QPSK | block_fade | 10 | 1.00 | +0.01 | 0.28 |
| QPSK | jammer | 10 | 1.00 | -0.03 | 0.27 |
| QPSK | awgn | 15 | 1.00 | +0.02 | 0.25 |
| QPSK | block_fade | 15 | 1.00 | +0.12 | 0.26 |
| QPSK | jammer | 15 | 1.00 | -0.00 | 0.25 |
| QPSK | awgn | 20 | 1.00 | +0.02 | 0.20 |
| QPSK | block_fade | 20 | 1.00 | -0.01 | 0.24 |
| QPSK | jammer | 20 | 1.00 | -0.06 | 0.21 |

False SNR_DROP rate of the Spectrum Agent on stationary captures (39 window pairs each):

- BPSK@-5dB: 0.000
- BPSK@0dB: 0.000
- BPSK@5dB: 0.000
- BPSK@10dB: 0.000
- BPSK@15dB: 0.000
- BPSK@20dB: 0.000
- QPSK@-5dB: 0.000
- QPSK@0dB: 0.000
- QPSK@5dB: 0.000
- QPSK@10dB: 0.000
- QPSK@15dB: 0.000
- QPSK@20dB: 0.000
- OFDM-QPSK@-5dB: 0.000
- OFDM-QPSK@0dB: 0.000
- OFDM-QPSK@5dB: 0.000
- OFDM-QPSK@10dB: 0.000
- OFDM-QPSK@15dB: 0.077
- OFDM-QPSK@20dB: 0.077
