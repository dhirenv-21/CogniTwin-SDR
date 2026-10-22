"""
Spectrum Agent validation against known test vectors (Python, synthetic data).

Covers the two defects found in this phase:
  * analyze_iq()'s SNR estimate was 10log10(mean/median |x|^2): bounded to
    ~0..1.8 dB and DEcreasing with SNR for PSK, so SNR_DROP could never fire;
  * the Task-5 classifier labelled every non-repeating BPSK/QPSK window OFDM-QPSK.

Every random draw is seeded, so thresholds are deterministic for this code.
"""

import os
import subprocess
import sys
import warnings

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.agents.messages import SpectrumIntelligenceResult  # noqa: E402
from src.agents.spectrum_agent import SpectrumAgent  # noqa: E402
from src.ai.modulation_classifier.dataset import generate_dataset, generate_single_signal  # noqa: E402
from src.ai.modulation_classifier.inference import analyze_iq  # noqa: E402
from src.ai.modulation_classifier.model import (  # noqa: E402
    DEFAULT_MODEL_PATH,
    ORIGINAL_MODEL_PATH,
    load_model,
    resolve_model_path,
)
from src.signal.analysis import (  # noqa: E402
    BLIND_SNR_FLOOR_DB,
    estimate_snr_blind,
)

N = 512


def _psk(rng, n, m):
    return np.exp(1j * (2 * np.pi * rng.integers(0, m, n) / m + (np.pi / 4 if m == 4 else 0.0)))


def _ofdm(rng, n):
    nsym = int(np.ceil(n / 80)) + 1
    grid = np.exp(1j * (np.pi / 2 * rng.integers(0, 4, (nsym, 64)) + np.pi / 4))
    t = np.fft.ifft(grid, axis=1) * 8.0
    w = np.concatenate([t[:, -16:], t], axis=1).reshape(-1)
    off = int(rng.integers(0, 80))                   # unknown symbol timing
    w = w[off:off + n]
    return w / np.sqrt(np.mean(np.abs(w) ** 2))


def _cn(rng, n, p):
    return np.sqrt(p / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


GEN = {
    "BPSK": lambda r: _psk(r, N, 2),
    "QPSK": lambda r: _psk(r, N, 4),
    "OFDM-QPSK": lambda r: _ofdm(r, N),
}


def _estimates(kind, snr_db, trials=60, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(trials):
        x = GEN[kind](rng)
        out.append(estimate_snr_blind(x + _cn(rng, N, 10 ** (-snr_db / 10))))
    return out


# ========================================================== blind SNR estimator
@pytest.mark.parametrize("kind,snr,tol", [
    ("BPSK", 3, 0.5), ("BPSK", 10, 0.3), ("BPSK", 25, 0.3),
    ("QPSK", 3, 0.5), ("QPSK", 10, 0.3), ("QPSK", 25, 0.3),
    ("OFDM-QPSK", 5, 1.0), ("OFDM-QPSK", 10, 1.0), ("OFDM-QPSK", 20, 1.0),
])
def test_blind_snr_is_unbiased_on_known_vectors(kind, snr, tol):
    est = _estimates(kind, snr)
    mean = np.mean([e["snr_db"] for e in est])
    assert abs(mean - snr) <= tol, f"{kind} @ {snr} dB: mean estimate {mean:.2f} dB"
    expected = "ofdm_cp" if kind == "OFDM-QPSK" else "m2m4"
    assert np.mean([e["method"] == expected for e in est]) >= 0.95


@pytest.mark.parametrize("kind", list(GEN))
def test_blind_snr_increases_with_true_snr(kind):
    """The old estimator DEcreased with SNR for PSK; this pins the direction."""
    snrs = [5, 10, 15, 20] if kind == "OFDM-QPSK" else [3, 5, 10, 15, 20]
    means = [np.mean([e["snr_db"] for e in _estimates(kind, s, trials=30, seed=s)]) for s in snrs]
    assert all(b > a for a, b in zip(means, means[1:])), means


def test_the_replaced_estimator_really_was_inverted():
    """Document the defect: mean/median power ratio falls as QPSK SNR rises."""
    rng = np.random.default_rng(3)
    old = []
    for snr in (0, 10, 20, 40):
        y = _psk(rng, N, 4) + _cn(rng, N, 10 ** (-snr / 10))
        p = np.abs(y) ** 2
        old.append(10 * np.log10(np.mean(p) / np.median(p)))
    assert old[0] > old[1] > old[2] > old[3] and max(old) < 2.0


def test_noise_only_reports_the_floor_not_a_random_number():
    """3-sigma kurtosis gate: ~0.1 % false acceptance expected, so allow <= 2/400."""
    rng = np.random.default_rng(4)
    res = [estimate_snr_blind(_cn(rng, N, 1.0)) for _ in range(400)]
    floored = [e for e in res if e["method"] == "below_resolution"]
    assert len(res) - len(floored) <= 2
    assert all(e["snr_db"] == BLIND_SNR_FLOOR_DB for e in floored)


def test_at_the_resolution_limit_estimates_are_accurate_or_floored():
    """PSK at 0 dB, N = 512: either resolved close to truth, or the floor - never noise."""
    for e in _estimates("QPSK", 0, trials=200, seed=9):
        if e["method"] == "m2m4":
            assert abs(e["snr_db"]) < 3.0, e
        else:
            assert e["snr_db"] == BLIND_SNR_FLOOR_DB, e


def test_blind_snr_is_scale_and_phase_invariant():
    """Unit-power adaptation and a block-fading rotation must not change it."""
    rng = np.random.default_rng(5)
    for kind in GEN:
        y = GEN[kind](rng) + _cn(rng, N, 0.1)
        ref = estimate_snr_blind(y)["snr_db"]
        for g in (0.01, 3.7 * np.exp(1j * 1.2), 250.0 * np.exp(-2.1j)):
            assert estimate_snr_blind(g * y)["snr_db"] == pytest.approx(ref, abs=1e-9)


def test_gaussian_interference_is_counted_as_noise():
    """Blind estimate tracks SINR: S/(N+J)."""
    rng = np.random.default_rng(6)
    vals = []
    for _ in range(40):
        y = _psk(rng, N, 4) + _cn(rng, N, 0.05) + _cn(rng, N, 0.05)    # SINR = 10 dB
        vals.append(estimate_snr_blind(y)["snr_db"])
    assert np.mean(vals) == pytest.approx(10.0, abs=0.4)


@pytest.mark.parametrize("x", [np.zeros(0), np.zeros(3, complex), np.zeros(512, complex),
                               np.full(512, np.nan + 0j)])
def test_blind_snr_degenerate_inputs(x):
    e = estimate_snr_blind(x)
    assert e["method"] == "below_resolution" and e["snr_db"] == BLIND_SNR_FLOOR_DB


# ========================================================== Spectrum Agent
def _agent_run(snr_seq, kind="QPSK", seed=7, interference=0.0):
    rng = np.random.default_rng(seed)
    agent = SpectrumAgent()
    out = []
    for snr in snr_seq:
        y = GEN[kind](rng) + _cn(rng, N, 10 ** (-snr / 10))
        out.append(agent.process(y / np.sqrt(np.mean(np.abs(y) ** 2)), timestamp_s=len(out) * 0.1,
                                 env_interference_power=interference))
    return out


def test_snr_drop_anomaly_is_now_reachable():
    res = _agent_run([20, 20, 20, 5, 5])
    assert [r.anomaly_flag for r in res] == ["NONE", "NONE", "NONE", "SNR_DROP", "NONE"]


@pytest.mark.parametrize("kind,snr", [("QPSK", 20), ("BPSK", 10), ("OFDM-QPSK", 15)])
def test_no_false_snr_drop_at_a_steady_operating_point(kind, snr):
    res = _agent_run([snr] * 40, kind=kind)
    assert sum(r.anomaly_flag == "SNR_DROP" for r in res) == 0


def test_high_interference_flag_and_output_schema():
    res = _agent_run([15, 15], interference=1.5)
    r = res[0]
    assert isinstance(r, SpectrumIntelligenceResult)
    assert r.anomaly_flag == "HIGH_INTERFERENCE"
    for f in ("snr_db", "bandwidth_hz", "classifier_confidence", "interference_power", "timestamp_s"):
        assert isinstance(getattr(r, f), float), f
    assert 0.0 <= r.classifier_confidence <= 1.0
    assert r.timestamp_s == 0.0 and res[1].timestamp_s == pytest.approx(0.1)


def test_analyze_iq_power_and_frequency_against_independent_values():
    fs = 100e3
    t = np.arange(N) / fs
    tone = 2.0 * np.exp(2j * np.pi * 12500.0 * t)
    r = analyze_iq(tone, sample_rate=fs)
    assert r["signal_power"] == pytest.approx(4.0)          # raw power, not normalised
    assert abs(r["dominant_frequency"] - 12500.0) <= fs / N
    assert r["snr_method"] in ("m2m4", "ofdm_cp", "below_resolution")


# ========================================================== classifier
@pytest.mark.parametrize("kind", ["BPSK", "QPSK", "OFDM-QPSK"])
def test_default_classifier_detects_non_repeating_streams(kind):
    """Task-5 model: 0/40 for BPSK and QPSK here (all -> OFDM-QPSK)."""
    rng = np.random.default_rng(11)
    hits = 0
    for _ in range(40):
        y = GEN[kind](rng) + _cn(rng, N, 10 ** (-15 / 10))
        hits += analyze_iq(y)["predicted_modulation"] == kind
    assert hits >= 34, f"{kind}: {hits}/40"


def test_original_model_is_still_available_and_unchanged_on_disk():
    p = resolve_model_path(ORIGINAL_MODEL_PATH)
    assert p is not None and os.path.getsize(p) > 0
    assert load_model(ORIGINAL_MODEL_PATH) is not load_model(DEFAULT_MODEL_PATH)


def test_load_model_is_cached():
    assert load_model() is load_model()


def test_model_path_resolves_from_another_working_directory(tmp_path):
    """Previously a relative path silently returned None outside the repo root."""
    code = ("import sys; sys.path.insert(0, %r); "
            "from src.ai.modulation_classifier.model import load_model; "
            "print(load_model() is not None)") % ROOT
    out = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path),
                         capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().endswith("True"), out.stderr


def test_missing_model_warns_instead_of_failing_silently(tmp_path):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert load_model(str(tmp_path / "nope.joblib")) is None
    assert any("predictions will be 'UNKNOWN'" in str(x.message) for x in w)


def test_dataset_defaults_reproduce_the_original_tiled_data():
    """representation/normalize/augment defaults must not change Task-5 data."""
    a = generate_dataset(2, [10.0], seed=42)[0]
    b = generate_dataset(2, [10.0], seed=42, representation="tiled", normalize=False, augment=False)[0]
    assert np.array_equal(a, b)


def test_stream_windows_do_not_repeat():
    x = generate_single_signal("QPSK", 40.0, seed=3, repeating=False)
    tiled = generate_single_signal("QPSK", 40.0, seed=3, repeating=True)
    period = 32                                            # tiled QPSK pattern length
    assert np.max(np.abs(tiled[:period] - tiled[period:2 * period])) < 0.1
    assert np.max(np.abs(x[:period] - x[period:2 * period])) > 0.5


def test_no_false_snr_drop_at_the_resolution_boundary():
    """Stationary PSK at 0 dB flips between ~0 dB and the floor; that is not a drop."""
    for kind in ("BPSK", "QPSK"):
        res = _agent_run([0] * 60, kind=kind, seed=21)
        assert sum(r.anomaly_flag == "SNR_DROP" for r in res) <= 2, kind


def test_a_real_drop_into_the_noise_still_registers():
    res = _agent_run([20, 20, -5], kind="QPSK", seed=22)
    assert res[-1].anomaly_flag == "SNR_DROP"
