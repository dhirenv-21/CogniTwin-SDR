"""
Launch the CogniTwin-SDR dashboard from anywhere:

    <cognitwin-dash python> dashboard/run_dashboard.py [--server.port 8501]

Runs `streamlit run dashboard/app.py` with the repository root as the working
directory, so .streamlit/config.toml (dark theme) and relative paths apply.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print("Streamlit is not installed in this interpreter. Use the cognitwin-dash environment "
              "(docs/DASHBOARD.md).")
        return 2
    os.chdir(ROOT)
    sys.argv = ["streamlit", "run", os.path.join(ROOT, "dashboard", "app.py"), *sys.argv[1:]]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
