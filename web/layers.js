/**
 * The map's layer stack (index.html, map.js): every layer, its group and
 * its lens, for every city.
 *
 * Look: a quiet base (land, forest, parks, lake, roads, tracks) so the housing
 * carries the colour: residential buildings in the year shades (web/years.js),
 * other buildings in a pale neutral, buildings in development in an ochre
 * "construction" accent (C-08). Roads use a
 * casing hierarchy whose widths grow exponentially with zoom (research report
 * docs/research/map-rendering.md §6.2). Trains and trams are told apart by
 * pattern, not colour: a red track would be read as a 1950-1989 building.
 *
 * Every toggleable layer carries metadata {"bg:group": <group>}; the layer
 * map menu (web/controls.js) switches whole groups on and off.
 */

// --- buildings: shared constants (also used by map.js for hover / filters) ---

// Underground buildings (AV "unterirdisches_Gebaeude": garages, shelters under
// gardens / courtyards) have a real cadastral outline but aren't visible on the
// ground or on swisstopo's basemap: drawn faintly, never extruded.
const ABOVE_GROUND = ["!=", ["get", "underground"], true];
const UNDERGROUND_FADE = (faded, normal) => ["case", ABOVE_GROUND, normal, faded];

// Not built yet (GWR status 1001 projektiert, 1002 bewilligt, 1003 im Bau):
// dashed outline, lighter fill, no 3D extrusion.
const UNFINISHED_STATUS = {
  1001: { de: "Geplant", en: "Planned" },
  1002: { de: "Bewilligt", en: "Approved" },
  1003: { de: "Im Bau", en: "Under construction" },
};
const IS_UNFINISHED = ["in", ["get", "building_status"], ["literal", [1001, 1002, 1003]]];
const NOT_UNFINISHED = ["!", IS_UNFINISHED];

// Housing (GWR building category 1010-1040: residential, also with other uses)
// gets the year shades; everything else (no housing, special buildings) fades
// to a pale neutral that still reads as a building (C-08).
// housing (C-08): Zürich: GWR category 1010-1040; Belgrade: OSM's residential
// building types, and buildings OSM only calls "building" (unknown use; web/city.js)
const IS_RESIDENTIAL = CITY.housing === "osm"
  ? ["!=", ["coalesce", ["get", "housing"], 1], 0]
  : ["in", ["get", "building_category"], ["literal", [1010, 1020, 1030, 1040]]];
const isHousing = get => (CITY.housing === "osm" ? Number(get("housing") ?? 1) !== 0 : [1010, 1020, 1030, 1040].includes(Number(get("building_category"))));

// What this city has (web/city.js CITY.coverage): a lens / place layer is
// "full" unless listed; "none" = no open source here, "partial" = a share of
// the buildings. The map keeps every lens and block and says so (owner, 2026-10-27).
const coverageOf = (kind, id) => ((CITY.coverage || {})[kind] || {})[id] || { state: "full" };
// a variant (walk_kita) can be missing while its lens has data: the variant's entry first
const lensCoverage = lensId => {
  const sel = colorMode(lensId), own = ((CITY.coverage || {}).lens || {})[lensId];
  return own || coverageOf("lens", sel ? sel.mode.id : lensId);
};
const cardUnavailable = key => ((CITY.coverage || {}).card || []).includes(key);
// a coverage text with the city's name (and a partial lens's share and source)
const covText = (key, cov) => t(key).replace("{city}", tr(CITY.name))
  .replace("{share}", cov && cov.share != null ? `${Math.round(cov.share * 100)} %` : "").replace("{source}", (cov && cov.source) || "");
const BUILDING = {
  otherFill: "#ece7e0",     // no housing: pale greige, a step above the oat land
  otherLine: "#c2b8ad",
  devFill: "#f4dfb2",       // in development (planned / approved / under construction): ochre accent
  devLine: "#a8741f",       // "construction" ochre: not a year shade, not a base colour
};
// fill and outline per building: development first, then housing by year, else neutral
// (the year mode; the sidebar restyles for the other colour modes, see modeFill)
const buildingFill = () => ["case", IS_UNFINISHED, BUILDING.devFill, IS_RESIDENTIAL, yearColorExpression(), BUILDING.otherFill];
const buildingLine = () => ["case", IS_RESIDENTIAL, yearOutlineExpression(), BUILDING.otherLine];

// Each building layer's own filter; map.js ANDs the era filter onto it.
const BUILDING_LAYER_FILTERS = {
  "buildings-2d": null,
  "buildings-2d-stroke": NOT_UNFINISHED,
  "buildings-2d-unfinished": IS_UNFINISHED,
  "buildings-3d": ["all", ABOVE_GROUND, NOT_UNFINISHED],
};

// --- the controls (web/controls.js; tiers C-09, lenses C-10) ---
// The map is built in tiers, each with its own visual channel, so different
// facts never fight over one colour:
//   1 buildings   the main theme: ONE fill colour mode at a time (+ legend);
//                 outline marks (dashed = in development) can combine
//   2 ground      area themes tinted under the buildings: pick ONE (or none)
//   3 places      point icons, told apart by symbol: any number on at once
//   4 base map    quiet context, on / off per group
// New layers register here (and get a "bg:group" if they're switchable).
// Labels are { de, en } (web/i18n.js).

// Building fill colour modes; the first is the default (C-09). Each mode
// colours the housing by one property, in four shades of one hue, lighter =
// less (noise: seven steps from pale yellow to deep red on ONE dB scale for
// day and night, so switching compares like with like; heating: one hue per
// energy source, fossil ones warm), with a deeper
// outline per class; buildings without housing and buildings in development
// keep their C-08 look in every mode, housing without a value gets the
// no-data greige. Kinds:
//   steps:   numeric `prop`, class i from steps[i-1] on (labels from `labels`)
//   classes: categorical `prop`, value -> class (`values`)
// `variants` (e.g. day / night) are sub-modes, id `<mode>_<variant>`.
// `fact` names the hover-card row the mode highlights (map.js).
// Colours: scripts/check_mode_colours.py (dE >= 20 between classes, also
// colour-blind; outlines >= 3:1 on the oat land; darker = more).
// Walking distance to the nearest place of a kind (build_walk.py): w_<id> metres along roads and paths, n_<id> the
// place (its position in /data/places_index.json). One list for the colour
// mode's variants, the filter and the building card's "nearby" list.
const WALK_KINDS = [
  { id: "kg", label: { de: "Kindergarten", en: "Kindergarten" } },
  { id: "kita", label: { de: "Kita", en: "Day care" } },
  { id: "sch", label: { de: "Schule", en: "School" } },
  { id: "stop", label: { de: "Haltestelle", en: "Stop" } },
  { id: "sup", label: { de: "Supermarkt", en: "Supermarket" } },
  { id: "post", label: { de: "Post", en: "Post office" } },
  { id: "doc", label: { de: "Arztpraxis", en: "Doctor" } },
  { id: "pha", label: { de: "Apotheke", en: "Pharmacy" } },
  { id: "play", label: { de: "Spielplatz", en: "Playground" } },
  { id: "bath", label: { de: "Baden", en: "Swimming" } },
  { id: "er", label: { de: "Notfallstation", en: "Emergency" } },
];
const WALK_M_PER_MIN = 80;          // the card's minutes: metres / 80, an estimate
const WALK_FILTER_MIN = [5, 10, 15];

const BUILDING_COLOR_MODES = [
  { id: "year", label: { de: "Baujahr", en: "Year built" }, fact: "hc.built",
    legendTitle: { de: "Wohngebäude nach Baujahr", en: "Residential buildings by year built" } },
  { id: "commute", label: { de: "Zürich HB", en: "To Zürich HB" }, fact: "hc.commute", prop: "commute_hb_min", steps: [20, 30, 40],
    // build_walk.py: walk to the best stop + its mean morning trip from the timetable profiles
    legendTitle: { de: "Zum Zürich HB, werktags 6:30–9 Uhr im Mittel (Fussweg, Warten, Fahrt)",
                   en: "To Zürich HB, weekdays 6:30–9:00 on average (walk, wait, ride)" },
    labels: ["< 20 min", "20 – 30", "30 – 40", "≥ 40"],
    colors: ["#dfe0fb", "#9fa7e8", "#6372bd", "#354176"], outlines: ["#7579a2", "#5c6dbb", "#023e91", "#00134e"] },
  { id: "walk", label: { de: "Zu Fuss", en: "On foot" }, fact: "hc.near",
    legendTitle: { de: "Fussweg zum nächsten Ort (≈ 80 m/min, Strassen und Wege)",
                   en: "Walk to the nearest place (≈ 80 m/min, roads and paths)" },
    variants: WALK_KINDS.map(k => ({ id: k.id, label: k.label, prop: `w_${k.id}`, steps: [400, 800, 1200],
      labels: ["≤ 5′", "5 – 10′", "10 – 15′", "> 15′"] })),
    colors: ["#d2eee9", "#60baaf", "#13857b", "#004e47"], outlines: ["#728b87", "#0b786e", "#00584f", "#00302a"] },
  { id: "noise_road", label: { de: "Strassenlärm", en: "Road noise" }, fact: "hc.roadNoise",
    legendTitle: { de: "Strassenlärm an der Fassade (BAFU)", en: "Road noise at the façade (BAFU)" },
    variants: [
      { id: "d", label: { de: "Tag", en: "Day" }, prop: "noise_road_day_db", steps: [40, 45, 50, 55, 60, 65],
        labels: ["< 40 dB", "40 – 45", "45 – 50", "50 – 55", "55 – 60", "60 – 65", "≥ 65"] },
      { id: "n", label: { de: "Nacht", en: "Night" }, prop: "noise_road_night_db", steps: [40, 45, 50, 55, 60, 65],
        labels: ["< 40 dB", "40 – 45", "45 – 50", "50 – 55", "55 – 60", "60 – 65", "≥ 65"] },
    ],
    colors: ["#fff1c1", "#fdd98a", "#f8b562", "#ee8b4c", "#d9603f", "#b03a45", "#73203d"], outlines: ["#897c43", "#97781b", "#ad6e01", "#b14e00", "#9c1900", "#770013", "#41000d"] },
  { id: "noise_rail", label: { de: "Bahnlärm", en: "Rail noise" }, fact: "hc.railNoise", missingIsLowest: true,
    legendTitle: { de: "Bahnlärm an der Fassade (BAFU)", en: "Rail noise at the façade (BAFU)" },
    variants: [
      { id: "d", label: { de: "Tag", en: "Day" }, prop: "noise_rail_day_db", steps: [40, 45, 50, 55, 60, 65],
        labels: ["< 40 dB", "40 – 45", "45 – 50", "50 – 55", "55 – 60", "60 – 65", "≥ 65"] },
      { id: "n", label: { de: "Nacht", en: "Night" }, prop: "noise_rail_night_db", steps: [40, 45, 50, 55, 60, 65],
        labels: ["< 40 dB", "40 – 45", "45 – 50", "50 – 55", "55 – 60", "60 – 65", "≥ 65"] },
    ],
    colors: ["#fff1c1", "#fdd98a", "#f8b562", "#ee8b4c", "#d9603f", "#b03a45", "#73203d"], outlines: ["#897c43", "#97781b", "#ad6e01", "#b14e00", "#9c1900", "#770013", "#41000d"] },
  { id: "heating", label: { de: "Heizung", en: "Heating" }, fact: "hc.heating", prop: "heating_class",
    legendTitle: { de: "Heizung nach Energieträger (GWR)", en: "Heating by energy source (GWR)" },
    classes: [
      { values: ["oil"], color: "#8c3b2c", outline: "#5c0c00", label: { de: "Heizöl", en: "Oil" } },
      { values: ["gas"], color: "#eb9a5c", outline: "#a7602b", label: "Gas" },
      { values: ["electric"], color: "#7d7d7d", outline: "#4a4a4a", label: { de: "Strom direkt", en: "Electric" } },
      { values: ["wood"], color: "#7fa87a", outline: "#3e713b", label: { de: "Holz", en: "Wood" } },
      { values: ["district"], color: "#684671", outline: "#370f44", label: { de: "Fernwärme", en: "District heating" } },
      { values: ["heatpump"], color: "#1caebc", outline: "#007788", label: { de: "Wärmepumpe", en: "Heat pump" } },
      { values: ["other", "none"], color: "#bdbdbd", outline: "#7c7c7c", label: { de: "Andere / keine", en: "Other / none" } },
    ] },
  { id: "floors", label: { de: "Geschosse", en: "Floors" }, fact: "hc.floorCount", prop: "floors", steps: [3, 5, 8],
    legendTitle: { de: "Wohngebäude nach Geschossen", en: "Residential buildings by floors" },
    labels: ["1 – 2", "3 – 4", "5 – 7", "8 +"],
    colors: ["#cde6fc", "#61b3ea", "#0078b4", "#00446d"], outlines: ["#5281a3", "#007cbd", "#004d93", "#001e4f"] },
  { id: "dwellings", label: { de: "Wohnungen", en: "Dwellings" }, fact: "hc.dwellings", prop: "num_dwellings", steps: [2, 6, 21],
    legendTitle: { de: "Wohnungen pro Gebäude", en: "Dwellings per building" },
    labels: ["1", "2 – 5", "6 – 20", "21 +"],
    colors: ["#c6eae0", "#55bca4", "#00896f", "#00513f"], outlines: ["#498778", "#00846a", "#00533a", "#00240e"] },
  { id: "solar", label: { de: "Solar", en: "Solar" }, fact: "hc.solar", prop: "solar_best_class",
    legendTitle: { de: "Eignung des besten Dachs für Solarstrom (BFE)", en: "Best roof's suitability for solar power (BFE)" },
    classes: [
      { values: ["Gering", "Mittel"], color: "#f4dfc9", outline: "#947755", label: { de: "gering / mittel", en: "low / medium" } },
      { values: ["Gut"], color: "#cfa36c", outline: "#976923", label: { de: "gut", en: "good" } },
      { values: ["Sehr gut"], color: "#9c6e2c", outline: "#633800", label: { de: "sehr gut", en: "very good" } },
      { values: ["Top"], color: "#5d3e0e", outline: "#320c00", label: "top" },
    ] },
];
const BUILDING_COLOR_MODES_NEXT = null;

// "noise_road_n" -> { mode, variant } (variant null for modes without); null if unknown.
// Knows every lens: the building modes and the area lenses (AREA_MODES, below).
function colorMode(id) {
  for (const m of LENS_MODES) {
    if (!m.variants && m.id === id) return { mode: m, variant: null };
    for (const v of m.variants || []) if (`${m.id}_${v.id}` === id) return { mode: m, variant: v };
  }
  return null;
}
const colorModeId = (m, v) => (v ? `${m.id}_${v.id}` : m.id);
const defaultColorModeId = m => colorModeId(m, m.variants ? m.variants[0] : null);

// The legend classes of a mode: [{ color, outline, label }]
function colorModeClasses(id) {
  const { mode: m, variant: v } = colorMode(id);
  if (m.id === "year") return YEAR_GROUPS.map(g => ({ color: g.color, outline: g.outline, label: g.label }));
  if (m.classes) return m.classes;
  const labels = (v || m).labels;
  return m.colors.map((c, i) => ({ color: c, outline: m.outlines[i], label: labels[i] }));
}

// Fill / outline expression for the housing in a mode (the C-08 cases are added by modeFill / modeLine)
function colorModeExpression(id, which) {
  const { mode: m, variant: v } = colorMode(id);
  if (m.id === "year") return which === "fill" ? yearColorExpression() : yearOutlineExpression();
  const noData = which === "fill" ? NO_YEAR_COLOR : NO_YEAR_OUTLINE;
  const pick = c => (which === "fill" ? c.color : c.outline);
  if (m.classes) {
    // match takes a plain array of labels per branch
    return ["match", ["coalesce", ["get", m.prop], ""], ...m.classes.flatMap(c => [c.values, pick(c)]), noData];
  }
  const prop = (v || m).prop, steps = (v || m).steps, cols = colorModeClasses(id).map(pick);
  const value = m.missingIsLowest ? ["coalesce", ["get", prop], -1] : ["get", prop];
  const step = ["step", ["to-number", value], cols[0]];
  steps.forEach((s, i) => step.push(s, cols[i + 1]));
  return m.missingIsLowest ? step : ["case", ["==", ["get", prop], null], noData, step];
}
// The class a building falls in for a lens: { color, outline, label } or null
// (no value). Same rules as colorModeExpression; the building card draws its
// values in these colours and the legend bar counts the housing per class.
const hasNum = v => v !== null && v !== undefined && v !== "" && !isNaN(Number(v));
function modeClass(id, p) {
  const sel = colorMode(id);
  if (!sel) return null;
  const { mode: m, variant: v } = sel;
  if (m.id === "year") {
    const g = yearGroup(p.baujahr);
    return g ? { color: g.color, outline: g.outline, label: g.label } : null;
  }
  if (m.classes) return m.classes.find(k => k.values.includes(p[m.prop])) || null;
  const raw = p[(v || m).prop];
  const val = hasNum(raw) ? Number(raw) : (m.missingIsLowest ? -1 : null);
  return val === null ? null : colorModeClasses(id)[(v || m).steps.filter(s => val >= s).length];
}
const modeFill = id => ["case", IS_UNFINISHED, BUILDING.devFill, IS_RESIDENTIAL, colorModeExpression(id, "fill"), BUILDING.otherFill];
const modeLine = id => ["case", IS_RESIDENTIAL, colorModeExpression(id, "line"), BUILDING.otherLine];

// The search profile (web/profile.js): a filter never adds
// a colour (C-09); the buildings it leaves out fade to the "no housing"
// greige, or, with `hide`, aren't drawn at all (C-10; the layers' own filters
// stay ANDed in). `match`: the expression of the filter criteria (null =
// none); `marks`: of the mark-only ones (null = none): the matching buildings
// that pass every mark get an outline (buildings-mark).
const BUILDING_NOISE_STEPS = [45, 50, 55, 60, 65];   // the old ?noise= filter (043), read by fromOldParams()
function applyBuildingColorMode(map, id, match, hide, marks) {
  const set = (layer, prop, value) => { if (map.getLayer(layer)) map.setPaintProperty(layer, prop, value); };
  const m = match || null;
  const fade = (expr, other) => m && !hide ? ["case", m, expr, other] : expr;
  set("buildings-2d", "fill-color", fade(modeFill(id), BUILDING.otherFill));
  set("buildings-2d-stroke", "line-color", fade(modeLine(id), BUILDING.otherLine));
  set("buildings-3d", "fill-extrusion-color", fade(modeFill(id), BUILDING.otherFill));
  for (const [layer, own] of Object.entries(BUILDING_LAYER_FILTERS)) {
    if (!map.getLayer(layer)) continue;
    const parts = [own, m && hide ? m : null].filter(Boolean);
    map.setFilter(layer, parts.length > 1 ? ["all", ...parts] : parts[0] || null);
  }
  if (map.getLayer("buildings-mark")) {
    const parts = [ABOVE_GROUND, m, marks].filter(Boolean);
    map.setFilter("buildings-mark", marks ? ["all", ...parts] : ["==", ["get", "egid"], -1]);
  }
}
const BUILDING_MARK_COLOR = "#4a4039";   // cocoa (theme --bg-ink): an outline, never a data colour

// 2D or 3D: which building layers show while the group is on
const BUILDING_VIEW_LAYERS = { "2d": ["buildings-2d", "buildings-2d-stroke"], "3d": ["buildings-3d"] };
function applyBuildingView(map, view, on) {
  for (const [v, ids] of Object.entries(BUILDING_VIEW_LAYERS)) {
    for (const id of ids) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on && v === view ? "visible" : "none");
  }
}

// Keys under the building legend, in the map's own colours
const BUILDING_KEYS = [
  { label: { de: "Baujahr unbekannt", en: "Year unknown" }, swatchStyle: "background:#ddd5ca;border:1px solid #9b8f82" },
  { label: { de: "Ohne Wohnnutzung", en: "No housing" }, swatchStyle: "background:#ece7e0;border:1px solid #c2b8ad" },
  { label: { de: "Geplant / im Bau", en: "Planned / under construction" }, swatchStyle: "background:#f4dfb2;border:1.5px dashed #a8741f" },
  { label: { de: "Unterirdisch", en: "Underground" }, swatchStyle: "background:#f3eee7;border:1px solid #d6cdc2" },
];

// Ground themes (pick one): area polygons tinted under the buildings (C-09).
// Each theme reads one source-layer of the archive and colours it by one
// property (`prop`); `classes` are the legend, in order, with the fill colour
// per value. Tints are drawn over the land, forest and relief and under the
// water, roads and buildings, at GROUND_OPACITY. Colours: one hue per theme,
// light to dark, apart from the year shades (scripts/check_ground_colours.py).
const GROUND_OPACITY = 0.95;
const GROUND_THEMES = [
  { id: "oev", sourceLayer: "oev_classes", prop: "k", fact: "hc.oev",   // ARE ÖV-Güteklassen
    label: { de: "ÖV-Güteklassen", en: "Public transport" },
    legendTitle: { de: "ÖV-Güteklasse (ARE)", en: "Public transport quality (ARE)" },
    classes: [
      { v: "A", color: "#d09369", label: { de: "A sehr gut", en: "A very good" } },
      { v: "B", color: "#e1ae8d", label: { de: "B gut", en: "B good" } },
      { v: "C", color: "#f1cab1", label: { de: "C mittel", en: "C fair" } },
      { v: "D", color: "#ffe6d7", label: { de: "D gering", en: "D basic" } },
    ] },
  // (risks) and 034 (property), Canton of Zürich WFS + BAFU (cities/zurich/pipeline/swiss/build_ground_themes.py)
  { id: "hazard", sourceLayer: "hazard", prop: "level", fact: "hc.hazard",
    label: { de: "Naturgefahren", en: "Natural hazards" },
    legendTitle: { de: "Gefahrenkarte Hochwasser + Massenbewegung (Kanton)", en: "Hazard map, flooding + mass movement (canton)" },
    note: { de: "Ohne Fläche = nicht untersucht, nicht \"sicher\".", en: "No tint = not assessed, not \"safe\"." },
    classes: [
      { v: "red", color: "#e48f8f", label: { de: "erheblich (rot)", en: "significant (red)" } },
      { v: "blue", color: "#9dbbe6", label: { de: "mittel (blau)", en: "moderate (blue)" } },
      { v: "yellow", color: "#f1dc7a", label: { de: "gering (gelb)", en: "low (yellow)" } },
      { v: "residual", color: "#f7eec4", label: { de: "Restgefährdung", en: "residual" } },
    ] },
  { id: "runoff", sourceLayer: "runoff", prop: "depth", fact: "hc.runoff",
    label: { de: "Oberflächenabfluss", en: "Surface runoff" },
    legendTitle: { de: "Oberflächenabfluss bei Starkregen, Fliesstiefe (BAFU)", en: "Surface runoff in heavy rain, flow depth (BAFU)" },
    note: { de: "Massstab ab 1:12'500, nicht parzellengenau; bis 10 cm nur in der Gebäudekarte.",
            en: "For 1:12,500 and smaller, not parcel-exact; up to 10 cm only in the building card." },
    classes: [
      { v: "d25", color: "#5d93c9", label: { de: "über 25 cm", en: "over 25 cm" } },
      { v: "d10", color: "#a9c7e6", label: { de: "10 – 25 cm", en: "10 – 25 cm" } },
    ] },
  { id: "aircraft", sourceLayer: "aircraft_noise", prop: "cls", fact: "hc.aircraft",
    label: { de: "Fluglärm", en: "Aircraft noise" },
    legendTitle: { de: "Fluglärm Flughafen Zürich, Tag (Lr)", en: "Zürich airport noise, day (Lr)" },
    classes: [
      { v: "db58", color: "#c8e3df", label: "58 – 60 dB" },
      { v: "db61", color: "#8cc2bb", label: "61 – 63 dB" },
      { v: "db64", color: "#4f9c93", label: "64 – 66 dB" },
      { v: "db67", color: "#2a6f68", label: { de: "67 dB und mehr", en: "67 dB and more" } },
    ] },
  { id: "contaminated", sourceLayer: "contaminated", prop: "status", fact: "hc.contaminated",
    label: { de: "Belastete Standorte", en: "Contaminated sites" },
    legendTitle: { de: "Belastete Standorte (Kanton, Bahn / ÖV, Armee)", en: "Contaminated sites (canton, rail / public transport, army)" },
    classes: [
      { v: ["remediate", "monitor"], color: "#b0603e", label: { de: "Altlast / zu überwachen", en: "needs remediation / monitoring" } },
      { v: ["investigate", "undefined", "provisional"], color: "#dfa07a", label: { de: "Untersuchung nötig / offen", en: "investigation needed / open" } },
      { v: ["no_action", "no_harm"], color: "#f1d5bd", label: { de: "belastet, keine Massnahmen", en: "polluted, no action needed" } },
    ] },
  { id: "zoning", sourceLayer: "zoning", prop: "zone", fact: "hc.zone",
    label: { de: "Bauzonen", en: "Zoning" },
    legendTitle: { de: "Zonenplan, Grundnutzung (Kanton)", en: "Zoning plan, main use (canton)" },
    classes: [
      // residential by the floors allowed (owner, 2026-10-19): one yellow, darker = taller
      { v: "W2", color: "#f9eab0", label: { de: "Wohnen bis 2 Geschosse", en: "residential, up to 2 floors" } },
      { v: "W3", color: "#f4d87a", label: { de: "Wohnen 3 Geschosse", en: "residential, 3 floors" } },
      { v: "W4", color: "#e6bf47", label: { de: "Wohnen 4 Geschosse", en: "residential, 4 floors" } },
      { v: "W5", color: "#b8901a", label: { de: "Wohnen 5+ Geschosse", en: "residential, 5+ floors" } },
      { v: "WG", color: "#e88d68", label: { de: "Wohnen + Gewerbe", en: "residential + business" } },
      { v: "K", color: "#de9484", label: { de: "Kern / Quartiererhaltung", en: "core / preservation" } },
      { v: "Z", color: "#c06e66", label: { de: "Zentrum", en: "centre" } },
      { v: "I", color: "#9aa7b8", label: { de: "Industrie / Gewerbe", en: "industry / business" } },
      { v: "OE", color: "#c9c0b6", label: { de: "öffentliche Bauten", en: "public buildings" } },
      { v: ["F", "N"], color: "#d4ebc6", label: { de: "Freihalte- / Nichtbauzone", en: "open space / non-building" } },
    ] },
  { id: "es", sourceLayer: "noise_es", prop: "es", fact: "hc.es",
    label: { de: "Lärm-Empfindlichkeit", en: "Noise sensitivity" },
    legendTitle: { de: "Lärmempfindlichkeitsstufe (ES, Zonenplan)", en: "Noise sensitivity level (ES, zoning plan)" },
    classes: [
      { v: "II", color: "#c2e0e8", label: { de: "ES II: Wohnen", en: "ES II: residential" } },
      { v: "III", color: "#93b4d9", label: { de: "ES III: gemischt", en: "ES III: mixed" } },
      { v: "IV", color: "#5481b8", label: { de: "ES IV: Industrie", en: "ES IV: industry" } },
    ] },
];
const GROUND_THEMES_NEXT = null;

// --- lenses (C-10): one colouring at a time ---
// An area lens is a ground theme that also colours the buildings standing on
// it, from the same value on every building (build_ground_themes.py joins it
// by footprint); the ground tint can be switched off. A building without the
// value gets the "no data" greige, labelled with what that means here (not
// assessed, not in the register, below 58 dB, ...), never "safe".
const AREA_LENS = {
  oev: { prop: "oev_class", missing: { de: "ohne Güteklasse", en: "no quality grade" } },
  hazard: { prop: "hazard", missing: { de: "nicht beurteilt", en: "not assessed" } },
  runoff: { prop: "runoff", missing: { de: "nicht kartiert", en: "not mapped" } },
  aircraft: { prop: "aircraft_db", steps: [61, 64, 67], missing: { de: "unter 58 dB", en: "below 58 dB" } },
  contaminated: { prop: "contaminated", missing: { de: "nicht im Kataster", en: "not registered" } },
  zoning: { prop: "zone", missing: { de: "keine Zone", en: "no zone" } },
  es: { prop: "es", missing: { de: "keine Stufe", en: "no level" } },
};
// a deeper outline in the class's own hue (mixed toward the cocoa ink)
function shade(hex, t) {
  const a = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)), b = [0x2b, 0x24, 0x20];
  return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, "0")).join("");
}
const AREA_MODES = GROUND_THEMES.map(g => {
  const a = AREA_LENS[g.id];
  const classes = g.classes.map(c => ({ values: [].concat(c.v), color: c.color, outline: shade(c.color, 0.45), label: c.label }));
  const base = { id: g.id, area: true, label: g.label, fact: g.fact, legendTitle: g.legendTitle, note: g.note, missing: a.missing, prop: a.prop };
  return a.steps
    ? { ...base, steps: a.steps, colors: classes.map(c => c.color), outlines: classes.map(c => c.outline), labels: classes.map(c => c.label) }
    : { ...base, classes };
});
// the city's own sense of a lens (web/city.js `lenses`: the commute target's name, its steps)
for (const [id, o] of Object.entries(CITY.lenses || {})) Object.assign(BUILDING_COLOR_MODES.find(m => m.id === id) || {}, o);
const LENS_MODES = [...BUILDING_COLOR_MODES, ...AREA_MODES];
// the catalogue ("Einfärben nach"), grouped by the question a lens answers
const LENS_GROUPS = [
  { id: "where", label: { de: "Lage & Wege", en: "Location & walks" }, modes: ["commute", "walk", "oev"] },
  { id: "quiet", label: { de: "Ruhe", en: "Quiet" }, modes: ["noise_road", "noise_rail", "aircraft", "es"] },
  { id: "building", label: { de: "Gebäude", en: "Building" }, modes: ["year", "floors", "dwellings", "heating", "solar"] },
  { id: "risk", label: { de: "Risiken", en: "Risks" }, modes: ["hazard", "runoff", "contaminated"] },
  { id: "law", label: { de: "Bau & Recht", en: "Zoning" }, modes: ["zoning"] },
];
const DEFAULT_LENS = "year";

// Places (each on / off, C-09): point layers as monochrome icons, told apart
// by symbol, never by a data colour. Each reads one source-layer; `kinds` are
// its symbols (icon "place-<kind>", drawn by placeIcon() below). Features
// with `hub: true` get the inverted (dark) disc, bigger, from `hubMinzoom`;
// the rest from `minzoom`. Names show on hover (no glyph server).
const PLACE_LAYERS = [
  { id: "stops", key: "s", sourceLayer: "stops", minzoom: 14, hubMinzoom: 11,   // BAV
    label: { de: "Haltestellen", en: "Stops" },
    kinds: [
      { v: "train", hub: true, label: { de: "Bahnhof (ab Zoom 11)", en: "Station (from zoom 11)" } },
      { v: "tram", label: "Tram" },
      { v: "bus", label: "Bus" },
      { v: "boat", label: { de: "Schiff", en: "Boat" } },
      { v: "funicular", label: { de: "Bergbahn", en: "Funicular" } },
    ] },
  { id: "schools", key: "c", sourceLayer: "schools", minzoom: 13,
    label: { de: "Schulen & Betreuung", en: "Schools & childcare" },
    kinds: [
      { v: "kindergarten", label: "Kindergarten" },
      { v: "school", label: { de: "Schule", en: "School" } },
      { v: "upper", label: { de: "Mittel- & Berufsfachschule", en: "Upper secondary & vocational school" } },
      { v: "kita", label: { de: "Kita (Krippe, Tagesstätte)", en: "Day care (Kita)" } },
    ] },
  { id: "hospitals", key: "h", sourceLayer: "hospitals", minzoom: 12, hubMinzoom: 11,
    label: { de: "Spitäler", en: "Hospitals" },
    kinds: [
      { v: "er", hub: true, label: { de: "Spital mit Notfallstation (ab Zoom 11)", en: "Hospital with emergency department (from zoom 11)" } },
      { v: "hospital", label: { de: "Spital, Klinik (Spitalliste)", en: "Hospital, clinic (canton's list)" } },
    ] },
  { id: "health", key: "a", sourceLayer: "health", minzoom: 14,
    label: { de: "Arztpraxen & Apotheken", en: "Doctors & pharmacies" },
    kinds: [
      { v: "doctor", label: { de: "Arztpraxis", en: "Doctor's practice" } },
      { v: "pharmacy", label: { de: "Apotheke", en: "Pharmacy" } },
    ] },
  { id: "shops", key: "e", sourceLayer: "shops", minzoom: 14,
    label: { de: "Einkauf & Post", en: "Groceries & post" },
    kinds: [
      { v: "supermarket", label: { de: "Supermarkt", en: "Supermarket" } },
      { v: "post", label: { de: "Post", en: "Post office" } },
    ] },
  { id: "baths", key: "b", sourceLayer: "baths", minzoom: 12,
    label: { de: "Baden", en: "Swimming" },
    kinds: [
      { v: "lakebath", label: { de: "See- & Flussbad, Badeplatz", en: "Lake & river bath, bathing spot" } },
      { v: "pool", label: { de: "Frei- & Hallenbad", en: "Outdoor & indoor pool" } },
    ] },
  { id: "playgrounds", key: "p", sourceLayer: "playgrounds", minzoom: 15,
    label: { de: "Spielplätze", en: "Playgrounds" },
    kinds: [
      { v: "playground", label: { de: "Öffentlicher Spielplatz", en: "Public playground" } },
    ] },
  { id: "air", key: "q", sourceLayer: "air", minzoom: 11,   // Belgrade: SEPA's stations (build_air.py)
    label: { de: "Luftqualität", en: "Air quality", sr: "Kvalitet vazduha" },
    kinds: [
      { v: "air", label: { de: "Messstation", en: "Monitoring station", sr: "Merna stanica" } },
    ] },
];
const PLACE_LAYERS_NEXT = null;

// Place pictograms, 24 x 24, drawn on a disc: dark glyph on white, or (hubs)
// white glyph on a cocoa disc. Shapes: fill = filled, holes = punched out
// in the disc colour, lines = stroked.
const PLACE_INK = "#4a4039";   // cocoa (theme --bg-ink)
const PLACE_GLYPHS = {
  train: { fill: ["M7 4h10a2.5 2.5 0 0 1 2.5 2.5V15a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2V6.5A2.5 2.5 0 0 1 7 4z"],
           holes: ["M7 6.5h10v4H7z", "M8 13.2a1.1 1.1 0 1 0 0 .1z", "M16 13.2a1.1 1.1 0 1 0 0 .1z"],
           lines: ["M8.5 17.5L6.5 20.5", "M15.5 17.5L17.5 20.5"] },
  tram: { fill: ["M7.5 7h9a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"],
          holes: ["M7.5 9h9v3.5h-9z"],
          lines: ["M9 3.5h6", "M12 3.5V7", "M9 18v2.5", "M15 18v2.5"] },
  bus: { fill: ["M6 4.5h12a2 2 0 0 1 2 2V16a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16V6.5a2 2 0 0 1 2-2z",
                "M6 17h3v2.5H6z", "M15 17h3v2.5h-3z"],
         holes: ["M6 7h12v4.5H6z", "M7.5 14.2a1 1 0 1 0 0 .1z", "M16.5 14.2a1 1 0 1 0 0 .1z"] },
  boat: { fill: ["M3.5 13.5h17l-2.5 5H6z", "M8 8.5h7v4H8z"],
          lines: ["M11.5 8.5V4.5", "M11.5 4.5l3.5 2"] },
  funicular: { fill: ["M5 17l3.5-10h11L16 17z"],
               holes: ["M9.5 9h7.5l-1.3 3.7H8.2z"],
               lines: ["M3 20.5L21 4"] },
  // schools & childcare (006): building blocks, schoolhouse with its bell, mortarboard, pram
  kindergarten: { fill: ["M3.5 13.5h7.5V21H3.5z", "M13 13.5h7.5V21H13z", "M12 3.5l5 8.5H7z"] },
  school: { fill: ["M4 11.5L12 5.5l8 6V21H4z"],
            holes: ["M10.3 15.5h3.4V21h-3.4z", "M10.6 10.6h2.8v2.6h-2.8z"],
            lines: ["M12 5.5V2.5", "M12 2.5h3.2"] },
  upper: { fill: ["M12 4.5l10 4.5-10 4.5L2 9z", "M6.5 12.2v4.3c0 1.6 2.5 3 5.5 3s5.5-1.4 5.5-3v-4.3L12 14.7z"],
           lines: ["M20.2 9.8v5.5"] },
  kita: { fill: ["M3.5 10.5h12.5a6.25 5 0 0 1-12.5 0z", "M16 10.5A6.5 6.5 0 0 0 9.5 4v6.5z",
                 "M6.5 18.2a1.9 1.9 0 1 0 0.1 0z", "M13.5 18.2a1.9 1.9 0 1 0 0.1 0z"],
          lines: ["M16 10.5l2.5-4h2"] },
  // health (032): the hospital H (on the dark disc with an emergency department), stethoscope, the pharmacy cross
  hospital: { fill: ["M6 4h3.4v6.3h5.2V4H18v16h-3.4v-6.3H9.4V20H6z"] },
  er: { fill: ["M6 4h3.4v6.3h5.2V4H18v16h-3.4v-6.3H9.4V20H6z"] },
  doctor: { fill: ["M18.5 10.2a2.2 2.2 0 1 0 0.1 0z"],
            lines: ["M6 3.5v5.5a4 4 0 0 0 8 0V3.5", "M10 13v2.5a4.25 4.25 0 0 0 8.5 0v-3"] },
  pharmacy: { fill: ["M9.5 4h5v5.5H20v5h-5.5V20h-5v-5.5H4v-5h5.5z"] },
  // groceries & post (035): shopping trolley, letter
  supermarket: { fill: ["M8.9 17.6a1.7 1.7 0 1 0 0.1 0z", "M16.6 17.6a1.7 1.7 0 1 0 0.1 0z", "M7 8.2h13l-1.9 6.3H8.4z"],
                 lines: ["M2.8 4.8h2.8l2.6 10.4h10.3"] },
  post: { lines: ["M3.5 6.5h17v11h-17z", "M3.5 6.5l8.5 6.5 8.5-6.5"] },
  // swimming & playgrounds (007): swimmer in the waves, pool ladder, swing
  lakebath: { fill: ["M17 5.2a2.1 2.1 0 1 0 0.1 0z"],
              lines: ["M4.5 12l5-3.2 3.2 3.4 3.8-1.8",
                      "M3 15.8c1.5-1.2 3-1.2 4.5 0s3 1.2 4.5 0 3-1.2 4.5 0 3 1.2 4.5 0",
                      "M3 19.5c1.5-1.2 3-1.2 4.5 0s3 1.2 4.5 0 3-1.2 4.5 0 3 1.2 4.5 0"] },
  pool: { lines: ["M8.5 15V5.5a2 2 0 0 0-3.2-1.6", "M15.5 15V5.5a2 2 0 0 0-3.2-1.6", "M8.5 8h7", "M8.5 11.5h7",
                  "M3 18.5c1.5-1.2 3-1.2 4.5 0s3 1.2 4.5 0 3-1.2 4.5 0 3 1.2 4.5 0"] },
  // three streaks of air
  air: { lines: ["M4 8.5h10.5a2.5 2.5 0 1 0-2.5-2.5", "M4 12.5h14.5a2.5 2.5 0 1 1-2.5 2.5", "M4 16.5h7"] },
  playground: { fill: ["M9.2 13.5h5.6v1.8H9.2z"], lines: ["M4 20.5L8 3.5h8l4 17", "M10 3.5v10", "M14 3.5v10"] },
};

// Draws "place-<kind>" / "place-<kind>-hub" as an ImageData for map.addImage.
function placeIcon(id) {
  const m = /^place-(\w+?)(-hub)?$/.exec(id);
  const glyph = m && PLACE_GLYPHS[m[1]];
  if (!glyph) return null;
  const hub = !!m[2], ratio = 2, size = (hub ? 26 : 22) * ratio;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const disc = hub ? PLACE_INK : "#ffffff", ink = hub ? "#ffffff" : PLACE_INK;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - ratio, 0, 2 * Math.PI);
  ctx.fillStyle = disc; ctx.fill();
  ctx.lineWidth = 1.2 * ratio; ctx.strokeStyle = PLACE_INK; ctx.stroke();
  const scale = size / 24 * 0.68;
  ctx.translate(size / 2 - 12 * scale, size / 2 - 12 * scale);
  ctx.scale(scale, scale);
  ctx.fillStyle = ink;
  (glyph.fill || []).forEach(d => ctx.fill(new Path2D(d)));
  ctx.fillStyle = disc;
  (glyph.holes || []).forEach(d => ctx.fill(new Path2D(d)));
  ctx.strokeStyle = ink; ctx.lineWidth = 1.8; ctx.lineCap = "round";
  (glyph.lines || []).forEach(d => ctx.stroke(new Path2D(d)));
  return { width: size, height: size, data: ctx.getImageData(0, 0, size, size).data, ratio };
}

// Icons are made on demand: MapLibre asks for each missing image once.
function initPlaceIcons(map) {
  map.on("styleimagemissing", e => {
    const icon = placeIcon(e.id);
    if (icon && !map.hasImage(e.id)) {
      map.addImage(e.id, { width: icon.width, height: icon.height, data: icon.data }, { pixelRatio: icon.ratio });
    }
  });
}

// The icon as a data URL, for the sidebar's legend
function placeIconUrl(id) {
  const icon = placeIcon(id);
  if (!icon) return "";
  const c = document.createElement("canvas");
  c.width = icon.width; c.height = icon.height;
  c.getContext("2d").putImageData(new ImageData(icon.data, icon.width, icon.height), 0, 0);
  return c.toDataURL();
}

function groundLayers() {
  return GROUND_THEMES.map(th => ({
    id: `ground-${th.id}`, type: "fill", source: "cadastre", "source-layer": th.sourceLayer,
    metadata: { "bg:ground": th.id },
    layout: { visibility: "none" },
    paint: {
      "fill-color": ["match", ["get", th.prop], ...th.classes.flatMap(c => [c.v, c.color]), "rgba(0,0,0,0)"],
      "fill-opacity": GROUND_OPACITY,
    }
  }));
}

function placeLayers() {
  const out = [];
  for (const pl of PLACE_LAYERS) {
    const HUB = ["==", ["get", "hub"], true];
    const common = (hub) => ({
      type: "symbol", source: "cadastre", "source-layer": pl.sourceLayer,
      metadata: { "bg:place": pl.key },
      layout: {
        visibility: "none",
        "icon-image": ["concat", "place-", ["get", "kind"], hub ? "-hub" : ""],
        "icon-size": hub ? ["interpolate", ["linear"], ["zoom"], 11, 0.6, 14, 0.9, 17, 1.1]
                         : ["interpolate", ["linear"], ["zoom"], 14, 0.7, 17, 1.0],
        "icon-allow-overlap": hub,
        "icon-padding": 1,
        // better-served stops win where icons would collide (ARE category, 1 = best)
        "symbol-sort-key": ["coalesce", ["get", "cat"], 9],
      },
    });
    out.push({ id: `place-${pl.id}`, minzoom: pl.minzoom, filter: ["!", HUB], ...common(false) });
    if (pl.hubMinzoom != null) out.push({ id: `place-${pl.id}-hub`, minzoom: pl.hubMinzoom, filter: HUB, ...common(true) });
  }
  return out;
}

// --- layer groups (on / off), in sidebar order; `key` is their letter in ?layers= ---
// (borders = municipality / Kreis lines plus the HTML place labels of web/area.js;
// `keys` are the legend rows shown under a base-map group)
const LAYER_GROUPS = [
  { id: "buildings", key: "b", label: { de: "Gebäude", en: "Buildings" }, tier: "buildings" },
  { id: "roads", key: "r", label: { de: "Strassen", en: "Roads" }, tier: "base", keys: [
    { label: { de: "Brücke", en: "Bridge" }, swatchStyle: "height:6px;background:#fffdf9;border:1.5px solid #a89a8b" },
    { label: { de: "im Tunnel", en: "in tunnel" }, swatchStyle: "height:0;border-top:2px dashed #d8cfc4" },
  ] },
  { id: "transit", key: "t", label: { de: "Bahn & Tram", en: "Rail & tram" }, tier: "base", keys: [
    { label: { de: "Bahn", en: "Rail" }, swatchStyle: "height:4px;background:repeating-linear-gradient(90deg,#b3a89c 0 4px,#fffdf9 4px 7px);border:1px solid #b3a89c" },
    { label: "Tram", swatchStyle: "height:2px;background:#b3a89c" },
    { label: { de: "im Tunnel", en: "in tunnel" }, swatchStyle: "height:0;border-top:2px dashed #d8cfc4" },
  ] },
  { id: "water", key: "w", label: { de: "Gewässer", en: "Water" }, tier: "base" },
  { id: "forest", key: "f", label: { de: "Wald", en: "Forest" }, tier: "base" },
  { id: "parks", key: "p", label: "Parks", tier: "base" },
  { id: "parcels", key: "l", label: { de: "Grundstücke", en: "Plots" }, tier: "base" },   // from z15
  { id: "borders", key: "g", label: { de: "Grenzen & Namen", en: "Borders & names" }, tier: "base" },   // keys: AREA_LEGEND_KEYS (web/area.js)
  { id: "relief", key: "h", label: "Relief", tier: "base" },
];
const group = g => ({ "bg:group": g });

// --- palette ---
// Soft / pastel "Scandi wellness" palette (decision C-06): oat
// land, powder-blue water, pale sage greens, cream roads with greige casings,
// cocoa-grey tracks. scripts/check_year_colours.py reads land / forest / park
// from here: the year colours are validated against them.
const BASE = {
  land: "#f6f1ea",          // oat
  forest: "#dbe6cf",        // cadastral survey's closed forest
  park: "#e4eed6",          // City of Zürich parks: fresher, with an outline
  parkLine: "#bdd3ad",
  water: "#cfe0ec",         // powder blue
  waterLine: "#a9c6dc",     // shoreline + rivers
  roadFill: "#fffdf9",
  roadCasing: "#e2d8cb",
  motorwayCasing: "#cbbcab",
  path: "#bfb3a5",
  track: "#b3a89c",         // trains, trams, funiculars: light warm grey, quieter than the buildings (C-08)
  tunnel: "#d8cfc4",        // tracks and roads in tunnels: faint dashes, under the roads
  bridgeCasing: "#a89a8b",  // bridges: a darker casing, drawn above what they cross (water, roads, tracks)
  parcel: "#bfae9b",        // land plot boundaries: solid hairline (paths are the dashed ones), under roads + buildings
};

// --- roads: swissTLM3D `objektart` -> class (Belgrade maps OSM classes onto it) ---
const ROAD_CLASS = ["match", ["get", "objektart"],
  [0, 1, 2, 3, 21], 5,     // motorway / expressway
  [4, 8, 20], 4,           // major
  [9], 3,                  // medium
  [10], 2,                 // local
  [5, 6, 11, 12], 1,       // minor (incl. driveways, squares)
  0];                      // paths & tracks (15-18), drawn by their own layer
const IS_PATH = ["in", ["get", "objektart"], ["literal", [15, 16, 17, 18]]];

// Fill width per class at a few zooms (px); casing adds `extra` on both sides
// together. Classes start at 0 width below the zoom where they appear.
const ROAD_WIDTHS = {
  //        motorway major medium local minor
  10: [1.6, 1.0, 0.5, 0, 0],
  12: [2.6, 1.8, 1.2, 0.6, 0],
  14: [5.0, 4.0, 3.0, 2.0, 1.0],
  16: [10, 8, 6.5, 5.0, 2.8],
  18: [22, 18, 14, 11, 6],
};
function roadWidth(extra) {
  const expr = ["interpolate", ["exponential", 1.5], ["zoom"]];
  for (const [z, w] of Object.entries(ROAD_WIDTHS)) {
    const byClass = ["match", ROAD_CLASS, 5, w[0], 4, w[1], 3, w[2], 2, w[3], 1, w[4], 0];
    // a road that isn't drawn yet at this zoom gets no casing either
    expr.push(+z, extra ? ["case", [">", byClass, 0], ["+", byClass, extra(+z)], 0] : byClass);
  }
  return expr;
}
const CASING_EXTRA = z => (z <= 12 ? 0.8 : z <= 14 ? 1.4 : 2.2);

const ROADS = ["==", ["get", "kind"], "road"];
const RAIL = ["==", ["get", "kind"], "rail"];
const IS_TRAM = ["==", ["get", "verkehrsmittel"], 200];
const IS_FUNICULAR = ["==", ["get", "standseilbahn"], 2];
const IS_TRAIN = ["all", ["!", IS_TRAM], ["!", IS_FUNICULAR]];
// swissTLM3D structure, added by cities/zurich/pipeline/swiss/build_rail_structures.py
const IN_TUNNEL = ["==", ["get", "structure"], "tunnel"];
const ON_SURFACE = ["!", IN_TUNNEL];
const ON_BRIDGE = ["==", ["get", "structure"], "bridge"];
// MultiLineStrings report "LineString" too; polygons likewise
const IS_LINE = ["==", ["geometry-type"], "LineString"];
const IS_POLYGON = ["==", ["geometry-type"], "Polygon"];

/**
 * The full layer list for a style using the `cadastre` vector source.
 * opts.extrusion: include the (hidden) 3D building layer (map page only).
 */
function cadastreLayers(opts) {
  opts = opts || {};
  const src = { source: "cadastre" };
  const layers = [
    { id: "background", type: "background", paint: { "background-color": BASE.land } },

    // --- land cover ---
    {
      id: "forest-fill", type: "fill", ...src, "source-layer": "greenery",
      filter: ["==", ["get", "type"], "forest"],
      metadata: group("forest"),
      paint: { "fill-color": BASE.forest }
    },
    {
      // public parks (City of Zürich): drawn above forest, outlined so they
      // read as places, not just green ground
      id: "park-fill", type: "fill", ...src, "source-layer": "greenery",
      filter: ["==", ["get", "type"], "park"],
      metadata: group("parks"),
      paint: { "fill-color": BASE.park }
    },
    {
      id: "park-line", type: "line", ...src, "source-layer": "greenery", minzoom: 13,
      filter: ["==", ["get", "type"], "park"],
      metadata: group("parks"),
      paint: {
        "line-color": BASE.parkLine,
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.5, 17, 1.5]
      }
    },

    // --- relief (web/relief.js), above the greenery, below everything else ---
    ...reliefLayers().map(l => ({ ...l, metadata: group("relief") })),

    // --- ground theme tints (pick one, sidebar), above land + relief, under water ---
    ...groundLayers(),

    // --- water: lake / river areas, shoreline, river centrelines ---
    // (swissTLM3D gives most rivers as lines only -- both layers are needed)
    {
      id: "water-fill", type: "fill", ...src, "source-layer": "water", filter: IS_POLYGON,
      metadata: group("water"),
      paint: { "fill-color": BASE.water }
    },
    {
      // shoreline for lakes and ponds only; river areas (018) are many small
      // pieces whose outlines would just cost frame time
      id: "water-shore", type: "line", ...src, "source-layer": "water",
      filter: ["all", IS_POLYGON, ["!=", ["get", "type"], "river_area"]],
      metadata: group("water"),
      paint: {
        "line-color": BASE.waterLine,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.4, 16, 1.2]
      }
    },
    {
      id: "water-rivers-line", type: "line", ...src, "source-layer": "water", filter: IS_LINE,
      metadata: group("water"),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": BASE.waterLine,
        // named rivers and streams a little wider than the unnamed ditches
        "line-width": ["interpolate", ["exponential", 1.4], ["zoom"],
          10, ["case", ["has", "name"], 0.7, 0.3],
          13, ["case", ["has", "name"], 1.4, 0.7],
          16, ["case", ["has", "name"], 3.0, 1.5],
          18, ["case", ["has", "name"], 5.0, 2.5]]
      }
    },

    // --- land plots (cadastral survey): hairline boundaries from z15, under roads + buildings ---
    {
      id: "parcels-line", type: "line", ...src, "source-layer": "parcels", minzoom: 15,
      metadata: group("parcels"),
      paint: {
        "line-color": BASE.parcel,
        "line-width": ["interpolate", ["linear"], ["zoom"], 15, 0.5, 17, 1.0, 19, 1.6],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 15, 0, 15.6, 1]
      }
    },

    // --- tracks in tunnels: faint dashes under everything above ground ---
    {
      id: "rail-tunnel", type: "line", ...src, "source-layer": "roads_rail", minzoom: 14,
      filter: ["all", RAIL, IN_TUNNEL],
      metadata: group("transit"),
      paint: {
        "line-color": BASE.tunnel,
        "line-width": ["interpolate", ["linear"], ["zoom"], 14, 1.0, 16, 1.6, 18, 2.4],
        "line-dasharray": [2, 2]
      }
    },

    // --- roads in tunnels (Milchbuck, Hirschengraben ...): faint dashes, like the tracks ---
    {
      id: "roads-tunnel", type: "line", ...src, "source-layer": "roads_rail", minzoom: 13,
      filter: ["all", ROADS, IN_TUNNEL],
      metadata: group("roads"),
      paint: {
        "line-color": BASE.tunnel,
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.8, 16, 2.0, 18, 3.2],
        "line-dasharray": [2, 2]
      }
    },

    // --- roads: casing under fill; paths dashed, from z15 (26k segments: clutter + frame time below) ---
    {
      id: "roads-casing", type: "line", ...src, "source-layer": "roads_rail",
      filter: ["all", ROADS, ON_SURFACE, ["!", IS_PATH]],
      metadata: group("roads"),
      layout: { "line-cap": "round", "line-join": "round", "line-sort-key": ROAD_CLASS },
      paint: {
        "line-color": ["case", ["==", ROAD_CLASS, 5], BASE.motorwayCasing, BASE.roadCasing],
        "line-width": roadWidth(CASING_EXTRA)
      }
    },
    {
      id: "roads-path", type: "line", ...src, "source-layer": "roads_rail", minzoom: 15,
      filter: ["all", ROADS, ON_SURFACE, IS_PATH],
      metadata: group("roads"),
      paint: {
        "line-color": BASE.path,
        "line-width": ["interpolate", ["linear"], ["zoom"], 15, 0.8, 18, 1.8],
        "line-dasharray": [3, 2]
      }
    },
    {
      id: "roads-fill", type: "line", ...src, "source-layer": "roads_rail",
      filter: ["all", ROADS, ON_SURFACE, ["!", IS_PATH]],
      metadata: group("roads"),
      layout: { "line-cap": "round", "line-join": "round", "line-sort-key": ROAD_CLASS },
      paint: { "line-color": BASE.roadFill, "line-width": roadWidth(null) }
    },

    // --- public transport tracks ---
    // trains: dark line with white dashes from z15 (the classic "ladder");
    // trams: thin solid line; funiculars: dotted
    {
      // tracks on bridges: a darker casing under the track (from z14)
      id: "rail-bridge-casing", type: "line", ...src, "source-layer": "roads_rail", minzoom: 14,
      filter: ["all", RAIL, ON_BRIDGE],
      metadata: group("transit"),
      paint: {
        "line-color": BASE.bridgeCasing,
        "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 14, 3.0, 16, 5.5, 18, 9]
      }
    },
    {
      id: "rail-train", type: "line", ...src, "source-layer": "roads_rail",
      filter: ["all", RAIL, IS_TRAIN, ON_SURFACE],
      metadata: group("transit"),
      paint: {
        "line-color": BASE.track,
        // hairline when zoomed out: the HB track field is dozens of parallel tracks
        "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 10, 0.4, 12, 0.6, 13, 0.9, 15, 1.8, 16, 2.6, 18, 4.4],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.45, 14, 0.8, 15, 1]
      }
    },
    {
      id: "rail-train-dash", type: "line", ...src, "source-layer": "roads_rail", minzoom: 15,
      filter: ["all", RAIL, IS_TRAIN, ON_SURFACE],
      metadata: group("transit"),
      paint: {
        "line-color": "#ffffff",
        "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 15, 0.9, 16, 1.3, 18, 2.2],
        "line-dasharray": [3, 3]
      }
    },
    {
      id: "rail-tram", type: "line", ...src, "source-layer": "roads_rail", minzoom: 13,
      filter: ["all", RAIL, IS_TRAM, ON_SURFACE],
      metadata: group("transit"),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": BASE.track,
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.5, 15, 1.1, 18, 2.4]
      }
    },
    {
      id: "rail-funicular", type: "line", ...src, "source-layer": "roads_rail", minzoom: 13,
      filter: ["all", RAIL, IS_FUNICULAR, ON_SURFACE],
      metadata: group("transit"),
      paint: {
        "line-color": BASE.track,
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 1.2, 18, 3],
        "line-dasharray": [0.6, 1.6]
      }
    },

    // --- road bridges, drawn again above the tracks and the roads they cross: darker casing + fill ---
    {
      id: "roads-bridge-casing", type: "line", ...src, "source-layer": "roads_rail", minzoom: 13,
      filter: ["all", ROADS, ON_BRIDGE, ["!", IS_PATH]],
      metadata: group("roads"),
      layout: { "line-cap": "butt", "line-join": "round" },
      paint: { "line-color": BASE.bridgeCasing, "line-width": roadWidth(z => CASING_EXTRA(z) + 1.2) }
    },
    {
      id: "roads-bridge-fill", type: "line", ...src, "source-layer": "roads_rail", minzoom: 13,
      filter: ["all", ROADS, ON_BRIDGE, ["!", IS_PATH]],
      metadata: group("roads"),
      layout: { "line-cap": "butt", "line-join": "round" },
      paint: { "line-color": BASE.roadFill, "line-width": roadWidth(null) }
    },
    {
      // footbridges (Stege) and paths on bridges: a small cased deck from z15
      id: "roads-bridge-path", type: "line", ...src, "source-layer": "roads_rail", minzoom: 15,
      filter: ["all", ROADS, ON_BRIDGE, IS_PATH],
      metadata: group("roads"),
      layout: { "line-cap": "butt" },
      paint: {
        "line-color": BASE.roadFill,
        "line-width": ["interpolate", ["linear"], ["zoom"], 15, 2.2, 18, 5]
      }
    },
    {
      id: "roads-bridge-path-edge", type: "line", ...src, "source-layer": "roads_rail", minzoom: 15,
      filter: ["all", ROADS, ON_BRIDGE, IS_PATH],
      metadata: group("roads"),
      layout: { "line-cap": "butt" },
      paint: {
        "line-color": BASE.bridgeCasing,
        "line-width": ["interpolate", ["linear"], ["zoom"], 15, 0.6, 18, 1],
        "line-gap-width": ["interpolate", ["linear"], ["zoom"], 15, 2.2, 18, 5]
      }
    },

    // --- buildings: housing by construction-year group (web/years.js), the rest neutral ---
    {
      // from z13: the tiles hold every building at z13-14 and none below (a random
      // sample looked like noise when zoomed out); shared/build_tiles.sh
      id: "buildings-2d", type: "fill", ...src, "source-layer": "buildings", minzoom: 13,
      metadata: group("buildings"),
      paint: {
        "fill-color": buildingFill(),
        // fade in over z13 -> z13.6 instead of popping in
        "fill-opacity": ["interpolate", ["linear"], ["zoom"],
          13, ["case", ["!", ABOVE_GROUND], 0, 0.3], 13.6, ["case", ["!", ABOVE_GROUND], 0.25, 0.95]]
      }
    },
    {
      // thin when zoomed out, so small buildings show their colour, not a black dot
      // outlines from z13.5: below that they are sub-pixel and only double the draw work
      id: "buildings-2d-stroke", type: "line", ...src, "source-layer": "buildings", minzoom: 13.5,
      filter: BUILDING_LAYER_FILTERS["buildings-2d-stroke"],
      metadata: group("buildings"),
      paint: {
        "line-color": buildingLine(),   // housing: deeper shade of its year group; the rest: greige
        "line-width": ["interpolate", ["linear"], ["zoom"], 13.5, 0.3, 14, 0.5, 16, 1.0, 18, 1.4],
        // (zoom must be the outermost expression; underground stays at 0.3)
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 13, UNDERGROUND_FADE(0, 0.3), 15, UNDERGROUND_FADE(0.3, 1)]
      }
    },
    {
      id: "buildings-2d-unfinished", type: "line", ...src, "source-layer": "buildings", minzoom: 13,
      filter: BUILDING_LAYER_FILTERS["buildings-2d-unfinished"],
      metadata: group("buildings"),
      paint: {
        "line-color": BUILDING.devLine,
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.5, 14, 1.0, 16, 2.2, 18, 3],
        "line-dasharray": [2, 1.2]
      }
    },
  ];
  if (opts.extrusion) {
    layers.push({
      // hidden until the 2D/3D toggle switches it on
      id: "buildings-3d", type: "fill-extrusion", ...src, "source-layer": "buildings",
      filter: BUILDING_LAYER_FILTERS["buildings-3d"],
      metadata: group("buildings"),
      layout: { visibility: "none" },
      paint: {
        "fill-extrusion-height": ["*", ["coalesce", ["get", "floors"], 3], 3.5],  // 3.5 m per floor
        "fill-extrusion-base": 0,
        "fill-extrusion-color": buildingFill(),
        // 1 = single draw pass; translucent extrusions are drawn twice
        "fill-extrusion-opacity": 1
      }
    });
    // the search profile's "mark only" criteria (web/profile.js): one outline layer
    layers.push({
      id: "buildings-mark", type: "line", ...src, "source-layer": "buildings", minzoom: 13,
      filter: ["==", ["get", "egid"], -1], metadata: { "bg:mark": true },
      paint: {
        "line-color": BUILDING_MARK_COLOR,
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 1.2, 16, 2.6, 18, 3.4],
      }
    });
    layers.push({
      id: "buildings-selected", type: "line", ...src, "source-layer": "buildings", minzoom: 13,
      filter: ["==", ["get", "egid"], -1], metadata: { "bg:select": true },
      paint: {
        "line-color": "#4a4039",
        "line-width": ["interpolate", ["linear"], ["zoom"], 13, 2, 16, 3.5, 18, 4.5],
        "line-opacity": 0.9,
      }
    });
  }
  // municipality + Kreis borders on top of everything (web/area.js); the panel
  // hides their HTML place labels together with them
  // place icons above everything
  return layers.concat(areaBorderLayers("cadastre").map(l => ({ ...l, metadata: group("borders") })), placeLayers());
}
