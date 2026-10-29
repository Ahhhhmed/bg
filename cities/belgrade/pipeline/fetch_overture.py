#!/usr/bin/env python3
"""Belgrade's base data from Overture Maps (https://overturemaps.org), one
GeoParquet per theme in cities/belgrade/data/src/ (gitignored, ~60 MB).

Overture is read straight from its public S3 bucket with pyarrow (no DuckDB:
its extensions can't be downloaded from the sandbox), through the HTTPS proxy
when one is set. Only the features whose bbox touches the area's bbox are
read; build_layers.py clips them to the area (the settlement of Belgrade).

    python3 cities/belgrade/pipeline/fetch_overture.py [--release 2026-10-21.0]

What comes from where (Overture's own attribution):
  buildings          OpenStreetMap (ODbL) + Microsoft ML Buildings (ODbL)
  addresses          RGZ address register via OpenAddresses ("rs/countrywide")
  places             Meta, Foursquare, Microsoft, AllThePlaces (CDLA-Permissive 2.0)
  transportation, base (water, land, land_use), divisions: OpenStreetMap (ODbL)
"""
import argparse
import os
import sys
import time
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "src"
BBOX = (20.20, 20.65, 44.67, 44.96)   # the settlement of Belgrade (20.221-20.623, 44.688-44.943) + a margin
# theme, type, columns
TABLES = [
    ("divisions", "division_area", ["id", "names", "subtype", "class", "country", "geometry"]),
    ("buildings", "building", ["id", "geometry", "height", "num_floors", "class", "subtype", "names", "sources", "is_underground", "level"]),
    ("addresses", "address", ["id", "geometry", "number", "street", "postcode", "unit", "sources"]),
    ("places", "place", ["id", "geometry", "names", "basic_category", "taxonomy", "confidence", "websites", "phones", "addresses", "sources"]),
    ("transportation", "segment", ["id", "geometry", "subtype", "class", "subclass", "names", "road_flags", "rail_flags", "level_rules"]),
    ("base", "water", ["id", "geometry", "subtype", "class", "names", "is_intermittent"]),
    ("base", "land", ["id", "geometry", "subtype", "class", "names"]),
    ("base", "land_use", ["id", "geometry", "subtype", "class", "names"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default="2026-10-21.0")
    a = ap.parse_args()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    fs = pafs.S3FileSystem(anonymous=True, region="us-west-2", **({"proxy_options": proxy} if proxy else {}))
    OUT.mkdir(parents=True, exist_ok=True)
    x0, x1, y0, y1 = BBOX
    for theme, typ, cols in TABLES:
        d = ds.dataset(f"overturemaps-us-west-2/release/{a.release}/theme={theme}/type={typ}/", filesystem=fs, format="parquet")
        names = set(d.schema.names)
        missing = [c for c in cols if c not in names]
        if missing:
            print(f"  {theme}/{typ}: no column(s) {missing} in this release, skipped", file=sys.stderr)
        use = [c for c in cols if c in names]
        f = (pc.field("bbox", "xmax") > x0) & (pc.field("bbox", "xmin") < x1) & (pc.field("bbox", "ymax") > y0) & (pc.field("bbox", "ymin") < y1)
        if theme == "divisions":
            f = f & (pc.field("country") == "RS")
        t = time.time()
        tab = d.to_table(columns=use, filter=f)
        pq.write_table(tab, OUT / f"{typ}.parquet")
        print(f"{theme}/{typ}: {tab.num_rows} rows in {time.time() - t:.0f}s", file=sys.stderr)
    (OUT / "RELEASE").write_text(a.release + "\n")


if __name__ == "__main__":
    main()
