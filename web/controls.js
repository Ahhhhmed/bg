/**
 * The map's controls (C-10), in four places with one job each, plus the
 * legend bar (they replaced the one long sidebar of C-09 / C-17):
 *
 *   brand card (top left)     the mark and name (a link to the map), the
 *                             language and a menu: the other cities
 *   "Einfärben nach"          one lens at a time from LENS_GROUPS (web/layers.js):
 *                             the 9 building modes and the 7 area themes; an
 *                             area lens colours the buildings by the area they
 *                             stand on and tints the ground (switchable)
 *   search profile            chips under the brand card and a panel on the
 *                             left (map page): criteria from any lens or place
 *                             kind (web/profile.js), each a filter
 *                             (the rest fade or hide) or "mark only" (an
 *                             outline), with the homes left after each
 *   map menu (top right)      place layers, base map, buildings, 2D / 3D
 *   legend bar (bottom left)  a pill with the lens's colours and name (like
 *                             the attribution pin); opens to its classes and
 *                             the C-08 keys (no counts: shares of what's in view
 *                             changed with every pan, owner 2026-10-24)
 *
 * State, strongest first: the URL, then the browser's last choice
 * (localStorage: lens, layers, places, area tint), then the defaults; every
 * change is written back, so a copied link shows the same map.
 *   ?color=   the lens: a building mode (`noise_road_n`) or an area lens
 *             (`hazard`); absent = year built
 *   ?area=0   an area lens without the ground tint
 *   ?layers=  letters of the visible groups (LAYER_GROUPS[].key; all = absent)
 *   ?places=  letters of the visible place layers (absent = none)
 *   map page, URL only (a link shows what its sender saw):
 *   ?view=3d ?f=<criteria> (web/profile.js) ?hide=1
 * Old links: ?ground=<theme> without ?color= opens that area lens; next to a
 * ?color= it is dropped (one colouring at a time, C-10); the filters of 043
 * (?housing ?years ?noise ?walk ?marks) become the same criteria.
 *
 * The map page's brand card also holds the address search (web/search.js, setSearch()).
 *
 * Usage: initControls(map, { page: "map" | "compare", menuMap })
 *   menuMap: the map whose top-right corner holds the map menu (default: map)
 * Returns { state, apply, select, showPlace, setView }.
 */
function initControls(map, opts) {
  opts = opts || {};
  const full = (opts.page || "map") === "map";
  const STORE = { layers: "bg-layers-v3", color: "bg-color", places: "bg-places", area: "bg-area",
                  legend: "bg-legend-min", panel: "bg-profile-open" };
  const load = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const save = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } };
  const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const params = new URLSearchParams(location.search);
  const pick = (name, storeKey) => params.has(name) ? params.get(name) : load(storeKey);
  const allLayers = LAYER_GROUPS.map(g => g.key).join("");
  const narrow = () => window.innerWidth < 700;
  const PANEL_W = 340, GAP = 16;

  let lens = params.get("color");
  if (!colorMode(lens)) {
    const g = params.get("ground");
    lens = g && colorMode(g) ? g : load(STORE.color);
  }
  if (!colorMode(lens)) lens = DEFAULT_LENS;
  const state = {
    layers: new Set((pick("layers", STORE.layers) ?? allLayers).split("").filter(k => LAYER_GROUPS.some(g => g.key === k))),
    lens,
    area: (pick("area", STORE.area) ?? "1") !== "0",
    places: new Set((pick("places", STORE.places) ?? "").split("").filter(k => PLACE_LAYERS.some(p => p.key === k))),
    view: params.get("view") === "3d" ? "3d" : "2d",
    // the search profile: [{ id, mark, lo, hi, miss, cls }], in the order added
    crits: full ? (params.has("f") ? critsFromParam(params.get("f")) : fromOldParams(params)) : [],
    hide: params.get("hide") === "1",
    selected: null,   // egid of the building whose card is open (ringed)
  };
  const lensSel = () => colorMode(state.lens);
  const lensMode = () => lensSel().mode;
  const buildingsGroup = LAYER_GROUPS.find(g => g.tier === "buildings");

  function writeState() {
    const layers = LAYER_GROUPS.map(g => g.key).filter(k => state.layers.has(k)).join("");
    const places = PLACE_LAYERS.map(p => p.key).filter(k => state.places.has(k)).join("");
    save(STORE.layers, layers); save(STORE.color, state.lens); save(STORE.places, places); save(STORE.area, state.area ? "1" : "0");
    const url = new URL(location.href);
    const set = (name, value, dflt) => value === dflt ? url.searchParams.delete(name) : url.searchParams.set(name, value);
    set("layers", layers, allLayers);
    set("color", state.lens, DEFAULT_LENS);
    url.searchParams.delete("ground");
    set("area", state.area ? "1" : "0", "1");
    set("places", places, "");
    if (full) {
      set("view", state.view, "2d");
      set("f", critsToParam(state.crits), "");
      for (const old of ["housing", "years", "noise", "walk", "marks"]) url.searchParams.delete(old);   // now in ?f=
      set("hide", state.hide ? "1" : "", "");
    }
    // ?f= readable in a copied link: its , : ~ unescaped (no other parameter has them)
    url.search = url.search.replace(/%2C/gi, ",").replace(/%3A/gi, ":").replace(/%7E/gi, "~");
    history.replaceState(null, "", url);
  }

  // A layer's own default visibility (the 3D buildings start hidden):
  // switching its group back on restores that, not "visible".
  const defaults = {};
  function apply() {
    const m = lensMode();
    for (const layer of map.getStyle().layers) {
      const md = layer.metadata || {};
      // the ground tint of the area lens, if it's on; place icons: each its own switch
      if (md["bg:ground"]) { map.setLayoutProperty(layer.id, "visibility", m.area && state.area && md["bg:ground"] === m.id ? "visible" : "none"); continue; }
      if (md["bg:place"]) { map.setLayoutProperty(layer.id, "visibility", state.places.has(md["bg:place"]) ? "visible" : "none"); continue; }
      const g = md["bg:group"];
      if (!g) continue;
      if (!(layer.id in defaults)) defaults[layer.id] = (layer.layout && layer.layout.visibility) || "visible";
      const grp = LAYER_GROUPS.find(x => x.id === g);
      if (!grp) continue;
      map.setLayoutProperty(layer.id, "visibility", state.layers.has(grp.key) ? defaults[layer.id] : "none");
    }
    applyBuildingColorMode(map, state.lens, full ? critsExpr(state.crits.filter(c => !c.mark)) : null, full && state.hide,
      full ? critsExpr(state.crits.filter(c => c.mark)) : null);   // web/layers.js, web/profile.js
    if (full) {
      const on = state.layers.has(buildingsGroup.key);
      applyBuildingView(map, state.view, on);
      if (map.getLayer("buildings-mark")) map.setLayoutProperty("buildings-mark", "visibility", on ? "visible" : "none");
      if (map.getLayer("buildings-selected")) {
        map.setFilter("buildings-selected", ["==", ["to-string", ["get", "egid"]], state.selected != null ? String(state.selected) : "-"]);
      }
    }
    // the place names are HTML markers (web/area.js), not style layers
    document.body.classList.toggle("bg-hide-area-labels", !state.layers.has("g"));
  }
  // bg:profile: the open building card redraws its "Passt zum Suchprofil" strip (map.js)
  // isStyleLoaded() is false while tiles load (e.g. right after a pan): apply once the map is idle then
  const update = () => { writeState(); if (map.isStyleLoaded()) apply(); else map.once("idle", apply); recount(); renderAll(); window.dispatchEvent(new Event("bg:profile")); };

  // --- the search profile's counts (web/profile.js): over every home, from
  // /data/profile_table.json, loaded when the first criterion is there ---
  let counts = null, tableFailed = false;
  function recount() {
    counts = full && state.crits.length && PROFILE_TABLE ? profileCounts(state.crits) : null;
    if (full && state.crits.length && !PROFILE_TABLE && !tableFailed) {
      loadProfileTable().then(() => { recount(); renderAll(); }).catch(() => { tableFailed = true; renderAll(); });
    }
  }
  const countText = n => (counts ? fmtCount(n) : tableFailed ? "?" : "…");

  // --- popovers: one open at a time; a bottom sheet on a phone ---
  let pop = null;
  function closePop() {
    if (!pop) return;
    pop.el.remove();
    document.body.classList.remove("bg-sheet-scrim");
    if (pop.anchor) pop.anchor.setAttribute("aria-expanded", "false");
    const a = pop.anchor; pop = null;
    if (a && document.activeElement === document.body) a.focus();
  }
  function openPop(id, anchor, cls, label, fill) {
    if (pop && pop.id === id) { closePop(); return; }
    closePop();
    const el = document.createElement("div");
    el.className = `bg-pop ${cls}`;
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", label);
    el.addEventListener("click", ev => ev.stopPropagation());
    document.body.appendChild(el);
    pop = { id, el, anchor, fill };
    anchor.setAttribute("aria-expanded", "true");
    fill(el);
    placePop();
    const first = el.querySelector("button, a, input, select");
    if (first) first.focus({ preventScroll: true });
  }
  function placePop() {
    if (!pop) return;
    const el = pop.el;
    el.classList.toggle("bg-pop-sheet", narrow());
    // phones: a bottom sheet with a grab handle over a dimmed map
    document.body.classList.toggle("bg-sheet-scrim", narrow());
    if (narrow() && !el.querySelector(":scope > .bg-grab")) attachSheetHandle(el, closePop);
    if (narrow()) { el.style.left = el.style.top = el.style.right = el.style.maxHeight = ""; return; }
    // on screen, 8 px from every edge: left-aligned to the button, else
    // right-aligned, else as far left as it fits; below the button, else above it
    // (the "+ Kriterium" button sits at the foot of the panel), else wherever it fits
    const W = window.innerWidth, H = window.innerHeight, m = 8, r = pop.anchor.getBoundingClientRect();
    el.style.right = ""; el.style.maxHeight = `${H - 2 * m}px`;
    const w = el.offsetWidth;
    el.style.left = `${Math.max(m, r.left + w <= W - m ? r.left : Math.min(r.right, W - m) - w)}px`;
    const h = el.offsetHeight;
    const below = H - m - (r.bottom + 8), above = r.top - 8 - m;
    if (h <= below || below >= above) { el.style.top = `${r.bottom + 8}px`; el.style.maxHeight = `${Math.max(120, below)}px`; }
    else { el.style.maxHeight = `${above}px`; el.style.top = `${Math.max(m, r.top - 8 - el.offsetHeight)}px`; }
  }
  const refillPop = () => { if (pop) { const tall = pop.el.classList.contains("bg-sheet-tall"); pop.fill(pop.el); pop.el.classList.toggle("bg-sheet-tall", tall); placePop(); } };
  document.addEventListener("click", closePop);
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && pop) { ev.stopPropagation(); closePop(); } }, true);
  window.addEventListener("resize", placePop);

  // a lens's class colours as one bar (the catalogue and the lens button)
  function lensBar(id) {
    const cs = colorModeClasses(id).map(c => c.color);
    return `linear-gradient(90deg, ${cs.map((c, i) => `${c} ${(i * 100 / cs.length).toFixed(2)}% ${((i + 1) * 100 / cs.length).toFixed(2)}%`).join(", ")})`;
  }
  const lensTitle = id => {
    const { mode: m, variant: v } = colorMode(id);
    return v ? `${tr(m.label)} · ${tr(v.label)}` : tr(m.label);
  };

  // --- brand card, lens button, profile chips (top left) ---
  let searchEl = null;   // the address search (web/search.js, map page), via setSearch()
  const top = document.createElement("div");
  top.className = "bc-top";
  document.body.appendChild(top);

  function renderTop() {
    const chips = full ? state.crits.map((c, i) => ({ k: i, text: critText(c), mark: c.mark })) : [];
    const profileOpen = document.body.classList.contains("bc-panel-open");
    top.innerHTML = `
      <div class="bc-row">
        <div class="bc-brand bg-card-ui">
          <a class="bc-home" href="${CITY.home || "/"}" title="${t("ctl.home")}"><span class="bg-mark"></span><span class="bc-name">${esc(tr(CITY.name)).toLowerCase()}</span></a>
          ${searchEl ? `<span class="bc-search-slot"></span>` : ""}
          <span class="bc-lang"></span>
          <button type="button" class="bc-mapmenu-btn" aria-expanded="false" aria-haspopup="dialog" aria-label="${t("ctl.mapMenuAria")}"><svg class="bc-icon" width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M10 3l8 4-8 4-8-4z"/><path d="M2 10.5l8 4 8-4"/><path d="M2 14l8 4 8-4"/></g></svg><span>${t("ctl.mapMenu")}</span></button>
        </div>
        <button type="button" class="bc-lens bg-card-ui" aria-expanded="false" aria-haspopup="dialog">
          <span class="bc-lens-bar" style="background:${lensBar(state.lens)}"></span>
          <span class="bc-lens-text"><span class="bc-lens-k">${t("ctl.colorBy")}</span><span class="bc-lens-v">${esc(lensTitle(state.lens))}</span></span>
          <span class="bc-caret" aria-hidden="true"></span>
        </button>
      </div>
      ${full ? `
      <div class="bc-chips">
        <button type="button" class="bc-profile-btn${profileOpen ? " on" : ""}" aria-expanded="${profileOpen}" aria-controls="bc-panel">
          <svg class="bc-icon" width="15" height="15" viewBox="0 0 15 15" aria-hidden="true"><g stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"><path d="M2 4h11M2 11h11"/><circle cx="5" cy="4" r="1.8" fill="var(--bg-card-solid)"/><circle cx="10" cy="11" r="1.8" fill="var(--bg-card-solid)"/></g></svg>${t("ctl.profile")}${chips.length ? ` · ${chips.length}` : ""}
        </button>
        ${chips.length ? `<span class="bc-count" data-chip-count><b>${countText(counts && counts.match)}</b> ${t("pf.matchShort")}</span>` : ""}
        ${chips.map(c => `
          <span class="bc-chip">${c.mark ? `<i class="bc-mark-key" style="border-color:${BUILDING_MARK_COLOR}" title="${t("pf.markOnly")}"></i>` : ""}${esc(c.text)}<button type="button" class="bg-x small" data-drop="${c.k}" aria-label="${esc(c.text)}: ${t("ctl.remove")}">×</button></span>`).join("")}
      </div>` : ""}`;
    top.querySelector(".bc-lang").appendChild(langSelect());   // web/i18n.js
    // the search field (web/search.js) is kept across redraws: what's typed and the focus stay
    if (searchEl) {
      const had = searchEl.contains(document.activeElement);
      top.querySelector(".bc-search-slot").replaceWith(searchEl);
      if (had) searchEl.querySelector("input").focus({ preventScroll: true });
    }
    const mapBtn = top.querySelector(".bc-mapmenu-btn");
    mapBtn.addEventListener("click", ev => { ev.stopPropagation(); openPop("mapmenu", mapBtn, "bc-mapmenu-pop", t("ctl.mapMenuAria"), fillMapMenu); });
    const lensBtn = top.querySelector(".bc-lens");
    lensBtn.addEventListener("click", ev => { ev.stopPropagation(); openPop("lens", lensBtn, "bc-lens-pop", t("ctl.colorBy"), fillLens); });
    if (full) {
      top.querySelector(".bc-profile-btn").addEventListener("click", ev => { ev.stopPropagation(); setPanel(!document.body.classList.contains("bc-panel-open"), true); });
      top.querySelectorAll("[data-drop]").forEach(b => b.addEventListener("click", ev => {
        ev.stopPropagation();
        state.crits.splice(Number(b.dataset.drop), 1);
        update();
      }));
    }
    // keep the open popover anchored to the redrawn button
    if (pop && pop.id === "lens") { pop.anchor = top.querySelector(".bc-lens"); pop.anchor.setAttribute("aria-expanded", "true"); }
    if (pop && pop.id === "mapmenu") { pop.anchor = top.querySelector(".bc-mapmenu-btn"); pop.anchor.setAttribute("aria-expanded", "true"); }
  }

  function fillMenu(el) {
    // the other cities (web/city.js CITY.others: root-relative links, a line on what each is)
    const links = (CITY.others || []).map(o => [o.href, tr(o.name), tr(o.sub)]);
    el.innerHTML = `
      <ul class="bc-menu-list">${links.map(([href, name, sub]) => `
        <li><a href="${href}"><span class="bc-menu-name">${esc(name)}</span><span class="bc-menu-sub">${esc(sub)}</span></a></li>`).join("")}
      </ul>`;
  }

  function fillLens(el) {
    const cur = lensSel();
    const item = id => {
      const m = LENS_MODES.find(x => x.id === id);
      const on = m === cur.mode;
      const firstId = defaultColorModeId(m);
      let variants = "";
      if (on && m.variants && m.variants.length > 4) {
        variants = `<label class="bc-variant-select">${t("ctl.walkTo")}
          <select data-variant>${m.variants.map(v => {
            const none = lensCoverage(colorModeId(m, v)).state === "none";   // no such places here
            return `<option value="${colorModeId(m, v)}" ${v === cur.variant ? "selected" : ""}${none ? " disabled" : ""}>${esc(tr(v.label))}${none ? ` – ${t("cov.noData")}` : ""}</option>`;
          }).join("")}</select></label>`;
      } else if (on && m.variants) {
        variants = `<span class="bc-variants" role="radiogroup" aria-label="${esc(tr(m.label))}">${m.variants.map(v => `
          <button type="button" role="radio" aria-checked="${v === cur.variant}" class="bc-variant${v === cur.variant ? " on" : ""}" data-lens="${colorModeId(m, v)}">${esc(tr(v.label))}</button>`).join("")}</span>`;
      }
      // no data in this city: greyed, not pickable (the default lens stays, with its note in the legend)
      const cov = coverageOf("lens", m.id), none = cov.state === "none" && !on;
      const tag = cov.state === "none" ? `<span class="bc-cov-tag" title="${esc(covText("cov.noneHere"))}">${t("cov.noData")}</span>`
        : cov.state === "partial" ? `<span class="bc-cov-tag" title="${esc(covText("cov.partial", cov))}">${Math.round(cov.share * 100)} %</span>` : "";
      return `
        <div class="bc-lens-item${on ? " on" : ""}${none ? " bc-lens-none" : ""}">
          <button type="button" class="bc-lens-pick" data-lens="${on ? state.lens : firstId}" aria-pressed="${on}"${none ? ` disabled aria-disabled="true"` : ""}>
            <span class="bc-lens-name">${esc(tr(m.label))}${m.area ? `<span class="bc-area-tag">${t("ctl.area")}</span>` : ""}${tag}</span>
            <span class="bc-lens-swatch" style="background:${lensBar(on ? state.lens : firstId)}"></span>
          </button>
          ${variants}
        </div>`;
    };
    el.innerHTML = `
      <div class="bc-pop-head">
        <span class="bc-pop-title">${t("ctl.colorBy")}</span>
        <span class="bc-pop-sub">${t("ctl.lensHint")}</span>
        <button type="button" class="bg-x" data-close aria-label="${t("ctl.close")}">×</button>
      </div>
      <div class="bc-lens-grid">${LENS_GROUPS.map(g => `
        <div class="bc-lens-group">
          <div class="bc-group-title">${esc(tr(g.label))}</div>
          ${g.modes.map(item).join("")}
        </div>`).join("")}
      </div>
      <label class="bc-check"><input type="checkbox" data-area ${state.area ? "checked" : ""}>${t("ctl.areaTint")}</label>`;
    el.querySelector("[data-close]").addEventListener("click", closePop);
    el.querySelectorAll("[data-lens]").forEach(b => b.addEventListener("click", () => { state.lens = b.dataset.lens; update(); refillPop(); }));
    const vs = el.querySelector("[data-variant]");
    if (vs) vs.addEventListener("change", () => { state.lens = vs.value; update(); refillPop(); });
    el.querySelector("[data-area]").addEventListener("change", e => { state.area = e.target.checked; update(); });
  }

  // --- map menu (top right): a MapLibre control, so it stacks with the zoom buttons ---
  const iconCache = {};
  const icon = id => (iconCache[id] = iconCache[id] || placeIconUrl(id));
  const swatch = {
    roads: `background: ${BASE.roadFill}; border: 2px solid ${BASE.roadCasing}; height: 8px`,
    water: `background: ${BASE.water}; border: 1px solid ${BASE.waterLine}`,
    transit: `background: repeating-linear-gradient(90deg, ${BASE.track} 0 4px, ${BASE.roadFill} 4px 7px); height: 4px; border: 1px solid ${BASE.track}`,
    forest: `background: ${BASE.forest}`,
    parks: `background: ${BASE.park}; border: 1px solid ${BASE.parkLine}`,
    borders: `background: transparent; border-top: 2px solid ${MUNICIPALITY_LINE_COLOR}; border-radius: 0; height: 0; margin-top: 2px`,
    relief: `background: linear-gradient(135deg, ${BASE.land}, #b9aea3)`,
    parcels: `background: transparent; border: 1.5px solid ${BASE.parcel}; border-radius: 2px`,
    buildings: `background: ${YEAR_GROUPS[1].color}; border: 1px solid ${YEAR_GROUPS[1].outline}`,
  };
  const groupKeys = { borders: AREA_LEGEND_KEYS };   // web/area.js
  const keyRows = keys => !keys || !keys.length ? "" : `
    <span class="bc-keys">${keys.map(k => `<span class="bc-key"><span class="bc-key-swatch" style="${k.swatchStyle}"></span>${esc(tr(k.label))}</span>`).join("")}</span>`;

  // the site menu (the other cities): a MapLibre control at the
  // top right, above the zoom buttons; on the comparison page on the raster
  // map's corner (opts.menuMap), the visible one there
  class MenuControl {
    onAdd() {
      const el = this.el = document.createElement("div");
      el.className = "maplibregl-ctrl bc-sitemenu";
      this.render();
      return el;
    }
    render() {
      this.el.innerHTML = `
        <button type="button" class="bc-menu-btn bg-card-ui" aria-expanded="false" aria-haspopup="dialog">
          <svg class="bc-icon" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><g stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 5h12M3 9h12M3 13h12"/></g></svg><span class="bc-menu-text">${t("ctl.menu")}</span>
        </button>`;
      const b = this.el.querySelector("button");
      b.addEventListener("click", ev => { ev.stopPropagation(); openPop("menu", b, "bc-menu-pop", t("ctl.menu"), fillMenu); });
      if (pop && pop.id === "menu") { pop.anchor = b; b.setAttribute("aria-expanded", "true"); }
    }
    onRemove() { this.el.remove(); }
  }
  const siteMenu = new MenuControl();
  (opts.menuMap || map).addControl(siteMenu, "top-right");
  siteMenu.el.parentElement.prepend(siteMenu.el);

  function fillMapMenu(el) {
    const zoomText = pl => `${t("ctl.fromZoom")} ${pl.kinds.some(k => k.hub) && pl.hubMinzoom ? `${pl.hubMinzoom} / ${pl.minzoom}` : pl.minzoom}`;
    el.innerHTML = `
      <div class="bc-pop-head">
        <span class="bc-pop-title">${t("sb.places")}</span><span class="bc-pop-sub">${t("ctl.placesAny")}</span>
        <button type="button" class="bg-x" data-close aria-label="${t("ctl.close")}">×</button>
      </div>
      <div class="bc-place-grid">${PLACE_LAYERS.map(pl => {
        const on = state.places.has(pl.key), none = coverageOf("place", pl.id).state === "none";
        return `
        <button type="button" class="bc-place${on ? " on" : ""}${none ? " bc-lens-none" : ""}" data-place="${pl.key}" aria-pressed="${on}"${none ? " disabled" : ""}>
          <img src="${icon(`place-${pl.kinds[0].v}${pl.kinds[0].hub ? "-hub" : ""}`)}" alt="">
          <span><span class="bc-place-name">${esc(tr(pl.label))}</span><span class="bc-place-sub">${none ? esc(covText("cov.noneHere")) : zoomText(pl)}</span></span>
        </button>`;
      }).join("")}
      </div>
      <div class="bc-pop-head sub"><span class="bc-pop-title">${t("sb.base")}</span><span class="bc-pop-sub">${t("ctl.baseQuiet")}</span></div>
      <div class="bc-base-list">${LAYER_GROUPS.map(g => `
        <label class="bc-check"><input type="checkbox" data-key="${g.key}" ${state.layers.has(g.key) ? "checked" : ""}>
          <span class="bc-swatch" style="${swatch[g.id] || ""}"></span><span>${esc(tr(g.label))}${keyRows(g.keys || groupKeys[g.id])}</span></label>`).join("")}
      </div>
      ${full ? `
      <div class="bc-view">
        <span>${t("sb.view")}</span>
        <span class="bc-seg" role="radiogroup" aria-label="${t("sb.view")}">
          ${["2d", "3d"].map(v => `<button type="button" role="radio" aria-checked="${state.view === v}" class="${state.view === v ? "on" : ""}" data-view="${v}">${v.toUpperCase()}</button>`).join("")}
        </span>
      </div>` : ""}`;
    el.querySelector("[data-close]").addEventListener("click", closePop);
    el.querySelectorAll("[data-place]").forEach(b => b.addEventListener("click", () => {
      const k = b.dataset.place;
      if (state.places.has(k)) state.places.delete(k); else state.places.add(k);
      update(); refillPop();
    }));
    el.querySelectorAll("input[data-key]").forEach(box => box.addEventListener("change", () => {
      if (box.checked) state.layers.add(box.dataset.key); else state.layers.delete(box.dataset.key);
      update();
    }));
    el.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => setView(b.dataset.view)));
  }

  function setView(v) {
    if (!full || state.view === v) return;
    state.view = v;
    // tilt for 3D, flat for 2D
    const d = ms => (matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : ms);
    map.easeTo(v === "3d" ? { pitch: 55, bearing: -20, duration: d(1000) } : { pitch: 0, bearing: 0, duration: d(800) });
    update(); refillPop();
  }

  // --- the search profile panel (map page, left) ---
  // the homes that match (a funnel: what each criterion leaves), the criteria
  // as cards (numbers: a range over the distribution of all homes; classes:
  // chips to strike), each "filter" or "mark only", and "+ Kriterium"
  const panel = full ? document.createElement("aside") : null;
  if (panel) {
    panel.className = "bc-panel bg-card-ui";
    panel.id = "bc-panel";
    document.body.appendChild(panel);
  }
  const RANGE_W = 100;   // the range track in % (handles at lo / hi)
  const pctOf = (s, v) => ((v - s.min) / (s.max - s.min) * RANGE_W).toFixed(2);
  function critHtml(c, i) {
    const s = critSpec(c.id);
    const left = counts ? counts.left[i] : null;
    const leftText = `<span class="bc-left" data-left="${i}">${countText(left)}</span> ${c.mark ? t("pf.ofMatching") : t("pf.left")}`;
    const head = `
      <div class="bc-crit-head">
        <span class="bc-crit-name">${c.mark ? `<i class="bc-mark-key" style="border-color:${BUILDING_MARK_COLOR}" aria-hidden="true"></i>` : ""}${esc(s.kind === "extra" ? tr(s.label) : tr(s.short))}</span>
        <span class="bc-crit-left">${leftText}</span>
        <button type="button" class="bg-x small" data-remove="${i}" aria-label="${esc(critText(c))}: ${t("ctl.remove")}">×</button>
      </div>`;
    let body = "", miss = "";
    if (s.kind === "range") {
      const h = PROFILE_TABLE ? profileHistogram(c) : null;
      const max = h ? Math.max(...h.bins, 1) : 1;
      const bars = h ? h.bins.map((n, b) => {
        const a = s.min + b * h.w, z = a + h.w;
        const inRange = (c.lo <= s.min || z > c.lo) && (c.hi >= s.max || a < c.hi + (s.int ? 1 : 0));
        return `<i data-b="${b}" class="${inRange ? "in" : ""}" style="height:${Math.max(2, Math.round(30 * n / max))}px"></i>`;
      }).join("") : "";
      miss = s.missingIsLowest ? "" : `
        <label class="bc-check bc-small"><input type="checkbox" data-miss="${i}" ${c.miss ? "checked" : ""}>${t("pf.missing")}${h ? ` (${fmtCount(h.missing)})` : ""}</label>`;
      body = `
        <div class="bc-hist" aria-hidden="true">${bars}</div>
        <div class="bc-range" data-range="${i}" style="--lo:${pctOf(s, c.lo)}%;--hi:${pctOf(s, c.hi)}%">
          <span class="bc-range-fill"></span>
          <input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${c.lo}" data-lo="${i}" aria-label="${esc(tr(s.short))}: ${t("pf.from")}">
          <input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${c.hi}" data-hi="${i}" aria-label="${esc(tr(s.short))}: ${t("pf.to")}">
        </div>
        <div class="bc-range-labels"><span>${s.min}${s.unit}</span><b data-val="${i}">${esc(rangeText(c, s))}</b><span>${s.max}${s.unit}+</span></div>`;
    } else if (s.kind === "class") {
      const keys = [...s.classes.map((k, j) => ({ j, label: tr(k.label), color: k.color })),
        { j: "n", label: tr(s.mode.missing || { de: "keine Angabe", en: "no data" }), color: NO_YEAR_COLOR }];
      body = `<div class="bc-class-chips">${keys.map(k => `
        <button type="button" class="bc-cls${c.cls.has(k.j) ? " on" : ""}" data-cls="${i}:${k.j}" aria-pressed="${c.cls.has(k.j)}"><i style="background:${k.color}"></i>${esc(k.label)}</button>`).join("")}
      </div>`;
    }
    const foot = `
      <div class="bc-crit-foot">${miss}
        <span class="bc-seg small" role="radiogroup" aria-label="${esc(tr(s.kind === "extra" ? s.label : s.short))}">
          <button type="button" role="radio" aria-checked="${!c.mark}" class="${c.mark ? "" : "on"}" data-mode="${i}:f">${t("pf.filter")}</button>
          <button type="button" role="radio" aria-checked="${c.mark}" class="${c.mark ? "on" : ""}" data-mode="${i}:m">${t("pf.markOnly")}</button>
        </span>
      </div>`;
    return `<section class="bc-crit${c.mark ? " marked" : ""}" data-crit="${i}">${head}${body}${foot}</section>`;
  }
  function renderPanel() {
    if (!panel) return;
    const list = state.crits;
    const filters = list.map((c, i) => [c, i]).filter(([c]) => !c.mark), marks = list.map((c, i) => [c, i]).filter(([c]) => c.mark);
    const share = counts ? counts.match / counts.total * 100 : 100;
    panel.setAttribute("aria-label", t("ctl.profile"));
    // keep the focus (and the scroll) where it was across the redraw
    const focus = document.activeElement && panel.contains(document.activeElement) ? document.activeElement : null;
    const focusKey = focus ? ["data-lo", "data-hi", "data-miss", "data-cls", "data-mode", "data-remove", "data-add", "data-copy", "data-hide"].map(a => focus.hasAttribute(a) ? `[${a}="${focus.getAttribute(a)}"]` : null).find(Boolean) : null;
    const scroll = panel.querySelector(".bc-panel-scroll");
    const top0 = scroll ? scroll.scrollTop : 0;
    panel.innerHTML = `
      <div class="bc-panel-head">
        <h2 class="bc-panel-title">${t("ctl.profile")}</h2>
        ${list.length ? `<button type="button" class="bc-pill-btn" data-copy>${t("pf.copy")}</button>` : ""}
        <button type="button" class="bg-x" data-close aria-label="${t("ctl.profileClose")}">${narrow() ? "×" : "‹"}</button>
      </div>
      ${list.length ? `
      <div class="bc-funnel" aria-live="polite">
        <div class="bc-funnel-row"><span class="bc-funnel-n" data-total>${countText(counts && counts.match)}</span>
          <span>${t("pf.of")} <span data-all>${counts ? fmtCount(counts.total) : "…"}</span> ${t("pf.homesMatch")}</span></div>
        <div class="bc-funnel-bar"><i data-bar style="width:${share.toFixed(1)}%"></i></div>
        ${tableFailed ? `<p class="bc-note">${t("pf.noTable")}</p>` : ""}
        <div class="bc-others">
          <span>${t("ctl.others")}</span>
          <span class="bc-seg" role="radiogroup" aria-label="${t("ctl.others")}">
            <button type="button" role="radio" aria-checked="${!state.hide}" class="${state.hide ? "" : "on"}" data-hide="0">${t("ctl.fade")}</button>
            <button type="button" role="radio" aria-checked="${state.hide}" class="${state.hide ? "on" : ""}" data-hide="1">${t("ctl.hide")}</button>
          </span>
        </div>
      </div>` : ""}
      <div class="bc-panel-scroll">
        ${list.length ? "" : `<p class="bc-note">${t("ctl.profileEmpty")}</p>`}
        ${filters.length ? `<div class="bc-group-title">${t("ctl.mustMatch")} · <button type="button" class="bc-link" data-reset>${t("sb.reset")}</button></div>` : ""}
        ${filters.map(([c, i]) => critHtml(c, i)).join("")}
        ${marks.length ? `<div class="bc-group-title">${t("ctl.markOnly")}</div>` : ""}
        ${marks.map(([c, i]) => critHtml(c, i)).join("")}
        <button type="button" class="bc-add" data-add aria-haspopup="dialog" aria-expanded="false">+ ${t("pf.add")} <span>${t("pf.addSub")}</span></button>
      </div>`;
    const box = sel => panel.querySelector(sel);
    box("[data-close]").addEventListener("click", () => setPanel(false, true));
    const reset = box("[data-reset]");
    if (reset) reset.addEventListener("click", () => { state.crits = state.crits.filter(c => c.mark); update(); });
    const copy = box("[data-copy]");
    if (copy) copy.addEventListener("click", () => {
      const done = () => { copy.textContent = t("pf.copied"); setTimeout(() => { copy.textContent = t("pf.copy"); }, 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(done, () => {}); else done();
    });
    panel.querySelectorAll("[data-hide]").forEach(b => b.addEventListener("click", () => { state.hide = b.dataset.hide === "1"; update(); }));
    panel.querySelectorAll("[data-remove]").forEach(b => b.addEventListener("click", () => { state.crits.splice(Number(b.dataset.remove), 1); update(); }));
    panel.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => {
      const [i, m] = b.dataset.mode.split(":");
      state.crits[Number(i)].mark = m === "m";
      update();
    }));
    panel.querySelectorAll("[data-miss]").forEach(b => b.addEventListener("change", () => { state.crits[Number(b.dataset.miss)].miss = b.checked; update(); }));
    panel.querySelectorAll("[data-cls]").forEach(b => b.addEventListener("click", () => {
      const [i, k] = b.dataset.cls.split(":");
      const set = state.crits[Number(i)].cls, key = k === "n" ? "n" : Number(k);
      if (set.has(key)) set.delete(key); else set.add(key);
      update();
    }));
    // the handles: the map and the counts follow while dragging (drawn in
    // place, so the drag goes on); the rest of the panel on release
    panel.querySelectorAll("[data-lo], [data-hi]").forEach(inp => {
      const i = Number(inp.dataset.lo ?? inp.dataset.hi), lo = inp.hasAttribute("data-lo");
      inp.addEventListener("input", () => {
        const c = state.crits[i], v = Number(inp.value);
        if (lo) c.lo = Math.min(v, c.hi); else c.hi = Math.max(v, c.lo);
        if (Number(inp.value) !== (lo ? c.lo : c.hi)) inp.value = lo ? c.lo : c.hi;
        softUpdate(i);
      });
      inp.addEventListener("change", () => update());
    });
    const add = box("[data-add]");
    add.addEventListener("click", ev => { ev.stopPropagation(); openPop("crit", add, "bc-crit-pop", t("pf.add"), fillCritPicker); });
    if (pop && pop.id === "crit") { pop.anchor = add; add.setAttribute("aria-expanded", "true"); }
    if (narrow()) attachSheetHandle(panel, () => setPanel(false, true));
    const sc = panel.querySelector(".bc-panel-scroll");
    if (sc) sc.scrollTop = top0;
    if (focusKey) { const f = panel.querySelector(focusKey); if (f) f.focus({ preventScroll: true }); }
  }
  // while a handle moves: the map (once per frame), the counts, the range's
  // own labels and bars, the chips; no redraw of the panel
  let frame = 0;
  function softUpdate(i) {
    writeState();
    if (!frame) frame = requestAnimationFrame(() => { frame = 0; if (map.isStyleLoaded()) apply(); });
    recount();
    const c = state.crits[i], s = critSpec(c.id), sec = panel.querySelector(`[data-crit="${i}"]`);
    if (sec) {
      const r = sec.querySelector(".bc-range");
      r.style.setProperty("--lo", `${pctOf(s, c.lo)}%`); r.style.setProperty("--hi", `${pctOf(s, c.hi)}%`);
      sec.querySelector(`[data-val="${i}"]`).textContent = rangeText(c, s);
      const h = PROFILE_TABLE && profileHistogram(c);
      if (h) sec.querySelectorAll(".bc-hist i").forEach(el => {
        const b = Number(el.dataset.b), a = s.min + b * h.w, z = a + h.w;
        el.classList.toggle("in", (c.lo <= s.min || z > c.lo) && (c.hi >= s.max || a < c.hi + (s.int ? 1 : 0)));
      });
    }
    paintCounts();
    renderTop();
  }
  function paintCounts() {
    if (!panel || !counts) return;
    const set = (sel, v) => { const el = panel.querySelector(sel); if (el) el.textContent = v; };
    set("[data-total]", fmtCount(counts.match));
    const bar = panel.querySelector("[data-bar]");
    if (bar) bar.style.width = `${(counts.match / counts.total * 100).toFixed(1)}%`;
    counts.left.forEach((n, i) => set(`[data-left="${i}"]`, fmtCount(n)));
  }

  // "+ Kriterium": every lens of the catalogue (variants: day / night, the
  // places on foot) and the extras; one already in the profile is ticked
  function fillCritPicker(el) {
    const has = id => state.crits.some(c => c.id === id);
    // a lens without data in this city can't become a criterion here (it would match nothing)
    const btn = (id, label, sw) => {
      const none = critSpec(id) && critSpec(id).kind !== "extra" && lensCoverage(id).state === "none";
      return `<button type="button" class="bc-pick${has(id) ? " on" : ""}${none ? " bc-lens-none" : ""}" data-pick="${id}" ${has(id) || none ? `aria-disabled="true"` : ""}${none ? ` disabled title="${esc(covText("cov.noneHere"))}"` : ""}>${sw ? `<span class="bc-lens-swatch" style="background:${lensBar(id)}"></span>` : ""}<span>${esc(label)}${has(id) ? " ✓" : ""}${none ? ` <span class="bc-cov-tag">${t("cov.noData")}</span>` : ""}</span></button>`;
    };
    const item = mid => {
      const m = LENS_MODES.find(x => x.id === mid);
      if (!m.variants) return critSpec(m.id) ? btn(m.id, tr(m.label), true) : "";
      return `<div class="bc-pick-group"><span class="bc-pick-name">${esc(tr(m.label))}</span>
        <span class="bc-pick-variants">${m.variants.map(v => btn(colorModeId(m, v), tr(v.label), false)).join("")}</span></div>`;
    };
    el.innerHTML = `
      <div class="bc-pop-head">
        <span class="bc-pop-title">${t("pf.add")}</span><span class="bc-pop-sub">${t("pf.addHint")}</span>
        <button type="button" class="bg-x" data-close aria-label="${t("ctl.close")}">×</button>
      </div>
      <div class="bc-lens-grid">${LENS_GROUPS.map(g => `
        <div class="bc-lens-group">
          <div class="bc-group-title">${esc(tr(g.label))}</div>
          ${g.modes.map(item).join("")}
        </div>`).join("")}
        <div class="bc-lens-group">
          <div class="bc-group-title">${t("pf.extras")}</div>
          ${PROFILE_EXTRAS.map(x => btn(x.id, tr(x.label), false)).join("")}
        </div>
      </div>`;
    el.querySelector("[data-close]").addEventListener("click", closePop);
    el.querySelectorAll("[data-pick]").forEach(b => b.addEventListener("click", () => {
      if (has(b.dataset.pick)) return;
      addCrit(newCrit(b.dataset.pick));
    }));
  }
  // a new criterion (from the picker or the legend); one per lens: a second
  // for the same lens replaces the first
  function addCrit(c) {
    if (!c) return;
    const at = state.crits.findIndex(x => x.id === c.id);
    if (at >= 0) state.crits[at] = c; else state.crits.push(c);
    closePop();
    update();
    if (!document.body.classList.contains("bc-panel-open")) setPanel(true, true);
    const i = at >= 0 ? at : state.crits.length - 1;
    const sec = panel.querySelector(`[data-crit="${i}"]`);
    if (sec) {
      sec.scrollIntoView({ block: "nearest" });
      const f = sec.querySelector("input, .bc-cls, [data-mode]");
      if (f) f.focus({ preventScroll: true });
    }
  }
  function padding(open) { return { left: open && !narrow() ? PANEL_W + 2 * GAP : 0 }; }
  function setPanel(open, animate) {
    if (!panel) return;
    // keep focus in the panel while it renders (re-rendering would drop it)
    document.body.classList.toggle("bc-panel-open", open);
    setTimeout(liftPin, animate ? 500 : 0);   // the legend moves with the panel
    panel.inert = !open;
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    if (!narrow()) save(STORE.panel, open ? "1" : "0");
    const d = animate && !matchMedia("(prefers-reduced-motion: reduce)").matches ? 450 : 0;
    map.easeTo({ padding: padding(open), duration: d });
    renderTop();
    if (open && animate) { const c = panel.querySelector("[data-close]"); if (c) c.focus({ preventScroll: true }); }
  }

  // --- legend bar (bottom left) ---
  const legend = document.createElement("section");
  legend.className = "bc-legend bg-card-ui";
  document.body.appendChild(legend);
  // collapsed (the default): a pill like the attribution pin, with the lens's
  // colours and name; a click opens the full legend, which folds back
  function renderLegend() {
    const id = state.lens, m = lensMode();
    const classes = colorModeClasses(id);
    const min = load(STORE.legend) !== "0";
    // the C-08 keys; the first is "no value": "year unknown", else what a
    // missing value means for this lens
    const keys = BUILDING_KEYS.slice();
    if (m.id !== "year") keys[0] = { ...keys[0], label: m.missing || { de: "Keine Angabe", en: "No data" } };
    if (m.missingIsLowest) keys.shift();
    const n = classes.length;
    // how much of this lens the city has (web/city.js coverage): a line in the legend
    const cov = lensCoverage(id);
    const covLine = cov.state === "none" ? covText("cov.legendNone") : cov.state === "partial" ? covText("cov.partial", cov) : "";
    // a click on a class adds it to the search profile (map page)
    const canAdd = full && !!critSpec(id) && cov.state !== "none";
    legend.classList.toggle("min", min);
    legend.setAttribute("aria-label", tr(m.legendTitle));
    legend.innerHTML = min ? `
      <button type="button" class="bc-legend-pill" data-min aria-expanded="false" aria-label="${t("ctl.legendShow")}: ${esc(tr(m.legendTitle))}">
        <span class="bc-legend-mini" style="background:${lensBar(id)}"></span>
        <span class="bc-legend-name">${esc(lensTitle(id))}${cov.state === "none" ? ` · ${t("cov.noData")}` : ""}</span>
        <span class="bc-legend-caret" aria-hidden="true">▴</span>
      </button>` : `
      <div class="bc-legend-head">
        <span class="bc-legend-title">${esc(tr(m.legendTitle))}${lensSel().variant ? ` · ${esc(tr(lensSel().variant.label))}` : ""}</span>
        <button type="button" class="bg-x small" data-min aria-expanded="true" aria-label="${t("ctl.legendHide")}">▾</button>
      </div>
      <div class="bc-legend-grid" style="--n:${n}">
        ${classes.map((c, i) => {
          // a class: its colour and label; on the map page a button that adds it to the profile
          const inner = `<span class="bc-class" style="background:${c.color};border-color:${c.outline || c.color}"></span><span class="bc-class-label">${esc(tr(c.label))}</span>`;
          return canAdd
            ? `<button type="button" class="bc-class-cell bc-class-add" data-add-class="${i}" title="${esc(tr(c.label))}: ${t("pf.legendAdd")}" aria-label="${esc(tr(c.label))}: ${t("pf.legendAdd")}">${inner}</button>`
            : `<span class="bc-class-cell">${inner}</span>`;
        }).join("")}
      </div>
      <div class="bc-legend-foot">
        ${keyRows(keys)}
      </div>
      ${covLine ? `<p class="bc-note bc-cov-note">${esc(covLine)}</p>` : ""}
      ${m.note ? `<p class="bc-note">${esc(tr(m.note))}</p>` : ""}
      ${canAdd ? `<p class="bc-note bc-legend-hint">${t("pf.legendHint")}</p>` : ""}`;
    legend.querySelectorAll("[data-add-class]").forEach(b => b.addEventListener("click", () => addCrit(critForClass(id, Number(b.dataset.addClass)))));
    legend.querySelector("[data-min]").addEventListener("click", () => {
      save(STORE.legend, min ? "0" : "1"); renderLegend();
      legend.querySelector("[data-min]").focus({ preventScroll: true });
    });
    liftPin();
  }
  // the attribution pin (bottom right) moves above the legend wherever the two
  // would meet: phones, narrow windows, the profile panel squeezing the legend (048)
  function liftPin() {
    const pin = document.querySelector(".fr-ctrl"), root = document.documentElement;
    root.style.setProperty("--bc-legend-h", "0px");
    if (!pin) return;
    const a = legend.getBoundingClientRect(), b = pin.getBoundingClientRect();
    if (a.width && a.right > b.left - 8 && a.left < b.right + 8 && a.top < b.bottom + 8) root.style.setProperty("--bc-legend-h", `${window.innerHeight - a.top}px`);
  }
  window.addEventListener("resize", liftPin);
  window.addEventListener("bg:fresh", () => requestAnimationFrame(liftPin));   // the pin got its date: wider
  function renderAll() { renderTop(); renderPanel(); renderLegend(); }
  recount();
  renderAll();
  window.addEventListener("bg:lang", () => { renderAll(); siteMenu.render(); refillPop(); });

  // the panel starts as the browser left it (closed at first, and always on a phone)
  const startOpen = full && !narrow() && load(STORE.panel) === "1";
  if (full) { map.setPadding(padding(startOpen)); setPanel(startOpen, false); }

  if (map.isStyleLoaded()) apply(); else map.once("load", apply);
  // a link with ?view=3d opens tilted
  if (full && state.view === "3d") map.once("load", () => map.easeTo({ pitch: 55, bearing: -20, duration: 0 }));
  writeState();

  // the building whose card is open stays ringed (null clears it)
  function select(p) {
    state.selected = p && p.egid != null ? p.egid : null;
    if (map.isStyleLoaded()) apply();
  }
  // turns a place layer on (the building card's "nearby" list opens a place's card)
  function showPlace(key) {
    if (state.places.has(key)) return;
    state.places.add(key);
    update();
  }
  // the address search's field goes into the brand card (web/search.js)
  function setSearch(el) { searchEl = el; renderTop(); }
  return { state, apply, select, showPlace, setView, setSearch };
}

// A bottom sheet's grab handle (phones): a bar at the top of the
// sheet that drags. Down past 90 px closes it (onClose), up makes it tall
// (`bg-sheet-tall`, nearly the whole screen), a tap or Enter switches between
// the two heights. The handle is a button, so it works without a pointer too.
function attachSheetHandle(sheetEl, onClose) {
  const h = document.createElement("button");
  h.type = "button";
  h.className = "bg-grab";
  h.setAttribute("aria-label", t("ctl.sheetSize"));
  h.innerHTML = "<i></i>";
  sheetEl.prepend(h);
  let y0 = null, dy = 0;
  const move = ev => {
    if (y0 === null) return;
    dy = ev.clientY - y0;
    sheetEl.style.transform = dy > 0 ? `translateY(${dy}px)` : "";
  };
  const end = () => {
    if (y0 === null) return;
    y0 = null;
    sheetEl.style.transform = "";
    sheetEl.classList.remove("bg-dragging");
    if (dy > 90) onClose();
    else if (dy < -40) sheetEl.classList.add("bg-sheet-tall");
    else if (Math.abs(dy) < 6) sheetEl.classList.toggle("bg-sheet-tall");
  };
  h.addEventListener("pointerdown", ev => { y0 = ev.clientY; dy = 0; sheetEl.classList.add("bg-dragging"); h.setPointerCapture(ev.pointerId); ev.preventDefault(); });
  h.addEventListener("pointermove", move);
  h.addEventListener("pointerup", end);
  h.addEventListener("pointercancel", end);
  // keyboard (a pointer tap ends in pointerup and fires no click after preventDefault)
  h.addEventListener("click", ev => { if (ev.detail === 0) sheetEl.classList.toggle("bg-sheet-tall"); ev.stopPropagation(); });
  return h;
}

// The zoom level, between the + and − buttons of a NavigationControl (the map
// menu says from which zoom each place layer shows). `map`: the map that owns
// the buttons; it reads that map's zoom.
function addZoomReadout(map) {
  const plus = map.getContainer().querySelector(".maplibregl-ctrl-zoom-in");
  if (!plus) return;
  const el = document.createElement("div");
  el.className = "bc-zoom";
  const show = () => {
    el.textContent = map.getZoom().toFixed(1);
    el.title = `Zoom ${el.textContent}`;
  };
  el.setAttribute("aria-hidden", "true");   // the buttons carry the meaning; this is a visual readout
  plus.after(el);
  show();
  map.on("zoom", show);
}
