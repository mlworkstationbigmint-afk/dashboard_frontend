"""
Analyst-only guided walkthrough.

A small hidden component iframe bootstraps a driver.js (CDN) product tour that runs
in the PARENT Streamlit document. Because Streamlit reruns only diff the app DOM (they
do NOT reload the page), globals + the injected tour survive navigation, so the tour can
step across pages by clicking the real nav buttons. Same-origin `srcdoc` iframe → the
iframe script can reach `window.parent.document`.

Trigger: auto-prompts once per browser (localStorage `bm_tour_seen`); a floating
"Take a tour" launcher (bottom-right, injected into the parent) replays it anytime.

Delivery mirrors app.py `_render_with_highlighter`: write a temp file + `st.iframe`
(avoids the deprecated `components.v1.html` 1.59 log-spam). Steps are data-driven in
JS (see TOUR_JS `STEPS`) so copy is easy to tune.
"""
import tempfile
import uuid
from pathlib import Path

import streamlit as st

DRIVER_JS = "https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist/driver.js.iife.js"
DRIVER_CSS = "https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist/driver.css"

# The tour. The iframe is a ONE-SHOT bootstrap: it injects driver.js AND the controller into the
# PARENT document, so all live execution runs in the parent window (which never reloads across
# Streamlit reruns) — the hidden iframe can be torn down/reloaded at any time without freezing a
# running tour. CONTROLLER is serialised with Function.toString() and re-evaluated in the parent
# realm, so inside it `document`/`window` ARE the parent's. __AUTO__ is replaced Python-side.
TOUR_JS = r"""<!doctype html><html><head><meta charset="utf-8"></head><body>
<script>
(function(){
  var P; try { P = window.parent; } catch(e) { return; }
  if (!P || P === window) return;
  var pd = P.document;

  // The controller — runs in the PARENT realm once injected (document/window = parent's).
  function CONTROLLER(){
    if (window.__bmTourInit) return;      // idempotent across re-injections
    window.__bmTourInit = true;
    var AUTO = __AUTO__, D = (window.driver && window.driver.js) ? window.driver.js.driver : null;
    if (!D) { window.__bmTourInit = false; return; }

    // ---- brand + driver overlay styling ----
    var stl = document.createElement("style");
    stl.textContent = ""
      + ".driver-popover.bm-pop{border-radius:16px;box-shadow:0 22px 60px rgba(2,18,43,.34);max-width:460px;padding:26px 28px 22px}"
      + ".driver-popover.bm-pop .driver-popover-title{font-size:21px;color:#024CA1;font-weight:800;line-height:1.3;margin:0 0 12px}"
      + ".driver-popover.bm-pop .driver-popover-description{font-size:15.5px;color:#1A1A1A;line-height:1.7;margin:0}"
      + ".driver-popover.bm-pop .driver-popover-close-btn{color:#94a3b8;font-size:26px;width:30px;height:30px;top:14px;right:14px}"
      + ".driver-popover.bm-pop .driver-popover-close-btn:hover{color:#1A1A1A}"
      // footer module: progress (left) + custom nav buttons (right), split off by a hairline rule.
      // driver.js renders no next/prev in single-highlight mode, so we draw our own.
      + ".driver-popover.bm-pop .bm-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;"
      + "margin-top:20px;padding-top:16px;border-top:1px solid #e8edf3}"
      + ".driver-popover.bm-pop .bm-meta{font-size:12.5px;color:#94a3b8;font-weight:600;letter-spacing:.2px}"
      + ".driver-popover.bm-pop .bm-nav{display:flex;gap:10px}"
      + ".driver-popover.bm-pop .bm-b{background:#eef2f7;color:#334155;border:1px solid #cbd5e1;border-radius:9px;"
      + "font-weight:700;padding:9px 18px;cursor:pointer;font-size:14px;font-family:inherit}"
      + ".driver-popover.bm-pop .bm-b:hover{background:#fff;color:#024CA1}"
      + ".driver-popover.bm-pop .bm-next{background:#EE4E24;color:#fff;border-color:#EE4E24}"
      + ".driver-popover.bm-pop .bm-next:hover{background:#fff;color:#EE4E24}"
      + ".driver-overlay,svg.driver-overlay{z-index:2147483000 !important}"
      + ".driver-popover{z-index:2147483600 !important}"   // MUST sit above the overlay or clicks are swallowed
      // lift the spotlighted element above the overlay — some app elements (e.g. the pulled-up location
      // dropdown) set their own z-index/stacking context that would otherwise keep them dimmed
      + ".driver-active-element{position:relative !important;z-index:2147483200 !important}"
      // launcher lives INSIDE the blue topbar (.bm-topbar-r), at the bar's right end just left of
      // Log out — so the blue header extends right up to it. Rounded-rectangle like Log out, but a
      // translucent-white chip so it stays visible ON the blue bar; hover inverts to white/blue.
      + "#bm-tour-launch{background:#fff;color:#024CA1;border:1px solid #fff;"
      + "border-radius:8px;padding:12px 26px;font-size:15.5px;font-weight:800;cursor:pointer;"
      + "font-family:inherit;white-space:nowrap}"
      + "#bm-tour-launch:hover{background:#024CA1;color:#fff;border-color:#fff}";
    document.head.appendChild(stl);

    // ---- parent-DOM helpers ----
    function q(sels){ for (var i=0;i<sels.length;i++){ var e=document.querySelector(sels[i]); if(e) return e; } return null; }
    var MAIN = ['[data-testid="stMainBlockContainer"]','[data-testid="stMain"]','section.main','[data-testid="stAppViewContainer"]'];
    function main(){ return q(MAIN); }
    function navBtn(txt){
      var box = document.querySelector(".st-key-bm_topnav"); if(!box) return null;
      var bs = box.querySelectorAll("button"), t = txt.toLowerCase();
      for (var i=0;i<bs.length;i++){ if((bs[i].innerText||"").trim().toLowerCase().indexOf(t) >= 0) return bs[i]; }
      return null;
    }
    function chart(){
      var m = main(); if(!m) return null;
      var fr = m.querySelectorAll("iframe");
      for (var i=0;i<fr.length;i++){ if(fr[i].clientHeight > 120) return fr[i]; }   // skip the 0-height tour iframe
      return null;
    }
    function isActive(btn){
      if(!btn) return false;
      var t = btn.getAttribute("data-testid") || "";
      return t.indexOf("primary") >= 0 || !!btn.querySelector('[data-testid*="primary"]');
    }
    function tabBtn(txt){   // a tab in the current page's st.tabs strip, matched by label text
      var m = main(); if(!m) return null;
      var bs = m.querySelectorAll('[data-testid="stTab"], button[role="tab"]'), t = txt.toLowerCase();
      for (var i=0;i<bs.length;i++){ if((bs[i].innerText||"").toLowerCase().indexOf(t) >= 0) return bs[i]; }
      return null;
    }
    function ensureTab(txt){   // click a calculators tab if it isn't already the active one (client-side, no rerun)
      var b = tabBtn(txt);
      if (b && b.getAttribute("aria-selected") !== "true") b.click();
    }
    function visible(el){ return !!(el && el.getClientRects().length); }   // laid-out (not a hidden tab panel)

    // ---- steps (nav = visible nav-button text the step lives on) ----
    var STEPS = [
    {nav:"Home", title:"Welcome 👋",
     desc:"This is the BigMint · AI Labs steel price-forecasting portal. Here’s a quick tour of what every part does. Use <b>Next</b> to move on, or close (×) to skip — you can replay it anytime from the <b>Take a tour</b> button, top-right beside <b>Log out</b>."},
    {nav:"Home", el:function(){return document.querySelector(".st-key-bm_topnav");},
     title:"Top navigation", desc:"Your main menu — every button opens a section of the portal. We’ll walk through each one."},
    {nav:"Home", el:function(){return navBtn("Home");}, title:"Home",
     desc:"The landing page: headline stats and quick-launch cards for every module."},
    {nav:"Home", el:function(){return navBtn("Forecasting");}, title:"Price Forecasting",
     desc:"Spot price vs the 12-week Ensemble forecast for each steel product — chart + week-by-week table."},
    {nav:"Home", el:function(){return navBtn("Analyst calls");}, title:"Analyst Calls",
     desc:"Monthly market-outlook notes: key insights, price drivers and downloadable PDF / PPT decks."},
    {nav:"Home", el:function(){return navBtn("Performance");}, title:"Performance Dashboard",
     desc:"How accurate past forecasts were — accuracy %, directional hit-rate and weekly deltas."},
    {nav:"Home", el:function(){return navBtn("Scenario Simulation");}, title:"Calculators",
     desc:"Three what-if tools: Landed Cost (import parity), Cost Head (production cost & margin) and Price Sensitivity."},
    {nav:"Home", el:function(){return navBtn("Methodology");}, title:"Methodology",
     desc:"The full explainer of how the forecasts are built — data, models, ensemble and accuracy."},
    {nav:"Home", el:function(){return document.querySelector(".st-key-logout_top");}, title:"Log out", side:"left",
     desc:"Sign out securely. Your session also expires on its own after 12 hours."},
    {nav:"Home", el:function(){return document.querySelector(".st-key-bm_home_kpis");}, title:"Key stats",
     desc:"At-a-glance: products tracked, the 12-week horizon, average accuracy (MAPA) and the latest data date."},
    {nav:"Home", el:function(){return q(['[class*="st-key-homemod_"]']);}, title:"Quick-launch cards",
     desc:"Shortcut cards — click any one to jump straight into that module."},
    {nav:"Home", el:function(){return document.querySelector(".st-key-home_methodology");}, title:"Methodology banner",
     desc:"A one-click jump to the methodology explainer."},
    // ---- cross-page: Price Forecasting ----
    {nav:"Forecasting", el:function(){return document.querySelector(".st-key-fc_group");}, title:"Product groups",
     desc:"You’re on <b>Price Forecasting</b>. Start here — switch between commodity groups: HRC, HR Plate, Rebar and Structural section."},
    {nav:"Forecasting", el:function(){return document.querySelector(".st-key-fc_view_box");}, title:"Graphical / Tabular",
     desc:"Slide this switch to flip between the chart and the week-by-week Actual-vs-Forecast table."},
    {nav:"Forecasting", el:function(){return document.querySelector(".st-key-fc_loc_box");}, title:"Location", side:"bottom",
     desc:"Pick the exact grade/location within the group — it applies to both the chart and the table."},
    {nav:"Forecasting", el:chart, title:"Forecast chart",
     desc:"Light-blue = actual spot, red dashed = the 12-week Ensemble forecast (violet = China import-parity landed cost on HRC). Hover any point for its price; use the zoom buttons just above the plot (1W…ALL)."},
    {nav:"Forecasting", el:function(){return document.querySelector(".st-key-fc_horizon");}, title:"Forecast horizon", side:"left",
     desc:"Choose 1 / 4 / 8 / 12 weeks ahead — it drives both how far the forecast is drawn and the forecast card below."},
    {nav:"Forecasting", el:function(){return q(['.bm-vcards']);}, title:"Price cards & rationale", side:"left",
     desc:"The last actual spot, the selected-horizon forecast with an up/down/flat chip, and a short <b>forecast rationale</b> explaining the call."},
    // ---- cross-page: Analyst Calls ----
    {nav:"Analyst calls", el:function(){return q(['[class*="st-key-callcard_"]']);}, title:"Analyst call card",
     desc:"You’re on <b>Analyst Calls</b>. Each card is a monthly market-outlook call — its date, title and a headline summary."},
    {nav:"Analyst calls", el:function(){return q(['.bm-call-secs']);}, title:"Driver breakdown",
     desc:"A one-line read per theme: Flats, Longs, Raw materials, Imports &amp; exports, and the Outlook."},
    {nav:"Analyst calls", el:function(){return q(['[class*="st-key-pdf_"]']);}, title:"Downloads",
     desc:"Grab the full market-summary <b>report (PDF)</b>, the analyst-call <b>pitchdeck (PPT)</b>, and a video link where available."},
    // ---- cross-page: Performance ----
    {nav:"Performance", el:function(){return document.querySelector(".st-key-perf_group");}, title:"Commodity group",
     desc:"You’re on the <b>Performance Dashboard</b>. Same group tabs as Forecasting — HRC / HR Plate / Rebar / Structural."},
    {nav:"Performance", el:function(){return document.querySelector(".st-key-perf_loc_box");}, title:"Location", side:"left",
     desc:"Pick the grade/location whose forecast accuracy you want to score."},
    {nav:"Performance", el:function(){return document.querySelector(".st-key-perf_kpis");}, title:"Accuracy scorecard",
     desc:"Headline metrics: absolute accuracy (MAPA), directional hit-rate, and delta accuracy over all weeks."},
    {nav:"Performance", el:chart, title:"Accuracy charts & table",
     desc:"Actual vs forecast, then weekly delta, weekly absolute accuracy %, directional hits and delta accuracy — scroll for all of them, with a week-wise detail table at the bottom."},
    // ---- cross-page: Calculators (deep) ----
    {nav:"Scenario Simulation", el:function(){return q(['[data-testid="stTabs"] [role="tablist"]','[data-testid="stTabs"]']);}, title:"Three what-if tools",
     desc:"You’re in the <b>Calculators</b> — three tools live in these tabs. We’ll open each one. Everything recomputes live as you edit."},
    // Price Sensitivity
    {nav:"Scenario Simulation", tab:"Price Sensitivity", el:function(){return document.querySelector(".st-key-sens_prod");}, title:"Price Sensitivity → product",
     desc:"<b>Tool 1 — Price Sensitivity.</b> Pick the product to analyse (HRC / HR Plate / Rebar)."},
    {nav:"Scenario Simulation", tab:"Price Sensitivity", el:function(){return q(['[class*="st-key-sens_knobwrap"]']);}, title:"Driver shocks",
     desc:"Each card is a price driver — drag the slider or type a ±% shock (presets and a per-driver reset included). Switch to the <b>Table</b> mode to type exact values."},
    {nav:"Scenario Simulation", tab:"Price Sensitivity", el:chart, title:"Contribution graph",
     desc:"Shows how your shocks flow through to the predicted price move, and each driver’s contribution. A <b>Table of changes</b> tab sits beside it."},
    {nav:"Scenario Simulation", tab:"Price Sensitivity", el:function(){return q(['[class*="st-key-sens_cur_"]']);}, title:"Current price & reset", side:"left",
     desc:"Set the current price the shocks are applied to; the predicted-move cards sit right below, with a one-click ‘reset all shocks’."},
    // Landed Cost
    {nav:"Scenario Simulation", tab:"Landed Cost", el:function(){return q(['[class*="st-key-imp_results"]']);}, title:"Landed Cost → verdict",
     desc:"<b>Tool 2 — Landed Cost.</b> Imported (landed, duty-paid) price by origin vs the domestic benchmark — tells you whether importing is viable."},
    {nav:"Scenario Simulation", tab:"Landed Cost", el:function(){return q(['[class*="st-key-imp_btnrow"]']);}, title:"Scenario inputs",
     desc:"Edit the per-location inputs above (FOB, freight, BCD/cess/safeguard, port), then <b>Calculate</b> — or Reset to the admin defaults."},
    {nav:"Scenario Simulation", tab:"Landed Cost", el:function(){return q(['[class*="st-key-imp_fx"]']);}, title:"FX sensitivity",
     desc:"Landed cost recomputed across a range of USD→INR rates, so you can see how currency swings shift import parity."},
    // Cost Head
    {nav:"Scenario Simulation", tab:"Cost Head", el:function(){return q(['[class*="st-key-cost_prod_"]']);}, title:"Cost Head → route & product",
     desc:"<b>Tool 3 — Cost Head.</b> Pick a route (BF / IF) and product to build its ex-works production cost."},
    {nav:"Scenario Simulation", tab:"Cost Head", el:chart, title:"Cost build-up vs market",
     desc:"A stacked per-plant cost build-up (one segment per cost element) vs the market price, with the mill margin overlaid. Every input in the table below is editable."},
    // ---- cross-page: Methodology ----
    {nav:"Methodology", el:function(){return q(['.bm-meth-hero']);}, title:"Methodology",
     desc:"Last stop — <b>Methodology</b>. How the forecast is built: a hybrid ML approach on 15+ years of BigMint-assessed prices."},
    {nav:"Methodology", el:function(){return q(['.bm-stat-row']);}, title:"Track record",
     desc:"Headline accuracy: ~98% absolute, plus directional &amp; delta accuracy, and an IOSCO-audited method."},
    {nav:"Methodology", el:function(){return q(['.bm-fm']);}, title:"The pipeline",
     desc:"Market inputs (domestic &amp; global prices, supply/demand, cost &amp; macro) → the AI forecast engine → the price forecast."},
    {nav:"Methodology", el:function(){return q(['.bm-factor-grid']);}, title:"Key factors",
     desc:"The drivers the model weighs — cost, value-chain, global parity, supply/demand and macro."},
    {nav:"Methodology", el:function(){return q(['.bm-horizon']);}, title:"Horizon",
     desc:"This dashboard runs the weekly model: a 12-week rolling forecast refreshed every week."},
    {nav:"Home", title:"You’re all set 🎉",
     desc:"That’s the full tour. Click <b>🧭 Take a tour</b> (top-right, beside Log out) any time to replay it. Happy forecasting!"}
  ];

    // ---- controller ----
    var d = null, idx = 0, curPage = null;

    function seen(){ try { localStorage.setItem("bm_tour_seen","1"); } catch(e){} }

    function step(i, dir){
      dir = dir || 1;
      if (i < 0) return;
      if (i >= STEPS.length){ d.destroy(); return; }
      var s = STEPS[i];
      if (s.nav && !navBtn(s.nav)) return step(i + dir, dir);   // page not visible to this role -> skip
      idx = i;
      var navigating = s.nav && s.nav !== curPage;
      if (navigating){ navBtn(s.nav).click(); curPage = s.nav; }
      var t0 = +new Date(), tries = 0;
      (function poll(){
        // after a nav click, wait for the target page to actually become active before we read the
        // DOM — otherwise we'd grab the OLD page's element (the rerun swap is async).
        if (navigating && !isActive(navBtn(s.nav)) && (+new Date() - t0) < 5000){ setTimeout(poll, 120); return; }
        if (s.tab) ensureTab(s.tab);   // activate the right calculators tab so its content is visible
        var el = s.el ? s.el() : null;
        // require the element to be VISIBLE (not a hidden st.tabs panel), else keep waiting
        if (s.el && !visible(el) && tries++ < 45){ setTimeout(poll, 120); return; }
        show(s, el, i);
      })();
    }

    function show(s, el, i){
      var last = i === STEPS.length - 1;
      var back = i > 0 ? '<button type="button" class="bm-b" data-bmact="prev">&larr; Back</button>' : '';
      var nav = '<div class="bm-nav">' + back
              + '<button type="button" class="bm-b bm-next" data-bmact="next">'
              + (last ? "Finish ✓" : "Next →") + '</button></div>';
      var foot = '<div class="bm-foot"><div class="bm-meta">Step ' + (i+1) + ' of ' + STEPS.length + '</div>' + nav + '</div>';
      var pop = {
        title: s.title,
        description: s.desc + foot,
        popoverClass: "bm-pop", align: "start", showButtons: ["close"]   // × only; next/prev are our own
      };
      if (el) pop.side = s.side || "bottom";     // side only matters when there's an element to anchor to
      d.highlight({ element: (el || undefined), popover: pop });
    }

    function start(){
      if (!d){
        d = D({
          animate:true, stagePadding:6, stageRadius:10, allowClose:true, overlayColor:"rgba(3,20,46,.72)",
          onCloseClick: function(){ d.destroy(); },       // the × (only native button we keep)
          onDestroyed: function(){ seen(); d = null; }    // fresh instance on replay
        });
      }
      curPage = null; idx = 0; step(0, 1);
    }

    function launcher(){
      if (document.getElementById("bm-tour-launch")) return;
      var b = document.createElement("button");
      b.id = "bm-tour-launch"; b.type = "button"; b.textContent = "🧭 Take a tour";
      b.addEventListener("click", start);
      // Dock into the blue topbar's right slot (bar's right end, just left of Log out) so the blue
      // header runs right up to the button. A MutationObserver (below) re-adds it if a rerun wipes it.
      var host = document.querySelector(".bm-topbar-r") || document.body;
      host.appendChild(b);
    }

    // custom-button handlers via event delegation (robust to CSP / popover re-renders — no inline onclick)
    document.addEventListener("click", function(e){
      var b = e.target && e.target.closest ? e.target.closest("[data-bmact]") : null;
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      if (b.getAttribute("data-bmact") === "next") step(idx + 1, 1); else step(idx - 1, -1);
    }, true);

    launcher();
    // Streamlit reruns re-render the topbar and can drop the injected button. Re-add it whenever it
    // goes missing (append triggers another mutation, but launcher() no-ops once it exists -> no loop).
    if (!window.__bmTourObserver){
      window.__bmTourObserver = new MutationObserver(function(){
        if (!document.getElementById("bm-tour-launch")) launcher();
      });
      window.__bmTourObserver.observe(document.body, {childList:true, subtree:true});
    }
    if (AUTO){ try { if (!localStorage.getItem("bm_tour_seen")) setTimeout(start, 650); } catch(e){} }
  }

  // ---- outer bootstrap (iframe realm): load driver.js into the PARENT, then inject the
  // controller so it runs in the parent realm. Idempotent: only the first iframe does this.
  if (P.__bmTourBooted) return;
  P.__bmTourBooted = true;
  function inject(){
    var s = pd.createElement("script");
    s.textContent = "(" + CONTROLLER.toString() + ")();";
    pd.body.appendChild(s);
  }
  if (P.driver && P.driver.js){ inject(); }
  else {
    var css = pd.createElement("link"); css.rel = "stylesheet"; css.href = "__CSS__"; pd.head.appendChild(css);
    var js = pd.createElement("script"); js.src = "__JS__"; js.onload = inject; pd.head.appendChild(js);
  }
})();
</script></body></html>"""


TOUR_ROLES = {"analyst", "adani"}   # roles that get the guided walkthrough


def render(user):
    """Render the guided-walkthrough bootstrap iframe (no-op for roles not in TOUR_ROLES).

    Cheap to call on every run: the iframe only injects driver.js + the controller into the
    parent document once (guarded by `__bmTourBooted` / `__bmTourInit`), after which the whole
    tour lives in the parent window and is independent of this iframe's lifecycle.
    """
    if (user.get("role") or "").strip().lower() not in TOUR_ROLES:
        return
    doc = TOUR_JS.replace("__AUTO__", "true").replace("__CSS__", DRIVER_CSS).replace("__JS__", DRIVER_JS)
    token = st.session_state.setdefault("_chart_doc_token", uuid.uuid4().hex[:10])
    doc_dir = Path(tempfile.gettempdir()) / "bm_charts"
    doc_dir.mkdir(exist_ok=True)
    doc_path = doc_dir / f"{token}_tour.html"
    doc_path.write_text(doc, encoding="utf-8")
    # hidden container (theme.py `.st-key-bm_tour_mount` display:none) — off the flex flow so it
    # adds no gap; the iframe still loads + runs its JS (same trick as the cookie manager).
    with st.container(key="bm_tour_mount"):
        st.iframe(doc_path, height=1)   # min positive height (1.59 rejects 0); container is display:none anyway
