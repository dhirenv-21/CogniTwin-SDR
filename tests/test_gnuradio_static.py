"""
Static checks of the GNU Radio sources, the GRC demo and the experiment scripts.

Category: static. These prove the files are consistent with each other; they do
NOT prove that GNU Radio or GNU Radio Companion loads or runs them.
"""

import glob
import math
import os
import py_compile
import subprocess
import sys

import numpy as np
import pytest

from src.gnuradio_phy.availability import gnuradio_available
from src.gnuradio_phy.receiver import constellation_points

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "gnuradio_phy")
GRC = os.path.join(ROOT, "grc", "cognitwin_phy_demo.grc")
SCRIPTS = sorted(glob.glob(os.path.join(ROOT, "experiments", "gnuradio_*.py")))


def _src(name):
    with open(os.path.join(PKG, name), encoding="utf-8") as fh:
        return fh.read()


def test_only_flowgraph_and_probe_import_gnuradio():
    for path in glob.glob(os.path.join(PKG, "*.py")):
        text = open(path, encoding="utf-8").read()
        if os.path.basename(path) in ("flowgraph.py", "availability.py"):
            continue
        assert "from gnuradio" not in text and "import gnuradio" not in text, path


def test_package_import_does_not_need_gnuradio():
    code = "import sys, src.gnuradio_phy, src.gnuradio_phy.closed_loop; print('gnuradio' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    if not gnuradio_available():
        assert out.stdout.strip() == "False"


def test_flowgraph_uses_gnuradio_blocks_for_the_signal_chain():
    text = _src("flowgraph.py")
    for blk in ("digital.chunks_to_symbols_bc", "filter.interp_fir_filter_ccf", "filter.fir_filter_ccf",
                "filter.firdes.root_raised_cosine", "analog.noise_source_c", "blocks.add_vcc",
                "channels.fading_model", "blocks.multiply_const_cc", "fft.fft_vcc",
                "digital.ofdm_cyclic_prefixer", "gr.top_block"):
        assert blk in text, blk
    # NumPy draws only experiment parameters: the bits (draw_bits) and the one-per-run
    # block-fading gain (block_fading_gain). Noise, jammer and fading come from GNU Radio.
    assert text.count("np.random") == 2
    assert text.count("standard_normal(") == 2


def test_scripts_compile():
    for s in SCRIPTS:
        py_compile.compile(s, doraise=True)


@pytest.mark.skipif(gnuradio_available(), reason="GNU Radio installed: scripts would really run")
# gnuradio_common is a library; gnuradio_campaign_analysis only reads saved CSVs (no GNU Radio needed)
@pytest.mark.parametrize("script", [s for s in SCRIPTS if not s.endswith(("gnuradio_common.py",
                                                                          "gnuradio_campaign_analysis.py"))],
                         ids=lambda s: os.path.basename(s))
def test_scripts_report_blocked_without_gnuradio(script):
    out = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 2 and "BLOCKED" in out.stdout, (out.stdout, out.stderr)


# ------------------------------------------------------------------ GRC demo

yaml = pytest.importorskip("yaml")


@pytest.fixture(scope="module")
def grc():
    with open(GRC, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_grc_structure(grc):
    names = [b["name"] for b in grc["blocks"]]
    assert len(names) == len(set(names))
    assert grc["options"]["parameters"]["generate_options"] == "qt_gui"
    assert grc["metadata"]["file_format"] == 1
    for src, sp, dst, dp in grc["connections"]:
        assert src in names and dst in names and sp.isdigit() and dp.isdigit()
    ids = {b["id"] for b in grc["blocks"]}
    for needed in ("qtgui_time_sink_x", "qtgui_freq_sink_x", "qtgui_const_sink_x", "variable_qtgui_range",
                   "analog_noise_source_x", "interp_fir_filter_xxx", "fir_filter_xxx"):
        assert needed in ids, needed


def test_grc_matches_python_flowgraph(grc):
    blocks = {b["name"]: b for b in grc["blocks"]}
    table = eval(blocks["qpsk_map"]["parameters"]["symbol_table"], {"math": math})
    assert np.allclose(table, constellation_points("QPSK"))
    sliders = {b["name"] for b in grc["blocks"] if b["id"] == "variable_qtgui_range"}
    assert {"snr_db", "jammer_power"} <= sliders
    assert blocks["sps"]["parameters"]["value"] == "4"
    assert "0.35" in blocks["rrc_taps"]["parameters"]["value"] and "11 * sps + 1" in blocks["rrc_taps"]["parameters"]["value"]


def test_no_repository_folder_shadows_the_gnuradio_package():
    """A top-level 'gnuradio' folder becomes a namespace package on sys.path and hides
    the real GNU Radio ('cannot import name gr from gnuradio'). Found and fixed once."""
    for name in os.listdir(ROOT):
        assert name.lower() not in ("gnuradio", "gnuradio.py"), name
