"""
One GNU Radio run end to end: flowgraph -> receiver -> export dict (-> NPZ + ledger),
and an export through the EXISTING bridge pipeline (Spectrum -> Twin -> Prediction ->
Cyber Defense -> ACWRA).
"""

import os
from typing import Any, Dict, Optional

from src.simulink_bridge.pipeline import PipelineResult, SimulinkACWRAPipeline

from .availability import require_gnuradio
from .config import GRPhyConfig
from .export import DEFAULT_LEDGER, IN_PROCESS_RUNS, build_export, write_export
from .receiver import demodulate_ofdm, demodulate_psk
from .validation import to_measurement, validate_gnuradio_dict


def run_gnuradio(cfg: GRPhyConfig, timestamp: float = 0.0) -> Dict[str, Any]:
    """Execute the flowgraph and return the export dict (not yet written)."""
    require_gnuradio()
    from .flowgraph import run_flowgraph   # imports GNU Radio

    capture, info = run_flowgraph(cfg)
    rx = demodulate_ofdm(cfg, capture) if cfg.modulation == "OFDM-QPSK" else demodulate_psk(cfg, capture)
    d = build_export(cfg, capture, info, rx, timestamp=timestamp)
    IN_PROCESS_RUNS[str(d["experiment_id"])] = str(d["content_sha256"])
    return d


def run_and_export(cfg: GRPhyConfig, out_dir: str, timestamp: float = 0.0,
                   ledger_path: Optional[str] = DEFAULT_LEDGER) -> str:
    """Run, write <out_dir>/<experiment_id>.npz (never overwriting), append to the ledger."""
    d = run_gnuradio(cfg, timestamp=timestamp)
    return write_export(d, os.path.join(out_dir, f"{d['experiment_id']}.npz"), ledger_path=ledger_path)


def decide_on_export(d: Dict[str, Any], pipeline: Optional[SimulinkACWRAPipeline] = None, *,
                     require_gnuradio: bool = False, ledger_path: Optional[str] = DEFAULT_LEDGER,
                     reset_state: bool = True) -> PipelineResult:
    """
    Validate an export and run it through the existing agents and ACWRA.

    An export that fails validation raises MeasurementValidationError: it never turns
    into a normal-looking decision.
    """
    rep = validate_gnuradio_dict(d, require_gnuradio=require_gnuradio, ledger_path=ledger_path)
    rep.raise_if_invalid(context=f"GNU Radio export {d.get('experiment_id', '?')}")
    pipe = pipeline or SimulinkACWRAPipeline()
    if reset_state:
        pipe.reset()
    return pipe.run_measurement(to_measurement(d, rep.facts["provenance"]), rep,
                                source_path=str(d.get("experiment_id", "")))


def selected_modulation(result: PipelineResult) -> str:
    dec = result.decision
    return next(c.modulation for c in dec.candidate_scores if c.strategy == dec.selected_strategy)
