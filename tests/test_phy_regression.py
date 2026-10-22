"""
PHY regression tests - one per bug found during the Simulink PHY debug.

Every test here corresponds to a concrete defect that was observed in the real
MATLAB/Simulink run, so that none of them can return silently.

    PHY-1  complex [t, x] From Workspace input zeroed the wanted signal
    PHY-2  |h_LS| ~ 0.0037 was a least-squares fit to noise, not a channel gain
    PHY-3  BER ~ 0.5 with positive SINR must be rejected, never reported as a result
    PHY-4  SNR/SIR/SINR must be computed from arrays, not inferred
    PHY-5  noise power must equal 10^(-SNR/10) for a unit-power transmit signal
    PHY-6  the jammer must be independent of the wanted signal (v1 used sqrt(P)*x)
    PHY-7  sample count / time vector / stop time invariants
    PHY-8  a dead-signal measurement must never reach the Spectrum Agent or ACWRA

None of these tests require MATLAB.
"""

import math
import os

import numpy as np
import pytest
import scipy.io as sio

from src.simulink_bridge.pipeline import SimulinkACWRAPipeline
from src.simulink_bridge.receiver import SimulinkReceiver
from src.simulink_bridge.reference_phy import generate_reference_measurement
from src.simulink_bridge.validation import (
    SIGNAL_PRESENCE_HEADROOM_DB,
    SIGNAL_PRESENCE_MARGIN_DB,
    MeasurementValidationError,
    measure_iq_statistics,
    validate_mat_dict,
)

FS = 100_000.0


# --------------------------------------------------------------------- helpers


def _qpsk(n, rng):
    return np.exp(1j * (2 * np.pi * rng.integers(0, 4, n) / 4 + np.pi / 4))


def _mat(rx, tx, snr_db, interf=0.0, h=1.0 + 0j, n=None, **extra):
    n = n if n is not None else rx.size
    d = {
        "iq_samples": rx.reshape(-1, 1),
        "tx_iq": tx.reshape(-1, 1),
        "time_vector": (np.arange(n) / FS).reshape(-1, 1),
        "snr_db": float(snr_db),
        "ber": 0.0,
        "modulation": "QPSK",
        "interference_power": float(interf),
        "channel_type": "AWGN",
        "timestamp": 0.0,
        "sample_rate": FS,
        "num_samples": float(n),
        "source": "simulink",
        "channel_gain_real": float(np.real(h)),
        "channel_gain_imag": float(np.imag(h)),
    }
    d.update(extra)
    return d


def _link(n=10000, snr_db=10.0, interf=0.0, h=1.0 + 0j, seed=1, signal=True):
    """Build a healthy (or deliberately signal-less) link realisation."""
    rng = np.random.default_rng(seed)
    tx = _qpsk(n, rng)
    p_n = 10.0 ** (-snr_db / 10.0)
    noise = math.sqrt(p_n / 2) * (rng.normal(size=n) + 1j * rng.normal(size=n))
    jam = (
        math.sqrt(interf / 2) * (rng.normal(size=n) + 1j * rng.normal(size=n))
        if interf > 0
        else np.zeros(n, dtype=complex)
    )
    rx = (h * tx if signal else 0.0) + noise + jam
    return tx, rx, noise, jam


# ============================================================ PHY-1 / PHY-8


def test_phy1_complex_time_column_is_detectable():
    """
    PHY-1: `iq_input = [t, tx]` with complex tx makes the TIME column complex.
    From Workspace's array format needs a real time column, which is why the
    block emitted zero. Assert the defect is mechanically detectable so the
    MATLAB-side guard has a Python counterpart.
    """
    t = (np.arange(1000) / FS).reshape(-1, 1)
    tx = _qpsk(1000, np.random.default_rng(0)).reshape(-1, 1)

    broken = np.hstack([t, tx])
    assert np.iscomplexobj(broken)
    assert np.iscomplexobj(broken[:, 0]), "the time column itself becomes complex"

    # The v3 fix: two separate REAL matrices.
    good_i = np.hstack([t, tx.real])
    good_q = np.hstack([t, tx.imag])
    assert not np.iscomplexobj(good_i)
    assert not np.iscomplexobj(good_q)
    assert np.allclose(good_i[:, 1] + 1j * good_q[:, 1], tx.ravel())


def test_phy8_dead_signal_measurement_is_rejected():
    """PHY-8: rx without the wanted signal must be rejected by the bridge."""
    tx, rx, _, _ = _link(signal=False, snr_db=10.0, n=10000)
    rep = validate_mat_dict(_mat(rx, tx, 10.0))
    assert not rep.ok
    assert rep.checks["wanted_signal_present"] == "FAIL"
    assert any("does not contain the transmitted signal" in e for e in rep.errors)


def test_phy8_healthy_measurement_is_accepted():
    tx, rx, _, _ = _link(signal=True, snr_db=10.0, n=10000)
    rep = validate_mat_dict(_mat(rx, tx, 10.0))
    assert rep.ok, rep.errors
    assert rep.checks["wanted_signal_present"] == "PASS"
    assert rep.facts["signal_margin_db"] > SIGNAL_PRESENCE_MARGIN_DB


def test_phy8_dead_signal_never_reaches_acwra(tmp_path):
    """The pipeline must refuse to run, not decide on garbage."""
    tx, rx, _, _ = _link(signal=False, snr_db=10.0, n=10000)
    path = tmp_path / "dead.mat"
    sio.savemat(str(path), _mat(rx, tx, 10.0))
    with pytest.raises(MeasurementValidationError, match="wanted_signal_present"):
        SimulinkACWRAPipeline().run_from_mat(str(path))


def test_phy8_presence_test_skips_when_uninformative():
    """
    A genuinely hopeless-but-real link must not be mistaken for a broken one.
    At SNR = -20 dB with only 512 samples the estimator cannot resolve the
    signal at all, so the check must SKIP rather than FAIL.
    """
    tx, rx, _, _ = _link(n=512, snr_db=-20.0, signal=True)
    rep = validate_mat_dict(_mat(rx, tx, -20.0))
    assert rep.checks["wanted_signal_present"] == "SKIP"
    assert rep.ok
    assert rep.facts["signal_margin_predicted_db"] < (
        SIGNAL_PRESENCE_MARGIN_DB + SIGNAL_PRESENCE_HEADROOM_DB
    )


def test_phy8_low_snr_long_capture_still_passes():
    """The same -20 dB link with 10000 samples IS resolvable and must pass."""
    tx, rx, _, _ = _link(n=10000, snr_db=-20.0, signal=True)
    rep = validate_mat_dict(_mat(rx, tx, -20.0))
    assert rep.checks["wanted_signal_present"] == "PASS"
    assert rep.ok


# ==================================================================== PHY-2


def test_phy2_ls_estimate_on_pure_noise_reproduces_the_observed_h():
    """
    PHY-2: |h| ~ 0.0037-0.0083 in the broken run was not a channel gain. It is
    the magnitude of a least-squares fit of tx to noise it is not present in,
    whose expectation is E|h_LS|^2 = P_rx / N.

    Reproduce that number and pin the relationship, so a future |h| ~ 0.004 is
    recognised as a dead input path rather than deep fading.
    """
    n = 10000
    mags = []
    for seed in range(300):
        tx, rx, _, _ = _link(n=n, snr_db=10.0, seed=seed, signal=False)
        mags.append(abs(np.vdot(tx, rx) / np.vdot(tx, tx)))
    mags = np.array(mags)

    p_rx = 10.0 ** (-10.0 / 10.0)          # noise only
    predicted_rms = math.sqrt(p_rx / n)     # = sqrt(0.1/10000) = 0.00316

    assert predicted_rms == pytest.approx(0.00316, abs=1e-4)
    assert np.sqrt(np.mean(mags ** 2)) == pytest.approx(predicted_rms, rel=0.15)
    # The user's observed 0.0037 / 0.0039 sit inside this distribution.
    assert np.percentile(mags, 5) < 0.0037 < np.percentile(mags, 95)


def test_phy2_healthy_link_ls_estimate_recovers_h():
    """With the signal present the same estimator lands on the true h."""
    for h in (1.0 + 0j, 0.6 + 0.3j, -0.2 + 0.9j):
        tx, rx, _, _ = _link(n=10000, snr_db=10.0, h=h, seed=5)
        h_ls = np.vdot(tx, rx) / np.vdot(tx, tx)
        assert abs(h_ls - h) / abs(h) < 0.05


def test_phy2_more_impairment_increases_the_spurious_estimate():
    """
    The broken run's |h| grew from 0.0037 to 0.0083 when interference was added.
    That is the signature of fitting noise: more impairment power, larger
    spurious correlation. A real channel gain would not care.
    """
    rms = {}
    for interf in (0.0, 0.25):
        mags = [
            abs(np.vdot(t, r) / np.vdot(t, t))
            for t, r, _, _ in (
                _link(n=10000, snr_db=10.0, interf=interf, seed=s, signal=False)
                for s in range(200)
            )
        ]
        rms[interf] = math.sqrt(float(np.mean(np.square(mags))))
    assert rms[0.25] > rms[0.0]
    assert rms[0.25] / rms[0.0] == pytest.approx(math.sqrt((0.1 + 0.25) / 0.1), rel=0.15)


# ==================================================================== PHY-3


def test_phy3_ber_half_with_positive_sinr_is_impossible_for_a_healthy_link():
    """
    PHY-3: BER ~ 0.4977 at a nominal 10 dB is not a marginal result, it is a
    coin flip. Assert that a healthy QPSK link at 10 dB is nowhere near 0.5.
    """
    m = generate_reference_measurement(
        modulation="QPSK", snr_db=10.0, interference_power=0.0,
        channel_type="AWGN", n_samples=20000, seed=3,
    )
    theory = 0.5 * math.erfc(math.sqrt(10.0) / math.sqrt(2))
    assert m["ber"] < 0.05, "BER near 0.5 at 10 dB means the signal is absent"
    assert m["ber"] == pytest.approx(theory, abs=2e-3)


@pytest.mark.parametrize("snr_db,expected", [(0.0, 0.1587), (5.0, 0.0377), (10.0, 0.00078)])
def test_phy3_ber_follows_qpsk_theory(snr_db, expected):
    """BER must track Q(sqrt(SNR_linear)) across the operating range."""
    m = generate_reference_measurement(
        modulation="QPSK", snr_db=snr_db, n_samples=40000, seed=17,
    )
    assert m["ber"] == pytest.approx(expected, abs=max(0.15 * expected, 1.5e-3))


def test_phy3_ber_decreases_monotonically_with_snr():
    bers = [
        generate_reference_measurement(modulation="QPSK", snr_db=s, n_samples=20000, seed=21)["ber"]
        for s in (0.0, 5.0, 10.0, 15.0, 20.0)
    ]
    assert all(b1 >= b2 for b1, b2 in zip(bers, bers[1:])), bers
    assert bers[0] > 0.1 and bers[-1] == pytest.approx(0.0, abs=1e-9)


# ==================================================================== PHY-4/5


def test_phy4_snr_sir_sinr_computed_from_arrays():
    """
    PHY-4: every reported figure must be reproducible from the raw arrays with
    the textbook definitions, not inferred.
    """
    h = 0.8 - 0.4j
    tx, rx, noise, jam = _link(n=20000, snr_db=12.0, interf=0.25, h=h, seed=11)

    p_sig = float(np.mean(np.abs(h * tx) ** 2))
    p_noise = float(np.mean(np.abs(noise) ** 2))
    p_jam = float(np.mean(np.abs(jam) ** 2))

    snr_db = 10 * math.log10(p_sig / p_noise)
    sir_db = 10 * math.log10(p_sig / p_jam)
    sinr_db = 10 * math.log10(p_sig / (p_noise + p_jam))

    assert np.max(np.abs(rx - (h * tx + jam + noise))) < 1e-12
    assert snr_db == pytest.approx(10 * math.log10(abs(h) ** 2) + 12.0, abs=0.3)
    assert sir_db == pytest.approx(10 * math.log10(abs(h) ** 2 / 0.25), abs=0.3)
    assert sinr_db < snr_db and sinr_db < sir_db


def test_phy5_noise_power_equals_ten_to_the_minus_snr_over_ten():
    """PHY-5: trace the actual scaling rather than the variable name."""
    for snr_db in (-10.0, 0.0, 10.0, 20.0, 40.0):
        _, _, noise, _ = _link(n=200000, snr_db=snr_db, seed=2)
        measured = float(np.mean(np.abs(noise) ** 2))
        expected = 10.0 ** (-snr_db / 10.0)
        assert 10 * math.log10(measured / expected) == pytest.approx(0.0, abs=0.05)


@pytest.mark.parametrize(
    "p,expected_sir_db",
    [(0.01, 20.0), (0.1, 10.0), (0.25, 6.0206), (0.5, 3.0103),
     (1.0, 0.0), (2.0, -3.0103), (4.0, -6.0206), (10.0, -10.0)],
)
def test_phy4_sir_matches_minus_ten_log_p(p, expected_sir_db):
    """The exact SIR table from the acceptance criteria, from real arrays."""
    tx, rx, noise, jam = _link(n=100000, snr_db=60.0, interf=p, seed=int(p * 100) + 1)
    sir_db = 10 * math.log10(np.mean(np.abs(tx) ** 2) / np.mean(np.abs(jam) ** 2))
    assert sir_db == pytest.approx(expected_sir_db, abs=0.1)


def test_phy4_sinr_decreases_monotonically_with_interference():
    sinrs = []
    for p in (0.0, 0.01, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0):
        tx, rx, noise, jam = _link(n=50000, snr_db=30.0, interf=p, seed=8)
        p_sig = float(np.mean(np.abs(tx) ** 2))
        sinrs.append(
            10 * math.log10(p_sig / (np.mean(np.abs(noise) ** 2) + np.mean(np.abs(jam) ** 2)))
        )
    assert all(a > b for a, b in zip(sinrs, sinrs[1:])), sinrs


# ==================================================================== PHY-6


def test_phy6_jammer_is_independent_of_the_wanted_signal():
    """
    PHY-6: v1 used interference = sqrt(P)*x, a coherent copy that scaled the
    link instead of degrading it. Assert independence.
    """
    n = 50000
    tx, rx, noise, jam = _link(n=n, snr_db=30.0, interf=0.5, seed=4)
    corr = abs(np.vdot(tx, jam)) / math.sqrt(
        float(np.vdot(tx, tx).real) * float(np.vdot(jam, jam).real)
    )
    assert corr < 5.0 / math.sqrt(n)

    # The v1 bug for contrast: a coherent copy correlates perfectly.
    coherent = math.sqrt(0.5) * tx
    corr_bad = abs(np.vdot(tx, coherent)) / math.sqrt(
        float(np.vdot(tx, tx).real) * float(np.vdot(coherent, coherent).real)
    )
    assert corr_bad == pytest.approx(1.0, abs=1e-9)


def test_phy6_coherent_interference_does_not_degrade_ber():
    """
    Demonstrates why the v1 model's interference was inert: adding sqrt(P)*x
    only rescales the constellation, so a decision-directed receiver is
    unaffected, while an independent jammer at the same power destroys it.
    """
    n = 20000
    rng = np.random.default_rng(6)
    tx = _qpsk(n, rng)
    noise = math.sqrt(10 ** (-20 / 10) / 2) * (rng.normal(size=n) + 1j * rng.normal(size=n))

    coherent = tx + math.sqrt(1.0) * tx + noise            # v1 style
    independent = tx + (math.sqrt(1.0 / 2) *
                        (rng.normal(size=n) + 1j * rng.normal(size=n))) + noise

    def ber(rx):
        const = np.exp(1j * (2 * np.pi * np.arange(4) / 4 + np.pi / 4))
        rx_n = rx / (np.vdot(tx, rx) / np.vdot(tx, tx))     # normalise out the gain
        idx_rx = np.argmin(np.abs(rx_n[:, None] - const[None, :]), axis=1)
        idx_tx = np.argmin(np.abs(tx[:, None] - const[None, :]), axis=1)
        return float(np.mean(idx_rx != idx_tx))

    assert ber(coherent) < 1e-3, "coherent 'interference' is inert - the v1 bug"
    assert ber(independent) > 0.05, "an independent jammer at P=1 must hurt"


# ==================================================================== PHY-7


def test_phy7_sample_count_and_stop_time_invariants():
    """
    PHY-7: a fixed-step solver runs t = 0..StopTime inclusive, i.e.
    StopTime/Ts + 1 steps. StopTime = (N-1)/Fs is the only value giving N.
    """
    for n in (512, 1024, 10000, 20000):
        ts = 1.0 / FS
        stop_wrong = 0.1                       # the original hard-coded value
        stop_right = (n - 1) / FS
        assert round(stop_right / ts) + 1 == n
        if n == 10000:
            assert round(stop_wrong / ts) + 1 == 10001   # reproduces the old off-by-one


def test_phy7_time_vector_and_sample_rate_consistent():
    n = 10000
    tx, rx, _, _ = _link(n=n)
    rep = validate_mat_dict(_mat(rx, tx, 10.0), expected_sample_rate=FS)
    assert rep.ok, rep.errors
    assert rep.checks["time_vector_length"] == "PASS"
    assert rep.checks["time_vector_monotonic"] == "PASS"
    assert rep.checks["sample_rate_matches_expected"] == "PASS"


def test_phy7_wrong_sample_count_rejected(tmp_path):
    tx, rx, _, _ = _link(n=10000)
    path = tmp_path / "n.mat"
    sio.savemat(str(path), _mat(rx, tx, 10.0))
    meas, rep = SimulinkReceiver.load_and_validate(str(path), expected_samples=10000)
    assert rep.ok and meas.num_samples == 10000
    with pytest.raises(MeasurementValidationError):
        SimulinkReceiver.load_and_validate(str(path), expected_samples=10001)


# ============================================================= end-to-end


def test_healthy_measurement_flows_all_the_way_to_a_decision(tmp_path):
    """The positive control: a correct PHY produces a full ACWRA decision."""
    tx, rx, noise, jam = _link(n=10000, snr_db=10.0, interf=0.25, seed=31)
    path = tmp_path / "healthy.mat"
    sio.savemat(str(path), _mat(rx, tx, 10.0, interf=0.25,
                                noise_iq=noise.reshape(-1, 1),
                                interference_iq=jam.reshape(-1, 1)))
    result = SimulinkACWRAPipeline().run_from_mat(str(path))
    assert result.validation.ok
    assert result.validation.checks["wanted_signal_present"] == "PASS"
    assert result.decision.selected_strategy
    assert np.isfinite(result.decision.expected_utility)
    # measured SINR must land near 10log10(1/(0.1+0.25)) = 4.56 dB
    assert result.iq_statistics["measured_snr_db"] == pytest.approx(4.56, abs=0.5)


def test_statistics_helper_agrees_with_manual_computation():
    h = 0.7 + 0.2j
    tx, rx, noise, jam = _link(n=20000, snr_db=15.0, interf=0.1, h=h, seed=44)
    stats = measure_iq_statistics(rx, sample_rate=FS, tx_iq=tx)

    p_sig = float(np.mean(np.abs(h * tx) ** 2))
    p_imp = float(np.mean(np.abs(noise + jam) ** 2))
    assert stats["measured_snr_db"] == pytest.approx(10 * math.log10(p_sig / p_imp), abs=0.2)
    assert stats["channel_gain_mag"] == pytest.approx(abs(h), rel=0.05)


# ==================================================================== PHY-9
# The create_cognitwin_model.m "Invalid expression" at line 257, column 80.


def _m_files():
    import glob
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return sorted(glob.glob(os.path.join(root, "simulink", "**", "*.m"), recursive=True))


def test_phy9_no_char_literal_touching_an_identifier():
    """
    PHY-9: inside a MATLAB `[ ... ]` concatenation, WHITESPACE is the element
    delimiter. `chart.Script` was built as

        chart.Script = [ 'line one'   newline ...
                         'line two'   newline ... ];

    and when a line grew long enough that the padding before `newline`
    disappeared, the source became

        '...interf_power.'newline ...

    a closing quote immediately followed by an identifier, with nothing to
    separate the two tokens. MATLAB reports "Invalid expression" at exactly the
    column where the identifier starts - line 257, column 80.

    Scan every MATLAB source for a closing char-literal quote directly abutting
    an identifier character. Comments are exempt (the fix's own explanatory
    comment deliberately shows the broken form).
    """
    import re

    offenders = []
    for path in _m_files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh.read().splitlines(), 1):
                if line.lstrip().startswith("%"):
                    continue
                for m in re.finditer(r"'(?=[A-Za-z_])", line):
                    # a closing quote has an odd number of quotes before it
                    if line[: m.start()].count("'") % 2 == 1:
                        offenders.append(f"{os.path.basename(path)}:{lineno} col {m.start() + 2}")

    assert not offenders, (
        "char literal abuts an identifier with no delimiter (MATLAB: 'Invalid "
        "expression'): " + ", ".join(offenders)
    )


def test_phy9_generator_uses_comma_delimited_cell_not_whitespace_concat():
    """
    The permanent fix: build the PHY_Channel script from a COMMA-delimited cell
    array joined with sprintf, which has no whitespace sensitivity at all, rather
    than a whitespace-delimited bracket concatenation.
    """
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "simulink", "create_cognitwin_model.m"),
               encoding="utf-8", errors="replace").read()

    assert "phyLines = { ..." in src
    assert "phyScript = sprintf('%s\\n', phyLines{:});" in src
    assert "chart.Script = phyScript;" in src

    # The PHY equations must still be present, verbatim and unaltered.
    for equation in (
        "'x = complex(xi, xq);', ...",
        "'h = complex(h_re, h_im);', ...",
        "'noisePower = 10^(-snr_db/10);', ...",
        "'noise = sqrt(noisePower/2) * complex(randn, randn);', ...",
        "'jam   = sqrt(max(interf_power,0)/2) * complex(randn, randn);', ...",
        "'y = h*x + jam + noise;', ...",
    ):
        assert equation in src, f"PHY equation missing or altered: {equation}"


def test_phy9_generator_validates_its_own_output():
    """The generator must refuse to install a truncated PHY_Channel body."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "simulink", "create_cognitwin_model.m"),
               encoding="utf-8", errors="replace").read()
    assert "create_cognitwin_model:BadPhyScript" in src
    assert "Generated PHY_Channel script is missing" in src


# =================================================================== PHY-10
# D4 reported FAIL on a healthy v3 build because it probed the wrong object.


def _matlab_isreal_after_concat(m: np.ndarray) -> bool:
    """
    Model MATLAB's `isreal` semantics for a concatenated [t, data] matrix.

    MATLAB narrows a concatenation back to real storage when the imaginary part
    is identically zero, so `isreal([complex(t,0), real_data])` is TRUE. Verified
    directly in a MATLAB-compatible interpreter:

        isreal([t, complex_tx])                  -> 0     (matrix IS complex)
        isreal([t, complex_tx](:,1))             -> 1     (extracted col narrows)
        isreal([complex(t,zeros(size(t))), I])   -> 1     (zero imag narrows)
        isreal([t + 1i*eps, I])                  -> 0     (genuinely complex)
        isreal(complex([t, I], zeros(N,2)))      -> 0     (storage forced complex)

    The middle row is why the original D4 failed on a healthy build: it asked
    about the extracted time column instead of the matrix From Workspace receives.
    """
    return not bool(np.any(m.imag != 0)) if np.iscomplexobj(m) else True


def _fw_input_ok(m: np.ndarray) -> tuple:
    """Python mirror of local_check_fw_input() in diagnose_simulink_phy.m."""
    m = np.asarray(m)
    if m.ndim != 2 or m.shape[1] < 2 or m.shape[0] < 2:
        return False, f"not a numeric N x >=2 matrix (shape {m.shape})"
    if not _matlab_isreal_after_concat(m):
        return False, "matrix is COMPLEX - From Workspace array format requires a real matrix"
    t = m[:, 0].real
    if not np.all(np.isfinite(m.real)) or (np.iscomplexobj(m) and not np.all(np.isfinite(m.imag))):
        return False, "matrix contains NaN or Inf"
    if np.any(np.diff(t) <= 0):
        return False, "time column is not strictly increasing"
    return True, "real [t, data] matrix, time column strictly increasing"


def _probe_table():
    n = 512
    t = (np.arange(n) / FS).reshape(-1, 1)
    tx = _qpsk(n, np.random.default_rng(4)).reshape(-1, 1)
    nan_col = np.cos(t).copy(); nan_col[0] = np.nan
    inf_col = np.cos(t).copy(); inf_col[0] = np.inf
    return [
        ("healthy real [t, I]", np.hstack([t, tx.real]), True),
        ("healthy real [t, Q]", np.hstack([t, tx.imag]), True),
        ("legacy [t, complex tx]  (the v2 bug)", np.hstack([t, tx]), False),
        ("time column genuinely complex", np.hstack([t + 1j * np.finfo(float).eps, tx.real]), False),
        # NOTE: MATLAB's complex([t, I], zeros(N,2)) - complex STORAGE forced with a
        # zero imaginary part, where isreal() returns false - has no numpy equivalent
        # (numpy has no storage flag independent of the values). That case is covered
        # by D4e in diagnose_simulink_phy.m and was verified in a MATLAB-compatible
        # interpreter; it is deliberately not mirrored here rather than faked.
        ("zero-imag time col (MATLAB narrows: NOT a defect)",
         np.hstack([t.astype(complex), tx.real.astype(complex)]), True),
        ("time column not increasing", np.hstack([t[::-1], tx.real]), False),
        ("NaN in data", np.hstack([t, nan_col]), False),
        ("Inf in data", np.hstack([t, inf_col]), False),
        ("single column, no data", t, False),
    ]


@pytest.mark.parametrize("label,matrix,expected", _probe_table(),
                         ids=[p[0][:38] for p in _probe_table()])
def test_phy10_from_workspace_input_contract(label, matrix, expected):
    """
    PHY-10 / requirement 7: real [t, I] and [t, Q] inputs are ACCEPTED, and every
    way of making the matrix complex - including a complex time column - is
    REJECTED. Same truth table the MATLAB D4 contract validator enforces.
    """
    ok, why = _fw_input_ok(matrix)
    assert ok is expected, f"{label}: accepted={ok}, expected={expected} ({why})"


def test_phy10_real_iq_inputs_reconstruct_the_waveform_exactly():
    """D4c: the two real streams must recombine into the transmit waveform bit-exactly."""
    n = 4096
    t = (np.arange(n) / FS).reshape(-1, 1)
    tx = _qpsk(n, np.random.default_rng(12)).reshape(-1, 1)

    input_i = np.hstack([t, tx.real])
    input_q = np.hstack([t, tx.imag])

    assert _fw_input_ok(input_i)[0]
    assert _fw_input_ok(input_q)[0]
    recon = input_i[:, 1] + 1j * input_q[:, 1]
    assert np.array_equal(recon, tx.ravel()), "I + jQ must reproduce tx exactly"


def test_phy10_d4_probes_the_matrix_not_an_extracted_column():
    """
    The original defect: D4 asked `~isreal(legacyInput(:,1))`. Extracting a column
    whose imaginary part is zero narrows it back to real, so the check reported
    FAIL on a healthy build. Pin the corrected form at the source level.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "simulink", "matlab", "diagnose_simulink_phy.m"),
               encoding="utf-8", errors="replace").read()

    executable = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("%")
    )
    # The fixed file still *quotes* the broken expression inside its explanatory
    # comment, on purpose. Only executable code must be free of it.
    assert "isreal(legacyInput(:,1))" not in executable, "the wrong-object probe must be gone"
    assert "isreal(legacyInput(:,1))" in src, "the explanation of the defect should be retained"
    assert "local_check_fw_input" in src, "D4 must use the input-format contract validator"
    # the validator must test complexity of the WHOLE matrix
    assert "if ~isreal(M)" in src
    assert "D4_input_format_contract" in src

    # all five sub-checks must still be required for D4 to pass
    assert "d4ok = okI && okQ && okRecon && okLegacyRejected && okComplexTimeRejected;" in src

    # the negative control must survive: the legacy format still has to be rejected
    assert "okLegacyRejected = ~okLegacyAccepted;" in src


def test_phy10_d5_to_d12_untouched():
    """Requirements 3 and 4: D11 and D5-D12 must not have been altered."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "simulink", "matlab", "diagnose_simulink_phy.m"),
               encoding="utf-8", errors="replace").read()

    for anchor in (
        "report = local_add(report, 'D5_phy_reconstructs_x', echoErr < 1e-12,",
        "report = local_add(report, 'D6_noise_power_vs_snr', noiseOk,",
        "report = local_add(report, 'D7_jam_power_and_independence',",
        "report = local_add(report, 'D8_channel_gain_applied', abs(hLs - hTrue) < 0.05,",
        "report = local_add(report, 'D9_rx_equals_model_equation', resid < 1e-12,",
        "report = local_add(report, 'D10_sample_count_and_time',",
        "report = local_add(report, 'D11_noiseless_loopback', loopErr < 1e-6,",
        "report = local_add(report, 'D12_ber_sanity', berHigh < 1e-3 && berLow > berHigh,",
    ):
        assert anchor in src, f"D5-D12 anchor changed or missing: {anchor}"

    # D11's stimulus must remain SNR = 200 dB, no jammer, h = 1
    assert "rl = local_sim(modelName, t, txProbe, 200, 0, 1+0i, Fs, N);" in src
