#!/usr/bin/env python3
"""
The sources behind the building card and the stop card, with their data
dates (C-05: every card says where its facts come from, so it's clear what
to refresh). Writes data/work/card_sources.json, which the build serves at
/data/card_sources.json and web/map.js / web/stops.js show in the card foot.

A source's date is its download cache's date (the newest of its files), so a
re-fetch moves it; without the cache (a fresh clone) the date already in the
JSON stays, else the date given here (the documented fetch, SOURCES.md).
Run after any re-fetch of a building or stop source:

    python3 cities/zurich/pipeline/card_sources.py

The place cards have their own table (places_sources.json, build_places.py).
"""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "data" / "work"
OUT = LAYERS / "card_sources.json"

# card -> code -> (label {de, en}, url, cache files / dirs under data/layers, fallback date)
SOURCES = {
    "building": {
        "gwr": ({"de": "BFS, Gebäude- und Wohnungsregister", "en": "FSO, buildings register (GWR)"},
                "https://www.housing-stat.ch", ["_gwr_raw_cache.json"], "2026-10-13"),
        "av": ({"de": "Amtliche Vermessung, Gebäude", "en": "Cadastral survey, buildings"},
               "https://geodienste.ch/services/av", ["_av_buildings_cache.json", "_av_projected_cache.json"], "2026-10-13"),
        "av_parcels": ({"de": "Amtliche Vermessung, Liegenschaften", "en": "Cadastral survey, plots"},
                       "https://geodienste.ch/services/av", ["_av_parcels_cache.json"], "2026-10-18"),
        "alti3d": ({"de": "swisstopo, swissALTI3D (Höhe)", "en": "swisstopo, swissALTI3D (elevation)"},
                   "https://www.swisstopo.admin.ch/de/hoehenmodell-swissalti3d", ["_dem_cache"], "2026-10-17"),
        "solar": ({"de": "BFE, Sonnendach", "en": "SFOE, solar roofs"},
                  "https://www.uvek-gis.admin.ch/BFE/sonnendach/", ["_solar_cache"], "2026-10-19"),
        "noise": ({"de": "BAFU, Strassen- und Bahnlärm (Modell)", "en": "FOEN, road and rail noise (model)"},
                  "https://map.geo.admin.ch/?layers=ch.bafu.laerm-strassenlaerm_tag", [], "2026-10-19"),
        "canton": ({"de": "Kanton Zürich, Zonen, ES, Gefahren, Fluglärm, belastete Standorte",
                    "en": "Canton of Zürich, zones, ES, hazards, aircraft noise, contaminated sites"},
                   "https://maps.zh.ch/wfs/OGDZHWFS", ["_ground_zoning_cache.json", "_ground_contaminated_cache.json"], "2026-10-19"),
        "runoff": ({"de": "BAFU, Oberflächenabfluss", "en": "FOEN, surface runoff"},
                   "https://data.geo.admin.ch/browser/index.html#/collections/ch.bafu.gefaehrdungskarte-oberflaechenabfluss",
                   ["_runoff_cache"], "2026-10-19"),
        "oev": ({"de": "ARE, ÖV-Güteklassen", "en": "ARE, public transport quality grades"},
                "https://data.geo.admin.ch/browser/index.html#/collections/ch.are.gueteklassen_oev",
                ["_transit_cache/OeV_Gueteklassen_ARE.gpkg"], "2026-10-19"),
        "bav_stops": ({"de": "BAV, Haltestellen", "en": "FOT, stops"},
                      "https://data.geo.admin.ch/browser/index.html#/collections/ch.bav.haltestellen-oev",
                      ["_transit_cache/haltestellen-oev_2056_de.csv.zip"], "2026-10-19"),
        # commute_hb_min: build_walk.py from the stops' timetable profiles (build_timetable.py)
        "commute": ({"de": "Fahrplan (GTFS, geOps), Zeit zum HB geschätzt", "en": "Timetable (GTFS, geOps), time to HB estimated"},
                    "https://gtfs.geops.ch", ["_gtfs_cache/gtfs_complete.zip"], "2026-10-22"),
        # the walking network of build_walk.py; the places are on their own cards
        "walk": ({"de": "swisstopo swissTLM3D, Strassen und Wege (Fusswege berechnet)",
                  "en": "swisstopo swissTLM3D, roads and paths (walks computed)"},
                 "https://www.swisstopo.admin.ch/de/landschaftsmodell-swisstlm3d", [], "2026-10-19"),
    },
    "stop": {
        "bav_stops": ({"de": "BAV, Haltestellen", "en": "FOT, stops"},
                      "https://data.geo.admin.ch/browser/index.html#/collections/ch.bav.haltestellen-oev",
                      ["_transit_cache/haltestellen-oev_2056_de.csv.zip"], "2026-10-19"),
        "gtfs": ({"de": "Fahrplan (GTFS, geOps)", "en": "Timetable (GTFS, geOps)"},
                 "https://gtfs.geops.ch", ["_gtfs_cache/gtfs_complete.zip"], "2026-10-22"),
    },
}


def cache_date(names):
    dates = []
    for n in names:
        p = LAYERS / n
        if p.exists():
            dates.append(max([p.stat().st_mtime] + [q.stat().st_mtime for q in p.rglob("*")] if p.is_dir() else [p.stat().st_mtime]))
    return datetime.date.fromtimestamp(max(dates)).isoformat() if dates else None


def main():
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    out = {}
    for card, sources in SOURCES.items():
        out[card] = {}
        for code, (label, url, files, fallback) in sources.items():
            date = cache_date(files) or (old.get(card, {}).get(code) or {}).get("date") or fallback
            out[card][code] = {**label, "url": url, "date": date}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    for card, s in out.items():
        print(f"  {card}: " + ", ".join(f"{c} {v['date']}" for c, v in s.items()))


if __name__ == "__main__":
    main()
