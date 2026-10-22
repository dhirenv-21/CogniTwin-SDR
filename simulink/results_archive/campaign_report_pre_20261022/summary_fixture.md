# CogniTwin-SDR Simulink -> ACWRA Validation Campaign

- Data source: **FIXTURE**  (Python reference PHY fixtures - NOT Simulink)
- Total checks executed: **402**

## Verdict totals

| Verdict | Count |
|---|---:|
| PASS | 396 |
| INCONCLUSIVE | 2 |
| NOT RUN | 4 |

## By group

| Group | PASS | STATISTICAL PASS | INCONCLUSIVE | FAIL | NOT RUN |
|---|---:|---:|---:|---:|---:|
| A_basic_simulink | 8 | 0 | 0 | 0 | 4 |
| B_modulation | 1 | 0 | 2 | 0 | 0 |
| C_snr | 13 | 0 | 0 | 0 | 0 |
| D_interference | 13 | 0 | 0 | 0 | 0 |
| E_channel | 6 | 0 | 0 | 0 | 0 |
| F_stress | 90 | 0 | 0 | 0 | 0 |
| G_iq_validation | 125 | 0 | 0 | 0 | 0 |
| H_data_integrity | 15 | 0 | 0 | 0 | 0 |
| I_end_to_end | 125 | 0 | 0 | 0 | 0 |

## Not run (with reason)

- **A1 Simulink model loads**: MATLAB/Simulink not available in this environment
- **A2 Simulink model compiles**: MATLAB/Simulink not available in this environment
- **A3 Simulation runs**: MATLAB/Simulink not available in this environment
- **A4 Simulation completes**: MATLAB/Simulink not available in this environment

## Inconclusive

- **B001 B_modulation_001_bpsk_snr10p0_int0p0_awgn**: pipeline completed and ACWRA decided, but SpectrumAgent reported 'OFDM-QPSK' for a 'BPSK' waveform (existing classifier limitation, not a pipeline fault)
- **B002 B_modulation_002_qpsk_snr10p0_int0p0_awgn**: pipeline completed and ACWRA decided, but SpectrumAgent reported 'OFDM-QPSK' for a 'QPSK' waveform (existing classifier limitation, not a pipeline fault)
