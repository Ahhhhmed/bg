#!/usr/bin/env python3
"""The last step of Zürich's pipeline: turns the Swiss scripts' outputs in
cities/zurich/data/work/ (the Swiss scripts' names: building_polygons_baujahr.geojson,
zurich_roads_rail.geojson, transit_stops.geojson, ...) into the city's layers
in the shared names the tiles and the web app read. Every layer is cut to the
city (BFS 261), with its 12 Kreise as the inner borders.

    python3 cities/zurich/pipeline/assemble.py [--from cities/zurich/data/work]

Writes cities/zurich/data/layers/*.geojson (gitignored; the tiles are built
from them by shared/build_tiles.sh), plus area_labels.json, the card and place
source tables, the place index, and the stop profiles of the stops in the city.
"""
import argparse
import json
import shutil
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.prepared import prep

HERE = Path(__file__).resolve().parent
CITY = HERE.parent
OUT = CITY / "data" / "layers"
DATA = CITY / "data"


def load(p):
    return json.loads(Path(p).read_text())


def dump(p, feats):
    Path(p).write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"  {Path(p).name}: {len(feats)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=str(CITY / "data" / "work"))
    a = ap.parse_args()
    S = Path(a.src)
    OUT.mkdir(parents=True, exist_ok=True)

    muni = [f for f in load(S / "municipalities.geojson")["features"] if f["properties"].get("bfs") == 261]
    city = shape(muni[0]["geometry"])
    inside, edge = prep(city), prep(city.buffer(0.0002))   # ~15 m: lines on the city's own border

    def clip(feats, keep_point=False):
        out = []
        for f in feats:
            g = shape(f["geometry"])
            if keep_point:
                if inside.contains(g.representative_point()):
                    out.append(f)
                continue
            if not inside.intersects(g):
                continue
            if inside.contains(g):
                out.append(f)
                continue
            c = g.intersection(city)
            if not c.is_empty:
                out.append({"type": "Feature", "properties": f["properties"], "geometry": mapping(c)})
        return out

    b = [f for f in load(S / "building_polygons_baujahr.geojson")["features"] if f["properties"].get("municipality") == "Zürich"]
    dump(OUT / "buildings.geojson", b)
    dump(OUT / "roads_rail.geojson", clip(load(S / "zurich_roads_rail.geojson")["features"]))
    dump(OUT / "water.geojson", clip(load(S / "zurich_water.geojson")["features"]))
    dump(OUT / "greenery.geojson", clip(load(S / "zurich_greenery.geojson")["features"]))
    dump(OUT / "parcels.geojson", clip(load(S / "zurich_parcels.geojson")["features"], keep_point=True))
    dump(OUT / "municipalities.geojson", muni + load(S / "kreise.geojson")["features"])
    # borders: the Kreise inside, the city's own border (the lake cut out)
    borders = [f for f in load(S / "area_borders.geojson")["features"]
               if f["properties"].get("level") == "kreis" or (f["properties"].get("level") == "municipality" and edge.intersects(shape(f["geometry"])))]
    borders = [f if f["properties"]["level"] == "kreis" else
               {"type": "Feature", "properties": f["properties"], "geometry": mapping(shape(f["geometry"]).intersection(city.buffer(0.0002)))}
               for f in borders]
    dump(OUT / "borders.geojson", [f for f in borders if f["geometry"]["coordinates"]])
    for p in sorted(S.glob("places_*.geojson")):
        dump(OUT / p.name, clip(load(p)["features"], keep_point=True))
    stops = clip(load(S / "transit_stops.geojson")["features"], keep_point=True)
    dump(OUT / "stops.geojson", stops)
    for src, layer in [("oev_gueteklassen", "oev_classes"), ("zurich_hazard", "hazard"), ("zurich_runoff", "runoff"),
                       ("zurich_aircraft_noise", "aircraft_noise"), ("zurich_contaminated", "contaminated"),
                       ("zurich_zoning", "zoning"), ("zurich_noise_es", "noise_es")]:
        dump(OUT / f"ground_{layer}.geojson", clip(load(S / f"{src}.geojson")["features"]))

    lab = load(S / "area_labels.json")
    x0, y0, x1, y1 = city.bounds
    lab = {**lab, "bbox": [round(x0, 5), round(y0, 5), round(x1, 5), round(y1, 5)],
           "labels": [l for l in lab["labels"] if l["level"] == "kreis" or l["name"] == "Zürich"]}
    (OUT / "area_labels.json").write_text(json.dumps(lab, ensure_ascii=False))
    for n in ["card_sources.json", "places_sources.json", "places_index.json"]:
        shutil.copy(S / n, DATA / n)
    sp = DATA / "stops"
    shutil.rmtree(sp, ignore_errors=True)
    sp.mkdir()
    nrs = {str(f["properties"]["nr"]) for f in stops}
    n = 0
    for f in (S / "stop_profiles").glob("*.json"):
        if f.stem in nrs:
            shutil.copy(f, sp / f.name)
            n += 1
    print(f"  stops/: {n} profiles")


if __name__ == "__main__":
    main()
