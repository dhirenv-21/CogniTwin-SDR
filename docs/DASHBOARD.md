# Control dashboard

Streamlit app that runs real GNU Radio simulations through the existing backend and
shows only what the runs (and the repository's recorded results) produced.

## Launch

From the repository root:

```bash
python dashboard/run_dashboard.py
```

Open <http://localhost:8501>. Port: append `--server.port 8502`.

`run_dashboard.py` uses the current interpreter when it can import GNU Radio. Otherwise it
relaunches in the first GNU Radio environment it finds that also has Streamlit:
`$COGNITWIN_GR_PYTHON`, then `cognitwin-gr` / `cognitwin-dash` under `D:\micromamba`,
`%USERPROFILE%\micromamba`, radioconda or miniforge. On Windows it puts the environment's
DLL folders on `PATH`, so no activation is needed. Use `--no-gr-switch` to stay on the current
interpreter (browse-only without GNU Radio).

Environment used on this machine (standalone micromamba, nothing registered system-wide):

```bash
micromamba create -n cognitwin-gr -c conda-forge python=3.12 numpy=2.2 scipy=1.15 "libblas=*=*openblas" gnuradio=3.10.12 scikit-learn=1.7.2 matplotlib joblib pytest pyyaml streamlit plotly pandas
```

## Structure

| file | role |
|---|---|
| `dashboard/app.py` | shell: `st.navigation` sidebar, top bar (GNU Radio state, run id, alerts), live job monitor |
| `dashboard/views/*.py` | one script per page (overview, live, campaign, agents, comparison, history, diagnostics, settings) |
| `dashboard/ui/theme.py` | design tokens (colours, fonts, spacing), global CSS, Plotly figure template |
| `dashboard/ui/components.py` | metric cards, chips, badges, section headers, empty states, pipeline, Lucide icons |
| `dashboard/ui/plots.py` | scientific plots (waveform, constellation, spectrum, PSD, BER/PER, decisions, comparisons) |
| `dashboard/ui/data.py` | cached loaders keyed on file mtimes, shared session state |
| `dashboard/backend.py` | validation, job control, result loading (no Streamlit; unit-tested) |
| `dashboard/worker.py` | job subprocess: closed loop / campaign through the existing code |
| `.streamlit/config.toml` | dark theme tokens |

## Views

| view | content |
|---|---|
| Overview | GNU Radio state, completed runs, validated episodes, latest BER/goodput, campaign state, latest signal and decision, ACWRA vs baselines, recent runs |
| Live Simulation | grouped inputs (Transmitter, Channel, Defense, Execution); KPI strip; I/Q waveform, constellation (received + equalised), spectrum, PSD; BER & goodput per episode; decision timeline; pipeline; reference BER/PER curves |
| Campaign Lab | grid design, exact workload (runs, flowgraphs, symbols), confirmation, launch, live monitor, results library (report, analysis, artifacts, downloads) |
| AI Agents | pipeline GNU Radio → I/Q → Spectrum → Twin → Prediction → Cyber Defense → ACWRA → next episode; per-agent recorded output; candidate utility scores; decision timeline with risk gate and applied-to-next-episode. Sources: dashboard runs (full trace), campaign episodes (headline outputs), repository demo |
| Policy Comparison | filters (channel, SNR, jammer); means; ACWRA − baseline paired CI forest plots; Wilcoxon p (n/a when not computable); per-condition heatmaps; findings computed from the data |
| Run History | search, filters and sorting; detail per run: configuration, metrics, signal, decisions, provenance, artifacts |
| System Diagnostics | GNU Radio probe, Python environment, data validation, dashboard test runner, recent problems, output locations (repository-relative paths only) |
| Settings | session display preferences (plot sample counts, Tx reference, refresh interval) |

## Behaviour

| item | where |
|---|---|
| Run simulation | `dashboard/worker.py` subprocess → `run_closed_loop` with `run_gnuradio` → `results/gnuradio/dashboard/runs/<id>/` (`ep<k>.npz`, `episodes.csv`, `decisions.jsonl`) |
| Run smoke test | same 2 conditions × 6 policies × 6 episodes as `gnuradio_campaign.py --smoke`; needs confirmation |
| Launch campaign | user grid; needs the confirmation box; new folder each time under `results/gnuradio/dashboard/campaigns/`; analysed with `experiments/gnuradio_campaign_analysis.py` |
| Stop job | terminates only a worker the dashboard started (checked by folder and process command line) |
| plots / cards | read back from the run's files; every episode is revalidated (`validate_gnuradio_dict`) |
| BER / PER vs SNR | BER validation runs and AWGN campaign episodes (GNU Radio only) |
| run history | GNU Radio, MATLAB (historical), Fixture, Aborted, Invalid, Stopped, Running |

Nothing runs when a page opens. Repository results (including `grcl1_20261022_v2`) are read-only.
Execution buttons are disabled when GNU Radio cannot be imported. One job at a time. Missing
values are shown as "—" (cards) or a grey "None" (sortable tables), never as 0.

GNU Radio status: *not installed* (module not importable), *installed · import failed*,
*ready* (probe succeeded) or *executing* (a dashboard worker with a live PID is running).

Not estimated by the Spectrum Agent: interference power (passed through by design).
Risk gate = Cyber Defense candidate set: CLOSED when it offers only "Keep Current".

Tests: `tests/test_dashboard.py` (job output redirected via `COGNITWIN_DASH_DIR`; every page
rendered with Streamlit's `AppTest`).
