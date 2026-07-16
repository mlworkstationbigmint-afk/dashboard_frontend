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
    ("Iron Ore (Sinter/Lumps/Pellets)", 9500.0, 1.650, "Rs./MT"),
    ("Coking Coal / Met Coke / PCI",    22000.0, 0.800, "Rs./MT"),
    ("Scrap HMS 80:20",                 38000.0, 0.150, "Rs./MT"),
    ("Limestone / Dolomite",             3500.0, 0.250, "Rs./MT"),
    ("Ferroalloys (SiMn)",              85000.0, 0.012, "Rs./MT"),
    ("Electricity",                         7.50, None,  "Rs./kWh"),
    ("Processing Cost",                  4500.0,   1.0,  "Rs./MT"),
    ("Miscellaneous Expenses",           1200.0,   1.0,  "Rs./MT"),
    ("Finance Cost (Avg)",               1500.0,   1.0,  "Rs./MT"),
    ("Depreciation & Amortization",      2000.0,   1.0,  "Rs./MT"),
]
# IF route: metallic-mix feedstock (Sponge Iron / Scrap / Pig Iron / Ferroalloys) then
# Non coking coal, power and OpEx. Norms are the final metallic-mix values (see _METALLIC_MIX).
IF_ELEMENTS = [
    ("Sponge Iron",                      9500.0, 0.976,  "Rs./MT"),
    ("Scrap HMS 80:20",                 38000.0, 0.1575, "Rs./MT"),
    ("Pig Iron",                        42000.0, 0.052,  "Rs./MT"),
    ("Ferroalloys (SiMn)",              85000.0, 0.012,  "Rs./MT"),
    ("Non coking coal RB2",             22000.0, 0.800,  "Rs./MT"),
    ("Electricity",                         7.50, None,  "Rs./kWh"),
    ("Processing Cost",                  4500.0,   1.0,  "Rs./MT"),
    ("Miscellaneous Expenses",           1200.0,   1.0,  "Rs./MT"),
    ("Finance Cost (Avg)",               1500.0,   1.0,  "Rs./MT"),
    ("Depreciation & Amortization",      2000.0,   1.0,  "Rs./MT"),
]
# Footnote spelling out how the IF metallic-mix norms are derived (norm = yield x mix share).
_METALLIC_MIX = ("Sponge Iron 1.22 × 80% = 0.976, Scrap 1.05 × 15% = 0.1575, "
                 "Pig Iron 1.04 × 5% = 0.052, Ferroalloys 1 × 1.2% = 0.012 (MT/MT)")


def _elem_cost(price, norm):
    """ENGINE: unit price × consumption norm (all prices in ₹)."""
    return price * norm


def _seed_df(product, is_if=False):
    """Default editable cost build-up for one plant, from the BF or IF element list.
    Electricity's norm is product-based (450 kWh/MT for HRC, 400 for Rebar)."""
    rows = []
    for label, price, norm, unit in (IF_ELEMENTS if is_if else BF_ELEMENTS):
        n = (450.0 if product == "HRC" else 400.0) if norm is None else float(norm)
        rows.append({"Cost element": label, "Unit": unit, "Price": float(price), "Norm": n})
    return pd.DataFrame(rows, columns=["Cost element", "Unit", "Price", "Norm"])


def _plant_costs(edited):
    """Ex-works total from an edited plant table (sum of unit price × norm over every row)."""
    return sum(_elem_cost(float(r["Price"]), float(r["Norm"])) for _, r in edited.iterrows())


CALC_CSS = """
<style>
/* breathing room (theme.py squeezes the block gap; loosen it on this dense page) */
[data-testid="stVerticalBlock"] { gap: 0.9rem !important; }
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


def _editor(prefix, product, ver, key, is_if=False):
    """One plant's editable cost table. Keyed by route+product (`key`) + reset-version so switching
    product re-seeds fresh values and Reset clears edits (fresh widget key). `product` ('HRC'/'Rebar')
    only drives the seeded defaults; `is_if` picks the IF element list. Columns:
    Cost element · Unit · Unit price · Consumption norm · Total cost (norm x unit price)."""
    wkey = f"cost_{prefix}_{key}_{ver}"
    df = _seed_df(product, is_if)
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
                        help="Unit the price is quoted in (Rs./MT, or Rs./kWh for electricity)."),
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
        f"Total cost: <b>Rs.{total:,.0f}</b>/MT &middot; "
        f"Margin: <b style='color:{col};'>Rs.{margin:,.0f}</b>/MT</div>",
        unsafe_allow_html=True)


def _cost_margin_figure(names, totals, margins, mkt_price):
    """Dual-axis: total-cost bars + market-price dashed line (left), mill margin on
    a secondary right axis (diamonds, coloured by sign)."""
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_bar(
        x=names, y=totals, name="Total cost", yaxis="y",
        marker=dict(color=theme.PRIMARY, cornerradius=9, line=dict(color="white", width=1.5)),
        text=[f"Rs.{v:,.0f}" for v in totals], textposition="outside",
        textfont=dict(size=12, color="#0f172a"), cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Total cost: Rs.%{y:,.0f}/MT<extra></extra>",
    )
    mcolors = [theme.SUCCESS if m >= 0 else theme.DANGER for m in margins]
    fig.add_scatter(
        x=names, y=margins, name="Mill margin", yaxis="y2", mode="lines+markers+text",
        line=dict(color=theme.ACCENT, width=2.5, dash="dot"),
        marker=dict(size=14, symbol="diamond", color=mcolors, line=dict(color="white", width=2)),
        text=[f"Rs.{v:,.0f}" for v in margins], textposition="top center",
        textfont=dict(size=11.5, color=theme.ACCENT),
        hovertemplate="<b>%{x}</b><br>Mill margin: Rs.%{y:,.0f}/MT<extra></extra>",
    )
    fig.add_hline(
        y=mkt_price, line=dict(color=theme.NEUTRAL, width=2, dash="dash"),
        annotation_text=f"  Market Rs.{mkt_price:,.0f}/MT  ", annotation_position="top right",
        annotation_font=dict(color="#fff", size=12),
        annotation_bgcolor=theme.NEUTRAL, annotation_bordercolor=theme.NEUTRAL, annotation_borderpad=4,
    )
    ymax = max(max(totals), mkt_price) * 1.18
    fig.update_layout(
        height=420, margin=dict(l=10, r=10, t=44, b=10), plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)", font=dict(family="sans-serif", size=12, color="#334155"),
        bargap=0.5, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12)),
        yaxis=dict(title="Cost / market (Rs./MT)", tickprefix="Rs.", tickformat=",.0f",
                   gridcolor="#f1f5f9", zeroline=False, range=[0, ymax]),
        yaxis2=dict(title="Mill margin (Rs./MT)", overlaying="y", side="right", tickprefix="Rs.",
                    tickformat=",.0f", showgrid=False, zeroline=True, zerolinecolor="#e2e8f0"),
    )
    fig.update_xaxes(tickfont=dict(size=13.5, color="#0f172a"))
    return fig


def _methodology_infographic():
    _sec("How the cost & margin are built", theme.icon("notes"))
    st.markdown(
        "Each plant is priced through the **same build-up** — every input's **unit price** (Rs./MT, or "
        "Rs./kWh for electricity) is multiplied by its **consumption norm** per tonne, summed into an ex-works "
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
        ("Ex-Works", "Ex-works cost", "Total production cost at the mill gate, before freight and taxes."),
        ("Norm", "Consumption norm", "Input consumed per tonne of finished steel (MT/MT, kg/MT, kWh/MT)."),
        ("Margin", "Mill margin", "Market price minus ex-works cost &mdash; the profit per tonne."),
        ("OpEx", "Operating expenses", "Processing, miscellaneous, finance and depreciation per tonne."),
        ("Unit", "Price unit", "The unit a price is quoted in — Rs./MT (Rs./kWh for electricity)."),
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
        "Rebar": ["Durgapur"],
    },
}


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
        _sec("Total cost vs market price & margin", theme.icon("trending"))
        chart_ph = st.empty()
    with col_ctrl:
        theme.section_title("Scenario controls", theme.icon("gauge"))
        mkt_price = st.number_input(f"Market price — {product} (Rs./MT)", value=55000.0, step=500.0,
                                    key=f"cost_mkt_{key}", min_value=0.0)
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
                edited[name] = _editor(f"p{i + j}", product, ver, key, is_if)
                totals[name] = _plant_costs(edited[name])
                margins[name] = mkt_price - totals[name]
                _totals_line(totals[name], margins[name])
    if is_if:
        st.caption(f"† **Metallic mix** — consumption norms shown are the final values: {_METALLIC_MIX}.")
    st.caption("**Total cost = consumption norm × unit price** (auto-computed per row). **Consumption norm** = "
               "input consumed per tonne of steel; **Unit** is Rs./MT (Rs./kWh for electricity). Edits update the "
               "chart live; **Reset** restores the product defaults.")

    # --- fill the chart ---
    with chart_ph.container():
        try:
            st.plotly_chart(
                _cost_margin_figure(plants, [totals[n] for n in plants],
                                    [margins[n] for n in plants], mkt_price),
                width="stretch", config={"displayModeBar": False})
        except Exception:
            st.bar_chart(pd.DataFrame({"Total cost": {n: totals[n] for n in plants}}))
        st.caption("Bars = ex-works cost per plant (left axis). Dashed line = market price. "
                   "Diamonds = mill margin on the right axis (green = profit, red = loss).")

    # --- headline + verdict ---
    lower = min(plants, key=lambda n: totals[n])
    banner_ph.markdown(
        f"<div class='kpi-banner'>Lower-cost producer: {lower} — Rs.{totals[lower]:,.0f}/MT "
        f"(vs market Rs.{mkt_price:,.0f}/MT)</div>", unsafe_allow_html=True)
    best = max(plants, key=lambda n: margins[n])
    profitable = [n for n in plants if margins[n] >= 0]
    if margins[best] >= 0:
        css = "mgmt-good"
        msg = (f"{len(profitable)} of {len(plants)} plants profitable at market Rs.{mkt_price:,.0f}/MT. "
               f"Best margin: {best} at Rs.{margins[best]:,.0f}/MT ({margins[best]/mkt_price*100:.1f}%).")
    else:
        css = "mgmt-bad"
        msg = (f"No plant is profitable at market Rs.{mkt_price:,.0f}/MT. "
               f"Smallest loss: {best} at Rs.{margins[best]:,.0f}/MT.")
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
