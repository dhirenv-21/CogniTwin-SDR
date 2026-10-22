"""
DIGITAL TWIN FORECAST EVALUATION (no future-data leakage).

For every scenario in config/scenarios/ plus a synthetic linear ramp, the existing
DigitalTwin is fed the observed state at each step. At time t a forecast for t + h
is made from the history up to and including t ONLY, and scored against the
environment's true state at t + h. Two forecasters:

    trend        DigitalTwin.predict_next()  (existing degree-1 extrapolation)
    persistence  the state observed at t     (naive baseline)

skill = 1 - MAE_trend / MAE_persistence   (> 0: the twin beats persistence)

Observations are either exact (the environment's true SNR, as the virtual-RF
orchestrator feeds the twin) or carry Gaussian measurement noise (sigma dB), the
situation of the Simulink bridge, which feeds per-window MEASURED SNR.

    python experiments/digital_twin_forecast_eval.py
    python experiments/digital_twin_forecast_eval.py --noise 0 1 2 --seeds 5

Outputs: results/digital_twin/forecast_eval/{forecast_metrics.csv, summary.md,
forecast_skill.png, config.json}. Synthetic Python environment only.
"""

import argparse
import csv
import glob
import json
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.digital_twin.twin import DigitalTwin
from src.virtual_rf.environment import VirtualRFEnvironment
from src.virtual_rf.scenario import ScenarioEngine
from src.virtual_rf.state import EnvironmentState

OUT_DIR = os.path.join(project_root, "results", "digital_twin", "forecast_eval")
DT = 0.1


def ramp_scenario(duration=3.0, start=25.0, slope=-6.0):
    """SNR falls linearly (one keyframe per step), the case a trend model is built for."""
    n = int(round(duration / DT))
    return {"name": "Synthetic linear ramp", "duration_seconds": duration,
            "keyframes": [{"time_s": round(i * DT, 6), "modulation": "QPSK",
                           "snr_db": start + slope * i * DT, "channel_type": "awgn",
                           "interference_type": "none", "interference_power": 0.0}
                          for i in range(n)]}


def true_trajectory(config, seed):
    env = VirtualRFEnvironment(scenario=ScenarioEngine(config), seed=seed)
    n = int(round(config.get("duration_seconds", 3.0) / DT))
    traj = []
    for _ in range(n):
        s, _ = env.step(DT)
        traj.append((float(s.timestamp_s), float(s.snr_db), float(s.ber), float(s.interference_power),
                     s.channel_type, s.modulation))
    return traj


def evaluate(traj, horizon, noise_db, rng):
    """Return per-step absolute errors (trend, persistence) and #insufficient-history steps."""
    twin = DigitalTwin()
    err_t, err_p, insufficient = [], [], 0
    observed = []
    for k, (t, snr, ber, jam, chan, mod) in enumerate(traj):
        obs_snr = snr + (rng.normal(0.0, noise_db) if noise_db > 0 else 0.0)
        observed.append(obs_snr)
        twin.update(EnvironmentState(timestamp_s=t, modulation=mod, snr_db=obs_snr, ber=ber,
                                     interference_power=jam, channel_type=chan))
        # leakage guard: nothing in the history is later than t
        assert max(s.timestamp_s for s in twin.history.get_history()) <= t + 1e-12
        if k + horizon >= len(traj):
            continue
        pred = twin.predict_next(horizon_seconds=horizon * DT)
        truth = traj[k + horizon][1]
        if pred["prediction_status"] != "SUCCESS":
            insufficient += 1
            continue
        assert abs(pred["predicted_timestamp_s"] - traj[k + horizon][0]) < 1e-6, "horizon misaligned"
        err_t.append(abs(pred["next_snr_db"] - truth))
        err_p.append(abs(obs_snr - truth))
    return np.array(err_t), np.array(err_p), insufficient


# ------------------------------------------------------------------ alternatives
# Evaluated ALONGSIDE the twin's predictor (which is unchanged). Parameters fixed a
# priori, not tuned on these results: alpha 0.5, jump 3 dB, residual 1 dB, window 5.
FORECASTERS = ("twin_trend", "persistence", "exp_smoothing", "changepoint_trend", "trend_fallback")


def forecast_alternatives(ts, ys, t_next, window=5, jump_db=3.0, resid_db=1.0, alpha=0.5):
    """Causal forecasts at t_next from observations (ts, ys) up to now only."""
    def line(tt, yy):
        tt, yy = np.asarray(tt, float), np.asarray(yy, float)
        if tt.size < 2 or np.std(tt) < 1e-12:
            return None
        return np.polyfit(tt, yy, 1)

    out = {"persistence": ys[-1]}
    level = ys[0]
    for y in ys[1:]:
        level = alpha * y + (1 - alpha) * level
    out["exp_smoothing"] = level
    cp = 0
    for i in range(1, len(ys)):
        if abs(ys[i] - ys[i - 1]) > jump_db:
            cp = i
    seg_t, seg_y = ts[cp:][-window:], ys[cp:][-window:]
    p = line(seg_t, seg_y) if len(seg_t) >= 3 else None
    out["changepoint_trend"] = float(np.polyval(p, t_next)) if p is not None else ys[-1]
    wt, wy = ts[-window:], ys[-window:]
    p2 = line(wt, wy) if len(wt) >= window else None
    if p2 is None:
        out["trend_fallback"] = ys[-1]
    else:
        resid = float(np.sqrt(np.mean((np.polyval(p2, wt) - np.asarray(wy)) ** 2)))
        out["trend_fallback"] = float(np.polyval(p2, t_next)) if resid <= resid_db else ys[-1]
    return out


def evaluate_all(traj, horizon, noise_db, rng):
    """Absolute errors per forecaster, scored on the steps where the twin has a forecast."""
    twin = DigitalTwin()
    errs = {f: [] for f in FORECASTERS}
    ts, ys = [], []
    for k, (t, snr, ber, jam, chan, mod) in enumerate(traj):
        obs = snr + (rng.normal(0.0, noise_db) if noise_db > 0 else 0.0)
        ts.append(t)
        ys.append(obs)
        twin.update(EnvironmentState(timestamp_s=t, modulation=mod, snr_db=obs, ber=ber,
                                     interference_power=jam, channel_type=chan))
        if k + horizon >= len(traj):
            continue
        pred = twin.predict_next(horizon_seconds=horizon * DT)
        if pred["prediction_status"] != "SUCCESS":
            continue
        truth = traj[k + horizon][1]
        alt = forecast_alternatives(ts, ys, t + horizon * DT)
        errs["twin_trend"].append(abs(pred["next_snr_db"] - truth))
        for f in FORECASTERS[1:]:
            errs[f].append(abs(alt[f] - truth))
    return {f: np.array(v) for f, v in errs.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Digital Twin forecast evaluation")
    ap.add_argument("--horizons", type=int, nargs="+", default=[1, 2, 5])
    ap.add_argument("--noise", type=float, nargs="+", default=[0.0, 1.0])
    ap.add_argument("--seeds", type=int, default=5, help="noise realisations per configuration")
    ap.add_argument("--out-dir", default=None, help="output folder (default: the committed results folder)")
    args = ap.parse_args(argv)
    global OUT_DIR
    if args.out_dir:
        OUT_DIR = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(project_root, args.out_dir)

    scenarios = {}
    for f in sorted(glob.glob(os.path.join(project_root, "config", "scenarios", "*.json"))):
        with open(f) as fh:
            scenarios[os.path.splitext(os.path.basename(f))[0]] = json.load(fh)
    scenarios["synthetic_ramp"] = ramp_scenario()

    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    for name, cfg in scenarios.items():
        traj = true_trajectory(cfg, seed=42)
        for noise in args.noise:
            for h in args.horizons:
                et_all, ep_all, ins = [], [], 0
                for seed in range(args.seeds if noise > 0 else 1):
                    et, ep, n_ins = evaluate(traj, h, noise, np.random.default_rng(1000 + seed))
                    et_all.append(et)
                    ep_all.append(ep)
                    ins += n_ins
                et, ep = np.concatenate(et_all), np.concatenate(ep_all)
                mae_t, mae_p = float(np.mean(et)), float(np.mean(ep))
                # both ~0 (constant channel, exact observations): skill undefined, report 0
                if mae_p < 1e-9:
                    skill = 0.0 if mae_t < 1e-9 else float("-inf")
                else:
                    skill = 1.0 - mae_t / mae_p
                rows.append({
                    "scenario": name, "noise_db": noise, "horizon_steps": h,
                    "horizon_s": round(h * DT, 3), "n_forecasts": int(et.size),
                    "insufficient_history": ins, "mae_trend_db": round(mae_t, 4),
                    "mae_persistence_db": round(mae_p, 4),
                    "max_err_trend_db": round(float(np.max(et)), 3) if et.size else float("nan"),
                    "skill_vs_persistence": round(skill, 4) if np.isfinite(skill) else skill,
                })

    with open(os.path.join(OUT_DIR, "forecast_metrics.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT_DIR, "config.json"), "w") as fh:
        json.dump({"dt_s": DT, "horizons": args.horizons, "noise_db": args.noise, "seeds": args.seeds,
                   "env_seed": 42, "history_window": DigitalTwin().predictor.history_window,
                   "scenarios": list(scenarios)}, fh, indent=2)

    lines = ["# Digital Twin forecast evaluation", "",
             "Synthetic virtual-RF environment. Forecast at t uses history <= t only; scored "
             "against the true SNR at t+h. `skill` = 1 - MAE_trend/MAE_persistence "
             "(positive: the twin's trend forecast beats repeating the last observation).", "",
             "| scenario | noise dB | h (steps) | n | MAE trend | MAE persist | skill |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['scenario']} | {r['noise_db']:g} | {r['horizon_steps']} | {r['n_forecasts']} | "
                     f"{r['mae_trend_db']:.3f} | {r['mae_persistence_db']:.3f} | {r['skill_vs_persistence']} |")
    alt_rows = []
    for name, cfg in scenarios.items():
        traj = true_trajectory(cfg, seed=42)
        for noise in args.noise:
            for h in args.horizons:
                acc = {f: [] for f in FORECASTERS}
                for seed in range(args.seeds if noise > 0 else 1):
                    e = evaluate_all(traj, h, noise, np.random.default_rng(1000 + seed))
                    for f in FORECASTERS:
                        acc[f].append(e[f])
                row = {"scenario": name, "noise_db": noise, "horizon_steps": h}
                for f in FORECASTERS:
                    row[f"mae_{f}_db"] = round(float(np.mean(np.concatenate(acc[f]))), 4)
                alt_rows.append(row)
    with open(os.path.join(OUT_DIR, "alternatives.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(alt_rows[0].keys()))
        w.writeheader()
        w.writerows(alt_rows)
    lines += ["", "## Alternative forecasters (evaluated alongside; the twin's predictor is unchanged)", "",
              "MAE in dB on the steps where the twin has a forecast. Parameters fixed a priori "
              "(alpha 0.5, jump 3 dB, residual 1 dB, window 5). Lowest MAE per row in **bold**.", "",
              "| scenario | noise | h | " + " | ".join(FORECASTERS) + " |",
              "|---|---|---|" + "---|" * len(FORECASTERS)]
    for r in alt_rows:
        vals = [r[f"mae_{f}_db"] for f in FORECASTERS]
        best = min(vals)
        cells = [f"**{v:.3f}**" if abs(v - best) < 1e-9 else f"{v:.3f}" for v in vals]
        lines.append(f"| {r['scenario']} | {r['noise_db']:g} | {r['horizon_steps']} | " + " | ".join(cells) + " |")
    with open(os.path.join(OUT_DIR, "summary.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    fig, axes = plt.subplots(1, len(args.noise), figsize=(6 * len(args.noise), 4.5), sharey=True, squeeze=False)
    for ax, noise in zip(axes[0], args.noise):
        names = list(scenarios)
        width = 0.8 / len(args.horizons)
        for i, h in enumerate(args.horizons):
            vals = [next(r["mae_trend_db"] - r["mae_persistence_db"] for r in rows
                         if r["scenario"] == n and r["noise_db"] == noise and r["horizon_steps"] == h)
                    for n in names]
            ax.bar(np.arange(len(names)) + i * width, vals, width, label=f"h = {h} step(s)")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(np.arange(len(names)) + 0.4 - width / 2)
        ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
        ax.set_title(f"observation noise {noise:g} dB")
        ax.grid(axis="y", alpha=0.3)
    axes[0][0].set_ylabel("MAE(trend) - MAE(persistence)  [dB]\n< 0: twin forecast better")
    axes[0][0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "forecast_skill.png"), dpi=130)

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
