# =============================================================================
# Steel Production Cost & Margin Calculator
# Adapted for the BigMint - AI Labs portal: wrapped in render(), fixed the
# malformed `header {` CSS block, defined the .material-label class, and made
# PDF output fpdf/fpdf2-safe. Calculation logic preserved.
# =============================================================================
import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime

CALC_CSS = """
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #e6e9ef; border-radius: 10px;
    background-color: #ffffff; padding: 18px; margin-bottom: 10px;
}
div[data-testid="stContainer"] { border: none !important; background: transparent !important; padding: 0px !important; }
h2 { color: #073A7D; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
h3 { color: #1e293b; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
.material-label { font-size: 14px; color: #334155; line-height: 38px; font-weight: 500; }
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


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)

    def sync_all_units():
        master_unit = st.session_state.master_unit_toggle
        base_keys = ["ore", "coal", "scrap", "flux", "alloy", "elec", "proc", "misc", "fin", "dep"]
        for k in base_keys:
            if f"p1_{k}_u" in st.session_state:
                st.session_state[f"p1_{k}_u"] = master_unit
            if f"p2_{k}_u" in st.session_state:
                st.session_state[f"p2_{k}_u"] = master_unit

    st.subheader("Steel Production Cost & Margin Calculator")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        product = c1.selectbox("Product", ["HRC", "Rebar"])
        ex_rate = c2.number_input("USD to INR Rate", value=93.0)
        mkt_price = c3.number_input(f"Market Price: {product} (INR/MT)", value=55000.0)
        c4.selectbox("Change All Currencies To:", ["INR (Rs.)", "USD ($)"], key="master_unit_toggle", on_change=sync_all_units)

    st.divider()

    def horizontal_input_block(title, default_p, default_n, key, prefix, has_norm=True):
        if has_norm:
            col_t, col_u, col_p, col_n = st.columns([2.2, 1.2, 1.2, 1.2])
            col_t.markdown(f"<div class='material-label'>{title}</div>", unsafe_allow_html=True)
            unit = col_u.selectbox("Unit", ["INR (Rs.)", "USD ($)"], key=f"{prefix}_{key}_u", label_visibility="collapsed")
            price = col_p.number_input("Price", value=float(default_p), key=f"{prefix}_{key}_p", label_visibility="collapsed")
            norm = col_n.number_input("Norm", value=float(default_n), key=f"{prefix}_{key}_n", label_visibility="collapsed")
        else:
            col_t, col_u, col_p = st.columns([2.2, 1.2, 2.4])
            col_t.markdown(f"<div class='material-label'>{title}</div>", unsafe_allow_html=True)
            unit = col_u.selectbox("Unit", ["INR (Rs.)", "USD ($)"], key=f"{prefix}_{key}_u", label_visibility="collapsed")
            price = col_p.number_input("Price", value=float(default_p), key=f"{prefix}_{key}_p", label_visibility="collapsed")
            norm = 1.0

        base_price = price * ex_rate if unit == "USD ($)" else price
        return base_price * norm

    def render_column_headers(has_norm=True, price_label="Price/MT", norm_label="Cons. Norm (MT/MT)"):
        if has_norm:
            c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.2, 1.2])
            c1.caption("Material"); c2.caption("Currency"); c3.caption(price_label); c4.caption(norm_label)
        else:
            c1, c2, c3 = st.columns([2.2, 1.2, 2.4])
            c1.caption("Item"); c2.caption("Currency"); c3.caption(price_label)

    def render_plant(prefix, name):
        st.markdown(f"<h2>{name}</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### Raw Material")
            render_column_headers(has_norm=True, price_label="Price/MT", norm_label="Cons. Norm (MT/MT)")
            ore = horizontal_input_block("Iron Ore (Fines/Lumps/Pellets)", 9500, 1.650, "ore", prefix)
            coal = horizontal_input_block("Coking Coal / Met Coke / PCI", 22000, 0.800, "coal", prefix)
            scrap = horizontal_input_block("Scrap HMS 80:20", 38000, 0.150, "scrap", prefix)

        with st.container(border=True):
            st.markdown("### Fluxes & Alloys")
            render_column_headers(has_norm=True, price_label="Price/kg", norm_label="Cons. Norm (kg/MT)")
            flux = horizontal_input_block("Limestone / Dolomite", 3.50, 250.0, "flux", prefix)
            alloy = horizontal_input_block("Ferroalloys (SiMn, FeMn, FeSi)", 85.0, 12.0, "alloy", prefix)

        with st.container(border=True):
            st.markdown("### Power")
            render_column_headers(has_norm=True, price_label="Price/kWh", norm_label="Power Cons. (kWh/MT)")
            power_norm = 450.0 if product == "HRC" else 400.0
            elec = horizontal_input_block("Electricity", 7.50, power_norm, "elec", prefix)

        with st.container(border=True):
            st.markdown("### OpEx")
            render_column_headers(has_norm=False, price_label="Price/MT")
            proc = horizontal_input_block("Processing Cost", 4500, None, "proc", prefix, has_norm=False)
            misc = horizontal_input_block("Miscellaneous Expenses", 1200, None, "misc", prefix, has_norm=False)
            fin = horizontal_input_block("Finance Cost (Avg)", 1500, None, "fin", prefix, has_norm=False)
            dep = horizontal_input_block("Depreciation & Amortization", 2000, None, "dep", prefix, has_norm=False)

        total_cost = ore + coal + scrap + flux + alloy + elec + proc + misc + fin + dep
        margin = mkt_price - total_cost
        return {"ore": ore, "coal": coal, "scrap": scrap, "flux": flux, "alloy": alloy,
                "elec": elec, "proc": proc, "misc": misc, "fin": fin, "dep": dep,
                "total": total_cost, "margin": margin}

    col_p1, col_p2 = st.columns(2, gap="medium")
    with col_p1:
        p1 = render_plant("p1", "Plant 1")
    with col_p2:
        p2 = render_plant("p2", "Plant 2")

    st.divider()
    st.markdown("<h2 style='text-align:left;'>Final Analysis & Cost Breakup</h2>", unsafe_allow_html=True)
    res_c1, res_c2 = st.columns(2, gap="large")

    def render_breakdown_card(p_data, name):
        st.markdown(f"<div style='text-align:center;font-weight:bold;color:#1e293b;font-size:1.2rem;margin-bottom:10px;'>{name} (INR/MT)</div>", unsafe_allow_html=True)
        with st.container(border=True):
            def breakdown_row(label, val):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"<div class='material-label'>{label}</div>", unsafe_allow_html=True)
                c2.markdown(f"<div style='text-align:right;font-weight:500;font-size:15px;color:#334155;'>Rs.{val:,.2f}</div>", unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:6px;'></div>", unsafe_allow_html=True)

            breakdown_row("Iron Ore (Fines/Lumps/Pellets)", p_data["ore"])
            breakdown_row("Coking Coal / Met Coke / PCI", p_data["coal"])
            breakdown_row("Scrap HMS 80:20", p_data["scrap"])
            breakdown_row("Limestone / Dolomite", p_data["flux"])
            breakdown_row("Ferroalloys (SiMn, FeMn, FeSi)", p_data["alloy"])
            breakdown_row("Electricity", p_data["elec"])
            breakdown_row("Processing Cost", p_data["proc"])
            breakdown_row("Miscellaneous Expenses", p_data["misc"])
            breakdown_row("Finance Cost (Avg)", p_data["fin"])
            breakdown_row("Depreciation & Amortization", p_data["dep"])
            st.markdown("<hr style='border-top:1px solid #e2e8f0;margin:15px 0;'>", unsafe_allow_html=True)
            m1, m2 = st.columns(2)
            m1.metric("Total Cost (Ex-Works)", f"Rs.{p_data['total']:,.2f}")
            m2.metric("Mill Margin", f"Rs.{p_data['margin']:,.2f}", delta=f"{(p_data['margin']/mkt_price)*100:.2f}%")

    with res_c1:
        render_breakdown_card(p1, "Plant 1")
    with res_c2:
        render_breakdown_card(p2, "Plant 2")

    st.divider()
    if st.button("Generate PDF Report", key="cost_pdf"):
        pdf = Report_PDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 8, f"Product: {product} | Market Price: Rs. {mkt_price:,} | Conversion Rate: {ex_rate}", 0, 1)
        pdf.ln(5)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("Arial", "B", 9)
        headers = ["Cost Element", "Plant 1 (Rs./MT)", "Plant 2 (Rs./MT)"]
        widths = [90, 50, 50]
        for idx, h in enumerate(headers):
            pdf.cell(widths[idx], 10, h, 1, 0, "C", 1)
        pdf.ln()
        pdf.set_font("Arial", "", 9)
        elements = [
            ("Iron Ore (Fines/Lumps/Pellets)", "ore"), ("Coking Coal / Met Coke / PCI", "coal"), ("Scrap HMS 80:20", "scrap"),
            ("Limestone / Dolomite", "flux"), ("Ferroalloys (SiMn, FeMn, FeSi)", "alloy"), ("Electricity", "elec"),
            ("Processing Cost", "proc"), ("Miscellaneous Expenses", "misc"), ("Finance Cost (Avg)", "fin"), ("Depreciation & Amortization", "dep"),
        ]
        for label, key in elements:
            pdf.cell(widths[0], 10, label, 1)
            pdf.cell(widths[1], 10, f"{p1[key]:,.2f}", 1, 0, "R")
            pdf.cell(widths[2], 10, f"{p2[key]:,.2f}", 1, 0, "R")
            pdf.ln()
        pdf.set_font("Arial", "B", 9)
        pdf.cell(widths[0], 10, "Total Cost (Ex-Works)", 1, 0, "L", 1)
        pdf.cell(widths[1], 10, f"{p1['total']:,.2f}", 1, 0, "R", 1)
        pdf.cell(widths[2], 10, f"{p2['total']:,.2f}", 1, 0, "R", 1)
        pdf.ln()
        pdf.cell(widths[0], 10, "Mill Margin", 1, 0, "L", 1)
        pdf.cell(widths[1], 10, f"{p1['margin']:,.2f}", 1, 0, "R", 1)
        pdf.cell(widths[2], 10, f"{p2['margin']:,.2f}", 1, 0, "R", 1)
        unique_name = f"Steel_Cost_Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        st.download_button("Download PDF Report", data=_pdf_bytes(pdf), file_name=unique_name, mime="application/pdf")

    st.divider()
    with st.expander("Methodology & Logic"):
        st.markdown(
            "**Objective** - comparative cost to produce one MT of finished steel at two facilities, "
            "with resulting mill margins at the current market price.\n\n"
            "**Consumption norms** - Material Price x Consumption Norm = cost contribution per tonne. "
            "Costs are grouped into Raw Materials, Fluxes & Alloys, Power and OpEx.\n\n"
            "**Mill Margin** = Market Price - Total Cost (Ex-Works), also shown as a % of selling price."
        )
