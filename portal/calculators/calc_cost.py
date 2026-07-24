# =============================================================================
# Steel Production Cost & Margin Calculator — BigMint AI Labs portal
# Rebuilt UI (dual-axis chart on top, controls beside it, editable per-plant cost
# tables, infographic methodology) — themed to match the Landed Cost calculator.
# The calculation ENGINE is unchanged: converted price × consumption norm per
# element, summed to an ex-works cost; margin = market price − total cost.
# =============================================================================
import streamlit as st
import pandas as pd

import theme        # shared brand palette + infographic CSS/helpers

# --- Engine inputs ------------------------------------------------------------
# Each element: (label, default unit price ₹, default consumption norm, unit).
# norm=None => product-based electricity norm (450 kWh/MT for HRC, 400 for Rebar).
# The BF (blast-furnace) and IF (induction-furnace) routes have different build-ups.
BF_ELEMENTS = [
    ("Iron Ore (Sinter/Lumps/Pellets)", 9500.0, 1.650, "INR/MT"),
    ("Coking Coal(PHCC inc PCI)",       22000.0, 0.800, "INR/MT"),
    ("Scrap HMS 80:20",                 38000.0, 0.150, "INR/MT"),
    ("Limestone / Dolomite",             3500.0, 0.250, "INR/MT"),
    ("Ferroalloys (SiMn)",              85000.0, 0.012, "INR/MT"),
    ("Electricity",                         7.50, None,  "INR/kWh"),
    ("Processing Cost",                  4500.0,   1.0,  "INR/MT"),
    ("Miscellaneous Expenses",           1200.0,   1.0,  "INR/MT"),
    ("Finance Cost (Avg)",               1500.0,   1.0,  "INR/MT"),
    ("Depreciation & Amortization",      2000.0,   1.0,  "INR/MT"),
]
# IF route: metallic-mix feedstock (Sponge Iron / Scrap / Pig Iron / Ferroalloys) then
# power and OpEx. Metallic norms are plant-specific (see IF_MIX); the norms
# below are only fallbacks for a plant not listed in IF_MIX.
IF_ELEMENTS = [
    ("Sponge Iron",                     23250.0, 0.976,  "INR/MT"),
    ("Scrap HMS 80:20",                 38000.0, 0.1575, "INR/MT"),
    ("Pig Iron",                        42000.0, 0.052,  "INR/MT"),
    ("Ferroalloys (SiMn)",              85000.0, 0.012,  "INR/MT"),
    ("Electricity",                         7.50, None,  "INR/kWh"),
    ("Processing Cost",                  4500.0,   1.0,  "INR/MT"),
    ("Miscellaneous Expenses",           1200.0,   1.0,  "INR/MT"),
    ("Finance Cost (Avg)",               1500.0,   1.0,  "INR/MT"),
    ("Depreciation & Amortization",      2000.0,   1.0,  "INR/MT"),
]
# Metallic charge: fixed finished-tonne-per-input-tonne yields, and each IF plant's mix shares.
# Consumption norm = yield × mix share; Ferroalloys stays a fixed 1 × 1.2% = 0.012 additive.
IF_YIELD = {"Sponge Iron": 1.22, "Scrap HMS 80:20": 1.05, "Pig Iron": 1.04}
IF_MIX = {
    "Durgapur": {"Sponge Iron": 0.80, "Scrap HMS 80:20": 0.15, "Pig Iron": 0.05},
    "Jalna":    {"Sponge Iron": 0.20, "Scrap HMS 80:20": 0.75, "Pig Iron": 0.05},
}
# Per-plant BF default overrides: unit prices by element + a plant electricity norm (kWh/MT, replaces
# the product-based 450/400). Elements/plants not listed fall back to the BF_ELEMENTS defaults.
BF_PLANT = {
    "Southern region": {
        "elec_norm": 650.0,
        "prices": {
            "Iron Ore (Sinter/Lumps/Pellets)": 4700.0,
            "Coking Coal(PHCC inc PCI)":       27800.0,
            "Scrap HMS 80:20":                 31555.0,
            "Limestone / Dolomite":             1500.0,
            "Ferroalloys (SiMn)":              75300.0,
            "Processing Cost":                  6500.0,
        },
    },
    "Eastern region": {
        "elec_norm": 650.0,
        "prices": {
            "Iron Ore (Sinter/Lumps/Pellets)": 2100.0,
            "Coking Coal(PHCC inc PCI)":       27500.0,
            "Scrap HMS 80:20":                 35000.0,
            "Limestone / Dolomite":             1500.0,
            "Ferroalloys (SiMn)":              76300.0,
            "Processing Cost":                  6500.0,
        },
    },
}

# Org-wide cost heads per route: the built-in element list (BF_ELEMENTS / IF_ELEMENTS) is the
# fallback, overridden by whatever an admin saves (persisted in the DB under the route's key via the
# Admin panel). Every user's sandbox seeds from these; their per-cell edits stay in-session only.
COST_HEAD_KEY = {"BF": "cost_head_bf_defaults", "IF": "cost_head_if_defaults"}
_BUILTIN_ELEMENTS = {"BF": BF_ELEMENTS, "IF": IF_ELEMENTS}


def _elements(route):
    """Effective cost heads for a route ('BF'/'IF'): the built-in element list unless an admin has
    saved a replacement. Returns a list of (label, unit_price, norm, unit). Never raises — a missing
    DB / no saved row just yields the built-in fallback."""
    try:
        import db
        saved = db.get_setting(COST_HEAD_KEY[route])
    except Exception:
        saved = None
    if saved:
        out = []
        for r in saved:
            try:
                out.append((str(r["label"]), float(r["price"]), float(r["norm"]),
                            str(r.get("unit") or "INR/MT")))
            except (TypeError, ValueError, KeyError):
                continue
        if out:
            return out
    return list(_BUILTIN_ELEMENTS[route])


def _elem_cost(price, norm):
    """ENGINE: unit price × consumption norm (all prices in ₹)."""
    return price * norm


def _mix_note(plant):
    """Per-plant metallic-mix footnote (norm = yield × mix share); None for non-IF plants."""
    mix = IF_MIX.get(plant)
    if not mix:
        return None
    parts = ", ".join(f"{m} {IF_YIELD[m]:g} × {round(share * 100):g}% = {IF_YIELD[m] * share:g}"
                      for m, share in mix.items())
    return f"† Metallic mix — {parts}; Ferroalloys 1 × 1.2% = 0.012 (MT/MT)."


def _seed_df(product, is_if=False, plant=None):
    """Default editable cost build-up for one plant, from the BF or IF element list. Electricity's
    norm is product-based (450 kWh/MT for HRC, 400 for Rebar); IF metallic norms come from the
    plant's mix (IF_MIX), falling back to the IF_ELEMENTS defaults if the plant isn't listed."""
    mix = IF_MIX.get(plant) if is_if else None
    bf = None if is_if else BF_PLANT.get(plant)
    rows = []
    for label, price, norm, unit in _elements("IF" if is_if else "BF"):
        if norm is None:                       # electricity: BF plant norm, else product-based 450/400
            n = bf["elec_norm"] if bf and "elec_norm" in bf else (450.0 if product == "HRC" else 400.0)
        elif mix and label in mix:
            n = IF_YIELD[label] * mix[label]
        else:
            n = float(norm)
        p = bf["prices"].get(label, price) if bf else price
        rows.append({"Cost element": label, "Unit": unit, "Price": float(p), "Norm": n})
    return pd.DataFrame(rows, columns=["Cost element", "Unit", "Price", "Norm"])


def _plant_costs(edited):
    """Ex-works total from an edited plant table (sum of unit price × norm over every row)."""
    return sum(_elem_cost(float(r["Price"]), float(r["Norm"])) for _, r in edited.iterrows())


CALC_CSS = """
<style>
/* NB: do NOT override [data-testid="stVerticalBlock"] gap here — unscoped/page-global, it shoved the
   whole Scenario page down and broke top alignment vs other pages. Keep app-wide 0.65rem (theme.py). */
[data-testid="stHorizontalBlock"] { gap: 1.1rem !important; }
/* prominent page heading (mirrors the Landed Cost calculator) */
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
/* headline banner + verdict boxes */
.kpi-banner { border-radius: 12px; padding: 13px 18px; margin: 2px 0 4px; font-size: 16px; font-weight: 700;
    color: #fff; background: linear-gradient(120deg, var(--bm-primary), var(--bm-primary-dark));
    box-shadow: 0 4px 16px rgba(2,76,161,.18); }
.mgmt-box { border-radius: 12px; padding: 14px 18px; margin-bottom: 4px; font-size: 15px; font-weight: 600; }
.mgmt-good { background: #e8f7ee; border: 1px solid #b7e4c7; color: #0b3d2e; }
.mgmt-bad  { background: #fdecea; border: 1px solid #f5b7b1; color: #7b241c; }
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


def _editor(prefix, product, ver, key, is_if=False, plant=None):
    """One plant's editable cost table. Keyed by route+product (`key`) + reset-version so switching
    product re-seeds fresh values and Reset clears edits (fresh widget key). `product` ('HRC'/'Rebar')
    only drives the seeded defaults; `is_if` picks the IF element list and `plant` its metallic mix.
    Columns: Cost element · Unit · Unit price · Consumption norm · Total cost (norm x unit price)."""
    wkey = f"cost_{prefix}_{key}_{ver}"
    df = _seed_df(product, is_if, plant)
    # Fold any stored edits back in so the read-only Total cost reflects the latest inputs.
    state = st.session_state.get(wkey)
    if state and state.get("edited_rows"):
        for ridx, chg in state["edited_rows"].items():
            for c, v in chg.items():
                df.at[int(ridx), c] = v
    df["Total"] = [_elem_cost(float(r["Price"]), float(r["Norm"])) for _, r in df.iterrows()]
    return st.data_editor(
        df, key=wkey, hide_index=True, num_rows="fixed", width="stretch",
        column_order=["Cost element", "Unit", "Price", "Norm", "Total"],
        column_config={
            "Cost element": st.column_config.TextColumn("Cost element", disabled=True, width="medium"),
            "Unit": st.column_config.TextColumn("Unit", disabled=True, width="small",
                        help="Unit the price is quoted in (INR/MT, or INR/kWh for electricity)."),
            "Price": st.column_config.NumberColumn("Unit price", format="%.2f", step=1.0, min_value=0.0),
            "Norm": st.column_config.NumberColumn("Consumption norm", format="%.3f", step=0.05, min_value=0.0,
                        help="Consumption per tonne of finished steel (OpEx rows use 1)."),
            "Total": st.column_config.NumberColumn("Total cost", format="%.0f", disabled=True,
                        help="Consumption norm x unit price."),
        },
    )


def _totals_line(total, margin):
    """Total cost + mill margin shown just below a plant's table (margin colored by sign)."""
    col = theme.SUCCESS if margin >= 0 else theme.DANGER
    st.markdown(
        f"<div style='margin:6px 0 2px;font-size:14px;font-weight:600;color:#334155;'>"
        f"Total cost: <b>INR {total:,.0f}</b>/MT &middot; "
        f"Margin: <b style='color:{col};'>INR {margin:,.0f}</b>/MT</div>",
        unsafe_allow_html=True)


# Categorical palette for the stacked cost-component segments (brand blues + accent + muted tones).
SEG_COLORS = ["#024CA1", "#2E7CD6", "#5BA3E0", "#8FC1EA", "#EE4E24",
              "#F5915F", "#1F9D55", "#7BC49A", "#64748B", "#A7B3C2"]


def _cost_margin_figure(names, edited, mkt_prices):
    """Stacked bars — one segment per cost element (its cost = consumption norm x unit price) — with
    two scatter overlays: market price (circles, left axis) and mill margin (diamonds coloured by
    sign, secondary right axis). Grand total labelled above each bar. Legend sits on top, outside."""
    import plotly.graph_objects as go
    fig = go.Figure()
    labels = list(edited[names[0]]["Cost element"])
    totals = {n: 0.0 for n in names}
    for k, label in enumerate(labels):
        ys = []
        for n in names:
            r = edited[n].iloc[k]
            c = _elem_cost(float(r["Price"]), float(r["Norm"]))
            totals[n] += c
            ys.append(c)
        fig.add_bar(
            x=names, y=ys, name=label,
            marker=dict(color=SEG_COLORS[k % len(SEG_COLORS)], line=dict(color="white", width=0.5)),
            hovertemplate="<b>%{x}</b><br>" + label + ": INR %{y:,.0f}/MT<extra></extra>",
        )
    margins = {n: mkt_prices[n] - totals[n] for n in names}
    fig.add_scatter(
        x=names, y=[mkt_prices[n] for n in names], name="Market price", yaxis="y", mode="markers",
        marker=dict(size=13, symbol="circle", color=theme.ACCENT, line=dict(color="white", width=2)),
        hovertemplate="<b>%{x}</b><br>Market price: INR %{y:,.0f}/MT<extra></extra>",
    )
    mcolors = [theme.SUCCESS if margins[n] >= 0 else theme.DANGER for n in names]
    fig.add_scatter(
        x=names, y=[margins[n] for n in names], name="Mill margin", yaxis="y2", mode="markers",
        marker=dict(size=15, symbol="diamond", color=mcolors, line=dict(color="white", width=2)),
        hovertemplate="<b>%{x}</b><br>Mill margin: INR %{y:,.0f}/MT<extra></extra>",
    )
    ymax = max(max(totals.values()), max(mkt_prices.values())) * 1.16
    fig.update_layout(
        barmode="stack", height=540, margin=dict(l=10, r=55, t=124, b=10), plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)", font=dict(family="sans-serif", size=12, color="#334155"),
        bargap=0.45,
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0.5, xanchor="center",
                    font=dict(size=10.5)),
        yaxis=dict(title="Cost / market (INR/MT)", tickprefix="INR ", tickformat=",.0f",
                   gridcolor="#f1f5f9", zeroline=False, range=[0, ymax]),
        yaxis2=dict(title="Mill margin (INR/MT)", overlaying="y", side="right", tickprefix="INR ",
                    tickformat=",.0f", showgrid=False, zeroline=True, zerolinecolor="#e2e8f0"),
        annotations=[dict(x=n, y=totals[n], xref="x", yref="y", text=f"INR {totals[n]:,.0f}",
                          showarrow=False, yshift=-17, font=dict(size=11.5, color="#0f172a"),
                          bgcolor="rgba(255,255,255,0.92)", bordercolor="#cbd5e1",
                          borderwidth=1, borderpad=3)
                     for n in names],
    )
    fig.update_xaxes(tickfont=dict(size=13.5, color="#0f172a"))
    return fig


def _methodology_infographic():
    _sec("How the cost & margin are built", theme.icon("notes"))
    st.markdown(
        "Each plant is priced through the **same build-up** — every input's **unit price** (INR/MT, or "
        "INR/kWh for electricity) is multiplied by its **consumption norm** per tonne, summed into an ex-works "
        "cost, then compared to the market price to give the mill margin. Edit any cell and the chart re-solves."
    )

    def _chips(items):
        return "".join(
            f"<div class='bm-chip'><span class='ic'>{theme.icon(ic, 15)}</span>{label}</div>"
            for ic, label in items
        )
    engine = (
        "<div class='bm-engine'>"
        "<div class='bm-engine-col bm-engine-in'><div class='bm-engine-h'>Inputs</div>"
        + _chips([("factory", "Material unit prices"),
                  ("rupee",   "Consumption norm per tonne"),
                  ("gauge",   "Market price")]) +
        "</div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-core'>"
        f"<span class='ic'>{theme.icon('calculator', 26)}</span>"
        "<div style='margin:0 0 6px;font-size:16px;font-weight:700;color:#fff;'>Cost &amp; Margin Engine</div>"
        "<p>unit price &rarr; &times; norm &rarr; sum &rarr; margin, applied identically to every plant.</p></div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-col bm-engine-out'><div class='bm-engine-h'>Outputs</div>"
        + _chips([("rupee",    "Ex-works cost per plant"),
                  ("target",   "Mill margin &amp; margin %"),
                  ("trending", "Lower-cost plant")]) +
        "</div></div>"
    )
    st.markdown(engine, unsafe_allow_html=True)

    st.write("")
    _sec("The equation pipeline", theme.icon("notes"))
    steps = [
        ("factory",    "Element cost", "Unit price &times; its norm.",
         "Cost = <b>Unit price</b> &times; <b>Norm</b>"),
        ("calculator", "Ex-works cost", "Sum every element.",
         "Total = &Sigma; Cost"),
        ("rupee",      "Mill margin",  "Market minus total cost.",
         "Margin = <b>Market</b> &minus; Total"),
        ("target",     "Margin %",     "Share of selling price.",
         "Margin% = Margin &divide; <b>Market</b>"),
        ("trending",   "Verdict",      "Higher margin wins.",
         "Higher <b>Margin</b> &rArr; better plant"),
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
        ("Ex-Works", "Ex-works cost", "Total production cost at the mill gate, before freight and taxes."),
        ("Norm", "Consumption norm", "Input consumed per tonne of finished steel (MT/MT, kg/MT, kWh/MT)."),
        ("Margin", "Mill margin", "Market price minus ex-works cost &mdash; the profit per tonne."),
        ("OpEx", "Operating expenses", "Processing, miscellaneous, finance and depreciation per tonne."),
        ("Unit", "Price unit", "The unit a price is quoted in — INR/MT (INR/kWh for electricity)."),
    ]
    html = "<div class='bm-factor-grid'>" + "".join(
        f"<div class='bm-factor'><div class='ic' style='font-weight:800;font-size:12px;'>{abbr}</div>"
        f"<div><h5>{full}</h5><p>{desc}</p></div></div>"
        for abbr, full, desc in terms
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


# Two production routes, each with its own product dropdown and named plants.
# BF (blast furnace): HRC + Rebar; IF (induction furnace): Rebar only.
ROUTE_PRODUCTS = {
    "BF route": {
        "HRC":   ["Southern region", "Eastern region"],
        "Rebar": ["Southern region", "Chhattisgarh"],
    },
    "IF route": {
        "Rebar": ["Durgapur", "Jalna"],
    },
}


# @st.fragment: an edit (cell, control, reset) reruns ONLY this product view — not the whole app
# script — so the editable cost tables stay responsive with no full-page reload on every change.
@st.fragment
def _render_product(product, plants, key, is_if=False):
    """One product view: dual-axis chart + controls, an editable cost table per plant, and the
    headline/verdict. `key` (route+product, e.g. 'bf_rebar') namespaces every widget so the same
    product in two routes never collides; `product` drives labels + seeded defaults. `is_if`
    selects the IF element list and shows the metallic-mix footnote. Engine unchanged."""
    verkey = f"cost_ver_{key}"
    st.session_state.setdefault(verkey, 0)

    def _reset_tables():
        st.session_state[verkey] = st.session_state.get(verkey, 0) + 1

    mgmt_ph = st.empty()      # margin verdict (filled after compute)
    banner_ph = st.empty()    # lower-cost headline

    # --- chart (left) + scenario controls (right) ---
    col_chart, col_ctrl = st.columns([2.5, 1], gap="large", vertical_alignment="center")
    with col_chart:
        _sec("Cost build-up vs market price", theme.icon("trending"))
        chart_ph = st.empty()
    with col_ctrl:
        theme.section_title("Scenario controls", theme.icon("gauge"))
        mkt_prices = {n: st.number_input(f"Market price — {n} (INR/MT)", value=55000.0, step=500.0,
                                         key=f"cost_mkt_{key}_{n}", min_value=0.0)
                      for n in plants}
        st.button("↺ Reset tables", key=f"cost_reset_{key}", on_click=_reset_tables, width="stretch",
                  help="Restore every plant's cost table to the defaults for this product.")

    # --- editable per-plant cost build-up (two tables per row) ---
    _sec("Editable cost build-up by plant", theme.icon("factory"))
    ver = st.session_state.get(verkey, 0)
    edited, totals, margins = {}, {}, {}
    for i in range(0, len(plants), 2):
        chunk = plants[i:i + 2]
        cols = st.columns(len(chunk), gap="large")
        for j, (col, name) in enumerate(zip(cols, chunk)):
            with col:
                st.markdown(f"**{name}**")
                edited[name] = _editor(f"p{i + j}", product, ver, key, is_if, name)
                totals[name] = _plant_costs(edited[name])
                margins[name] = mkt_prices[name] - totals[name]
                _totals_line(totals[name], margins[name])
                note = _mix_note(name)
                if note:
                    st.caption(note)
    st.caption("**Total cost = consumption norm × unit price** (auto-computed per row). **Consumption norm** = "
               "input consumed per tonne of steel; **Unit** is INR/MT (INR/kWh for electricity). Edits update the "
               "chart live; **Reset** restores the product defaults.")

    # --- fill the chart ---
    with chart_ph.container():
        try:
            # stable key (namespaced by the fragment's route+product `key`) so Streamlit updates the
            # chart in place on each cost-cell edit instead of unmounting/re-plotting it — kills the flash.
            st.plotly_chart(
                _cost_margin_figure(plants, edited, mkt_prices),
                width="stretch", config={"displayModeBar": False}, key=f"cost_chart_{key}")
        except Exception:
            st.bar_chart(pd.DataFrame({"Total cost": {n: totals[n] for n in plants}}))
        st.caption("Stacked bars = each cost element's contribution to the ex-works cost per plant "
                   "(total labelled above each bar). Orange circles = market price (left axis); "
                   "diamonds = mill margin on the right axis (green = profit, red = loss).")

    # --- headline + verdict ---
    lower = min(plants, key=lambda n: totals[n])
    banner_ph.markdown(
        f"<div class='kpi-banner'>Lower-cost producer: {lower} — INR {totals[lower]:,.0f}/MT "
        f"(vs market INR {mkt_prices[lower]:,.0f}/MT)</div>", unsafe_allow_html=True)
    best = max(plants, key=lambda n: margins[n])
    profitable = [n for n in plants if margins[n] >= 0]
    if margins[best] >= 0:
        css = "mgmt-good"
        msg = (f"{len(profitable)} of {len(plants)} plants profitable at current market prices. "
               f"Best margin: {best} at INR {margins[best]:,.0f}/MT ({margins[best]/mkt_prices[best]*100:.1f}%).")
    else:
        css = "mgmt-bad"
        msg = (f"No plant is profitable at current market prices. "
               f"Smallest loss: {best} at INR {margins[best]:,.0f}/MT.")
    mgmt_ph.markdown(f"<div class='mgmt-box {css}'>Management view: {msg}</div>", unsafe_allow_html=True)


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='bm-calc-head'>"
        f"<div class='bm-calc-title'>{theme.icon('calculator', 30)} Production Cost &amp; Margin Simulation</div>"
        "<div class='bm-calc-sub'>Multi-plant ex-works cost build-up &middot; mill margin vs the market price</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Pick a route (BF / IF) and product, then compare the cost to produce one tonne of finished "
               "steel across its plants and the resulting mill margins at the current market price. "
               "Every value is editable.")

    for tab, route in zip(st.tabs(list(ROUTE_PRODUCTS)), ROUTE_PRODUCTS):
        with tab:
            prods = ROUTE_PRODUCTS[route]
            rkey = route.split()[0].lower()          # 'bf' / 'if'
            names = list(prods)
            # clickable tab-strip (same widget as the forecast page's product selector)
            product = st.segmented_control("Product", names, default=names[0],
                                           key=f"cost_prod_{rkey}", label_visibility="collapsed")
            product = product if product in prods else names[0]
            _render_product(product, prods[product], key=f"{rkey}_{product.lower()}",
                            is_if=(rkey == "if"))

    st.divider()
    _methodology_infographic()
    _glossary()


def _admin_route_editor(route):
    """One route's org-wide cost-head editor: add / rename / delete rows and set each head's unit
    price + consumption norm, with Save-as-default / Reset persisted under the route's DB key."""
    verkey = f"cost_admin_{route}_ver"
    ver = st.session_state.setdefault(verkey, 0)
    df = pd.DataFrame([{"Cost element": l, "Unit": u, "Price": p, "Norm": n}
                       for l, p, n, u in _elements(route)])
    edited = st.data_editor(
        df, key=f"cost_admin_{route}_{ver}", hide_index=True, num_rows="dynamic", width="stretch",
        column_order=["Cost element", "Unit", "Price", "Norm"],
        column_config={
            "Cost element": st.column_config.TextColumn("Cost element", required=False,
                        help="Add, rename or delete cost heads here. Blank rows are ignored on save."),
            "Unit": st.column_config.TextColumn("Unit", help="INR/MT, or INR/kWh for electricity."),
            "Price": st.column_config.NumberColumn("Unit price", format="%.2f", step=1.0, min_value=0.0),
            "Norm": st.column_config.NumberColumn("Consumption norm", format="%.3f", step=0.05, min_value=0.0,
                        help="Consumption per tonne of finished steel (OpEx rows use 1)."),
        },
    )
    c1, c2 = st.columns([1, 1], vertical_alignment="center")
    if c1.button("💾 Save as default for all users", key=f"cost_admin_{route}_save", type="primary",
                 width="stretch"):
        out = []
        for _, r in edited.iterrows():
            label = str(r.get("Cost element", "") or "").strip()
            if not label:                                  # skip blank rows
                continue
            out.append({
                "label": label,
                "unit": str(r.get("Unit") or "INR/MT"),
                "price": float(r["Price"]) if pd.notna(r["Price"]) else 0.0,
                "norm": float(r["Norm"]) if pd.notna(r["Norm"]) else 0.0,
            })
        try:
            import db
            db.set_setting(COST_HEAD_KEY[route], out)
            st.success(f"Saved — these are now the {route}-route cost heads for all users.")
        except Exception as e:
            st.error(f"Save failed: {e}")
    if c2.button("↺ Reset to built-in", key=f"cost_admin_{route}_reset", width="stretch",
                 help="Discard the saved cost heads and revert to the built-in defaults for this route."):
        try:
            import db
            db.set_setting(COST_HEAD_KEY[route], [])       # empty -> _elements() falls back to built-in
        except Exception as e:
            st.error(f"Reset failed: {e}")
        st.session_state[verkey] += 1
        st.rerun()


def render_admin_defaults():
    """Admin: manage the org-wide cost heads for BOTH production routes (BF + IF). Add / rename /
    delete rows and set each head's unit price + consumption norm, then save them as the default
    every user's sandbox starts from (persisted per route in the DB). Non-admins can only edit
    values within their own sandbox."""
    st.markdown(CALC_CSS, unsafe_allow_html=True)
    st.caption("These are the **org-wide cost heads** every user's sandbox starts from. Pick a route, "
               "add / rename / delete rows (＋ to add, select + 🗑 to remove), set the unit price and "
               "consumption norm, then **Save as default**. Plant-specific overrides still apply on top "
               "(BF per-plant prices / electricity norm; IF metallic-mix norms).")
    route = st.segmented_control("Route", list(COST_HEAD_KEY), default="BF",
                                 key="cost_admin_route", label_visibility="collapsed")
    _admin_route_editor(route or "BF")
