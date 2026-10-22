# Spectrum Agent on GNU Radio I/Q

Data: GNU Radio software simulation, 6912 windows.

Accuracy 0.859, ECE 0.051.

```json
{
  "windows": 6912,
  "accuracy": 0.8586516203703703,
  "ece_10bin": 0.05107494212962954,
  "confusion": {
    "BPSK": {
      "BPSK": 2099,
      "OFDM-QPSK": 161,
      "QPSK": 0,
      "UNKNOWN": 44
    },
    "QPSK": {
      "BPSK": 0,
      "OFDM-QPSK": 572,
      "QPSK": 1674,
      "UNKNOWN": 58
    },
    "OFDM-QPSK": {
      "BPSK": 3,
      "OFDM-QPSK": 2162,
      "QPSK": 56,
      "UNKNOWN": 83
    }
  },
  "per_class": {
    "BPSK": {
      "precision": 0.9985727878211227,
      "recall": 0.9110243055555556,
      "f1": 0.952791647753064
    },
    "QPSK": {
      "precision": 0.9676300578034682,
      "recall": 0.7265625,
      "f1": 0.8299454635597422
    },
    "OFDM-QPSK": {
      "precision": 0.7468048359240069,
      "recall": 0.9383680555555556,
      "f1": 0.8316984035391422
    }
  },
  "accuracy_by_impairment_snr": {
    "awgn@-5dB": 0.6423611111111112,
    "awgn@+0dB": 0.9444444444444444,
    "awgn@+5dB": 0.9861111111111112,
    "awgn@+10dB": 0.9826388888888888,
    "awgn@+15dB": 0.9756944444444444,
    "awgn@+20dB": 0.96875,
    "block_rayleigh@-5dB": 0.3506944444444444,
    "block_rayleigh@+0dB": 0.5625,
    "block_rayleigh@+5dB": 0.8506944444444444,
    "block_rayleigh@+10dB": 0.96875,
    "block_rayleigh@+15dB": 0.9722222222222222,
    "block_rayleigh@+20dB": 0.9652777777777778,
    "jammer@-5dB": 0.6597222222222222,
    "jammer@+0dB": 0.9236111111111112,
    "jammer@+5dB": 0.9895833333333334,
    "jammer@+10dB": 0.9861111111111112,
    "jammer@+15dB": 0.9826388888888888,
    "jammer@+20dB": 0.9791666666666666,
    "tv_rayleigh@-5dB": 0.5208333333333334,
    "tv_rayleigh@+0dB": 0.7430555555555556,
    "tv_rayleigh@+5dB": 0.8819444444444444,
    "tv_rayleigh@+10dB": 0.9131944444444444,
    "tv_rayleigh@+15dB": 0.9305555555555556,
    "tv_rayleigh@+20dB": 0.9270833333333334
  },
  "snr_bias_db_true_sinr_ge_5dB": {
    "BPSK/awgn": -0.021623712471124542,
    "BPSK/block_rayleigh": 0.029559548985763164,
    "BPSK/jammer": 0.030194961669468518,
    "BPSK/tv_rayleigh": -4.870414405816758,
    "OFDM-QPSK/awgn": -0.10439528049855075,
    "OFDM-QPSK/block_rayleigh": -0.019866882023800724,
    "OFDM-QPSK/jammer": -0.0269511205489593,
    "OFDM-QPSK/tv_rayleigh": -0.12254247884542324,
    "QPSK/awgn": 0.023091559780622523,
    "QPSK/block_rayleigh": -0.010093133454744736,
    "QPSK/jammer": 0.05341102204743165,
    "QPSK/tv_rayleigh": -4.9654637386051705
  },
  "snr_mae_db_true_sinr_ge_5dB": {
    "BPSK/awgn": 0.18269844133876198,
    "BPSK/block_rayleigh": 0.22743430615258303,
    "BPSK/jammer": 0.24353296838733363,
    "BPSK/tv_rayleigh": 4.881467655834677,
    "OFDM-QPSK/awgn": 0.5809842838094438,
    "OFDM-QPSK/block_rayleigh": 0.5025880616466967,
    "OFDM-QPSK/jammer": 0.5074688661704602,
    "OFDM-QPSK/tv_rayleigh": 0.5449303603425795,
    "QPSK/awgn": 0.18121377340091235,
    "QPSK/block_rayleigh": 0.2290848082330147,
    "QPSK/jammer": 0.2615873557934565,
    "QPSK/tv_rayleigh": 4.987651150819845
  },
  "false_snr_drop_rate": 0.004629629629629629,
  "interference_estimation": "NOT EVALUATED: the SpectrumAgent passes interference power through"
}
```
