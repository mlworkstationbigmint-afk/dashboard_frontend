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

/* ---- knob cards (Sliders mode) — soft neumorphic panels, all identical size ---- */
.st-key-sens_knobwrap [data-testid="stHorizontalBlock"] { gap: 0.85rem !important; align-items: stretch; }
.st-key-sens_knobwrap [data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #edf1f7 !important; border-radius: 16px !important;
    background: linear-gradient(158deg, #ffffff 0%, #f4f7fb 100%) !important;
    box-shadow: 0 6px 16px rgba(15,23,42,.06), inset 0 1px 0 #ffffff !important;
    padding: 13px 15px 15px !important; min-height: 132px; height: 100%;
    display: flex; flex-direction: column; justify-content: space-between;
    transition: box-shadow .2s ease, transform .2s ease; }
.st-key-sens_knobwrap [data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 12px 26px rgba(2,76,161,.13), inset 0 1px 0 #ffffff !important;
    transform: translateY(-2px); }
/* driver name = clean centred caption (like LEVEL / WIDTH on the reference) */
.st-key-sens_knobwrap [data-testid="stSlider"] [data-testid="stWidgetLabel"] { min-height: 34px; }
.st-key-sens_knobwrap [data-testid="stSlider"] [data-testid="stWidgetLabel"] p {
    font-size: 11.5px !important; font-weight: 700 !important; color: var(--bm-primary-dark) !important;
    text-align: center; line-height: 1.25; letter-spacing: .3px; text-transform: uppercase; }
/* the current-value bubble above the thumb — make it a crisp accent pill */
.st-key-sens_knobwrap [data-testid="stSliderThumbValue"] {
    font-size: 12px !important; font-weight: 700 !important; color: var(--bm-primary-dark) !important; }
/* de-clutter: hide the -20 / +20 end ticks (a caption explains the range instead) */
.st-key-sens_knobwrap [data-testid="stSliderTickBar"] { display: none !important; }
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


def _hrc_spec():
    """Build the HRC product spec from the LIVE Ridge fit (sensitivities =
    coefficients). No per-driver base prices ship with the model, so HRC takes
    % shocks only."""
    model, columns = load_model()
    drivers = []
    for col, beta in zip(columns, model.coef_):
        raw = col.split("_lag")[0]
        drivers.append((_HRC_SHORT.get(raw, raw[:34]), 0.0, float(beta), "% chg"))
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


def _changes_table(drivers, dpct, dunit, base, contrib_rs, has_base, height):
    """Driver-by-driver 'table of changes': the shock applied and its ₹ effect."""
    rows = []
    for i, (nm, _b0, _beta, unit) in enumerate(drivers):
        eff_pct = dpct[i] + ((dunit[i] / base[i] * 100.0) if (has_base and base[i]) else 0.0)
        shock = f"{eff_pct:+.2f}%"
        if has_base and dunit[i]:
            sign = "+" if dunit[i] >= 0 else "−"
            shock += f"  ({sign}{abs(dunit[i]):,.0f} {unit})"
        rows.append({"Driver": nm, "Shock applied": shock,
                     "Contribution (Rs./t)": round(contrib_rs[nm], 0)})
    df = (pd.DataFrame(rows)
          .sort_values("Contribution (Rs./t)", key=lambda s: s.abs(), ascending=False))
    st.dataframe(df, width="stretch", hide_index=True, height=height, column_config={
        "Contribution (Rs./t)": st.column_config.NumberColumn("Contribution (Rs./t)", format="Rs.%+.0f"),
    })


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
def _render_product(spec, key):
    drivers = spec["drivers"]
    n = len(drivers)
    names = [d[0] for d in drivers]
    has_base = any(d[1] for d in drivers)

    ss = st.session_state
    # canonical shock state (shared by BOTH input modes): per-driver Δ%, Δ₹, base
    ss.setdefault(f"sens_dpct_{key}", {i: 0.0 for i in range(n)})
    ss.setdefault(f"sens_dunit_{key}", {i: 0.0 for i in range(n)})
    ss.setdefault(f"sens_base_{key}", {i: float(drivers[i][1]) for i in range(n)})
    ss.setdefault(f"sens_ver_{key}", 0)      # bumped by Reset -> remounts editors
    ss.setdefault(f"sens_sync_{key}", 0)     # bumped on mode switch -> reseeds from canonical
    dpct, dunit, base = (ss[f"sens_dpct_{key}"], ss[f"sens_dunit_{key}"], ss[f"sens_base_{key}"])

    def _reset():
        for i in range(n):
            dpct[i] = 0.0
            dunit[i] = 0.0
            base[i] = float(drivers[i][1])
        ss[f"sens_ver_{key}"] += 1

    def _eff_pct(i):
        return dpct[i] + ((dunit[i] / base[i] * 100.0) if (has_base and base[i]) else 0.0)

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
        st.button("↺ Reset shocks", key=f"sens_reset_{key}", on_click=_reset, width="stretch",
                  help="Clear every driver shock back to zero.")
        st.markdown(_model_note(spec), unsafe_allow_html=True)

    # --- input editors: two modes, one shared shock state ---
    _sec("Market shocks by driver", theme.icon("factory"))
    mode = st.segmented_control("Input mode", ["Sliders", "Table"], default="Sliders",
                                key=f"sens_mode_{key}", label_visibility="collapsed") or "Sliders"
    prevk = f"sens_modeprev_{key}"
    if ss.get(prevk) not in (None, mode):     # switched modes -> reseed the new editor from canonical
        ss[f"sens_sync_{key}"] += 1
    ss[prevk] = mode
    tok = f"{ss[f'sens_ver_{key}']}_{ss[f'sens_sync_{key}']}"

    if mode == "Sliders":
        per = 4                                    # fixed grid -> every knob card is the same width
        with st.container(key="sens_knobwrap"):
            for r0 in range(0, n, per):
                cols = st.columns(per)
                for j in range(per):
                    i = r0 + j
                    if i >= n:
                        continue                   # leave the trailing cells empty (keeps widths equal)
                    with cols[j], st.container(border=True):
                        seed = max(-20.0, min(20.0, round(_eff_pct(i), 2)))   # knobs cap at ±20%
                        v = st.slider(names[i], -20.0, 20.0, value=seed, step=0.5,
                                      key=f"sl_{key}_{i}_{tok}")
                    dpct[i] = v      # a knob expresses the whole shock as a %, so the ₹ part folds in
                    dunit[i] = 0.0
        st.caption("Drag a knob to shock a driver by ±20%. Switch to **Table** to type exact values "
                   "or enter absolute ₹ / unit changes — your shocks carry across both modes.")
    else:
        rows = []
        for i, (nm, _b0, _beta, unit) in enumerate(drivers):
            r = {"Driver": nm}
            if has_base:
                r["Base price"] = float(base[i])
                r["Δ (₹ / unit)"] = float(dunit[i])
            r["Δ %"] = float(dpct[i])
            rows.append(r)
        cols = ["Driver"] + (["Base price"] if has_base else []) + ["Δ %"] \
            + (["Δ (₹ / unit)"] if has_base else [])
        colcfg = {
            "Driver": st.column_config.TextColumn("Driver", disabled=True, width="large"),
            "Δ %": st.column_config.NumberColumn("Δ %", format="%.2f", step=0.5,
                help="Percentage change to apply to this driver."),
        }
        if has_base:
            colcfg["Base price"] = st.column_config.NumberColumn("Base price", format="%.2f", step=1.0,
                help="Reference level used to convert a ₹ / unit change into a %. Editable.")
            colcfg["Δ (₹ / unit)"] = st.column_config.NumberColumn("Δ (₹ / unit)", format="%.2f", step=1.0,
                help="Absolute change in the driver's own unit (Rs./t, USD/t, MT).")
        edited = st.data_editor(pd.DataFrame(rows)[cols], key=f"tbl_{key}_{tok}",
                                num_rows="fixed", hide_index=True, width="stretch", column_config=colcfg)
        for i in range(n):
            dpct[i] = float(edited.iloc[i]["Δ %"])
            if has_base:
                base[i] = float(edited.iloc[i]["Base price"])
                dunit[i] = float(edited.iloc[i]["Δ (₹ / unit)"])
        st.caption("Enter a shock as **Δ %** and/or an absolute **Δ (₹ / unit)** — they add. "
                   "₹ inputs convert to % via the editable **Base price**. Switch to **Sliders** for quick "
                   "what-ifs — your shocks carry across both modes.")

    # --- compute (shared engine) ---
    eff = {names[i]: eng.effective_frac(dpct[i], dunit[i] if has_base else 0.0,
                                        base[i] if has_base else 0.0) for i in range(n)}
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
        _changes_table(drivers, dpct, dunit, base, crs, has_base, vh)

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
def _methodology_infographic():
    _sec("How the sensitivity prediction is built", theme.icon("notes"))
    st.markdown(
        "Each product is a **stateless single-row model**: the predicted move depends only on the "
        "driver shocks you enter — no history, momentum or market-state terms. Every driver carries a "
        "fixed **sensitivity** (how much the product moves per 1% move in that driver), estimated once "
        "on years of month-on-month price changes. Your shocks are weighted by that sensitivity, summed, "
        "and applied to the current price."
    )

    def _chips(items):
        return "".join(
            f"<div class='bm-chip'><span class='ic'>{theme.icon(ic, 15)}</span>{label}</div>"
            for ic, label in items
        )
    engine = (
        "<div class='bm-engine'>"
        "<div class='bm-engine-col bm-engine-in'><div class='bm-engine-h'>Inputs</div>"
        + _chips([("factory", "Driver shock: Δ% or Δ₹"),
                  ("gauge",   "Editable base prices"),
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
        ("factory",    "Shock",       "Enter Δ% or Δ₹ per driver.",
         "shock = Δ% or Δ₹"),
        ("gauge",      "To percent",  "₹ converts via base price.",
         "eff% = Δ% + Δ₹ &divide; <b>Base</b>"),
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
            f"<div class='bm-flow-t'>{title}</div>"
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
        ("eff%", "Effective % change", "A driver's shock as a %: Δ% plus any Δ₹ divided by its base price."),
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
    _methodology_infographic()
    _glossary()
