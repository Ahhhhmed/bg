---
name: map-style
description: Changing how the city map looks or what it shows -- layer styles, year colours and legend, relief, the building / place / stop cards, the controls (lens catalogue, search profile, map menu, legend bar, data-age pin), the soft theme, a city's coverage -- without breaking the rules earlier sessions learned the hard way. Use for any change in web/ or a city's city.js.
---

# Map style

## Where things live (`web/`, one copy for every city)
| File | What |
|---|---|
| `../cities/<id>/city.js` | **the city** (`CITY`): name, languages, centre, relief, credits, housing rule, border labels, the other cities, `coverage` (what's missing and why), `strings` / `lenses` (its own sense of a label: the commute target), `classNames` |
| `years.js` | the four year groups + colours (C-07): `yearColorExpression()`, `yearGroup()` |
| `layers.js` | **the layer stack** (`cadastreLayers()`), palette (`BASE`), road classes, building constants, the tiers (C-09): `BUILDING_COLOR_MODES`, `GROUND_THEMES`, `PLACE_LAYERS`, `PLACE_GLYPHS`, `LAYER_GROUPS`; the lenses (C-10): `AREA_MODES`, `LENS_MODES`, `LENS_GROUPS`, `modeClass()`; coverage: `coverageOf()`, `lensCoverage()`, `cardUnavailable()`, `covText()` |
| `i18n.js`, `i18n_sr.js` | the UI languages (C-03): `STRINGS`, `t()`, `tr()` for `{ de, en, sr }` labels; Serbian falls back to `SR_TEXT[english]` |
| `controls.js` | the controls (C-10): brand card + map menu, site menu (the other cities), zoom readout, lens catalogue (greys lenses without data), search-profile panel and chips, legend bar (with the coverage line); CSS in `controls.css` |
| `profile.js` | the search profile (C-17): `PROFILE_RANGES`, `critExpr()` (map) and `critPass()` (JS) -- one rule, keep both in step --, `?f=`, the counts over `data/profile_table.json` |
| `search.js` | address, place and stop search (C-18) |
| `freshness.js` | the attribution pin with the data age (C-16) |
| `nearby.js` | the card's "In der Nähe, zu Fuss" list and the stop gist (C-15) |
| `places.js` | place cards (C-14): `PLACE_CARDS`, `PLACE_ACCENT` |
| `stops.js` | the stop card (C-13) |
| `map.js` | map setup, card placement (`placeCard`), the building card (`buildingCardModel`, C-12), GWR code tables (Zürich) |
| `relief.js` | the relief: WMTS tiles (Zürich) or an image (Belgrade), `CITY.relief` |
| `area.js` | borders and HTML labels (no glyph server) |
| `theme.css` | the look's tokens (C-06) |

A new web file must be added to the `WEB` list in `scripts/build.sh`, or it
404s on the deployment while working locally.

## Rules
- **Every city, gaps said out loud (C-01):** a new lens / place layer / card block / walk kind
  exists for every city. A city without a source for it gets an entry in its
  `CITY.coverage` (`lens.<id>`, `place.<id>`, `card: [i18n key]`, `lens.walk_<kind>`); the UI
  greys it and says why. Never hide it, never fill a gap with a guess (C-05).
- **Nothing city-specific in `web/`:** a value that differs by city goes into `city.js`.
- **Languages (C-03):** every label is `{ de, en }` (+ `sr` where Serbian differs from
  `SR_TEXT`) or a `t("key")` string; a new English string needs its line in `i18n_sr.js`.
  Anything drawn from them re-renders on the `bg:lang` event.
- **Tiers, one colour per channel (C-09):** a building colour goes into
  `BUILDING_COLOR_MODES`, an area theme into `GROUND_THEMES`, a point layer into
  `PLACE_LAYERS` (monochrome icon, glyph in `PLACE_GLYPHS`), base layers into `LAYER_GROUPS`.
  Never a new floating panel. Colour modes: four shades of one hue, darker = more; run
  `python3 scripts/check_mode_colours.py` / `check_ground_colours.py` / `check_year_colours.py`.
- **Housing in front (C-08):** `isHousing()` / `IS_RESIDENTIAL` per `CITY.housing`.
- **Nothing off screen, no control over another; phones get bottom sheets and 44 px targets
  (C-10).** Check at phone width too.
- **One vector source** (`cadastre`); layers pick a `source-layer`. **Water needs a fill and a
  line layer.** Every toggleable layer has `metadata: {"bg:group": ...}`.
- **Buildings from z13 (C-11):** tiles from `shared/build_tiles.sh` only.
- **Text never wears a year colour**; the year colours appear only where they mean a year (C-07).
- **Building card (C-12):** a new property gets a block in `buildingCardModel()`; every block
  always shows; escape every data string (`escapeHtml`).
- **Tiles URL:** keep `cadastre.pmtiles"` literally in `map.js` (the build versions it).
- **Pinned libraries:** MapLibre GL 5.24.0 and pmtiles 3.0.6 from unpkg; don't bump in passing.

## Verify
`verify-site` skill: local `dist/` first, then the preview; screenshots of the changed
area in each city.
