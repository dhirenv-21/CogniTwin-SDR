"""
INDEPENDENT VERIFICATION OF SIMULINK MAT EXPORTS.

Recomputes every physical quantity from the raw arrays in the MAT file and compares
against what MATLAB reported. Nothing here trusts a variable name: signal, noise and
interference powers are computed from `tx_iq`, `noise_iq` and `interference_iq`
directly, and the BER is re-derived by demodulating the received waveform in Python.

This is the cross-check that would have caught the zero-signal PHY fault immediately:
`signal_present` compares the least-squares channel estimate against the pure-noise
floor P_rx/N, which is exactly where the broken build's |h| ~ 0.0037 came from.

In directory mode it also compares the noise arrays of runs with DIFFERENT seeds.
The v3 Simulink build failed that test: randn inside PHY_Channel ignored every
seed, so all runs shared one noise realisation.

BER theory (coherent, Gray mapped, SINR measured from the arrays):
    QPSK, OFDM-QPSK : Q(sqrt(SINR))        BPSK : Q(sqrt(2*SINR))

    python experiments/verify_simulink_mat.py --dir simulink/results/baseline
    python experiments/verify_simulink_mat.py --mat simulink/results/sim_qpsk_snr10_int0_awgn.mat
"""

import argparse
import glob
import math
import os
import sys
from typing import Any, Dict, List, Optional

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import numpy as np
import scipy.io as sio
from scipy.special import erfc

from src.simulink_bridge.validation import (
    OFDM_CP_LEN,
    OFDM_N_FFT,
    check_modulation_signature,
    find_shared_noise_realisations,
    flatten_matlab_iq,
)

BAR = "=" * 92

# Acceptance tolerances, fixed here rather than chosen after seeing results.
TOL = {
    "power_rel": 1e-9,        # recomputed vs MATLAB-reported power
    "db_abs": 0.05,           # recomputed vs MATLAB-reported dB figures
    "noise_vs_nominal_db": 0.5,
    "sir_vs_nominal_db": 0.5,
    "signal_margin_db": 10.0,  # |h_LS|^2 above the pure-noise floor P_rx/N
    "residual": 1e-9,          # max|rx - (h*tx + jam + noise)|
    "ber_abs": 2.0e-3,
    "ber_rel": 0.35,
    "jam_corr_sigma": 5.0,     # |corr(tx,jam)| below this many 1/sqrt(N)
    "noise_iq_balance_db": 0.5,  # |10log10(P_noise,I / P_noise,Q)|
    "power_budget_sigma": 6.0,   # P_rx vs P_sig + P_noise + P_jam, in cross-term sigmas
}


def ber_theory_fn(modulation: str, sinr_lin: float) -> float:
    """Coherent Gray-mapped BER. BPSK sees only the in-phase half of the noise."""
    if modulation.upper() == "BPSK":
        return q_func(math.sqrt(2.0 * sinr_lin))
    return q_func(math.sqrt(sinr_lin))


def q_func(x: float) -> float:
    return 0.5 * erfc(x / math.sqrt(2.0))


def _scalar(mat: Dict[str, Any], key: str, default=None):
    if key not in mat:
        return default
    v = np.asarray(mat[key])
    if v.dtype.kind in ("U", "S"):
        return str(v.reshape(-1)[0])
    if v.size == 0:
        return default
    return float(np.real(v.reshape(-1)[0]))


def _text(mat: Dict[str, Any], key: str, default="") -> str:
    if key not in mat:
        return default
    v = np.asarray(mat[key])
    if v.dtype.kind in ("U", "S"):
        flat = v.reshape(-1)
        return "".join(str(c) for c in flat.tolist()).strip()
    return default


def _demod_qpsk_bpsk(rx_eq: np.ndarray, m_order: int) -> np.ndarray:
    """Nearest-constellation demapping, inverse of cognitwin_waveform.m."""
    offset = math.pi / 4 if m_order == 4 else 0.0
    const = np.exp(1j * (2 * np.pi * np.arange(m_order) / m_order + offset))
    idx = np.argmin(np.abs(rx_eq[:, None] - const[None, :]), axis=1)
    gray = idx ^ (idx >> 1)                       # binary -> Gray
    k = int(math.log2(m_order))
    bits = np.zeros(idx.size * k, dtype=np.int8)
    for b in range(k):
        bits[b::k] = (gray >> (k - 1 - b)) & 1    # MSB first
    return bits


def _demod_ofdm_qpsk(rx_eq: np.ndarray, n_fft: int = OFDM_N_FFT, cp_len: int = OFDM_CP_LEN) -> np.ndarray:
    """Strip CP, unitary FFT, QPSK demap. Inverse of cognitwin_waveform.m OFDM-QPSK."""
    sym_len = n_fft + cp_len
    n_sym = rx_eq.size // sym_len
    if n_sym == 0:
        return np.zeros(0, dtype=np.int8)
    blocks = rx_eq[: n_sym * sym_len].reshape(n_sym, sym_len)[:, cp_len:]
    grid = np.fft.fft(blocks, n=n_fft, axis=1) / math.sqrt(n_fft)
    return _demod_qpsk_bpsk(grid.reshape(-1), 4)


class Check:
    def __init__(self, name: str, ok: Optional[bool], detail: str):
        self.name, self.ok, self.detail = name, ok, detail

    @property
    def tag(self) -> str:
        if self.ok is None:
            return "SKIP"
        return "PASS" if self.ok else "FAIL"


def verify_mat(path: str) -> List[Check]:
    checks: List[Check] = []
    mat = sio.loadmat(path)

    def add(name, ok, detail):
        checks.append(Check(name, ok, detail))

    # A results table (e.g. baseline_results.mat) is not a measurement export.
    if not any(k in mat for k in ("iq_samples", "snr_db", "modulation")):
        add("measurement_file", None,
            "not a measurement export (no iq_samples / snr_db / modulation) - skipped")
        return checks

    # ---- provenance ------------------------------------------------------
    source = _text(mat, "source", "unknown")
    header = str(mat.get("__header__", b""))
    written_by_matlab = "PCWIN" in header or "GLNX" in header or "MACI" in header or "maci" in header
    add("provenance", source.lower().startswith("simulink"),
        f"source='{source}'  MAT header: {header[:70]}"
        + ("  [written by MATLAB]" if written_by_matlab else "  [NOT written by MATLAB]"))

    # ---- arrays ----------------------------------------------------------
    if "iq_samples" not in mat:
        add("arrays_present", False, "no iq_samples in file")
        return checks
    rx = flatten_matlab_iq(mat["iq_samples"])
    n = rx.size

    tx = flatten_matlab_iq(mat["tx_iq"]) if "tx_iq" in mat else None
    noise = flatten_matlab_iq(mat["noise_iq"]) if "noise_iq" in mat else None
    jam = flatten_matlab_iq(mat["interference_iq"]) if "interference_iq" in mat else None

    checks_passed = _scalar(mat, "checks_passed")
    if checks_passed is not None:
        add("matlab_checks_passed", checks_passed == 1.0,
            f"checks_passed = {checks_passed:g} (0 means MATLAB recorded a failed PHY check)")

    add("arrays_present", tx is not None,
        f"rx {n} samples"
        + (f", tx {tx.size}" if tx is not None else ", NO tx reference")
        + (f", noise {noise.size}" if noise is not None else ", NO noise array")
        + (f", jam {jam.size}" if jam is not None else ", NO interference array"))

    fs = _scalar(mat, "sample_rate", 100000.0)
    snr_nominal = _scalar(mat, "snr_db", float("nan"))
    p_nominal = _scalar(mat, "interference_power", 0.0)
    modulation = _text(mat, "modulation", "QPSK")
    channel = _text(mat, "channel_type", "AWGN")

    # ---- sample counts / time vector -------------------------------------
    n_declared = _scalar(mat, "num_samples", n)
    add("sample_count", int(n_declared) == n,
        f"logged {n}, declared {int(n_declared)}")

    if "time_vector" in mat:
        tv = np.asarray(mat["time_vector"]).reshape(-1).astype(float)
        expect = np.arange(n) / fs
        terr = float(np.max(np.abs(tv - expect))) if tv.size == n else float("inf")
        add("time_vector", tv.size == n and terr < 1e-12,
            f"length {tv.size}, max|t - (0:N-1)/Fs| = {terr:.3e}, Fs = {fs:.1f} Hz")
        stop = _scalar(mat, "sim_stop_time")
        if stop is not None:
            add("stop_time", abs(stop - (n - 1) / fs) < 1e-12,
                f"StopTime = {stop:.9g} s, required (N-1)/Fs = {(n-1)/fs:.9g} s")
    else:
        add("time_vector", None, "no time_vector in file")

    # ---- channel gain ----------------------------------------------------
    h_re = _scalar(mat, "channel_gain_real")
    h_im = _scalar(mat, "channel_gain_imag")
    h = complex(h_re, h_im) if h_re is not None else None

    if tx is None:
        add("independent_powers", None, "no tx reference; powers cannot be separated")
        return checks

    m = min(n, tx.size)
    rx, tx = rx[:m], tx[:m]

    # ---- THE decisive check: is the wanted signal actually in rx? ---------
    h_ls = complex(np.vdot(tx, rx) / np.vdot(tx, tx))
    p_rx = float(np.mean(np.abs(rx) ** 2))
    noise_floor = p_rx / m                     # E|h_LS|^2 when rx is pure noise
    margin_db = 10 * math.log10(max(abs(h_ls) ** 2, 1e-300) / max(noise_floor, 1e-300))
    add("wanted_signal_present", margin_db > TOL["signal_margin_db"],
        f"|h_LS|^2 = {abs(h_ls)**2:.6g}, pure-noise floor P_rx/N = {noise_floor:.6g}, "
        f"margin = {margin_db:.1f} dB (need > {TOL['signal_margin_db']:.0f} dB)")

    if h is not None:
        rel = abs(h_ls - h) / max(abs(h), 1e-300)
        add("ls_matches_reported_h", rel < 0.25,
            f"reported h = {h.real:.4f}{h.imag:+.4f}j (|h| = {abs(h):.4f}), "
            f"LS = {h_ls.real:.4f}{h_ls.imag:+.4f}j (|h| = {abs(h_ls):.4f}), rel err {rel:.4f}")
    else:
        add("ls_matches_reported_h", None, "no channel_gain_real/imag in file")

    # ---- independently recomputed powers ---------------------------------
    p_tx = float(np.mean(np.abs(tx) ** 2))
    add("tx_unit_power", abs(p_tx - 1.0) < 1e-6, f"mean|tx|^2 = {p_tx:.9f}")

    sig_ok, sig_detail = check_modulation_signature(tx, modulation)
    add("tx_matches_modulation", sig_ok, f"label '{modulation}': {sig_detail}")

    if h is None:
        h = h_ls
    sig = h * tx
    p_sig = float(np.mean(np.abs(sig) ** 2))

    if noise is not None and jam is not None:
        noise, jam = noise[:m], jam[:m]
        p_noise = float(np.mean(np.abs(noise) ** 2))
        p_jam = float(np.mean(np.abs(jam) ** 2))

        resid = float(np.max(np.abs(rx - (sig + jam + noise))))
        add("rx_equals_model_sum", resid < TOL["residual"],
            f"max|rx - (h*tx + jam + noise)| = {resid:.3e}")

        # jam must be independent of tx (guards the coherent-copy bug)
        corr = float(abs(np.vdot(tx, jam)) /
                     math.sqrt(float(np.vdot(tx, tx).real) * max(float(np.vdot(jam, jam).real), 1e-300))) \
            if p_jam > 0 else 0.0
        thr = TOL["jam_corr_sigma"] / math.sqrt(m)
        add("jam_independent_of_tx", corr < thr if p_jam > 0 else True,
            f"|corr(tx, jam)| = {corr:.5f} (threshold {thr:.5f})" if p_jam > 0
            else "interference disabled")

        if p_jam > 0 and p_noise > 0:
            cnj = float(abs(np.vdot(noise, jam)) /
                        math.sqrt(float(np.vdot(noise, noise).real) * float(np.vdot(jam, jam).real)))
            add("noise_independent_of_jam", cnj < thr,
                f"|corr(noise, jam)| = {cnj:.5f} (threshold {thr:.5f})")
        else:
            add("noise_independent_of_jam", None, "interference disabled")

        v_i = float(np.mean(noise.real ** 2))
        v_q = float(np.mean(noise.imag ** 2))
        if v_i > 0 and v_q > 0:
            bal = 10 * math.log10(v_i / v_q)
            add("noise_is_circular", abs(bal) < TOL["noise_iq_balance_db"],
                f"P_noise,I / P_noise,Q = {bal:.3f} dB (must be within {TOL['noise_iq_balance_db']} dB)")
        elif v_i > 0 or v_q > 0:
            add("noise_is_circular", False,
                f"P_noise,I = {v_i:.3g}, P_noise,Q = {v_q:.3g}: one quadrature carries no noise")
        else:
            add("noise_is_circular", None, "noise_iq is identically zero")

        # Fading and interference must show up in the received power exactly as
        # the components predict; cross terms are O(1/sqrt(N)).
        budget = p_sig + p_noise + p_jam
        slack = TOL["power_budget_sigma"] * math.sqrt(
            2.0 * (p_sig * p_noise + p_sig * p_jam + p_noise * p_jam) / m) + 1e-12
        add("rx_power_matches_components", abs(p_rx - budget) <= slack,
            f"P_rx = {p_rx:.6f} vs |h|^2 P_tx + P_noise + P_jam = {budget:.6f} "
            f"(|h|^2 = {abs(h)**2:.4f}; tolerance {slack:.2e})")
    else:
        # Fall back to the LS residual split when the model did not log them.
        p_noise = float(np.mean(np.abs(rx - sig) ** 2)) - max(p_nominal, 0.0)
        p_noise = max(p_noise, 1e-300)
        p_jam = max(p_nominal, 0.0)
        add("rx_equals_model_sum", None, "noise_iq / interference_iq not in file")
        add("jam_independent_of_tx", None, "interference_iq not in file")

    snr_db = 10 * math.log10(p_sig / max(p_noise, 1e-300))
    sir_db = 10 * math.log10(p_sig / p_jam) if p_jam > 0 else float("inf")
    sinr_db = 10 * math.log10(p_sig / max(p_noise + p_jam, 1e-300))

    add("recomputed_powers", True,
        f"P_sig = {p_sig:.6f}  P_noise = {p_noise:.6f}  P_jam = {p_jam:.6f}  P_rx = {p_rx:.6f}")
    add("recomputed_snr_sir_sinr", True,
        f"SNR = {snr_db:.3f} dB   SIR = {sir_db:.3f} dB   SINR = {sinr_db:.3f} dB")

    # ---- agreement with what MATLAB reported ------------------------------
    for key, mine, label in (
        ("measured_signal_power", p_sig, "P_sig"),
        ("measured_noise_power", p_noise, "P_noise"),
        ("measured_interference_power", p_jam, "P_jam"),
    ):
        theirs = _scalar(mat, key)
        if theirs is None:
            add(f"matlab_agrees_{label}", None, f"{key} not in file")
        else:
            rel = abs(theirs - mine) / max(abs(mine), 1e-300)
            add(f"matlab_agrees_{label}", rel < 1e-6,
                f"MATLAB {theirs:.9g} vs Python {mine:.9g} (rel {rel:.2e})")

    snr_tx_ref_db = 10 * math.log10(p_tx / max(p_noise, 1e-300))
    for key, mine, label in (
        ("measured_snr_db", snr_db, "SNR"),
        ("measured_snr_tx_ref_db", snr_tx_ref_db, "SNR_tx_ref"),
        ("measured_sinr_db", sinr_db, "SINR"),
    ):
        theirs = _scalar(mat, key)
        if theirs is None or not np.isfinite(theirs):
            add(f"matlab_agrees_{label}_db", None, f"{key} absent or non-finite")
        else:
            add(f"matlab_agrees_{label}_db", abs(theirs - mine) < TOL["db_abs"],
                f"MATLAB {theirs:.3f} dB vs Python {mine:.3f} dB")

    # ---- nominal-parameter agreement --------------------------------------
    if np.isfinite(snr_nominal):
        expect_noise = 10 ** (-snr_nominal / 10.0)
        err = abs(10 * math.log10(max(p_noise, 1e-300) / expect_noise))
        add("noise_matches_nominal_snr", err < TOL["noise_vs_nominal_db"],
            f"P_noise = {p_noise:.6g}, 10^(-SNR/10) = {expect_noise:.6g} "
            f"for nominal SNR {snr_nominal:.1f} dB ({err:.2f} dB error)")

    if p_nominal > 0:
        expect_sir = -10 * math.log10(p_nominal) + 10 * math.log10(abs(h) ** 2)
        err = abs(sir_db - expect_sir)
        add("sir_matches_nominal", err < TOL["sir_vs_nominal_db"],
            f"SIR = {sir_db:.3f} dB, expected 10log10(|h|^2/P) = {expect_sir:.3f} dB "
            f"({err:.3f} dB error)")
    else:
        add("sir_matches_nominal", None, "interference disabled")

    # ---- independently recomputed BER -------------------------------------
    ber_reported = _scalar(mat, "ber")
    mod_u = modulation.upper()
    psk_1sps = mod_u in ("BPSK", "QPSK") and _scalar(mat, "samples_per_symbol", 1.0) == 1.0
    is_ofdm = mod_u in ("OFDM-QPSK", "OFDM_QPSK", "OFDM")
    if psk_1sps or is_ofdm:
        rx_eq = rx / h
        # Re-derive the transmitted bits from the transmitted samples themselves,
        # so this path shares nothing with the MATLAB demodulator.
        if is_ofdm:
            bits_rx = _demod_ofdm_qpsk(rx_eq)
            bits_tx = _demod_ofdm_qpsk(tx)
        else:
            m_order = 2 if mod_u == "BPSK" else 4
            bits_rx = _demod_qpsk_bpsk(rx_eq, m_order)
            bits_tx = _demod_qpsk_bpsk(tx, m_order)
        nb = min(bits_rx.size, bits_tx.size)
        ber_py = float(np.mean(bits_rx[:nb] != bits_tx[:nb])) if nb else float("nan")

        sinr_lin = p_sig / max(p_noise + p_jam, 1e-300)
        ber_theory = ber_theory_fn(mod_u, sinr_lin)

        if ber_reported is not None:
            add("ber_matches_matlab", abs(ber_py - ber_reported) < 5e-4,
                f"Python {ber_py:.6f} vs MATLAB {ber_reported:.6f} over {nb} bits")
        if ber_theory > 0.005:
            ok = abs(ber_py - ber_theory) <= TOL["ber_rel"] * ber_theory
        else:
            ok = abs(ber_py - ber_theory) <= TOL["ber_abs"]
        theory_txt = "Q(sqrt(2*SINR))" if mod_u == "BPSK" else "Q(sqrt(SINR))"
        add("ber_matches_theory", ok,
            f"measured {ber_py:.6f}, theory {theory_txt} = {ber_theory:.6f} at SINR {sinr_db:.2f} dB")
        add("ber_not_coinflip", ber_py < 0.45 or sinr_db < 0.0,
            f"BER {ber_py:.6f} at SINR {sinr_db:.2f} dB "
            f"(~0.5 with positive SINR would mean the signal is absent)")
    else:
        add("ber_matches_theory", None,
            f"independent Python demodulation not implemented for {modulation} (sps="
            f"{_scalar(mat, 'samples_per_symbol', 1.0):g})")

    return checks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Independently verify Simulink MAT exports")
    ap.add_argument("--mat", help="single MAT file")
    ap.add_argument("--dir", help="directory of MAT files")
    ap.add_argument("--quiet", action="store_true", help="only print failures")
    args = ap.parse_args(argv)

    files: List[str] = []
    if args.mat:
        files = [args.mat]
    elif args.dir:
        files = sorted(glob.glob(os.path.join(args.dir, "**", "*.mat"), recursive=True))
    else:
        for d in (os.path.join("simulink", "results", "baseline"),
                  os.path.join("simulink", "results")):
            files = sorted(glob.glob(os.path.join(d, "*.mat")))
            if files:
                break

    if not files:
        print("No MAT files found. Produce some with:")
        print("    cd simulink/matlab; run_baseline_tests")
        return 1

    print(BAR)
    print("INDEPENDENT VERIFICATION OF SIMULINK MAT EXPORTS")
    print(BAR)
    print(f"Files: {len(files)}\n")

    totals = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    failing_files: List[str] = []
    noise_records = []
    jam_records = []

    for path in files:
        try:
            checks = verify_mat(path)
        except Exception as exc:
            print(f"[ERROR] {path}: {type(exc).__name__}: {exc}")
            totals["FAIL"] += 1
            failing_files.append(path)
            continue

        noise_rec, jam_rec = _realisation_records(path)
        if noise_rec is not None:
            noise_records.append(noise_rec)
        if jam_rec is not None:
            jam_records.append(jam_rec)

        n_fail = sum(1 for c in checks if c.ok is False)
        for c in checks:
            totals[c.tag] += 1
        if n_fail:
            failing_files.append(path)

        if args.quiet and not n_fail:
            continue

        print(f"--- {os.path.basename(path)}   ({'OK' if not n_fail else f'{n_fail} FAILED'})")
        for c in checks:
            if args.quiet and c.ok is not False:
                continue
            print(f"    [{c.tag}] {c.name:<32} {c.detail}")
        print()

    shared = report_shared_realisations(noise_records, jam_records)
    if shared:
        totals["FAIL"] += 1

    print(BAR)
    print(f"TOTALS: {totals['PASS']} pass, {totals['FAIL']} fail, {totals['SKIP']} skip")
    if failing_files:
        print(f"\n{len(failing_files)} file(s) with failures:")
        for f in failing_files:
            print(f"  {f}")
    print(BAR)
    return 1 if (failing_files or shared) else 0


def _realisation_records(path: str):
    """(label, seed, array) for the noise and jammer of one export, or None."""
    try:
        mat = sio.loadmat(path)
    except Exception:
        return None, None
    seed = _scalar(mat, "noise_seed")
    if seed is None:
        seed = _scalar(mat, "seed")
    label = os.path.basename(path)
    noise = flatten_matlab_iq(mat["noise_iq"]) if "noise_iq" in mat else None
    jam = flatten_matlab_iq(mat["interference_iq"]) if "interference_iq" in mat else None
    return ((label, seed, noise) if noise is not None else None,
            (label, seed, jam) if jam is not None else None)


def report_shared_realisations(noise_records, jam_records) -> int:
    """Print and count different-seed pairs that share a noise/jammer draw."""
    if len(noise_records) < 2:
        return 0
    print("--- CROSS-FILE: noise / jammer realisation independence across seeds")
    total = 0
    for what, recs in (("noise_iq", noise_records), ("interference_iq", jam_records)):
        seeds = sorted({r[1] for r in recs if r[1] is not None})
        pairs = find_shared_noise_realisations(recs)
        total += len(pairs)
        if not pairs:
            print(f"    [PASS] {what:<16} {len(recs)} files, {len(seeds)} distinct seeds: "
                  f"no different-seed pair is correlated")
            continue
        worst = max(p[2] for p in pairs)
        print(f"    [FAIL] {what:<16} {len(pairs)} different-seed pairs share one realisation "
              f"(max |corr| = {worst:.4f}; independent draws give ~1/sqrt(N))")
        for a, b, c in pairs[:5]:
            print(f"             {a}  ~  {b}   |corr| = {c:.4f}")
        if len(pairs) > 5:
            print(f"             ... {len(pairs) - 5} more")
    if total:
        print("    The model ignored the seed. Rebuild with create_cognitwin_model (v4,")
        print("    NOISE_SEED input) and regenerate these files.")
    print()
    return total


if __name__ == "__main__":
    raise SystemExit(main())
