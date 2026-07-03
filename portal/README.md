# BigMint - AI Labs : Price Forecasting: Steel (Adani portal prototype)

Standalone Streamlit UI prototype. Data is a static, cached snapshot of the
dashboard's existing forecast/accuracy files - no live connection.

## Run
```bash
# from the dashboard base folder
pip install -r portal/requirements.txt
streamlit run portal/app.py
```

## Demo logins (per-user)
| Username | Password     | Role    |
|----------|--------------|---------|
| adani    | Adani@2026   | Adani   |
| admin    | Admin@2026   | Admin   |
| analyst  | Analyst@2026 | Analyst |

(Front-end demo auth only - not production access control. Defined in `auth.py`.)

## Modules
- **Home** - landing with module cards.
- **Price forecasting** - Steel: spot vs 12-week Ensemble (Wgt-Mean) forecast + direction for the six products.
- **Analyst calls** - placeholder repository (summaries + PPT/PDF), to be wired later.
- **Performance dashboard** - week-wise Spot / Forecast / Delta / Direction + MAPA & directional-accuracy KPIs (6 or 16-week window).
- **Calculators** - Import Price (HRC), Production Cost & Margin, Price Elasticity (HRC).

## Layout
```
portal/
  app.py              entry: auth gate, nav, branding, pages
  theme.py            brand palette + CSS + helpers
  auth.py             demo users
  data_loader.py      cached readers for forecast_forward + accuracy tables
  calculators/        calc_import_price.py, calc_cost.py, calc_elasticity.py, HRC - Copy.csv
  assets/             bigmint_logo.png  (drop your logo here)
  requirements.txt
```

## Notes / pending
- Logo: place `assets/bigmint_logo.png` (wordmark fallback otherwise).
- Analyst calls: real summaries/decks + upload workflow.
- Calculators: integrated from the BigMint calculator with the malformed `header {` CSS
  block fixed and PDF export made fpdf/fpdf2-safe.
