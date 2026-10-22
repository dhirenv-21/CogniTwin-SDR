"""
GNU Radio PHY run configuration.

One GRPhyConfig fully determines one flowgraph execution: waveform, channel, noise,
interference, fading and every seed. Its hash (config_hash) is the experiment's
identity; two runs with the same hash and the same GNU Radio version must produce
identical samples (tests/test_gnuradio_execution.py checks this).

Conventions (identical to the Simulink bridge, docs/DATA_SCHEMA_PROVENANCE.md):
    snr_db              Es/N0 per exported sample, transmit-referenced, WITHOUT the
                        jammer and WITHOUT the fade (unit-energy symbols).
    interference_power  J, Gaussian jammer power relative to the unit transmit
                        signal, measured at the same point as the noise.
    SINR                |h|^2 / (10^(-snr_db/10) + J)

For BPSK/QPSK the flowgraph runs at sps samples per symbol with root-raised-cosine
pulse shaping; both filters have unit energy, so after the matched filter at the
symbol instants the per-sample noise variance equals the oversampled per-sample
noise variance sigma^2, and Es/N0 = 1/sigma^2. OFDM-QPSK has no pulse shaping:
exported samples are the time-domain OFDM samples (64-point IFFT + 16-sample CP).
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

FLOWGRAPH_VERSION = "gr-phy-1"

MODULATIONS = ("BPSK", "QPSK", "OFDM-QPSK")
CHANNELS = ("AWGN", "RAYLEIGH", "RICIAN")
# none          : h = 1 (AWGN only)
# block         : one complex gain per run, drawn from the seed (block fading
#                 across runs, static within a run) - the Simulink v4 semantics
# time_varying  : gr-channels fading_model (sum of sinusoids, Doppler fD*Ts per
#                 oversampled sample); the gain changes within the run
FADING_MODES = ("none", "block", "time_varying")

OFDM_N_FFT = 64
OFDM_CP_LEN = 16
PACKET_BITS = 256
SYMBOL_RATE = 100000.0


def source_sha256(path: str) -> str:
    """SHA-256 of a source file with line endings normalised (git may convert CRLF)."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()


@dataclass(frozen=True)
class GRPhyConfig:
    modulation: str = "QPSK"
    snr_db: float = 10.0
    interference_power: float = 0.0
    channel: str = "AWGN"
    fading_mode: str = "none"
    doppler_fdts: float = 1e-4          # time_varying only: fD * Ts (oversampled Ts)
    rician_k: float = 2.0               # RICIAN only (linear K, specular/scattered)
    n_symbols: int = 4096               # PSK symbols, or OFDM QPSK symbols (multiple of 64)
    sps: int = 4                        # PSK only
    rolloff: float = 0.35               # PSK only
    span_symbols: int = 11              # PSK only: RRC length in symbols
    symbol_rate: float = SYMBOL_RATE    # exported samples per second
    seed: int = 1
    extra: Dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self):
        mod = str(self.modulation).upper()
        chan = str(self.channel).upper()
        object.__setattr__(self, "modulation", mod)
        object.__setattr__(self, "channel", chan)
        if mod not in MODULATIONS:
            raise ValueError(f"modulation {self.modulation!r} not in {MODULATIONS}")
        if chan not in CHANNELS:
            raise ValueError(f"channel {self.channel!r} not in {CHANNELS}")
        if self.fading_mode not in FADING_MODES:
            raise ValueError(f"fading_mode {self.fading_mode!r} not in {FADING_MODES}")
        if (chan == "AWGN") != (self.fading_mode == "none"):
            raise ValueError("AWGN requires fading_mode='none'; RAYLEIGH/RICIAN require 'block' or 'time_varying'")
        for name in ("snr_db", "interference_power", "doppler_fdts", "rician_k", "rolloff", "symbol_rate"):
            v = float(getattr(self, name))
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError(f"{name} must be finite, got {v}")
        if not -30.0 <= self.snr_db <= 60.0:
            raise ValueError(f"snr_db={self.snr_db} outside [-30, 60] dB")
        if self.interference_power < 0:
            raise ValueError("interference_power must be >= 0")
        if int(self.n_symbols) < 256:
            raise ValueError("n_symbols must be >= 256")
        if mod == "OFDM-QPSK" and int(self.n_symbols) % OFDM_N_FFT:
            raise ValueError(f"OFDM-QPSK n_symbols must be a multiple of {OFDM_N_FFT}")
        if int(self.sps) < 2 or not 0.0 < self.rolloff <= 1.0 or int(self.span_symbols) < 2:
            raise ValueError("need sps >= 2, 0 < rolloff <= 1, span_symbols >= 2")
        if not 0.0 < self.doppler_fdts < 0.5:
            raise ValueError("doppler_fdts must be in (0, 0.5)")
        if int(self.seed) < 1 or int(self.seed) > 2**31 - 64:
            # GNU Radio's gr::random treats seed 0 as 'seed from the clock'.
            raise ValueError("seed must be in [1, 2^31 - 64] (0 would mean a clock seed in GNU Radio)")

    # ------------------------------------------------------------------ seeds
    # Independent streams for the bits, noise, jammer and fade, so changing one
    # (e.g. the jammer power) never changes the others' realisation.
    @property
    def bit_seed(self) -> int:
        return int(self.seed)

    @property
    def noise_seed(self) -> int:
        return int(self.seed) * 4 + 1

    @property
    def jammer_seed(self) -> int:
        return int(self.seed) * 4 + 2

    @property
    def fading_seed(self) -> int:
        return int(self.seed) * 4 + 3

    @property
    def bits_per_symbol(self) -> int:
        return 1 if self.modulation == "BPSK" else 2

    @property
    def n_bits(self) -> int:
        return int(self.n_symbols) * self.bits_per_symbol

    @property
    def waveform_sample_rate(self) -> float:
        """Rate inside the flowgraph (oversampled for PSK)."""
        return float(self.symbol_rate) * (self.sps if self.modulation != "OFDM-QPSK" else 1)

    @property
    def payload_bits_per_second(self) -> float:
        """Raw payload bit rate before errors. OFDM pays the CP overhead (64/80)."""
        if self.modulation == "OFDM-QPSK":
            return 2.0 * OFDM_N_FFT / (OFDM_N_FFT + OFDM_CP_LEN) * self.symbol_rate
        return self.bits_per_symbol * self.symbol_rate

    @property
    def occupied_bandwidth_hz(self) -> float:
        """(1 + rolloff) Rs for RRC PSK; the full sample rate for OFDM (all 64 bins used)."""
        if self.modulation == "OFDM-QPSK":
            return float(self.symbol_rate)
        return (1.0 + self.rolloff) * self.symbol_rate

    def identity(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("extra", None)
        d["flowgraph_version"] = FLOWGRAPH_VERSION
        return d

    def config_hash(self) -> str:
        blob = json.dumps(self.identity(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def experiment_id(self, prefix: str = "gr") -> str:
        return f"{prefix}-{self.modulation}-{self.channel}-{self.fading_mode}-" \
               f"snr{self.snr_db:+.1f}-J{self.interference_power:.3f}-s{self.seed}-{self.config_hash()[:10]}"

    def replace(self, **kw) -> "GRPhyConfig":
        d = asdict(self)
        d.update(kw)
        return GRPhyConfig(**d)
