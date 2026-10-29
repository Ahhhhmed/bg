/**
 * Place cards (backlogs 006 / 032 / 035 / 007): hover a place icon (school,
 * hospital, practice, shop, bath, playground) for its card, click to pin it
 * (with its links); a bottom sheet on phones. Stops have their own card
 * (web/stops.js).
 *
 * One design for every category, like the building card in small:
 *   - the icon, the name, kind · qualifier · municipality
 *   - figures: big numbers in tiles tinted with the category's accent
 *     (size, students, pools, open until, ...)
 *   - chips: the category's key facts with a dot in their colour (school
 *     stage, play equipment, bath features, chain, ...)
 *   - rows: the category's details, then the address (no nearest stop:
 *     owner, 2026-10-23, these are places one walks or cycles to)
 *   - pinned: website and phone; the sources linked in the foot
 * The data is what cities/zurich/pipeline/swiss/build_places.py puts on each point, only
 * what a source states (C-05): a key fact no source states is a dashed
 * "unbekannt" chip / tile, and the foot lists the point's sources with their
 * data dates (/data/places_sources.json).
 *
 * A place icon over a building wins: the building card doesn't open while
 * the pointer is on an icon (placeAt(), used by map.js), so the pin's card
 * isn't hidden by the building's.
 * Loaded after map.js (uses its popup, pinnedCard, placeCard, openSheet, ...).
 */

const pcYes = v => v === 1 || v === true || v === "yes";
// OSM healthcare:speciality codes on the practices
const SPECIALITIES = {
  intensive: { de: "Intensivmedizin", en: "intensive care" }, psychiatry: { de: "Psychiatrie", en: "psychiatry" },
  orthopaedics: { de: "Orthopädie", en: "orthopaedics" }, paediatrics: { de: "Kinder- und Jugendmedizin", en: "paediatrics" },
  paediatric_surgery: { de: "Kinderchirurgie", en: "paediatric surgery" }, general: { de: "Allgemeinmedizin", en: "general medicine" },
  psychotherapy: { de: "Psychotherapie", en: "psychotherapy" }, plastic_surgery: { de: "Plastische Chirurgie", en: "plastic surgery" },
  emergency: { de: "Notfallmedizin", en: "emergency medicine" }, cardiology: { de: "Kardiologie", en: "cardiology" },
  surgery: { de: "Chirurgie", en: "surgery" }, rheumatology: { de: "Rheumatologie", en: "rheumatology" },
};

// Colour on the cards (C-14): each category has a soft accent for its figure
// tiles; chips carry a dot in the colour of what they are (a school stage, a
// kind of play equipment, a bath feature, a chain), from the categorical
// palette of the stop card (STOP_LINE_COLORS, web/stops.js, validated for
// colour-blind separation). Text stays cocoa (the chip is a tint, C-07 spirit).
const [C_BLUE, C_ORANGE, C_TEAL, C_MUSTARD, C_MAGENTA, C_GREEN, C_VIOLET, C_RED] = STOP_LINE_COLORS;
const PLACE_ACCENT = { schools: C_BLUE, hospitals: C_RED, health: C_RED, shops: C_GREEN, baths: C_TEAL, playgrounds: C_ORANGE, air: C_VIOLET };
const STAGES = {
  kita: [C_MAGENTA, { de: "Kita", en: "Day care" }], kg: [C_MUSTARD, { de: "Kindergarten", en: "Kindergarten" }],
  prim: [C_GREEN, { de: "Primarschule", en: "Primary school" }], sek: [C_BLUE, { de: "Sekundarschule", en: "Lower secondary" }],
  vs: [C_TEAL, { de: "Volksschule", en: "Compulsory school" }], special: [C_ORANGE, { de: "Sonderschule", en: "Special school" }],
  mittel: [C_VIOLET, { de: "Mittelschule", en: "Upper secondary" }], beruf: [C_RED, { de: "Berufsfachschule", en: "Vocational school" }],
};
// play equipment (OSM `playground=*`), grouped by what children do on it
const GEAR = {
  swing: [C_BLUE, { de: "Schaukel", en: "swing" }], basketswing: [C_BLUE, { de: "Nestschaukel", en: "basket swing" }],
  slide: [C_ORANGE, { de: "Rutschbahn", en: "slide" }], zipwire: [C_ORANGE, { de: "Seilbahn", en: "zip line" }],
  climbingframe: [C_GREEN, { de: "Klettergerüst", en: "climbing frame" }], structure: [C_GREEN, { de: "Spielturm", en: "play tower" }],
  climbingwall: [C_GREEN, { de: "Kletterwand", en: "climbing wall" }], rope_traverse: [C_GREEN, { de: "Seilparcours", en: "rope course" }],
  balancebeam: [C_GREEN, { de: "Balancierbalken", en: "balance beam" }], wobble_bridge: [C_GREEN, { de: "Wackelbrücke", en: "wobble bridge" }],
  horizontal_bar: [C_GREEN, { de: "Reck", en: "bar" }], ladder: [C_GREEN, { de: "Leiter", en: "ladder" }],
  stepping_stone: [C_GREEN, { de: "Trittsteine", en: "stepping stones" }], tunnel_tube: [C_GREEN, { de: "Kriechröhre", en: "tunnel" }],
  sandpit: [C_MUSTARD, { de: "Sandkasten", en: "sandpit" }], water: [C_TEAL, { de: "Wasserspiel", en: "water play" }],
  springy: [C_MAGENTA, { de: "Federwippe", en: "spring rider" }], seesaw: [C_MAGENTA, { de: "Wippe", en: "seesaw" }],
  roundabout: [C_VIOLET, { de: "Karussell", en: "roundabout" }], spinner: [C_VIOLET, { de: "Drehscheibe", en: "spinner" }],
  trampoline: [C_RED, { de: "Trampolin", en: "trampoline" }], playhouse: [C_MUSTARD, { de: "Spielhaus", en: "playhouse" }],
  hammock: [C_TEAL, { de: "Hängematte", en: "hammock" }], activitypanel: [C_MUSTARD, { de: "Spieltafel", en: "activity panel" }],
  platform: [C_GREEN, { de: "Plattform", en: "platform" }],
};
const BATH_FEATURES = {
  slide: [C_ORANGE, { de: "Rutschbahn", en: "water slide" }], diving: [C_BLUE, { de: "Sprungturm", en: "diving" }],
  volleyball: [C_MUSTARD, { de: "Beachvolleyball", en: "beach volleyball" }], playground: [C_GREEN, { de: "Spielplatz", en: "playground" }],
  sauna: [C_RED, { de: "Sauna", en: "sauna" }], food: [C_MAGENTA, { de: "Kiosk / Restaurant", en: "kiosk / restaurant" }],
};
// supermarket chains in their own colours (a dot, not the text)
const CHAIN_COLORS = { coop: "#e3501b", migros: "#f07d00", denner: "#c8102e", aldi: "#00498f", lidl: "#0050aa",
                       spar: "#00843d", volg: "#e30613", voi: "#f39200", landi: "#2e7d32", alnatura: "#7a9a01" };

const pcArea = m => m >= 5000 ? `${(m / 10000).toLocaleString(locale(), { maximumFractionDigits: 1 })} ha` : `${fmtNum(m)} m²`;
const pcChip = (color, label) => ({ color, label });
const pcFig = (value, label) => ({ value, label });

// Every fact on a card is one a source states (C-05); a key fact no source
// states shows as "unbekannt", never as a guess. The sources of a card's
// facts, with their data dates, come from data/places_sources.json.
let PLACE_SOURCES = null;   // null until it arrives: the card then leaves its sources out and redraws (lateData)
fetch("../data/places_sources.json").then(r => (r.ok ? r.json() : {})).catch(() => ({}))
  .then(d => { PLACE_SOURCES = d || {}; lateData(); });

const SPEC_LABELS = { ...SPECIALITIES,
  internal: { de: "Innere Medizin", en: "internal medicine" }, family_medicine: { de: "Hausarztmedizin", en: "family medicine" },
  general_practice: { de: "Allgemeinmedizin", en: "general practice" } };
const specLabel = s => SPEC_LABELS[s] || s.replace(/_/g, " ");

function schoolStages(p) {
  if (p.kind === "kita") return ["kita"];
  if (p.kind === "kindergarten") return ["kg"];
  if (p.kind === "upper") return /beruf/i.test(p.info || "") ? ["beruf"] : /mittel/i.test(p.info || "") ? ["mittel"] : [];
  if (p.info === "Sonderschule") return ["special"];
  const st = p.stage ? String(p.stage).split(",") : [];
  return st.length ? st : p.info === "Volksschule" ? ["vs"] : [];
}
function gearList(p) {
  return String(p.gear || "").split(",").filter(Boolean).map(x => { const [k, n] = x.split(":"); return [k, Number(n) || 1]; })
    .filter(([k]) => GEAR[k]).sort((a, b) => b[1] - a[1]);
}
const UNKNOWN = { de: "unbekannt", en: "unknown" };
// the canton's hospital lists a hospital is on (Zürcher Spitalliste 2023)
const HOSPITAL_LISTS = {
  acute: [C_RED, { de: "Akutspital", en: "Acute care" }], psych: [C_VIOLET, { de: "Psychiatrie", en: "Psychiatry" }],
  rehab: [C_GREEN, { de: "Rehabilitation", en: "Rehabilitation" }],
};
const unknownChip = label => ({ unknown: true, label });
const pub = p => p.public === 1 ? pcChip(C_TEAL, { de: "Öffentlich", en: "Public" })
  : p.public === 0 ? pcChip(C_MAGENTA, { de: "Privat", en: "Private" }) : unknownChip({ de: "Öffentlich / privat", en: "Public / private" });
const wheel = p => pcYes(p.wheelchair) ? pcChip(C_TEAL, { de: "Rollstuhlgängig", en: "Wheelchair accessible" })
  : p.wheelchair === "limited" ? pcChip(C_MUSTARD, { de: "Teilweise rollstuhlgängig", en: "Partly wheelchair accessible" })
  : p.wheelchair === "no" ? pcChip(null, { de: "Nicht rollstuhlgängig", en: "Not wheelchair accessible" })
  : unknownChip({ de: "Rollstuhlgängigkeit", en: "Wheelchair access" });
const hoursRow = { prop: "hours", label: { de: "Öffnungszeiten", en: "Opening hours" }, key: true };

// per category: figures (big tiles in the accent), chips (dots; a key fact
// without a source value is a dashed "… unbekannt" chip), rows (`key: true`
// rows show "unbekannt" when empty)
const PLACE_CARDS = {
  schools: {
    figures: [
      p => p.kind === "upper" || p.kind === "school" ? pcFig(p.students ? fmtNum(p.students) : UNKNOWN, { de: "Schüler:innen", en: "students" }) : null,
      p => p.kind === "upper" || p.kind === "school" ? pcFig(p.area_m2 ? pcArea(p.area_m2) : UNKNOWN, { de: "Areal", en: "grounds" }) : null,
    ],
    chips: [
      p => { const st = schoolStages(p); return st.length ? st.map(s => pcChip(...STAGES[s])) : unknownChip({ de: "Schulstufe", en: "School stage" }); },
      pub,
      p => p.kind !== "kita" ? null : p.subsidised === 1 ? pcChip(C_GREEN, { de: "Subventionierte Plätze", en: "Subsidised places" })
        : unknownChip({ de: "Subventionierte Plätze", en: "Subsidised places" }),
      p => p.site ? pcChip(null, p.site) : null,
      p => p.ages ? pcChip(null, { de: `${p.ages} Jahre`, en: `ages ${p.ages}` }) : null,
      p => p.grades ? pcChip(null, { de: `Klassen ${p.grades}`, en: `Grades ${p.grades}` }) : null,
    ],
    rows: [
      { prop: "district", label: { de: "Schulkreis", en: "School district" } },
      { prop: "unit", label: { de: "Schuleinheit", en: "School unit" } },
      { prop: "op", label: { de: "Träger", en: "Run by" } },
    ] },
  hospitals: {
    // the canton's hospital lists (C-05): emergency station = the general basic
    // package (BP) of the acute list, which requires one
    figures: [
      p => pcFig(p.er_mandate === 1 ? { de: "ja", en: "yes" } : p.er_mandate === 0 ? { de: "nicht im Auftrag", en: "not in mandate" }
        : { de: "kein Akutspital", en: "not acute care" }, { de: "Notfallstation", en: "Emergency station" }),
      p => p.groups != null ? pcFig(String(p.groups), { de: "Leistungsgruppen", en: "service groups" }) : null,
      p => p.area_m2 ? pcFig(pcArea(p.area_m2), { de: "Areal", en: "site" }) : null,
      p => p.beds ? pcFig(fmtNum(p.beds), { de: "Betten (OSM)", en: "beds (OSM)" }) : null,
    ],
    chips: [
      p => String(p.lists || "").split(",").filter(l => HOSPITAL_LISTS[l]).map(l => pcChip(...HOSPITAL_LISTS[l])),
    ],
    rows: [
      { prop: "op", label: { de: "Träger", en: "Run by" }, key: true },
      { prop: "areas", label: { de: "Leistungsbereiche", en: "Service areas" }, fmt: v => String(v).split(";").join(", ") },
    ] },
  health: {
    figures: [],
    chips: [
      p => p.kind !== "doctor" ? null : (() => { const sp = String(p.spec || "").split(",").filter(Boolean);
             return sp.length ? sp.map(s => pcChip(C_MAGENTA, specLabel(s))) : unknownChip({ de: "Fachgebiet", en: "Speciality" }); })(),
      wheel,
    ],
    rows: [{ prop: "op", label: { de: "Praxis / Betreiber", en: "Practice / operator" } },
           { prop: "brand", label: { de: "Kette", en: "Chain" } }] },
  shops: {
    figures: [
      p => pcFig(p.close_max || UNKNOWN, { de: "spätestens offen bis", en: "latest closing" }),
      p => pcFig(p.sunday === 1 ? { de: "offen", en: "open" } : p.sunday === 0 ? { de: "zu", en: "closed" } : UNKNOWN, { de: "Sonntag", en: "Sunday" }),
      p => p.kind === "supermarket" ? pcFig(p.area_m2 ? pcArea(p.area_m2) : UNKNOWN, { de: "Ladenfläche", en: "floor area" }) : null,
    ],
    chips: [
      p => { const c = String(p.brand || "").split(/\s/)[0].toLowerCase();
             return p.brand ? pcChip(CHAIN_COLORS[c] || null, p.brand) : p.kind === "supermarket" ? unknownChip({ de: "Kette", en: "Chain" }) : null; },
      p => p.kind === "post" ? (p.post_type ? pcChip(C_MUSTARD, { de: `Typ: ${p.post_type}`, en: `type: ${p.post_type}` }) : unknownChip({ de: "Filiale oder Agentur", en: "Branch or agency" })) : null,
      p => /^(yes|only)$/.test(p.organic || "") ? pcChip(C_GREEN, { de: p.organic === "only" ? "Nur Bio" : "Bio", en: p.organic === "only" ? "Organic only" : "Organic" }) : null,
      p => p.cash === 1 ? pcChip(C_BLUE, { de: "Bargeldbezug", en: "Cash withdrawal" }) : null,
    ],
    rows: [hoursRow] },
  baths: {
    figures: [
      p => pcFig(p.area_m2 ? pcArea(p.area_m2) : UNKNOWN, { de: "Anlage", en: "site" }),
      p => pcFig(p.area_m2 ? String(p.pools || 0) : UNKNOWN, { de: "Becken", en: "pools" }),
    ],
    chips: [
      p => p.kind === "pool" ? (p.info ? pcChip(C_TEAL, p.info) : unknownChip({ de: "Hallen- oder Freibad", en: "Indoor or outdoor" })) : null,
      p => p.water ? pcChip(C_TEAL, p.water) : null,
      p => p.area_m2 ? String(p.has || "").split(",").filter(k => BATH_FEATURES[k]).map(k => pcChip(...BATH_FEATURES[k]))
        : unknownChip({ de: "Ausstattung", en: "Facilities" }),
    ],
    rows: [{ prop: "op", label: { de: "Betrieb", en: "Run by" } }] },
  // Belgrade: SEPA's monitoring stations (build_air.py). The figures are the
  // last 30 days' means of preliminary hourly values; a station SEPA has
  // verified also shows its 2024 annual means. No verdict against a limit:
  // a 30-day mean isn't an annual mean, and SEPA doesn't grade them either.
  air: {
    figures: [
      p => pcFig(p.pm25_30d != null ? `${fmtNum(p.pm25_30d, 1)}` : UNKNOWN, { de: "PM2.5 µg/m³", en: "PM2.5 µg/m³", sr: "PM2.5 µg/m³" }),
      p => pcFig(p.pm10_30d != null ? `${fmtNum(p.pm10_30d, 1)}` : UNKNOWN, { de: "PM10 µg/m³", en: "PM10 µg/m³", sr: "PM10 µg/m³" }),
      p => pcFig(p.no2_30d != null ? `${fmtNum(p.no2_30d, 1)}` : UNKNOWN, { de: "NO₂ µg/m³", en: "NO₂ µg/m³", sr: "NO₂ µg/m³" }),
      p => p.o3_30d != null ? pcFig(`${fmtNum(p.o3_30d, 1)}`, { de: "O₃ µg/m³", en: "O₃ µg/m³", sr: "O₃ µg/m³" }) : null,
    ],
    chips: [
      p => pcChip(C_MUSTARD, { de: `Ø 30 Tage bis ${fmtDate(p.to)}, vorläufig`, en: `30-day mean to ${fmtDate(p.to)}, preliminary`,
                               sr: `Ø 30 dana do ${fmtDate(p.to)}, neverifikovano` }),
      p => p.pm10_2024 != null || p.pm25_2024 != null || p.no2_2024 != null
        ? pcChip(C_GREEN, { de: "verifiziert 2024", en: "verified 2024", sr: "verifikovano 2024" })
        : unknownChip({ de: "Jahresmittel 2024", en: "2024 annual mean", sr: "Godišnji prosek 2024" }),
    ],
    rows: [
      { prop: "pm25_2024", label: { de: "Jahresmittel 2024", en: "Annual mean 2024", sr: "Godišnji prosek 2024" },
        fmt: (v, p) => [["PM2.5", p.pm25_2024], ["PM10", p.pm10_2024], ["NO₂", p.no2_2024]]
          .filter(([, x]) => x != null).map(([k, x]) => `${k} ${fmtNum(x, 1)}`).join(" · ") + " µg/m³" },
      { prop: "net", label: { de: "Messnetz", en: "Network", sr: "Merna mreža" }, key: true },
      { prop: "code", label: { de: "Stationscode", en: "Station code", sr: "Kod stanice" } },
      { prop: "pm25_30d", label: { de: "Zum Vergleich", en: "For reference", sr: "Za poređenje" }, key: true,
        fmt: () => tr({ de: "EU-Jahresgrenzwerte: PM2.5 25, PM10 40, NO₂ 40 µg/m³; WHO-Richtwerte 2021: 5, 15, 10",
                        en: "EU annual limits: PM2.5 25, PM10 40, NO₂ 40 µg/m³; WHO guidelines 2021: 5, 15, 10",
                        sr: "EU godišnje granične vrednosti: PM2.5 25, PM10 40, NO₂ 40 µg/m³; SZO smernice 2021: 5, 15, 10" }) },
    ] },
  playgrounds: {
    figures: [
      p => pcFig(p.area_m2 ? pcArea(p.area_m2) : UNKNOWN, { de: "Fläche", en: "size" }),
      p => { const n = gearList(p).reduce((a, [, c]) => a + c, 0);
             return pcFig(n ? String(n) : UNKNOWN, { de: "Spielgeräte (OSM)", en: "play items (OSM)" }); },
      p => pcFig(p.ages ? String(p.ages).replace(/\s*Jahre?n?$/i, "") : UNKNOWN, { de: "Jahre", en: "years" }),
    ],
    chips: [
      p => gearList(p).map(([k, n]) => pcChip(GEAR[k][0], n > 1 ? `${n}× ${tr(GEAR[k][1])}` : GEAR[k][1])),
      p => p.setting && p.setting !== "Spielplatz" ? pcChip(null, p.setting) : null,
    ],
    rows: [
      { prop: "equip", label: { de: "Spielgeräte (Stadt)", en: "Play equipment (city)" } },
      { prop: "park", label: { de: "Im Park", en: "In the park" }, fmt: (v, p) => p.park_m2 ? `${v} (${pcArea(p.park_m2)})` : v },
      { prop: "elements", label: { de: "Anlage", en: "Grounds" } },
      { prop: "special", label: { de: "Besonderes", en: "Notes" } },
      { prop: "surface", label: { de: "Belag", en: "Surface" } },
    ] },
};

const shortMuni = m => String(m || "").replace(/\s*\(ZH\)$/, "");
const fmtDate = d => d ? new Date(d).toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" }) : t("pc.unknown");

function placeCardHtml(pl, p, pinned) {
  const cfg = PLACE_CARDS[pl.id] || { figures: [], chips: [], rows: [] };
  const accent = PLACE_ACCENT[pl.id] || "#8a7b70";
  const kind = pl.kinds.find(k => k.v === p.kind);
  // (the legend's "(from zoom 11)" hint doesn't belong on the card)
  const kindLabel = kind ? tr(kind.label).replace(/\s*\((ab|from) [Zz]oom \d+\)/, "") : "";
  const sub = [kindLabel, p.info, shortMuni(p.muni)].filter(Boolean).join(" · ");
  const icon = placeIconUrl(`place-${p.kind}${p.hub ? "-hub" : ""}`);
  const figures = (cfg.figures || []).map(f => f(p)).filter(Boolean).slice(0, 4);
  const chips = (cfg.chips || []).flatMap(f => [].concat(f(p) || [])).filter(Boolean).map(c => c.unknown
    ? `<span class="hc-chip hc-na">${escapeHtml(`${tr(c.label)}: ${t("pc.unknown")}`)}</span>`
    : `<span class="hc-chip${c.color ? "" : " hc-plain"}"${c.color ? ` style="--c:${c.color};--o:${c.color}"` : ""}>${escapeHtml(tr(c.label))}</span>`).join("");
  const rows = cfg.rows.filter(r => r.key || (p[r.prop] != null && p[r.prop] !== ""))
    .map(r => [tr(r.label), p[r.prop] == null || p[r.prop] === "" ? t("pc.unknown") : r.fmt ? r.fmt(p[r.prop], p) : String(p[r.prop])]);
  rows.push([t("pc.address"), p.addr || t("pc.unknown")]);
  const links = pinned ? [
    p.web ? `<a href="${escapeHtml(/^https?:/.test(p.web) ? p.web : `https://${p.web}`)}" target="_blank" rel="noopener">${t("pc.website")} ↗</a>` : "",
    p.tel ? `<a href="tel:${escapeHtml(String(p.tel).replace(/[^+\d]/g, ""))}">${escapeHtml(String(p.tel).trim())}</a>` : "",
  ].filter(Boolean) : [];
  // where every fact comes from, with the data's date (linked when pinned)
  const table = (PLACE_SOURCES || {})[pl.id] || {};
  const srcs = String(p.srcs || "").split(",").filter(Boolean).map(c => table[c] ? (pinned
    ? `<a href="${escapeHtml(table[c].url)}" target="_blank" rel="noopener">${escapeHtml(tr(table[c]))}</a> (${table[c].date ? freshDateHtml(table[c].date) : escapeHtml(t("pc.unknown"))})`
    : `${escapeHtml(tr(table[c]))} (${table[c].date ? freshDateHtml(table[c].date) : escapeHtml(t("pc.unknown"))})`) : escapeHtml(c));
  const foot = [PLACE_SOURCES ? `${t("pc.sources")}: ${srcs.join(" · ")}` : "", pinned ? "" : escapeHtml(t("hc.pinHint"))]
    .filter(Boolean).join(" · ");
  return `<div class="hover-card pc-card" data-pid="${escapeHtml(p.pid || "")}" style="--accent:${accent}">
    <div class="pc-head">
      ${icon ? `<img class="pc-icon" src="${icon}" alt="">` : ""}
      <div class="pc-titles"><div class="hc-title">${escapeHtml(p.name || `${kindLabel} (${t("pc.noName")})`)}</div>
        ${sub ? `<div class="hc-place">${escapeHtml(sub)}</div>` : ""}</div>
    </div>
    ${figures.length ? `<div class="hc-figures pc-figures">${figures.map(f => {
      const unk = f.value === UNKNOWN;
      return `<div class="hc-fig ${unk ? "pc-unk" : "hc-tinted"}" style="--c:${accent};--o:${accent}"><strong>${escapeHtml(tr(f.value))}</strong><span>${escapeHtml(tr(f.label))}</span></div>`; }).join("")}</div>` : ""}
    ${chips ? `<div class="pc-chips">${chips}</div>` : ""}
    ${rows.length ? `<dl class="pc-rows">${rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd${v === t("pc.unknown") ? ' class="pc-unk-text"' : ""}>${escapeHtml(v)}</dd>`).join("")}</dl>` : ""}
    ${links.length ? `<div class="hc-links pc-links">${links.join("")}</div>` : ""}
    <div class="hc-foot pc-sources">${foot}</div>
  </div>`;
}

// the place icon under a point, if any (stops included): map.js skips the
// building card there
function placeLayerIds() {
  return PLACE_LAYERS.flatMap(pl => [`place-${pl.id}`, `place-${pl.id}-hub`]).filter(id => map.getLayer(id));
}
function placeAt(point) {
  const ids = placeLayerIds().filter(id => map.getLayoutProperty(id, "visibility") !== "none");
  return ids.length ? map.queryRenderedFeatures(point, { layers: ids })[0] || null : null;
}

let hoveredPlace = null;
function showPlaceCard(e, pinned) {
  if (!e.features.length) return;
  const f = e.features[0], p = f.properties;
  const pl = PLACE_LAYERS.find(x => x.sourceLayer === f.sourceLayer);
  if (!pl) return;
  map.getCanvas().style.cursor = "pointer";
  const key = `${f.sourceLayer}:${p.name}:${f.geometry.coordinates.join(",")}`;
  const lngLat = { lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] };
  if (pinned) {
    pinnedAt = Date.now();
    popup.remove();
    hoveredPlace = null;
    const html = placeCardHtml(pl, p, true);
    rememberCard({ draw: () => placeCardHtml(pl, p, true), pinned: true, lngLat, sel: `.pc-card[data-pid="${p.pid}"]` });
    if (isNarrow()) openSheet(html, lngLat);
    else { pinnedCard.options.anchor = "top-left"; placeCard(pinnedCard, lngLat, html); }
    return;
  }
  if (pinnedCard.isOpen() || sheet || isNarrow()) return;
  if (popup.isOpen() && hoveredPlace === key) return;
  hoveredPlace = key;
  hoveredEgid = null;   // the building card is drawn afresh after this one
  popup.options.anchor = "top-left";
  placeCard(popup, lngLat, placeCardHtml(pl, p, false));
  rememberCard({ draw: () => placeCardHtml(pl, p, false), pinned: false, lngLat, sel: `.pc-card[data-pid="${p.pid}"]` });
}
for (const pl of PLACE_LAYERS) {
  if (pl.id === "stops") continue;   // web/stops.js
  for (const id of [`place-${pl.id}`, `place-${pl.id}-hub`]) {
    map.on("mousemove", id, e => showPlaceCard(e, false));
    map.on("click", id, e => { e.originalEvent && e.originalEvent.stopPropagation(); showPlaceCard(e, true); });
    map.on("mouseleave", id, () => { hoveredPlace = null; });
  }
}
