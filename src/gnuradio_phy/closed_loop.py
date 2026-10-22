"""
Episode-based closed loop over the GNU Radio PHY.

This is SEQUENTIAL RECONFIGURATION, not a streaming loop: each episode is one
complete flowgraph execution with a fixed configuration. After episode e finishes,
the policy observes ONLY episode e's export and chooses the modulation of episode
e + 1. Nothing is applied retroactively: the configuration of episode e is frozen
(GRPhyConfig is immutable) before any decision that uses episode e is computed, and
each row records which episode the decision came from.

Policies
    acwra            existing pipeline (Spectrum -> Twin -> Prediction -> Defense ->
                     ACWRA) on each export; its selected modulation is applied next
    no_adaptation    the same pipeline runs and decides, but the decision is NOT
                     applied (initial modulation kept) - isolates the actuation
    fixed_<MOD>      always MOD
    sinr_threshold   BPSK if the previous episode's MEASURED SINR
                     1 / (P_noise + P_jam) < 10 dB, else QPSK (the CL-2 rule, fed
                     with measured instead of configured values)

Pairing: for a given (schedule, seed) every policy sees the same per-episode SNR,
J, channel and seeds (noise, jammer and fade streams), so differences come from
the modulation choices. Bit streams differ in length between modulations.

Metrics (measured from the GNU Radio bits, per episode)
    BER         bit errors / bits compared
    PER         256-bit packets with >= 1 error / packets (uncoded, no ARQ)
    goodput     (1 - PER) * payload bit rate  [BPSK 100 kb/s, QPSK 200 kb/s,
                OFDM-QPSK 160 kb/s after the 64/80 CP overhead]
    SE          goodput / occupied bandwidth  [(1 + rolloff) Rs for PSK, Rs for OFDM]
"""

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.simulink_bridge.pipeline import SimulinkACWRAPipeline

from .config import GRPhyConfig
from .receiver import goodput_bps, spectral_efficiency
from .runner import decide_on_export, run_gnuradio, selected_modulation
from .validation import validate_gnuradio_dict

POLICIES = ("acwra", "no_adaptation", "fixed_BPSK", "fixed_QPSK", "fixed_OFDM-QPSK", "sinr_threshold")
SINR_THRESHOLD_DB = 10.0


@dataclass(frozen=True)
class EpisodeCondition:
    snr_db: float
    interference_power: float = 0.0
    channel: str = "AWGN"
    fading_mode: str = "none"


def episode_seed(seed: int, episode: int) -> int:
    """Shared by every policy, so episodes are paired across policies."""
    return int(seed) * 1000 + int(episode) + 1


def run_closed_loop(
    schedule: List[EpisodeCondition],
    policy: str,
    seed: int,
    *,
    initial_modulation: str = "QPSK",
    base: Optional[GRPhyConfig] = None,
    phy: Callable[[GRPhyConfig], Dict[str, Any]] = run_gnuradio,
    require_gnuradio: bool = False,
    ledger_path: Optional[str] = None,
    condition_name: str = "",
    on_episode: Optional[Callable[[Dict[str, Any], Dict[str, Any], Any], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Run len(schedule) episodes. phy(cfg) must return an export dict
    (run_gnuradio by default); its provenance is recorded per row from the
    validator, so a non-GNU-Radio phy can never be reported as GNU Radio.

    on_episode(row, export, pipeline_result_or_None), if given, is called after each
    episode's decision; it only observes (the dashboard records agent outputs with it).
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; choose from {POLICIES}")
    base = base or GRPhyConfig()
    fixed = policy[len("fixed_"):] if policy.startswith("fixed_") else None
    current = fixed or initial_modulation
    uses_pipeline = policy in ("acwra", "no_adaptation")
    pipeline = SimulinkACWRAPipeline() if uses_pipeline else None
    if pipeline is not None:
        pipeline.reset()
    rows: List[Dict[str, Any]] = []
    decided_by: Optional[int] = None

    for e, cond in enumerate(schedule):
        cfg = base.replace(modulation=current, snr_db=cond.snr_db, interference_power=cond.interference_power,
                           channel=cond.channel, fading_mode=cond.fading_mode, seed=episode_seed(seed, e))
        d = phy(cfg)                                        # episode e runs with a frozen cfg
        row: Dict[str, Any] = {
            "condition": condition_name, "policy": policy, "seed": seed, "episode": e,
            "experiment_id": str(d["experiment_id"]), "content_sha256": str(d["content_sha256"]),
            "modulation_applied": cfg.modulation, "decision_from_episode": decided_by,
            "snr_db_configured": cfg.snr_db, "snr_db_measured": float(d["measured_snr_db"]),
            "interference_power": cfg.interference_power,
            "interference_power_measured": float(d["measured_interference_power"]),
            "channel": cfg.channel, "fading_mode": cfg.fading_mode,
            "ber": float(d["ber"]), "ber_theory": float(d["ber_theory"]), "per": float(d["per"]),
            "bits": int(d["bits_compared"]), "goodput_bps": goodput_bps(cfg, float(d["per"])),
            "spectral_efficiency": spectral_efficiency(cfg, float(d["per"])),
        }
        nxt, decision_info, res = current, {}, None
        if uses_pipeline:
            res = decide_on_export(d, pipeline, require_gnuradio=require_gnuradio, ledger_path=ledger_path,
                                   reset_state=False)    # the twin keeps its history across episodes
            dec = res.decision
            decision_info = {
                "provenance": res.validation.facts.get("provenance", ""),
                "detected_modulation": res.spectrum_result.modulation,
                "detected_confidence": float(res.spectrum_result.classifier_confidence),
                "estimated_snr_db": float(res.spectrum_result.snr_db),
                "risk_score": float(res.snapshot.prediction_result.risk_score),
                "selected_strategy": dec.selected_strategy, "expected_utility": float(dec.expected_utility),
                "acwra_modulation": selected_modulation(res),
            }
            if policy == "acwra":
                nxt = decision_info["acwra_modulation"]
        else:
            rep = validate_gnuradio_dict(d, require_gnuradio=require_gnuradio, ledger_path=ledger_path)
            rep.raise_if_invalid(context=f"episode {e}")
            decision_info["provenance"] = rep.facts.get("provenance", "")
            if policy == "sinr_threshold":
                p_n = 10 ** (-row["snr_db_measured"] / 10)
                sinr_db = -10 * math.log10(p_n + max(row["interference_power_measured"], 0.0))
                decision_info["sinr_db_measured"] = sinr_db
                nxt = "BPSK" if sinr_db < SINR_THRESHOLD_DB else "QPSK"
        row.update(decision_info)
        row["next_modulation"] = nxt
        rows.append(row)
        if on_episode is not None:
            on_episode(row, d, res)
        current, decided_by = nxt, e
    return rows


def summarise_episode(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One run (policy x condition x seed): bit-weighted BER, mean goodput / SE, switches."""
    bits = sum(r["bits"] for r in rows)
    errs = sum(r["ber"] * r["bits"] for r in rows)
    mods = [r["modulation_applied"] for r in rows]
    return {
        "condition": rows[0]["condition"], "policy": rows[0]["policy"], "seed": rows[0]["seed"],
        "episodes": len(rows), "ber": errs / bits if bits else float("nan"),
        "goodput_bps": sum(r["goodput_bps"] for r in rows) / len(rows),
        "spectral_efficiency": sum(r["spectral_efficiency"] for r in rows) / len(rows),
        "per": sum(r["per"] for r in rows) / len(rows),
        "switches": sum(1 for a, b in zip(mods, mods[1:]) if a != b),
        "provenance": "|".join(sorted({str(r.get("provenance", "")) for r in rows})),
    }
