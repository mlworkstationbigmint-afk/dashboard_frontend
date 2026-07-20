# BigMint – AI Labs Price Forecasting: Steel — Master Reference

> **Single source of truth for future task switches.** This file merges the former
> `handoff.md` (project reference: run/deploy, file map, modules, "edit X → go here",
> data sources, gotchas, changelog) and `PLAN_per_role_dashboards.md` (the per-role
> white-label feature plan/record, now **Appendix A**).
> **Update THIS file after every task/edit.**


Standalone **Streamlit UI** for Adani. Data is a cached snapshot of the
dashboard's existing forecast/accuracy files.

## Run
```bash
# from the repo root (so .streamlit/config.toml + relative data paths resolve)
cd C:\Users\Pc\Documents\Adani\dashboard_frontend
conda activate neuralforecast
streamlit run portal/app.py
```
Env = conda **`neuralforecast`**. Needs: streamlit, plotly, fpdf2, scikit-learn, openpyxl, pandas, numpy
(kaleido only for static PNG export), plus the **auth stack**: `SQLAlchemy`, `psycopg[binary]`, `argon2-cffi`, `PyJWT`, `extra-streamlit-components`. Console needs `PYTHONUTF8=1` for ₹ glyphs.
`.claude/launch.json` runs the same command on **port 8501** (`--server.headless true`); `.devcontainer/` runs it for Codespaces.

**Data location:** public code, **private data**. If `st.secrets['data']` is set, `data_loader.py` pulls the real files at runtime from a **private GitHub repo** (via the Contents API) into a temp dir; with no secrets it falls back to the bundled **in-repo sample** so the public code still runs. No `$PORTAL_DATA_DIR`, no sibling folder. See the **2026-07-03** changelog + `.streamlit/secrets.toml.example`.

**Auth store:** production, **self-managed users in Neon Postgres** (no longer in-repo). `db.py` reads **`database_url`** + **`session_signing_key`** from `st.secrets` (falling back to env vars, then `.streamlit/secrets.toml`, for CLI scripts/tests). `auth.py` does argon2id hashing, lockout, and JWT cookie sessions; `seed_users.py` seeds the first accounts. **Both secrets are required** — without them `db.database_url()` / `db.signing_key()` raise on first use (the "database_url is not set" error). Use Neon's **pooled** connection string. See the **2026-07-06** changelog.

## Deploy (Streamlit Community Cloud)
1. **Deploy**: on share.streamlit.io, deploy from this repo, main file = **`portal/app.py`**, Python 3.11/3.12. Deps come from the root **`requirements.txt`** (`streamlit==1.59.0` pinned — what the deployment actually runs; now also includes the auth stack — `SQLAlchemy` / `psycopg[binary]` / `argon2-cffi` / `PyJWT` / `extra-streamlit-components`. `portal/requirements.txt` mirrors these).
2. **Private data**: create a *private* GitHub repo (e.g. `dashboard-data`) laid out as `accuracy_tables/forecast_forward.xlsx`, `accuracy_tables/Accuracy_Table_11.xlsx`, `calculators/HRC - Copy.csv`. Make a **fine-grained PAT** scoped to only that repo with **read-only Contents**. In *Manage app → Settings → Secrets*, add a `[data]` block (`github_owner` / `github_repo` / `github_ref` / `github_token`) — see `.streamlit/secrets.toml.example`. The app then fetches the real data at runtime (`data_loader._fetch_private_data_dir`, `@st.cache_resource` → downloaded once per deploy); with no `[data]`, it shows the sample.
3. **Admin writes (optional)**: to let the Admin tab save analyst-call text + upload PDF/PPT decks, add **`github_write_token`** to `[data]` — a PAT with **Contents: Read & Write** on the data repo (or give `github_token` write access and skip it). Admin writes go to `analyst_calls/calls.json` + `analyst_calls/files/<id>/…` in that repo. Without it, the Admin tab is read-only (save disabled).
4. **Auth (required)**: add two **top-level** secrets — **`database_url`** (a Neon Postgres **pooled** connection string: host contains `-pooler`, ends `?sslmode=require`) and **`session_signing_key`** (32+ random bytes, e.g. `python -c "import secrets;print(secrets.token_hex(32))"`, signs the session cookie). Then **seed the first users once**: `python portal/seed_users.py` — creates adani/admin/analyst with random temp passwords + `must_reset=True`, written to the git-ignored `.streamlit/seed_credentials.txt`. Tables (`users`/`sessions`/`audit_log`) are auto-created by `db.init_db()` (the seed script calls it). Users live in Neon, **not** in `auth.py`; manage them at runtime via the **Admin tab → User management**. There is no `[auth]` secrets block. (`db._config()` also reads these from env vars / `.streamlit/secrets.toml` when run outside Streamlit.)
- **Backend swap**: to move data to S3/GCS instead of GitHub, replace the body of `_fetch_private_data_dir()` (reads) + `gh_put_file`/`gh_delete_file` (Admin writes).
- **⚠ History was scrubbed (2026-07-03):** the real data files were removed from git history + force-pushed (`git filter-repo`); backup bundle at `../dashboard_frontend_PRESCRUB_backup.bundle`. **No in-repo sample data remains** — with no `[data]` secrets the forecast/accuracy readers will error, so the app must run with secrets (or add a small dummy sample back). The Analyst page still works sample-less via `SAMPLE_ANALYST_CALLS`.

## Logins (production auth — Neon Postgres + argon2id)
Users live in the **Neon `users` table**, not in code. Passwords are **argon2id**-hashed; a login mints a **signed JWT** stored in the `portal_session` cookie, backed by a server-side row in `sessions` (so logout / disable / password-change **revoke** it). Seed the initial accounts once with `python portal/seed_users.py` → creates **adani** (Adani), **admin** (Admin), **analyst** (Analyst) with **random one-time passwords** (written to the git-ignored `.streamlit/seed_credentials.txt`) and `must_reset=True`, so each user is forced to set their own password on first login. Thereafter add / disable / reset / re-role / delete users from the **Admin tab → User management**. Policy: **5** failed attempts → **15 min** lockout; sessions last **12 h** (`MAX_ATTEMPTS` / `LOCKOUT_MINUTES` / `SESSION_TTL_HOURS` in `auth.py`).

> ⚠ The old demo passwords (`Adani@2026` etc.) and their SHA-256 hashes still exist in **git history** (pre-2026-07-06 `auth.py`). They no longer work, but treat them as burned — don't reuse them.

## Locked decisions
- Streamlit UI-only prototype; **per-user login backed by Neon Postgres (argon2id + JWT cookie sessions)**; **12-week** horizon.
- Headline forecast line = **Ensemble (Weighted Mean)**.
- Title: plain-text "Price Forecasting: Steel" (browser tab / login caption / Home H2). The **topbar heading** is now **per-role** (see the 2026-07-07 changelog): the **login/default** profile reads "BIGMINT `|` AI LABS : Steel Prices Forecasting Model" (no "STEEL GCP -" prefix as of 2026-07-13); the logged-in **Adani** profile reads "BIGMINT `|` ADANI `|` STEEL GCP - AI LABS : Steel Prices Forecasting Model" (BigMint logo · pipe · Adani chip · pipe · title — separators are pipes, not `×`); internal **Analyst/Admin** profiles drop the Adani chip (BigMint-only). Brand name is **BigMint** (never "Bigmint").
- **Per-role white-label dashboards (2026-07-07):** one deployment; each `auth.ROLES` value gets its own static branding (`theme.ROLE_PROFILES`) + admin-controlled commodity access (`db.role_commodities`) + analyst-call audience. See **Appendix A** below.
- Static snapshot data (no live connection).

## Steel products (catalog — 11)
Mumbai/Raipur: HRC · HR Plate · Rebar BF Mumbai · Rebar IF Mumbai · Rebar IF Raipur · Structure (IF Raipur)
Mundra (added 2026-07-10): HRC Mundra · HR Plate Mundra · Rebar BF Mundra · Rebar IF Mundra · Structure Mundra
> Full catalog in `data_loader.STEEL_PRODUCTS`. Since 2026-07-07 each **role** sees an admin-chosen subset (Admin tab → Commodity access); a role with nothing saved sees all. Admins always see all. Products group (HRC / HR Plate / Rebar / Structure) with a per-group location dropdown via `app.py` `_product_group` + `FORECAST_LOCATION_LABELS`.

## File map  (everything under `dashboard/portal/`)
| File | What it does |
|------|--------------|
| `app.py` | Entry: page config, auth gate, top nav, 5 pages, chart helpers |
| `theme.py` | Brand palette, CSS (themeable via `--bm-*` vars), icons, topbar, KPI/card/table helpers; **per-role branding** (`ROLE_PROFILES`/`profile_for`/`apply_role_theme`) |
| `grid.py` | **BigMint-themed AgGrid** (`bm_grid` + shared `JS_*` formatters): blue header/white bold, sort/filter/resize/pagination; used by forecasting + performance tables. Falls back to `st.dataframe` if `streamlit-aggrid` is absent |
| `auth.py` | Auth core (UI-agnostic, no users in-file): argon2id verify + lockout, JWT cookie sessions (`create_session`/`resolve_session`/`logout`), user CRUD helpers |
| `db.py` | Neon Postgres layer (SQLAlchemy): schema (`users`/`sessions`/`audit_log`/`role_commodities`) + queries + config resolution (`database_url` / `session_signing_key`) |
| `seed_users.py` | One-time seeder: creates the first users with random temp passwords → git-ignored `.streamlit/seed_credentials.txt` (`--force` to reset) |
| `data_loader.py` | Cached readers for forecast_forward + accuracy tables |
| `calculators/calc_import_price.py` | tab **"Landed Cost"** (import vs landed-cost parity, HRC) |
| `calculators/calc_cost.py` | tab **"Cost Head"** (production cost & margin) |
| `calculators/calc_elasticity.py` | tab **"Price Sensitivity"** — product tab-strip (HRC / HR Plate / Rebar), editable driver table, contribution chart, methodology. HRC = live Ridge fit; HR Plate/Rebar = fixed-β (see `engine_sensitivity.py`) |
| `calculators/engine_sensitivity.py` | Pure-Python sensitivity engine: `compute()` (price = current × e^Σ(eff%×β)), `effective_frac()`, and the fixed-β `HR_PLATE`/`REBAR` specs from the backtested `REBAR__3.XLS`/`HRPLAT_2.XLS` sheets |
| `calculators/HRC - Copy.csv` | Calculators' own dataset (last date 25-Jan-26) |
| `assets/bigmint_logo.png` | Top-bar BigMint logo (wordmark fallback if absent) |
| `assets/adani_logo.png` | Co-brand Adani logo, white chip in topbar (auto-trimmed from `_orig`, 1020×364; fallback chain: this → `adani_logo_orig.png` → gradient-text 'adani') |
| `assets/adani_logo_orig.png` | Untrimmed original Adani logo (1402×854). **Source for the trimmed `adani_logo.png` AND its runtime fallback — do NOT delete.** |
| `../.streamlit/config.toml` | Streamlit theme (primaryColor #EE4E24 — orange accent for buttons/tabs; **now tracked** so it deploys) |
| `../requirements.txt` | pip deps for Streamlit Cloud (**streamlit==1.59.0** pinned; + auth stack: SQLAlchemy / psycopg[binary] / argon2-cffi / PyJWT / extra-streamlit-components). Root copy is canonical; `portal/requirements.txt` mirrors it |
| `../.streamlit/secrets.toml.example` | Template for the **`[data]`** block (private-data GitHub repo + fine-grained PAT). **Also needs `database_url` + `session_signing_key`** for auth (top-level). Real `secrets.toml` is git-ignored |

## Modules
- **Home** — overview stats + 4 module cards + a full-width **Methodology banner** button below them.
- **Price forecasting** — Steel only: product selector + KPI strip, then a **Graphical view / Tabular view** tab pair (Graphical = spot-vs-forecast chart; Tabular = one continuous *Actual vs Forecast* table, history flowing into the 12-wk-ahead forecast), then a **Forecast rationale** section (placeholder, per-product via `RATIONALES`). (Raw-material tab removed earlier.) **The grouped roles (Adani / Analyst / Admin) instead see a *grouped* layout** — a top HRC/HR Plate/Rebar/Structure group tab-strip, then one row with a **sliding pill switch** (Graphical/Tabular; an `st.segmented_control` styled as a grey capsule track + a white label-width pill that glides behind the active option) on the left and the **location dropdown on the right** (usable in both views), then the graph on top (week/zoom buttons just above the plot, in-chart legend, year-stamped x-axis labels), then the 3 price cards below the view block (see the 2026-07-07 changelog + `GROUPED_FORECASTING_ROLES`).
- **Analyst calls** — cards driven by **editable content** (`data_loader.load_analyst_calls()` → `analyst_calls/calls.json` in the private repo, else `SAMPLE_ANALYST_CALLS`): each card = month, title, headline summary, a one-line sectioned breakdown (Flats/Longs/Raw materials/Imports & exports/Outlook), and **live Download PDF / PPT** buttons (fetch the deck bytes from the private repo). No video. Managed via the Admin tab.
- **Admin** *(role = Admin only)* — content manager for the Analyst-calls page (`page_admin()`): add / edit / delete calls (text + sections), upload PDF/PPT decks, live preview. Saves to the private repo via the GitHub Contents API (`save_analyst_calls` / `upload_call_file` / `gh_delete_file`), needs `github_write_token` (or a write-capable `github_token`); shows a warning + disables saving when absent.
- **Performance dashboard** — product selector only (window toggle removed); reads **all rows** of `Accuracy_Table_11`. MAPA / directional / avg-delta KPIs, actual-vs-forecast chart + weekly-delta (Rs.) bars + **weekly accuracy % line** + **weekly directional-accuracy bars** + week-wise table.
- **Calculators** — 3 tools in tabs.
- **Methodology** — general (not per-product) infographic page: gradient hero + stat strip (~98% accuracy / 15+ yrs / 1–2% delta / IOSCO) + a 6-step **pipeline flow** (data → signals → ML+sentiment → ensemble → 12-wk forecast → accuracy) + 6 **key-factor** cards + 3 **horizon** cards + transparency/governance cards + disclaimer. Content sourced/generalised from bigmint.co forecasting methodology. All built with HTML/CSS (`.bm-meth-*`, `.bm-flow*`, `.bm-factor*`, `.bm-horizon*` in `theme.py`).

## "Edit X → go here"
- **Per-role branding (logo/co-brand/title/colors/visible pages)** → `theme.ROLE_PROFILES` (+ `DEFAULT_PROFILE`); resolved by `theme.profile_for(role)`; applied per session by `theme.apply_role_theme()` (called in `app.py` after login) + `render_topbar(user)`. Themeable colors are CSS vars (`--bm-primary`/`--bm-primary-dark`/`--bm-primary-soft`/`--bm-accent`) seeded on `:root` in `inject_css()`. **Add a new client:** add role to `auth.ROLES`, drop its logo in `assets/`, add a `ROLE_PROFILES` entry, then set access from the Admin tab.
- **Which commodities a role sees** → **Admin tab → Commodity access** (`app.py` `_admin_access_panel()`) → `db.role_commodities` (`db.get_role_commodities`/`set_role_commodities`); read via `app.py` `allowed_products(role)` (empty config or Admin ⇒ all)
- **Which analyst calls a role sees** → each call's **Audience** multiselect in the Admin call editor (`page_admin`), stored as `audiences` on the call; filtered by `app.py` `_call_visible(call, role)` in `page_analyst` (**deny-by-default**: a non-admin role sees a call only if it's in the audience; empty audience = unassigned ⇒ admins only; admins always see all)
- Brand colours/logo (defaults) → `theme.py` palette + `.streamlit/config.toml`; co-brand logos → `theme.py` `_cobrand_logo_html` (+ `ADANI_LOGO_CANDIDATES` fallback) + `render_topbar`; topbar heading text/pipes → `render_topbar()` + `.bm-portal-title` CSS
- Tab + segmented-selector accent (orange) → `theme.py` `inject_css()` tab/segmented CSS block (overrides primaryColor for those elements only)
- Nav items / page wiring → `app.py` `NAV` list + `PAGES` dict. `top_nav()` shows only the pages in the role's `theme.profile_for(...)["pages"]` (+ appends **Admin** for admins); the dispatch guard (bottom of `app.py`) resets a hidden `st.session_state.page` back to Home. Change which pages a role sees → that role's `pages` in `theme.ROLE_PROFILES`
- Home module cards (clickable) → `app.py` `page_home()` `modules` list + `theme.py` `.st-key-homemod_*` CSS
- Home Methodology banner (full-width) → `app.py` `page_home()` `home_methodology` button + `theme.py` `.st-key-home_methodology` CSS
- Log out button (header top-right, primary) → `app.py` header `st.columns([6,1])` block (key `logout_top`)
- Chart look / lines / hover ball → `app.py` `_style_fig`, `_spot_trace`, `forecast_chart`, `perf_chart`, `delta_bar`, `accuracy_chart`, `directional_accuracy_bar`, `_render_with_highlighter`; colours in `theme.py` (`SPOT_LINE`, `FORECAST_LINE`, `FORECAST_HALO`)
- Products (catalog) → `data_loader.py` `STEEL_PRODUCTS`; per-role visible subset → `app.py` `allowed_products()` + `db.role_commodities` (Admin tab)
- Users → **Admin tab → User management** (`app.py` `_admin_users_panel()`) at runtime, or `python portal/seed_users.py` to seed. Stored in the Neon `users` table; helpers in `auth.py` (`create_user`/`upsert_user`/`set_password`/`set_active`/`set_role`/`delete_user`/`list_users`) over `db.py`. `authenticate()` returns `(user, status)` — argon2id verify + lockout
- Roles → `auth.ROLES` are the built-in roles, but an admin can **create a new role** in the Add-user form (free-text field). The role list shown in every picker (add-user, Apply-role, Commodity-access, call Audience) is `app.py` `known_roles()` = `auth.ROLES` **∪ roles already assigned to a user**, so a runtime-created role auto-appears everywhere. A new role gets `DEFAULT_PROFILE` branding + all commodities (unconfigured) + no calls (deny-by-default) until configured; **custom branding still needs a dev to add a `theme.ROLE_PROFILES` entry**
- Session / cookie behaviour (login persists across refresh, logout, forced first-login reset) → `app.py` cookie block (`cookie_manager`, `_read_cookie_token`, `_start_session`, deferred `_cookie_write`/`_cookie_clear`, `force_password_change`) + `auth.create_session`/`resolve_session`/`logout`. Signed JWT in the `portal_session` cookie; server rows in `sessions`
- Post-refresh full-screen splash (while the cookie is read) → `theme.loading_screen()`; in-app **translucent** loading overlay (page switches / slow reruns) → `inject_css()` `[data-testid="stApp"]::before/::after` gated by `:has([data-testid="stStatusWidget"])`
- DB connection / auth secrets (`database_url`, `session_signing_key`) → `db.py` `_config()` (st.secrets → env → `.streamlit/secrets.toml`); `db.py` rewrites `postgresql://` → `postgresql+psycopg://` for SQLAlchemy
- Analyst content → **Admin tab** (`app.py` `page_admin()`, admins only). Data lives in `analyst_calls/calls.json` + `analyst_calls/files/<id>/…` in the private repo; read via `data_loader.load_analyst_calls()` / `fetch_call_file()`, written via `save_analyst_calls()` / `upload_call_file()` / `gh_delete_file()`. Card render shared by `page_analyst()` + the Admin preview (`_render_call_card`). Fallback = `data_loader.SAMPLE_ANALYST_CALLS`; sections list = `ANALYST_SECTIONS`. Write needs `github_write_token`
- Methodology page content (pipeline steps, factors, horizons, stats) → `app.py` `page_methodology()` (`steps`/`factors` lists + inline HTML); infographic styling → `theme.py` `.bm-meth-*`/`.bm-flow*`/`.bm-factor*`/`.bm-horizon*`
- Forecast rationale text → `app.py` `RATIONALES` dict (add a key per product name; `_default` is the placeholder shown until then)
- Forecasting Graphical/Tabular views → `app.py` `page_forecasting()` nested `render_graph_view()` / `render_table_view()`; grouped roles switch them with the `fc_view` **segmented-control toggle**, other roles with `st.tabs`
- **Grouped forecasting layout (Adani / Analyst / Admin)** — group tabs (HRC/HR Plate/Rebar/Structure) → one row: **Graphical/Tabular slider switch (left) + location dropdown (right)** (dropdown shared across Graphical+Tabular) → graph on top (no title, week/zoom buttons JUST ABOVE the plot + in-chart legend + short year in x-axis labels) → price cards below the tabs → `app.py` `page_forecasting()` grouped branch + helpers `_grouped_forecasting` / `_product_group` / `_grouped_products` / `_location_label` + `FORECAST_GROUP_ORDER` + nested `price_cards()`; which roles get it → `app.py` `GROUPED_FORECASTING_ROLES`; the chart's legend-position / year-label / compact-size (buttons-above + h=620) toggles → `forecast_chart(legend_inside=…, year_labels=…, compact=…)`; the dropdown's border/tint + right-aligned same-row placement (negative-margin pull-up) → `theme.py` `.st-key-fc_loc_box`; the sliding pill switch (an `st.segmented_control`, key `fc_view`; grey capsule track / `::before` white pill / `:has()` pill-parking transform) → `theme.py` `.st-key-fc_view_box` (container keys set in `app.py`)
- Forecast chart time slider + Zoom buttons (1W/4W/8W/12W/26W/YTD/ALL) → `app.py` `forecast_chart()` `rangeslider`/`rangeselector` block (end of the function, before `_render_with_highlighter`)
- **China import-parity landed-cost line (HRC chart)** → `app.py` `_china_landed_series()` + `CHINA_FX_BY_YEAR`/`CHINA_FX_DEFAULT`/`CHINA_LANDED_LINE` (just above `forecast_chart`); drawn by `forecast_chart(landed=…)`; gated to `product == "HRC"` in `page_forecasting()`. Duties/freight/port inherited from the Landed-Cost admin defaults (`calc_import_price._effective_defaults` China lane). Retune the year FX or line colour there; broaden past HRC by relaxing the `product == "HRC"` gate.
- History shown in chart + historical table → **full available history, no window/trim**. `forecast_chart()` and the tabular block both use `dropna(subset=["Actual"])` with no `.tail()`; the old `HIST_WEEKS` constant was removed (2026-07-03)
- Data parsing → `data_loader.py`
- Data **location** → `data_loader.py` `_data_root()`: fetched private-repo temp dir when `st.secrets['data']` is set (`_fetch_private_data_dir`), else the in-repo sample (repo root). `acc_dir()` / `calculators_csv()` / `ff_path()` / `acc_path()` build every path from that root. Swap backend (S3/GCS) = rewrite `_fetch_private_data_dir()` body
- Direction Up/Down/Flat + flat threshold (500) → `data_loader.py` `direction_flag()` / `FLAT_THRESHOLD`

## Data sources (read once, cached)
> **Location:** resolved by `data_loader._data_root()` — a **private GitHub repo** (downloaded to a temp dir) when `st.secrets['data']` is configured, else the **in-repo sample**. `acc_dir()` / `calculators_csv()` build paths from that root; readers are **mtime-keyed** (`@st.cache_data`). The layout below is the same in the private repo and the sample. (NB: `_auto_refresh_on_data_change` polling only picks up *local* file edits — private data is fetched once per deploy via `@st.cache_resource`; update it by editing the private repo + rebooting the app / clearing cache.)
- `accuracy_tables/forecast_forward.xlsx` — `Summary` (per product: last actual, next-wk & +12wk forecast + dir; a `Top-3 models (direction)` column exists but is **no longer displayed** — see changelog) and per-product sheets (12-wk path: Date, Week, Forecast, Δ, Direction).
- `accuracy_tables/Accuracy_Table_11.xlsx` — week-wise Actual/Forecast (sheet `Ensemble_WgtMean`), one wide 7-col block per product; parsed by column position (`_read_accuracy` finds each block by its product label in row 0). Renamed from `Accuracy_Table_6.xlsx` on 2026-07-10 (6/16-week both retired). The app runs entirely off Table_11 (`ACC_FILES` has only `"11-week"`; every `load_accuracy()` call passes `"11-week"`). Stored MAE/MAPA/Delta/Directional cols are sparse → derive Delta/Direction from Actual/Forecast (Up/Down/Flat via `direction_flag`, ±500 Rs./ton dead-band ⇒ Flat).
- `calculators/HRC - Copy.csv` — calculators' dataset (in the sample it lives at `portal/calculators/`).

## Gotchas (don't re-break these)
- **Nav**: current page = `st.session_state.page` (a plain key, NOT a widget key). Nav is `st.button`s (active = `type="primary"`). NEVER bind a widget `key` to the nav and then mutate it → raises "cannot be modified after the widget is instantiated". **Log out** is a separate primary `st.button` (key `logout_top`) in the header columns, not in the nav row.
- **Charts**: rendered via a custom Plotly.js iframe layer (CDN `plotly-2.35.2`) to get the **hover-following highlighter ball** (Plotly can't enlarge the hovered marker natively). `_render_with_highlighter()` adds halo+core marker traces moved on `plotly_hover`. Delivery = **`st.iframe(temp-file path)`** (since 2026-07-07; inlines the file as the iframe `srcdoc` — replaced the deprecated `components.v1.html`, which log-spams on streamlit 1.59; per-session temp file under `%TEMP%/bm_charts/`). → **needs internet (CDN)**; for offline, bundle plotly.js locally.
- Chart hover = `hovermode="closest"` (unified looked janky). Pass plotly **layout-scalar dates as python datetime** via `_dt()` (pandas Timestamp breaks JSON serialization); `fig.to_json()` handles trace dates.
- Forecast chart = light-blue actual + **red dashed** forecast (history fit + 12-wk) with red ball+pink halo. Colours: `SPOT_LINE #5E92D6`, `FORECAST_LINE #E12B20`.
- **Calculators**: each exposes `render()`; their CSS had `div.stButton>button` overrides removed so they don't clobber nav buttons; a malformed `header{...}` CSS block was fixed. (PDF export was removed 2026-07-15.)
- Logo blue is `#024CA1` (= theme PRIMARY) so it blends into the bar.
- **Auth store is Neon Postgres, not `auth.py`** — `database_url` + `session_signing_key` MUST be in secrets or the app errors on first DB call ("database_url is not set"). Use Neon's **pooled** string (`-pooler` host) — the direct one exhausts connections under Streamlit reruns. `db.py` rewrites `postgresql://` → `postgresql+psycopg://` for SQLAlchemy. On Streamlit Cloud, `secrets.toml` is **not** deployed — the pasted secrets are the only source (a common failure is pasting the keys **under** a `[section]` header, which makes them non-top-level and invisible).
- **Cookie writes must be DEFERRED, never in the same run as `st.rerun()`** — `st.rerun()` discards the current run's frontend deltas, so an `extra_streamlit_components` `cookie_manager.set()`/`delete()` right before it never reaches the browser (this caused "refresh logs me out" + a logout `KeyError`). Pattern: queue the mutation in `st.session_state` (`_cookie_write` / `_cookie_clear`) and perform it on the **next** run (a full render NOT followed by a rerun). Logout clears the cookie by overwriting it **expired** (avoids the library's `delete()` `KeyError`, which does `del self.cookies[name]`).
- **Cookie read** — prefer `st.context.cookies` (from the HTTP request; present on a genuine refresh) and fall back to `cookie_manager.cookies` (the component's async read, populated after one extra rerun). Because that fallback is async, the first render after a refresh can't distinguish "logged out" from "cookie not delivered yet" → we show `theme.loading_screen()` once (guarded by `_cookie_probed`) instead of flashing the login form. (The temporary `?authdebug=1` readout was removed on 2026-07-06 once cookie persistence was confirmed on Cloud.)
- **Loading overlay via `:has()`** — the translucent in-app overlay keys off `[data-testid="stStatusWidget"]` (Streamlit's running indicator, in the DOM only mid-rerun), toggled with a pure-CSS `:has()` rule + `::before/::after` on `[data-testid="stApp"]` (no JS, no extra DOM node, no layout shift). Needs a `:has()`-capable browser (all current evergreens). If a Streamlit upgrade renames that testid, re-grep the static JS — verified against **1.58**. The full-screen splash uses z-index `2147483647`; the translucent overlay `99990/99991`. **Show-delay (2026-07-06, bumped to .7s 2026-07-11):** the overlay only appears after a rerun has lasted **>.7s** — the `:has(...)` (visible) rule carries `transition: opacity .18s .7s, visibility 0s .7s`, while the base rule hides promptly (no delay). (Raised from .4s because reruns landing just over the old threshold still flashed occasionally.) Fast reruns (e.g. moving between the login username/password fields, each of which fires a quick rerun) finish before the delay elapses, so the overlay no longer flashes; slow reruns (page switches, chart loads) still show it. **Keep the delay only on the `:has` rule** — putting it on the base rule would delay hiding and make the overlay linger.
- **Accent = orange**: `primaryColor` is `#EE4E24` (ACCENT orange) in config.toml — it natively drives **primary buttons (Sign in / Log out / active nav) + tab highlights + segmented selected state** orange. The **brand topbar stays blue** because it uses the `PRIMARY` (#024CA1) constant in `theme.py` CSS, *not* `primaryColor`. **Tabs** are a **sliding segmented switch**: on 1.59 (react-aria) the white pill is `.react-aria-SelectionIndicator` pinned to the active tab's own box (`inset:0`, inline transform/size overridden — it moves *with* the selection rather than gliding across the track); the grey track is `[data-testid="stTabs"] div[role="tablist"]`, tab buttons are `div[data-testid="stTab"][role="tab"]` (`[aria-selected="true"]` = orange active). The Product segmented selector + the fc_view pill switch use `button[data-variant="segmented_control"][aria-checked="true"]`.
- **⚠ Streamlit 1.59 ONLY (react-aria) — no more baseweb (2026-07-18).** The app targets **streamlit 1.59.0** (pinned in root + `portal/requirements.txt`); the deployment runs it too. As of 2026-07-18 **all dead 1.58 `data-baseweb="…"` / `stBaseButton-…Active` selectors were removed** — the CSS keys ONLY on 1.59 markup. **Rule:** style via **Streamlit-owned markup** (testids like `[data-testid="stTabs"]` / `stTab` / `stSelectbox` / `stNumberInput`, `st-key-*` classes, `role=`/`aria-*` attributes, `.react-aria-*`). **Do NOT add `data-baseweb` selectors** — they no-op on 1.59. Inputs/dropdowns get their white-fill + single rounded orange border from the **app-wide `stSelectbox` / `stNumberInput` / `stTextInput` / `stTextArea` / `stDateInput` rules in `theme.py`** (colour-only border, never width — a forced width makes zero-width reset borders on outer wrappers show as a second box). See memory `streamlit-159-only`.

## Changelog
### 2026-07-18 (latest++++++++++++++++++++++++++++++++++++) — Forecasting: China import-parity landed-cost line on the HRC chart
- New **third chart line on HRC (Exy-Mumbai) only**: for each historical week, the Mumbai HRC spot (Rs./t) is read back to an implied **China FOB in USD** at that YEAR's fixed average FX, then run through the **Landed-Cost calculator's China lane** (`calc_import_price.compute_landed` with the China `_effective_defaults()` freight + BCD/cess/safeguard + port) to get a landed Rs./t. Overlaid violet (`CHINA_LANDED_LINE #7C3AED`) alongside the light-blue spot + red-dashed forecast.
- **FX is one flat value per calendar year, NOT per week** — `CHINA_FX_BY_YEAR = {2024: 83.6, 2025: 87.4, 2026: 93.0}` (`CHINA_FX_DEFAULT 93.0` for other years) in [app.py](portal/app.py) just above `forecast_chart`. Edit these to retune. Duty/freight/port come from the Landed-Cost admin defaults, so changing them there also moves this line.
- Plumbing: [app.py](portal/app.py) `_china_landed_series(acc)` builds `(dates, vals)` (returns None on any failure → line just drops); `forecast_chart(..., landed=None)` draws the optional trace + folds its values into the y-range padding; `page_forecasting()` computes `china_landed` only when `product == "HRC"` and passes it to both graph-view calls (grouped + non-grouped). Non-grouped footnote notes the violet line when present.
- Because the landed base is the spot itself (not a real, lower China FOB), the line sits ~25–30% above spot — an honest reflection of the duty stack, and fully tunable via the constants above.

### 2026-07-18 (latest+++++++++++++++++++++++++++++++++++) — Login + reset pages redesigned from scratch (modular branded card)
- [app.py](portal/app.py) `login_screen()` + `force_password_change()` rebuilt. **Topbar kept** (logo + brand elements) for a clean transition into the app; the card below carries product title + subtitle via `_login_brand(title, sub)` (logo NOT duplicated in the card), a thin blue→orange brand strip across the card top, soft shadow. **Auth engine unchanged** (`auth.authenticate` / `_start_session` / status handling identical).
- Sign-in / Set-password button **inverts on hover** (orange fill → white fill + orange text/border).
- All login styling now lives in ONE scoped **`LOGIN_CSS`** constant in `app.py` (keyed to `.st-key-login_card` / `.st-key-reset_card`), injected on both pages — clean grey input border that turns orange on `:focus-within`, `-webkit-autofill` forced white (was showing a tinted fill), muted→accent reveal-eye, full-width bold submit. Fixes the earlier "sloppy"/uneven Username-vs-Password box.
- The ad-hoc login-input rules in [theme.py](portal/theme.py) were removed (replaced by a one-line pointer) so the two don't fight. Reset page also gets the branded header + clean inputs via the shared CSS.

### 2026-07-18 (latest++++++++++++++++++++++++++++++++++) — Full migration to Streamlit 1.59 (all baseweb removed) + app-wide input border-box fix
- **All dead 1.58 selectors removed** — [theme.py](portal/theme.py) had `data-baseweb="tab-*"` / `data-baseweb="select"` / `data-baseweb="popover"` rules and `stBaseButton-segmented_controlActive` twins paired with the live 1.59 (react-aria) rules; the baseweb halves are gone. The CSS now keys ONLY on 1.59 markup (testids / `role`/`aria-*` / `.react-aria-*`). Stale "both generations" comments in [app.py](portal/app.py), [calc_elasticity.py](portal/calculators/calc_elasticity.py) + the two MASTER gotchas updated to 1.59-only.
- ⚠ The grouped Forecasting + Performance **location dropdowns** lost their special blue border/soft-blue fill (that block used baseweb `select` markup, dead on 1.59) — they now use the app-wide white+orange selectbox styling. A comment in `theme.py` marks where to re-add a distinct tint with `stSelectbox` selectors if wanted.
- **App-wide input border-box fix** — added a `theme.py` rule giving **stNumberInput / stTextInput / stTextArea / stDateInput** the same clean box as the dropdowns (white fill + ONE rounded orange border, no inner notch/seam, orange −/+ stepper glyphs). ⚠ The transparent-inner group MUST include `button` — the number input's `−/+` steppers are `<button>`s, and leaving them out left a visible seam/double-border on every number box (the dropdowns have no buttons, hence looked clean). Fixes the pale/seamed look on Price Sensitivity "Current price" + knob value boxes, Cost Head market price, admin/login fields. Colour-only border (never width). The Price Sensitivity knob card's own box-building CSS was **deleted** so it inherits this one clean recipe (kept only its centred value + stepper-hover).
- No installation changes — `streamlit==1.59.0` was already pinned everywhere. Migration was CSS-only.

### 2026-07-18 (latest+++++++++++++++++++++++++++++++++) — Price Sensitivity: white knob cards + per-product estimation equation
- [calc_elasticity.py](portal/calculators/calc_elasticity.py) knob-card background → **solid white** (was a `#ffffff→#f4f7fb` gradient). Preset chips left unchanged.
- **Estimation equation now filters to the selected product** — `_methodology_infographic(product_label)` keeps only the matching `eqs` row (HRC → HRC only, etc.; falls back to all three if the label doesn't match). Call site passes `spec["label"]`.

### 2026-07-18 (latest++++++++++++++++++++++++++++++++) — Landed Cost: editor in its own fragment → outputs stay frozen during edits
- CSS fix alone wasn't enough — the Plotly chart + AgGrid FX-grid still **re-mounted** on every buffered cell edit / FTA tick (they sit in the same body as the editor), so the page still shuffled.
- Fix: [calc_import_price.py](portal/calculators/calc_import_price.py) `_render_body` now nests the scenario table + Calculate/Reset/Save in an inner `@st.fragment _editor()`. Buffered edits rerun **only** `_editor` → the outputs below (verdict banner, chart, FX grid, methodology) are not touched and stay mounted (no flicker). Calculate/Reset commit to session state then `st.rerun(scope="app")` → everything redraws **once, together**. Reset switched from `on_click` to inline (commit → rerun) since the full rerun re-seeds the fresh-keyed editor anyway.

### 2026-07-18 (latest+++++++++++++++++++++++++++++++) — Landed Cost: stop the layout "jump then settle" on every edit
- After wrapping `render()` in `@st.fragment`, every edit re-emitted `CALC_CSS` (which the fragment contained). That `<style>` carries **global `!important` block/column gap** rules — tearing it down for a frame snapped gaps back to the theme default, so the whole page visibly reshuffled then settled ("moves everything for some seconds then comes back").
- Fix: split [calc_import_price.py](portal/calculators/calc_import_price.py) `render()` into a **non-fragment wrapper** (injects `CALC_CSS` once) + `_render_body()` (`@st.fragment`). CSS now stays mounted across fragment reruns — matches the pattern already used by `calc_elasticity`/`calc_cost` (CSS in non-fragment `render`, interactive body in the fragment), which is why they never flashed.

### 2026-07-18 (latest++++++++++++++++++++++++++++++) — Calculators: no full-page reload on edits (@st.fragment)
- Table edits were re-running the whole `app.py` script (auth, sidebar, all tabs, footer) on every keystroke/checkbox → visible loading lag. Fix: scope reruns to the view being edited via `@st.fragment`.
- [calc_import_price.py](portal/calculators/calc_import_price.py): `render()` now decorated `@st.fragment`.
- [calc_cost.py](portal/calculators/calc_cost.py): `_render_product()` now decorated `@st.fragment`.
- Price Sensitivity ([calc_elasticity.py](portal/calculators/calc_elasticity.py) `_render_product`) already had it. No `st.data_editor`/`slider` elsewhere — `app.py`'s selectbox/segmented nav intentionally reruns the page.

### 2026-07-17 (latest+++++++++++++++++++++++++++++) — Landed cost: ticking FTA zeroes BCD % + Cess on BCD % in the table
- [calc_import_price.py](portal/calculators/calc_import_price.py): on Calculate-commit, when a row's **FTA** box is ticked, `bcd_pct` + `cess_pct` are forced to **0.0** in session state so the scenario table visibly mirrors what the engine already does (FTA waives BCD + its cess). Other duty fields (port, safeguard, cess-on-SG) are unaffected. Applies on Calculate like every other edit — no live snap-back.

### 2026-07-17 (latest++++++++++++++++++++++++++++) — Landed cost: port + duties moved from Global variables to the per-location table
- [calc_import_price.py](portal/calculators/calc_import_price.py): **Global variables** panel now holds only **Domestic benchmark / FX / Threshold CIF** (`GVAR_DEFAULTS`, `GVAR_ORDER`, `GMAP` trimmed to 3; `_read_globals` returns only those). The other five — **Port Rs./t, BCD %, Cess on BCD %, Safeguard %, Cess on SG %** — moved into the **Scenario inputs by location** table as editable per-origin columns (`DUTY_COLS`), so each location can carry its own port + duty rates.
- Per-location defaults live in `_LOC_DUTY` (seeded from the old org-wide defaults) and are spread into every `LOC_DEFAULTS` row; `_effective_defaults` now loads **all** location fields from the admin-saved row (not just fob/freight/fta).
- Session state adds `{p}_{field}_{region}` for each duty field; setdefault, `_reset_locs`, the editor frame, `pending`/`dirty` diffs, Calculate-commit, and the **admin Save-as-default** payload all iterate `DUTY_COLS`. Compute builds a per-location effective `g` via `_gL(r)` = global g merged with that origin's committed duties (used for the main results **and** the FX-sensitivity table); `compute_landed` signature unchanged.

### 2026-07-17 (latest+++++++++++++++++++++++++++) — Label edits + Price Sensitivity estimation equation
- [app.py](portal/app.py) `_week_of_month_label` → now returns a **long date** ("17 July 2026") instead of "Week N, Mon YYYY" (drives the Home "Last updated on" KPI + the forecast "Last actual spot" caption).
- **Performance** page: section title "Actual vs Forecast deviation" → **"Actual price vs Forecast price"**.
- **Structure** group tab now displays **"Structural section"** in both the Forecasting and Performance group tab-strips, via new `_group_label()` + `format_func=` on the two `st.segmented_control`s. Internal group key stays `"Structure"` so `_location_label`/`_loc_label` prefix-stripping and `FORECAST_GROUP_ORDER` are untouched.
- [calc_elasticity.py](portal/calculators/calc_elasticity.py): new **"The estimation equation"** methodology sub-section — the general log-log OLS form `log(P_t)=α+β₁log(IO_t)+β₂log(Coal_t)+β₃log(Prod_t)+β₄log(EXIM_t)+ε_t` rendered once per product (HRC / HR Plate / Rebar) in a styled `.bm-eqset`/`.bm-eqrow` block, with a caption noting real models use an expanded driver set.

### 2026-07-16 (latest++++++++++++++++++++++++++) — Price Sensitivity: value box truly white + stepper hover + no-freeze steppers
- [calc_elasticity.py](portal/calculators/calc_elasticity.py) value box **solid white**: the leftover grey was Streamlit's `base-input`/container fill, not the shell. Now forcing `background`+`background-color:#fff` on `[data-testid="stNumberInput"] > div`, `[data-baseweb="input"]`, `[data-baseweb="base-input"]` and all inner `*`; shell alone keeps the orange border/radius/clip.
- **Stepper hover** fixed (glyphs were vanishing — hover bg matched the orange glyph): default = orange glyph on white; `button:hover` → orange fill + **white** glyph (`svg fill:#fff` + `color:#fff`).
- **±/steppers no longer freeze the page**: `_render_product` decorated `@st.fragment`, so a shock change (slider / number ± / preset / reset) reruns ONLY that product view — not the whole Calculators page (methodology infographic, glossary, tabs) — keeping the steppers responsive and stopping dropped rapid clicks. Product tab-strip stays outside the fragment (switching product = full rerun, as before).

### 2026-07-16 (latest+++++++++++++++++++++++++) — Price Sensitivity: tidy value box + tighter slider↔labels gap
- [calc_elasticity.py](portal/calculators/calc_elasticity.py): value box cleaned up — dropped the drop-shadow, added `overflow:hidden` so all four corners read rounded, and **centred** the value so it no longer strands to the far left of the −/+ steppers (one uniform white/orange-border box). Stepper `border:none`.
- Follow-up: killed the inner **notch/seam** (Streamlit's stepper group carried its own bg + radius + margin inside the box). Now only the OUTER `[data-baseweb="input"]` shell carries border/radius/clip; every inner element (`[data-baseweb="input"] *`) is flattened to no-border / no-radius / no-margin → one uniform rounded box. Inner elements painted **solid `#fff`** (not transparent) so the whole box is explicitly white (no card-gradient tint bleeding through).
- Slider tick labels (−20…+20) pulled up close to the slider: `.knob-ticks` margin-top −6px → −16px (kills the fat gap from the card's 0.9rem vertical block gap).

### 2026-07-16 (latest++++++++++++++++++++++++) — Price Sensitivity: driver value box → white, orange-bordered (like the dropdowns)
- [calc_elasticity.py](portal/calculators/calc_elasticity.py) knob-card CSS: the `st.number_input` (value + −/+ stepper) beside each slider now renders as a **white box with the app dropdown's rounded orange (`--bm-accent`) border** + light shadow; value is bold `--bm-primary-dark`, stepper glyphs orange. Layout unchanged (`[2,1]` columns), so the box stays right next to the slider.

### 2026-07-16 (latest+++++++++++++++++++++++) — Price Sensitivity: 4-up slider grid + Calculators page heading dropped
- `page_calculators()` in [app.py](portal/app.py): removed the `## Scenario Simulation` page heading above the tabs (the in-tab titles carry it).
- [calc_elasticity.py](portal/calculators/calc_elasticity.py) Sliders mode: driver cards now **4 per row** (`per` 2→4). To fit the narrower cards, the knobwrap horizontal gap tightened (0.85→0.5rem) and preset chips shrunk (font 11→9.5px, padding/min-height down, `white-space:nowrap`).

### 2026-07-16 (latest++++++++++++++++++++++) — Forecast rationales: real per-product commentary replaces the placeholder
- `RATIONALES` in [app.py](portal/app.py) (~L789) now has real **Pulling down / Holding up / Net** entries (with a bold `₹price → descriptor` lead line) for the six Mumbai/Raipur products: **Rebar BF Mumbai, Rebar IF Mumbai, Rebar IF Raipur, Structure (IF Raipur), HRC, HR Plate**. Keyed by the `dl.STEEL_PRODUCTS` name. Framing is demand/cost-driver narrative (monsoon lull, cost floor, pre-festive restocking, import parity), not model-ensemble mechanics.
- The Mundra products + anything unlisted still fall back to `_default` (still the old Demand/Supply/Trade/Net-view placeholder). Rendered as-is in the rationale card/section (`render_rationale` / `_rationale_card_html`).

### 2026-07-16 (latest+++++++++++++++++++++) — Cost Head BF: element rename + per-plant Southern/Eastern defaults
- **Renamed** BF element "Coking Coal / Met Coke / PCI" → **"Coking Coal(PHCC inc PCI)"** (`BF_ELEMENTS`, [calc_cost.py](portal/calculators/calc_cost.py)).
- **New `BF_PLANT` per-plant override table** (unit prices by element + a plant electricity norm) wired into `_seed_df` (`bf = BF_PLANT.get(plant)`; electricity uses `elec_norm` else product-based 450/400; prices via `bf["prices"].get(label, price)`). Plants/elements not listed keep BF_ELEMENTS defaults.
  - **Southern region**: Iron Ore 4700, Coking Coal 27800, Scrap 31555, Dolomite 1500, Ferroalloys 75300, Processing 6500, Electricity norm 650.
  - **Eastern region**: Iron Ore 2100, Coking Coal 27500, Scrap 35000, Dolomite 1500, Ferroalloys 76300, Processing 6500, Electricity norm 650.
  - ⚠ Keyed by **plant name**, so "Southern region" also gets these defaults in **Rebar BF** (not just HRC); "Eastern region" is HRC-only. All cells stay editable; Reset restores these.

### 2026-07-16 (latest++++++++++++++++++++) — Forecasts default to the Mumbai location
- New helper `_default_loc(loc_labels)` in [app.py](portal/app.py) picks the first label containing "mumbai", else `loc_labels[0]`. Used to seed the per-group location default on both the **Forecasting** page (~L900) and the **Accuracy/Performance** page (~L1496), replacing the old `loc_labels[0]`.
- Effect (grouped roles adani/analyst/admin): **HRC → Mumbai**, **HR Plate → Mumbai**, **Rebar → Rebar IF Mumbai** (first Mumbai in sorted order); **Structure** has no Mumbai variant so it's unchanged. Non-grouped roles already land on `"HRC"` (the Mumbai HRC). Only the landing default changed — every location is still selectable.

### 2026-07-16 (latest+++++++++++++++++++) — Cost Head chart: legend headroom + total-cost label moved inside bar
- **Legend no longer spills into the plot** ([calc_cost.py](portal/calculators/calc_cost.py) `_cost_margin_figure`) — top margin 92 → **124**, height 520 → **540**, legend `y` 1.02 → **1.04**, so all ~12 entries clear the bars.
- **Total-cost label moved inside the bar top** in a small white box (`yshift` +12 → **-17**, `bgcolor` white 0.92 + `bordercolor` #cbd5e1 + `borderpad` 3) — fixes the collision with the market-price dot and reads cleanly over the top segments.

### 2026-07-16 (latest++++++++++++++++++) — Cost Head: Sponge Iron default price → ₹23,250/MT
- `IF_ELEMENTS` Sponge Iron unit price 9500 → **23250** in [calc_cost.py](portal/calculators/calc_cost.py). Single seed source, so it applies to every IF plant (Durgapur & Jalna). Norm/mix unchanged. Editable per cell as before.

### 2026-07-16 (latest+++++++++++++++++) — Cost Head: stacked cost-element bars + market-price & margin scatters
- **Chart rebuilt** in [calc_cost.py](portal/calculators/calc_cost.py) `_cost_margin_figure(names, edited, mkt_prices)` — now takes the per-plant edited tables + per-plant market prices (was `totals, margins, mkt_price`). Bars are **stacked**, one segment per cost element (segment = consumption norm × unit price, new `SEG_COLORS` 10-colour palette), so each bar shows every component's contribution; the **grand total is labelled above each bar** (layout `annotations`, `xref=x`/`yref=y`).
- **Two scatter overlays**: **Market price** = orange **circles**+line on the **left** axis (`yaxis="y"`); **Mill margin** = **diamonds** (green/red by sign) + dotted neutral line on a **secondary right axis** (`yaxis2`, `overlaying="y"`, `side="right"`). Margin is derived inside the figure (`mkt_prices[n] - totals[n]`), so the signature stayed the same.
- **Legend moved on top, outside** the plot — `orientation="h"`, `y=1.02`, `xanchor="center"`, `x=0.5`; top margin bumped to 92 and height to 520 so the ~12-entry legend clears the bars.
- **Market price is per-plant** — the single `st.number_input` is one input per plant (`cost_mkt_{key}_{n}`, `mkt_prices` dict). Margins, banner (`mkt_prices[lower]`) and verdict (`mkt_prices[best]`, "current market prices") use it.
- Applies to **all routes/products** (BF + IF) since `_render_product` drives them all. Section header → "Cost build-up vs market price"; chart caption updated.
- ⚠ Visual-only — verify in-app: legend layout on top, right-axis margin scale + diamond colours, total-label placement above tall bars.

### 2026-07-16 (latest++++++++++++) — Price Sensitivity: coupled slider+number driver cards, presets, per-driver readout, HRC baselines
- **New reusable `driver_control(driver_id, label, baseline, unit)`** ([calc_elasticity.py](portal/calculators/calc_elasticity.py)) renders one knob card: a **coupled `st.slider` + `st.number_input`** (two-way synced), a **-20/-10/0/+10/+20** tick scale under the slider, **±20/±10/0 preset buttons**, a **"baseline → shocked (Δabs, Δ%)"** readout with a colour-coded delta (green up / red down / muted at 0), and a **per-driver reset**. Adding a driver = one call.
- **Canonical shock state is now a scalar % per driver** — `st.session_state["shock_{key}_{i}"]` in [-20,20]. Replaced the old `sens_dpct_/sens_dunit_/sens_base_` dicts. **Two-way sync** is done natively: module-level `on_change` callbacks (`_cb_slider`/`_cb_number`/`_cb_preset`) write only the canonical key, and `driver_control` pushes canonical → both widget keys (`sl_/num_`) *before* they render each run (no custom JS component). Both modes + presets + resets all read/write this one value, so a shock set anywhere shows everywhere.
- **Zero-snap**: `_snap()` clamps to ±20 and snaps |shock| ≤ 0.75 to exactly 0 → readout shows "no change".
- **Recompute is LIVE on every change** (no "Apply" button) — `eng.compute()` is a cached-Ridge + vectorised dot·exp over ≤10 drivers, sub-ms; gating it would only desync the two modes. *(Decision confirmed with user.)*
- **Indian digit grouping** for ₹ drivers (`_indian`, e.g. `12,34,567`); `_cur`/`_fmt_val` pick ₹ / $ / € / quantity-unit formatting from each driver's unit string.
- **Table mode** gained a **% shock / Absolute change** toggle: type either a percentage or a change in the driver's native unit (₹/$/€/Mt/kt), converted to % via the baseline; both write the shared shock state. Read-only Baseline / Shocked value / Δ columns alongside the one editable column. Reseeds (via `sens_sync` + toggle token) on mode-switch / toggle-flip / global-reset.
- **Single global "Reset all shocks"** in the controls column (`_reset_all`); per-driver resets live on each card.
- **HRC now carries per-driver baselines + units** (`_HRC_META`) so HRC also supports absolute entry: Iron Ore Fines = ₹6,450/t (real); **the other 9 are ⚠ placeholders** (order-of-magnitude sane per unit) — replace before real use. Baselines only scale the unit⇄% conversion; the % shock the model consumes never depends on them.
- **Grid is 2-up** (`per=2`) so each denser card stays usable. Table-of-changes gained a "Baseline → shocked" column.
- ⚠ Visual-only — verify in-app: two-way slider/number sync, preset/reset, mode+toggle state carry-over, and that an absolute-unit entry (off the 0.5 grid) doesn't upset the slider on switch-back.

### 2026-07-16 (latest+++++++++++) — Price Sensitivity: neumorphic knob cards + Graph/Table matched heights
- **Knobs redesigned as soft neumorphic cards** (reference: white audio-plugin panels). Sliders wrapped in a
  keyed `st.container(key="sens_knobwrap")`; CSS scoped to `.st-key-sens_knobwrap` styles the bordered
  containers (`stVerticalBlockBorderWrapper`) as gradient white cards w/ soft shadow + hover lift, the driver
  label (`stWidgetLabel p`) as a centred uppercase caption, and hides the ±20 end ticks (`stSliderTickBar`).
  The slider **accent stays native** (config `primaryColor` orange) — no fragile baseweb/react-aria internals
  touched.
- **All knobs identical size** — fixed **4-up** grid (`st.columns(4)` every row, trailing cells left empty)
  instead of `st.columns(len(row))`, so the last row's cards keep the same width; cards share `min-height`.
- **Graph and Table-of-changes now fill the same box** — `_view_height(n)` (`44 + 34·n`, clamped 300–560)
  feeds both the Plotly `height` and the `st.dataframe(height=…)`.
- File: `portal/calculators/calc_elasticity.py`. ⚠ Visual-only — verify in-app.

### 2026-07-16 (latest++++++++++) — Price Sensitivity: dual input modes, view tabs, KPI cards, sensitivities hidden
- **Two interchangeable input modes tied to one shock state.** An `st.segmented_control` ("Sliders" / "Table")
  switches between per-driver **knobs** (±20% sliders, 3-up) and the **editable Table** (Base / Δ% / Δ₹).
  Canonical shock lives in session state (`sens_dpct_/sens_dunit_/sens_base_{key}` dicts); both editors seed
  from it and write back, so shocks carry across modes. Sync trick: widget-key suffix `tok = ver_sync` —
  `ver` bumps on Reset, `sync` bumps when the mode changes (remounts the editor to reseed from canonical). A
  knob expresses the whole shock as a %, folding any ₹ part into Δ% (dunit→0).
- **Contribution area is now a Graph / Table-of-changes tab pair.** Graph is **persistent even at 0 shocks**
  (symmetric x-range centred on zero, no more "enter a shock" info box). "Table of changes" lists each driver's
  applied shock (% and ₹) + its ₹/t contribution, sorted by magnitude.
- **Predicted change / Forecasted price / Absolute change moved to the right rail as modular KPI cards**
  (`theme.kpi_card` inside `.bm-vcards bm-vcards-sm`, forecast-page style) directly under the Current-price
  input. **Removed** the blue predicted-price banner (`.kpi-banner`), the old 3-across `st.metric` row, and the
  "Pick a product…" caption.
- **No sensitivity (β) values are shown anywhere** — the driver table's β column is gone and methodology/glossary
  say "sensitivity" (never a number) so the model can't be reverse-engineered. `_hrc_spec()`/specs still hold
  the coefficients internally; only inputs + outputs are surfaced.
- Files: `portal/calculators/calc_elasticity.py`. ⚠ Visual-only — verify in-app (esp. mode-switch state carry
  + data_editor stability).

### 2026-07-16 (latest+++++++++) — Price Sensitivity rebuilt from scratch: HRC / HR Plate / Rebar product tab-strip + new backend engine
- **New page (UI from scratch), engines preserved.** `calc_elasticity.render()` fully rewritten to match the
  Landed Cost / Cost Head calculators: prominent `.bm-calc-head` header, **product tab-strip** via
  `st.segmented_control` (HRC / HR Plate / Rebar — same widget as the forecast page's product selector),
  an **editable driver table** (`st.data_editor`), a **horizontal contribution chart** (Plotly, green = up /
  red = down), a **predicted-price banner** + 3 `st.metric` KPIs, then a shared landed-cost-style
  **methodology** (engine infographic + 6-step equation pipeline) + **glossary**.
- **Removed** the old sliders-with-`"Price impact: Rs. +0"`-captions UI (per request) and the old
  `Driver Contribution` dataframe. No PDF here (already removed 2026-07-15).
- **New backend engine `calculators/engine_sensitivity.py`** (pure Python, no Streamlit):
  `compute(current, drivers, eff_fracs)` → `price = current × e^Σ(eff%×β)`, `effective_frac(Δ%, Δ₹, base)`
  (= `Δ%/100 + Δ₹/base`, matching the sheet's *"enter EITHER % or ₹"* columns), and fixed-β **`HR_PLATE`**
  (LassoCV, OOS R²=0.83, RMSE 1.85%/₹807, 7 drivers) + **`REBAR`** (RidgeCV, OOS R²=0.51, RMSE 3.8%/₹1,993,
  9 drivers) specs transcribed from `REBAR__3.XLS` / `HRPLAT_2.XLS`. **Verified**: Rebar reference scenario
  (Scrap +₹1000, Pellet +₹500, Pig Iron +₹500) reproduces the sheet exactly (impact 0.010647, price ₹53,428).
- **HRC engine unchanged** — still the live `Ridge(alpha=10)` fit on the calculators CSV (`load_model`);
  `_hrc_spec()` just adapts its coefficients (β) + short driver names into the shared renderer. HRC takes
  **% shocks only** (no per-driver base prices ship with the model); HR Plate / Rebar expose editable
  **Base price** + **Δ (₹ / unit)** columns so shocks can be entered in either % or absolute units.
- Files: `portal/calculators/calc_elasticity.py` (rewritten), `portal/calculators/engine_sensitivity.py`
  (new). ⚠ Visual-only rebuild — verify in-app.

### 2026-07-16 (latest+++++++++++++++) — Cost Head: Jalna IF plant restored with its own metallic mix
- IF metallic norms are now **plant-specific**: `IF_YIELD` (Sponge 1.22 / Scrap 1.05 / Pig 1.04) × per-plant
  `IF_MIX` shares. Durgapur = Sponge 80 / Scrap 15 / Pig 5; **Jalna = Scrap 75 / Sponge 20 / Pig 5** (Ferroalloys
  fixed 0.012 both). `_seed_df(product, is_if, plant)` and `_editor(..., plant)` thread the plant name.
- New `_mix_note(plant)` builds each plant's `yield × mix%` footnote; rendered per-plant below its table (replaced
  the single section-level footnote). Jalna re-added to `ROUTE_PRODUCTS["IF route"]["Rebar"]`.

### 2026-07-16 (latest++++++++++++++) — Cost Head: IF route rebuilt (metallic-mix series, Durgapur only)
- Replaced the single shared `ELEMENTS` list with route-specific **`BF_ELEMENTS`** / **`IF_ELEMENTS`**
  (`(label, price, norm, unit)` tuples; the per-element key/`ELEM_KEYS`/`IF_LABELS` machinery is gone since
  only the summed total is used downstream). `_seed_df(product, is_if)` picks the list; `_plant_costs` now just
  sums `price×norm` over the rows.
- **IF series** = Sponge Iron · Scrap HMS 80:20 · **Pig Iron (new)** · Ferroalloys (SiMn) · Non coking coal RB2 ·
  Electricity · OpEx. **Dolomite removed.** Norms are the final metallic-mix values: Sponge Iron 0.976, Scrap
  0.1575, Pig Iron 0.052, Ferroalloys 0.012 (`_METALLIC_MIX` footnote shows `yield × mix%` below the IF section).
- **IF route → Durgapur only** (`ROUTE_PRODUCTS["IF route"]["Rebar"] = ["Durgapur"]`, dropped Jalna).

### 2026-07-16 (latest+++++++++++++) — Cost Head: Unit column = measurement unit, USD/FX removed
- **Unit** column is now a read-only measurement unit (`Rs./kWh` for electricity, `Rs./MT` for everything else),
  no longer the INR/USD selectbox. `_seed_df` emits it; dropped `CURRENCY_OPTS`/`USD` constants.
- **USD conversion fully removed** (was incoherent with no currency choice): `_elem_cost(price, norm)` = price×norm;
  `_plant_costs(edited)` lost its `ex_rate` arg; `_editor` lost `ex_rate`; the **USD→INR rate** scenario input is gone.
- Methodology infographic, equation pipeline (dropped the "Currency" step), and glossary (FX→Unit term) updated to
  match. All prices are ₹.

### 2026-07-16 (latest++++++++++++) — Cost Head: column reorder + kg→ton + Sinter
- Column order now **Cost element · Unit · Unit price · Consumption norm · Total cost** (`Cur.` header renamed
  **Unit**; still the INR/USD selectbox). `column_order` updated in `_editor`.
- `ELEMENTS`: Limestone/Dolomite & Ferroalloys switched kg→ton — Limestone `3.50 Rs./kg × 250 kg/MT` →
  `3500 Rs./MT × 0.250 MT/MT`; Ferroalloys `85 × 12` → `85000 × 0.012` (basis strings → `Rs./MT x MT/MT`;
  totals unchanged: 875 / 1020). Iron Ore label `Fines`→`Sinter` (BF route).

### 2026-07-16 (latest+++++++++++) — Cost Head: table reformatted (norm · unit price · cur. · total cost)
- Every plant table is now **Cost element · Consumption norm · Unit price · Cur. · Total cost**. Dropped the
  old `Basis`/`Price x Norm` column; renamed `Norm`→"Consumption norm", `Price`→"Unit price".
- **Total cost** is a new read-only computed column = `norm × unit price` (USD rows FX-converted via `_elem_cost`).
  `_editor` folds stored `st.session_state[wkey]["edited_rows"]` back onto the seed each rerun so Total stays live;
  gained an `ex_rate` param. `_seed_df` column order/keys updated; `column_order` pins the display order.
- Engine (`_elem_cost`/`_plant_costs`, read by name) unchanged; grand total + margin still shown by `_totals_line`.

### 2026-07-16 (latest++++++++++) — Cost Head: IF-route cost-element relabels + Ferroalloys everywhere
- **Everywhere:** `ELEMENTS` alloy label `Ferroalloys (SiMn, FeMn, FeSi)` → `Ferroalloys (SiMn)`.
- **IF route only:** new `IF_LABELS` map relabels (display only, engine keys/order unchanged) `ore`→`Sponge Iron`,
  `coal`→`Non coking coal RB2`, `flux`→`Dolomite`. Threaded `is_if` flag: `render()` (`rkey=="if"`) →
  `_render_product` → `_editor` → `_seed_df(product, is_if)`.

### 2026-07-16 (latest+++++++++) — Cost Head: rename region labels, "Price x Norm" column, per-table total/margin
- Plant labels renamed to region names in `ROUTE_PRODUCTS`: BF HRC = `Southern region`, `Eastern region`;
  BF Rebar = `Southern region`, `Chhattisgarh` (was `JSW Vijaynagar […]`, `SAIL […]`, `JSW`, `CG`).
- `_editor` **Basis** column header → **"Price x Norm"** (dict key unchanged).
- New `_totals_line(total, margin)` renders **Total cost + Margin** (margin colored by sign) directly below
  each plant's table; per-plant cost/margin now computed inside the table loop instead of a separate pass.

### 2026-07-15 (latest++++++++) — Cost Head: BF / IF route tabs, each with a product dropdown
- **Restructured from HRC/Rebar tabs to two route tabs — "BF route" and "IF route" — each with a Product
  dropdown.** `PRODUCT_PLANTS` → `ROUTE_PRODUCTS`: BF = HRC (`Southern region`,
  `Eastern region`) + Rebar (`Southern region`, `Chhattisgarh`); IF = Rebar (`Durgapur`, `Jalna`). `render()` loops the two
  route tabs, shows a **`st.segmented_control`** clickable tab-strip of that route's products (same widget
  as the forecast page's product selector, `label_visibility="collapsed"` + `x if x in prods else names[0]`
  fallback), and renders the picked one.
- `_render_product(product, plants, key)` + `_editor(prefix, product, ver, key)` gained a **`key`** arg
  (route+product, e.g. `bf_rebar`/`if_rebar`) that namespaces every widget/session key — needed because
  `st.tabs` runs both tab bodies each rerun and Rebar now lives in both routes. `product` ('HRC'/'Rebar')
  still drives labels + seeded defaults (electricity norm 450 vs 400). Engine untouched.
- File: `portal/calculators/calc_cost.py`.

### 2026-07-15 (latest+++++++) — Performance tab: KPIs now mirror the accuracy table's metric columns + new Delta chart
- **The 3 KPI cards are now the averages of the accuracy table's own metric columns.** Each commodity
  block in `Accuracy_Table_11.xlsx` (sheet `Ensemble_WgtMean`) is **7 cols wide**: `Actual, Forecast, MAE,
  MAPA (%), Delta (%), Directional (%), *Directional Ratio`. The metric cells are **Excel formulas with no
  cached values** (pandas reads them as NaN), so `data_loader._read_accuracy` now **recomputes them exactly**
  and stores three point-valued (0..1) columns — `AbsAcc`, `DirAcc`, `DeltaAcc`. `accuracy_kpis` returns
  `{mapa, dir_acc, delta_acc}` = each column's mean × 100 (blank weeks skipped, matching the sheet's AVERAGE
  rows). `hit_rate_12` and the old all-weeks `Hit`-based `dir_acc` are gone.
  - **MAPA (%)** = `1 − |Actual − Forecast| / Actual`.
  - **Directional (%)** = `1` if predicted dir matches actual (both inside the ±500 dead-band = a correct
    "flat" call), else `0`. `Hit` is now `DirAcc == 1` so the "Weekly directional hit accuracy" chart matches.
  - **Delta (%)** = share of the actual week-over-week move the forecast captured, signed & capped at 1
    (predicted-flat → `500/|move|`; wrong-way → negative). Blank (NaN) for week 1 and predicted-move-but-flat
    weeks. `th = FLAT_THRESHOLD (500)`.
- **New chart `delta_acc_bar(view)`** — the weekly **Delta (%)** column (×100), green-heavy gradient, in a new
  **"Weekly delta accuracy"** section. Display clamped to [−100, 100] (true value in hover); blank weeks are gaps.
- **Accuracy-chart order matches the KPI cards: absolute → directional → delta** (below the Actual-vs-forecast
  line + the Rs. deviation bars).
- Card captions: Directional = "correct up/down/flat calls", Delta = "avg weekly move capture". `data_loader`
  imports `numpy as np`. Verified against the real file (HRC: MAPA 99.2 / Dir 88.9 / Delta 87.8).
- Files: `portal/app.py`, `portal/data_loader.py`.

### 2026-07-15 (latest++++++) — Removed PDF generation from all calculators
- **The "Generate branded PDF report" feature is gone from all three calculators.** Removed the download buttons
  and all PDF-building code: `calc_elasticity.py` (inline PDF block + `datetime` import), `calc_import_price.py`
  (`build_pdf()` + the PDF-snapshot block + `datetime` import), `calc_cost.py` (`_cost_section()`,
  `_cost_report_bytes()`, the per-product `st.session_state["cost_report_*"]` stash, the "Report" section/button,
  and the `datetime` import). All three dropped `import report_pdf as report`.
- **`portal/report_pdf.py` is now orphaned** (no remaining importers) but left in place; `fpdf2` is still in both
  `requirements.txt` files. Delete both if the branded-PDF base won't be reused. (app.py's PDF references are the
  unrelated analyst-call deck upload/download — untouched.) Engines/calculation logic unchanged.

### 2026-07-15 (latest+++++) — Report PDFs: number every page, starting at 1
- **`report_pdf.py`: every page now carries a number, cover = 1.** Switched from the inner-only `_content_pages`
  counter (cover/back cover unnumbered, first content page was "1") to fpdf's 1-based `page_no()`. `footer()` runs
  on all pages: cover/back cover (tracked in `_cover_pages`) show a plain white number in the blue band above the
  red strip; inner pages keep the red footer bar with `www.bigmint.co` + `pg. N`. So a Cost report reads 1 (cover),
  2 (HRC), 3 (Rebar), 4 (back cover).

### 2026-07-15 (latest++++) — BigMint-branded (CodeG) PDFs; one PDF per report with a section per commodity
- **New shared module `portal/report_pdf.py` — `BrandedPDF(FPDF)` (CodeG formatting).** A4 portrait: solid-blue
  **cover** (white logo + title/subtitle/meta, gray site band, red bottom strip), **inner pages** (white, blue
  Archivo-Bold page title top-left, blue logo top-right, gray rule, **red full-width footer bar** with
  `www.bigmint.co` + `pg. N`), and a **back cover** (Contact Us). Palette = brand blue `#024CA1` / red `#FF4036` /
  body `#1A1A1A` / gray `#E8E8E8`. Helpers: `cover()`, `back_cover()`, `start_section(title, meta)` (new page per
  section), `subheader()`, `body()`, `keyvals()`, `table(headers, rows, widths, aligns, bold_rows)` (blue header,
  zebra rows, thin gray rules, bold+tinted total rows), `pdf_bytes()`.
- **Brand assets bundled into the repo** so PDFs render branded on the deployed app (the `C:\…\CodeG\` paths are
  local-only): `portal/assets/fonts/Archivo-{Regular,SemiBold,Bold}.ttf`, `portal/assets/bm_logo_light_bg.png`
  (blue logo → white pages), `portal/assets/bm_logo_dark_bg.png` (white logo → blue cover). **Graceful fallback:**
  missing fonts → core Helvetica (with latin-1 sanitising); missing logos → skipped. Never crashes. Needs `fpdf2`
  (`add_font`); on plain fpdf it falls back to Helvetica.
- **All three calculators now emit ONE branded PDF** (cover → section(s) → back cover), replacing their old
  ad-hoc `FPDF` subclasses (`HRC_Snapshot_PDF` / two `Report_PDF`) + local `_pdf_bytes`:
  - **Cost Head (multi-commodity):** a single **"Generate branded PDF report (HRC + Rebar)"** button *below the
    tabs* produces one PDF with **a separate page/section per commodity** (HRC page, Rebar page). Each
    `_render_product` stashes its results in `st.session_state[f"cost_report_{product}"]` (both tab bodies run
    each rerun), and `_cost_report_bytes()` / `_cost_section()` assemble them. The per-tab PDF buttons are gone.
  - **Landed Cost:** `build_pdf()` now returns a `BrandedPDF` (cover + "HRC — Import vs Landed Cost" section + back
    cover); button → `report.pdf_bytes`.
  - **Price Sensitivity:** branded cover + "HRC — Price Elasticity Forecast" section (summary keyvals + driver table).
- Files: `report_pdf.py` (new), `calculators/calc_cost.py`, `calculators/calc_import_price.py`,
  `calculators/calc_elasticity.py`, `portal/assets/*`. Engines untouched. Verified: each builds a valid multi-page
  PDF with Archivo (Cost report = 4 pages: cover+HRC+Rebar+back). ⚠ Eyeball the branded output in-app.

### 2026-07-15 (latest+++) — Cost Head: HRC/Rebar tabs with named plants; drop cost-breakup table
- **Removed the "Cost breakup — Plant 1 vs Plant 2" AgGrid + the 4 metric tiles below it.** `import grid`
  dropped from `calc_cost.py` (no longer used). Per-plant totals/margins now read off the chart labels + banner.
- **Product selectbox → HRC / Rebar tabs.** `render()` now renders a `bm-calc-head` heading, then
  `st.tabs(["HRC","Rebar"])`, then the methodology/glossary once below. Each tab calls new
  **`_render_product(product, plants)`** with its named plants:
  - **HRC:** `Southern region`, `Eastern region` (2 plants).
  - **Rebar:** `Southern region`, `Chhattisgarh`, `Durgapur`, `Jalna` (4 plants).
  Plant list lives in `PRODUCT_PLANTS`. Editable tables lay out **two per row** (Rebar → 2×2). Controls
  (USD→INR, Market price, Reset) and the reset-version are **per-product** (`cost_fx_{p}` / `cost_mkt_{p}` /
  `cost_ver_{p}`); editor keys are `cost_p{idx}_{product}_{ver}`. Chart/banner/verdict now scale to N plants
  (verdict: "X of N plants profitable… best margin …").
- **PDF** moved to `_build_pdf(product, plants, …)` — one column per plant (2 or 4), widths computed from the
  page width; `_ascii()` guards the latin-1 core font. Engine still **byte-for-byte unchanged** (HRC total
  Rs. 53,445/MT verified). File: `calculators/calc_cost.py`. ⚠ Visual-only — verify in-app.

### 2026-07-15 (latest++) — Cost Head calculator rebuilt from scratch (engine untouched)
- **`calculators/calc_cost.py` `render()` fully rewritten; the calculation engine is byte-for-byte unchanged**
  — `_elem_cost()` = `price × FX (if USD) × norm`, summed to ex-works total, `margin = market − total`;
  HRC default total still **Rs. 53,445/MT**, electricity norm still 450 (HRC) / 400 (Rebar). Verified numerically.
- **New layout (themed like Landed Cost):**
  - **Dual-axis chart on top** (`_cost_margin_figure`, plotly): total-cost **bars** per plant + market-price
    **dashed line** on the left axis; **mill margin** as diamonds on a **secondary right axis** (green/red by sign).
  - **Scenario controls moved to the right of the chart** (`st.columns([2.5,1])`): Product, USD→INR rate,
    Market price, + a Reset button. No card/box around them.
  - **Plant cost cards → two editable `st.data_editor` tables** (`_editor`), columns Cost element / Basis /
    Currency / Price / Norm; `num_rows="fixed"`, keyed by `cost_{p}_{product}_{ver}` so switching product
    re-seeds and Reset (version bump) clears edits. Currency is now **per-row** (the old global
    "Change All Currencies To" toggle + `sync_all_units` are gone). Edits update the chart **live** (no
    Calculate button — no derived column feeds back into the editor, so no snap-back).
  - **Cost breakup** = themed AgGrid (`grid.bm_grid`) comparing Plant 1 vs Plant 2 per element + a 4-metric
    row (total cost + mill margin % per plant), replacing the old breakdown cards.
  - **KPI banner + management verdict** placeholders (`.kpi-banner` / `.mgmt-box`) like Landed Cost.
  - **Methodology & Logic → infographic** (`_methodology_infographic` + `_glossary`): Inputs→Engine→Outputs
    panel, 6-step equation pipeline, glossary — reusing theme's `.bm-engine` / `.bm-flow` / `.bm-factor-grid`.
  - PDF report preserved (same columns/rows, now sourced from the edited tables).
- File: `calculators/calc_cost.py` only. ⚠ Visual-only rebuild — verify in-app.

### 2026-07-15 (latest+) — Dropdown double-border fix + Cost Head top-row box removed
- **Selectbox "box outgrowing the border" fixed (app-wide).** `theme.py`'s `[data-testid="stSelectbox"] div`
  rule recoloured the border on *every* nested div, so any wrapper still carrying a stray reset border-width
  showed as a second box around the rounded control. Now: zero all inner borders (`border-color:transparent`)
  and paint exactly one rounded orange border on `[data-testid="stSelectbox"] > div:last-child` (the baseweb
  select wrapper, after the label). File: `theme.py`.
- **Cost Head top control row: white card box removed.** The Product / USD-to-INR / Market Price / Change-All-
  Currencies row was wrapped in `st.container(border=True)` → a stark white card ("weird white backbox" behind
  the labels). Dropped to a plain `st.container()` so the controls sit clean on the page. File:
  `calculators/calc_cost.py`. ⚠ Visual-only. The per-section panels (Raw Material / Fluxes & Alloys / Power /
  OpEx) + breakdown cards still use the same white `border=True` card — left as-is (not flagged); flatten them
  too if wanted.

### 2026-07-15 (latest) — Landed Cost: admin-set org defaults + per-user sandbox, FOB snap-back fixed, no price sheet
- **FOB no longer snaps back on edit.** Root cause: `Spot Rs./t` was re-derived from the editor's *live* edit buffer
  (`_live_fob`), which changed the data_editor's source frame on every keystroke; Streamlit 1.59 discards a
  data_editor's pending edits when its input `data` changes, so the typed FOB reverted. Fix: **Spot is now derived
  from the COMMITTED FOB** (× FX) only — the source frame is stable across edit-reruns, so edits persist until
  **Calculate**. `_live_fob` and the edit-buffer read removed.
- **No more price-sheet fetch.** Dropped the CSV feed entirely from this calculator: removed `fetch_fob_prices`,
  `load_price_feed`, `_load_price_feed`, `_csv_mtime`, the `HRC - Copy.csv` path resolution, `CSV_FOB_COLS`,
  `DOMESTIC_COL`, and the `os`/`data_loader` deps here. FOB/freight/FTA/globals now come from **defaults only**.
- **One org-wide set of defaults, editable by the Admin.** New built-in fallbacks `GVAR_DEFAULTS` + `LOC_DEFAULTS`
  in `calc_import_price.py`; `_effective_defaults()` merges the **admin-saved values** on top (persisted in Postgres).
  Storage: new generic **`app_settings`** table (`key TEXT PK, value TEXT JSON, updated_at`) + `db.get_setting` /
  `db.set_setting` (upsert). Table added to `_DDL` so `init_db()` auto-creates it on next run.
- **Admin panel now hosts the same calculator.** `calc_import_price.render(is_admin=True)` is embedded in
  `page_admin()` (under an expander "Admin — Landed Cost defaults"); a **"💾 Save as default for all users"** button
  writes the current globals + committed per-location inputs to `app_settings`.
- **Every user gets a private sandbox** seeded from those defaults; their edits live in session only (reset on
  logout). Independence is via a **key namespace**: admin editor uses `adm_*` session/editor keys, users use `imp_*`
  (`fob_`/`freight_`/`fta_`, `_locs_ver`/`_gvars_ver`, editor keys, `_view`/`_calc`/`_reset`/`_gv_reset`/`_pdf`).
  Container keys `fc_view_box`/`imp_btnrow` stay literal (CSS hooks; only one calc renders per run so no collision).
- Captions reworded (admin: "org-wide defaults … Save as default"; user: "private what-if sandbox … resets on
  logout"). `render()` now takes `is_admin=False`.
- Files: `calculators/calc_import_price.py`, `db.py`, `app.py` (+ this changelog). ⚠ Needs the Neon `database_url`
  secret for Save/seed to persist; with no DB it silently falls back to the built-in defaults (never raises).

### 2026-07-14 (latest+++++++++++++++++++++++) — Landed Cost: live Spot, one-line eq3, plain engine heading
- **Spot Rs./t now tracks the FOB the user types (live), not just committed FOB.** Read the in-progress FOB from
  the data_editor's own state (`st.session_state[ekey]["edited_rows"]`, updated before the edit-triggered rerun) via
  `_live_fob(i, r)`; Spot = that × FX. Default until edited; updates when the FOB cell changes. Still read-only, still
  not in the engine.
- **Equation-pipeline step 3 on one line:** dropped the redundant `SG =` (the duplicate SG left of `<`) →
  `(SG + Cess) if TVD < Thr else 0`.
- **Engine infographic heading:** `<h4>Landed-cost engine</h4>` → styled `<div>` **"Landed-Cost Engine"** so
  Streamlit no longer adds the hover anchor-link icon (same trick theme.py uses for `.bm-flow` titles).
- File: `calculators/calc_import_price.py`.
- **Reset now works reliably (values + FTA checkbox).** Popping the editor key could miss cells; switched to
  **versioned editor keys** — `imp_locs_ver` / `imp_gvars_ver` counters; the editors key on `imp_locs_{ver}` /
  `imp_gvars_{ver}`, and each Reset callback resets the committed defaults and **bumps the version** → the widget
  gets a brand-new key and re-initialises from the default DataFrame (numbers AND FTA checkboxes cleared).
- **Reset hugs Calculate:** wrapped the button row in `st.container(key="imp_btnrow")` with a scoped
  `stHorizontalBlock` gap of 0.4rem (overrides the page's 1.1rem); buttons `width="stretch"` in `[1,1,6]` columns.
- **Tabular view height** 400 → **370** so the table lines up with the graph (AgGrid header/border sit inside the
  height, so it was rendering a touch taller than the plotly chart).
- File: `calculators/calc_import_price.py`.
- Steps 3/4 misrepresented the engine: old step 4 `Cost$ = TVD + SG` implied SG is always added and dropped the
  cess-on-safeguard. Now step 3 defines the whole term conditionally — `SG = (SG + Cess) if TVD < Thr else 0` —
  and step 4 `Cost$ = TVD + SG` is correct in both branches (= TVD above threshold, = TVD+SG+cess below). Matches
  `compute_landed` (`addl = SG + SG_cess` only when `tvd < threshold`). Engine unchanged; display-only fix.
- File: `calculators/calc_import_price.py`.
- Shortened all six step descriptions to a single line so the cards are even height, and set the `.bm-eq` chip to
  `margin-top:auto` (pins it to each card's bottom; cards already stretch equal height) → the six equations now line
  up on one row regardless of text length.
- File: `calculators/calc_import_price.py`.
- Re-wired the location table per request: **FOB $/t is the editable reference** (seeded from the feed), and
  **Spot is now derived read-only `Spot Rs./t = FOB × FX`** (was an editable $ column). Uses committed FOB, so it
  refreshes on Calculate; also tracks global FX changes (FX is live).
- Reverted last entry's editable-`$`-Spot: dropped the `spot_{r}` session_state; Spot is no longer an input, so
  it's excluded from the Calculate pending-diff, the commit, and the Reset. FOB/Freight/FTA remain the editable
  inputs; both Reset buttons unchanged in behaviour (location reset now covers FOB/Freight/FTA only).
- File: `calculators/calc_import_price.py`.
- **Spot $/t is now editable** (was read-only). Seeded/pre-filled from the fetched feed value (`spot_{r}`
  session_state, new); included in the Calculate pending-diff + commit. ⚠ Spot is a persisted **reference** — it
  does NOT feed `compute_landed` (the engine still uses FOB); flag if it should drive the calc.
- **Two Reset buttons** (both via `on_click` callbacks so they can pop the editor-state keys — the only way to
  actually clear in-cell edits):
  - **↺ Reset variables** under the Global-variables table → `_reset_gvars` pops `imp_gvars` (re-seeds defaults);
    disabled unless a global differs from its default (`gv_dirty`).
  - **↺ Reset** beside Calculate → `_reset_locs` restores `spot_/fob_/freight_/fta_` to the fetched values and pops
    `imp_locs`; disabled unless something (buffer or committed) differs from fetched (`dirty`).
- Button row regrouped to `[1, 1, 5]` (Calculate · Reset · caption).
- File: `calculators/calc_import_price.py`.
- **Global-variables table better placed:** graph/vars columns now `vertical_alignment="center"`, so the 8-row
  table sits balanced against the tall graph instead of bunched at the top with empty space below.
- **Less space between sections:** removed the three `st.divider()`s (before Scenario inputs, Sensitivity,
  Methodology) + the blank line before Glossary — the accent-bar `.bm-sec` headings already separate sections.
  (Element spacing inside sections stays at the 0.9rem gap from the prior entry.)
- **"How landed cost is built" is now a plain description** below the heading (removed the blue `.bm-meth-hero`
  card wrapper in `_methodology_infographic`; `.bm-meth-hero` itself stays in theme.py — the main Methodology page
  still uses it).
- File: `calculators/calc_import_price.py`.
- **Fixed invisible pager nav buttons.** `_GRID_CSS` was whitening `.ag-icon` globally → the pagination arrows were
  white-on-white. Now only header icons are white (`.ag-header .ag-icon`); paging arrows are accent-blue (dim grey
  when disabled), so the prev/next/first/last buttons show **on the sides of "Page N of M"** as intended.
- **Default page size 50** (was 52) + **page-size dropdown** offering **10 / 25 / 100** via
  `paginationPageSizeSelector`. (52 wasn't a standard option, which is why the "Page Size" box read blank.)
  `bm_grid` default `page_size=50`; forecasting + performance callers updated 52→50.
- Files: `grid.py`, `app.py`.
- **Tabular view now fills the same footprint as the graph.** `_results_table` dropped `domLayout="autoHeight"` and
  renders at **fixed `height=400`** (= the plotly chart height in `_landed_figure`), so toggling Graphical↔Tabular
  no longer shrinks the block. (The FX-sensitivity grid keeps autoHeight — it's a standalone section.)
- **Element spacing (not section spacing):** the global theme squeezes `stVerticalBlock` gap to 0.65rem, which read
  as cramped *within* sections. `CALC_CSS` now bumps the gap to **0.9rem** (+ `stHorizontalBlock` to 1.1rem),
  injected after theme.py so it wins; page-local (only emitted on the Calculators page). Reverted the earlier
  between-section `_space()` spacers + helper (that wasn't the ask).
- File: `calculators/calc_import_price.py`.

### 2026-07-14 (latest++++++++++++++) — AgGrid: client-side sort (fix slow load + janky animation)
- **`grid.py`: `update_mode=GridUpdateMode.NO_UPDATE`.** Root cause of the slow forecasting load + weird sort
  animation: AgGrid's default `update_mode` returns the grid's data to Python on load **and on every
  sort/filter**, each triggering a full Streamlit rerun that re-mounts the grid. These tables are display-only, so
  NO_UPDATE keeps all sort/filter **client-side** — no round-trip, no rerun, no re-mount. Instant + smooth.
- Also `animateRows=False` + `suppressColumnMoveAnimation=True` (via `configure_grid_options` in `bm_grid`) to kill
  the row-shuffle animation. Dropped the risky `reload_data=` kwarg (removed in some st-aggrid versions).
- Applies to all four grids (forecasting, performance, Landed Cost tabular + sensitivity). File: `grid.py`.

### 2026-07-14 (latest+++++++++++++) — Landed Cost read-only tables → AgGrid too
- **`calculators/calc_import_price.py` now `import grid`.** The **Tabular view** (`_results_table`) and the
  **Exchange-rate sensitivity** table converted from `st.dataframe` to `grid.bm_grid` (blue header, sortable),
  matching forecasting/performance. Both are small so they use `page_size=0` + `domLayout="autoHeight"` (no pager,
  no empty space). Values pass raw; `$` formatter + `vs Domestic` signed-Rs formatter built inline via the `Js`
  callback arg, Landed uses `grid.JS_MONEY`; Decision cell coloured green/red.
- **Kept as `st.data_editor`:** the Global-variables + per-location **input** tables (editing + Calculate gating
  depend on the editor). Only the two read-only display tables moved to AgGrid.
- Same `streamlit-aggrid` dependency/fallback as the prior entry — nothing new to install.

### 2026-07-14 (latest++++++++++++) — Forecasting + performance tables → AgGrid (custom design + native features)
- **New `portal/grid.py` with `bm_grid()` — a BigMint-skinned AgGrid.** Replaces the HTML `.bm-table` +
  `render_sortable_table` for the forecasting *Actual vs forecast* and performance *Week-wise detail* tables.
  Gives what `st.dataframe` can't theme AND `.bm-table` can't do interactively: **blue header (white, bold) +
  click-to-sort + per-column filter + column resize + pagination (52/pg)**. `st.dataframe` renders on a
  `<canvas>`, so it can't take the blue header — that's why we moved to AgGrid.
- **`render_sortable_table` DELETED** (both callers now use `grid.bm_grid`). The Prev/Next pager + its theme.py
  button CSS + the sort dropdown/flip are all gone (superseded by AgGrid's built-in sort/pagination).
- **Cell formatting via shared JsCode** in grid.py (`JS_MONEY`/`JS_DATE`/`JS_DELTA`/`JS_DELTA_PCT`/`JS_DIR_FMT`/
  `JS_DIR_STYLE`, plus `js_row_bg(field,bg)` for the orange forecast-row shading). Values pass raw (numbers/dates)
  so **sorting is correct**, formatting is display-only. Direction column → coloured ▲/▼/→.
- **Skin** = `custom_css` in grid.py (`.ag-header` blue, white bold header text, rounded frame, zebra + hover).
  Theme colours pulled from `theme.PRIMARY`/`theme.NEUTRAL`.
- **Safety:** `grid.py` try/imports `st_aggrid`; if missing/incompatible it **falls back to `st.dataframe`** so the
  app never crashes. `JS_*` are `None` when absent but only used inside the `configure` callback (run only when
  AgGrid is present).
- **Dependency:** `streamlit-aggrid>=1.0.5` added to root + `portal/requirements.txt`. Dry-run resolves to
  **1.2.1.post2**, requires only `streamlit>=1.2` → **no change to the `streamlit==1.59.0` pin** (also pulls
  `python-decouple`). ⚠ **Not installed in the `neuralforecast` env yet** — run `conda activate neuralforecast &&
  pip install streamlit-aggrid` locally (Cloud picks it up from requirements on next deploy). Until installed
  locally you'll see the `st.dataframe` fallback. **Runtime rendering on Streamlit 1.59 still needs a visual check.**
- Files: `grid.py` (new), `app.py` (import + 2 call sites + removed helper), `theme.py` (dropped dead pager CSS),
  `requirements.txt` ×2 (+ changelog + file map).

### 2026-07-14 (latest+++++++++++) — Tables: blue header, no sort UI, nicer pager (forecasting + performance)
- **`render_sortable_table` (app.py) simplified — affects BOTH the forecasting *Actual vs forecast* table and the
  performance *Week-wise detail* table.** Removed the **"Sort by" dropdown** + the **↕ flip button** (and all the
  `_sortcol`/`_flip`/`_desc`/`_sig` state + whole-frame sort + active-column ▲/▼ arrows). Rows now render in the
  DataFrame's given order (both frames are already chronological, so the default view is unchanged). Legacy
  `sortable`/`sort_by` column-dict keys are accepted-and-ignored, so callers didn't change.
- **Pager relaid out** to `Prev · meta · Next` (`[1.3, 4, 1.3]`), meta centred.
- **`theme.py`:** `.bm-table thead th` now **blue-filled (`--bm-primary`) with white text, font-weight 800** (was
  pale `--bm-primary-soft` + dark text @600) — applies to every `.bm-table` (incl. `.bm-table-lg`). Added
  **Prev/Next pager button** styling (pill, blue outline → orange fill on hover, muted when disabled), keyed on the
  `st-key-…_prev` / `…_next` wrapper classes. Bumped `.bm-tbl-meta` to 13px/600.
- Footnotes on both tables updated (dropped the "sort any column…" wording).
- ⚠ *Scope note:* native `st.dataframe` grids (Landed Cost tabular/sensitivity, the data_editors) can't take the
  blue header via CSS — only the custom `.bm-table` component was restyled. Say if those should be converted too.
- Files: `app.py`, `theme.py` (+ changelog).

### 2026-07-14 (latest++++++++++) — Landed Cost: heading + Calculate gate + Spot column + graph/table switch
- **Prominent page heading:** new `.bm-calc-head`/`.bm-calc-title` (30px bold, icon) + subtitle, replacing the
  small `theme.section_title`. Added local `.bm-sec` prominent section headings (19px, accent left bar) + `_sec()`
  helper; used for all major sections (graph, scenario inputs, sensitivity, methodology, pipeline, glossary).
- **"How landed cost is built"** pulled OUT of the `bm-meth-hero` card into its own `_sec` heading (card now holds
  just the description paragraph).
- **Calculate button + edit gating:** table edits are now **pending** (buffered in the `imp_locs` editor state) and
  no longer auto-applied. A primary **Calculate** button sits below the table, **disabled until the buffer differs**
  from the committed `fob_/freight_/fta_` session_state; clicking commits the buffer and everything recomputes.
  Globals table stays live (immediate).
- **Table columns:** removed read-only *Landed Rs./t*; added read-only **Spot $/t** = the price **fetched from the
  CSV feed** for that origin (`fob_data[r]["fob"]` when its `source` is a feed column, i.e. not `Manual*`; **blank**
  for origins not in the file — Middle East / Custom). Columns now Location · Spot $/t · FTA? · FOB $/t · Freight $/t.
- **Graphical/Tabular switch** above the chart — `st.segmented_control` inside a `st.container(key="fc_view_box")`
  so it reuses theme.py's sliding-pill CSS (widget key `imp_view`). Tabular view = `_results_table()` (Location,
  FTA, CFR, TVD, Safeguard, Landed, vs Domestic, Decision; cheapest first).
- **Spacing:** `gap="large"` on the graph/globals row + `st.divider()` between major sections for prominence.
- File: `calculators/calc_import_price.py` only (+ this changelog). ⚠ *Assumption to confirm:* "spot price" = the
  feed's latest FOB assessment per origin (read-only reference). Flag if a different spot was meant.

### 2026-07-14 (latest+++++++++) — Landed Cost: full UI/UX rebuild (engine untouched), theme-aligned
- **`calculators/calc_import_price.py` `render()` rewritten end-to-end; calculation engine (`compute_landed`,
  `fetch_fob_prices`, feed loader, PDF) unchanged.** New top-to-bottom layout:
  1. Management verdict box + blue **Lowest cost source** banner (banner recoloured flat-green → theme-blue gradient).
  2. **Graph on top** (landed-cost diverging bar vs domestic line) with the **global variables** as a small editable
     `st.data_editor` table **to its side** (`st.columns([2.5, 1])`). The 8 globals (Domestic, FX, Threshold CIF,
     Port & misc, BCD %, Cess on BCD %, Safeguard %, Cess on safeguard %) now live in that one table — the old
     "Global assumptions" number_inputs **and** the "Duty rates" expander are gone.
  3. **Customisable per-location table** (`st.data_editor`): Location · FTA? checkbox · FOB $/t · Freight $/t ·
     Landed Rs./t (read-only). Replaces the per-region **cards** (`render_card`/`render_group` deleted).
  4. Exchange-rate sensitivity table. 5. PDF snapshot button (kept). 6. **Methodology & Logic** rebuilt as a
     modular, equation-heavy infographic (`bm-meth-hero` + `bm-engine` Inputs→engine→Outputs + a 6-step `bm-flow`
     equation pipeline using new `.bm-eq` chip). 7. **Glossary** as a `bm-factor-grid`.
- **Removed:** per-region cards, the "FOB price sources & disclosure" expander, the old `st.expander` methodology,
  and dead `breakdown_table()`. Calc module now `import theme` and reuses `theme.section_title/icon/colours`.
- Placeholders (`st.empty()`) hold the top verdict/banner/chart so they render above but compute after the
  location table. **Known minor quirk:** the editor's own read-only *Landed Rs./t* cell lags one rerun after an
  edit (graph/verdict update immediately); Streamlit's edit-triggered rerun corrects it.
- Files: `calculators/calc_import_price.py` (CSS trimmed: kept `.kpi-banner`/`.mgmt-*`, added `.bm-eq`).

### 2026-07-13 (latest++++++++) — All dropdowns white + orange border · horizon tab label · forecast card shows target date
- **ALL dropdowns → white fill + orange border (app-wide).** ⚠ Key gotcha: on the deployed **Streamlit 1.59**
  build the selectbox does **NOT** expose `data-baseweb="select"`, so *all* the `div[data-baseweb="select"]…`
  rules (border, primary-soft tint, bold text) silently no-op — boxes show Streamlit's default pale
  `secondaryBackgroundColor` (#F1F5FB). Fix targets the stable **`[data-testid="stSelectbox"]`** testid,
  **un-scoped so it hits every selectbox in the app** (location pickers, Sort by, Admin, etc.): whitens every
  inner `div`/`input` (`background:#fff`), **recolours the control's existing border to `--bm-accent` (orange),
  colour only**, and colours the arrow `svg` accent too. Recolouring beats adding a border: only the full
  control box has a visible (rounded ~1px) border, so exactly that one element goes orange — wrapping value
  AND arrow, curved corner preserved. (Adding a border to `[role="combobox"]` only wrapped the value, leaving
  the arrow outside.) ⚠ **Do NOT force `border-width`:** Streamlit's reset puts `border:0 solid` on *every*
  div, so a forced width makes a square-cornered outer container's zero-width border suddenly show as a
  **rectangle around the rounded one**; colour-only leaves those at width 0 (invisible). The options popover
  renders in a body portal, so it's unaffected. Was briefly blue + forecasting-only before this generalisation.
- **Horizon tab now has a visible label.** The grouped-graphical **1W/4W/8W/12W** `st.segmented_control`
  (`key="fc_horizon"`) switched `label_visibility` `collapsed → visible` and the label text is now
  **"Forecast horizon (weeks ahead)"** so users see what the pills do. (`app.py`, right rail.)
- **Forecast card title = the target date, not "{n}-week forecast".** In `price_cards()` the second card's
  title is now **"Forecast — 19 July, 2026"** style (long format, no leading-zero day): computed from
  `fwd.iloc[horizon-1]["Date"]` (12-week path is week-ordered, row 0 = week 1; clamped to len). Falls back to
  the old `"{n}-week forecast"` if the date is missing/NA. Value/direction still track the tab as before.

### 2026-07-11 (latest+++++++) — Methodology hero: three accuracy stat cards (single row)
- **Stat row now leads with the three accuracy metrics.** The "Price accuracy" card was relabelled **"Average absolute price accuracy"** (value `~98%` unchanged), and two new `bm-stat` cards were added: **Delta accuracy `~60%`** and **Directional accuracy `~70%`** (static marketing figures, matching the Performance dashboard's KPI trio). Row is 6 cards: the 3 accuracies, then 15+ yrs / Typical absolute price difference 1–2% / IOSCO. Also renamed the delta card label **"Typical delta (error band)" → "Typical absolute price difference (error band)"**. → `app.py` `page_methodology()`.
- **Grid `4 → 6` columns** so all 6 cards sit on one line (`.bm-stat-row` in `theme.py`; the narrow breakpoint stays `1fr 1fr` for mobile). `bm-stat-row` is used only on the Methodology page.

### 2026-07-11 (latest++++++) — Analyst-call AI auto-fill: switched Gemini → Groq (429 free-tier cap)
- **Provider swapped to Groq** (free, OpenAI-compatible) after the Gemini key hit a **429 quota** cap. `portal/ai_fill.py` now POSTs to `https://api.groq.com/openai/v1/chat/completions` (default model **`llama-3.3-70b-versatile`**, `response_format={"type":"json_object"}`, `Authorization: Bearer`); response parsed from `choices[0].message.content`. `extract_pptx_text()` unchanged. Function renamed **`gemini_ready()` → `ai_ready()`** (app.py updated). Key now read from **`st.secrets['groq']['api_key']`**; secrets `[gemini]` block replaced with **`[groq]`** in both `secrets.toml` (placeholder `YOUR_GROQ_API_KEY` — user pastes a free key from console.groq.com) and `secrets.toml.example`. `python-pptx` dep unchanged.

### 2026-07-11 (latest+++++) — Analyst calls: AI auto-fill from the pitch deck (initial, Gemini)
- **New module `portal/ai_fill.py`.** `extract_pptx_text(bytes, name)` (pulls titles/bodies/tables/speaker-notes from a **.pptx** via `python-pptx`; raises on legacy `.ppt` or empty deck), and `fill_analyst_sections(deck_text, sections)` → `{"summary": <short paragraph>, <section>: <one-liner>, …}`. Deck text capped at 20k chars. (Originally Gemini; see the newer entry above — now Groq.)
- **Admin editor wiring** (`page_admin()`): the **Pitchdeck uploader moved out of the `st.form`** (above it) so one upload both attaches the deck on save *and* feeds the AI; added an **"✨ Auto-fill sections with AI"** button next to it (enabled only for a `.pptx` when a key is configured). On click it extracts text → calls the LLM → writes the drafted summary + section lines into the form fields' `session_state` keys → `st.rerun()` (admin reviews/edits before Save). Summary = short paragraph, each section = one-liner, per spec.
- **Form field seeding:** the Headline-summary + section inputs no longer pass `value=`; instead their `session_state` keys are seeded once per selection (from the edited call) *before* the form. This lets the AI button set them directly without Streamlit's "default value + Session State" warning. PDF uploader stays inside the form.
- **Secrets / deps.** API key **never hardcoded** (public repo) — read from git-ignored `secrets.toml`. Added **`python-pptx>=0.6.21`** to both `requirements.txt` files. On Streamlit Cloud, paste the provider secrets block into *Manage app > Settings > Secrets*. Local testing needs `pip install python-pptx`.

### 2026-07-11 (latest++++) — Login card: top spacing for breathing room
- **Sign-in / reset card sits lower.** Added a responsive top margin — `margin: clamp(48px, 9vh, 120px) auto 0` (was `0 auto`) — on `.st-key-login_card, .st-key-reset_card` so the card no longer hugs the topbar; scales with viewport height but stays bounded. Width (460px) unchanged. → `theme.py` login/reset card rule.

### 2026-07-11 (latest+++) — Loading overlay show-delay .4s → .7s
- **Reduced overlay flashing.** The translucent in-app loading overlay's show-delay was raised from **.4s to .7s** — reruns that finished just over the old threshold still briefly flashed the scrim/spinner. Now only reruns lasting >.7s reveal it; genuinely slow ones (page switches, chart loads) still show it. Only the `:has(stStatusWidget)` (visible) rule's transition delay changed; the base rule still hides promptly. → `theme.py` `inject_css()` loading-overlay block.

### 2026-07-11 (latest++) — Analyst-call cards: modular heading + narrower body measure
- **Heading restructured.** The single `bm-call-title` line ("<date> — <title>") is now a two-part header: a small **orange uppercase date eyebrow** (`.bm-call-date`, `ACCENT` colour, letter-spaced) above a **larger 18px title** (`.bm-call-title`, was 16px, date text removed). Markup change in `_render_call_card()` (`.bm-call-head` wrapper wrapping `.bm-call-date` + `.bm-call-title`).
- **Body no longer runs edge-to-edge.** `.bm-call-summary` and `.bm-call-secs` are capped at **`max-width:82%`**, so the summary paragraph and section rows end well left of the right edge (roughly under the "Report · Pitchdeck · Video" line) with a consistent right gutter — reads as a defined text column instead of full-bleed. → `theme.py` `.bm-call-*` block.

### 2026-07-11 (latest+) — Analyst calls: "Watch video" button → "Video Podcast"
- **Button relabelled** on the analyst-call cards: **"Watch video" → "Video Podcast"** (both the live `link_button` when `call["video"]` is set and the fallback `button` that opens the not-available modal). Icon (`:material/play_circle:`) and behaviour unchanged. Also updated the admin "Video link (URL)" field help text to match. → `app.py` `_call_card()` + `page_admin()` editor.

### 2026-07-11 (latest) — Performance KPI: "Average delta" → 12-week directional hit rate (labelled "Delta accuracy")
- **Third KPI card replaced.** The Performance dashboard's k3 card was **"Average delta"** (`avg_delta` = mean of `DeltaPct`); it now shows the count of *correct* weekly directional calls over the **last 12 weeks ÷ 12** as a percentage (`{:.0f}%`), sublabel "correct calls / last 12 weeks". Card label is **"Delta accuracy"** (the metric under the hood is the 12-week directional hit rate). → `app.py` `page_performance()` k3 + `data_loader.accuracy_kpis()`.
- **`accuracy_kpis()` change:** dropped the `avg_delta` key, added `hit_rate_12 = rows.tail(12)["Hit"].sum() / 12 * 100` where `rows = valid.iloc[1:]` (skips the first, prior-reference-less week — same `iloc[1:]` logic the directional chart/KPI already use). Denominator is fixed at **12** per spec; empty-frame return now yields `hit_rate_12: None`. No other call sites referenced `avg_delta`.

### 2026-07-10 (latest++++++) — +5 Mundra commodities; accuracy table renamed 6→11
- **Added 5 Mundra products** to `data_loader.STEEL_PRODUCTS` (display key → ff/acc sheet):
  `HRC Mundra`→`HRC MUNDRA`, `HR Plate Mundra`→`HR PLATE MUNDRA`, `Rebar BF Mundra`→`REBAR BF MUNDRA`,
  `Rebar IF Mundra`→`REBAR IF MUNDRA`, `Structure Mundra`→`STRUCTURE MUNDRA`. Catalog is now **11**.
  No parser change — the new `forecast_forward` sheets and the `Accuracy_Table_11` wide blocks share the
  existing layout (verified: 12 forward rows + 82 accuracy actuals for every product). They slot into the
  existing groups automatically via `_product_group` prefix matching (HRC / HR Plate / Rebar / Structure),
  so each group's location dropdown gains its Mundra entry.
- **Full names for the location dropdown** added to `app.py` `FORECAST_LOCATION_LABELS`: "HRC Mundra -
  2.5-8mm IS2062", "HR Plate Mundra - 20-40mm E250 BR", "Rebar Mundra BF - 12-32mm Fe500D", "Rebar
  Mundra IF - 12-32mm Fe500", "Structure Angle Mundra - 150x150 IF Route".
- **Accuracy table renamed `Accuracy_Table_6.xlsx` → `Accuracy_Table_11.xlsx`** in the data repo. Frontend
  updated: `ACC_FILES = {"11-week": "Accuracy_Table_11.xlsx"}` and all `load_accuracy("6-week", …)` call
  sites → `"11-week"` (`app.py` ×3 + `data_loader.last_actual_date`). `_fetch_private_data_dir` /
  `data_files()` derive from `ACC_FILES`, so they pick up the new file automatically.
- **Access note:** roles with a saved Commodity-access subset (`db.role_commodities`) won't see the new
  products until an admin adds them; roles with no saved config (default) see all 11. **Deploy note:** the
  private-data fetch is `@st.cache_resource` (once per deploy) — push the data repo AND reboot the app so
  it re-fetches `Accuracy_Table_11.xlsx` + the updated `forecast_forward.xlsx`.
### 2026-07-10 (latest+++++) — Analyst-call cards: visual polish (spacing + modern buttons, orange hover)
- **`_render_call_card` restyled** (`app.py` + `theme.py`). The bordered container now takes a
  `key=f"callcard_{cid}"` so its `st-key-callcard_*` class can **scope button CSS to the card only**
  (nav / Sign-in / Log-out buttons untouched — see the calculators gotcha). New/updated `theme.py`
  classes: **`.bm-call-title`** (16px bold, replaces the old `**bold**`), **`.bm-call-kinds`**
  (uppercase caption), **`.bm-call-summary`** (line-height 1.6), roomier **`.bm-call-sec`** rows
  (padding 7→10px, gap 12→16px, label 140→150px), and a **`.bm-call-sep`** divider before the action
  row (added via an empty div in `app.py`). Buttons (`.stButton` / `.stDownloadButton` / `.stLinkButton`
  inside the card): rounded 10px, subtle border + shadow, and **hover → orange** (accent border/text,
  tinted bg, `translateY(-1px)` lift); disabled deck buttons stay muted (`opacity:.5`, no hover). All
  button styling is behind the `div[class*="st-key-callcard"]` scope.
### 2026-07-10 (latest++++) — Footer co-brand is user-specific (BigMint-only before login)
- **`theme.footer()` now derives its co-brand from the logged-in role** instead of the hardcoded
  "© BigMint - Adani". Reads `st.session_state.user` → `profile_for(role)["cobrand_label"]`: Adani role
  shows "© BigMint - Adani · AI Labs", internal roles (Analyst/Admin, no co-brand) and the **login
  screen (no user)** show "© BigMint · AI Labs". Mirrors the topbar rule; no call-site changes (footer
  reads session state itself). Label is title-cased so a future client's `cobrand_label` shows too.
### 2026-07-10 (latest+++) — `adani_dev` staging role removed everywhere
- **Dropped `adani_dev` from the codebase** now the grouped layout is promoted and the staging users
  are being deleted. `GROUPED_FORECASTING_ROLES` is now `{"adani", "analyst", "admin"}` (`app.py`), and
  every `adani_dev` mention in code comments/docstrings (`app.py`, `theme.py`) was reworded to "grouped
  layout / grouped roles". Current-state docs in this file updated too (Modules, "Edit X → go here",
  Appendix A). Older dated changelog entries below still name `adani_dev` as a historical record of the
  staging phase. No behaviour change — the three live roles already had the grouped layout.
### 2026-07-10 (latest++) — Login screen is BigMint-only (no client co-brand)
- **`theme.render_topbar()` now drops the co-brand chip when there's no user** (login screen). Before,
  `render_topbar(None)` fell back to `DEFAULT_PROFILE` (which carries the Adani co-brand), so the login
  topbar showed BigMint · Adani · title. Now `cobrand = _cobrand_logo_html(profile) if user else ""` —
  the login bar is **BigMint logo · title** only. Logged-in users still get their role's co-brand
  (Adani for the Adani role; internal roles already had none). Title text unchanged (product name, not
  a company). One-line change in `theme.py`.
### 2026-07-10 (latest+) — Grouped/adani_dev layout PROMOTED to Adani, Analyst, Admin
- **`GROUPED_FORECASTING_ROLES` widened `{"adani_dev"}` → `{"adani_dev", "adani", "analyst", "admin"}`**
  (`app.py` ~line 780). All the behaviour that was gated on `_grouped_forecasting(role)` now applies to
  the three live roles: the **grouped Price-forecasting layout** (group tab-strip → Graphical/Tabular
  pill switch + right-aligned full-name location dropdown → graph on top → price cards to the right +
  rationale card), the **Performance page grouped picker**, and the **Methodology weekly-only "Forecast
  horizons" card**. `adani_dev` kept in the set only until those staging users are deleted (user will
  remove them). Single-flag promotion — no other role gates exist; branding (`theme.ROLE_PROFILES`) is
  unchanged. Non-grouped fallback code stays for any future role not in the set.
### 2026-07-10 (latest) — Analyst calls reformat: admin-set video link + full call date; button renames
- **Analyst-call model gained `date` + `video`** (`data_loader.py` `SAMPLE_ANALYST_CALLS` — each entry
  now carries `"date": "YYYY-MM-DD"` and `"video": ""`; `month` kept for back-compat/fallback).
- **Card (`app.py` `_render_call_card`, shared by Analyst page + Admin preview):** header shows the
  **full call date** (new `_call_date_label(call)` → `%d %B %Y` from `date`, else legacy `month`); the
  **PPT button is relabelled "Download Analyst Call Pitchdeck"** (PDF button stays "Download Market
  Summary Report"); the **"Watch video"** button is now **`st.link_button(url)` when `call["video"]` is
  set** (opens the admin URL in a new tab) and falls back to the `_video_unavailable` modal when blank.
  Button row `st.columns([2, 2, 1.2, 1])`; header split `[4, 2]`; top-right caption → "Report ·
  Pitchdeck · Video".
- **Admin call editor (`app.py` `page_admin`):** the "Month *" text box is replaced by a
  **"Analyst call date *" `st.date_input`** (`format="DD/MM/YYYY"`, default via new `_call_date_value`
  — parses `date`, else `month`, else today); added a **"Video link (URL)" text input**; deck uploaders
  relabelled "Market Summary Report (PDF)" / "Analyst Call Pitchdeck (PPT)". Saved record now writes
  `date` (ISO), `month` (derived `%B %Y`, back-compat) and `video`; `id` for new calls = the ISO date;
  the old "Month is required" guard was dropped (date_input always returns a value). Selectbox labels
  use `_call_date_label`. NB: `_slug()` is now unused (was only the month→id slug) — left in place.
### 2026-07-10 (later) — Analyst calls: "Download PDF" → "Download Market Summary Report"; live "Watch video" → not-available modal
- **Analyst-call card (`app.py` `_render_call_card`, shared by `page_analyst` + Admin preview).**
  (a) The **"Download PDF"** button is relabelled **"Download Market Summary Report"** (still the same
  `_deck_button` wired to `call["pdf"]` / `application/pdf`; disabled when no PDF is uploaded, as
  before). (b) Added an always-live **"Watch video"** button (`:material/play_circle:`) that opens a
  new **`@st.dialog("Video not available")`** modal (`_video_unavailable`) — the link stays enabled but
  routes to a "not available" placeholder since no clips exist yet. Button row widened to
  `st.columns([2.4, 1.1, 1.1, 2])` for the longer report label. NB: the small top-right card caption
  still reads "PDF / PPT" (`app.py` ~1162) — left as-is (not requested); update to "Report / PPT /
  Video" if desired.

### 2026-07-10 — Scenario Simulation: tabs renamed + reordered; Price Sensitivity Reset + Rs. contributions; Methodology sentiment removed + weekly-only horizon for adani_dev + pipeline chain → engine infographic
- **Methodology pipeline chain → "From data to forecast" engine infographic** (`app.py`
  `page_methodology()` + `theme.py`). Replaced the old 6-step numbered `.bm-flow` chain (Market data →
  Signal engineering → ML → Ensemble → 12-wk → Accuracy) with a general **Inputs → Model → Outputs**
  infographic (`.bm-engine*`): left "Inputs" card (15+ yrs BigMint-assessed prices; cost/supply-demand;
  global/macro), a gradient center "Forecasting model" node ("a defined, data-driven methodology fits
  historical price relationships across selected factors from available data"), and a right "Outputs"
  card (12-week path; up/down/flat; back-checked vs spot). Deliberately **general** — no over-claimed
  model names — matching BigMint's own high-level published methodology (checked
  bigmint.co/forecast/product/27 + /methodology; both keep it high-level, IOSCO-assured assessments).
  New CSS `.bm-engine / .bm-engine-col / .bm-engine-in/out / .bm-engine-h / .bm-chip / .bm-engine-core /
  .bm-engine-arrow` in `theme.py`, collapsing to one column under 1024px. Section title changed
  "The forecasting pipeline" → **"From data to forecast"** (avoids duplicating the hero heading).
- **Methodology "Forecast horizons" — weekly-only for `adani_dev`** (`app.py` `page_methodology()`).
  Gated on `_grouped_forecasting(user["role"])` (the existing `adani_dev` staging flag): that role now
  sees a **single prominent horizon card** ("Weekly — 12-week rolling forecast", stating monthly/
  quarterly/annual are not part of this build) instead of the 4-up grid, since Adani has weekly models
  only. All other roles keep the original 4 cards (Weekly/Monthly/Quarterly/Annual) + the 12-week
  footnote. Styling is inline overrides on `.bm-horizon` (no theme.py change). Promote to production
  Adani later by widening the gate (same pattern as `GROUPED_FORECASTING_ROLES`).
- **Methodology page — all "sentiment" mentions removed** (`app.py` `page_methodology()`). Edited the
  hero paragraph (dropped "combined with market sentiment"), the pipeline steps ("Signal engineering"
  desc lost "+ sentiment"; "ML + sentiment" step → **"Machine learning"** / "Multiple models predict
  each product."), **removed the "Market sentiment" key-factor card** (`mic`) leaving 5 factors, the
  Transparency "Explainable by design" card ("cost and supply&ndash;demand factors"), and the closing
  disclaimer ("unexpected events or market disruptions"). NB: the **`RATIONALES` placeholder** on the
  Price Forecasting page still says "Trade &amp; sentiment / market sentiment" (`app.py` ~762) — left
  as-is, out of scope (methodology only).
- **Price Sensitivity (`calc_elasticity.py`): Reset button + Driver Contribution now in Rs.** (a) A
  **"Reset"** button under the "Market Shocks (%)" heading zeroes every shock slider via an `on_click`
  callback (`_reset_shocks` sets each slider's `st.session_state[col] = 0.0` — must be a callback, not
  inline, since the sliders are already instantiated above). (b) The **Driver Contribution** table's
  **"Contribution (%)"** column was replaced with **"Price Change (Rs.)"** = `current_price *
  (shock × elasticity)` (linear per-driver rupee impact), rounded to whole Rs. and sorted by it. The
  **PDF report** breakdown was updated to match (header + `Rs. …` cell) so it doesn't KeyError on the
  renamed column. (c) Each **Market Shocks slider now shows its Rs. price impact** below it via
  `st.caption(f"Price impact: Rs. {…:+,.0f}")` — same `price_contributions` array (now computed once
  above the slider loop and reused by the Driver Contribution table). Sliders stay in **%** (the
  log/elasticity model needs % input); only the per-driver Rs. effect is surfaced alongside.
- **Scenario Simulation tabs renamed and reordered** (`app.py` `page_calculators()`, ~line 1525).
  New order + labels: **1. "Price Sensitivity"** (`calc_elasticity`, was "Price Elasticity (HRC)"),
  **2. "Landed Cost"** (`calc_import_price`, was "Import vs Landed Cost (HRC)"),
  **3. "Cost Head"** (`calc_cost`, was "Production Cost & Margin"). Only the tab labels + order
  changed; each calculator's own `render()` body is untouched.

### 2026-07-09 — Go-live polish: nav centring, Scenario Simulation rename, week-of-month date, logo de-boxed, prototype text removed, forecasting H2 removed, zoom buttons re-done as HTML (no jitter), forecasts rounded to Rs.50, sortable+paginated data tables
- **Forecasts rounded to the nearest Rs.50** — new `app.py` `_round50(x)` (NaN/None pass through).
  Applied to every DISPLAYED forecast: the price cards (`_forecast_at`), the main chart's forecast
  line + hover (`forecast_chart` `fc_vals`, hover now `,.0f`), the performance chart's forecast line +
  hover (`perf_chart`), and both data tables (below). Actuals/spot are left untouched; accuracy KPIs
  (MAPA etc.) still compute off the raw forecast — only the shown numbers are rounded.
- **Data tables → sortable (whole-dataset) + paginated, 52 rows/page** — new reusable
  `app.py` `render_sortable_table(df, columns, key, rows_per_page=52, row_class, table_class, footnote)`.
  Controls row above each table: a **"Sort by" selectbox** (offers the sortable columns), a **flip
  icon button** (`:material/swap_vert:`) toggling asc/desc with a ▲/▼ on the active column header, a
  meta line ("Rows 1–52 of N · Page p/n"), and **Prev/Next** buttons. Sorting runs on the ENTIRE frame
  (`df.sort_values(..., na_position="last")`) BEFORE the page is sliced, so descending really surfaces
  the last rows; a change of sort column or direction jumps back to page 1. State per table in
  session_state (`{key}_sortcol/_desc/_page/_sig`). Wired into: (1) the **forecasting Tabular view**
  (`render_table_view` now builds one unified frame — history rows + forward rows tagged `_fwd` for the
  `bm-fc-row` shading — Forecast rounded, Δ = Actual − rounded FC; Direction column non-sortable), and
  (2) the **Performance "Week-wise detail"** table (Forecast rounded, Delta/% recomputed off it).
  New `theme.py` `.bm-tbl-meta` style for the meta line. The Admin user table (`st.dataframe`) already
  sorts natively and was left as-is.
- **FIX: Prev/Next pagination now uses `on_click` callbacks** (`render_sortable_table`). The first cut
  computed the buttons' `disabled` flags + the page slice from `cur` (the page BEFORE the click) but
  updated `page` inline AFTER rendering the buttons — so for one render the state lagged: Prev looked
  active on page 1, Next looked active on the last page, and a click could appear to "do nothing".
  Now Prev/Next mutate `st.session_state[{key}_page]` via an `on_click` `_bump(±1)` callback (which
  runs at the start of the next rerun, BEFORE the controls render), so `cur`, the disabled flags and
  the sliced page always agree in the same render. Page is also clamped + persisted up front so a
  shrunken row count can't strand you past the last page.
- **Performance page: grouped picker + green-heavy gradient bars + section renames.** (1) The product
  picker matches the forecasting page for grouped roles (`_grouped_forecasting`): a **group tab-strip**
  (`key="perf_group"`) + **full-name location dropdown** (`_loc_label`, `key="perf_loc_{group}"`) — now
  laid out **on one row via `st.columns([1, 1.2])`**, tabs left / dropdown **right-aligned** in its
  column (`.st-key-perf_loc_box` = `max-width:640px; margin-left:auto`, no negative pull-up); non-grouped
  roles keep the flat `perf_prod` selector. (2) **"Weekly forecast absolute accuracy"** (renamed) is a
  **green-heavy gradient bar** (`accuracy_chart`): colorscale red→amber→green with `cmin` pushed 0.35·range
  BELOW the min (so the worst week is amber, not deep red), highest = green; **h 300→200** and the
  **y-axis zoomed to `[min(95, floor(min)) … 100]`** since accuracy is always high-90s (variation now
  visible). (3) **"Actual vs Forecast deviation"** (renamed from Weekly delta; footnote "All prices
  rounded off to Rs.50") — `delta_bar` now uses **rounded-forecast − spot**, coloured by |deviation| on a
  **green-heavy** scale (green 0→0.55, amber 0.8, red 1.0), **h 200→320** so small deviations read. (4)
  **"Weekly directional hit accuracy"** (renamed). Both bar charts render via `st.plotly_chart`.
  `theme.py`: `.st-key-perf_loc_box` + fc/perf dropdown inner styling share selectors.
- **Performance charts: same width + tighter y-labels + inline legend + footnote dropped.** The four
  charts (perf line + delta + accuracy + directional) previously each auto-expanded their left margin to
  their own y-label width ("Rs.62,000" vs "98%" vs "Correct"), so they rendered at DIFFERENT widths and
  didn't line up. Now all use a **fixed left margin `_PERF_ML = 68`px with `margin.autoexpand=False`** →
  identical plot width; `r=16, b=30` shared too. The **y-label gap** (`ticklabelstandoff`) dropped from
  `_style_fig`'s **8 → 3** on every performance chart (consistent, tight). The **"Actual vs forecast"
  line chart's legend moved INSIDE** the plot (top-left, translucent-white bg, `y=0.98`) with a slim
  `t=14` top margin. The **"All prices rounded off to Rs.50" footnote was removed** (rounding is applied
  silently). Heights kept (perf/delta 320, accuracy/directional 200). NB `ticklabelstandoff` is already
  used by `_style_fig`, so the installed Plotly supports it.
- **FIX: intermittent `KeyError: 'auth'` at startup** — added `[server] fileWatcherType = "none"` to
  `.streamlit/config.toml`. The error came from Python's import machinery (`sys.modules.pop('auth')`
  in `_load_unlocked`) when Streamlit's watchdog file-watcher purged `sys.modules` mid-import during a
  git-pull redeploy (the traceback fired right at "Pulling code changes from Github"). On Streamlit
  Cloud, code changes arrive as a full process restart, so the watcher is unnecessary; disabling it
  removes the reload race. (Trade-off: no local hot-reload on file save — fine here, the app is
  verified on the deployment, not run locally.)
- **Top nav centred with equal gaps** — `app.py` `top_nav()` column widths changed from
  `[1] + [1.35]*(n-1)` (Home deliberately narrower) to **`[1]*len(items)`** so every nav button is
  the same width and the inter-button gaps are uniform. A small **8px spacer** (`st.markdown` div) now
  sits between the brand bar and the nav row so the nav sits a touch lower. → `app.py` `top_nav()` +
  the line just above `top_nav()`.
- **Home module cards — icon on the heading, bigger heading, left-aligned + vertically centred, equal-length one-liners.**
  The 4 module card-buttons (`.st-key-homemod_*` in `theme.py`) keep the **vertical-stack** format
  (title → one-liner → "Open →"), **left-aligned**, content **vertically centred** in the card
  (`justify-content:center`). Changes this pass: (a) the **material icon is now embedded INSIDE the bold
  title** — `app.py` label is `**:material/{mi}: {title}** {desc} *Open →*` with the `icon=` param
  dropped (proven pattern — `top_nav()` already puts `:material/…:` inside a button label); the title
  `strong` is styled `display:flex;align-items:center;gap:9px` so icon + heading sit on one row, icon
  26px. (b) **Heading bigger**: `strong` font 18px → **21px**. (c) **Descriptions rewritten to ≈95 chars
  each (~2 lines)** so all four wrap to the same number of lines, the cards line up AND the cards look
  fuller (equal length is what keeps them aligned — the desc is inline text in the same `<p>` as the
  block `strong`/`em`, so it can't be height-reserved without splitting the label into separate markdown
  paragraphs, which is unreliable in button labels). (d) **Fill the page:** card `min-height` 196→**230px**
  + padding bumped, and the **"Modules" heading enlarged** — rendered as `.bm-h.bm-modules-h` (22px bold,
  `margin:24px 0 16px`, icon 22px) instead of the default `section_title` size. ⚠ Earlier same-day
  misfire: mis-read "centre" as horizontal + made the `<p>` a flexbox to force 3 lines, which squished
  the whole label into a row — reverted.
- **Zoom-button (1W/4W/8W/12W/26W/YTD/ALL) click "shift" fixed — rangeselector replaced by HTML buttons.**
  A first pass tried CSS (`outline:none` / `user-select:none`) on the SVG `.rangeselector` buttons; it
  did **not** stop the jitter — Plotly re-renders the whole button group on every click and re-measures
  each button, so the strip shifts a pixel or two regardless of CSS. **Fix:** dropped Plotly's
  `rangeselector` from the figure entirely and render the zoom buttons as **plain HTML `<button>`s in a
  fixed `.rangebtns` row ABOVE the plot**, inside the chart iframe (`_HL_TEMPLATE`). Each button carries
  `data-start`/`data-end` (ISO datetimes computed in `forecast_chart`: `end` = last forecast date, `start`
  = `end − N·7 days − forecast span`, plus YTD = Jan-1 and ALL = full history) and a click handler that
  does `Plotly.relayout(gd, {"xaxis.range":[start,end]})` + toggles the `.active` class. Fixed geometry ⇒
  **zero movement**. Wiring: `_render_with_highlighter(fig, …, range_buttons=[…])` builds the row and
  injects `__RANGEBTNS__` + `__ACCENT__` (active-pill colour) into the template; iframe height grows by
  `extra_h=40` for the row; default active button = **ALL** (matches the initial full-range view). Plot
  top margin cut (compact `46→18`) now the buttons live outside the plot; the in-chart legend/annotation
  keep their inside-plot positions. `perf_chart` passes no `range_buttons`, so it's unaffected.
- **"Price forecasting" H2 removed** from the forecasting page (`page_forecasting()` — the group
  tab-strip + view switch already make the context obvious; the page title also lives in the browser tab
  + Home). Just deleted the `st.markdown("## Price forecasting")` line.
- **Grouped "location" dropdown now shows full descriptive product names** — new `app.py`
  `FORECAST_LOCATION_LABELS` (keyed by `dl.STEEL_PRODUCTS` key) + `_loc_label(group, name)` helper
  (full name if configured, else the short `_location_label` fallback). `loc_map` in
  `page_forecasting()` now keys on those. Names per owner: HRC = "HRC, Exy-Mumbai, India, IS2062, Gr
  E250 Br.,2.5-8mm / CTL"; HR Plate = "HR Plate, Exy-Mumbai, India, Gr E250 Br.,5-10mm (HSM)"; the 3
  Rebars = "Rebar, {Exy-Mumbai … BF Route | Exw-Mumbai … IF Route | Exw-Raipur … IF Route}"; Structure =
  "Structure-Angle, Exw-Raipur, India, IS 2062/2011 E-250 Gr A,150x150 Angle, IF Route". **These are the
  only editable knob** — change the strings in that dict. `theme.py` `.st-key-fc_loc_box` widened
  `250px → 660px` (~85 chars, `max-width:100%`) so even the longest name shows in full on one line;
  value font 12.5px + a global `li[role="option"]` rule lets popover options wrap/show in full. The dropdown key still
  maps back to the short `STEEL_PRODUCTS` key, so data lookups (`products[product]`, ff/acc) are
  unchanged; only the *displayed* label changed. **(update: 660px = ~85 chars, per owner.)**
- **Forecast-horizon tab + right rail restructure (grouped graphical view).** The right-side price
  rail changed: (1) the **"+12-week forecast" card was removed**; (2) a **1W/4W/8W/12W segmented tab**
  (`st.segmented_control` `key="fc_horizon"`, `format_func` `n→"{n}W"`, default 1) now sits **above the
  cards**; (3) the second card is now a **"{n}-week forecast"** whose value/direction tracks the tab —
  `app.py` `_forecast_at(n)` reads the n-th row of the 12-week `fwd` path **positionally** (row 0 = week
  1, clamped to len; n=1 falls back to the summary "Next-wk forecast"), direction = `dl.direction_flag(fc
  − last_actual)`. The **"Last actual spot" card is unchanged** by the tab. `price_cards(vertical, horizon)`
  now emits **2** cards (was 3) and adds the `bm-vcards-sm` class; the horizontal branch uses
  `st.columns(len(cards))`. (4) Cards **made smaller AND horizontal** via `theme.py` `.bm-vcards-sm`
  (padding 11×13, value 20px, icon 26px; `display:flex;flex-wrap:wrap` so the icon+label header sits on
  top and the **value (left) + date / direction-chip (right, `margin-left:auto`) share one row** instead
  of the sub stacking below; rail left-aligned, full-width). (5) The **Forecast rationale is now the 3rd
  card** in the rail (`_rationale_card_html()` — heading INSIDE the card via `.bm-kpi-top` icon+label,
  matching the other two; body `.bm-rationale-body` 12px), appended into the same `.bm-vcards` column via
  `price_cards(..., extra_card=…)`. The **"Placeholder rationale — analyst commentary…" footnote was
  removed.** `render_rationale()` (no args now) is the full-width version used by the OTHER views only
  (guarded by `rationale_shown`). Chart/rail split `st.columns([5,1]) → [5,1.25]`.
  **(6) The horizon tab now ALSO drives the GRAPH:** `render_graph_view(horizon)` passes `fwd.head(n)` to
  `forecast_chart`, so the forecast is drawn out to **n weeks forward only** (1W → 1-wk nub, 12W → full);
  the shaded-region annotation is now dynamic `f"{len(fwd)}-wk ahead"`. The horizon is read from
  `st.session_state["fc_horizon"]` BEFORE the chart renders (the tab widget lives in the right rail,
  rendered after the chart) — default 1. The historical forecast fit is always fully drawn; only the
  forward extent + x-range end change. Non-grouped + grouped Tabular views still show 2 cards (no +12w),
  horizon fixed at 1 (next-week), full forecast.
- **"Calculators" → "Scenario Simulation"** everywhere user-facing: nav label (`NAV` 2nd field —
  **internal page key stays `"Calculators"`** so routing / `PAGES` / `profile["pages"]` are untouched),
  Home module-card title, `page_calculators()` H2, and the three tool subheaders
  (`calc_import_price.py`, `calc_elasticity.py`, `calc_cost.py`). README module bullet updated too.
- **"Last updated" now shows week-of-month** — new `app.py` `_week_of_month_label(d)` →
  `"Week N, Mon YYYY"` (N = `(day-1)//7 + 1`, 1–5). Wired into the Home **"Last updated on"** KPI and
  the forecasting **"Last actual spot"** card date (both previously `%d %b %Y`). Sidebar "Data as of"
  left as the exact date (technical/data-source detail).
- **Adani logo de-boxed** — `.bm-adani-chip` in `theme.py` dropped the white background / padding /
  rounded corners / shadow (`background:#fff; border-radius:8px; padding:5px 11px; box-shadow…`) and is
  now just `display:inline-flex; align-items:center;`. The gradient "adani" wordmark now sits directly
  on the blue brand bar (no square). ⚠ If legibility of the cyan left edge on the blue bar is a
  concern, revisit — but per request the box is removed.
- **All "prototype" UI text removed** (going live): footer disclaimer trimmed to "AI-generated
  forecasts are indicative." (dropped "Prototype build — data shown is a static snapshot.");
  Methodology footnote "This Adani **prototype** surfaces…" → "This Adani **dashboard** surfaces…";
  `app.py` module docstring and `portal/README.md`/this handoff's header de-prototyped. Historical
  changelog entries left intact.
- All edited modules `py_compile` clean.
  → `app.py`, `theme.py`, `calculators/calc_import_price.py`, `calculators/calc_elasticity.py`,
  `calculators/calc_cost.py`, `README.md`.

### 2026-07-08 — Full alignment on Streamlit 1.59 (pin + env + dual-generation tab CSS)
- **Everything now targets 1.59.0, the version the Cloud deployment actually runs.** Root
  `requirements.txt` pin bumped `1.58.0` → **`1.59.0`** (comment rewritten; `portal/requirements.txt`
  mirror pinned to the same instead of `>=1.30`); the local conda **`neuralforecast` env upgraded to
  1.59.0** (was 1.58.0). Local and Cloud are on the same build again.
- **Plain `st.tabs` pill styling fixed for 1.59 (react-aria)** — closes the open follow-up from
  2026-07-07: calculators + non-grouped forecasting tabs rendered as default underline tabs on the
  deployment because the pill CSS only keyed on 1.58's `data-baseweb="tab-*"` attributes. Every tab
  rule in `theme.py` `inject_css()` now has a react-aria twin (selectors from the live-captured 1.59
  markup in the tabs gotcha): grey track = `[data-baseweb="tab-list"], [data-testid="stTabs"]
  div[role="tablist"]`; tab buttons / hover / orange-bold active = `div[data-testid="stTab"][role="tab"]`
  (+ `[aria-selected="true"]`) alongside the baseweb equivalents; the **white pill on 1.59 is the
  `.react-aria-SelectionIndicator`** (lives INSIDE the active tab) pinned to the tab's box —
  `position:absolute; inset:0; transform:none; width/height:auto` (all `!important`, defeating its
  inline underline geometry) + `border-radius:9px; background:#fff` + the pill shadow; a
  `div[data-testid="stTab"] > :not(.react-aria-SelectionIndicator)` rule keeps the label above it.
  **NB:** on 1.59 the pill *moves with the selection* (the indicator lives in the active tab) rather
  than gliding across the track like 1.58's `tab-highlight` — same look, no glide animation.
  **NOT yet verified live on 1.59** (edited blind per workflow; the sandbox-probe workflow in the
  tabs gotcha is the way to check — throwaway 1.59 venv may still exist at `C:\st_probe`).
- `app.py` `page_forecasting()` comment refreshed (the pill *switch* stays on `st.segmented_control`;
  tabs CSS covering 1.59 doesn't change that choice). Both files `py_compile` clean.
  → `requirements.txt`, `portal/requirements.txt`, `portal/theme.py`, `portal/app.py`, gotchas above.
- **Tab track no longer spans the full screen + app made more compact** (owner screenshot: the
  calculators' grey tab track stretched edge-to-edge on 1.59, plus dead space at the top). Fixes in
  `theme.py` `inject_css()`: **(a)** the tab-list track gained `width:fit-content` +
  `max-width:100%` + `align-self:flex-start` (all `!important`) — on 1.59 the tablist is a
  *stretched flex item*, so the old `display:inline-flex; width:auto` shrink-to-fit never applied.
  **(b)** top space: `.block-container` rule (now also matched via the `stMainBlockContainer` testid
  twin in case a newer build drops the emotion class) `padding-top 1rem → 0.4rem`, bottom
  `2rem → 1.2rem`; the header-collapse rule hardened (`height/min-height:0 !important; padding:0`,
  + `stAppHeader` testid twin). **(c)** compaction: global `stVerticalBlock` gap `1rem → 0.65rem`;
  markdown `h1–h3` padding trimmed to `.35rem` top/bottom via a **direct-child** selector
  (`[data-testid="stMarkdownContainer"] > h1…` — headings inside custom HTML cards like
  `.bm-meth-hero` are untouched); topbar bottom margin `14px → 10px`. **Dependent retune:** the
  `.st-key-fc_loc_box` pull-up margin `−58px → −52px` (it eats the block gap + its own height; the
  gap shrank ~6px — see the updated grouped-layout entry). `py_compile` clean; **not verified live**
  (edited blind per workflow). → `portal/theme.py`.
- **Second compaction pass (owner: "very little space from the sides, remove ALL the space from
  the top")** — `.block-container`/`stMainBlockContainer`: side padding `2.2rem → 0.8rem`, top
  padding/margin **0** (bottom `1rem`); added flush-top guards `[data-testid="stAppViewContainer"],
  [data-testid="stMain"] {padding/margin-top:0}` and `[data-testid="stDecoration"]
  {display:none}` (streamlit's coloured top strip) so nothing in the app chrome holds the top
  open. The blue topbar now sits at the very top edge of the viewport. NB the owner's screenshot
  showing the old spacing was the DEPLOYED app — these fixes (and the earlier compaction) only
  reach it once committed + pushed to `main`. → `portal/theme.py`.
- **Third pass (top gap persisted on the deployment): the REAL top-gap culprits + sides eased to
  1.2rem** — two things still held the top open: **(1) the `stx.CookieManager` component**
  (`app.py:61`, key `portal_cm`) renders an invisible **iframe above the topbar on every run** — its
  element container cost its own height + one block gap. Now `display:none` via
  `.st-key-portal_cm` (+ `div[class*=…]` twin). Hidden iframes still load & run JS, so **cookie
  reads/writes keep working** (verify login-persists-across-refresh + logout when checking live —
  if cookies break, this rule is the first suspect; switch to `height:0;overflow:hidden` instead).
  **(2) the app header** painted its Share/toolbar icons over the page even at `height:0` → now
  fully `display:none` (element-agnostic `[data-testid="stHeader"], [data-testid="stAppHeader"]`).
  Safe for the `:has(stStatusWidget)` loading overlay — `:has()` matches display:none subtrees.
  Side padding eased `0.8rem → 1.2rem` per owner ("add bit margin on the sides").
  → `portal/theme.py`.
- **Grouped forecasting: price cards moved from below the chart to its RIGHT + y-axis tick gap** —
  in `page_forecasting()` the grouped **Graphical** view is now `st.columns([4, 1], gap="small",
  vertical_alignment="center")`: chart left, the three price KPI cards **stacked vertically** on the
  right (`price_cards(vertical=True)` — new param; vertical renders into `st` directly instead of
  3 columns). The **Tabular** view keeps the cards below the table (they now render inside that
  branch; the old shared below-the-tabs render was removed). Non-grouped layout untouched (cards
  above the tabs). Chart width adapts via the existing ResizeObserver → `Plotly.Plots.resize`.
  Also `_style_fig` y-axis gained `ticklabelstandoff=8` (the x-axis already had 6) — a sliver of
  gap between the Rs. tick labels and the plot edge, per owner. `py_compile` clean.
  → `portal/app.py` (`page_forecasting`, `_style_fig`).
- **Right-side card stack refined (owner: narrower + spread to the chart's full height)** — the
  chart/cards split went `[4,1] → [5,1]`, and the cards now live in `st.container(key="fc_cards_box")`
  spread over the chart height. **Two failed cuts before the working one** (owner screenshots:
  cards kept bunching at the top): (1) height/space-between on `.st-key-fc_cards_box` — the
  st-key class lands on the container's border wrapper, not the flex block; (2) re-targeting the
  inner `[data-testid="stVerticalBlock"]` + a `> div {height:100%}` bridge — still bunched on the
  deployed build. **Final approach (works, keep this one):** dropped the keyed container entirely;
  `price_cards(vertical=True)` now emits the three cards as **ONE `.bm-vcards` HTML block**
  (`display:flex; flex-direction:column; height:632px` = compact chart 620 + `st.iframe` pad 12,
  retune if `forecast_chart`'s compact `h` changes) —
  all in our own markup, zero dependence on Streamlit's container DOM. Spread style iterated
  twice more on owner screenshots (space-between voids, then full-height equal panels — both
  "too wide and awkward"). **Final look (owner-approved direction): natural-height cards,
  `gap:14px`, top-aligned — leftover space below the third card is fine — with a hard
  `max-width:280px` cap so the rail can't balloon on wide screens, `margin-left:auto`
  right-aligning it under the location dropdown.** No fixed 632px height anymore.
  → `portal/app.py`, `portal/theme.py`.
### 2026-07-07 — Per-role white-label dashboards + admin-managed access (in progress)
- **App now fills the whole screen width (full-bleed at any resolution)** — the custom
  `.block-container` cap `max-width:1180px` in `theme.py` `inject_css()` became `max-width:100%`
  with `2.2rem` side padding (`layout="wide"` was already set, the CSS cap was the limiter). Charts
  adapt automatically (`st.iframe` width `stretch` + the `_HL_TEMPLATE` ResizeObserver →
  `Plotly.Plots.resize`; native charts/tables use `width="stretch"`). The **login** and
  **password-reset** cards would stretch absurdly on wide monitors, so their bordered containers
  gained keys (`login_card` / `reset_card`) and a `max-width:460px; margin:0 auto` rule in
  `theme.py`. To restore a capped layout, put a px `max-width` back on `.block-container`. →
  `theme.py`, `app.py`.
> Feature plan: **Appendix A** below. Turns the app into a per-role white-label
> dashboard on a single deployment: each role gets its own branding (dev-configured, static), and the
> Admin controls which commodities + which analyst calls each role sees (runtime). Landing task-by-task.
- **Deployment runs Streamlit 1.59 (pin not honored) — pill switch + segmented accent fixed for
  both versions; `components.html` → `st.iframe`** — the owner's deployed app emits 1.59's
  "`st.components.v1.html` will be removed" warning, i.e. it runs **streamlit 1.59.0**, NOT the
  pinned 1.58.0 (the local conda `neuralforecast` env was bumped to **1.59.0** on 2026-07-08 to match
  the deployment — check the Cloud requirements install log / reboot the app if
  the pin should stick). 1.59 replaced baseweb widgets with **react-aria** markup, which broke the
  pill switch there ("frozen overlay": the grey track rendered but the pill never moved and the
  active label never coloured, because 1.59's segmented buttons have **no
  `stBaseButton-segmented_controlActive` testid** — the active option is marked
  `aria-checked="true"` / `data-selected="true"` on a `data-variant="segmented_control"` button
  under the same `role="radiogroup"`). Fixes, all verified live in sandbox probes on BOTH 1.58 and
  1.59: **(a)** the `.st-key-fc_view_box` pill-parking `:has()` rule and the active-label rules now
  match **either generation** (testid OR `aria-checked="true"`); on 1.59 the pill demonstrably
  glides 4↔135 with intermediate transform samples (react-aria flips `aria-checked` client-side
  pre-rerun, so the transition fires). **(b)** the **global segmented-control accent rule** (orange
  active option — Product/group strips) gained the 1.59 selector
  `button[data-variant="segmented_control"][aria-checked="true"]`. **(c)** `_render_with_highlighter`
  no longer calls deprecated `components.html` (log-spams on 1.59; removal announced mid-2026):
  charts now render via **`st.iframe(path)`** — it inlines the file as the iframe `srcdoc`
  (same-origin, JS verified to execute on both versions), so the doc is written to a per-session
  temp file (`%TEMP%/bm_charts/<session-token>_<dom_id>.html`; the `uuid` session token in
  `st.session_state` stops concurrent viewers clobbering each other). `streamlit.components.v1`
  import removed from `app.py`. **(d)** all 20 `use_container_width=True` kwargs (buttons /
  plotly_chart / dataframe / form_submit_button across `app.py`, `calc_elasticity.py`,
  `calc_import_price.py`) replaced with **`width="stretch"`** — 1.59 deprecation-warns on every
  call (removal announced end-2025); the `width` kwarg verified present on all four widgets in
  local 1.58, so both versions are happy. **NB:** plain `st.tabs` (calculators + non-grouped
  forecasting) were still underline-styled on 1.59 at the time — **fixed 2026-07-08** (dual-generation
  tab selectors in `theme.py`; see that changelog entry + the tabs gotcha). → `app.py`, `theme.py`,
  `calculators/calc_elasticity.py`, `calculators/calc_import_price.py`.
- **adani_dev — grouped layout refinements: dropdown → RIGHT, week/zoom buttons → just ABOVE the
  plot, Graphical/Tabular → sliding pill switch** — three tweaks to the grouped forecasting page
  (updates the entry below): **(1)** the location dropdown moved from left-above-the-tabs to the
  **right side of the view-switch row** — `.st-key-fc_loc_box` gains `margin-left:auto` +
  a negative `margin-bottom` + `position:relative;z-index:5`, pulling it down beside the tabs block
  that renders after it (was −58px; retuned to **−52px** on 2026-07-08 when the global block gap went
  compact — tune it if the vertical alignment drifts; z-index keeps it clickable).
  **(2)** the week/zoom buttons (1W…ALL) moved from inside the plot to **just above it**: in
  `forecast_chart(compact=True)` the rangeselector is now `y=1.01, yanchor="bottom"` with
  `top_margin=46` (was y=0.98 "top" inside + margin 18); the in-plot legend rises back to `y=0.99`
  (it no longer needs to duck under the buttons). **(3)** the Graphical/Tabular switch (grouped
  branch only) is a **sliding segmented pill switch**: a fixed **270×42px grey capsule track**
  (`min/max-width` pinned — it's a shrinking flex item otherwise) and a **label-width white pill
  (131×34px) that glides behind the active option**, active label orange/700, inactive grey (the
  classic tab-pill look). It is built on **`st.segmented_control` (key `fc_view`), NOT `st.tabs`** —
  a first cut styled the tabs via `data-baseweb="tab-*"` selectors and verified locally, but the
  **deployed app renders tabs without those attributes** (see the new tabs gotcha), so it silently
  fell back to underline tabs there. The switch instead keys on Streamlit-owned markup
  (`div[role="radiogroup"]`, `stBaseButton-segmented_control*` testids) that already styles reliably
  in this app. The pill is a `::before` pseudo-element; a `:has(button:last-of-type[…Active])` rule
  flips its `translateX` between the two halves (x=4 / x=135 = 4+(270−8)/2; pill w=131=(270−8)/2 —
  recompute both if the track width changes), the transform transition makes it glide (no-`:has()`
  fallback: pill stays left; active label still orange/bold). (An interim iOS-knob variant — blue
  gradient + round white knob — was built and verified the same day, then restyled to this pill per
  owner preference; geometry notes for it are in git history.) In `page_forecasting()` the two view
  bodies were refactored into nested `render_graph_view()` / `render_table_view()`; grouped renders
  them behind the switch (`view or "Graphical view"` — deselecting the active option falls back to
  the graph), non-grouped keeps the plain `st.tabs`. **Verified live in a sandbox probe** (Streamlit
  1.58): 270×42 grey track, white 131×34 pill parks 4↔135 with a smooth glide, active label
  orange/700, inactive grey, and the plain product/group segmented control keeps its default
  styling. → `app.py` (`page_forecasting`, `forecast_chart`), `theme.py` (`.st-key-fc_loc_box`,
  new `.st-key-fc_view_box` block).
- **adani_dev — grouped forecasting layout (group tabs → graph on top → price cards; styled location
  dropdown; in-chart legend; year labels)** — the `adani_dev` role sees a restructured **Price
  forecasting** page. Layout order: a top **commodity-group** segmented control (**HRC / HR Plate /
  Rebar / Structure**, derived from the role's allowed products via `_product_group` /
  `_grouped_products`) → a **left-aligned location dropdown** → the **Graphical/Tabular tabs** (so the
  **graph sits at the top**) → the **3 price KPI cards** (moved *below* the tab block) → rationale. Within a
  group a **location / full-name dropdown** (`_location_label` strips the group prefix — Rebar →
  *BF Mumbai / IF Mumbai / IF Raipur*; single-member groups show their one name), sorted
  **alphabetically**, defaulting to the first. The dropdown is **left-aligned and sits ABOVE the
  Graphical/Tabular tabs** (`st.container(key="fc_loc_box")`, styled in `theme.py` with a **coloured
  border + soft tint**, accent on hover) so it can be changed in **both** views without switching back
  to the graph. **No section title** on the Graphical tab; the **week/zoom buttons live INSIDE the
  plot** (top-left) and the Plotly **legend sits inside just below them**; the x-axis date ticks gain
  the **short year** (`%d %b %y`). The grouped chart runs via `forecast_chart(compact=True)` — a
  **taller plot (h=620)** with the zoom buttons moved inside (`rangeselector` y≈0.98 top-left) so the
  **top margin drops to 18** (buttons no longer float above) and the plot is bigger; the colour-legend
  footnote is dropped for this layout (the in-chart legend covers it). Selection persists per group via
  `st.session_state["fc_loc_<slug>"]` (resolved at the top, so graph, table and cards all follow it).
  All gated by `app.py` `GROUPED_FORECASTING_ROLES` (case-insensitive; currently just `adani_dev`) via
  `_grouped_forecasting(role)`; **other roles keep the existing flat layout** (cards above the tabs,
  section title + footnote present, full-height chart). `forecast_chart()` gained `legend_inside` /
  `year_labels` / `compact` kwargs (default off — no change for non-grouped roles); the price-card block
  was refactored into a nested `price_cards()` so it can render above or below the tabs. **Promotion to
  Adani:** add `"adani"` to `GROUPED_FORECASTING_ROLES`. → `app.py`, `theme.py`.
- **theme.py — per-role branding profiles + CSS-variable theming (task 1/5)** — the 4 themeable colors
  (`PRIMARY`/`PRIMARY_DARK`/`PRIMARY_SOFT`/`ACCENT`) in `inject_css()` are now driven by CSS custom
  properties (`--bm-primary` / `--bm-primary-dark` / `--bm-primary-soft` / `--bm-accent`) seeded with
  the BigMint defaults on `:root`. New **`ROLE_PROFILES`** / **`DEFAULT_PROFILE`** dicts (keyed by
  `auth.ROLES` values) hold each role's co-brand logo/label, topbar title, colors and visible `pages`;
  **`profile_for(role)`** merges over the default; **`apply_role_theme(profile)`** emits a tiny
  `<style>:root{…}</style>` override so the topbar + all custom surfaces re-brand per session (call it
  from `app.py` after login — wired in task 4). **`render_topbar(user)`** now builds the bar from the
  role profile (BigMint logo · optional co-brand chip · title); `cobrand_logo=None` hides the chip +
  one pipe (internal Analyst/Admin = BigMint-only). New `_cobrand_logo_html(profile)` generalises the
  old `_adani_logo_html` (kept, unused). Added `import html`. **Limitation:** `config.toml`
  `primaryColor` is a build-time global, so native Streamlit primary buttons/tabs keep the global
  orange for all roles; only the brand topbar + custom-CSS surfaces follow the role. → `theme.py`.
- **db.py — `role_commodities` table + accessors (task 2/5)** — new table `role_commodities(role,
  commodity, PK(role,commodity))` added to `_DDL`. **NB:** the app never called `init_db()` before
  (it relied on `seed_users.py`), so task 4 adds a cached `_ensure_db_schema()` in `app.py` that runs
  `db.init_db()` once per process — this creates `role_commodities` on already-seeded deployments with
  no manual migration. `get_role_commodities(role)` returns the allowed list (**empty = unconfigured ⇒ app treats
  as all**); `set_role_commodities(role, list)` replaces a role's set atomically (DELETE then INSERT,
  bound params). Admins bypass this in the app layer (always all). → `db.py`.
- **data_loader.py — `audiences` on sample calls (task 3/5)** — each `SAMPLE_ANALYST_CALLS` entry gains
  `"audiences": []` (empty/missing ⇒ **unassigned: admins only** — see the deny-by-default update
  below). `load_analyst_calls` /
  `save_analyst_calls` are generic dict (de)serializers, so real calls in `calls.json` carry the field
  through unchanged once the Admin sets it (task 4). → `data_loader.py`.
- **app.py — per-role filtering, page-gating, apply theme, admin access panel (task 4/5)** — new
  helpers `allowed_products(role)` (role's `STEEL_PRODUCTS` subset; Admin + unconfigured roles = all)
  and `_call_visible(call, role)` (audience filter). After login, `theme.apply_role_theme(profile_for(
  user.role))` re-brands the session. **Product filtering** applied in `page_forecasting` /
  `page_performance` (segmented control built from `allowed_products`, empty-state message) and
  `page_home` (product count/KPI/MAPA loop + welcome text). **`page_analyst`** filters calls by audience
  (admins see all). **Page-gating:** `top_nav` shows only the role's profile `pages` (+ Admin item for
  admins); the dispatch guard resets a hidden `st.session_state.page` to Home; Home module cards +
  Methodology banner are filtered to visible pages. **Admin call form** gained an *Audience* multiselect
  (`audiences` saved on the record). New **`_admin_access_panel()`** in `page_admin` (expander →
  select role → multiselect commodities → save to `db.set_role_commodities`; rejects an empty set).
  Also added a cached **`_ensure_db_schema()`** (runs `db.init_db()` once per process) so the new
  table exists at runtime without a manual migration. → `app.py`.
- **Verified (task 5/5)** — `py_compile` on all four modules; a smoke test against **live Neon**
  confirmed `init_db()` creates `role_commodities` and `get/set_role_commodities` round-trip (test rows
  restored afterwards, DB left clean); `profile_for()` returns distinct branding per role (Adani =
  co-brand + steel title; Analyst/Admin = no co-brand + "AI LABS" title); `_call_visible` filters by
  audience correctly. The login screen renders the new profile-driven topbar with no console/render
  errors. **Not yet screenshotted in-app per role** — that needs a login (all seeded accounts are
  `must_reset` / use owner-set passwords); left for the owner or a throwaway test account.
- **Analyst-call audience is now DENY-BY-DEFAULT (post-review change)** — flipped `_call_visible`: an
  untagged call (empty `audiences`) is **no longer visible to everyone** — it's *unassigned* and shows
  to **admins only**; a non-admin role sees a call only when its role is explicitly in the call's
  audience. (Previously empty = all, which meant `analyst`/`adani` saw every untagged call.) The admin
  call editor's Audience help text + the `SAMPLE_ANALYST_CALLS`/`data_loader` comments were updated.
  **⚠ Migration:** any existing call in `calls.json` with no `audiences` becomes admin-only until an
  admin opens it and picks its audience — go tag existing calls after deploying this. → `app.py`,
  `data_loader.py`.
- **Admin can create new roles from the Add-user form (post-review change)** — the add-user Role
  dropdown gained a "…or create a new role" free-text field; a non-blank value wins (case-insensitively
  reusing an existing role's casing to avoid `Adani`/`adani` dupes — `_resolve_new_role`). All role
  pickers (add-user, Apply-role, Commodity access, call Audience) now build from **`known_roles()`** =
  `auth.ROLES` ∪ roles already on a user, so a runtime-created role appears everywhere without editing
  `auth.ROLES`. A new role starts with `DEFAULT_PROFILE` branding + all commodities + no calls; a dev
  adds a `theme.ROLE_PROFILES` entry for custom branding. → `app.py`.
- **Removed the `?authdebug=1` diagnostic panel** — cookie persistence is confirmed solid on Cloud, so the temporary opt-in debug block (request-vs-component cookie readout) was deleted from `app.py`. The cookie read path (`st.context.cookies` → `cookie_manager` fallback + `_cookie_probed` loading splash) is unchanged. Clears auth follow-up (1). → `app.py`.
- **Auth replaced: production self-managed user store in Neon Postgres (supersedes the 2026-07-03 "Auth is now IN-FILE ONLY" entry)** — the SHA-256 `USERS` dict in `auth.py` is gone. New **`db.py`** (SQLAlchemy over a Neon Postgres **pooled** connection) owns three tables — `users` (argon2id `password_hash`, `role`, `is_active`, `must_reset`, `failed_attempts`, `locked_until`), `sessions` (SHA-256 of an opaque session id + `expires_at`; server-side revocable), `audit_log` — created by `db.init_db()`. **`auth.py`** rewritten UI-agnostic: `authenticate() → (user, status)` (`ok`/`invalid`/`locked`/`disabled`) with argon2id verify, failure counting + **lockout (5 tries / 15 min)** and a dummy-hash timing guard; `create_session()` / `resolve_session()` / `logout()` mint/validate/revoke a **signed JWT** carried in the `portal_session` cookie (12 h TTL); user-management helpers (`create_user`/`upsert_user`/`set_password`/`set_active`/`set_role`/`delete_user`/`list_users`). New **`seed_users.py`** seeds adani/admin/analyst with random temp passwords + `must_reset=True` → git-ignored `.streamlit/seed_credentials.txt`. Secrets now require **`database_url`** + **`session_signing_key`** (top-level; `db._config()` reads st.secrets → env → secrets.toml). Deps added to both `requirements.txt` files: `argon2-cffi`, `SQLAlchemy`, `psycopg[binary]`, `PyJWT`, `extra-streamlit-components`. `.gitignore` now ignores `.streamlit/seed_credentials.txt` + `*.local`. → `db.py`, `auth.py`, `seed_users.py`, `requirements.txt`, `portal/requirements.txt`, `.gitignore`.
- **Login flow rewired for cookie-backed sessions + forced first-login reset** — `app.py`: `login_screen()` calls the new `authenticate()`, surfaces locked/disabled/invalid messages, and on success `_start_session()` (mint session + **queue** the cookie write). `force_password_change()` gates any `must_reset` user before the app. On refresh, session is restored from the `portal_session` cookie (`_read_cookie_token` → `resolve_session`). **Cookie writes are deferred** to the next run (`_cookie_write`/`_cookie_clear`) because `st.rerun()` discards same-run component output — this fixed "refresh logs me out" and a logout `KeyError`. Cookie read prefers `st.context.cookies`, falls back to the component; a one-shot loading splash (`_cookie_probed` → `theme.loading_screen()`) hides the login flash while the cookie is fetched. Logout revokes the server session, clears the cookie, wipes session_state. Added `?authdebug=1` diagnostics. → `app.py`.
- **Admin tab → User management panel** — `_admin_users_panel()` (admins only): users table + **add user** (generates a one-time password, `must_reset=True`) + per-user **change role / enable-disable / reset password / delete**, guarded against disabling/deleting **yourself** or the **last active admin**. → `app.py` `page_admin()`.
- **Full-screen splash + translucent in-app loading overlay** — `theme.loading_screen()` paints an opaque brand-spinner splash (all Streamlit chrome hidden) for the single probe render after a refresh (removes the login flash). Separately, `inject_css()` adds a **translucent** overlay (scrim + blur + spinner) via `[data-testid="stApp"]::before/::after` gated by `:has([data-testid="stStatusWidget"])`, so any page switch / slow rerun shows a loading state automatically — pure CSS, no JS, no extra DOM. → `theme.py`, `app.py`.
- **Login page chrome — removed then restored** — briefly stripped the topbar/footer for a "generic" login, then reverted per request: `login_screen()` + `force_password_change()` keep the normal topbar + footer and the "Price Forecasting: Steel" caption. → `app.py`.

### 2026-07-03
- **Admin tab — editable Analyst-calls content (text + PDF/PPT uploads)** — new **role-gated** page `page_admin()` (nav item shown only when `user["role"] == "Admin"`; `top_nav()` now builds its columns dynamically). Admin can add / edit / delete calls (month, title, summary, 5 sections) and upload PDF/PPT decks. Content persists to the **private data repo** via the GitHub Contents API: `analyst_calls/calls.json` (text) + `analyst_calls/files/<id>/…` (decks), written by `data_loader.save_analyst_calls` / `upload_call_file` / `gh_delete_file` using a new **`github_write_token`** secret (falls back to `github_token` if it has write access; save disabled + warned if neither can write). `page_analyst()` was rewritten to render from `load_analyst_calls()` with **live Download PDF/PPT** buttons (deck bytes fetched via `fetch_call_file`, cached) — no video. With no secrets it shows `SAMPLE_ANALYST_CALLS` so the public app still runs. All admin-entered text is `html.escape`d at render. Added `import requests` usage; the read path stays read-only. → `app.py` (`page_admin`, `page_analyst`, `_render_call_card`, `_deck_button`, `top_nav`, `PAGES`), `data_loader.py` (analyst-calls section), `.streamlit/secrets.toml.example`.
- **Git history scrubbed** — removed `accuracy_tables/*.xlsx` + `portal/calculators/HRC - Copy.csv` from all 8 commits with `git filter-repo` and force-pushed `origin/main` (verified: no data files anywhere in local or remote history). Pre-scrub backup bundle saved outside the repo. Note: GitHub may still cache old commit SHAs — purge via GitHub Support if needed; treat previously-public data as exposed.
- **Data moved to a PRIVATE GitHub repo (public code / private data) — supersedes the "IN-REPO ONLY" bullet below from earlier today** — `data_loader.py` now fetches the real files at runtime from a private repo when `st.secrets['data']` is set: `_fetch_private_data_dir()` hits the **GitHub Contents API** with a read-only fine-grained PAT (`Accept: application/vnd.github.raw`), `@st.cache_resource` so it downloads once per deploy into a temp dir; with no secrets it falls back to the in-repo sample. New helpers `_data_cfg()` / `_data_root()` / `ff_path()` / `acc_path()`; `acc_dir()` + `calculators_csv()` derive from the resolved root; the old `FF_PATH` / `ACC_PATHS` / `ACC_DIR` module constants + `USING_PRIVATE_DATA` were removed (internal only — `load_*` signatures unchanged). Added **`requests`** to `requirements.txt`; rewrote `.streamlit/secrets.toml.example` with the active `[data]` block. **Setup:** private `dashboard-data` repo laid out `accuracy_tables/forecast_forward.xlsx` + `accuracy_tables/Accuracy_Table_6.xlsx` + `calculators/HRC - Copy.csv`, a fine-grained PAT (read-only Contents, that repo only), and a `[data]` block in Streamlit Cloud secrets. **Still TODO:** once the private repo is populated, `git rm` the sample `accuracy_tables/*.xlsx` here, `.gitignore` them, and scrub git history (keep a dummy sample so the public code still runs). Verified the no-secrets fallback loads the sample (summary 6 / HRC accuracy 82 / forward 12). → `data_loader.py`, `requirements.txt`, `.streamlit/secrets.toml.example`.
- **Forecasting tab now shows the FULL spot history (was a rolling 26-week window)** — removed the `HIST_WEEKS = 26` constant and the `.tail(HIST_WEEKS)` calls in `forecast_chart()` and the Tabular-view history table, so both now render every available actual (currently **82 weeks, Dec 2024 → latest**) instead of trimming to the most recent ~26 weeks — which cut the chart/table off around **Dec 2025**. The chart's default x-range is derived from the first history date, so it auto-spans the full range; the rangeslider + zoom buttons (1W/4W/8W/12W/26W/YTD/ALL) still let the user narrow it, and chart/table stay in sync (both untrimmed). NB: 26W and ALL are now **distinct again** (with only 26 wk loaded they used to coincide). → `app.py` `forecast_chart()` + `page_forecasting()` tabular block.
- **[SUPERSEDED later 2026-07-03 — private data re-introduced via a GitHub repo; see the top bullet for this date]** ~~Data is now IN-REPO ONLY — the private-data mechanism was removed~~ — `data_loader.py` reads data **directly from this repo** (`accuracy_tables/` + `portal/calculators/`) via `acc_dir()` / `calculators_csv()`. There is no longer a `_private_data_root()` / `_fetch_private_data_dir()`, no `$PORTAL_DATA_DIR`, no sibling `../dashboard-data`, and no `st.secrets['data']` GitHub download (`USING_PRIVATE_DATA = False`). Readers stay mtime-keyed + auto-refresh. **This supersedes the 2026-07-02 "Private data support" entry and the data half of the "deploy prep" entry** (both the data- and auth-via-secrets layers are now gone — see the auth bullet below). `.streamlit/secrets.toml.example` + `.gitignore` still mention the old `[data]` / `dashboard-data` approach as leftover documentation only. → `data_loader.py`, `calculators/*`.
- **Auth is now IN-FILE ONLY — the `st.secrets['auth']` override was dropped** — removed `auth._active_users()`; `authenticate()` reads directly from the built-in `USERS` dict (SHA-256 hashes) in `auth.py`. The three demo logins are unchanged (adani/Adani@2026, admin/Admin@2026, analyst/Analyst@2026 — hashes verified). To change a login, edit `USERS`. Mirrors the in-repo data revert above, so the app now reads **no `st.secrets` at all** and `.streamlit/secrets.toml*` is vestigial. → `auth.py`.
- **`Accuracy_Table_16.xlsx` removed from the repo** — the app already ran off Table_6 only (window toggle gone since 2026-06-25); the 16-week file is now physically deleted and `ACC_PATHS` has just `"6-week"`. → `accuracy_tables/`, `data_loader.py`.
- **⚠ Note (now being resolved):** the sample `accuracy_tables/` data is still committed here. The fix is in progress — real data has moved to the private GitHub repo (top bullet); the remaining step is to `git rm` + `.gitignore` the committed samples and scrub history, keeping a dummy sample.

### 2026-07-02
- **Topbar heading reformatted → "BIGMINT | ADANI | STEEL GCP - AI LABS : Steel Prices Forecasting Model"** — the topbar now shows BigMint logo · `|` · Adani chip · `|` · portal title. Added a **second `|` pipe** (another `.bm-cobrand-x` span) between the Adani chip and the portal title, and **removed the `border-left`+`padding-left` divider** on `.bm-portal-title` (it doubled up with the new pipe). Portal-title text changed from "AI Labs — Price Forecasting: Steel" → **"STEEL GCP - AI LABS : Steel Prices Forecasting Model"**. → `theme.py` `render_topbar()` + `.bm-portal-title` CSS. **NB:** the *plain-text* title "Price Forecasting: Steel" is still used in the browser tab `page_title`, the login caption, and the Home H2 (`app.py` ~lines 20/36/347) — only the co-branded **topbar** heading was reformatted here.
- **Adani logo regenerated from the untrimmed original** — `assets/adani_logo.png` had been deleted; recreated it by auto-trimming the whitespace off `assets/adani_logo_orig.png` (1402×854 → **1020×364**, ~12px pad). `_adani_logo_html()` now walks a **candidate list** `ADANI_LOGO_CANDIDATES = [adani_logo.png, adani_logo_orig.png]` before the gradient-wordmark fallback, so the co-brand still renders (using the original) if the trimmed file is ever removed again. → `theme.py`. **Verified live** (login screen topbar): 2 pipes present, full title fits with no overflow clip (title right 687 < bar right 714), adani `<img>` loaded (natural 1020×364).
- **[SUPERSEDED 2026-07-03 — data is now in-repo only; see top of changelog]** **Private data support — data root is now configurable (public code, private real data)** — the repo is **public on GitHub**, so real/proprietary data must never be committed here. `data_loader.py` now resolves a **data root** at import (first hit wins): (1) `$PORTAL_DATA_DIR`, (2) a sibling `../dashboard-data` folder, (3) `None` → the in-repo **sample** (kept tracked so the public repo still runs). New helpers `acc_dir()` + `calculators_csv()` build every data path from that root; `ACC_DIR`/`FF_PATH`/`ACC_PATHS` derive from `acc_dir()`. A private root must mirror the sample layout: `<root>/accuracy_tables/*.xlsx` and `<root>/calculators/HRC - Copy.csv`. The two calculators (`calc_elasticity.py`, `calc_import_price.py`) now set `CSV_PATH = data_loader.calculators_csv()` (try/except fallback to the in-repo CSV). Added a repo **`.gitignore`** (ignores `dashboard-data/`, `.streamlit/secrets.toml`, `*.env`, caches; **does NOT** ignore the sample so the public demo keeps working). → `data_loader.py`, `calculators/calc_elasticity.py`, `calculators/calc_import_price.py`, `.gitignore`. **Setup for real data:** create a *private* `dashboard-data` repo with that layout, clone it as a sibling of `dashboard/` (or set `PORTAL_DATA_DIR`), and the app picks it up automatically — no code change. (Sample data currently in the public repo/history is unchanged; scrubbing it from history would be a separate `git filter-repo` + force-push.)
- **[PARTIALLY SUPERSEDED 2026-07-03 — the private-data download AND the auth-via-secrets override were both removed; only the `requirements.txt` / pinning part still applies]** **Streamlit Community Cloud deploy prep (public code, private data + real auth via secrets)** — added **`requirements.txt`** (pip deps for Cloud, since it doesn't use the conda env; **`streamlit==1.58.0` pinned** to preserve the baseweb tab-pill CSS). Cloud has **no persistent disk**, so `data_loader._private_data_root()` gained a tier between the sibling folder and the sample: if `st.secrets['data']` is set, `_fetch_private_data_dir()` (`@st.cache_resource`) **downloads** the four data files from a **private GitHub repo** (`github_owner`/`github_repo`/`github_ref` + read-only fine-grained PAT `github_token`) into a temp dir; the function body is the single swap-point for S3/GCS/Drive. Auth now reads users from `st.secrets['auth']['users']` via `auth._active_users()`, falling back to the built-in demo users for local dev — real passwords stay out of the public repo (also removed the plaintext `# Adani@2026`-style hash comments). Added **`.streamlit/secrets.toml.example`** (the real `secrets.toml` is git-ignored). **Local dev is unchanged** (no secrets → sample data + demo logins). See the **Deploy** section. → `requirements.txt`, `data_loader.py`, `auth.py`, `.streamlit/secrets.toml.example`.

### 2026-06-30
- **Forecast chart — bottom time slider + Zoom buttons (1W/4W/8W/12W/26W/YTD/ALL) + weekly grid** — added a Plotly **rangeslider** (bottom navigator strip) and a **rangeselector** button row to `forecast_chart()` (the Graphical-view spot-vs-forecast chart only; the shared `_style_fig` is untouched so other charts are unaffected). **Zoom buttons control how much HISTORY (the actual+forecast section) is shown; the 12-week forward forecast stays pinned in view — only dragging the slider can hide it.** Mechanism: Plotly's `backward` stepmode anchors the window's right edge to the current range max, so each "N W" button spans **N weeks of history + the full forecast** via `count = N*7 + forecast_span` days (clamped to the loaded history); YTD = `step="year"/stepmode="todate"`; ALL = a count-based full-span button (`step="day"`, NOT `step="all"` — see the padding gotcha below).
  - **GOTCHA / bug fixed (the "all show ~2 weeks less" bug):** Plotly autorange **pads** the axis max beyond the last data point (~16 days / ~2.3 weeks here). Since `backward` anchors to the *current range max*, that padding shifted every window right and dropped ~2 weeks of history (e.g. 1W showed −2.3 weeks of history, 4W showed 0.7). **Fix:** set an **explicit x-range with `autorange=False`** (`range=[_dt(start_all), _dt(last_fc)]`) so the axis max is EXACTLY the last forecast date, and make **ALL count-based** (`step="all"` re-enables autorange → re-pads → breaks the next backward click). After the fix, **verified live**: every button's right edge sits exactly on the last forecast date (0-day offset) and 1W/4W/8W/12W show 1/4/8/12 weeks of history. **Do not** switch ALL back to `step="all"` or remove the explicit range, or the padding bug returns.
  - **Weekly grid** ("better weekly visualisation"): `_style_fig` hides vertical gridlines; this chart re-enables them with **faint weekly minor gridlines** (`minor=dict(dtick=7*86400000, tick0=_dt(last_actual), showgrid=True, gridcolor="#f3f6fa")`) + light major gridlines (`gridcolor="#e8eef5"`) and date tick labels (`tickformat="%d %b"`). Verified: ALL view ≈ 35 weekly minor lines + monthly major ticks; 8W view ≈ 18 weekly lines — the weekly grid adapts to the zoom. (Needs plotly.py ≥ 5.8 for `minor`; env has 6.8.0.)
  - Active button uses `activecolor=ACCENT` (orange). Layout adjusted **only for this chart**: height 500→560, top margin →82 to clear the buttons, legend moved to the **top-right** (zoom buttons sit top-left). NB: with `HIST_WEEKS=26` weeks of history loaded, **26W == ALL** (harmless). Layout/range scalars use `_dt()` (python datetime) per the JSON-serialization gotcha. Works through the custom `_render_with_highlighter` CDN layer. (Earlier same-day iterations: first used 1M/3M/6M `step="month"` backward; then switched to week buttons but still hit the autorange-padding bug fixed above.) → `app.py` `forecast_chart()`.
  - **Slider shows a clean solid line only (dots hidden, dashes removed)** — the forecast trace is `lines+markers` + `dash="dash"`, so its per-point dots and dashes also appeared in the rangeslider mini-preview. Plotly has no per-slider trace styling, so two scoped CSS rules in the `_HL_TEMPLATE` `<style>` clean up the slider: `.rangeslider-container path.point{display:none}` hides the slider's marker dots, and `.rangeslider-container path.js-line{stroke-dasharray:none}` draws the forecast line **solid** in the slider (the spot line is already solid). Both keep the **area fill** in the slider and leave the **main chart unchanged** (markers intact + forecast line still dashed). The rules only match charts that have a rangeslider (just the forecast chart), so they're safe in the shared template. **Verified live (dots rule):** slider 0 visible dots / 2 lines / 1 fill; main chart 38/38 markers intact. → `app.py` `_HL_TEMPLATE`.
- **Tab slide fixed (Graphical ↔ Tabular pill now actually glides)** — the sliding white pill was snapping, not sliding. Root cause: the `div[data-baseweb="tab-highlight"]` transition targeted `left`/`width`, but baseweb (Streamlit 1.58) repositions the highlight via **`transform: translateX(...)`** — so the transitioned property never changed and the pill jumped. Changed the transition to `transform .28s, width .28s` (was `left .28s, width .28s`) in `theme.py`. **Verified live** by polling the highlight's computed `translateX` during a tab switch: it eases smoothly between positions (5px↔149px) over ~280ms. → `theme.py` (`div[data-baseweb="tab-highlight"]` block); see updated "Accent = orange" gotcha.
- **Log out button — invert on hover** — the header Log out button (primary, orange fill) now **inverts on hover**: white fill + orange (`ACCENT`) border + orange text/icon. Scoped to its `div[class*="st-key-logout_top"]` container so other primary buttons (Sign in, active nav) are untouched. → `theme.py` (rule after `.stButton > button[kind="primary"]`).

### 2026-06-26
- **Home — full-width Methodology banner** — added a wide gradient banner button **spanning the four module cards** that navigates to the Methodology page (key `home_methodology`, `schema` icon). via `div[class*="st-key-home_methodology"]` CSS in `theme.py` — distinct from the `st-key-homemod_*` card-buttons (no selector clash). **Matches the white module cards**: white bg + `#e8edf3` border, blue (`PRIMARY`) icon, `PRIMARY_DARK` title (20px/800), `NEUTRAL` description, `PRIMARY_SOFT` hover. **Tall banner** (min-height 92px); the label `<p>` is flexed so the **"View →" CTA is a solid orange pill (orange bg, white text) pushed to the far right** (whole banner is the click target, so the pill is clickable). → `app.py` `page_home()` + `theme.py`.
- **New Methodology page (infographic-led)** — added a 6th top-nav page **Methodology** (`NAV` + `top_nav` widened to 6 cols + `PAGES` + `page_methodology()` in `app.py`; `schema` material icon). General (not per-product) methodology generalised from bigmint.co: gradient **hero**, **stat strip** (~98% accuracy / 15+ yrs data / 1–2% delta / IOSCO-audited), a 6-step **pipeline flow** infographic laid out as **two balanced rows of three** (1→2→3 / 4→5→6, arrows within each row, orange step-numbers carry the sequence across the row break — avoids the ugly 5+1 flex-wrap; built by chunking `steps` 3-at-a-time in `page_methodology()`): Market data → Signal engineering → ML + sentiment → Ensemble → 12-wk forecast → Accuracy tracking, 6 **key-factor** cards (cost drivers, upstream–downstream, global prices, supply & demand, macro, sentiment), **4 forecast-horizon** cards (Weekly, Short term=monthly, Medium term=quarterly, Long term=annual; grid is `repeat(4,1fr)`), transparency/IOSCO cards, and a limitations disclaimer. All HTML/CSS infographics — new `.bm-meth-hero`, `.bm-stat*`, `.bm-flow*`, `.bm-factor*`, `.bm-horizon*` classes in `theme.py` (responsive grid collapses at 760px). Reachable from the nav and from a full-width banner button on Home (see the Home Methodology banner entry). → `app.py`, `theme.py`.
- **Branding renamed → "Price Forecasting: Steel"** — product title changed from "Steel Price Forecasting Model" everywhere it's shown: browser tab `page_title`, login caption, Home header (`app.py`), and the topbar portal title "AI Labs — Price Forecasting: Steel" (`theme.py`). Also updated the `app.py` docstring, `README.md` and this handoff's title/locked-decision line. (Earlier same-day entries still reference the old name as historical record.)
- **Login — Demo credentials section removed** — dropped the "Demo credentials" expander (username/password list) from `login_screen()`. `auth.DEMO_CREDENTIALS` is now unused by the app but **left defined in `auth.py`** (documents the demo logins; re-add the expander to surface it again). → `app.py` `login_screen()`.
- **Home KPI relabel** — the 4th overview KPI label "Last actual" → **"Last updated on"** (value/sublabel unchanged: most-recent assessment date). → `app.py` `page_home()`.
- **Import calculator — landed-cost bar chart (modern restyle)** — added a Plotly bar chart (x = country/source, y = landed cost Rs./t) below the "lowest cost source" banner in `calc_import_price.py` `render()`. Bars sorted cheapest→priciest with **rounded corners** (`marker.cornerradius`), white borders, bold value labels, and a **diverging colour scale by `diff`** (green = cheaper than domestic → amber ≈ parity → red = pricier, `cmid=0`). Domestic benchmark = a **dashed blue line with a pill badge** (`add_hline` + annotation bgcolor). Light gridlines, `bargap=0.45`. Plain `st.plotly_chart` (no highlighter layer); `st.bar_chart` fallback in try/except. → `calculators/calc_import_price.py`.
- **Analyst Calls — detailed sectioned summary** — each call card now shows, below the headline summary line, a labelled one-line breakdown: **Flats / Longs / Raw materials / Imports & exports / Outlook** (label column + one-line text, styled via `.bm-call-sec*` in `theme.py`). All are **placeholder** copy for now (real per-call commentary to be supplied) — defined in the `CALL_SECTIONS` list in `page_analyst()`; edit/extend that list to change sections. → `app.py` `page_analyst()` + `theme.py`.
- **Performance week-wise table — Week column removed** — the "Week-wise detail" table dropped its leading `W1/W2/…` column; it now shows **Date | Spot | Forecast | Delta**. (The directional-accuracy KPI/chart are unaffected.) → `app.py` `page_performance()`.
- **Tabs → animated sliding switch** — the Graphical/Tabular tabs keep the segmented-pill look but the white active pill now **slides** between options instead of snapping. Done by repurposing baseweb's `tab-highlight` (which it repositions inline per active tab) into a full-height white pill + an explicit `transition:left/width .28s` ease; removed the per-tab static white bg/shadow so the sliding pill is the only moving white element; tab buttons raised above it via `z-index`. → `theme.py` tab CSS. (Streamlit only swaps the *panel content* on rerun — that part can't carousel-slide; the **switch indicator** is what animates.)
- **Forecasting Tabular view → one continuous Actual-vs-Forecast table** — single table with cols **Date | Actual | Forecast | Δ (Actual − Forecast) | Direction**, history flowing straight into the 12-week-ahead forecast:
  - **History rows** (top): Actual + Forecast + Δ filled; **Direction left blank**. Window = shared `HIST_WEEKS` constant (= 26), the *same window as the chart* — `forecast_chart` and the table both `tail(HIST_WEEKS)` so the table mirrors the graph (verified: equal row counts for all 6 products). `acc_hist = load_accuracy("16-week", …)`, filtered `dropna(["Actual"])` to match the chart exactly.
  - **Forecast rows** (bottom, from `fwd`): **Actual + Δ blank**, Forecast + Direction filled; tinted with `.bm-fc-row` (faint orange band, mirrors the chart's shaded forecast region). **Week column** and the old **"Δ vs last actual" column** are gone.
  - `acc_hist` load hoisted above the tabs (was inside the Graphical tab) so both tabs share it. Footnote notes the top-N history window + that shaded rows are the forecast. → `app.py` `page_forecasting()`, `theme.py` (`.bm-fc-row`).
- **Forecasting chart + tabs restyle (modern look, bigger, no edge-clipping)** —
  - *Tabs → segmented pills*: `theme.py` tab CSS rewritten from underline-tabs to a **pill/segmented control** on a grey track (`div[data-baseweb="tab-list"]` = inline-flex rounded `#e9edf4` bg; active tab = white pill + orange text + shadow; `tab-highlight`/`tab-border` hidden). Applies to **all** `st.tabs` (forecasting + calculators).
  - *Chart bigger + same footprint as table*: `forecast_chart` height 430 → **500**; forecast-path table uses new **`.bm-table-lg`** variant (15px, padding 14/13px, uppercase header) so the two tabs feel equal-sized.
  - *"Cut from the sides" fix*: `_HL_TEMPLATE` now resets iframe `html,body` margins and adds a **`ResizeObserver` + window-resize** handler calling `Plotly.Plots.resize(gd)` (re-fits on tab-switch / window resize); `_style_fig` margins widened (l14/r22/t38/b14) + x-axis `automargin`; edge markers/halo set `cliponaxis=False` so they don't clip at the plot border.
  - *Modern styling*: actual-spot line now has a soft blue **area fill** (`_spot_trace(..., fill=True)`, `fill="tozeroy"` over a padded y-range so it reads as a band, not a block to zero); a dotted **divider** (`add_vline`) + faint orange **shaded band** (`add_vrect`) + "12-wk ahead" annotation mark where the forward forecast begins. Verified `fig.to_json()` still serializes (datetimes via `_dt()`). → `app.py` (`_style_fig`, `_spot_trace`, `_HL_TEMPLATE`, `_render_with_highlighter`, `forecast_chart`), `theme.py`.
- **Price forecasting — Graphical/Tabular tabs + Rationale section** — the spot-vs-forecast **chart** and the **12-week forecast-path table** are now split into two `st.tabs(["Graphical view", "Tabular view"])` (Graphical is the default/first tab; flip the order in `page_forecasting()` if Tabular should lead). Below the tabs, a new **"Forecast rationale"** section renders per-product commentary from a module-level `RATIONALES` dict (currently a single `"_default"` **placeholder** with Demand / Supply & cost / Trade & sentiment / Net-view stub bullets) — real analyst text to be supplied later by adding entries keyed by product name. New `notes` icon added to `theme.py` `_ICON_PATHS` for the section heading. → `app.py` `page_forecasting()` + `RATIONALES`, `theme.py`.
- **MAPA now averaged over the full series (82 wk), not last 16** — the **Home** overview KPI ("Avg absolute accuracy") was computing MAPA on `.tail(16)` of each product and labelled "MAPA, last 16 wk". Removed the `.tail(16)` cap so it averages the full series; label is now dynamic `f"MAPA, {n_weeks}-wk avg"` (currently 82). The **Performance** page already read all rows (no cap) — added the week count to its MAPA sublabel (`f"100 - mean abs % error · {len(view)} wk"`). Week count is computed from the data (`Accuracy_Table_6` = 82 rows/product), not hardcoded, so it self-updates. → `app.py` `page_home()` + `page_performance()`.
- **Accent flipped to orange** — `primaryColor` in `.streamlit/config.toml` changed `#024CA1` (blue) → `#EE4E24` (orange ACCENT) so **primary buttons (Sign in / Log out / active nav) and tab highlights** all render orange natively, not just via the version-fragile CSS overrides. The brand **topbar stays blue** (uses the `PRIMARY` constant in `theme.py`, independent of `primaryColor`). See updated "Accent = orange" gotcha. NB: `.streamlit/config.toml` is **untracked in git** — this change lives only in the working tree.
- **Footer co-brand separator `|` → `-`** — footer now reads "© BigMint - Adani · AI Labs" (the `&nbsp;|&nbsp;` before the bigmint.co link is a separate list separator, left as-is). → `theme.py` `footer()`.
- **Home — Performance card description lengthened** — was a 2-line blurb ("Week-wise accuracy: spot, forecast, delta and direction.") which left its "Open →" CTA higher than the other three 3-line cards. Expanded to "Week-wise accuracy: spot vs forecast, weekly delta, MAPA and directional hit-rate." so it wraps to ~3 lines and the CTAs align across the row. → `app.py` `page_home()` `modules` list.
- **Co-brand text removed; topbar separator `×` → `|`** — the "BigMint × Adani" co-brand string now appears **only in the topbar** (as the two logos). Topbar divider between BigMint logo and the Adani chip changed from `&times;` to a pipe `|` (`render_topbar()` in `theme.py`; `.bm-cobrand-x` styling unchanged — class name kept as the CSS hook). Removed the co-brand text from: browser tab `page_title` → "Steel Price Forecasting Model", login caption → "Steel Price Forecasting Model", Home header → "## Steel Price Forecasting Model" (all `app.py`). **Footer keeps the co-branding** (separator later finalized to `-` — see the footer entry above): "© BigMint - Adani · AI Labs" (`theme.py` `footer()`). → `theme.py`, `app.py`.

### 2026-06-25
- **Analyst Calls** — added a third **Download Video** button (`:material/videocam:`) per call card beside PDF/PPT; row layout now `st.columns([1,1,1,3])`, corner label "PDF / PPT / Video". All three remain **disabled placeholders** (no real files wired yet). → `app.py` `page_analyst()`.
- **Performance dashboard** — added two full-width charts below the Rs. delta bar (both read the same `view` frame; wired in `page_performance()` after `delta_bar`):
  - **Weekly forecast accuracy (%)** — `accuracy_chart()`: green spline line of `100 − |DeltaPct|`, %-suffixed y-axis, hover-ball.
  - **Weekly directional accuracy** — `directional_accuracy_bar()`: diverging bars per week, green "up" = correct directional call, red "down" = wrong (first week neutral — no prior reference, matching the KPI's `iloc[1:]` logic); hover shows predicted vs actual.
- **Direction flags (Up/Down/Flat), flat threshold = 500** — new `direction_flag(delta, thr=500)` + `FLAT_THRESHOLD = 500.0` in `data_loader.py`; a **±500 Rs./ton dead-band ⇒ Flat**. Applied in: `load_accuracy` `PredDir`/`ActualDir` (change vs prior week's spot), `load_forward` `Direction` (derived from `Delta`, replacing the value read from the file), and the forecasting-page **Next-wk / +12-wk KPI chips** (recomputed in `page_forecasting()` from `forecast − last actual`). Directional-accuracy KPI sublabel → "correct up/down/flat calls".
- **Log out button** — moved out of the nav row into the **top-right of the header** and restyled `type="primary"` to match the Sign-in button. Header is now `st.columns([6,1], vertical_alignment="center")`: brand bar (hcol1) + Log out (hcol2, key `logout_top`). Nav row trimmed to the 5 page buttons (old `nav_logout` removed). → `app.py` header block + `top_nav()`.
- **Tabs + segmented-selector accent → orange** — targeted CSS in `theme.py` `inject_css()` so the **active tab** (label + underline) and **active segmented selector** (Product/Window) render in `ACCENT` (#EE4E24); brand bar, primary buttons and `primaryColor` (#024CA1) stay blue. Selectors (verified vs Streamlit 1.58 bundle): `button[data-baseweb="tab"][aria-selected="true"]`, `div[data-baseweb="tab-highlight"]`, `button[data-testid="stBaseButton-segmented_controlActive"]` (+ its `p`). NB: these were **not** orange before — fresh accent, not a revert.
- **Performance dashboard — data source simplified** — removed the 6/16-week window toggle; the section now always reads **`Accuracy_Table_6`** and shows **all rows** (dropped the `.tail(16)` cap), so KPIs/charts/table span the full series. Direction column still uses the ±500 up/down/flat `direction_flag`; Actual/Forecast come straight from the sheet. `Accuracy_Table_16` is now unused by the app (file + `ACC_PATHS["16-week"]` left in place, just not referenced). → `app.py` `page_performance()`.
- **Performance week-wise table — Direction column removed** — dropped the Direction chip column (header, per-row cell, and the footnote line); the table now shows **Week / Date / Spot / Forecast / Delta**. The up/down/flat `direction_flag` logic is unchanged and still feeds the directional-accuracy KPI + the weekly directional-accuracy chart. → `app.py` `page_performance()`.
- **Co-branding → BigMint × Adani** — topbar now renders BigMint logo **×** Adani logo (Adani sits in a white chip via `_adani_logo_html()`, which loads `assets/adani_logo.png` or falls back to a gradient-text "adani"). Page title, login caption, home header and footer all read "BigMint × Adani". Also fixed brand-name casing **Bigmint → BigMint** (login caption + home header in `app.py`; the wordmark fallback in `theme.py`). → `theme.py` (`_adani_logo_html`, `render_topbar`, CSS `.bm-adani-chip` / `.bm-cobrand-x`, footer) + `app.py`. The official `adani_logo.png` is now in place and **auto-trimmed** (1402×854 → 1108×452; untrimmed original kept as `adani_logo_orig.png`), so the topbar shows the real Adani logo (fallback no longer used).
- **Removed model-architecture mentions (NHITS / NBEATSx / TFT / …)** — dropped the "Model agreement (top-3 by direction)" footnote and the `top3` read in `page_forecasting()`. These names were never hardcoded in the app; they came only from the data's `Top-3 models (direction)` column, which still exists in `forecast_forward.xlsx` but is no longer surfaced anywhere in the UI. → `app.py`.
- **Removed Raw-material price forecast section** — deleted the second tab in `page_forecasting()`; the page is now **steel-only with no tab wrapper** (steel content rendered directly under the page). Cleaned up the now-orphaned `BIGMINT_URL` (`app.py`) and `STEEL_FF_LABELS` (`data_loader.py`), and dropped "plus the raw-material feed" from the Home "Price forecasting" card. (Unrelated "raw material" wording in the analyst market-commentary placeholder and the cost calculator's cost categories was left as-is.) → `app.py`, `data_loader.py`.
- **Home modules → uniform clickable card-buttons** — replaced the three HTML `module_card`s + separate "Open" buttons **and** the standalone Calculators card/button with **four equal clickable card-buttons in one row** (`st.columns(4)`): Price Forecasting / Analyst Calls / Performance / Calculators. Each whole card is a single `st.button` (material icon + **bold title** + description) that navigates on click — no more separate "Open" button. Styled via `div[class*="st-key-homemod_"]` CSS in `theme.py`, scoped by Streamlit's per-key container class (≥1.39; running 1.58) so nav/logout/other buttons are untouched. `theme.module_card()` is now unused but left in place. → `app.py` `page_home()` + `theme.py`.

## Pending / not done
- Analyst Calls: real summaries + PPT/PDF/**video** + upload workflow (PDF/PPT/Video buttons exist but are disabled placeholders).
- Horizon tabs (Short/Medium/Long/Weekly) from the reference — NOT added (locked to 12-wk).
- Calculators' inner styling still original (lighter look than the rest).
- **Auth follow-ups:** (1) ~~Remove the `?authdebug=1` panel from `app.py`~~ **DONE 2026-07-06** — the diagnostic block was removed from `app.py`. (2) Consider scrubbing the old demo passwords/hashes from git history (they're in pre-2026-07-06 `auth.py`). (3) Neon free tier scales to zero → first query after idle has a cold-start (~1–2 s); a keepalive/paid tier would remove it. (4) Delete `.streamlit/seed_credentials.txt` after distributing the temp passwords. (5) `.streamlit/secrets.toml.example` documents `database_url` + `session_signing_key` as of 2026-07-06 — keep it in sync if the auth secrets change.


---

# Appendix A — Per-role white-label dashboards + admin-managed access (feature plan / record)


> Status tracker for the multi-role dashboard feature. Tasks are checked off as they land;
> this doc is updated after **each** task. Approved 2026-07-06.

## Context
Today the portal renders one identical dashboard for everyone: a hardcoded BigMint · Adani topbar
(`theme.render_topbar`), the full fixed set of 6 commodities (`data_loader.STEEL_PRODUCTS`) on every
page, and a single global list of analyst calls. The goal is a **per-role white-label app** on a
single deployment:

- Each **role** (`auth.ROLES = ["Admin", "Analyst", "Adani"]`, extensible) gets its own branded
  dashboard — logo/co-brand, title, theme colors, and which nav pages are visible. **Branding is
  static, developer-configured once in code**, applied per session from the logged-in user's role.
- The **Admin** controls, at runtime, **which commodities** each role sees and **which analyst calls**
  each role sees (calls tagged by audience). These are the only runtime-editable knobs.

## Design overview
| Concern | Where it lives | Who edits |
|---|---|---|
| Branding (logo, co-brand, title, colors, visible pages) | `theme.ROLE_PROFILES` dict (code) | Dev, once |
| Commodity access per role | new Postgres table `role_commodities` | Admin (Admin tab) |
| Analyst-call audience | `audiences` field on each call in `calls.json` / `SAMPLE_ANALYST_CALLS` | Admin (call editor) |

Single deployment; the logged-in user's `role` selects everything at render time.

## Tasks
- [x] **1. theme.py** — `ROLE_PROFILES`/`DEFAULT_PROFILE`/`profile_for`/`apply_role_theme`; refactor the
  4 themeable colors in `inject_css` to CSS variables (`--bm-primary`, `--bm-primary-dark`,
  `--bm-primary-soft`, `--bm-accent`) seeded on `:root`; `render_topbar(user)` builds co-brand, title
  and bar color from the profile. Left BigMint logo stays constant; `cobrand_logo=None` hides the chip.
- [x] **2. db.py** — add `role_commodities (role, commodity, PK(role,commodity))` to `_DDL`;
  `get_role_commodities(role)` + `set_role_commodities(role, list)` (DELETE-then-INSERT txn).
- [x] **3. data_loader.py** — add `"audiences": []` to each `SAMPLE_ANALYST_CALLS` entry (empty = all).
- [x] **4. app.py** — `allowed_products(role)` + `_call_visible(call, role)` helpers; call
  `theme.apply_role_theme(profile_for(user.role))` after login; filter products in
  forecasting/performance/home; filter calls in `page_analyst`; audience `multiselect` in the admin
  call form; new `_admin_access_panel()` in `page_admin`; gate `top_nav` + page routing by profile.
- [x] **5. Docs + verify** — this doc updated after every task; `py_compile` all modules; live-Neon
  smoke test (schema create + commodity round-trip w/ cleanup + profile resolution + audience filter);
  login screen renders the new topbar with no errors. In-app per-role screenshots pending an owner login.

## Semantics / decisions
- **Commodity access:** a role with **no saved rows = all** commodities (unconfigured default). To
  restrict, admin saves a subset; saving an empty set is disallowed — so empty-config only ever means
  "unconfigured = all" (no ambiguity). Admin role always sees all.
- **Analyst audience (deny-by-default, updated 2026-07-07):** a non-admin role sees a call only if its
  role is explicitly in the call's `audiences`. Empty/missing ⇒ *unassigned*: **admins only** (no other
  role sees it). Admin always sees all calls (incl. the preview). ⚠ Existing untagged `calls.json`
  entries become admin-only until an admin assigns their audience.
- **Adding a new client role:** the **admin** creates the role directly in the Add-user form
  (free-text "create a new role") — no `auth.ROLES` edit needed; it auto-appears in every role picker
  via `known_roles()`. Then set its commodity access + tag its calls in the Admin tab. For **custom
  branding** (logo/title/colors/pages) a **dev** drops a logo in `portal/assets/` and adds a
  `theme.ROLE_PROFILES` entry; until then the new role uses `DEFAULT_PROFILE`.
- **Grouped forecasting layout (Adani / Analyst / Admin; born 2026-07-07 as `adani_dev`, promoted 2026-07-10):** beyond branding/access, a role can get a
  different **Price-forecasting UI**. The grouped roles use a **grouped** layout — a top HRC/HR Plate/Rebar/
  Structure group tab-strip, then one row with a **sliding pill switch** for Graphical/Tabular on
  the left (an `st.segmented_control` — NOT `st.tabs`, whose baseweb CSS hooks are dead on the deployed
  build (streamlit 1.59, react-aria markup) — styled as a grey capsule track + a white label-width pill
  gliding behind the active option; selectors cover both the 1.58 testid and the 1.59 `aria-checked`
  markup, `.st-key-fc_view_box`; on 2026-07-08 everything was aligned on 1.59 — conda env +
  requirements pins bumped to 1.59.0, and plain `st.tabs` pill CSS in `theme.py` gained the
  react-aria selector generation too, so `st.tabs` is styleable again on the deployment; same day the
  tab track got `width:fit-content` — it stretched full-screen as a 1.59 flex item — and the app went
  compact: block gap 1rem→0.65rem, top padding/margin 0 + stDecoration hidden + app header
  display:none + the CookieManager iframe (`st-key-portal_cm`, the real top-gap culprit) hidden,
  side padding 1.2rem, heading padding trimmed, `.st-key-fc_loc_box` pull-up retuned
  −58px→−52px to the new gap) and a
  **right-aligned location/full-name dropdown** (styled border + tint, **shared across Graphical+Tabular** so it works
  in the table view too, sorted alphabetically, defaulting to the first), then the **graph on top**
  (no section title), then the **3 price cards stacked to the RIGHT of the chart** (2026-07-08:
  moved from below the tab block — `st.columns([5,1])` + `price_cards(vertical=True)`, which emits
  one `.bm-vcards` HTML flex column — natural-height cards, 14px gaps, top-aligned,
  max-width 280px, right-aligned (own markup — Streamlit-container CSS attempts kept bunching);
  the Tabular view keeps them below the table; y-axis ticks also gained an 8px label standoff),
  an in-chart legend, and
  year-stamped x-axis labels. The chart runs `forecast_chart(compact=True)` with the **week/zoom
  buttons sitting just ABOVE the plot** (rangeselector y=1.01/bottom) and a slim top margin so the
  plot stays **bigger** (h=620, top margin 46).
  Gated by `app.py` `GROUPED_FORECASTING_ROLES` (case-insensitive) =
  `{"adani", "analyst", "admin"}` — a dev-controlled behaviour flag, not a runtime knob. The staging
  role `adani_dev` was dropped 2026-07-10 once the layout was promoted to the live roles; the
  non-grouped fallback code remains for any future role left out of the set.

> NB (2026-07-07): the whole app is now **full-bleed** — `.block-container` fills the viewport width
> at any resolution (was 1180px) — so every role's dashboard, including the grouped layout, scales
> with the monitor; login/reset cards stay capped at 460px. See the handoff changelog.

## Known limitation
`.streamlit/config.toml` `primaryColor` is a build-time global, so native Streamlit widgets (default
primary buttons/tabs) keep the global orange for all roles. The brand topbar and all custom-CSS
surfaces follow the role. Acceptable for the current build.

## Verification
1. `python -m py_compile portal/app.py portal/theme.py portal/db.py portal/data_loader.py`.
2. `role_commodities` is created by the cached `_ensure_db_schema()` (runs `db.init_db()` once per
   process) — the app didn't previously call `init_db()`. Confirm login works with no schema error.
3. Run via the `portal` launch config (port 8501); log in as adani / analyst / admin — branding + nav
   differ. Admin sets Adani to a 2-commodity subset → adani sees only those. Admin tags a call
   `[Analyst]` → adani can't see it, analyst can, admin preview still shows it. Stale hidden page →
   falls back to Home.

## Post-plan UI polish
- **2026-07-09 (go-live pass):** top nav centred with equal-width buttons + an 8px drop below the
  brand bar; the Home **module cards**: icon embedded in the (bigger) bold heading, left-aligned +
  vertically centred, one-liners rewritten to ≈equal length (~2 lines) so they wrap identically and
  align, taller cards + enlarged "Modules" heading to fill the page;
  the "Calculators" page **relabelled "Scenario Simulation"** everywhere user-facing
  (**internal page key `"Calculators"` kept** — routing/`PAGES`/`profile["pages"]` unchanged); the
  "Last updated on" / "Last actual spot" dates now render as **"Week N, Mon YYYY"**
  (`app._week_of_month_label`); the Adani co-brand logo's **white square/chip removed** (sits directly
  on the blue bar); **all "prototype" UI text removed** for launch; the **"Price forecasting" H2 dropped**
  from the forecasting page; and the forecasting **zoom buttons (1W/4W/…) rebuilt as fixed HTML buttons**
  above the chart (Plotly's SVG rangeselector jittered on click — CSS didn't help, so it was replaced
  with HTML `<button>`s wired to `Plotly.relayout`). Also the grouped **location dropdown now shows full
  descriptive product names** (`app.FORECAST_LOCATION_LABELS`; box widened 250→660px ≈ 85 chars) — this dict is the
  editable knob for those labels. The grouped **graphical right rail** was also restructured: the
  **+12-week card removed**, a **1W/4W/8W/12W forecast-horizon tab** added above the (now smaller,
  horizontal) cards that drives **both** the second card's value (`_forecast_at(n)`, positional on the
  12-wk `fwd` path) **and the graph** (`render_graph_view(horizon)` → `fwd.head(n)`, forecast drawn out to
  n weeks), and the **Forecast rationale moved into the rail as the 3rd card** (heading inside the card).
  Finally, **all displayed forecasts are rounded to Rs.50** (`_round50`) and **both data tables**
  (forecasting Tabular view + Performance week-wise detail) are now **sortable over the whole dataset +
  paginated at 52 rows/page** via a reusable `render_sortable_table` (sort-by picker + asc/desc flip icon
  + Prev/Next). **Fixes:** Prev/Next rebuilt on `on_click` callbacks (disabled-state/page no longer lag a
  render — Prev was showing active on page 1, Next on the last page); and the intermittent
  `KeyError: 'auth'` at startup fixed with `[server] fileWatcherType = "none"` in `.streamlit/config.toml`
  (watchdog was purging `sys.modules` mid-import during git-pull redeploys). The **Performance page** also
  gained the forecasting-style **grouped picker** (group tab-strip + full-name location dropdown, on one
  row — tabs left / dropdown right), **green-heavy gradient bars** (accuracy: highest green, y-axis zoomed
  to the high-90s, shorter; deviation: rounded-forecast−spot, green = small error, taller), and section
  renames (Actual vs Forecast deviation / Weekly forecast absolute accuracy / Weekly directional hit
  accuracy). All four performance charts share a **fixed left margin (`_PERF_ML=68`, autoexpand off) so
  they render at the same width**, a tighter y-label standoff (8→3), the line chart's **legend moved
  inside**, and the rounded-price footnote removed. Full detail in the Changelog above (2026-07-09).
- **2026-07-10:** Scenario Simulation tabs renamed + reordered (`app.py` `page_calculators()`) to
  **Price Sensitivity** (elasticity) → **Landed Cost** (import parity) → **Cost Head** (production
  cost & margin). Labels/order only; calculator bodies unchanged. Full detail in the Changelog above.
- **2026-07-20:** Layout pass (impeccable). Assessed the whole portal — layout already systematic
  (consistent block gap, tuned hierarchy, correct grid/flex split, 1024/760 breakpoints); no rewrite.
  One fix applied: **Methodology stat strip** (`theme.py` `.bm-stat-row`) now steps **6→3→2** — added a
  `repeat(3,1fr)` at the 1024px breakpoint so the six tiles no longer cram on tablet (was 6→2 only at 760px).
- **2026-07-20 (audit + fixes):** Ran `/impeccable audit` (scored 15/20, Good) then the recommended
  commands. **clarify:** `.bm-call-kinds` + login reveal-eye recoloured `#94a3b8`→`#64748B` (were <4.5:1).
  **extract:** neutral ramp tokenised — added `--bm-border`/`--bm-line`/`--bm-ink` to `:root` and replaced
  the repeated literals `#e8edf3`(×10)/`#eef2f7`/`#334155` in `theme.py` (grid.py left literal — AgGrid
  shadow DOM can't read `:root`). **harden:** section-title divs got `role=heading`/`aria-level` (keeps the
  div, avoids Streamlit's anchor icon); arbitrary z-indexes (99990/99991/2147483647/5) replaced by a named
  `--z-raise…--z-splash` scale. **polish:** gradient-text logo fallbacks (`_adani_logo_html`,
  `_cobrand_logo_html`) → solid `PRIMARY`; login `::placeholder` set to `#6b7686` (was failing-contrast
  browser default). **optimize + adapt:** assessed, no change — Plotly CDN is HTTP-cached across iframes
  with a working fallback (not worth vendoring); the 270px view-switch pill fits all real viewports (≥320px).
- **2026-07-20 (harden):** `.bm-flow-t` step-flow titles in the three calculators (calc_elasticity,
  calc_import_price, calc_cost) given `role=heading`/`aria-level=4` — real heading semantics for the
  numbered pipeline steps, kept as divs to avoid Streamlit's markdown anchor icon (same trick as
  `section_title`). Note: the methodology page itself no longer uses `.bm-flow` (it's on `.bm-engine`).
