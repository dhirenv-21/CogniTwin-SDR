"""
Simulink -> Multi-Agent -> ACWRA Integration Pipeline.

This module is the ONLY new glue layer added by Task 11. It contains no signal
processing decisions, no modulation classification, no risk equations, no counterfactual
model and no utility mathematics of its own. Every decision-making stage is delegated to
the components that already exist in the repository:

    SpectrumAgent            src/agents/spectrum_agent.py       (unmodified)
    DigitalTwin              src/digital_twin/twin.py           (unmodified)
    PredictionAgent          src/agents/prediction_agent.py     (unmodified)
    CyberDefenseAgent        src/agents/cyber_defense_agent.py  (unmodified)
    MultiAgentSnapshot       src/agents/messages.py             (unmodified)
    VirtualRFEnvironment     src/virtual_rf/environment.py      (unmodified, .simulate only)
    ACWRAEngine              src/acwra/engine.py                (unmodified)

Why an adapter instead of MultiAgentOrchestrator.step()
-------------------------------------------------------
MultiAgentOrchestrator.step() begins by calling VirtualRFEnvironment.step(), which
SYNTHESISES its own I/Q internally. For Task 11 the I/Q must come from MATLAB/Simulink
instead. This adapter therefore reuses the orchestrator's *own agent instances* and
executes the orchestrator's steps 2-6 verbatim, substituting only step 1 (the signal
source). No agent is duplicated and no decision equation is re-implemented.

Real-measurement policy
-----------------------
The pipeline refuses to invent measurements. If the MAT file is missing or malformed the
run fails loudly (MeasurementValidationError / FileNotFoundError). Synthetic fixtures are
only ever produced by src/simulink_bridge/reference_phy.py and are always tagged
source="python-fixture" so they can never be mistaken for a real Simulink export.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.agents.messages import MultiAgentSnapshot, SpectrumIntelligenceResult
from src.agents.orchestrator import MultiAgentOrchestrator
from src.acwra.decision import ACWRADecision
from src.acwra.engine import ACWRAEngine
from src.digital_twin.state import DigitalTwinState
from src.virtual_rf.state import EnvironmentState

from .protocol import SimulinkMeasurement
from .receiver import SimulinkReceiver
from .validation import (
    MeasurementValidationError,
    ValidationReport,
    flatten_matlab_iq,
    measure_iq_statistics,
    validate_measurement,
)


# Map MATLAB channel labels onto the lowercase labels the Digital Twin / VirtualRF use.
_CHANNEL_MAP = {
    "AWGN": "awgn",
    "RAYLEIGH": "rayleigh",
    "RICIAN": "rician",
}


def matlab_channel_to_internal(channel_type: str) -> str:
    """Translate a MATLAB channel label to the repository's internal label."""
    return _CHANNEL_MAP.get(str(channel_type).strip().upper(), str(channel_type).strip().lower())


@dataclass
class WindowObservation:
    """One analysis window of the real Simulink capture, after agent processing."""

    index: int
    timestamp_s: float
    start_sample: int
    end_sample: int
    measured_power: float
    measured_snr_db: Optional[float]
    spectrum_result: SpectrumIntelligenceResult = None
    twin_state: DigitalTwinState = None
    # SNR handed to the Digital Twin: transmit-referenced, noise only (see run_measurement)
    twin_snr_db: Optional[float] = None
    twin_snr_source: str = ""  # "measured_noise_iq" | "nominal"


@dataclass
class PipelineResult:
    """Complete record of one Simulink -> ACWRA end-to-end run."""

    measurement: SimulinkMeasurement
    validation: ValidationReport
    iq_statistics: Dict[str, float]
    windows: List[WindowObservation]
    snapshot: MultiAgentSnapshot
    counterfactuals: List[Dict[str, Any]]
    decision: ACWRADecision
    sample_rate: float
    window_size: int
    source_path: str = ""

    @property
    def spectrum_result(self) -> SpectrumIntelligenceResult:
        return self.snapshot.spectrum_result

    def to_row(self) -> Dict[str, Any]:
        """Flatten the run into a single results-table row (Task 11, Part 11)."""
        m = self.measurement
        spec = self.snapshot.spectrum_result
        pred = self.snapshot.prediction_result
        dec = self.decision
        return {
            "modulation_true": m.modulation,
            "snr_db_nominal": m.snr_db,
            "snr_db_measured": self.iq_statistics.get("measured_snr_db", float("nan")),
            "interference_power": m.interference_power,
            "channel_type": m.channel_type,
            "ber_measured": m.ber,
            "measured_power": self.iq_statistics.get("measured_power", float("nan")),
            "num_samples": m.num_samples,
            "modulation_detected": spec.modulation if spec else "",
            "confidence": spec.classifier_confidence if spec else float("nan"),
            "anomaly": spec.anomaly_flag if spec else "",
            "risk_score": pred.risk_score if pred else float("nan"),
            "risk_level": pred.risk_level if pred else "",
            "n_candidates": len(dec.candidate_scores),
            "selected_strategy": dec.selected_strategy,
            "expected_utility": dec.expected_utility,
            "source": m.source,
            "provenance": m.provenance,
            "model_version": self.validation.facts.get("model_version", ""),
            "run_id": self.validation.facts.get("run_id", ""),
        }


class SimulinkACWRAPipeline:
    """
    Drives a real Simulink measurement through the existing CogniTwin-SDR stack.

    Usage:
        pipeline = SimulinkACWRAPipeline()
        result = pipeline.run_from_mat("simulink/results/measurement_case.mat")
        print(result.decision.decision_trace)
    """

    def __init__(
        self,
        orchestrator: Optional[MultiAgentOrchestrator] = None,
        acwra_engine: Optional[ACWRAEngine] = None,
        sample_rate: float = 100000.0,
        window_size: int = 512,
        window_stride: Optional[int] = None,
        max_windows: int = 24,
    ):
        # Existing orchestrator (owns the existing SpectrumAgent / PredictionAgent /
        # CyberDefenseAgent / DigitalTwin instances). Never subclassed, never patched.
        self.orchestrator = orchestrator or MultiAgentOrchestrator(sample_rate=sample_rate)
        # Existing ACWRA engine with its untouched default weights
        # (w_t=0.4, w_se=0.2, w_b=0.6, lambda_c=1.0).
        self.acwra = acwra_engine or ACWRAEngine()
        self.sample_rate = float(sample_rate)
        self.window_size = int(window_size)
        self.window_stride = int(window_stride) if window_stride else int(window_size)
        self.max_windows = int(max_windows)

    # ------------------------------------------------------------------ loading

    def load(
        self,
        mat_path: str,
        *,
        expected_samples: Optional[int] = None,
        expected_sample_rate: Optional[float] = None,
        sample_count_tolerance: int = 0,
        strict: bool = True,
        **provenance_kwargs,
    ) -> Tuple[SimulinkMeasurement, ValidationReport]:
        """Load and validate a real MAT-file export. Never fabricates data.

        provenance_kwargs: require_real, require_model_version, not_before
        (see SimulinkReceiver.load_and_validate).
        """
        return SimulinkReceiver.load_and_validate(
            mat_path,
            expected_samples=expected_samples,
            expected_sample_rate=expected_sample_rate,
            sample_count_tolerance=sample_count_tolerance,
            strict=strict,
            **provenance_kwargs,
        )

    # ------------------------------------------------------------- windowing

    def _iter_windows(self, iq: np.ndarray) -> List[Tuple[int, int]]:
        """
        Split the real capture into consecutive analysis windows.

        Windowing is what lets a single Simulink capture populate the Digital Twin's
        history buffer, so the existing TrendPredictor (which needs >= history_window
        states) can produce a genuine SUCCESS forecast instead of INSUFFICIENT_HISTORY.
        Every window carries real samples - none are synthesised or repeated.
        """
        n = int(iq.size)
        w = self.window_size
        s = self.window_stride
        if n < w:
            return [(0, n)]
        bounds = []
        start = 0
        while start + w <= n and len(bounds) < self.max_windows:
            bounds.append((start, start + w))
            start += s
        return bounds

    # ------------------------------------------------------------------- run

    def run_measurement(
        self,
        measurement: SimulinkMeasurement,
        validation: Optional[ValidationReport] = None,
        source_path: str = "",
    ) -> PipelineResult:
        """
        Execute the full pipeline on an already-loaded real measurement.

        Stage map:
            1. measured I/Q statistics            (measurement only)
            2. SpectrumAgent.process()            EXISTING agent, per window
            3. DigitalTwin.update()               EXISTING twin
            4. PredictionAgent.process()          EXISTING agent
            5. CyberDefenseAgent.process()        EXISTING agent
            6. MultiAgentSnapshot                 EXISTING dataclass
            7. DigitalTwin.evaluate_counterfactuals() via ACWRAEngine (EXISTING sandbox)
            8. ACWRAEngine.evaluate_and_decide()  EXISTING mathematics
        """
        # A measurement handed in directly (not via load()) is validated here too.
        # Without this, a NaN sample made the LS SNR measurement NaN, the pipeline
        # silently fell back to the NOMINAL SNR, features were nan_to_num'd, and a
        # normal-looking decision came out of corrupted data.
        if validation is None:
            validation = validate_measurement(measurement)
            validation.raise_if_invalid(context="run_measurement")
        for name, arr in (("iq_samples", measurement.iq_samples), ("tx_iq", measurement.tx_iq)):
            if arr is not None and not np.all(np.isfinite(arr)):
                raise MeasurementValidationError(f"run_measurement: {name} contains NaN or Inf")

        orch = self.orchestrator
        fs = measurement.sample_rate if measurement.sample_rate > 0 else self.sample_rate

        iq = measurement.iq_samples
        stats = measure_iq_statistics(iq, sample_rate=fs, tx_iq=measurement.tx_iq)

        internal_channel = matlab_channel_to_internal(measurement.channel_type)
        window_duration = self.window_size / fs if fs > 0 else 0.1
        base_t = measurement.timestamp

        noise_arr = None
        if "noise_iq" in measurement.extras:
            try:
                noise_arr = flatten_matlab_iq(measurement.extras["noise_iq"])
                if noise_arr.size != iq.size:
                    noise_arr = None
            except MeasurementValidationError:
                noise_arr = None

        windows: List[WindowObservation] = []
        spectrum_res = None
        twin_state = None

        for idx, (lo, hi) in enumerate(self._iter_windows(iq)):
            block = iq[lo:hi]
            t_win = base_t + idx * window_duration

            # -- Stage 2: EXISTING SpectrumAgent on REAL Simulink I/Q -------------
            # convert_for_spectrum_agent() applies the repository's own deterministic
            # representation adapter (unit-power normalisation + 512-sample window).
            block_meas = SimulinkMeasurement(
                iq_samples=block,
                snr_db=measurement.snr_db,
                ber=measurement.ber,
                modulation=measurement.modulation,
                interference_power=measurement.interference_power,
                channel_type=measurement.channel_type,
                timestamp=t_win,
                sample_rate=fs,
                source=measurement.source,
            )
            iq_adapted, t_curr, interf_pwr = SimulinkReceiver.convert_for_spectrum_agent(
                block_meas
            )
            spectrum_res = orch.spectrum_agent.process(
                iq_samples=iq_adapted,
                timestamp_s=t_curr,
                env_interference_power=interf_pwr,
            )

            # -- Stage 3: EXISTING DigitalTwin update ----------------------------
            # The EnvironmentState mirrors the REAL measurement. BER and throughput are
            # derived through the existing VirtualRFEnvironment.simulate() model so the
            # twin stays internally consistent with the sandbox it will later query.
            win_stats = measure_iq_statistics(block, sample_rate=fs, tx_iq=(
                measurement.tx_iq[lo:hi] if measurement.tx_iq is not None else None
            ))
            measured_snr = win_stats.get("measured_snr_db")
            # The Digital Twin's sandbox (src/virtual_rf/link_model.py) takes a
            # TRANSMIT-referenced, noise-only SNR and adds the interference J and the
            # expected fade itself. measured_snr_db above is a post-fade SINR (the LS
            # error rx - h*tx contains the jammer), so feeding it would count the
            # jammer and the fade twice. Use P_tx / P_noise from the logged noise
            # when the export has it, else the configured SNR (labelled 'nominal').
            snr_for_twin, twin_snr_source = float(measurement.snr_db), "nominal"
            if noise_arr is not None and measurement.tx_iq is not None:
                p_tx = float(np.mean(np.abs(measurement.tx_iq[lo:hi]) ** 2))
                p_n = float(np.mean(np.abs(noise_arr[lo:hi]) ** 2))
                if p_tx > 0 and p_n > 0:
                    snr_for_twin, twin_snr_source = 10.0 * np.log10(p_tx / p_n), "measured_noise_iq"

            probe_state = EnvironmentState(
                timestamp_s=t_win,
                modulation=measurement.modulation,
                snr_db=snr_for_twin,
                signal_power=float(win_stats["measured_power"]),
                interference_power=float(measurement.interference_power),
                channel_type=internal_channel,
                ber=float(measurement.ber),
            )
            # EXISTING counterfactual physics model, used purely to fill throughput /
            # packet-loss / latency consistently. No new equations introduced here.
            derived = orch.env.simulate(
                probe_state, {"modulation": measurement.modulation, "snr_db": snr_for_twin}
            )

            env_state = EnvironmentState(
                timestamp_s=t_win,
                modulation=measurement.modulation,
                snr_db=snr_for_twin,
                signal_power=float(win_stats["measured_power"]),
                interference_power=float(measurement.interference_power),
                bandwidth_hz=float(spectrum_res.bandwidth_hz),
                channel_type=internal_channel,
                # Prefer the BER MATLAB actually measured; fall back to the model only
                # when the export carried no BER at all.
                ber=float(measurement.ber) if measurement.ber > 0.0 else float(derived.ber),
                packet_loss=float(derived.packet_loss),
                throughput_bps=float(derived.throughput_bps),
                latency_ms=float(derived.latency_ms),
            )

            twin_state = orch.digital_twin.update(
                env_state,
                ai_result={
                    "predicted_modulation": spectrum_res.modulation,
                    "confidence": spectrum_res.classifier_confidence,
                    "snr_db": spectrum_res.snr_db,
                },
            )

            windows.append(
                WindowObservation(
                    index=idx,
                    timestamp_s=t_win,
                    start_sample=lo,
                    end_sample=hi,
                    measured_power=float(win_stats["measured_power"]),
                    measured_snr_db=measured_snr,
                    twin_snr_db=snr_for_twin,
                    twin_snr_source=twin_snr_source,
                    spectrum_result=spectrum_res,
                    twin_state=twin_state,
                )
            )

        if spectrum_res is None:
            raise ValueError("No analysis window could be formed from the measurement.")

        t_final = windows[-1].timestamp_s

        # -- Stage 4: EXISTING PredictionAgent -----------------------------------
        prediction_res = orch.prediction_agent.process(
            digital_twin=orch.digital_twin,
            horizon_seconds=window_duration,
        )

        # -- Stage 5: EXISTING CyberDefenseAgent ---------------------------------
        defense_candidates = orch.cyber_defense_agent.process(
            spectrum_res=spectrum_res,
            prediction_res=prediction_res,
            dt_state=twin_state,
        )

        # -- Stage 6: EXISTING MultiAgentSnapshot --------------------------------
        snapshot = MultiAgentSnapshot(
            timestamp_s=t_final,
            spectrum_result=spectrum_res,
            prediction_result=prediction_res,
            defense_candidates=defense_candidates,
        )

        # Sandbox metrics recomputed for reporting only. The ACWRA engine performs its
        # own authoritative call to digital_twin.evaluate_counterfactuals() internally;
        # this copy exists so the demo can print the sandbox table.
        counterfactuals = orch.digital_twin.evaluate_counterfactuals(
            candidate_strategies=defense_candidates.candidate_strategies
        )

        # -- Stages 7 & 8: EXISTING ACWRA decision mathematics -------------------
        decision = self.acwra.evaluate_and_decide(snapshot, orch.digital_twin)

        return PipelineResult(
            measurement=measurement,
            validation=validation,
            iq_statistics=stats,
            windows=windows,
            snapshot=snapshot,
            counterfactuals=counterfactuals,
            decision=decision,
            sample_rate=fs,
            window_size=self.window_size,
            source_path=source_path,
        )

    def run_from_mat(
        self,
        mat_path: str,
        *,
        expected_samples: Optional[int] = None,
        expected_sample_rate: Optional[float] = None,
        sample_count_tolerance: int = 0,
        strict: bool = True,
        reset_state: bool = True,
        **provenance_kwargs,
    ) -> PipelineResult:
        """
        Full end-to-end run starting from a real MATLAB/Simulink MAT export.

        Args:
            reset_state: Clear the Digital Twin history and the SpectrumAgent's SNR
                memory before the run, so each MAT file is evaluated independently
                and results are reproducible regardless of call order.
        """
        if reset_state:
            self.reset()

        measurement, report = self.load(
            mat_path,
            expected_samples=expected_samples,
            expected_sample_rate=expected_sample_rate,
            sample_count_tolerance=sample_count_tolerance,
            strict=strict,
            **provenance_kwargs,
        )
        return self.run_measurement(measurement, report, source_path=mat_path)

    def reset(self):
        """Reset per-run agent/twin state without rebuilding the components."""
        self.orchestrator.digital_twin.history.clear()
        self.orchestrator.spectrum_agent.prev_snr_db = None
