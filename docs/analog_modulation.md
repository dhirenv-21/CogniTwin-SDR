# CogniTwin-SDR: Analog Modulation & Demodulation Coursework Guide

This document provides a comprehensive theoretical and practical coursework reference mapping analog communication concepts to the Python implementation within **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| Communication Concept | Mathematical Model / Definition | Python Implementation File | Class / Function Name |
| :--- | :--- | :--- | :--- |
| **Baseband Signal Generation** | $m(t) = A_m \cos(2\pi f_m t)$ | [src/signal/generator.py](../src/signal/generator.py) | `generate_sinusoid` |
| **Analytic Signal (Hilbert)** | $x_a(t) = x(t) + j \mathcal{H}\{x(t)\}$ | [src/signal/generator.py](../src/signal/generator.py) | `to_iq` |
| **AWGN Channel Modeling** | $r(t) = s(t) + n(t), \quad \text{SNR}_{dB}$ | [src/channel/awgn.py](../src/channel/awgn.py) | `AWGNChannel.transmit` |
| **AM DSB-SC** | $s(t) = m(t) \cos(2\pi f_c t)$ | [src/modulation/analog/am.py](../src/modulation/analog/am.py) | `AMDSBSCModulator` |
| **AM DSB-TC** | $s(t) = A_c [1 + \mu m_n(t)] \cos(2\pi f_c t)$ | [src/modulation/analog/am.py](../src/modulation/analog/am.py) | `AMDSTCModulator` |
| **SSB (USB / LSB)** | $s(t) = m(t)\cos(2\pi f_c t) \mp \hat{m}(t)\sin(2\pi f_c t)$ | [src/modulation/analog/ssb.py](../src/modulation/analog/ssb.py) | `SSBModulator` |
| **Narrowband FM (NBFM)** | $s(t) = A_c \cos(2\pi f_c t + 2\pi k_f \int m dt), \, \beta \ll 1$ | [src/modulation/analog/fm.py](../src/modulation/analog/fm.py) | `FMModulator` |
| **Wideband FM (WBFM)** | $s(t) = A_c \cos(2\pi f_c t + 2\pi k_f \int m dt), \, \beta \ge 1$ | [src/modulation/analog/fm.py](../src/modulation/analog/fm.py) | `FMModulator` |
| **Phase Modulation (PM)** | $s(t) = A_c \cos(2\pi f_c t + k_p m(t))$ | [src/modulation/analog/pm.py](../src/modulation/analog/pm.py) | `PMModulator` |
| **FIR Low-Pass Filtering** | $H(f) \text{ zero-phase FIR LPF}$ | [src/signal/filters.py](../src/signal/filters.py) | `design_fir_lowpass`, `apply_filter` |
| **Reconstruction Metrics** | $\text{Pearson } r, \text{ MSE}, \text{ NRE}$ | [src/evaluation/metrics.py](../src/evaluation/metrics.py) | `pearson_correlation`, `mean_squared_error` |

---

## 📖 Theoretical Fundamentals & Implementation Details

### 1. Amplitude Modulation (AM)

- **DSB-SC**: Double Sideband Suppressed Carrier suppresses the carrier component to maximize power efficiency. Demodulation requires coherent detection: multiplying $s(t)$ by $\cos(2\pi f_c t)$ yields $\frac{1}{2} m(t) + \frac{1}{2} m(t)\cos(4\pi f_c t)$. Low-pass filtering eliminates the $2f_c$ high-frequency term.
- **DSB-TC**: Transmitted Carrier adds a carrier offset $A_c$ to enable non-coherent envelope detection. The envelope $e(t) = |s(t) + j \mathcal{H}\{s(t)\}|$ is extracted via Hilbert analytic representation, followed by DC offset subtraction.

### 2. Single Sideband (SSB)

SSB eliminates one sideband to conserve 50% bandwidth ($B_{SSB} = W$ vs $B_{DSB} = 2W$). It uses the phase discrimination method via Hilbert transform $\hat{m}(t) = \mathcal{H}\{m(t)\}$:
- **Upper Sideband (USB)**: $s_{USB}(t) = m(t)\cos(2\pi f_c t) - \hat{m}(t)\sin(2\pi f_c t)$
- **Lower Sideband (LSB)**: $s_{LSB}(t) = m(t)\cos(2\pi f_c t) + \hat{m}(t)\sin(2\pi f_c t)$

### 3. Angle Modulation: Frequency Modulation (FM) & Phase Modulation (PM)

- **FM**: Instantaneous frequency varies linearly with message $f(t) = f_c + k_f m(t)$. The phase is the time integral of frequency.
  - **Carson's Rule**: Bandwidth $B_{FM} = 2(\Delta f + f_m) = 2 f_m (\beta + 1)$.
  - **NBFM**: $\beta = \frac{\Delta f}{f_m} \ll 1$, occupying $B \approx 2 f_m$.
  - **WBFM**: $\beta \ge 1$, occupying significantly wider bandwidth $B \approx 2 \Delta f$.
  - **Demodulation**: Converting passband to baseband analytic representation $y(t) = x_a(t) e^{-j 2\pi f_c t}$, extracting wrapped phase $\theta(t) = \text{angle}(y(t))$, unwrapping phase jumps via `np.unwrap`, and computing the time derivative $\frac{d\theta}{dt}$ yields $2\pi k_f m(t)$.

- **PM**: Instantaneous phase varies linearly with message $\phi(t) = 2\pi f_c t + k_p m(t)$. Demodulation extracts baseband phase angle, applies mandatory phase unwrapping (`np.unwrap`), and scales by $\frac{1}{k_p}$.

---

## 🏃 Instructions to Run Tests and Demo

```bash
# 1. Run all unit tests (Task 1 + Task 2)
pytest

# 2. Run Task 2 Analog Communication Laboratory Demo
python experiments/analog_modulation_demo.py
```
Output plots will be generated in `results/analog/`.
