# =============================================================================
# Price Elasticity Calculator - Hot Rolled Coil (HRC)
# Adapted for the BigMint - AI Labs portal: wrapped in render(), fixed the
# malformed `header {` CSS block, robust CSV path, single fpdf/fpdf2-safe PDF
# output. Ridge-regression elasticity logic preserved.
# =============================================================================
import os
import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from fpdf import FPDF
from datetime import datetime

try:  # resolve the in-repo CSV path via the shared loader; fall back to a sibling file
    import data_loader as _dl
    CSV_PATH = _dl.calculators_csv()
except Exception:
    CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HRC - Copy.csv")

CALC_CSS = """
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #e6e9ef; border-radius: 10px;
    background-color: #ffffff; padding: 18px; margin-bottom: 10px;
}
div[data-testid="stContainer"] { border: none !important; background: transparent !important; padding: 0px !important; }
h2 { color: #073A7D; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
h3 { color: #1e293b; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
</style>
"""


def _pdf_bytes(pdf):
    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)


class Report_PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Price Elasticity and Forecast Analysis Report", 0, 1, "C")
        self.set_font("Arial", "I", 8)
        self.cell(0, 5, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, "C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


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


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)
    model, columns = load_model()

    st.subheader("Price Elasticity Calculator - Hot Rolled Coil")

    for col in columns:
        if col not in st.session_state:
            st.session_state[col] = 0.0

    shock_vector = np.array([st.session_state[col] / 100 for col in columns])
    elasticities = model.coef_

    top_col1, top_col2 = st.columns([1, 2])
    with top_col1:
        with st.container(border=True):
            st.markdown("**Current Market Price: HRC**")
            current_price = st.number_input("HRC Price (INR/t)", value=50000, step=500, label_visibility="collapsed")
            st.markdown(f"<h2>Rs.{current_price:,}</h2>", unsafe_allow_html=True)

    with top_col2:
        with st.container(border=True):
            st.markdown("**Analysis**")
            impact = np.dot(elasticities, shock_vector)
            final_price = current_price * np.exp(impact)
            price_change = final_price - current_price
            sub1, sub2, sub3 = st.columns(3)
            sub1.metric("Expected Change (%)", f"{round(impact*100, 2)} %")
            sub2.metric("Forecasted Price", f"Rs. {round(final_price, 0):,}")
            sub3.metric("Absolute Change", f"Rs. {round(price_change, 0):,}")

    st.markdown("<h3 style='border-bottom:none;'>Market Shocks (%)</h3>", unsafe_allow_html=True)
    num_cols = 5
    rows = [columns[i:i + num_cols] for i in range(0, len(columns), num_cols)]
    for row in rows:
        cols = st.columns(len(row))
        for idx, col in enumerate(row):
            with cols[idx]:
                with st.container(border=True):
                    name = col.split("_lag")[0][:50]
                    st.slider(name, -20.0, 20.0, step=0.5, key=col)

    st.markdown("<h3 style='border-bottom:none;'>Driver Contribution</h3>", unsafe_allow_html=True)
    contributions = shock_vector * elasticities
    contrib_df = pd.DataFrame({
        "Factor": [c.split("_lag")[0] for c in columns],
        "Contribution (%)": contributions * 100,
    }).sort_values(by="Contribution (%)", ascending=False)
    st.dataframe(contrib_df, width="stretch")

    st.divider()
    if st.button("Generate PDF Report", key="elas_pdf"):
        pdf = Report_PDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(0, 10, " Market Forecast Summary ", 0, 1, "L", 1)
        pdf.set_font("Arial", "", 10)
        pdf.ln(2)
        pdf.cell(90, 8, f"Current Market Price: Rs. {current_price:,}", 0, 0)
        pdf.cell(90, 8, f"Forecasted Price: Rs. {round(final_price, 0):,}", 0, 1)
        pdf.cell(90, 8, f"Expected Change (%): {round(impact*100, 2)}%", 0, 0)
        pdf.cell(90, 8, f"Absolute Change: Rs. {round(price_change, 0):,}", 0, 1)
        pdf.ln(10)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 10, " Driver Contribution Breakdown ", 0, 1, "L", 1)
        pdf.ln(2)
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font("Arial", "B", 9)
        headers = ["Market Factor / Driver", "Contribution (%)"]
        widths = [130, 60]
        for idx, h in enumerate(headers):
            pdf.cell(widths[idx], 10, h, 1, 0, "C", 1)
        pdf.ln()
        pdf.set_font("Arial", "", 9)
        for _, row in contrib_df.iterrows():
            clean_name = row["Factor"].encode("ascii", "ignore").decode("ascii")
            pdf.cell(widths[0], 10, clean_name, 1)
            pdf.cell(widths[1], 10, f"{row['Contribution (%)']:.4f}%", 1, 0, "R")
            pdf.ln()
        unique_name = f"HRC_Elasticity_Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        st.download_button("Download PDF Report", data=_pdf_bytes(pdf), file_name=unique_name, mime="application/pdf")

    st.divider()
    with st.expander("Methodology & Logic"):
        st.markdown(
            "**Objective** - estimate HRC price elasticity to market drivers and forecast price moves "
            "from user-defined shocks.\n\n"
            "**Model** - variables are log-transformed and differenced (percentage changes), then a Ridge "
            "regression (alpha=10) is fit; coefficients are read as elasticities.\n\n"
            "**Forecast** - Total Impact = sum(factor elasticity x factor % shock); "
            "Forecasted Price = Current Price x e^(Total Impact). The driver table shows each factor's contribution."
        )
