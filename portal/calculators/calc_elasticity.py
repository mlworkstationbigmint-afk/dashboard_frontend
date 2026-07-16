# =============================================================================
# Price Sensitivity calculator — HRC · HR Plate · Rebar
# =============================================================================
# Rebuilt UI (product tab-strip like the forecast page, editable driver table,
# contribution chart, infographic methodology) — themed to match the Landed Cost
# and Cost Head calculators.
#
# The ENGINE is unchanged: predicted move = Σ(effective % change × β), price =
# current × e^Σ. HRC keeps its live Ridge fit (load_model below); HR Plate and
# Rebar use the fixed-β models baked into engine_sensitivity.py (from the
# backtested REBAR__3.XLS / HRPLAT_2.XLS sheets). Shared maths: engine.compute().
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
/* headline banner (predicted price) */
.kpi-banner { border-radius: 12px; padding: 13px 18px; margin: 2px 0 4px; font-size: 16px; font-weight: 700;
    color: #fff; background: linear-gradient(120deg, var(--bm-primary), var(--bm-primary-dark));
    box-shadow: 0 4px 16px rgba(2,76,161,.18); }
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
    """Build the HRC product spec from the LIVE Ridge fit (β = coefficients). No
    per-driver base prices ship with the model, so HRC takes % shocks only."""
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
# Product rendering
# -----------------------------------------------------------------------------
def _seed_df(drivers, has_base):
    rows = []
    for name, base, beta, _unit in drivers:
        r = {"Driver": name, "β (% per 1%)": round(beta, 4)}
        if has_base:
            r["Base price"] = float(base)
            r["Δ (₹ / unit)"] = 0.0
        r["Δ %"] = 0.0
        rows.append(r)
    cols = ["Driver", "β (% per 1%)"] + (["Base price"] if has_base else []) + ["Δ %"] \
        + (["Δ (₹ / unit)"] if has_base else [])
    return pd.DataFrame(rows)[cols]


def _contrib_figure(names, contrib_rs):
    """Horizontal diverging bars — each driver's ₹/t contribution to the move."""
    import plotly.graph_objects as go
    order = sorted(names, key=lambda n: contrib_rs[n])      # most negative at bottom
    vals = [contrib_rs[n] for n in order]
    colors = [theme.SUCCESS if v >= 0 else theme.DANGER for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=order, orientation="h",
        marker=dict(color=colors, cornerradius=6, line=dict(color="white", width=1)),
        text=[(f"Rs.{v:+,.0f}" if abs(v) >= 1 else "") for v in vals], textposition="outside",
        textfont=dict(size=11, color="#0f172a"), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Contribution: Rs.%{x:+,.0f}/t<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color="#cbd5e1", width=1.5))
    fig.update_layout(height=max(240, 40 * len(order)), margin=dict(l=10, r=40, t=8, b=8),
                      plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="sans-serif", size=12, color="#334155"), showlegend=False)
    fig.update_xaxes(title_text="Contribution to price (Rs./t)", tickprefix="Rs.",
                     tickformat=",.0f", gridcolor="#f1f5f9", zeroline=False)
    fig.update_yaxes(title_text="", automargin=True)
    return fig


def _model_note(spec):
    if spec.get("r2") is None:      # HRC — live weekly fit
        return (f"<div class='bm-modelnote'><b>Model:</b> {spec['model']}<br>"
                f"<b>Coefficients:</b> re-fit live whenever the price sheet updates<br>"
                f"<b>Trained on:</b> {spec['period']}</div>")
    return (f"<div class='bm-modelnote'><b>Model:</b> {spec['model']}<br>"
            f"<b>Backtest:</b> OOS R² {spec['r2']:.2f} · RMSE {spec['rmse_pct']:.2f}% "
            f"(≈Rs.{spec['rmse_rs']:,}/t)<br>"
            f"<b>Fitted on:</b> {spec['n_obs']} monthly moves, {spec['period']}</div>")


def _render_product(spec, key):
    drivers = spec["drivers"]
    names = [d[0] for d in drivers]
    has_base = any(d[1] for d in drivers)

    verkey = f"sens_ver_{key}"
    st.session_state.setdefault(verkey, 0)

    def _reset():
        st.session_state[verkey] = st.session_state.get(verkey, 0) + 1

    st.caption(spec["full_name"])
    banner_ph = st.empty()
    kpi_ph = st.empty()

    col_chart, col_ctrl = st.columns([2.5, 1], gap="large", vertical_alignment="center")
    with col_ctrl:
        theme.section_title("Scenario controls", theme.icon("gauge"))
        current = st.number_input(f"Current {spec['label']} price (Rs./t)", value=float(spec["current"]),
                                  step=250.0, min_value=0.0, key=f"sens_cur_{key}")
        st.button("↺ Reset shocks", key=f"sens_reset_{key}", on_click=_reset, width="stretch",
                  help="Clear every driver shock back to zero.")
        st.markdown(_model_note(spec), unsafe_allow_html=True)
    with col_chart:
        _sec("Driver contribution to the predicted move", theme.icon("trending"))
        chart_ph = st.empty()

    # --- editable driver table: enter a shock as Δ% and/or Δ₹ per driver ---
    _sec("Market shocks by driver", theme.icon("factory"))
    ver = st.session_state[verkey]
    colcfg = {
        "Driver": st.column_config.TextColumn("Driver", disabled=True, width="large"),
        "β (% per 1%)": st.column_config.NumberColumn(
            "β (% per 1%)", disabled=True, format="%.4f",
            help="Sensitivity: predicted % move in the product per 1% move in this driver."),
        "Δ %": st.column_config.NumberColumn("Δ %", format="%.2f", step=0.5,
            help="Percentage change you want to apply to this driver."),
    }
    if has_base:
        colcfg["Base price"] = st.column_config.NumberColumn("Base price", format="%.2f", step=1.0,
            help="Reference level used to convert a ₹/unit change into a %. Editable.")
        colcfg["Δ (₹ / unit)"] = st.column_config.NumberColumn("Δ (₹ / unit)", format="%.2f", step=1.0,
            help="Absolute change in the driver's own unit (Rs./t, USD/t, MT). Converted to % via the base price.")
    edited = st.data_editor(_seed_df(drivers, has_base), key=f"sens_tbl_{key}_{ver}",
                            num_rows="fixed", hide_index=True, width="stretch", column_config=colcfg)
    st.caption("Enter a shock as **Δ %** or as an absolute **Δ (₹ / unit)** — or both (they add). "
               "₹ inputs convert to % using the editable **Base price**. β is fixed by the model. "
               "**Reset** clears every shock.")

    # --- compute (shared engine) ---
    eff = {}
    for i, (name, base0, _beta, _unit) in enumerate(drivers):
        row = edited.iloc[i]
        dp = float(row["Δ %"])
        du = float(row["Δ (₹ / unit)"]) if has_base else 0.0
        base = float(row["Base price"]) if has_base else base0
        eff[name] = eng.effective_frac(dp, du, base)
    impact, final, _cpct, crs = eng.compute(current, drivers, eff)
    change = final - current

    # --- chart ---
    with chart_ph.container():
        if any(abs(v) >= 1 for v in crs.values()):
            try:
                st.plotly_chart(_contrib_figure(names, crs), width="stretch",
                                config={"displayModeBar": False})
            except Exception:
                st.bar_chart(pd.DataFrame({"Rs./t": crs}))
            st.caption("Each bar = current price × driver shock × β. "
                       "Green pushes the price up, red pulls it down.")
        else:
            st.info("Enter a shock in the table below to see each driver's contribution.",
                    icon=":material/info:")

    # --- headline + KPIs ---
    if abs(impact) < 1e-9:
        banner_ph.markdown(
            f"<div class='kpi-banner'>Predicted {spec['label']} price: Rs.{final:,.0f}/t — "
            f"unchanged (no shocks entered)</div>", unsafe_allow_html=True)
    else:
        arrow = "▲ rise" if change > 0 else "▼ fall"
        banner_ph.markdown(
            f"<div class='kpi-banner'>Predicted {spec['label']} price: Rs.{final:,.0f}/t — "
            f"a {abs(impact) * 100:.2f}% {arrow} ({'+' if change >= 0 else '−'}Rs.{abs(change):,.0f}/t) "
            f"from Rs.{current:,.0f}/t</div>", unsafe_allow_html=True)
    with kpi_ph.container():
        m1, m2, m3 = st.columns(3)
        m1.metric("Predicted change", f"{impact * 100:+.2f} %")
        m2.metric("Forecasted price", f"Rs. {final:,.0f}")
        m3.metric("Absolute change", f"Rs. {change:+,.0f}")


# -----------------------------------------------------------------------------
# Methodology (landed-cost style) + glossary — shared across products
# -----------------------------------------------------------------------------
def _methodology_infographic():
    _sec("How the sensitivity prediction is built", theme.icon("notes"))
    st.markdown(
        "Each product is a **stateless single-row model**: the predicted move depends only on the "
        "driver shocks you enter — no history, momentum or market-state terms. Every driver carries a "
        "fixed **sensitivity β** (how much the product moves per 1% move in that driver), estimated once "
        "on years of month-on-month price changes. Your shocks are weighted by β, summed, and applied to "
        "the current price."
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
        "<p>shock &rarr; to % &rarr; &times; β &rarr; sum &rarr; e<sup>Σ</sup>, per driver.</p></div>"
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
        ("factory",    "Shock",        "Enter Δ% or Δ₹ per driver.",
         "shock = Δ% or Δ₹"),
        ("gauge",      "To percent",   "₹ converts via base price.",
         "eff% = Δ% + Δ₹ &divide; <b>Base</b>"),
        ("calculator", "Weight by β",  "Scale by the driver's sensitivity.",
         "c = eff% &times; <b>&beta;</b>"),
        ("notes",      "Sum",          "Add every driver's share.",
         "impact = &Sigma; c"),
        ("rupee",      "Apply",        "Compound onto the current price.",
         "Price = Current &times; e<sup>impact</sup>"),
        ("trending",   "Read",         "Direction and magnitude.",
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
        ("β", "Sensitivity", "Predicted % move in the product per 1% move in a driver — the model's weight."),
        ("eff%", "Effective % change", "A driver's shock as a %: Δ% plus any Δ₹ divided by its base price."),
        ("Σ", "Predicted move", "Sum of every driver's contribution (eff% × β) — the total log-return."),
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
    st.caption("Pick a product, shock its cost / benchmark drivers, and read the predicted price move. "
               "Each product has its own fixed sensitivities (β) from a backtested model.")

    # fixed-β products (HR Plate, Rebar) + the live-fit HRC spec
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
