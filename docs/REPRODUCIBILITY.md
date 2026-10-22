# Reproducibility guide

Two independent reproduction paths. They are never mixed: Python results are labelled
virtual RF, synthetic or fixture; Simulink results come only from a MATLAB machine.

## A. Python (any machine, ~25 min total)

```bash
python -m venv venv
venv\Scripts\activate                     # Linux/macOS: source venv/bin/activate
pip install -r requirements-lock.txt      # exact versions used for the committed results
python -m pytest -q                       # full test suite
python experiments/reproduce_python_results.py
```

`reproduce_python_results.py` writes only into **new** folders, and never overwrites a
committed result. It compares each artefact with the committed one and prints
MATCH / DIFFER:

| step | script | output | compared with |
|---|---|---|---|
| 1 | `spectrum_agent_eval.py --out-dir …` | `results/reproductions/<stamp>/spectrum_eval/` | `results/ai/spectrum_eval/metrics.json` |
| 2 | `digital_twin_forecast_eval.py --out-dir …` | `results/reproductions/<stamp>/forecast_eval/` | `results/digital_twin/forecast_eval/*.csv` |
| 3 | `closed_loop_evaluation.py --run-id repro_<stamp>` | `results/evaluation/closed_loop/repro_<stamp>/` | `results/evaluation/closed_loop/cl2_20261022/episodes.csv` |
| 4 | `retrain_modulation_classifier.py --check` | nothing written | `results/ai/modulation_classifier/retrain_eval/evaluation.json` |

`--quick` runs steps 1–3 with a 2-seed `original` closed-loop subset (≈ 5 min).
`python experiments/research_evaluation.py` regenerates `results/evaluation/RESEARCH_EVALUATION.md`
from the committed outputs (the run ids are fixed in the script).

Determinism: all generators are seeded. Re-running at the same commit gives identical
non-timing numbers. `repro_of_run_20261022_v1` reproduced `run_20261022_v1` bit-for-bit in
all 180 episodes. Timing columns (`decide_ms`, `step_ms`) vary between machines.

Every run folder's `config.json` records the commit (suffixed `-dirty` if `src/` or
`experiments/` had uncommitted changes), seeds, conditions, policies and versions.

## B. MATLAB / Simulink (a machine with MATLAB + Simulink)

Exactly as in [`MATLAB_HANDOFF.md`](reports/MATLAB_HANDOFF.md):

```matlab
cd <repo>/simulink/matlab
logDir = run_v4_validation                 % archive -> build -> D1-D18 -> Rayleigh -> baseline
loop   = run_simulink_closed_loop          % optional: Simulink in the loop with the Python agents
```

Then, back on the Python side:

```bash
python experiments/handoff_check.py post
```

The closed-loop function needs `python` on the MATLAB machine's PATH, with
`requirements-lock.txt` installed, or `opts.python` set to that interpreter.

## Data that must not be regenerated in place

`simulink/results/` (historical v2/v3 exports and legacy files), `simulink/results_archive/`,
and every existing `results/evaluation/closed_loop/<run_id>/`. New runs always get new
folders; see `docs/DATA_SCHEMA_PROVENANCE.md`.
