"""
Synthetic Dataset Generator for Radio Signal / Modulation Classification.

Generates complex I/Q signals across 8 modulation schemes (AM-DSB-SC, AM-DSB-TC, FM, ASK, FSK, BPSK, QPSK, OFDM-QPSK)
and multiple SNR levels, extracting features and splitting into independent Train (70%), Validation (15%), and Test (15%) sets.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
from sklearn.model_selection import train_test_split

from src.signal.generator import generate_sinusoid, to_iq, add_awgn
from src.modulation.analog import AMDSBSCModulator, AMDSTCModulator, FMModulator
from src.modulation.digital import generate_bits, ASKModulator, FSKModulator, PSKModulator
from src.multicarrier.ofdm import OFDMTransmitterReceiver
from .features import extract_features, FEATURE_NAMES


MODULATION_CLASSES: List[str] = [
    "AM-DSB-SC",
    "AM-DSB-TC",
    "FM",
    "ASK",
    "FSK",
    "BPSK",
    "QPSK",
    "OFDM-QPSK",
]


def generate_single_signal(
    mod_type: str,
    snr_db: float,
    sample_rate: float = 100000.0,
    n_samples: int = 512,
    seed: int = 42,
    repeating: bool = True,
) -> np.ndarray:
    """
    Generates a single complex I/Q signal array for a specified modulation type and SNR.

    repeating (default True, the original Task-5 behaviour): digital classes tile a
    short random pattern (n_samples//16 symbols, 512 OFDM bits) to fill the window.
    repeating=False draws enough bits for a genuinely non-repeating window, which
    is what a real link (and the Simulink PHY) produces.
    """
    duration = n_samples / sample_rate
    carrier_freq = 10000.0  # 10 kHz

    if mod_type == "AM-DSB-SC":
        _, msg = generate_sinusoid(freq=1000.0, sampling_rate=sample_rate, duration=duration, amplitude=1.0)
        mod = AMDSBSCModulator()
        passband = mod.modulate(msg, carrier_freq=carrier_freq, sample_rate=sample_rate)
        iq = to_iq(passband, method="hilbert")

    elif mod_type == "AM-DSB-TC":
        _, msg = generate_sinusoid(freq=1000.0, sampling_rate=sample_rate, duration=duration, amplitude=1.0)
        mod = AMDSTCModulator()
        passband = mod.modulate(msg, carrier_freq=carrier_freq, sample_rate=sample_rate, mod_index=0.8)
        iq = to_iq(passband, method="hilbert")

    elif mod_type == "FM":
        _, msg = generate_sinusoid(freq=1000.0, sampling_rate=sample_rate, duration=duration, amplitude=1.0)
        mod = FMModulator()
        passband = mod.modulate(msg, carrier_freq=carrier_freq, sample_rate=sample_rate, freq_dev=2000.0)
        iq = to_iq(passband, method="hilbert")

    elif mod_type == "ASK":
        n_bits = max(16, n_samples // 16) if repeating else n_samples
        bits = generate_bits(n_bits, seed=seed)
        mod = ASKModulator()
        iq = mod.modulate_baseband(bits)
        # Repeat to n_samples
        repeats = int(np.ceil(n_samples / len(iq)))
        iq = np.tile(iq, repeats)[:n_samples]

    elif mod_type == "FSK":
        n_bits = max(16, n_samples // 16) if repeating else n_samples
        bits = generate_bits(n_bits, seed=seed)
        mod = FSKModulator()
        iq = mod.modulate_baseband(bits)
        repeats = int(np.ceil(n_samples / len(iq)))
        iq = np.tile(iq, repeats)[:n_samples]

    elif mod_type == "BPSK":
        n_bits = max(16, n_samples // 16) if repeating else n_samples
        bits = generate_bits(n_bits, seed=seed)
        mod = PSKModulator(M=2)
        iq = mod.modulate_baseband(bits)
        repeats = int(np.ceil(n_samples / len(iq)))
        iq = np.tile(iq, repeats)[:n_samples]

    elif mod_type == "QPSK":
        n_bits = max(32, (n_samples // 16) * 2) if repeating else 2 * n_samples
        bits = generate_bits(n_bits, seed=seed)
        mod = PSKModulator(M=4)
        iq = mod.modulate_baseband(bits)
        repeats = int(np.ceil(n_samples / len(iq)))
        iq = np.tile(iq, repeats)[:n_samples]

    elif mod_type == "OFDM-QPSK":
        n_bits = 512 if repeating else 128 * int(np.ceil(n_samples / 80.0))
        bits = generate_bits(n_bits, seed=seed)
        ofdm = OFDMTransmitterReceiver(n_fft=64, cp_len=16, modulation_order=4)
        wave, _ = ofdm.modulate(bits)
        repeats = int(np.ceil(n_samples / len(wave)))
        iq = np.tile(wave, repeats)[:n_samples]

    else:
        raise ValueError(f"Unknown modulation type '{mod_type}'.")

    # Add AWGN noise for target SNR
    noisy_iq = add_awgn(iq, snr_db=snr_db, seed=seed)
    return noisy_iq


def generate_dataset(
    samples_per_class_per_snr: int = 100,
    snr_levels: List[float] = [0.0, 5.0, 10.0, 15.0, 20.0],
    sample_rate: float = 100000.0,
    seed: int = 42,
    representation: str = "tiled",
    normalize: bool = False,
    augment: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Generates feature dataset X and class labels y across specified SNR levels.

    representation: "tiled" (default, original Task-5 data), "stream"
        (non-repeating symbols) or "mixed" (one of each per sample index).
    normalize: scale each window to unit mean power before feature extraction,
        exactly as analyze_iq() now does at inference time.
    augment: deployment-like impairments drawn from the dataset RNG - a random
        carrier phase (block-fading rotation) on every window, and on half the
        windows an independent complex Gaussian jammer with power log-uniform in
        [0.05, 1] relative to the unit signal power.
    Defaults (tiled, no normalisation, no augmentation) reproduce the original
    Task-5 dataset exactly.

    Args:
        samples_per_class_per_snr: Number of samples per class per SNR level (default 100).
        snr_levels: List of SNR values in dB.
        sample_rate: Sampling frequency in Hz.
        seed: Random seed.

    Returns:
        Tuple of (X_features, y_labels, snr_array, metadata_dict).
    """
    if representation not in ("tiled", "stream", "mixed"):
        raise ValueError(f"representation must be tiled, stream or mixed (got '{representation}')")
    modes = {"tiled": [True], "stream": [False], "mixed": [True, False]}[representation]
    rng = np.random.default_rng(seed)

    X_list = []
    y_list = []
    snr_list = []

    for mod_idx, mod_type in enumerate(MODULATION_CLASSES):
        for snr in snr_levels:
            for s_idx in range(samples_per_class_per_snr):
                for repeating in modes:
                    sample_seed = int(rng.integers(0, 1000000))
                    iq_signal = generate_single_signal(
                        mod_type=mod_type,
                        snr_db=snr,
                        sample_rate=sample_rate,
                        n_samples=512,
                        seed=sample_seed,
                        repeating=repeating,
                    )
                    if augment:
                        iq_signal = iq_signal * np.exp(1j * rng.uniform(0.0, 2.0 * np.pi))
                        if rng.random() < 0.5:
                            p_jam = float(10.0 ** rng.uniform(np.log10(0.05), 0.0))
                            n = iq_signal.size
                            iq_signal = iq_signal + np.sqrt(p_jam / 2.0) * (
                                rng.standard_normal(n) + 1j * rng.standard_normal(n)
                            )
                    if normalize:
                        p = float(np.mean(np.abs(iq_signal) ** 2))
                        if p > 0:
                            iq_signal = iq_signal / np.sqrt(p)
                    feats = extract_features(iq_signal, sample_rate=sample_rate)
                    X_list.append(feats)
                    y_list.append(mod_type)
                    snr_list.append(snr)

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=str)
    snrs = np.array(snr_list, dtype=np.float64)

    metadata = {
        "classes": MODULATION_CLASSES,
        "snr_levels": snr_levels,
        "feature_names": FEATURE_NAMES,
        "num_samples": len(y),
        "representation": representation,
        "normalize": normalize,
        "augment": augment,
    }

    return X, y, snrs, metadata


def get_train_val_test_splits(
    X: np.ndarray,
    y: np.ndarray,
    snrs: np.ndarray,
    seed: int = 42,
) -> Tuple[Tuple[np.ndarray, np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Splits dataset into independent Train (70%), Validation (15%), and Test (15%) sets.

    Returns:
        ((X_train, y_train, snr_train), (X_val, y_val, snr_val), (X_test, y_test, snr_test))
    """
    # Check minimum class count for stratify safety
    _, counts1 = np.unique(y, return_counts=True)
    strat1 = y if (len(counts1) > 0 and np.min(counts1) >= 2) else None

    X_train, X_temp, y_train, y_temp, snr_train, snr_temp = train_test_split(
        X, y, snrs, test_size=0.30, random_state=seed, stratify=strat1
    )

    _, counts2 = np.unique(y_temp, return_counts=True)
    strat2 = y_temp if (len(counts2) > 0 and np.min(counts2) >= 2) else None

    X_val, X_test, y_val, y_test, snr_val, snr_test = train_test_split(
        X_temp, y_temp, snr_temp, test_size=0.50, random_state=seed, stratify=strat2
    )

    return (X_train, y_train, snr_train), (X_val, y_val, snr_val), (X_test, y_test, snr_test)
