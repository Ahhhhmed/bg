"""
Fetch the City of Zürich's 12 district (Kreis) borders.

Source: Stadt Zürich open data, dataset "Stadtkreise"
(https://data.stadt-zuerich.ch/dataset/geo_stadtkreise), via the city's WFS
on www.ogd.stadt-zuerich.ch (layer `adm_stadtkreise_a`, GeoJSON, WGS84).
Replaces the hand-made quartiere.geojson on the map.

Writes data/work/kreise.geojson (one feature per Kreis: name "Kreis N",
kreis N, level "kreis"). clip_to_area.py turns it into border lines and
labels.

It tolerates format drift: a FeatureCollection or a zip containing one,
coordinates in WGS84, LV95 (EPSG:2056) or LV03 (EPSG:21781), and the Kreis
number from whichever property holds 1-12 (today: `bezeichnung` "Kreis 6").
It prints what it found and fails unless it finds exactly the 12 Kreise.
"""
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

LAYERS = Path(__file__).resolve().parents[2] / "data" / "work"
OUT = LAYERS / "kreise.geojson"
# The dataset's "GeoJSON download" links on www.stadt-zuerich.ch return an
# HTML page (2026-10-13); the city's WFS serves the same polygons as GeoJSON.
URLS = [
    "https://www.ogd.stadt-zuerich.ch/wfs/geoportal/Stadtkreise?SERVICE=WFS&VERSION=1.1.0"
    "&REQUEST=GetFeature&TYPENAME=adm_stadtkreise_a"
    "&OUTPUTFORMAT=application/vnd.geo%2Bjson&SRSNAME=EPSG:4326",
]


def download():
    errors = []
    for url in URLS:
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                body = resp.read()
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue
        if body[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                name = next(n for n in z.namelist() if n.lower().endswith((".json", ".geojson")))
                body = z.read(name)
        try:
            data = json.loads(body)
        except ValueError:
            errors.append(f"{url}: not JSON (starts {body[:80]!r})")
            continue
        if data.get("type") == "FeatureCollection":
            print(f"downloaded {len(data['features'])} features from {url}")
            return data
        errors.append(f"{url}: JSON but not a FeatureCollection (keys {list(data)[:5]})")
    sys.exit("could not download the Kreise:\n  " + "\n  ".join(errors))


def to_wgs84(fc):
    sample = shape(fc["features"][0]["geometry"]).representative_point()
    if abs(sample.x) <= 180:
        return lambda g: g
    epsg = 2056 if sample.x > 2_000_000 else 21781
    print(f"coordinates look like EPSG:{epsg}, reprojecting")
    t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return lambda g: transform(t.transform, g)


def kreis_number(props):
    for key, value in props.items():
        if re.search(r"(knr|kreis|nummer|name|bez)", key, re.I):
            m = re.search(r"\b(1[0-2]|[1-9])\b", str(value))
            if m:
                return int(m.group(1))
    return None


def main():
    fc = download()
    print("first feature's properties:", fc["features"][0]["properties"])
    reproject = to_wgs84(fc)
    by_kreis = {}
    for f in fc["features"]:
        n = kreis_number(f["properties"])
        if n is None:
            sys.exit(f"no Kreis number found in properties {f['properties']}")
        by_kreis.setdefault(n, []).append(reproject(shape(f["geometry"])))
    if sorted(by_kreis) != list(range(1, 13)):
        sys.exit(f"expected Kreise 1-12, found {sorted(by_kreis)}")
    features = []
    for n in range(1, 13):
        g = unary_union(by_kreis[n]).buffer(0)
        features.append({"type": "Feature", "geometry": mapping(g),
                         "properties": {"name": f"Kreis {n}", "kreis": n, "level": "kreis"}})
        print(f"  Kreis {n:>2}: {len(by_kreis[n])} part(s)")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"wrote 12 Kreise -> {OUT}")

    print("now re-run clip_to_area.py to add Kreis borders and labels, then rebuild the tiles")

if __name__ == "__main__":
    main()
