# CogniTwin-SDR: Multi-Agent Cognitive Wireless Intelligence Layer Guide

This document details the multi-agent cognitive intelligence architecture in **CogniTwin-SDR**, mapping agent roles to Python implementation components.

---

## 📌 Concept to Python Implementation Mapping

| Multi-Agent Concept | Functional Role / Responsibility | Python Implementation File | Class Name |
| :--- | :--- | :--- | :--- |
| **Inter-Agent Messages** | Structured evidence data containers | [src/agents/messages.py](../src/agents/messages.py) | `SpectrumIntelligenceResult`, `PredictionResult`, `DefenseCandidate`, `MultiAgentSnapshot` |
| **Base Agent Layer** | Shared abstract interface, confidence & status tracking | [src/agents/base_agent.py](../src/agents/base_agent.py) | `BaseAgent` |
| **Spectrum Intelligence Agent** | I/Q analysis via ML classifier & anomaly detection | [src/agents/spectrum_agent.py](../src/agents/spectrum_agent.py) | `SpectrumAgent` |
| **Prediction Agent** | DT trend querying & mathematical risk scoring | [src/agents/prediction_agent.py](../src/agents/prediction_agent.py) | `PredictionAgent` |
| **Cyber Defense Agent** | Candidate mitigation strategy generation | [src/agents/cyber_defense_agent.py](../src/agents/cyber_defense_agent.py) | `CyberDefenseAgent` |
| **Multi-Agent Orchestrator** | 6-step sequential pipeline execution & snapshotting | [src/agents/orchestrator.py](../src/agents/orchestrator.py) | `MultiAgentOrchestrator` |

---

## 📖 Key Architecture Principles

### 1. Separation of Intelligence from Action
Agents produce structured observations, trend predictions, risk scores, and candidate mitigation strategies, but do **NOT** execute adaptation decisions on the radio environment. (Decision logic is reserved for the ACWRA engine in Task 9).

### 2. Mathematical Risk Scoring Model
The Prediction Agent maps short-horizon forecast metrics into a bounded risk score $R \in [0.0, 1.0]$:
$$R = \text{clip}\left( 0.5 \cdot \frac{\text{BER}_{next}}{0.1} + 0.3 \cdot \frac{20 - \text{SNR}_{next}}{20} + 0.2 \cdot \frac{P_{interf}}{2.0}, \, 0.0, \, 1.0 \right)$$
- $R < 0.25 \rightarrow \mathbf{LOW}$
- $0.25 \le R < 0.50 \rightarrow \mathbf{MEDIUM}$
- $0.50 \le R < 0.75 \rightarrow \mathbf{HIGH}$
- $R \ge 0.75 \rightarrow \mathbf{CRITICAL}$

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run unit test suite (Tasks 1-8)
pytest tests/test_agents.py

# 2. Run multi-agent intelligence layer demo
python experiments/multi_agent_demo.py
```
Output plots will be saved to `results/agents/agent_risk_timeline.png` and `results/agents/agent_confidence_timeline.png`.
