"""
Shared plumbing for the GNU Radio experiment scripts (gnuradio_*.py).

Every script calls blocked_or_none() first: without an importable GNU Radio it
prints BLOCKED with the import error and exits 2. No script ever falls back to
another data source.
"""

import datetime as _dt
import json
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (project_root, os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.gnuradio_phy.availability import gnuradio_available, gnuradio_version, unavailable_reason  # noqa: E402
from src.gnuradio_phy.export import DEFAULT_LEDGER as DEFAULT_LEDGER_PATH  # noqa: E402,F401

RESULTS = os.path.join(project_root, "results", "gnuradio")
EXIT_BLOCKED = 2


def blocked_or_none():
    """Return EXIT_BLOCKED (after printing why) if GNU Radio cannot run here, else None."""
    if gnuradio_available():
        print(f"GNU Radio {gnuradio_version()} available ({sys.executable})")
        return None
    print("BLOCKED: GNU Radio flowgraph NOT RUN.")
    print(unavailable_reason())
    print("Setup: docs/GNURADIO_SETUP.md")
    return EXIT_BLOCKED


def new_run_dir(kind: str, run_id: str = "") -> str:
    """results/gnuradio/<kind>/<run_id>/, refusing to reuse an existing folder."""
    run_id = run_id or _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    path = os.path.join(RESULTS, kind, run_id)
    if os.path.exists(path):
        raise FileExistsError(f"{path} exists; results are never overwritten (pass a new --run-id)")
    os.makedirs(path)
    return path


def git_commit() -> str:
    import closed_loop_evaluation as cle
    return cle._git_commit()


def write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, default=str)


def run_metadata(extra=None):
    meta = {
        "data_class": "GNU Radio software simulation (no SDR hardware, no over-the-air)",
        "gnuradio_version": gnuradio_version(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "commit": git_commit(),
        "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    meta.update(extra or {})
    return meta
