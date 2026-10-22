"""
Spectrum Intelligence Agent Module.

Analyzes raw radio frequency I/Q samples using machine learning and spectral signal processing,
detecting modulation schemes and flagging spectral anomalies.
"""

from typing import Optional
import numpy as np

from src.ai.modulation_classifier.inference import analyze_iq
from src.signal.analysis import BLIND_SNR_RESOLUTION_DB
from .base_agent import BaseAgent
from .messages import SpectrumIntelligenceResult


class SpectrumAgent(BaseAgent):
    """
    Specialized agent for spectrum intelligence and modulation observation.
    """

    def __init__(self, sample_rate: float = 100000.0):
        super().__init__(name="SpectrumIntelligenceAgent")
        self.sample_rate = sample_rate
        self.prev_snr_db: Optional[float] = None

    def process(
        self,
        iq_samples: np.ndarray,
        timestamp_s: float = 0.0,
        env_interference_power: float = 0.0,
    ) -> SpectrumIntelligenceResult:
        """
        Analyzes I/Q sample buffer and returns SpectrumIntelligenceResult.

        Args:
            iq_samples: 1D complex array of I/Q samples.
            timestamp_s: Current simulation timestamp.
            env_interference_power: Ground truth or estimated interference power.

        Returns:
            SpectrumIntelligenceResult dataclass.
        """
        self.status = "ANALYZING_IQ"

        # Use 512-sample block for classification matching Task 5 dataset block size
        input_block = iq_samples[:512] if len(iq_samples) >= 512 else iq_samples
        ml_res = analyze_iq(input_block, sample_rate=self.sample_rate, confidence_threshold=0.60)

        mod_type = ml_res["predicted_modulation"]
        snr_est = float(ml_res["snr_db"])
        bw = float(ml_res["bandwidth_hz"])
        conf = float(ml_res["confidence"])
        self.confidence = conf

        # Anomaly Detection Logic
        anomaly = "NONE"
        if self.prev_snr_db is not None:
            # Compare at the estimator's resolution: a window that fell below
            # resolution reports the floor (-10 dB), which would otherwise look like a
            # ~10 dB drop from a neighbour resolved at ~0 dB (measured: 20-26 % false
            # SNR_DROP for stationary PSK at 0 dB). Drops from well above the
            # resolution limit still register.
            snr_drop = max(self.prev_snr_db, BLIND_SNR_RESOLUTION_DB) - max(snr_est, BLIND_SNR_RESOLUTION_DB)
            if snr_drop > 3.0:
                anomaly = "SNR_DROP"
            elif env_interference_power > 1.0:
                anomaly = "HIGH_INTERFERENCE"
        elif env_interference_power > 1.0:
            anomaly = "HIGH_INTERFERENCE"

        self.prev_snr_db = snr_est

        result = SpectrumIntelligenceResult(
            timestamp_s=timestamp_s,
            modulation=mod_type,
            snr_db=snr_est,
            interference_power=env_interference_power,
            bandwidth_hz=bw,
            classifier_confidence=conf,
            anomaly_flag=anomaly,
        )

        self._last_output = result
        self.status = "IDLE"
        return result
