"""BigMint-themed AgGrid tables — custom design **plus** native features (click-to-sort,
column resize, per-column filter, pagination).

Why a component: st.dataframe renders on a <canvas>, so its header/cells can't be themed
via CSS (that's why the blue-header trick only worked on the HTML .bm-table). AgGrid is real
DOM, so `custom_css` restyles it fully while keeping the interactive grid features.

Safe by design: if `streamlit-aggrid` isn't installed (or fails to import on a given
Streamlit build), `bm_grid` falls back to st.dataframe so the app never crashes.
"""
import streamlit as st
import theme

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
    HAS_AGGRID = True
except Exception:                       # package missing or incompatible with this Streamlit build
    HAS_AGGRID = False
    JsCode = None                       # so callers can reference grid.JsCode safely

# --- BigMint grid skin: blue header (white, bold), rounded frame, soft zebra + hover ---
# Keys are CSS selectors; AgGrid class names (.ag-*) are stable across recent versions.
_GRID_CSS = {
    ".ag-root-wrapper": {"border": "1px solid #e8edf3 !important", "border-radius": "12px !important",
                         "overflow": "hidden !important"},
    ".ag-header": {"background-color": f"{theme.PRIMARY} !important", "border-bottom": "none !important"},
    ".ag-header-cell": {"color": "#ffffff !important"},
    ".ag-header-cell-text": {"color": "#ffffff !important", "font-weight": "800 !important",
                             "letter-spacing": ".2px"},
    # White icons ONLY in the header (sort/filter/menu). Do NOT whiten .ag-icon globally — that made
    # the pagination arrows white-on-white (invisible). Paging icons keep the theme's dark colour.
    ".ag-header .ag-icon, .ag-header-cell-menu-button .ag-icon": {"color": "#ffffff !important"},
    ".ag-row": {"font-size": "13.5px", "color": "#334155", "border-color": "#eef2f7 !important"},
    ".ag-row-odd": {"background-color": "#fbfcfe !important"},
    ".ag-row-hover": {"background-color": "#f2f7ff !important"},
    ".ag-paging-panel": {"color": theme.NEUTRAL, "border-top": "1px solid #eef2f7 !important",
                         "font-size": "12.5px"},
    # pagination nav buttons: accent them so they read as clickable, dim when disabled.
    ".ag-paging-button": {"cursor": "pointer"},
    ".ag-paging-button .ag-icon": {"color": f"{theme.PRIMARY} !important"},
    ".ag-paging-button.ag-disabled .ag-icon": {"color": "#c2ccd9 !important"},
}


def bm_grid(df, key, configure=None, height=560, page_size=50, fit=True):
    """Render `df` as a BigMint-skinned AgGrid.

    configure: optional callback(gob, Js) to set column headers / valueFormatters / row styles,
               where `gob` is a GridOptionsBuilder and `Js` is st_aggrid.JsCode. Called only when
               AgGrid is available.
    page_size: rows per page (falsy → no pagination). Default 50; the page-size dropdown offers
               10/25/50/100.
    """
    if df is None or len(df) == 0:
        st.info("No rows to display.")
        return None
    if not HAS_AGGRID:                  # graceful fallback — functional, just not themed
        st.dataframe(df, width="stretch", hide_index=True)
        st.caption("Themed grid unavailable — `streamlit-aggrid` is not installed.")
        return None

    gob = GridOptionsBuilder.from_dataframe(df)
    gob.configure_default_column(sortable=True, resizable=True, filter=True,
                                 suppressMovable=True, minWidth=90)
    # These tables are display-only, so keep sort/filter fully client-side: no data round-trip,
    # no Streamlit rerun on every click (that was re-mounting the grid = slow + janky animation).
    gob.configure_grid_options(animateRows=False, suppressColumnMoveAnimation=True,
                               suppressPropertyNamesCheck=True)
    if page_size:
        gob.configure_pagination(paginationAutoPageSize=False, paginationPageSize=page_size)
        # page-size dropdown options (default selection = page_size, which must be in the list)
        gob.configure_grid_options(paginationPageSizeSelector=[10, 25, 50, 100])
    if configure:
        configure(gob, JsCode)
    return AgGrid(df, gridOptions=gob.build(), key=key, height=height, theme="alpine",
                  custom_css=_GRID_CSS, allow_unsafe_jscode=True,
                  fit_columns_on_grid_load=fit, enable_enterprise_modules=False,
                  update_mode=GridUpdateMode.NO_UPDATE)


# --- shared JS formatters (only built when AgGrid is available; None otherwise) ---
# Reference these as grid.JS_* from callers; they're only ever used inside a `configure`
# callback, which bm_grid runs only when HAS_AGGRID is True — so None is never touched.
def js_row_bg(field, bg):
    """Row style that tints rows whose `field` is truthy (e.g. forecast rows)."""
    if not HAS_AGGRID:
        return None
    return JsCode("function(p){if(p.data && p.data['%s']){return {'background-color':'%s'};}}" % (field, bg))


if HAS_AGGRID:
    JS_MONEY = JsCode("function(p){return (p.value==null||isNaN(p.value))?''"
                      ":'INR'+Math.round(p.value).toLocaleString('en-IN');}")
    JS_DATE = JsCode("function(p){if(!p.value)return '';var d=new Date(p.value);"
                     "return isNaN(d)?p.value:d.toLocaleDateString('en-GB',"
                     "{day:'2-digit',month:'short',year:'numeric'});}")
    JS_DELTA = JsCode("function(p){if(p.value==null||isNaN(p.value))return '';"
                      "var v=Math.round(p.value);return (v>=0?'+':'')+v.toLocaleString('en-IN');}")
    # Delta + percent (reads sibling DeltaPct on the row) — used by the performance table.
    JS_DELTA_PCT = JsCode("function(p){if(p.value==null||isNaN(p.value))return '';"
                          "var v=Math.round(p.value);var s=(v>=0?'+':'')+v.toLocaleString('en-IN');"
                          "var pct=p.data?p.data.DeltaPct:null;"
                          "if(pct!=null&&!isNaN(pct))s+=' ('+(pct>=0?'+':'')+pct.toFixed(1)+'%)';return s;}")
    JS_DIR_FMT = JsCode("function(p){var v=(p.value||'').toString().toLowerCase();if(!v)return '';"
                        "if(v.indexOf('up')>=0||v.indexOf('ris')>=0)return '▲ Up';"
                        "if(v.indexOf('down')>=0||v.indexOf('fall')>=0||v.indexOf('fell')>=0)return '▼ Down';"
                        "return '→ Flat';}")
    JS_DIR_STYLE = JsCode("function(p){var v=(p.value||'').toString().toLowerCase();var c='#64748B';"
                          "if(v.indexOf('up')>=0||v.indexOf('ris')>=0)c='#1F9D55';"
                          "else if(v.indexOf('down')>=0||v.indexOf('fall')>=0||v.indexOf('fell')>=0)c='#D8382B';"
                          "return {color:c,'font-weight':'700'};}")
else:
    JS_MONEY = JS_DATE = JS_DELTA = JS_DELTA_PCT = JS_DIR_FMT = JS_DIR_STYLE = None
