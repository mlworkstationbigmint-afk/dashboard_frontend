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
  Structure group tab-strip, then one row with a **modern slider switch** for Graphical/Tabular on the
  left (capsule track + gliding accent thumb, `.st-key-fc_view_box`) and a **right-aligned
  location/full-name dropdown** (styled border + tint, **shared across Graphical+Tabular** so it works
  in the table view too, sorted alphabetically, defaulting to the first), then the **graph on top**
  (no section title), then the **3 price cards below the tab block**, an in-chart legend, and
  year-stamped x-axis labels. The chart runs `forecast_chart(compact=True)` with the **week/zoom
  buttons sitting just ABOVE the plot** (rangeselector y=1.01/bottom) and a slim top margin so the
  plot stays **bigger** (h=620, top margin 46).
  Gated by `app.py` `GROUPED_FORECASTING_ROLES` (case-
  insensitive) — a dev-controlled behaviour flag, not a runtime knob. This is the staging ground for
  the eventual Adani cut-over: **promote by adding `"adani"` to `GROUPED_FORECASTING_ROLES`** (and, if
  desired later, fold the flag into `theme.ROLE_PROFILES`). Non-grouped roles are unaffected.

## Known limitation
`.streamlit/config.toml` `primaryColor` is a build-time global, so native Streamlit widgets (default
primary buttons/tabs) keep the global orange for all roles. The brand topbar and all custom-CSS
surfaces follow the role. Acceptable for the prototype.

## Verification
1. `python -m py_compile portal/app.py portal/theme.py portal/db.py portal/data_loader.py`.
2. `role_commodities` is created by the cached `_ensure_db_schema()` (runs `db.init_db()` once per
   process) — the app didn't previously call `init_db()`. Confirm login works with no schema error.
3. Run via the `portal` launch config (port 8501); log in as adani / analyst / admin — branding + nav
   differ. Admin sets Adani to a 2-commodity subset → adani sees only those. Admin tags a call
   `[Analyst]` → adani can't see it, analyst can, admin preview still shows it. Stale hidden page →
   falls back to Home.
