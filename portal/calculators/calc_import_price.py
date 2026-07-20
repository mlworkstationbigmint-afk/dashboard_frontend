# =============================================================================
# India: Import Price Calculator - Hot-Rolled Coil (HRC)
# Adapted for the BigMint - AI Labs portal: wrapped in render(), robust CSV path,
# fpdf/fpdf2-safe PDF output. Original calculation logic preserved.
# =============================================================================
import streamlit as st
import pandas as pd

import theme        # shared brand palette + infographic CSS/helpers (same as the rest of the portal)
import grid         # BigMint-themed AgGrid (blue header, sort/filter); falls back to st.dataframe

HRC_FULL_NAME = "HRC, Exy-Mumbai, India, 2.5-8mm / CTL, IS2062, Gr E250 Br."

DEFAULT_BCD_PCT = 7.5
DEFAULT_CESS_PCT = 10.0       # Social Welfare Surcharge on BCD
DEFAULT_SG_PCT = 12.0         # Safeguard duty
DEFAULT_SG_CESS_PCT = 10.0    # Cess on safeguard duty

# --- Defaults -----------------------------------------------------------------
# The calculator no longer reads FOB from the price sheet. Instead there is one
# org-wide set of defaults: the built-in fallback below, overridden by whatever
# the Admin saves (persisted in the DB under SETTINGS_KEY). Every user's private
# sandbox is seeded from these defaults; their edits stay in the session only.
SETTINGS_KEY = "landed_cost_defaults"

# g-dict key -> the human label used in the globals editor (order preserved).
# Only the truly org-wide knobs stay here; port + duties are now per-location (see LOC_DEFAULTS).
GMAP = {
    "domestic":      "Domestic benchmark (Rs./t)",
    "fx":            "FX (USD→INR)",
    "threshold_cif": "Threshold CIF ($/t)",
}

GVAR_DEFAULTS = {
    "Domestic benchmark (Rs./t)":   52450.0,
    "FX (USD→INR)":                 93.0,
    "Threshold CIF ($/t)":          675.0,
}

# Per-location duty/port defaults (moved out of the globals). Each location carries its own
# port handling + duty rates, all seeded from the old org-wide defaults but now editable per row.
_LOC_DUTY = {
    "port_inr":    2000.0,
    "bcd_pct":     DEFAULT_BCD_PCT,
    "cess_pct":    DEFAULT_CESS_PCT,
    "sg_pct":      DEFAULT_SG_PCT,
    "sg_cess_pct": DEFAULT_SG_CESS_PCT,
}

LOC_DEFAULTS = {
    "China":       {"fob": 470.0, "freight": 25.0, "fta": False, **_LOC_DUTY},
    "Russia":      {"fob": 460.0, "freight": 30.0, "fta": False, **_LOC_DUTY},
    "EU":          {"fob": 742.0, "freight": 35.0, "fta": False, **_LOC_DUTY},
    "Middle East": {"fob": 520.0, "freight": 15.0, "fta": True,  **_LOC_DUTY},
    "Custom 1":    {"fob": 535.0, "freight": 20.0, "fta": False, **_LOC_DUTY},
    "Custom 2":    {"fob": 535.0, "freight": 20.0, "fta": False, **_LOC_DUTY},
}

# Per-location duty/port fields -> the column header shown in the scenario table (order preserved).
# Session state is keyed `{p}_{field}_{region}`; these feed compute_landed as a per-row `g` override.
DUTY_COLS = {
    "port_inr":    "Port Rs./t",
    "bcd_pct":     "BCD %",
    "cess_pct":    "Cess on BCD %",
    "sg_pct":      "Safeguard %",
    "sg_cess_pct": "Cess on SG %",
}


def _effective_defaults():
    """Built-in defaults with the admin-saved values (if any) merged on top.
    Returns (gvars: {label: float}, locs: {region: {fob, freight, fta}}). Never
    raises — a missing DB / no saved row just yields the built-in fallback."""
    gvars = dict(GVAR_DEFAULTS)
    locs = {r: dict(v) for r, v in LOC_DEFAULTS.items()}
    try:
        import db
        saved = db.get_setting(SETTINGS_KEY)
    except Exception:
        saved = None
    if saved:
        for lbl, val in (saved.get("globals") or {}).items():
            if lbl in gvars:
                try:
                    gvars[lbl] = float(val)
                except (TypeError, ValueError):
                    pass
        for r, v in (saved.get("locations") or {}).items():
            if r in locs and isinstance(v, dict):
                out = dict(locs[r])
                for f in out:
                    if f in v:
                        out[f] = bool(v[f]) if f == "fta" else float(v[f])
                locs[r] = out
    return gvars, locs

CALC_CSS = """
<style>
/* Element breathing room: the global theme squeezes the block gap to 0.65rem, which reads as very
   compact on this dense page. Loosen the gap between stacked elements (injected after theme.py, so
   it wins). Scoped to the Calculators page since this CSS is only emitted while that page renders. */
[data-testid="stVerticalBlock"] { gap: 0.9rem !important; }
/* Column pairs (graph|globals) get a touch more horizontal air too. */
[data-testid="stHorizontalBlock"] { gap: 1.1rem !important; }
/* ...except the Calculate/Reset row: keep Reset hugging Calculate (override the wider gap above). */
.st-key-imp_btnrow [data-testid="stHorizontalBlock"] { gap: 0.4rem !important; }
/* Lowest-cost banner -> theme-blue gradient (was flat green) so it reads as the page headline. */
.kpi-banner { border-radius: 12px; padding: 13px 18px; margin: 2px 0 4px; font-size: 16px; font-weight: 700;
    color: #fff; background: linear-gradient(120deg, var(--bm-primary), var(--bm-primary-dark));
    box-shadow: 0 4px 16px rgba(2,76,161,.18); }
/* Management-view verdict box: semantic green (viable) / red (not viable). */
.mgmt-box { border-radius: 12px; padding: 14px 18px; margin-bottom: 4px; font-size: 15px; font-weight: 600; }
.mgmt-good { background: #e8f7ee; border: 1px solid #b7e4c7; color: #0b3d2e; }
.mgmt-bad  { background: #fdecea; border: 1px solid #f5b7b1; color: #7b241c; }
/* equation chip inside the methodology pipeline (reuses theme .bm-flow*). margin-top:auto pins it to
   the card bottom so all six equations align on one row (cards already stretch to equal height). */
.bm-eq { margin-top: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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


VIEW_OPTS = ["Graphical view", "Tabular view"]


def _sec(text, icon=""):
    """Prominent section heading (bigger than theme.section_title; accent left bar)."""
    ic = f"{icon} " if icon else ""
    st.markdown(f"<div class='bm-sec'>{ic}{text}</div>", unsafe_allow_html=True)


def _results_table(regions, results, domestic):
    """Tabular twin of the landed-cost chart (cheapest first) — themed AgGrid."""
    ordered = sorted(regions, key=lambda r: results[r]["landed"])
    df = pd.DataFrame([{
        "Location": r,
        "FTA": "Yes" if results[r]["is_fta"] else "No",
        "CFR": results[r]["cfr"],
        "TVD": results[r]["tvd"],
        "Safeguard": "Applied" if results[r]["sg_applied"] else "—",
        "Landed": results[r]["landed"],
        "vsDomestic": results[r]["diff"],
        "Decision": "IMPORT VIABLE" if results[r]["diff"] < 0 else "NOT VIABLE",
    } for r in ordered])

    def _cfg(gob, Js):
        usd = Js("function(p){return (p.value==null||isNaN(p.value))?''"
                 ":'$'+Math.round(p.value).toLocaleString('en-US');}")
        vsd = Js("function(p){if(p.value==null||isNaN(p.value))return '';var v=Math.round(p.value);"
                 "return (v<0?'-':'+')+'Rs.'+Math.abs(v).toLocaleString('en-IN');}")
        dec = Js("function(p){var v=(p.value||'').toString();"
                 "return {color:v.indexOf('NOT')>=0?'#D8382B':'#1F9D55','font-weight':'700'};}")
        gob.configure_column("Location", width=130)
        gob.configure_column("FTA", width=80)
        gob.configure_column("CFR", headerName="CFR $/t", type=["numericColumn"], valueFormatter=usd)
        gob.configure_column("TVD", headerName="TVD $/t", type=["numericColumn"], valueFormatter=usd)
        gob.configure_column("Safeguard", width=110)
        gob.configure_column("Landed", headerName="Landed Rs./t", type=["numericColumn"], valueFormatter=grid.JS_MONEY)
        gob.configure_column("vsDomestic", headerName="vs Domestic", type=["numericColumn"], valueFormatter=vsd)
        gob.configure_column("Decision", cellStyle=dec, width=150)

    # Height tuned to match the plotly chart's rendered footprint (see _landed_figure, height=400):
    # the AgGrid header + border sit inside this, so ~370 lines up with the graph it toggles with.
    grid.bm_grid(df, key="imp_results", configure=_cfg, page_size=0, height=370, fit=True)


# -----------------------------------------------------------------------------
# Global-variable side table  (small editable Value column beside the graph)
# -----------------------------------------------------------------------------
# Labels are the dict keys AND what the user sees; order is preserved (py3.7+).
GVAR_ORDER = [
    "Domestic benchmark (Rs./t)",
    "FX (USD→INR)",
    "Threshold CIF ($/t)",
]


def _read_globals(seed, p):
    """Render the editable global-variables table and return the `g` dict the
    engine expects. `seed` = the effective defaults (built-in + admin-saved); `p`
    namespaces the widget key so the admin editor and each user's sandbox stay
    independent. Streamlit persists edits under the key, so `seed` only applies
    on first load (or after a Reset bumps the version)."""
    df = pd.DataFrame({"Value": [seed[k] for k in GVAR_ORDER]}, index=GVAR_ORDER)
    df.index.name = "Variable"
    edited = st.data_editor(
        df, key=f"{p}_gvars_{st.session_state.get(f'{p}_gvars_ver', 0)}", width="stretch", hide_index=False,
        column_config={"Value": st.column_config.NumberColumn("Value", format="%.2f", step=0.5)},
    )
    v = {k: float(edited.loc[k, "Value"]) for k in GVAR_ORDER}
    return {
        "domestic": v["Domestic benchmark (Rs./t)"], "fx": v["FX (USD→INR)"],
        "threshold_cif": v["Threshold CIF ($/t)"],
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
        "Every origin is walked through the **same customs pipeline** — from the quoted FOB price to "
        "the final rupee cost at an Indian port — then measured against the domestic benchmark. "
        "Change any global variable or per-location input, press **Calculate**, and the whole chain re-solves."
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
        "<div style='margin:0 0 6px;font-size:16px;font-weight:700;color:#fff;'>Landed-Cost Engine</div>"
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
        ("factory",   "Cost &amp; Freight", "Origin quote + freight.",
         "CFR = FOB + Freight"),
        ("calculator", "Duty",            "Duty + cess (FTA waives).",
         "TVD = CFR + <b>BCD</b> + Cess"),
        ("target",    "Safeguard",        "Only if TVD &lt; threshold.",
         "(SG + Cess) if TVD &lt; Thr else 0"),
        ("gauge",     "USD cost",         "TVD + any safeguard.",
         "Cost$ = TVD + <b>SG</b>"),
        ("rupee",     "Rupee landed",     "Convert at FX, add port.",
         "Landed = Cost$&times;<b>FX</b> + Port"),
        ("trending",  "Verdict",          "Beat the domestic price.",
         "Landed &lt; <b>Domestic</b> &rArr; VIABLE"),
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


def render(is_admin=False):
    # CSS is injected OUTSIDE the fragment (once per full run) so a fragment rerun never re-emits
    # this <style> block. It carries global !important layout rules (block/column gaps); re-emitting
    # it on every edit tore the old style down for a frame — the whole page visibly reshuffled then
    # settled. Keeping it in the non-fragment wrapper (like the other calculators) holds it stable.
    st.markdown(CALC_CSS, unsafe_allow_html=True)
    _render_body(is_admin)


# @st.fragment: any edit (cell, checkbox, Calculate, Reset, global var) reruns ONLY this body — not
# the whole app script (sidebar, auth, other tabs, footer) — so the table stays responsive with no
# full-page reload. The page CSS lives in render() above, so it isn't re-injected on these reruns.
@st.fragment
def _render_body(is_admin=False):
    # Key namespace: the Admin editor ("adm") edits the org-wide defaults; every
    # other view ("imp") is a private per-session sandbox. Only one of the two
    # ever renders in a single script run (different pages), but the session-state
    # DATA keys persist across page switches, so they must not collide.
    p = "adm" if is_admin else "imp"

    gvars_def, locs_def = _effective_defaults()
    regions = list(locs_def.keys())
    st.session_state.setdefault(f"{p}_locs_ver", 0)     # bump -> new editor key -> fresh widget
    st.session_state.setdefault(f"{p}_gvars_ver", 0)
    for r in regions:
        st.session_state.setdefault(f"{p}_fob_{r}", locs_def[r]["fob"])
        st.session_state.setdefault(f"{p}_freight_{r}", locs_def[r]["freight"])
        st.session_state.setdefault(f"{p}_fta_{r}", locs_def[r]["fta"])
        for f in DUTY_COLS:
            st.session_state.setdefault(f"{p}_{f}_{r}", locs_def[r][f])

    # Reset callbacks run BEFORE widgets re-instantiate (on_click). Bumping the editor's key version
    # gives it a brand-new key, so the widget re-initialises from the fresh (default) DataFrame —
    # reliably clearing edited numbers AND the FTA checkboxes (popping the old key could miss cells).
    def _reset_locs():
        for r in regions:
            st.session_state[f"{p}_fob_{r}"] = locs_def[r]["fob"]
            st.session_state[f"{p}_freight_{r}"] = locs_def[r]["freight"]
            st.session_state[f"{p}_fta_{r}"] = locs_def[r]["fta"]
            for f in DUTY_COLS:
                st.session_state[f"{p}_{f}_{r}"] = locs_def[r][f]
        st.session_state[f"{p}_locs_ver"] += 1

    def _reset_gvars():
        st.session_state[f"{p}_gvars_ver"] += 1

    st.markdown(
        "<div class='bm-calc-head'>"
        f"<div class='bm-calc-title'>{theme.icon('calculator', 30)} Import Price Scenario Simulation</div>"
        "<div class='bm-calc-sub'>Hot-Rolled Coil &middot; landed-cost parity vs the domestic benchmark</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if is_admin:
        st.caption(f"{HRC_FULL_NAME}  ·  These are the **org-wide defaults** every user starts from. "
                   "Edit the globals and per-location inputs, press **Calculate**, then **Save as default** below.")
    else:
        st.caption(f"{HRC_FULL_NAME}  ·  Your private what-if sandbox — seeded from the org defaults; "
                   "edits reset when you log out.")

    # --- top: management verdict + lowest-cost banner (filled after compute) ---
    mgmt_ph = st.empty()
    banner_ph = st.empty()

    # --- graph on top (with a Graphical/Tabular switch), global variables to its side ---
    # vertical_alignment centre so the 8-row variables table sits balanced against the tall graph.
    col_chart, col_vars = st.columns([2.5, 1], gap="large", vertical_alignment="center")
    with col_chart:
        _sec("Landed cost by country vs domestic benchmark", theme.icon("trending"))
        with st.container(key="fc_view_box"):     # reuses theme.py's sliding-pill switch CSS
            view = st.segmented_control("View", VIEW_OPTS, default=VIEW_OPTS[0],
                                        key=f"{p}_view", label_visibility="collapsed")
        chart_ph = st.empty()
    with col_vars:
        theme.section_title("Global variables", theme.icon("gauge"))
        g = _read_globals(gvars_def, p)
        gv_dirty = any(float(g[k]) != float(gvars_def[lbl]) for k, lbl in GMAP.items())
        st.button("↺ Reset variables", key=f"{p}_gv_reset", on_click=_reset_gvars,
                  disabled=not gv_dirty, help="Reset all global variables to their defaults.")
    domestic = g["domestic"]
    view = view or VIEW_OPTS[0]                    # deselection falls back to the graph

    # --- per-location scenario table lives in its OWN fragment -----------------------------------
    # Buffered edits (cell numbers, FTA ticks) rerun ONLY this fragment, so the outputs below —
    # verdict banner, chart, FX-sensitivity grid, methodology — are never re-rendered while you type.
    # The heavy Plotly + AgGrid components stay mounted instead of re-mounting on every keystroke
    # (that re-mount was the "everything jumps then settles" flicker). Outputs redraw once, all
    # together, only when Calculate / Reset commits and fires a single full rerun.
    @st.fragment
    def _editor():
        _sec("Scenario inputs by location", theme.icon("factory"))
        ekey = f"{p}_locs_{st.session_state.get(f'{p}_locs_ver', 0)}"
        # Spot Rs./t is derived from the COMMITTED FOB (× FX), not the live edit buffer. Rebuilding
        # the editor's source frame from in-progress edits made Streamlit treat the data as changed
        # and drop the edit (the "FOB snaps back" bug); a stable frame lets edits persist to Calculate.
        loc_cols = {
            "Spot Rs./t": [float(st.session_state[f"{p}_fob_{r}"]) * g["fx"] for r in regions],
            "FTA": [bool(st.session_state[f"{p}_fta_{r}"]) for r in regions],
            "FOB $/t": [float(st.session_state[f"{p}_fob_{r}"]) for r in regions],
            "Freight $/t": [float(st.session_state[f"{p}_freight_{r}"]) for r in regions],
        }
        for f, col in DUTY_COLS.items():                # per-location port + duty columns
            loc_cols[col] = [float(st.session_state[f"{p}_{f}_{r}"]) for r in regions]
        loc_df = pd.DataFrame(loc_cols, index=regions)
        loc_df.index.name = "Location"
        loc_edit = st.data_editor(
            loc_df, key=ekey, width="stretch", hide_index=False,
            column_config={
                "Spot Rs./t": st.column_config.NumberColumn("Spot Rs./t", format="Rs.%.0f", disabled=True,
                            help="Derived: FOB × FX (read-only). Refreshes on Calculate."),
                "FTA": st.column_config.CheckboxColumn("FTA?", help="Waives BCD + its cess for this origin."),
                "FOB $/t": st.column_config.NumberColumn("FOB $/t", format="$%.0f", step=5.0,
                            help="Origin reference price — editable; press Calculate to apply."),
                "Freight $/t": st.column_config.NumberColumn("Freight $/t", format="$%.0f", step=1.0),
                "Port Rs./t": st.column_config.NumberColumn("Port Rs./t", format="Rs.%.0f", step=100.0,
                            help="Port handling & misc for this origin."),
                "BCD %": st.column_config.NumberColumn("BCD %", format="%.1f", step=0.5,
                            help="Basic customs duty (FTA waives it)."),
                "Cess on BCD %": st.column_config.NumberColumn("Cess on BCD %", format="%.1f", step=0.5,
                            help="Social welfare surcharge on BCD (FTA waives it)."),
                "Safeguard %": st.column_config.NumberColumn("Safeguard %", format="%.1f", step=0.5,
                            help="Safeguard duty, applied only if TVD < threshold."),
                "Cess on SG %": st.column_config.NumberColumn("Cess on SG %", format="%.1f", step=0.5,
                            help="Cess on the safeguard duty."),
            },
        )
        # pending = the editor buffer differs from the applied (committed) values -> lights Calculate
        # (Spot is derived/read-only, so it isn't part of the diff.)
        pending = any(
            float(loc_edit.loc[r, "FOB $/t"]) != float(st.session_state[f"{p}_fob_{r}"])
            or float(loc_edit.loc[r, "Freight $/t"]) != float(st.session_state[f"{p}_freight_{r}"])
            or bool(loc_edit.loc[r, "FTA"]) != bool(st.session_state[f"{p}_fta_{r}"])
            or any(float(loc_edit.loc[r, col]) != float(st.session_state[f"{p}_{f}_{r}"])
                   for f, col in DUTY_COLS.items())
            for r in regions
        )
        # reset enabled whenever anything (buffer or committed) differs from the effective defaults
        dirty = pending or any(
            float(st.session_state[f"{p}_fob_{r}"]) != float(locs_def[r]["fob"])
            or float(st.session_state[f"{p}_freight_{r}"]) != float(locs_def[r]["freight"])
            or bool(st.session_state[f"{p}_fta_{r}"]) != bool(locs_def[r]["fta"])
            or any(float(st.session_state[f"{p}_{f}_{r}"]) != float(locs_def[r][f])
                   for f in DUTY_COLS)
            for r in regions
        )
        with st.container(key="imp_btnrow"):           # scoped tight gap so Reset hugs Calculate
            bcol1, bcol2, bcol3 = st.columns([1, 1, 6], vertical_alignment="center")
            calc = bcol1.button("Calculate", key=f"{p}_calc", type="primary", disabled=not pending,
                                width="stretch")
            reset = bcol2.button("↺ Reset", key=f"{p}_reset", disabled=not dirty,
                                 width="stretch", help="Reset FOB / Freight / FTA back to the default values.")
            bcol3.caption("Edit FOB, freight, FTA, port or the per-origin duty rates, then press "
                          "**Calculate** to apply. Spot Rs./t = FOB × FX (read-only); **Reset** restores defaults.")
        # Both commit COMMITTED state that the outputs depend on, so both fire a single full rerun
        # (scope="app") to redraw the chart + tables together — the only time anything below re-renders.
        if reset:
            _reset_locs()
            st.rerun(scope="app")
        if calc:                                       # commit the buffer -> full rerun recomputes below
            for r in regions:
                st.session_state[f"{p}_fob_{r}"] = float(loc_edit.loc[r, "FOB $/t"])
                st.session_state[f"{p}_freight_{r}"] = float(loc_edit.loc[r, "Freight $/t"])
                is_fta = bool(loc_edit.loc[r, "FTA"])
                st.session_state[f"{p}_fta_{r}"] = is_fta
                for f, col in DUTY_COLS.items():
                    # FTA waives BCD + its cess -> force those rates to 0 so the table mirrors the math.
                    st.session_state[f"{p}_{f}_{r}"] = 0.0 if (is_fta and f in ("bcd_pct", "cess_pct")) \
                        else float(loc_edit.loc[r, col])
            st.rerun(scope="app")

        # --- Admin: persist the current values as the org-wide defaults for every user ---
        if is_admin:
            if st.button("💾 Save as default for all users", key=f"{p}_save", type="primary",
                         help="Press Calculate first to apply any pending edits, then save. These "
                              "values become the starting point in every user's sandbox."):
                try:
                    import db
                    db.set_setting(SETTINGS_KEY, {
                        "globals": {lbl: float(g[k]) for k, lbl in GMAP.items()},
                        "locations": {r: {"fob": float(st.session_state[f"{p}_fob_{r}"]),
                                          "freight": float(st.session_state[f"{p}_freight_{r}"]),
                                          "fta": bool(st.session_state[f"{p}_fta_{r}"]),
                                          **{f: float(st.session_state[f"{p}_{f}_{r}"]) for f in DUTY_COLS}}
                                      for r in regions},
                    })
                    st.success("Saved — these are now the defaults for all users.")
                except Exception as e:
                    st.error(f"Save failed: {e}")

    _editor()

    # --- compute with the committed inputs ---
    # Each origin gets its own effective g: the 3 global knobs (domestic/fx/threshold) merged with
    # that location's committed port + duty rates.
    def _gL(r):
        return {**g, **{f: float(st.session_state[f"{p}_{f}_{r}"]) for f in DUTY_COLS}}
    results = {
        r: compute_landed(st.session_state[f"{p}_fob_{r}"], st.session_state[f"{p}_freight_{r}"], st.session_state[f"{p}_fta_{r}"], _gL(r))
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
                # stable key (namespaced by the adm/imp `p`) so Streamlit updates the chart in place
                # on each cell edit instead of unmounting/re-plotting it — kills the redraw flash.
                st.plotly_chart(_landed_figure(regions, results, domestic),
                                width="stretch", config={"displayModeBar": False},
                                key=f"landed_chart_{p}")
            except Exception:
                st.bar_chart(pd.DataFrame({"Landed Rs./t": {r: results[r]["landed"] for r in regions}}))
            st.caption("Sorted cheapest → priciest. Colour shows distance from domestic parity "
                       "(green = cheaper, amber ≈ parity, red = pricier). Dashed line = domestic benchmark.")
        else:                                      # Tabular
            _results_table(regions, results, domestic)
            st.caption(f"Sorted cheapest → priciest vs domestic benchmark Rs.{int(domestic):,}/t.")

    # --- exchange-rate sensitivity ---
    _sec("Exchange-rate sensitivity (landed Rs./t)", theme.icon("rupee"))
    fx_rows = []
    for r in regions:
        row = {"Location": r}
        for fxs in [91.0, 93.0, 95.0]:
            res_fx = compute_landed(st.session_state[f"{p}_fob_{r}"], st.session_state[f"{p}_freight_{r}"],
                                    st.session_state[f"{p}_fta_{r}"], {**_gL(r), "fx": fxs})
            row[f"FX {fxs:.0f}"] = res_fx["landed"]
        fx_rows.append(row)

    def _fx_cfg(gob, Js):
        gob.configure_column("Location", width=130)
        for fxs in (91, 93, 95):
            gob.configure_column(f"FX {fxs}", type=["numericColumn"], valueFormatter=grid.JS_MONEY)
        gob.configure_grid_options(domLayout="autoHeight")

    grid.bm_grid(pd.DataFrame(fx_rows), key="imp_fx", configure=_fx_cfg, page_size=0, height=320)
    st.caption(f"Domestic benchmark for reference: Rs.{int(domestic):,}/t.")

    # --- methodology (modular, equation-heavy) + glossary ---
    _methodology_infographic()
    _glossary()
