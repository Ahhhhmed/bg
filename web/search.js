/**
 * Address, place and stop search in the brand card (C-10).
 *
 * Searches, without any outside geocoder:
 *   - every building with a GWR address: /data/address_index.json
 *     (shared/pipeline/address_index.py: address, postcode, EGID, position; public
 *     register fields only), loaded the first time the field is used;
 *   - every place and stop: /data/places_index.json (PLACE_INDEX, nearby.js).
 * Every word typed must start a word of the entry ("schef 29", "wipkingen
 * bahnhof"); Enter or a click flies there and opens the card: a building's
 * pinned card (openBuildingCard, map.js), a place's or a stop's (openNearby,
 * nearby.js). A combobox: arrows move through the list, Escape closes it,
 * a second Escape clears the field. Leads are never in it (private).
 *
 * Usage: initSearch(controls) after the controls (map.js); returns the element.
 * Loaded after nearby.js.
 */
function initSearch(controls) {
  const MAX = 8;
  const el = document.createElement("div");
  el.className = "bc-search";
  el.innerHTML = `
    <svg class="bc-search-icon" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="7" cy="7" r="4.6"/><path d="M10.5 10.5L14 14"/></g></svg>
    <input type="search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="bc-search-list" autocomplete="off" spellcheck="false">
    <button type="button" class="bg-x small bc-search-clear" hidden>×</button>
    <ul class="bc-search-list" id="bc-search-list" role="listbox" hidden></ul>`;
  const input = el.querySelector("input"), list = el.querySelector("ul"), clear = el.querySelector(".bc-search-clear");
  const label = () => {
    input.placeholder = t("srch.placeholder");
    input.setAttribute("aria-label", t("srch.label"));
    clear.setAttribute("aria-label", t("srch.clear"));
  };
  label();
  window.addEventListener("bg:lang", () => { label(); if (!list.hidden) show(); });
  el.addEventListener("click", ev => ev.stopPropagation());

  // "Scheffelstr. 29" -> "scheffelstrasse 29"; umlauts and accents folded (Zürich = zurich = zuerich)
  const norm = s => String(s || "").toLowerCase()
    .replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/str\.(?=\s|\d|$)/g, "strasse").replace(/[^a-z0-9]+/g, " ").trim();
  // the same folding for the umlaut written plainly ("zurich"): both forms are words of the entry
  const plain = s => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  const words = s => [...new Set(`${norm(s)} ${plain(s)}`.split(" ").filter(Boolean))];

  let addresses = null, loading = null, failed = false, places = null;
  function loadAddresses() {
    if (addresses || loading) return loading;
    loading = fetch("../data/address_index.json").then(r => (r.ok ? r.json() : Promise.reject(r.status))).then(d => {
      const at = Object.fromEntries(d.cols.map((c, i) => [c, i]));
      addresses = d.rows.map(r => ({ kind: "addr", name: r[at.address], plz: r[at.plz], egid: r[at.egid], lon: r[at.lon], lat: r[at.lat],
        words: words(`${r[at.address]} ${r[at.plz]}`), key: norm(r[at.address]) }));
      if (document.activeElement === input || input.value) show();
    }, () => { failed = true; loading = null; show(); });
    return loading;
  }
  // the places and stops, from the index the cards use (nearby.js)
  function placeEntries() {
    if (places && places.length) return places;
    places = (typeof PLACE_INDEX !== "undefined" ? PLACE_INDEX : []).map((e, idx) => {
      const pl = PLACE_LAYERS.find(x => x.id === e[1]);
      const k = pl && pl.kinds.find(x => x.v === e[2]);
      const hub = !!(k && k.hub);   // a station: first among the stops
      // a stop's name without its town ("Zürich, Stauffacher") also counts as its start
      const short = e[1] === "stops" && e[3].includes(", ") ? norm(e[3].slice(e[3].indexOf(", ") + 2)) : null;
      return { kind: e[1] === "stops" ? "stop" : "place", name: e[3], idx, icon: `${e[2]}${hub ? "-hub" : ""}`, hub, what: k ? k.label : (pl && pl.label), words: words(e[3]), key: norm(e[3]), short };
    });
    return places;
  }

  // every query word must start a word of the entry; the best first:
  // the whole query at the start of the name, then exact words, then short names
  function find(q) {
    const qw = norm(q).split(" ").filter(Boolean);
    if (!qw.length) return [];
    const qs = qw.join(" "), digits = /\d/.test(qs);
    const pool = [...placeEntries(), ...(addresses || [])];
    const hits = [];
    for (const e of pool) {
      let exact = 0, ok = true;
      for (const w of qw) {
        let found = false;
        for (const x of e.words) {
          if (x === w) { found = true; exact++; break; }
          if (x.startsWith(w)) found = true;
        }
        if (!found) { ok = false; break; }
      }
      if (!ok) continue;
      // a number in the query: addresses first; else stops (stations first), then places
      const kind = digits ? (e.kind === "addr" ? 5 : 0) : (e.kind === "stop" ? (e.hub ? 8 : 6) : e.kind === "place" ? 5 : 0);
      const score = (e.key.startsWith(qs) || (e.short && e.short.startsWith(qs)) ? 100 : 0) + exact * 10 + kind - e.name.length / 100;
      hits.push([score, e]);
      if (hits.length > 4000) break;   // a one-letter query: enough to rank
    }
    hits.sort((a, b) => b[0] - a[0] || a[1].name.localeCompare(b[1].name, "de", { numeric: true }));
    return hits.slice(0, MAX).map(h => h[1]);
  }

  let results = [], active = -1;
  const optionHtml = (e, i) => {
    const icon = e.kind === "addr" ? "" : placeIconUrl(`place-${e.icon}`);
    // the kind without the map menu's zoom note ("Bahnhof (ab Zoom 11)")
    const sub = e.kind === "addr" ? [e.plz, t("srch.building")].filter(Boolean).join(" · ") : String(tr(e.what) || "").replace(/\s*\([^)]*[Zz]oom[^)]*\)$/, "");
    return `<li role="option" id="bc-search-${i}" aria-selected="${i === active}" data-i="${i}" class="${i === active ? "on" : ""}">
      ${icon ? `<img src="${icon}" alt="">` : `<i class="bc-search-house" aria-hidden="true"></i>`}
      <span><span class="bc-search-name">${escapeHtml(e.name)}</span><span class="bc-search-sub">${escapeHtml(sub || "")}</span></span></li>`;
  };
  function show() {
    const q = input.value.trim();
    clear.hidden = !input.value;
    if (!q) { hide(); return; }
    results = find(q);
    if (active >= results.length) active = results.length - 1;
    const note = !results.length
      ? (failed ? t("srch.failed") : !addresses ? t("srch.loading") : t("srch.none"))
      : !addresses && !failed ? t("srch.loading") : "";
    list.innerHTML = results.map(optionHtml).join("") + (note ? `<li class="bc-search-note" role="presentation">${escapeHtml(note)}</li>` : "");
    list.hidden = false;
    // phones: the list spans the screen (8 px margins), under the brand card
    if (window.matchMedia("(max-width: 699px)").matches) {
      const r = el.getBoundingClientRect();
      list.style.left = `${8 - r.left}px`;
      list.style.width = `${window.innerWidth - 16}px`;
    } else { list.style.left = list.style.width = ""; }
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `bc-search-${active}`); else input.removeAttribute("aria-activedescendant");
  }
  function hide() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }
  function choose(e) {
    if (!e) return;
    input.value = e.kind === "addr" && e.plz ? `${e.name}, ${e.plz}` : e.name;
    clear.hidden = false;
    hide();
    if (window.matchMedia("(max-width: 699px)").matches) input.blur();   // the phone keyboard goes away
    if (e.kind === "addr") openBuildingByEgid(e.egid, { lng: e.lon, lat: e.lat });   // map.js
    else openNearby(e.idx);   // nearby.js
  }

  let timer = 0;
  input.addEventListener("focus", () => { loadAddresses(); if (input.value) show(); });
  input.addEventListener("input", () => { loadAddresses(); active = -1; clearTimeout(timer); timer = setTimeout(show, 60); });
  input.addEventListener("keydown", ev => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (list.hidden) show();
      if (!results.length) return;
      active = ev.key === "ArrowDown" ? (active + 1) % results.length : (active <= 0 ? results.length - 1 : active - 1);
      show();
      const li = list.querySelector(`[data-i="${active}"]`);
      if (li) li.scrollIntoView({ block: "nearest" });
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      clearTimeout(timer);
      results = find(input.value.trim());
      choose(results[active >= 0 ? active : 0]);
    } else if (ev.key === "Escape") {
      ev.stopPropagation();
      if (!list.hidden) hide(); else { input.value = ""; clear.hidden = true; }
    }
  });
  list.addEventListener("mousedown", ev => ev.preventDefault());   // keep the focus in the field
  list.addEventListener("click", ev => {
    const li = ev.target.closest("[data-i]");
    if (li) choose(results[Number(li.dataset.i)]);
  });
  clear.addEventListener("click", () => { input.value = ""; hide(); clear.hidden = true; input.focus(); });
  document.addEventListener("click", hide);
  controls.setSearch(el);
  return el;
}
