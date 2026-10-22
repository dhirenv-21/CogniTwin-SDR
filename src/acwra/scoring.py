"""
ACWRA Multi-Objective Scoring Engine.

Implements mathematical utility scoring with zero-division safeguards, theoretical spectral efficiency derivation,
and complexity priors.
"""

from typing import Dict, List, Any
import numpy as np

from .decision import CandidateScore


class ACWRAScoringEngine:
    """
    Deterministic scoring engine computing multi-objective utility for candidate strategies.
    """

    def __init__(
        self,
        weight_throughput: float = 0.4,
        weight_se: float = 0.2,
        weight_ber: float = 0.6,
        lambda_complexity: float = 1.0,
    ):
        self.w_t = weight_throughput
        self.w_se = weight_se
        self.w_b = weight_ber
        self.lambda_c = lambda_complexity

    @staticmethod
    def get_theoretical_spectral_efficiency(modulation: str) -> float:
        """
        Derives theoretical spectral efficiency (bits/symbol/Hz).

        Note: Clearly labeled as theoretical spectral efficiency, distinct from measured channel throughput.
        OFDM-QPSK accounts for CP overhead (n_fft=64, cp_len=16 -> 64/80 = 0.8 efficiency factor).
        """
        mod_upper = modulation.upper()
        if "OFDM" in mod_upper:
            # 64 subcarriers / (64 + 16 CP) = 0.8 overhead factor
            cp_efficiency = 64.0 / (64.0 + 16.0)
            return 2.0 * cp_efficiency  # 1.6 bits/symbol
        elif "BPSK" in mod_upper:
            return 1.0
        elif "QPSK" in mod_upper:
            return 2.0
        elif "16" in mod_upper or "QAM" in mod_upper:
            return 4.0
        else:
            return 2.0  # Default QPSK equivalent

    @staticmethod
    def get_complexity_prior(modulation: str) -> float:
        """
        Returns deterministic waveform complexity prior K_c.
        BPSK = 0.0, QPSK = 0.25, OFDM-QPSK = 0.50.
        """
        mod_upper = modulation.upper()
        if "OFDM" in mod_upper:
            return 0.50
        elif "BPSK" in mod_upper:
            return 0.0
        elif "QPSK" in mod_upper:
            return 0.25
        else:
            return 0.25

    @staticmethod
    def min_max_normalize(values: np.ndarray) -> np.ndarray:
        """
        Applies min-max normalization with ZERO-DIVISION SAFEGUARD.

        If max(values) == min(values), sets normalized values to 0.0 for all candidates.
        """
        v_min = float(np.min(values))
        v_max = float(np.max(values))

        if np.isclose(v_max, v_min):
            return np.zeros_like(values, dtype=np.float64)

        return (values - v_min) / (v_max - v_min)

    def score_candidates(
        self,
        counterfactual_results: List[Dict[str, Any]],
        risk_score: float,
        confidence: float,
    ) -> List[CandidateScore]:
        """
        Evaluates multi-objective utility for a list of candidate strategy counterfactual results.

        Args:
            counterfactual_results: Output dict list from DigitalTwin.simulate_counterfactuals().
            risk_score: Future risk score R from PredictionAgent (0.0 to 1.0).
            confidence: Overall agent confidence C (0.0 to 1.0).

        Returns:
            List of CandidateScore instances.
        """
        n_candidates = len(counterfactual_results)
        if n_candidates == 0:
            return []

        raw_tputs = np.array([r["predicted_throughput_bps"] for r in counterfactual_results], dtype=np.float64)
        raw_bers = np.array([r["predicted_ber"] for r in counterfactual_results], dtype=np.float64)

        # Theoretical spectral efficiency array
        raw_ses = np.array(
            [self.get_theoretical_spectral_efficiency(r["modulation"]) for r in counterfactual_results],
            dtype=np.float64,
        )

        # Apply Min-Max Normalization with Safeguard
        t_norm = self.min_max_normalize(raw_tputs)
        ber_norm = self.min_max_normalize(raw_bers)
        se_norm = self.min_max_normalize(raw_ses)

        scores = []
        for i, r in enumerate(counterfactual_results):
            strat = r["strategy"]
            mod = r["modulation"]
            ber = r["predicted_ber"]
            tput = r["predicted_throughput_bps"]
            se = raw_ses[i]

            k_c = self.get_complexity_prior(mod)

            # Multi-Objective Utility Formula
            # U(c) = [C * (w_t * T_norm + w_se * SE_norm)] - [(1 + R) * w_b * BER_norm] - [lambda_c * (1 - C) * K_c]
            t_term = confidence * (self.w_t * t_norm[i] + self.w_se * se_norm[i])
            b_term = (1.0 + risk_score) * self.w_b * ber_norm[i]
            c_term = self.lambda_c * (1.0 - confidence) * k_c

            utility = float(t_term - b_term - c_term)

            scores.append(
                CandidateScore(
                    strategy=strat,
                    modulation=mod,
                    predicted_ber=float(ber),
                    predicted_throughput_bps=float(tput),
                    theoretical_se=float(se),
                    utility_score=utility,
                    t_norm=float(t_norm[i]),
                    ber_norm=float(ber_norm[i]),
                    se_norm=float(se_norm[i]),
                    complexity_prior=k_c,
                )
            )

        return scores
