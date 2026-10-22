# CogniTwin-SDR: ACWRA (Adaptive Cognitive Wireless Reasoning Algorithm) Guide

This document provides coursework documentation for the **Adaptive Cognitive Wireless Reasoning Algorithm (ACWRA)** in **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| ACWRA Concept | Theoretical / Mathematical Model | Python Implementation File | Class / Function Name |
| :--- | :--- | :--- | :--- |
| **Candidate Decision Object** | Output decision object with utility scores & trace | [src/acwra/decision.py](../src/acwra/decision.py) | `ACWRADecision`, `CandidateScore` |
| **Explainability Trace** | Human-readable decision trace logger | [src/acwra/trace.py](../src/acwra/trace.py) | `DecisionTrace` |
| **Multi-Objective Utility Engine** | Normalization safeguards, SE derivation & utility math | [src/acwra/scoring.py](../src/acwra/scoring.py) | `ACWRAScoringEngine` |
| **ACWRA Decision Engine** | Main deterministic decision loop & candidate selection | [src/acwra/engine.py](../src/acwra/engine.py) | `ACWRAEngine` |

---

## 📖 Mathematical Formulation

### 1. Multi-Objective Utility Function
For each candidate strategy $c$, ACWRA calculates a multi-objective utility score $U(c)$:
$$U(c) = \left[ C \cdot (w_t \cdot T_{norm} + w_{se} \cdot SE_{norm}) \right] - \left[ (1 + R) \cdot w_b \cdot BER_{norm} \right] - \left[ \lambda_c \cdot (1 - C) \cdot K_c \right]$$

#### Parameters & Weights
- $w_t = 0.4$: Throughput weight
- $w_{se} = 0.2$: Spectral efficiency weight
- $w_b = 0.6$: Bit Error Rate (BER) penalty weight
- $\lambda_c = 1.0$: Confidence penalty scaling factor
- $R \in [0.0, 1.0]$: Future Risk Score (from Prediction Agent)
- $C \in [0.0, 1.0]$: Overall Agent Confidence (from Spectrum Agent)

### 2. Min-Max Normalization Safeguard (ZeroDivisionError Prevention)
For metric array $V \in \{T, BER, SE\}$:
$$\text{If } \max(V) == \min(V): \quad V_{norm}[i] = 0.0 \quad \forall i$$
$$\text{Else: } \quad V_{norm}[i] = \frac{V[i] - \min(V)}{\max(V) - \min(V)}$$

### 3. Theoretical Spectral Efficiency & Waveform Complexity Priors
- **Theoretical Spectral Efficiency ($SE_{theoretical}$)**:
  - BPSK = $1.0$ bits/symbol
  - QPSK / Keep Current = $2.0$ bits/symbol
  - OFDM-QPSK = $2.0 \times \frac{N_{fft}}{N_{fft} + CP} = 2.0 \times \frac{64}{80} = 1.6$ bits/symbol (CP overhead accounted for).
- **Waveform Complexity Prior ($K_c$)**:
  - BPSK = $0.0$, QPSK = $0.25$, OFDM-QPSK = $0.50$.

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run unit test suite (Tasks 1-9)
pytest tests/test_acwra.py

# 2. Run ACWRA decision dashboard demo
python experiments/acwra_demo.py
```
Output plot will be saved to `results/acwra/acwra_utility_breakdown.png`.

---

## 📐 Specification of the implementation (audited 2026-10-22)

This section describes what `src/acwra/` computes. The equations, weights and
normalisation above are unchanged; this text only states their meaning precisely.

### Inputs and their sources

| symbol | meaning | unit / range | source |
|---|---|---|---|
| candidate set | strategies to score | `Keep Current`, `BPSK`, `QPSK`, `OFDM-QPSK` | `CyberDefenseAgent`: risk LOW + no anomaly → `[Keep Current]`; MEDIUM + no anomaly → `[Keep Current, QPSK]`; otherwise all four |
| `T` | predicted goodput of the candidate | b/s | `DigitalTwin.evaluate_counterfactuals` → `VirtualRFEnvironment.simulate` → `src/virtual_rf/link_model.py` (expected over the fading distribution) |
| `BER` | predicted bit error rate | [0, 0.5] | same sandbox |
| `SE` | theoretical spectral efficiency | b/symbol | table above (no channel dependence) |
| `K_c` | complexity prior | {0, 0.25, 0.5} | table above |
| `R` | risk score | [0, 1], validated | `PredictionAgent` (0.5·BER term + 0.3·SNR term + 0.2·interference term of the twin's 1-step forecast; 0 with insufficient history) |
| `C` | classifier confidence | [0, 1], validated | `SpectrumAgent` (max class probability of the modulation classifier) |

"Keep Current" is scored as the Digital Twin's current modulation. That is the
classifier's label when it is not `UNKNOWN`, so a misclassification changes what
"Keep Current" means (see the classifier evaluation).

### Normalisation is relative to each decision's candidate set

`T_norm`, `BER_norm` and `SE_norm` are min-max normalised **over the candidates being
compared in that decision**. Consequences:
* utilities are only comparable **within** one decision, not across decisions;
* with a single candidate, or when all candidates have equal T / BER / SE, the normalised
  terms are 0 and only the complexity term remains;
* how much BER and throughput differ in absolute terms does not enter the utility, only
  their rank and relative spacing.

### Selection rule

`selected = argmax U(c)`. Ties are broken by **strategy name ascending**
(`BPSK` < `Keep Current` < `OFDM-QPSK` < `QPSK`). "Keep Current" and the candidate naming
the current modulation always tie exactly (identical counterfactuals). On a BPSK link the
reported strategy is then `BPSK`; on a QPSK link it is `Keep Current`. Either way the
**effective** modulation does not change. Switch counts must therefore use the effective
modulation (`CandidateScore.modulation`), as `experiments/closed_loop_evaluation.py` does.
There is **no switching cost** in U(c).

### Input validation (added 2026-10-22; equations unchanged)

`ACWRAEngine.evaluate_and_decide` raises `ValueError` if `R` or `C` is non-finite or
outside [0, 1], if a counterfactual BER or goodput is non-finite, or if no candidate is
proposed. Previously NaN made every utility NaN and the first candidate was silently
chosen, and an empty list raised `IndexError`.

### Worked example (pinned by `tests/test_acwra_validation.py::test_utility_matches_a_hand_calculation`)

Candidates A = QPSK (200 kb/s, BER 0.01), B = BPSK (100 kb/s, BER 0.001), O = OFDM-QPSK
(150 kb/s, BER 0.0055); R = 0.5, C = 0.8:

| | T_norm | BER_norm | SE_norm | K_c | U |
|---|---|---|---|---|---|
| A | 1 | 1 | 1 | 0.25 | 0.8·0.6 − 1.5·0.6·1 − 0.2·0.25 = **−0.47** |
| B | 0 | 0 | 0 | 0 | **0** |
| O | 0.5 | 0.5 | 0.6 | 0.5 | 0.8·0.32 − 1.5·0.6·0.5 − 0.2·0.5 = **−0.294** |

B is selected. Because w_b(1+R) ≥ w_t + w_se = 0.6 for every R ≥ 0 and C ≤ 1, the
lowest-BER candidate never loses to one that is best on every reward term but worst on
BER (they tie only at R = 0, C = 1, when the complexity term also vanishes). The objective
is BER-averse by construction, which explains why ACWRA trades goodput for BER in the
closed-loop evaluations.
