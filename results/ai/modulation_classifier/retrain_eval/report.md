# Modulation classifier retraining evaluation

Synthetic Python data only (no Simulink). Accuracy counts below-threshold (`UNKNOWN`) predictions as wrong. All inputs are normalised to unit power, as analyze_iq() serves them. `stream+impaired` adds a random carrier phase and, on half the windows, a Gaussian jammer (power 0.05-1), so its SNR axis is the noise-only SNR; the effective SINR is lower.

Train: mixed representation, 11200 windows, seed 2026. Test: fresh seed 777, 2800 windows per representation.

| model | test data | overall | -5 dB | 0 dB | 5 dB | 10 dB | 15 dB | 20 dB | 30 dB |
|---|---|---|---|---|---|---|---|---|---|
| original | tiled | 0.677 | 0.177 | 0.485 | 0.600 | 0.870 | 0.870 | 0.868 | 0.873 |
| mixed | tiled | 0.950 | 0.785 | 0.965 | 0.978 | 0.993 | 0.973 | 0.980 | 0.975 |
| original | stream | 0.519 | 0.133 | 0.500 | 0.500 | 0.625 | 0.625 | 0.625 | 0.625 |
| mixed | stream | 0.950 | 0.723 | 0.968 | 0.990 | 0.993 | 0.988 | 0.998 | 0.993 |
| original | stream+impaired | 0.316 | 0.130 | 0.270 | 0.302 | 0.367 | 0.380 | 0.385 | 0.375 |
| mixed | stream+impaired | 0.942 | 0.718 | 0.922 | 0.990 | 0.988 | 0.990 | 0.995 | 0.993 |

Per-class accuracy:

| model | test data | AM-DSB-SC | AM-DSB-TC | FM | ASK | FSK | BPSK | QPSK | OFDM-QPSK |
|---|---|---|---|---|---|---|---|---|---|
| original | tiled | 0.86 | 0.00 | 0.57 | 0.89 | 0.84 | 0.68 | 0.58 | 1.00 |
| mixed | tiled | 0.96 | 1.00 | 0.97 | 0.97 | 0.92 | 0.97 | 0.91 | 0.90 |
| original | stream | 0.86 | 0.00 | 0.57 | 0.87 | 0.86 | 0.00 | 0.00 | 1.00 |
| mixed | stream | 0.96 | 1.00 | 0.97 | 0.99 | 0.90 | 1.00 | 0.84 | 0.94 |
| original | stream+impaired | 0.84 | 0.00 | 0.35 | 0.23 | 0.10 | 0.00 | 0.00 | 1.00 |
| mixed | stream+impaired | 0.94 | 1.00 | 0.95 | 0.95 | 0.95 | 0.98 | 0.81 | 0.96 |
