# =============================================================================
# Steel Production Cost & Margin Calculator — BigMint AI Labs portal
# Rebuilt UI (dual-axis chart on top, controls beside it, editable per-plant cost
# tables, infographic methodology) — themed to match the Landed Cost calculator.
# The calculation ENGINE is unchanged: converted price × consumption norm per
# element, summed to an ex-works cost; margin = market price − total cost.
# =============================================================================
import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime

import theme   # shared brand palette + infographic CSS/helpers
import grid    # BigMint-themed AgGrid (blue header, sort/filter)

# --- Engine inputs ------------------------------------------------------------
CURRENCY_OPTS = ["INR (Rs.)", "USD ($)"]
USD = "USD ($)"

# key, label, group, default price, default norm (None => product-based, see _seed),
# price/norm basis (documentation shown in the editor).
ELEMENTS = [
    ("ore",   "Iron Ore (Fines/Lumps/Pellets)", "Raw Material",     9500.0, 1.650, "Rs./MT x MT/MT"),
    ("coal",  "Coking Coal / Met Coke / PCI",   "Raw Material",    22000.0, 0.800, "Rs./MT x MT/MT"),
    ("scrap", "Scrap HMS 80:20",                "Raw Material",    38000.0, 0.150, "Rs./MT x MT/MT"),
    ("flux",  "Limestone / Dolomite",           "Fluxes & Alloys",     3.50, 250.0, "Rs./kg x kg/MT"),
    ("alloy", "Ferroalloys (SiMn, FeMn, FeSi)", "Fluxes & Alloys",    85.0,  12.0, "Rs./kg x kg/MT"),
    ("elec",  "Electricity",                    "Power",               7.50, None, "Rs./kWh x kWh/MT"),
    ("proc",  "Processing Cost",                "OpEx",             4500.0,   1.0, "Rs./MT"),
    ("misc",  "Miscellaneous Expenses",         "OpEx",             1200.0,   1.0, "Rs./MT"),
    ("fin",   "Finance Cost (Avg)",             "OpEx",             1500.0,   1.0, "Rs./MT"),
    ("dep",   "Depreciation & Amortization",    "OpEx",             2000.0,   1.0, "Rs./MT"),
]
ELEM_KEYS = [e[0] for e in ELEMENTS]


def _elem_cost(price, currency, norm, ex_rate):
    """UNCHANGED ENGINE: USD prices convert at the FX rate, then × consumption norm."""
    base = price * ex_rate if currency == USD else price
    return base * norm


def _seed_df(product):
    """Default editable cost build-up for one plant. Electricity's norm depends on
    the product (450 kWh/MT for HRC, 400 for Rebar) — matches the original logic."""
    rows = []
    for key, label, group, price, norm, basis in ELEMENTS:
        n = (450.0 if product == "HRC" else 400.0) if key == "elec" else float(norm)
        rows.append({"Cost element": label, "Basis": basis, "Currency": CURRENCY_OPTS[0],
                     "Price": float(price), "Norm": n})
    return pd.DataFrame(rows, columns=["Cost element", "Basis", "Currency", "Price", "Norm"])


def _plant_costs(edited, ex_rate):
    """Per-element cost dict + ex-works total from an edited plant table (row order
    matches ELEMENTS; the editor is num_rows='fixed' so positions are stable)."""
    costs = {}
    for i, key in enumerate(ELEM_KEYS):
        row = edited.iloc[i]
        costs[key] = _elem_cost(float(row["Price"]), row["Currency"], float(row["Norm"]), ex_rate)
    return costs, sum(costs.values())


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


def _pdf_bytes(pdf):
    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)


class Report_PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Steel Production Cost and Margin Analysis Report", 0, 1, "C")
        self.set_font("Arial", "I", 8)
        self.cell(0, 5, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, "C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


def _sec(text, icon=""):
    ic = f"{icon} " if icon else ""
    st.markdown(f"<div class='bm-sec'>{ic}{text}</div>", unsafe_allow_html=True)


def _editor(prefix, product, ver):
    """One plant's editable cost table. Keyed by product + reset-version so switching
    product re-seeds fresh values and Reset clears edits (fresh widget key)."""
    return st.data_editor(
        _seed_df(product), key=f"cost_{prefix}_{product}_{ver}", hide_index=True,
        num_rows="fixed", width="stretch",
        column_config={
            "Cost element": st.column_config.TextColumn("Cost element", disabled=True, width="medium"),
            "Basis": st.column_config.TextColumn("Basis", disabled=True, width="small",
                        help="Unit the price is quoted in x its consumption norm."),
            "Currency": st.column_config.SelectboxColumn("Cur.", options=CURRENCY_OPTS, required=True,
                        width="small", help="Set to USD ($) to enter a dollar price — converted at the USD->INR rate."),
            "Price": st.column_config.NumberColumn("Price", format="%.2f", step=1.0, min_value=0.0),
            "Norm": st.column_config.NumberColumn("Norm", format="%.3f", step=0.05, min_value=0.0,
                        help="Consumption per tonne of finished steel (OpEx rows use 1)."),
        },
    )


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
        "Each plant is priced through the **same build-up** — every input's price (in ₹ or converted "
        "from USD) is multiplied by its **consumption norm** per tonne, summed into an ex-works cost, "
        "then compared to the market price to give the mill margin. Edit any cell and the chart re-solves."
    )

    def _chips(items):
        return "".join(
            f"<div class='bm-chip'><span class='ic'>{theme.icon(ic, 15)}</span>{label}</div>"
            for ic, label in items
        )
    engine = (
        "<div class='bm-engine'>"
        "<div class='bm-engine-col bm-engine-in'><div class='bm-engine-h'>Inputs</div>"
        + _chips([("factory", "Material prices &amp; currency"),
                  ("rupee",   "Consumption norm per tonne"),
                  ("gauge",   "Market price &amp; USD&rarr;INR")]) +
        "</div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-core'>"
        f"<span class='ic'>{theme.icon('calculator', 26)}</span>"
        "<div style='margin:0 0 6px;font-size:16px;font-weight:700;color:#fff;'>Cost &amp; Margin Engine</div>"
        "<p>price &rarr; convert &rarr; &times; norm &rarr; sum &rarr; margin, applied identically to every plant.</p></div>"
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
        ("gauge",      "Currency",     "USD prices convert at FX.",
         "Rs. = Price &times; <b>FX</b>"),
        ("factory",    "Element cost", "Converted price &times; its norm.",
         "Cost = Rs.Price &times; <b>Norm</b>"),
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
        ("FX", "USD&rarr;INR rate", "Rate used to convert any USD-quoted input into rupees."),
        ("Basis", "Price basis", "The unit a price is quoted in (Rs./MT, Rs./kg, Rs./kWh) &times; its norm."),
    ]
    html = "<div class='bm-factor-grid'>" + "".join(
        f"<div class='bm-factor'><div class='ic' style='font-weight:800;font-size:12px;'>{abbr}</div>"
        f"<div><h5>{full}</h5><p>{desc}</p></div></div>"
        for abbr, full, desc in terms
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)
    st.session_state.setdefault("cost_ver", 0)

    def _reset_tables():
        st.session_state["cost_ver"] = st.session_state.get("cost_ver", 0) + 1

    st.markdown(
        "<div class='bm-calc-head'>"
        f"<div class='bm-calc-title'>{theme.icon('calculator', 30)} Production Cost &amp; Margin Simulation</div>"
        "<div class='bm-calc-sub'>Two-plant ex-works cost build-up &middot; mill margin vs the market price</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Compare the cost to produce one tonne of finished steel at two plants, and the resulting "
               "mill margins at the current market price. Every value below is editable.")

    mgmt_ph = st.empty()      # margin verdict (filled after compute)
    banner_ph = st.empty()    # lower-cost headline

    # --- chart (left) + scenario controls (right) ---
    col_chart, col_ctrl = st.columns([2.5, 1], gap="large", vertical_alignment="center")
    with col_chart:
        _sec("Total cost vs market price & margin", theme.icon("trending"))
        chart_ph = st.empty()
    with col_ctrl:
        theme.section_title("Scenario controls", theme.icon("gauge"))
        product = st.selectbox("Product", ["HRC", "Rebar"], key="cost_product")
        ex_rate = st.number_input("USD → INR rate", value=93.0, step=0.5, key="cost_fx")
        mkt_price = st.number_input(f"Market price — {product} (Rs./MT)", value=55000.0, step=500.0,
                                    key="cost_mkt", min_value=0.0)
        st.button("↺ Reset tables", key="cost_reset", on_click=_reset_tables, width="stretch",
                  help="Restore both plants' cost tables to the defaults for the selected product.")

    # --- editable per-plant cost build-up ---
    _sec("Editable cost build-up by plant", theme.icon("factory"))
    ver = st.session_state.get("cost_ver", 0)
    e1, e2 = st.columns(2, gap="large")
    with e1:
        st.markdown("**Plant 1**")
        ed1 = _editor("p1", product, ver)
    with e2:
        st.markdown("**Plant 2**")
        ed2 = _editor("p2", product, ver)
    st.caption("Price basis is shown per row. **Norm** = consumption per tonne of steel. Switch a row's "
               "**Cur.** to USD ($) to enter a dollar price (converted at the USD→INR rate). Edits update "
               "the chart live; **Reset** restores the product defaults.")

    costs1, total1 = _plant_costs(ed1, ex_rate)
    costs2, total2 = _plant_costs(ed2, ex_rate)
    margin1, margin2 = mkt_price - total1, mkt_price - total2

    # --- fill the chart ---
    with chart_ph.container():
        try:
            st.plotly_chart(_cost_margin_figure(["Plant 1", "Plant 2"], [total1, total2],
                                                [margin1, margin2], mkt_price),
                            width="stretch", config={"displayModeBar": False})
        except Exception:
            st.bar_chart(pd.DataFrame({"Total cost": {"Plant 1": total1, "Plant 2": total2}}))
        st.caption("Bars = ex-works cost per plant (left axis). Dashed line = market price. "
                   "Diamonds = mill margin on the right axis (green = profit, red = loss).")

    # --- headline + verdict ---
    lower = "Plant 1" if total1 <= total2 else "Plant 2"
    lower_cost = min(total1, total2)
    banner_ph.markdown(
        f"<div class='kpi-banner'>Lower-cost producer: {lower} — Rs.{lower_cost:,.0f}/MT "
        f"(vs market Rs.{mkt_price:,.0f}/MT)</div>", unsafe_allow_html=True)
    best_margin = max(margin1, margin2)
    css = "mgmt-good" if best_margin >= 0 else "mgmt-bad"
    if best_margin >= 0:
        msg = (f"Both plants priced against market Rs.{mkt_price:,.0f}/MT. "
               f"Mill margin — Plant 1: Rs.{margin1:,.0f}/MT ({margin1/mkt_price*100:.1f}%), "
               f"Plant 2: Rs.{margin2:,.0f}/MT ({margin2/mkt_price*100:.1f}%).")
    else:
        msg = (f"Both plants are under water at market Rs.{mkt_price:,.0f}/MT. "
               f"Loss — Plant 1: Rs.{margin1:,.0f}/MT, Plant 2: Rs.{margin2:,.0f}/MT.")
    mgmt_ph.markdown(f"<div class='mgmt-box {css}'>Management view: {msg}</div>", unsafe_allow_html=True)

    # --- cost breakup comparison ---
    _sec("Cost breakup — Plant 1 vs Plant 2", theme.icon("rupee"))
    comp = pd.DataFrame([{"Group": grp, "Cost element": label,
                          "Plant 1": costs1[key], "Plant 2": costs2[key]}
                         for (key, label, grp, *_rest) in ELEMENTS])

    def _cmp_cfg(gob, Js):
        gob.configure_column("Group", width=140)
        gob.configure_column("Cost element", width=240)
        gob.configure_column("Plant 1", headerName="Plant 1 (Rs./MT)", type=["numericColumn"],
                             valueFormatter=grid.JS_MONEY)
        gob.configure_column("Plant 2", headerName="Plant 2 (Rs./MT)", type=["numericColumn"],
                             valueFormatter=grid.JS_MONEY)
        gob.configure_grid_options(domLayout="autoHeight")

    grid.bm_grid(comp, key="cost_cmp", configure=_cmp_cfg, page_size=0, height=400, fit=True)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Plant 1 — Total cost", f"Rs.{total1:,.0f}/MT")
    k2.metric("Plant 1 — Mill margin", f"Rs.{margin1:,.0f}/MT", delta=f"{margin1/mkt_price*100:.1f}%")
    k3.metric("Plant 2 — Total cost", f"Rs.{total2:,.0f}/MT")
    k4.metric("Plant 2 — Mill margin", f"Rs.{margin2:,.0f}/MT", delta=f"{margin2/mkt_price*100:.1f}%")

    # --- PDF snapshot (unchanged report content) ---
    if st.button("Generate PDF Report", key="cost_pdf"):
        pdf = Report_PDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 8, f"Product: {product} | Market Price: Rs. {mkt_price:,.0f} | Conversion Rate: {ex_rate}", 0, 1)
        pdf.ln(5)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("Arial", "B", 9)
        headers = ["Cost Element", "Plant 1 (Rs./MT)", "Plant 2 (Rs./MT)"]
        widths = [90, 50, 50]
        for idx, h in enumerate(headers):
            pdf.cell(widths[idx], 10, h, 1, 0, "C", 1)
        pdf.ln()
        pdf.set_font("Arial", "", 9)
        for key, label, *_rest in ELEMENTS:
            pdf.cell(widths[0], 10, label, 1)
            pdf.cell(widths[1], 10, f"{costs1[key]:,.2f}", 1, 0, "R")
            pdf.cell(widths[2], 10, f"{costs2[key]:,.2f}", 1, 0, "R")
            pdf.ln()
        pdf.set_font("Arial", "B", 9)
        pdf.cell(widths[0], 10, "Total Cost (Ex-Works)", 1, 0, "L", 1)
        pdf.cell(widths[1], 10, f"{total1:,.2f}", 1, 0, "R", 1)
        pdf.cell(widths[2], 10, f"{total2:,.2f}", 1, 0, "R", 1)
        pdf.ln()
        pdf.cell(widths[0], 10, "Mill Margin", 1, 0, "L", 1)
        pdf.cell(widths[1], 10, f"{margin1:,.2f}", 1, 0, "R", 1)
        pdf.cell(widths[2], 10, f"{margin2:,.2f}", 1, 0, "R", 1)
        unique_name = f"Steel_Cost_Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        st.download_button("Download PDF Report", data=_pdf_bytes(pdf), file_name=unique_name,
                           mime="application/pdf")

    # --- methodology (infographic) + glossary ---
    _methodology_infographic()
    _glossary()
