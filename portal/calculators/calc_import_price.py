# =============================================================================
# India: Import Price Calculator - Hot-Rolled Coil (HRC)
# Adapted for the BigMint - AI Labs portal: wrapped in render(), robust CSV path,
# fpdf/fpdf2-safe PDF output. Original calculation logic preserved.
# =============================================================================
import os
import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime

HRC_FULL_NAME = "HRC, Exy-Mumbai, India, 2.5-8mm / CTL, IS2062, Gr E250 Br."

DEFAULT_BCD_PCT = 7.5
DEFAULT_CESS_PCT = 10.0       # Social Welfare Surcharge on BCD
DEFAULT_SG_PCT = 12.0         # Safeguard duty
DEFAULT_SG_CESS_PCT = 10.0    # Cess on safeguard duty

try:  # resolve the in-repo CSV path via the shared loader; fall back to a sibling file
    import data_loader as _dl
    CSV_PATH = _dl.calculators_csv()
except Exception:
    CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HRC - Copy.csv")
DOMESTIC_COL = "HRC, Exy-Mumbai, India, 2.5-8mm / CTL, IS2062, Gr E250 Br."
CSV_FOB_COLS = {
    "China":  "HRC, FOB Rizhao, China, 2.5mm",
    "Russia": "HRC, FOB Black Sea, Russia, 3mm, SAE1006",
    "EU":     "Platts North European HRC, EXW Ruhr",
}

CALC_CSS = """
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #e6e9ef; border-radius: 10px;
    background-color: #ffffff; padding: 16px; margin-bottom: 10px;
}
div[data-testid="stContainer"] { border: none !important; background: transparent !important; padding: 0px !important; }
h2, h3, h4 { color: #073A7D; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
label, .stMarkdown p { word-break: normal; overflow-wrap: anywhere; }
.kpi-banner { border-radius: 10px; padding: 14px 18px; margin: 4px 0 2px 0;
    font-size: 18px; font-weight: 700; color: #0b3d2e;
    background: #e8f7ee; border: 1px solid #b7e4c7; }
.mgmt-box { border-radius: 10px; padding: 14px 18px; margin-bottom: 6px; font-size: 16px; font-weight: 600; }
.mgmt-good { background: #e8f7ee; border: 1px solid #b7e4c7; color: #0b3d2e; }
.mgmt-bad  { background: #fdecea; border: 1px solid #f5b7b1; color: #7b241c; }
.group-head { font-size: 18px; font-weight: 800; margin: 6px 0 2px 0; color: #073A7D; }
.group-sub  { color: #64748b; font-size: 13px; margin-bottom: 8px; }
</style>
"""


def _pdf_bytes(pdf):
    """Return PDF bytes regardless of fpdf (str) or fpdf2 (bytearray)."""
    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)


def _csv_mtime():
    try:
        return os.path.getmtime(CSV_PATH)
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False)
def _load_price_feed(mtime):   # mtime in the cache key => re-read when the CSV changes
    """Read 'HRC - Copy.csv' and return (latest_row_dict, as_of_date) or (None, None)."""
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    except Exception:
        return None, None
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    for c in df.columns:
        if c == date_col:
            continue
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "").str.strip(), errors="coerce")
    df = df.dropna(how="all")
    if df.empty:
        return None, None
    last = df.iloc[-1]
    as_of = str(last[date_col])
    feed = {c: (None if pd.isna(last[c]) else float(last[c])) for c in df.columns if c != date_col}
    return feed, as_of


def load_price_feed():
    """Latest price-feed row. Re-read when the CSV changes."""
    return _load_price_feed(_csv_mtime())


def fetch_fob_prices():
    feed, as_of = load_price_feed()
    label = as_of if as_of else "-"
    data = {
        "China":       {"fob": 470.0, "freight": 25.0, "source": "Manual default", "source_date": "-", "fta_default": False},
        "Russia":      {"fob": 460.0, "freight": 30.0, "source": "Manual default", "source_date": "-", "fta_default": False},
        "EU":          {"fob": 742.0, "freight": 35.0, "source": "Manual default", "source_date": "-", "fta_default": False},
        "Middle East": {"fob": 520.0, "freight": 15.0, "source": "Manual entry (not in feed)", "source_date": "-", "fta_default": True},
        "Custom 1":    {"fob": 535.0, "freight": 20.0, "source": "Manual entry", "source_date": "-", "fta_default": False},
        "Custom 2":    {"fob": 535.0, "freight": 20.0, "source": "Manual entry", "source_date": "-", "fta_default": False},
    }
    if feed:
        for region, col in CSV_FOB_COLS.items():
            val = feed.get(col)
            if val is not None:
                data[region]["fob"] = float(val)
                data[region]["source"] = col
                data[region]["source_date"] = label
    domestic_default = 52450.0
    if feed and feed.get(DOMESTIC_COL) is not None:
        domestic_default = float(feed[DOMESTIC_COL])
    return data, domestic_default, as_of, bool(feed)


def compute_landed(fob, freight, is_fta, g):
    cfr = fob + freight
    if is_fta:
        bcd_pct, cess_pct = 0.0, 0.0
    else:
        bcd_pct, cess_pct = g["bcd_pct"], g["cess_pct"]
    bcd_amt = cfr * bcd_pct / 100.0
    cess_amt = bcd_amt * cess_pct / 100.0
    tvd = cfr + bcd_amt + cess_amt

    sg_applied = tvd < g["threshold_cif"]
    if sg_applied:
        sg_val = tvd * g["sg_pct"] / 100.0
        sg_cess = sg_val * g["sg_cess_pct"] / 100.0
        addl = sg_val + sg_cess
    else:
        addl = 0.0

    cost_usd = tvd + addl
    cost_inr = cost_usd * g["fx"]
    landed = cost_inr + g["port_inr"]
    diff = landed - g["domestic"]
    return {
        "fob": fob, "freight": freight, "cfr": cfr,
        "bcd_pct": bcd_pct, "bcd_amt": bcd_amt, "cess_pct": cess_pct, "cess_amt": cess_amt,
        "tvd": tvd, "sg_applied": sg_applied, "addl_usd": addl, "addl_inr": addl * g["fx"],
        "cost_usd": cost_usd, "cost_inr": cost_inr, "landed": landed, "diff": diff, "is_fta": is_fta,
    }


def breakdown_table(res, g):
    sg_label = "applied" if res["sg_applied"] else "not applied"
    return (
        "| Step | Value |\n|:--|--:|\n"
        f"| FOB | ${res['fob']:,.2f} |\n"
        f"| + Freight | ${res['freight']:,.2f} |\n"
        f"| **= CFR** | **${res['cfr']:,.2f}** |\n"
        f"| + BCD ({res['bcd_pct']:.1f}%) | ${res['bcd_amt']:,.2f} |\n"
        f"| + Cess on BCD ({res['cess_pct']:.1f}%) | ${res['cess_amt']:,.2f} |\n"
        f"| **= TVD** | **${res['tvd']:,.2f}** |\n"
        f"| + Safeguard ({sg_label}) | ${res['addl_usd']:,.2f} |\n"
        f"| **= Cost (USD/t)** | **${res['cost_usd']:,.2f}** |\n"
        f"| x FX (Rs.{g['fx']:.1f}) | Rs.{res['cost_inr']:,.0f} |\n"
        f"| + Port & misc | Rs.{g['port_inr']:,.0f} |\n"
        f"| **= Landed cost** | **Rs.{res['landed']:,.0f}** |\n"
    )


class HRC_Snapshot_PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "HRC Import Price Scenario Report", 0, 1, "C")
        self.set_font("Arial", "I", 8)
        self.cell(0, 5, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, "C")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


def build_pdf(pdf_rows, g, summary_line, best_line):
    pdf = HRC_Snapshot_PDF()
    pdf.add_page()
    epw = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Arial", "B", 9)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(epw, 5, summary_line)
    pdf.set_font("Arial", "", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(epw, 5, best_line)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 6, f"Domestic: Rs.{int(g['domestic']):,}/t  |  FX: {g['fx']}  |  Threshold CIF: ${int(g['threshold_cif'])}", 0, 1)
    pdf.ln(3)

    headers = ["Region", "FTA", "CFR $", "TVD $", "Safeguard", "Landed Rs.", "Decision"]
    widths = [28, 12, 24, 24, 26, 30, 46]
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", "B", 8)
    for w, h in zip(widths, headers):
        pdf.cell(w, 9, h, 1, 0, "C", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 8)
    for r in pdf_rows:
        pdf.cell(widths[0], 9, r["Region"], 1)
        pdf.cell(widths[1], 9, r["FTA"], 1, 0, "C")
        pdf.cell(widths[2], 9, r["CFR"], 1, 0, "R")
        pdf.cell(widths[3], 9, r["TVD"], 1, 0, "R")
        pdf.cell(widths[4], 9, r["SG"], 1, 0, "C")
        pdf.cell(widths[5], 9, r["Landed"], 1, 0, "R")
        pdf.set_text_color(0, 128, 0) if r["Viable"] else pdf.set_text_color(200, 0, 0)
        pdf.cell(widths[6], 9, r["Decision"], 1, 0, "C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
    return pdf


def render_card(region, res, g, fob_meta):
    with st.container(border=True):
        badge = "FTA - BCD waived" if res["is_fta"] else "Non-FTA - standard duty"
        st.markdown(f"#### {region}")
        st.caption(badge)

        if res["diff"] < 0:
            st.success(f"**IMPORT VIABLE**  \nSave Rs.{abs(int(res['diff'])):,}/t vs domestic")
        else:
            st.error(f"**NOT VIABLE**  \nSave Rs.{int(res['diff']):,}/t (Domestic cheaper)")

        st.metric("Landed cost at port", f"Rs.{int(res['landed']):,}")

        if res["sg_applied"]:
            st.warning(
                f"Safeguard: **APPLIED**  \n"
                f"Impact: +Rs.{int(res['addl_inr']):,}/t  \n"
                f"Reason: TVD ${res['tvd']:,.0f} < Threshold ${g['threshold_cif']:,.0f}"
            )
        else:
            st.caption(f"Safeguard: NOT APPLIED (TVD ${res['tvd']:,.0f} >= Threshold ${g['threshold_cif']:,.0f})")

        c1, c2 = st.columns(2)
        c1.number_input("FOB $/t", key=f"fob_{region}", step=5.0)
        c2.number_input("Freight $/t", key=f"freight_{region}", step=1.0)
        st.toggle("FTA origin", key=f"fta_{region}", help="Waives BCD + cess for this origin and moves it to the FTA group.")

        with st.expander("View breakdown  (FOB -> Duty -> FX -> Final)"):
            st.markdown(breakdown_table(res, g))
            st.caption(f"FOB source: {fob_meta['source']} (as of {fob_meta['source_date']})")


def render_group(title, subtitle, regions_sorted, results, g, fob_data, max_per_row=3):
    st.markdown(f"<div class='group-head'>{title}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='group-sub'>{subtitle}</div>", unsafe_allow_html=True)
    if not regions_sorted:
        st.caption("No regions in this group.")
        return
    for start in range(0, len(regions_sorted), max_per_row):
        chunk = regions_sorted[start:start + max_per_row]
        cols = st.columns(max_per_row)
        for col, region in zip(cols, chunk):
            with col:
                render_card(region, results[region], g, fob_data[region])


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)

    fob_data, domestic_default, feed_as_of, feed_ok = fetch_fob_prices()
    regions = list(fob_data.keys())
    for r in regions:
        st.session_state.setdefault(f"fob_{r}", fob_data[r]["fob"])
        st.session_state.setdefault(f"freight_{r}", fob_data[r]["freight"])
        st.session_state.setdefault(f"fta_{r}", fob_data[r]["fta_default"])

    st.subheader("India: Import Price Calculator - Hot-Rolled Coil")

    summary_ph = st.container()
    banner_ph = st.container()
    st.divider()

    st.markdown("##### Global assumptions")
    gc1, gc2, gc3, gc4 = st.columns(4)
    with gc1:
        domestic = st.number_input("Domestic benchmark (Rs./t)", value=int(domestic_default), step=50)
        st.caption(HRC_FULL_NAME)
    with gc2:
        fx = st.number_input("FX  (USD -> INR)", value=93.0, step=0.5)
    with gc3:
        threshold_cif = st.number_input("Threshold CIF ($/t)", value=675, step=5)
    with gc4:
        port_inr = st.number_input("Port handling & misc (Rs./t)", value=2000, step=100)

    with st.expander("Duty rates (common defaults)"):
        dc1, dc2, dc3, dc4 = st.columns(4)
        bcd_pct = dc1.number_input("BCD %", value=DEFAULT_BCD_PCT, step=0.5)
        cess_pct = dc2.number_input("Cess on BCD %", value=DEFAULT_CESS_PCT, step=0.5)
        sg_pct = dc3.number_input("Safeguard duty %", value=DEFAULT_SG_PCT, step=0.5)
        sg_cess_pct = dc4.number_input("Cess on safeguard %", value=DEFAULT_SG_CESS_PCT, step=0.5)
        st.caption("FTA origins automatically waive BCD + its cess. Safeguard applies whenever TVD < threshold.")

    g = {
        "domestic": domestic, "fx": fx, "threshold_cif": threshold_cif, "port_inr": port_inr,
        "bcd_pct": bcd_pct, "cess_pct": cess_pct, "sg_pct": sg_pct, "sg_cess_pct": sg_cess_pct,
    }

    results = {
        r: compute_landed(st.session_state[f"fob_{r}"], st.session_state[f"freight_{r}"], st.session_state[f"fta_{r}"], g)
        for r in regions
    }
    cheapest = min(regions, key=lambda r: results[r]["landed"])
    cl = results[cheapest]["landed"]
    viable = [r for r in regions if results[r]["diff"] < 0]

    with summary_ph:
        if viable:
            best_v = min(viable, key=lambda r: results[r]["landed"])
            msg = (f"{len(viable)} of {len(regions)} sources viable. "
                   f"Cheapest viable: {best_v} at Rs.{int(results[best_v]['landed']):,}/t "
                   f"(save Rs.{int(domestic - results[best_v]['landed']):,}/t vs domestic Rs.{int(domestic):,}).")
            css = "mgmt-good"
        else:
            msg = (f"Imports not viable. Domestic Rs.{int(domestic):,}/t beats the cheapest import "
                   f"({cheapest} Rs.{int(cl):,}/t) by Rs.{int(cl - domestic):,}/t.")
            css = "mgmt-bad"
        st.markdown(f"<div class='mgmt-box {css}'>Management view: {msg}</div>", unsafe_allow_html=True)

    with banner_ph:
        st.markdown(
            f"<div class='kpi-banner'>Lowest cost source: {cheapest} - Rs.{int(cl):,}/t"
            f"{'  (FTA)' if results[cheapest]['is_fta'] else ''}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("##### Landed cost by country vs domestic benchmark")
    try:
        import plotly.graph_objects as go
        ordered_chart = sorted(regions, key=lambda r: results[r]["landed"])
        landed_vals = [results[r]["landed"] for r in ordered_chart]
        diffs = [results[r]["diff"] for r in ordered_chart]   # landed - domestic (cheap < 0 < pricey)
        fig = go.Figure(go.Bar(
            x=ordered_chart, y=landed_vals,
            marker=dict(
                color=diffs, cmid=0,                          # diverging: green (cheap) -> amber -> red (pricey)
                colorscale=[[0.0, "#15A34A"], [0.5, "#FBBF24"], [1.0, "#E11D48"]],
                line=dict(color="white", width=1.5), cornerradius=9,
            ),
            text=[f"Rs.{int(v):,}" for v in landed_vals], textposition="outside",
            textfont=dict(size=12, color="#0f172a"),
            cliponaxis=False, hovertemplate="<b>%{x}</b><br>Landed: Rs.%{y:,.0f}/t<extra></extra>",
        ))
        fig.add_hline(
            y=domestic, line=dict(color="#024CA1", width=2, dash="dash"),
            annotation_text=f"  Domestic Rs.{int(domestic):,}/t  ", annotation_position="top left",
            annotation_font=dict(color="white", size=12),
            annotation_bgcolor="#024CA1", annotation_bordercolor="#024CA1", annotation_borderpad=4,
        )
        fig.update_layout(height=400, margin=dict(l=10, r=10, t=34, b=10),
                          plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="sans-serif", size=12, color="#334155"),
                          bargap=0.45, showlegend=False)
        fig.update_yaxes(title_text="Landed cost (Rs./t)", tickprefix="Rs.", tickformat=",.0f",
                         gridcolor="#f1f5f9", zeroline=False,
                         range=[0, max(max(landed_vals), domestic) * 1.13])
        fig.update_xaxes(title_text="", tickfont=dict(size=12.5, color="#0f172a"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        st.bar_chart(pd.DataFrame({"Landed Rs./t": {r: results[r]["landed"] for r in regions}}))
    st.caption("Sorted cheapest → priciest. Colour shows distance from domestic parity "
               "(green = cheaper, amber ≈ parity, red = pricier). Dashed line = domestic benchmark.")

    st.markdown("##### Exchange-rate sensitivity (landed Rs./t)")
    fx_rows = []
    for r in regions:
        row = {"Region": r}
        for fxs in [91.0, 93.0, 95.0]:
            res_fx = compute_landed(st.session_state[f"fob_{r}"], st.session_state[f"freight_{r}"],
                                    st.session_state[f"fta_{r}"], {**g, "fx": fxs})
            row[f"FX {fxs:.0f}"] = f"Rs.{int(res_fx['landed']):,}"
        fx_rows.append(row)
    st.dataframe(pd.DataFrame(fx_rows).set_index("Region"), use_container_width=True)
    st.caption(f"Domestic benchmark for reference: Rs.{int(domestic):,}/t.")

    with st.expander("FOB price sources & disclosure"):
        if feed_ok:
            st.success(f"Live feed: 'HRC - Copy.csv' loaded - latest assessment dated {feed_as_of}.")
        else:
            st.warning("Feed 'HRC - Copy.csv' not found - showing manual fallback values.")
        src_df = pd.DataFrame([
            {"Region": r, "FOB $/t": st.session_state[f"fob_{r}"], "Freight $/t": st.session_state[f"freight_{r}"],
             "Source": fob_data[r]["source"], "As of": fob_data[r]["source_date"]}
            for r in regions
        ]).set_index("Region")
        st.dataframe(src_df, use_container_width=True)

    st.divider()

    fta_regions = sorted([r for r in regions if st.session_state[f"fta_{r}"]], key=lambda r: results[r]["landed"])
    non_fta_regions = sorted([r for r in regions if not st.session_state[f"fta_{r}"]], key=lambda r: results[r]["landed"])

    render_group("FTA countries", "BCD waived - sorted cheapest to priciest", fta_regions, results, g, fob_data)
    st.markdown("&nbsp;", unsafe_allow_html=True)
    render_group("Non-FTA countries", "Standard duties - sorted cheapest to priciest", non_fta_regions, results, g, fob_data)

    st.divider()
    ordered = sorted(regions, key=lambda r: results[r]["landed"])
    pdf_data = [{
        "Region": r,
        "FTA": "Yes" if results[r]["is_fta"] else "No",
        "CFR": f"${results[r]['cfr']:,.0f}",
        "TVD": f"${results[r]['tvd']:,.0f}",
        "SG": "Applied" if results[r]["sg_applied"] else "No",
        "Landed": f"Rs.{int(results[r]['landed']):,}",
        "Decision": "IMPORT VIABLE" if results[r]["diff"] < 0 else "NOT VIABLE",
        "Viable": results[r]["diff"] < 0,
    } for r in ordered]

    if viable:
        bv = min(viable, key=lambda r: results[r]["landed"])
        summary_line = (f"Summary: {len(viable)} of {len(regions)} sources viable. "
                        f"Cheapest viable {bv} at Rs.{int(results[bv]['landed']):,}/t.")
    else:
        summary_line = (f"Summary: Imports not viable. Domestic Rs.{int(domestic):,}/t beats cheapest import "
                        f"({cheapest} Rs.{int(cl):,}/t) by Rs.{int(cl - domestic):,}/t.")
    best_line = f"Lowest cost source: {cheapest} at Rs.{int(cl):,}/t. Feed as of {feed_as_of if feed_as_of else 'n/a'}."

    if st.button("Generate PDF Report", key="imp_pdf"):
        pdf = build_pdf(pdf_data, g, summary_line, best_line)
        unique_name = f"HRC_Snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        st.download_button("Download PDF Report", data=_pdf_bytes(pdf), file_name=unique_name, mime="application/pdf")

    st.divider()
    with st.container(border=True):
        st.subheader("Glossary of Terms")
        g_col1, g_col2 = st.columns(2)
        with g_col1:
            st.write("**FOB:** Free On Board")
            st.write("**CFR:** Cost and Freight")
            st.write("**BCD:** Basic Custom Duty")
        with g_col2:
            st.write("**TVD:** Total Value for Duty")
            st.write("**CIF:** Cost, Insurance, and Freight")
            st.write("**FTA:** Free Trade Agreement")

    with st.expander("Methodology & Logic"):
        st.markdown(
            "**Objective** - Determine the landed cost of HRC imports into India per origin and "
            "compare each against the domestic benchmark to flag viability and the cheapest source.\n\n"
            "**Data feed** - China/Russia/EU FOB and the domestic Exy-Mumbai benchmark are read from the "
            "latest row of 'HRC - Copy.csv'. FX and Threshold CIF are user inputs. Middle East and Custom "
            "origins are entered manually.\n\n"
            "**CFR** = FOB + Freight. **TVD** = CFR + BCD + Cess (FTA waives BCD + cess). "
            "Safeguard duty + its cess apply when TVD < Threshold. "
            "**Landed** = (TVD + Safeguard) x FX + Port & misc. Landed < Domestic => IMPORT VIABLE."
        )
