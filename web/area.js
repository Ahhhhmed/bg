/**
 * Map area overlay of the city map (index.html):
 * municipality and Zürich Kreis border layers, their name labels, and fitting
 * the initial view to the area.
 *
 * Labels are HTML markers rather than MapLibre symbol layers: symbol text
 * needs a glyph server, and this project's style deliberately has none (no
 * third-party font host to depend on). There are only ~25 labels, so DOM
 * markers are cheap. Border lines are the `borders` tile layer (lake cut out,
 * see cities/zurich/pipeline/swiss/clip_to_area.py). Label positions and the area bbox come from
 * data/layers/area_labels.json, written by cities/zurich/pipeline/swiss/clip_to_area.py and
 * cities/zurich/pipeline/swiss/build_kreise.py.
 */
const AREA_LABELS_URL = "../data/layers/area_labels.json";

// Both borders are cocoa with a cream casing (soft redesign, 028), so they
// stand out from the greige road casings (Kreis borders often run along
// streets). Municipality: solid and thick. Kreis: a visibly lower level --
// thinner, dashed, lighter. Kreis lines are only the internal ones (the
// city's outer edge is drawn as a municipality border).
const MUNICIPALITY_LINE_COLOR = "#7a6c61";
const KREIS_LINE_COLOR = "#a3968a";
const BORDER_CASING_COLOR = "#fffaf4";

function areaBorderLayers(source) {
  return [
    {
      id: "kreis-casing", type: "line", source, "source-layer": "borders",
      filter: ["==", ["get", "level"], "kreis"],
      layout: { "line-join": "round" },
      paint: {
        "line-color": BORDER_CASING_COLOR,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 2.0, 13, 3.5, 16, 6.5],
        "line-opacity": 0.85
      }
    },
    {
      id: "kreis-line", type: "line", source, "source-layer": "borders",
      filter: ["==", ["get", "level"], "kreis"],
      layout: { "line-join": "round" },
      paint: {
        "line-color": KREIS_LINE_COLOR,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.8, 13, 1.5, 16, 2.8],
        // shorter dashes when zoomed out, or they merge into a solid line
        "line-dasharray": ["step", ["zoom"], ["literal", [2, 2]], 14, ["literal", [5, 3]]]
      }
    },
    {
      id: "municipality-casing", type: "line", source, "source-layer": "borders",
      filter: ["==", ["get", "level"], "municipality"],
      layout: { "line-join": "round" },
      paint: {
        "line-color": BORDER_CASING_COLOR,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 2.4, 13, 4.0, 16, 7],
        "line-opacity": 0.85
      }
    },
    {
      id: "municipality-line", type: "line", source, "source-layer": "borders",
      filter: ["==", ["get", "level"], "municipality"],
      layout: { "line-join": "round" },
      paint: {
        "line-color": MUNICIPALITY_LINE_COLOR,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1.0, 13, 2.0, 16, 3.6]
      }
    }
  ];
}

// the city's names for its two border levels (web/city.js)
const AREA_LEGEND_KEYS = [
  { label: CITY.borders.municipality, swatchStyle: `height:0;border-top:3px solid ${MUNICIPALITY_LINE_COLOR}` },
  { label: CITY.borders.kreis, swatchStyle: `height:0;border-top:2px dashed ${KREIS_LINE_COLOR}` },
];

// Zoom ranges in which each label level is shown.
const LABEL_ZOOMS = {
  municipality: [0, 14.5],
  kreis: [11.5, 15.5],
};

function injectAreaLabelCss() {
  if (document.getElementById("area-label-css")) return;
  const style = document.createElement("style");
  style.id = "area-label-css";
  style.textContent = `
    .area-label {
      pointer-events: none;
      white-space: nowrap;
      text-shadow: 0 0 3px #fffaf4, 0 0 4px #fffaf4, 0 0 8px #fffaf4;
    }
    /* town names in the soft serif, Kreis names in the rounded sans (web/theme.css) */
    .area-label.municipality {
      font-family: "Fraunces", Georgia, serif;
      font-variation-settings: "SOFT" 100, "WONK" 0;
      font-size: 15px; font-weight: 600; letter-spacing: 0.02em;
      color: #5c4f46;
    }
    .area-label.kreis {
      font-family: "Nunito", system-ui, sans-serif;
      font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: lowercase;
      color: #766a60;
    }
  `;
  document.head.appendChild(style);
}

/**
 * Adds labels to `map` and, unless opts.fit === false, fits the view to the
 * area. Returns a promise resolving to the area bbox (or null if the labels
 * file is missing -- the map still works, just without labels).
 */
async function initAreaOverlay(map, opts = {}) {
  let data;
  try {
    const resp = await fetch(AREA_LABELS_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (e) {
    console.warn("area labels unavailable:", e);
    return null;
  }
  if (opts.fit !== false && data.bbox) {
    const [x0, y0, x1, y1] = data.bbox;
    map.fitBounds([[x0, y0], [x1, y1]], { padding: opts.padding ?? 20, duration: 0 });
  }
  injectAreaLabelCss();
  const markers = data.labels.map((l) => {
    const el = document.createElement("div");
    el.className = `area-label ${l.level}`;
    el.textContent = l.name;
    const marker = new maplibregl.Marker({ element: el }).setLngLat([l.lon, l.lat]).addTo(map);
    return { marker, el, level: l.level };
  });
  const update = () => {
    const z = map.getZoom();
    for (const m of markers) {
      const [lo, hi] = LABEL_ZOOMS[m.level] || [0, 24];
      m.el.style.display = z >= lo && z < hi ? "" : "none";
    }
  };
  map.on("zoom", update);
  update();
  return data.bbox;
}
