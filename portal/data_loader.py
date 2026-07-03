"""
Static-snapshot data loader for the BigMint - AI Labs portal.

Reads the dashboard's existing files ONCE (cached) and reshapes the messy
multi-header sheets into tidy per-product frames. No live connection: the
@st.cache_data layer means each file is read a single time per session.

Data lives entirely IN THIS REPO (no private folders, no network fetch):
  dashboard/accuracy_tables/forecast_forward.xlsx  - summary + 12-week forward path
  dashboard/accuracy_tables/Accuracy_Table_6.xlsx  - week-wise actual/forecast
  portal/calculators/HRC - Copy.csv                - calculators' dataset

Each file is re-read whenever it changes on disk (the @st.cache_data layer is keyed
on the file's modification time), so updating a data file + a rerun shows the new data.
"""
import os
import pandas as pd
import streamlit as st

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../dashboard
PORTAL_DIR = os.path.dirname(os.path.abspath(__file__))              # .../dashboard/portal

# --- Data location ---------------------------------------------------------
# The app reads ONLY the in-repo data folders (dashboard/accuracy_tables +
# portal/calculators) — so editing those files and rerunning shows the change.
# There is deliberately NO $PORTAL_DATA_DIR override and NO st.secrets['data']
# network download: nothing private or external is consulted.
USING_PRIVATE_DATA = False   # kept for backwards-compat; the app never uses private data


def acc_dir() -> str:
    """Folder holding the accuracy/forecast xlsx files (in-repo)."""
    return os.path.join(BASE, "accuracy_tables")


def calculators_csv(name: str = "HRC - Copy.csv") -> str:
    """Path to a calculators dataset CSV (in-repo)."""
    return os.path.join(PORTAL_DIR, "calculators", name)


ACC_DIR = acc_dir()
FF_PATH = os.path.join(ACC_DIR, "forecast_forward.xlsx")
ACC_PATHS = {
    "6-week":  os.path.join(ACC_DIR, "Accuracy_Table_6.xlsx"),
    # "16-week" (Accuracy_Table_16.xlsx) retired — the whole app now runs off Table_6.
}
HEADLINE_SHEET = "Ensemble_WgtMean"   # headline forecast line shown to Adani

# display name -> sheet/label used in the source files
STEEL_PRODUCTS = {
    "HRC":                   {"ff": "HRC",                 "acc": "HRC"},
    "HR Plate":              {"ff": "HR PLATE",            "acc": "HR PLATE"},
    "Rebar BF Mumbai":       {"ff": "REBAR BF MUMBAI",     "acc": "REBAR BF MUMBAI"},
    "Rebar IF Mumbai":       {"ff": "REBAR IF MUMBAI",     "acc": "REBAR IF MUMBAI"},
    "Rebar IF Raipur":       {"ff": "REBAR IF RAIPUR",     "acc": "REBAR IF RAIPUR"},
    "Structure (IF Raipur)": {"ff": "STRUCTURE IF RAIPUR", "acc": "STRUCTURE IF RAIPUR"},
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
    return (FF_PATH, *ACC_PATHS.values(), calculators_csv())


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
    return _read_summary(FF_PATH, _mtime(FF_PATH))


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
    return _read_forward(FF_PATH, ff_sheet, _mtime(FF_PATH))


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
    df["Hit"] = df["PredDir"] == df["ActualDir"]
    return df


def load_accuracy(window: str, acc_label: str) -> pd.DataFrame:
    """Week-wise Actual/Forecast for one product from an accuracy table.

    Returns Date, Actual, Forecast, Delta, DeltaPct, PredDir, ActualDir, Hit.
    Re-read when the file changes.
    """
    path = ACC_PATHS[window]
    return _read_accuracy(path, acc_label, _mtime(path))


def accuracy_kpis(df: pd.DataFrame) -> dict:
    """Compute MAPA (absolute accuracy), directional accuracy and avg delta over a frame."""
    if df.empty:
        return {"mapa": None, "dir_acc": None, "avg_delta": None}
    valid = df.dropna(subset=["Actual", "Forecast"])
    mape = (valid["Delta"].abs() / valid["Actual"]).mean() * 100
    rows = valid.iloc[1:]   # first row has no previous reference
    dir_acc = rows["Hit"].mean() * 100 if len(rows) else None
    return {
        "mapa": 100 - mape,
        "dir_acc": dir_acc,
        "avg_delta": valid["DeltaPct"].mean(),
    }


def last_actual_date():
    """The most recent date for which an ACTUAL spot price exists, across all products,
    read straight from the accuracy table (not the Summary sheet). This is the app's
    'data as of' date. Because load_accuracy is mtime-keyed, editing Accuracy_Table_6.xlsx
    updates this automatically — no need to also touch the Summary sheet. Returns a
    pandas Timestamp, or None if no actuals are present."""
    latest = None
    for meta in STEEL_PRODUCTS.values():
        av = load_accuracy("6-week", meta["acc"]).dropna(subset=["Actual"])
        if not av.empty:
            d = av["Date"].max()
            if latest is None or d > latest:
                latest = d
    return latest


def summary_row(summary: pd.DataFrame, ff_label: str):
    """Return the summary row (dict) for a product label, or None."""
    m = summary[summary["Product"].astype(str).str.strip() == ff_label]
    return m.iloc[0].to_dict() if not m.empty else None
