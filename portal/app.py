"""
BigMint - AI Labs : Price Forecasting: Steel
Dedicated Adani portal.

Run:  streamlit run portal/app.py     (from the dashboard base folder)
"""
import os
import sys
import re
import html
import base64
import uuid
import tempfile
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme
import grid
import auth
import db
import data_loader as dl
import ai_fill
import tour
from calculators import calc_import_price, calc_cost, calc_elasticity

st.set_page_config(
    page_title="Price Forecasting: Steel",
    layout="wide",
    initial_sidebar_state="collapsed",
)
theme.inject_css()


@st.cache_resource(show_spinner=False)
def _ensure_db_schema():
    """Create any missing tables once per process (idempotent CREATE IF NOT EXISTS).
    The app historically relied on seed_users.py to run init_db(), so new tables
    (e.g. role_commodities) must be ensured here for already-seeded deployments."""
    db.init_db()
    return True


_ensure_db_schema()


# On every fresh page load — a browser refresh or a new login starts with an empty
# session_state (see the cookie note below) — re-check the private data repo's HEAD so
# the latest push is picked up. Only the tiny SHA lookup is invalidated; the per-SHA
# download and per-file parse caches are reused when the repo hasn't moved, so an
# unchanged repo costs one cheap API call, not a re-download.
if "_booted" not in st.session_state:
    st.session_state["_booted"] = True
    dl._remote_sha.clear()


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------
# The browser cookie holds a signed session token so a refresh (which clears
# st.session_state) can restore the login. Two details make this reliable on
# Streamlit Cloud:
#   * READ from st.context.cookies — the HTTP request carries the cookie, so it
#     is available on the very first run after a refresh with no component
#     round-trip and no login flash.
#   * WRITE / CLEAR are DEFERRED to the next run. st.rerun() discards the
#     current run's frontend output, which would drop the cookie component's
#     browser-side write (the cause of "refresh logs me out" and the logout
#     KeyError). We queue the mutation in session_state and perform it on the
#     following run, which renders a full page and is NOT followed by st.rerun().
cookie_manager = stx.CookieManager(key="portal_cm")

_pending_write = st.session_state.pop("_cookie_write", None)
if _pending_write is not None:
    _name, _val, _exp = _pending_write
    try:
        # max_age (relative seconds) is timezone-proof; expires_at is a fallback
        # for browsers that prefer an absolute date.
        cookie_manager.set(_name, _val, expires_at=_exp,
                           max_age=auth.SESSION_TTL_HOURS * 3600, key="cm_set")
    except Exception:
        pass
elif st.session_state.pop("_cookie_clear", False):
    # Delete by overwriting with an immediately-expired empty cookie (avoids the
    # library's delete() KeyError when its in-memory view lacks the cookie).
    try:
        cookie_manager.set(auth.COOKIE_NAME, "", max_age=0,
                           expires_at=db.utcnow() - dt.timedelta(days=1), key="cm_clear")
    except Exception:
        pass


def _read_cookie_token():
    """Read the session cookie from two sources for reliability on refresh.

    1) st.context.cookies — the HTTP request; present on a genuine page reload.
    2) the cookie component's live read — authoritative for cookies set
       client-side this session (may need one extra rerun to populate).
    """
    try:
        tok = st.context.cookies.get(auth.COOKIE_NAME)
        if tok:
            return tok
    except Exception:
        pass
    try:
        # cookie_manager.cookies is populated by CookieManager.__init__'s getAll
        # (no second component). It's {} on the very first render, then filled.
        return (cookie_manager.cookies or {}).get(auth.COOKIE_NAME)
    except Exception:
        return None


def _start_session(profile):
    """Mint a session, store it in session_state, and queue the cookie write."""
    token, expires = auth.create_session(profile["username"])
    st.session_state.user = profile
    st.session_state._auth_token = token
    st.session_state["_cookie_write"] = (auth.COOKIE_NAME, token, expires)


def _password_problem(p1: str, p2: str):
    if p1 != p2:
        return "The two passwords don't match."
    if len(p1) < 10:
        return "Use at least 10 characters."
    return None


# ---------------------------------------------------------------------------
# PER-ROLE ACCESS (commodities + analyst-call audience)
# ---------------------------------------------------------------------------
def allowed_products(role):
    """The `dl.STEEL_PRODUCTS` subset a role may see. Admins and any role with no
    saved config see all (order preserved). Set per role from the Admin tab."""
    if role == "Admin":
        return dl.STEEL_PRODUCTS
    allow = db.get_role_commodities(role)
    if not allow:                       # unconfigured => all
        return dl.STEEL_PRODUCTS
    return {k: v for k, v in dl.STEEL_PRODUCTS.items() if k in allow}


def _call_visible(call, role):
    """Deny-by-default: a call is visible to a (non-admin) role only if that role is
    explicitly in its audience. Untagged calls (empty audience) are 'unassigned' and
    show to admins only — the admin picks each call's audience. Admins bypass this
    (see page_analyst)."""
    return role in (call.get("audiences") or [])


def known_roles():
    """Built-in roles (`auth.ROLES`) plus any custom role already assigned to a user,
    so a role the admin created at runtime appears in every role picker. Built-ins
    first, insertion order preserved."""
    roles = list(auth.ROLES)
    for u in auth.list_users():
        if u["role"] not in roles:
            roles.append(u["role"])
    return roles


def _resolve_new_role(custom, picked):
    """Resolve the add-user role: a non-blank custom name wins over the dropdown.
    A custom name matching an existing role case-insensitively reuses that role's
    exact casing so we don't fork 'Adani' vs 'adani'."""
    custom = (custom or "").strip()
    if not custom:
        return picked
    for r in known_roles():
        if r.lower() == custom.lower():
            return r
    return custom


# Self-contained branded sign-in / reset card. Scoped to the two container keys so it never
# touches the rest of the app. Keeps the core brand (BigMint logo, blue+orange scheme) and the
# auth engine unchanged — this only restyles the shell. Colours come from the --bm-* CSS vars
# seeded on :root by theme.inject_css().
LOGIN_CSS = """
<style>
/* card shell */
.st-key-login_card, .st-key-reset_card {
    max-width: 430px; margin: clamp(40px,8vh,110px) auto 0;
    background: #fff !important; border: 1px solid #e6ebf3 !important; border-radius: 18px !important;
    box-shadow: 0 18px 50px rgba(2,76,161,.12) !important; padding: 0 !important; overflow: hidden;
}
/* thin brand gradient strip across the top of the card */
.st-key-login_card::before, .st-key-reset_card::before {
    content: ""; display: block; height: 5px;
    background: linear-gradient(90deg, var(--bm-primary), var(--bm-accent));
}
/* inner padding (the bordered container's content wrapper) */
.st-key-login_card > div, .st-key-reset_card > div { padding: 30px 34px 28px; }
/* brand header */
.bm-login-brand { text-align: center; margin-bottom: 20px; }
.bm-login-logo { display: flex; justify-content: center; margin-bottom: 14px; }
.bm-login-title { font-size: 22px; font-weight: 800; color: var(--bm-primary-dark);
    letter-spacing: .2px; line-height: 1.2; }
.bm-login-sub { margin-top: 5px; font-size: 13px; color: #6b7686; font-weight: 500; }
/* tighter vertical rhythm so username/password sit closer together */
.st-key-login_card [data-testid="stVerticalBlock"],
.st-key-reset_card [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }
/* field labels */
.st-key-login_card [data-testid="stTextInput"] label,
.st-key-reset_card [data-testid="stTextInput"] label {
    font-size: 12px !important; font-weight: 700 !important; text-transform: uppercase;
    letter-spacing: .4px; color: var(--bm-primary-dark) !important; }
/* field box: ONE clean grey border -> orange on focus (overrides the app-wide input rule cleanly,
   no notch). Border the div that directly wraps the <input>, and clear the outer wrapper's border. */
.st-key-login_card [data-testid="stTextInput"] > div:last-child,
.st-key-reset_card [data-testid="stTextInput"] > div:last-child { border-color: transparent !important; }
.st-key-login_card [data-testid="stTextInput"] div:has(> input),
.st-key-reset_card [data-testid="stTextInput"] div:has(> input) {
    border: 1.5px solid #d7dee9 !important; border-radius: 10px !important; background: #fff !important;
    box-shadow: none !important; transition: border-color .15s ease, box-shadow .15s ease; }
.st-key-login_card [data-testid="stTextInput"] div:has(> input):focus-within,
.st-key-reset_card [data-testid="stTextInput"] div:has(> input):focus-within {
    border-color: var(--bm-accent) !important; box-shadow: 0 0 0 3px rgba(238,78,36,.15) !important; }
.st-key-login_card [data-testid="stTextInput"] input,
.st-key-reset_card [data-testid="stTextInput"] input {
    background: transparent !important; padding: 11px 13px !important; font-size: 14.5px !important;
    color: var(--bm-primary-dark) !important; }
/* placeholder: #6b7686 ≈ 4.9:1 on white (default browser placeholder gray fails AA); opacity:1 so
   Firefox/Safari don't dim it further. */
.st-key-login_card [data-testid="stTextInput"] input::placeholder,
.st-key-reset_card [data-testid="stTextInput"] input::placeholder {
    color: #6b7686 !important; opacity: 1 !important; }
/* keep browser autofill white (it was painting a tinted fill) */
.st-key-login_card [data-testid="stTextInput"] input:-webkit-autofill,
.st-key-reset_card [data-testid="stTextInput"] input:-webkit-autofill {
    -webkit-box-shadow: 0 0 0 40px #fff inset !important;
    -webkit-text-fill-color: var(--bm-primary-dark) !important; }
/* reveal-password eye: muted, accent on hover */
.st-key-login_card [data-testid="stTextInput"] button,
.st-key-reset_card [data-testid="stTextInput"] button {
    color: #64748B !important; background: transparent !important; border: none !important; }
.st-key-login_card [data-testid="stTextInput"] button:hover,
.st-key-reset_card [data-testid="stTextInput"] button:hover { color: var(--bm-accent) !important; }
/* submit button: full-width, a touch taller/bolder; invert on hover (fill -> white, text -> accent) */
.st-key-login_card [data-testid="stButton"] button,
.st-key-reset_card [data-testid="stButton"] button {
    margin-top: 8px; padding: 11px 0 !important; font-size: 15px !important;
    font-weight: 700 !important; border-radius: 10px !important;
    border: 1.5px solid var(--bm-accent) !important; transition: background-color .15s ease, color .15s ease; }
.st-key-login_card [data-testid="stButton"] button:hover,
.st-key-reset_card [data-testid="stButton"] button:hover {
    background: #fff !important; background-color: #fff !important; color: var(--bm-accent) !important; }
.st-key-login_card [data-testid="stButton"] button:hover p,
.st-key-reset_card [data-testid="stButton"] button:hover p { color: var(--bm-accent) !important; }
</style>
"""


def _login_brand(title: str, sub: str) -> str:
    """Card header: product title + subtitle (the BigMint logo lives in the topbar above)."""
    return ("<div class='bm-login-brand'>"
            f"<div class='bm-login-title'>{html.escape(title)}</div>"
            f"<div class='bm-login-sub'>{html.escape(sub)}</div>"
            "</div>")


def _login_bg_style() -> str:
    """Full-bleed steel-mill backdrop for the sign-in screen only. Encodes
    assets/login_bg.webp as a data URI (same pattern as the logo helpers) and lays a
    white frost over it so the steel reads as a light industrial texture behind the
    solid-white login card (styled in LOGIN_CSS). Returns '' (plain background, login
    still works) if the asset is missing. Injected AFTER LOGIN_CSS so these rules win."""
    path = os.path.join(theme.ASSETS_DIR, "login_bg.webp")
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except OSError:
        return ""
    return (
        "<style>"
        "[data-testid='stAppViewContainer']{"
        "background:"
        "linear-gradient(180deg,rgba(255,255,255,.80) 0%,rgba(255,255,255,.66) 100%),"
        f"url('data:image/webp;base64,{b64}') center/cover no-repeat fixed !important;}}"
        "[data-testid='stHeader']{background:transparent !important;}"
        "</style>"
    )


def login_screen():
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(_login_bg_style(), unsafe_allow_html=True)
    theme.render_topbar(None)
    with st.columns([1, 1.4, 1])[1]:
        with st.container(border=True, key="login_card"):
            st.markdown(_login_brand("Steel Price Forecasting", "Sign in to your dashboard"),
                        unsafe_allow_html=True)
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            if st.button("Sign in", width="stretch", type="primary"):
                profile, status = auth.authenticate(username, password)
                if status == "ok":
                    _start_session(profile)
                    st.session_state.page = "Home"
                    st.rerun()
                elif status == "locked":
                    st.error("Too many failed attempts. Try again in a few minutes.")
                elif status == "disabled":
                    st.error("This account is disabled. Contact an administrator.")
                else:
                    st.error("Invalid username or password.")
    st.stop()


def force_password_change():
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    theme.render_topbar(st.session_state.user)
    with st.columns([1, 1.4, 1])[1]:
        with st.container(border=True, key="reset_card"):
            st.markdown(_login_brand("Set a new password",
                                     "Your account needs a new password before you continue."),
                        unsafe_allow_html=True)
            p1 = st.text_input("New password", type="password", key="reset_p1")
            p2 = st.text_input("Confirm new password", type="password", key="reset_p2")
            if st.button("Set password", width="stretch", type="primary"):
                problem = _password_problem(p1, p2)
                if problem:
                    st.error(problem)
                else:
                    uname = st.session_state.user["username"]
                    auth.set_password(uname, p1, must_reset=False)
                    # set_password revoked old sessions; mint + queue a fresh one.
                    _start_session({**st.session_state.user, "must_reset": False})
                    st.rerun()
    theme.footer()
    st.stop()


# Restore a prior login from the cookie if session_state was cleared (refresh).
if "user" not in st.session_state:
    _tok = _read_cookie_token()
    _restored = auth.resolve_session(_tok) if _tok else None
    if _restored:
        st.session_state.user = _restored
        st.session_state._auth_token = _tok
    elif not st.session_state.get("_cookie_probed"):
        # First render after a refresh: the cookie component hasn't reported its
        # value yet, so we can't tell "logged out" from "cookie not delivered
        # yet". Show a full-screen loading animation (NOT the login form) and let
        # the component's automatic rerun deliver the cookie on the next run.
        # This removes the flash of the login screen before auto-login.
        st.session_state["_cookie_probed"] = True
        theme.loading_screen()
        st.stop()

if "user" not in st.session_state:
    login_screen()

user = st.session_state.user
if user.get("must_reset"):
    force_password_change()

# Re-brand the app for this user's role (topbar + all custom surfaces). inject_css()
# already seeded the BigMint defaults for the login screen.
_profile = theme.profile_for(user.get("role"))
theme.apply_role_theme(_profile)

st.session_state.setdefault("page", "Home")

# header: brand bar + a primary "Log out" button (same design as Sign in) pinned top-right. The
# "Take a tour" launcher (tour-eligible roles) is injected by tour.py into the blue bar's right slot
# (.bm-topbar-r), so it sits at the bar's right end just left of Log out.
hcol1, hcol2 = st.columns([6, 1], vertical_alignment="center")
with hcol1:
    theme.render_topbar(user)
with hcol2:
    if st.button("Log out", key="logout_top", type="primary", width="stretch", icon=":material/logout:"):
        auth.logout(st.session_state.get("_auth_token"))
        for k in ("user", "_auth_token", "nav", "calc", "page"):
            st.session_state.pop(k, None)
        st.session_state["_cookie_clear"] = True   # cleared on the next (login) render
        st.rerun()

# data controls (collapsed sidebar): which folder the app reads, the data 'as of'
# date, and a manual refresh. Data files are re-read automatically whenever they
# change on disk (mtime-keyed cache); the app also polls in the background and
# reruns on its own when a file changes (see _auto_refresh_on_data_change), so
# edits to accuracy_tables/ (or the calculators CSV) show up with no manual step.
with st.sidebar:
    st.caption("**Data source**")
    st.caption(f"`{dl.acc_dir()}`")
    _asof = dl.last_actual_date()
    st.caption(f"Data as of **{_asof:%d %b %Y}**" if _asof is not None else "Data as of —")
    st.caption("Auto-refreshes when files change.")
    if st.button("Refresh data", width="stretch", icon=":material/refresh:",
                 help="Re-read the data files from disk right now."):
        st.cache_data.clear()
        st.cache_resource.clear()   # also drop the fetched private-repo snapshot → re-download
        st.rerun()


# Auto pick-up of data edits: poll the data files' mtimes in the background and rerun
# the whole app when any change, so updating a file in accuracy_tables/ (or the
# calculators CSV) shows up on its own — no manual refresh, no restart. The readers
# are mtime-keyed, so the rerun re-reads only the changed file. The first render just
# records the baseline signature; later changes trigger an app-wide rerun.
@st.fragment(run_every=30)
def _auto_refresh_on_data_change():
    sig = dl.data_signature()
    seen = st.session_state.get("_data_sig")
    if seen != sig:
        st.session_state["_data_sig"] = sig
        if seen is not None:
            st.rerun(scope="app")


_auto_refresh_on_data_change()


# ---------------------------------------------------------------------------
# TOP NAVIGATION (button-driven; page state is NOT a widget key)
# ---------------------------------------------------------------------------
NAV = [
    ("Home", "Home", "home"),
    ("Price Forecasting", "Forecasting", "trending_up"),
    ("Analyst Calls", "Analyst calls", "campaign"),
    ("Performance Dashboard", "Performance", "insights"),
    ("Calculators", "Scenario Simulation", "calculate"),
    ("Methodology", "Methodology", "schema"),
]


def top_nav():
    allowed = set(theme.profile_for(user.get("role"))["pages"])   # role-visible pages
    items = [it for it in NAV if it[0] in allowed]
    if user.get("role") == "Admin":                       # Admin tab is admin-only
        items.append(("Admin", "Admin", "admin_panel_settings"))
    widths = [1] * len(items)                             # equal-width buttons -> equal gaps, centred
    cols = st.columns(widths)
    for i, (name, label, mi) in enumerate(items):
        active = st.session_state.page == name
        if cols[i].button(f":material/{mi}: {label}", key=f"nav_{name}",
                          type="primary" if active else "secondary", width="stretch"):
            st.session_state.page = name
            st.rerun()


st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)   # drop the nav a touch below the brand bar
with st.container(key="bm_topnav"):          # stable anchor for the analyst walkthrough (tour.py)
    top_nav()
tour.render(user)                            # analyst-only guided tour bootstrap (no-op for other roles)
st.write("")


# ---------------------------------------------------------------------------
# CHART HELPERS
# ---------------------------------------------------------------------------
# The forecast chart and historical table show the FULL available spot history
# (no fixed window) so nothing earlier than the most recent months is trimmed off.
# The chart's rangeslider + zoom buttons let the user narrow the view when they want to.


def _style_fig(fig, height=430, money=True):
    """Shared clean styling + a snap-to-point 'ball pointer' hover for all charts."""
    fig.update_layout(
        height=height, margin=dict(l=14, r=22, t=38, b=14),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=12.5)),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        hovermode="closest", dragmode=False, hoverdistance=80,
        font=dict(family="sans-serif", size=12, color="#334155"),
    )
    if money:
        fig.update_yaxes(tickprefix="INR ", tickformat=",.0f",
                         title_text="per MT", title_font=dict(size=11, color="#64748b"),
                         title_standoff=8)
    fig.update_yaxes(gridcolor="#eef2f7", zeroline=False, showline=False, automargin=True,
                     ticklabelstandoff=8)
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)", showline=True, linecolor="#e2e8f0",
                     automargin=True, ticklabelstandoff=6)
    return fig


def _dt(t):
    return t.to_pydatetime() if hasattr(t, "to_pydatetime") else t


# Fixed left margin (px) shared by ALL performance-page charts so they render at the SAME width,
# regardless of how wide each one's y-axis labels are ("INR62,000" vs "98%" vs "Correct"). Wide
# enough for the price labels; used with margin autoexpand=False so it never varies per chart.
_PERF_ML = 92   # room for the vertical "per MT" y-axis title on the price charts (still aligns all charts)


def _round50(x):
    """Round a forecast value to the nearest INR 50 (NaN/None pass through unchanged).
    All displayed forecasts are rounded to 50 (cards, tables, chart line + hover)."""
    if x is None or pd.isna(x):
        return x
    return int(round(x / 50.0)) * 50


def _spot_trace(dates, vals, fill=False):
    import plotly.graph_objects as go
    extra = dict(fill="tozeroy", fillcolor="rgba(94,146,214,0.10)") if fill else {}
    return go.Scatter(
        x=[_dt(d) for d in dates], y=list(vals), name="Spot (actual)", mode="lines",
        line=dict(color=theme.SPOT_LINE, width=2.6, shape="spline", smoothing=0.4),
        cliponaxis=False,
        hovertemplate="%{x|%d-%b-%y}<br><b>Spot Price: INR %{y:,.2f}</b><extra></extra>",
        hoverlabel=dict(bgcolor="white", bordercolor="#cfe0f5", font=dict(color=theme.SPOT_DARK)),
        **extra)


# custom Plotly.js layer: a halo+core "highlighter" ball that follows the hovered point
_HL_TEMPLATE = """
<style>html,body{margin:0;padding:0;overflow:hidden;background:transparent;}
/* bottom rangeslider preview: show the line + fill only, hide the per-point dots (only matches charts that have a rangeslider) */
.rangeslider-container path.point{display:none !important;}
/* and draw the forecast line solid in the slider (overrides its dashed stroke; main chart stays dashed) */
.rangeslider-container path.js-line{stroke-dasharray:none !important;}
/* zoom (week) buttons: custom HTML above the plot, fixed geometry so they NEVER shift on click
   (Plotly's own SVG rangeselector re-renders + jitters when a button is clicked). */
.rangebtns{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px 2px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.rangebtns button{font-size:11.5px;font-weight:600;color:#1f2937;background:#eef2f7;
  border:1px solid #e2e8f0;border-radius:7px;padding:3px 11px;cursor:pointer;line-height:1.45;
  outline:none;-webkit-tap-highlight-color:transparent;-webkit-user-select:none;user-select:none;
  transition:background .12s ease,color .12s ease,border-color .12s ease;}
.rangebtns button:hover{border-color:#cbd5e1;background:#e6ebf2;}
/* historical week window: blue gradient light (1W) -> dark (12W/26W/YTD); ALL stays neutral.
   .active still wins (defined after) so the clicked button reads as selected. */
.rangebtns button:nth-child(1){background:#e8f0fb;border-color:#cfe0f6;color:#024CA1;}
.rangebtns button:nth-child(2){background:#b9d3f2;border-color:#a9cbef;color:#024CA1;}
.rangebtns button:nth-child(3){background:#5b93da;border-color:#5b93da;color:#fff;}
.rangebtns button:nth-child(4){background:#024CA1;border-color:#024CA1;color:#fff;}
.rangebtns button:nth-child(5){background:#023d82;border-color:#023d82;color:#fff;}
.rangebtns button:nth-child(6){background:#012f66;border-color:#012f66;color:#fff;}
.rangebtns button.active{background:__ACCENT__;border-color:__ACCENT__;color:#fff;}</style>
__RANGEBTNS__
<div id="__DIV__" style="width:100%;height:__H__px;"></div>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script>
const fig = __FIGJSON__;
const gd = document.getElementById("__DIV__");
Plotly.newPlot(gd, fig.data, fig.layout, {displayModeBar:false, responsive:true});
// wire the custom zoom buttons -> relayout the x-range (no jitter, unlike the SVG rangeselector)
(function(){var rb=document.getElementById("rb___DIV__");if(!rb)return;
  var btns=rb.querySelectorAll("button");
  btns.forEach(function(b){b.addEventListener("click",function(){
    for(var i=0;i<btns.length;i++)btns[i].classList.remove("active");
    b.classList.add("active");
    Plotly.relayout(gd,{"xaxis.range":[b.getAttribute("data-start"),b.getAttribute("data-end")]});
  });});})();
function hexA(c,a){ if(!c) return 'rgba(225,43,32,'+a+')'; if(c[0]!=='#') return c; var h=c.slice(1); if(h.length===3){h=h.split('').map(function(x){return x+x;}).join('');} var n=parseInt(h,16); return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')'; }
gd.on('plotly_hover', function(d){ var p=d.points[0]; var col=(p.fullData.line&&p.fullData.line.color)||'#E12B20'; Plotly.restyle(gd, {x:[[p.x],[p.x]], y:[[p.y],[p.y]], 'marker.color':[hexA(col,0.20), col]}, [__HALO__,__CORE__]); });
gd.on('plotly_unhover', function(){ Plotly.restyle(gd, {x:[[],[]], y:[[],[]]}, [__HALO__,__CORE__]); });
// keep the plot fitted to its container (fixes edge-clipping on tab switch / window resize)
if (window.ResizeObserver) { new ResizeObserver(function(){ Plotly.Plots.resize(gd); }).observe(gd); }
window.addEventListener('resize', function(){ Plotly.Plots.resize(gd); });
</script>
"""


def _render_with_highlighter(fig, height=430, dom_id="chart", range_buttons=None):
    """Render a Plotly figure via a custom JS layer that adds a hover-following ball.
    range_buttons (optional): a list of {label, start, end, active} dicts rendered as a fixed
    HTML zoom-button row above the plot (replaces Plotly's jittery SVG rangeselector)."""
    import plotly.graph_objects as go
    fig.update_layout(autosize=True)
    fig.add_trace(go.Scatter(x=[], y=[], mode="markers", hoverinfo="skip", showlegend=False,
                             cliponaxis=False, marker=dict(size=22, color="rgba(225,43,32,0.18)")))
    fig.add_trace(go.Scatter(x=[], y=[], mode="markers", hoverinfo="skip", showlegend=False,
                             cliponaxis=False, marker=dict(size=9, color=theme.FORECAST_LINE, line=dict(width=2, color="#ffffff"))))
    halo_idx, core_idx = len(fig.data) - 2, len(fig.data) - 1
    rangebtns_html, extra_h = "", 0
    if range_buttons:
        parts = []
        for b in range_buttons:
            cls = " class='active'" if b.get("active") else ""
            parts.append("<button%s data-start='%s' data-end='%s'>%s</button>"
                         % (cls, b["start"], b["end"], html.escape(b["label"])))
        rangebtns_html = "<div class='rangebtns' id='rb_%s'>%s</div>" % (dom_id, "".join(parts))
        extra_h = 40
    doc = (_HL_TEMPLATE.replace("__DIV__", dom_id).replace("__H__", str(height))
           .replace("__RANGEBTNS__", rangebtns_html).replace("__ACCENT__", theme.ACCENT)
           .replace("__FIGJSON__", fig.to_json())
           .replace("__HALO__", str(halo_idx)).replace("__CORE__", str(core_idx)))
    # st.iframe replaces the deprecated components.v1.html (removal announced for mid-2026;
    # 1.59 warns on every call). It takes a src PATH and inlines the file as the iframe's
    # srcdoc (read synchronously at call time), so write the doc to a per-session temp file —
    # the session token keeps concurrent viewers from overwriting each other's charts.
    token = st.session_state.setdefault("_chart_doc_token", uuid.uuid4().hex[:10])
    doc_dir = Path(tempfile.gettempdir()) / "bm_charts"
    doc_dir.mkdir(exist_ok=True)
    doc_path = doc_dir / f"{token}_{dom_id}.html"
    doc_path.write_text(doc, encoding="utf-8")
    st.iframe(doc_path, height=height + 12 + extra_h)


# --- India duty-paid landed-cost overlay ------------------------------------------------------
# A third chart line (violet) on the Rebar IF Mumbai + HRC forecast charts: the weekly India
# duty-paid landed cost from landed_costs.xlsx (Donghua China rebar / FOB-Rizhao China HRC).
# Loaded per product at the call site via dl.load_landed(); see _LANDED_OVERLAY below.
CHINA_LANDED_LINE = "#7C3AED"                 # violet — distinct from blue spot / red forecast


def forecast_chart(acc, fwd, legend_inside=False, year_labels=False, compact=False,
                   landed=None, landed_label="Import landed"):
    """Light-blue actual spot (soft area fill) + bold red dashed forecast, with a dotted
    divider and a faint shaded band marking the 12-week-ahead region.
    legend_inside places the legend inside the plot (white region); year_labels adds the
    short year to the x-axis date ticks; compact grows the plot + slims the top margin so the
    zoom buttons sit just above the graph (all used by the grouped forecasting layout).
    landed (optional): (dates, vals) of the China import-parity landed cost to overlay."""
    hist = acc.dropna(subset=["Actual"]).copy()
    if hist.empty:
        st.info("No historical spot series available for this product.")
        return
    try:
        import plotly.graph_objects as go
        fc_dates = list(hist["Date"]) + list(fwd["Date"])
        fc_vals = [_round50(v) for v in (list(hist["Forecast"]) + list(fwd["Forecast"]))]
        fig = go.Figure()
        fig.add_trace(_spot_trace(hist["Date"], hist["Actual"], fill=True))
        if landed:
            l_dates, l_vals = landed
            fig.add_trace(go.Scatter(
                x=[_dt(d) for d in l_dates], y=list(l_vals), name=landed_label, mode="lines",
                line=dict(color=CHINA_LANDED_LINE, width=2.4, shape="spline", smoothing=0.4),
                cliponaxis=False,
                hovertemplate="%{x|%d-%b-%y}<br><b>" + landed_label + ": INR %{y:,.0f}</b><extra></extra>",
                hoverlabel=dict(bgcolor="white", bordercolor="#ddd0f0", font=dict(color=CHINA_LANDED_LINE))))
        fig.add_trace(go.Scatter(
            x=[_dt(d) for d in fc_dates], y=fc_vals, name="Forecast", mode="lines+markers",
            line=dict(color=theme.FORECAST_LINE, width=2.8, dash="dash", shape="spline", smoothing=0.4),
            marker=dict(size=5, color=theme.FORECAST_LINE, line=dict(width=4, color=theme.FORECAST_HALO)),
            cliponaxis=False,
            hovertemplate="%{x|%d-%b-%y}<br><b>Forecast Price: INR %{y:,.0f}</b><extra></extra>",
            hoverlabel=dict(bgcolor="white", bordercolor="#f3c2bd", font=dict(color=theme.FORECAST_LINE))))

        # dotted divider + faint shaded band where the 12-week-ahead forecast begins
        split_x = _dt(hist["Date"].iloc[-1])
        if len(fwd):
            fig.add_vrect(x0=split_x, x1=_dt(fwd["Date"].iloc[-1]),
                          fillcolor="rgba(238,78,36,0.05)", line_width=0, layer="below")
            fig.add_annotation(x=split_x, y=1, yref="paper", text=f"{len(fwd)}-wk ahead",
                               showarrow=False, xanchor="left", yanchor="top", xshift=6,
                               font=dict(size=11, color=theme.ACCENT))
        fig.add_vline(x=split_x, line=dict(color="#94a3b8", width=1.3, dash="dot"))

        # pad the y-range so the area fill reads as a band rather than a block down to zero
        landed_vals = list(landed[1]) if landed else []
        yvals = [v for v in list(hist["Actual"]) + fc_vals + landed_vals if pd.notna(v)]
        if yvals:
            lo, hi = min(yvals), max(yvals)
            pad = (hi - lo) * 0.14 or hi * 0.03
            fig.update_yaxes(range=[lo - pad, hi + pad])

        # bottom time slider (navigator) + Zoom buttons.
        # The zoom buttons control how much HISTORY (the actual+forecast section) is shown; the
        # 12-week forward forecast stays pinned in view — only dragging the slider hides it.
        # An explicit x-range (autorange=False) pins the axis max to EXACTLY the last forecast
        # date: Plotly's `backward` rangeselector anchors to the current range max, and autorange
        # would pad that max (~16 days here), shifting every window right and dropping ~2 weeks of
        # history. With the padding gone, each "N W" = N weeks of history + the full forecast →
        # count(days) = N*7 + forecast-span (clamped to the loaded history). ALL is also
        # count-based, NOT step="all" (which re-enables autorange and re-introduces the padding).
        last_actual = hist["Date"].iloc[-1]
        last_fc = fwd["Date"].iloc[-1] if len(fwd) else last_actual
        start_all = hist["Date"].iloc[0]
        fc_span = max(int((pd.Timestamp(last_fc) - pd.Timestamp(last_actual)).days), 0)
        all_days = max(int((pd.Timestamp(last_fc) - pd.Timestamp(start_all)).days), 1)

        # Zoom (week) buttons are rendered as custom HTML buttons ABOVE the plot (see
        # _render_with_highlighter / _HL_TEMPLATE), NOT Plotly's own SVG rangeselector: the
        # rangeselector redraws its buttons on every click and visibly jitters/shifts, whereas
        # plain HTML buttons have fixed geometry and never move. Each button just relayouts
        # xaxis.range to [end - N weeks (+ the forecast span), last forecast date], so the
        # 12-week forecast stays pinned and only the amount of history shown changes.
        end_ts = pd.Timestamp(last_fc)

        def _bk(n):
            return end_ts - pd.Timedelta(days=min(n * 7 + fc_span, all_days))

        def _btn(label, start_ts, active=False):
            return {"label": label, "active": active,
                    "start": pd.Timestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end_ts.strftime("%Y-%m-%d %H:%M:%S")}

        range_buttons = [
            _btn("1W", _bk(1)), _btn("4W", _bk(4)), _btn("8W", _bk(8)),
            _btn("12W", _bk(12)), _btn("26W", _bk(26)),
            _btn("YTD", pd.Timestamp(year=end_ts.year, month=1, day=1)),
            _btn("ALL", start_all, active=True),   # default view = full history
        ]

        h = 620 if compact else 560
        top_m = 18 if compact else 82            # buttons now sit OUTSIDE the plot -> slimmer top margin
        fig = _style_fig(fig, height=h)
        fig.update_xaxes(
            # exact range (no autorange padding) so the backward zoom anchors on the last forecast date
            range=[_dt(start_all), _dt(last_fc)], autorange=False,
            # weekly grid for week-by-week reading: faint weekly minor lines + month-ish major ticks
            showgrid=True, gridcolor="#e8eef5", tickformat=("%d %b %y" if year_labels else "%d %b"),
            minor=dict(dtick=7 * 86400000, tick0=_dt(last_actual), showgrid=True, gridcolor="#f3f6fa"),
            rangeslider=dict(visible=True, thickness=0.10, bgcolor="#f1f5f9",
                             bordercolor="#e2e8f0", borderwidth=1,
                             range=[_dt(start_all), _dt(last_fc)]),
        )
        # legend_inside places the legend inside the plot's white region (the top-right slot is
        # taken by the location dropdown in the grouped layout); otherwise keep it above the chart.
        if legend_inside:
            legend = dict(orientation="h", x=0.012, xanchor="left", y=0.99, yanchor="top",
                          bgcolor="rgba(255,255,255,0.74)", bordercolor="#e2e8f0", borderwidth=1,
                          font=dict(size=11.5))
        else:
            legend = dict(x=1, xanchor="right", y=1.18, yanchor="bottom")
        fig.update_layout(margin=dict(l=14, r=22, t=top_m, b=18), legend=legend)
        _render_with_highlighter(fig, height=h, dom_id="fc_chart", range_buttons=range_buttons)
    except Exception:
        h = hist.set_index("Date")[["Actual", "Forecast"]]
        f = fwd.set_index("Date")[["Forecast"]].rename(columns={"Forecast": "Forecast (12-wk)"})
        st.line_chart(pd.concat([h, f], axis=1))


def perf_chart(view):
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(_spot_trace(view["Date"], view["Actual"]))
        fig.add_trace(go.Scatter(
            x=[_dt(d) for d in view["Date"]], y=[_round50(v) for v in view["Forecast"]], name="Forecast",
            mode="lines+markers", line=dict(color=theme.FORECAST_LINE, width=2.6, dash="dash"),
            marker=dict(size=6, color=theme.FORECAST_LINE, line=dict(width=4, color=theme.FORECAST_HALO)),
            hovertemplate="%{x|%d-%b-%y}<br><b>Forecast Price: INR %{y:,.0f}</b><extra></extra>",
            hoverlabel=dict(bgcolor="white", bordercolor="#f3c2bd", font=dict(color=theme.FORECAST_LINE))))
        f = _style_fig(fig, height=320)
        # fixed left margin (autoexpand off) so every performance chart is the SAME width; legend
        # moved INSIDE the plot's white space (top-left); smaller y-label standoff (was 8 -> 3).
        f.update_layout(margin=dict(l=_PERF_ML, r=16, t=14, b=30, autoexpand=False),
                        legend=dict(orientation="h", x=0.015, xanchor="left", y=0.98, yanchor="top",
                                    bgcolor="rgba(255,255,255,0.78)", bordercolor="#e2e8f0",
                                    borderwidth=1, font=dict(size=11.5)))
        f.update_yaxes(automargin=False, ticklabelstandoff=3)
        _render_with_highlighter(f, height=320, dom_id="perf_chart")
    except Exception:
        st.line_chart(view.set_index("Date")[["Actual", "Forecast"]])


def delta_bar(view):
    """Actual-vs-forecast deviation (rounded-forecast − spot) bars, colour-graded by ABSOLUTE
    deviation with a GREEN-HEAVY scale: most of the range is green (small/accurate), amber only
    near the top, red for the very largest. Bars still point up/down by sign. Taller (h=320) so the
    smaller deviations are still visible."""
    try:
        import plotly.graph_objects as go
        deltas = view["Forecast"].map(_round50) - view["Actual"]
        absd = deltas.abs()
        cmax = float(absd.max()) or 1.0
        fig = go.Figure(go.Bar(
            x=view["Date"], y=list(deltas),
            marker=dict(color=list(absd), cmin=0, cmax=cmax, showscale=False, line=dict(width=0),
                        colorscale=[[0.0, theme.SUCCESS], [0.55, "#8DC63F"], [0.8, "#F5A623"], [1.0, theme.DANGER]]),
            hovertemplate="INR %{y:,.0f}<extra>Forecast − Spot</extra>"))
        fig.update_layout(height=320, margin=dict(l=_PERF_ML, r=16, t=10, b=30, autoexpand=False),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                          hovermode="x unified", bargap=0.3,
                          hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0"),
                          font=dict(size=11, color="#334155"))
        fig.update_yaxes(tickprefix="INR ", tickformat=",.0f", gridcolor="#eef2f7", zeroline=True,
                         zerolinecolor="#cbd5e1", automargin=False, ticklabelstandoff=3,
                         title_text="per MT", title_font=dict(size=11, color="#64748b"),
                         title_standoff=8)
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.bar_chart(view.set_index("Date")[["Delta"]])


def delta_acc_bar(view):
    """Weekly delta accuracy — the accuracy table's 'Delta (%)' column (points ×100): the share of
    the actual week-over-week move the forecast captured. 100% = fully captured; negative = moved
    the wrong way. Green-heavy gradient (higher = greener). Weeks with no prior reference or a
    flat-but-predicted-move are blank in the sheet and skipped here. Display clamped to [−100, 100];
    the hover shows the true value."""
    try:
        import plotly.graph_objects as go
        raw = [v * 100 if pd.notna(v) else None for v in view["DeltaAcc"]]
        ys = [None if v is None else max(-100.0, min(100.0, v)) for v in raw]
        cvals = [-100.0 if v is None else max(-100.0, min(100.0, v)) for v in raw]
        texts = ["No prior reference / flat week" if v is None else f"Move captured: {v:.0f}%"
                 for v in raw]
        fig = go.Figure(go.Bar(
            x=view["Date"], y=ys, customdata=texts,
            marker=dict(color=cvals, cmin=-100, cmax=100, showscale=False, line=dict(width=0),
                        colorscale=[[0.0, theme.DANGER], [0.5, "#F5A623"], [0.75, "#8DC63F"], [1.0, theme.SUCCESS]]),
            hovertemplate="%{customdata}<extra></extra>"))
        fig.update_layout(height=200, margin=dict(l=_PERF_ML, r=16, t=10, b=30, autoexpand=False),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                          hovermode="x unified", bargap=0.3,
                          hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0"),
                          font=dict(size=11, color="#334155"))
        fig.update_yaxes(range=[-100, 100], ticksuffix="%", gridcolor="#eef2f7", zeroline=True,
                         zerolinecolor="#cbd5e1", automargin=False, ticklabelstandoff=3)
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.bar_chart((view.set_index("Date")["DeltaAcc"] * 100).to_frame("Delta %"))


def accuracy_chart(view):
    """Weekly forecast absolute accuracy (%) = 100 - |forecast-vs-spot % error|, as a GREEN-HEAVY
    gradient bar chart (highest = green). Compact (h=200) and the y-axis is zoomed into the high band
    (values are always up in the high-90s) so the week-to-week variation is actually visible."""
    try:
        import plotly.graph_objects as go
        acc_pct = 100 - view["DeltaPct"].abs()
        lo, hi = float(acc_pct.min()), float(acc_pct.max())
        if hi - lo < 1e-9:                        # all-equal -> avoid a degenerate colour scale
            lo, hi = lo - 1, hi + 1
        cmin = lo - (hi - lo) * 0.35              # push the worst week up out of the deep red (green-heavy)
        y_lo = min(95.0, float(int(lo)))          # zoom the axis in — everything sits above ~95%
        fig = go.Figure(go.Bar(
            x=view["Date"], y=list(acc_pct),
            marker=dict(color=list(acc_pct), cmin=cmin, cmax=hi, showscale=False, line=dict(width=0),
                        colorscale=[[0.0, theme.DANGER], [0.22, "#F5A623"], [0.5, "#8DC63F"], [1.0, theme.SUCCESS]]),
            hovertemplate="%{x|%d-%b-%y}<br><b>Accuracy: %{y:.1f}%</b><extra></extra>"))
        fig.update_layout(height=200, margin=dict(l=_PERF_ML, r=16, t=10, b=30, autoexpand=False),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                          hovermode="x unified", bargap=0.3,
                          hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0"),
                          font=dict(size=11, color="#334155"))
        fig.update_yaxes(range=[y_lo, 100], ticksuffix="%", gridcolor="#eef2f7",
                         automargin=False, ticklabelstandoff=3)
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.bar_chart((100 - view["DeltaPct"].abs()).to_frame("Accuracy %").set_index(view["Date"]))


def directional_accuracy_bar(view):
    """Per-week directional call: correct (up bar, green) vs wrong (down bar, red)."""
    try:
        import plotly.graph_objects as go
        ys, colors, texts = [], [], []
        for i, r in enumerate(view.itertuples()):
            if i == 0:                       # first week has no prior reference (matches KPI logic)
                ys.append(0); colors.append(theme.NEUTRAL)
                texts.append("No prior reference")
                continue
            hit = bool(r.Hit)
            ys.append(1 if hit else -1)
            colors.append(theme.SUCCESS if hit else theme.DANGER)
            texts.append(f"Predicted {r.PredDir} &middot; Actual {r.ActualDir} &middot; {'Correct' if hit else 'Wrong'}")
        fig = go.Figure(go.Bar(x=view["Date"], y=ys, marker_color=colors, customdata=texts,
                               hovertemplate="%{customdata}<extra></extra>"))
        fig.update_layout(height=200, margin=dict(l=_PERF_ML, r=16, t=10, b=30, autoexpand=False),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                          hovermode="x unified", bargap=0.45,
                          hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0"),
                          font=dict(size=11, color="#334155"))
        fig.update_yaxes(tickvals=[-1, 1], ticktext=["Wrong", "Correct"], range=[-1.4, 1.4],
                         gridcolor="#eef2f7", zeroline=True, zerolinecolor="#cbd5e1",
                         automargin=False, ticklabelstandoff=3)
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.bar_chart(view.assign(Correct=view["Hit"].astype(int)).set_index("Date")[["Correct"]])


# ---------------------------------------------------------------------------
# PAGE: HOME
# ---------------------------------------------------------------------------
def _week_of_month_label(d) -> str:
    """Format a date as a long date, e.g. '17 July 2026'."""
    if d is None or pd.isna(d):
        return "-"
    d = pd.Timestamp(d)
    return f"{d.day} {d:%B %Y}"


def page_home():
    products = allowed_products(user["role"])          # role-scoped commodities
    n_products = len(products)
    allowed_pages = set(theme.profile_for(user.get("role"))["pages"])
    st.markdown("## Price Forecasting: Steel")
    st.write("")

    # "Last updated on" = the newest date an ACTUAL spot exists, read from the accuracy
    # table itself — so updating that file moves this date with no other edits needed.
    last_actual = dl.last_actual_date()
    last_update = _week_of_month_label(last_actual)
    mapas = []
    n_weeks = 0
    for _, meta in products.items():
        acc = dl.load_accuracy("11-week", meta["acc"]).dropna(subset=["Actual", "Forecast"])
        n_weeks = max(n_weeks, len(acc))
        k = dl.accuracy_averages(meta["acc"])
        if k["mapa"] is not None:
            mapas.append(k["mapa"])
    avg_mapa = sum(mapas) / len(mapas) if mapas else None

    with st.container(key="bm_home_kpis"):     # stable anchor for the analyst walkthrough (tour.py)
        s1, s2, s3, s4 = st.columns(4)
        s1.markdown(theme.kpi_card("Steel products", str(n_products), "tracked weekly", theme.icon("factory")), unsafe_allow_html=True)
        s2.markdown(theme.kpi_card("Forecast horizon", "12 wk", "Ensemble Wgt-Mean", theme.icon("trending")), unsafe_allow_html=True)
        s3.markdown(theme.kpi_card("Avg absolute accuracy", f"{avg_mapa:.1f}%" if avg_mapa else "-", f"MAPA, {n_weeks}-wk avg", theme.icon("target")), unsafe_allow_html=True)
        s4.markdown(theme.kpi_card("Last updated on", last_update, "latest actual spot date", theme.icon("calendar")), unsafe_allow_html=True)

    st.write("")
    st.markdown(f"<div class='bm-h bm-modules-h' role='heading' aria-level='2'>{theme.icon('home', 22)} Modules</div>",
                unsafe_allow_html=True)
    # Descriptions are kept ~the same length (≈95 chars, ~2 lines) so they wrap to the same number of
    # lines in every card, keeping the cards visually aligned and the cards nicely filled.
    modules = [
        ("Price forecasting", "Spot price versus the 12-week Ensemble forecast for every tracked steel product, updated weekly.", "trending_up", "Price Forecasting"),
        ("Analyst calls", "Monthly market-outlook calls with the key insights, price drivers and downloadable slide decks.", "campaign", "Analyst Calls"),
        ("Performance", "Week-wise forecast accuracy: spot versus forecast, weekly delta, MAPA and directional hit-rate.", "insights", "Performance Dashboard"),
        ("Scenario Simulation", "Import versus landed-cost parity, production cost and margin, plus price-elasticity what-if tools.", "calculate", "Calculators"),
    ]
    modules = [m for m in modules if m[3] in allowed_pages]   # only role-visible modules
    if modules:
        for col, (title, desc, mi, target) in zip(st.columns(len(modules)), modules):
            with col:
                # whole card is one clickable button (styled via .st-key-homemod_* in theme.py). The
                # material icon is embedded INSIDE the bold title (not the icon= param) so it sits on the
                # heading line; label = **[icon] title** (strong/block) + brief (p text) + *Open ->* (em/block CTA).
                if st.button(f"**:material/{mi}: {title}** {desc} *Open →*",
                             key=f"homemod_{target.replace(' ', '_')}", width="stretch"):
                    st.session_state.page = target
                    st.rerun()

    # full-width banner button spanning the module cards -> Methodology (if visible to this role)
    if "Methodology" in allowed_pages:
        if st.button("**Methodology** — how the forecasts are built: data, models, ensemble & accuracy. *View →*",
                     key="home_methodology", icon=":material/schema:", width="stretch"):
            st.session_state.page = "Methodology"
            st.rerun()
    theme.footer()


# Per-product forecast rationales (Momentum / Call / Rationale), keyed by the product name as in
# dl.STEEL_PRODUCTS. Products without an entry fall back to "_default".
RATIONALES = {
    "_default": (
        "<b>Demand</b> &mdash; <i>placeholder.</i> End-use demand drivers (construction, auto, infra "
        "spending) will be summarised here.<br>"
        "<b>Supply &amp; cost</b> &mdash; <i>placeholder.</i> Raw-material moves (iron ore, coking coal, "
        "scrap), mill output and inventory.<br>"
        "<b>Trade &amp; sentiment</b> &mdash; <i>placeholder.</i> Imports/exports, landed-cost parity and "
        "market sentiment.<br>"
        "<b>Net view</b> &mdash; <i>placeholder.</i> How the above nets out into the 12-week direction shown above."
    ),
    "Rebar BF Mumbai": (
        "<b>₹52,000 &rarr; dips to ~₹48,200, rebounds to ₹53,122.</b><br>"
        "<b>Pulling down (near-term)</b> &mdash; Sharp ₹8,000 correction still working through; monsoon "
        "construction lull caps site demand and keeps trade buyers destocking rather than restocking.<br>"
        "<b>Holding up / recovery (late horizon)</b> &mdash; Blast-furnace cost floor (iron ore + coking coal) "
        "limits how far it can fall; as monsoon eases and pre-festive restocking begins in September, demand "
        "firms → the model's rebound into wk12.<br>"
        "<b>Net</b> &mdash; Correction extends a few more weeks, bottoms mid-monsoon, then recovers with "
        "seasonal demand. High conviction on the fall, lower on the timing of the bounce."
    ),
    "Rebar IF Mumbai": (
        "<b>₹45,896 &rarr; flat, then up to ₹47,262.</b><br>"
        "<b>Pulling down</b> &mdash; Same monsoon demand softness; the down-move that ran through Q2 is still "
        "the dominant backdrop.<br>"
        "<b>Holding up</b> &mdash; The fall has already flattened (last three weeks near-flat) — scrap-linked "
        "(induction-route) cost floor is holding; mild post-monsoon demand pickup supports the gentle "
        "late-horizon lift.<br>"
        "<b>Net</b> &mdash; Basing near ₹46k, then a soft ~3% recovery. Near-term flat is well-supported; the "
        "size of the rebound is the soft part."
    ),
    "Rebar IF Raipur": (
        "<b>₹42,175 &rarr; range-bound ₹42,000–42,900.</b><br>"
        "<b>Pulling down</b> &mdash; Monsoon caps construction demand in the central region; no fresh demand "
        "trigger.<br>"
        "<b>Holding up</b> &mdash; Prices have found a floor ~₹42k — sponge/scrap input costs underpin it and "
        "prevent further slide.<br>"
        "<b>Net</b> &mdash; Consolidation, slight early up-bias fading to flat. This is the &quot;nothing "
        "moves&quot; call — cost floor and weak demand roughly balance."
    ),
    "Structure (IF Raipur)": (
        "<b>₹47,767 &rarr; steady climb to ₹49,680.</b><br>"
        "<b>Pulling down (near-term)</b> &mdash; Monsoon weakness on structurals (infra/fabrication) keeps the "
        "first few weeks flat.<br>"
        "<b>Holding up</b> &mdash; The correction is clearly decelerating; cost floor plus early pre-festive "
        "infra/fabrication restocking drives a steady ~4% recovery through September.<br>"
        "<b>Net</b> &mdash; Bottoming then a slow, well-supported climb — the most consistent up-call in the "
        "set."
    ),
    "HRC": (
        "<b>₹58,250 &rarr; gentle grind up to ₹60,324.</b><br>"
        "<b>Pulling down</b> &mdash; Very little — a soft ₹450 drift; flats are less exposed to the monsoon "
        "construction cycle.<br>"
        "<b>Holding up</b> &mdash; Stable auto/manufacturing/appliance demand plus firm import-parity levels "
        "support a slow grind higher.<br>"
        "<b>Net</b> &mdash; Direction up is reasonable off a very stable base (~+3.6%); magnitude is the less "
        "certain part."
    ),
    "HR Plate": (
        "<b>₹57,600 &rarr; sideways, ends ~₹57,567.</b><br>"
        "<b>Pulling down</b> &mdash; Mild demand softness (project/fabrication) keeps a lid on any rally.<br>"
        "<b>Holding up</b> &mdash; Import parity and stable manufacturing offtake put a floor under it.<br>"
        "<b>Net</b> &mdash; Balanced — supply, demand and cost roughly offset, so it stays range-bound with no "
        "net move over 12 weeks."
    ),
}


# ---------------------------------------------------------------------------
# PAGE: PRICE FORECASTING
# ---------------------------------------------------------------------------
# Top-level commodity groups for the grouped forecasting layout. Within a group a
# top-right dropdown picks the specific location/full name; a group appears only if
# it has ≥1 allowed member.
FORECAST_GROUP_ORDER = ["HRC", "HR Plate", "Rebar", "Structure"]

# Roles that get the grouped forecasting UI (group selector at top + per-group location
# dropdown in the old legend slot + in-chart legend + short year in the x-axis labels).
# Case-insensitive. The grouped layout is the standard for the live roles (Adani / Analyst / Admin).
GROUPED_FORECASTING_ROLES = {"adani", "analyst", "admin"}


def _grouped_forecasting(role):
    return (role or "").strip().lower() in GROUPED_FORECASTING_ROLES


def _group_label(g):
    """Display label for a forecast group tab (internal key kept intact for lookups)."""
    return "Structural section" if g == "Structure" else g


def _product_group(name):
    """Map a STEEL_PRODUCTS key to its top-level group; unknown products form their own group."""
    n = (name or "").strip().lower()
    if n.startswith("hr plate") or n.startswith("hrplate"):
        return "HR Plate"
    if n.startswith("hrc"):
        return "HRC"
    if n.startswith("rebar"):
        return "Rebar"
    if n.startswith("structure"):
        return "Structure"
    return name


def _grouped_products(products):
    """{group: {product_name: meta}} ordered by FORECAST_GROUP_ORDER; only non-empty groups."""
    groups = {}
    for name, meta in products.items():
        groups.setdefault(_product_group(name), {})[name] = meta
    ordered = {g: groups[g] for g in FORECAST_GROUP_ORDER if g in groups}
    for g, mem in groups.items():
        ordered.setdefault(g, mem)
    return ordered


def _location_label(group, name):
    """Short location label for a product within its group (strip the group prefix), else the
    full name — 'Rebar IF Raipur'→'IF Raipur', 'Structure (IF Raipur)'→'IF Raipur', 'HRC'→'HRC'."""
    if name.lower().startswith(group.lower()):
        rest = name[len(group):].strip(" -–—()")
        if rest:
            return rest
    return name


# Full descriptive product names shown in the grouped forecasting "location" dropdown, keyed by
# the dl.STEEL_PRODUCTS key. Anything not listed falls back to the short _location_label (e.g. a
# newly added product). Edit these strings to change what the dropdown displays.
FORECAST_LOCATION_LABELS = {
    "HRC":                   "HRC, Exy-Mumbai, India, IS2062, Gr E250 Br.,2.5-8mm / CTL",
    "HR Plate":              "HR Plate, Exy-Mumbai, India, Gr E250 Br.,5-10mm (HSM)",
    "Rebar BF Mumbai":       "Rebar, Exy-Mumbai, India, IS 1786 Fe 500D,12-32mm, BF Route",
    "Rebar IF Mumbai":       "Rebar, Exw-Mumbai, India, Fe 500, IS 1786,12-25mm, IF Route",
    "Rebar IF Raipur":       "Rebar, Exw-Raipur, India, Fe 500, IS 1786,12-25mm, IF Route",
    "Structure (IF Raipur)": "Structure-Angle, Exw-Raipur, India, IS 2062/2011 E-250 Gr A,150x150 Angle, IF Route",
    "HRC Mundra":            "HRC Mundra - 2.5-8mm IS2062",
    "HR Plate Mundra":       "HR Plate Mundra - 20-40mm E250 BR",
    "Rebar BF Mundra":       "Rebar Mundra BF - 12-32mm Fe500D",
    "Rebar IF Mundra":       "Rebar Mundra IF - 12-32mm Fe500",
    "Structure Mundra":      "Structure Angle Mundra - 150x150 IF Route",
}


def _loc_label(group, name):
    """The dropdown label for a product: the full descriptive name if configured, else short."""
    return FORECAST_LOCATION_LABELS.get(name, _location_label(group, name))


def _default_loc(loc_labels):
    """Default location for a group: the first Mumbai variant if the group has one, else the
    first label. Keeps Mumbai as the landing selection across every forecast group."""
    return next((l for l in loc_labels if "mumbai" in l.lower()), loc_labels[0])


def page_forecasting():
    products = allowed_products(user["role"])
    if not products:
        st.info("No commodities are enabled for your account yet. Please contact an administrator.",
                icon=":material/info:")
        theme.footer()
        return
    grouped = _grouped_forecasting(user["role"])
    loc_labels = loc_key = None
    if grouped:
        groups = _grouped_products(products)
        gkeys = list(groups.keys())
        group = st.segmented_control("Commodity group", gkeys, default=gkeys[0],
                                     key="fc_group", label_visibility="collapsed",
                                     format_func=_group_label)
        group = group if group in groups else gkeys[0]
        loc_map = {_loc_label(group, n): n for n in groups[group]}   # full label -> product key
        loc_labels = sorted(loc_map)
        loc_key = f"fc_loc_{group.replace(' ', '_')}"
        if st.session_state.get(loc_key) not in loc_labels:   # default/sanitise before the widget
            st.session_state[loc_key] = _default_loc(loc_labels)
        product = loc_map[st.session_state[loc_key]]
    else:
        keys = list(products.keys())
        default = keys[0]
        product = st.segmented_control("Product", keys, default=default, key="fc_prod",
                                       label_visibility="collapsed")
        product = product if product in products else default
    meta = products[product]
    summary = dl.load_summary()
    row = dl.summary_row(summary, meta["ff"])
    fwd = dl.load_forward(meta["ff"])
    acc_hist = dl.load_accuracy("11-week", meta["acc"])   # Accuracy_Table_11 (6/16 retired)
    # Rebar IF Mumbai + HRC + HR Plate also get an India duty-paid landed-cost overlay from landed_costs.xlsx
    # (Donghua China rebar / FOB-Rizhao China HRC & HR Plate, weekly, dated to week-end). {product: (sheet, label)}.
    _LANDED_OVERLAY = {"HRC": ("HRC", "China landed"), "Rebar IF Mumbai": ("Rebar", "China landed"),
                       "HR Plate": ("HR Plate", "China landed")}
    landed = landed_label = None
    if product in _LANDED_OVERLAY:
        _sheet, landed_label = _LANDED_OVERLAY[product]
        _ldf = dl.load_landed(_sheet)
        if not _ldf.empty:
            landed = (list(_ldf["Date"]), list(_ldf["Landed"]))

    def _forecast_at(n):
        """(forecast value, direction-vs-last-actual) at forward week n (the 1/4/8/12 horizon
        picked by the tab). The 12-week path is week-ordered (row 0 = week 1), so address it
        positionally — robust to a missing/NA 'Week' column, and clamped to what's loaded."""
        if not row:
            return None, "Flat"
        la = row.get("Last actual (INR/ton)", row.get("Last actual (Rs./ton)", row.get("Last actual (₹/ton)")))
        fc = None
        if fwd is not None and len(fwd):
            fc = fwd.iloc[min(max(int(n), 1), len(fwd)) - 1].get("Forecast")
        if (fc is None or pd.isna(fc)) and n == 1:
            fc = row.get("Next-wk forecast")     # fall back to the summary's next-week value
        fc = _round50(fc)                        # forecasts are shown rounded to the nearest INR 50
        d = dl.direction_flag(fc - la) if (pd.notna(fc) and pd.notna(la)) else "Flat"
        return fc, d

    def price_cards(vertical=False, horizon=1, extra_card=""):
        # Two cards: Last actual spot + the {horizon}-week-forward forecast. The old +12-week card
        # was removed; the forecast card's horizon is driven by the 1W/4W/8W/12W tab (grouped
        # graphical view). vertical=True stacks them in one HTML column beside the chart; extra_card
        # (raw HTML, e.g. the Forecast-rationale card) is appended inside that same column.
        if not row:
            return
        last_actual = row.get("Last actual (INR/ton)", row.get("Last actual (Rs./ton)", row.get("Last actual (₹/ton)")))
        last_date = pd.to_datetime(row.get("Last actual date"), errors="coerce")
        fc, fc_dir = _forecast_at(horizon)
        fc_val = f"₹{fc:,.0f}" if pd.notna(fc) else "—"
        # Card title = the exact calendar date this {horizon}-week forecast is FOR, long format
        # (e.g. "Forecast — 19 July, 2026"), driven by the 1W/4W/8W/12W tab. The 12-week path is
        # week-ordered (row 0 = week 1), so the date sits at positional index horizon-1.
        fc_title = f"{horizon}-week forecast"
        if fwd is not None and len(fwd):
            _fc_date = pd.to_datetime(
                fwd.iloc[min(max(int(horizon), 1), len(fwd)) - 1].get("Date"), errors="coerce")
            if pd.notna(_fc_date):
                fc_title = f"Forecast — {_fc_date.day} {_fc_date.strftime('%B, %Y')}"
        cards = [
            ("Last actual spot", f"₹{last_actual:,.0f}", _week_of_month_label(last_date), theme.icon("rupee")),
            (fc_title, fc_val, theme.direction_chip(fc_dir), theme.icon("trending")),
        ]
        if vertical:
            # One self-contained HTML flex column (.bm-vcards / .bm-vcards-sm, theme.py), immune to
            # how Streamlit nests its container/block DOM.
            st.markdown("<div class='bm-vcards bm-vcards-sm'>"
                        + "".join(theme.kpi_card(t, v, s, i) for t, v, s, i in cards)
                        + extra_card
                        + "</div>", unsafe_allow_html=True)
        else:
            for slot, (title, value, sub, ic) in zip(st.columns(len(cards)), cards):
                slot.markdown(theme.kpi_card(title, value, sub, ic), unsafe_allow_html=True)

    # Default layout: price cards above the tabs. Grouped layout: the graph goes on top
    # (right after the group tabs) with the cards stacked to its RIGHT (Graphical view);
    # the Tabular view keeps them below the table.
    if not grouped:
        price_cards()
        st.write("")
    else:
        # Shared location dropdown on the RIGHT of the view-switch row (CSS pulls it down
        # beside the Graphical/Tabular slider — theme.py .st-key-fc_loc_box) so it can be
        # changed in both the Graphical and Tabular views without switching back to the graph.
        with st.container(key="fc_loc_box"):
            st.selectbox("Location", loc_labels, key=loc_key, label_visibility="collapsed")

    def render_graph_view(horizon=None):
        if grouped:
            # No section title; the zoom (week) buttons sit just ABOVE the plot (compact mode).
            # The 1W/4W/8W/12W horizon tab limits how far FORWARD the forecast is drawn: show only
            # the first `horizon` weeks of the 12-week path (None => all).
            fwd_view = fwd.head(int(horizon)) if horizon else fwd
            forecast_chart(acc_hist, fwd_view, legend_inside=True, year_labels=True, compact=True,
                           landed=landed, landed_label=landed_label)
        else:
            theme.section_title("Spot vs forecast (12-week ahead)", theme.icon("trending"))
            forecast_chart(acc_hist, fwd, landed=landed, landed_label=landed_label)
            _cl = (f" Violet = India duty-paid {landed_label.lower()} cost." if landed else "")
            st.markdown("<div class='bm-footnote'>Light blue = actual spot. Red dashed = model forecast "
                        f"(historical fit + 12-week ahead).{_cl} Hover any point for its price.</div>",
                        unsafe_allow_html=True)

    def render_table_view():
        # One continuous table: history (actual+forecast+delta, blank direction) flows into the
        # 12-week-ahead forecast (forecast+direction, blank actual+delta). Forecasts rounded to INR 50;
        # Δ = Actual − rounded forecast. Sortable (whole dataset) + paginated (52 rows/page).
        theme.section_title("Actual vs Forecast Price (history &rarr; 12-week ahead)", theme.icon("calendar"))
        hist_t = acc_hist.dropna(subset=["Actual"])
        rows = []
        for r in hist_t.itertuples():
            fc = _round50(r.Forecast)
            rows.append({"Date": r.Date, "Actual": r.Actual, "Forecast": fc,
                         "Delta": (r.Actual - fc) if pd.notna(fc) else float("nan"),
                         "Direction": "", "_fwd": False})
        for r in fwd.itertuples():
            rows.append({"Date": r.Date, "Actual": float("nan"), "Forecast": _round50(r.Forecast),
                         "Delta": float("nan"), "Direction": r.Direction, "_fwd": True})
        tdf = pd.DataFrame(rows)

        def _fc_grid(gob, Js):
            gob.configure_column("Date", headerName="Date", valueFormatter=grid.JS_DATE,
                                 filter="agDateColumnFilter", width=130)
            gob.configure_column("Actual", headerName="Actual (INR/t)", type=["numericColumn"],
                                 valueFormatter=grid.JS_MONEY)
            gob.configure_column("Forecast", headerName="Forecast (INR/t)", type=["numericColumn"],
                                 valueFormatter=grid.JS_MONEY)
            gob.configure_column("Delta", headerName="Δ (Actual − Forecast)", type=["numericColumn"],
                                 valueFormatter=grid.JS_DELTA)
            gob.configure_column("Direction", headerName="Direction", valueFormatter=grid.JS_DIR_FMT,
                                 cellStyle=grid.JS_DIR_STYLE, filter=False, width=120)
            gob.configure_column("_fwd", hide=True)
            gob.configure_grid_options(getRowStyle=grid.js_row_bg("_fwd", "rgba(238,78,36,0.06)"))

        grid.bm_grid(tdf, key="fc_tbl", configure=_fc_grid, page_size=50)
        st.markdown("<div class='bm-footnote'>Shaded rows = 12-week-ahead forecast (no actuals yet). "
                    "Forecasts rounded to INR 50; &Delta; = actual &minus; forecast. "
                    "Headline line = Ensemble (Weighted Mean).</div>", unsafe_allow_html=True)

    def render_rationale():
        # Full-width Forecast-rationale section (non-grouped + grouped Tabular views).
        rationale = RATIONALES.get(product, RATIONALES["_default"])
        theme.section_title("Forecast rationale", theme.icon("notes"))
        st.markdown(
            f"<div class='bm-card'><div class='bm-desc' style='font-size:13.5px;line-height:1.65;'>{rationale}</div></div>",
            unsafe_allow_html=True,
        )

    def _rationale_card_html():
        # The rationale as a 3rd KPI-style card (heading INSIDE the card, like the other two),
        # appended into the grouped graphical right rail's .bm-vcards column.
        rationale = RATIONALES.get(product, RATIONALES["_default"])
        return ("<div class='bm-card'><div class='bm-kpi-top'>"
                f"<span class='bm-kpi-icon'>{theme.icon('notes')}</span>"
                "<span class='bm-kpi-label'>Forecast rationale</span></div>"
                f"<div class='bm-desc bm-rationale-body'>{rationale}</div></div>")

    VIEW_OPTS = ["Graphical view", "Tabular view"]
    rationale_shown = False
    if grouped:
        # Sliding pill switch (segmented control styled in theme.py .st-key-fc_view_box).
        # Built on st.segmented_control, NOT st.tabs: it keys on Streamlit-owned
        # radiogroup/testid/aria (react-aria) markup. theme.py's plain-tabs pill CSS also uses
        # the 1.59 selectors (stTab / react-aria-SelectionIndicator), but this switch predates
        # that and stays on the segmented control.
        with st.container(key="fc_view_box"):
            view = st.segmented_control("View", VIEW_OPTS, default=VIEW_OPTS[0],
                                        key="fc_view", label_visibility="collapsed")
        if (view or VIEW_OPTS[0]) == VIEW_OPTS[0]:   # deselection falls back to the graph
            # The 1W/4W/8W/12W horizon tab drives BOTH the graph (forecast drawn out to N weeks) and
            # the forecast card. The tab widget lives in the right rail (rendered after the chart),
            # so read its current value from session_state BEFORE the chart is drawn.
            horizon = int(st.session_state.get("fc_horizon") or 1)
            # Chart on the left; right rail = horizon tab, two (smaller) price cards, rationale card.
            chart_col, cards_col = st.columns([5, 1.25], gap="small")
            with chart_col:
                render_graph_view(horizon)
            with cards_col:
                st.segmented_control("Forecast horizon (weeks ahead)", [1, 4, 8, 12],
                                     format_func=lambda n: f"{n}W", default=1,
                                     key="fc_horizon", label_visibility="visible")
                price_cards(vertical=True, horizon=horizon, extra_card=_rationale_card_html())
            rationale_shown = True
        else:
            render_table_view()
            st.write("")
            price_cards()
    else:
        tab_graph, tab_table = st.tabs(VIEW_OPTS)
        with tab_graph:
            render_graph_view()
        with tab_table:
            render_table_view()

    # Rationale full-width below for every view EXCEPT the grouped graphical one (it already put the
    # rationale in the right rail, as the 3rd card under the price cards).
    if not rationale_shown:
        st.write("")
        render_rationale()
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: ANALYST CALLS  (placeholder)
# ---------------------------------------------------------------------------
_PPT_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _deck_button(col, label, path, sig, mime, icon, key):
    """A live download button for an uploaded deck, or a disabled button when absent."""
    if not path:
        col.button(label, key=key, disabled=True, icon=icon)
        return
    data = dl.fetch_call_file(path, sig)
    if data is None:
        col.button(label, key=key, disabled=True, icon=icon, help="File unavailable")
        return
    col.download_button(label, data=data, file_name=os.path.basename(path),
                        mime=mime, key=key, icon=icon)


def _call_date_label(call) -> str:
    """Full display date for a call — formatted 'date' (ISO) if set, else the legacy 'month' string."""
    d = call.get("date")
    if d:
        try:
            return dt.datetime.strptime(d, "%Y-%m-%d").strftime("%d %B %Y")
        except (ValueError, TypeError):
            return str(d)
    return call.get("month", "")


def _call_date_value(call):
    """A datetime.date for the admin date picker — from 'date' (ISO), else parsed 'month', else today."""
    d = (call or {}).get("date")
    if d:
        try:
            return dt.datetime.strptime(d, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    m = (call or {}).get("month")
    if m:
        try:
            return dt.datetime.strptime(m, "%B %Y").date()
        except (ValueError, TypeError):
            pass
    return dt.date.today()


def _render_call_card(call, sig):
    """Render one analyst-call card (shared by the Analyst page and the Admin preview)."""
    cid = call.get("id", "x")
    # keyed container -> unique `st-key-callcard_*` class so button styling stays scoped to the card
    with st.container(border=True, key=f"callcard_{cid}"):
        top = st.columns([4, 2])
        top[0].markdown(
            f"<div class='bm-call-head'>"
            f"<div class='bm-call-date'>{html.escape(_call_date_label(call))}</div>"
            f"<div class='bm-call-title'>{html.escape(call.get('title', ''))}</div>"
            f"</div>", unsafe_allow_html=True)
        kinds = "Report &middot; Pitchdeck" + (" &middot; Video" if call.get("video") else "")
        top[1].markdown(f"<div class='bm-call-kinds'>{kinds}</div>", unsafe_allow_html=True)
        if call.get("summary"):
            st.markdown(f"<div class='bm-call-summary'>{html.escape(call['summary'])}</div>",
                        unsafe_allow_html=True)
        secs = call.get("sections", {})
        rows = "".join(
            f"<div class='bm-call-sec'><span class='bm-call-sec-l'>{html.escape(lbl)}</span>"
            f"<span class='bm-call-sec-t'>{html.escape(secs.get(lbl, ''))}</span></div>"
            for lbl in dl.ANALYST_SECTIONS if secs.get(lbl)
        )
        if rows:
            st.markdown(f"<div class='bm-call-secs'>{rows}</div>", unsafe_allow_html=True)
        st.markdown("<div class='bm-call-sep'></div>", unsafe_allow_html=True)
        # Video button only shows when a link is set in the backend (else it's dropped entirely).
        if call.get("video"):
            b1, b2, b3, _ = st.columns([2, 2, 1.2, 1])
        else:
            b1, b2, _ = st.columns([2, 2, 2.2])
            b3 = None
        _deck_button(b1, "Download Market Summary Report", call.get("pdf", ""), sig, "application/pdf",
                     ":material/picture_as_pdf:", f"pdf_{cid}")
        _deck_button(b2, "Download Analyst Call Pitchdeck", call.get("ppt", ""), sig, _PPT_MIME,
                     ":material/slideshow:", f"ppt_{cid}")
        if b3 is not None:
            b3.link_button("Video Podcast", call["video"], icon=":material/play_circle:")


def page_analyst():
    st.markdown("## Analyst calls / meets")
    calls = dl.load_analyst_calls()
    if user["role"] != "Admin":                       # admins see every call; others see their audience
        calls = [c for c in calls if _call_visible(c, user["role"])]
    if not calls:
        st.info("No analyst calls published for your account yet.", icon=":material/info:")
        theme.footer()
        return
    sig = dl.data_sig()
    for call in calls:
        _render_call_card(call, sig)
    if user["role"] == "Admin":
        st.caption("You're an admin — use the **Admin** tab to add, edit or remove calls, set each "
                   "call's audience, and upload decks.")
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: ADMIN  (role-gated; edits the Analyst-calls content in the private repo)
# ---------------------------------------------------------------------------
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "call"


def _admin_users_panel():
    """Self-service user administration: create, disable, reset, re-role, delete."""
    with st.expander("User management", icon=":material/group:"):
        users = auth.list_users()
        active_admins = [u["username"] for u in users
                         if u["role"] == "Admin" and u["is_active"]]

        st.dataframe(
            [{"username": u["username"], "name": u["name"], "role": u["role"],
              "active": bool(u["is_active"]),
              "locked": u["locked_until"] is not None} for u in users],
            hide_index=True, width="stretch",
        )

        st.markdown("**Add a user**")
        with st.form("add_user_form", clear_on_submit=True):
            a1, a2, a3 = st.columns(3)
            new_username = a1.text_input("Username")
            new_name = a2.text_input("Full name")
            new_role_pick = a3.selectbox("Role", known_roles())
            new_role_custom = st.text_input(
                "…or create a new role (leave blank to use the dropdown)",
                key="add_user_new_role",
                help="A new role starts with the default branding and access to all commodities, "
                     "and sees no analyst calls until you tag some for it. Set its commodity access "
                     "in the Commodity-access panel and tag its calls in the call editor; for custom "
                     "branding a developer adds a profile in theme.ROLE_PROFILES.")
            add = st.form_submit_button("Create user", type="primary")
        if add:
            uname = (new_username or "").strip().lower()
            role = _resolve_new_role(new_role_custom, new_role_pick)
            if not uname or not new_name.strip():
                st.error("Username and full name are both required.")
            elif not role:
                st.error("Pick a role from the dropdown or type a new one.")
            elif db.get_user(uname) is not None:
                st.error(f"User '{uname}' already exists.")
            else:
                temp = auth.generate_temp_password()
                auth.create_user(uname, new_name.strip(), role, temp, must_reset=True)
                st.success(f"Created '{uname}' with role **{role}**. Share this one-time password — "
                           "they'll set their own on first login:")
                st.code(temp, language=None)

        if not users:
            return
        st.markdown("**Manage a user**")
        sel = st.selectbox("Select user", [u["username"] for u in users],
                           key="admin_user_sel")
        selrow = next(u for u in users if u["username"] == sel)
        is_self = sel == user["username"]
        last_admin = sel in active_admins and len(active_admins) == 1

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            _roles = known_roles()
            role_idx = _roles.index(selrow["role"]) if selrow["role"] in _roles else 0
            new_r = st.selectbox("Role", _roles, index=role_idx, key=f"role_{sel}")
            if st.button("Apply role", key=f"applyrole_{sel}", width="stretch"):
                if last_admin and new_r != "Admin":
                    st.error("Can't demote the last active admin.")
                else:
                    auth.set_role(sel, new_r)
                    st.rerun()
        with m2:
            if selrow["is_active"]:
                if st.button("Disable", key=f"dis_{sel}", width="stretch",
                             disabled=is_self or last_admin,
                             help="You can't disable yourself or the last admin."):
                    auth.set_active(sel, False)
                    st.rerun()
            else:
                if st.button("Enable", key=f"en_{sel}", width="stretch"):
                    auth.set_active(sel, True)
                    st.rerun()
        with m3:
            if st.button("Reset password", key=f"rst_{sel}", width="stretch"):
                temp = auth.generate_temp_password()
                auth.set_password(sel, temp, must_reset=True)
                st.session_state["_admin_last_temp"] = (sel, temp)
                st.rerun()
        with m4:
            if st.button("Delete", key=f"del_{sel}", width="stretch",
                         disabled=is_self or last_admin,
                         help="You can't delete yourself or the last admin."):
                auth.delete_user(sel)
                st.session_state.pop("_admin_last_temp", None)
                st.rerun()

        last_temp = st.session_state.get("_admin_last_temp")
        if last_temp and last_temp[0] == sel:
            st.info(f"One-time password for '{sel}' (they must change it on next login):")
            st.code(last_temp[1], language=None)


def _admin_access_panel():
    """Per-role commodity access: which commodities each user type sees on
    Forecasting / Performance / Home. Stored in Neon (`db.role_commodities`)."""
    with st.expander("Commodity access (per user type)", icon=":material/tune:"):
        st.caption("Pick which commodities each user type sees on Forecasting, Performance and Home. "
                   "A user type with nothing saved sees **all** commodities; save a subset to restrict it. "
                   "Admins always see everything.")
        roles = [r for r in known_roles() if r != "Admin"]
        role = st.selectbox("User type", roles, key="access_role_sel")
        all_products = list(dl.STEEL_PRODUCTS.keys())
        current = db.get_role_commodities(role)
        chosen = st.multiselect("Commodities this user type can see", all_products,
                                default=(current or all_products), key=f"access_ms_{role}")
        if current:
            st.caption(f"Currently restricted to **{len(current)}** of {len(all_products)}: "
                       f"{', '.join(current)}.")
        else:
            st.caption("Currently unconfigured → this user type sees **all** commodities.")
        if st.button("Save access", type="primary", key=f"access_save_{role}"):
            if not chosen:
                st.error("Select at least one commodity — an empty set isn't allowed (it would leave an "
                         "empty dashboard). To hide the whole page for a role, edit its profile in `theme.py`.")
            else:
                db.set_role_commodities(role, chosen)
                st.success(f"Saved commodity access for **{role}**: {', '.join(chosen)}.")
                st.rerun()


def page_admin():
    if user["role"] != "Admin":
        st.error("This page is for admins only.")
        theme.footer()
        return

    _admin_users_panel()
    _admin_access_panel()

    st.markdown("## Admin — Landed Cost defaults")
    with st.expander("Set the org-wide Landed Cost defaults (the starting point for every user)", expanded=False):
        calc_import_price.render(is_admin=True)

    st.markdown("## Admin — Cost Head defaults")
    with st.expander("Manage the org-wide cost heads for both routes (add / rename / delete + set defaults)", expanded=False):
        calc_cost.render_admin_defaults()

    st.markdown("## Admin — Analyst calls")
    if not dl.can_admin_write():
        st.warning("Saving is disabled — no write credentials found. Add a **`github_write_token`** "
                   "(a fine-grained PAT with *Contents: Read & Write* on the data repo) to the `[data]` "
                   "secrets, or give the existing `github_token` write access. See "
                   "`.streamlit/secrets.toml.example`.", icon=":material/warning:")

    calls = dl.load_analyst_calls()
    labels = ["➕ New call"] + [f"{_call_date_label(c) or '?'} — {c.get('title', '')}" for c in calls]
    choice = st.selectbox("Edit an existing call, or create a new one", labels, key="admin_pick")
    editing = calls[labels.index(choice) - 1] if choice != labels[0] else None
    ekey = editing["id"] if editing else "new"   # keys change with selection so fields reset

    esecs = (editing or {}).get("sections", {})
    # Seed the AI-fillable fields once per selection so the "Auto-fill with AI" button
    # (below, outside the form) can write straight into their session_state keys without
    # tripping Streamlit's "default value + Session State" warning (so no `value=` here).
    if f"summary_{ekey}" not in st.session_state:
        st.session_state[f"summary_{ekey}"] = (editing or {}).get("summary", "")
    for _lbl in dl.ANALYST_SECTIONS:
        _sk = f"sec_{ekey}_{_lbl}"
        if _sk not in st.session_state:
            st.session_state[_sk] = esecs.get(_lbl, "")

    # --- Pitch deck upload + AI auto-fill (outside the form so the button can act
    #     mid-edit; the same upload both attaches the deck on save and feeds the AI) ---
    st.markdown("**Analyst Call Pitchdeck (PPT)**")
    ppt_up = st.file_uploader("Pitchdeck — upload a .pptx to enable AI auto-fill (.ppt attaches only)",
                              type=["ppt", "pptx"], key=f"ppt_up_{ekey}", label_visibility="collapsed")
    _is_pptx = ppt_up is not None and ppt_up.name.lower().endswith(".pptx")
    ac1, ac2 = st.columns([1, 2], vertical_alignment="center")
    gen = ac1.button("✨ Auto-fill sections with AI", key=f"ai_gen_{ekey}",
                     disabled=not (_is_pptx and ai_fill.ai_ready()),
                     help="Reads the uploaded .pptx and drafts the headline summary + section "
                          "one-liners with AI. Review and edit before saving.")
    if not ai_fill.ai_ready():
        ac2.caption("⚠ Add a Groq API key under `[groq]` in secrets to enable AI auto-fill.")
    elif ppt_up is not None and not _is_pptx:
        ac2.caption("AI auto-fill needs a **.pptx** file (legacy .ppt can only be attached).")
    if gen:
        try:
            with st.spinner("Reading the deck and drafting sections…"):
                deck_text = ai_fill.extract_pptx_text(ppt_up.getvalue(), ppt_up.name)
                drafted = ai_fill.fill_analyst_sections(deck_text, dl.ANALYST_SECTIONS)
            st.session_state[f"summary_{ekey}"] = drafted.get("summary", "")
            for _lbl in dl.ANALYST_SECTIONS:
                st.session_state[f"sec_{ekey}_{_lbl}"] = drafted.get(_lbl, "")
            st.toast("Sections drafted — review and edit before saving.", icon="✨")
            st.rerun()
        except Exception as e:
            st.error(f"AI auto-fill failed: {e}")

    with st.form(f"call_form_{ekey}"):
        c1, c2 = st.columns(2)
        call_date = c1.date_input("Analyst call date *", value=_call_date_value(editing),
                                  format="DD/MM/YYYY", key=f"date_{ekey}")
        title = c2.text_input("Title", value=(editing or {}).get("title", "Market outlook call"),
                              key=f"title_{ekey}")
        summary = st.text_area("Headline summary", height=80, key=f"summary_{ekey}")
        st.markdown("**Sections** (leave blank to hide a row)")
        secvals = {lbl: st.text_input(lbl, key=f"sec_{ekey}_{lbl}")
                   for lbl in dl.ANALYST_SECTIONS}
        aud_opts = [r for r in known_roles() if r != "Admin"]
        aud_default = [r for r in (editing or {}).get("audiences", []) if r in aud_opts]
        audiences = st.multiselect("Audience — user types who see this call", aud_opts,
                                   default=aud_default, key=f"aud_{ekey}",
                                   help="Pick who sees this call. Leave empty = unassigned "
                                        "(admins only — no other role sees it). Admins always see all calls.")
        video = st.text_input("Video link (URL)", value=(editing or {}).get("video", ""),
                              placeholder="https://…  (leave blank if none)", key=f"video_{ekey}",
                              help="Users get a live “Video Podcast” button linking here; "
                                   "blank hides the button entirely.")
        pdf_up = st.file_uploader("Market Summary Report (PDF)", type=["pdf"], key=f"pdf_up_{ekey}")
        if editing:
            for kind, p in (("PDF", editing.get("pdf")), ("PPT", editing.get("ppt"))):
                if p:
                    st.caption(f"Current {kind}: `{os.path.basename(p)}` (upload a new file to replace it)")
        saved = st.form_submit_button("Save call", type="primary", width="stretch",
                                      disabled=not dl.can_admin_write())

    if saved:
        cid = (editing or {}).get("id") or call_date.strftime("%Y-%m-%d")
        record = {
            "id": cid, "date": call_date.strftime("%Y-%m-%d"),
            "month": call_date.strftime("%B %Y"), "title": title.strip(),
            "summary": summary.strip(),
            "sections": {lbl: secvals[lbl].strip() for lbl in dl.ANALYST_SECTIONS},
            "pdf": (editing or {}).get("pdf", ""), "ppt": (editing or {}).get("ppt", ""),
            "video": video.strip(), "audiences": audiences,   # [] = visible to all
        }
        try:
            if pdf_up is not None:
                record["pdf"] = dl.upload_call_file(cid, pdf_up.name, pdf_up.getvalue())
            if ppt_up is not None:
                record["ppt"] = dl.upload_call_file(cid, ppt_up.name, ppt_up.getvalue())
            if any(c.get("id") == cid for c in calls):
                new_calls = [record if c.get("id") == cid else c for c in calls]
            else:
                new_calls = [record] + calls
            dl.save_analyst_calls(new_calls)
            st.success(f"Saved “{_call_date_label(record)}”.")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")

    if editing and dl.can_admin_write():
        st.divider()
        if st.button("Delete this call", icon=":material/delete:", key=f"del_{ekey}"):
            try:
                for p in (editing.get("pdf"), editing.get("ppt")):
                    if p:
                        dl.gh_delete_file(p, f"Delete deck for {editing['id']}")
                dl.save_analyst_calls([c for c in calls if c.get("id") != editing["id"]])
                st.success("Deleted.")
                st.rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")

    st.divider()
    st.caption("Preview — exactly what analysts see on the Analyst calls tab:")
    sig = dl.data_sig()
    for call in calls:
        _render_call_card(call, sig)
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: PERFORMANCE DASHBOARD
# ---------------------------------------------------------------------------
# Accuracy glossary — rendered as a reference box at the foot of the Performance page and as
# hover tooltips (ⓘ) on the matching metric cards + chart titles. (term, idea, formula).
ACC_GLOSSARY = {
    "mapa": ("Absolute accuracy (MAPA)",
             "Measures how closely forecasts track actual prices on average, based on the size of the error irrespective of direction. Higher values indicate greater accuracy.",
             "100% - mean(|Forecast - Actual| / Actual)"),
    "dir": ("Directional accuracy",
            "The share of weeks in which the forecast correctly anticipated the week-over-week price direction — up, down, or flat.",
            "correct direction calls / total weeks x 100"),
    "delta": ("Delta accuracy",
              "Forecasted price change vs actual price change — how much of the actual weekly price movement the forecast captured. 100% reflects the full move.",
              "mean(captured move / actual move x 100)"),
    "na": ("NA *",
           "Weeks with no data, or where the forecast price deviation stays within the acceptable limit — marked NA and dropped from the averages above.",
           ""),
}


def _acc_help(key):
    """A small ⓘ marker whose native tooltip carries the metric's plain-language definition (see ACC_GLOSSARY)."""
    _term, idea, _formula = ACC_GLOSSARY[key]
    return f" <span class='bm-help' title='{idea}'>&#9432;</span>"


def _acc_glossary_html():
    items = "".join(
        f"<div class='bm-gl-item'><span class='bm-gl-term'>{term}</span>"
        f"<div class='bm-gl-idea'>{idea}</div>"
        + (f"<span class='bm-gl-formula'>{formula}</span>" if formula else "")
        + "</div>"
        for term, idea, formula in ACC_GLOSSARY.values())
    return ("<div class='bm-glossary'><div class='bm-glossary-h'>Accuracy glossary</div>"
            f"{items}</div>")


def page_performance():
    st.markdown("## Performance dashboard")
    products = allowed_products(user["role"])
    if not products:
        st.info("No commodities are enabled for your account yet. Please contact an administrator.",
                icon=":material/info:")
        theme.footer()
        return
    # Same commodity picker as the forecasting page for grouped roles: a group tab-strip
    # (HRC / HR Plate / Rebar / Structure) + a full-name location dropdown; other roles keep the
    # flat product selector.
    if _grouped_forecasting(user["role"]):
        groups = _grouped_products(products)
        gkeys = list(groups.keys())
        # group tab-strip (left) + full-name location dropdown (right) on ONE row
        gcol, lcol = st.columns([1, 1.2], vertical_alignment="center")
        with gcol:
            group = st.segmented_control("Commodity group", gkeys, default=gkeys[0],
                                         key="perf_group", label_visibility="collapsed",
                                         format_func=_group_label)
        group = group if group in groups else gkeys[0]
        loc_map = {_loc_label(group, n): n for n in groups[group]}   # full label -> product key
        loc_labels = sorted(loc_map)
        loc_key = f"perf_loc_{group.replace(' ', '_')}"
        if st.session_state.get(loc_key) not in loc_labels:          # default/sanitise before the widget
            st.session_state[loc_key] = _default_loc(loc_labels)
        with lcol:
            with st.container(key="perf_loc_box"):
                st.selectbox("Location", loc_labels, key=loc_key, label_visibility="collapsed")
        product = loc_map[st.session_state[loc_key]]
    else:
        keys = list(products.keys())
        default = keys[0]
        product = st.segmented_control("Product", keys, default=default, key="perf_prod",
                                       label_visibility="collapsed")
        product = product if product in products else default
    meta = products[product]

    df = dl.load_accuracy("11-week", meta["acc"])   # Accuracy_Table_11 only (window toggle removed)
    if df.empty:
        st.warning("No accuracy data found for this product.")
        theme.footer()
        return
    view = df.dropna(subset=["Actual", "Forecast"]).reset_index(drop=True)   # all rows from the sheet
    kpis = dl.accuracy_averages(meta["acc"])   # headline KPIs = the sheet's own AVERAGE row

    with st.container(key="perf_kpis"):        # stable anchor for the analyst walkthrough (tour.py)
        k1, k2, k3 = st.columns(3)
        k1.markdown(theme.kpi_card("Absolute accuracy (MAPA)" + _acc_help("mapa"),
                    f"{kpis['mapa']:.1f}%" if kpis['mapa'] is not None else "-", f"100 - mean abs % error · {len(view)} wk", theme.icon("target")), unsafe_allow_html=True)
        k2.markdown(theme.kpi_card("Directional accuracy" + _acc_help("dir"),
                    f"{kpis['dir_acc']:.0f}%" if kpis['dir_acc'] is not None else "-", f"correct up/down/flat calls · 12wk cycle avg over {len(view)} wk", theme.icon("gauge")), unsafe_allow_html=True)
        k3.markdown(theme.kpi_card("Delta accuracy" + _acc_help("delta"),
                    f"{kpis['delta_acc']:.0f}%" if kpis['delta_acc'] is not None else "-", f"avg weekly move capture · {len(view)} wk", theme.icon("trending")), unsafe_allow_html=True)

    st.write("")
    theme.section_title("Actual vs Forecast Price Trend graph" + _acc_help("mapa"), theme.icon("trending"))
    perf_chart(view)
    theme.section_title("Actual price vs Forecast Price Deviation Graph", theme.icon("gauge"))
    delta_bar(view)
    st.markdown("<div class='bm-footnote' style='margin-top:-6px;font-weight:700;'>Top / positive bars = Forecast was higher than Spot; "
                "bottom / negative bars = Forecast was lower than Spot.</div>", unsafe_allow_html=True)
    theme.section_title("Weekly forecast absolute accuracy" + _acc_help("mapa"), theme.icon("target"))
    accuracy_chart(view)
    theme.section_title("Weekly directional hit accuracy" + _acc_help("dir"), theme.icon("gauge"))
    directional_accuracy_bar(view)
    theme.section_title("Weekly delta accuracy" + _acc_help("delta"), theme.icon("trending"))
    delta_acc_bar(view)
    st.markdown("<div class='bm-footnote' style='margin-top:-2px;font-weight:700;color:var(--bm-ink);'>* Absent weeks, or weeks where the forecast price deviation stays within the acceptable limit, are marked NA and dropped from the average.</div>",
                unsafe_allow_html=True)

    theme.section_title("Week-wise detail", theme.icon("calendar"))
    # Forecast rounded to INR 50; Delta (and %) recomputed off the rounded forecast so the row is
    # self-consistent. Sortable over the whole dataset + paginated (52 rows/page).
    pdf = view[["Date", "Actual", "Forecast"]].copy()
    pdf["Forecast"] = pdf["Forecast"].map(_round50)
    pdf["Delta"] = pdf["Forecast"] - pdf["Actual"]
    pdf["DeltaPct"] = pdf["Delta"] / pdf["Actual"] * 100

    def _perf_grid(gob, Js):
        gob.configure_column("Date", headerName="Date", valueFormatter=grid.JS_DATE,
                             filter="agDateColumnFilter", width=130)
        gob.configure_column("Actual", headerName="Spot", type=["numericColumn"], valueFormatter=grid.JS_MONEY)
        gob.configure_column("Forecast", headerName="Forecast", type=["numericColumn"], valueFormatter=grid.JS_MONEY)
        gob.configure_column("Delta", headerName="Delta", type=["numericColumn"], valueFormatter=grid.JS_DELTA_PCT)
        gob.configure_column("DeltaPct", hide=True)

    grid.bm_grid(pdf, key="perf_tbl", configure=_perf_grid, page_size=50)
    st.markdown("<div class='bm-footnote'>Delta = Forecast &minus; Spot (forecast rounded to INR 50).</div>",
                unsafe_allow_html=True)
    st.write("")
    st.markdown(_acc_glossary_html(), unsafe_allow_html=True)
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: CALCULATORS
# ---------------------------------------------------------------------------
def page_calculators():
    # Opens straight on a tab strip, mirroring page_forecasting (which opens on its group
    # segmented-control). Same as forecasting: no wrapper container, no top-margin hack — the
    # strip sits flush at the top exactly like forecasting's, so the two pages line up.
    t1, t2, t3 = st.tabs(["Price Sensitivity", "Landed Cost", "Cost Head"])
    with t1:
        calc_elasticity.render()
    with t2:
        calc_import_price.render()
    with t3:
        calc_cost.render()
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: METHODOLOGY  (general, infographic-led)
# ---------------------------------------------------------------------------
def page_methodology():
    st.markdown("## Methodology")

    # Hero text + manual button share ONE keyed container that carries the blue card
    # styling, so the white button renders INSIDE the blue "How the forecast is built" panel.
    _manual = os.path.join(theme.ASSETS_DIR, "BigMint_Portal_User_Manual.pdf")
    with st.container(key="meth_hero"):
        st.markdown(
            "<div class='bm-meth-hero'>"
            "<h3>How the forecast is built</h3>"
            "<p>BigMint AI Labs forecasts steel prices with a <b>hybrid approach</b> &mdash; machine-learning "
            "models trained on 15+ years of BigMint-assessed price data. "
            "Each forecast distils cost, supply&ndash;demand, global and macro signals into a single, transparent "
            "price path with a documented rationale.</p></div>",
            unsafe_allow_html=True,
        )
        if os.path.exists(_manual):
            with open(_manual, "rb") as _f:
                st.download_button("Download user manual", _f.read(),
                                   file_name="BigMint_Portal_User_Manual.pdf",
                                   mime="application/pdf", icon=":material/download:")

    st.markdown(
        "<div class='bm-stat-row'>"
        "<div class='bm-stat'><div class='bm-stat-v'>~98%</div><div class='bm-stat-l'>Average absolute price accuracy</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>~60%</div><div class='bm-stat-l'>Delta accuracy</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>~70%</div><div class='bm-stat-l'>Directional accuracy</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>15+ yrs</div><div class='bm-stat-l'>Historical data trained on</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>1&ndash;2%</div><div class='bm-stat-l'>Typical absolute price difference (error band)</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>IOSCO</div><div class='bm-stat-l'>Audited methodology</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    theme.section_title("From data to forecast", theme.icon("trending"))
    # Engine layout: the original Inputs / Outputs chip columns flank a rich modular
    # pipeline (the blue .bm-fm infographic) in the centre, in place of the old plain
    # "model" box. .bm-engine-wide sizes all tracks to content so the wide centre fits
    # (the plain .bm-engine grid stays narrow for the calculators). Styled in theme.py.
    engine_in = [
        ("factory", "50+ touchpoints based on 15+ yrs of global and local assessed prices", "BigMint's physical price benchmarks"),
        ("rupee",   "Cost, supply &amp; demand",     "Raw-material costs and market-balance signals"),
        ("home",    "Global &amp; macro factors",    "Import/export parity, FX, rates &amp; policy"),
    ]
    engine_out = [
        ("calendar", "12-week forward price path",   "Weekly outlook, refreshed every week"),
        ("trending", "Up / down / flat direction",   "Expected move against the current level"),
        ("notes",    "Back-checked vs realised spot", "Every forecast validated against actuals"),
    ]
    def _engine_chips(items):
        return "".join(
            f"<div class='bm-chip'><span class='ic'>{theme.icon(ic, 15)}</span>"
            f"<span class='bm-chip-txt'><b>{title}</b><small>{sub}</small></span></div>"
            for ic, title, sub in items
        )
    # centre: modular pipeline infographic (Market Inputs -> AI Forecast Engine -> Output)
    fm_inputs = [
        ("home",     "Domestic Price",      "Local market rates"),
        ("globe",    "Global Price",        "International benchmarks"),
        ("gauge",    "Supply &amp; Demand", "Market balance"),
        ("rupee",    "Cost Drivers",        "Input &amp; freight costs"),
        ("calendar", "Macro Factors",       "Economy, FX, policy"),
    ]
    fm_engine = [
        ("cpu",    "ML Evaluation",      "Pattern &amp; trend models"),
        ("chat",   "Sentiment Analysis", "News &amp; market mood"),
        ("target", "Impact Analysis",    "Event-driven shifts"),
    ]
    def _fm_cards(items):
        return "".join(
            f"<div class='bm-fm-card'><span class='ic'>{theme.icon(ic, 20)}</span>"
            f"<b>{title}</b><small>{desc}</small></div>"
            for ic, title, desc in items
        )
    fm = (
        "<div class='bm-fm'>"
        "<div class='bm-fm-block'><div class='bm-fm-hd'><span class='bm-fm-num'>1</span><b>Market Inputs</b></div>"
        f"<div class='bm-fm-cards'>{_fm_cards(fm_inputs)}</div></div>"
        "<div class='bm-fm-arrow'>&rarr;</div>"
        "<div class='bm-fm-block'><div class='bm-fm-hd'><span class='bm-fm-num'>2</span><b>AI Forecast Engine</b></div>"
        f"<div class='bm-fm-cards'>{_fm_cards(fm_engine)}</div></div>"
        "<div class='bm-fm-arrow'>&rarr;</div>"
        "<div class='bm-fm-block'><div class='bm-fm-hd'><span class='bm-fm-num'>3</span><b>Output</b></div>"
        "<div class='bm-fm-cards'><div class='bm-fm-fc'>"
        f"<span class='ic'>{theme.icon('monitor', 26)}</span><b>Forecast</b>"
        "<small>Price direction, range &amp; horizon</small>"
        "<span class='bm-fm-badge'>Prediction</span></div></div></div>"
        "</div>"
    )
    engine = (
        "<div class='bm-engine bm-engine-wide'>"
        f"<div class='bm-engine-col bm-engine-in'><div class='bm-engine-h'>Inputs</div>{_engine_chips(engine_in)}</div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        f"{fm}"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        f"<div class='bm-engine-col bm-engine-out'><div class='bm-engine-h'>Outputs</div>{_engine_chips(engine_out)}</div>"
        "</div>"
    )
    st.markdown(engine, unsafe_allow_html=True)

    st.write("")
    theme.section_title("FlowChart", theme.icon("trending"))
    _flow_path = os.path.join(theme.ASSETS_DIR, "methodology_flowchart.png")
    if os.path.exists(_flow_path):
        with open(_flow_path, "rb") as _fh:
            _flow_b64 = base64.b64encode(_fh.read()).decode()
        # Full-bleed width; mix-blend-mode:multiply drops the image's light-grey backdrop into the
        # page background so the blue line-art blends seamlessly with the brand theme (no grey box).
        st.markdown(
            f"<div class='bm-flowchart' style='width:100%;text-align:center;'>"
            f"<img src='data:image/png;base64,{_flow_b64}' alt='Data-to-forecast flow chart' "
            "style='width:88%;max-width:1350px;height:auto;display:inline-block;mix-blend-mode:multiply;'/></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("FlowChart image not found — add `portal/assets/methodology_flowchart.png`.")

    st.write("")
    theme.section_title("Key factors the model weighs", theme.icon("gauge"))
    factors = [
        ("rupee",    "Cost drivers",            "Raw-material &amp; conversion costs that set the price floor."),
        ("trending", "Upstream &amp; downstream", "Linked prices along the steel value chain."),
        ("home",     "Global prices",           "Import / export parity &amp; international benchmarks."),
        ("gauge",    "Supply &amp; demand",      "Output, inventory and end-use demand balance."),
        ("calendar", "Macro-economic",          "Rates, FX, growth and policy signals."),
    ]
    grid = "<div class='bm-factor-grid'>" + "".join(
        f"<div class='bm-factor'><div class='ic'>{theme.icon(ic, 20)}</div>"
        f"<div><h5>{title}</h5><p>{desc}</p></div></div>"
        for ic, title, desc in factors
    ) + "</div>"
    st.markdown(grid, unsafe_allow_html=True)

    st.write("")
    theme.section_title("Forecast horizons", theme.icon("clock"))
    if _grouped_forecasting(user["role"]):
        # Grouped roles run the weekly model only — surface just that,
        # prominently, instead of a lone card stranded in a 4-up grid.
        st.markdown(
            "<div class='bm-horizon' style='border-top-width:4px;padding:22px 26px;'>"
            "<span class='tag'>Near term &middot; Weekly</span>"
            "<h5 style='font-size:19px;margin:4px 0 8px;'>Weekly &mdash; 12-week rolling forecast</h5>"
            "<p style='font-size:13.5px;max-width:820px;'>This dashboard runs on BigMint's <b>weekly</b> "
            "model: next-week price moves refreshed every week, with the headline Ensemble (Weighted "
            "Mean) projected <b>12 weeks</b> ahead. Monthly, quarterly and annual horizons are not "
            "part of this build.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        horizons = [
            ("Near term",   "Weekly",     "Next-week price moves, updated every week."),
            ("Short term",  "Monthly",    "Near-term month-ahead outlook."),
            ("Medium term", "Quarterly",  "Quarterly view, refreshed monthly."),
            ("Long term",   "Annual",     "Annual view, refreshed quarterly."),
        ]
        hz = "<div class='bm-horizon-grid'>" + "".join(
            f"<div class='bm-horizon'><span class='tag'>{tag}</span><h5>{title}</h5><p>{desc}</p></div>"
            for tag, title, desc in horizons
        ) + "</div>"
        st.markdown(hz, unsafe_allow_html=True)
        st.markdown("<div class='bm-footnote'>This dashboard surfaces the <b>12-week</b> horizon on the "
                    "headline Ensemble (Weighted Mean) line.</div>", unsafe_allow_html=True)

    st.write("")
    theme.section_title("Transparency &amp; governance", theme.icon("notes"))
    tcol = st.columns(2)
    tcol[0].markdown(
        "<div class='bm-card'><h4>Explainable by design</h4>"
        "<div class='bm-desc'>Every forecast ships with a <b>rationale</b> &mdash; a breakdown of the key "
        "cost and supply&ndash;demand factors behind the move &mdash; so the logic behind each "
        "price shift is transparent and auditable, not a black box.</div></div>",
        unsafe_allow_html=True)
    tcol[1].markdown(
        "<div class='bm-card'><h4>IOSCO-aligned</h4>"
        "<div class='bm-desc'>Assessments follow BigMint's IOSCO-audited methodology &mdash; objective and "
        "consistent across time and location, with noise and bias removed by an automated pricing system "
        "trusted for globally referenced commodity price benchmarks.</div></div>",
        unsafe_allow_html=True)

    st.write("")
    st.info("Forecasts use selected factors based on data availability and do not account for unexpected "
            "events or market disruptions. Treat them as indicative, not guarantees.",
            icon=":material/info:")

    theme.footer()


# ---------------------------------------------------------------------------
# DISPATCH
# ---------------------------------------------------------------------------
PAGES = {
    "Home": page_home,
    "Price Forecasting": page_forecasting,
    "Analyst Calls": page_analyst,
    "Performance Dashboard": page_performance,
    "Calculators": page_calculators,
    "Methodology": page_methodology,
    "Admin": page_admin,
}
# Gate the current page by the role's profile (fall back to Home for a hidden page,
# e.g. a stale st.session_state.page after a role change). Home is in every profile.
_allowed_pages = set(theme.profile_for(user.get("role"))["pages"])
if user.get("role") == "Admin":
    _allowed_pages.add("Admin")
if st.session_state.page not in _allowed_pages:
    st.session_state.page = "Home"
PAGES.get(st.session_state.page, page_home)()
