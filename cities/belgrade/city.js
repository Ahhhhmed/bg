// Belgrade: the settlement of Belgrade (389 km2) and its 10 urban municipalities.
// Read by every page script (web/*.js) as CITY. What Belgrade lacks next to
// Zürich is listed in `coverage`: the map keeps the same lenses and card, and
// says "no data for Belgrade" where there is no open source (owner, 2026-10-27).
const NONE = { state: "none" };
const CITY = {
  id: "belgrade",
  name: { de: "Belgrad", en: "Belgrade", sr: "Beograd" },
  langs: ["sr", "en"],
  center: [20.46, 44.805], zoom: 12.2,
  credits: "© OpenStreetMap · Overture Maps · RGZ · Sekretarijat za javni prevoz · SEPA · Copernicus",
  // Copernicus DEM hillshade (pipeline/build_relief.py; its corners = X0..X1, Y0..Y1 there)
  relief: { type: "image", url: "../data/layers/relief.png", coordinates: [[20.0, 45.0], [20.95, 45.0], [20.95, 44.5], [20.0, 44.5]] },
  housing: "osm",                           // housing = OSM residential building types (unknown use counts as housing)
  idLabel: null,                            // no register id; the card shows the outline's source
  borders: { municipality: { de: "Grenze der Siedlung Belgrad", en: "Border of the settlement of Belgrade", sr: "Granica naselja Beograd" },
             kreis: { de: "Stadtgemeinde", en: "City municipality", sr: "Gradska opština" } },
  home: "/",   // the site's start page is this map
  // the menu links them: Zürich is the reference, a fuller map of the same app (C-23)
  others: [{ id: "zurich", href: "/zurich/", name: { de: "Referenz: Zürich", en: "Reference: Zürich", sr: "Referenca: Cirih" },
             sub: { de: "dieselbe Karte mit vollständigeren Daten", en: "the same map with fuller data", sr: "ista karta sa potpunijim podacima" } }],
  coverage: {
    lens: {
      year: NONE, noise_road: NONE, noise_rail: NONE, heating: NONE,
      floors: { state: "partial", share: 0.13, source: "OpenStreetMap" }, dwellings: NONE, solar: NONE,
      oev: NONE, hazard: NONE, runoff: NONE, aircraft: NONE, contaminated: NONE, zoning: NONE, es: NONE,
      // places on foot the sources here don't have: day care apart from kindergartens, emergency stations
      walk_kita: NONE, walk_er: NONE,
    },
    place: {},
    // card blocks / figures / tags without a source here (i18n keys)
    card: ["hc.built", "hc.dwellings", "hc.volume", "hc.heating", "hc.heating2", "hc.solar", "hc.sec.plot",
           "hc.roadNoise", "hc.railNoise", "hc.aircraft", "hc.es", "hc.oev", "hc.zone",
           "hc.hazard", "hc.runoff", "hc.contaminated", "tag.elevation", "tag.shelter", "tag.rooms", "tag.heatedArea"],
    walk: "full",
  },
  // the commute lens: to Trg Republike (owner, 2026-10-27), steps for a bigger city
  lenses: {
    commute: {
      label: { de: "Trg Republike", en: "To Trg Republike", sr: "Do Trga Republike" },
      legendTitle: { de: "Zum Trg Republike, werktags 6:30–9 Uhr im Mittel (Fussweg, Warten, Fahrt)",
                     en: "To Trg Republike, weekdays 6:30–9:00 on average (walk, wait, ride)",
                     sr: "Do Trga Republike, radnim danima 6:30–9:00 u proseku (pešaka, čekanje, vožnja)" },
      steps: [20, 35, 50], labels: ["< 20 min", "20 – 35", "35 – 50", "≥ 50"],
    },
  },
  // OSM building types (Overture `class`) for the card's second line
  classNames: {
    house: { de: "Haus", en: "House", sr: "Kuća" }, apartments: { de: "Mehrfamilienhaus", en: "Apartment building", sr: "Stambena zgrada" },
    residential: { de: "Wohngebäude", en: "Residential building", sr: "Stambeni objekat" }, detached: { de: "Einfamilienhaus", en: "Detached house", sr: "Samostalna kuća" },
    semidetached_house: { de: "Doppelhaus", en: "Semi-detached house", sr: "Dvojna kuća" }, terrace: { de: "Reihenhaus", en: "Terraced house", sr: "Kuća u nizu" },
    dormitory: { de: "Wohnheim", en: "Dormitory", sr: "Dom" }, houseboat: { de: "Hausboot", en: "Houseboat", sr: "Splav" },
    commercial: { de: "Geschäftshaus", en: "Commercial building", sr: "Poslovni objekat" }, retail: { de: "Ladengeschäft", en: "Retail building", sr: "Trgovina" },
    office: { de: "Bürogebäude", en: "Office building", sr: "Poslovna zgrada" }, industrial: { de: "Industriegebäude", en: "Industrial building", sr: "Industrijski objekat" },
    school: { de: "Schule", en: "School", sr: "Škola" }, kindergarten: { de: "Kindergarten", en: "Kindergarten", sr: "Vrtić" },
    university: { de: "Hochschule", en: "University", sr: "Fakultet" }, hospital: { de: "Spital", en: "Hospital", sr: "Bolnica" },
    church: { de: "Kirche", en: "Church", sr: "Crkva" }, garage: { de: "Garage", en: "Garage", sr: "Garaža" }, garages: { de: "Garagen", en: "Garages", sr: "Garaže" },
    shed: { de: "Schuppen", en: "Shed", sr: "Šupa" }, roof: { de: "Dach", en: "Roof", sr: "Nadstrešnica" }, warehouse: { de: "Lager", en: "Warehouse", sr: "Magacin" },
    hotel: { de: "Hotel", en: "Hotel", sr: "Hotel" }, public: { de: "Öffentliches Gebäude", en: "Public building", sr: "Javni objekat" },
    construction: { de: "Im Bau", en: "Under construction", sr: "U izgradnji" },
  },
  // the Belgrade sense of a few labels
  strings: {
    "cov.cityName": { de: "Belgrad", en: "Belgrade", sr: "Beograd" },
    "hc.commute": { de: "Zum Trg Republike", en: "To Trg Republike", sr: "Do Trga Republike" },
    "hc.hbStop": { de: "Haltestelle zum Trg Republike", en: "Stop for Trg Republike", sr: "Stanica ka Trgu Republike" },
    "hc.stopGist": { de: "Zum Trg Republike morgens", en: "To Trg Republike, mornings", sr: "Do Trga Republike, ujutru" },
    "hc.commuteModel": { de: "Zum Trg Republike geschätzt: Fussweg zur besten Haltestelle (≈ 80 m/min) + ihre mittlere Reisezeit inkl. Warten, werktags 6:30–9 Uhr",
                         en: "to Trg Republike estimated: walk to the best stop (≈ 80 m/min) + its mean trip including the wait, weekdays 6:30–9:00",
                         sr: "do Trga Republike, procena: pešaka do najbolje stanice (≈ 80 m/min) + njeno prosečno putovanje sa čekanjem, radnim danima 6:30–9:00" },
    "sc.walkModel": { de: "Fusswege zwischen Haltestellen geschätzt (Luftlinie × 1,3 bei 80 m/min, + 1 min); der Fahrplan hat keine Umsteigezeiten",
                      en: "walks between stops estimated (straight line × 1.3 at 80 m/min, + 1 min); the timetable has no transfer times",
                      sr: "pešačenje između stanica procenjeno (vazdušna linija × 1,3 pri 80 m/min, + 1 min); red vožnje nema vremena presedanja" },
    "sc.atHb": { de: "Hier ist der Trg Republike.", en: "This is Trg Republike.", sr: "Ovde je Trg Republike." },
    "sc.average": { de: "Ø zum Trg Republike", en: "avg. to Trg Republike", sr: "Ø do Trga Republike" },
    "sc.day": { de: "Weg zum Trg Republike über den Tag", en: "To Trg Republike through the day", sr: "Do Trga Republike tokom dana" },
    "sc.dayAria": { de: "Reisezeit zum Trg Republike über den Tag", en: "Travel time to Trg Republike through the day", sr: "Vreme putovanja do Trga Republike tokom dana" },
  },
};
