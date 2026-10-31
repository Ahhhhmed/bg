/**
 * Zurich 100% Vector Map & 3D Building Age (Baujahr) Cadastre
 * Powered by MapLibre GL JS (WebGL Hardware-Accelerated Vector Engine)
 * All layers are streamed from one PMTiles archive (see below)
 */

// Register the PMTiles protocol so MapLibre can read pmtiles:// vector sources.
// All ~148k features (88k buildings + 54k road/rail segments + water/greenery/
// municipality / Kreis borders/transit) are packed into one ~17MB archive by tippecanoe -- loading
// the raw GeoJSON directly (~100MB for buildings alone) would freeze the browser.
const pmtilesProtocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);
const PMTILES_URL = "pmtiles://../data/layers/cadastre.pmtiles";   // the city's archive (shared/build_tiles.sh); the build versions the URL

// Construction-year groups and their colours: web/years.js (shared with
// controls.js).

// Building constants (ABOVE_GROUND, IS_UNFINISHED, UNFINISHED_STATUS,
// BUILDING_LAYER_FILTERS) and the whole layer stack: web/layers.js.

const FOOTPRINT_LABELS = {
  cadastral_footprint_av: { de: "Amtliche Vermessung", en: "Cadastral survey" },
  real_roof_footprint_solar_vector: { de: "Dachflächen (Solar)", en: "Roof areas (solar)" },
  extracted_from_raster_tiles: { de: "Aus Rasterkarte", en: "Traced from raster map" },
  approximate_square_from_gwr_point: { de: "Näherung (Quadrat)", en: "Approximation (square)" },
  osm_footprint: { de: "OpenStreetMap", en: "OpenStreetMap" },
  ml_footprint: { de: "Microsoft ML (aus Luftbildern erkannt)", en: "Microsoft ML (detected in imagery)", sr: "Microsoft ML (prepoznato sa snimaka)" },
};

// Style: one vector source for the whole archive -- every layer reads its own
// source-layer (five sources pointing at the same file made MapLibre fetch and
// parse each tile five times measured -79% download, -22..48%
// frame time). The layers themselves are in web/layers.js.
const vectorStyle = {
  version: 8,
  name: "Zurich Vector Cadastre",
  sources: {
    cadastre: { type: "vector", url: PMTILES_URL },
    ...reliefSources()   // web/relief.js
  },
  // Light for the 3D buildings: fixed to the map (shading doesn't swing when
  // the map rotates), from the north-north-west like the relief convention.
  light: { anchor: "map", position: [1.15, 337, 35], intensity: 0.4 },
  layers: cadastreLayers({ extrusion: true })
};

// Initialize MapLibre GL WebGL Map
const map = new maplibregl.Map({
  container: "map",
  style: vectorStyle,
  center: CITY.center,   // web/city.js; the area overlay then fits the city
  zoom: CITY.zoom,
  pitch: 0,
  bearing: 0,
  // phones report 3; 2 looks the same and draws 44% faster
  pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  // the credits sit in the data-age pin instead (web/freshness.js, C-16)
  attributionControl: false
});

// place pictograms are drawn on demand (web/layers.js)
initPlaceIcons(map);

// Navigation Controls
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
addZoomReadout(map);   // web/controls.js
// credits and the data age, bottom right (C-16)
map.addControl(new FreshnessControl(CITY.credits), "bottom-right");

// GWR heat generator (gwaerzh1, stored as `heating_code`). The fuel of a
// boiler (oil, gas, wood) is a separate GWR field that isn't in the tiles.
const HEATING_NAMES = {
  7400: { de: "Kein Wärmeerzeuger", en: "No heat generator" },
  7410: { de: "Wärmepumpe", en: "Heat pump" }, 7411: { de: "Wärmepumpe (mehrere Gebäude)", en: "Heat pump (several buildings)" },
  7420: { de: "Solarthermie", en: "Solar thermal" }, 7421: { de: "Solarthermie (mehrere Gebäude)", en: "Solar thermal (several buildings)" },
  7430: { de: "Heizkessel", en: "Boiler" }, 7431: { de: "Heizkessel (mehrere Gebäude)", en: "Boiler (several buildings)" },
  7432: { de: "Heizkessel", en: "Boiler" }, 7433: { de: "Heizkessel (mehrere Gebäude)", en: "Boiler (several buildings)" },
  7434: { de: "Heizkessel (kondensierend)", en: "Condensing boiler" }, 7435: { de: "Heizkessel (kondensierend, mehrere Gebäude)", en: "Condensing boiler (several buildings)" },
  7436: { de: "Ofen", en: "Stove" },
  7440: { de: "Wärme-Kraft-Kopplung", en: "Combined heat and power" }, 7441: { de: "Wärme-Kraft-Kopplung (mehrere Gebäude)", en: "Combined heat and power (several buildings)" },
  7450: { de: "Elektro-Zentralspeicher", en: "Electric storage heating" }, 7451: { de: "Elektro-Zentralspeicher (mehrere Gebäude)", en: "Electric storage heating (several buildings)" },
  7452: { de: "Elektro direkt", en: "Direct electric" },
  7460: { de: "Fernwärme / Wärmetauscher", en: "District heating / heat exchanger" }, 7461: { de: "Fernwärme / Wärmetauscher (mehrere Gebäude)", en: "District heating / heat exchanger (several buildings)" },
  7499: { de: "Andere", en: "Other" },
};

// GWR energy source of the heating (genh1, `heating_energy`), shown after the generator.
const ENERGY_NAMES = {
  7500: { de: "keine", en: "none" }, 7501: { de: "Luft", en: "air" },
  7510: { de: "Erdwärme", en: "ground heat" }, 7511: { de: "Erdwärmesonde", en: "ground probe" },
  7512: { de: "Erdregister", en: "ground collector" }, 7513: { de: "Wasser", en: "water" },
  7520: "Gas", 7530: { de: "Heizöl", en: "oil" },
  7540: { de: "Holz", en: "wood" }, 7541: { de: "Stückholz", en: "logs" }, 7542: { de: "Holzpellets", en: "wood pellets" },
  7543: { de: "Holzschnitzel", en: "wood chips" }, 7550: { de: "Abwärme", en: "waste heat" },
  7560: { de: "Strom", en: "electricity" }, 7570: { de: "Sonne", en: "solar" },
  7580: { de: "Fernwärme", en: "district heating" }, 7581: { de: "Fernwärme", en: "district heating" },
  7582: { de: "Fernwärme", en: "district heating" }, 7598: { de: "unbestimmt", en: "undetermined" }, 7599: { de: "andere", en: "other" },
};

// Ground facts on each building (backlogs 033 / 034, cities/zurich/pipeline/swiss/build_ground_themes.py);
// the zone / hazard / ES class labels come from GROUND_THEMES (web/layers.js).
const HAZARD_PROCESS = {
  flood: { de: "Hochwasser", en: "flooding" }, landslide: { de: "Massenbewegung", en: "mass movement" },
  both: { de: "Hochwasser + Massenbewegung", en: "flooding + mass movement" },
};
const RUNOFF_DEPTH = {
  d0: { de: "bis 10 cm", en: "up to 10 cm" }, d10: "10 – 25 cm", d25: { de: "über 25 cm", en: "over 25 cm" },
};
const AIRCRAFT_LIMIT = {
  aw: { de: "Alarmwert überschritten", en: "alarm value exceeded" },
  igw: { de: "Immissionsgrenzwert überschritten", en: "exposure limit exceeded" },
  pw: { de: "Planungswert überschritten", en: "planning value exceeded" },
  ok: { de: "Planungswert eingehalten", en: "planning value met" },
};
const CONTAMINATED_STATUS = {
  remediate: { de: "sanierungsbedürftig (Altlast)", en: "needs remediation" },
  monitor: { de: "überwachungsbedürftig", en: "needs monitoring" },
  investigate: { de: "untersuchungsbedürftig", en: "needs investigation" },
  undefined: { de: "Untersuchungsbedarf offen", en: "investigation need open" },
  provisional: { de: "provisorischer Eintrag", en: "provisional entry" },
  no_action: { de: "keine Massnahmen nötig", en: "no action needed" },
  no_harm: { de: "keine schädlichen Einwirkungen", en: "no harmful effects expected" },
};
const CONTAMINATED_SITE = {
  landfill: { de: "Ablagerung", en: "landfill" }, industrial: { de: "Betriebsstandort", en: "industrial site" },
  accident: { de: "Unfallstandort", en: "accident site" }, shooting: { de: "Schiessanlage", en: "shooting range" },
};
function groundLabel(themeId, value) {
  const th = GROUND_THEMES.find(g => g.id === themeId);
  const c = th && th.classes.find(c => [].concat(c.v).includes(value));
  return c ? tr(c.label) : null;
}

// GWR building category (gkat).
const CATEGORY_NAMES = {
  1010: { de: "Provisorische Unterkunft", en: "Temporary shelter" },
  1020: { de: "Reines Wohngebäude", en: "Residential only" },
  1030: { de: "Wohngebäude mit Nebennutzung", en: "Residential with other uses" },
  1040: { de: "Teilweise Wohnnutzung", en: "Partly residential" },
  1060: { de: "Ohne Wohnnutzung", en: "No housing" },
  1080: { de: "Sonderbau", en: "Special building" },
};

// Solar roof suitability class (BFE sonnendach.ch), stored in German.
const SOLAR_CLASSES = {
  "Gering": { de: "Gering", en: "Low" }, "Mittel": { de: "Mittel", en: "Medium" },
  "Gut": { de: "Gut", en: "Good" }, "Sehr gut": { de: "Sehr gut", en: "Very good" }, "Top": { de: "Top", en: "Top" },
};

function escapeHtml(v) {
  return String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function getEra(year) {
  const g = yearGroup(year);
  return g ? { label: tr(g.label), color: g.color } : { label: tr(BUILDING_KEYS[0].label), color: NO_YEAR_COLOR };
}

// "8136/813600" (PLZ / PLZ6) -> "8136"
function plzOf(p) {
  return p.plz ? String(p.plz).split("/")[0] : "";
}

// GWR building class (gklas, `building_class`): what the building is, finer
// than the category. Shown under the address.
const CLASS_NAMES = {
  1110: { de: "Einfamilienhaus", en: "Single-family house" },
  1121: { de: "Zweifamilienhaus", en: "Two-family house" },
  1122: { de: "Mehrfamilienhaus", en: "Apartment building" },
  1130: { de: "Wohnheim", en: "Residential home" },
  1211: { de: "Hotel", en: "Hotel" },
  1212: { de: "Kurzfristige Beherbergung", en: "Short-stay accommodation" },
  1220: { de: "Bürogebäude", en: "Office building" },
  1230: { de: "Handelsgebäude", en: "Retail building" },
  1231: { de: "Restaurant / Bar", en: "Restaurant / bar" },
  1241: { de: "Verkehr / Kommunikation", en: "Transport / communication" },
  1242: { de: "Garage", en: "Garage" },
  1251: { de: "Industriegebäude", en: "Industrial building" },
  1252: { de: "Lager / Silo / Behälter", en: "Storage / silo / tank" },
  1261: { de: "Kultur / Freizeit", en: "Culture / leisure" },
  1262: { de: "Museum / Bibliothek", en: "Museum / library" },
  1263: { de: "Schule / Hochschule", en: "School / university" },
  1264: { de: "Spital / Gesundheit", en: "Hospital / health" },
  1265: { de: "Sporthalle", en: "Sports hall" },
  1271: { de: "Landwirtschaft", en: "Farm building" },
  1272: { de: "Kirche / Kultbau", en: "Church / place of worship" },
  1273: { de: "Denkmal", en: "Monument" },
  1274: { de: "Sonstiger Hochbau", en: "Other building" },
  1275: { de: "Gemeinschaftsunterkunft", en: "Collective accommodation" },
  1276: { de: "Tierhaltung", en: "Livestock building" },
  1277: { de: "Pflanzenbau", en: "Greenhouse / crop building" },
  1278: { de: "Landwirtschaft (andere)", en: "Farm building (other)" },
};

// Exposure limits (Immissionsgrenzwerte) of the Noise Abatement Ordinance
// (LSV, annexes 3 and 4: road and rail are the same) per sensitivity level,
// [day, night] in dB(A). The card marks them on the noise meters.
const NOISE_LIMITS = { I: [55, 45], II: [60, 50], III: [65, 55], IV: [70, 60] };
const NOISE_SCALE = [30, 75];   // dB at the meter's ends

const isNum = v => v !== null && v !== undefined && v !== "" && !isNaN(Number(v));
const fmtNum = (n, digits = 0) => Number(n).toLocaleString(locale(),
  { maximumFractionDigits: digits, minimumFractionDigits: digits });

// The class a building falls in for a colour mode ("heating", "noise_road_n",
// ...; web/layers.js) or a ground theme ("hazard", "zoning", ...), with the
// colour the map gives it: { color, outline, label } or null. The card draws
// every value in its layer's colour (owner: "more colour,
// matching the layers"), so the card reads like the map.
// (modeClass is in web/layers.js: the legend bar counts with it too)
function groundClass(id, p) {
  const g = GROUND_THEMES.find(x => x.id === id);
  if (!g) return null;
  const db = Number(p.aircraft_db);
  const value = { hazard: p.hazard, runoff: p.runoff, contaminated: p.contaminated, zoning: p.zone, es: p.es, oev: p.oev_class,
    aircraft: db >= 67 ? "db67" : db >= 64 ? "db64" : db >= 61 ? "db61" : db >= 58 ? "db58" : null }[id];
  const c = value && g.classes.find(k => [].concat(k.v).includes(value));
  return c ? { color: c.color, outline: c.color, label: c.label } : null;
}

// Everything we know about a building, for the card and the inspector:
//   figures:  the key numbers (flats, floors, footprint, volume), each with
//             its colour mode's class where there is one
//   sections: themed blocks; a block is { key, text, ... } where `key` is the
//             i18n key (also what a colour mode's / ground theme's `fact`
//             names, so the card can mark the active one), `text` the plain
//             value (inspector), and the rest says how the card draws it:
//               main / sub   the value large, a detail line small
//               cls          { color, ... }: drawn as a chip in that colour
//               meter        noise rows [label, dB, limit]
//               scale        a mode's classes with the building's one marked
//               share        a 0-100 bar
//               na           no value: why (no data, not assessed, not in
//                            the register, ...), drawn as a dashed chip
//             Every block always appears (owner: the card shows
//             what we don't know too); `col` is the card column (0 left,
//             1 right). `tags`: the building's small facts, [text, known].
function buildingCardModel(p) {
  const join = (...parts) => parts.filter(Boolean).join(" · ");
  const na = t("hc.na");

  // the key figures, always all five ("–" without a value)
  const figures = [];
  // a figure this city has no source for: "–", its tooltip says so (web/city.js coverage)
  const fig = (key, has, value, cls) => (cardUnavailable(key)
    ? figures.push({ key, value: "–", cls: null, text: covText("cov.na"), unavailable: true })
    : figures.push({ key, value: has ? value : "–", cls: has ? cls : null, text: has ? value : na }));
  fig("hc.built", !!p.baujahr, String(p.baujahr), modeClass("year", p));
  fig("hc.dwellings", isNum(p.num_dwellings), fmtNum(p.num_dwellings), modeClass("dwellings", p));
  fig("hc.floorCount", isNum(p.floors) && p.floors > 0, fmtNum(p.floors), modeClass("floors", p));
  fig("hc.area", isNum(p.area_m2) && p.area_m2 > 0, `${fmtNum(p.area_m2)} m²`);
  fig("hc.volume", isNum(p.volume_m3) && p.volume_m3 > 0, `${fmtNum(p.volume_m3)} m³`);

  // the building's small facts as pills; [text, known]
  const shelter = Number(p.civil_defense_shelter);
  const rooms = Number(p.separate_rooms);
  // use: GWR category (Zürich), or OSM's building type (Belgrade: housing / not / unknown)
  const osmUse = p.housing === 1 ? { de: "Wohngebäude (OSM)", en: "Residential (OSM)", sr: "Stambeni (OSM)" }
    : p.housing === 0 ? { de: "Ohne Wohnnutzung (OSM)", en: "No housing (OSM)", sr: "Bez stanovanja (OSM)" } : null;
  const tags = [
    // unknown: the label with a dash, in a dashed pill
    CITY.housing === "osm" ? [tr(osmUse) || `${t("hc.use")} –`, !!osmUse, "use"]
      : [tr(CATEGORY_NAMES[p.building_category]) || `${t("hc.use")} –`, !!CATEGORY_NAMES[p.building_category], "use"],
    [isNum(p.elevation_m) ? `${fmtNum(p.elevation_m)} ${t("hc.asl")}` : `${t("hc.elevation")} –`, isNum(p.elevation_m), "elevation"],
    // GWR gschutzr (civil-defence shelter, 0 / 1) and gazzi (separate rooms outside the flats)
    [shelter === 1 ? t("hc.shelter") : shelter === 0 ? t("hc.noShelter") : `${t("hc.shelter")} –`, isNum(p.civil_defense_shelter), "shelter"],
    [isNum(p.separate_rooms) ? `${fmtNum(rooms)} ${t("hc.rooms")}` : `${t("hc.rooms")} –`, isNum(p.separate_rooms), "rooms"],
    // GWR gebf: the energy reference area (heated floor area), not the footprint
    [isNum(p.heated_area_m2) && p.heated_area_m2 > 0 ? `${fmtNum(p.heated_area_m2)} m² ${t("hc.heatedArea")}` : `${t("hc.heatedArea")} –`,
      isNum(p.heated_area_m2) && p.heated_area_m2 > 0, "heatedArea"],
  ].filter(tg => !cardUnavailable(`tag.${tg[2]}`));   // facts this city has no source for: left out

  // a block: { key, main, sub, cls, half } or, without a value, { key, na: why }
  const block = (key, main, extra) => (main
    ? { key, main, half: true, text: join(main, extra && extra.sub), ...extra }
    : { key, na: (extra && extra.why) || na, half: !(extra && extra.half === false), text: (extra && extra.why) || na });

  // heating: the class (the heating mode's colour), the generator below
  const heatCls = modeClass("heating", p);
  const generator = tr(HEATING_NAMES[p.heating_code]), energy = tr(ENERGY_NAMES[p.heating_energy]);
  // the second heating (gwaerzh2 / genh2); 7400 / 7500 = "none"
  const known2 = isNum(p.heating_source_2) || isNum(p.heating_code_2);
  const energy2 = isNum(p.heating_code_2) && p.heating_code_2 !== 7500 ? tr(ENERGY_NAMES[p.heating_code_2]) : null;
  const generator2 = isNum(p.heating_source_2) && p.heating_source_2 !== 7400 ? tr(HEATING_NAMES[p.heating_source_2]) : null;
  const cap = v => (v ? v.charAt(0).toUpperCase() + v.slice(1) : v);

  // solar: the four classes of the solar mode, the building's marked
  const kwh = Number(p.solar_annual_kwh);
  const solarSub = join(kwh > 0 ? (kwh >= 1000 ? `${fmtNum(kwh / 1000, 1)} MWh/${t("hc.year")}` : `${fmtNum(kwh)} kWh/${t("hc.year")}`) : null,
    Number(p.solar_annual_revenue_chf) > 0 ? `≈ CHF ${fmtNum(p.solar_annual_revenue_chf)}` : null,
    Number(p.solar_panel_area_m2) > 0 ? `${fmtNum(p.solar_panel_area_m2)} m²` : null);
  const solarMode = BUILDING_COLOR_MODES.find(m => m.id === "solar");
  const solarAt = p.solar_best_class ? solarMode.classes.findIndex(k => k.values.includes(p.solar_best_class)) : -1;

  // noise: BAFU's modelled façade noise, on the noise mode's scale
  const limits = NOISE_LIMITS[p.es];
  const noise = (key, mode, day, night, why) => {
    if (!isNum(day)) return { key, na: why, text: why };
    const d = Math.round(day), n = isNum(night) ? Math.round(night) : null;
    const over = limits && (d > limits[0] || (n !== null && n > limits[1]));
    return { key, text: join(`${d} dB ${t("hc.day")}`, n !== null ? `${n} dB ${t("hc.night")}` : null, over ? `${t("hc.overLimit")} (ES ${p.es})` : null),
      meter: { mode, rows: [[t("hc.day"), d, limits && limits[0]], ...(n !== null ? [[t("hc.night"), n, limits && limits[1]]] : [])] },
      note: over ? `${t("hc.overLimit")} (ES ${p.es})` : null };
  };

  const zoneLabel = groundLabel("zoning", p.zone);
  const built = isNum(p.parcel_built_pct) ? Number(p.parcel_built_pct) : null;
  const oevCls = groundClass("oev", p);
  const stopKind = { train: { de: "Bahn", en: "rail" }, tram: "Tram", bus: "Bus", boat: { de: "Schiff", en: "boat" },
    funicular: { de: "Standseilbahn", en: "funicular" } }[p.stop_kind];

  const sections = [
    { key: "hc.sec.energy", col: 0, blocks: [
      block("hc.heating", heatCls ? tr(heatCls.label) : (generator || energy), { cls: heatCls, sub: join(generator, heatCls ? null : energy) }),
      block("hc.heating2", known2 ? (cap(energy2) || generator2 || t("hc.none")) : null, { sub: energy2 ? generator2 : null, plain: !(energy2 || generator2) }),
      solarAt >= 0
        ? { key: "hc.solar", text: join(tr(SOLAR_CLASSES[p.solar_best_class]), solarSub),
            main: tr(SOLAR_CLASSES[p.solar_best_class]) || p.solar_best_class, scale: { classes: solarMode.classes, at: solarAt }, sub: solarSub }
        : { key: "hc.solar", na, text: na },
    ] },
    // land plot (cadastral survey)
    { key: "hc.sec.plot", col: 0, blocks: [
      Number(p.parcel_area_m2) > 0
        ? { key: "hc.sec.plot", main: `${fmtNum(p.parcel_area_m2)} m²`, aside: p.parcel_number && `${t("hc.plotNr")} ${p.parcel_number}`,
            share: built, shareLabel: built !== null ? `${built} % ${t("hc.plotBuilt")}` : null,
            text: join(`${fmtNum(p.parcel_area_m2)} m²`, built !== null ? `${built} % ${t("hc.plotBuilt")}` : t("hc.builtUnknown"), p.parcel_number) }
        : { key: "hc.sec.plot", na, text: na },
    ] },
    { key: "hc.sec.noise", col: 1, blocks: [
      noise("hc.roadNoise", "noise_road", p.noise_road_day_db, p.noise_road_night_db, na),
      // no value = no rail model at that spot (the rail-noise mode draws it as the lowest class)
      noise("hc.railNoise", "noise_rail", p.noise_rail_day_db, p.noise_rail_night_db, t("hc.noRail")),
      // the aircraft-noise map starts at 58 dB
      block("hc.aircraft", isNum(p.aircraft_db) ? `${p.aircraft_db} dB` : null, { cls: groundClass("aircraft", p),
        sub: tr(AIRCRAFT_LIMIT[p.aircraft_limit]), why: t("hc.below58") }),
      block("hc.es", p.es && p.es !== "none" ? `ES ${p.es}` : null, { cls: groundClass("es", p),
        sub: (groundLabel("es", p.es) || "").replace(/^ES [IV]+:\s*/, ""), why: p.es === "none" ? t("hc.noEs") : na }),
    ] },
    { key: "hc.sec.location", col: 1, blocks: [
      // public transport to Zürich HB, weekday morning (cities/zurich/pipeline/swiss/build_walk.py)
      // an estimate, not a timetable query for this address (C-05): "≈", the model in the card foot
      block("hc.commute", isNum(p.commute_hb_min) ? `≈ ${p.commute_hb_min} min` : null, { cls: modeClass("commute", p),
        sub: p.commute_hb_stop && `${t("hc.commuteFrom")} ${p.commute_hb_stop}`, why: t("hc.noStopNear") }),
      // ARE quality grade the building lies in; outside every grade = below D (build_transit.py)
      block("hc.oev", p.oev_class ? tr(oevCls && oevCls.label) || p.oev_class : null, { cls: oevCls, why: t("hc.noOev") }),
      block("hc.zone", p.zone_abbr || zoneLabel, { cls: groundClass("zoning", p), sub: p.zone_abbr ? zoneLabel : null }),
      // the stop the commute to HB goes from (on foot / C-04; the
      // nearest on foot where there is none), with the gist of its timetable
      // card; the straight-line stop of build_transit.py without either
      (ns => ns
        ? block(ns.key, ns.main, { plain: true, sub: ns.sub, near: ns.idx, gist: ns.nr })   // idx / nr null until the index is there
        : block("hc.stop", isNum(p.stop_m) ? `${fmtNum(p.stop_m)} m` : null, { plain: true, sub: join(tr(stopKind), p.stop_name, t("pc.straight")) }))(
        typeof nearStop === "function" ? nearStop(p) : null),
    ] },
    // ground facts (033 / 034); no hazard = not assessed, not "safe"
    { key: "hc.sec.risks", col: 0, blocks: [
      block("hc.hazard", p.hazard ? groundLabel("hazard", p.hazard) : null, { cls: groundClass("hazard", p),
        sub: tr(HAZARD_PROCESS[p.hazard_process]), why: t("hc.notAssessed") }),
      block("hc.runoff", p.runoff ? tr(RUNOFF_DEPTH[p.runoff]) || p.runoff : null, { cls: groundClass("runoff", p), why: t("hc.noRunoff") }),
      // register: the canton's, or a federal one (BAV public transport, VBS army, BAZL airfields)
      block("hc.contaminated", p.contaminated ? tr(CONTAMINATED_STATUS[p.contaminated]) : null, { cls: groundClass("contaminated", p), half: false,
        sub: join(tr(CONTAMINATED_SITE[p.contaminated_site]), p.contaminated_register && p.contaminated_register !== "ZH" ? p.contaminated_register : null),
        why: t("hc.notRegistered") }),
    ] },
  ];
  // a block this city has no source for (web/city.js coverage): a dashed "not available in <city>" chip
  for (const s of sections) s.blocks = s.blocks.map(b => (cardUnavailable(b.key) ? { key: b.key, na: covText("cov.na"), half: b.half, text: covText("cov.na") } : b));
  return { figures, tags, sections };
}

// 2D / 3D: the map menu owns it (web/controls.js); for scripts and the console
function setViewMode(mode) { controls.setView(mode); }

// Hover Tooltip on Building Polygons
// (maxWidth: the card sets its own width in style.css)
const popup = new maplibregl.Popup({
  closeButton: false,
  closeOnClick: false,
  offset: 12,
  maxWidth: "none"
});

// The building card is taller than MapLibre's automatic anchoring can fit, so
// it is placed by hand: its top-left corner beside the pointer, on the side
// with room (or, where neither side has room, clamped into the map), shifted
// up or down to stay inside the map (and clear of the controls). No tip: it would point at the card's middle, not the pointer.
let placing = false;   // a card being redrawn in place: its "close" doesn't clear the selection
function placeCard(card, lngLat, html) {
  // the page itself never scrolls (a focused element half off screen once scrolled it; 048)
  for (const s of [document.scrollingElement, map.getContainer()]) if (s && (s.scrollTop || s.scrollLeft)) s.scrollTop = s.scrollLeft = 0;
  placing = true;
  card.setLngLat(lngLat).setHTML(html).addTo(map);
  placing = false;
  const el = card.getElement();
  el.classList.add("bg-card-popup");
  el.classList.toggle("bg-hover-popup", card === popup);
  const W = el.offsetWidth;
  let H = el.offsetHeight;
  const c = map.getCanvas(), pt = map.project(lngLat);
  const left = 8 + ((map.getPadding && map.getPadding().left) || 0), right = c.clientWidth - 8;
  const gap = 14;
  let top = 8, bottom = c.clientHeight - 40;   // clear of the attribution pin in the corner
  // beside the pointer: right of it if that fits, else left of it; a third
  // of the card above the pointer, kept inside the map
  let x = null;
  if (pt.x + gap + W <= right) x = pt.x + gap;
  else if (pt.x - gap - W >= left) x = pt.x - gap - W;
  let y;
  if (x !== null) {
    y = Math.max(top, Math.min(pt.y - H / 3, bottom - H));
  } else {
    // no room beside it (near the search-profile panel or a narrow window): below or above
    // the pointer if that fits; otherwise the whole card inside the map,
    // over the pointer if need be (the hover card lets the mouse through,
    // see .bg-hover-popup, so the map keeps its hover)
    x = Math.max(left, Math.min(pt.x - W / 2, right - W));
    if (pt.y + gap + H <= bottom) y = pt.y + gap;
    else if (pt.y - gap - H >= top) y = pt.y - gap - H;
    else {
      x = pt.x - left > right - pt.x ? left : right - W;   // the side with more room
      y = Math.max(top, Math.min(pt.y - H / 3, bottom - H));
    }
  }
  // keep clear of the controls over the map (web/controls.js): below the
  // top-left chrome and above the legend bar where the card would meet them
  const box = c.getBoundingClientRect();
  const over = r => r.width && x + box.left < r.right && x + box.left + W > r.left;
  for (const sel of [".bc-row", ".bc-chips"]) {
    const el = document.querySelector(sel), r = el && el.getBoundingClientRect();
    if (r && over(r) && getComputedStyle(el).display !== "none") top = Math.max(top, r.bottom - box.top + 8);
  }
  const lg = document.querySelector(".bc-legend"), lr = lg && lg.getBoundingClientRect();
  if (lr && over(lr)) bottom = Math.min(bottom, lr.top - box.top - 8);
  // a card taller than the free band (a long search profile, chips in two rows)
  // gets the band's height and scrolls inside (pinned) or is cut with a fade
  // (hover: the click pins the whole card); before 048 it ran off the screen
  const body = el.querySelector(".hover-card");
  if (body && H > bottom - top) {
    // the band minus the popup's own frame around the card
    body.style.maxHeight = `${Math.max(160, bottom - top - (H - body.offsetHeight))}px`;
    body.classList.toggle("hc-capped", card === popup);
    H = el.offsetHeight;
  }
  if (y + H > bottom) y = Math.max(top, bottom - H);
  if (y < top) y = top;
  const dx = x - pt.x, dy = y - pt.y;
  card.setOffset([dx, dy]);
  // a pinned card takes the focus (keyboard users land in it), without scrolling anything
  if (card !== popup) {
    const f = el.querySelector(".maplibregl-popup-close-button");
    if (f && !el.contains(document.activeElement)) f.focus({ preventScroll: true });
  }
}

// The building card: on hover, and pinned on click with the links (the ÖREB
// extract: the official register of public-law restrictions on the plot, a PDF
// from the canton by the plot's EGRID). Layout:
// header (address, place, building type, year), the key figures as tiles,
// then the themed sections in two columns (one on a phone), ids at the foot.
// Values are drawn, not listed: chips in the layer's colour, noise meters on
// the noise mode's scale, the solar classes as a scale, the plot's built
// share as a bar. Text stays in the text colour on a light tint of the class
// colour (CLAUDE.md: text never wears a data colour).
function buildingCardHtml(p, pinned) {
  const era = getEra(p.baujahr);
  const status = tr(UNFINISHED_STATUS[p.building_status]);
  const type = tr(CLASS_NAMES[p.building_class] || (CITY.classNames || {})[p.building_class]);
  const place = `${plzOf(p)} ${p.municipality || ''}`.trim();
  const { figures, tags, sections } = buildingCardModel(p);
  const allBlocks = sections.flatMap(s => s.blocks);
  const firstMeter = allBlocks.find(b => b.meter && b.meter.rows.some(r => r[2]));
  const esBlock = allBlocks.find(b => b.key === "hc.es");
  const active = activeFacts();
  const on = key => (active.includes(key) ? " hc-active" : "");
  const tint = cls => (cls ? ` style="--c:${cls.color};--o:${cls.outline || cls.color}"` : "");
  const pos = v => Math.max(0, Math.min(100, (v - NOISE_SCALE[0]) / (NOISE_SCALE[1] - NOISE_SCALE[0]) * 100)).toFixed(1);

  // noise: the mode's seven colours as the track, lit up to the value
  const meter = ({ mode, rows }) => {
    const m = BUILDING_COLOR_MODES.find(x => x.id === mode);
    const edges = [NOISE_SCALE[0], ...m.variants[0].steps, NOISE_SCALE[1]];
    return `<div class="hc-meter">${rows.map(([label, db, limit]) => `
      <span class="hc-meter-label">${escapeHtml(label)}</span>
      <span class="hc-track">${m.colors.map((c, i) => {
        const a = edges[i], b = edges[i + 1];
        const lit = db >= b ? 100 : db <= a ? 0 : (db - a) / (b - a) * 100;
        return `<i style="--c:${c};flex:${b - a}"><b style="width:${lit.toFixed(0)}%"></b></i>`;
      }).join("")}${limit ? `<u style="left:${pos(limit)}%" title="${escapeHtml(t("hc.limitNote"))} ${escapeHtml(p.es)}"></u>` : ""}</span>
      <span class="hc-meter-value">${db}<small> dB</small></span>`).join("")}</div>`;
  };
  const scale = ({ classes, at }) => `<div class="hc-scale">${classes.map((k, i) =>
    `<i class="${i === at ? "hc-on" : ""}" style="--c:${k.color};--o:${k.outline}" title="${escapeHtml(tr(k.label))}"></i>`).join("")}</div>`;

  const blockHtml = b => {
    // the first meter's caption carries the limit legend and the ES chip
    // (the ES block is then left out)
    if (b.key === "hc.es" && firstMeter) return "";
    const aside = b === firstMeter && esBlock
      ? `<span class="hc-legend${on("hc.es")}" title="${escapeHtml(t("hc.limitNote"))} ${escapeHtml(p.es)}"><u></u>${t("hc.limit")} <span class="hc-chip hc-mini"${tint(esBlock.cls)}>${escapeHtml(esBlock.main)}</span></span>`
      : b.scale ? `<span class="hc-aside">${escapeHtml(b.main)}</span>`
      : b.aside ? `<span class="hc-aside hc-quiet-text">${escapeHtml(b.aside)}</span>` : "";
    const head = `<div class="hc-cap"><span>${t(b.key)}</span>${aside}</div>`;
    let body;
    if (b.na) {
      body = `<div class="hc-main"><span class="hc-chip hc-na">${escapeHtml(b.na)}</span></div>`;
    } else if (b.meter) {
      body = `${meter(b.meter)}${b.note ? `<div class="hc-over-note">${escapeHtml(b.note)}</div>` : ""}`;
    } else if (b.scale) {
      body = `${scale(b.scale)}${b.sub ? `<div class="hc-sub">${escapeHtml(b.sub)}</div>` : ""}`;
    } else if (b.share !== undefined) {
      body = `<div class="hc-share"><strong>${escapeHtml(b.main)}</strong>${b.share !== null
        ? `<span><i style="width:${Math.min(100, b.share)}%"></i></span>${escapeHtml(b.shareLabel)}`
        : `<em class="hc-unk">${escapeHtml(t("hc.builtUnknown"))}</em>`}</div>`;
    } else {
      body = `<div class="hc-main"><span class="hc-chip${b.cls ? "" : " hc-plain"}"${tint(b.cls)}>${escapeHtml(b.main)}</span></div>${b.sub ? `<div class="hc-sub">${escapeHtml(b.sub)}</div>` : ""}`;
    }
    const gist = b.gist != null ? `<div class="hc-gist" data-stop-gist="${escapeHtml(b.gist)}"></div>` : "";
    const near = pinned && b.near != null ? ` data-near="${b.near}" role="button" tabindex="0"` : "";
    return `<div class="hc-block${b.half ? " hc-half" : ""}${b.near != null && pinned ? " hc-link" : ""}${on(b.key)}"${near}>${head}${body}${gist}</div>`;
  };

  const links = pinned && p.egrid
    ? `<div class="hc-links"><a href="https://maps.zh.ch/oereb/v2/extract/pdf?EGRID=${encodeURIComponent(p.egrid)}" target="_blank" rel="noopener">${t("hc.oereb")}</a></div>` : '';
  const foot = [p.egid && CITY.idLabel ? `${CITY.idLabel} ${escapeHtml(p.egid)}` : null, p.egrid ? `EGRID ${escapeHtml(p.egrid)}` : null,
    FOOTPRINT_LABELS[p.geometry_type] ? `${t("hc.footprint")}: ${escapeHtml(tr(FOOTPRINT_LABELS[p.geometry_type]))}` : null,
    pinned ? null : t("hc.pinHint")].filter(Boolean).join(" · ");
  // where the facts come from, with their data dates (C-05; cities/zurich/pipeline/card_sources.py), on the pinned card
  const sources = pinned ? cardSourcesHtml("building", true) : "";
  return `
    <div class="hover-card hc-building" data-egid="${escapeHtml(p.egid)}">
      <div class="hc-head">
        <div class="hc-title">${escapeHtml(p.address || t("hc.building"))}${status ? ` <span class="status-badge">${status}</span>` : ''}${p.underground ? ` <span class="status-badge hc-quiet">${t("hc.underground")}</span>` : ''}</div>
        <div class="hc-place">${escapeHtml([place, type].filter(Boolean).join(" · "))}</div>
        <div class="hc-tags">${tags.map(([x, known]) => `<span${known ? "" : ' class="hc-na-tag"'}>${escapeHtml(x)}</span>`).join("")}</div>
      </div>
      ${profileStripHtml(p)}
      ${figures.length ? `<div class="hc-figures">${figures.map(f => `
        <div class="hc-fig${f.cls ? " hc-tinted" : ""}${f.unavailable ? " hc-fig-na" : ""}${on(f.key)}"${tint(f.cls)}${f.unavailable ? ` title="${escapeHtml(f.text)}"` : f.key === "hc.built" && p.baujahr ? ` title="${escapeHtml(era.label)}"` : ""}><strong>${escapeHtml(f.value)}</strong><span>${t(f.key)}</span></div>`).join("")}
      </div>` : ""}
      <div class="hc-sections">${[0, 1].map(col => `<div class="hc-col">${sections.filter(s => s.col === col).map(s => `
        <section class="hc-sec">
          <div class="hc-blocks">${s.blocks.map(blockHtml).join("")}</div>
        </section>`).join("")}</div>`).join("")}
      </div>
      ${typeof nearbyHtml === "function" ? nearbyHtml(p, pinned) : ""}
      <div class="hc-foot">${foot}</div>
      ${sources ? `<div class="hc-foot pc-sources">${sources}${cardUnavailable("hc.commute") ? "" : `<br>${escapeHtml(t("hc.commuteModel"))}`}</div>` : ""}
      ${links}
    </div>`;
}

// "Passt zum Suchprofil, n von m": each criterion of the search
// profile with the building's value and whether it passes (filters) or is
// marked (mark only); nothing without a profile
function profileStripHtml(p) {
  const list = (typeof controls !== "undefined" && controls.state.crits) || [];
  if (!list.length) return "";
  const rows = list.map(c => ({ c, ok: critPass(c, p) }));
  const filters = rows.filter(r => !r.c.mark), passed = filters.filter(r => r.ok).length;
  const head = filters.length
    ? `<b>${t(passed === filters.length ? "pf.fits" : "pf.fitsNot")}</b><span>${passed} ${t("pf.of")} ${filters.length}</span>`
    : `<b>${t("pf.marks")}</b>`;
  return `
      <section class="hc-profile${filters.length && passed < filters.length ? " hc-profile-no" : ""}" aria-label="${escapeHtml(t("ctl.profile"))}">
        <div class="hc-profile-head">${head}</div>
        <div class="hc-profile-rows">${rows.map(({ c, ok }) => `
          <div class="hc-profile-row${c.mark ? " hc-mark" : ""}">
            <span class="hc-ok${ok ? " yes" : ""}" aria-hidden="true">${ok ? "✓" : "–"}</span>
            <span class="hc-profile-label">${escapeHtml((c.mark ? `${t("pf.marked")}: ` : "") + critText(c))}<span class="bg-sr"> (${escapeHtml(t(c.mark ? (ok ? "pf.marked" : "pf.notMarked") : (ok ? "pf.pass" : "pf.fail")))})</span></span>
            <b>${escapeHtml(critValue(c, p))}</b>
          </div>`).join("")}
        </div>
      </section>`;
}

// The sources of the building / stop cards ({card: {code: {de, en, url, date}}},
// data/layers/card_sources.json), loaded once; "Quellen: name (date) · ...".
let CARD_SOURCES = {};
fetch("../data/card_sources.json").then(r => (r.ok ? r.json() : {})).then(d => { CARD_SOURCES = d || {}; lateData(); }).catch(() => {});
function cardSourcesHtml(card, linked) {
  const list = Object.values(CARD_SOURCES[card] || {});
  if (!list.length) return "";
  return `${escapeHtml(t("pc.sources"))}: ${list.map(s => {
    const name = escapeHtml(tr(s)) + (s.date ? ` (${freshDateHtml(s.date)})` : "");   // in its age colour (C-16)
    return linked && s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${name}</a>` : name;
  }).join(" · ")}`;
}

// The card follows the building under the pointer (mousemove, not only
// mouseenter, which fires once for the whole layer), redrawn only when that
// building changes; none while a card is pinned, nor on a phone (no hover:
// a tap opens the sheet below).
let hoveredEgid = null;
const isNarrow = () => window.matchMedia("(max-width: 600px)").matches;
function handleBuildingHover(e) {
  map.getCanvas().style.cursor = 'pointer';
  if (!e.features.length || pinnedCard.isOpen() || sheet || isNarrow()) return;
  // a place icon on top of the building wins: its card, not the building's
  // (web/places.js; stops in web/stops.js)
  if (placeAt(e.point)) return;
  const p = e.features[0].properties;
  if (popup.isOpen() && hoveredEgid === p.egid) return;
  hoveredEgid = p.egid;
  popup.options.anchor = "top-left";
  placeCard(popup, e.lngLat, buildingCardHtml(p, false));
  rememberCard({ draw: () => buildingCardHtml(p, false), pinned: false, lngLat: e.lngLat, sel: `.hc-building[data-egid="${p.egid}"]` });
  if (typeof hydrateBuildingCard === "function") hydrateBuildingCard();
}

// click: the same card, pinned (with a close button and the ÖREB link); on a
// phone as a sheet along the bottom of the screen, since a card the size of
// the screen anchored at the tap would run off it
// focusAfterOpen off: MapLibre would focus the card before placeCard moves it,
// while it still hangs below the screen, and the browser scrolled the whole
// page to it (the map and its controls shifted up). placeCard
// focuses it once it is in place.
const pinnedCard = new maplibregl.Popup({ closeButton: true, closeOnClick: true, offset: 12, maxWidth: "none", anchor: "top-left", focusAfterOpen: false });
let sheet = null;
function dropSheet() {
  if (sheet) { sheet.remove(); sheet = null; }
}
// closing the card also drops the ring around its building
function closeSheet() {
  dropSheet();
  controls.select(null);
}
pinnedCard.on("close", () => { if (!placing) controls.select(null); });
// lngLat: what the card is about; the first time a sheet shows it, the map
// moves so it sits in the free band between the controls and the sheet
// (the sheet hid the building that was tapped). A redraw of the
// same card (late data, the stop card loading) keeps its height and the map.
let sheetAt = null;
function openSheet(html, lngLat) {
  const tall = !!sheet && sheet.classList.contains("bg-sheet-tall");
  const scroll = sheet ? sheet.scrollTop : 0;
  const same = !!sheet && lngLat && sheetAt && sheetAt.lng === lngLat.lng && sheetAt.lat === lngLat.lat;
  dropSheet();
  sheet = document.createElement("div");
  sheet.className = `hc-sheet${tall && same ? " bg-sheet-tall" : ""}`;
  sheet.setAttribute("role", "dialog");
  sheet.innerHTML = `<button type="button" class="hc-sheet-close" aria-label="${t("hc.close")}">×</button>${html}`;
  sheet.querySelector(".hc-sheet-close").addEventListener("click", closeSheet);
  attachSheetHandle(sheet, closeSheet);   // web/controls.js
  document.body.appendChild(sheet);
  if (same) sheet.scrollTop = scroll;
  if (lngLat && !same) { sheetAt = { lng: lngLat.lng, lat: lngLat.lat }; keepAboveSheet(lngLat); }
}
function keepAboveSheet(lngLat) {
  const sheetTop = sheet.getBoundingClientRect().top;
  let top = 0;
  for (const sel of [".bc-row", ".bc-chips"]) {
    const el = document.querySelector(sel), r = el && el.getBoundingClientRect();
    if (r && r.height && getComputedStyle(el).display !== "none") top = Math.max(top, r.bottom);
  }
  const y = map.project(lngLat).y, pad = 24;
  if (y > top + pad && y < sheetTop - pad) return;   // already in view
  const target = sheetTop - top > 3 * pad ? (top + sheetTop) / 2 : sheetTop - pad;
  map.panBy([0, y - target], { duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 400 });
}
let pinnedAt = 0;   // performance.now() of the last pin: a click's own timeStamp is on the same clock

// The card on screen and how to draw it again. Some of what a card shows
// arrives after it opened (the place index, the source tables: small JSON
// files fetched at start-up); when one arrives, lateData() redraws the card
// that is still showing, so it never keeps a placeholder or a wrong default.
//   { draw: () => html, pinned, lngLat, sel: a selector that finds this card }
let openCard = null;
function rememberCard(c) { openCard = c; }
window.addEventListener("bg:profile", () => lateData());   // the profile changed: the card's strip with it
function lateData() {
  const c = openCard;
  if (!c) return;
  const host = c.pinned ? (sheet || (pinnedCard.isOpen() && pinnedCard.getElement())) : (popup.isOpen() && popup.getElement());
  if (!host || !host.querySelector(c.sel)) return;   // that card has been replaced or closed
  const html = c.draw();
  if (c.pinned && sheet) openSheet(html, c.lngLat);
  else placeCard(c.pinned ? pinnedCard : popup, c.lngLat, html);
  if (typeof hydrateBuildingCard === "function") hydrateBuildingCard();
}

function handleBuildingPin(e) {
  if (!e.features.length) return;
  // a place icon on top of the building wins (the stop card pins itself)
  const places = PLACE_LAYERS.flatMap(pl => [`place-${pl.id}`, `place-${pl.id}-hub`]).filter(id => map.getLayer(id));
  if (places.length && map.queryRenderedFeatures(e.point, { layers: places }).length) return;
  openBuildingCard(e.features[0].properties, e.lngLat);
}
// a building's pinned card (a sheet on a phone), with its ring on the map
function openBuildingCard(bp, lngLat) {
  pinnedAt = performance.now();
  popup.remove();
  const html = buildingCardHtml(bp, true);
  rememberCard({ draw: () => buildingCardHtml(bp, true), pinned: true, lngLat, sel: `.hc-building[data-egid="${bp.egid}"]` });
  if (isNarrow()) openSheet(html, lngLat);
  else { pinnedCard.options.anchor = "top-left"; placeCard(pinnedCard, lngLat, html); }
  controls.select(bp);
  if (typeof hydrateBuildingCard === "function") hydrateBuildingCard();
}
// The address search (web/search.js): fly to a building by its
// EGID and open its card once its tile is there. The buildings show from z13;
// 17 frames the building with its street.
function openBuildingByEgid(egid, lngLat) {
  if (!controls.state.layers.has("b")) { controls.state.layers.add("b"); controls.apply(); }
  pinnedCard.remove();
  closeSheet();
  const open = () => {
    const hit = map.querySourceFeatures("cadastre", { sourceLayer: "buildings", filter: ["==", ["to-string", ["get", "egid"]], String(egid)] })[0];
    if (hit) openBuildingCard(hit.properties, lngLat);
  };
  map.once("idle", open);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  map.flyTo({ center: [lngLat.lng, lngLat.lat], zoom: Math.max(17, map.getZoom()), duration: reduce ? 0 : 1200 });
}
map.on('click', 'buildings-2d', handleBuildingPin);
map.on('click', 'buildings-3d', handleBuildingPin);
// a tap on the map next to the buildings closes the sheet (the layer click
// above runs first for a tap on a building)
// Not a fixed time window: building the card took more than 50 ms on a slow
// phone, and the same tap closed the sheet it had just opened. A card pinned
// while this click was handled has a pinnedAt at or after the click's own timeStamp.
map.on('click', e => {
  const t = e.originalEvent && e.originalEvent.timeStamp;
  if (t ? pinnedAt < t : performance.now() - pinnedAt > 50) closeSheet();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { pinnedCard.remove(); closeSheet(); }
});

function handleBuildingLeave() {
  map.getCanvas().style.cursor = '';
  hoveredEgid = null;
  popup.remove();
}

map.on('mousemove', 'buildings-2d', handleBuildingHover);
map.on('mouseleave', 'buildings-2d', handleBuildingLeave);
map.on('mousemove', 'buildings-3d', handleBuildingHover);
map.on('mouseleave', 'buildings-3d', handleBuildingLeave);

// Place icons: the name (and what serves a stop) on hover, since the style has
// no glyph server for labels. Icons sit above the buildings, so this card wins.
const MODE_NAMES = {
  train: { de: "Bahn", en: "Rail" }, metro: "Metro", tram: "Tram", bus: "Bus",
  boat: { de: "Schiff", en: "Boat" }, rack: { de: "Zahnradbahn", en: "Rack railway" },
  funicular: { de: "Standseilbahn", en: "Funicular" }, cable: { de: "Seilbahn", en: "Cable car" },
  lift: { de: "Lift", en: "Lift" },
};
// place icons: their cards are in web/places.js (stops: web/stops.js); leaving
// one closes its hover card
for (const pl of PLACE_LAYERS) {
  for (const id of [`place-${pl.id}`, `place-${pl.id}-hub`]) map.on('mouseleave', id, handleBuildingLeave);
}

// Click on a building: ringed on the map while its pinned card is open (C-10)
function handleBuildingClick(e) {
  if (!e.features.length) return;
  const places = PLACE_LAYERS.flatMap(pl => [`place-${pl.id}`, `place-${pl.id}-hub`]).filter(id => map.getLayer(id));
  if (places.length && map.queryRenderedFeatures(e.point, { layers: places }).length) return;
  controls.select(e.features[0].properties);
}

map.on('click', 'buildings-2d', handleBuildingClick);
map.on('click', 'buildings-3d', handleBuildingClick);

// Load Complete Event
// (The building count is hardcoded from the pipeline's own output, not a
// client-side fetch of the source GeoJSON -- that file is ~100MB and is
// exactly what the PMTiles archive exists to avoid loading.)
map.on('load', () => {
  const el = document.getElementById('building-count');
  if (el) el.innerText = '88,439 real GWR buildings (PMTiles)';
});


// The controls (web/controls.js, C-10); first, so the area fit below frames
// the area in the part of the map the search-profile panel leaves free.
const controls = initControls(map, { page: "map" });
// the card block the active lens is about (ringed on the card)
function activeFacts() {
  const m = colorMode(controls.state.lens);
  return [m && m.mode.fact].filter(Boolean);
}
initAreaOverlay(map);
