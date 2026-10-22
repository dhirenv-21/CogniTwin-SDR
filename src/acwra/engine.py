"""
ACWRA Main Decision Engine Module.

Executes the deterministic Adaptive Cognitive Wireless Reasoning Algorithm (ACWRA).
"""

import math
from typing import Optional, List
from src.digital_twin.twin import DigitalTwin
from src.agents.messages import MultiAgentSnapshot
from .decision import ACWRADecision, CandidateScore
from .scoring import ACWRAScoringEngine
from .trace import DecisionTrace


class ACWRAEngine:
    """
    Main ACWRA decision loop engine.
    """

    def __init__(
        self,
        weight_throughput: float = 0.4,
        weight_se: float = 0.2,
        weight_ber: float = 0.6,
        lambda_complexity: float = 1.0,
    ):
        self.scoring_engine = ACWRAScoringEngine(
            weight_throughput=weight_throughput,
            weight_se=weight_se,
            weight_ber=weight_ber,
            lambda_complexity=lambda_complexity,
        )

    def evaluate_and_decide(
        self,
        snapshot: MultiAgentSnapshot,
        digital_twin: DigitalTwin,
    ) -> ACWRADecision:
        """
        Runs the deterministic ACWRA decision pipeline.

        Args:
            snapshot: MultiAgentSnapshot evidence from MultiAgentOrchestrator.
            digital_twin: DigitalTwin instance for counterfactual sandbox simulation.

        Returns:
            ACWRADecision object containing selected strategy, utility scores, and decision trace.
        """
        # 1. Extract Candidate Strategies
        candidates = ["Keep Current"]
        if snapshot.defense_candidates is not None:
            candidates = snapshot.defense_candidates.candidate_strategies
        if not candidates:
            # used to surface as an IndexError on sorted_scores[0]
            raise ValueError("ACWRA: the defense message proposes no candidate strategies")

        # 2. Run Counterfactual Sandbox Simulation via Digital Twin
        cf_results = digital_twin.evaluate_counterfactuals(candidate_strategies=candidates)

        # 3. Extract Risk and Confidence Metrics
        risk_score = 0.0
        confidence = 1.0

        if snapshot.prediction_result is not None:
            risk_score = snapshot.prediction_result.risk_score

        if snapshot.spectrum_result is not None:
            confidence = snapshot.spectrum_result.classifier_confidence

        # Input validation only - the utility mathematics below is unchanged. A NaN
        # risk or confidence made every utility NaN, and the sort then silently
        # returned the first candidate; out-of-range values changed the winner
        # without complaint.
        for name, value in (("risk_score", risk_score), ("confidence", confidence)):
            if value is None or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"ACWRA: {name}={value} must be a finite number in [0, 1]")
        for r in cf_results:
            for key in ("predicted_ber", "predicted_throughput_bps"):
                if not math.isfinite(float(r[key])):
                    raise ValueError(f"ACWRA: counterfactual {r['strategy']!r} has {key}={r[key]}")

        # 4. Compute Utility Scores
        candidate_scores = self.scoring_engine.score_candidates(
            counterfactual_results=cf_results,
            risk_score=risk_score,
            confidence=confidence,
        )

        # 5. Deterministic Utility Selection (Highest Utility Winner)
        # Sort deterministically by utility descending, then strategy name ascending for tie-breaking
        sorted_scores = sorted(candidate_scores, key=lambda cs: (-cs.utility_score, cs.strategy))

        winning_score = sorted_scores[0]
        selected_strategy = winning_score.strategy
        winning_utility = winning_score.utility_score

        # 6. Format Explainability Trace
        trace_str = DecisionTrace.format_trace(
            timestamp_s=snapshot.timestamp_s,
            selected_strategy=selected_strategy,
            winning_utility=winning_utility,
            candidate_scores=candidate_scores,
            risk_score=risk_score,
            confidence=confidence,
        )

        return ACWRADecision(
            timestamp_s=snapshot.timestamp_s,
            selected_strategy=selected_strategy,
            expected_utility=winning_utility,
            candidate_scores=candidate_scores,
            risk_score=risk_score,
            agent_confidence=confidence,
            decision_trace=trace_str,
        )
