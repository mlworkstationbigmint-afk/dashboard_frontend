# =============================================================================
# Price-sensitivity engine — stateless single-row model
# =============================================================================
# Pure-Python calculation core for the Price Sensitivity calculator (no Streamlit
# in here — the UI lives in calc_elasticity.py). Mirrors the backtested Excel
# sheets (REBAR__3.XLS, HRPLAT_2.XLS):
#
#     effective % change per driver = Δ% + Δ(₹ or unit) / base price
#     predicted log-return          = Σ (effective % change × β)
#     predicted price               = current price × e^(predicted log-return)
#
# β (sensitivity, % move per 1% driver move) is fixed per product — estimated
# once by RidgeCV / LassoCV on month-on-month % changes and baked in below.
# HRC keeps its own live Ridge fit (see calc_elasticity.load_model); this module
# supplies the fixed-β HR Plate and Rebar models plus the shared compute().
# =============================================================================
import numpy as np


def compute(current_price, drivers, eff_fracs):
    """Stateless sensitivity prediction.

    drivers    : list of (name, base_price, beta, unit)
    eff_fracs  : {driver_name: effective fractional change}  (0.03 == +3%)

    Returns (impact, final_price, contrib_pct, contrib_rs):
      impact       — Σ (effective change × β), the predicted log-return
      final_price  — current_price × e^impact
      contrib_pct  — {name: effective change × β}  (each driver's share of impact)
      contrib_rs   — {name: current_price × contrib_pct}  (that share in ₹/t)
    """
    contrib_pct = {name: eff_fracs.get(name, 0.0) * beta
                   for name, _base, beta, _unit in drivers}
    impact = sum(contrib_pct.values())
    final_price = current_price * float(np.exp(impact))
    contrib_rs = {name: current_price * v for name, v in contrib_pct.items()}
    return impact, final_price, contrib_pct, contrib_rs


def effective_frac(delta_pct, delta_unit, base_price):
    """Combine a % input and a ₹/unit input into one effective fractional change.
    ₹/unit is converted to % via the (editable) base price. Either may be zero."""
    frac = (delta_pct or 0.0) / 100.0
    if base_price:
        frac += (delta_unit or 0.0) / base_price
    return frac


# --- Rebar — Exy-Mumbai, BF route, Fe 500D -----------------------------------
# RidgeCV on 149 MoM observations (Jan-2014 → Jun-2026). OOS R²=0.51,
# RMSE 3.8% / ₹1,993 per t. Source: BF_Rebar_Mumbai.csv (BigMint series).
REBAR = {
    "label": "Rebar",
    "full_name": "Rebar, Exy-Mumbai · BF route · Fe 500D",
    "current": 52862.5,
    "model": "RidgeCV on month-on-month % changes",
    "r2": 0.51, "rmse_pct": 3.8, "rmse_rs": 1993,
    "n_obs": 149, "period": "Jan 2014 – Jun 2026",
    # name, base price (default Jun-26), β (% per 1%), unit
    "drivers": [
        ("Iron Ore Fines (NMDC, Fe64)",   4850.0,  0.086247, "Rs./t"),
        ("Scrap HMS 80:20 (Mumbai)",     33328.0,  0.194529, "Rs./t"),
        ("Pellet Fe63 (Raipur)",          9156.25, -0.001238, "Rs./t"),
        ("Pig Iron (Raipur)",            37438.0,  0.365247, "Rs./t"),
        ("Sponge Iron (Durgapur)",       26192.0, -0.113405, "Rs./t"),
        ("Billet (Mumbai)",              41518.0,  0.018898, "Rs./t"),
        ("Ingot (Mumbai)",               40994.0,  0.178468, "Rs./t"),
        ("Coking Coal (FoB Australia)",    198.57, 0.026794, "USD/t"),
        ("BF Rebar Production (supply)",     1.129, -0.003976, "MT"),
    ],
}

# --- HR Plate — Exy-Mumbai, 5-10mm, Gr E250 Br -------------------------------
# LassoCV on 197 MoM observations (Jan-2010 → Jun-2026). OOS R²=0.83,
# RMSE 1.85% / ₹807 per t. Domestic HRC dominates (β≈0.73): HR Plate moves
# almost one-for-one with HRC; raw materials act mostly through HRC.
# Source: HR_Plate_Mumbai.csv + HRC_Mumbai.csv.
HR_PLATE = {
    "label": "HR Plate",
    "full_name": "HR Plate, Exy-Mumbai · 5-10mm · Gr E250 Br",
    "current": 57725.0,
    "model": "LassoCV on month-on-month % changes",
    "r2": 0.83, "rmse_pct": 1.85, "rmse_rs": 807,
    "n_obs": 197, "period": "Jan 2010 – Jun 2026",
    "drivers": [
        ("Iron Ore Fines Fe62 (CNF Rizhao)",  9519.73, -0.048313, "Rs./t"),
        ("Coking Coal HCC MV (FOB Australia)", 21079.67, 0.016004, "Rs./t"),
        ("Scrap HMS 80:20 (Mumbai)",          33328.0,  0.023178, "Rs./t"),
        ("Pellet Fe63 (Raipur)",               9156.25, 0.026843, "Rs./t"),
        ("HRC Exw-Mumbai (IS2062, 2.5-8mm)",  58275.0,  0.731840, "Rs./t"),
        ("HRC FOB Rizhao China",              51217.92, 0.083817, "Rs./t"),
        ("HRC FOB Black Sea",                 53580.37, 0.079965, "Rs./t"),
    ],
}

# fixed-β products keyed by label (HRC is handled live in calc_elasticity)
MODELS = {m["label"]: m for m in (HR_PLATE, REBAR)}
