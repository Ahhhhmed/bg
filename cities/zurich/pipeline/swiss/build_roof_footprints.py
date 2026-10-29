"""
Replace raster-traced building shapes with REAL vector footprints where
possible, from swisstopo/BFE's solar-roof-suitability layer
(ch.bfe.solarenergie-eignung-daecher; the national GeoPackage, see solar_roofs.py). That layer is computed per roof
*facet* (one polygon per planar roof segment), but each facet carries the
building's real `gwr_egid` -- the same EGID join key as our GWR data. So
unioning all facets sharing an EGID gives the real roof footprint, straight
from authoritative government vector data. No raster, no text labels, no
risk of a street/city-name label being mistaken for a building.

Priority per building:
  1. Unioned solar-roof-facet footprint (real vector, exact EGID join) --
     best available, and immune to the "ZÜRICH" label bug since it was
     never raster-derived.
  2. The raster-traced shape from the previous pass IF it was matched to
     this exact EGID (geometry_type == extracted_from_raster_tiles) --
     still raster-derived, but matching to a *known real coordinate* makes
     stray text landing there extremely unlikely.
  3. The original square approximation.

The previous pass's "unmatched" / "duplicate" bonus shapes (no EGID at
all) are dropped entirely -- that category is exactly where the text-label
artifacts concentrated, since real GWR points essentially never sit near
map label text by chance.
"""
import json
import sys
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon
from solar_roofs import facets_cached

# The map area (config/area.yaml, see area.py); facets touching it (+200 m).
REGION = area_polygon().buffer(0.002)  # ~200 m margin

ROOT = Path(__file__).resolve().parents[2]
BUILDINGS_PATH = ROOT / "data" / "work" / "building_polygons_baujahr.geojson"
SQUARE_BACKUP = ROOT / "data" / "work" / "building_polygons_baujahr.square_approx.geojson.bak"

LAYER = "ch.bfe.solarenergie-eignung-daecher"
# --skip-facets: don't load the facet layer; reuse the previous run's
# solar shapes / values from the current building file, by EGID
SKIP_FACETS = "--skip-facets" in sys.argv


def main():
    print("Loading prior building dataset (GWR squares + raster-traced shapes)...")
    current = json.loads(BUILDINGS_PATH.read_text())["features"]
    square_base = json.loads(SQUARE_BACKUP.read_text())["features"]  # one entry per real GWR egid

    by_egid_square = {f["properties"]["egid"]: f for f in square_base}
    print(f"  {len(by_egid_square)} real GWR buildings (authoritative square baseline)")

    raster_matched = {}
    prior_solar = {}  # egid -> (geometry, solar_* properties), used with --skip-facets
    for f in current:
        p = f["properties"]
        if p.get("geometry_type") == "extracted_from_raster_tiles" and p.get("egid") is not None:
            raster_matched[p["egid"]] = f["geometry"]
        if p.get("egid") is not None:
            solar_props = {k: v for k, v in p.items() if k.startswith("solar_")}
            geom = f["geometry"] if p.get("geometry_type") == "real_roof_footprint_solar_vector" else None
            if solar_props or geom:
                prior_solar[p["egid"]] = (geom, solar_props)
    print(f"  {len(raster_matched)} have a prior raster-traced shape (EGID-matched)")

    if SKIP_FACETS:
        # carry the previous run's solar shapes and solar_* values over by EGID
        print(f"--skip-facets: not loading {LAYER}; carrying over prior solar data for "
              f"{len(prior_solar)} buildings by EGID")
        raw = []
    else:
        # The facets come from the national GeoPackage (solar_roofs.py), not
        # the identify API: the layer is too dense to tile through identify
        # (~370k facets in 2 h and not done for the area).
        raw = facets_cached(REGION)
    print(f"Grouping {len(raw)} facets by building EGID...")

    facets_by_egid = {}
    for r in raw:
        egid = r.get("properties", {}).get("gwr_egid")
        geom = r.get("geometry")
        if egid is None or not geom:
            continue
        facets_by_egid.setdefault(str(egid), []).append(geom)

    print(f"  {len(facets_by_egid)} buildings have real roof-facet geometry")

    print("Unioning facets per building into real footprint polygons...")
    solar_footprints = {}
    failed = 0
    for egid, geoms in facets_by_egid.items():
        try:
            shapes = [shape(g).buffer(0) for g in geoms]
            merged = unary_union(shapes)
            if merged.is_empty:
                continue
            solar_footprints[egid] = mapping(merged)
        except Exception:
            failed += 1
    print(f"  {len(solar_footprints)} real footprints built ({failed} failed to union)")

    print("Assembling final building set...")
    tier_counts = {"solar_real": 0, "raster_matched": 0, "square": 0}
    final_features = []
    for egid, square_f in by_egid_square.items():
        props = dict(square_f["properties"])
        if egid in solar_footprints:
            geom = solar_footprints[egid]
            geom_type = geom["type"]
            if geom_type not in ("Polygon", "MultiPolygon"):
                geom = None
            if geom is not None:
                props["geometry_type"] = "real_roof_footprint_solar_vector"
                props["source"] = "data.geo.admin.ch ch.bfe.solarenergie-eignung-daecher (GeoPackage), unioned per EGID"
                final_features.append({"type": "Feature", "geometry": geom, "properties": props})
                tier_counts["solar_real"] += 1
                continue
        if SKIP_FACETS and egid in prior_solar:
            geom, solar_props = prior_solar[egid]
            props.update(solar_props)
            if geom is not None:
                props["geometry_type"] = "real_roof_footprint_solar_vector"
                props["source"] = "geo.admin.ch ch.bfe.solarenergie-eignung-daecher (earlier run), unioned per EGID"
                final_features.append({"type": "Feature", "geometry": geom, "properties": props})
                tier_counts["solar_real"] += 1
                continue
        if egid in raster_matched:
            props["geometry_type"] = "extracted_from_raster_tiles"
            final_features.append({"type": "Feature", "geometry": raster_matched[egid], "properties": props})
            tier_counts["raster_matched"] += 1
            continue
        final_features.append({**square_f, "properties": props})
        tier_counts["square"] += 1

    print("Final building geometry sources:")
    for k, v in tier_counts.items():
        print(f"  {k}: {v}")

    BUILDINGS_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": final_features}))
    print(f"Wrote {len(final_features)} buildings -> {BUILDINGS_PATH}")
    print(f"\nBuildings still using the square approximation: {tier_counts['square']}")


if __name__ == "__main__":
    main()
