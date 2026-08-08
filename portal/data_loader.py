"""
Data loader for the BigMint - AI Labs portal.

Reshapes the messy multi-header forecast/accuracy sheets into tidy per-product
frames, cached so each file is read once per session (@st.cache_data).

DATA SOURCE (public code, private data):
  * If st.secrets['data'] is set, the real files are pulled at runtime from a
    PRIVATE GitHub repo (see _fetch_private_data_dir) into a temp dir — nothing
    private is committed to this (public) repo.
  * With no secrets, it falls back to the bundled in-repo SAMPLE so the public
    code still runs. See .streamlit/secrets.toml.example.

Files (same layout in the private repo and the in-repo sample):
  accuracy_tables/forecast_forward.xlsx  - summary + 12-week forward path
  accuracy_tables/Accuracy_Table_11.xlsx   - week-wise actual/forecast (1 week ahead)
  accuracy_tables/Accuracy_Table_11_{4,8,12}W.xlsx - same, 4/8/12 weeks ahead
  calculators/HRC.csv             - calculators' dataset
"""
import os
import json
import base64
import tempfile
from urllib.parse import quote
import pandas as pd
import streamlit as st

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
PORTAL_DIR = os.path.dirname(os.path.abspath(__file__))              # <repo>/portal

# Data files as relative paths (identical in the private repo and the in-repo sample).
FF_NAME = "forecast_forward.xlsx"
LANDED_NAME = "landed_costs.xlsx"                  # weekly India duty-paid landed cost (Rebar/HRC sheets)
# Accuracy tables keyed by FORECAST HORIZON (weeks ahead). 1 = the original next-week table
# (Table_11); 4/8/12 are the back-tested longer-horizon runs. All 11 products in every one.
ACC_FILES = {1:  "Accuracy_Table_11.xlsx",
             4:  "Accuracy_Table_11_4W.xlsx",
             8:  "Accuracy_Table_11_8W.xlsx",
             12: "Accuracy_Table_11_12W.xlsx"}
HEADLINE_SHEET = "Ensemble_WgtMean"               # headline forecast line shown to Adani


# --- Data location: private GitHub repo (via st.secrets) or in-repo sample -----
def _data_cfg():
    """The [data] secrets block, or None when it isn't configured."""
    try:
        cfg = st.secrets.get("data", None)
    except Exception:
        cfg = None
    return cfg if cfg else None


@st.cache_data(ttl=25, show_spinner=False)
def _remote_sha(owner: str, repo: str, ref: str, token: str) -> str:
    """Current HEAD commit SHA of the data repo's ref. One cheap API call, cached ~25s
    (just under the 30s data poll) so a fresh push is noticed within a poll cycle without
    hammering the API on every path lookup. Returns "" on any error (degrade, don't crash)."""
    import requests
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{quote(ref)}"
        resp = requests.get(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.sha",
            "X-GitHub-Api-Version": "2022-11-28"}, timeout=15)
        resp.raise_for_status()
        return resp.text.strip()
    except Exception:
        return ""


@st.cache_resource(show_spinner="Loading data…")
def _fetch_private_data_dir(owner: str, repo: str, ref: str, token: str, sha: str) -> str:
    """Download the private data files from a GitHub repo into a temp dir and return its
    path. `sha` is the repo HEAD, used as a cache key: a new push changes it and forces a
    fresh download — that's what makes edits show up without an app restart. Uses the
    Contents API with the raw media type, so a fine-grained token with read-only 'Contents'
    access to just that repo is enough. Single swap-point for another backend (S3/GCS/etc.)."""
    import requests
    dest = tempfile.mkdtemp(prefix="bm_data_")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    at = sha or ref   # pin to the exact commit when known, so content matches the cache key
    # (path, required): the 4/8/12-week accuracy tables are optional — a data repo that hasn't
    # got them yet just loses those horizon tabs instead of falling back to the sample wholesale.
    rels = ((f"accuracy_tables/{FF_NAME}", True),
            (f"accuracy_tables/{LANDED_NAME}", True),
            *[(f"accuracy_tables/{fn}", w == 1) for w, fn in ACC_FILES.items()],
            ("calculators/HRC.csv", True))
    for rel, required in rels:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(rel)}?ref={at}"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 404 and not required:
            continue
        resp.raise_for_status()
        out = os.path.join(dest, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(resp.content)
    return dest


def _data_root() -> str:
    """Folder that holds accuracy_tables/ and calculators/: the fetched private-repo temp
    dir when secrets are set, else the repo root (in-repo sample). Not cached itself — it's
    cheap (a ~25s-cached SHA check) and MUST re-run each call so a new push re-points it at
    a fresh fetch. The download itself stays cached per-SHA in _fetch_private_data_dir."""
    cfg = _data_cfg()
    if cfg:
        try:
            sha = _remote_sha(cfg["github_owner"], cfg["github_repo"],
                              cfg.get("github_ref", "main"), cfg["github_token"])
            return _fetch_private_data_dir(
                cfg["github_owner"], cfg["github_repo"],
                cfg.get("github_ref", "main"), cfg["github_token"], sha)
        except Exception:
            st.warning("Private data fetch failed — showing the bundled sample instead.")
    return BASE


def acc_dir() -> str:
    """Folder holding the accuracy/forecast xlsx files."""
    return os.path.join(_data_root(), "accuracy_tables")


def calculators_csv() -> str:
    """Path to the calculators dataset CSV."""
    root = _data_root()
    # in-repo sample keeps the CSV under portal/calculators; the private repo puts it at calculators/
    base = PORTAL_DIR if root == BASE else root
    return os.path.join(base, "calculators", "HRC.csv")


def ff_path() -> str:
    """Absolute path to forecast_forward.xlsx (private temp dir or in-repo)."""
    return os.path.join(acc_dir(), FF_NAME)


def landed_path() -> str:
    """Absolute path to landed_costs.xlsx (private temp dir or in-repo)."""
    return os.path.join(acc_dir(), LANDED_NAME)


def acc_path(window: int) -> str:
    """Absolute path to an accuracy table for a horizon (1/4/8/12 weeks ahead)."""
    return os.path.join(acc_dir(), ACC_FILES[window])

# display name -> sheet/label used in the source files
STEEL_PRODUCTS = {
    "HRC":                   {"ff": "HRC",                 "acc": "HRC"},
    "HR Plate":              {"ff": "HR PLATE",            "acc": "HR PLATE"},
    "Rebar BF Mumbai":       {"ff": "REBAR BF MUMBAI",     "acc": "REBAR BF MUMBAI"},
    "Rebar IF Mumbai":       {"ff": "REBAR IF MUMBAI",     "acc": "REBAR IF MUMBAI"},
    "Rebar IF Raipur":       {"ff": "REBAR IF RAIPUR",     "acc": "REBAR IF RAIPUR"},
    "Structure (IF Raipur)": {"ff": "STRUCTURE IF RAIPUR", "acc": "STRUCTURE IF RAIPUR"},
    "HRC Mundra":            {"ff": "HRC MUNDRA",          "acc": "HRC MUNDRA"},
    "HR Plate Mundra":       {"ff": "HR PLATE MUNDRA",     "acc": "HR PLATE MUNDRA"},
    "Rebar BF Mundra":       {"ff": "REBAR BF MUNDRA",     "acc": "REBAR BF MUNDRA"},
    "Rebar IF Mundra":       {"ff": "REBAR IF MUNDRA",     "acc": "REBAR IF MUNDRA"},
    "Structure Mundra":      {"ff": "STRUCTURE MUNDRA",    "acc": "STRUCTURE MUNDRA"},
}


def _num(s):
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False).str.replace("₹", "", regex=False).str.strip(),
        errors="coerce",
    )


FLAT_THRESHOLD = 500.0   # INR/ton dead-band: |change| <= 500 => Flat


def direction_flag(delta, thr: float = FLAT_THRESHOLD) -> str:
    """Up / Down / Flat from a numeric change, with a +/-thr dead-band mapping to Flat."""
    if pd.isna(delta):
        return "Flat"
    if delta > thr:
        return "Up"
    if delta < -thr:
        return "Down"
    return "Flat"


def _mtime(path: str) -> float:
    """File modification time, passed into the cached readers as a cache key so an
    edited file is re-read on the next rerun. Without this, @st.cache_data would read
    each file only once per session (edits wouldn't show until a restart)."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def data_files() -> tuple:
    """Every data file the app reads. Used for change-detection + the sidebar caption."""
    return (ff_path(), landed_path(), *[acc_path(w) for w in ACC_FILES], calculators_csv())


def data_signature():
    """A value that changes whenever the data changes — polled to auto-refresh the app.
    Private-repo mode: the repo HEAD SHA (changes on every push, so a push shows up on its
    own within a poll cycle — no restart or manual clear). In-repo sample mode: max file
    mtime on disk. Cheap in both cases (a ~25s-cached SHA call, or a stat)."""
    cfg = _data_cfg()
    if cfg:
        return _remote_sha(cfg["github_owner"], cfg["github_repo"],
                           cfg.get("github_ref", "main"), cfg["github_token"])
    return max((_mtime(p) for p in data_files()), default=0.0)


@st.cache_data(show_spinner=False)
def _read_summary(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Summary")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_summary() -> pd.DataFrame:
    """Forecast_forward 'Summary' sheet (already tidy). Re-read when the file changes."""
    p = ff_path()
    return _read_summary(p, _mtime(p))


@st.cache_data(show_spinner=False)
def _read_forward(path: str, ff_sheet: str, mtime: float) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=ff_sheet, header=None)
    # row 0 = title, row 1 = column names, row 2+ = weekly rows
    data = raw.iloc[2:, :5].copy()
    data.columns = ["Date", "Week", "Forecast", "Delta", "Direction"]
    data = data.dropna(subset=["Date"])
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data["Week"] = pd.to_numeric(data["Week"], errors="coerce").astype("Int64")
    data["Forecast"] = _num(data["Forecast"])
    data["Delta"] = _num(data["Delta"])
    data["Direction"] = data["Delta"].map(direction_flag)   # +/-500 dead-band => Flat
    return data.dropna(subset=["Date", "Forecast"]).reset_index(drop=True)


def load_forward(ff_sheet: str) -> pd.DataFrame:
    """12-week forward path for one product. Returns Date, Week, Forecast, Delta, Direction.
    Re-read when the file changes."""
    p = ff_path()
    return _read_forward(p, ff_sheet, _mtime(p))


@st.cache_data(show_spinner=False)
def _read_landed(path: str, sheet: str, mtime: float) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, usecols=[0, 1], names=["Date", "Landed"], header=0)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Landed"] = _num(df["Landed"])
    return df.dropna(subset=["Date", "Landed"]).reset_index(drop=True)


def load_landed(sheet: str) -> pd.DataFrame:
    """Weekly India duty-paid landed cost for one product ('Rebar' or 'HRC' sheet).
    Returns Date, Landed. Empty frame if the file/sheet is missing. Re-read on file change."""
    p = landed_path()
    try:
        return _read_landed(p, sheet, _mtime(p))
    except Exception:
        return pd.DataFrame(columns=["Date", "Landed"])


def _sheet_metrics(actual: pd.Series, forecast: pd.Series, lag: int):
    """(MAPA, Delta, Directional) in points (0..1), recomputed EXACTLY as the accuracy sheet's own
    Excel formulas do — reference = the actual `lag` weeks earlier (the forecast horizon), with the
    same +/-500 dead-band.

    Why this exists: those three columns are FORMULA cells. openpyxl/pandas can only read a formula's
    CACHED result, and a workbook generated by a script and never opened+saved in Excel has no cache
    -> every metric reads blank (empty KPIs, all-'Wrong' directional bars, empty delta chart). Used
    to fill whatever the sheet didn't cache; cached values, when present, still win.

    Sheet formulas (row r, prev = actual at r-lag), reproduced 1:1:
      MAPA        = 1 - |A-F| / A
      cap         = MAX(0, 1 - |A-F| / MAX(|am|, |fm|))            am = A-prev, fm = F-prev
      Delta       = |fm|>=500 ? (|am|<500 ? BLANK : (am,fm opposite signs ? -cap : cap))
                              : (|am|<500 ? 1 : MAX(0, 1 - |am|/1000))
      Directional = |am|<500 ? (|fm|<500 ? 1 : 0) : (am*fm > 0 ? 1 : 0)
    """
    prev = actual.shift(lag)
    am, fm = actual - prev, forecast - prev
    err = (actual - forecast).abs()
    small_a, big_f = am.abs() < 500, fm.abs() >= 500

    mapa = 1 - err / actual.where(actual != 0)
    cap = (1 - err / pd.concat([am.abs(), fm.abs()], axis=1).max(axis=1)).clip(lower=0)
    cap = cap.where(am * fm >= 0, -cap)                       # opposite direction => negative capture
    delta = cap.where(~small_a).where(                        # |am|<500 & |fm|>=500 => blank
        big_f, (1 - am.abs() / 1000).clip(lower=0).where(~small_a, 1.0))
    dir_acc = ((am * fm) > 0).astype(float).where(~small_a, (~big_f).astype(float))

    both = actual.notna() & forecast.notna()
    valid = both & prev.notna()          # Delta/Directional need a reference week; MAPA does not
    return mapa.where(both), delta.where(valid), dir_acc.where(valid)


@st.cache_data(show_spinner=False)
def _read_accuracy(path: str, acc_label: str, mtime: float, lag: int = 1) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=HEADLINE_SHEET, header=None)

    # locate the product's block start column from the product-label row (row 0)
    labels = [str(x).strip() if pd.notna(x) else "" for x in raw.iloc[0].tolist()]
    if acc_label not in labels:
        return pd.DataFrame(columns=["Date", "Actual", "Forecast"])
    start = labels.index(acc_label)

    # Each product block is 7 cols: Actual, Forecast, MAE, MAPA (%), Delta (%), Directional (%), *Ratio.
    # The three accuracy metrics are READ STRAIGHT FROM THE SHEET — its own Excel formulas are the
    # source of truth. All three are POINTS (0..1); the UI multiplies by 100 to show a %. Blank weeks
    # (the sheet leaves some Delta/Directional cells empty) come through as NaN.
    dates = pd.to_datetime(raw.iloc[3:, 0], errors="coerce")
    df = pd.DataFrame({
        "Date": dates.values,
        "Actual":   _num(raw.iloc[3:, start]).values,
        "Forecast": _num(raw.iloc[3:, start + 1]).values,
        "AbsAcc":   _num(raw.iloc[3:, start + 3]).values,   # MAPA (%)
        "DeltaAcc": _num(raw.iloc[3:, start + 4]).values,   # Delta (%)
        "DirAcc":   _num(raw.iloc[3:, start + 5]).values,   # Directional (%)
    })
    # …but a formula cell with no cached result reads blank, so fill the gaps with the sheet's own
    # formulas re-run in pandas. Done BEFORE any row is dropped, so the "lag weeks back" reference
    # lines up with the sheet's row positions exactly.
    _mapa, _delta, _dir = _sheet_metrics(df["Actual"], df["Forecast"], lag)
    df["AbsAcc"] = df["AbsAcc"].fillna(_mapa)
    df["DeltaAcc"] = df["DeltaAcc"].fillna(_delta)
    df["DirAcc"] = df["DirAcc"].fillna(_dir)
    df = df.dropna(subset=["Date"]).dropna(subset=["Actual", "Forecast"], how="all").reset_index(drop=True)

    df["Delta"] = df["Forecast"] - df["Actual"]
    df["DeltaPct"] = (df["Delta"] / df["Actual"]) * 100
    # Direction labels (Up/Down/Flat) drive only the hover text on the directional chart — not any metric.
    prev_actual = df["Actual"].shift(1)
    df["PredDir"] = (df["Forecast"] - prev_actual).map(direction_flag)   # vs prior week's spot, +/-500 => Flat
    df["ActualDir"] = (df["Actual"] - prev_actual).map(direction_flag)
    df.loc[df.index[0], ["PredDir", "ActualDir"]] = "Flat"              # no prior reference
    df["Hit"] = df["DirAcc"] == 1.0                                     # sheet's per-week directional hit
    return df


def load_accuracy(window: int, acc_label: str) -> pd.DataFrame:
    """Week-wise Actual/Forecast for one product at a forecast horizon (1/4/8/12 weeks ahead).

    Returns Date, Actual, Forecast, Delta, DeltaPct, PredDir, ActualDir, Hit,
    AbsAcc, DirAcc, DeltaAcc (the last three in points, 0..1). Empty frame when the
    horizon's file/product block is absent. Re-read when the file changes.
    """
    path = acc_path(window)
    try:
        return _read_accuracy(path, acc_label, _mtime(path), window)
    except Exception:
        return pd.DataFrame(columns=["Date", "Actual", "Forecast"])


@st.cache_data(show_spinner=False)
def _read_accuracy_avgs(path: str, acc_label: str, mtime: float) -> dict:
    """The product block's AVERAGE row (row 3) — MAPA / Delta / Directional — read straight from the
    sheet's own averages (points -> %). None for a missing block or blank cell."""
    raw = pd.read_excel(path, sheet_name=HEADLINE_SHEET, header=None)
    labels = [str(x).strip() if pd.notna(x) else "" for x in raw.iloc[0].tolist()]
    if acc_label not in labels:
        return {"mapa": None, "dir_acc": None, "delta_acc": None}
    start = labels.index(acc_label)
    row = raw.iloc[2]                                 # row 3 (0-indexed) = the sheet's AVERAGE row

    def g(off):
        v = pd.to_numeric(row.iloc[start + off], errors="coerce")
        return float(v) * 100 if pd.notna(v) else None

    return {"mapa": g(3), "delta_acc": g(4), "dir_acc": g(5)}


def accuracy_averages(acc_label: str, window: int = 1) -> dict:
    """Absolute (MAPA), directional and delta accuracy for one product — taken from the accuracy
    table's OWN AVERAGE row (row 3 of the block). That row is an =AVERAGE() formula, so it reads
    blank on a workbook Excel never cached; each blank falls back to the mean of the week-wise
    column (same thing AVERAGE computes — blanks ignored). Re-read when the file changes."""
    p = acc_path(window)
    try:
        avgs = _read_accuracy_avgs(p, acc_label, _mtime(p))
    except Exception:
        avgs = {"mapa": None, "dir_acc": None, "delta_acc": None}
    if any(v is None for v in avgs.values()):
        wk = load_accuracy(window, acc_label)
        for key, col in (("mapa", "AbsAcc"), ("delta_acc", "DeltaAcc"), ("dir_acc", "DirAcc")):
            if avgs[key] is None and col in wk:
                m = wk[col].mean()
                avgs[key] = float(m) * 100 if pd.notna(m) else None
    return avgs


def last_actual_date():
    """The most recent date for which an ACTUAL spot price exists, across all products,
    read straight from the accuracy table (not the Summary sheet). This is the app's
    'data as of' date. Because load_accuracy is mtime-keyed, editing Accuracy_Table_11.xlsx
    updates this automatically — no need to also touch the Summary sheet. Returns a
    pandas Timestamp, or None if no actuals are present."""
    latest = None
    for meta in STEEL_PRODUCTS.values():
        av = load_accuracy(1, meta["acc"]).dropna(subset=["Actual"])
        if not av.empty:
            d = av["Date"].max()
            if latest is None or d > latest:
                latest = d
    return latest


def summary_row(summary: pd.DataFrame, ff_label: str):
    """Return the summary row (dict) for a product label, or None."""
    m = summary[summary["Product"].astype(str).str.strip() == ff_label]
    return m.iloc[0].to_dict() if not m.empty else None


# ===========================================================================
# ANALYST CALLS — editable content (text + PDF/PPT) stored in the private repo
# ---------------------------------------------------------------------------
# The Admin page writes `analyst_calls/calls.json` (the text) and uploads decks
# to `analyst_calls/files/<id>/…` in the SAME private GitHub repo, via the
# Contents API. Reading uses the read token; writing uses `github_write_token`
# (or falls back to `github_token` if that one has write access). With no
# secrets, the Analyst page shows SAMPLE_ANALYST_CALLS so the public app runs.
# ===========================================================================
ANALYST_JSON = "analyst_calls/calls.json"
ANALYST_FILES_DIR = "analyst_calls/files"
ANALYST_SECTIONS = ["Flats", "Longs", "Raw materials", "Imports & exports", "Outlook"]

# Shown when no private store is configured/reachable (plain text — escaped at render).
# "audiences" = list of roles that may see the call (deny-by-default). Empty/missing
# => unassigned: admins only, no other role sees it (the app filters via _call_visible
# in app.py; admins always see every call). Set the audience from the Admin call editor.
SAMPLE_ANALYST_CALLS = [
    {"id": "2026-06", "date": "2026-06-15", "month": "June 2026", "title": "Market outlook call",
     "summary": "Flat-to-soft HRC into Q3; raw-material support easing as iron-ore and coking-coal cool.",
     "sections": {"Flats": "HRC / CR / plate — sample commentary.",
                  "Longs": "Rebar / wire rod / structurals — sample commentary.",
                  "Raw materials": "Iron ore, coking coal & scrap — sample commentary.",
                  "Imports & exports": "Trade flows and landed-cost parity — sample commentary.",
                  "Outlook": "Near-term price direction — sample commentary."},
     "pdf": "", "ppt": "", "video": "", "audiences": []},
    {"id": "2026-05", "date": "2026-05-15", "month": "May 2026", "title": "Market outlook call",
     "summary": "Rebar firm on monsoon-led restocking; scrap stable.",
     "sections": {s: "" for s in ANALYST_SECTIONS}, "pdf": "", "ppt": "", "video": "", "audiences": []},
    {"id": "2026-04", "date": "2026-04-15", "month": "April 2026", "title": "Market outlook call",
     "summary": "Q1 review and forward view across flats and longs.",
     "sections": {s: "" for s in ANALYST_SECTIONS}, "pdf": "", "ppt": "", "video": "", "audiences": []},
]


def _read_token_cfg():
    """(owner, repo, ref, read_token) from st.secrets['data'], or None."""
    cfg = _data_cfg()
    if not cfg:
        return None
    try:
        return (cfg["github_owner"], cfg["github_repo"], cfg.get("github_ref", "main"), cfg["github_token"])
    except Exception:
        return None


def _write_token_cfg():
    """(owner, repo, ref, write_token) — prefers github_write_token, else github_token."""
    cfg = _data_cfg()
    if not cfg:
        return None
    token = cfg.get("github_write_token") or cfg.get("github_token")
    if not token:
        return None
    try:
        return (cfg["github_owner"], cfg["github_repo"], cfg.get("github_ref", "main"), token)
    except Exception:
        return None


def can_admin_write() -> bool:
    """True when write credentials are configured (enables the Admin save/upload)."""
    return _write_token_cfg() is not None


def data_sig() -> str:
    """Cache key + spinner-free identifier for the current data source."""
    tc = _read_token_cfg()
    return f"{tc[0]}/{tc[1]}@{tc[2]}" if tc else "sample"


def _gh_headers(token: str, raw: bool = False) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _gh_url(owner: str, repo: str, path: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(path)}"


def _gh_get_bytes(path: str):
    """Raw bytes of a repo file (read token), or None if missing/unconfigured."""
    tc = _read_token_cfg()
    if not tc:
        return None
    import requests
    owner, repo, ref, token = tc
    r = requests.get(f"{_gh_url(owner, repo, path)}?ref={ref}",
                     headers=_gh_headers(token, raw=True), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


@st.cache_data(show_spinner=False)
def _read_calls_json(sig: str):
    raw = _gh_get_bytes(ANALYST_JSON)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def load_analyst_calls() -> list:
    """Analyst-call dicts from the private repo (else the bundled sample), newest call first.

    Sorted here rather than at the render sites so the Analyst cards and the Admin
    picker stay in step. ISO 'date' sorts lexicographically; legacy entries carrying
    only 'month' have no 'date' and fall to the bottom.
    """
    calls = SAMPLE_ANALYST_CALLS
    if _read_token_cfg():
        data = _read_calls_json(data_sig())
        if data and isinstance(data.get("calls"), list):
            calls = data["calls"]
    return sorted(calls, key=lambda c: c.get("date") or "", reverse=True)


@st.cache_data(show_spinner=False)
def fetch_call_file(path: str, sig: str):
    """Bytes of an uploaded deck (cached per path), or None."""
    if not path:
        return None
    return _gh_get_bytes(path)


def _gh_get_sha(path: str):
    """Current blob sha of a file (needed to update), or None if it doesn't exist."""
    wc = _write_token_cfg()
    if not wc:
        return None
    import requests
    owner, repo, ref, token = wc
    r = requests.get(f"{_gh_url(owner, repo, path)}?ref={ref}",
                     headers=_gh_headers(token), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("sha")


def gh_put_file(path: str, content: bytes, message: str) -> None:
    """Create or update a file in the private repo (Contents API)."""
    wc = _write_token_cfg()
    if not wc:
        raise RuntimeError("No write token configured (github_write_token / github_token).")
    import requests
    owner, repo, ref, token = wc
    body = {"message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": ref}
    sha = _gh_get_sha(path)
    if sha:
        body["sha"] = sha
    r = requests.put(_gh_url(owner, repo, path), headers=_gh_headers(token), json=body, timeout=30)
    r.raise_for_status()


def gh_delete_file(path: str, message: str) -> None:
    """Delete a file from the private repo if it exists."""
    wc = _write_token_cfg()
    if not wc:
        return
    import requests
    owner, repo, ref, token = wc
    sha = _gh_get_sha(path)
    if not sha:
        return
    r = requests.delete(_gh_url(owner, repo, path), headers=_gh_headers(token),
                        json={"message": message, "sha": sha, "branch": ref}, timeout=30)
    r.raise_for_status()


def upload_call_file(call_id: str, filename: str, content: bytes) -> str:
    """Upload a deck under analyst_calls/files/<id>/ and return its repo path."""
    path = f"{ANALYST_FILES_DIR}/{call_id}/{filename}"
    gh_put_file(path, content, f"Upload {filename} for {call_id}")
    return path


def save_analyst_calls(calls: list) -> None:
    """Persist the calls list to analyst_calls/calls.json and refresh read caches."""
    payload = json.dumps({"calls": calls}, ensure_ascii=False, indent=2).encode("utf-8")
    gh_put_file(ANALYST_JSON, payload, "Update analyst calls content")
    _read_calls_json.clear()
    fetch_call_file.clear()


if __name__ == "__main__":
    # Self-check for _sheet_metrics — one row per branch of the sheet's Delta/Directional formulas.
    # Run: python portal/data_loader.py
    _a = pd.Series([100000.0, 100200, 102000, 101000, 101800, 102000])
    _f = pd.Series([100000.0, 100300, 103000, 102600, 101200, 102500])
    _mapa, _delta, _dir = _sheet_metrics(_a, _f, lag=1)
    assert abs(_mapa[1] - (1 - 100 / 100200)) < 1e-12, _mapa[1]
    assert pd.isna(_delta[0]) and pd.isna(_dir[0])                # no reference week
    assert _delta[1] == 1.0 and _dir[1] == 1.0                    # both moves inside the 500 dead-band
    assert abs(_delta[2] - (1 - 1000 / 2800)) < 1e-12 and _dir[2] == 1.0    # same direction, partial capture
    assert _delta[3] == 0.0 and _dir[3] == 0.0                    # forecast up, actual down
    assert abs(_delta[4] - 0.2) < 1e-12 and _dir[4] == 1.0        # forecast flat, actual moved 800
    assert pd.isna(_delta[5]) and _dir[5] == 0.0                  # actual flat, forecast moved => Delta blank
    print("_sheet_metrics OK")
