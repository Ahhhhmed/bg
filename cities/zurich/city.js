// The City of Zürich (12 Kreise). Read by every page script (web/*.js) as CITY;
// the build copies it to <city>/web/city.js. See docs/schema.md.
const CITY = {
  id: "zurich",
  name: { de: "Zürich", en: "Zürich", sr: "Cirih" },
  langs: ["de", "en"],
  center: [8.535, 47.375], zoom: 12.5,
  credits: "© swisstopo · BFS · BAFU · Kanton ZH · Stadt Zürich · OSM",
  relief: { type: "wmts" },                 // swisstopo's relief tiles (web/relief.js)
  housing: "gwr",                           // housing = GWR category 1010-1040
  idLabel: "EGID",
  borders: { municipality: { de: "Stadtgrenze", en: "City border" }, kreis: { de: "Stadtkreis", en: "City district (Kreis)" } },
  // what this city has: lenses, place layers, card blocks (a key missing here = full)
  home: "/zurich/",
  // the menu links them: this map is the reference for Belgrade's (C-23)
  others: [{ id: "belgrade", href: "/", name: { de: "Belgrad", en: "Belgrade", sr: "Beograd" },
             sub: { de: "die Hauptkarte dieses Projekts", en: "this project's main map", sr: "glavna karta projekta" } }],
  // no air-quality layer here (backlog 001: the city's stations and BAFU's modelled maps)
  coverage: { lens: {}, place: { air: { state: "none" } }, card: [], walk: "full" },
};
