"""
ACWRA Decision Trace & Explainability Module.

Generates human-readable explainability logs detailing utility scoring, risk penalties,
agent confidence factors, complexity priors, and strategy selection rationale.
"""

from typing import List
from .decision import CandidateScore


class DecisionTrace:
    """
    Explainability logger formatting human-readable decision traces.
    """

    @staticmethod
    def format_trace(
        timestamp_s: float,
        selected_strategy: str,
        winning_utility: float,
        candidate_scores: List[CandidateScore],
        risk_score: float,
        confidence: float,
    ) -> str:
        """
        Formats a detailed, human-readable explainability trace string.
        """
        lines = []
        lines.append(f"ACWRA DECISION TRACE (t = {timestamp_s:.2f} s)")
        lines.append("=" * 75)
        lines.append(f"• Selected Strategy : '{selected_strategy}' (Expected Utility: {winning_utility:+.4f})")
        lines.append(f"• Agent Evidence    : Risk Score R = {risk_score:.2f} | Confidence C = {confidence * 100:.1f}%\n")
        lines.append("• Candidate Utility Scoring Breakdown:")
        lines.append("-" * 75)
        lines.append(f" {'STRATEGY':<20} | {'PRED BER':<10} | {'T_NORM':<8} | {'SE_NORM':<8} | {'K_C':<6} | {'UTILITY':<10}")
        lines.append("-" * 75)

        for cs in candidate_scores:
            prefix = "==>" if cs.strategy == selected_strategy else "   "
            line = (
                f"{prefix} {cs.strategy:<17} | {cs.predicted_ber:<10.4f} | {cs.t_norm:<8.2f} | "
                f"{cs.se_norm:<8.2f} | {cs.complexity_prior:<6.2f} | {cs.utility_score:<+10.4f}"
            )
            lines.append(line)

        lines.append("-" * 75)
        lines.append("• Rationale & Penalty Analysis:")

        # Find min BER among candidates
        min_ber = min(cs.predicted_ber for cs in candidate_scores) if candidate_scores else 0.0
        winning_cs = next((cs for cs in candidate_scores if cs.strategy == selected_strategy), None)

        for cs in candidate_scores:
            if cs.strategy == selected_strategy:
                if confidence < 0.70:
                    lines.append(f"  - Winner '{cs.strategy}': Selected under low agent confidence (C = {confidence*100:.1f}%); waveform complexity penalty K_c penalized higher-order options in favor of robust baseline.")
                elif winning_cs and np_isclose(winning_cs.predicted_ber, min_ber) and winning_cs.theoretical_se > 1.0:
                    lines.append(f"  - Winner '{cs.strategy}': Matched the minimum predicted BER while providing higher theoretical spectral efficiency.")
                else:
                    lines.append(f"  - Winner '{cs.strategy}': Achieves optimal balance of throughput, BER robustness, and spectral efficiency.")
            else:
                penalties = []
                if confidence < 0.70 and cs.complexity_prior > 0.0:
                    penalties.append(f"Waveform complexity penalty K_c ({cs.complexity_prior:.2f}) active under low confidence (C={confidence*100:.1f}%)")
                if cs.ber_norm > 0.0 and risk_score > 0.5:
                    penalties.append(f"BER penalty under elevated risk (R={risk_score:.2f})")
                if cs.t_norm == 0.0 and cs.ber_norm == 1.0:
                    penalties.append("High BER causing packet loss")

                pen_str = "; ".join(penalties) if penalties else "Lower utility balance"
                lines.append(f"  - Rejected '{cs.strategy}': {pen_str} (Utility: {cs.utility_score:+.4f})")

        return "\n".join(lines)


def np_isclose(a: float, b: float, atol: float = 1e-5) -> bool:
    return abs(a - b) <= atol
