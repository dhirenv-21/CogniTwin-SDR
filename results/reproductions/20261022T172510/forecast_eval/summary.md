# Digital Twin forecast evaluation

Synthetic virtual-RF environment. Forecast at t uses history <= t only; scored against the true SNR at t+h. `skill` = 1 - MAE_trend/MAE_persistence (positive: the twin's trend forecast beats repeating the last observation).

| scenario | noise dB | h (steps) | n | MAE trend | MAE persist | skill |
|---|---|---|---|---|---|---|
| awgn_degradation | 0 | 1 | 25 | 1.920 | 0.800 | -1.4 |
| awgn_degradation | 0 | 2 | 24 | 3.333 | 1.667 | -1.0 |
| awgn_degradation | 0 | 5 | 21 | 9.524 | 4.762 | -1.0 |
| awgn_degradation | 1 | 1 | 125 | 2.431 | 1.491 | -0.6302 |
| awgn_degradation | 1 | 2 | 120 | 4.027 | 2.317 | -0.7381 |
| awgn_degradation | 1 | 5 | 105 | 9.960 | 5.191 | -0.9188 |
| broadband_jamming | 0 | 1 | 25 | 1.920 | 0.800 | -1.4 |
| broadband_jamming | 0 | 2 | 24 | 3.333 | 1.667 | -1.0 |
| broadband_jamming | 0 | 5 | 21 | 9.524 | 4.762 | -1.0 |
| broadband_jamming | 1 | 1 | 125 | 2.431 | 1.491 | -0.6302 |
| broadband_jamming | 1 | 2 | 120 | 4.027 | 2.317 | -0.7381 |
| broadband_jamming | 1 | 5 | 105 | 9.960 | 5.191 | -0.9188 |
| clear_channel | 0 | 1 | 25 | 0.000 | 0.000 | 0.0 |
| clear_channel | 0 | 2 | 24 | 0.000 | 0.000 | 0.0 |
| clear_channel | 0 | 5 | 21 | 0.000 | 0.000 | 0.0 |
| clear_channel | 1 | 1 | 125 | 0.769 | 0.759 | -0.0127 |
| clear_channel | 1 | 2 | 120 | 0.987 | 0.760 | -0.2972 |
| clear_channel | 1 | 5 | 105 | 1.649 | 0.755 | -1.1843 |
| dynamic_combat_environment | 0 | 1 | 35 | 1.234 | 0.514 | -1.4 |
| dynamic_combat_environment | 0 | 2 | 34 | 2.118 | 1.059 | -1.0 |
| dynamic_combat_environment | 0 | 5 | 31 | 5.806 | 2.903 | -1.0 |
| dynamic_combat_environment | 1 | 1 | 175 | 1.723 | 1.196 | -0.4407 |
| dynamic_combat_environment | 1 | 2 | 170 | 2.755 | 1.716 | -0.6058 |
| dynamic_combat_environment | 1 | 5 | 155 | 6.142 | 3.296 | -0.8635 |
| multipath_fading | 0 | 1 | 25 | 1.152 | 0.480 | -1.4 |
| multipath_fading | 0 | 2 | 24 | 2.000 | 1.000 | -1.0 |
| multipath_fading | 0 | 5 | 21 | 5.714 | 2.857 | -1.0 |
| multipath_fading | 1 | 1 | 125 | 1.683 | 1.171 | -0.4375 |
| multipath_fading | 1 | 2 | 120 | 2.693 | 1.650 | -0.6323 |
| multipath_fading | 1 | 5 | 105 | 6.151 | 3.286 | -0.8717 |
| swept_jamming | 0 | 1 | 25 | 1.152 | 0.480 | -1.4 |
| swept_jamming | 0 | 2 | 24 | 2.000 | 1.000 | -1.0 |
| swept_jamming | 0 | 5 | 21 | 5.714 | 2.857 | -1.0 |
| swept_jamming | 1 | 1 | 125 | 1.767 | 1.223 | -0.4452 |
| swept_jamming | 1 | 2 | 120 | 2.783 | 1.688 | -0.6484 |
| swept_jamming | 1 | 5 | 105 | 6.728 | 3.421 | -0.9669 |
| synthetic_ramp | 0 | 1 | 25 | 0.000 | 0.600 | 1.0 |
| synthetic_ramp | 0 | 2 | 24 | 0.000 | 1.200 | 1.0 |
| synthetic_ramp | 0 | 5 | 21 | 0.000 | 3.000 | 1.0 |
| synthetic_ramp | 1 | 1 | 125 | 0.769 | 0.900 | 0.1462 |
| synthetic_ramp | 1 | 2 | 120 | 0.987 | 1.233 | 0.1999 |
| synthetic_ramp | 1 | 5 | 105 | 1.649 | 2.909 | 0.4332 |

## Alternative forecasters (evaluated alongside; the twin's predictor is unchanged)

MAE in dB on the steps where the twin has a forecast. Parameters fixed a priori (alpha 0.5, jump 3 dB, residual 1 dB, window 5). Lowest MAE per row in **bold**.

| scenario | noise | h | twin_trend | persistence | exp_smoothing | changepoint_trend | trend_fallback |
|---|---|---|---|---|---|---|---|
| awgn_degradation | 0 | 1 | 1.920 | **0.800** | 1.599 | **0.800** | **0.800** |
| awgn_degradation | 0 | 2 | 3.333 | **1.667** | 2.498 | **1.667** | **1.667** |
| awgn_degradation | 0 | 5 | 9.524 | **4.762** | 5.699 | **4.762** | **4.762** |
| awgn_degradation | 1 | 1 | 2.431 | **1.491** | 1.802 | 1.530 | 1.551 |
| awgn_degradation | 1 | 2 | 4.027 | **2.317** | 2.663 | 2.540 | 2.476 |
| awgn_degradation | 1 | 5 | 9.960 | **5.191** | 5.709 | 5.636 | 5.365 |
| broadband_jamming | 0 | 1 | 1.920 | **0.800** | 1.599 | **0.800** | **0.800** |
| broadband_jamming | 0 | 2 | 3.333 | **1.667** | 2.498 | **1.667** | **1.667** |
| broadband_jamming | 0 | 5 | 9.524 | **4.762** | 5.699 | **4.762** | **4.762** |
| broadband_jamming | 1 | 1 | 2.431 | **1.491** | 1.802 | 1.530 | 1.551 |
| broadband_jamming | 1 | 2 | 4.027 | **2.317** | 2.663 | 2.540 | 2.476 |
| broadband_jamming | 1 | 5 | 9.960 | **5.191** | 5.709 | 5.636 | 5.365 |
| clear_channel | 0 | 1 | **0.000** | **0.000** | **0.000** | **0.000** | **0.000** |
| clear_channel | 0 | 2 | **0.000** | **0.000** | **0.000** | **0.000** | **0.000** |
| clear_channel | 0 | 5 | **0.000** | **0.000** | **0.000** | **0.000** | **0.000** |
| clear_channel | 1 | 1 | 0.769 | 0.759 | **0.461** | 0.769 | 0.805 |
| clear_channel | 1 | 2 | 0.987 | 0.760 | **0.463** | 0.987 | 0.993 |
| clear_channel | 1 | 5 | 1.649 | 0.755 | **0.451** | 1.649 | 1.586 |
| dynamic_combat_environment | 0 | 1 | 1.234 | **0.514** | 1.028 | **0.514** | **0.514** |
| dynamic_combat_environment | 0 | 2 | 2.118 | **1.059** | 1.587 | **1.059** | **1.059** |
| dynamic_combat_environment | 0 | 5 | 5.806 | **2.903** | 3.478 | **2.903** | **2.903** |
| dynamic_combat_environment | 1 | 1 | 1.723 | **1.196** | 1.310 | 1.264 | 1.251 |
| dynamic_combat_environment | 1 | 2 | 2.755 | **1.716** | 1.836 | 1.950 | 1.862 |
| dynamic_combat_environment | 1 | 5 | 6.142 | **3.296** | 3.545 | 3.826 | 3.541 |
| multipath_fading | 0 | 1 | 1.152 | **0.480** | 0.960 | **0.480** | **0.480** |
| multipath_fading | 0 | 2 | 2.000 | **1.000** | 1.499 | **1.000** | **1.000** |
| multipath_fading | 0 | 5 | 5.714 | **2.857** | 3.418 | **2.857** | **2.857** |
| multipath_fading | 1 | 1 | 1.683 | **1.171** | 1.208 | 1.210 | 1.231 |
| multipath_fading | 1 | 2 | 2.693 | **1.650** | 1.711 | 1.874 | 1.810 |
| multipath_fading | 1 | 5 | 6.151 | **3.286** | 3.468 | 3.732 | 3.460 |
| swept_jamming | 0 | 1 | 1.152 | **0.480** | 0.960 | **0.480** | **0.480** |
| swept_jamming | 0 | 2 | 2.000 | **1.000** | 1.500 | **1.000** | **1.000** |
| swept_jamming | 0 | 5 | 5.714 | **2.857** | 3.428 | **2.857** | **2.857** |
| swept_jamming | 1 | 1 | 1.767 | **1.223** | 1.271 | 1.233 | 1.252 |
| swept_jamming | 1 | 2 | 2.783 | **1.688** | 1.780 | 1.919 | 1.874 |
| swept_jamming | 1 | 5 | 6.728 | **3.421** | 3.625 | 4.185 | 3.931 |
| synthetic_ramp | 0 | 1 | **0.000** | 0.600 | 1.197 | **0.000** | **0.000** |
| synthetic_ramp | 0 | 2 | **0.000** | 1.200 | 1.797 | **0.000** | **0.000** |
| synthetic_ramp | 0 | 5 | **0.000** | 3.000 | 3.596 | **0.000** | **0.000** |
| synthetic_ramp | 1 | 1 | **0.769** | 0.900 | 1.123 | 0.783 | 0.801 |
| synthetic_ramp | 1 | 2 | 0.987 | 1.233 | 1.713 | **0.979** | 0.987 |
| synthetic_ramp | 1 | 5 | **1.649** | 2.909 | 3.536 | 1.745 | 1.774 |
