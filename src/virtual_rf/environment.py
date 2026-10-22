"""
Discrete-Time Block-Based Virtual RF Environment.

Implements Environment state machine, step execution, observation buffer,
and counterfactual simulate function for future Cognitive Digital Twin reasoning.
"""

from typing import Any, Dict, Optional, Tuple
import numpy as np

from src.signal.generator import generate_sinusoid, to_iq, add_awgn
from src.modulation.analog import AMDSBSCModulator, AMDSTCModulator, FMModulator
from src.modulation.digital import generate_bits, ASKModulator, FSKModulator, PSKModulator, calculate_ber
from src.multicarrier.ofdm import OFDMTransmitterReceiver
from src.multicarrier.channel import MultipathChannel

from .state import EnvironmentState
from .scenario import ScenarioEngine
from .interference import InterferenceGenerator
from .link_model import FADING_CHANNELS, link_metrics


class VirtualRFEnvironment:
    """
    Discrete-time software Virtual RF Environment state machine.
    """

    def __init__(
        self,
        scenario: Optional[ScenarioEngine] = None,
        sample_rate: float = 100000.0,
        seed: Optional[int] = 42,
    ):
        self.sample_rate = sample_rate
        self.scenario = scenario if scenario is not None else ScenarioEngine()
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        self.current_time_s = 0.0
        self.current_state = EnvironmentState(timestamp_s=0.0)
        self.last_iq_buffer = np.zeros(512, dtype=np.complex128)
        self.interference_gen = InterferenceGenerator(sample_rate=sample_rate, seed=seed)

        # Closed-loop actuation (opt-in). When set, step() transmits this modulation
        # instead of the scenario keyframe's, so an adaptation decision can be
        # applied to subsequent steps. None (default) keeps the scenario in control.
        self.modulation_override: Optional[str] = None
        # Power gain of the channel realised in the latest step (1.0 for AWGN).
        self.last_channel_gain: float = 1.0

        # Initialize initial state from scenario
        self._update_state_from_scenario()

    def _update_state_from_scenario(self):
        kf = self.scenario.get_keyframe_at(self.current_time_s)
        self.current_state.timestamp_s = self.current_time_s
        self.current_state.modulation = kf.get("modulation", "QPSK")
        self.current_state.snr_db = float(kf.get("snr_db", 20.0))
        self.current_state.channel_type = kf.get("channel_type", "awgn")
        self.current_state.interference_power = float(kf.get("interference_power", 0.0))

    def observe_state(self) -> EnvironmentState:
        """Returns snapshot of current EnvironmentState dataclass."""
        return self.current_state

    def observe_iq(self) -> np.ndarray:
        """Returns complex I/Q sample array generated during the last step."""
        return self.last_iq_buffer

    def step(self, duration_seconds: float = 0.1) -> Tuple[EnvironmentState, np.ndarray]:
        """
        Advances discrete simulation clock by duration_seconds.

        Generates I/Q signal, applies channel fading and interference,
        updates internal state metrics (BER, packet loss, latency), and returns (state, iq_samples).
        """
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive.")

        n_samples = max(64, int(round(duration_seconds * self.sample_rate)))
        kf = self.scenario.get_keyframe_at(self.current_time_s)

        mod_type = kf.get("modulation", self.current_state.modulation)
        if self.modulation_override is not None:
            mod_type = self.modulation_override
        snr_db = float(kf.get("snr_db", self.current_state.snr_db))
        chan_type = kf.get("channel_type", self.current_state.channel_type)
        interf_type = kf.get("interference_type", "none")
        interf_pow = float(kf.get("interference_power", 0.0))

        step_seed = int(self.rng.integers(0, 1000000))
        iq_clean = self._generate_mod_iq(mod_type, n_samples, seed=step_seed)

        # Apply channel fading / impairments
        iq_channel = self._apply_channel(iq_clean, chan_type, snr_db, seed=step_seed)

        # Apply interference
        iq_interf = self._apply_interference(iq_channel, interf_type, interf_pow, n_samples)

        self.last_iq_buffer = iq_interf

        # Update environment metrics with the fade REALISED in this block (the
        # sandbox, simulate(), uses the expectation over the fading distribution)
        ber, pkt_loss, latency_ms, throughput = self._compute_congestion_metrics(
            mod_type, snr_db, chan_type, interf_pow,
            channel_gain=self.last_channel_gain if chan_type in FADING_CHANNELS else None,
        )

        self.current_state.timestamp_s = self.current_time_s
        self.current_state.modulation = mod_type
        self.current_state.snr_db = snr_db
        self.current_state.channel_type = chan_type
        self.current_state.interference_power = interf_pow
        self.current_state.signal_power = float(np.mean(np.abs(iq_clean) ** 2))
        self.current_state.ber = ber
        self.current_state.packet_loss = pkt_loss
        self.current_state.latency_ms = latency_ms
        self.current_state.throughput_bps = throughput

        # Advance discrete clock
        self.current_time_s += duration_seconds
        return self.current_state, self.last_iq_buffer

    def simulate(self, current_state: EnvironmentState, strategy: Dict[str, Any]) -> EnvironmentState:
        """
        Pure/counterfactual function predicting output state if a candidate strategy
        (e.g., modulation="BPSK", coding="FEC") were applied, WITHOUT advancing environment time.
        """
        candidate_mod = strategy.get("modulation", current_state.modulation)
        candidate_snr = float(strategy.get("snr_db", current_state.snr_db))
        chan_type = current_state.channel_type
        interf_pow = current_state.interference_power

        ber, pkt_loss, latency_ms, throughput = self._compute_congestion_metrics(
            candidate_mod, candidate_snr, chan_type, interf_pow
        )

        predicted_state = EnvironmentState(
            timestamp_s=current_state.timestamp_s,
            modulation=candidate_mod,
            snr_db=candidate_snr,
            signal_power=current_state.signal_power,
            interference_power=interf_pow,
            bandwidth_hz=current_state.bandwidth_hz,
            channel_type=chan_type,
            ber=ber,
            packet_loss=pkt_loss,
            throughput_bps=throughput,
            latency_ms=latency_ms,
        )
        return predicted_state

    def _generate_mod_iq(self, mod_type: str, n_samples: int, seed: int) -> np.ndarray:
        from src.ai.modulation_classifier.dataset import generate_single_signal
        # Generate clean signal block of 512 samples at snr=100 dB
        block_iq = generate_single_signal(
            mod_type=mod_type,
            snr_db=100.0,
            sample_rate=self.sample_rate,
            n_samples=512,
            seed=seed,
        )
        repeats = int(np.ceil(n_samples / len(block_iq)))
        return np.tile(block_iq, repeats)[:n_samples]

    def _apply_channel(self, iq: np.ndarray, chan_type: str, snr_db: float, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        if chan_type == "rayleigh":
            # 2-tap Rayleigh fading
            gains = (rng.normal(0, 1, 2) + 1j * rng.normal(0, 1, 2)) / np.sqrt(2)
            # matched-filter (two-path) power gain, normalised to E[g] = 1
            self.last_channel_gain = float((abs(gains[0]) ** 2 + 0.25 * abs(gains[1]) ** 2) / 1.25)
            iq_faded = np.zeros_like(iq)
            iq_faded += gains[0] * iq
            iq_faded[2:] += 0.5 * gains[1] * iq[:-2]
            return add_awgn(iq_faded, snr_db=snr_db, seed=seed)
        elif chan_type == "rician":
            # Rician fading (LOS component + Rayleigh scatter)
            los = 1.0 + 0j
            scatter = (rng.normal(0, 1) + 1j * rng.normal(0, 1)) / np.sqrt(2)
            h = (np.sqrt(2.0) * los + scatter) / np.sqrt(3.0)
            self.last_channel_gain = float(abs(h) ** 2)
            return add_awgn(h * iq, snr_db=snr_db, seed=seed)
        else:
            # Clean AWGN
            self.last_channel_gain = 1.0
            return add_awgn(iq, snr_db=snr_db, seed=seed)

    def _apply_interference(self, iq: np.ndarray, interf_type: str, interf_pow: float, n_samples: int) -> np.ndarray:
        if interf_pow <= 0 or interf_type == "none":
            return iq

        if interf_type == "narrowband":
            jam = self.interference_gen.generate_narrowband_tone(freq_offset_hz=2000.0, power=interf_pow, n_samples=n_samples)
        elif interf_type == "broadband":
            jam = self.interference_gen.generate_broadband_noise(power=interf_pow, n_samples=n_samples)
        elif interf_type == "swept":
            jam = self.interference_gen.generate_swept_jamming(start_freq_hz=-10000, end_freq_hz=10000, power=interf_pow, n_samples=n_samples)
        else:
            jam = np.zeros(n_samples, dtype=np.complex128)

        return iq + jam

    def _compute_congestion_metrics(
        self,
        mod_type: str,
        snr_db: float,
        chan_type: str,
        interf_pow: float,
        channel_gain: Optional[float] = None,
    ) -> Tuple[float, float, float, float]:
        """
        (ber, packet_loss, latency_ms, throughput_bps) from the link abstraction in
        src/virtual_rf/link_model.py: SINR = g / (N0 + J) with a Gaussian-equivalent
        jammer, exact coherent BER, uncoded 256-bit packets. channel_gain is the
        realised block-fading power gain (step()); None gives the expectation over the
        fading distribution (simulate(), i.e. the Digital Twin sandbox).
        """
        ber, packet_loss, latency_ms, throughput, _ = link_metrics(
            mod_type, snr_db, chan_type, interf_pow, channel_gain=channel_gain
        )
        return ber, packet_loss, latency_ms, throughput
