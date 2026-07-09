# Per-role white-label dashboards + admin-managed access — PLAN

> Status tracker for the multi-role dashboard feature. Tasks are checked off as they land;
> `handoff.md` is updated after **each** task. Approved 2026-07-06.

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
- [x] **5. handoff.md + verify** — handoff updated after every task; `py_compile` all modules; live-Neon
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
- **Per-role forecasting layout (adani_dev, 2026-07-07):** beyond branding/access, a role can get a
  different **Price-forecasting UI**. `adani_dev` uses a **grouped** layout — a top HRC/HR Plate/Rebar/
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
  Gated by `app.py` `GROUPED_FORECASTING_ROLES` (case-
  insensitive) — a dev-controlled behaviour flag, not a runtime knob. This is the staging ground for
  the eventual Adani cut-over: **promote by adding `"adani"` to `GROUPED_FORECASTING_ROLES`** (and, if
  desired later, fold the flag into `theme.ROLE_PROFILES`). Non-grouped roles are unaffected.

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
  inside**, and the rounded-price footnote removed. Full detail in `handoff.md` changelog 2026-07-09.
