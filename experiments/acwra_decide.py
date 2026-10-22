"""
ONE CLOSED-LOOP DECISION FROM ONE MAT EXPORT (called by run_simulink_closed_loop.m).

    python experiments/acwra_decide.py --mat <export.mat> --state <twin_state.json> --out <decision.json>
                                       [--require-real] [--require-model-version v4]

1. Loads and validates the export (strict; --require-real accepts only a MATLAB-written
   source='simulink' file).
2. Restores the Digital Twin history and the Spectrum Agent's previous SNR from --state
   (absent on the first step), so successive calls behave like one continuous run.
3. Runs the existing pipeline: Spectrum Agent -> Digital Twin -> Prediction Agent ->
   Cyber Defense Agent -> ACWRA (SimulinkACWRAPipeline.run_measurement, no reset).
4. Writes the decision (DECISION_FIELDS) to --out and the updated state to --state.

Exit codes: 0 decision written; 3 measurement rejected or unreadable (NO decision is
written - the caller must not invent one).
"""

import argparse
import json
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.digital_twin.state import DigitalTwinState
from src.simulink_bridge.pipeline import SimulinkACWRAPipeline
from src.simulink_bridge.validation import MeasurementValidationError

DECISION_FIELDS = (
    "selected_strategy", "next_modulation", "expected_utility", "risk_score", "agent_confidence",
    "provenance", "model_version", "mat", "timestamp_s", "twin_snr_db", "twin_snr_source",
    "candidate_scores", "decision_trace", "environment",
)
STATE_VERSION = 1


def _restore(pipeline, path):
    if not path or not os.path.isfile(path):
        return 0
    with open(path) as fh:
        st = json.load(fh)
    if st.get("version") != STATE_VERSION:
        raise ValueError(f"unsupported state version {st.get('version')} in {path}")
    twin = pipeline.orchestrator.digital_twin
    for d in st.get("history", []):
        s = DigitalTwinState(**d)
        twin.history.append(s)
        twin.state = s
    pipeline.orchestrator.spectrum_agent.prev_snr_db = st.get("prev_snr_db")
    return len(st.get("history", []))


def _save(pipeline, path):
    twin = pipeline.orchestrator.digital_twin
    st = {"version": STATE_VERSION,
          "history": [s.to_dict() for s in twin.history.get_history()],
          "prev_snr_db": pipeline.orchestrator.spectrum_agent.prev_snr_db}
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="One ACWRA decision from one MAT export")
    ap.add_argument("--mat", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--require-real", action="store_true")
    ap.add_argument("--require-model-version", default=None)
    args = ap.parse_args(argv)

    pipeline = SimulinkACWRAPipeline()
    try:
        n_hist = _restore(pipeline, args.state)
        meas, report = pipeline.load(args.mat, strict=True, require_real=args.require_real,
                                     require_model_version=args.require_model_version)
        result = pipeline.run_measurement(meas, report, source_path=args.mat)
    except (FileNotFoundError, MeasurementValidationError, ValueError) as exc:
        print(f"REJECTED - no decision written: {exc}")
        return 3

    dec = result.decision
    nxt = next(c.modulation for c in dec.candidate_scores if c.strategy == dec.selected_strategy)
    last = result.windows[-1] if result.windows else None
    out = {
        "selected_strategy": dec.selected_strategy,
        "next_modulation": nxt,
        "expected_utility": dec.expected_utility,
        "risk_score": dec.risk_score,
        "agent_confidence": dec.agent_confidence,
        "provenance": meas.provenance,
        "model_version": report.facts.get("model_version", ""),
        "mat": os.path.abspath(args.mat),
        "timestamp_s": dec.timestamp_s,
        "twin_snr_db": last.twin_snr_db if last else None,
        "twin_snr_source": last.twin_snr_source if last else "",
        "candidate_scores": [c.to_dict() for c in dec.candidate_scores],
        "decision_trace": dec.decision_trace,
        "environment": "simulink export" if meas.provenance == "simulink_export" else meas.provenance,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    _save(pipeline, args.state)
    print(f"DECISION {dec.selected_strategy} -> next {nxt} | U {dec.expected_utility:+.4f} | "
          f"R {dec.risk_score:.2f} | provenance {meas.provenance} | twin history {n_hist} -> "
          f"{len(pipeline.orchestrator.digital_twin.history)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
