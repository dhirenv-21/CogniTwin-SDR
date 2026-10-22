# CogniTwin-SDR: Cognitive Digital Twin (CDT) Guide

This document provides coursework references and technical explanations mapping the Cognitive Digital Twin (CDT) architecture to Python implementation components in **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| Digital Twin Concept | Mathematical Model / Definition | Python Implementation File | Class / Function Name |
| :--- | :--- | :--- | :--- |
| **Digital Twin State Snapshot** | `@dataclass` storing mirror of environment metrics | [src/digital_twin/state.py](../src/digital_twin/state.py) | `DigitalTwinState` |
| **Chronological History Buffer** | Bounded FIFO queue (max 50 states) & rate of change | [src/digital_twin/history.py](../src/digital_twin/history.py) | `HistoryBuffer` |
| **Short-Horizon Trend Predictor** | Degree-1 linear extrapolation (`np.polyfit`) | [src/digital_twin/predictor.py](../src/digital_twin/predictor.py) | `TrendPredictor` |
| **Counterfactual Sandbox** | Stateless strategy evaluation via `VirtualRFEnvironment.simulate()` | [src/digital_twin/counterfactual.py](../src/digital_twin/counterfactual.py) | `CounterfactualSandbox` |
| **Experience Memory V1** | Past transition tuple storage & Euclidean similarity search | [src/digital_twin/experience.py](../src/digital_twin/experience.py) | `ExperienceMemory` |
| **Fidelity Evaluator** | Mean Absolute Error (MAE) comparing forecast vs actual | [src/digital_twin/fidelity.py](../src/digital_twin/fidelity.py) | `FidelityEvaluator` |
| **Main CDT Engine** | State update, cloning, prediction, sandbox orchestration | [src/digital_twin/twin.py](../src/digital_twin/twin.py) | `DigitalTwin` |

---

## 📖 Theoretical Principles

### 1. Counterfactual Sandbox Isolation

In autonomous cyber-defense, executing unverified adaptation strategies directly on an active radio link risks link dropouts or severe jamming. The Digital Twin provides a **Counterfactual Sandbox**:
$$\mathbf{S}_{hypothetical} = \text{Sandbox}.\text{simulate}(\mathbf{S}_{current}, \mathbf{a}_{candidate})$$
Because `simulate()` is purely functional and stateless, candidate strategies (BPSK, QPSK, OFDM-QPSK) are evaluated without advancing the real environment clock or altering physical link state.

### 2. Short-Horizon Trend Extrapolation

Using a sliding window of recent states ($N=5$), the trend predictor fits a first-degree polynomial to forecast near-future degradation:
$$\text{Metric}(t_{next}) = p_0 \cdot t_{next} + p_1$$
If history length $< 5$, the predictor returns `prediction_status = "INSUFFICIENT_HISTORY"`, ensuring robust behavior during startup transients.

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run unit test suite (Tasks 1-7)
pytest tests/test_digital_twin.py

# 2. Run Digital Twin tracking and trend prediction demo
python experiments/digital_twin_demo.py

# 3. Run counterfactual strategy evaluation demo
python experiments/counterfactual_demo.py
```
Output plots will be saved to `results/digital_twin/prediction_vs_actual.png` and `results/digital_twin/counterfactual_comparison.png`.
