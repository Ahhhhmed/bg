/**
 * Relief shading under the vector map. In Zürich swisstopo's own relief
 * tiles (swissALTI3D Reliefschattierung) from wmts.geo.admin.ch, in Belgrade
 * a hillshade image from the Copernicus DEM (build_relief.py).
 *
 * The shading is a full grey image (flat ground is grey too), hence the low
 * opacity (25 %). The layer goes above the
 * greenery and below water, roads and buildings.
 */
// The city's relief (web/city.js CITY.relief): swisstopo's tiles in Zürich,
// our own hillshade image elsewhere (cities/belgrade/pipeline/build_relief.py:
// one PNG, its corners in city.js).
function reliefSources() {
  if (CITY.relief.type === "image") return { relief: { type: "image", url: CITY.relief.url, coordinates: CITY.relief.coordinates } };
  return {
    relief: {
      type: "raster",
      tiles: ["https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissalti3d-reliefschattierung/default/current/3857/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 18,
      attribution: "© swisstopo (swissALTI3D)"
    }
  };
}

function reliefLayers() {
  return [{
    id: "relief",
    type: "raster",
    source: "relief",
    paint: {
      "raster-opacity": 0.25,   // soft redesign (028): lighter, airier
      "raster-fade-duration": 0
    }
  }];
}
