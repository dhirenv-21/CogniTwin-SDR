"""
Unit tests for Analog Modulation & Demodulation Module.
"""

import numpy as np
import pytest

from src.signal.generator import generate_sinusoid
from src.signal.analysis import estimate_bandwidth
from src.channel.awgn import apply_awgn
from src.evaluation.metrics import pearson_correlation
from src.modulation.analog import (
    AMDSBSCModulator,
    AMDSTCModulator,
    SSBModulator,
    FMModulator,
    PMModulator,
)


@pytest.fixture
def signal_setup():
    """
    Standard test parameters fixture.
    fs = 100 kHz, fc = 10 kHz, fm = 1 kHz, duration = 0.1 s
    """
    sample_rate = 100000.0  # Hz
    carrier_freq = 10000.0  # Hz
    msg_freq = 1000.0  # Hz
    duration = 0.1  # seconds

    t, message = generate_sinusoid(
        freq=msg_freq,
        sampling_rate=sample_rate,
        duration=duration,
        amplitude=1.0,
    )
    return {
        "t": t,
        "message": message,
        "sample_rate": sample_rate,
        "carrier_freq": carrier_freq,
        "msg_freq": msg_freq,
    }


def test_am_dsbsc_dimensions_and_correlation(signal_setup):
    """
    Tests AM DSB-SC array dimensions and high-SNR reconstruction correlation (>0.90).
    """
    m = signal_setup["message"]
    fs = signal_setup["sample_rate"]
    fc = signal_setup["carrier_freq"]

    modulator = AMDSBSCModulator()
    modulated = modulator.modulate(m, carrier_freq=fc, sample_rate=fs)
    noisy = apply_awgn(modulated, snr_db=30.0, seed=42)
    recovered = modulator.demodulate(noisy, carrier_freq=fc, sample_rate=fs, lpf_cutoff=3000.0)

    assert len(modulated) == len(m), "Modulated signal length mismatch."
    assert len(recovered) == len(m), "Recovered signal length mismatch."

    # Trim edge transients for metric computation
    trim = 100
    r = pearson_correlation(m[trim:-trim], recovered[trim:-trim])
    assert r > 0.90, f"AM DSB-SC Pearson correlation {r:.4f} is below 0.90 threshold."


def test_am_dsbtc_dimensions_and_correlation(signal_setup):
    """
    Tests AM DSB-TC array dimensions and high-SNR reconstruction correlation (>0.90).
    """
    m = signal_setup["message"]
    fs = signal_setup["sample_rate"]
    fc = signal_setup["carrier_freq"]

    modulator = AMDSTCModulator()
    modulated = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, mod_index=0.8)
    noisy = apply_awgn(modulated, snr_db=30.0, seed=42)
    recovered = modulator.demodulate(noisy, carrier_freq=fc, sample_rate=fs, lpf_cutoff=3000.0)

    assert len(modulated) == len(m)
    assert len(recovered) == len(m)

    trim = 100
    r = pearson_correlation(m[trim:-trim], recovered[trim:-trim])
    assert r > 0.90, f"AM DSB-TC Pearson correlation {r:.4f} is below 0.90 threshold."


def test_ssb_usb_and_lsb_correlation(signal_setup):
    """
    Tests SSB USB and LSB reconstruction correlation (>0.90).
    """
    m = signal_setup["message"]
    fs = signal_setup["sample_rate"]
    fc = signal_setup["carrier_freq"]

    modulator = SSBModulator()

    for sideband in ["usb", "lsb"]:
        modulated = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, sideband=sideband)
        noisy = apply_awgn(modulated, snr_db=30.0, seed=42)
        recovered = modulator.demodulate(noisy, carrier_freq=fc, sample_rate=fs, lpf_cutoff=3000.0)

        assert len(modulated) == len(m)
        assert len(recovered) == len(m)

        trim = 100
        r = pearson_correlation(m[trim:-trim], recovered[trim:-trim])
        assert r > 0.90, f"SSB-{sideband.upper()} Pearson correlation {r:.4f} is below 0.90 threshold."


def test_fm_nbfm_and_wbfm_correlation(signal_setup):
    """
    Tests NBFM and WBFM reconstruction correlation (>0.90).
    """
    m = signal_setup["message"]
    fs = signal_setup["sample_rate"]
    fc = signal_setup["carrier_freq"]

    modulator = FMModulator()

    # NBFM (freq_dev = 200 Hz)
    mod_nb = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, freq_dev=200.0)
    rec_nb = modulator.demodulate(mod_nb, carrier_freq=fc, sample_rate=fs, freq_dev=200.0, lpf_cutoff=3000.0)

    # WBFM (freq_dev = 5000 Hz)
    mod_wb = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, freq_dev=5000.0)
    rec_wb = modulator.demodulate(mod_wb, carrier_freq=fc, sample_rate=fs, freq_dev=5000.0, lpf_cutoff=3000.0)

    trim = 150
    r_nb = pearson_correlation(m[trim:-trim], rec_nb[trim:-trim])
    r_wb = pearson_correlation(m[trim:-trim], rec_wb[trim:-trim])

    assert r_nb > 0.90, f"NBFM Pearson correlation {r_nb:.4f} is below 0.90 threshold."
    assert r_wb > 0.90, f"WBFM Pearson correlation {r_wb:.4f} is below 0.90 threshold."


def test_fm_nbfm_vs_wbfm_bandwidth(signal_setup):
    """
    Tests that WBFM occupies significantly larger bandwidth than NBFM.
    """
    m = signal_setup["message"]
    fs = signal_setup["sample_rate"]
    fc = signal_setup["carrier_freq"]

    modulator = FMModulator()
    mod_nb = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, freq_dev=200.0)
    mod_wb = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, freq_dev=5000.0)

    bw_nb = estimate_bandwidth(mod_nb, fs, method="occupied", power_ratio=0.99)
    bw_wb = estimate_bandwidth(mod_wb, fs, method="occupied", power_ratio=0.99)

    assert bw_wb > bw_nb * 1.5, f"WBFM bandwidth ({bw_wb:.1f} Hz) is not significantly larger than NBFM ({bw_nb:.1f} Hz)."


def test_pm_correlation(signal_setup):
    """
    Tests PM reconstruction correlation (>0.90).
    """
    m = signal_setup["message"]
    fs = signal_setup["sample_rate"]
    fc = signal_setup["carrier_freq"]

    modulator = PMModulator()
    modulated = modulator.modulate(m, carrier_freq=fc, sample_rate=fs, phase_dev=1.5)
    noisy = apply_awgn(modulated, snr_db=30.0, seed=42)
    recovered = modulator.demodulate(noisy, carrier_freq=fc, sample_rate=fs, phase_dev=1.5, lpf_cutoff=3000.0)

    assert len(modulated) == len(m)
    assert len(recovered) == len(m)

    trim = 100
    r = pearson_correlation(m[trim:-trim], recovered[trim:-trim])
    assert r > 0.90, f"PM Pearson correlation {r:.4f} is below 0.90 threshold."
