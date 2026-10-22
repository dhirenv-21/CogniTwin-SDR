"""
PHY v4 validation tests: noise seeding, modulation identity, BPSK/OFDM BER
theory, and the bridge gate on MATLAB's own consistency battery.

None of these tests run MATLAB. They exercise the Python validation code on
synthetic arrays built with the MATLAB constellations, plus - where present -
the real Simulink exports already in simulink/results/baseline/.
"""

import glob
import math
import os
import sys

import numpy as np
import pytest
import scipy.io as sio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.simulink_bridge.validation import (  # noqa: E402
    check_modulation_signature,
    find_shared_noise_realisations,
    validate_mat_dict,
)

sys.path.insert(0, os.path.join(ROOT, "experiments"))
import verify_simulink_mat as vsm  # noqa: E402

FS = 100e3
MODS = ("BPSK", "QPSK", "OFDM-QPSK")


# ------------------------------------------------------------------ helpers
def _gray_to_bin(g: np.ndarray) -> np.ndarray:
    b = g.copy()
    mask = g >> 1
    while np.any(mask):
        b ^= mask
        mask >>= 1
    return b


def _psk(bits: np.ndarray, m_order: int) -> np.ndarray:
    """MSB-first packing -> Gray decode -> exp(j(2 pi m/M + offset)), as cognitwin_waveform.m."""
    k = int(math.log2(m_order))
    g = np.zeros(bits.size // k, dtype=np.int64)
    for b in range(k):
        g = g * 2 + bits[b::k]
    m = _gray_to_bin(g)
    offset = math.pi / 4 if m_order == 4 else 0.0
    return np.exp(1j * (2 * np.pi * m / m_order + offset))


def _tx(mod: str, n: int, rng: np.random.Generator):
    """Unit-power transmit waveform and its bits, matching cognitwin_waveform.m."""
    if mod in ("BPSK", "QPSK"):
        m_order = 2 if mod == "BPSK" else 4
        k = int(math.log2(m_order))
        bits = rng.integers(0, 2, n * k)
        return _psk(bits, m_order), bits
    n_sym = int(math.ceil(n / 80))
    bits = rng.integers(0, 2, n_sym * 128)
    grid = _psk(bits, 4).reshape(n_sym, 64)
    t_sym = np.fft.ifft(grid, axis=1) * math.sqrt(64)
    wave = np.concatenate([t_sym[:, -16:], t_sym], axis=1).reshape(-1)[:n]
    return wave / math.sqrt(np.mean(np.abs(wave) ** 2)), bits


def _cn(n: int, power: float, rng: np.random.Generator) -> np.ndarray:
    return math.sqrt(power / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


def _export(mod, snr_db, n=20000, interf=0.0, h=1 + 0j, seed=1, source="python-fixture"):
    """A MAT dict with the run_simulink_case field layout, BER from the KNOWN bits."""
    rng = np.random.default_rng(seed)
    tx, bits = _tx(mod, n, rng)
    noise = _cn(n, 10 ** (-snr_db / 10), rng)
    jam = _cn(n, interf, rng) if interf > 0 else np.zeros(n, dtype=complex)
    rx = h * tx + jam + noise

    rx_eq = rx / h
    if mod == "OFDM-QPSK":
        bits_rx = vsm._demod_ofdm_qpsk(rx_eq)
    else:
        bits_rx = vsm._demod_qpsk_bpsk(rx_eq, 2 if mod == "BPSK" else 4)
    nb = min(bits_rx.size, bits.size)
    ber = float(np.mean(bits_rx[:nb] != bits[:nb]))

    return {
        "iq_samples": rx.reshape(-1, 1),
        "tx_iq": tx.reshape(-1, 1),
        "noise_iq": noise.reshape(-1, 1),
        "interference_iq": jam.reshape(-1, 1),
        "time_vector": (np.arange(n) / FS).reshape(-1, 1),
        "snr_db": float(snr_db),
        "ber": ber,
        "modulation": mod,
        "interference_power": float(interf),
        "channel_type": "AWGN" if h == 1 else "Rayleigh",
        "sample_rate": FS,
        "num_samples": float(n),
        "samples_per_symbol": 1.0,
        "seed": float(seed),
        "noise_seed": float(seed + 1000),
        "channel_gain_real": float(np.real(h)),
        "channel_gain_imag": float(np.imag(h)),
        "source": source,
    }


def _verify(tmp_path, mat, name="case.mat"):
    path = str(tmp_path / name)
    sio.savemat(path, mat)
    return {c.name: c for c in vsm.verify_mat(path)}


# ======================================================= modulation identity
@pytest.mark.parametrize("mod", MODS)
def test_signature_accepts_the_matching_modulation(mod):
    tx, _ = _tx(mod, 4000, np.random.default_rng(3))
    ok, detail = check_modulation_signature(tx, mod)
    assert ok is True, detail


@pytest.mark.parametrize("actual,label", [
    (a, b) for a in MODS for b in MODS if a != b
])
def test_signature_rejects_a_mislabelled_waveform(actual, label):
    """A QPSK waveform exported as 'BPSK' (or any other swap) must be caught."""
    tx, _ = _tx(actual, 4000, np.random.default_rng(5))
    ok, detail = check_modulation_signature(tx, label)
    assert ok is False, f"{actual} accepted as {label}: {detail}"


def test_signature_rejects_a_noisy_waveform_posing_as_tx():
    """rx is not a valid transmit reference: the check is exact, not statistical."""
    rng = np.random.default_rng(6)
    tx, _ = _tx("QPSK", 4000, rng)
    ok, _ = check_modulation_signature(tx + _cn(4000, 1e-4, rng), "QPSK")
    assert ok is False


def test_signature_is_undefined_for_unsupported_labels():
    ok, detail = check_modulation_signature(np.ones(100, dtype=complex), "FM")
    assert ok is None and "no modulation signature" in detail


def test_bridge_fails_a_mislabelled_simulink_export_but_only_warns_for_fixtures():
    rng = np.random.default_rng(7)
    tx, _ = _tx("QPSK", 2000, rng)
    rx = tx + _cn(2000, 0.1, rng)
    base = {"iq_samples": rx, "tx_iq": tx, "snr_db": 10.0, "modulation": "BPSK"}

    rep = validate_mat_dict(dict(base, source="simulink"))
    assert rep.checks["tx_matches_modulation"] == "FAIL"
    assert not rep.ok

    rep = validate_mat_dict(dict(base, source="python-fixture"))
    assert rep.checks["tx_matches_modulation"] == "WARN"
    assert rep.ok

    rep = validate_mat_dict(dict(base, modulation="QPSK", source="simulink"))
    assert rep.checks["tx_matches_modulation"] == "PASS"


# ===================================================== MATLAB checks gate
@pytest.mark.parametrize("value,expected", [(1.0, "PASS"), (0.0, "FAIL"), (None, "SKIP")])
def test_bridge_honours_matlab_checks_passed(value, expected):
    """run_simulink_case(..., struct('strict', false)) can write checks_passed = 0."""
    rng = np.random.default_rng(8)
    tx, _ = _tx("QPSK", 2000, rng)
    mat = {"iq_samples": tx + _cn(2000, 0.1, rng), "tx_iq": tx,
           "snr_db": 10.0, "modulation": "QPSK"}
    if value is not None:
        mat["checks_passed"] = value
    rep = validate_mat_dict(mat)
    assert rep.checks["matlab_checks_passed"] == expected
    assert rep.ok is (expected != "FAIL")


# ==================================================== noise realisations
def test_shared_noise_detector_flags_identical_and_rescaled_draws():
    rng = np.random.default_rng(9)
    n = _cn(10000, 1.0, rng)
    recs = [
        ("seed11_snr10", 11.0, 0.316 * n),
        ("seed23_snr10", 23.0, 0.316 * n),       # identical draw, different seed
        ("seed37_snr0", 37.0, 1.0 * n),          # same draw rescaled (SNR ladder)
    ]
    flagged = find_shared_noise_realisations(recs)
    assert len(flagged) == 3
    assert all(c == pytest.approx(1.0) for _, _, c in flagged)


def test_shared_noise_detector_accepts_independent_draws():
    rng = np.random.default_rng(10)
    recs = [(f"s{k}", float(k), _cn(10000, 0.1, rng)) for k in range(6)]
    assert find_shared_noise_realisations(recs) == []


def test_shared_noise_detector_does_not_compare_runs_with_the_same_seed():
    """Same seed -> same draw is correct behaviour, not a defect."""
    rng = np.random.default_rng(11)
    n = _cn(5000, 1.0, rng)
    recs = [("ladder_snr0", 11.0, n), ("ladder_snr20", 11.0, 0.1 * n)]
    assert find_shared_noise_realisations(recs) == []


def test_shared_noise_detector_ignores_disabled_interference():
    z = np.zeros(1000, dtype=complex)
    assert find_shared_noise_realisations([("a", 1.0, z), ("b", 2.0, z)]) == []


def test_real_simulink_exports_match_their_model_version():
    """
    Real data in simulink/results/baseline/. v3 exports (no model_version field)
    were produced by a model whose randn ignored the seed, so different-seed runs
    MUST share a realisation; v4 exports MUST NOT. If the files are regenerated
    with the v4 model, the second half of this test takes over automatically.
    """
    files = sorted(glob.glob(os.path.join(ROOT, "simulink", "results", "baseline", "*.mat")))
    by_version = {"v3": [], "v4": []}
    for f in files:
        mat = sio.loadmat(f)
        if "noise_iq" not in mat:
            continue
        version = vsm._text(mat, "model_version", "v3") or "v3"
        seed = vsm._scalar(mat, "noise_seed", vsm._scalar(mat, "seed"))
        by_version.setdefault(version, []).append(
            (os.path.basename(f), seed, np.asarray(mat["noise_iq"]).reshape(-1)))

    checked = False
    v3 = by_version["v3"]
    if len({r[1] for r in v3}) >= 2:
        assert find_shared_noise_realisations(v3), "v3 exports unexpectedly independent"
        checked = True
    v4 = by_version["v4"]
    if len({r[1] for r in v4}) >= 2:
        assert find_shared_noise_realisations(v4) == [], "v4 exports share a noise draw"
        checked = True
    if not checked:
        pytest.skip("no multi-seed Simulink exports in simulink/results/baseline")


# ================================================================ verifier
def test_bpsk_theory_uses_two_times_sinr():
    for sinr in (0.5, 1.0, 2.0, 10.0):
        assert vsm.ber_theory_fn("BPSK", sinr) == pytest.approx(vsm.q_func(math.sqrt(2 * sinr)))
        assert vsm.ber_theory_fn("QPSK", sinr) == pytest.approx(vsm.q_func(math.sqrt(sinr)))


def test_verifier_bpsk_ber_matches_the_corrected_theory(tmp_path):
    """
    BPSK at 3 dB: Q(sqrt(2*SINR)) ~ 0.023, the old Q(sqrt(SINR)) ~ 0.079. The
    measured BER must sit on the first and far outside the 35 % band of the second.
    """
    chk = _verify(tmp_path, _export("BPSK", 3.0, seed=21))
    assert chk["ber_matches_theory"].tag == "PASS", chk["ber_matches_theory"].detail
    assert chk["ber_matches_matlab"].tag == "PASS"
    measured = float(_export("BPSK", 3.0, seed=21)["ber"])
    wrong = vsm.q_func(math.sqrt(10 ** 0.3))
    assert abs(measured - wrong) > 0.35 * wrong


@pytest.mark.parametrize("snr_db", [2.0, 6.0, 10.0])
def test_verifier_demodulates_ofdm_independently(tmp_path, snr_db):
    """OFDM-QPSK used to SKIP ber_matches_theory; it is now recomputed in Python."""
    mat = _export("OFDM-QPSK", snr_db, n=16000, seed=int(snr_db) + 30)
    chk = _verify(tmp_path, mat)
    assert chk["tx_matches_modulation"].tag == "PASS"
    assert chk["ber_matches_matlab"].tag == "PASS", chk["ber_matches_matlab"].detail
    assert chk["ber_matches_theory"].tag == "PASS", chk["ber_matches_theory"].detail


def test_verifier_power_budget_tracks_fading_and_interference(tmp_path):
    h = 0.4 * np.exp(1j * 1.1)
    chk = _verify(tmp_path, _export("QPSK", 10.0, interf=0.5, h=h, seed=40))
    for name in ("rx_power_matches_components", "noise_is_circular",
                 "noise_independent_of_jam", "rx_equals_model_sum", "ber_matches_theory"):
        assert chk[name].tag == "PASS", f"{name}: {chk[name].detail}"


def test_verifier_catches_an_unapplied_fading_gain(tmp_path):
    """rx built with h = 1 but exported as if faded: the power budget must break."""
    mat = _export("QPSK", 20.0, seed=41)
    mat["channel_gain_real"], mat["channel_gain_imag"] = 0.5, 0.0
    chk = _verify(tmp_path, mat)
    assert chk["rx_power_matches_components"].tag == "FAIL"
    assert chk["rx_equals_model_sum"].tag == "FAIL"


def test_verifier_catches_real_only_noise(tmp_path):
    mat = _export("QPSK", 10.0, seed=42)
    noise = np.asarray(mat["noise_iq"]).reshape(-1)
    real_noise = math.sqrt(2) * noise.real + 0j
    tx = np.asarray(mat["tx_iq"]).reshape(-1)
    mat["noise_iq"] = real_noise.reshape(-1, 1)
    mat["iq_samples"] = (tx + real_noise).reshape(-1, 1)
    chk = _verify(tmp_path, mat)
    assert chk["noise_is_circular"].tag == "FAIL"


def test_verifier_flags_a_failed_matlab_battery(tmp_path):
    mat = dict(_export("QPSK", 10.0, seed=43), checks_passed=0.0)
    assert _verify(tmp_path, mat)["matlab_checks_passed"].tag == "FAIL"


def test_verifier_skips_results_tables(tmp_path):
    path = str(tmp_path / "baseline_results.mat")
    sio.savemat(path, {"results": np.zeros((2, 2)), "crit": "x"})
    checks = vsm.verify_mat(path)
    assert [c.tag for c in checks] == ["SKIP"]


def test_verifier_directory_mode_fails_on_shared_noise(tmp_path, capsys):
    shared = _export("QPSK", 10.0, seed=50)
    for seed in (51, 52):
        m = _export("QPSK", 10.0, seed=seed)
        tx = np.asarray(m["tx_iq"]).reshape(-1)
        m["noise_iq"] = shared["noise_iq"]
        m["iq_samples"] = (tx + np.asarray(shared["noise_iq"]).reshape(-1)).reshape(-1, 1)
        sio.savemat(str(tmp_path / f"run_{seed}.mat"), m)
    assert vsm.main(["--dir", str(tmp_path), "--quiet"]) == 1
    assert "share one realisation" in capsys.readouterr().out


def test_verifier_directory_mode_passes_independent_runs(tmp_path):
    for seed in (61, 62, 63):
        sio.savemat(str(tmp_path / f"run_{seed}.mat"),
                    _export("QPSK", 10.0, seed=seed, source="simulink"))
    assert vsm.main(["--dir", str(tmp_path), "--quiet"]) == 0


# ========================================================= MATLAB sources
def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def test_generator_seeds_the_block_rng_once_per_simulation():
    src = _read("simulink", "create_cognitwin_model.m")
    assert ("'function [y, jam, noise, x] = fcn(xi, xq, snr_db, interf_power, "
            "h_re, h_im, noise_seed)', ...") in src
    # seeding must be guarded so it happens once, not every sample
    i_guard = src.index("'if isempty(rngSeeded)', ...")
    i_rng = src.index("'    rng(noise_seed);', ...")
    i_noise = src.index("'noise = sqrt(noisePower/2) * complex(randn, randn);', ...")
    assert i_guard < i_rng < i_noise
    assert "'persistent rngSeeded', ..." in src
    assert "add_line(modelName,'NOISE_SEED/1','PHY_Channel/7','autorouting','on');" in src
    # the generator refuses to install a script missing its noise-source line,
    # in either mode
    assert "seedMarker = 'rng(noise_seed);';" in src
    assert "seedMarker = 'complex(ni, nq);';" in src
    assert "isempty(strfind(phyScript, seedMarker))" in src


def test_generator_default_noise_source_is_seeded_random_number_blocks():
    """
    Default build: four Simulink Random Number blocks whose Seed parameters are
    derived from NoiseSeed, wired into PHY_Channel inputs 7-10. Their Seed is the
    documented control of each block's own generator, unlike randn in a MATLAB
    Function block.
    """
    src = _read("simulink", "create_cognitwin_model.m")
    assert "NoiseSource = 'random_number_blocks';" in src
    assert "add_block('simulink/Sources/Random Number'," in src
    assert "rnNames = {'NOISE_I','NOISE_Q','JAM_I','JAM_Q'};" in src
    assert "'Seed',sprintf('mod(4*NoiseSeed + %d, 4294967291)', k-1)," in src
    assert "'SampleTime','1/Fs'," in src
    assert "'Mean','0'," in src and "'Variance','1'," in src
    assert "add_line(modelName,[rnNames{k} '/1'],sprintf('PHY_Channel/%d', 6+k),'autorouting','on');" in src
    assert ("'function [y, jam, noise, x] = fcn(xi, xq, snr_db, interf_power, "
            "h_re, h_im, ni, nq, ji, jq)', ...") in src
    assert "'noise = sqrt(noisePower/2) * complex(ni, nq);', ..." in src
    assert "'jam   = sqrt(max(interf_power,0)/2) * complex(ji, jq);', ..." in src
    # compile before save, and always build next to the script
    assert "set_param(modelName,'SimulationCommand','update');" in src
    assert "create_cognitwin_model:UpdateFailed" in src
    assert "generatorDir = fileparts(mfilename('fullpath'));" in src


def test_random_number_seed_mapping_never_shares_a_stream_between_runs():
    """
    Seeds per run are mod(4*NoiseSeed + k, P), k = 0..3. The campaign uses
    consecutive run seeds, so a naive NoiseSeed + k mapping would hand run s's
    Q stream to run s+1's I stream (|corr| = 0.5). Check the real mapping over
    every NoiseSeed the drivers can produce in practice.
    """
    p = 4294967291
    seen = {}
    for noise_seed in range(1000, 1000 + 20000):     # opts.seed 0..19999
        for k in range(4):
            s = (4 * noise_seed + k) % p
            assert s not in seen, f"stream seed {s} shared by {seen[s]} and {noise_seed}"
            seen[s] = noise_seed
        assert 0 <= s < 2 ** 32
    # and the naive mapping really would collide
    naive = [(n + k) for n in (1011, 1012) for k in range(4)]
    assert len(set(naive)) < len(naive)


def test_driver_and_diagnostic_accept_either_seeded_build():
    for parts in (("simulink", "matlab", "run_simulink_case.m"),
                  ("simulink", "matlab", "diagnose_simulink_phy.m")):
        src = _read(*parts)
        assert "find_system(modelName, 'SearchDepth', 1, 'BlockType', 'RandomNumber');" in src
        assert "all(ismember({'NOISE_I','NOISE_Q','JAM_I','JAM_Q'}, rnNames))" in src
    assert "m.noise_source                = noiseSource;" in _read(
        "simulink", "matlab", "run_simulink_case.m")


def test_driver_passes_the_seed_to_the_model_and_refuses_unseeded_builds():
    src = _read("simulink", "matlab", "run_simulink_case.m")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("%"))
    assert "assignin('base', 'NoiseSeed',         noiseSeed);" in code
    assert "run_simulink_case:UnseededModel" in code
    # the call that looked like it seeded the model but did not must be gone
    assert "rng(opts.seed + 1000)" not in code
    assert "run_simulink_case:SimulationFailed" in code
    for field in ("m.noise_seed", "m.measured_snr_tx_ref_db", "m.snr_definition",
                  "m.run_id", "m.model_version"):
        assert field in code, field


def test_diagnostic_covers_seed_interference_fading_modulation_export():
    src = _read("simulink", "matlab", "diagnose_simulink_phy.m")
    for name in ("D13_noise_seed_control", "D14_noise_circular_and_independent",
                 "D15_interference_effect", "D16_fading_effect",
                 "D17_modulation_identity", "D18_export_contract"):
        assert f"'{name}'" in src, name


def test_matlab_and_python_modulation_checks_use_the_same_thresholds():
    m_src = _read("simulink", "matlab", "cognitwin_check_modulation.m")
    for frag in ("magErr < 1e-9 && imErr < 1e-9", "magErr < 1e-9 && phErr < 1e-9",
                 "cpErr < 1e-12 && paprDb > 3"):
        assert frag in m_src, frag
