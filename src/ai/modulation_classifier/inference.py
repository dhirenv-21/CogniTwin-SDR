"""
Inference API for Radio Signal & Modulation Analysis.

Provides analyze_iq function for Spectrum Intelligence Agents, implementing feature extraction,
probabilistic ML inference, and confidence thresholding (confidence < 0.60 -> 'UNKNOWN').
"""

from typing import Any, Dict, Optional
import numpy as np

from src.signal.analysis import (
    estimate_frequency,
    estimate_bandwidth,
    calculate_power,
    estimate_snr_blind,
)
from .features import extract_features
from .model import load_model


def analyze_iq(
    iq_samples: np.ndarray,
    sample_rate: float = 100000.0,
    model: Optional[Any] = None,
    confidence_threshold: float = 0.60,
) -> Dict[str, Any]:
    """
    Upstream ML Analysis Engine for Spectrum Intelligence Agents.

    Extracts features, predicts modulation scheme with confidence thresholding,
    and calculates signal power, dominant frequency, bandwidth, and estimated SNR.

    Args:
        iq_samples: 1D complex array of received I/Q signal samples.
        sample_rate: Sampling frequency in Hz.
        model: Optional pre-loaded scikit-learn model instance.
        confidence_threshold: Minimum probability required for class assignment (default 0.60).

    Returns:
        Dictionary containing:
        {
            "predicted_modulation": str, # "UNKNOWN" if confidence < 0.60
            "confidence": float,
            "snr_db": float,
            "dominant_frequency": float,
            "bandwidth_hz": float,
            "signal_power": float,
        }
    """
    x = np.asarray(iq_samples, dtype=np.complex128)
    if len(x) == 0:
        return {
            "predicted_modulation": "UNKNOWN",
            "confidence": 0.0,
            "snr_db": 0.0,
            "snr_method": "below_resolution",
            "dominant_frequency": 0.0,
            "bandwidth_hz": 0.0,
            "signal_power": 0.0,
        }

    # 1. Feature Extraction on a unit-power copy. Seven of the features scale with
    # absolute amplitude, and callers differ: the Simulink bridge normalises every
    # window, the virtual-RF orchestrator does not. Normalising here makes the
    # classifier input identical on both paths (the default model is trained on
    # normalised windows). signal_power below is still reported from the raw input.
    p_in = float(np.mean(np.abs(x) ** 2))
    x_feat = x / np.sqrt(p_in) if p_in > 0 and np.isfinite(p_in) else x
    features = extract_features(x_feat, sample_rate=sample_rate)

    # 2. Load Model if not provided
    if model is None:
        model = load_model()

    if model is not None and hasattr(model, "predict_proba"):
        # Model Inference
        probs = model.predict_proba([features])[0]
        max_prob = float(np.max(probs))
        best_idx = int(np.argmax(probs))
        raw_class = str(model.classes_[best_idx])

        # CRUCIAL CONFIDENCE THRESHOLD LOGIC:
        if max_prob < confidence_threshold:
            predicted_modulation = "UNKNOWN"
        else:
            predicted_modulation = raw_class
    else:
        # Fallback if no model loaded
        predicted_modulation = "UNKNOWN"
        max_prob = 0.0

    # 3. Compute Metrics
    power = calculate_power(x)
    dom_freq = estimate_frequency(x, sample_rate)
    bw_3db = estimate_bandwidth(x, sample_rate, method="3db")

    # Blind SNR estimate (no transmit reference). This used to be
    # 10*log10(mean|x|^2 / median|x|^2), which is ~0 dB for a clean PSK signal and
    # ~1.6 dB for pure noise: bounded to 0..1.8 dB, falling as the link IMPROVED, and
    # flat for OFDM. That made the Spectrum Agent's 3 dB SNR_DROP anomaly unreachable.
    blind = estimate_snr_blind(x)

    return {
        "predicted_modulation": predicted_modulation,
        "confidence": max_prob,
        "snr_db": float(blind["snr_db"]),
        "snr_method": blind["method"],
        "dominant_frequency": dom_freq,
        "bandwidth_hz": bw_3db,
        "signal_power": power,
    }
