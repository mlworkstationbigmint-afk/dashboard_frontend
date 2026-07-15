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
  accuracy_tables/Accuracy_Table_11.xlsx - week-wise actual/forecast
  calculators/HRC - Copy.csv             - calculators' dataset
"""
import os
import json
import base64
import tempfile
from urllib.parse import quote
import numpy as np
import pandas as pd
import streamlit as st

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
PORTAL_DIR = os.path.dirname(os.path.abspath(__file__))              # <repo>/portal

# Data files as relative paths (identical in the private repo and the in-repo sample).
FF_NAME = "forecast_forward.xlsx"
ACC_FILES = {"11-week": "Accuracy_Table_11.xlsx"}   # 6/16-week retired; app runs off Table_11
HEADLINE_SHEET = "Ensemble_WgtMean"               # headline forecast line shown to Adani


# --- Data location: private GitHub repo (via st.secrets) or in-repo sample -----
def _data_cfg():
    """The [data] secrets block, or None when it isn't configured."""
    try:
        cfg = st.secrets.get("data", None)
    except Exception:
        cfg = None
    return cfg if cfg else None


@st.cache_resource(show_spinner="Loading data…")
def _fetch_private_data_dir(owner: str, repo: str, ref: str, token: str) -> str:
    """Download the private data files from a GitHub repo into a temp dir (once per
    deploy) and return its path. Uses the Contents API with the raw media type, so a
    fine-grained token with read-only 'Contents' access to just that repo is enough.
    This function body is the single swap-point for another backend (S3/GCS/etc.)."""
    import requests
    dest = tempfile.mkdtemp(prefix="bm_data_")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    rels = (f"accuracy_tables/{FF_NAME}",
            *[f"accuracy_tables/{fn}" for fn in ACC_FILES.values()],
            "calculators/HRC - Copy.csv")
    for rel in rels:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(rel)}?ref={ref}"
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        out = os.path.join(dest, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(resp.content)
    return dest


@st.cache_resource(show_spinner=False)
def _data_root() -> str:
    """Folder that holds accuracy_tables/ and calculators/: the fetched private-repo
    temp dir when secrets are set, else the repo root (in-repo sample). Cached so the
    fetch (and any fallback warning) happens once per deploy."""
    cfg = _data_cfg()
    if cfg:
        try:
            return _fetch_private_data_dir(
                cfg["github_owner"], cfg["github_repo"],
                cfg.get("github_ref", "main"), cfg["github_token"])
        except Exception:
            st.warning("Private data fetch failed — showing the bundled sample instead.")
    return BASE


def acc_dir() -> str:
    """Folder holding the accuracy/forecast xlsx files."""
    return os.path.join(_data_root(), "accuracy_tables")


def calculators_csv(name: str = "HRC - Copy.csv") -> str:
    """Path to a calculators dataset CSV."""
    root = _data_root()
    # in-repo sample keeps the CSV under portal/calculators; the private repo puts it at calculators/
    base = PORTAL_DIR if root == BASE else root
    return os.path.join(base, "calculators", name)


def ff_path() -> str:
    """Absolute path to forecast_forward.xlsx (private temp dir or in-repo)."""
    return os.path.join(acc_dir(), FF_NAME)


def acc_path(window: str) -> str:
    """Absolute path to an accuracy table (private temp dir or in-repo)."""
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


FLAT_THRESHOLD = 500.0   # Rs./ton dead-band: |change| <= 500 => Flat


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
    return (ff_path(), *[acc_path(w) for w in ACC_FILES], calculators_csv())


def data_signature() -> float:
    """A single number that changes whenever ANY data file changes on disk.
    Cheap (stat only, NOT cached) — the app polls this to auto-refresh when a
    file in accuracy_tables/ (or the calculators CSV) is edited, so updates show
    up on their own with no manual refresh or restart."""
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
def _read_accuracy(path: str, acc_label: str, mtime: float) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=HEADLINE_SHEET, header=None)

    # locate the product's block start column from the product-label row (row 0)
    labels = [str(x).strip() if pd.notna(x) else "" for x in raw.iloc[0].tolist()]
    if acc_label not in labels:
        return pd.DataFrame(columns=["Date", "Actual", "Forecast"])
    start = labels.index(acc_label)

    dates = pd.to_datetime(raw.iloc[3:, 0], errors="coerce")
    actual = _num(raw.iloc[3:, start])
    forecast = _num(raw.iloc[3:, start + 1])
    df = pd.DataFrame({"Date": dates.values, "Actual": actual.values, "Forecast": forecast.values})
    df = df.dropna(subset=["Date"]).dropna(subset=["Actual", "Forecast"], how="all").reset_index(drop=True)

    df["Delta"] = df["Forecast"] - df["Actual"]
    df["DeltaPct"] = (df["Delta"] / df["Actual"]) * 100
    prev_actual = df["Actual"].shift(1)
    df["PredDir"] = (df["Forecast"] - prev_actual).map(direction_flag)   # vs prior week's spot, +/-500 => Flat
    df["ActualDir"] = (df["Actual"] - prev_actual).map(direction_flag)
    df.loc[df.index[0], ["PredDir", "ActualDir"]] = "Flat"               # no prior reference

    # ---- per-week accuracy columns, replicated EXACTLY from Accuracy_Table_11.xlsx -------------
    # Each commodity block in the sheet carries Actual, Forecast, MAE, MAPA (%), Delta (%),
    # Directional (%). Those metric cells are Excel FORMULAS (no cached values), so we recompute
    # them here. All three are in POINTS (0..1); the UI multiplies by 100 to show a %. th = the
    # +/-500 Rs./ton dead-band (FLAT_THRESHOLD). am = actual week-over-week move (spot - prior spot);
    # pm = predicted move (forecast - prior spot).
    th = FLAT_THRESHOLD
    am = df["Actual"] - prev_actual
    pm = df["Forecast"] - prev_actual

    # MAPA (%) = 1 - |Actual - Forecast| / Actual  (absolute price accuracy, per week)
    df["AbsAcc"] = 1 - (df["Actual"] - df["Forecast"]).abs() / df["Actual"]
    df.loc[df["Actual"] == 0, "AbsAcc"] = np.nan

    amflat, pmflat = am.abs() < th, pm.abs() < th
    amf, af = amflat.to_numpy(), am.to_numpy()

    # Directional (%) = 1 when the predicted direction matches the actual (both inside the dead-band
    # counts as a correct 'flat' call), else 0.
    df["DirAcc"] = np.where(amflat, np.where(pmflat, 1.0, 0.0), np.where(am * pm > 0, 1.0, 0.0))

    # Delta (%) = share of the actual move that the forecast captured (signed, capped at 1). Blank
    # when the forecast called a move but the market stayed flat.
    up, down = (pm >= th).to_numpy(), (pm <= -th).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (am.abs() / pm.abs()).to_numpy()               # |am/pm|; inf where pm==0 (unused)
        capped = np.minimum(1.0, ratio)
        # base = predicted-flat weeks: perfect if actual also flat, else partial credit 500/|am|
        delta = np.where(pmflat.to_numpy(),
                         np.where(amf, 1.0, np.minimum(1.0, th / np.abs(af))), np.nan)
        delta = np.where(up & ~amf & (af < 0), -ratio, delta)      # predicted up, actual down
        delta = np.where(up & ~amf & (af >= 0), capped, delta)     # predicted up, actual up
        delta = np.where(down & ~amf & (af > 0), -ratio, delta)    # predicted down, actual up
        delta = np.where(down & ~amf & (af <= 0), capped, delta)   # predicted down, actual down
    df["DeltaAcc"] = delta

    df.loc[df.index[0], ["DirAcc", "DeltaAcc"]] = np.nan        # first week has no prior reference
    df["Hit"] = df["DirAcc"] == 1.0                             # drives the weekly directional chart
    return df


def load_accuracy(window: str, acc_label: str) -> pd.DataFrame:
    """Week-wise Actual/Forecast for one product from an accuracy table.

    Returns Date, Actual, Forecast, Delta, DeltaPct, PredDir, ActualDir, Hit,
    AbsAcc, DirAcc, DeltaAcc (the last three in points, 0..1).
    Re-read when the file changes.
    """
    path = acc_path(window)
    return _read_accuracy(path, acc_label, _mtime(path))


def accuracy_kpis(df: pd.DataFrame) -> dict:
    """Absolute (MAPA), directional and delta accuracy — the averages of the accuracy-table's
    MAPA (%) / Directional (%) / Delta (%) columns (points -> %), matching the sheet's AVERAGE rows
    (blank weeks ignored)."""
    if df.empty:
        return {"mapa": None, "dir_acc": None, "delta_acc": None}

    def _avg_pct(col):
        s = df[col].dropna()
        return s.mean() * 100 if len(s) else None

    return {
        "mapa": _avg_pct("AbsAcc"),
        "dir_acc": _avg_pct("DirAcc"),
        "delta_acc": _avg_pct("DeltaAcc"),
    }


def last_actual_date():
    """The most recent date for which an ACTUAL spot price exists, across all products,
    read straight from the accuracy table (not the Summary sheet). This is the app's
    'data as of' date. Because load_accuracy is mtime-keyed, editing Accuracy_Table_11.xlsx
    updates this automatically — no need to also touch the Summary sheet. Returns a
    pandas Timestamp, or None if no actuals are present."""
    latest = None
    for meta in STEEL_PRODUCTS.values():
        av = load_accuracy("11-week", meta["acc"]).dropna(subset=["Actual"])
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
    """List of analyst-call dicts from the private repo, else the bundled sample."""
    if _read_token_cfg():
        data = _read_calls_json(data_sig())
        if data and isinstance(data.get("calls"), list):
            return data["calls"]
    return SAMPLE_ANALYST_CALLS


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
