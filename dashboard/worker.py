"""
Dashboard job worker: python dashboard/worker.py <job_dir>

Runs one job described by <job_dir>/job.json through the EXISTING code
(src/gnuradio_phy runner, closed loop, validators, agents, ACWRA; the campaign
condition builder and analysis from experiments/). Progress goes to status.json.
Without GNU Radio the job ends in state 'blocked' and nothing is produced.
"""

import csv
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE, os.path.join(ROOT, "experiments")):
    if p not in sys.path:
        sys.path.insert(0, p)

import backend as B  # noqa: E402
from src.gnuradio_phy.availability import gnuradio_available, unavailable_reason  # noqa: E402


class Status:
    def __init__(self, path):
        self.path = os.path.join(path, "status.json")
        self.d = B.read_json(self.path, {}) or {}
        self.d.update(pid=os.getpid(), started=time.time())

    def set(self, **kw):
        self.d.update(kw)
        self.d["elapsed_s"] = time.time() - self.d["started"]
        B.write_json(self.path, self.d)


def _append_csv(path, row, keys=None):
    new = not os.path.exists(path)
    keys = keys or list(row)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


def _write_csv(path, rows):
    """Rewrite the whole file (union of keys), atomically, so a partial campaign stays readable."""
    keys = sorted({k for r in rows for k in r})
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


EPISODE_KEYS = ["episode", "experiment_id", "content_sha256", "provenance", "modulation_applied",
                "decision_from_episode", "snr_db_configured", "snr_db_measured", "interference_power",
                "interference_power_measured", "channel", "fading_mode", "ber", "ber_theory", "per", "bits",
                "goodput_bps", "spectral_efficiency", "detected_modulation", "detected_confidence",
                "estimated_snr_db", "risk_score", "selected_strategy", "expected_utility", "acwra_modulation",
                "sinr_db_measured", "next_modulation", "wall_time_s", "sinr_db_post_fade"]


def decision_record(row, d, res):
    """Everything the agents produced for one episode (or the rule decision for baselines)."""
    rec = {"episode": row["episode"], "experiment_id": row["experiment_id"], "policy": row["policy"],
           "modulation_applied": row["modulation_applied"], "next_modulation": row["next_modulation"],
           "provenance": row.get("provenance", "")}
    if res is None:
        rec["rule"] = "SINR threshold 10 dB on measured SINR" if row["policy"] == "sinr_threshold" else "fixed"
        if "sinr_db_measured" in row:
            rec["sinr_db_measured"] = row["sinr_db_measured"]
        return rec
    w = res.windows[-1]
    s, t, p = w.spectrum_result, w.twin_state, res.snapshot.prediction_result
    dc, dec = res.snapshot.defense_candidates, res.decision
    rec.update(
        spectrum={"modulation": s.modulation, "confidence": s.classifier_confidence, "blind_snr_db": s.snr_db,
                  "anomaly": s.anomaly_flag, "windows": len(res.windows)},
        twin={"snr_db": t.snr_db, "snr_source": w.twin_snr_source, "ber": t.ber, "interference": t.interference_power,
              "condition": t.threat_condition, "history": len(res.windows)},
        prediction={"status": p.prediction_status, "next_snr_db": p.next_snr_db, "next_ber": p.next_ber,
                    "risk": p.risk_score, "level": p.risk_level},
        candidates=list(dc.candidate_strategies), defense_rationale=dc.rationale,
        scores=[c.to_dict() for c in dec.candidate_scores], selected=dec.selected_strategy,
        utility=dec.expected_utility, confidence=dec.agent_confidence,
        applied_next=row["next_modulation"] if row["policy"] == "acwra" else row["modulation_applied"],
        trace=dec.decision_trace)
    return rec


def run_simulation(job_dir, spec, st):
    from src.gnuradio_phy.closed_loop import EpisodeCondition, run_closed_loop
    from src.gnuradio_phy.export import write_export
    from src.gnuradio_phy.runner import run_gnuradio
    inp = B.SimInputs(**{k: v for k, v in spec.items() if k in B.SimInputs.__dataclass_fields__})
    cfg, err = B.validate_inputs(inp)
    if err:
        st.set(state="invalid", message=json.dumps(err))
        return 1
    n = int(inp.episodes)
    chan, fading = B.CHANNELS[inp.channel]
    sched = [EpisodeCondition(cfg.snr_db, cfg.interference_power, chan, fading)] * n
    st.set(state="running", total=n, done=0, failed=0, message="running GNU Radio")
    counter = {"k": 0}

    def phy(c):
        d = run_gnuradio(c)
        write_export(d, os.path.join(job_dir, f"ep{counter['k']}.npz"), ledger_path=B.LEDGER)
        counter["k"] += 1
        return d

    def on_episode(row, d, res):
        row = dict(row, wall_time_s=float(d.get("wall_time_s", float("nan"))), sinr_db_post_fade=B.sinr_db(d))
        _append_csv(os.path.join(job_dir, "episodes.csv"), row, EPISODE_KEYS)
        with open(os.path.join(job_dir, "decisions.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(decision_record(row, d, res), default=float) + "\n")
        st.set(done=row["episode"] + 1, message=f"episode {row['episode'] + 1}/{n}")

    run_closed_loop(sched, inp.effective_policy(), seed=int(inp.seed), initial_modulation=inp.modulation,
                    base=cfg, phy=phy, ledger_path=B.LEDGER, condition_name="dashboard", on_episode=on_episode)
    st.set(state="done", message="complete")
    return 0


def _campaign_conditions(spec):
    from src.gnuradio_phy.closed_loop import EpisodeCondition as E
    if spec.get("smoke"):
        import gnuradio_campaign as gc
        allc = gc.conditions(6)
        return {k: allc[k] for k in ("static_awgn_snr8_J0.05", "step_jammer")}, 6
    c = B.CampaignInputs(**{k: v for k, v in spec.items() if k in B.CampaignInputs.__dataclass_fields__})
    out = {}
    for ch in c.channels:
        chan, fading = B.CHANNELS[ch]
        key = chan.lower() + ("_tv" if fading == "time_varying" else "")
        for s in c.snrs:
            for j in c.jammers:
                out[f"static_{key}_snr{float(s):g}_J{float(j):g}"] = [E(float(s), float(j), chan, fading)] * int(c.episodes)
    return out, int(c.episodes)


def run_campaign(job_dir, spec, st):
    from src.gnuradio_phy import GRPhyConfig
    from src.gnuradio_phy.closed_loop import POLICIES, run_closed_loop, summarise_episode
    if spec.get("smoke"):
        seeds, policies, n_sym, init = [1], list(POLICIES), 4096, "QPSK"
    else:
        err = B.validate_campaign(B.CampaignInputs(**{k: v for k, v in spec.items()
                                                      if k in B.CampaignInputs.__dataclass_fields__}))
        if err:
            st.set(state="invalid", message=json.dumps(err))
            return 1
        seeds, policies, n_sym, init = spec["seeds"], spec["policies"], int(spec["n_symbols"]), spec["initial_modulation"]
    conds, _ = _campaign_conditions(spec)
    total = len(conds) * len(seeds) * len(policies)
    st.set(state="running", total=total, done=0, failed=0, message="running")
    base = GRPhyConfig(n_symbols=n_sym)
    done = failed = 0
    errors, all_steps, all_runs = [], [], []
    for ci, (name, sched) in enumerate(conds.items()):
        for s in seeds:
            for pol in policies:
                try:
                    rows = run_closed_loop(sched, pol, seed=1000 * ci + int(s), base=base, initial_modulation=init,
                                           condition_name=name)
                    summ = summarise_episode(rows)
                    summ["seed"] = int(s)
                    all_steps.extend(rows)
                    all_runs.append(summ)
                    _write_csv(os.path.join(job_dir, "episodes_steps.csv"), all_steps)
                    _write_csv(os.path.join(job_dir, "runs.csv"), all_runs)
                    done += 1
                except Exception as exc:  # recorded, never hidden
                    failed += 1
                    errors.append(f"{name} seed {s} {pol}: {type(exc).__name__}: {exc}")
                    B.write_json(os.path.join(job_dir, "failures.json"), errors)
                st.set(done=done, failed=failed, message=f"{name} ({ci + 1}/{len(conds)})")
    if os.path.exists(os.path.join(job_dir, "runs.csv")):
        import subprocess
        subprocess.run([sys.executable, os.path.join(ROOT, "experiments", "gnuradio_campaign_analysis.py"), ROOT,
                        job_dir], cwd=ROOT, capture_output=True, text=True)
    st.set(state="done" if failed == 0 else "done_with_failures", message=f"{done} runs, {failed} failed")
    return 0


def main(job_dir):
    job = B.read_json(os.path.join(job_dir, "job.json"))
    st = Status(job_dir)
    if not gnuradio_available():
        st.set(state="blocked", message=unavailable_reason())
        return 2
    try:
        if job["kind"] == "simulation":
            return run_simulation(job_dir, job["spec"], st)
        return run_campaign(job_dir, dict(job["spec"], smoke=job["kind"] == "smoke"), st)
    except Exception as exc:
        st.set(state="failed", message=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
