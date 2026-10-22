# Closed-loop evaluation `run_20261022_v1`

Commit `b5f490d`, 6 scenarios x 6 policies x 5 seeds = 180 episodes, 5700 steps. Mean (std over seeds).

**Caveat:** outcomes come from the same virtual-RF link model the Digital Twin sandbox uses; this evaluates decision logic under a perfect model, not physical-layer performance.

## awgn_degradation

| policy | goodput kb/s | regret kb/s | BER | pkt loss | SE b/sym | switches | in oracle set | recovery steps | decide ms |
|---|---|---|---|---|---|---|---|---|---|
| acwra | 102.1 (0.0) | 19.1 | 0.0262 | 0.340 | 1.37 | 1.0 | 0.70 | 0.0 | 0.13 |
| fixed_BPSK | 66.6 (0.0) | 54.6 | 0.0262 | 0.334 | 1.00 | 0.0 | 0.33 | 5.0 | 0.00 |
| fixed_QPSK | 121.2 (0.0) | 0.0 | 0.0531 | 0.394 | 2.00 | 0.0 | 1.00 | 0.0 | 0.00 |
| fixed_OFDM-QPSK | 121.2 (0.0) | 0.0 | 0.0531 | 0.394 | 1.60 | 0.0 | 1.00 | 0.0 | 0.00 |
| snr_threshold | 121.2 (0.0) | 0.0 | 0.0291 | 0.394 | 1.70 | 1.0 | 1.00 | 0.0 | 0.00 |
| oracle | 121.2 (0.0) | 0.0 | 0.0265 | 0.394 | 1.67 | 1.0 | 1.00 | 0.0 | 0.00 |
Steps where every modulation ties (all packets lost): 10 of 30.

## broadband_jamming

| policy | goodput kb/s | regret kb/s | BER | pkt loss | SE b/sym | switches | in oracle set | recovery steps | decide ms |
|---|---|---|---|---|---|---|---|---|---|
| acwra | 66.7 (0.0) | 0.0 | 0.1917 | 0.667 | 1.63 | 3.6 | 1.00 | 0.0 | 0.15 |
| fixed_BPSK | 33.3 (0.0) | 33.3 | 0.1917 | 0.667 | 1.00 | 0.0 | 0.67 | 0.0 | 0.00 |
| fixed_QPSK | 66.7 (0.0) | 0.0 | 0.1919 | 0.667 | 2.00 | 0.0 | 1.00 | 0.0 | 0.00 |
| fixed_OFDM-QPSK | 66.7 (0.0) | 0.0 | 0.1919 | 0.667 | 1.60 | 0.0 | 1.00 | 0.0 | 0.00 |
| snr_threshold | 66.7 (0.0) | 0.0 | 0.1919 | 0.667 | 1.70 | 1.0 | 1.00 | 0.0 | 0.00 |
| oracle | 66.7 (0.0) | 0.0 | 0.1917 | 0.667 | 1.33 | 1.0 | 1.00 | 0.0 | 0.00 |
Steps where every modulation ties (all packets lost): 20 of 30.

## clear_channel

| policy | goodput kb/s | regret kb/s | BER | pkt loss | SE b/sym | switches | in oracle set | recovery steps | decide ms |
|---|---|---|---|---|---|---|---|---|---|
| acwra | 200.0 (0.0) | 0.0 | 0.0000 | 0.000 | 2.00 | 0.0 | 1.00 | nan | 0.12 |
| fixed_BPSK | 100.0 (0.0) | 100.0 | 0.0000 | 0.000 | 1.00 | 0.0 | 0.00 | nan | 0.00 |
| fixed_QPSK | 200.0 (0.0) | 0.0 | 0.0000 | 0.000 | 2.00 | 0.0 | 1.00 | nan | 0.00 |
| fixed_OFDM-QPSK | 200.0 (0.0) | 0.0 | 0.0000 | 0.000 | 1.60 | 0.0 | 1.00 | nan | 0.00 |
| snr_threshold | 200.0 (0.0) | 0.0 | 0.0000 | 0.000 | 2.00 | 0.0 | 1.00 | nan | 0.00 |
| oracle | 200.0 (0.0) | 0.0 | 0.0000 | 0.000 | 2.00 | 0.0 | 1.00 | nan | 0.00 |
Steps where every modulation ties (all packets lost): 0 of 30.

## dynamic_combat_environment

| policy | goodput kb/s | regret kb/s | BER | pkt loss | SE b/sym | switches | in oracle set | recovery steps | decide ms |
|---|---|---|---|---|---|---|---|---|---|
| acwra | 50.0 (0.0) | 0.0 | 0.1966 | 0.750 | 1.52 | 4.4 | 1.00 | 0.0 | 0.15 |
| fixed_BPSK | 25.0 (0.0) | 25.0 | 0.1964 | 0.750 | 1.00 | 0.0 | 0.75 | 0.0 | 0.00 |
| fixed_QPSK | 50.0 (0.0) | 0.0 | 0.2015 | 0.750 | 2.00 | 0.0 | 1.00 | 0.0 | 0.00 |
| fixed_OFDM-QPSK | 50.0 (0.0) | 0.0 | 0.2015 | 0.750 | 1.60 | 0.0 | 1.00 | 0.0 | 0.00 |
| snr_threshold | 50.0 (0.0) | 0.0 | 0.1969 | 0.750 | 1.52 | 1.0 | 1.00 | 0.0 | 0.00 |
| oracle | 50.0 (0.0) | 0.0 | 0.1964 | 0.750 | 1.25 | 1.0 | 1.00 | 0.0 | 0.00 |
Steps where every modulation ties (all packets lost): 30 of 40.

## multipath_fading

| policy | goodput kb/s | regret kb/s | BER | pkt loss | SE b/sym | switches | in oracle set | recovery steps | decide ms |
|---|---|---|---|---|---|---|---|---|---|
| acwra | 119.7 (7.5) | 41.7 | 0.0031 | 0.170 | 1.51 | 2.0 | 0.56 | 0.0 | 0.13 |
| fixed_BPSK | 94.8 (0.0) | 66.7 | 0.0002 | 0.052 | 1.00 | 0.0 | 0.33 | 5.0 | 0.00 |
| fixed_QPSK | 133.6 (0.0) | 27.8 | 0.0070 | 0.332 | 2.00 | 0.0 | 0.67 | 5.0 | 0.00 |
| fixed_OFDM-QPSK | 133.6 (0.0) | 27.8 | 0.0070 | 0.332 | 1.60 | 0.0 | 0.67 | 5.0 | 0.00 |
| snr_threshold | 133.6 (0.0) | 27.8 | 0.0070 | 0.332 | 2.00 | 0.0 | 0.67 | 5.0 | 0.00 |
| oracle | 161.4 (0.0) | 0.0 | 0.0002 | 0.052 | 1.67 | 1.0 | 1.00 | 0.0 | 0.00 |
Steps where every modulation ties (all packets lost): 0 of 30.

## swept_jamming

| policy | goodput kb/s | regret kb/s | BER | pkt loss | SE b/sym | switches | in oracle set | recovery steps | decide ms |
|---|---|---|---|---|---|---|---|---|---|
| acwra | 100.0 (0.0) | 0.0 | 0.1503 | 0.500 | 1.53 | 1.0 | 1.00 | 0.0 | 0.15 |
| fixed_BPSK | 50.0 (0.0) | 50.0 | 0.1501 | 0.500 | 1.00 | 0.0 | 0.50 | 0.0 | 0.00 |
| fixed_QPSK | 100.0 (0.0) | 0.0 | 0.1530 | 0.500 | 2.00 | 0.0 | 1.00 | 0.0 | 0.00 |
| fixed_OFDM-QPSK | 100.0 (0.0) | 0.0 | 0.1530 | 0.500 | 1.60 | 0.0 | 1.00 | 0.0 | 0.00 |
| snr_threshold | 100.0 (0.0) | 0.0 | 0.1503 | 0.500 | 1.53 | 1.0 | 1.00 | 0.0 | 0.00 |
| oracle | 100.0 (0.0) | 0.0 | 0.1501 | 0.500 | 1.50 | 1.0 | 1.00 | 0.0 | 0.00 |
Steps where every modulation ties (all packets lost): 15 of 30.

## ACWRA internals

| scenario | mean utility | twin 1-step SNR MAE dB | full step ms |
|---|---|---|---|
| awgn_degradation | 0.109 | 1.92 | 31.7 |
| broadband_jamming | 0.018 | 1.92 | 31.1 |
| clear_channel | -0.019 | 0.00 | 31.4 |
| dynamic_combat_environment | 0.014 | 1.23 | 31.4 |
| multipath_fading | -0.001 | 1.15 | 31.5 |
| swept_jamming | -0.012 | 1.15 | 31.3 |
