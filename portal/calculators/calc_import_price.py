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

import theme   # shared brand palette + infographic CSS/helpers (same as the rest of the portal)

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
/* Lowest-cost banner -> theme-blue gradient (was flat green) so it reads as the page headline. */
.kpi-banner { border-radius: 12px; padding: 13px 18px; margin: 2px 0 4px; font-size: 16px; font-weight: 700;
    color: #fff; background: linear-gradient(120deg, var(--bm-primary), var(--bm-primary-dark));
    box-shadow: 0 4px 16px rgba(2,76,161,.18); }
/* Management-view verdict box: semantic green (viable) / red (not viable). */
.mgmt-box { border-radius: 12px; padding: 14px 18px; margin-bottom: 4px; font-size: 15px; font-weight: 600; }
.mgmt-good { background: #e8f7ee; border: 1px solid #b7e4c7; color: #0b3d2e; }
.mgmt-bad  { background: #fdecea; border: 1px solid #f5b7b1; color: #7b241c; }
/* equation chip inside the methodology pipeline (reuses theme .bm-flow*). */
.bm-eq { margin-top: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; font-weight: 600; color: var(--bm-primary-dark);
    background: var(--bm-primary-soft); border: 1px solid #dbe7f7; border-radius: 8px;
    padding: 7px 9px; line-height: 1.45; width: 100%; box-sizing: border-box; }
.bm-eq b { color: var(--bm-accent); }
/* prominent page heading (bigger + more visible than the shared .bm-h). */
.bm-calc-head { margin: 4px 0 14px; padding: 0 0 13px; border-bottom: 2px solid var(--bm-primary-soft); }
.bm-calc-title { display: flex; align-items: center; gap: 13px; font-size: 30px; font-weight: 800;
    color: var(--bm-primary-dark); line-height: 1.15; letter-spacing: .2px; }
.bm-calc-title svg { color: var(--bm-primary); flex: 0 0 auto; }
.bm-calc-sub { margin: 7px 0 0 1px; color: #64748b; font-size: 14px; font-weight: 500; }
/* prominent section heading (bigger than .bm-h, accent left bar) — used across this calculator. */
.bm-sec { display: flex; align-items: center; gap: 10px; font-size: 19px; font-weight: 700;
    color: var(--bm-primary-dark); margin: 8px 0 12px; padding-left: 12px;
    border-left: 4px solid var(--bm-accent); }
.bm-sec svg { color: var(--bm-primary); flex: 0 0 auto; }
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


VIEW_OPTS = ["Graphical view", "Tabular view"]


def _sec(text, icon=""):
    """Prominent section heading (bigger than theme.section_title; accent left bar)."""
    ic = f"{icon} " if icon else ""
    st.markdown(f"<div class='bm-sec'>{ic}{text}</div>", unsafe_allow_html=True)


def _results_table(regions, results, domestic):
    """Tabular twin of the landed-cost chart (cheapest first)."""
    ordered = sorted(regions, key=lambda r: results[r]["landed"])
    rows = [{
        "Location": r,
        "FTA": "Yes" if results[r]["is_fta"] else "No",
        "CFR $/t": f"${results[r]['cfr']:,.0f}",
        "TVD $/t": f"${results[r]['tvd']:,.0f}",
        "Safeguard": "Applied" if results[r]["sg_applied"] else "—",
        "Landed Rs./t": f"Rs.{int(results[r]['landed']):,}",
        "vs Domestic": f"{'-' if results[r]['diff'] < 0 else '+'}Rs.{abs(int(results[r]['diff'])):,}",
        "Decision": "IMPORT VIABLE" if results[r]["diff"] < 0 else "NOT VIABLE",
    } for r in ordered]
    st.dataframe(pd.DataFrame(rows).set_index("Location"), width="stretch")


# -----------------------------------------------------------------------------
# Global-variable side table  (small editable Value column beside the graph)
# -----------------------------------------------------------------------------
# Labels are the dict keys AND what the user sees; order is preserved (py3.7+).
GVAR_ORDER = [
    "Domestic benchmark (Rs./t)",
    "FX (USD→INR)",
    "Threshold CIF ($/t)",
    "Port handling & misc (Rs./t)",
    "BCD %",
    "Cess on BCD %",
    "Safeguard duty %",
    "Cess on safeguard %",
]


def _read_globals(domestic_default):
    """Render the editable global-variables table and return the `g` dict the
    engine expects. Streamlit persists the edits under the widget key, so the
    seeded defaults only apply on first load."""
    seed = {
        "Domestic benchmark (Rs./t)": float(domestic_default),
        "FX (USD→INR)":               93.0,
        "Threshold CIF ($/t)":        675.0,
        "Port handling & misc (Rs./t)": 2000.0,
        "BCD %":                      DEFAULT_BCD_PCT,
        "Cess on BCD %":              DEFAULT_CESS_PCT,
        "Safeguard duty %":           DEFAULT_SG_PCT,
        "Cess on safeguard %":        DEFAULT_SG_CESS_PCT,
    }
    df = pd.DataFrame({"Value": [seed[k] for k in GVAR_ORDER]}, index=GVAR_ORDER)
    df.index.name = "Variable"
    edited = st.data_editor(
        df, key="imp_gvars", width="stretch", hide_index=False,
        column_config={"Value": st.column_config.NumberColumn("Value", format="%.2f", step=0.5)},
    )
    v = {k: float(edited.loc[k, "Value"]) for k in GVAR_ORDER}
    return {
        "domestic": v["Domestic benchmark (Rs./t)"], "fx": v["FX (USD→INR)"],
        "threshold_cif": v["Threshold CIF ($/t)"], "port_inr": v["Port handling & misc (Rs./t)"],
        "bcd_pct": v["BCD %"], "cess_pct": v["Cess on BCD %"],
        "sg_pct": v["Safeguard duty %"], "sg_cess_pct": v["Cess on safeguard %"],
    }


def _landed_figure(regions, results, domestic):
    """Diverging landed-cost bar chart vs the domestic benchmark line."""
    import plotly.graph_objects as go
    ordered = sorted(regions, key=lambda r: results[r]["landed"])
    landed_vals = [results[r]["landed"] for r in ordered]
    diffs = [results[r]["diff"] for r in ordered]     # landed - domestic (cheap < 0 < pricey)
    fig = go.Figure(go.Bar(
        x=ordered, y=landed_vals,
        marker=dict(
            color=diffs, cmid=0,                       # diverging: green (cheap) -> amber -> red (pricey)
            colorscale=[[0.0, theme.SUCCESS], [0.5, "#FBBF24"], [1.0, theme.DANGER]],
            line=dict(color="white", width=1.5), cornerradius=9,
        ),
        text=[f"Rs.{int(v):,}" for v in landed_vals], textposition="outside",
        textfont=dict(size=12, color="#0f172a"),
        cliponaxis=False, hovertemplate="<b>%{x}</b><br>Landed: Rs.%{y:,.0f}/t<extra></extra>",
    ))
    fig.add_hline(
        y=domestic, line=dict(color=theme.PRIMARY, width=2, dash="dash"),
        annotation_text=f"  Domestic Rs.{int(domestic):,}/t  ", annotation_position="top left",
        annotation_font=dict(color="white", size=12),
        annotation_bgcolor=theme.PRIMARY, annotation_bordercolor=theme.PRIMARY, annotation_borderpad=4,
    )
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=34, b=10),
                      plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="sans-serif", size=12, color="#334155"),
                      bargap=0.45, showlegend=False)
    fig.update_yaxes(title_text="Landed cost (Rs./t)", tickprefix="Rs.", tickformat=",.0f",
                     gridcolor="#f1f5f9", zeroline=False,
                     range=[0, max(max(landed_vals), domestic) * 1.13])
    fig.update_xaxes(title_text="", tickfont=dict(size=12.5, color="#0f172a"))
    return fig


def _methodology_infographic():
    """Modular, equation-heavy methodology block built from theme infographic CSS."""
    _sec("How landed cost is built", theme.icon("notes"))
    st.markdown(
        "<div class='bm-meth-hero'>"
        "<p>Every origin is walked through the <b>same customs pipeline</b> &mdash; from the quoted "
        "FOB price to the final rupee cost at an Indian port &mdash; then measured against the "
        "domestic benchmark. Change any global variable or per-location input, press "
        "<b>Calculate</b>, and the whole chain re-solves.</p></div>",
        unsafe_allow_html=True,
    )

    # Inputs -> engine -> outputs
    def _chips(items):
        return "".join(
            f"<div class='bm-chip'><span class='ic'>{theme.icon(ic, 15)}</span>{label}</div>"
            for ic, label in items
        )
    engine = (
        "<div class='bm-engine'>"
        "<div class='bm-engine-col bm-engine-in'><div class='bm-engine-h'>Inputs</div>"
        + _chips([("factory", "FOB &amp; freight per origin"),
                  ("rupee",   "Duties: BCD, cess, safeguard"),
                  ("gauge",   "FX &amp; port handling")]) +
        "</div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-core'>"
        f"<span class='ic'>{theme.icon('calculator', 26)}</span>"
        "<h4>Landed-cost engine</h4>"
        "<p>CFR &rarr; duty &rarr; safeguard &rarr; FX &rarr; port, applied identically to every source.</p></div>"
        "<div class='bm-engine-arrow'>&rarr;</div>"
        "<div class='bm-engine-col bm-engine-out'><div class='bm-engine-h'>Outputs</div>"
        + _chips([("rupee",    "Landed Rs./t per origin"),
                  ("target",   "Viable vs domestic?"),
                  ("trending", "Cheapest source")]) +
        "</div></div>"
    )
    st.markdown(engine, unsafe_allow_html=True)

    st.write("")
    _sec("The equation pipeline", theme.icon("notes"))
    steps = [
        ("factory",   "Cost &amp; Freight", "Origin quote plus ocean freight.",
         "CFR = FOB + Freight"),
        ("calculator", "Duty",            "Basic customs duty and its cess. FTA origins waive both.",
         "TVD = CFR + <b>BCD</b> + Cess"),
        ("target",    "Safeguard",        "Extra duty only when TVD sits below the threshold CIF.",
         "if TVD &lt; Thr &rarr; +<b>SG</b> + Cess"),
        ("gauge",     "USD cost",         "Total customs value plus any safeguard.",
         "Cost$ = TVD + SG"),
        ("rupee",     "Rupee landed",     "Convert at FX and add port handling &amp; misc.",
         "Landed = Cost$&times;<b>FX</b> + Port"),
        ("trending",  "Verdict",          "Beat the domestic benchmark to be import-viable.",
         "Landed &lt; <b>Domestic</b> &rArr; VIABLE"),
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
        ("FOB", "Free On Board", "Price of goods loaded at the origin port, before freight."),
        ("CFR", "Cost &amp; Freight", "FOB plus ocean freight to the destination port."),
        ("BCD", "Basic Customs Duty", "Standard import duty levied on the CFR value."),
        ("TVD", "Total Value for Duty", "CFR plus BCD and its cess &mdash; the customs base."),
        ("CIF", "Cost, Insurance &amp; Freight", "Reference value the safeguard threshold is set against."),
        ("FTA", "Free Trade Agreement", "Origin agreement that waives BCD and its cess."),
    ]
    grid = "<div class='bm-factor-grid'>" + "".join(
        f"<div class='bm-factor'><div class='ic' style='font-weight:800;font-size:12px;'>{abbr}</div>"
        f"<div><h5>{full}</h5><p>{desc}</p></div></div>"
        for abbr, full, desc in terms
    ) + "</div>"
    st.markdown(grid, unsafe_allow_html=True)


def render():
    st.markdown(CALC_CSS, unsafe_allow_html=True)

    fob_data, domestic_default, feed_as_of, feed_ok = fetch_fob_prices()
    regions = list(fob_data.keys())
    for r in regions:
        st.session_state.setdefault(f"fob_{r}", fob_data[r]["fob"])
        st.session_state.setdefault(f"freight_{r}", fob_data[r]["freight"])
        st.session_state.setdefault(f"fta_{r}", fob_data[r]["fta_default"])

    st.markdown(
        "<div class='bm-calc-head'>"
        f"<div class='bm-calc-title'>{theme.icon('calculator', 30)} Import Price Scenario Simulation</div>"
        "<div class='bm-calc-sub'>Hot-Rolled Coil &middot; landed-cost parity vs the domestic benchmark</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    feed_note = (f"Live feed · HRC - Copy.csv · latest assessment {feed_as_of}"
                 if feed_ok else "Feed HRC - Copy.csv not found · manual fallback values in use")
    st.caption(f"{HRC_FULL_NAME}  ·  {feed_note}")

    # --- top: management verdict + lowest-cost banner (filled after compute) ---
    mgmt_ph = st.empty()
    banner_ph = st.empty()
    st.write("")

    # --- graph on top (with a Graphical/Tabular switch), global variables to its side ---
    col_chart, col_vars = st.columns([2.5, 1], gap="large")
    with col_chart:
        _sec("Landed cost by country vs domestic benchmark", theme.icon("trending"))
        with st.container(key="fc_view_box"):     # reuses theme.py's sliding-pill switch CSS
            view = st.segmented_control("View", VIEW_OPTS, default=VIEW_OPTS[0],
                                        key="imp_view", label_visibility="collapsed")
        chart_ph = st.empty()
    with col_vars:
        theme.section_title("Global variables", theme.icon("gauge"))
        g = _read_globals(domestic_default)
    domestic = g["domestic"]
    view = view or VIEW_OPTS[0]                    # deselection falls back to the graph

    # --- customisable per-location table; edits stay pending until Calculate ---
    st.divider()
    _sec("Scenario inputs by location", theme.icon("factory"))
    # Spot = the price fetched from the CSV feed for that origin; blank for origins not in the file.
    def _spot(r):
        return float(fob_data[r]["fob"]) if not str(fob_data[r]["source"]).lower().startswith("manual") else None
    loc_df = pd.DataFrame({
        "Spot $/t": [_spot(r) for r in regions],
        "FTA": [bool(st.session_state[f"fta_{r}"]) for r in regions],
        "FOB $/t": [float(st.session_state[f"fob_{r}"]) for r in regions],
        "Freight $/t": [float(st.session_state[f"freight_{r}"]) for r in regions],
    }, index=regions)
    loc_df.index.name = "Location"
    loc_edit = st.data_editor(
        loc_df, key="imp_locs", width="stretch", hide_index=False,
        column_config={
            "Spot $/t": st.column_config.NumberColumn("Spot $/t", format="$%.0f", disabled=True,
                        help="Origin price fetched from the CSV feed (read-only; blank if not in the file)."),
            "FTA": st.column_config.CheckboxColumn("FTA?", help="Waives BCD + its cess for this origin."),
            "FOB $/t": st.column_config.NumberColumn("FOB $/t", format="$%.0f", step=5.0),
            "Freight $/t": st.column_config.NumberColumn("Freight $/t", format="$%.0f", step=1.0),
        },
    )
    # pending = the editor buffer differs from the applied (committed) values -> lights Calculate
    pending = any(
        float(loc_edit.loc[r, "FOB $/t"]) != float(st.session_state[f"fob_{r}"])
        or float(loc_edit.loc[r, "Freight $/t"]) != float(st.session_state[f"freight_{r}"])
        or bool(loc_edit.loc[r, "FTA"]) != bool(st.session_state[f"fta_{r}"])
        for r in regions
    )
    bcol1, bcol2 = st.columns([1, 4])
    calc = bcol1.button("Calculate", key="imp_calc", type="primary", disabled=not pending)
    bcol2.caption("Edit FOB, freight or FTA, then press **Calculate** to apply. "
                  "Spot is the feed reference (read-only).")
    if calc:                                       # commit the buffer -> everything recomputes below
        for r in regions:
            st.session_state[f"fob_{r}"] = float(loc_edit.loc[r, "FOB $/t"])
            st.session_state[f"freight_{r}"] = float(loc_edit.loc[r, "Freight $/t"])
            st.session_state[f"fta_{r}"] = bool(loc_edit.loc[r, "FTA"])

    # --- compute with the committed inputs ---
    results = {
        r: compute_landed(st.session_state[f"fob_{r}"], st.session_state[f"freight_{r}"], st.session_state[f"fta_{r}"], g)
        for r in regions
    }
    cheapest = min(regions, key=lambda r: results[r]["landed"])
    cl = results[cheapest]["landed"]
    viable = [r for r in regions if results[r]["diff"] < 0]

    # --- backfill the top placeholders + the chart ---
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
    mgmt_ph.markdown(f"<div class='mgmt-box {css}'>Management view: {msg}</div>", unsafe_allow_html=True)
    banner_ph.markdown(
        f"<div class='kpi-banner'>Lowest cost source: {cheapest} — Rs.{int(cl):,}/t"
        f"{'  (FTA)' if results[cheapest]['is_fta'] else ''}</div>",
        unsafe_allow_html=True,
    )

    with chart_ph.container():
        if view == VIEW_OPTS[0]:                   # Graphical
            try:
                st.plotly_chart(_landed_figure(regions, results, domestic),
                                width="stretch", config={"displayModeBar": False})
            except Exception:
                st.bar_chart(pd.DataFrame({"Landed Rs./t": {r: results[r]["landed"] for r in regions}}))
            st.caption("Sorted cheapest → priciest. Colour shows distance from domestic parity "
                       "(green = cheaper, amber ≈ parity, red = pricier). Dashed line = domestic benchmark.")
        else:                                      # Tabular
            _results_table(regions, results, domestic)
            st.caption(f"Sorted cheapest → priciest vs domestic benchmark Rs.{int(domestic):,}/t.")

    # --- exchange-rate sensitivity ---
    st.divider()
    _sec("Exchange-rate sensitivity (landed Rs./t)", theme.icon("rupee"))
    fx_rows = []
    for r in regions:
        row = {"Location": r}
        for fxs in [91.0, 93.0, 95.0]:
            res_fx = compute_landed(st.session_state[f"fob_{r}"], st.session_state[f"freight_{r}"],
                                    st.session_state[f"fta_{r}"], {**g, "fx": fxs})
            row[f"FX {fxs:.0f}"] = f"Rs.{int(res_fx['landed']):,}"
        fx_rows.append(row)
    st.dataframe(pd.DataFrame(fx_rows).set_index("Location"), width="stretch")
    st.caption(f"Domestic benchmark for reference: Rs.{int(domestic):,}/t.")

    # --- PDF snapshot ---
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

    # --- methodology (modular, equation-heavy) + glossary ---
    st.divider()
    _methodology_infographic()
    st.write("")
    _glossary()
