"""
ACWRA Decision Dataclasses.

Defines candidate scoring breakdowns and overall decision output structures for ACWRA.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class CandidateScore:
    """Detailed score breakdown for a single candidate communication strategy."""
    strategy: str
    modulation: str
    predicted_ber: float
    predicted_throughput_bps: float
    theoretical_se: float
    utility_score: float
    t_norm: float
    ber_norm: float
    se_norm: float
    complexity_prior: float

    def to_dict(self) -> Dict[str, Any]:
        """Converts candidate score to dictionary."""
        return {
            "strategy": self.strategy,
            "modulation": self.modulation,
            "predicted_ber": self.predicted_ber,
            "predicted_throughput_bps": self.predicted_throughput_bps,
            "theoretical_se": self.theoretical_se,
            "utility_score": self.utility_score,
            "t_norm": self.t_norm,
            "ber_norm": self.ber_norm,
            "se_norm": self.se_norm,
            "complexity_prior": self.complexity_prior,
        }


@dataclass
class ACWRADecision:
    """Final decision output object produced by the ACWRA decision engine."""
    timestamp_s: float
    selected_strategy: str
    expected_utility: float
    candidate_scores: List[CandidateScore] = field(default_factory=list)
    risk_score: float = 0.0
    agent_confidence: float = 1.0
    decision_trace: str = ""
