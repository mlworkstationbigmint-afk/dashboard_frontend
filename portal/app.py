"""
BigMint - AI Labs : Price Forecasting: Steel
Dedicated portal prototype (UI demo) for Adani.

Run:  streamlit run portal/app.py     (from the dashboard base folder)
"""
import os
import sys
import re
import html
import datetime as dt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import extra_streamlit_components as stx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme
import auth
import db
import data_loader as dl
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
    """An analyst call is visible if it has no audience (all) or lists this role."""
    aud = call.get("audiences") or []
    return (not aud) or (role in aud)


def login_screen():
    theme.render_topbar(None)
    cols = st.columns([1, 1.5, 1])
    with cols[1]:
        with st.container(border=True):
            st.markdown("### Sign in")
            st.caption("Price Forecasting: Steel")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("Sign in", use_container_width=True, type="primary"):
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
    theme.footer()
    st.stop()


def force_password_change():
    theme.render_topbar(st.session_state.user)
    cols = st.columns([1, 1.5, 1])
    with cols[1]:
        with st.container(border=True):
            st.markdown("### Set a new password")
            st.caption("Your account requires a new password before you continue.")
            p1 = st.text_input("New password", type="password", key="reset_p1")
            p2 = st.text_input("Confirm new password", type="password", key="reset_p2")
            if st.button("Set password", use_container_width=True, type="primary"):
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

# header: brand bar + a primary "Log out" button (same design as Sign in) pinned top-right
hcol1, hcol2 = st.columns([6, 1], vertical_alignment="center")
with hcol1:
    theme.render_topbar(user)
with hcol2:
    if st.button("Log out", key="logout_top", type="primary", use_container_width=True, icon=":material/logout:"):
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
    if st.button("Refresh data", use_container_width=True, icon=":material/refresh:",
                 help="Re-read the data files from disk right now."):
        st.cache_data.clear()
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
    ("Calculators", "Calculators", "calculate"),
    ("Methodology", "Methodology", "schema"),
]


def top_nav():
    allowed = set(theme.profile_for(user.get("role"))["pages"])   # role-visible pages
    items = [it for it in NAV if it[0] in allowed]
    if user.get("role") == "Admin":                       # Admin tab is admin-only
        items.append(("Admin", "Admin", "admin_panel_settings"))
    widths = [1] + [1.35] * (len(items) - 1)              # keep Home a touch narrower
    cols = st.columns(widths)
    for i, (name, label, mi) in enumerate(items):
        active = st.session_state.page == name
        if cols[i].button(f":material/{mi}: {label}", key=f"nav_{name}",
                          type="primary" if active else "secondary", use_container_width=True):
            st.session_state.page = name
            st.rerun()


top_nav()
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
        fig.update_yaxes(tickprefix="Rs.", tickformat=",.0f")
    fig.update_yaxes(gridcolor="#eef2f7", zeroline=False, showline=False, automargin=True)
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)", showline=True, linecolor="#e2e8f0",
                     automargin=True, ticklabelstandoff=6)
    return fig


def _dt(t):
    return t.to_pydatetime() if hasattr(t, "to_pydatetime") else t


def _spot_trace(dates, vals, fill=False):
    import plotly.graph_objects as go
    extra = dict(fill="tozeroy", fillcolor="rgba(94,146,214,0.10)") if fill else {}
    return go.Scatter(
        x=[_dt(d) for d in dates], y=list(vals), name="Spot (actual)", mode="lines",
        line=dict(color=theme.SPOT_LINE, width=2.6, shape="spline", smoothing=0.4),
        cliponaxis=False,
        hovertemplate="%{x|%d-%b-%y}<br><b>Spot Price: Rs.%{y:,.2f}</b><extra></extra>",
        hoverlabel=dict(bgcolor="white", bordercolor="#cfe0f5", font=dict(color=theme.SPOT_DARK)),
        **extra)


# custom Plotly.js layer: a halo+core "highlighter" ball that follows the hovered point
_HL_TEMPLATE = """
<style>html,body{margin:0;padding:0;overflow:hidden;background:transparent;}
/* bottom rangeslider preview: show the line + fill only, hide the per-point dots (only matches charts that have a rangeslider) */
.rangeslider-container path.point{display:none !important;}
/* and draw the forecast line solid in the slider (overrides its dashed stroke; main chart stays dashed) */
.rangeslider-container path.js-line{stroke-dasharray:none !important;}</style>
<div id="__DIV__" style="width:100%;height:__H__px;"></div>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script>
const fig = __FIGJSON__;
const gd = document.getElementById("__DIV__");
Plotly.newPlot(gd, fig.data, fig.layout, {displayModeBar:false, responsive:true});
function hexA(c,a){ if(!c) return 'rgba(225,43,32,'+a+')'; if(c[0]!=='#') return c; var h=c.slice(1); if(h.length===3){h=h.split('').map(function(x){return x+x;}).join('');} var n=parseInt(h,16); return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')'; }
gd.on('plotly_hover', function(d){ var p=d.points[0]; var col=(p.fullData.line&&p.fullData.line.color)||'#E12B20'; Plotly.restyle(gd, {x:[[p.x],[p.x]], y:[[p.y],[p.y]], 'marker.color':[hexA(col,0.20), col]}, [__HALO__,__CORE__]); });
gd.on('plotly_unhover', function(){ Plotly.restyle(gd, {x:[[],[]], y:[[],[]]}, [__HALO__,__CORE__]); });
// keep the plot fitted to its container (fixes edge-clipping on tab switch / window resize)
if (window.ResizeObserver) { new ResizeObserver(function(){ Plotly.Plots.resize(gd); }).observe(gd); }
window.addEventListener('resize', function(){ Plotly.Plots.resize(gd); });
</script>
"""


def _render_with_highlighter(fig, height=430, dom_id="chart"):
    """Render a Plotly figure via a custom JS layer that adds a hover-following ball."""
    import plotly.graph_objects as go
    fig.update_layout(autosize=True)
    fig.add_trace(go.Scatter(x=[], y=[], mode="markers", hoverinfo="skip", showlegend=False,
                             cliponaxis=False, marker=dict(size=22, color="rgba(225,43,32,0.18)")))
    fig.add_trace(go.Scatter(x=[], y=[], mode="markers", hoverinfo="skip", showlegend=False,
                             cliponaxis=False, marker=dict(size=9, color=theme.FORECAST_LINE, line=dict(width=2, color="#ffffff"))))
    halo_idx, core_idx = len(fig.data) - 2, len(fig.data) - 1
    html = (_HL_TEMPLATE.replace("__DIV__", dom_id).replace("__H__", str(height))
            .replace("__FIGJSON__", fig.to_json())
            .replace("__HALO__", str(halo_idx)).replace("__CORE__", str(core_idx)))
    components.html(html, height=height + 12)


def forecast_chart(acc, fwd):
    """Light-blue actual spot (soft area fill) + bold red dashed forecast, with a dotted
    divider and a faint shaded band marking the 12-week-ahead region."""
    hist = acc.dropna(subset=["Actual"]).copy()
    if hist.empty:
        st.info("No historical spot series available for this product.")
        return
    try:
        import plotly.graph_objects as go
        fc_dates = list(hist["Date"]) + list(fwd["Date"])
        fc_vals = list(hist["Forecast"]) + list(fwd["Forecast"])
        fig = go.Figure()
        fig.add_trace(_spot_trace(hist["Date"], hist["Actual"], fill=True))
        fig.add_trace(go.Scatter(
            x=[_dt(d) for d in fc_dates], y=fc_vals, name="Forecast", mode="lines+markers",
            line=dict(color=theme.FORECAST_LINE, width=2.8, dash="dash", shape="spline", smoothing=0.4),
            marker=dict(size=5, color=theme.FORECAST_LINE, line=dict(width=4, color=theme.FORECAST_HALO)),
            cliponaxis=False,
            hovertemplate="%{x|%d-%b-%y}<br><b>Forecast Price: Rs.%{y:,.2f}</b><extra></extra>",
            hoverlabel=dict(bgcolor="white", bordercolor="#f3c2bd", font=dict(color=theme.FORECAST_LINE))))

        # dotted divider + faint shaded band where the 12-week-ahead forecast begins
        split_x = _dt(hist["Date"].iloc[-1])
        if len(fwd):
            fig.add_vrect(x0=split_x, x1=_dt(fwd["Date"].iloc[-1]),
                          fillcolor="rgba(238,78,36,0.05)", line_width=0, layer="below")
            fig.add_annotation(x=split_x, y=1, yref="paper", text="12-wk ahead",
                               showarrow=False, xanchor="left", yanchor="top", xshift=6,
                               font=dict(size=11, color=theme.ACCENT))
        fig.add_vline(x=split_x, line=dict(color="#94a3b8", width=1.3, dash="dot"))

        # pad the y-range so the area fill reads as a band rather than a block down to zero
        yvals = [v for v in list(hist["Actual"]) + fc_vals if pd.notna(v)]
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

        def _wk_button(n, label):
            return dict(count=min(n * 7 + fc_span, all_days), step="day",
                        stepmode="backward", label=label)

        fig = _style_fig(fig, height=560)
        fig.update_xaxes(
            # exact range (no autorange padding) so the backward zoom anchors on the last forecast date
            range=[_dt(start_all), _dt(last_fc)], autorange=False,
            # weekly grid for week-by-week reading: faint weekly minor lines + month-ish major ticks
            showgrid=True, gridcolor="#e8eef5", tickformat="%d %b",
            minor=dict(dtick=7 * 86400000, tick0=_dt(last_actual), showgrid=True, gridcolor="#f3f6fa"),
            rangeslider=dict(visible=True, thickness=0.10, bgcolor="#f1f5f9",
                             bordercolor="#e2e8f0", borderwidth=1,
                             range=[_dt(start_all), _dt(last_fc)]),
            rangeselector=dict(
                buttons=[
                    _wk_button(1, "1W"), _wk_button(4, "4W"), _wk_button(8, "8W"),
                    _wk_button(12, "12W"), _wk_button(26, "26W"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=all_days, label="ALL", step="day", stepmode="backward"),
                ],
                x=0, xanchor="left", y=1.18, yanchor="bottom",
                bgcolor="#eef2f7", activecolor=theme.ACCENT,
                bordercolor="#e2e8f0", borderwidth=1,
                font=dict(size=11.5, color="#1f2937"),
            ),
        )
        # raise the top margin to clear the zoom buttons; move the legend to the top-right
        fig.update_layout(margin=dict(l=14, r=22, t=82, b=18),
                          legend=dict(x=1, xanchor="right", y=1.18, yanchor="bottom"))
        _render_with_highlighter(fig, height=560, dom_id="fc_chart")
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
            x=[_dt(d) for d in view["Date"]], y=list(view["Forecast"]), name="Forecast",
            mode="lines+markers", line=dict(color=theme.FORECAST_LINE, width=2.6, dash="dash"),
            marker=dict(size=6, color=theme.FORECAST_LINE, line=dict(width=4, color=theme.FORECAST_HALO)),
            hovertemplate="%{x|%d-%b-%y}<br><b>Forecast Price: Rs.%{y:,.2f}</b><extra></extra>",
            hoverlabel=dict(bgcolor="white", bordercolor="#f3c2bd", font=dict(color=theme.FORECAST_LINE))))
        _render_with_highlighter(_style_fig(fig, height=320), height=320, dom_id="perf_chart")
    except Exception:
        st.line_chart(view.set_index("Date")[["Actual", "Forecast"]])


def delta_bar(view):
    try:
        import plotly.graph_objects as go
        colors = [theme.DANGER if d > 0 else theme.SUCCESS for d in view["Delta"]]
        fig = go.Figure(go.Bar(x=view["Date"], y=view["Delta"], marker_color=colors,
                               hovertemplate="Rs.%{y:,.0f}<extra>Forecast - Spot</extra>"))
        fig.update_layout(height=200, margin=dict(l=8, r=8, t=8, b=8),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                          hovermode="x unified", bargap=0.35,
                          hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0"),
                          font=dict(size=11, color="#334155"))
        fig.update_yaxes(tickprefix="Rs.", tickformat=",.0f", gridcolor="#eef2f7", zeroline=True, zerolinecolor="#cbd5e1")
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        st.bar_chart(view.set_index("Date")[["Delta"]])


def accuracy_chart(view):
    """Per-week forecast accuracy (%) = 100 - |forecast-vs-spot % error|."""
    try:
        import plotly.graph_objects as go
        acc_pct = 100 - view["DeltaPct"].abs()
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[_dt(d) for d in view["Date"]], y=list(acc_pct), name="Accuracy",
            mode="lines+markers", line=dict(color=theme.SUCCESS, width=2.6, shape="spline", smoothing=0.4),
            marker=dict(size=6, color=theme.SUCCESS, line=dict(width=4, color="rgba(31,157,85,0.16)")),
            hovertemplate="%{x|%d-%b-%y}<br><b>Accuracy: %{y:.1f}%</b><extra></extra>",
            hoverlabel=dict(bgcolor="white", bordercolor="#cdeedd", font=dict(color=theme.SUCCESS))))
        f = _style_fig(fig, height=300, money=False)
        f.update_yaxes(ticksuffix="%")
        _render_with_highlighter(f, height=300, dom_id="acc_chart")
    except Exception:
        st.line_chart((100 - view["DeltaPct"].abs()).to_frame("Accuracy %").set_index(view["Date"]))


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
        fig.update_layout(height=200, margin=dict(l=8, r=8, t=8, b=8),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", dragmode=False,
                          hovermode="x unified", bargap=0.45,
                          hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0"),
                          font=dict(size=11, color="#334155"))
        fig.update_yaxes(tickvals=[-1, 1], ticktext=["Wrong", "Correct"], range=[-1.4, 1.4],
                         gridcolor="#eef2f7", zeroline=True, zerolinecolor="#cbd5e1")
        fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        st.bar_chart(view.assign(Correct=view["Hit"].astype(int)).set_index("Date")[["Correct"]])


# ---------------------------------------------------------------------------
# PAGE: HOME
# ---------------------------------------------------------------------------
def page_home():
    products = allowed_products(user["role"])          # role-scoped commodities
    n_products = len(products)
    allowed_pages = set(theme.profile_for(user.get("role"))["pages"])
    st.markdown("## Price Forecasting: Steel")
    st.markdown(f"Welcome, **{user['name']}**. {n_products} steel "
                f"product{'s' if n_products != 1 else ''}, 12-week Ensemble forecasts and week-wise accuracy.")
    st.write("")

    # "Last updated on" = the newest date an ACTUAL spot exists, read from the accuracy
    # table itself — so updating that file moves this date with no other edits needed.
    last_actual = dl.last_actual_date()
    last_update = last_actual.strftime("%d %b %Y") if last_actual is not None else "-"
    mapas = []
    n_weeks = 0
    for _, meta in products.items():
        acc = dl.load_accuracy("6-week", meta["acc"]).dropna(subset=["Actual", "Forecast"])
        n_weeks = max(n_weeks, len(acc))
        k = dl.accuracy_kpis(acc)
        if k["mapa"] is not None:
            mapas.append(k["mapa"])
    avg_mapa = sum(mapas) / len(mapas) if mapas else None

    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(theme.kpi_card("Steel products", str(n_products), "tracked weekly", theme.icon("factory")), unsafe_allow_html=True)
    s2.markdown(theme.kpi_card("Forecast horizon", "12 wk", "Ensemble Wgt-Mean", theme.icon("trending")), unsafe_allow_html=True)
    s3.markdown(theme.kpi_card("Avg absolute accuracy", f"{avg_mapa:.1f}%" if avg_mapa else "-", f"MAPA, {n_weeks}-wk avg", theme.icon("target")), unsafe_allow_html=True)
    s4.markdown(theme.kpi_card("Last updated on", last_update, "latest actual spot date", theme.icon("calendar")), unsafe_allow_html=True)

    st.write("")
    theme.section_title("Modules", theme.icon("home"))
    modules = [
        ("Price forecasting", "Spot vs 12-week Ensemble forecast for the steel products.", "trending_up", "Price Forecasting"),
        ("Analyst calls", "Monthly market-outlook calls, key insights and downloadable decks.", "campaign", "Analyst Calls"),
        ("Performance", "Week-wise accuracy: spot vs forecast, weekly delta, MAPA and directional hit-rate.", "insights", "Performance Dashboard"),
        ("Calculators", "Import vs landed-cost, production cost & margin, and price-elasticity tools.", "calculate", "Calculators"),
    ]
    modules = [m for m in modules if m[3] in allowed_pages]   # only role-visible modules
    if modules:
        for col, (title, desc, mi, target) in zip(st.columns(len(modules)), modules):
            with col:
                # whole card is one clickable button (styled via .st-key-homemod_* in theme.py)
                # label = **title** (strong/block) + brief (p text) + *Open ->* (em/block CTA)
                if st.button(f"**{title}** {desc} *Open →*", key=f"homemod_{target.replace(' ', '_')}",
                             icon=f":material/{mi}:", use_container_width=True):
                    st.session_state.page = target
                    st.rerun()

    # full-width banner button spanning the module cards -> Methodology (if visible to this role)
    if "Methodology" in allowed_pages:
        if st.button("**Methodology** — how the forecasts are built: data, models, ensemble & accuracy. *View →*",
                     key="home_methodology", icon=":material/schema:", use_container_width=True):
            st.session_state.page = "Methodology"
            st.rerun()
    theme.footer()


# Placeholder forecast rationales. Real per-product analyst commentary to be supplied later;
# add an entry keyed by the product name (as in dl.STEEL_PRODUCTS) to override "_default".
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
}


# ---------------------------------------------------------------------------
# PAGE: PRICE FORECASTING
# ---------------------------------------------------------------------------
def page_forecasting():
    st.markdown("## Price forecasting")
    products = allowed_products(user["role"])
    if not products:
        st.info("No commodities are enabled for your account yet. Please contact an administrator.",
                icon=":material/info:")
        theme.footer()
        return
    keys = list(products.keys())
    default = keys[0]
    product = st.segmented_control("Product", keys, default=default, key="fc_prod",
                                   label_visibility="collapsed")
    product = product if product in products else default
    meta = products[product]
    summary = dl.load_summary()
    row = dl.summary_row(summary, meta["ff"])
    fwd = dl.load_forward(meta["ff"])
    acc_hist = dl.load_accuracy("6-week", meta["acc"])   # Accuracy_Table_6 (Table_16 retired)

    if row:
        last_actual = row.get("Last actual (Rs./ton)", row.get("Last actual (₹/ton)"))
        last_date = pd.to_datetime(row.get("Last actual date"), errors="coerce")
        ld = last_date.strftime("%d %b %Y") if pd.notna(last_date) else "-"
        nextwk = row.get("Next-wk forecast")
        p12 = row.get("+12wk forecast")

        nextwk_dir = dl.direction_flag(nextwk - last_actual) if (pd.notna(nextwk) and pd.notna(last_actual)) else row.get("Next-wk dir", "")
        p12_dir = dl.direction_flag(p12 - last_actual) if (pd.notna(p12) and pd.notna(last_actual)) else row.get("+12wk dir", "")

        k1, k2, k3 = st.columns(3)
        k1.markdown(theme.kpi_card("Last actual spot", f"Rs.{last_actual:,.0f}", ld, theme.icon("rupee")), unsafe_allow_html=True)
        k2.markdown(theme.kpi_card("Next-week forecast", f"Rs.{nextwk:,.0f}", theme.direction_chip(nextwk_dir), theme.icon("clock")), unsafe_allow_html=True)
        k3.markdown(theme.kpi_card("+12-week forecast", f"Rs.{p12:,.0f}", theme.direction_chip(p12_dir), theme.icon("trending")), unsafe_allow_html=True)
    else:
        last_actual, last_date = None, None

    st.write("")
    tab_graph, tab_table = st.tabs(["Graphical view", "Tabular view"])

    with tab_graph:
        theme.section_title("Spot vs forecast (12-week ahead)", theme.icon("trending"))
        forecast_chart(acc_hist, fwd)
        st.markdown("<div class='bm-footnote'>Light blue = actual spot. Red dashed = model forecast "
                    "(historical fit + 12-week ahead). Hover any point for its price.</div>",
                    unsafe_allow_html=True)

    with tab_table:
        # One continuous table: history (actual+forecast+delta, blank direction) flows into
        # the 12-week-ahead forecast (forecast+direction, blank actual+delta).
        theme.section_title("Actual vs forecast (history &rarr; 12-week ahead)", theme.icon("calendar"))
        hist_t = acc_hist.dropna(subset=["Actual"])
        body = ""
        for r in hist_t.itertuples():
            fc = f"Rs.{r.Forecast:,.0f}" if pd.notna(r.Forecast) else ""
            if pd.notna(r.Forecast):
                d = r.Actual - r.Forecast
                delta = f"{'+' if d >= 0 else ''}{d:,.0f}"
            else:
                delta = ""
            body += (f"<tr><td>{r.Date:%d %b %Y}</td>"
                     f"<td class='bm-r'>Rs.{r.Actual:,.0f}</td>"
                     f"<td class='bm-r'>{fc}</td>"
                     f"<td class='bm-r'>{delta}</td>"
                     f"<td class='bm-c'></td></tr>")
        for r in fwd.itertuples():
            body += (f"<tr class='bm-fc-row'><td>{r.Date:%d %b %Y}</td>"
                     f"<td class='bm-r'></td>"
                     f"<td class='bm-r'>Rs.{r.Forecast:,.0f}</td>"
                     f"<td class='bm-r'></td>"
                     f"<td class='bm-c'>{theme.direction_chip(r.Direction)}</td></tr>")
        st.markdown(
            "<table class='bm-table bm-table-lg'><thead><tr><th>Date</th>"
            "<th class='bm-r'>Actual (Rs./t)</th><th class='bm-r'>Forecast (Rs./t)</th>"
            "<th class='bm-r'>&Delta; (Actual &minus; Forecast)</th><th class='bm-c'>Direction</th></tr></thead>"
            f"<tbody>{body}</tbody></table>",
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='bm-footnote'>Top {len(hist_t)} rows = realised spot vs forecast "
                    "(same window as the chart); shaded rows = 12-week-ahead forecast (no actuals yet). "
                    "&Delta; = actual &minus; forecast. Headline line = Ensemble (Weighted Mean).</div>",
                    unsafe_allow_html=True)

    # ---- Forecast rationale (placeholder; real analyst commentary supplied later) ----
    st.write("")
    theme.section_title("Forecast rationale", theme.icon("notes"))
    rationale = RATIONALES.get(product, RATIONALES["_default"])
    st.markdown(
        f"<div class='bm-card'><div class='bm-desc' style='font-size:13.5px;line-height:1.65;'>{rationale}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='bm-footnote'>Placeholder rationale &mdash; analyst commentary to be wired in a later phase.</div>",
                unsafe_allow_html=True)
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


def _render_call_card(call, sig):
    """Render one analyst-call card (shared by the Analyst page and the Admin preview)."""
    with st.container(border=True):
        top = st.columns([5, 1])
        top[0].markdown(f"**{html.escape(call.get('month', ''))} &mdash; "
                        f"{html.escape(call.get('title', ''))}**", unsafe_allow_html=True)
        top[1].markdown("<div style='text-align:right;color:#64748b;font-size:12px;'>PDF / PPT</div>",
                        unsafe_allow_html=True)
        if call.get("summary"):
            st.markdown(f"<div class='bm-desc' style='font-size:13.5px;'>{html.escape(call['summary'])}</div>",
                        unsafe_allow_html=True)
        secs = call.get("sections", {})
        rows = "".join(
            f"<div class='bm-call-sec'><span class='bm-call-sec-l'>{html.escape(lbl)}</span>"
            f"<span class='bm-call-sec-t'>{html.escape(secs.get(lbl, ''))}</span></div>"
            for lbl in dl.ANALYST_SECTIONS if secs.get(lbl)
        )
        if rows:
            st.markdown(f"<div class='bm-call-secs'>{rows}</div>", unsafe_allow_html=True)
        cid = call.get("id", "x")
        b1, b2, _ = st.columns([1, 1, 4])
        _deck_button(b1, "Download PDF", call.get("pdf", ""), sig, "application/pdf",
                     ":material/picture_as_pdf:", f"pdf_{cid}")
        _deck_button(b2, "Download PPT", call.get("ppt", ""), sig, _PPT_MIME,
                     ":material/slideshow:", f"ppt_{cid}")


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
            hide_index=True, use_container_width=True,
        )

        st.markdown("**Add a user**")
        with st.form("add_user_form", clear_on_submit=True):
            a1, a2, a3 = st.columns(3)
            new_username = a1.text_input("Username")
            new_name = a2.text_input("Full name")
            new_role = a3.selectbox("Role", auth.ROLES)
            add = st.form_submit_button("Create user", type="primary")
        if add:
            uname = (new_username or "").strip().lower()
            if not uname or not new_name.strip():
                st.error("Username and full name are both required.")
            elif db.get_user(uname) is not None:
                st.error(f"User '{uname}' already exists.")
            else:
                temp = auth.generate_temp_password()
                auth.create_user(uname, new_name.strip(), new_role, temp, must_reset=True)
                st.success(f"Created '{uname}'. Share this one-time password — "
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
            role_idx = auth.ROLES.index(selrow["role"]) if selrow["role"] in auth.ROLES else 0
            new_r = st.selectbox("Role", auth.ROLES, index=role_idx, key=f"role_{sel}")
            if st.button("Apply role", key=f"applyrole_{sel}", use_container_width=True):
                if last_admin and new_r != "Admin":
                    st.error("Can't demote the last active admin.")
                else:
                    auth.set_role(sel, new_r)
                    st.rerun()
        with m2:
            if selrow["is_active"]:
                if st.button("Disable", key=f"dis_{sel}", use_container_width=True,
                             disabled=is_self or last_admin,
                             help="You can't disable yourself or the last admin."):
                    auth.set_active(sel, False)
                    st.rerun()
            else:
                if st.button("Enable", key=f"en_{sel}", use_container_width=True):
                    auth.set_active(sel, True)
                    st.rerun()
        with m3:
            if st.button("Reset password", key=f"rst_{sel}", use_container_width=True):
                temp = auth.generate_temp_password()
                auth.set_password(sel, temp, must_reset=True)
                st.session_state["_admin_last_temp"] = (sel, temp)
                st.rerun()
        with m4:
            if st.button("Delete", key=f"del_{sel}", use_container_width=True,
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
        roles = [r for r in auth.ROLES if r != "Admin"]
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

    st.markdown("## Admin — Analyst calls")
    if not dl.can_admin_write():
        st.warning("Saving is disabled — no write credentials found. Add a **`github_write_token`** "
                   "(a fine-grained PAT with *Contents: Read & Write* on the data repo) to the `[data]` "
                   "secrets, or give the existing `github_token` write access. See "
                   "`.streamlit/secrets.toml.example`.", icon=":material/warning:")

    calls = dl.load_analyst_calls()
    labels = ["➕ New call"] + [f"{c.get('month', '?')} — {c.get('title', '')}" for c in calls]
    choice = st.selectbox("Edit an existing call, or create a new one", labels, key="admin_pick")
    editing = calls[labels.index(choice) - 1] if choice != labels[0] else None
    ekey = editing["id"] if editing else "new"   # keys change with selection so fields reset

    esecs = (editing or {}).get("sections", {})
    with st.form(f"call_form_{ekey}"):
        c1, c2 = st.columns(2)
        month = c1.text_input("Month *", value=(editing or {}).get("month", ""),
                              placeholder="e.g. July 2026", key=f"month_{ekey}")
        title = c2.text_input("Title", value=(editing or {}).get("title", "Market outlook call"),
                              key=f"title_{ekey}")
        summary = st.text_area("Headline summary", value=(editing or {}).get("summary", ""),
                               height=80, key=f"summary_{ekey}")
        st.markdown("**Sections** (leave blank to hide a row)")
        secvals = {lbl: st.text_input(lbl, value=esecs.get(lbl, ""), key=f"sec_{ekey}_{lbl}")
                   for lbl in dl.ANALYST_SECTIONS}
        aud_opts = [r for r in auth.ROLES if r != "Admin"]
        aud_default = [r for r in (editing or {}).get("audiences", []) if r in aud_opts]
        audiences = st.multiselect("Audience — user types who see this call", aud_opts,
                                   default=aud_default, key=f"aud_{ekey}",
                                   help="Leave empty = visible to everyone. Admins always see all calls.")
        u1, u2 = st.columns(2)
        pdf_up = u1.file_uploader("PDF deck", type=["pdf"], key=f"pdf_up_{ekey}")
        ppt_up = u2.file_uploader("PPT deck", type=["ppt", "pptx"], key=f"ppt_up_{ekey}")
        if editing:
            for kind, p in (("PDF", editing.get("pdf")), ("PPT", editing.get("ppt"))):
                if p:
                    st.caption(f"Current {kind}: `{os.path.basename(p)}` (upload a new file to replace it)")
        saved = st.form_submit_button("Save call", type="primary", use_container_width=True,
                                      disabled=not dl.can_admin_write())

    if saved:
        if not month.strip():
            st.error("Month is required.")
        else:
            cid = (editing or {}).get("id") or _slug(month)
            record = {
                "id": cid, "month": month.strip(), "title": title.strip(),
                "summary": summary.strip(),
                "sections": {lbl: secvals[lbl].strip() for lbl in dl.ANALYST_SECTIONS},
                "pdf": (editing or {}).get("pdf", ""), "ppt": (editing or {}).get("ppt", ""),
                "audiences": audiences,   # [] = visible to all
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
                st.success(f"Saved “{record['month']}”.")
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
def page_performance():
    st.markdown("## Performance dashboard")
    products = allowed_products(user["role"])
    if not products:
        st.info("No commodities are enabled for your account yet. Please contact an administrator.",
                icon=":material/info:")
        theme.footer()
        return
    keys = list(products.keys())
    default = keys[0]
    product = st.segmented_control("Product", keys, default=default, key="perf_prod",
                                   label_visibility="collapsed")
    product = product if product in products else default
    meta = products[product]

    df = dl.load_accuracy("6-week", meta["acc"])   # Accuracy_Table_6 only (window toggle removed)
    if df.empty:
        st.warning("No accuracy data found for this product.")
        theme.footer()
        return
    view = df.dropna(subset=["Actual", "Forecast"]).reset_index(drop=True)   # all rows from the sheet
    kpis = dl.accuracy_kpis(view)

    k1, k2, k3 = st.columns(3)
    k1.markdown(theme.kpi_card("Absolute accuracy (MAPA)",
                f"{kpis['mapa']:.1f}%" if kpis['mapa'] is not None else "-", f"100 - mean abs % error · {len(view)} wk", theme.icon("target")), unsafe_allow_html=True)
    k2.markdown(theme.kpi_card("Directional accuracy",
                f"{kpis['dir_acc']:.0f}%" if kpis['dir_acc'] is not None else "-", "correct up/down/flat calls", theme.icon("gauge")), unsafe_allow_html=True)
    k3.markdown(theme.kpi_card("Average delta",
                f"{kpis['avg_delta']:+.1f}%" if kpis['avg_delta'] is not None else "-", "forecast vs spot", theme.icon("trending")), unsafe_allow_html=True)

    st.write("")
    theme.section_title("Actual vs forecast", theme.icon("trending"))
    perf_chart(view)
    theme.section_title("Weekly delta (forecast - spot)", theme.icon("insights") if False else theme.icon("gauge"))
    delta_bar(view)
    theme.section_title("Weekly forecast accuracy (%)", theme.icon("target"))
    accuracy_chart(view)
    theme.section_title("Weekly directional accuracy", theme.icon("gauge"))
    directional_accuracy_bar(view)

    theme.section_title("Week-wise detail", theme.icon("calendar"))
    rows_html = ""
    for r in view.itertuples():
        rows_html += (
            f"<tr><td>{r.Date:%d %b %Y}</td>"
            f"<td class='bm-r'>Rs.{r.Actual:,.0f}</td>"
            f"<td class='bm-r'>Rs.{r.Forecast:,.0f}</td>"
            f"<td class='bm-r'>{'+' if r.Delta>=0 else ''}{r.Delta:,.0f} ({r.DeltaPct:+.1f}%)</td></tr>"
        )
    st.markdown(
        "<table class='bm-table'><thead><tr><th>Date</th>"
        "<th class='bm-r'>Spot</th><th class='bm-r'>Forecast</th>"
        "<th class='bm-r'>Delta</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='bm-footnote'>Delta = Forecast - Spot.</div>",
                unsafe_allow_html=True)
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: CALCULATORS
# ---------------------------------------------------------------------------
def page_calculators():
    st.markdown("## Calculators")
    t1, t2, t3 = st.tabs(["Import vs Landed Cost (HRC)", "Production Cost & Margin", "Price Elasticity (HRC)"])
    with t1:
        calc_import_price.render()
    with t2:
        calc_cost.render()
    with t3:
        calc_elasticity.render()
    theme.footer()


# ---------------------------------------------------------------------------
# PAGE: METHODOLOGY  (general, infographic-led)
# ---------------------------------------------------------------------------
def page_methodology():
    st.markdown("## Methodology")

    st.markdown(
        "<div class='bm-meth-hero'>"
        "<h3>How the forecast is built</h3>"
        "<p>BigMint AI Labs forecasts steel prices with a <b>hybrid approach</b> &mdash; machine-learning "
        "models trained on 15+ years of BigMint-assessed price data, combined with market sentiment. "
        "Each forecast distils cost, supply&ndash;demand, global and macro signals into a single, transparent "
        "price path with a documented rationale.</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='bm-stat-row'>"
        "<div class='bm-stat'><div class='bm-stat-v'>~98%</div><div class='bm-stat-l'>Price accuracy</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>15+ yrs</div><div class='bm-stat-l'>Historical data trained on</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>1&ndash;2%</div><div class='bm-stat-l'>Typical delta (error band)</div></div>"
        "<div class='bm-stat'><div class='bm-stat-v'>IOSCO</div><div class='bm-stat-l'>Audited methodology</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    theme.section_title("The forecasting pipeline", theme.icon("trending"))
    steps = [
        ("factory",  "Market data",        "Real-time trades, confirmed deals &amp; 15+ yrs of assessed prices."),
        ("gauge",    "Signal engineering", "Cost, supply&ndash;demand, global &amp; macro factors + sentiment."),
        ("target",   "ML + sentiment",     "Multiple models predict each product; sentiment adjusts."),
        ("trending", "Ensemble",           "Models blended into the headline Ensemble (Weighted Mean)."),
        ("calendar", "12-wk forecast",     "Forward price path with up / down / flat direction."),
        ("notes",    "Accuracy tracking",  "Every forecast back-checked against realised spot."),
    ]
    # One continuous left-to-right pipeline (6 steps, arrows between). Rendered as a
    # CSS grid (card / arrow / card / …) so it never wraps into the awkward 3+3
    # diagonal jump; it collapses to a single vertical column on narrow screens
    # (see .bm-flow in theme.py).
    flow = "<div class='bm-flow'>"
    for j, (ic, title, desc) in enumerate(steps):
        flow += (f"<div class='bm-flow-step'><div class='num'>{j + 1}</div>"
                 f"<div class='ic'>{theme.icon(ic, 22)}</div><div class='bm-flow-t'>{title}</div><p>{desc}</p></div>")
        if j < len(steps) - 1:
            flow += "<div class='bm-flow-arrow'>&rarr;</div>"
    flow += "</div>"
    st.markdown(flow, unsafe_allow_html=True)

    st.write("")
    theme.section_title("Key factors the model weighs", theme.icon("gauge"))
    factors = [
        ("rupee",    "Cost drivers",            "Raw-material &amp; conversion costs that set the price floor."),
        ("trending", "Upstream &amp; downstream", "Linked prices along the steel value chain."),
        ("home",     "Global prices",           "Import / export parity &amp; international benchmarks."),
        ("gauge",    "Supply &amp; demand",      "Output, inventory and end-use demand balance."),
        ("calendar", "Macro-economic",          "Rates, FX, growth and policy signals."),
        ("mic",      "Market sentiment",        "Tone from deals, news and participant behaviour."),
    ]
    grid = "<div class='bm-factor-grid'>" + "".join(
        f"<div class='bm-factor'><div class='ic'>{theme.icon(ic, 20)}</div>"
        f"<div><h5>{title}</h5><p>{desc}</p></div></div>"
        for ic, title, desc in factors
    ) + "</div>"
    st.markdown(grid, unsafe_allow_html=True)

    st.write("")
    theme.section_title("Forecast horizons", theme.icon("clock"))
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
    st.markdown("<div class='bm-footnote'>This Adani prototype surfaces the <b>12-week</b> horizon on the "
                "headline Ensemble (Weighted Mean) line.</div>", unsafe_allow_html=True)

    st.write("")
    theme.section_title("Transparency &amp; governance", theme.icon("notes"))
    tcol = st.columns(2)
    tcol[0].markdown(
        "<div class='bm-card'><h4>Explainable by design</h4>"
        "<div class='bm-desc'>Every forecast ships with a <b>rationale</b> &mdash; a breakdown of the key "
        "cost, supply&ndash;demand and sentiment factors behind the move &mdash; so the logic behind each "
        "price shift is transparent and auditable, not a black box.</div></div>",
        unsafe_allow_html=True)
    tcol[1].markdown(
        "<div class='bm-card'><h4>IOSCO-aligned</h4>"
        "<div class='bm-desc'>Assessments follow BigMint's IOSCO-audited methodology &mdash; objective, "
        "consistent across time and location, with noise and bias removed by an automated pricing system.</div></div>",
        unsafe_allow_html=True)

    st.write("")
    st.info("Forecasts use selected factors based on data availability and do not account for unexpected "
            "events, market disruptions or sentiment-driven shocks. Treat them as indicative, not guarantees.",
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
