# Key decisions

Decisions future sessions must not undo by accident. Each says what was
decided, why, and where it lives in the repo. Smaller choices stay in their
PR's "Decisions for review" and the backlog item's Log.

To change one: say so to the owner, get their OK, then edit the entry. Don't
delete it: add "**Superseded** by C-NN (date)" and write the new decision as a
new entry. New entries go at the end with the next number.

bg is a map of Belgrade; Zürich is its reference (C-23). The map app started
as the web map of a private Zürich project (2026-10); the entries up to C-18
are the rules that map was built on, carried over because the app still
follows them.

---

### C-01 · One map, every city: the same colouring, gaps said out loud (2026-10-27)
- **Decision (owner):** every city gets the same map: the same lenses, colours, cards and
  controls. Year built is the default lens everywhere.
- Where a city has no source for a lens, a place layer, a card block or a walk kind, it
  stays visible but greyed, with the reason ("keine Daten", "nicht verfügbar für Belgrad");
  the legend says so too. Never hidden, never filled with a guess.
- **Where:** `cities/<id>/city.js` (`CITY.coverage`), read by `lensCoverage()`,
  `coverageOf()`, `cardUnavailable()` in `web/layers.js`.

### C-02 · One app, a config per city; a public repo (2026-10-27)
- **Decision (owner):** the repo is public and holds only open data and the code. There's
  one copy of the web app (`web/`); anything that differs by city is in
  `cities/<id>/city.js`, never in an `if (city === ...)`. Each city has its own pipeline
  (its sources differ) and writes the same layer names and building properties, so the
  tiles, the profile table and the address index are built by shared scripts.
- The repo started with one fresh commit (no history carried over from the private project).
- **Where:** `cities/`, `shared/`, `scripts/build.sh` (copies only listed files; refuses
  private-looking ones).

### C-03 · Languages per city (2026-10-18, 2026-10-27)
- **Decision (owner):** every UI string exists in each of the city's languages, switched in
  place by a dropdown (`?lang=`, localStorage). Zürich: German (default) and English.
  Belgrade: Serbian in Latin script (default) and English; Cyrillic may come later.
- Place names, addresses and data values stay as their source writes them.
- **Where:** `web/i18n.js` (`t()`, `tr()`; labels are `{ de, en, sr }`), `web/i18n_sr.js`
  (`SR_TEXT`, Serbian keyed by the English text).

### C-04 · The commute goes to one point per city, from the timetable (2026-10-23, 2026-10-27)
- **Decision (owner):** Zürich: Zürich HB. Belgrade: Trg Republike.
- Per building: the best stop within 1.5 km on foot of walk (network metres / 80) + that
  stop's mean trip to the target on a weekday morning 06:30-09:00, waiting included, from a
  profile scan of the GTFS timetable. Stops near the target walk there. An estimate: "≈".
- The card's stop is the one the commute goes from, not the nearest stop.
- Property names are the same in every city (`commute_hb_min`, `hb_mean`, `n_hb`): "hb" is
  the city's target; the labels come from `CITY.strings` / `CITY.lenses`.
- **Where:** `shared/pipeline/transit_profiles.py`, `shared/pipeline/walk.py`, each city's
  transit script.

### C-05 · Only what a source states (2026-10-23)
- **Decision (owner):** a fact on the map comes from a register field, a tag, or a point
  lying *inside* a source's outline. No name patterns, no nearest-neighbour matching, no
  guessing (no estimated years where no register has them). A missing key fact shows as a
  dashed "unbekannt" / "nicht verfügbar" chip. Every card lists its sources with their dates.
- Joins are by an identifier the sources share (EGID, EGRID, a station's own name in both
  of one agency's datasets), never by proximity.
- **Where:** every pipeline; `card_sources.json` / `places_sources.json` per city.

### C-06 · Soft look: "wellness / Scandi soft" (2026-10-17)
- **Decision (owner):** oat `#f6f1ea` background, cream `#fffaf4` cards, cocoa `#4a4039`
  text (muted `#766a60`, the lightest that passes 4.5:1), soft cocoa `#6b5d53` for controls
  and links. Fraunces (SOFT axis on, often lowercase) for titles, Nunito for the rest.
  Rounded cards, pills, soft shadows, slow fades, off under `prefers-reduced-motion`.
- **Where:** `web/theme.css` (tokens), `web/style.css`, `web/controls.css`.

### C-07 · Year colours: one hue in four shades, only where they mean a year (2026-10-18)
- **Decision (owner):** four year groups (before 1950, 1950-1989, 1990-2009, 2010 and
  later) in one dusty aubergine (LCh h 320), newer = darker: fills `#eeddf1` / `#bea2c5` /
  `#8d6b96` / `#563a5e`, outlines `#957f9a` / `#917199` / `#623e6c` / `#2e1037`. Every pair
  of fills >= dE 20 apart under normal and simulated colour-blind vision, every outline
  >= 3:1 on the background.
- The year colours appear only on the map, its legend and swatches, never as decoration.
  Text never wears them (a swatch beside the year). The signature is the contour mark
  (`web/mark.svg`, also the favicon).
- **Where:** `web/years.js`.

### C-08 · Housing in front, the rest in the background (2026-10-18)
- **Decision (owner):** only housing gets the year shades; buildings without housing fade
  to greige `#ece7e0` but stay recognisable; buildings in development get an ochre fill with
  a dashed outline; underground ones are faint and never extruded. Tracks are a light warm
  grey, quieter than the buildings; tunnels are faint dashes; bridges are drawn again above
  what they cross.
- Housing per city: Zürich: GWR category 1010-1040. Belgrade: OSM's `building` tag; a
  building whose use is unknown counts as housing (under review, C-22).
- **Where:** `web/layers.js` (`IS_RESIDENTIAL`, `isHousing()`), `CITY.housing`.

### C-09 · The map in tiers; colours don't stack (2026-10-18)
- **Decision (owner):** buildings are the main theme, coloured by one mode at a time; area
  themes under them are pick-one; places are monochrome icons, any number on; the base map
  is on / off only, never coloured by data. A filter never adds a colour: buildings it
  leaves out fade to greige, or are hidden (`?hide=1`).
- **Where:** `web/layers.js` (`BUILDING_COLOR_MODES`, `GROUND_THEMES`, `PLACE_LAYERS`,
  `LAYER_GROUPS`).

### C-10 · Controls in four places, one lens at a time (2026-10-24)
- **Decision (owner):** the building modes and the area themes are one catalogue of lenses
  (`LENS_MODES`); one lens colours the map. The controls live in four places: the brand card
  (top left: city, search, language, the map menu with places, base map, 2D / 3D), "Einfärben
  nach" next to it, the search profile (chips + left panel), the site menu (top right: the
  other cities), plus the legend bar (bottom left) and the attribution pin (bottom right).
  A new layer goes into one of those lists, never into a new floating panel.
- Nothing off screen, no control over another; on phones popovers, the profile and the card
  are bottom sheets, every control a 44 px touch target.
- **Where:** `web/controls.js`, `web/controls.css`.

### C-11 · Buildings from z13, complete; never thinned at random (2026-10-18)
- **Decision (owner):** the tiles have no buildings below z13, all but underground / < 40 m²
  ones at z13, all at z14; `--drop-densest-as-needed` kept a random share of buildings and
  looked like noise. One vector source for the whole archive (one source per theme cost 5x
  download).
- **Where:** `shared/build_tiles.sh`, the `cadastre` source in `web/map.js`.

### C-12 · The building card shows everything (2026-10-19)
- **Decision (owner):** key figures (year first), then blocks for every layer's fact, each in
  its layer's colour; the active lens's block is ringed. Every block always shows; a building
  without the value gets a dashed chip saying why. The pinned card ends with its sources and
  their dates.
- **Where:** `buildingCardModel()` in `web/map.js`.

### C-13 · Stop cards from the timetable (2026-10-22)
- **Decision (owner):** each stop's card shows its trips to the city's target over a weekday:
  one hour at a time (fastest, mean, slowest, the wait, the cycle), the day's curve, and the
  departures. Each line gets its own colour from a fixed palette. The transit lines are not
  drawn on the map.
- **Where:** `web/stops.js`, `data/stops/<nr>.json` per city.

### C-14 · Place cards: one design for every category (2026-10-23)
- **Decision (owner):** icon, name, kind · municipality, figure tiles in the category's accent,
  coloured chips and rows, address; website and phone when pinned. A place icon beats the
  building under it.
- **Where:** `web/places.js` (`PLACE_CARDS`).

### C-15 · Walking distances and the card's neighbourhood (2026-10-23)
- **Decision (owner):** per building and kind the metres along roads and paths (no motorways)
  to the nearest known place (`w_<kind>`, `n_<kind>`); minutes = metres / 80, "≈". They feed
  the walk lens, the profile and the card's "In der Nähe, zu Fuss" list.
- **Where:** `shared/pipeline/walk.py` (Belgrade), Zürich's `build_walk.py`; `web/nearby.js`.

### C-16 · Data age in the attribution pin (2026-10-24)
- **Decision (owner):** one indicator for the whole map: the oldest date of what it shows,
  coloured by age, in the attribution pin; the cards' source dates use the same colours.
- **Where:** `web/freshness.js`.

### C-17 · The search profile counts homes (2026-10-23, 2026-10-25)
- **Decision (owner):** criteria on any lens or walk; each rule written twice, `critExpr()`
  (MapLibre) and `critPass()` (JS); the counts are over the housing only, from
  `data/profile_table.json`, never from rendered features. State in the URL, not localStorage.
- **Where:** `web/profile.js`, `shared/pipeline/profile_table.py`.

### C-18 · The map is the city's start page; the address search (2026-10-24, 2026-10-25)
- **Decision (owner):** `/<city>/` is the map; the field in the brand card searches every
  building with an address and every place / stop (every typed word starts a word of the
  entry, accents folded). The address index holds the address, postcode, id and position only.
- **Where:** `scripts/build.sh`, `web/search.js`, `shared/pipeline/address_index.py`.

### C-19 · Zürich refreshes from the Swiss sources itself (2026-10-29)
- **Decision (owner):** the Swiss fetch scripts the City of Zürich needs live in
  `cities/zurich/pipeline/swiss/`, with the area set to one municipality (BFS 261) and its
  12 Kreise as inner borders; `refresh.sh` runs them in order and `assemble.py` writes the
  shared layer names.
- **Where:** `cities/zurich/`.

### C-20 · MIT for the code; the data under its sources' licences (2026-10-29)
- **Decision (owner):** the code is MIT-licensed (`LICENSE`); every dataset keeps its source's
  licence and attribution (`NOTICE.md`, the attribution pin, the cards' sources). OSM-derived
  data stays ODbL.

### C-21 · Air quality: measured values, no verdict (2026-10-29)
- **Decision (owner):** monitoring stations as a place layer, one card each: the last 30 days'
  means (preliminary, unverified, labelled so) and verified annual means where the agency
  publishes them. The EU limits and WHO guidelines are shown for reference only: a 30-day
  mean isn't an annual mean. Zürich has no air layer (greyed: no source wired in).
- **Where:** `cities/belgrade/pipeline/build_air.py`, `PLACE_CARDS.air` in `web/places.js`.

### C-22 · Belgrade: the settlement, 10 urban municipalities; unknown use counts as housing (2026-10-27, under review)
- **Decision (taken for the first version, for the owner to confirm):** the area is the
  settlement Beograd with its 10 urban municipalities as inner borders (not the 17 of the
  City of Belgrade, the suburban ones are mostly fields). OSM `building=yes` (use unknown)
  counts as housing, drawn in the "year unknown" shade and counted in the profile.
- **Where:** `cities/belgrade/pipeline/build_layers.py`.

### C-23 · bg is a Belgrade map; Zürich is the reference (2026-10-29)
- **Decision (owner):** the project is **bg** (short for Belgrade), in the public repo
  `Ahhhhmed/bg`. Its start page `/` is Belgrade's map; the city picker is gone. Zürich stays
  at `/zurich/` as the reference: the same app with fuller data, linked from the menu
  ("Referenca: Cirih"), to show what a feature looks like where a source exists.
- Zürich is refreshed rarely: when the shared app changes or the reference needs it. Its own
  roadmap items are P3. The repo's docs are in English; the map's UI is Serbian / English.
- **Where:** `scripts/build.sh` (the start page), `CITY.home` / `CITY.others` in
  `cities/*/city.js`, `backlog/`.
