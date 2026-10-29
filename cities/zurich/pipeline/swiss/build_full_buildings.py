"""
TODO-1 / TODO-2: real building coverage with construction year (Baujahr).

Source: the federal GWR (Gebaeude- und Wohnungsregister) via geo.admin.ch's
identify API, layer `ch.bfs.gebaeude_wohnungs_register`. Each result is a
real registered building: EGID, address, construction year (gbauj),
floor count (gastw), footprint area (gebf/garea), heating type, etc.

Caveat (intentional, documented): the GWR layer is address-point geometry,
not cadastral footprint polygons (true footprints require the ~3GB national
swissTLM3D/AV shapefile, impractical to pull for this project). We derive an
approximate square footprint polygon from each point, sized to match the
building's real registered floor area (`gebf`, falling back to `garea`),
so shapes are plausible and proportioned correctly even though they are not
the true parcel outline. `geometry_type` is left in the properties so this
is traceable rather than silently passed off as cadastral-accuracy data.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from geoadmin_tiles import fetch_layer
from area import area_bbox, area_polygon

# The map area (config/area.yaml, see area.py); fetch tiles only near it.
BBOX = area_bbox()
REGION = area_polygon().buffer(0.002)  # ~200 m margin
GWR_RAW_CACHE = Path(__file__).resolve().parents[2] / "data" / "work" / "_gwr_raw_cache.json"

LAYER = "ch.bfs.gebaeude_wohnungs_register"
OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "work" / "building_polygons_baujahr.geojson"

ERA_BUCKETS = [
    (1920, "<1920"),
    (1970, "1920-1969"),
    (2000, "1970-1999"),
    (None, "2000+"),
]


def era_for(year):
    if year is None:
        return "unknown"
    for cutoff, label in ERA_BUCKETS:
        if cutoff is None or year < cutoff:
            return label


def square_footprint(lon, lat, area_m2):
    if not area_m2 or area_m2 <= 0:
        area_m2 = 80  # fallback: typical small footprint
    side_m = math.sqrt(area_m2)
    # local metres-per-degree approximation at this latitude
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    dlat = (side_m / 2) / m_per_deg_lat
    dlon = (side_m / 2) / m_per_deg_lon
    return [[
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]]


def main():
    print("Fetching real GWR building records from geo.admin.ch ...")
    raw = fetch_layer(LAYER, BBOX, geometry_format=None, log_prefix="[buildings] ", region=REGION)
    # enrich_building_properties.py reads the same raw records from this cache
    # instead of fetching them a second time
    GWR_RAW_CACHE.write_text(json.dumps(raw))

    features = []
    for r in raw:
        geom = r.get("geometry") or {}
        lon, lat = geom.get("x"), geom.get("y")
        if lon is None or lat is None:
            continue
        a = r.get("attributes", {})
        baujahr = a.get("gbauj")
        area = a.get("gebf") or a.get("garea")
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": square_footprint(lon, lat, area),
            },
            "properties": {
                "egid": a.get("egid"),
                "address": a.get("strname_deinr"),
                "plz": a.get("plz_plz6"),
                "municipality": a.get("ggdename"),
                "baujahr": baujahr,
                "era": era_for(baujahr),
                "floors": a.get("gastw"),
                "area_m2": area,
                "heating_code": a.get("gwaerzh1"),
                "building_category": a.get("gkat"),
                "building_class": a.get("gklas"),
                "geometry_type": "approximate_square_from_gwr_point",
                "source": "geo.admin.ch ch.bfs.gebaeude_wohnungs_register (live)",
            },
        })

    fc = {"type": "FeatureCollection", "features": features}
    OUT_PATH.write_text(json.dumps(fc))
    print(f"Wrote {len(features)} real buildings -> {OUT_PATH}")

    with_year = sum(1 for f in features if f["properties"]["baujahr"])
    print(f"  {with_year}/{len(features)} have a known construction year")


if __name__ == "__main__":
    main()
