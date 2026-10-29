/**
 * The building card's neighbourhood:
 *   - "In der Nähe, zu Fuss": the nearest place of each kind (WALK_KINDS in
 *     layers.js) with the walk along roads and paths (w_<kind> metres,
 *     cities/zurich/pipeline/swiss/build_walk.py; minutes ≈ metres / 80);
 *   - the stop for Zürich HB (else the nearest) with the gist of its timetable
 *     card (lines, the mean morning trip to HB, the cycle): a commute preview;
 *   - on the pinned card every entry opens that place's (or stop's) card:
 *     its place layer is switched on, the map pans / zooms to it if needed.
 * n_<kind> on a building is a position in /data/places_index.json
 * ([id, layer, kind, name, lon, lat]; id = the place's `pid` or the stop's nr).
 * Loaded after map.js, stops.js and places.js (uses their cards and helpers).
 */

// The index arrives a moment after the page: until then a card shows the
// distances (they are in the tiles) with "…" for the names, then redraws
// (lateData(), map.js); if it can't be loaded, the names say so.
let PLACE_INDEX = [], INDEX_STATE = "loading";   // loading | ready | failed
fetch("../data/places_index.json").then(r => (r.ok ? r.json() : Promise.reject(r.status)))
  .then(d => { PLACE_INDEX = d || []; INDEX_STATE = "ready"; }, () => { INDEX_STATE = "failed"; })
  .then(() => lateData());
const pendingName = () => (INDEX_STATE === "loading" ? "…" : t("hc.nearNoName"));

const walkMin = m => Math.max(1, Math.round(m / WALK_M_PER_MIN));
const walkText = m => `≈ ${walkMin(m)}′ · ${m >= 1000 ? `${fmtNum(m / 1000, 1)} km` : `${fmtNum(m)} m`}`;
const nearEntry = i => (Number.isInteger(Number(i)) && i !== "" && i != null ? PLACE_INDEX[Number(i)] : null);

// the list under the sections: one row per kind (the stop has its own block)
function nearbyHtml(p, pinned) {
  // no walking distances in this city yet (web/city.js coverage.walk): say so, the block stays
  if ((CITY.coverage || {}).walk === "none") {
    return `<div class="hc-nearby"><div class="hc-cap"><span>${escapeHtml(t("hc.near"))}</span></div>`
      + `<div class="hc-main"><span class="hc-chip hc-na">${escapeHtml(covText("cov.walkNone"))}</span></div></div>`;
  }
  const rows = WALK_KINDS.filter(k => k.id !== "stop").map(k => {
    const m = Number(p[`w_${k.id}`]), e = nearEntry(p[`n_${k.id}`]);
    if (lensCoverage(`walk_${k.id}`).state === "none") {   // no such places in this city's sources
      return `<li class="hc-near-none"><i></i><span class="hc-near-kind">${escapeHtml(tr(k.label))}</span><span class="hc-near-name">${escapeHtml(covText("cov.na"))}</span><span class="hc-near-dist">–</span></li>`;
    }
    if (m > 0 && !e) {   // the walk is known, the place's name not yet (or not at all)
      return `<li><i></i><span class="hc-near-kind">${escapeHtml(tr(k.label))}</span><span class="hc-near-name hc-quiet-text">${escapeHtml(pendingName())}</span>`
        + `<span class="hc-near-dist">${escapeHtml(walkText(m))}</span></li>`;
    }
    if (!(m > 0)) {
      return `<li class="hc-near-none"><i></i><span class="hc-near-kind">${escapeHtml(tr(k.label))}</span><span class="hc-near-name">–</span><span class="hc-near-dist">${escapeHtml(t("hc.nearNone"))}</span></li>`;
    }
    const icon = placeIconUrl(`place-${e[2]}${e[2] === "er" ? "-hub" : ""}`);
    const attrs = pinned ? ` data-near="${Number(p[`n_${k.id}`])}" role="button" tabindex="0"` : "";
    return `<li${attrs}>${icon ? `<img src="${icon}" alt="">` : "<i></i>"}<span class="hc-near-kind">${escapeHtml(tr(k.label))}</span>`
      + `<span class="hc-near-name">${escapeHtml(e[3] || tr(k.label))}</span><span class="hc-near-dist">${escapeHtml(walkText(m))}</span></li>`;
  }).join("");
  return `<div class="hc-nearby"><div class="hc-cap"><span>${escapeHtml(t("hc.near"))}</span>`
    + `<span class="hc-aside hc-quiet-text" title="${escapeHtml(t("hc.nearHint"))}">≈ 80 m/min</span></div><ul>${rows}</ul></div>`;
}

// the card's stop: the one that makes most sense for Zürich HB (the stop the
// commute estimate goes from, n_hb / w_hb, build_walk.py; owner 2026-10-23),
// else the nearest on foot. { key, main, sub, nr, idx }
function nearStop(p) {
  for (const [key, n, w] of [["hc.hbStop", p.n_hb, p.w_hb], ["hc.stop", p.n_stop, p.w_stop]]) {
    if (w == null || !(Number(w) >= 0)) continue;
    const e = nearEntry(n), main = walkText(Math.max(10, Number(w)));
    // before the index is there: the walk, "…" for the name, no gist / link yet
    return e ? { key, main, sub: e[3], nr: e[0], idx: Number(n) } : { key, main, sub: pendingName(), nr: null, idx: null };
  }
  return null;
}

// the stop card's gist, filled in once the stop's JSON is there (stops.js caches it)
function stopGistHtml(o) {
  if (!o) return "";
  const lines = [...o.lines].sort((a, b) => b[4] - a[4]).slice(0, 6).map(l => lineBadge(l, o)).join("");
  const ps = o.parts && o.parts.morning;
  const trip = o.at_hb ? t("sc.atHb") : ps && ps.mean != null
    ? `${t("hc.stopGist")} Ø ${fmtMin(ps.mean)}′${ps.takt ? ` · ${t("sc.cycle")} ${fmtTakt(ps.takt)}′` : ""}` : "";
  return `<div class="hc-gist-lines">${lines}</div>${trip ? `<div class="hc-sub">${escapeHtml(trip)}</div>` : ""}`;
}
function hydrateBuildingCard() {
  document.querySelectorAll("[data-stop-gist]:not([data-done])").forEach(el => {
    el.dataset.done = "1";
    // stopData() gives the cached data itself once loaded, a promise before
    Promise.resolve(stopData(el.dataset.stopGist)).then(o => { el.innerHTML = stopGistHtml(o); });
  });
}

// open a place's (or stop's) card from its index entry
function openNearby(idx) {
  const e = PLACE_INDEX[idx];
  if (!e) return;
  const [id, layer, , , lon, lat] = e;
  const pl = PLACE_LAYERS.find(x => x.id === layer);
  if (!pl) return;
  controls.showPlace(pl.key);
  pinnedCard.remove();
  closeSheet();
  const zoom = Math.max(map.getZoom(), pl.minzoom + 0.5);   // every icon of the layer shows
  const open = () => {
    const filter = layer === "stops" ? ["==", ["get", "nr"], Number(id)] : ["==", ["get", "pid"], id];
    const hit = map.querySourceFeatures("cadastre", { sourceLayer: pl.sourceLayer, filter })[0];
    if (!hit) return;
    // the shape the cards expect from a rendered feature
    const f = { sourceLayer: pl.sourceLayer, properties: hit.properties, geometry: { type: "Point", coordinates: [lon, lat] } };
    const ev = { features: [f], point: map.project([lon, lat]), lngLat: { lng: lon, lat } };
    if (layer === "stops") showStopCard(ev, true); else showPlaceCard(ev, true);
  };
  const pad = map.getPadding(), c = map.getContainer();
  const pt = map.project([lon, lat]);
  const inView = pt.x > (pad.left || 0) + 40 && pt.x < c.clientWidth - 40 && pt.y > 40 && pt.y < c.clientHeight - 40;
  if (inView && map.getZoom() >= zoom - 0.01) { map.once("idle", open); map.triggerRepaint(); }
  else { map.once("idle", open); map.easeTo({ center: [lon, lat], zoom, duration: 700 }); }
}
document.addEventListener("click", ev => {
  const el = ev.target.closest && ev.target.closest("[data-near]");
  if (!el) return;
  ev.preventDefault();
  ev.stopPropagation();
  openNearby(Number(el.dataset.near));
});
document.addEventListener("keydown", ev => {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  const el = ev.target.closest && ev.target.closest("[data-near]");
  if (el) { ev.preventDefault(); openNearby(Number(el.dataset.near)); }
});
