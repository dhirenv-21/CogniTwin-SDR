"""
Design tokens, global CSS and the Plotly figure template for the dashboard.

Every colour the UI uses is defined here once; components and plots refer to the
tokens, never to literal hex values.
"""

import plotly.graph_objects as go

# ------------------------------------------------------------------ tokens
BG = "#080D18"
SIDEBAR = "#0D1423"
PANEL = "#111B2C"
ELEVATED = "#162237"
BORDER = "#25344A"
BORDER_SOFT = "#1B2738"
GRID = "#1A2638"

TEXT = "#E6EDF7"
TEXT_2 = "#8C9BB3"
TEXT_3 = "#5E6E87"

CYAN = "#38D9FF"
INDIGO = "#818CF8"
SUCCESS = "#34C79A"
WARNING = "#F5B54A"
ERROR = "#F2706B"
SLATE = "#94A3B8"

TONES = {"ok": SUCCESS, "warn": WARNING, "err": ERROR, "info": CYAN, "run": CYAN, "accent": INDIGO,
         "muted": TEXT_3, "neutral": TEXT_2}

# fixed colour per policy so a policy looks the same in every chart
POLICY_COLORS = {"acwra": CYAN, "sinr_threshold": INDIGO, "fixed_BPSK": SUCCESS, "fixed_QPSK": WARNING,
                 "fixed_OFDM-QPSK": "#E879A8", "no_adaptation": SLATE}
MOD_COLORS = {"BPSK": CYAN, "QPSK": INDIGO, "OFDM-QPSK": SUCCESS}

FONT_UI = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"
FONT_MONO = "'JetBrains Mono', 'Cascadia Mono', Consolas, monospace"


# ------------------------------------------------------------------ plots

def fig(height: int = 300, title: str = "", **layout) -> go.Figure:
    """An empty figure in the dashboard style (transparent paper, panel plot area, soft grid)."""
    f = go.Figure()
    f.update_layout(
        template="plotly_dark", height=height,
        margin=dict(l=56, r=16, t=40 if title else 16, b=48),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PANEL,
        font=dict(family=FONT_UI, size=11.5, color=TEXT_2),
        title=dict(text=title, font=dict(size=12.5, color=TEXT), x=0, xanchor="left", y=0.98) if title else dict(text=""),
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right", bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11, color=TEXT_2)),
        hoverlabel=dict(bgcolor=ELEVATED, bordercolor=BORDER, font=dict(family=FONT_MONO, size=11.5, color=TEXT)),
        colorway=[CYAN, INDIGO, SUCCESS, WARNING, ERROR, SLATE],
        **layout)
    axis = dict(gridcolor=GRID, zerolinecolor=BORDER, linecolor=BORDER, showline=True, mirror=False,
                tickfont=dict(family=FONT_MONO, size=10.5, color=TEXT_2), title_font=dict(size=11.5, color=TEXT_2),
                ticks="outside", tickcolor=BORDER, ticklen=4)
    f.update_xaxes(**axis)
    f.update_yaxes(**axis)
    return f


PLOT_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
               "toImageButtonOptions": {"format": "png", "scale": 2}}


# ------------------------------------------------------------------ CSS

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
  --bg:{BG}; --sidebar:{SIDEBAR}; --panel:{PANEL}; --elev:{ELEVATED}; --border:{BORDER}; --border-soft:{BORDER_SOFT};
  --text:{TEXT}; --text-2:{TEXT_2}; --text-3:{TEXT_3};
  --cyan:{CYAN}; --indigo:{INDIGO}; --ok:{SUCCESS}; --warn:{WARNING}; --err:{ERROR};
  --mono:{FONT_MONO}; --ui:{FONT_UI};
  --r-sm:6px; --r-md:10px; --r-lg:14px;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
}}

/* ---------- shell ---------- */
html, body, [data-testid="stApp"] {{ background:var(--bg); }}
header[data-testid="stHeader"] {{ background:transparent; height:2.5rem; }}
[data-testid="stMainBlockContainer"], .block-container {{
  padding-top:1.1rem !important; padding-bottom:3rem !important; max-width:1680px; }}
[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] {{ display:none; }}
[data-testid="stSidebar"] {{ border-right:1px solid var(--border-soft); }}
[data-testid="stSidebarHeader"] {{ padding-bottom:.25rem; }}
[data-testid="stSidebarNav"] {{ padding-top:.25rem; }}
[data-testid="stSidebarNavItems"] {{ gap:2px; }}
[data-testid="stSidebarNavLink"] {{ border-radius:8px; padding:.42rem .7rem; margin:0 .25rem; transition:background .15s ease; }}
[data-testid="stSidebarNavLink"] span {{ color:var(--text-2); font-weight:500; font-size:.88rem; }}
[data-testid="stSidebarNavLink"]:hover {{ background:rgba(56,217,255,.06); }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{ background:rgba(56,217,255,.10);
  box-shadow: inset 2px 0 0 var(--cyan); }}
[data-testid="stSidebarNavLink"][aria-current="page"] span {{ color:var(--text); }}
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {{ color:var(--text-3); }}
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {{ color:var(--cyan); }}
[data-testid="stSidebarNavSeparator"] {{ border-color:var(--border-soft); }}

/* ---------- typography ---------- */
h1, h2, h3, h4 {{ letter-spacing:-.01em; }}
.mono, code {{ font-family:var(--mono) !important; }}
p, li {{ color:var(--text); }}
[data-testid="stCaptionContainer"] {{ color:var(--text-3); }}

/* ---------- native widgets ---------- */
[data-testid="stWidgetLabel"] p {{ color:var(--text-2); font-size:.8rem; font-weight:500; }}
.stButton > button, .stDownloadButton > button, [data-testid="stBaseButton-secondary"] {{
  border-radius:8px; font-weight:600; letter-spacing:.01em; transition:all .15s ease; }}
[data-testid="stBaseButton-primary"] {{ background:var(--cyan); color:#04121C; border:1px solid var(--cyan); }}
[data-testid="stBaseButton-primary"]:hover {{ background:#5fe2ff; border-color:#5fe2ff; color:#04121C; }}
[data-testid="stBaseButton-primary"]:disabled {{ background:rgba(56,217,255,.18); border-color:transparent;
  color:rgba(230,237,247,.45); }}
button:focus-visible, [role="tab"]:focus-visible, input:focus-visible, a:focus-visible {{
  outline:2px solid var(--cyan) !important; outline-offset:2px; }}
[data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stVerticalBlock"][class*="Border"] {{ border-radius:var(--r-lg); }}
[data-testid="stExpander"] details {{ border-color:var(--border-soft); border-radius:var(--r-md); background:var(--panel); }}
[data-testid="stTabs"] [role="tablist"] {{ gap:1.25rem; border-bottom:1px solid var(--border-soft); }}
[data-testid="stTabs"] [role="tab"] p {{ font-size:.84rem; font-weight:500; }}
[data-testid="stProgress"] > div > div > div > div {{ background:var(--cyan); }}
[data-testid="stDataFrame"] {{ border-radius:var(--r-md); }}
[data-testid="stPlotlyChart"] {{ border-radius:var(--r-md); }}
[data-testid="stAlert"] {{ border-radius:var(--r-md); }}

/* ---------- bordered panels (st.container(border=True)) ---------- */
.st-key-panel, [class*="st-key-panel_"] {{ background:var(--panel); border:1px solid var(--border-soft) !important;
  border-radius:var(--r-lg) !important; padding:var(--s4) var(--s4) var(--s3) !important; }}

/* rendered markdown documents (reports) inside panels */
[class*="st-key-panel_"] [data-testid="stMarkdownContainer"] h1 {{ font-size:1.2rem; font-weight:650; padding:.2rem 0 .4rem; }}
[class*="st-key-panel_"] [data-testid="stMarkdownContainer"] h2 {{ font-size:1rem; font-weight:600; padding:.6rem 0 .3rem;
  color:var(--text-2); }}
[class*="st-key-panel_"] [data-testid="stMarkdownContainer"] table {{ font-size:.8rem; }}
[class*="st-key-panel_"] [data-testid="stMarkdownContainer"] td {{ font-family:var(--mono); font-size:.76rem; }}

/* ---------- top bar ---------- */
.ct-top {{ display:flex; align-items:flex-end; justify-content:space-between; gap:var(--s4); flex-wrap:wrap;
  padding-bottom:var(--s3); margin-bottom:var(--s4); border-bottom:1px solid var(--border-soft); }}
.ct-crumb {{ font-size:.74rem; color:var(--text-3); letter-spacing:.04em; display:flex; align-items:center; gap:6px; }}
.ct-crumb b {{ color:var(--text-2); font-weight:500; }}
.ct-title {{ font-size:1.5rem; font-weight:650; color:var(--text); margin-top:2px; letter-spacing:-.015em; line-height:1.2; }}
.ct-sub {{ font-size:.84rem; color:var(--text-2); margin-top:2px; }}
.ct-status {{ display:flex; gap:var(--s2); flex-wrap:wrap; align-items:center; }}

/* ---------- chips / badges ---------- */
.chip {{ display:inline-flex; align-items:center; gap:6px; height:26px; padding:0 10px; border-radius:999px;
  border:1px solid var(--border); background:var(--panel); color:var(--text-2); font-size:.76rem; font-weight:500;
  white-space:nowrap; }}
.chip .dot {{ width:7px; height:7px; border-radius:50%; background:var(--c); flex:none; }}
.chip.run .dot {{ animation:ctpulse 1.6s ease-in-out infinite; }}
.chip .mono {{ font-size:.74rem; color:var(--text); }}
@keyframes ctpulse {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(56,217,255,.55) }} 50% {{ box-shadow:0 0 0 4px rgba(56,217,255,0) }} }}
.badge {{ display:inline-flex; align-items:center; gap:5px; padding:1px 8px; border-radius:6px; font-size:.7rem;
  font-weight:600; letter-spacing:.03em; color:var(--c); background:color-mix(in srgb, var(--c) 13%, transparent);
  border:1px solid color-mix(in srgb, var(--c) 28%, transparent); white-space:nowrap; text-transform:uppercase; }}

/* ---------- section headers ---------- */
.ct-sec {{ display:flex; align-items:baseline; justify-content:space-between; gap:var(--s3); margin:2px 0 var(--s2); }}
.ct-sec .h {{ margin:0; padding:0; line-height:1.4; font-size:.78rem; font-weight:600; color:var(--text-2); text-transform:uppercase;
  letter-spacing:.09em; display:flex; align-items:center; gap:8px; }}
.ct-sec .h svg {{ flex:none; color:var(--cyan); }}
.ct-sec .r {{ font-size:.76rem; color:var(--text-3); }}

/* ---------- metric cards ---------- */
.ct-metrics {{ display:grid; gap:var(--s3); grid-template-columns:repeat(auto-fit, minmax(var(--min,170px), 1fr));
  margin-bottom:var(--s4); }}
.ct-metric {{ background:var(--panel); border:1px solid var(--border-soft); border-radius:var(--r-lg);
  padding:14px 16px 13px; position:relative; overflow:hidden; transition:border-color .15s ease; min-width:0; }}
.ct-metric:hover {{ border-color:var(--border); }}
.ct-metric .k {{ font-size:.72rem; color:var(--text-2); font-weight:500; display:flex; align-items:center; gap:7px;
  letter-spacing:.02em; }}
.ct-metric .k svg {{ color:var(--c, var(--text-3)); flex:none; }}
.ct-metric .v {{ font-family:var(--mono); font-size:1.42rem; font-weight:500; color:var(--vc, var(--text));
  margin-top:8px; line-height:1.15; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; letter-spacing:-.02em; }}
.ct-metric .v small {{ font-size:.78rem; color:var(--text-2); margin-left:4px; font-family:var(--ui); letter-spacing:0; }}
.ct-metric .s {{ font-size:.72rem; color:var(--text-3); margin-top:5px; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }}
.ct-metric .v.long {{ font-size:1.12rem; font-family:var(--ui); font-weight:600; letter-spacing:-.01em; padding-top:3px; }}
.ct-metric.compact {{ padding:10px 12px 9px; }}
.ct-metric.compact .v {{ font-size:1.08rem; margin-top:5px; }}
.ct-metric::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:var(--c, transparent);
  opacity:.85; }}

/* ---------- empty state ---------- */
.ct-empty {{ border:1px dashed var(--border); border-radius:var(--r-lg); padding:36px 24px; text-align:center;
  background:linear-gradient(180deg, rgba(56,217,255,.025), transparent); }}
.ct-empty .ic {{ width:44px; height:44px; border-radius:12px; margin:0 auto 12px; display:grid; place-items:center;
  background:rgba(56,217,255,.08); color:var(--cyan); border:1px solid rgba(56,217,255,.18); }}
.ct-empty .t {{ font-weight:600; color:var(--text); font-size:.95rem; }}
.ct-empty .b {{ color:var(--text-2); font-size:.82rem; margin-top:4px; max-width:460px; margin-left:auto; margin-right:auto; }}

/* ---------- pipeline ---------- */
.ct-pipe {{ display:flex; flex-wrap:wrap; align-items:stretch; gap:0; row-gap:10px; padding:2px 2px 8px; }}
.ct-node {{ flex:1 1 104px; min-width:104px; background:var(--panel); border:1px solid var(--border-soft);
  border-radius:var(--r-md); padding:10px 11px; position:relative; transition:border-color .15s ease, background .15s ease; }}
.ct-node.sel {{ border-color:var(--c); background:color-mix(in srgb, var(--c) 6%, var(--panel)); }}
.ct-node .n {{ display:flex; align-items:center; gap:6px; font-size:.7rem; font-weight:600; color:var(--text-2);
  text-transform:uppercase; letter-spacing:.06em; }}
.ct-node .n svg {{ color:var(--c); flex:none; }}
.ct-node .st {{ margin-top:6px; }}
.ct-node .o {{ margin-top:6px; font-family:var(--mono); font-size:.76rem; color:var(--text); line-height:1.35;
  word-break:break-word; }}
.ct-node .o.na {{ color:var(--text-3); font-family:var(--ui); }}
.ct-link {{ flex:0 0 12px; align-self:center; height:1px; background:var(--border); position:relative; }}
.ct-link::after {{ content:""; position:absolute; right:0; top:-3px; border:3.5px solid transparent; border-left:5px solid var(--border); }}

/* ---------- key/value list ---------- */
.ct-kv {{ display:grid; grid-template-columns:minmax(110px, auto) 1fr; gap:6px 14px; font-size:.82rem; }}
.ct-kv .k {{ color:var(--text-3); }}
.ct-kv .v {{ color:var(--text); font-family:var(--mono); font-size:.79rem; word-break:break-word; }}

/* ---------- activity list ---------- */
.ct-list {{ display:flex; flex-direction:column; }}
.ct-row {{ display:flex; align-items:center; gap:10px; padding:9px 2px; border-bottom:1px solid var(--border-soft);
  font-size:.82rem; min-width:0; }}
.ct-row:last-child {{ border-bottom:none; }}
.ct-row .id {{ font-family:var(--mono); color:var(--text); font-size:.78rem; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; flex:1; min-width:0; }}
.ct-row .m {{ color:var(--text-3); font-size:.74rem; white-space:nowrap; }}

/* ---------- sidebar brand + status ---------- */
.ct-side-status {{ margin:8px 4px 0; padding:12px; border:1px solid var(--border-soft); border-radius:var(--r-md);
  background:rgba(8,13,24,.5); font-size:.76rem; color:var(--text-2); }}
.ct-side-status .row {{ display:flex; align-items:center; gap:8px; padding:3px 0; }}
.ct-side-status .dot {{ width:7px; height:7px; border-radius:50%; background:var(--c); flex:none; }}
.ct-side-foot {{ color:var(--text-3); font-size:.7rem; margin:10px 6px 0; }}

/* ---------- misc ---------- */
.ct-note {{ font-size:.78rem; color:var(--text-3); margin-top:4px; }}
.ct-note b {{ color:var(--text-2); font-weight:500; }}
.ct-err {{ color:var(--err); font-size:.76rem; margin:-.35rem 0 .45rem; display:flex; gap:6px; align-items:center; }}
.ct-summary {{ background:var(--elev); border:1px solid var(--border); border-radius:var(--r-md); padding:12px 14px; }}
.ct-summary .big {{ font-family:var(--mono); font-size:1.25rem; color:var(--text); }}
.ct-finding {{ border-left:2px solid var(--c); padding:6px 0 6px 12px; margin:6px 0; font-size:.84rem; color:var(--text); }}
.ct-finding .k {{ color:var(--text-3); font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; }}
hr {{ border-color:var(--border-soft) !important; }}

@media (max-width: 1100px) {{
  .ct-title {{ font-size:1.25rem; }}
  .ct-node {{ min-width:120px; }}
}}
@media (max-width: 1200px) {{
  /* laptop / tablet: columns wrap instead of shrinking below a readable width */
  [data-testid="stMain"] [data-testid="stHorizontalBlock"] {{ flex-wrap:wrap; row-gap:var(--s3); }}
  [data-testid="stMain"] [data-testid="stColumn"] {{ flex:1 1 260px !important; min-width:min(100%, 260px) !important; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ animation:none !important; transition:none !important; }} }}
</style>
"""
