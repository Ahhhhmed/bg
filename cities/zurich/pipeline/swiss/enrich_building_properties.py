"""
Enrich the existing building dataset with more public attributes, without
touching geometry:

1. Re-fetch the full raw GWR record per building (same API as before, but
   this time keep every useful field instead of a narrow subset), cached to
   disk so a re-run doesn't need to hit the API again.
2. Aggregate BFE's solar-roof facets (_roof_facets_cache.json, built from
   the national GeoPackage by solar_roofs.py if missing) into per-building
   solar potential metrics.
3. Elevation at each building's centroid from swisstopo's swissALTI3D, as
   the 5 m raster data/work/elevation_5m.tif (build_elevation.py).
   (Until 2026-10-23 this was the nearest point of a ~110 m grid sampled
   from the height API: up to ~80 m off, so not the building's own value.)
4. Sample BAFU road and rail noise at each building (GeoTIFFs).

`--gwr-only`: only redo step 1 from the cached raw GWR records (no network).

`--elevation-only`: only redo step 3 (no network).

`--solar-only`: only redo step 2 on the current building file (every solar_*
value is replaced, nothing else is touched); needs no GWR cache and no
network beyond the GeoPackage download.
"""
import json
import math
import os
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent))
from geoadmin_tiles import FetchIncomplete, fetch_layer
from area import area_bbox, area_polygon
from solar_roofs import facets_cached

# The map area (config/area.yaml, see area.py); fetch tiles only near it.
BBOX = area_bbox()
REGION = area_polygon().buffer(0.002)  # ~200 m margin

_WGS84_TO_LV95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)

ROOT = Path(__file__).resolve().parents[2]
BUILDINGS_PATH = ROOT / "data" / "work" / "building_polygons_baujahr.geojson"
GWR_CACHE = ROOT / "data" / "work" / "_gwr_raw_cache.json"
DEM_PATH = ROOT / "data" / "work" / "elevation_5m.tif"   # LV95, uint16 decimetres, 0 = no data

GWR_LAYER = "ch.bfs.gebaeude_wohnungs_register"


def centroid(geometry):
    """Robust centroid for Polygon or MultiPolygon via shapely (handles both geometry types)."""
    c = shape(geometry).centroid
    return c.x, c.y


def fetch_gwr_raw():
    if GWR_CACHE.exists():
        print(f"Loading cached raw GWR fetch from {GWR_CACHE}...")
        return json.loads(GWR_CACHE.read_text())
    print("Re-fetching full raw GWR records (richer property set this time)...")
    raw = fetch_layer(GWR_LAYER, BBOX, geometry_format=None, log_prefix="[gwr] ", region=REGION)
    GWR_CACHE.write_text(json.dumps(raw))
    print(f"  cached {len(raw)} raw GWR records -> {GWR_CACHE}")
    return raw


# The heating colour mode: what a building heats with, from the
# GWR energy source (genh1), else the heat generator (gwaerzh1). Codes:
# genh 7520 gas, 7530 oil, 754x wood, 7560 electricity, 758x district heating,
# 7501 air / 7510-7513 ground or water (heat pumps), 7570 solar, 7550 waste
# heat, 7598 undetermined, 7599 other, 7500 none; gwaerzh 741x heat pump,
# 745x electric, 746x district heating, 7400 no heat generator.
def heating_class(genh, gwaerzh):
    if genh == 7530:
        return "oil"
    if genh == 7520:
        return "gas"
    if genh in (7501, 7510, 7511, 7512, 7513) or gwaerzh in (7410, 7411):
        return "heatpump"
    if genh in (7580, 7581, 7582) or gwaerzh in (7460, 7461):
        return "district"
    if genh in (7540, 7541, 7542, 7543):
        return "wood"
    if genh == 7560 or gwaerzh in (7450, 7451, 7452):
        return "electric"
    if genh in (7500,) or gwaerzh == 7400:
        return "none"
    if genh is None and gwaerzh is None:
        return None
    return "other"


# GWR keys this script writes, plus the names they had before;
# all are dropped from a building before its GWR values are applied, so no
# value survives under a stale name.
GWR_KEYS_OLD = ("heritage_protection", "civil_defense_shelter", "separate_rooms")


def build_gwr_enrichment(raw):
    by_egid = {}
    for r in raw:
        a = r.get("attributes", {})
        egid = a.get("egid")
        if egid is None:
            continue
        by_egid[str(egid)] = {
            "num_dwellings": a.get("ganzwhg"),
            "building_status": a.get("gstat"),
            # GWR gschutzr: the building has a civil-defence shelter (0 / 1).
            # (Stored as `heritage_protection` until heritage
            # protection isn't a GWR field at all.)
            "civil_defense_shelter": a.get("gschutzr"),
            "demolition_year": a.get("gabbj"),
            "volume_m3": a.get("gvol"),
            # garea is the footprint; gebf the energy reference area (heated
            # floor area). Until 2026-10-23 area_m2 was gebf, else garea.
            "area_m2": a.get("garea"),
            "heated_area_m2": a.get("gebf"),
            "egrid": a.get("egrid"),
            "parcel_number": a.get("lparz"),
            "heating_energy": a.get("genh1"),
            "heating_class": heating_class(a.get("genh1"), a.get("gwaerzh1")),
            "heating_code_2": a.get("genh2"),
            "heating_source_2": a.get("gwaerzh2"),
            # GWR gazzi: separate rooms outside the flats (was misnamed
            # `civil_defense_shelter` until)
            "separate_rooms": a.get("gazzi"),
        }
    return by_egid


# klasse_text (German part) from worst to best; BFE classes 1-5 by kWh/m2/year:
# < 800, 800-1000, 1000-1200, 1200-1400, >= 1400
SOLAR_CLASS_ORDER = ["Gering", "Mittel", "Gut", "Sehr gut", "Top"]


def _orphan_facets_by_location(facets, features):
    """Facets without a usable EGID (none, or one no building of ours has -- the
    BFE data is from 2021, EGIDs get re-registered) assigned to the building
    whose footprint holds the facet's representative point. Strict, like the
    AV matching: only existing buildings without any EGID-matched facet,
    never underground or in-development ones, and a facet inside two
    footprints is dropped. Facets of
    another building's EGID (shared roofs) are never moved. -> {egid: [facet]}
    """
    import shapely
    from shapely.strtree import STRtree

    ours = {str(f["properties"].get("egid")) for f in features}
    has_egid_facets = {str(r["properties"]["gwr_egid"]) for r in facets
                       if r["properties"].get("gwr_egid") is not None}
    orphans = [r for r in facets if r["properties"].get("gwr_egid") is None
               or str(r["properties"]["gwr_egid"]) not in ours]
    # not for buildings in development (GWR status 1001-1003): the 2021 roof
    # in their footprint is the old building they replace
    targets = [f for f in features
               if str(f["properties"].get("egid")) not in has_egid_facets
               and not f["properties"].get("underground")
               and f["properties"].get("building_status") not in (1001, 1002, 1003)
               and f.get("geometry")]
    if not orphans or not targets:
        return {}
    tree = STRtree([shape(f["geometry"]) for f in targets])
    pts = shapely.points([shape(r["geometry"]).representative_point().coords[0] for r in orphans])
    fi, bi = tree.query(pts, predicate="within")
    hits = {}
    for i, j in zip(fi.tolist(), bi.tolist()):
        hits.setdefault(i, []).append(j)
    out = {}
    for i, js in hits.items():
        if len(js) == 1:
            out.setdefault(str(targets[js[0]]["properties"]["egid"]), []).append(orphans[i])
    print(f"  {len(orphans)} facets without a usable EGID; {sum(map(len, out.values()))} of them "
          f"matched by location to {len(out)} buildings without EGID-matched facets")
    return out


def build_solar_enrichment(features=None):
    """{egid: solar_* values}. Facets join by their GWR EGID; with `features`,
    buildings without any get the facets lying in their footprint whose EGID is
    missing or stale (_orphan_facets_by_location, marked solar_match: location)."""
    facets = facets_cached(REGION)
    groups = {}
    for r in facets:
        egid = r.get("properties", {}).get("gwr_egid")
        if egid is not None:
            groups.setdefault(str(egid), []).append(r)
    by_location = _orphan_facets_by_location(facets, features) if features else {}
    groups.update(by_location)

    by_egid = {}
    for key, r in ((k, r) for k, rs in groups.items() for r in rs):
        p = r.get("properties", {})
        agg = by_egid.setdefault(key, {
            "solar_annual_kwh": 0.0,
            "solar_panel_area_m2": 0.0,
            "solar_annual_revenue_chf": 0.0,
            "solar_classes": [],
            "solar_orientation_deg": [],
        })
        agg["solar_annual_kwh"] += p.get("stromertrag") or 0
        agg["solar_panel_area_m2"] += p.get("flaeche_kollektoren") or 0
        agg["solar_annual_revenue_chf"] += p.get("finanzertrag") or 0
        if p.get("klasse_text"):
            agg["solar_classes"].append(p["klasse_text"].split("##")[0])
        if p.get("ausrichtung") is not None:
            agg["solar_orientation_deg"].append(p["ausrichtung"])

    result = {}
    for egid, agg in by_egid.items():
        classes = agg["solar_classes"]
        # the best facet's class (until 2026-10-19 the ranking only knew "Hoch" / "Mittel" /
        # "Gering", so Gut / Sehr gut / Top lost to Mittel or Gering on the same roof)
        best_class = max(classes, key=lambda c: SOLAR_CLASS_ORDER.index(c) if c in SOLAR_CLASS_ORDER else -1) \
            if classes else None
        orientations = agg["solar_orientation_deg"]
        result[egid] = {
            "solar_annual_kwh": round(agg["solar_annual_kwh"], 1),
            "solar_panel_area_m2": round(agg["solar_panel_area_m2"], 1),
            "solar_annual_revenue_chf": round(agg["solar_annual_revenue_chf"], 1),
            "solar_best_class": best_class,
            "solar_avg_orientation_deg": round(sum(orientations) / len(orientations), 1) if orientations else None,
        }
        if egid in by_location:
            result[egid]["solar_match"] = "location"
    return result


def sample_elevation(features):
    """elevation_m (m a.s.l., 0.1 m) at each building's centroid, from the
    5 m swissALTI3D raster; no value outside it."""
    import rasterio
    pts = [_WGS84_TO_LV95.transform(*centroid(f["geometry"])) for f in features]
    hits = 0
    with rasterio.open(DEM_PATH) as src:
        for f, v in zip(features, src.sample(pts)):
            f["properties"].pop("elevation_m", None)
            if int(v[0]) > 0:
                f["properties"]["elevation_m"] = round(int(v[0]) / 10, 1)
                hits += 1
    print(f"  {hits}/{len(features)} buildings got an elevation from {DEM_PATH.name}")


NOISE_LAYERS = {
    "noise_road_day_db": "https://data.geo.admin.ch/ch.bafu.laerm-strassenlaerm_tag/laerm-strassenlaerm_tag/laerm-strassenlaerm_tag_2056.tif",
    "noise_road_night_db": "https://data.geo.admin.ch/ch.bafu.laerm-strassenlaerm_nacht/laerm-strassenlaerm_nacht/laerm-strassenlaerm_nacht_2056.tif",
    "noise_rail_day_db": "https://data.geo.admin.ch/ch.bafu.laerm-bahnlaerm_tag/laerm-bahnlaerm_tag/laerm-bahnlaerm_tag_2056.tif",
    "noise_rail_night_db": "https://data.geo.admin.ch/ch.bafu.laerm-bahnlaerm_nacht/laerm-bahnlaerm_nacht/laerm-bahnlaerm_nacht_2056.tif",
}


def sample_noise(features):
    import rasterio

    lv95_points = [_WGS84_TO_LV95.transform(*centroid(f["geometry"])) for f in features]

    failed = []
    for prop_name, url in NOISE_LAYERS.items():
        print(f"Sampling {prop_name} from real BAFU noise GeoTIFF...")
        vsicurl = "/vsicurl/" + url
        try:
            with rasterio.open(vsicurl) as src:
                nodata = src.nodata
                values = src.sample(lv95_points)
                count = 0
                for f, v in zip(features, values):
                    val = float(v[0])
                    if nodata is not None and val == nodata:
                        continue
                    f["properties"][prop_name] = round(val, 1)
                    count += 1
            print(f"  {count}/{len(features)} buildings got a real {prop_name} value")
        except Exception as e:
            print(f"  ! failed to sample {prop_name}: {e}")
            failed.append(prop_name)
    # a failed GeoTIFF would leave that noise value out for every building
    #: stop before the dataset is written, unless asked not to
    if failed and os.environ.get("BAU_ALLOW_PARTIAL_FETCH") != "1":
        raise FetchIncomplete(f"noise sampling failed for {', '.join(failed)}; re-run, or set "
                              "BAU_ALLOW_PARTIAL_FETCH=1 to write the buildings without those values")


def solar_only(data):
    solar_enrich = build_solar_enrichment(data["features"])
    print(f"Solar enrichment ready for {len(solar_enrich)} buildings")
    hits = 0
    for f in data["features"]:
        p = f["properties"]
        for k in [k for k in p if k.startswith("solar_")]:
            del p[k]
        v = solar_enrich.get(str(p.get("egid")))
        if v:
            p.update(v)
            hits += 1
    print(f"  {hits}/{len(data['features'])} buildings have solar values")
    BUILDINGS_PATH.write_text(json.dumps(data))
    print(f"Wrote {BUILDINGS_PATH}")


def main():
    print("Loading current building dataset...")
    data = json.loads(BUILDINGS_PATH.read_text())
    features = data["features"]
    print(f"  {len(features)} buildings")
    if "--solar-only" in sys.argv:
        return solar_only(data)
    if "--elevation-only" in sys.argv:
        sample_elevation(features)
        BUILDINGS_PATH.write_text(json.dumps(data))
        return
    if "--gwr-only" in sys.argv:
        gwr_enrich = build_gwr_enrichment(fetch_gwr_raw())
        hits = 0
        for f in features:
            for k in GWR_KEYS_OLD:
                f["properties"].pop(k, None)
            v = gwr_enrich.get(str(f["properties"].get("egid")))
            if v:
                f["properties"].update(v)
                hits += 1
        print(f"  {hits}/{len(features)} buildings updated from the GWR cache")
        BUILDINGS_PATH.write_text(json.dumps(data))
        return

    raw_gwr = fetch_gwr_raw()
    gwr_enrich = build_gwr_enrichment(raw_gwr)
    print(f"GWR enrichment ready for {len(gwr_enrich)} buildings")

    solar_enrich = build_solar_enrichment(data["features"])
    print(f"Solar enrichment ready for {len(solar_enrich)} buildings")

    print("Merging enrichment into building properties...")
    for i, f in enumerate(features):
        egid = f["properties"].get("egid")
        if egid is not None:
            egid = str(egid)
            for k in GWR_KEYS_OLD:
                f["properties"].pop(k, None)
            if egid in gwr_enrich:
                f["properties"].update(gwr_enrich[egid])
            for k in [k for k in f["properties"] if k.startswith("solar_")]:
                del f["properties"][k]  # no stale values from an earlier run
            if egid in solar_enrich:
                f["properties"].update(solar_enrich[egid])
        if i % 20000 == 0:
            print(f"  ...{i}/{len(features)} buildings enriched")

    sample_elevation(features)
    sample_noise(features)

    BUILDINGS_PATH.write_text(json.dumps(data))
    print(f"Wrote enriched dataset -> {BUILDINGS_PATH}")


if __name__ == "__main__":
    main()
