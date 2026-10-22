"""
Launch the CogniTwin-SDR dashboard from anywhere:

    python dashboard/run_dashboard.py [--server.port 8501]

Runs `streamlit run dashboard/app.py` with the repository root as the working
directory, so .streamlit/config.toml (dark theme) and relative paths apply.

If this interpreter cannot import GNU Radio, the launcher looks for a GNU Radio
conda environment that also has Streamlit and re-launches itself there, so
simulations can execute. Search order: $COGNITWIN_GR_PYTHON, then the
`cognitwin-gr` / `cognitwin-dash` environments of micromamba (D:\\micromamba,
%USERPROFILE%\\micromamba), radioconda and miniforge. `--no-gr-switch` keeps the
current interpreter (browse-only when it has no GNU Radio).
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENVS = ("cognitwin-gr", "cognitwin-dash")


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def candidate_pythons():
    if os.environ.get("COGNITWIN_GR_PYTHON"):
        yield os.environ["COGNITWIN_GR_PYTHON"]
    home = os.path.expanduser("~")
    roots = [r"D:\micromamba", os.path.join(home, "micromamba"), os.path.join(home, "radioconda"),
             os.path.join(home, "miniforge3"), os.path.join(home, "miniconda3"), r"C:\ProgramData\radioconda"]
    for root in roots:
        for env in ENVS:
            exe = os.path.join(root, "envs", env, "python.exe" if os.name == "nt" else "bin/python")
            if os.path.exists(exe):
                yield exe


def conda_env(exe: str) -> dict:
    """Environment for a conda python run without activation (DLL folders first on PATH on Windows)."""
    env = dict(os.environ)
    prefix = os.path.dirname(exe) if os.name == "nt" else os.path.dirname(os.path.dirname(exe))
    if os.name == "nt":
        extra = [prefix, os.path.join(prefix, "Library", "mingw-w64", "bin"), os.path.join(prefix, "Library", "usr", "bin"),
                 os.path.join(prefix, "Library", "bin"), os.path.join(prefix, "Scripts")]
    else:
        extra = [os.path.join(prefix, "bin")]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env["CONDA_PREFIX"] = prefix
    env["COGNITWIN_GR_SWITCHED"] = "1"
    return env


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--no-gr-switch"]
    if "--no-gr-switch" not in sys.argv and not os.environ.get("COGNITWIN_GR_SWITCHED") and not _has("gnuradio"):
        for exe in candidate_pythons():
            if os.path.normcase(os.path.abspath(exe)) == os.path.normcase(os.path.abspath(sys.executable)):
                continue
            env = conda_env(exe)
            probe = subprocess.run([exe, "-c", "import gnuradio.gr, streamlit"], env=env, capture_output=True)
            if probe.returncode == 0:
                print(f"GNU Radio found: relaunching with {exe}")
                return subprocess.call([exe, os.path.abspath(__file__), *args], env=env, cwd=ROOT)
        print("GNU Radio not found in this interpreter or a known conda environment: browse-only mode "
              "(see docs/DASHBOARD.md to enable execution).")
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print("Streamlit is not installed in this interpreter. Use the cognitwin-gr environment "
              "(docs/DASHBOARD.md).")
        return 2
    os.chdir(ROOT)
    sys.argv = ["streamlit", "run", os.path.join(ROOT, "dashboard", "app.py"), *args]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
