# CogniTwin-SDR: OFDM & 2×2 MIMO Communication Guide

This document provides coursework references and technical explanations mapping multicarrier OFDM and 2×2 MIMO communication concepts to the Python implementation within **CogniTwin-SDR**.

---

## 📌 Concept to Python Implementation Mapping

| Communication Concept | Mathematical Model / Definition | Python Implementation File | Class / Function Name |
| :--- | :--- | :--- | :--- |
| **OFDM Subcarrier Modulation** | $x[n] = \frac{1}{\sqrt{N}} \sum_{k=0}^{N-1} X[k] e^{j 2\pi k n / N}$ | [src/multicarrier/ofdm.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/ofdm.py) | `OFDMTransmitterReceiver` |
| **Cyclic Prefix Insertion** | $x_{cp} = [x[N-N_{cp}:], x]$ | [src/multicarrier/ofdm.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/ofdm.py) | `modulate` |
| **Multipath Fading Channel** | $h[n] = \sum_{l=0}^{L-1} a_l \delta[n - \tau_l]$ | [src/multicarrier/channel.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/channel.py) | `MultipathChannel` |
| **1-Tap Frequency Equalization** | $\hat{X}[k] = \frac{Y[k]}{H[k]}$ | [src/multicarrier/ofdm.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/ofdm.py) | `demodulate` |
| **2×2 Spatial Multiplexing** | $\mathbf{y}(t) = \mathbf{H} \mathbf{x}(t) + \mathbf{n}(t)$ | [src/multicarrier/mimo.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/mimo.py) | `MIMO2x2System` |
| **Per-Subcarrier ZF Equalization** | $\mathbf{W}_{ZF}[k] = \mathbf{H}[k]^{-1}$ | [src/multicarrier/mimo.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/mimo.py) | `transmit_and_equalize` |
| **Multicarrier Strategy API** | Returns $\{\text{ber}, \text{throughput}, \eta\}$ | [src/multicarrier/common.py](file:///c:/Users/HP/Desktop/AMRITA/SEM-3/PROJECTS/SDC/cognitwin-sdr/src/multicarrier/common.py) | `simulate_ofdm_mimo` |

---

## 📖 Theoretical Principles

### 1. Orthogonal Frequency Division Multiplexing (OFDM)

OFDM converts a frequency-selective fading wideband channel into $N$ flat-fading narrowband subchannels using Inverse Fast Fourier Transform (IFFT) at the transmitter and FFT at the receiver.

- **Cyclic Prefix (CP)**: By copying the last $N_{cp}$ samples of an IFFT symbol to its beginning, CP converts linear convolution with the channel impulse response into circular convolution. This eliminates Inter-Symbol Interference (ISI) provided $N_{cp} \ge L_{channel}$, and allows 1-tap frequency-domain equalization per subcarrier ($\hat{X}[k] = Y[k] / H[k]$).

### 2. 2×2 MIMO Spatial Multiplexing & Zero-Forcing (ZF) Equalization

2×2 MIMO uses 2 transmit antennas and 2 receive antennas to transmit two parallel data streams simultaneously over the same frequency band, doubling the spectral efficiency ($\eta_{MIMO} = 2 \times \eta_{single}$).

- **Per-Subcarrier Channel Matrix**: For each subcarrier $k$, the channel is represented by a $2 \times 2$ complex matrix:
  $$\mathbf{H}[k] = \begin{bmatrix} H_{11}[k] & H_{12}[k] \\ H_{21}[k] & H_{22}[k] \end{bmatrix}$$
- **Zero-Forcing Equalizer**:
  $$\mathbf{W}_{ZF}[k] = \mathbf{H}[k]^{-1} = \frac{1}{\det(\mathbf{H}[k])} \begin{bmatrix} H_{22}[k] & -H_{12}[k] \\ -H_{21}[k] & H_{11}[k] \end{bmatrix}$$
  $$\hat{\mathbf{X}}[k] = \mathbf{W}_{ZF}[k] \mathbf{Y}[k]$$

---

## 🏃 Running Tests & Experiments

```bash
# 1. Run all unit tests (Tasks 1, 2, 3, and 4)
pytest

# 2. Run OFDM Cyclic Prefix benefit demonstration
python experiments/ofdm_demo.py

# 3. Run 2x2 MIMO spatial multiplexing constellation demo
python experiments/mimo_demo.py

# 4. Run OFDM vs 2x2 MIMO-OFDM BER performance evaluation
python experiments/ofdm_mimo_ber.py
```
Output plots will be saved to `results/ofdm/` and `results/mimo/`.
