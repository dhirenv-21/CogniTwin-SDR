# CogniTwin-SDR: Digital Carrier Modulation & BER Analysis Guide

This document maps syllabus digital communication concepts to the Python implementation within **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| Digital Communication Concept | Mathematical Model / Definition | Python Implementation File | Class / Function Name |
| :--- | :--- | :--- | :--- |
| **Bit Generation & BER** | $\text{BER} = \frac{\sum (b_{tx} \neq b_{rx})}{N_{bits}}$ | [src/modulation/digital/common.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/common.py) | `generate_bits`, `calculate_ber` |
| **Gray Coding & Mapping** | $g = b \oplus (b \gg 1)$ | [src/modulation/digital/common.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/common.py) | `binary_to_gray`, `gray_to_binary` |
| **Amplitude Shift Keying (ASK)** | $s(t) = A_k \cos(2\pi f_c t), A_k \in \{0, 1\}$ | [src/modulation/digital/ask.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/ask.py) | `ASKModulator` |
| **Frequency Shift Keying (FSK)** | $s(t) = \cos(2\pi f_k t), f_k \in \{f_0, f_1\}$ | [src/modulation/digital/fsk.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/fsk.py) | `FSKModulator` |
| **Binary Phase Shift Keying (BPSK)** | $s(t) = \pm \cos(2\pi f_c t), \phi \in \{0, \pi\}$ | [src/modulation/digital/psk.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/psk.py) | `PSKModulator(M=2)` |
| **Quadrature PSK (QPSK)** | $s(t) = I_k \cos(2\pi f_c t) - Q_k \sin(2\pi f_c t)$ | [src/modulation/digital/psk.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/psk.py) | `PSKModulator(M=4)` |
| **M-ary PSK (8-PSK, 16-PSK)** | $S_m = e^{j(2\pi m / M)}, m=0\dots M-1$ | [src/modulation/digital/psk.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/psk.py) | `PSKModulator(M=8, 16)` |
| **Research Strategy Simulation API** | $\text{Returns } \{\text{ber}, \eta, \dots\}$ | [src/modulation/digital/common.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/modulation/digital/common.py) | `simulate_strategy` |

---

## 📖 Theoretical Principles & Performance Metrics

### 1. Complex Baseband vs. Passband Simulation

- **Passband Simulation**: Upconverts I/Q symbols to carrier frequency $f_c$ using $s(t) = I(t)\cos(2\pi f_c t) - Q(t)\sin(2\pi f_c t)$. Excellent for time-domain waveform visualization, but requires high sampling rates $f_s \gg f_c$ and large memory arrays.
- **Complex Baseband Simulation**: Directly models complex symbols $S_k = I_k + j Q_k$ and adds complex AWGN noise $N \sim \mathcal{CN}(0, \sigma^2)$. Allows simulating $100,000+$ bits in fractions of a second for Monte Carlo BER vs. SNR evaluation.

### 2. Spectral Efficiency ($\eta$)

Spectral efficiency measures data rate per unit bandwidth ($\text{bits/sec/Hz}$):
- **BPSK / 2-ASK / 2-FSK**: $\eta = 1 \text{ bit/sec/Hz}$ ($k = 1$ bit/symbol).
- **QPSK**: $\eta = 2 \text{ bits/sec/Hz}$ ($k = 2$ bits/symbol).
- **8-PSK**: $\eta = 3 \text{ bits/sec/Hz}$ ($k = 3$ bits/symbol).
- **16-PSK**: $\eta = 4 \text{ bits/sec/Hz}$ ($k = 4$ bits/symbol).

### 3. Gray Coding

To minimize bit error probability under symbol detection errors, Gray coding ensures adjacent constellation points differ by exactly 1 bit. If a noise spike causes a symbol decision error to an adjacent point, only 1 bit is flipped out of $k$ bits.

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run all unit tests (Task 1 + Task 2 + Task 3)
pytest

# 2. Run fast BER vs SNR performance experiment
python experiments/ber_vs_snr.py

# 3. Run digital modulation waveform and constellation demo
python experiments/digital_modulation_demo.py
```
Output plots will be saved to `results/digital/`.
