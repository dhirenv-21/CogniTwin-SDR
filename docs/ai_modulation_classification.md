# CogniTwin-SDR: AI Radio Signal / Modulation Classification Guide

This document provides coursework references and technical explanations mapping AI/ML radio modulation classification concepts to the Python implementation within **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| AI / ML Concept | Mathematical Model / Definition | Python Implementation File | Function / Class Name |
| :--- | :--- | :--- | :--- |
| **I/Q Feature Extraction** | Vectorized time-domain & spectral features | [src/ai/modulation_classifier/features.py](../src/ai/modulation_classifier/features.py) | `extract_features` |
| **Synthetic Dataset Generation** | 8 classes across 5 SNR levels ($0 \dots 20 \text{ dB}$) | [src/ai/modulation_classifier/dataset.py](../src/ai/modulation_classifier/dataset.py) | `generate_dataset` |
| **Train/Val/Test Splitting** | Independent 70% / 15% / 15% stratified split | [src/ai/modulation_classifier/dataset.py](../src/ai/modulation_classifier/dataset.py) | `get_train_val_test_splits` |
| **Random Forest Model** | Ensemble Decision Trees & Serialization | [src/ai/modulation_classifier/model.py](../src/ai/modulation_classifier/model.py) | `train_classifier`, `save_model` |
| **Model Evaluation** | Confusion Matrix, Macro F1, Accuracy vs. SNR | [src/ai/modulation_classifier/evaluation.py](../src/ai/modulation_classifier/evaluation.py) | `evaluate_model` |
| **Spectrum Intelligence Inference** | `predict_proba()` + Confidence Threshold ($<0.60 \rightarrow \text{UNKNOWN}$) | [src/ai/modulation_classifier/inference.py](../src/ai/modulation_classifier/inference.py) | `analyze_iq` |

---

## 📖 Theoretical Principles

### 1. Feature Engineering for Radio Modulation Classification

Rather than passing raw I/Q samples directly into complex deep neural networks, domain-specific feature engineering extracts discriminative statistical and spectral metrics:
- **Amplitude Statistics**: $\mu_A, \sigma_A$, Skewness, Kurtosis discriminate constant-envelope modulations (BPSK, QPSK, FM) from amplitude-varying modulations (AM, ASK, 8-PSK).
- **Phase Statistics**: $\mu_\phi, \sigma_\phi$ discriminate phase-modulated schemes from frequency or amplitude schemes.
- **I/Q Correlation**: Captures phase coupling between in-phase and quadrature branches.
- **Spectral Flatness & Entropy**: Measure energy distribution uniformity across subcarriers, distinguishing single-carrier signals from wideband OFDM multicarrier signals.

### 2. Confidence Thresholding ($P_{conf} < 0.60 \rightarrow \text{"UNKNOWN"}$)

In autonomous cognitive digital twin systems, downstream decision agents must avoid hallucinating signal types on extremely noisy or out-of-distribution inputs. The `analyze_iq` function extracts prediction probabilities $P(C_k | \mathbf{x})$:
$$\text{Class} = \begin{cases} \arg\max_{k} P(C_k | \mathbf{x}), & \text{if } \max_{k} P(C_k | \mathbf{x}) \ge 0.60 \\ \text{"UNKNOWN"}, & \text{otherwise} \end{cases}$$

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run all unit tests (Tasks 1, 2, 3, 4, and 5)
pytest

# 2. Run AI Modulation Classifier training, evaluation, and live inference demo
python experiments/modulation_classifier_demo.py
```
Output models and diagnostic plots will be saved to `results/ai/modulation_classifier/`.
