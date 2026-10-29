"""
Replace the hand-sketched placeholder water/greenery polygons with real
swissTLM3D vector data (same live geo.admin.ch identify API approach used
for buildings/roads). The old zurich_water.geojson / zurich_greenery.geojson
were small hand-drawn approximations (a handful of coordinates each) --
hence the visible mismatch against the real raster basemap.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from geoadmin_tiles import fetch_layer
from area import area_bbox, area_polygon

# The map area (config/area.yaml, see area.py); fetch tiles only near it.
BBOX = area_bbox()
REGION = area_polygon().buffer(0.002)  # ~200 m margin

ROOT = Path(__file__).resolve().parents[2]

TARGETS = [
    ("ch.swisstopo.swisstlm3d-gewaessernetz", "water", ROOT / "data" / "work" / "zurich_water.geojson"),
    # Greenery is NOT fetched here: swisstlm3d-wald isn't served as vectors by
    # identify (see SOURCES.md); zurich_greenery.geojson comes from
    # build_greenery_raster.py, and writing it here would overwrite it.
]


def main():
    for layer, kind, out_path in TARGETS:
        print(f"Fetching real {kind} vector data from {layer} ...")
        raw = fetch_layer(layer, BBOX, geometry_format="geojson", log_prefix=f"[{kind}] ", region=REGION)
        features = []
        for r in raw:
            geom = r.get("geometry")
            if not geom:
                continue
            props = dict(r.get("properties", {}))
            props["kind"] = kind
            props["source"] = f"geo.admin.ch {layer} (live)"
            features.append({"type": "Feature", "geometry": geom, "properties": props})
        out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
        print(f"  wrote {len(features)} real {kind} features -> {out_path}")


if __name__ == "__main__":
    main()
