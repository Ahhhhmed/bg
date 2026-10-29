#!/usr/bin/env python3
"""The search profile's table: every housing building's values
for the lenses, so the map can count what each criterion leaves over the whole
area (the tiles only hold what is in view).

Reads cities/<city>/data/layers/buildings.geojson (the city\'s pipeline
writes it), writes cities/<city>/data/profile_table.json,
served at /data/profile_table.json:

    {"n": 60064, "cols": {"<prop>": [value per building, ...], ...}}

Housing = GWR category 1010-1040 (the owner, 2026-10-25: the profile counts
homes). One column per property a criterion reads (PROFILE_PROPS, the same
names as in the tiles); string columns are dictionary-coded
({"dict": [...], "codes": [index or -1]}) to keep the file small. Public
register / model values only, no addresses or ids. Run it after anything that
rewrites the buildings (build_walk.py, the ground themes, a re-fetch), like
the tiles.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument("city"); CITY = _ap.parse_args().city
SRC = ROOT / "cities" / CITY / "data/layers/buildings.geojson"
OUT = ROOT / "cities" / CITY / "data/profile_table.json"
HOUSING = {1010, 1020, 1030, 1040}
WALK = ["kg", "kita", "sch", "stop", "sup", "post", "doc", "pha", "play", "bath", "er"]   # WALK_KINDS in web/layers.js
NUMERIC = ["baujahr", "commute_hb_min", *[f"w_{k}" for k in WALK], "noise_road_day_db", "noise_road_night_db",
           "noise_rail_day_db", "noise_rail_night_db", "floors", "num_dwellings", "aircraft_db", "civil_defense_shelter"]
TEXT = ["heating_class", "solar_best_class", "oev_class", "hazard", "runoff", "contaminated", "zone", "es"]


def num(v):
    if v is None or v == "":
        return None
    f = float(v)
    return int(f) if f == int(f) else round(f, 1)


def main():
    if not SRC.exists():
        sys.exit(f"{SRC} missing: run the city's pipeline first (README)")
    feats = json.loads(SRC.read_text())["features"]
    # housing: GWR category 1010-1040 (Zürich), else OSM's residential types or unknown use (`housing` != 0; Belgrade)
    home = lambda p: p.get("building_category") in HOUSING if "building_category" in p else p.get("housing", 1) != 0
    rows = [f["properties"] for f in feats if home(f["properties"])]
    cols = {k: [num(p.get(k)) for p in rows] for k in NUMERIC}
    for k in TEXT:
        vals = [p.get(k) for p in rows]
        d = sorted({v for v in vals if v not in (None, "")})
        at = {v: i for i, v in enumerate(d)}
        cols[k] = {"dict": d, "codes": [at.get(v, -1) for v in vals]}
    # a column without a single value (a fact this city doesn't have) is left out: the map reads it as "no value"
    cols = {k: v for k, v in cols.items() if (any(x is not None for x in v) if isinstance(v, list) else v["dict"])}
    OUT.write_text(json.dumps({"n": len(rows), "cols": cols}, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} housing buildings, {len(cols)} columns, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
