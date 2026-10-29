"""
TODO-3: real roads, rail & footpaths.

Source: swissTLM3D via geo.admin.ch identify API (same approach as
build_full_buildings.py) -- real MultiLineString geometry + attributes
(street name, road class, etc.), not placeholder sketch data.
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

OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "work" / "zurich_roads_rail.geojson"

LAYERS = {
    "ch.swisstopo.swisstlm3d-strassen": "road",
    "ch.swisstopo.swisstlm3d-eisenbahnnetz": "rail",
}


def main():
    features = []
    for layer, kind in LAYERS.items():
        print(f"Fetching real {kind} network from {layer} ...")
        raw = fetch_layer(layer, BBOX, geometry_format="geojson", log_prefix=f"[{kind}] ", region=REGION)
        for r in raw:
            geom = r.get("geometry")
            if not geom:
                continue
            props = dict(r.get("properties", {}))
            props["kind"] = kind
            props["source"] = f"geo.admin.ch {layer} (live)"
            features.append({"type": "Feature", "geometry": geom, "properties": props})

    fc = {"type": "FeatureCollection", "features": features}
    OUT_PATH.write_text(json.dumps(fc))
    print(f"Wrote {len(features)} real road/rail segments -> {OUT_PATH}")


if __name__ == "__main__":
    main()
