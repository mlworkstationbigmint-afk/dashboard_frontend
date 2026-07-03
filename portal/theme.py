"""
BigMint - AI Labs portal: brand theme, CSS and shared UI helpers.
Colours sampled from the bigmint.co logo/site (blue + orange accent).
"""
import os
import base64
import streamlit as st

# ---- Brand palette ----
PRIMARY      = "#024CA1"   # BigMint blue (logo bg -> seamless top bar)
PRIMARY_DARK = "#023A7A"
PRIMARY_SOFT = "#EAF1FB"
ACCENT       = "#EE4E24"   # orange / red CTA accent
SUCCESS      = "#1F9D55"   # up
DANGER       = "#D8382B"   # down
NEUTRAL      = "#64748B"   # flat / muted
BG_SOFT      = "#F4F6FA"

# chart line colours (actual = light blue, forecast = bold red w/ soft halo)
SPOT_LINE     = "#5E92D6"
SPOT_DARK     = "#1F5FA8"
FORECAST_LINE = "#E12B20"
FORECAST_HALO = "rgba(225,43,32,0.16)"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO_PATH  = os.path.join(ASSETS_DIR, "bigmint_logo.png")
# Adani co-brand logo: prefer the trimmed asset, fall back to the untrimmed original.
ADANI_LOGO_CANDIDATES = [
    os.path.join(ASSETS_DIR, "adani_logo.png"),
    os.path.join(ASSETS_DIR, "adani_logo_orig.png"),
]


def _logo_html(height: int = 30) -> str:
    if os.path.exists(LOGO_PATH):
        try:
            with open(LOGO_PATH, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return f"<img src='data:image/png;base64,{b64}' style='height:{height}px;display:block;'/>"
        except Exception:
            pass
    return ("<span style='font-weight:800;font-size:22px;letter-spacing:.6px;color:#fff;'>BigMint</span>")


def _adani_logo_html(height: int = 26) -> str:
    """Adani co-brand logo. Uses assets/adani_logo.png (trimmed), else
    assets/adani_logo_orig.png; otherwise a gradient 'adani' wordmark approximation."""
    for path in ADANI_LOGO_CANDIDATES:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                return f"<img src='data:image/png;base64,{b64}' style='height:{height}px;display:block;'/>"
            except Exception:
                continue
    return ("<span style='font-weight:800;font-size:21px;letter-spacing:.2px;"
            "background:linear-gradient(90deg,#1196C6,#6A4DA3,#C42A6B);"
            "-webkit-background-clip:text;background-clip:text;"
            "color:transparent;-webkit-text-fill-color:transparent;'>adani</span>")


def inject_css():
    st.markdown(f"""
<style>
.stApp {{ background-color: {BG_SOFT}; }}
.block-container {{ padding-top: 1rem !important; padding-bottom: 2rem; max-width: 1180px; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
#MainMenu, footer {{ visibility: hidden; }}
section[data-testid="stSidebar"], div[data-testid="collapsedControl"] {{ display: none !important; }}

/* ---------- top brand bar ---------- */
.bm-topbar {{
    background: {PRIMARY}; border-radius: 12px; padding: 13px 22px;
    display: flex; align-items: center; justify-content: space-between;
    margin: 0 0 14px 0; box-shadow: 0 2px 10px rgba(2,76,161,.18);
}}
.bm-topbar-l {{ display:flex; align-items:center; gap:13px; }}
.bm-cobrand-x {{ color:#cfe0f5; font-size:17px; font-weight:600; }}
.bm-adani-chip {{ background:#fff; border-radius:8px; padding:5px 11px; display:inline-flex;
    align-items:center; box-shadow:0 1px 3px rgba(0,0,0,.14); }}
.bm-portal-title {{ color:#fff; font-size:15px; font-weight:600; opacity:.96; }}
.bm-topbar-r {{ color:#cfe0f5; font-size:12.5px; text-align:right; line-height:1.4; }}
.bm-topbar-r b {{ color:#fff; }}

/* ---------- nav pills (st.button based) ---------- */
div[data-testid="stHorizontalBlock"] {{ align-items: stretch; }}
.stButton > button {{ border-radius: 9px; font-weight: 600; transition: all .15s ease; }}
.stButton > button[kind="secondary"] {{
    background:#fff; border:1px solid #dbe3ee; color:#334155;
}}
.stButton > button[kind="secondary"]:hover {{
    border-color:{PRIMARY}; color:{PRIMARY}; background:{PRIMARY_SOFT};
}}
.stButton > button[kind="primary"] {{ box-shadow:0 2px 8px rgba(2,76,161,.25); }}

/* ---------- Log out button: invert (orange) on hover ---------- */
div[class*="st-key-logout_top"] button:hover {{
    background:#fff !important; border:1px solid {ACCENT} !important; color:{ACCENT} !important;
    box-shadow:0 2px 8px rgba(238,78,36,.20);
}}
div[class*="st-key-logout_top"] button:hover [data-testid="stIconMaterial"],
div[class*="st-key-logout_top"] button:hover p {{ color:{ACCENT} !important; }}

/* ---------- home module card-buttons (whole card is one clickable button) ---------- */
/* layout: icon on top -> **title** (strong) -> brief (p text) -> *Open ->* (em CTA) */
div[class*="st-key-homemod_"] button {{
    height:100%; min-height:196px; flex-direction:column;
    align-items:flex-start; justify-content:flex-start; gap:0;
    text-align:left; white-space:normal; padding:22px 22px 20px; border-radius:16px;
    border:1px solid #e8edf3 !important; background:#fff !important;
    box-shadow:0 1px 2px rgba(16,24,40,.05); font-weight:400;
    transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease, background .18s ease;
}}
div[class*="st-key-homemod_"] button:hover {{
    border-color:{PRIMARY} !important; background:{PRIMARY_SOFT} !important;
    transform:translateY(-3px); box-shadow:0 10px 26px rgba(2,76,161,.12);
}}
/* leading material icon -> larger, on its own row above the text */
div[class*="st-key-homemod_"] button [data-testid="stIconMaterial"] {{
    font-size:30px !important; width:30px; height:30px; color:{PRIMARY}; margin-bottom:14px;
}}
div[class*="st-key-homemod_"] button strong {{
    display:block; font-size:18px; color:{PRIMARY_DARK}; font-weight:700; margin-bottom:6px;
}}
div[class*="st-key-homemod_"] button p {{ font-size:13.5px; color:{NEUTRAL}; line-height:1.5; margin:0; font-weight:400; }}
/* "Open ->" call-to-action (rendered from the *Open ->* em in the label) */
div[class*="st-key-homemod_"] button em {{
    display:block; font-style:normal; font-weight:700; color:{ACCENT};
    font-size:13px; letter-spacing:.3px; margin-top:14px;
}}

/* ---------- home Methodology banner (full-width button spanning the 4 cards) ---------- */
div[class*="st-key-home_methodology"] {{ margin-top:16px; }}
div[class*="st-key-home_methodology"] button {{
    width:100%; min-height:92px; flex-direction:row; align-items:center; justify-content:flex-start;
    gap:18px; text-align:left; white-space:normal; padding:24px 28px; border-radius:18px;
    border:1px solid #e8edf3 !important; color:{PRIMARY_DARK} !important; font-weight:400;
    background:#fff !important;
    box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease, background .18s ease;
}}
div[class*="st-key-home_methodology"] button:hover {{
    border-color:{PRIMARY} !important; background:{PRIMARY_SOFT} !important;
    transform:translateY(-2px); box-shadow:0 10px 26px rgba(2,76,161,.12);
}}
div[class*="st-key-home_methodology"] button [data-testid="stIconMaterial"] {{
    font-size:32px !important; width:32px; height:32px; color:{PRIMARY};
}}
/* let the label row stretch so the CTA can sit at the far right */
div[class*="st-key-home_methodology"] button [data-testid="stMarkdownContainer"] {{ flex:1 1 auto; }}
div[class*="st-key-home_methodology"] button [data-testid="stMarkdownContainer"] p {{
    display:flex; align-items:center; flex-wrap:wrap; gap:4px 12px; margin:0;
}}
div[class*="st-key-home_methodology"] button strong {{
    font-size:20px; color:{PRIMARY_DARK}; font-weight:800; letter-spacing:.2px;
}}
div[class*="st-key-home_methodology"] button p {{ font-size:13.5px; color:{NEUTRAL}; font-weight:400; }}
/* "View ->" CTA -> solid orange pill, pushed to the right, reads as clickable (whole banner navigates) */
div[class*="st-key-home_methodology"] button em {{
    margin-left:auto; font-style:normal; font-weight:800; color:#fff;
    background:{ACCENT}; padding:9px 20px; border-radius:10px; font-size:14px; white-space:nowrap;
    box-shadow:0 2px 8px rgba(238,78,36,.30);
}}
div[class*="st-key-home_methodology"] button:hover em {{ filter:brightness(.97); }}

/* ---------- direction chips ---------- */
.dir-chip {{ font-size:12px; font-weight:600; padding:3px 10px; border-radius:20px; white-space:nowrap; display:inline-block; }}
.dir-up   {{ background:#e7f6ee; color:{SUCCESS}; }}
.dir-down {{ background:#fbe9e7; color:{DANGER}; }}
.dir-flat {{ background:#eef1f5; color:{NEUTRAL}; }}

/* ---------- cards / KPIs ---------- */
.bm-card {{ background:#fff; border:1px solid #e8edf3; border-radius:14px; padding:16px 18px; height:100%;
    box-shadow:0 1px 2px rgba(16,24,40,.04); transition:transform .18s ease, box-shadow .18s ease; }}
.bm-card:hover {{ transform:translateY(-2px); box-shadow:0 8px 22px rgba(2,76,161,.10); }}
.bm-kpi-top {{ display:flex; align-items:center; gap:8px; margin-bottom:6px; }}
.bm-kpi-icon {{ width:30px;height:30px;border-radius:8px;background:{PRIMARY_SOFT};color:{PRIMARY};
    display:flex;align-items:center;justify-content:center;font-size:17px; }}
.bm-kpi-label {{ color:{NEUTRAL}; font-size:13px; font-weight:500; }}
.bm-kpi-value {{ font-size:26px; font-weight:700; color:#0f172a; line-height:1.15; }}
.bm-kpi-sub {{ font-size:12.5px; color:{NEUTRAL}; margin-top:4px; }}
.bm-card h4 {{ margin:2px 0 4px 0; color:{PRIMARY_DARK}; font-size:16px; }}
.bm-card .bm-desc {{ color:{NEUTRAL}; font-size:13px; }}

/* analyst-call detailed summary: label + one-line section rows */
.bm-call-secs {{ margin:8px 0 2px 0; }}
.bm-call-sec {{ display:flex; gap:12px; padding:7px 0; border-top:1px dashed #eef2f7; font-size:13.5px; line-height:1.45; }}
.bm-call-sec:first-child {{ border-top:none; }}
.bm-call-sec-l {{ flex:0 0 140px; font-weight:700; color:{PRIMARY_DARK}; }}
.bm-call-sec-t {{ color:{NEUTRAL}; }}

/* section heading */
.bm-h {{ font-size:15px; font-weight:600; color:{PRIMARY_DARK}; margin:6px 0 6px 0;
    display:flex; align-items:center; gap:8px; }}

/* ---------- tables ---------- */
.bm-table {{ width:100%; border-collapse:collapse; font-size:13.5px; background:#fff;
    border:1px solid #e8edf3; border-radius:12px; overflow:hidden; }}
.bm-table thead th {{ background:{PRIMARY_SOFT}; color:{PRIMARY_DARK}; font-weight:600;
    padding:10px 12px; text-align:left; }}
.bm-table tbody td {{ padding:9px 12px; border-top:1px solid #eef2f7; color:#334155; }}
.bm-table tbody tr:hover {{ background:#f7faff; }}
/* forecast (future) rows in the continuous forecasting table -> faint orange band (matches chart) */
.bm-table tbody tr.bm-fc-row {{ background:rgba(238,78,36,0.05); }}
.bm-table tbody tr.bm-fc-row:hover {{ background:rgba(238,78,36,0.10); }}
.bm-r {{ text-align:right; font-variant-numeric:tabular-nums; }}
.bm-c {{ text-align:center; }}
/* larger table variant (used for the forecast-path table so it matches the chart's footprint) */
.bm-table-lg {{ font-size:15px; box-shadow:0 1px 2px rgba(16,24,40,.05); }}
.bm-table-lg thead th {{ padding:14px 18px; font-size:13px; letter-spacing:.3px; text-transform:uppercase; }}
.bm-table-lg tbody td {{ padding:13px 18px; }}

/* ---------- tabs -> sliding segmented switch (white pill glides to the active tab) ---------- */
div[data-baseweb="tab-list"] {{
    position:relative; gap:6px; background:#e9edf4; padding:5px; border-radius:13px; margin-bottom:6px;
    border-bottom:none !important; display:inline-flex; width:auto;
    box-shadow:inset 0 1px 2px rgba(16,24,40,.06);
}}
/* baseweb's tab-highlight, repurposed from a bottom underline into a full-height pill.
   baseweb positions it via `transform: translateX()` (NOT `left`) and updates `width`
   as you switch tabs, so the transition MUST cover transform/width for the pill to glide. */
div[data-baseweb="tab-highlight"] {{
    top:5px !important; bottom:5px !important; height:auto !important; z-index:0 !important;
    border-radius:9px !important; background:#fff !important;
    box-shadow:0 1px 4px rgba(16,24,40,.16) !important;
    transition:transform .28s cubic-bezier(.4,0,.2,1), width .28s cubic-bezier(.4,0,.2,1) !important;
}}
div[data-baseweb="tab-border"] {{ display:none !important; }}
button[data-baseweb="tab"] {{
    position:relative; z-index:1; font-size:14.5px; font-weight:600; color:{NEUTRAL};
    background:transparent !important; border:none !important; border-radius:9px;
    padding:9px 26px; margin:0; height:auto; transition:color .2s ease;
}}
button[data-baseweb="tab"]:not([aria-selected="true"]):hover {{ color:{PRIMARY_DARK}; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color:{ACCENT} !important; font-weight:700; }}
/* segmented selectors (Product) -> orange active */
button[data-testid="stBaseButton-segmented_controlActive"] {{
    color:{ACCENT} !important; border-color:{ACCENT} !important;
    background-color:rgba(238,78,36,0.10) !important;
}}
button[data-testid="stBaseButton-segmented_controlActive"] p {{ color:{ACCENT} !important; }}

/* ---------- methodology infographics ---------- */
.bm-meth-hero {{ background:linear-gradient(120deg,{PRIMARY} 0%,{PRIMARY_DARK} 100%); color:#fff;
    border-radius:16px; padding:22px 26px; margin:2px 0 18px; box-shadow:0 6px 22px rgba(2,76,161,.20); }}
.bm-meth-hero h3 {{ margin:0 0 6px; font-size:20px; color:#fff; }}
.bm-meth-hero p {{ margin:0; font-size:14px; line-height:1.6; color:#dce8f8; max-width:860px; }}
/* stat strip */
.bm-stat-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:0 0 20px; }}
.bm-stat {{ background:#fff; border:1px solid #e8edf3; border-radius:14px; padding:16px 18px; text-align:center;
    box-shadow:0 1px 2px rgba(16,24,40,.05); }}
.bm-stat-v {{ font-size:24px; font-weight:800; color:{PRIMARY_DARK}; line-height:1.1; }}
.bm-stat-l {{ font-size:12.5px; color:{NEUTRAL}; margin-top:4px; }}
/* horizontal process flow — one continuous pipeline (single row, arrows between).
   CSS grid (card / arrow / card / …) so it never wraps into an awkward 3+3 jump;
   collapses to a vertical column on narrow screens (media query below). */
.bm-flow {{ display:grid; grid-template-columns:1fr auto 1fr auto 1fr auto 1fr auto 1fr auto 1fr;
    align-items:stretch; gap:0 4px; margin:18px 0 14px; }}
.bm-flow-step {{ background:#fff; border:1px solid #e8edf3; border-radius:14px;
    padding:20px 16px 15px; position:relative; box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:transform .15s ease, box-shadow .15s ease; }}
.bm-flow-step:hover {{ transform:translateY(-2px); box-shadow:0 8px 20px rgba(2,76,161,.10); }}
.bm-flow-step .num {{ position:absolute; top:-12px; left:16px; width:26px; height:26px; border-radius:50%;
    background:{ACCENT}; color:#fff; font-size:12.5px; font-weight:700; display:flex; align-items:center;
    justify-content:center; box-shadow:0 2px 6px rgba(238,78,36,.35); }}
.bm-flow-step .ic {{ width:38px; height:38px; border-radius:10px; background:{PRIMARY_SOFT}; color:{PRIMARY};
    display:flex; align-items:center; justify-content:center; margin:2px 0 10px; }}
.bm-flow-step h5 {{ margin:0 0 6px; font-size:14px; line-height:1.3; min-height:2.6em;
    color:{PRIMARY_DARK}; font-weight:700; }}   /* reserve 2 lines so all descriptions align */
.bm-flow-step p {{ margin:0; font-size:12.5px; color:{NEUTRAL}; line-height:1.45; }}
/* arrow pinned to the icon row (align-self:start + padding) so 1..6 share one flow line */
.bm-flow-arrow {{ align-self:start; padding-top:30px; display:flex; align-items:flex-start;
    justify-content:center; color:{ACCENT}; font-size:18px; font-weight:700; }}
/* factor grid */
.bm-factor-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:6px 0; }}
.bm-factor {{ display:flex; gap:12px; align-items:flex-start; background:#fff; border:1px solid #e8edf3;
    border-radius:14px; padding:14px 16px; box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:transform .15s ease, box-shadow .15s ease; }}
.bm-factor:hover {{ transform:translateY(-2px); box-shadow:0 8px 20px rgba(2,76,161,.10); }}
.bm-factor .ic {{ flex:0 0 38px; width:38px; height:38px; border-radius:10px; background:{PRIMARY_SOFT}; color:{PRIMARY};
    display:flex; align-items:center; justify-content:center; }}
.bm-factor h5 {{ margin:0 0 2px; font-size:13.5px; color:{PRIMARY_DARK}; font-weight:700; }}
.bm-factor p {{ margin:0; font-size:12.5px; color:{NEUTRAL}; line-height:1.4; }}
/* horizon cards */
.bm-horizon-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:6px 0; }}
.bm-horizon {{ background:#fff; border:1px solid #e8edf3; border-top:3px solid {ACCENT}; border-radius:14px;
    padding:16px 18px; box-shadow:0 1px 2px rgba(16,24,40,.05); }}
.bm-horizon h5 {{ margin:0 0 4px; font-size:15px; color:{PRIMARY_DARK}; }}
.bm-horizon p {{ margin:0; font-size:12.5px; color:{NEUTRAL}; line-height:1.5; }}
.bm-horizon .tag {{ display:inline-block; font-size:11px; font-weight:700; color:{ACCENT};
    background:rgba(238,78,36,.10); border-radius:20px; padding:2px 10px; margin-bottom:8px; }}
@media (max-width:900px) {{
    /* pipeline: single row -> vertical column, arrows rotate to point downward */
    .bm-flow {{ grid-template-columns:1fr; }}
    .bm-flow-step {{ margin:0 0 4px; }}
    .bm-flow-arrow {{ transform:rotate(90deg); margin:3px 0; padding-top:0; align-self:center; }}
}}
@media (max-width:760px) {{
    .bm-stat-row, .bm-factor-grid, .bm-horizon-grid {{ grid-template-columns:1fr 1fr; }}
}}

/* links / footer */
.bm-link-btn a {{ display:inline-block; background:{ACCENT}; color:#fff!important; text-decoration:none;
    padding:11px 20px; border-radius:9px; font-weight:600; font-size:14px; box-shadow:0 2px 8px rgba(238,78,36,.25); }}
.bm-link-btn a:hover {{ filter:brightness(.95); }}
.bm-footnote {{ color:{NEUTRAL}; font-size:12px; margin-top:8px; }}
.bm-footer {{ margin-top:26px; padding-top:14px; border-top:1px solid #e2e8f0; color:{NEUTRAL};
    font-size:12px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
.bm-footer a {{ color:{PRIMARY}; text-decoration:none; }}
</style>
""", unsafe_allow_html=True)


_ICON_PATHS = {
    "home":       "<path d='M3 11l9-8 9 8'/><path d='M5 10v10h14V10'/>",
    "trending":   "<path d='M3 17l6-6 4 4 8-8'/><path d='M21 8V14M21 8h-6' stroke-linejoin='round'/>",
    "mic":        "<rect x='9' y='3' width='6' height='11' rx='3'/><path d='M5 11a7 7 0 0 0 14 0'/><path d='M12 18v3'/>",
    "gauge":      "<path d='M3 14a9 9 0 0 1 18 0'/><path d='M12 14l4-3'/>",
    "calculator": "<rect x='5' y='3' width='14' height='18' rx='2'/><path d='M8 7h8'/><path d='M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 18h.01M12 18h.01M16 18h.01'/>",
    "rupee":      "<path d='M7 4h10M7 8h10M16 4c0 5-4 6-9 6 4 0 7 4 7 8'/>",
    "calendar":   "<rect x='4' y='5' width='16' height='16' rx='2'/><path d='M16 3v4M8 3v4M4 11h16'/>",
    "clock":      "<circle cx='12' cy='12' r='9'/><path d='M12 7v5l3 2'/>",
    "factory":    "<path d='M3 21V9l6 4V9l6 4V9l6 4v8z'/>",
    "target":     "<circle cx='12' cy='12' r='8'/><circle cx='12' cy='12' r='3'/>",
    "notes":      "<rect x='5' y='3' width='14' height='18' rx='2'/><path d='M8 8h8M8 12h8M8 16h5'/>",
}


def icon(name: str, size: int = 18) -> str:
    p = _ICON_PATHS.get(name, "")
    return (f"<svg viewBox='0 0 24 24' width='{size}' height='{size}' fill='none' "
            f"stroke='currentColor' stroke-width='2' stroke-linecap='round' "
            f"stroke-linejoin='round'>{p}</svg>")


def render_topbar(user: dict | None = None):
    right = ""
    if user:
        right = f"Signed in as <b>{user['name']}</b><br>{user['role']} access"
    st.markdown(
        f"<div class='bm-topbar'>"
        f"<div class='bm-topbar-l'>{_logo_html()}"
        f"<span class='bm-cobrand-x'>|</span>"
        f"<span class='bm-adani-chip'>{_adani_logo_html()}</span>"
        f"<span class='bm-cobrand-x'>|</span>"
        f"<span class='bm-portal-title'>STEEL GCP - AI LABS : Steel Prices Forecasting Model</span></div>"
        f"<div class='bm-topbar-r'>{right}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def direction_chip(direction: str) -> str:
    d = str(direction).strip().lower()
    if d in ("up", "rise", "rising"):
        return "<span class='dir-chip dir-up'>&#9650; Up</span>"
    if d in ("down", "fall", "falling"):
        return "<span class='dir-chip dir-down'>&#9660; Down</span>"
    return "<span class='dir-chip dir-flat'>&rarr; Flat</span>"


def arrow(direction: str) -> str:
    d = str(direction).strip().lower()
    if d == "up":
        return f"<span style='color:{SUCCESS};font-weight:700;'>&#9650;</span>"
    if d == "down":
        return f"<span style='color:{DANGER};font-weight:700;'>&#9660;</span>"
    return f"<span style='color:{NEUTRAL};font-weight:700;'>&rarr;</span>"


def kpi_card(label: str, value: str, sub: str = "", icon: str = "") -> str:
    icon_html = f"<span class='bm-kpi-icon'>{icon}</span>" if icon else ""
    sub_html = f"<div class='bm-kpi-sub'>{sub}</div>" if sub else ""
    return (f"<div class='bm-card'><div class='bm-kpi-top'>{icon_html}"
            f"<span class='bm-kpi-label'>{label}</span></div>"
            f"<div class='bm-kpi-value'>{value}</div>{sub_html}</div>")


def module_card(title: str, desc: str, icon: str = "") -> str:
    icon_html = f"<span class='bm-kpi-icon' style='width:34px;height:34px;font-size:19px;'>{icon}</span>" if icon else ""
    return (f"<div class='bm-card'><div class='bm-kpi-top'>{icon_html}"
            f"<h4 style='margin:0;'>{title}</h4></div>"
            f"<div class='bm-desc'>{desc}</div></div>")


def section_title(text: str, icon: str = ""):
    ic = f"{icon} " if icon else ""
    st.markdown(f"<div class='bm-h'>{ic}{text}</div>", unsafe_allow_html=True)


def footer():
    st.markdown(
        "<div class='bm-footer'>"
        "<span>AI-generated forecasts are indicative. Prototype build &mdash; data shown is a static snapshot.</span>"
        "<span>&copy; BigMint - Adani &middot; AI Labs &nbsp;|&nbsp; <a href='https://www.bigmint.co/' target='_blank'>bigmint.co</a></span>"
        "</div>",
        unsafe_allow_html=True,
    )
