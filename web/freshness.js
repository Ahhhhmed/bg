/**
 * Data age (C-16): one indicator for the whole site, in the attribution pin at
 * the bottom right: "Datenstand <oldest fetch date>". It counts from our last
 * fetch of each source (the dates in /data/card_sources.json and
 * /data/places_sources.json, written by cities/zurich/pipeline/card_sources.py and
 * build_places.py), not the source's own publication date. Orange from 2
 * months, red from 4 (calendar months): a reminder to re-fetch. A click lists
 * every source with its date in the same colours; the cards' source dates use
 * them too (freshDateHtml).
 *
 * ?today=2027-02-20 pretends another day (to check the colours).
 */
const FRESH_WARN_MONTHS = 2, FRESH_OLD_MONTHS = 4;
const freshToday = (() => {
  const q = new URLSearchParams(location.search).get("today");
  const d = q && /^\d{4}-\d{2}-\d{2}$/.test(q) ? new Date(q + "T12:00:00") : new Date();
  return isNaN(d) ? new Date() : d;
})();

// "2026-10-13" -> whole calendar months until today
function monthsOld(date) {
  const d = new Date(date + "T12:00:00");
  let m = (freshToday.getFullYear() - d.getFullYear()) * 12 + freshToday.getMonth() - d.getMonth();
  if (freshToday.getDate() < d.getDate()) m -= 1;
  return Math.max(0, m);
}
// "ok" | "warn" (>= 2 months) | "old" (>= 4 months)
function ageLevel(date) {
  if (!date) return "ok";
  const m = monthsOld(date);
  return m >= FRESH_OLD_MONTHS ? "old" : m >= FRESH_WARN_MONTHS ? "warn" : "ok";
}
const freshDate = date => new Date(date + "T12:00:00").toLocaleDateString(locale(),
  { day: "numeric", month: "short", year: "numeric" });
// a date in a card's source list, in its age colour
function freshDateHtml(date) {
  if (!date) return "";
  return `<span class="fr-date fr-${ageLevel(date)}">${freshDate(date).replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span>`;
}

// every source with its fetch date, once (by label and date), oldest first
let FRESH_SOURCES = null;
const freshLoaded = Promise.all(["../data/card_sources.json", "../data/places_sources.json"].map(u =>
  fetch(u).then(r => (r.ok ? r.json() : {})).catch(() => ({}))))
  .then(tables => {
    const seen = new Map();
    for (const table of tables) for (const group of Object.values(table)) for (const s of Object.values(group || {})) {
      if (!s || !s.date) continue;
      const key = `${s.de}|${s.date}`;
      if (!seen.has(key)) seen.set(key, s);
    }
    FRESH_SOURCES = [...seen.values()].sort((a, b) => a.date.localeCompare(b.date) || a.de.localeCompare(b.de));
    window.dispatchEvent(new CustomEvent("bg:fresh"));
  });

// The attribution pin: the map's credits and the data date; a click opens the
// source list. A MapLibre control, so it sits in the map's corner like the
// stock attribution it replaces (attributionControl: false on the map).
class FreshnessControl {
  constructor(credits) { this.credits = credits; }
  onAdd(map) {
    this.map = map;
    const el = this.el = document.createElement("div");
    el.className = "maplibregl-ctrl fr-ctrl";
    const render = () => {
      const oldest = FRESH_SOURCES && FRESH_SOURCES[0] && FRESH_SOURCES[0].date;
      const level = ageLevel(oldest);
      const months = oldest ? monthsOld(oldest) : 0;
      el.innerHTML = `
        <button type="button" class="fr-pin" aria-expanded="false" aria-label="${t("fr.aria")}">
          <span class="fr-credits">${this.credits}</span>
          ${oldest ? `<span class="fr-pill fr-${level}">${t("fr.asOf")} ${freshDate(oldest)}${level !== "ok" ? ` · ${months} ${t("fr.months")}` : ""}</span>` : ""}
        </button>`;
      el.querySelector(".fr-pin").addEventListener("click", ev => { ev.stopPropagation(); this.toggle(); });
      if (this.pop) this.fill();
    };
    this.render = render;
    render();
    window.addEventListener("bg:fresh", render);
    window.addEventListener("bg:lang", render);
    document.addEventListener("click", ev => { if (this.pop && !this.pop.contains(ev.target)) this.close(); });
    document.addEventListener("keydown", ev => { if (ev.key === "Escape") this.close(); });
    return el;
  }
  onRemove() { this.el.remove(); }
  toggle() { if (this.pop) this.close(); else this.open(); }
  open() {
    const pop = this.pop = document.createElement("div");
    pop.className = "fr-pop bg-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", t("fr.aria"));
    pop.addEventListener("click", ev => ev.stopPropagation());
    document.body.appendChild(pop);
    this.fill();
    const btn = this.el.querySelector(".fr-pin");
    btn.setAttribute("aria-expanded", "true");
    const r = btn.getBoundingClientRect();
    pop.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
    pop.style.bottom = `${window.innerHeight - r.top + 8}px`;
    pop.style.maxHeight = `${Math.max(160, r.top - 16)}px`;   // all of it above the pin, scrolling inside (048)
    const first = pop.querySelector("a, button");
    if (first) first.focus();
  }
  fill() {
    const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
    const rows = (FRESH_SOURCES || []).map(s => `
      <li><a href="${esc(s.url || "#")}" target="_blank" rel="noopener">${esc(tr(s))}</a>${freshDateHtml(s.date)}</li>`).join("");
    this.pop.innerHTML = `
      <div class="fr-head"><span class="fr-title">${t("fr.sources")}</span><span class="fr-sub">${t("fr.fetched")}</span>
        <button type="button" class="bg-x" aria-label="${t("ctl.close")}">×</button></div>
      <ul class="fr-list">${rows}</ul>
      <p class="fr-rule">${t("fr.rule")} · <a href="https://maplibre.org" target="_blank" rel="noopener">MapLibre</a></p>`;
    this.pop.querySelector(".bg-x").addEventListener("click", () => this.close());
  }
  close() {
    if (!this.pop) return;
    this.pop.remove(); this.pop = null;
    const btn = this.el.querySelector(".fr-pin");
    if (btn) { btn.setAttribute("aria-expanded", "false"); }
  }
}
