/**
 * Construction-year groups, shared by map.js and controls.js.
 * Labels are { de, en } (web/i18n.js tr()); the ranges are plain strings.
 *
 * Four groups chosen by the owner on 2026-10-17. Colours since 2026-10-18
 * (decision C-07): ONE hue in four shades, newer = darker, like the print
 * sheets. The hue is a dusty aubergine (LCh h = 320), picked because it hints
 * at nothing by itself (green would read as "new" / "eco", red as danger,
 * blue as water, orange / brown would merge with the cocoa and oat theme).
 *
 * The fills step 20 L* apart (90 / 70 / 50 / 29), so every pair is >= dE 20
 * (CIELAB) apart for normal vision and simulated deutan, protan and tritan
 * vision; each has a deeper outline in the same hue, >= 3:1 against the oat
 * background, that carries the shape where the fill is pale. Checked by
 * scripts/check_year_colours.py; change colours only with it.
 */
const YEAR_GROUPS = [
  { from: null, to: 1949, label: { de: "vor 1950", en: "before 1950" },  color: "#eeddf1", outline: "#957f9a" },
  { from: 1950, to: 1989, label: "1950 – 1989", color: "#bea2c5", outline: "#917199" },
  { from: 1990, to: 2009, label: "1990 – 2009", color: "#8d6b96", outline: "#623e6c" },
  { from: 2010, to: null, label: { de: "ab 2010", en: "2010 and later" }, color: "#563a5e", outline: "#2e1037" },
];
const NO_YEAR_COLOR = "#ddd5ca";         // greige: no hue = no data
const NO_YEAR_OUTLINE = "#9b8f82";

// MapLibre colour expression: step on `baujahr`, gray when it's missing.
function yearColorExpression() {
  const expr = ["step", ["get", "baujahr"], YEAR_GROUPS[0].color];
  for (const g of YEAR_GROUPS.slice(1)) expr.push(g.from, g.color);
  return ["case", ["==", ["get", "baujahr"], null], NO_YEAR_COLOR, expr];
}

// Same, for the outline colour.
function yearOutlineExpression() {
  const expr = ["step", ["get", "baujahr"], YEAR_GROUPS[0].outline];
  for (const g of YEAR_GROUPS.slice(1)) expr.push(g.from, g.outline);
  return ["case", ["==", ["get", "baujahr"], null], NO_YEAR_OUTLINE, expr];
}

// The group a year falls in, or null for a missing year.
function yearGroup(year) {
  if (!year) return null;
  return YEAR_GROUPS.find(g => (g.from == null || year >= g.from) && (g.to == null || year <= g.to));
}

// Map filter for one group (index into YEAR_GROUPS).
function yearGroupFilter(i) {
  const g = YEAR_GROUPS[i], parts = [["!=", ["get", "baujahr"], null]];
  if (g.from != null) parts.push([">=", ["get", "baujahr"], g.from]);
  if (g.to != null) parts.push(["<=", ["get", "baujahr"], g.to]);
  return ["all", ...parts];
}
