/**
 * The search profile's criteria (C-10): any lens, every place
 * kind on foot, plus two extras (housing only, the shelter), each "filter"
 * (buildings outside it fade or hide) or "mark only" (an outline). One rule
 * per criterion, used three ways so they always agree:
 *   critExpr()   the MapLibre expression the building layers fade / hide by
 *   critPass()   the same test in JS, for a building's card and the counts
 *   the counts   over /data/profile_table.json (shared/pipeline/profile_table.py):
 *                every housing building's values, so a count covers the whole
 *                area, not what is in view (the owner: count the homes)
 *
 * A criterion: { id, mark, lo, hi, miss, cls }
 *   id    a lens id (`commute`, `walk_kita`, `noise_road_n`, `hazard`, ...)
 *         or an extra (`housing`, `shelter`)
 *   mark  true = mark only (outline), false = filter
 *   range lenses (numbers): lo / hi in the shown unit (minutes, dB, year,
 *         floors); a handle at the scale's end means open on that side;
 *         miss = buildings without a value pass too
 *   class lenses: cls = the allowed class indices (into the lens's
 *         classes), "n" = no value / no class
 * In the URL: ?f=<crit>,<crit>,... with <crit> = [~]<id>[:<spec>] (~ = mark
 * only); range spec "lo-hi" (either side empty = open) + "n" if a missing
 * value passes, class spec the allowed indices joined by "." (+ "n").
 * Examples: commute:-30 · walk_kita:-5 · noise_road_n:-45 · heating:1.2.3.4.5.6
 * Old links (?housing ?years ?noise ?walk ?marks) are translated by fromOldParams().
 */

// The scale of each range lens: the shown unit, its ends and step, the factor
// to the stored value (walks: metres = minutes x 80), the value a new
// criterion starts with (the owner's "Zum HB <= 30'") and, for lenses where a
// missing value means "the lowest" (rail noise: no rail nearby; aircraft:
// below 58 dB), that it counts as the lowest.
const PROFILE_RANGES = {
  year: { prop: "baujahr", min: 1900, max: 2030, step: 5, unit: "", int: true, bins: 26 },
  commute: { prop: "commute_hb_min", min: 0, max: 60, step: 1, unit: "′", int: true, hi: 30, bins: 12 },
  walk: { min: 0, max: 20, step: 1, unit: "′", factor: WALK_M_PER_MIN, hi: 10, bins: 20 },
  noise_road: { min: 30, max: 70, step: 1, unit: " dB", hi: 50, bins: 16 },
  noise_rail: { min: 30, max: 70, step: 1, unit: " dB", hi: 45, bins: 16, missingIsLowest: true },
  aircraft: { prop: "aircraft_db", min: 57, max: 70, step: 1, unit: " dB", int: true, hi: 60, bins: 13, missingIsLowest: true, firstLo: 58 },
  floors: { prop: "floors", min: 1, max: 12, step: 1, unit: "", int: true, bins: 12 },
  dwellings: { prop: "num_dwellings", min: 1, max: 40, step: 1, unit: "", int: true, bins: 20 },
};

// The extras: criteria that aren't a lens (`pass` gets a getter: prop => value)
const PROFILE_EXTRAS = [
  { id: "housing", label: { de: "Nur Wohngebäude", en: "Housing only" },
    expr: IS_RESIDENTIAL, pass: get => isHousing(get) },
  { id: "shelter", label: { de: "Mit Zivilschutzraum", en: "With a civil-defence shelter" }, mark: true,
    expr: ["==", ["get", "civil_defense_shelter"], 1], pass: get => Number(get("civil_defense_shelter")) === 1 },
];
const inLang = (x, lang) => (typeof x === "string" ? x : x[lang]);

// What a criterion is about: { id, kind: "range" | "class" | "extra", mode, variant, prop, label, ... }
// (kept per id: the counts ask for it once per home and criterion)
const CRIT_SPECS = new Map();
function critSpec(id) {
  if (!CRIT_SPECS.has(id)) CRIT_SPECS.set(id, makeCritSpec(id));
  return CRIT_SPECS.get(id);
}
function makeCritSpec(id) {
  const ex = PROFILE_EXTRAS.find(e => e.id === id);
  if (ex) return { id, kind: "extra", label: ex.label, extra: ex };
  const sel = colorMode(id);
  if (!sel) return null;
  const { mode: m, variant: v } = sel;
  const label = v ? Object.fromEntries(["de", "en"].map(l => [l, `${inLang(m.label, l)} · ${inLang(v.label, l)}`])) : m.label;
  // walks: the place, not "On foot · ..." (the owner's "Kita <= 5'")
  const short = m.id === "walk" ? v.label : label;
  const r = PROFILE_RANGES[m.id];
  if (r) return { id, kind: "range", mode: m, variant: v, label, short, ...r, prop: r.prop || (v || m).prop, factor: r.factor || 1 };
  if (m.classes) return { id, kind: "class", mode: m, variant: v, label, short, prop: m.prop, classes: m.classes };
  return null;
}

// a new criterion for a lens, with its scale's start values (everything
// allowed for a class lens: the owner strikes what doesn't suit)
function newCrit(id, mark) {
  const s = critSpec(id);
  if (!s) return null;
  const c = { id, mark: !!(mark != null ? mark : s.kind === "extra" && s.extra.mark) };
  if (s.kind === "range") {
    c.lo = s.lo != null ? s.lo : s.min;
    c.hi = s.hi != null ? s.hi : s.max;
    c.miss = false;
  } else if (s.kind === "class") {
    c.cls = new Set([...s.classes.map((_, i) => i), "n"]);
  }
  return c;
}

// --- the test, as an expression and in JS (keep the two in step) ---
function critExpr(c) {
  const s = critSpec(c.id);
  if (s.kind === "extra") return s.extra.expr;
  if (s.kind === "range") {
    const v = ["to-number", ["get", s.prop]];
    const parts = [];
    if (c.lo > s.min) parts.push([">=", v, c.lo * s.factor]);
    if (c.hi < s.max) parts.push(["<=", v, c.hi * s.factor]);
    const inRange = parts.length ? ["all", ...parts] : true;
    // a missing value: the lowest (passes if the low end is open), or as chosen
    const missing = s.missingIsLowest ? c.lo <= s.min : !!c.miss;
    return ["case", ["==", ["get", s.prop], null], missing, inRange];
  }
  // class lens: the values of the allowed classes; "n" = a value in no class (or none)
  const all = s.classes.flatMap(k => k.values);
  const allowed = s.classes.flatMap((k, i) => (c.cls.has(i) ? k.values : []));
  const value = ["coalesce", ["get", s.prop], ""];
  if (c.cls.has("n")) {
    const banned = all.filter(x => !allowed.includes(x));
    return banned.length ? ["match", value, banned, false, true] : true;
  }
  return allowed.length ? ["match", value, allowed, true, false] : false;
}

// p: a building's properties, or a getter (prop => value) for the table
function critPass(c, p) {
  const s = critSpec(c.id);
  const get = typeof p === "function" ? p : k => p[k];
  if (s.kind === "extra") return s.extra.pass(get);
  const raw = get(s.prop);
  if (s.kind === "range") {
    if (raw === null || raw === undefined || raw === "") return s.missingIsLowest ? c.lo <= s.min : !!c.miss;
    const v = Number(raw);
    return (c.lo <= s.min || v >= c.lo * s.factor) && (c.hi >= s.max || v <= c.hi * s.factor);
  }
  const i = raw == null ? -1 : s.classes.findIndex(k => k.values.includes(raw));
  return c.cls.has(i < 0 ? "n" : i);
}

// the expression for a list of criteria (null = none): all of them
function critsExpr(list) {
  list = list.filter(c => critSpec(c.id).kind === "extra" || lensCoverage(c.id).state !== "none");   // no data here: doesn't filter
  if (!list.length) return null;
  const parts = list.map(critExpr);
  return parts.length === 1 ? parts[0] : ["all", ...parts];
}

// --- what a criterion says, in words ---
const fmtCount = n => Number(n).toLocaleString(locale());
function rangeText(c, s) {
  const u = s.unit, lo = c.lo > s.min, hi = c.hi < s.max;
  if (lo && hi) return c.lo === c.hi ? `${c.lo}${u}` : `${c.lo} – ${c.hi}${u}`;
  if (hi) return `≤ ${c.hi}${u}`;
  if (lo) return `≥ ${c.lo}${u}`;
  return t("pf.any");
}
// "Heizung: ohne Heizöl" / "Naturgefahren: gering (gelb), Restgefährdung"
function classText(c, s) {
  const miss = tr(s.mode.missing || { de: "keine Angabe", en: "no data" });
  // the "no value" class in quotes when left out: "ohne „nicht beurteilt“", not "ohne nicht beurteilt"
  const names = (i, out) => (i === "n" ? (out ? t("pf.quote").replace("%s", miss) : miss) : tr(s.classes[i].label));
  const keys = [...s.classes.map((_, i) => i), "n"];
  const on = keys.filter(k => c.cls.has(k)), off = keys.filter(k => !c.cls.has(k));
  if (!off.length) return t("pf.any");
  if (!on.length) return t("pf.none");
  return off.length <= on.length ? `${t("pf.without")} ${off.map(k => names(k, true)).join(", ")}` : on.map(k => names(k, false)).join(", ");
}
function critText(c) {
  const s = critSpec(c.id);
  if (s.kind === "extra") return tr(s.label);
  return s.kind === "range" ? `${tr(s.short)} ${rangeText(c, s)}` : `${tr(s.short)}: ${classText(c, s)}`;
}
// a building's own value for the criterion, as the card shows it
function critValue(c, p) {
  const s = critSpec(c.id);
  if (s.kind === "extra") return c.id === "shelter" ? (Number(p.civil_defense_shelter) === 1 ? t("pf.yes") : t("pf.no")) : "";
  const raw = p[s.prop];
  if (raw === null || raw === undefined || raw === "") return tr(s.mode.missing || { de: "keine Angabe", en: "no data" });
  if (s.kind === "range") {
    const v = Number(raw) / s.factor;
    return `${s.factor === 1 ? (Number.isInteger(v) ? v : v.toFixed(0)) : Math.max(1, Math.round(v))}${s.unit}`;
  }
  const k = s.classes.find(x => x.values.includes(raw));
  return k ? tr(k.label) : tr(s.mode.missing || { de: "keine Angabe", en: "no data" });
}

// --- the URL ---
function critToParam(c) {
  const s = critSpec(c.id);
  let spec = "";
  if (s.kind === "range") spec = `${c.lo > s.min ? c.lo : ""}-${c.hi < s.max ? c.hi : ""}${c.miss && !s.missingIsLowest ? "n" : ""}`;
  else if (s.kind === "class") spec = [...s.classes.map((_, i) => i), "n"].filter(k => c.cls.has(k)).join(".");
  const dflt = s.kind === "extra" && !!s.extra.mark;
  return `${c.mark !== dflt ? "~" : ""}${c.id}${s.kind === "extra" ? "" : `:${spec}`}`;
}
function critFromParam(str) {
  const m = /^(~?)([a-z_]+)(?::(.*))?$/.exec(str.trim());
  if (!m) return null;
  const s = critSpec(m[2]);
  if (!s) return null;
  const c = newCrit(m[2]);
  if (m[1]) c.mark = !c.mark;
  const spec = m[3] || "";
  if (s.kind === "range") {
    const r = /^(\d*)-(\d*)(n?)$/.exec(spec);
    if (!r) return c;
    const clamp = v => Math.max(s.min, Math.min(s.max, Number(v)));
    c.lo = r[1] === "" ? s.min : clamp(r[1]);
    c.hi = r[2] === "" ? s.max : clamp(r[2]);
    if (c.lo > c.hi) [c.lo, c.hi] = [c.hi, c.lo];
    c.miss = r[3] === "n";
  } else if (s.kind === "class" && m[3] !== undefined) {
    c.cls = new Set(spec.split(".").filter(Boolean).map(k => (k === "n" ? "n" : Number(k))).filter(k => k === "n" || (k >= 0 && k < s.classes.length)));
  }
  return c;
}
const critsFromParam = v => (v || "").split(",").map(critFromParam).filter(Boolean);
const critsToParam = list => list.map(critToParam).join(",");

// The filters of 043 (?housing=1 ?years=0-3 ?noise=50 ?walk=kg:10 ?marks=s)
// as criteria: the same buildings match as before
function fromOldParams(params) {
  const out = [];
  if (params.get("housing") === "1") out.push(newCrit("housing"));
  const y = /^(\d)-(\d)$/.exec(params.get("years") || "");
  if (y) {
    const last = YEAR_GROUPS.length - 1, a = Math.min(+y[1], last), b = Math.min(Math.max(+y[2], +y[1]), last);
    if (a > 0 || b < last) {
      // the year groups as a range of years; the old filter left buildings without a year out
      const c = newCrit("year"), s = critSpec("year");
      c.lo = a > 0 ? YEAR_GROUPS[a].from : s.min;
      c.hi = b < last ? YEAR_GROUPS[b].to : s.max;
      c.miss = false;
      out.push(c);
    }
  }
  const noise = Number(params.get("noise"));
  if (BUILDING_NOISE_STEPS.includes(noise)) {
    const c = newCrit("noise_road_d");
    c.lo = critSpec("noise_road_d").min; c.hi = noise; c.miss = true;   // a building without a value passed
    out.push(c);
  }
  const [kind, min] = (params.get("walk") || "").split(":");
  if (WALK_KINDS.some(k => k.id === kind) && WALK_FILTER_MIN.includes(Number(min))) {
    const c = newCrit(`walk_${kind}`);
    c.lo = 0; c.hi = Number(min);
    out.push(c);
  }
  if ((params.get("marks") || "").includes("s")) out.push(newCrit("shelter", true));
  return out;
}

// A legend class as a criterion: that class only (range lenses: its bounds)
function critForClass(lensId, index) {
  const s = critSpec(lensId);
  if (!s) return null;
  const c = newCrit(lensId);
  if (s.kind === "class") { c.cls = new Set([index]); return c; }
  if (lensId === "year") {
    const g = YEAR_GROUPS[index];
    c.lo = g.from != null ? g.from : s.min; c.hi = g.to != null ? g.to : s.max;
    return c;
  }
  // a step class is [step, next step): whole numbers end one below the next
  // step (commute 20 - 30 = 20 .. 29), measured ones at it (noise 45 - 50 dB)
  const steps = (s.variant || s.mode).steps.map(x => x / s.factor);
  c.lo = index > 0 ? Math.max(s.min, steps[index - 1]) : (s.firstLo || s.min);
  c.hi = index < steps.length ? Math.min(s.max, steps[index] - (s.int ? 1 : 0)) : s.max;
  c.miss = false;
  return c;
}

// --- the table and the counts ---
let PROFILE_TABLE = null, profileTableLoading = null;
function loadProfileTable() {
  if (PROFILE_TABLE) return Promise.resolve(PROFILE_TABLE);
  if (!profileTableLoading) {
    profileTableLoading = fetch("../data/profile_table.json")
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => {
        // dictionary-coded text columns back to values
        for (const [k, v] of Object.entries(d.cols)) if (v && v.dict) d.cols[k] = v.codes.map(i => (i < 0 ? null : v.dict[i]));
        PROFILE_TABLE = d;
        return d;
      })
      .catch(e => { profileTableLoading = null; throw e; });
  }
  return profileTableLoading;
}

// The funnel over the housing: { total, left: [after each filter criterion,
// in order; mark criteria: of the matching ones, how many it marks], match }
function profileCounts(list) {
  const d = PROFILE_TABLE;
  if (!d) return null;
  const n = d.n, cols = d.cols;
  let i = 0;
  const get = k => (cols[k] ? cols[k][i] : (k === "building_category" ? 1020 : null));   // every row is housing
  const filters = list.filter(c => !c.mark), marks = list.filter(c => c.mark);
  const left = list.map(() => 0);
  let match = 0;
  for (i = 0; i < n; i++) {
    let ok = true;
    for (let j = 0; j < list.length && ok; j++) {
      const c = list[j];
      if (c.mark) continue;
      if (!critPass(c, get)) ok = false;
      else left[j]++;
    }
    if (!ok) continue;
    match++;
    for (let j = 0; j < list.length; j++) if (list[j].mark && critPass(list[j], get)) left[j]++;
  }
  return { total: n, left, match, filters: filters.length, marks: marks.length };
}

// The distribution of all housing over a range criterion's scale (the bars
// behind its handles): counts per bin, the last bin "and more", the first
// "and less"; `missing`: the homes without a value
function profileHistogram(c) {
  const d = PROFILE_TABLE, s = critSpec(c.id);
  if (!d || s.kind !== "range") return null;
  const col = d.cols[s.prop], bins = new Array(s.bins).fill(0), w = (s.max - s.min) / s.bins;
  let missing = 0;
  for (const raw of col) {
    if (raw === null || raw === undefined) { missing++; continue; }
    const v = raw / s.factor;
    bins[Math.max(0, Math.min(s.bins - 1, Math.floor((v - s.min) / w)))]++;
  }
  return { bins, w, missing };
}
