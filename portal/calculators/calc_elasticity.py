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

    st.subheader("Price Elasticity Scenario Simulation - Hot Rolled Coil")

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

    def _reset_shocks():
        for c in columns:
            st.session_state[c] = 0.0
    st.button("Reset", key="elas_reset", on_click=_reset_shocks)

    # Rs. price impact of each driver's shock (current price x shock x elasticity),
    # shown beside its slider and reused by the Driver Contribution table below.
    contributions = shock_vector * elasticities
    price_contributions = current_price * contributions

    num_cols = 5
    rows = [columns[i:i + num_cols] for i in range(0, len(columns), num_cols)]
    for row in rows:
        cols = st.columns(len(row))
        for idx, col in enumerate(row):
            with cols[idx]:
                with st.container(border=True):
                    name = col.split("_lag")[0][:50]
                    st.slider(name, -20.0, 20.0, step=0.5, key=col)
                    st.caption(f"Price impact: Rs. {price_contributions[columns.index(col)]:+,.0f}")

    st.markdown("<h3 style='border-bottom:none;'>Driver Contribution</h3>", unsafe_allow_html=True)
    contrib_df = pd.DataFrame({
        "Factor": [c.split("_lag")[0] for c in columns],
        "Price Change (Rs.)": np.round(price_contributions, 0),
    }).sort_values(by="Price Change (Rs.)", ascending=False)
    st.dataframe(contrib_df, width="stretch")

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
