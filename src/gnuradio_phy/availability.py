"""
Is GNU Radio importable here, and which version?

Every GNU Radio execution path calls require_gnuradio(), which raises
GNURadioUnavailable with the concrete import error. Nothing falls back to NumPy
samples: without GNU Radio there is no GNU Radio data.
"""

import functools
import sys
from typing import Optional, Tuple

INSTALL_HINT = (
    "GNU Radio is not importable from this interpreter ({exe}). Install it in a "
    "SEPARATE conda environment (see docs/GNURADIO_SETUP.md), e.g. radioconda or "
    "`conda create -n cognitwin-gr -c conda-forge gnuradio=3.10 scikit-learn=1.7.2 scipy matplotlib joblib pytest`, "
    "then run "
    "this command from that environment."
)


class GNURadioUnavailable(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def probe() -> Tuple[bool, Optional[str], str]:
    """(available, version, detail). Cached: the import is slow."""
    try:
        from gnuradio import gr  # noqa: F401
        from gnuradio import analog, blocks, channels, digital, fft, filter  # noqa: F401
    except Exception as exc:  # ImportError, or a DLL load failure on Windows
        return False, None, f"{type(exc).__name__}: {exc}"
    try:
        version = str(gr.version())
    except Exception as exc:
        return False, None, f"gnuradio imported but gr.version() failed: {exc}"
    return True, version, f"GNU Radio {version} at {getattr(gr, '__file__', '?')}"


def gnuradio_available() -> bool:
    return probe()[0]


def gnuradio_version() -> Optional[str]:
    return probe()[1]


def unavailable_reason() -> str:
    ok, _, detail = probe()
    return "" if ok else f"{INSTALL_HINT.format(exe=sys.executable)} Import error: {detail}"


def require_gnuradio() -> str:
    ok, version, _ = probe()
    if not ok:
        raise GNURadioUnavailable(unavailable_reason())
    return version
