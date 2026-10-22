"""
Inter-Agent Communication Message Dataclasses.

Defines structured evidence messages exchanged between specialized intelligence agents.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class SpectrumIntelligenceResult:
    """Output message produced by the Spectrum Intelligence Agent."""
    timestamp_s: float = 0.0
    modulation: str = "QPSK"
    snr_db: float = 20.0
    interference_power: float = 0.0
    bandwidth_hz: float = 25000.0
    classifier_confidence: float = 1.0
    anomaly_flag: str = "NONE"


@dataclass
class PredictionResult:
    """Output message produced by the Prediction Agent."""
    predicted_timestamp_s: float = 0.0
    next_snr_db: Optional[float] = 20.0
    next_ber: Optional[float] = 0.0
    next_interference_power: Optional[float] = 0.0
    risk_score: float = 0.0
    risk_level: str = "LOW"
    prediction_status: str = "SUCCESS"


@dataclass
class DefenseCandidate:
    """Output message produced by the Cyber Defense Agent."""
    candidate_strategies: List[str] = field(default_factory=lambda: ["Keep Current"])
    rationale: str = "System Operating Nominally"
    risk_level: str = "LOW"


@dataclass
class MultiAgentSnapshot:
    """Combined evidence snapshot produced by the MultiAgentOrchestrator."""
    timestamp_s: float = 0.0
    spectrum_result: Optional[SpectrumIntelligenceResult] = None
    prediction_result: Optional[PredictionResult] = None
    defense_candidates: Optional[DefenseCandidate] = None
