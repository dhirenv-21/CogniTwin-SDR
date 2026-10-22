# CogniTwin-SDR: Software-Only Virtual RF Environment Guide

This document provides technical documentation mapping the discrete-time Virtual RF Environment architecture to Python implementation components in **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| Environment Concept | Mathematical Model / Definition | Python Implementation File | Class / Function Name |
| :--- | :--- | :--- | :--- |
| **Environment State Snapshot** | Dataclass representing physical & network state | [src/virtual_rf/state.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/virtual_rf/state.py) | `EnvironmentState` |
| **Discrete-Time State Machine** | Block-based time advancement via `step(duration_seconds)` | [src/virtual_rf/environment.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/virtual_rf/environment.py) | `VirtualRFEnvironment` |
| **Observation APIs** | `observe_iq()`, `observe_state()` | [src/virtual_rf/environment.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/virtual_rf/environment.py) | `observe_iq`, `observe_state` |
| **Counterfactual Simulation** | Pure state prediction API `simulate(state, strategy)` | [src/virtual_rf/environment.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/virtual_rf/environment.py) | `simulate` |
| **Interference / Jamming** | Narrowband tone, Broadband noise, Swept chirp jamming | [src/virtual_rf/interference.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/virtual_rf/interference.py) | `InterferenceGenerator` |
| **Time-Varying Scenario Engine** | JSON keyframe loader and evaluator | [src/virtual_rf/scenario.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/virtual_rf/scenario.py) | `ScenarioEngine` |

---

## 📖 Key Architecture Principles

### 1. Discrete-Time State Machine (No Threading / Async Loops)
To ensure deterministic execution and fast reproducible simulation without multi-threading race conditions or infinite real-time loops:
- Time advances **only** when `step(duration_seconds)` is explicitly invoked.
- Each `step` invocation calculates the precise number of I/Q samples: $N = \lfloor \Delta t \times f_s \rfloor$.
- Samples are pushed to the observation buffer `observe_iq()`.

### 2. Counterfactual Simulation API (`simulate`)
For autonomous Cognitive Digital Twins, candidate communication strategies (e.g. changing modulation from QPSK to BPSK or increasing transmit power) must be evaluated *hypothetically* before executing real-world adaptation:
$$\text{State}_{predicted} = \text{simulate}(\text{State}_{current}, \text{Strategy}_{candidate})$$
This operation is pure, deterministic, and does not alter environment time or internal state.

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run unit test suite (Tasks 1-6)
pytest tests/test_virtual_rf.py

# 2. Run end-to-end Virtual RF & ML classifier integration demo
python experiments/virtual_rf_demo.py

# 3. Run time-varying scenario transition demo
python experiments/scenario_transition_demo.py
```
Output plots will be saved to `results/virtual_rf/scenario_transition.png`.
