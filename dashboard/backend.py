"""
Dashboard backend: input validation, job control, result loading.

No Streamlit import (tested in plain Python). Jobs run in a separate worker process
(dashboard/worker.py), so the UI stays responsive and STOP can terminate exactly the
process the dashboard started. Everything the UI shows is read back from files the
worker wrote; nothing is computed for display that the run did not produce.

Layout (all under results/gnuradio/dashboard/, git-ignored):
    runs/<run_id>/       job.json, status.json, episodes.csv, decisions.jsonl, ep<k>.npz
    campaigns/<run_id>/  job.json, status.json, runs.csv, episodes_steps.csv, analysis.md
    run_ledger.jsonl     provenance ledger for dashboard exports
Repository results (BER validation, campaigns, demos, aborted runs, Simulink exports)
are read only.
"""

import csv
import datetime as _dt
import json
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from src.gnuradio_phy.closed_loop import POLICIES  # noqa: E402
from src.gnuradio_phy.config import MODULATIONS, OFDM_N_FFT, GRPhyConfig  # noqa: E402

# COGNITWIN_DASH_DIR redirects all dashboard job output (used by the tests)
DASH = os.environ.get("COGNITWIN_DASH_DIR") or os.path.join(ROOT, "results", "gnuradio", "dashboard")
RUNS = os.path.join(DASH, "runs")
CAMPAIGNS = os.path.join(DASH, "campaigns")
LEDGER = os.path.join(DASH, "run_ledger.jsonl")
WORKER = os.path.join(ROOT, "dashboard", "worker.py")

# UI label -> (channel, fading_mode); only combinations GRPhyConfig accepts
CHANNELS = {
    "AWGN": ("AWGN", "none"),
    "Rayleigh (block)": ("RAYLEIGH", "block"),
    "Rician (block)": ("RICIAN", "block"),
    "Rayleigh (changing)": ("RAYLEIGH", "time_varying"),
    "Rician (changing)": ("RICIAN", "time_varying"),
}
POLICY_LABELS = {
    "acwra": "ACWRA", "fixed_BPSK": "Fixed BPSK", "fixed_QPSK": "Fixed QPSK",
    "fixed_OFDM-QPSK": "Fixed OFDM-QPSK", "sinr_threshold": "SINR Threshold", "no_adaptation": "Non-adaptive",
}
assert set(POLICY_LABELS) == set(POLICIES)

# data classes shown in the run history
SRC_GNURADIO = "GNU Radio"
SRC_MATLAB = "MATLAB (historical)"
SRC_FIXTURE = "Fixture"
SRC_ABORTED = "Aborted"
SRC_INVALID = "Invalid"
SRC_STOPPED = "Stopped"
SRC_RUNNING = "Running"


# ------------------------------------------------------------------ inputs

@dataclass
class SimInputs:
    modulation: str = "QPSK"            # initial modulation (fixed_* policies override it)
    seed: int = 1
    n_symbols: int = 4096
    sps: int = 4
    rolloff: float = 0.35
    channel: str = "AWGN"
    snr_db: float = 10.0
    jammer: float = 0.0
    doppler_fdts: float = 1e-4
    rician_k: float = 2.0
    policy: str = "acwra"
    adaptation: bool = True             # ACWRA only: False -> no_adaptation
    episodes: int = 3

    def effective_policy(self) -> str:
        if self.policy == "acwra" and not self.adaptation:
            return "no_adaptation"
        return self.policy


def validate_inputs(inp: SimInputs) -> Tuple[Optional[GRPhyConfig], Dict[str, str]]:
    """(config, {field: error}). The config is built by GRPhyConfig itself."""
    err: Dict[str, str] = {}
    if inp.modulation not in MODULATIONS:
        err["modulation"] = f"one of {MODULATIONS}"
    if inp.channel not in CHANNELS:
        err["channel"] = f"one of {list(CHANNELS)}"
    if inp.policy not in POLICIES:
        err["policy"] = f"one of {list(POLICY_LABELS.values())}"
    if not 1 <= int(inp.episodes) <= 50:
        err["episodes"] = "1 to 50"
    if not 2 <= int(inp.sps) <= 16:
        err["sps"] = "2 to 16"
    if not 0.0 < float(inp.rolloff) <= 1.0:
        err["rolloff"] = "0 < roll-off <= 1"
    mods = {inp.modulation}
    if inp.policy == "acwra" and inp.adaptation or inp.policy == "sinr_threshold":
        mods |= {"BPSK", "QPSK"}          # what these policies can switch to
    if inp.policy.startswith("fixed_"):
        mods = {inp.policy[len("fixed_"):]}
    if "OFDM-QPSK" in mods and int(inp.n_symbols) % OFDM_N_FFT:
        err["n_symbols"] = f"multiple of {OFDM_N_FFT} for OFDM-QPSK"
    if not 256 <= int(inp.n_symbols) <= 262144:
        err["n_symbols"] = "256 to 262144"
    if err:
        return None, err
    chan, fading = CHANNELS[inp.channel]
    try:
        cfg = GRPhyConfig(modulation=inp.modulation, snr_db=float(inp.snr_db), interference_power=float(inp.jammer),
                          channel=chan, fading_mode=fading, doppler_fdts=float(inp.doppler_fdts),
                          rician_k=float(inp.rician_k), n_symbols=int(inp.n_symbols), sps=int(inp.sps),
                          rolloff=float(inp.rolloff), seed=int(inp.seed))
        for m in mods:                     # every modulation the loop may apply must be valid
            cfg.replace(modulation=m)
    except (ValueError, TypeError) as exc:
        import re
        msg = str(exc)
        key = next((k for k in ("snr_db", "interference_power", "seed", "n_symbols", "doppler_fdts", "rician_k")
                    if re.search(r"\b" + k + r"\b", msg)), "config")
        return None, {{"interference_power": "jammer"}.get(key, key): msg}
    return cfg, {}


@dataclass
class CampaignInputs:
    channels: List[str] = field(default_factory=lambda: ["AWGN", "Rayleigh (block)"])
    snrs: List[float] = field(default_factory=lambda: [4.0, 12.0])
    jammers: List[float] = field(default_factory=lambda: [0.0, 0.2])
    initial_modulation: str = "QPSK"
    seeds: List[int] = field(default_factory=lambda: [1, 2])
    policies: List[str] = field(default_factory=lambda: ["acwra", "fixed_QPSK", "sinr_threshold"])
    episodes: int = 6
    n_symbols: int = 4096

    def n_runs(self) -> int:
        return len(self.channels) * len(self.snrs) * len(self.jammers) * len(self.seeds) * len(self.policies)

    def n_flowgraphs(self) -> int:
        return self.n_runs() * int(self.episodes)


def validate_campaign(c: CampaignInputs) -> Dict[str, str]:
    err = {}
    for name in ("channels", "snrs", "jammers", "seeds", "policies"):
        if not getattr(c, name):
            err[name] = "select at least one"
    if any(ch not in CHANNELS for ch in c.channels):
        err["channels"] = "unsupported channel"
    if any(p not in POLICIES for p in c.policies):
        err["policies"] = "unsupported policy"
    if not 1 <= int(c.episodes) <= 50:
        err["episodes"] = "1 to 50"
    if c.n_runs() > 5000:
        err["size"] = f"{c.n_runs()} runs; limit 5000"
    if not err:
        for ch in c.channels:
            for s in c.snrs:
                for j in c.jammers:
                    _, e = validate_inputs(SimInputs(modulation=c.initial_modulation, channel=ch, snr_db=s, jammer=j,
                                                     n_symbols=c.n_symbols, seed=c.seeds[0]))
                    if e:
                        err["grid"] = f"{ch}, {s} dB, J {j}: {e}"
                        return err
    return err


# ------------------------------------------------------------------ jobs

def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")[:-3]


def new_job_dir(kind: str) -> Tuple[str, str]:
    base = RUNS if kind in ("simulation",) else CAMPAIGNS
    os.makedirs(base, exist_ok=True)
    stem = f"{'sim' if kind == 'simulation' else kind}_{_stamp()}"
    for i in range(1000):
        run_id = stem if i == 0 else f"{stem}_{i}"
        path = os.path.join(base, run_id)
        try:
            os.mkdir(path)                     # atomic: never reuse a folder
            return run_id, path
        except FileExistsError:
            continue
    raise RuntimeError("could not allocate a new job folder")


def write_json(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str)
    os.replace(tmp, path)


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def launch(kind: str, spec: Dict[str, Any], python: Optional[str] = None) -> Tuple[str, str, int]:
    """Start a worker process for a job. Returns (run_id, folder, pid). The caller confirms campaigns."""
    run_id, path = new_job_dir(kind)
    write_json(os.path.join(path, "job.json"), {"kind": kind, "run_id": run_id, "spec": spec,
                                                "created": _dt.datetime.now().isoformat(timespec="seconds")})
    write_json(os.path.join(path, "status.json"), {"state": "queued", "done": 0, "total": 0, "failed": 0})
    log = open(os.path.join(path, "worker.log"), "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([python or sys.executable, WORKER, path], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=flags)
    st = read_json(os.path.join(path, "status.json"), {})
    st["pid"] = proc.pid
    write_json(os.path.join(path, "status.json"), st)
    return run_id, path, proc.pid


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True)
        return str(int(pid)) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def job_status(path: str) -> Dict[str, Any]:
    st = read_json(os.path.join(path, "status.json"), {}) or {}
    if st.get("state") in ("queued", "running") and st.get("pid") and not _pid_alive(int(st["pid"])):
        st = dict(st, state="failed", message=st.get("message") or "worker exited unexpectedly (see worker.log)")
    return st


def stop_job(path: str) -> bool:
    """Terminate a job ONLY if this dashboard started it (folder under results/gnuradio/dashboard)."""
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(DASH) + os.sep):
        raise PermissionError("only jobs started by the dashboard can be stopped")
    st = read_json(os.path.join(path, "status.json"), {}) or {}
    pid = int(st.get("pid") or 0)
    if st.get("state") not in ("queued", "running") or not pid:
        return False
    worker_cmd = _cmdline(pid)
    if worker_cmd is not None and "worker.py" not in worker_cmd:
        raise PermissionError(f"PID {pid} is not a dashboard worker")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.kill(pid, 15)
    st.update(state="stopped", message="stopped from the dashboard")
    write_json(os.path.join(path, "status.json"), st)
    return True


def _cmdline(pid: int) -> Optional[str]:
    if os.name != "nt":
        try:
            return open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
        except OSError:
            return None
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\").CommandLine"],
                         capture_output=True, text=True)
    return out.stdout.strip() or None


def active_jobs() -> List[str]:
    out = []
    for base in (RUNS, CAMPAIGNS):
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                p = os.path.join(base, d)
                if job_status(p).get("state") in ("queued", "running"):
                    out.append(p)
    return out


# ------------------------------------------------------------------ result loading

def load_episodes(run_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(run_dir, "episodes.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def load_decisions(run_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(run_dir, "decisions.jsonl")
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    return out


def load_episode_export(run_dir: str, episode: int):
    """(export dict, ValidationReport) for one episode, revalidated against the dashboard ledger."""
    from src.gnuradio_phy.export import load_export
    from src.gnuradio_phy.validation import validate_gnuradio_dict
    d = load_export(os.path.join(run_dir, f"ep{int(episode)}.npz"))
    return d, validate_gnuradio_dict(d, ledger_path=LEDGER)


def sinr_db(d: Dict[str, Any]) -> float:
    """Measured post-fade SINR from the exported branches: mean|h|^2 P_tx / (P_noise + P_jam)."""
    g2 = np.abs(np.asarray(d["channel_gain_iq"])) ** 2
    p_tx = np.abs(np.asarray(d["tx_iq"])) ** 2
    p_nj = np.abs(np.asarray(d["noise_iq"])) ** 2 + np.abs(np.asarray(d["interference_iq"])) ** 2
    return 10 * math.log10(max(float(np.mean(g2 * p_tx)), 1e-300) / max(float(np.mean(p_nj)), 1e-300))


def risk_gate(decision: Optional[Dict[str, Any]]) -> str:
    if not decision or "candidates" not in decision:
        return "n/a"
    c = decision["candidates"]
    return "CLOSED (Keep Current only)" if list(c) == ["Keep Current"] else f"OPEN ({len(c)} candidates)"


def signal_products(d: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """Arrays for the plots, all derived from one export (no other data)."""
    from scipy.signal import welch
    from src.gnuradio_phy.config import OFDM_CP_LEN
    iq = np.asarray(d["iq_samples"], dtype=np.complex128)
    h = np.asarray(d["channel_gain_iq"], dtype=np.complex128)
    fs = float(d["sample_rate"])
    if str(d["modulation"]) == "OFDM-QPSK":
        L = OFDM_N_FFT + OFDM_CP_LEN
        n = iq.size // L
        blk = iq[: n * L].reshape(n, L)[:, OFDM_CP_LEN:]
        hs = h[: n * L].reshape(n, L)[:, OFDM_CP_LEN:].mean(axis=1)
        eq = (np.fft.fft(blk, axis=1) / math.sqrt(OFDM_N_FFT) / hs[:, None]).reshape(-1)
    else:
        eq = iq / np.where(np.abs(h) > 0, h, 1.0)
    nfft = 1024 if iq.size >= 1024 else int(2 ** math.floor(math.log2(iq.size)))
    spec = np.fft.fftshift(np.abs(np.fft.fft(iq[:nfft] * np.hanning(nfft))) ** 2)
    f_spec = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    f_psd, psd = welch(iq, fs=fs, nperseg=min(512, iq.size), return_onesided=False, scaling="density")
    order = np.argsort(f_psd)
    return {"iq": iq, "tx": np.asarray(d["tx_iq"], dtype=np.complex128), "eq": eq, "fs": fs,
            "f_spec": f_spec, "spec_db": 10 * np.log10(spec / max(spec.max(), 1e-300) + 1e-15),
            "f_psd": f_psd[order], "psd_db": 10 * np.log10(psd[order] + 1e-300)}


def _row(run_id, source, mod, chan, snr, jam, ber, policy, action, status, path, kind):
    return {"Run ID": run_id, "Source": source, "Modulation": mod, "Channel": chan, "SNR": snr, "Jammer": jam,
            "BER": ber, "Policy": policy, "Action": action, "Status": status, "_path": path, "_kind": kind}


def run_history() -> List[Dict[str, Any]]:
    """Every run the dashboard can show, each labelled with its data class."""
    rows: List[Dict[str, Any]] = []
    # dashboard simulations
    if os.path.isdir(RUNS):
        for rid in sorted(os.listdir(RUNS), reverse=True):
            p = os.path.join(RUNS, rid)
            job = read_json(os.path.join(p, "job.json"), {}) or {}
            st = job_status(p)
            sp = job.get("spec", {})
            eps = load_episodes(p)
            last = eps[-1] if eps else {}
            state = st.get("state", "?")
            prov = {e.get("provenance") for e in eps}
            src = {"running": SRC_RUNNING, "queued": SRC_RUNNING, "stopped": SRC_STOPPED,
                   "failed": SRC_INVALID}.get(state, SRC_GNURADIO if prov == {"gnuradio_export"} else
                                              SRC_FIXTURE if prov == {"python_fixture"} else SRC_INVALID)
            ber = np.mean([float(e["ber"]) for e in eps]) if eps else None
            rows.append(_row(rid, src, sp.get("modulation", ""), sp.get("channel", ""), sp.get("snr_db"),
                             sp.get("jammer"), ber, POLICY_LABELS.get(sp.get("policy_effective", ""), ""),
                             last.get("selected_strategy") or last.get("next_modulation", ""), state, p, "dash_run"))
    # dashboard campaigns
    if os.path.isdir(CAMPAIGNS):
        for rid in sorted(os.listdir(CAMPAIGNS), reverse=True):
            p = os.path.join(CAMPAIGNS, rid)
            st = job_status(p)
            state = st.get("state", "?")
            src = {"running": SRC_RUNNING, "queued": SRC_RUNNING, "stopped": SRC_STOPPED,
                   "failed": SRC_INVALID}.get(state, SRC_GNURADIO)
            rows.append(_row(rid, src, "mixed", "grid", "", "", None, "campaign", "", state, p, "campaign"))
    # repository campaigns (read only)
    camp = os.path.join(ROOT, "results", "gnuradio", "campaign")
    if os.path.isdir(camp):
        for rid in sorted(os.listdir(camp), reverse=True):
            p = os.path.join(camp, rid)
            if os.path.exists(os.path.join(p, "ABORTED.md")):
                rows.append(_row(rid, SRC_ABORTED, "mixed", "grid", "", "", None, "campaign", "", "aborted", p, "aborted"))
            elif os.path.exists(os.path.join(p, "runs.csv")):
                rows.append(_row(rid, SRC_GNURADIO, "mixed", "grid", "", "", None, "campaign", "", "done", p, "campaign"))
    # repository demo runs (read only)
    demo = os.path.join(ROOT, "results", "gnuradio", "demo")
    if os.path.isdir(demo):
        for rid in sorted(os.listdir(demo), reverse=True):
            p = os.path.join(demo, rid)
            npz = [f for f in os.listdir(p) if f.endswith(".npz")]
            if npz:
                rows.append(_row(rid, SRC_GNURADIO, npz[0].split("-")[1], npz[0].split("-")[2], "", "", None, "demo",
                                 "", "done", os.path.join(p, npz[0]), "npz"))
    # historical MATLAB/Simulink exports (read only; metadata only)
    for sub in ("baseline", ""):
        d = os.path.join(ROOT, "simulink", "results", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".mat"):
                rows.append(_row(f[:-4], SRC_MATLAB, "", "", "", "", None, "", "", "historical",
                                 os.path.join(d, f), "mat"))
    fx = os.path.join(ROOT, "simulink", "results", "campaign_fixture")
    if os.path.isdir(fx):
        for f in sorted(os.listdir(fx))[:50]:
            if f.endswith(".mat"):
                rows.append(_row(f[:-4], SRC_FIXTURE, "", "", "", "", None, "", "", "fixture", os.path.join(fx, f), "mat"))
    return rows


def mat_summary(path: str) -> Dict[str, Any]:
    """Validated metadata of a historical MAT export (no plots synthesised)."""
    from src.simulink_bridge.receiver import SimulinkReceiver
    from src.simulink_bridge.validation import MeasurementValidationError
    try:
        m, rep = SimulinkReceiver.load_and_validate(path, strict=False)
    except (MeasurementValidationError, OSError, KeyError, ValueError) as exc:
        return {"valid": False, "error": str(exc)}
    return {"valid": rep.ok, "provenance": m.provenance, "modulation": m.modulation, "snr_db": m.snr_db,
            "interference_power": m.interference_power, "channel": m.channel_type, "ber": m.ber,
            "samples": m.num_samples, "summary": rep.summary(), "errors": rep.errors[:5], "iq": m.iq_samples}


def ber_curves() -> Dict[str, List[Dict[str, Any]]]:
    """BER/PER vs SNR from executed GNU Radio data only: BER validation runs + AWGN campaign episodes."""
    out: Dict[str, List[Dict[str, Any]]] = {"ber_validation": [], "campaign_per": []}
    bv = os.path.join(ROOT, "results", "gnuradio", "ber_validation")
    if os.path.isdir(bv):
        for rid in sorted(os.listdir(bv)):
            p = os.path.join(bv, rid, "ber.csv")
            if os.path.exists(p):
                with open(p, newline="") as fh:
                    for r in csv.DictReader(fh):
                        out["ber_validation"].append({"run": rid, "modulation": r["modulation"],
                                                      "snr_db": float(r["snr_db"]), "ber": float(r["ber"]),
                                                      "lo": float(r["ci_low"]), "hi": float(r["ci_high"]),
                                                      "theory": float(r["ber_theory"])})
    agg: Dict[Tuple[str, float], List[Tuple[float, float]]] = {}
    for p in campaign_dirs():
        f = os.path.join(p, "episodes_steps.csv")
        if not os.path.exists(f):
            continue
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("channel") == "AWGN" and r.get("provenance") == "gnuradio_export":
                    agg.setdefault((r["modulation_applied"], round(float(r["snr_db_configured"]), 2)), []).append(
                        (float(r["per"]), float(r["ber"])))
    for (mod, snr), v in sorted(agg.items()):
        out["campaign_per"].append({"modulation": mod, "snr_db": snr, "per": float(np.mean([x[0] for x in v])),
                                    "ber": float(np.mean([x[1] for x in v])), "episodes": len(v)})
    return out


def campaign_dirs() -> List[str]:
    """Completed (non-aborted) campaigns: repository ones and dashboard ones."""
    out = []
    for base in (os.path.join(ROOT, "results", "gnuradio", "campaign"), CAMPAIGNS):
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                p = os.path.join(base, d)
                if os.path.exists(os.path.join(p, "runs.csv")) and not os.path.exists(os.path.join(p, "ABORTED.md")):
                    out.append(p)
    return out


def campaign_comparison(path: str) -> Dict[str, Any]:
    """Policy means and condition-level paired ACWRA - baseline statistics (existing CL-2 routine)."""
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import closed_loop_evaluation as cle
    with open(os.path.join(path, "runs.csv"), newline="") as fh:
        runs = list(csv.DictReader(fh))
    for r in runs:
        for k in ("goodput_bps", "ber", "per", "spectral_efficiency", "switches"):
            r[k] = float(r[k])
        r["seed"] = int(r["seed"])
    pols = sorted({r["policy"] for r in runs})
    conds = sorted({r["condition"] for r in runs})
    means = [{"policy": p, "goodput_kbps": float(np.mean([r["goodput_bps"] for r in runs if r["policy"] == p])) / 1e3,
              "ber": float(np.mean([r["ber"] for r in runs if r["policy"] == p])),
              "per": float(np.mean([r["per"] for r in runs if r["policy"] == p])),
              "runs": sum(1 for r in runs if r["policy"] == p)} for p in pols]
    paired = []
    if "acwra" in pols:
        for b in pols:
            if b == "acwra":
                continue
            for m in ("goodput_bps", "ber"):
                res = cle.paired_comparison(runs, "acwra", b, m, conds)
                if res:
                    paired.append(res)
    return {"means": means, "paired": paired, "conditions": len(conds), "runs": len(runs)}


def gnuradio_status() -> Dict[str, Any]:
    from src.gnuradio_phy.availability import probe
    ok, ver, detail = probe()
    return {"available": ok, "version": ver, "detail": detail, "python": sys.executable}


def spec_from_inputs(inp: SimInputs) -> Dict[str, Any]:
    d = asdict(inp)
    d["policy_effective"] = inp.effective_policy()
    return d
