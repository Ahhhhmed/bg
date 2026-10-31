/**
 * The stop card: hover a stop for its commute profile to Zürich
 * HB over a weekday; click to pin. The data is one small JSON per stop
 * (data/stops/<nr>.json, built by cities/zurich/pipeline/swiss/build_timetable.py from the
 * Swiss GTFS timetable), fetched on the first hover.
 *
 * What it shows, top to bottom:
 *   - name, modes, the lines serving the stop as badges, one colour per line
 *   - the hour picked (07:00-08:00 to start): fastest, average, slowest trip
 *     to HB in that hour (waiting at the stop included), the cycle, the mean
 *     wait at the stop (green / yellow / orange / red)
 *   - the day: travel time to HB for every minute 05:00-00:30, a sawtooth
 *     (each tooth: the wait for the next good departure, then the ride), the
 *     picked hour shaded
 *   - the picked hour as a clock: its departures as dots on a dial, in the
 *     colour of the line taken first
 *   - every connection of that hour, leg by leg
 * The pinned card (and the phone sheet) is interactive: click the day chart,
 * a part of the day or the arrows to pick the hour; the hour stays picked for
 * the next stop. The hover card lets the mouse through, so it only shows.
 * Loaded after map.js (uses its escapeHtml, placeCard, popup, ...).
 */

const STOP_DATA = new Map();     // nr -> data, a pending Promise, or null
const STOP_PROPS = new Map();    // nr -> the stop's tile properties, to redraw a pinned card
let stopHour = 7;                // the hour shown, kept from stop to stop
// minutes, as PARTS in build_timetable.py
const STOP_PARTS = { early: [300, 390], morning: [390, 540], day: [540, 960], evening: [960, 1140], night: [1140, 1470] };

// One colour per line on a card, so the badges, the clock's dots and the
// connections can be told apart (the timetable's own colours are one per
// mode: every VBZ tram orange). Categorical, in this fixed order, validated on
// the card's cream (dataviz validate_palette.js: CVD dE >= 8.8 for adjacent
// slots, normal vision >= 21.5); every badge carries its line's name too.
// The lines taken first towards HB get the first slots; past eight, a quiet
// grey by mode.
const STOP_LINE_COLORS = ["#2f6fb8", "#d9662b", "#16977a", "#cf9a00", "#c9578a", "#3f8a2a", "#6650c8", "#c43f3f"];
const STOP_MODE_FALLBACK = { train: "#8a7b70", tram: "#a3958a", bus: "#b3a69b", boat: "#8a9aa6",
                             funicular: "#a3958a", metro: "#8a7b70", cable: "#a3958a" };

function stopData(nr) {
  if (!STOP_DATA.has(nr)) {
    STOP_DATA.set(nr, fetch(`../data/stops/${nr}.json`)
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null)
      .then(d => { STOP_DATA.set(nr, d); return d; }));
  }
  return STOP_DATA.get(nr);
}

const hhmm = min => {
  const m = Math.round(min) % (24 * 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};
const fmtMin = v => (v == null ? "–" : `${LANG === "de" ? String(Math.round(v * 10) / 10).replace(".", ",") : Math.round(v * 10) / 10}`);
const fmtTakt = v => (v == null ? "–" : v === 7.5 ? "7½" : String(v));
const hourLabel = h => `${hhmm(h * 60)}–${hhmm(h * 60 + 60)}`;

const lineKey = l => `${l[1]}:${l[0]}`;
function lineSlots(o) {
  if (o._slots) return o._slots;
  const first = new Map(), order = [];
  o.legs.forEach(legs => {
    if (legs && legs.length) { const k = lineKey(o.labels[legs[0][0]]); first.set(k, (first.get(k) || 0) + 1); }
  });
  order.push(...[...first.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0]));
  for (const l of [...o.lines].sort((a, b) => b[4] - a[4])) if (!order.includes(lineKey(l))) order.push(lineKey(l));
  for (const legs of o.legs) for (const [li] of legs || []) if (!order.includes(lineKey(o.labels[li]))) order.push(lineKey(o.labels[li]));
  o._slots = new Map(order.slice(0, STOP_LINE_COLORS.length).map((k, i) => [k, STOP_LINE_COLORS[i]]));
  return o._slots;
}

function lineColors(l, o) {
  const bg = lineSlots(o).get(lineKey(l)) || STOP_MODE_FALLBACK[l[1]] || "#a3958a";
  // text on the badge: dark or white, whichever contrasts more (WCAG)
  const n = parseInt(bg.slice(1), 16);
  const lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const L = 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  return { bg, fg: 1.05 / (L + 0.05) >= (L + 0.05) / 0.068 ? "#ffffff" : "#2b2420" };
}

function lineBadge(l, o, extra = "") {
  const { bg, fg } = lineColors(l, o);
  return `<span class="sc-line sc-${l[1]}" style="background:${bg};color:${fg}"${extra}>${escapeHtml(l[0])}</span>`;
}

// Travel time to HB (min) when arriving at the stop at minute t: the wait for
// the next departure of the profile plus its ride. The profile is sorted by
// departure, and a later departure never arrives earlier.
function travelAt(o, t) {
  const i = o.dep.findIndex(d => d >= t);
  return i < 0 ? null : o.arr[i] - t;
}

// The hour's figures, exact on the sawtooth: fastest (at a departure),
// slowest (just after one), the mean over the hour, departures in it, and the
// mean wait at the stop for someone arriving at a random time in the hour
// (until the next departure of the profile: the next one worth taking to HB).
function hourStats(o, h) {
  const a = h * 60, b = a + 60;
  let i = o.dep.findIndex(d => d >= a);
  if (i < 0) return null;
  let t = a, sum = 0, wait = 0, span = 0, min = Infinity, max = -Infinity, n = 0;
  for (; i < o.dep.length && t < b; i++) {
    const d = o.dep[i], arr = o.arr[i], t1 = Math.min(d, b);
    if (t1 > t) { sum += (arr - (t + t1) / 2) * (t1 - t); wait += (d - (t + t1) / 2) * (t1 - t); span += t1 - t; }
    max = Math.max(max, arr - t);
    min = Math.min(min, arr - t1);
    if (d < b) n++;
    t = Math.max(t, t1);
  }
  return { min, max, mean: span ? sum / span : min, wait: span ? wait / span : 0, deps: n };
}

// the mean wait as a traffic light (owner, 2026-10-22): up to 3 min green,
// to 6 yellow, to 10 orange, longer red
const STOP_WAIT_CLASSES = [
  [3, "#7fbf6a", "#3f7a2e"], [6, "#f2d35a", "#a8861a"], [10, "#f0a050", "#b0621e"], [Infinity, "#e0645a", "#9e3029"],
];
const waitClass = w => STOP_WAIT_CLASSES.find(([up]) => w <= up);

function partOf(h) {
  const m = h * 60 + 30;
  return Object.keys(STOP_PARTS).find(k => m >= STOP_PARTS[k][0] && m < STOP_PARTS[k][1]) || null;
}

// the hours a card can show: inside the day chart and with departures
function hourRange(o) {
  const end = o.curve_start + o.curve.length * 2;
  const lo = Math.max(Math.floor(o.curve_start / 60), Math.floor(o.dep[0] / 60));
  const hi = Math.min(Math.floor((end - 1) / 60), Math.floor(o.dep[o.dep.length - 1] / 60));
  return [lo, Math.max(lo, hi)];
}

// The day's sawtooth: travel time (min) over 05:00-00:30, the hour shaded.
const DAY = { W: 440, H: 96, padL: 26, padB: 16, padT: 6, step: 2 };
function stopDayChart(o, hour) {
  const { W, H, padL, padB, padT, step } = DAY;
  const start = o.curve_start, span = o.curve.length * step;
  const vals = o.curve.filter(v => v != null);
  if (!vals.length) return "";
  const yMax = Math.max(15, Math.ceil(Math.min(Math.max(...vals), 90) / 15) * 15);
  const x = m => padL + (Math.min(Math.max(m, start), start + span) - start) / span * (W - padL - 4);
  const y = v => padT + (1 - Math.min(v, yMax) / yMax) * (H - padT - padB);
  let d = "", pen = false;
  o.curve.forEach((v, i) => {
    if (v == null) { pen = false; return; }
    d += `${pen ? "L" : "M"}${x(start + i * step).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  const grid = [];
  for (let v = 15; v <= yMax; v += 15) {
    grid.push(`<line x1="${padL}" x2="${W - 4}" y1="${y(v)}" y2="${y(v)}" class="sc-grid"/><text x="${padL - 4}" y="${y(v) + 3}" class="sc-axis" text-anchor="end">${v}</text>`);
  }
  const hours = [];
  for (let h = 6; h <= 24; h += 3) {
    hours.push(`<text x="${x(h * 60)}" y="${H - 3}" class="sc-axis" text-anchor="middle">${String(h % 24).padStart(2, "0")}</text>`);
  }
  const band = `<rect x="${x(hour * 60)}" y="${padT}" width="${x(hour * 60 + 60) - x(hour * 60)}" height="${H - padT - padB}" class="sc-band"/>`;
  return `<svg class="sc-day" viewBox="0 0 ${W} ${H}" data-start="${start}" data-span="${span}" data-ymax="${yMax}" role="img" aria-label="${escapeHtml(t("sc.dayAria"))}">
    ${band}${grid.join("")}${hours.join("")}
    <path d="${d}" class="sc-saw"/>
    <text x="${padL}" y="${padT + 8}" class="sc-axis">min</text>
    <g class="sc-guide"><line y1="${padT}" y2="${H - padB}"/><circle r="2.6"/><text y="${padT + 8}"></text></g>
    <rect x="${padL}" y="0" width="${W - padL - 4}" height="${H - padB}" class="sc-hit"/>
  </svg>`;
}

// One hour as a clock: departures as dots in the colour of the first line.
function stopClock(o, hour, takt) {
  const S = 132, c = S / 2, r = 50;
  const deps = [];
  o.dep.forEach((dm, i) => {
    if (dm >= hour * 60 && dm < (hour + 1) * 60 && o.legs[i] && o.legs[i].length) {
      deps.push({ min: dm - hour * 60, line: o.labels[o.legs[i][0][0]], travel: o.arr[i] - dm });
    }
  });
  const ticks = [];
  for (let m = 0; m < 60; m += 5) {
    const a = (m / 60) * 2 * Math.PI - Math.PI / 2, r1 = m % 15 ? r + 5 : r + 8;
    ticks.push(`<line x1="${c + Math.cos(a) * (r + 2)}" y1="${c + Math.sin(a) * (r + 2)}" x2="${c + Math.cos(a) * r1}" y2="${c + Math.sin(a) * r1}" class="sc-tick"/>`);
  }
  const dots = deps.map(dp => {
    const a = (dp.min / 60) * 2 * Math.PI - Math.PI / 2;
    // the faster the journey, the further out the dot (outer ring = quickest)
    const rr = r - 6 - Math.min(dp.travel, 60) / 60 * 26;
    const { bg } = lineColors(dp.line, o);
    return `<line x1="${c + Math.cos(a) * (r - 4)}" y1="${c + Math.sin(a) * (r - 4)}" x2="${c + Math.cos(a) * rr}" y2="${c + Math.sin(a) * rr}" class="sc-spoke"/>
      <circle cx="${c + Math.cos(a) * r}" cy="${c + Math.sin(a) * r}" r="4.6" fill="${bg}" class="sc-dot"><title>${hhmm(hour * 60 + dp.min)} · ${escapeHtml(dp.line[0])} · ${Math.round(dp.travel)} min</title></circle>`;
  }).join("");
  return `<svg class="sc-clock" viewBox="0 0 ${S} ${S}" role="img" aria-label="${escapeHtml(`${t("sc.clockAria")} ${hourLabel(hour)}`)}">
    <circle cx="${c}" cy="${c}" r="${r}" class="sc-face"/>
    ${ticks.join("")}${dots}
    <text x="${c}" y="${c - 2}" text-anchor="middle" class="sc-clock-big">${takt ? fmtTakt(takt) : "–"}</text>
    <text x="${c}" y="${c + 12}" text-anchor="middle" class="sc-clock-small">${escapeHtml(takt ? t("sc.minCycle") : t("sc.noCycle"))}</text>
    <text x="${c}" y="10" text-anchor="middle" class="sc-axis">${hhmm(hour * 60)}</text>
  </svg>`;
}

// Every connection departing in the hour, leg by leg.
function stopJourneys(o, hour) {
  const out = [];
  for (let i = 0; i < o.dep.length; i++) {
    if (o.dep[i] < hour * 60 || o.dep[i] >= hour * 60 + 60) continue;
    const legs = o.legs[i] || [];
    const steps = legs.map(([li, at, stop], k) => {
      const last = k === legs.length - 1;
      const where = o.stops[stop] || "";
      return `${lineBadge(o.labels[li], o)}<span class="sc-to">${escapeHtml(last && /Zürich HB$/.test(where) ? "" : `→ ${where}`)}</span>`;
    }).join('<span class="sc-chg">·</span>');
    const travel = Math.round(o.arr[i] - o.dep[i]);
    // starts at a nearby stop: "on foot 3′ to X" first
    const w = o.walk && o.walk[i];
    const walk = w ? `<span class="sc-walk">${escapeHtml(t("sc.walk"))} ≈ ${w[1]}′ → ${escapeHtml(o.stops[w[0]] || "")}</span><span class="sc-chg">·</span>` : "";
    out.push(`<li><span class="sc-time">${hhmm(o.dep[i])}</span><span class="sc-legs">${walk}${steps}</span>
      <span class="sc-arr">${hhmm(o.arr[i])} <small>${travel} min${o.ntr[i] ? ` · ${o.ntr[i]}× ${escapeHtml(t("sc.change"))}` : ""}</small></span></li>`);
  }
  return out.length ? `<ul class="sc-journeys">${out.join("")}</ul>`
    : `<div class="sc-journeys sc-nodeps">${escapeHtml(t("sc.noDeps"))}</div>`;
}

function stopCardHtml(p, o, pinned) {
  const modes = String(p.modes || "").split(",").filter(Boolean).map(m => tr(MODE_NAMES[m]) || m).join(" · ");
  const head = `<div class="hc-head">
      <div class="hc-title">${escapeHtml(p.name || "")}</div>
      <div class="hc-place">${escapeHtml(modes)}${o && o.day ? ` · ${escapeHtml(t("sc.timetable"))} ${escapeHtml(new Date(o.day).toLocaleDateString(locale(), { weekday: "short", day: "numeric", month: "short" }))}` : ""}</div>
    </div>`;
  if (o === undefined) {
    return `<div class="hover-card hc-building sc-card" data-nr="${escapeHtml(String(p.nr))}">${head}<div class="sc-loading">${escapeHtml(t("sc.loading"))}</div></div>`;
  }
  if (o === null) {
    return `<div class="hover-card hc-building sc-card" data-nr="${escapeHtml(String(p.nr))}">${head}<div class="hc-chip hc-na">${escapeHtml(t("sc.noData"))}</div></div>`;
  }
  const lines = o.lines.length
    ? `<div class="sc-lines">${o.lines.map(l => lineBadge(l, o, ` title="${escapeHtml(`${l[0]} · ${l[4]} ${t("sc.perDay")}`)}"`)).join("")}</div>` : "";
  if (o.at_hb) {
    return `<div class="hover-card hc-building sc-card" data-nr="${escapeHtml(String(p.nr))}">${head}${lines}<div class="sc-hb">${escapeHtml(t("sc.atHb"))}</div></div>`;
  }
  const [lo, hi] = hourRange(o);
  const hour = Math.max(lo, Math.min(hi, stopHour));
  const s = hourStats(o, hour) || {};
  const part = partOf(hour);
  const takt = part && o.parts[part] ? o.parts[part].takt : null;
  const fig = (v, label) => `<div class="hc-fig"><strong>${v}</strong><span>${escapeHtml(label)}</span></div>`;
  const commute = modeClass("commute", { commute_hb_min: s.mean });
  const parts = Object.keys(STOP_PARTS).map(k => {
    const ps = o.parts[k] || {};
    const h0 = Math.max(lo, Math.min(hi, Math.ceil(STOP_PARTS[k][0] / 60)));
    return `<button type="button" class="sc-part${k === part ? " sc-on" : ""}" data-hour="${h0}"${pinned ? "" : ' tabindex="-1"'}><span>${escapeHtml(t(`sc.part.${k}`))}</span>
      <b>${ps.mean != null ? `${fmtMin(ps.mean)}′` : "–"}</b><small>${ps.takt ? `${escapeHtml(t("sc.cycle"))} ${fmtTakt(ps.takt)}′` : escapeHtml(ps.mean != null ? t("sc.irregular") : t("sc.none"))}</small></button>`;
  }).join("");
  const arrow = (dir, to, label) => `<button type="button" class="sc-step" data-hour="${to}" aria-label="${escapeHtml(t(label))}"${to < lo || to > hi ? " disabled" : ""}${pinned ? "" : ' tabindex="-1"'}>${dir}</button>`;
  // the sources with their dates (C-05, cities/zurich/pipeline/card_sources.py), linked on the pinned card
  const foot = [o.feed_station ? escapeHtml(`${t("sc.feedStation")} ${o.feed_station}`) : null,
    cardSourcesHtml("stop", pinned) || escapeHtml(t("sc.source")), escapeHtml(t("sc.walkModel"))].filter(Boolean).join(" · ");
  return `<div class="hover-card hc-building sc-card${pinned ? " sc-live" : ""}" data-nr="${escapeHtml(String(o.nr))}">
    ${head}${lines}
    <div class="sc-sel">
      ${arrow("‹", hour - 1, "sc.prevHour")}<strong>${hourLabel(hour)}</strong>${arrow("›", hour + 1, "sc.nextHour")}
      <span class="hc-quiet-text">${escapeHtml(t(pinned ? "sc.pickHint" : "sc.pinToPick"))}</span>
    </div>
    <div class="hc-figures">
      ${fig(s.min != null ? `${fmtMin(s.min)}′` : "–", t("sc.fastest"))}
      <div class="hc-fig hc-tinted"${commute ? ` style="--c:${commute.color};--o:${commute.outline}"` : ""}><strong>${s.mean != null ? `${fmtMin(s.mean)}′` : "–"}</strong><span>${escapeHtml(t("sc.average"))}</span></div>
      ${fig(s.max != null ? `${fmtMin(s.max)}′` : "–", t("sc.slowest"))}
      ${fig(takt ? `${fmtTakt(takt)}′` : "–", t("sc.cycle"))}
      ${s.wait != null ? (([, c, ol]) => `<div class="hc-fig hc-tinted" style="--c:${c};--o:${ol}" title="${escapeHtml(t("sc.waitHint"))}"><strong>${fmtMin(s.wait)}′</strong><span>${escapeHtml(t("sc.wait"))}</span></div>`)(waitClass(s.wait)) : fig("–", t("sc.wait"))}
    </div>
    <div class="sc-row">
      <div class="sc-daybox"><div class="hc-cap"><span>${escapeHtml(t("sc.day"))}</span><span class="hc-aside hc-quiet-text">${escapeHtml(t("sc.dayHint"))}</span></div>${stopDayChart(o, hour)}
        <div class="sc-parts">${parts}</div></div>
      <div class="sc-clockbox"><div class="hc-cap"><span>${escapeHtml(t("sc.clock"))}</span></div>${stopClock(o, hour, takt)}</div>
    </div>
    <div class="hc-cap sc-jcap"><span>${escapeHtml(t("sc.journeys"))} ${hourLabel(hour)}</span></div>
    ${stopJourneys(o, hour)}
    <div class="hc-foot pc-sources">${foot}</div>
  </div>`;
}

// hover / pin, sharing the building card's popup, placement and phone sheet
let hoveredStop = null;
function showStopCard(e, pinned) {
  if (!e.features.length) return;
  const f = e.features[0], p = f.properties, nr = String(p.nr);
  const lngLat = { lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] };
  map.getCanvas().style.cursor = "pointer";
  if (!pinned && (pinnedCard.isOpen() || sheet || isNarrow())) return;
  if (!pinned && popup.isOpen() && hoveredStop === nr) return;
  hoveredStop = pinned ? null : nr;
  hoveredEgid = null;
  STOP_PROPS.set(nr, p);
  const card = pinned ? pinnedCard : popup;
  const draw = o => {
    const html = stopCardHtml(p, o, pinned);
    if (pinned && isNarrow()) openSheet(html, lngLat);
    else { card.options.anchor = "top-left"; placeCard(card, lngLat, html); }
  };
  if (pinned) { pinnedAt = performance.now(); popup.remove(); }
  const cached = STOP_DATA.get(nr);
  if (cached && typeof cached.then !== "function") { draw(cached); return; }
  draw(undefined);
  stopData(nr).then(o => {
    // only the card of this stop: the pinned card / sheet may show another one by now
    const host = pinned ? (sheet || (pinnedCard.isOpen() && pinnedCard.getElement())) : (hoveredStop === nr && popup.getElement());
    if (host && host.querySelector(`.sc-card[data-nr="${nr}"]`)) draw(o);
  });
}
for (const id of ["place-stops", "place-stops-hub"]) {
  map.on("mousemove", id, e => showStopCard(e, false));
  map.on("click", id, e => { e.originalEvent && e.originalEvent.stopPropagation(); showStopCard(e, true); });
  map.on("mouseleave", id, () => { hoveredStop = null; });
}

// The pinned card picks its hour: redrawn in place (the connection list has a
// fixed height, so the card keeps its size and its place).
function pickStopHour(cardEl, hour) {
  const nr = cardEl.dataset.nr, o = STOP_DATA.get(nr), p = STOP_PROPS.get(nr);
  if (!o || typeof o.then === "function" || !p) return;
  const [lo, hi] = hourRange(o);
  stopHour = Math.max(lo, Math.min(hi, hour));
  cardEl.outerHTML = stopCardHtml(p, o, true);
}
function dayChartMinute(svg, e) {
  const box = svg.getBoundingClientRect();
  const vx = (e.clientX - box.left) / box.width * DAY.W;
  const f = (vx - DAY.padL) / (DAY.W - DAY.padL - 4);
  return f < 0 || f > 1 ? null : +svg.dataset.start + f * +svg.dataset.span;
}
document.addEventListener("click", e => {
  const card = e.target.closest && e.target.closest(".sc-live");
  if (!card) return;
  const btn = e.target.closest("button[data-hour]");
  if (btn) { pickStopHour(card, +btn.dataset.hour); return; }
  const svg = e.target.closest(".sc-day");
  if (svg) {
    const m = dayChartMinute(svg, e);
    if (m != null) pickStopHour(card, Math.floor(m / 60));
  }
});
// a guide on the pinned card's day chart: the time under the pointer and the
// travel time to HB from then
document.addEventListener("mousemove", e => {
  const svg = e.target.closest && e.target.closest(".sc-live .sc-day");
  document.querySelectorAll(".sc-guide.sc-on").forEach(g => { if (!svg || !svg.contains(g)) g.classList.remove("sc-on"); });
  if (!svg) return;
  const o = STOP_DATA.get(svg.closest(".sc-live").dataset.nr), m = dayChartMinute(svg, e);
  const g = svg.querySelector(".sc-guide");
  const v = m == null || !o || typeof o.then === "function" ? null : travelAt(o, m);
  if (v == null) { g.classList.remove("sc-on"); return; }
  const { W, H, padL, padB, padT } = DAY, yMax = +svg.dataset.ymax;
  const x = padL + (m - +svg.dataset.start) / +svg.dataset.span * (W - padL - 4);
  const y = padT + (1 - Math.min(v, yMax) / yMax) * (H - padT - padB);
  for (const k of ["x1", "x2"]) g.querySelector("line").setAttribute(k, x);
  g.querySelector("circle").setAttribute("cx", x);
  g.querySelector("circle").setAttribute("cy", y);
  const label = g.querySelector("text"), flip = x > W - 70;
  label.textContent = `${hhmm(m)} · ${Math.round(v)}′`;
  label.setAttribute("x", flip ? x - 4 : x + 4);
  label.setAttribute("text-anchor", flip ? "end" : "start");
  g.classList.add("sc-on");
});
