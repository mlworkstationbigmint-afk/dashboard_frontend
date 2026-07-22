"""
BigMint - AI Labs portal: brand theme, CSS and shared UI helpers.
Colours sampled from the bigmint.co logo/site (blue + orange accent).
"""
import os
import html
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
            f"color:{PRIMARY};'>adani</span>")


# ---------------------------------------------------------------------------
# Per-role branding profiles (static, developer-configured once)
# ---------------------------------------------------------------------------
# Each role gets its own dashboard chrome — co-brand logo/label, topbar title,
# theme colors and which nav pages are visible. Applied per session from the
# logged-in user's role (render_topbar + apply_role_theme, wired in app.py).
# The left BigMint logo is constant (product owner); the co-brand chip varies.
#
# Add a new client (dev, once): add its role to auth.ROLES, drop its logo in
# assets/, add an entry below, then set commodity access + tag analyst calls
# from the Admin tab. cobrand_logo=None hides the co-brand chip (BigMint-only).
ALL_PAGES = ["Home", "Price Forecasting", "Analyst Calls",
             "Performance Dashboard", "Calculators", "Methodology"]

DEFAULT_PROFILE = {
    "cobrand_logo": "adani_logo.png",   # white chip logo in the topbar (None => no chip)
    "cobrand_label": "adani",           # gradient-text fallback if the image is missing
    "title": "GCP Steel - AI Labs - BigMint - Steel Price Forecasting Model",
    "primary": PRIMARY,
    "primary_dark": PRIMARY_DARK,
    "primary_soft": PRIMARY_SOFT,
    "accent": ACCENT,
    "pages": ALL_PAGES,
}

ROLE_PROFILES = {
    # title omitted on every role -> all inherit DEFAULT_PROFILE's title (one header everywhere).
    "Adani": {
        "cobrand_logo": "adani_logo.png",
        "cobrand_label": "adani",
    },
    "Analyst": {                         # internal BigMint view (no client co-brand)
        "cobrand_logo": None,
        "cobrand_label": "",
    },
    "Admin": {                           # internal BigMint view (Admin tab added in top_nav)
        "cobrand_logo": None,
        "cobrand_label": "",
    },
}


def profile_for(role) -> dict:
    """A role's branding profile, merged over DEFAULT_PROFILE (used for the login
    screen and any unknown role)."""
    return {**DEFAULT_PROFILE, **ROLE_PROFILES.get(role or "", {})}


def _cobrand_logo_html(profile: dict, height: int = 26) -> str:
    """Co-brand chip image for a profile, else a gradient wordmark of its label,
    else empty. Reuses the Adani fallback chain when the label is 'adani'."""
    candidates = []
    if profile.get("cobrand_logo"):
        candidates.append(os.path.join(ASSETS_DIR, profile["cobrand_logo"]))
    if profile.get("cobrand_label") == "adani":
        candidates += ADANI_LOGO_CANDIDATES
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                return f"<img src='data:image/png;base64,{b64}' style='height:{height}px;display:block;'/>"
            except Exception:
                continue
    label = profile.get("cobrand_label") or ""
    if not label:
        return ""
    return (f"<span style='font-weight:800;font-size:21px;letter-spacing:.2px;color:{PRIMARY};'>"
            + html.escape(label) + "</span>")


def apply_role_theme(profile: dict) -> None:
    """Override the :root brand tokens for the logged-in role. Call once after the
    user is resolved (see app.py); inject_css() seeds the BigMint defaults for the
    login screen."""
    st.markdown(
        "<style>:root{"
        f"--bm-primary:{profile['primary']};"
        f"--bm-primary-dark:{profile['primary_dark']};"
        f"--bm-primary-soft:{profile['primary_soft']};"
        f"--bm-accent:{profile['accent']};"
        "}</style>",
        unsafe_allow_html=True,
    )


def inject_css():
    st.markdown(f"""
<style>
/* Themeable brand tokens — defaults here (BigMint); apply_role_theme() overrides
   these per logged-in role so the topbar + all custom surfaces re-brand per session. */
:root {{
    --bm-primary: {PRIMARY};
    --bm-primary-dark: {PRIMARY_DARK};
    --bm-primary-soft: {PRIMARY_SOFT};
    --bm-accent: {ACCENT};
    /* neutral ramp — NOT re-themed per role (apply_role_theme only overrides the --bm-primary/-accent
       brand tokens above). grid.py keeps literal hexes: AgGrid's shadow DOM can't read this :root. */
    --bm-border: #e8edf3;   /* card + control borders */
    --bm-line:   #eef2f7;   /* hairline row separators / chart gridlines */
    --bm-ink:    #334155;   /* body text on white surfaces */
    /* semantic z-index scale: raise < sticky < overlay < splash (was arbitrary 99990/2147483647) */
    --z-raise: 5; --z-sticky: 100; --z-overlay: 900; --z-overlay-top: 901; --z-splash: 1000;
}}
.stApp {{ background-color: {BG_SOFT}; }}
/* full-bleed: fill the whole viewport width at any resolution (was capped at 1180px);
   side padding keeps content off the screen edges. layout="wide" is set in app.py.
   target both the `.block-container` class and the stMainBlockContainer testid (same element)
   so this survives either being renamed by a build. */
.block-container, [data-testid="stMainBlockContainer"] {{
    padding-top: 0 !important; margin-top: 0 !important; padding-bottom: 1rem; max-width: 100%;
    padding-left: 1.2rem; padding-right: 1.2rem; }}
/* the CookieManager component (app.py, key portal_cm) is an invisible iframe rendered ABOVE the
   topbar on every run — display:none removes its element container from the flex flow entirely
   (height:0 would still cost one block gap). Hidden iframes still load + run JS, so cookie
   reads/writes keep working. */
.st-key-portal_cm, div[class*="st-key-portal_cm"] {{ display: none !important; }}
/* analyst walkthrough bootstrap (tour.py, key bm_tour_mount): same trick — a hidden iframe that
   still runs its JS (drives a driver.js tour in the parent doc), off the flex flow so no gap. */
.st-key-bm_tour_mount, div[class*="st-key-bm_tour_mount"] {{ display: none !important; }}
/* no residual top offset from the app chrome: view container / main section flush to the
   viewport top; stDecoration is streamlit's coloured top strip. */
[data-testid="stAppViewContainer"], [data-testid="stMain"] {{ padding-top: 0 !important; margin-top: 0 !important; }}
[data-testid="stDecoration"] {{ display: none !important; }}
/* compact vertical rhythm: streamlit's default 1rem gap between blocks -> 0.65rem.
   NB: the .st-key-fc_loc_box negative pull-up margin below is tuned to THIS gap —
   retune it if this changes. */
[data-testid="stVerticalBlock"] {{ gap: 0.65rem !important; }}
/* compact headings: streamlit gives markdown h1-h3 tall default padding. Direct-child
   selector so headings inside custom HTML cards (.bm-meth-hero etc.) are untouched. */
[data-testid="stMarkdownContainer"] > h1,
[data-testid="stMarkdownContainer"] > h2,
[data-testid="stMarkdownContainer"] > h3 {{
    padding-top: 0.35rem !important; padding-bottom: 0.35rem !important;
}}
/* login / password-reset cards are fully styled by LOGIN_CSS in app.py (self-contained branded
   card + clean inputs), injected on the login + reset pages. Nothing here so the two don't fight. */
/* kill the app header entirely (it painted its Share/toolbar icons over the top of the page
   even at height:0). display:none keeps stStatusWidget in the DOM, so the :has() loading
   overlay below still works. Selectors deliberately element-agnostic (header OR div). */
[data-testid="stHeader"], [data-testid="stAppHeader"] {{
    display: none !important; height: 0 !important; min-height: 0 !important; padding: 0 !important; }}
#MainMenu, footer {{ visibility: hidden; }}
section[data-testid="stSidebar"], div[data-testid="collapsedControl"] {{ display: none !important; }}

/* ---------- translucent loading overlay (auto, shown while rerunning) ----------
   Streamlit keeps stStatusWidget in the DOM only while the script is running, so
   :has() lets us fade in a full-screen scrim + spinner during page switches or
   any slow rerun. Pure CSS via ::before/::after — no JS, no extra DOM node. */
@keyframes bm-spin {{ to {{ transform: rotate(360deg); }} }}
[data-testid="stApp"]::before {{
    content: ""; position: fixed; inset: 0; z-index: var(--z-overlay);
    background: rgba(244,246,250,0.55);
    -webkit-backdrop-filter: blur(1.5px); backdrop-filter: blur(1.5px);
    opacity: 0; visibility: hidden;
    transition: opacity .18s ease, visibility 0s .18s;
}}
[data-testid="stApp"]::after {{
    content: ""; position: fixed; top: 50%; left: 50%;
    width: 54px; height: 54px; margin: -27px 0 0 -27px; z-index: var(--z-overlay-top);
    border-radius: 50%; border: 5px solid rgba(2,76,161,0.15);
    border-top-color: var(--bm-accent); border-right-color: var(--bm-primary);
    opacity: 0; visibility: hidden;
    transition: opacity .18s ease, visibility 0s .18s;
    animation: bm-spin .85s linear infinite;
}}
/* Only reveal the overlay once a rerun has lasted >.7s. Fast reruns (e.g. moving
   between the login username/password fields, each of which fires a quick rerun)
   finish before the delay elapses, so the overlay never flashes; genuinely slow
   reruns (page switches, chart loads) still show it. The delay lives on the :has
   (visible) rule; the base rule above hides promptly (no show-delay). Bumped .4s -> .7s
   because reruns landing just over the old threshold still flashed occasionally. */
[data-testid="stApp"]:has([data-testid="stStatusWidget"])::before,
[data-testid="stApp"]:has([data-testid="stStatusWidget"])::after {{
    opacity: 1; visibility: visible;
    transition: opacity .18s ease .7s, visibility 0s .7s;
}}
@media (prefers-reduced-motion: reduce) {{
    [data-testid="stApp"]::after {{ animation-duration: 2s; }}
}}

/* ---------- top brand bar ---------- */
.bm-topbar {{
    background: var(--bm-primary); border-radius: 12px; padding: 13px 22px;
    display: flex; align-items: center; justify-content: space-between;
    margin: 0 0 10px 0; box-shadow: 0 2px 10px rgba(2,76,161,.18);
}}
.bm-topbar-l {{ display:flex; align-items:center; gap:13px; }}
.bm-cobrand-x {{ color:#cfe0f5; font-size:17px; font-weight:600; }}
.bm-adani-chip {{ display:inline-flex; align-items:center; }}
.bm-portal-title {{ color:#fff; font-size:15px; font-weight:600; opacity:.96; }}
.bm-topbar-r {{ color:#cfe0f5; font-size:12.5px; text-align:right; line-height:1.4; }}
.bm-topbar-r b {{ color:#fff; }}

/* ---------- nav pills (st.button based) ---------- */
div[data-testid="stHorizontalBlock"] {{ align-items: stretch; }}
.stButton > button {{ border-radius: 9px; font-weight: 600; transition: all .15s ease; }}
.stButton > button[kind="secondary"] {{
    background:#fff; border:1px solid #dbe3ee; color:var(--bm-ink);
}}
.stButton > button[kind="secondary"]:hover {{
    border-color:var(--bm-primary); color:var(--bm-primary); background:var(--bm-primary-soft);
}}
.stButton > button[kind="primary"] {{ box-shadow:0 2px 8px rgba(2,76,161,.25); }}
/* keyboard focus ring — brand accent, on every st.button / download / link (was relying on the
   browser default outline only). :focus-visible so mouse clicks don't show the ring, keyboard does. */
.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible,
.stLinkButton > a:focus-visible {{
    outline:2px solid var(--bm-accent) !important; outline-offset:2px !important;
    box-shadow:0 0 0 4px rgba(238,78,36,.18) !important;
}}

/* ---------- Log out button: invert (orange) on hover ---------- */
div[class*="st-key-logout_top"] button:hover {{
    background:#fff !important; border:1px solid var(--bm-accent) !important; color:var(--bm-accent) !important;
    box-shadow:0 2px 8px rgba(238,78,36,.20);
}}
div[class*="st-key-logout_top"] button:hover [data-testid="stIconMaterial"],
div[class*="st-key-logout_top"] button:hover p {{ color:var(--bm-accent) !important; }}

/* ---------- home module card-buttons (whole card is one clickable button) ---------- */
/* layout: icon on top -> **title** (strong) -> brief (p text) -> *Open ->* (em CTA) */
div[class*="st-key-homemod_"] button {{
    height:100%; min-height:230px; flex-direction:column;
    align-items:flex-start; justify-content:center; gap:0;
    text-align:left; white-space:normal; padding:26px 24px 24px; border-radius:16px;
    border:1px solid var(--bm-border) !important; background:#fff !important;
    box-shadow:0 1px 2px rgba(16,24,40,.05); font-weight:400;
    transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease, background .18s ease;
}}
div[class*="st-key-homemod_"] button:hover {{
    border-color:var(--bm-primary) !important; background:var(--bm-primary-soft) !important;
    transform:translateY(-3px); box-shadow:0 10px 26px rgba(2,76,161,.12);
}}
/* heading row: the material icon is embedded inside the bold title, so lay the title out as a
   flex row (icon + heading together) with the icon sized/coloured to sit beside the bigger heading */
div[class*="st-key-homemod_"] button strong {{
    display:flex; align-items:center; gap:9px;
    font-size:21px; color:var(--bm-primary-dark); font-weight:700; margin-bottom:8px;
}}
div[class*="st-key-homemod_"] button strong [data-testid="stIconMaterial"] {{
    font-size:26px !important; width:26px; height:26px; color:var(--bm-primary); flex:0 0 auto;
}}
div[class*="st-key-homemod_"] button p {{ font-size:13.5px; color:{NEUTRAL}; line-height:1.5; margin:0; font-weight:400; }}
/* "Open ->" call-to-action (rendered from the *Open ->* em in the label) */
div[class*="st-key-homemod_"] button em {{
    display:block; font-style:normal; font-weight:700; color:var(--bm-accent);
    font-size:13px; letter-spacing:.3px; margin-top:14px;
}}

/* ---------- home Methodology banner (full-width button spanning the 4 cards) ---------- */
div[class*="st-key-home_methodology"] {{ margin-top:16px; }}
div[class*="st-key-home_methodology"] button {{
    width:100%; min-height:92px; flex-direction:row; align-items:center; justify-content:flex-start;
    gap:18px; text-align:left; white-space:normal; padding:24px 28px; border-radius:18px;
    border:1px solid var(--bm-border) !important; color:var(--bm-primary-dark) !important; font-weight:400;
    background:#fff !important;
    box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease, background .18s ease;
}}
div[class*="st-key-home_methodology"] button:hover {{
    border-color:var(--bm-primary) !important; background:var(--bm-primary-soft) !important;
    transform:translateY(-2px); box-shadow:0 10px 26px rgba(2,76,161,.12);
}}
div[class*="st-key-home_methodology"] button [data-testid="stIconMaterial"] {{
    font-size:32px !important; width:32px; height:32px; color:var(--bm-primary);
}}
/* let the label row stretch so the CTA can sit at the far right */
div[class*="st-key-home_methodology"] button [data-testid="stMarkdownContainer"] {{ flex:1 1 auto; }}
div[class*="st-key-home_methodology"] button [data-testid="stMarkdownContainer"] p {{
    display:flex; align-items:center; flex-wrap:wrap; gap:4px 12px; margin:0;
}}
div[class*="st-key-home_methodology"] button strong {{
    font-size:20px; color:var(--bm-primary-dark); font-weight:800; letter-spacing:.2px;
}}
div[class*="st-key-home_methodology"] button p {{ font-size:13.5px; color:{NEUTRAL}; font-weight:400; }}
/* "View ->" CTA -> solid orange pill, pushed to the right, reads as clickable (whole banner navigates) */
div[class*="st-key-home_methodology"] button em {{
    margin-left:auto; font-style:normal; font-weight:800; color:#fff;
    background:var(--bm-accent); padding:9px 20px; border-radius:10px; font-size:14px; white-space:nowrap;
    box-shadow:0 2px 8px rgba(238,78,36,.30);
}}
div[class*="st-key-home_methodology"] button:hover em {{ filter:brightness(.97); }}

/* ---------- direction chips ---------- */
.dir-chip {{ font-size:12px; font-weight:600; padding:3px 10px; border-radius:20px; white-space:nowrap; display:inline-block; }}
.dir-up   {{ background:#e7f6ee; color:{SUCCESS}; }}
.dir-down {{ background:#fbe9e7; color:{DANGER}; }}
.dir-flat {{ background:#eef1f5; color:{NEUTRAL}; }}

/* ---------- cards / KPIs ---------- */
.bm-card {{ background:#fff; border:1px solid var(--bm-border); border-radius:14px; padding:16px 18px; height:100%;
    box-shadow:0 1px 2px rgba(16,24,40,.04); transition:transform .18s ease, box-shadow .18s ease; }}
.bm-card:hover {{ transform:translateY(-2px); box-shadow:0 8px 22px rgba(2,76,161,.10); }}
.bm-kpi-top {{ display:flex; align-items:center; gap:8px; margin-bottom:6px; }}
.bm-kpi-icon {{ width:30px;height:30px;border-radius:8px;background:var(--bm-primary-soft);color:var(--bm-primary);
    display:flex;align-items:center;justify-content:center;font-size:17px; }}
.bm-kpi-label {{ color:{NEUTRAL}; font-size:13px; font-weight:500; }}
.bm-kpi-value {{ font-size:26px; font-weight:700; color:#0f172a; line-height:1.15; }}
.bm-kpi-sub {{ font-size:12.5px; color:{NEUTRAL}; margin-top:4px; }}
.bm-card h4 {{ margin:2px 0 4px 0; color:var(--bm-primary-dark); font-size:16px; }}
.bm-card .bm-desc {{ color:{NEUTRAL}; font-size:13px; }}

/* analyst-call detailed summary: label + one-line section rows.
   Body text (summary + section rows) is capped at 82% so it doesn't run edge-to-edge under the
   Report/Pitchdeck/Video line — a consistent right gutter keeps the card modular. */
.bm-call-date {{ color:{ACCENT}; font-size:11.5px; font-weight:700; letter-spacing:.06em;
    text-transform:uppercase; margin-bottom:3px; }}
.bm-call-title {{ font-size:18px; font-weight:700; color:var(--bm-primary-dark); line-height:1.3; }}
.bm-call-kinds {{ text-align:right; color:{NEUTRAL}; font-size:11px; font-weight:600; letter-spacing:.04em;
    text-transform:uppercase; padding-top:4px; }}
.bm-call-summary {{ color:var(--bm-ink); font-size:13.5px; line-height:1.6; margin:10px 0 2px; max-width:82%; }}
.bm-call-secs {{ margin:14px 0 2px 0; max-width:82%; }}
.bm-call-sec {{ display:flex; gap:16px; padding:10px 2px; border-top:1px dashed #e6ebf2; font-size:13.5px; line-height:1.5; }}
.bm-call-sec:first-child {{ border-top:none; }}
.bm-call-sec-l {{ flex:0 0 150px; font-weight:700; color:var(--bm-primary-dark); }}
.bm-call-sec-t {{ color:{NEUTRAL}; }}
.bm-call-sep {{ border-top:1px solid var(--bm-line); margin:14px 0 12px; }}
/* analyst-call cards: spacing + modern buttons with orange hover (scoped to the card key so nav /
   Sign-in / Log-out buttons are untouched) */
div[class*="st-key-callcard"] {{ margin-bottom:16px; }}
div[class*="st-key-callcard"] .stButton button,
div[class*="st-key-callcard"] .stDownloadButton button,
div[class*="st-key-callcard"] .stLinkButton a {{
    border-radius:10px; border:1px solid #d7dee8; background:#fff; color:var(--bm-primary-dark);
    font-weight:600; box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:border-color .15s ease, color .15s ease, background .15s ease, box-shadow .15s ease, transform .15s ease; }}
div[class*="st-key-callcard"] .stButton button:hover:not(:disabled),
div[class*="st-key-callcard"] .stDownloadButton button:hover:not(:disabled),
div[class*="st-key-callcard"] .stLinkButton a:hover {{
    border-color:var(--bm-accent); color:var(--bm-accent); background:rgba(238,78,36,.06);
    box-shadow:0 6px 16px rgba(238,78,36,.18); transform:translateY(-1px); }}
div[class*="st-key-callcard"] .stButton button:disabled,
div[class*="st-key-callcard"] .stDownloadButton button:disabled {{ opacity:.5; }}

/* section heading */
.bm-h {{ font-size:15px; font-weight:600; color:var(--bm-primary-dark); margin:6px 0 6px 0;
    display:flex; align-items:center; gap:8px; }}
/* Home "Modules" heading: larger + more breathing room so the section fills the page */
.bm-modules-h {{ font-size:22px; font-weight:700; margin:24px 0 16px 0; gap:10px; }}
.bm-modules-h svg {{ stroke-width:2.2; }}

/* ---------- tables ---------- */
.bm-table {{ width:100%; border-collapse:collapse; font-size:13.5px; background:#fff;
    border:1px solid var(--bm-border); border-radius:12px; overflow:hidden; }}
.bm-table thead th {{ background:var(--bm-primary); color:#fff; font-weight:800;
    padding:11px 12px; text-align:left; letter-spacing:.2px; }}
.bm-table tbody td {{ padding:9px 12px; border-top:1px solid var(--bm-line); color:var(--bm-ink); }}
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
/* Streamlit 1.59 (react-aria): container [data-testid="stTabs"] > div[role="tablist"], tabs are
   div[data-testid="stTab"][role="tab"] with aria-selected, and the moving underline is a
   div.react-aria-SelectionIndicator INSIDE the active tab. Attribute-only selectors + !important
   on every declaration so the framework's own styled-component rules can't win. */
[data-testid="stTabs"] div[role="tablist"] {{
    position:relative !important; gap:6px !important; background:#e9edf4 !important;
    padding:5px !important; border-radius:13px !important; margin-bottom:6px !important;
    border-bottom:none !important; display:inline-flex !important;
    /* shrink-to-fit: on 1.59 the tablist is a stretched flex item, so inline-flex/width:auto
       alone leaves the grey track spanning the full screen — pin it to its content. */
    width:fit-content !important; max-width:100% !important; align-self:flex-start !important;
    box-shadow:inset 0 1px 2px rgba(16,24,40,.06) !important;
}}
/* the white pill: react-aria's SelectionIndicator lives INSIDE the active tab, so pin it to the
   tab's own box (inset:0; inline transform/size overridden) — it moves with the selection rather
   than gliding across the track, but reads as the same white pill. Needs the tab itself
   position:relative (set below). */
[data-testid="stTabs"] .react-aria-SelectionIndicator {{
    position:absolute !important; inset:0 !important; width:auto !important; height:auto !important;
    transform:none !important; z-index:0 !important; border-radius:9px !important;
    background:#fff !important; box-shadow:0 1px 4px rgba(16,24,40,.16) !important;
}}
div[data-testid="stTab"][role="tab"] {{
    position:relative !important; z-index:1 !important; font-size:14.5px !important; font-weight:600 !important;
    color:{NEUTRAL} !important; background:transparent !important; border:none !important;
    border-radius:9px !important; padding:9px 26px !important; margin:0 !important; height:auto !important;
    transition:color .2s ease !important;
}}
/* keep the tab label above the in-tab pill */
div[data-testid="stTab"][role="tab"] > :not(.react-aria-SelectionIndicator) {{ position:relative; z-index:1; }}
div[data-testid="stTab"][role="tab"]:not([aria-selected="true"]):hover {{ color:var(--bm-primary-dark) !important; }}
div[data-testid="stTab"][role="tab"][aria-selected="true"] {{ color:var(--bm-accent) !important; font-weight:700 !important; }}
/* segmented selectors (Product) -> orange active. 1.59 (react-aria) marks the active option with
   data-variant="segmented_control" + aria-checked="true". */
button[data-variant="segmented_control"][aria-checked="true"] {{
    color:var(--bm-accent) !important; border-color:var(--bm-accent) !important;
    background-color:rgba(238,78,36,0.10) !important;
}}
button[data-variant="segmented_control"][aria-checked="true"] p {{ color:var(--bm-accent) !important; }}
/* commodity group / product tab-strips -> bold names */
.st-key-fc_group button p, .st-key-perf_group button p,
.st-key-fc_prod button p, .st-key-perf_prod button p {{ font-weight:800 !important; }}
/* Forecast-forward horizon tabs (fc_horizon: 1W/4W/8W/12W) -> blue gradient, light 1W -> dark 12W.
   Same gradient idea as the chart's historical zoom buttons (.rangebtns in app.py). The selected
   option keeps its orange border (generic segmented rule) as the pick indicator. */
.st-key-fc_horizon button:nth-of-type(1) {{ background:#e8f0fb !important; }}
.st-key-fc_horizon button:nth-of-type(2) {{ background:#b9d3f2 !important; }}
.st-key-fc_horizon button:nth-of-type(3) {{ background:#5b93da !important; }}
.st-key-fc_horizon button:nth-of-type(4) {{ background:#024CA1 !important; }}
.st-key-fc_horizon button:nth-of-type(1) p, .st-key-fc_horizon button:nth-of-type(2) p {{ color:#024CA1 !important; }}
.st-key-fc_horizon button:nth-of-type(3) p, .st-key-fc_horizon button:nth-of-type(4) p {{ color:#fff !important; }}
/* selected horizon -> FULL orange fill (not just the border) */
.st-key-fc_horizon button[aria-checked="true"] {{ background:var(--bm-accent) !important;
    border-color:var(--bm-accent) !important; }}
.st-key-fc_horizon button[aria-checked="true"] p {{ color:#fff !important; font-weight:800 !important; }}
/* accuracy glossary: hover-info marker on cards/titles + the reference box at the page foot */
.bm-help {{ cursor:help; color:var(--bm-accent); font-weight:700; font-size:.82em;
    vertical-align:super; margin-left:2px; text-decoration:none; }}
.bm-glossary {{ background:#f7f9fc; border:1px solid var(--bm-border); border-radius:12px;
    padding:14px 18px; margin-top:6px; }}
.bm-glossary-h {{ font-weight:800; color:var(--bm-primary-dark); font-size:14.5px; margin-bottom:8px; }}
.bm-gl-item {{ padding:7px 0; border-top:1px solid var(--bm-line); }}
.bm-gl-item:first-of-type {{ border-top:none; }}
.bm-gl-term {{ font-weight:700; color:var(--bm-ink); }}
.bm-gl-idea {{ color:#475569; font-size:13px; margin:2px 0; }}
.bm-gl-formula {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px;
    color:var(--bm-primary-dark); background:#eef3fb; border-radius:6px; padding:2px 7px; display:inline-block; }}
/* grouped-forecasting location dropdown -> make it stand out: coloured border + tint */
/* RIGHT-aligned and pulled down onto the Graphical/Tabular slider row (negative margin eats
   the block gap + its own height) so switch (left) + dropdown (right) share one line; it stays
   usable in both views. z-index keeps it clickable above the tabs block that renders after it. */
.st-key-fc_loc_box {{
    /* -52px = 0.65rem compact block gap (~10px, set on stVerticalBlock above) + own ~42px
       height (was -58px under the default 1rem gap) — retune if either changes.
       ~85-char wide (660px) so the full descriptive product names (app.py FORECAST_LOCATION_LABELS)
       show in full on one line; capped at the viewport so it never overflows. */
    width:660px; max-width:100%; margin-left:auto; margin-bottom:-52px; position:relative; z-index:var(--z-raise);
}}
/* Performance page reuses the same dropdown, RIGHT-aligned in its own column on the SAME row as the
   group tab-strip (st.columns handles the row, so no negative pull-up needed). */
.st-key-perf_loc_box {{ width:100%; max-width:640px; margin-left:auto; }}
/* NB: on 1.59 the fc/perf location dropdowns use the app-wide white+orange selectbox styling
   below (the old baseweb blue-tint block was removed — baseweb `select` markup is gone on 1.59).
   Restore a distinct tint here with stSelectbox selectors if the plain look isn't wanted. */
/* dropdown popover options: show the full descriptive name (no clipping), comfortable line height */
ul[role="listbox"] li {{
    font-size:12.5px !important; line-height:1.4 !important; white-space:normal !important;
}}
.st-key-fc_loc_box svg, .st-key-perf_loc_box svg {{ fill:var(--bm-primary) !important; color:var(--bm-primary) !important; }}
/* ALL dropdowns (selectboxes) app-wide: WHITE fill + a single curved ORANGE border. Streamlit 1.59 does
   NOT expose data-baseweb="select" (react-aria markup), and its pale secondaryBackgroundColor (#F1F5FB)
   would otherwise show through — target the stable `stSelectbox` testid
   instead. Whiten the closed control + every inner wrapper/input (the options popover renders in a body
   portal, so it's untouched). For the border: rather than guess which wrapper holds value + arrow, just
   RECOLOUR (colour only — NOT width) whatever element already carries the control's default border. The
   real control box has a rounded ~1px border, so it goes orange keeping its curve, wrapping value AND
   arrow. ⚠ Do NOT force border-width here: Streamlit's reset puts `border:0 solid` on EVERY div, so a
   forced width makes a square-cornered outer container's zero-width border suddenly show as a rectangle
   around the rounded one. Colour-only leaves those reset borders at width 0 (invisible). */
[data-testid="stSelectbox"] div,
[data-testid="stSelectbox"] input {{
    background:#fff !important; background-color:#fff !important;
    border-color:transparent !important; box-shadow:none !important;
}}
/* Paint exactly ONE rounded orange border on the control itself (the last child of the
   selectbox = the baseweb select wrapper, after the label). Zeroing the inner borders above
   first stops stray reset-borders on wrapper divs from showing as a second box that "outgrows"
   the control. */
[data-testid="stSelectbox"] > div:last-child {{
    border:1px solid var(--bm-accent) !important; border-radius:8px !important; box-shadow:none !important;
}}
[data-testid="stSelectbox"] svg {{ fill:var(--bm-accent) !important; color:var(--bm-accent) !important; }}

/* ALL number / text / textarea / date inputs app-wide: the SAME clean box as the dropdowns above —
   WHITE fill + exactly ONE curved ORANGE border, no inner notch or double-border seam. Same 1.59-safe
   recipe: whiten every inner wrapper + zero its reset border-colour, then paint one rounded orange
   border on the control (the input's last-child wrapper). Colour-only border, never width (see the
   ⚠ note above). More-specific component overrides (e.g. the knob cards) still win. */
[data-testid="stNumberInput"] div, [data-testid="stNumberInput"] input, [data-testid="stNumberInput"] button,
[data-testid="stTextInput"] div, [data-testid="stTextInput"] input,
[data-testid="stTextArea"] div, [data-testid="stTextArea"] textarea,
[data-testid="stDateInput"] div, [data-testid="stDateInput"] input {{
    background:#fff !important; background-color:#fff !important;
    border-color:transparent !important; box-shadow:none !important;
}}
[data-testid="stNumberInput"] > div:last-child,
[data-testid="stTextInput"] > div:last-child,
[data-testid="stTextArea"] > div:last-child,
[data-testid="stDateInput"] > div:last-child {{
    border:1px solid var(--bm-accent) !important; border-radius:8px !important; box-shadow:none !important;
}}
/* number-input −/+ steppers: orange glyphs to match the accent border */
[data-testid="stNumberInput"] button svg {{ fill:var(--bm-accent) !important; color:var(--bm-accent) !important; }}

/* grouped-forecasting right-side price-card stack: ONE HTML flex column (emitted whole by
   app.py price_cards(vertical=True)). Our own markup, so no dependence on how Streamlit
   nests its container/block DOM (a keyed-container attempt failed — the st-key class lands
   on wrappers the flex rules never reached). Final look per owner: natural-height cards,
   14px gaps, top-aligned (leftover space below the third card is fine), and a hard width
   cap so the rail can't balloon on wide screens; right-aligned to match the location
   dropdown above it. */
.bm-vcards {{ display: flex; flex-direction: column; gap: 14px;
    max-width: 280px; margin-left: auto; }}
.bm-vcards .bm-card {{ height: auto; }}
/* smaller variant: the grouped graphical right rail now holds a horizon tab + 2 cards + the
   rationale, so the cards are trimmed down and fill the (left-aligned) rail width. Each card lays
   out HORIZONTALLY — icon+label header on top, then the value on the left with the date / direction
   chip on its RIGHT (not stacked below). */
.bm-vcards.bm-vcards-sm {{ max-width: 100%; margin-left: 0; gap: 10px; }}
.bm-vcards-sm .bm-card {{ padding: 11px 13px; border-radius: 12px;
    display: flex; flex-wrap: wrap; align-items: center; }}
.bm-vcards-sm .bm-kpi-top {{ flex: 0 0 100%; margin-bottom: 4px; }}
.bm-vcards-sm .bm-kpi-value {{ font-size: 20px; line-height: 1.1; }}
.bm-vcards-sm .bm-kpi-icon {{ width: 26px; height: 26px; font-size: 15px; }}
.bm-vcards-sm .bm-kpi-label {{ font-size: 12px; }}
.bm-vcards-sm .bm-kpi-sub {{ font-size: 11.5px; margin: 0 0 0 auto; }}   /* date / dir chip -> right side */
.bm-vcards-sm .bm-desc {{ flex: 1 1 100%; }}
.bm-vcards-sm .bm-rationale-body {{ font-size: 12px; line-height: 1.55; margin-top: 2px; }}

/* grouped-forecasting Graphical/Tabular switch -> sliding segmented PILL switch:
   grey capsule track, a label-width WHITE PILL that glides behind the active option, orange
   active text (same look as the classic tab pill). Built on st.segmented_control (NOT st.tabs):
   its stButtonGroup / stBaseButton testids are Streamlit's own and stable across versions, unlike
   the baseweb `data-baseweb="tab-*"` attributes that the deployed build dropped. The track is the
   button-group; the pill is a ::before pseudo-element whose translateX flips via :has() on which
   option is Active; the transform transition makes it glide. Geometry: track 270px, 4px inset,
   two equal halves -> pill w=131 (=(270-8)/2), parks at x=4 / x=135 — recompute both if the track
   width changes. Fallback: without :has() the pill stays left (active label still orange/bold). */
/* the keyed container stretches full-width by default (flex child) — hug the 270px pill instead,
   so the switch (and its tour highlight) only spans its own width, not the whole row. */
.st-key-fc_view_box {{ width:fit-content !important; }}
.st-key-fc_view_box div[role="radiogroup"] {{
    position:relative !important; display:flex !important; width:270px !important;
    min-width:270px !important; max-width:270px !important;
    height:42px !important; padding:0 !important; gap:0 !important; border-radius:999px !important;
    background:#e9edf4 !important;
    box-shadow:inset 0 1px 2px rgba(16,24,40,.08) !important;
}}
.st-key-fc_view_box div[role="radiogroup"]::before {{
    content:""; position:absolute; top:4px; left:0; width:131px; height:34px;
    border-radius:999px; background:#fff; box-shadow:0 1px 4px rgba(16,24,40,.16);
    transform:translateX(4px); transition:transform .28s cubic-bezier(.4,0,.2,1);
    pointer-events:none; z-index:0;
}}
/* pill parking: 1.59 (react-aria segmented control) marks the active option with aria-checked="true". */
.st-key-fc_view_box div[role="radiogroup"]:has(button:last-of-type[aria-checked="true"])::before {{
    transform:translateX(135px);                 /* right half: 4 + (270-8)/2 */
}}
.st-key-fc_view_box div[role="radiogroup"] button {{
    flex:1 1 0 !important; height:100% !important; margin:0 !important; padding:0 !important;
    border:none !important; border-radius:999px !important; background:transparent !important;
    box-shadow:none !important; position:relative; z-index:1;
    color:{NEUTRAL} !important; justify-content:center !important;
}}
.st-key-fc_view_box div[role="radiogroup"] button p {{
    color:inherit !important; font-size:13px !important; font-weight:600 !important;
}}
.st-key-fc_view_box div[role="radiogroup"] button:hover {{ color:var(--bm-primary-dark) !important; }}
.st-key-fc_view_box div[role="radiogroup"] button[aria-checked="true"] {{
    color:var(--bm-accent) !important; background:transparent !important; border:none !important;
    box-shadow:none !important;
}}
.st-key-fc_view_box div[role="radiogroup"] button[aria-checked="true"] p {{
    color:var(--bm-accent) !important; font-weight:700 !important;
}}

/* ---------- methodology infographics ---------- */
.bm-meth-hero {{ background:linear-gradient(120deg,var(--bm-primary) 0%,var(--bm-primary-dark) 100%); color:#fff;
    border-radius:16px; padding:22px 26px; margin:2px 0 18px; box-shadow:0 6px 22px rgba(2,76,161,.20); }}
.bm-meth-hero h3 {{ margin:0 0 6px; font-size:20px; color:#fff; }}
.bm-meth-hero p {{ margin:0; font-size:14px; line-height:1.6; color:#dce8f8; max-width:860px; }}
/* stat strip */
.bm-stat-row {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:0 0 20px; }}
.bm-stat {{ background:#fff; border:1px solid var(--bm-border); border-radius:14px; padding:16px 18px; text-align:center;
    box-shadow:0 1px 2px rgba(16,24,40,.05); }}
.bm-stat-v {{ font-size:24px; font-weight:800; color:var(--bm-primary-dark); line-height:1.1; }}
.bm-stat-l {{ font-size:12.5px; color:{NEUTRAL}; margin-top:4px; }}
/* horizontal process flow — one continuous pipeline (single row, arrows between).
   CSS grid (card / arrow / card / …) so it never wraps into an awkward 3+3 jump;
   collapses to a vertical column on narrow screens (media query below). */
.bm-flow {{ display:grid; grid-template-columns:1fr auto 1fr auto 1fr auto 1fr auto 1fr auto 1fr;
    align-items:stretch; gap:0 4px; margin:18px 0 14px; }}
.bm-flow-step {{ display:flex; flex-direction:column; align-items:flex-start; text-align:left;
    background:#fff; border:1px solid var(--bm-border); border-radius:14px;
    padding:22px 16px 16px; position:relative; box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:transform .15s ease, box-shadow .15s ease; }}
.bm-flow-step:hover {{ transform:translateY(-2px); box-shadow:0 8px 20px rgba(2,76,161,.10); }}
.bm-flow-step .num {{ position:absolute; top:-12px; left:16px; width:26px; height:26px; border-radius:50%;
    background:var(--bm-accent); color:#fff; font-size:12.5px; font-weight:700; display:flex; align-items:center;
    justify-content:center; box-shadow:0 2px 6px rgba(238,78,36,.35); }}
.bm-flow-step .ic {{ width:38px; height:38px; border-radius:10px; background:var(--bm-primary-soft); color:var(--bm-primary);
    display:flex; align-items:center; justify-content:center; margin:0 0 10px; }}
.bm-flow-step .bm-flow-t {{ margin:0 0 6px; font-size:14px; line-height:1.3;
    color:var(--bm-primary-dark); font-weight:700; }}   /* plain div (not <h5>) so Streamlit adds no anchor-link icon */
.bm-flow-step p {{ margin:0; font-size:12.5px; color:{NEUTRAL}; line-height:1.45; }}
/* arrow pinned to the icon row (align-self:start + padding) so 1..6 share one flow line */
.bm-flow-arrow {{ align-self:start; padding-top:30px; display:flex; align-items:flex-start;
    justify-content:center; color:var(--bm-accent); font-size:18px; font-weight:700; }}
/* methodology engine infographic (Inputs -> Model -> Outputs); replaces the old numbered chain */
.bm-engine {{ display:grid; grid-template-columns:1fr auto 1.15fr auto 1fr; align-items:stretch; gap:0 10px; margin:18px 0 14px; }}
.bm-engine-col {{ background:#fff; border:1px solid var(--bm-border); border-radius:14px; padding:16px 16px 14px; box-shadow:0 1px 2px rgba(16,24,40,.05); }}
.bm-engine-in {{ border-top:3px solid var(--bm-primary); }}
.bm-engine-out {{ border-top:3px solid var(--bm-accent); }}
.bm-engine-h {{ font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:{NEUTRAL}; margin:0 0 10px; }}
.bm-chip {{ display:flex; align-items:center; gap:9px; background:#f6f8fc; border:1px solid var(--bm-border); border-radius:10px; padding:9px 11px; margin:0 0 8px; font-size:12.5px; color:var(--bm-primary-dark); font-weight:600; line-height:1.3; }}
.bm-chip:last-child {{ margin-bottom:0; }}
.bm-chip .ic {{ flex:0 0 24px; width:24px; height:24px; border-radius:7px; background:var(--bm-primary-soft); color:var(--bm-primary); display:flex; align-items:center; justify-content:center; }}
.bm-engine-core {{ display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; background:linear-gradient(135deg,var(--bm-primary) 0%,var(--bm-primary-dark) 100%); color:#fff; border-radius:16px; padding:20px 18px; box-shadow:0 6px 22px rgba(2,76,161,.22); }}
.bm-engine-core .ic {{ width:46px; height:46px; border-radius:12px; background:rgba(255,255,255,.16); display:flex; align-items:center; justify-content:center; margin:0 0 10px; }}
.bm-engine-core h4 {{ margin:0 0 6px; font-size:16px; color:#fff; }}
.bm-engine-core p {{ margin:0; font-size:12.5px; line-height:1.5; color:#dce8f8; }}
.bm-engine-arrow {{ display:flex; align-items:center; justify-content:center; color:var(--bm-accent); font-size:20px; font-weight:700; }}
/* factor grid */
.bm-factor-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:6px 0; }}
.bm-factor {{ display:flex; gap:12px; align-items:flex-start; background:#fff; border:1px solid var(--bm-border);
    border-radius:14px; padding:14px 16px; box-shadow:0 1px 2px rgba(16,24,40,.05);
    transition:transform .15s ease, box-shadow .15s ease; }}
.bm-factor:hover {{ transform:translateY(-2px); box-shadow:0 8px 20px rgba(2,76,161,.10); }}
.bm-factor .ic {{ flex:0 0 38px; width:38px; height:38px; border-radius:10px; background:var(--bm-primary-soft); color:var(--bm-primary);
    display:flex; align-items:center; justify-content:center; }}
.bm-factor h5 {{ margin:0 0 2px; font-size:13.5px; color:var(--bm-primary-dark); font-weight:700; }}
.bm-factor p {{ margin:0; font-size:12.5px; color:{NEUTRAL}; line-height:1.4; }}
/* horizon cards */
.bm-horizon-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:6px 0; }}
.bm-horizon {{ background:#fff; border:1px solid var(--bm-border); border-top:3px solid var(--bm-accent); border-radius:14px;
    padding:16px 18px; box-shadow:0 1px 2px rgba(16,24,40,.05); }}
.bm-horizon h5 {{ margin:0 0 4px; font-size:15px; color:var(--bm-primary-dark); }}
.bm-horizon p {{ margin:0; font-size:12.5px; color:{NEUTRAL}; line-height:1.5; }}
.bm-horizon .tag {{ display:inline-block; font-size:11px; font-weight:700; color:var(--bm-accent);
    background:rgba(238,78,36,.10); border-radius:20px; padding:2px 10px; margin-bottom:8px; }}
@media (max-width:1024px) {{
    /* pipeline: single row -> vertical column, arrows rotate to point downward */
    .bm-flow {{ grid-template-columns:1fr; }}
    .bm-flow-step {{ margin:0 0 4px; }}
    .bm-flow-arrow {{ transform:rotate(90deg); margin:3px 0; padding-top:0; align-self:center; }}
    /* engine: single column, arrows point downward */
    .bm-engine {{ grid-template-columns:1fr; gap:8px 0; }}
    .bm-engine-arrow {{ transform:rotate(90deg); margin:2px 0; }}
    /* stat strip: 6-up gets cramped on tablet -> 3-up before the 2-up phone step below */
    .bm-stat-row {{ grid-template-columns:repeat(3,1fr); }}
}}
@media (max-width:760px) {{
    .bm-stat-row, .bm-factor-grid, .bm-horizon-grid {{ grid-template-columns:1fr 1fr; }}
}}

/* links / footer */
.bm-link-btn a {{ display:inline-block; background:var(--bm-accent); color:#fff!important; text-decoration:none;
    padding:11px 20px; border-radius:9px; font-weight:600; font-size:14px; box-shadow:0 2px 8px rgba(238,78,36,.25); }}
.bm-link-btn a:hover {{ filter:brightness(.95); }}
.bm-footnote {{ color:{NEUTRAL}; font-size:12px; margin-top:8px; }}
/* sortable/paginated table meta line ("Rows 1-52 of 90 · Page 1/2") */
.bm-tbl-meta {{ color:{NEUTRAL}; font-size:12.5px; text-align:center; }}
.bm-footer {{ margin-top:26px; padding-top:14px; border-top:1px solid #e2e8f0; color:{NEUTRAL};
    font-size:12px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
.bm-footer a {{ color:var(--bm-primary); text-decoration:none; }}
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
    """Brand bar for the logged-in user's role: (co-brand chip) · BigMint logo · title.
    The co-brand chip + one pipe are omitted when the role's profile has no co-brand
    (internal Analyst/Admin); the login screen uses DEFAULT_PROFILE, which keeps the chip."""
    profile = profile_for(user.get("role") if user else None)
    # Co-brand chip shows on the login screen too (DEFAULT_PROFILE carries the Adani logo).
    cobrand = _cobrand_logo_html(profile)
    parts = ["<div class='bm-topbar-l'>"]
    if cobrand:   # Adani chip sits BEFORE the BigMint logo
        parts.append(f"<span class='bm-adani-chip'>{cobrand}</span>"
                     "<span class='bm-cobrand-x'>|</span>")
    parts.append(_logo_html())
    parts.append("<span class='bm-cobrand-x'>|</span>"
                 f"<span class='bm-portal-title'>{html.escape(profile['title'])}</span></div>")
    st.markdown(
        f"<div class='bm-topbar'>{''.join(parts)}"
        f"<div class='bm-topbar-r'></div>"
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


def kpi_card(label: str, value: str, sub: str = "", icon: str = "") -> str:
    icon_html = f"<span class='bm-kpi-icon'>{icon}</span>" if icon else ""
    sub_html = f"<div class='bm-kpi-sub'>{sub}</div>" if sub else ""
    return (f"<div class='bm-card'><div class='bm-kpi-top'>{icon_html}"
            f"<span class='bm-kpi-label'>{label}</span></div>"
            f"<div class='bm-kpi-value'>{value}</div>{sub_html}</div>")


def section_title(text: str, icon: str = ""):
    ic = f"{icon} " if icon else ""
    # role/aria-level give screen readers a real heading without Streamlit's markdown-heading anchor icon.
    st.markdown(f"<div class='bm-h' role='heading' aria-level='3'>{ic}{text}</div>", unsafe_allow_html=True)


def footer():
    st.markdown(
        "<div class='bm-footer'>"
        "<span>Note: AI-generated forecasts are indicative.</span>"
        "<span>&copy; BigMint &middot; Adani</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def loading_screen():
    """A full-viewport brand loading animation with nothing else on screen.

    Covers the whole page (including Streamlit's own chrome) with a centered
    animated spinner. Used for the brief moment after a refresh while the
    session cookie is being read back.
    """
    st.markdown(
        f"""
        <style>
          /* hide all Streamlit chrome while the splash is up */
          header[data-testid="stHeader"], [data-testid="stToolbar"],
          [data-testid="stDecoration"], [data-testid="stStatusWidget"],
          [data-testid="stSidebar"], .bm-topbar, .bm-footer,
          section.main footer {{ display: none !important; }}

          #bm-splash {{
              position: fixed; inset: 0; z-index: var(--z-splash);
              display: flex; align-items: center; justify-content: center;
              background: {BG_SOFT};
          }}
          #bm-splash .bm-ring {{
              width: 68px; height: 68px; border-radius: 50%;
              border: 6px solid var(--bm-primary-soft);
              border-top-color: var(--bm-accent);
              border-right-color: var(--bm-primary);
              animation: bm-spin 0.85s linear infinite;
          }}
          @keyframes bm-spin {{ to {{ transform: rotate(360deg); }} }}
          @media (prefers-reduced-motion: reduce) {{
              #bm-splash .bm-ring {{ animation-duration: 2s; }}
          }}
        </style>
        <div id="bm-splash"><div class="bm-ring"></div></div>
        """,
        unsafe_allow_html=True,
    )
