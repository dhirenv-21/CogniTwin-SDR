# Control dashboard

Streamlit app that runs real GNU Radio simulations through the existing backend and
shows only what the runs produced.

## Launch

```bash
C:\Users\HP\radioconda\envs\cognitwin-dash\python.exe dashboard\run_dashboard.py
```

Open <http://localhost:8501>. Port: append `--server.port 8502`.

Environment `cognitwin-dash` = a clone of `cognitwin-gr` (GNU Radio 3.10.12.0, NumPy 2.2.6)
plus `streamlit` and `plotly` from conda-forge (`--freeze-installed`, so nothing else changed).
Recreate with:

```bash
mamba create -y -n cognitwin-dash --clone cognitwin-gr
mamba install -y -n cognitwin-dash -c conda-forge --freeze-installed streamlit plotly
```

## Behaviour

| item | where |
|---|---|
| RUN SIMULATION | `dashboard/worker.py` subprocess → `run_closed_loop` with `run_gnuradio` → `results/gnuradio/dashboard/runs/<id>/` (`ep<k>.npz`, `episodes.csv`, `decisions.jsonl`) |
| RUN SMOKE TEST | same 2 conditions × 6 policies × 6 episodes as `gnuradio_campaign.py --smoke`; needs confirmation |
| RUN CAMPAIGN | user grid; needs the confirmation box; analysed with `experiments/gnuradio_campaign_analysis.py` |
| STOP JOB | terminates only a worker the dashboard started (checked by folder and process command line) |
| plots / cards | read back from the run's files; every episode is revalidated (`validate_gnuradio_dict`) |
| BER / PER vs SNR | BER validation runs and AWGN campaign episodes (GNU Radio only) |
| run history | GNU Radio, MATLAB (historical), Fixture, Aborted, Invalid, Stopped, Running |

Nothing runs when the page opens. Repository results are read-only. Execution buttons
are disabled when GNU Radio cannot be imported. One job at a time.

Not estimated by the Spectrum Agent: interference power (passed through by design).
Risk gate = Cyber Defense candidate set: CLOSED when it offers only "Keep Current".

Tests: `tests/test_dashboard.py` (job output redirected via `COGNITWIN_DASH_DIR`).
