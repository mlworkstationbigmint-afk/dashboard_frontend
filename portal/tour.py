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
      + ".driver-popover.bm-pop{border-radius:14px;box-shadow:0 18px 48px rgba(2,18,43,.34);max-width:360px}"
      + ".driver-popover.bm-pop .driver-popover-title{font-size:16px;color:#024CA1;font-weight:800;line-height:1.25}"
      + ".driver-popover.bm-pop .driver-popover-description{font-size:13.5px;color:#1A1A1A;line-height:1.5}"
      + ".driver-popover.bm-pop .driver-popover-close-btn{color:#94a3b8}"
      // custom nav buttons (driver.js renders no next/prev in single-highlight mode, so we draw our own)
      + ".driver-popover.bm-pop .bm-nav{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}"
      + ".driver-popover.bm-pop .bm-b{background:#eef2f7;color:#334155;border:1px solid #cbd5e1;border-radius:8px;"
      + "font-weight:700;padding:6px 14px;cursor:pointer;font-size:13px;font-family:inherit}"
      + ".driver-popover.bm-pop .bm-b:hover{background:#fff;color:#024CA1}"
      + ".driver-popover.bm-pop .bm-next{background:#EE4E24;color:#fff;border-color:#EE4E24}"
      + ".driver-popover.bm-pop .bm-next:hover{background:#fff;color:#EE4E24}"
      + ".driver-popover.bm-pop .bm-meta{margin-top:10px;font-size:11px;color:#94a3b8}"
      + ".driver-overlay,svg.driver-overlay{z-index:2147483000 !important}"
      + ".driver-popover{z-index:2147483600 !important}"   // MUST sit above the overlay or clicks are swallowed
      + "#bm-tour-launch{position:fixed;right:18px;bottom:18px;z-index:2147482000;background:#024CA1;color:#fff;"
      + "border:none;border-radius:999px;padding:9px 16px;font-size:13px;font-weight:700;cursor:pointer;"
      + "box-shadow:0 8px 22px rgba(2,18,43,.30);font-family:inherit}"
      + "#bm-tour-launch:hover{background:#EE4E24}";
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

    // ---- steps (nav = visible nav-button text the step lives on) ----
    var STEPS = [
    {nav:"Home", title:"Welcome 👋",
     desc:"This is the BigMint · AI Labs steel price-forecasting portal. Here’s a quick tour of what every part does. Use <b>Next</b> to move on, or close (×) to skip — you can replay it anytime from the <b>Take a tour</b> button, bottom-right."},
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
    // ---- cross-page ----
    {nav:"Forecasting", el:main, title:"Price Forecasting page",
     desc:"Pick a product group in the tabs at the top (HRC / HR Plate / Rebar / Structural). Below are the view controls, the chart, the price cards and a forecast rationale."},
    {nav:"Forecasting", el:function(){return document.querySelector(".st-key-fc_view_box");}, title:"Graphical / Tabular",
     desc:"Slide this switch to flip between the chart and the week-by-week Actual-vs-Forecast table."},
    {nav:"Forecasting", el:function(){return document.querySelector(".st-key-fc_loc_box");}, title:"Location", side:"left",
     desc:"Choose the delivery location for the selected product group."},
    {nav:"Forecasting", el:chart, title:"Forecast chart",
     desc:"Light-blue = actual spot, red dashed = the 12-week Ensemble forecast. Hover any point for values, and use the zoom buttons just above the plot (1W…ALL)."},
    {nav:"Analyst calls", el:main, title:"Analyst Calls page",
     desc:"Each card is a monthly call — headline summary, a sectioned breakdown of price drivers, and live <b>Download PDF / PPT</b> buttons for the deck."},
    {nav:"Performance", el:main, title:"Performance Dashboard page",
     desc:"MAPA, directional hit-rate and average delta up top; then actual-vs-forecast, weekly delta bars, an accuracy-% line and a week-wise table."},
    {nav:"Scenario Simulation", el:main, title:"Calculators page",
     desc:"Three tabs of interactive what-if tools — edit the inputs and the outputs recompute live."},
    {nav:"Methodology", el:main, title:"Methodology page",
     desc:"The end-to-end pipeline: data → signals → ML + sentiment → ensemble → 12-week forecast → accuracy, plus the key price factors and governance."},
    {nav:"Home", title:"You’re all set 🎉",
     desc:"That’s the tour. Click <b>Take a tour</b> (bottom-right) any time to see it again. Happy forecasting!"}
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
        var el = s.el ? s.el() : null;
        if (s.el && !el && tries++ < 45){ setTimeout(poll, 120); return; }   // then wait for the step element
        show(s, el, i);
      })();
    }

    function show(s, el, i){
      var last = i === STEPS.length - 1;
      var back = i > 0 ? '<button type="button" class="bm-b" data-bmact="prev">&larr; Back</button>' : '';
      var nav = '<div class="bm-nav">' + back
              + '<button type="button" class="bm-b bm-next" data-bmact="next">'
              + (last ? "Finish ✓" : "Next →") + '</button></div>';
      var pop = {
        title: s.title,
        description: s.desc + '<div class="bm-meta">Step ' + (i+1) + ' of ' + STEPS.length + '</div>' + nav,
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
      document.body.appendChild(b);
    }

    // custom-button handlers via event delegation (robust to CSP / popover re-renders — no inline onclick)
    document.addEventListener("click", function(e){
      var b = e.target && e.target.closest ? e.target.closest("[data-bmact]") : null;
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      if (b.getAttribute("data-bmact") === "next") step(idx + 1, 1); else step(idx - 1, -1);
    }, true);

    launcher();
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


def render(user):
    """Render the analyst walkthrough bootstrap iframe (no-op for other roles).

    Cheap to call on every run: the iframe only injects driver.js + the controller into the
    parent document once (guarded by `__bmTourBooted` / `__bmTourInit`), after which the whole
    tour lives in the parent window and is independent of this iframe's lifecycle.
    """
    if (user.get("role") or "").strip().lower() != "analyst":
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
