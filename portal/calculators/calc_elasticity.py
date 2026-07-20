# =============================================================================
# Price Sensitivity calculator — HRC · HR Plate · Rebar
# =============================================================================
# Product tab-strip (HRC / HR Plate / Rebar, same widget as the forecast page),
# two interchangeable input modes tied to the same shock state — Sliders (knobs)
# and a customisable Table — a persistent contribution chart with a Graph /
# Table-of-changes view switch, KPI cards on the right, and a landed-cost-style
# methodology.
#
# The ENGINE is unchanged: predicted move = Σ(effective % change × sensitivity),
# price = current × e^Σ. HRC keeps its live Ridge fit (load_model below); HR
# Plate and Rebar use the fixed-sensitivity models in engine_sensitivity.py
# (from the backtested REBAR__3.XLS / HRPLAT_2.XLS sheets). The per-driver
# sensitivities are never displayed, so the model can't be reverse-engineered.
# =============================================================================
import os
import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge

import theme
from calculators import engine_sensitivity as eng

try:  # resolve the in-repo CSV path via the shared loader; fall back to a sibling file
    import data_loader as _dl
    CSV_PATH = _dl.calculators_csv()
except Exception:
    CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HRC - Copy.csv")

HRC_FULL_NAME = "HRC, Exy-Mumbai · 2.5-8mm / CTL · IS2062, Gr E250 Br."

CALC_CSS = """
<style>
/* breathing room (theme.py squeezes the block gap; loosen it on this dense page) */
[data-testid="stVerticalBlock"] { gap: 0.9rem !important; }
[data-testid="stHorizontalBlock"] { gap: 1.1rem !important; }
/* prominent page heading (mirrors the Landed Cost / Cost Head calculators) */
.bm-calc-head { margin: 4px 0 14px; padding: 0 0 13px; border-bottom: 2px solid var(--bm-primary-soft); }
.bm-calc-title { display: flex; align-items: center; gap: 13px; font-size: 30px; font-weight: 800;
    color: var(--bm-primary-dark); line-height: 1.15; letter-spacing: .2px; }
.bm-calc-title svg { color: var(--bm-primary); flex: 0 0 auto; }
.bm-calc-sub { margin: 7px 0 0 1px; color: #64748b; font-size: 14px; font-weight: 500; }
/* section heading — accent left bar */
.bm-sec { display: flex; align-items: center; gap: 10px; font-size: 19px; font-weight: 700;
    color: var(--bm-primary-dark); margin: 8px 0 12px; padding-left: 12px;
    border-left: 4px solid var(--bm-accent); }
.bm-sec svg { color: var(--bm-primary); flex: 0 0 auto; }
/* model / backtest fact card in the controls column */
.bm-modelnote { font-size: 12.5px; line-height: 1.6; color: #475569; background: var(--bm-primary-soft);
    border: 1px solid #dbe7f7; border-radius: 10px; padding: 11px 13px; margin-top: 6px; }
.bm-modelnote b { color: var(--bm-primary-dark); }
/* equation chip inside the methodology pipeline (reuses theme .bm-flow*) */
.bm-eq { margin-top: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; font-weight: 600; color: var(--bm-primary-dark);
    background: var(--bm-primary-soft); border: 1px solid #dbe7f7; border-radius: 8px;
    padding: 7px 9px; line-height: 1.45; width: 100%; box-sizing: border-box; }
.bm-eq b { color: var(--bm-accent); }
/* general estimation equation block (one row per product) */
.bm-eqset { display: flex; flex-direction: column; gap: 8px; margin: 4px 0 6px; }
.bm-eqrow { display: flex; align-items: center; gap: 12px; background: var(--bm-primary-soft);
    border: 1px solid #dbe7f7; border-left: 4px solid var(--bm-accent); border-radius: 10px;
    padding: 10px 14px; }
.bm-eqtag { flex: 0 0 auto; min-width: 72px; font-size: 11px; font-weight: 800; letter-spacing: .3px;
    text-transform: uppercase; color: var(--bm-accent); }
.bm-eqbody { font-family: ui-serif, Georgia, "Times New Roman", serif; font-size: 15px;
    color: var(--bm-primary-dark); line-height: 1.5; }
.bm-eqbody sub { font-size: 11px; }

/* ---- knob cards (Sliders mode) — soft neumorphic panels, all identical size ---- */
.st-key-sens_knobwrap [data-testid="stHorizontalBlock"] { gap: 0.5rem !important; align-items: stretch; }
.st-key-sens_knobwrap [data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #edf1f7 !important; border-radius: 16px !important;
    background: #ffffff !important;
    box-shadow: 0 6px 16px rgba(15,23,42,.06), inset 0 1px 0 #ffffff !important;
    padding: 13px 15px 15px !important; min-height: 132px; height: 100%;
    display: flex; flex-direction: column; justify-content: space-between;
    transition: box-shadow .2s ease, transform .2s ease; }
.st-key-sens_knobwrap [data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 12px 26px rgba(2,76,161,.13), inset 0 1px 0 #ffffff !important;
    transform: translateY(-2px); }
/* kill any inner fill (Streamlit paints the bordered container's inner block with the theme's
   grey secondaryBackground on 1.59) so the whole card reads pure white. */
.st-key-sens_knobwrap [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"],
.st-key-sens_knobwrap [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] {
    background: transparent !important; background-color: transparent !important; }
/* driver name = clean centred uppercase caption (like LEVEL / WIDTH on the reference) */
.knob-label { text-align: center; font-size: 11.5px; font-weight: 700; letter-spacing: .4px;
    text-transform: uppercase; color: var(--bm-primary-dark); min-height: 30px; line-height: 1.2;
    display: flex; align-items: center; justify-content: center; margin: 0 0 2px; }
/* the current-value bubble above the thumb */
.st-key-sens_knobwrap [data-testid="stSliderThumbValue"] {
    font-size: 12px !important; font-weight: 700 !important; color: var(--bm-primary-dark) !important; }
/* hide the widget's own -20/+20 ticks; we render our own aligned scale under the slider */
.st-key-sens_knobwrap [data-testid="stSliderTickBar"] { display: none !important; }
.knob-ticks { display: flex; justify-content: space-between; font-size: 9.5px; color: #a3adbb;
    letter-spacing: .2px; margin: -16px 3px 2px; }
/* baseline -> shocked result line (coloured delta) */
.knob-res { text-align: center; font-size: 12px; color: #334155; line-height: 1.45; margin: 8px 0 3px; }
.knob-res b { color: var(--bm-primary-dark); }
.knob-res .arw { color: #94a3b8; margin: 0 3px; }
.knob-res .dl { font-weight: 700; }
.knob-res.up .dl { color: #1F9D55; }
.knob-res.down .dl { color: #D8382B; }
.knob-res.muted { color: #94a3b8; }
/* compact preset chips + quiet per-driver reset inside the knob cards */
.st-key-sens_knobwrap div[class*="st-key-pre_"] button {
    padding: 2px 0 !important; min-height: 23px !important; font-size: 9.5px !important;
    font-weight: 700 !important; border-radius: 7px !important; white-space: nowrap !important; }
.st-key-sens_knobwrap div[class*="st-key-rst_"] button {
    padding: 1px 0 !important; min-height: 22px !important; font-size: 11px !important;
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: #94a3b8 !important; }
.st-key-sens_knobwrap div[class*="st-key-rst_"] button:hover { color: var(--bm-accent) !important; }
/* The value + −/+ box (white fill + ONE rounded orange border, no inner seam) comes from the
   app-wide stNumberInput rule in theme.py — the same clean recipe as the dropdowns. Here we only
   add the centred, bold value; the stepper glyph colours + hover are below. */
.st-key-sens_knobwrap [data-testid="stNumberInput"] input {
    padding: 4px 6px !important; text-align: center !important;
    font-weight: 700 !important; color: var(--bm-primary-dark) !important; }
/* steppers: orange glyph on white; on HOVER -> orange fill + WHITE glyph (so they never vanish) */
.st-key-sens_knobwrap [data-testid="stNumberInput"] button { color: var(--bm-accent) !important; }
.st-key-sens_knobwrap [data-testid="stNumberInput"] button svg { fill: var(--bm-accent) !important; }
.st-key-sens_knobwrap [data-testid="stNumberInput"] button:hover {
    background: var(--bm-accent) !important; background-color: var(--bm-accent) !important; color: #fff !important; }
.st-key-sens_knobwrap [data-testid="stNumberInput"] button:hover svg { fill: #fff !important; }
</style>
"""


def _sec(text, icon=""):
    ic = f"{icon} " if icon else ""
    st.markdown(f"<div class='bm-sec'>{ic}{text}</div>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# HRC engine — UNCHANGED live Ridge fit on the calculators CSV
# -----------------------------------------------------------------------------
def _csv_mtime():
    try:
        return os.path.getmtime(CSV_PATH)
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False)
def _load_model(mtime):   # mtime in the cache key => re-read when the CSV changes
    df = pd.read_csv(CSV_PATH)
    df.columns = df.columns.str.strip()
    target = "HRC, Exy-Mumbai, India, 2.5-8mm / CTL, IS2062, Gr E250 Br."
    features = [
        "Iron Ore Fines, Odisha Index, India, 0-10mm, Fe 62%",
        "Coking Coal, CNF Paradip, India, 0-40mm, HCC 64 Mid Vol, Australia",
        "Melting Scrap, DAP-Mumbai, India, HMS(80:20)",
        "HRC, FOB Rizhao, China, 2.5mm",
        "HRC, FOB Black Sea, Russia, 3mm, SAE1006",
        "Platts North European HRC, EXW Ruhr",
        "CRC, Exy-Mumbai, India, IS 513, CR1,0.90mm / CTL",
        "India Production Quantity of Flat Steel in MT",
        "India weekly HRC Imports MT",
        "India weekly HRC Exports MT",
    ]
    for col in features + [target]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    df = df.sort_values(by="Date").dropna()
    lagged_df = pd.DataFrame()
    lagged_df[target] = df[target]
    for f in features:
        lagged_df[f"{f}_lag0"] = df[f]
    lagged_df = lagged_df.dropna()
    lagged_df = lagged_df[(lagged_df > 0).all(axis=1)]
    log_df = np.log(lagged_df)
    ret_df = log_df.diff().dropna()
    X = ret_df.drop(columns=[target])
    y = ret_df[target]
    model = Ridge(alpha=10)
    model.fit(X, y)
    return model, list(X.columns)


def load_model():
    """Fit the Ridge elasticity model. Re-read/re-fit when the CSV changes."""
    return _load_model(_csv_mtime())


# short display names for the (long) HRC feature columns
_HRC_SHORT = {
    "Iron Ore Fines, Odisha Index, India, 0-10mm, Fe 62%": "Iron Ore Fines (Odisha, Fe62)",
    "Coking Coal, CNF Paradip, India, 0-40mm, HCC 64 Mid Vol, Australia": "Coking Coal (CNF Paradip)",
    "Melting Scrap, DAP-Mumbai, India, HMS(80:20)": "Melting Scrap HMS 80:20 (Mumbai)",
    "HRC, FOB Rizhao, China, 2.5mm": "HRC FOB Rizhao (China)",
    "HRC, FOB Black Sea, Russia, 3mm, SAE1006": "HRC FOB Black Sea (Russia)",
    "Platts North European HRC, EXW Ruhr": "HRC EXW Ruhr (N. Europe)",
    "CRC, Exy-Mumbai, India, IS 513, CR1,0.90mm / CTL": "CRC Exy-Mumbai",
    "India Production Quantity of Flat Steel in MT": "Flat Steel Production (India)",
    "India weekly HRC Imports MT": "HRC Imports (India, weekly)",
    "India weekly HRC Exports MT": "HRC Exports (India, weekly)",
}

# Per-driver (baseline, unit) for HRC. Iron Ore Fines is real (₹6,450/t, Jun-26);
# the rest are ⚠ PLACEHOLDERS — order-of-magnitude sane per unit so the
# "baseline → shocked" readout is legible, but replace with real values before use.
# Baselines only scale the ₹/unit ⇄ % conversion; the % shock itself (what the
# model consumes) never depends on them.
_HRC_META = {
    "Iron Ore Fines (Odisha, Fe62)":     (6450.0,   "₹/t"),
    "Coking Coal (CNF Paradip)":         (210.0,    "$/t"),   # ⚠ placeholder
    "Melting Scrap HMS 80:20 (Mumbai)":  (36000.0,  "₹/t"),   # ⚠ placeholder
    "HRC FOB Rizhao (China)":            (560.0,    "$/t"),   # ⚠ placeholder
    "HRC FOB Black Sea (Russia)":        (570.0,    "$/t"),   # ⚠ placeholder
    "HRC EXW Ruhr (N. Europe)":          (620.0,    "€/t"),   # ⚠ placeholder
    "CRC Exy-Mumbai":                    (62000.0,  "₹/t"),   # ⚠ placeholder
    "Flat Steel Production (India)":     (10.5,     "Mt"),    # ⚠ placeholder
    "HRC Imports (India, weekly)":       (150.0,    "kt"),    # ⚠ placeholder
    "HRC Exports (India, weekly)":       (120.0,    "kt"),    # ⚠ placeholder
}
_HRC_PLACEHOLDER = 10000.0     # fallback baseline for any unmapped driver


def _hrc_spec():
    """Build the HRC product spec from the LIVE Ridge fit (sensitivities =
    coefficients). Per-driver baselines + units come from _HRC_META so HRC also
    supports absolute (₹/$/€/unit) shock entry, same as HR Plate / Rebar."""
    model, columns = load_model()
    drivers = []
    for col, beta in zip(columns, model.coef_):
        name = _HRC_SHORT.get(col.split("_lag")[0], col.split("_lag")[0][:34])
        baseline, unit = _HRC_META.get(name, (_HRC_PLACEHOLDER, "unit"))
        drivers.append((name, float(baseline), float(beta), unit))
    return {
        "label": "HRC", "full_name": HRC_FULL_NAME, "current": 50000.0,
        "model": "Ridge regression (α=10) on log-differenced weekly prices",
        "r2": None, "rmse_pct": None, "rmse_rs": None, "n_obs": None,
        "period": "15+ yrs of weekly BigMint-assessed prices", "drivers": drivers,
    }


# -----------------------------------------------------------------------------
# Charts / tables
# -----------------------------------------------------------------------------
def _view_height(n):
    """Shared pixel height so the Graph and the Table-of-changes fill the same box."""
    return int(min(560, max(300, 44 + 34 * n)))            # header + one row per driver


def _contrib_figure(names, contrib_rs, height):
    """Horizontal diverging bars — each driver's ₹/t contribution to the move.
    Persistent: renders (flat, centred on zero) even when no shocks are entered."""
    import plotly.graph_objects as go
    order = sorted(names, key=lambda n: contrib_rs[n])      # most negative at bottom
    vals = [contrib_rs[n] for n in order]
    colors = [theme.SUCCESS if v >= 0 else theme.DANGER for v in vals]
    maxabs = max((abs(v) for v in vals), default=0.0)
    rng = maxabs * 1.28 if maxabs >= 1 else 500.0           # symmetric range keeps 0 centred
    fig = go.Figure(go.Bar(
        x=vals, y=order, orientation="h",
        marker=dict(color=colors, cornerradius=6, line=dict(color="white", width=1)),
        text=[(f"Rs.{v:+,.0f}" if abs(v) >= 1 else "") for v in vals], textposition="outside",
        textfont=dict(size=11, color="#0f172a"), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Contribution: Rs.%{x:+,.0f}/t<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color="#cbd5e1", width=1.5))
    fig.update_layout(height=height, margin=dict(l=10, r=40, t=8, b=8),
                      plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="sans-serif", size=12, color="#334155"), showlegend=False)
    fig.update_xaxes(title_text="Contribution to price (Rs./t)", tickprefix="Rs.",
                     tickformat=",.0f", gridcolor="#f1f5f9", zeroline=False, range=[-rng, rng])
    fig.update_yaxes(title_text="", automargin=True)
    return fig


def _changes_table(drivers, key, contrib_rs, height):
    """Driver-by-driver 'table of changes': the shock applied and its ₹ effect."""
    ss = st.session_state
    rows = []
    for i, (nm, base, _beta, unit) in enumerate(drivers):
        pct = ss.get(f"shock_{key}_{i}", 0.0)
        shock = f"{pct:+.2f}%"
        if pct:
            dabs = base * pct / 100.0
            shock += f"  ({'+' if dabs >= 0 else '−'}{_fmt_val(abs(dabs), unit)})"
        rows.append({"Driver": nm, "Shock applied": shock,
                     "Baseline → shocked": f"{_fmt_val(base, unit)} → {_fmt_val(base * (1 + pct / 100.0), unit)}",
                     "Contribution (Rs./t)": round(contrib_rs[nm], 0)})
    df = (pd.DataFrame(rows)
          .sort_values("Contribution (Rs./t)", key=lambda s: s.abs(), ascending=False))
    st.dataframe(df, width="stretch", hide_index=True, height=height, column_config={
        "Contribution (Rs./t)": st.column_config.NumberColumn("Contribution (Rs./t)", format="Rs.%+.0f"),
    })


# -----------------------------------------------------------------------------
# Shared shock state, formatting + the reusable per-driver control
# -----------------------------------------------------------------------------
# Canonical shock lives in st.session_state[f"shock_{key}_{i}"] as a % in [-20, 20].
# Both input modes (Sliders, Table) read and write it, so a shock set in one mode
# shows in the other. Recompute is LIVE (cheap: cached Ridge fit + a vectorised
# dot·exp over ≤10 drivers), so there is no "Apply" gate.
_ZERO_SNAP = 0.75      # |shock| within this snaps to exactly 0 (neutral / no change)


def _snap(v):
    """Clamp to [-20, 20] and snap the neutral zone to exactly 0."""
    v = max(-20.0, min(20.0, float(v)))
    return 0.0 if abs(v) <= _ZERO_SNAP else v


def _cb_slider(did):
    st.session_state[f"shock_{did}"] = _snap(st.session_state[f"sl_{did}"])


def _cb_number(did):
    st.session_state[f"shock_{did}"] = _snap(st.session_state[f"num_{did}"])


def _cb_preset(did, val):
    st.session_state[f"shock_{did}"] = _snap(val)


def _cur(unit):
    """Currency symbol implied by a unit string ('' for quantity drivers)."""
    u = (unit or "").lower()
    if "₹" in unit or u.startswith("rs") or "inr" in u:
        return "₹"
    if "$" in unit or "usd" in u:
        return "$"
    if "€" in unit or "eur" in u:
        return "€"
    return ""


def _indian(n):
    """Integer with Indian digit grouping (e.g. 12,34,567), sign preserved."""
    n = int(round(n))
    neg, s = n < 0, str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if neg else "") + s


def _fmt_val(v, unit):
    """Format a value with the right grouping/symbol for its unit."""
    cur = _cur(unit)
    if cur == "₹":
        return "₹" + _indian(v)
    if cur:                                    # $ or €
        return f"{cur}{v:,.0f}"
    suffix = (unit or "").strip()              # quantity: Mt / kt / MT
    return (f"{v:,.2f} {suffix}" if abs(v) < 100 else f"{v:,.0f} {suffix}").strip()


def _result_html(baseline, pct, unit):
    """'baseline → shocked (Δ abs, Δ%)' with a colour-coded delta."""
    shocked = baseline * (1 + pct / 100.0)
    dabs = shocked - baseline
    if pct == 0:
        return f"<div class='knob-res muted'>{_fmt_val(baseline, unit)} · no change</div>"
    cls = "up" if pct > 0 else "down"
    sign = "+" if dabs >= 0 else "−"
    return (f"<div class='knob-res {cls}'>{_fmt_val(baseline, unit)}"
            f"<span class='arw'>→</span><b>{_fmt_val(shocked, unit)}</b> "
            f"<span class='dl'>({sign}{_fmt_val(abs(dabs), unit)}, {pct:+.1f}%)</span></div>")


def driver_control(driver_id, label, baseline, unit):
    """One driver card: coupled slider + number_input (two-way synced via the
    shared shock state), a tick scale, ±20/±10/0 presets, a baseline→shocked
    readout, and a per-driver reset. Adding a driver is a single call."""
    ss = st.session_state
    sk = f"shock_{driver_id}"
    ss.setdefault(sk, 0.0)
    # push the canonical value into both widgets BEFORE they render (this is what
    # keeps slider⇄number in sync and carries shocks across modes/presets/resets)
    ss[f"sl_{driver_id}"] = ss[sk]
    ss[f"num_{driver_id}"] = ss[sk]

    with st.container(border=True):
        st.markdown(f"<div class='knob-label'>{label}</div>", unsafe_allow_html=True)
        c_sl, c_num = st.columns([2, 1], vertical_alignment="center")
        with c_sl:
            st.slider(label, -20.0, 20.0, step=0.5, key=f"sl_{driver_id}",
                      on_change=_cb_slider, args=(driver_id,), label_visibility="collapsed")
            st.markdown("<div class='knob-ticks'><span>-20</span><span>-10</span>"
                        "<span>0</span><span>+10</span><span>+20</span></div>", unsafe_allow_html=True)
        with c_num:
            st.number_input(label, -20.0, 20.0, step=0.5, key=f"num_{driver_id}", format="%.1f",
                            on_change=_cb_number, args=(driver_id,), label_visibility="collapsed")
        for c, val in zip(st.columns(5), (-20, -10, 0, 10, 20)):
            c.button("0" if val == 0 else f"{val:+d}", key=f"pre_{driver_id}_{val}",
                     on_click=_cb_preset, args=(driver_id, float(val)), width="stretch")
        st.markdown(_result_html(baseline, ss[sk], unit), unsafe_allow_html=True)
        st.button("↺ Reset", key=f"rst_{driver_id}", on_click=_cb_preset,
                  args=(driver_id, 0.0), width="stretch")


def _model_note(spec):
    if spec.get("r2") is None:      # HRC — live weekly fit
        return (f"<div class='bm-modelnote'><b>Model:</b> {spec['model']}<br>"
                f"<b>Sensitivities:</b> re-fit live whenever the price sheet updates<br>"
                f"<b>Trained on:</b> {spec['period']}</div>")
    return (f"<div class='bm-modelnote'><b>Model:</b> {spec['model']}<br>"
            f"<b>Backtest:</b> OOS R² {spec['r2']:.2f} · RMSE {spec['rmse_pct']:.2f}% "
            f"(≈Rs.{spec['rmse_rs']:,}/t)<br>"
            f"<b>Fitted on:</b> {spec['n_obs']} monthly moves, {spec['period']}</div>")


# -----------------------------------------------------------------------------
# One product view
# -----------------------------------------------------------------------------
# @st.fragment: a shock change (slider / number ±, preset, reset) reruns ONLY this
# product view — not the whole Calculators page — so the +/- steppers stay responsive
# instead of freezing / dropping rapid clicks on a full-page rerun.
@st.fragment
def _render_product(spec, key):
    drivers = spec["drivers"]
    n = len(drivers)
    names = [d[0] for d in drivers]

    ss = st.session_state
    # canonical shock state (shared by BOTH input modes): one % per driver, in
    # session keyed by driver id so the rest of the model can read it.
    for i in range(n):
        ss.setdefault(f"shock_{key}_{i}", 0.0)
    ss.setdefault(f"sens_sync_{key}", 0)     # bumped on mode/toggle switch -> reseeds the table

    def _reset_all():                         # single global "Reset all shocks"
        for i in range(n):
            ss[f"shock_{key}_{i}"] = 0.0
        ss[f"sens_sync_{key}"] += 1

    st.caption(spec["full_name"])

    # --- top: contribution view (left) + controls & KPI cards (right) ---
    col_main, col_side = st.columns([2.5, 1], gap="large")
    with col_main:
        _sec("Driver contribution to the predicted move", theme.icon("trending"))
        tab_g, tab_t = st.tabs(["Graph", "Table of changes"])
        with tab_g:
            graph_ph = st.empty()
        with tab_t:
            tbl_ph = st.empty()
    with col_side:
        theme.section_title("Scenario controls", theme.icon("gauge"))
        current = st.number_input(f"Current {spec['label']} price (Rs./t)", value=float(spec["current"]),
                                  step=250.0, min_value=0.0, key=f"sens_cur_{key}")
        kpi_ph = st.empty()      # predicted-move cards sit right under the current price
        st.button("↺ Reset all shocks", key=f"sens_reset_{key}", on_click=_reset_all, width="stretch",
                  help="Clear every driver shock back to zero.")
        st.markdown(_model_note(spec), unsafe_allow_html=True)

    # --- input editors: two modes, one shared shock state ---
    _sec("Market shocks by driver", theme.icon("factory"))
    mode = st.segmented_control("Input mode", ["Sliders", "Table"], default="Sliders",
                                key=f"sens_mode_{key}", label_visibility="collapsed") or "Sliders"
    prevk = f"sens_modeprev_{key}"
    if ss.get(prevk) not in (None, mode):     # switched modes -> reseed the table from canonical
        ss[f"sens_sync_{key}"] += 1
    ss[prevk] = mode

    if mode == "Sliders":
        per = 4                                # 4-up grid; each card holds the full control set
        with st.container(key="sens_knobwrap"):
            for r0 in range(0, n, per):
                cols = st.columns(per)
                for j in range(per):
                    i = r0 + j
                    if i >= n:
                        continue               # leave the trailing cell empty (keeps widths equal)
                    with cols[j]:
                        driver_control(f"{key}_{i}", names[i], drivers[i][1], drivers[i][3])
        st.caption("Drag a knob or type a %, or use the ±20 / ±10 / 0 presets. Values within ±0.75% snap "
                   "to no-change. Switch to **Table** to type exact values or absolute unit changes — "
                   "shocks carry across both modes.")
    else:
        pct_mode = (st.segmented_control("Enter shocks as", ["% shock", "Absolute change"],
                    default="% shock", key=f"sens_enter_{key}") or "% shock") == "% shock"
        if ss.get(f"sens_enterprev_{key}") not in (None, pct_mode):     # toggle flip -> reseed editor
            ss[f"sens_sync_{key}"] += 1
        ss[f"sens_enterprev_{key}"] = pct_mode

        editcol = "Shock %" if pct_mode else "Δ (native unit)"
        rows = []
        for i, (nm, b0, _beta, unit) in enumerate(drivers):
            pct = ss[f"shock_{key}_{i}"]
            shocked = b0 * (1 + pct / 100.0)
            dabs = shocked - b0
            rows.append({
                "Driver": nm,
                "Baseline": _fmt_val(b0, unit),
                editcol: float(pct if pct_mode else round(dabs, 2)),
                "Shocked": _fmt_val(shocked, unit),
                "Result": "no change" if pct == 0 else
                          f"{'+' if dabs >= 0 else '−'}{_fmt_val(abs(dabs), unit)}  ({pct:+.1f}%)",
            })
        order = ["Driver", "Baseline", editcol, "Shocked", "Result"]
        colcfg = {
            "Driver": st.column_config.TextColumn("Driver", disabled=True, width="large"),
            "Baseline": st.column_config.TextColumn("Baseline", disabled=True),
            "Shocked": st.column_config.TextColumn("Shocked value", disabled=True),
            "Result": st.column_config.TextColumn("Δ", disabled=True),
            editcol: (st.column_config.NumberColumn("Shock %", format="%.1f", step=0.5,
                        help="Percentage change (−20 to +20).") if pct_mode else
                      st.column_config.NumberColumn("Δ (native unit)", format="%.2f", step=1.0,
                        help="Absolute change in the driver's own unit — converted to % via the baseline.")),
        }
        tok = f"{ss[f'sens_sync_{key}']}_{'p' if pct_mode else 'a'}"
        edited = st.data_editor(pd.DataFrame(rows)[order], key=f"tbl_{key}_{tok}",
                                num_rows="fixed", hide_index=True, width="stretch", column_config=colcfg)
        for i in range(n):
            b0 = drivers[i][1]
            if pct_mode:
                pct = float(edited.iloc[i]["Shock %"])
            else:
                dabs = float(edited.iloc[i]["Δ (native unit)"])
                pct = (dabs / b0 * 100.0) if b0 else 0.0
            ss[f"shock_{key}_{i}"] = _snap(pct)
        st.caption("Toggle **% shock** / **Absolute change** to type either a percentage or a change in the "
                   "driver's own unit (₹ / $ / € / Mt / kt) — converted via the baseline. Values within ±0.75% "
                   "snap to no-change. Switch to **Sliders** for quick what-ifs — shocks carry across modes.")

    # --- compute (shared engine) — LIVE on every change ---
    eff = {names[i]: ss[f"shock_{key}_{i}"] / 100.0 for i in range(n)}
    impact, final, _cpct, crs = eng.compute(current, drivers, eff)
    change = final - current

    # --- fill the persistent chart / table-of-changes (matched heights) ---
    vh = _view_height(n)
    with graph_ph.container():
        try:
            st.plotly_chart(_contrib_figure(names, crs, vh), width="stretch",
                            config={"displayModeBar": False})
        except Exception:
            st.bar_chart(pd.DataFrame({"Rs./t": crs}))
        st.caption("Each bar = current price × driver shock. Green pushes the price up, red pulls it down.")
    with tbl_ph.container():
        _changes_table(drivers, key, crs, vh)

    # --- KPI cards (modular, forecast-page style) under the current price ---
    cards = [
        ("Predicted change", f"{impact * 100:+.2f}%", "log-return applied", theme.icon("trending")),
        ("Forecasted price", f"Rs.{final:,.0f}", f"from Rs.{current:,.0f}", theme.icon("rupee")),
        ("Absolute change", f"Rs.{change:+,.0f}", "per tonne", theme.icon("gauge")),
    ]
    kpi_ph.markdown("<div class='bm-vcards bm-vcards-sm'>"
                    + "".join(theme.kpi_card(t, v, s, ic) for t, v, s, ic in cards)
                    + "</div>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Methodology (landed-cost style) + glossary — shared across products
# -----------------------------------------------------------------------------
def _methodology_infographic(product_label=None):
    _sec("How the sensitivity prediction is built", theme.icon("notes"))
    st.markdown(
        "Each product is a **stateless single-row model**: the predicted move depends only on the "
        "driver shocks you enter — no history, momentum or market-state terms. Every driver carries a "
        "fixed **sensitivity** (how much the product moves per 1% move in that driver), estimated once "
        "on years of month-on-month price changes. Your shocks are weighted by that sensitivity, summed, "
        "and applied to the current price."
    )

    st.write("")
    _sec("The estimation equation", theme.icon("notes"))
    st.markdown(
        "The fixed per-driver sensitivities (β) are the coefficients of a **log-log OLS regression** "
        "estimated once per product on month-on-month data — so each β reads directly as an elasticity "
        "(% move in the product per 1% move in the driver). The general form, one fit per product:"
    )
    eqs = [
        ("HRC",      "log(HRC<sub>t</sub>)"),
        ("HR Plate", "log(HRPlate<sub>t</sub>)"),
        ("Rebar",    "log(Rebar<sub>t</sub>)"),
    ]
    if product_label:                          # show only the selected product's equation
        eqs = [e for e in eqs if e[0] == product_label] or eqs
    rows = "".join(
        f"<div class='bm-eqrow'><span class='bm-eqtag'>{tag}</span>"
        f"<span class='bm-eqbody'>{lhs} = &alpha; + &beta;<sub>1</sub>log(IO<sub>t</sub>) "
        "+ &beta;<sub>2</sub>log(Coal<sub>t</sub>) + &beta;<sub>3</sub>log(Prod<sub>t</sub>) "
        "+ &beta;<sub>4</sub>log(EXIM<sub>t</sub>) + &epsilon;<sub>t</sub></span></div>"
        for tag, lhs in eqs
    )
    st.markdown("<div class='bm-eqset'>" + rows + "</div>", unsafe_allow_html=True)
    st.caption("IO = iron ore · Coal = coking coal · Prod = production/supply · EXIM = export–import parity. "
               "Actual products use an expanded driver set; this is the shared functional form.")

    def _chips(items):
        return "".join(
            f"<div class='bm-chip'><span class='ic'>{theme.icon(ic, 15)}</span>{label}</div>"
            for ic, label in items
        )
    engine = (
        "<div class='bm-engine'>"
        "<div class='bm-engine-col bm-engine-in'><div class='bm-engine-h'>Inputs</div>"
        + _chips([("factory", "Driver shock: % or absolute"),
                  ("gauge",   "Fixed per-driver baselines"),
                  ("rupee",   "Current product price")]) +
        "</div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-core'>"
        f"<span class='ic'>{theme.icon('calculator', 26)}</span>"
        "<div style='margin:0 0 6px;font-size:16px;font-weight:700;color:#fff;'>Sensitivity Engine</div>"
        "<p>shock &rarr; to % &rarr; weight &rarr; sum &rarr; e<sup>Σ</sup>, per driver.</p></div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-col bm-engine-out'><div class='bm-engine-h'>Outputs</div>"
        + _chips([("trending", "Predicted % move"),
                  ("rupee",    "Forecasted price Rs./t"),
                  ("target",   "Driver-by-driver split")]) +
        "</div></div>"
    )
    st.markdown(engine, unsafe_allow_html=True)

    st.write("")
    _sec("The equation pipeline", theme.icon("notes"))
    steps = [
        ("factory",    "Shock",       "Enter a % or an absolute change.",
         "shock = Δ% or Δunit"),
        ("gauge",      "To percent",  "Absolute converts via the baseline.",
         "shock% = Δunit &divide; <b>Base</b>"),
        ("calculator", "Weight",      "Scale by the driver's sensitivity.",
         "c = eff% &times; <b>sensitivity</b>"),
        ("notes",      "Sum",         "Add every driver's share.",
         "impact = &Sigma; c"),
        ("rupee",      "Apply",       "Compound onto the current price.",
         "Price = Current &times; e<sup>impact</sup>"),
        ("trending",   "Read",        "Direction and magnitude.",
         "impact &gt; 0 &rArr; price up"),
    ]
    cells = []
    for i, (ic, title, desc, eq) in enumerate(steps, 1):
        cells.append(
            "<div class='bm-flow-step'>"
            f"<div class='num'>{i}</div>"
            f"<div class='ic'>{theme.icon(ic, 20)}</div>"
            f"<div class='bm-flow-t' role='heading' aria-level='4'>{title}</div>"
            f"<p>{desc}</p>"
            f"<div class='bm-eq'>{eq}</div></div>"
        )
        if i < len(steps):
            cells.append("<div class='bm-flow-arrow'>&rarr;</div>")
    st.markdown("<div class='bm-flow'>" + "".join(cells) + "</div>", unsafe_allow_html=True)


def _glossary():
    _sec("Glossary of terms", theme.icon("notes"))
    terms = [
        ("Sens.", "Sensitivity", "How much the product moves per 1% move in a driver — fixed per model, not shown."),
        ("shock", "Driver shock", "The % move applied to a driver — typed directly, or an absolute change converted via its fixed baseline."),
        ("Σ", "Predicted move", "Sum of every driver's contribution (shock × sensitivity) — the total log-return."),
        ("e^Σ", "Compounding", "The summed move is applied as a growth factor: price × e^Σ."),
        ("R²", "Out-of-sample fit", "Share of real price moves the model explained on data it never saw."),
        ("RMSE", "Typical error", "Average size of the model's one-period miss, in % and Rs./t."),
    ]
    html = "<div class='bm-factor-grid'>" + "".join(
        f"<div class='bm-factor'><div class='ic' style='font-weight:800;font-size:12px;'>{abbr}</div>"
        f"<div><h5>{full}</h5><p>{desc}</p></div></div>"
        for abbr, full, desc in terms
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='bm-calc-head'>"
        f"<div class='bm-calc-title'>{theme.icon('gauge', 30)} Price Sensitivity Scenario Simulation</div>"
        "<div class='bm-calc-sub'>What-if driver shocks &middot; predicted price move by product</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # fixed-sensitivity products (HR Plate, Rebar) + the live-fit HRC spec
    specs = [_hrc_spec(), eng.MODELS["HR Plate"], eng.MODELS["Rebar"]]
    labels = [s["label"] for s in specs]

    # product tab-strip — same widget as the forecast page's product selector
    picked = st.segmented_control("Product", labels, default=labels[0], key="sens_prod",
                                  label_visibility="collapsed")
    spec = next((s for s in specs if s["label"] == picked), specs[0])
    _render_product(spec, key=spec["label"].lower().replace(" ", "_"))

    st.divider()
    _methodology_infographic(spec["label"])
    _glossary()
