/**
 * The UI languages of each city (CITY.langs: Zürich de / en, Belgrade sr / en),
 * the first one the default. Loaded first by every page.
 *
 * - Fixed UI strings: STRINGS below, by key; in HTML mark an element with
 *   data-i18n="key" (text), data-i18n-aria="key" (aria-label) or
 *   data-i18n-title="key" (title); applyI18n() fills them in.
 * - Labels inside config lists (web/layers.js, web/years.js, the GWR code
 *   tables in web/map.js) are { de, en } objects; tr() picks the language.
 * - Place names, addresses and data values stay as they are.
 *
 * Choice, strongest first: ?lang= in the URL, then the browser's last choice
 * (localStorage), then the city's default. Switching updates the page in place (no
 * reload, the map keeps its view) and fires a "bg:lang" event on window,
 * which the sidebar listens to; hover cards read the language when they open.
 *
 * Usage: langSelect() returns the dropdown; addStrings({...}) adds strings
 * (the city's own, CITY.strings); t("key") / tr({ de, en, sr }) give the text.
 */
// the city's languages, its first the default (web/city.js: CITY.langs)
const ALL_LANGS = { de: "Deutsch", en: "English", sr: "Srpski" };
const LANGS = ((typeof CITY !== "undefined" && CITY.langs) || ["de", "en"]).map(id => ({ id, label: ALL_LANGS[id] }));
const DEFAULT_LANG = LANGS[0].id;

const STRINGS = {
  "lang.label": { de: "Sprache", en: "Language" },
  "title.map": typeof CITY !== "undefined" ? { de: `${CITY.name.de} · bg`, en: `${CITY.name.en} · bg`, sr: `${CITY.name.sr} · bg` } : { de: "bg", en: "bg" },

  // map controls (web/controls.js, C-10)
  "ctl.aria": { de: "Kartensteuerung", en: "Map controls" },
  "ctl.home": { de: "Zur Karte", en: "To the map" },
  "ctl.menu": { de: "Menü", en: "Menu" },
  "ctl.colorBy": { de: "Einfärben nach", en: "Colour by" },
  "ctl.lensHint": { de: "eine Linse auf einmal; Flächen-Linsen färben die Gebäude und auf Wunsch den Boden", en: "one lens at a time; area lenses colour the buildings and, if you like, the ground" },
  "ctl.area": { de: "Fläche", en: "area" },
  "ctl.areaTint": { de: "Fläche einfärben (bei Flächen-Linsen)", en: "Tint the area (area lenses)" },
  "ctl.close": { de: "Schliessen", en: "Close" },
  "ctl.sheetSize": { de: "Blatt grösser oder kleiner (ziehen: nach unten schliesst)", en: "Sheet taller or shorter (drag down to close)" },
  "ctl.walkTo": { de: "Ziel", en: "Destination" },
  "ctl.legendHide": { de: "Legende einklappen", en: "Collapse the legend" },
  "ctl.legendShow": { de: "Legende ausklappen", en: "Expand the legend" },
  "ctl.mapMenu": { de: "Karte", en: "Map" },
  "ctl.mapMenuAria": { de: "Orte, Grundkarte und Ansicht", en: "Places, base map and view" },
  "ctl.placesAny": { de: "beliebig viele, als Symbole", en: "any number, as symbols" },
  "ctl.baseQuiet": { de: "ruhig, nie nach Daten gefärbt", en: "quiet, never coloured by data" },
  "ctl.fromZoom": { de: "ab Zoom", en: "from zoom" },
  "ctl.buildings": { de: "Gebäude", en: "Buildings" },
  "ctl.show": { de: "anzeigen", en: "show" },
  "ctl.profile": { de: "Suchprofil", en: "Search profile" },
  "ctl.profileOpen": { de: "Suchprofil öffnen", en: "Open the search profile" },
  "ctl.profileClose": { de: "Suchprofil schliessen", en: "Close the search profile" },
  "ctl.profileEmpty": { de: "Noch keine Kriterien. „+ Kriterium“ oder ein Klick auf eine Farbe der Legende fügt eines hinzu; Gebäude, die nicht passen, werden blass.", en: "No criteria yet. “+ Criterion” or a click on a colour in the legend adds one; buildings that don't match fade out." },
  "ctl.others": { de: "Andere Gebäude", en: "Other buildings" },
  "ctl.fade": { de: "abschwächen", en: "fade" },
  "ctl.hide": { de: "ausblenden", en: "hide" },
  "ctl.remove": { de: "entfernen", en: "remove" },
  "ctl.marked": { de: "markiert", en: "marked" },
  "ctl.mustMatch": { de: "muss passen", en: "must match" },
  "ctl.markOnly": { de: "nur markieren (Umriss)", en: "mark only (outline)" },
  // what a city has (web/city.js coverage)
  "cov.noData": { de: "keine Daten", en: "no data", sr: "nema podataka" },
  "cov.noneHere": { de: "Für {city} gibt es dafür keine offene Quelle", en: "No open source for this in {city}", sr: "Za {city} nema otvorenog izvora za ovo" },
  "cov.legendNone": { de: "Für {city} gibt es dafür keine offene Quelle: alle Gebäude erscheinen ohne Angabe.", en: "No open source for this in {city}: every building shows without a value.", sr: "Za {city} nema otvorenog izvora: sve zgrade su bez podatka." },
  "cov.partial": { de: "Bekannt für {share} der Gebäude ({source}); die übrigen erscheinen ohne Angabe.", en: "Known for {share} of the buildings ({source}); the rest show without a value.", sr: "Poznato za {share} zgrada ({source}); ostale su bez podatka." },
  "cov.na": { de: "in {city} nicht verfügbar", en: "not available in {city}", sr: "nije dostupno za {city}" },
  "cov.walkNone": { de: "Fusswege: für {city} noch nicht berechnet", en: "Walks: not computed for {city} yet", sr: "Pešačenje: za {city} još nije izračunato" },

  // the address search (web/search.js)
  "srch.placeholder": { de: "Adresse, Ort oder Haltestelle", en: "Address, place or stop" },
  "srch.label": { de: "Suche: Adresse, Ort oder Haltestelle", en: "Search: address, place or stop" },
  "srch.clear": { de: "Suche leeren", en: "Clear the search" },
  "srch.building": { de: "Gebäude", en: "building" },
  "srch.none": { de: "Nichts gefunden", en: "Nothing found" },
  "srch.loading": { de: "Adressen werden geladen …", en: "Loading the addresses …" },
  "srch.failed": { de: "Die Adressen konnten nicht geladen werden; Orte und Haltestellen gehen.", en: "The addresses could not be loaded; places and stops work." },
  // the search profile's criteria (web/profile.js)
  "pf.add": { de: "Kriterium", en: "Criterion" },
  "pf.addSub": { de: "jede Linse, jeder Ort", en: "any lens, any place" },
  "pf.addHint": { de: "was ein Zuhause haben soll; die Zahl zeigt, wie viele Wohngebäude danach übrig sind", en: "what a home should have; the count shows how many residential buildings are left" },
  "pf.extras": { de: "Weiteres", en: "More" },
  "pf.left": { de: "übrig", en: "left" },
  "pf.ofMatching": { de: "der passenden", en: "of the matching" },
  "pf.of": { de: "von", en: "of" },
  "pf.homesMatch": { de: "Wohngebäuden passen", en: "residential buildings match" },
  "pf.matchShort": { de: "passen", en: "match" },
  "pf.filter": { de: "filtern", en: "filter" },
  "pf.markOnly": { de: "nur markieren", en: "mark only" },
  "pf.missing": { de: "auch ohne Wert", en: "also without a value" },
  "pf.from": { de: "von", en: "from" },
  "pf.to": { de: "bis", en: "to" },
  "pf.any": { de: "alle", en: "any" },
  "pf.none": { de: "keine", en: "none" },
  "pf.without": { de: "ohne", en: "not" },
  "pf.quote": { de: "„%s“", en: "“%s”" },
  "pf.yes": { de: "ja", en: "yes" },
  "pf.no": { de: "nein", en: "no" },
  "pf.copy": { de: "Link kopieren", en: "Copy link" },
  "pf.copied": { de: "kopiert", en: "copied" },
  "pf.noTable": { de: "Die Zählung konnte nicht geladen werden; die Karte filtert trotzdem.", en: "The counts could not be loaded; the map filters all the same." },
  "pf.legendAdd": { de: "ins Suchprofil", en: "add to the search profile" },
  "pf.legendHint": { de: "Klick auf eine Farbe: ins Suchprofil", en: "Click a colour to add it to the search profile" },
  "pf.fits": { de: "Passt zum Suchprofil", en: "Matches the search profile" },
  "pf.fitsNot": { de: "Passt nicht zum Suchprofil", en: "Doesn't match the search profile" },
  "pf.marks": { de: "Markierungen", en: "Marks" },
  "pf.pass": { de: "passt", en: "matches" },
  "pf.fail": { de: "passt nicht", en: "doesn't match" },
  "pf.marked": { de: "markiert", en: "marked" },
  "pf.notMarked": { de: "nicht markiert", en: "not marked" },
  "sb.view": { de: "Ansicht", en: "View" },
  "sb.reset": { de: "zurücksetzen", en: "reset" },
  "sb.housingOnly": { de: "Nur Wohngebäude", en: "Housing only" },
  "sb.yearFrom": { de: "Baujahr von", en: "Built from" },
  "sb.yearTo": { de: "Baujahr bis", en: "Built until" },
  "sb.noiseMax": { de: "Strassenlärm Tag", en: "Road noise, day" },
  "sb.walkMax": { de: "Zu Fuss", en: "On foot" },
  "sb.walkTo": { de: "Zu Fuss zu", en: "Walk to" },
  "sb.walkMinutes": { de: "höchstens Minuten", en: "at most minutes" },
  "sb.places": { de: "Orte", en: "Places" },
  "sb.base": { de: "Grundkarte", en: "Base map" },
  // data age (web/freshness.js, C-16)
  "fr.asOf": { de: "Datenstand", en: "Data as of" },
  "fr.months": { de: "Monate alt", en: "months old" },
  "fr.sources": { de: "Quellen", en: "Sources" },
  "fr.fetched": { de: "abgerufen am", en: "fetched on" },
  "fr.rule": { de: "orange ab 2, rot ab 4 Monaten seit dem Abruf", en: "orange from 2, red from 4 months after fetching" },
  "fr.aria": { de: "Quellen und Datenstand", en: "Sources and data age" },
  "hc.near": { de: "In der Nähe, zu Fuss", en: "Nearby, on foot" },
  "hc.nearNone": { de: "über 6 km", en: "over 6 km" },
  "hc.nearNoName": { de: "Name nicht verfügbar", en: "name not available" },
  "hc.nearHint": { de: "Fussweg über Strassen und Wege, ≈ 80 m/min; anklicken öffnet den Ort", en: "walk along roads and paths, ≈ 80 m/min; click to open the place" },
  "hc.stopGist": { de: "Zum HB morgens", en: "To HB, mornings" },
  "sb.any": { de: "alle", en: "any" },
  "sb.marks": { de: "Markieren", en: "Mark" },

  // building hover card (web/map.js)
  "hc.building": { de: "Gebäude", en: "Building" },
  "hc.built": { de: "Baujahr", en: "Built" },
  "hc.unknown": { de: "unbekannt", en: "unknown" },
  "hc.use": { de: "Nutzung", en: "Use" },
  "hc.flat": { de: "Wohnung", en: "flat" },
  "hc.flats": { de: "Wohnungen", en: "flats" },
  "hc.floor": { de: "Geschoss", en: "floor" },
  "hc.floors": { de: "Geschosse", en: "floors" },
  "hc.heating": { de: "Heizung", en: "Heating" },
  "hc.day": { de: "Tag", en: "day" },
  "hc.night": { de: "Nacht", en: "night" },
  "hc.roadNoise": { de: "Strassenlärm", en: "Road noise" },
  "hc.railNoise": { de: "Bahnlärm", en: "Rail noise" },
  "hc.solar": { de: "Solar (Dach)", en: "Solar (roof)" },
  // GWR gschutzr = civil-defence shelter, gazzi = separate rooms
  "hc.shelter": { de: "Zivilschutzraum", en: "Civil-defence shelter" },
  "hc.rooms": { de: "Separate Wohnräume", en: "Separate rooms" },
  "hc.type": { de: "Gebäudeart", en: "Building type" },
  "hc.dwellings": { de: "Wohnungen", en: "Flats" },
  "hc.floorCount": { de: "Geschosse", en: "Floors" },
  "hc.area": { de: "Grundfläche", en: "Footprint" },
  "hc.volume": { de: "Volumen", en: "Volume" },
  "hc.elevation": { de: "Höhe", en: "Elevation" },
  "hc.asl": { de: "m ü. M.", en: "m a.s.l." },
  "hc.heating2": { de: "Zusatzheizung", en: "Second heating" },
  "hc.solarYield": { de: "Solarstrom", en: "Solar power" },
  "hc.year": { de: "Jahr", en: "year" },
  "hc.plotNr": { de: "Nummer", en: "Number" },
  "hc.overLimit": { de: "über Grenzwert", en: "above limit" },
  "hc.limit": { de: "Grenzwert", en: "limit" },
  "hc.limitNote": {
    de: "Strich: Immissionsgrenzwert der Lärmschutz-Verordnung für die Empfindlichkeitsstufe",
    en: "Tick: exposure limit of the Noise Abatement Ordinance for the sensitivity level",
  },
  "hc.sec.energy": { de: "Energie", en: "Energy" },
  "hc.sec.noise": { de: "Lärm", en: "Noise" },
  "hc.sec.location": { de: "Lage", en: "Location" },
  "hc.sec.risks": { de: "Risiken", en: "Risks" },
  "hc.sec.plot": { de: "Grundstück", en: "Plot" },
  "hc.pinHint": { de: "Klicken zum Anheften", en: "Click to pin" },
  "hc.close": { de: "Schliessen", en: "Close" },
  // stop card (web/stops.js)
  // place cards (web/places.js)
  "pc.address": { de: "Adresse", en: "Address" },
  "pc.website": { de: "Website", en: "Website" },
  "pc.sources": { de: "Quellen", en: "Sources" },
  "pc.unknown": { de: "unbekannt", en: "unknown" },
  "pc.noName": { de: "ohne Namen", en: "no name" },
  "pc.straight": { de: "Luftlinie", en: "straight line" },
  "sc.loading": { de: "Fahrplan wird geladen …", en: "Loading the timetable …" },
  "sc.noData": { de: "Für diese Haltestelle gibt es an diesem Tag keine Verbindungen.", en: "No connections from this stop on that day." },
  "sc.atHb": { de: "Hier ist der Zürich HB.", en: "This is Zürich HB." },
  "sc.timetable": { de: "Fahrplan", en: "timetable" },
  "sc.fastest": { de: "schnellste", en: "fastest" },
  "sc.average": { de: "Ø zum HB", en: "avg. to HB" },
  "sc.slowest": { de: "längste", en: "slowest" },
  "sc.cycle": { de: "Takt", en: "cycle" },
  "sc.wait": { de: "Ø Wartezeit", en: "avg. wait" },
  "sc.waitHint": { de: "Mittlere Wartezeit an der Haltestelle, wenn man zu einer zufälligen Zeit in dieser Stunde kommt: bis 3′ grün, bis 6′ gelb, bis 10′ orange, darüber rot", en: "Mean wait at the stop when arriving at a random time in this hour: up to 3′ green, to 6′ yellow, to 10′ orange, longer red" },
  "sc.day": { de: "Weg zum HB über den Tag", en: "To HB through the day" },
  "sc.dayHint": { de: "Warten + Fahrt, Minuten", en: "wait + ride, minutes" },
  "sc.dayAria": { de: "Reisezeit zum HB über den Tag", en: "Travel time to HB through the day" },
  "sc.clock": { de: "Die Stunde als Uhr", en: "The hour as a clock" },
  "sc.clockAria": { de: "Abfahrten als Uhr,", en: "Departures as a clock," },
  "sc.minCycle": { de: "Min.-Takt", en: "min cycle" },
  "sc.noCycle": { de: "kein fester Takt", en: "no fixed cycle" },
  "sc.irregular": { de: "unregelmässig", en: "irregular" },
  "sc.none": { de: "kein Angebot", en: "no service" },
  "sc.journeys": { de: "Verbindungen", en: "Connections" },
  "sc.noDeps": { de: "In dieser Stunde fährt hier nichts ab.", en: "No departures in this hour." },
  "sc.prevHour": { de: "eine Stunde früher", en: "one hour earlier" },
  "sc.nextHour": { de: "eine Stunde später", en: "one hour later" },
  "sc.pickHint": { de: "Kurve, Tageszeit oder ‹ › anklicken", en: "click the curve, a part of the day or ‹ ›" },
  "sc.pinToPick": { de: "Klicken zum Anheften und eine Stunde wählen", en: "Click to pin and pick an hour" },
  "sc.change": { de: "umsteigen", en: "change" },
  "sc.walk": { de: "zu Fuss", en: "walk" },
  "sc.walkModel": { de: "Fusswege: Umsteigezeit des Fahrplans, sonst geschätzt (Luftlinie × 1,3 bei 80 m/min)", en: "walks: the timetable's transfer time, else estimated (straight line × 1.3 at 80 m/min)" },
  "sc.perDay": { de: "Abfahrten am Tag", en: "departures a day" },
  "sc.part.early": { de: "früh", en: "early" },
  "sc.part.morning": { de: "Morgen", en: "morning" },
  "sc.part.day": { de: "Tag", en: "day" },
  "sc.part.evening": { de: "Abend", en: "evening" },
  "sc.part.night": { de: "Nacht", en: "night" },
  "sc.feedStation": { de: "Fahrplan der Haltestelle", en: "timetable of stop" },
  "sc.source": { de: "Fahrplan: opentransportdata.swiss via geOps (GTFS)", en: "Timetable: opentransportdata.swiss via geOps (GTFS)" },
  // no value on a building (every block shows, saying why)
  "hc.na": { de: "keine Angabe", en: "no data" },
  "hc.none": { de: "keine", en: "none" },
  "hc.noShelter": { de: "kein Zivilschutzraum", en: "no civil-defence shelter" },
  "hc.noRail": { de: "kein Bahnlärm modelliert", en: "no rail noise modelled" },
  "hc.below58": { de: "unter 58 dB", en: "below 58 dB" },
  "hc.noEs": { de: "keine Stufe festgelegt", en: "no level set" },
  "hc.noStopNear": { de: "keine Haltestelle in 1,5 km Fussweg", en: "no stop within 1.5 km on foot" },
  "hc.oev": { de: "ÖV-Güteklasse", en: "Transit quality" },
  "hc.noOev": { de: "keine (unter D)", en: "none (below D)" },
  "hc.stop": { de: "Nächste Haltestelle", en: "Nearest stop" },
  "hc.hbStop": { de: "Haltestelle zum HB", en: "Stop for Zürich HB" },
  "hc.notAssessed": { de: "nicht beurteilt", en: "not assessed" },
  "hc.noRunoff": { de: "nicht kartiert", en: "none mapped" },
  "hc.notRegistered": { de: "nicht im Kataster", en: "not in the register" },
  "hc.plot": { de: "Grundstück", en: "Plot" },
  "hc.commute": { de: "Zum HB", en: "To Zürich HB" },
  "hc.zone": { de: "Zone", en: "Zone" },
  "hc.es": { de: "Empfindlichkeit", en: "Sensitivity" },
  "hc.hazard": { de: "Naturgefahr", en: "Natural hazard" },
  "hc.runoff": { de: "Oberflächenabfluss", en: "Surface runoff" },
  "hc.aircraft": { de: "Fluglärm", en: "Aircraft noise" },
  "hc.contaminated": { de: "Belasteter Standort", en: "Contaminated site" },
  "hc.oereb": { de: "ÖREB-Auszug des Grundstücks (PDF) ↗", en: "Plot's public-law restrictions (ÖREB, PDF) ↗" },
  "hc.commuteFrom": { de: "ab", en: "from" },
  "hc.heatedArea": { de: "Energiebezugsfläche", en: "heated floor area" },
  "hc.builtUnknown": { de: "bebaut: unbekannt (nicht alle Umrisse vermessen)", en: "built: unknown (not every outline surveyed)" },
  "hc.commuteModel": { de: "Zum HB geschätzt: Fussweg zur besten Haltestelle (≈ 80 m/min) + ihre mittlere Reisezeit zum HB inkl. Warten, werktags 6:30–9 Uhr", en: "to HB estimated: walk to the best stop (≈ 80 m/min) + its mean trip to HB including the wait, weekdays 6:30–9:00" },
  "hc.plotBuilt": { de: "bebaut", en: "built" },
  "hc.yes": { de: "ja", en: "yes" },
  "hc.place": { de: "Gemeinde / PLZ", en: "Municipality / postcode" },
  "hc.footprint": { de: "Grundriss", en: "Footprint" },
  "hc.underground": { de: "unterirdisch", en: "underground" },

};

const LANG_KEY = `bg-lang-${(typeof CITY !== "undefined" && CITY.id) || ""}`;
let LANG = (() => {
  const ok = l => LANGS.some(x => x.id === l);
  const fromUrl = new URLSearchParams(location.search).get("lang");
  if (ok(fromUrl)) return fromUrl;
  try { const saved = localStorage.getItem(LANG_KEY); if (ok(saved)) return saved; } catch (e) { /* storage blocked */ }
  return DEFAULT_LANG;
})();

function addStrings(more) { Object.assign(STRINGS, more); }
// the city's own sense of a few labels (cities/<id>/city.js `strings`)
if (typeof CITY !== "undefined" && CITY.strings) addStrings(CITY.strings);
// number and date format of the current language
const locale = () => ({ de: "de-CH", en: "en-GB", sr: "sr-Latn-RS" })[LANG] || "en-GB";

// A { de, en } label in the current language (plain strings pass through).
// Serbian: the label's own `sr`, else its English looked up in SR_TEXT
// (web/i18n_sr.js), else the English.
function tr(v) {
  if (LANG === "sr") {
    const sr = typeof SR_TEXT !== "undefined" ? SR_TEXT : {};
    if (v && typeof v === "object") return v.sr ?? sr[v.en] ?? v.en ?? v.de;
    return typeof v === "string" ? sr[v] ?? v : v;
  }
  if (v && typeof v === "object") return v[LANG] ?? v.en ?? v.de;
  return v;
}

function t(key) {
  const s = STRINGS[key];
  return s ? tr(s) : key;
}

function applyI18n(root) {
  root = root || document;
  root.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-aria]").forEach(el => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
  root.querySelectorAll("[data-i18n-title]").forEach(el => el.setAttribute("title", t(el.dataset.i18nTitle)));
  document.documentElement.lang = LANG;
  root.querySelectorAll("select.bg-lang").forEach(sel => { sel.value = LANG; });
}

function setLang(lang) {
  if (lang === LANG || !LANGS.some(x => x.id === lang)) return;
  LANG = lang;
  try { localStorage.setItem(LANG_KEY, lang); } catch (e) { /* storage blocked */ }
  const url = new URL(location.href);
  if (lang === DEFAULT_LANG) url.searchParams.delete("lang"); else url.searchParams.set("lang", lang);
  history.replaceState(null, "", url);
  applyI18n();
  window.dispatchEvent(new CustomEvent("bg:lang", { detail: lang }));
}

// The language dropdown: a small pill-shaped native <select>.
function langSelect() {
  const sel = document.createElement("select");
  sel.className = "bg-lang";
  sel.setAttribute("data-i18n-aria", "lang.label");
  sel.setAttribute("aria-label", t("lang.label"));
  // phones: "DE" / "EN", so the brand card has room for the search
  const short = window.matchMedia && window.matchMedia("(max-width: 699px)").matches;
  sel.innerHTML = LANGS.map(l => `<option value="${l.id}">${short ? l.id.toUpperCase() : l.label}</option>`).join("");
  sel.value = LANG;
  sel.addEventListener("change", () => setLang(sel.value));
  return sel;
}

(function injectLangCss() {
  const style = document.createElement("style");
  style.textContent = `
    select.bg-lang {
      appearance: none; -webkit-appearance: none;
      padding: 4px 24px 4px 11px; border-radius: 999px; cursor: pointer;
      border: 1px solid var(--bg-rule, #e8dfd3); color: var(--bg-ink, #4a4039);
      font: 600 12px var(--bg-font, system-ui, sans-serif);
      background: var(--bg-card-solid, #fffaf4) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%236b5d53' stroke-width='1.5'/%3E%3C/svg%3E") no-repeat right 9px center;
      transition: background-color var(--bg-slow, .45s) var(--bg-ease, ease);
    }
    select.bg-lang:hover { background-color: #f6efe6; }
    select.bg-lang:focus-visible { outline: 2px solid var(--bg-accent, #6b5d53); outline-offset: 2px; }
  `;
  document.head.appendChild(style);
})();

document.addEventListener("DOMContentLoaded", () => applyI18n());
