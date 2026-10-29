"""
Place layers for the map's "Orte" tier (C-09): points drawn as monochrome
icons, one source-layer each, `kind` = the icon. One function per layer
below; each returns its points, which are then clipped to the area and
written to data/work/places_<layer>.geojson.

  python3 cities/zurich/pipeline/swiss/build_places.py            # every layer
  python3 cities/zurich/pipeline/swiss/build_places.py schools    # just these
  python3 cities/zurich/pipeline/swiss/build_places.py --refresh  # re-download (else cached)

Then shared/build_tiles.sh zurich (the `places` pass reads every places_*.geojson).

Rules (owner, 2026-10-23, C-05): every fact on a point is one its source
states -- a register field or an OSM tag, or an OSM outline the point lies
inside. Nothing is guessed from names or from "the nearest thing around";
a fact no source states is left out, and the card says "unbekannt". Every
point lists its sources (`srcs`, codes into SOURCES below); their names,
links and data dates go to data/work/places_sources.json, which the card
shows, so it is clear what to refresh when something changes.

Point properties: name (as the source spells it; may be missing), kind,
info (a qualifier the source states), srcs, bfs, muni, addr, web, tel, op,
the category's own facts (see each builder). No nearest stop: the owner
doesn't reach these places by public transport (2026-10-23).

Sources, per layer (details and counts in data/work/SOURCES.md):
  schools: City of Zürich registers for the city (Schulanlagen
    WFS: kindergartens, Volksschulen, special schools; Kindertagesstaette
    WFS: Kitas); the Canton of Zürich's open WFS for Mittelschulen /
    Berufsfachschulen everywhere; OpenStreetMap (Overpass, overpass.osm.ch)
    for kindergartens, schools and childcare in the other 12 municipalities,
    by their OSM tag (amenity=kindergarten / school / childcare).
  hospitals: the Canton of Zürich's hospital lists (acute,
    psychiatry, rehabilitation spreadsheets), in the area and up to NEAR_M
    outside it, placed at their GWR building by config/hospital_sites.yaml;
    `er` = the acute list's general basic package (BP), which the canton's
    requirements tie to an emergency station.
  health: OSM amenity=doctors (minus stated specialists) and
    amenity=pharmacy.
  shops: OSM shop=supermarket (chain = the `brand` tag) and
    amenity=post_office.
  baths: lake and river bathing places from the Canton of
    Zürich's `ms:ogd-1670_giszhpub_gs_badeplatz_p`; pools: the City of
    Zürich's Freibäder / Hallenbäder (Sport WFS) and, outside the city, OSM
    swimming facilities by tag.
  playgrounds: the City of Zürich's public playgrounds
    (POI_oeffentliche_Spielplaetze); OSM leisure=playground open to the
    public in the other municipalities.
Downloads are cached in data/work/_places_cache/ (gitignored); a cache
file's date is the data date shown on the cards.
"""
import datetime
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon, municipality_features  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
CACHE = LAYERS / "_places_cache"
SOURCES_OUT = LAYERS / "places_sources.json"
ZURICH_BFS = 261
CITY_WFS = "https://www.ogd.stadt-zuerich.ch/wfs/geoportal/{service}?SERVICE=WFS&VERSION=1.1.0" \
           "&REQUEST=GetFeature&TYPENAME={typename}&outputFormat=GeoJSON&srsName=EPSG:4326"
CANTON_WFS = "https://maps.zh.ch/wfs/OGDZHWFS?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature" \
             "&TYPENAMES={typename}&OUTPUTFORMAT=geojson&SRSNAME=EPSG:4326"
OVERPASS = "https://overpass.osm.ch/api/interpreter"
REFRESH = "--refresh" in sys.argv
M2 = 75500.0 * 111320.0   # m2 per deg2 at Zürich's latitude (sizes on the card only)

# every source a fact can come from: its name on the card, where to get it,
# and the cache files whose date is its data date
SOURCES = {
    "city_schools": ({"de": "Stadt Zürich, Schulanlagen", "en": "City of Zürich, schools"},
                     "https://data.stadt-zuerich.ch/dataset/geo_schulanlagen", ["city_poi_kindergarten_view.json"]),
    "city_kitas": ({"de": "Stadt Zürich, Kindertagesstätten", "en": "City of Zürich, day care"},
                   "https://data.stadt-zuerich.ch/dataset/geo_kindertagesstaette", ["city_poi_kindertagesstaette_view.json"]),
    "canton_sekii": ({"de": "Kanton Zürich, Schulen Sek II", "en": "Canton of Zürich, upper-secondary schools"},
                     "https://maps.zh.ch/wfs/OGDZHWFS", ["canton_ms_ogd-0600_giszhpub_mba_sekii_schulen_p.json"]),
    "canton_spitalliste": ({"de": "Kanton Zürich, Spitallisten 2023 (Akutsomatik, Psychiatrie, Rehabilitation)",
                            "en": "Canton of Zürich, hospital lists 2023 (acute, psychiatry, rehabilitation)"},
                           "https://www.zh.ch/de/gesundheit/spitaeler-kliniken/spitalplanung.html", ["canton_spitalliste_*.xlsx"]),
    "city_spital": ({"de": "Stadt Zürich, Spitäler (Adresse)", "en": "City of Zürich, hospitals (address)"},
                    "https://www.ogd.stadt-zuerich.ch/wfs/geoportal/Spital", ["city_poi_spital_view.json"]),
    "gwr": ({"de": "BFS, Gebäude- und Wohnungsregister (Lage)", "en": "FSO, buildings register (position)"},
            "https://www.housing-stat.ch", ["gwr_*.json"]),
    "city_sport": ({"de": "Stadt Zürich, Sport (Bäder)", "en": "City of Zürich, sport (pools)"},
                   "https://data.stadt-zuerich.ch/dataset/geo_sport", ["city_poi_freibad_view.json"]),
    "canton_baths": ({"de": "Kanton Zürich, Badeplätze", "en": "Canton of Zürich, bathing places"},
                     "https://maps.zh.ch/wfs/OGDZHWFS", ["canton_ms_ogd-1670_giszhpub_gs_badeplatz_p.json"]),
    "city_playgrounds": ({"de": "Stadt Zürich, öffentliche Spielplätze", "en": "City of Zürich, public playgrounds"},
                         "https://data.stadt-zuerich.ch/dataset/geo_poi_oeffentliche_spielplaetze", ["city_poi_spielplatz_view.json"]),
    "osm": ({"de": "OpenStreetMap", "en": "OpenStreetMap"}, "https://www.openstreetmap.org/copyright", None),
    "osm_geom": ({"de": "OpenStreetMap, Flächen", "en": "OpenStreetMap, outlines"}, "https://www.openstreetmap.org/copyright", None),
}


# ---------- downloads (cached) ----------

def _get(url, cache_name, data=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    if data is not None:
        # an Overpass query: the cache file is tied to the query itself, so a
        # changed query never reuses an old answer
        stem, ext = cache_name.rsplit(".", 1)
        cache_name = f"{stem}.{hashlib.sha1(data).hexdigest()[:10]}.{ext}"
    path = CACHE / cache_name
    if path.exists() and not REFRESH:
        return json.loads(path.read_text())
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "bg-map (open data)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read()
            out = json.loads(body)
            path.write_text(json.dumps(out))
            return out
        except Exception as e:  # noqa: BLE001 -- retried, then raised
            if attempt == 3:
                raise RuntimeError(f"download failed: {url[:120]}: {e}") from e
            # Overpass answers "too many requests" in HTML when queried in a row
            time.sleep(20 * (attempt + 1) if data is not None else 2 ** (attempt + 1))


def city_wfs(service, typename):
    return _get(CITY_WFS.format(service=service, typename=typename), f"city_{typename}.json")["features"]


def canton_wfs(typename):
    return _get(CANTON_WFS.format(typename=typename), f"canton_{typename.replace(':', '_')}.json")["features"]


def _bbox(margin_m):
    w, s, e, n = area_polygon().bounds
    return (f"({s - margin_m / 111320:.4f},{w - margin_m / 75500:.4f},"
            f"{n + margin_m / 111320:.4f},{e + margin_m / 75500:.4f})")


def overpass(name, selectors, margin_m=0):
    """OSM elements matching any of `selectors` (Overpass QL filters such as
    '["amenity"="school"]') in the area's bbox (grown by `margin_m`), as
    (lon, lat, tags, ref); ways and relations at their centre."""
    bbox = _bbox(margin_m)
    q = "[out:json][timeout:180];(" + "".join(f"nwr{sel}{bbox};" for sel in selectors) + ");out center tags;"
    d = _get(OVERPASS, f"osm_{name}.json", data=urllib.parse.urlencode({"data": q}).encode())
    out = []
    for el in d["elements"]:
        c = el.get("center") or el
        if "lon" in c:
            out.append((c["lon"], c["lat"], el.get("tags", {}), f"{el['type']}/{el['id']}"))
    return out


def overpass_geom(name, query_body, margin_m=300):
    """(shape, tags) for OSM elements with geometry: closed ways and
    multipolygon relations as polygons, other ways as lines, nodes as points."""
    q = "[out:json][timeout:240];(" + query_body.replace("{bbox}", _bbox(margin_m)) + ");out geom tags;"
    d = _get(OVERPASS, f"osm_{name}_geom.json", data=urllib.parse.urlencode({"data": q}).encode())
    out = []
    for el in d["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "node":
            out.append((Point(el["lon"], el["lat"]), tags))
        elif el["type"] == "way" and el.get("geometry"):
            pts = [(g["lon"], g["lat"]) for g in el["geometry"]]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                poly = Polygon(pts)
                out.append((poly if poly.is_valid else poly.buffer(0), tags))
            elif len(pts) >= 2:
                out.append((LineString(pts), tags))
        elif el["type"] == "relation":
            lines = [LineString([(g["lon"], g["lat"]) for g in m["geometry"]])
                     for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
            polys = list(polygonize(unary_union(lines))) if lines else []
            if polys:
                out.append((unary_union(polys), tags))
    return out


# ---------- area ----------

class Area:
    def __init__(self):
        self.shape = area_polygon()
        self.poly = prep(self.shape)
        feats = municipality_features()
        self.geoms = [shape(f["geometry"]) for f in feats]
        self.bfs = [f["properties"]["bfs"] for f in feats]
        self.tree = STRtree(self.geoms)

    def municipality(self, lon, lat):
        """BFS number of the municipality the point lies in, None outside the area."""
        pt = Point(lon, lat)
        if not self.poly.contains(pt):
            return None
        for i in self.tree.query(pt):
            if self.geoms[i].contains(pt):
                return self.bfs[i]
        return None

    def near(self, lon, lat, metres):
        """True if the point is within `metres` of the area (outside it)."""
        return self.shape.distance(Point(lon, lat)) * 75500 <= metres


def dedupe(points, metres=60):
    """Drops a point of the same kind and the same (non-empty) name within
    `metres` of one kept before it: OSM sometimes has a place as a node and as
    its grounds. Points without a name are never merged."""
    kept, out = {}, []
    for p in points:
        x, y = p["lon"] * 75500, p["lat"] * 111320
        name = p.get("name") or ""
        if name and any((x - qx) ** 2 + (y - qy) ** 2 < metres ** 2 for qx, qy in kept.get((p["kind"], name), [])):
            continue
        kept.setdefault((p["kind"], name), []).append((x, y))
        out.append(p)
    return out


class Outlines:
    """Polygons with an index: the smallest one a point lies in (no "nearest")."""
    def __init__(self, items):
        self.items = [(g, t) for g, t in items if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 0]
        self.tree = STRtree([g for g, _ in self.items]) if self.items else None

    def at(self, lon, lat):
        if not self.tree:
            return None
        pt = Point(lon, lat)
        hits = [self.items[i] for i in self.tree.query(pt) if self.items[i][0].contains(pt)]
        return min(hits, key=lambda h: h[0].area) if hits else None

    def all_at(self, lon, lat):
        """Every polygon the point lies in."""
        if not self.tree:
            return []
        pt = Point(lon, lat)
        return [self.items[i] for i in self.tree.query(pt) if self.items[i][0].contains(pt)]


def m2(g):
    return int(round(g.area * M2, -1))


# ---------- what the card shows ----------

def _short(v, n=110):
    v = re.sub(r"<[^>]+>", " ", str(v or "")).strip()
    v = re.sub(r"\s+", " ", v)
    return v if len(v) <= n else v[:n - 1].rstrip() + "…"


def city_extra(p):
    """addr / web / tel from a City of Zürich POI record."""
    town = f"{p.get('plz') or ''} {p.get('ort') or ''}".strip()
    return {"addr": _short(", ".join(x for x in [p.get("adresse") or "", town] if x)),
            "web": p.get("www") or "", "tel": (p.get("tel") or "").strip()}


def osm_extra(tags):
    """addr / web / tel / op from OSM tags (addr:* or contact:*)."""
    g = lambda k: tags.get(f"addr:{k}") or tags.get(f"contact:{k}") or ""
    street = " ".join(x for x in [g("street"), g("housenumber")] if x)
    town = " ".join(x for x in [g("postcode"), g("city")] if x)
    return {"addr": ", ".join(x for x in [street, town] if x),
            "web": tags.get("website") or tags.get("contact:website") or "",
            "tel": tags.get("phone") or tags.get("contact:phone") or "",
            "op": tags.get("operator") if tags.get("operator") and tags.get("operator") != tags.get("name") else "",
            "wheelchair": tags.get("wheelchair") or ""}


def osm_ages(tags):
    a, b = tags.get("min_age"), tags.get("max_age")
    return f"{a or 0} – {b}" if b else (f"{a}+" if a else "")


def osm_public(tags):
    """1 / 0 from OSM operator:type, else nothing (unknown)."""
    t = tags.get("operator:type")
    return 0 if t == "private" else 1 if t in ("public", "government", "community", "municipal") else None


def osm_stage(tags):
    """School stages an OSM element states: isced:level 1 = primary, 2 =
    lower secondary (Sek), or school:CH = primarschule / oberstufe."""
    isced = re.split(r"[;,\- ]+", tags.get("isced:level") or "")
    ch = (tags.get("school:CH") or "").lower()
    out = []
    if "1" in isced or "primar" in ch:
        out.append("prim")
    if "2" in isced or "oberstufe" in ch or "sekundar" in ch:
        out.append("sek")
    return ",".join(out)


# ---------- layers ----------

def build_schools(area):
    """Kindergartens, Volksschulen, Mittel- / Berufsfachschulen and Kitas."""
    pts, notes = [], {}

    def add(lon, lat, **p):
        bfs = area.municipality(lon, lat)
        if bfs is not None:
            pts.append({"lon": lon, "lat": lat, "bfs": bfs, **p})

    # City of Zürich: the Schulamt's registers of its own (public) schools
    for typename, kind, info in [("poi_kindergarten_view", "kindergarten", ""),
                                 ("poi_volksschule_view", "school", "Volksschule"),
                                 ("poi_sonderschule_view", "school", "Sonderschule")]:
        for f in city_wfs("Schulanlagen", typename):
            lon, lat = f["geometry"]["coordinates"][:2]
            p = f["properties"]
            add(lon, lat, name=p.get("name") or "", kind=kind, info=info, srcs=["city_schools"], public=1,
                **city_extra(p), district=p.get("schulkreis") or "", unit=p.get("einheit") or "")
    # City of Zürich: licensed Kitas (public and private); "subsidised" is the
    # register's own remark, otherwise unknown
    for f in city_wfs("Kindertagesstaette", "poi_kindertagesstaette_view"):
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f["properties"]
        sub = 1 if "subventionierte plätze" in (p.get("bemerkung") or "").lower() else None
        add(lon, lat, name=p.get("name") or "", kind="kita", info="", srcs=["city_kitas"], **city_extra(p), subsidised=sub)

    # Canton: Mittelschulen and Berufsfachschulen, everywhere
    for f in canton_wfs("ms:ogd-0600_giszhpub_mba_sekii_schulen_p"):
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f["properties"]
        street = " ".join(x for x in [p.get("schule_strasse") or "", str(p.get("schule_haus_nr") or "")] if x)
        town = f"{p.get('schule_plz') or ''} {p.get('schule_ort') or ''}".strip()
        add(lon, lat, name=p.get("schule_name") or "", kind="upper", info=p.get("schule_typ") or "",
            srcs=["canton_sekii"], addr=", ".join(x for x in [street, town] if x), web=p.get("web") or "",
            tel=(p.get("kontakt_tel") or "").strip(), students=p.get("anzahl_sus"),
            site=p.get("standort_typ") or "")

    # OpenStreetMap for the other municipalities, kind by the OSM tag
    osm = overpass("schools", ['["amenity"="kindergarten"]', '["amenity"="school"]', '["amenity"="childcare"]'])
    skipped = {"city": 0, "not_general_school": 0, "upper_secondary": 0}
    kind_of = {"kindergarten": "kindergarten", "school": "school", "childcare": "kita"}
    for lon, lat, tags, ref in osm:
        bfs = area.municipality(lon, lat)
        if bfs is None:
            continue
        if bfs == ZURICH_BFS:
            skipped["city"] += 1
            continue
        if tags.get("amenity") == "school" and tags.get("school") in ("language", "music", "dance", "driving", "art"):
            skipped["not_general_school"] += 1
            continue
        if tags.get("amenity") == "school" and re.search(r"(^|[;,\- ])[345]($|[;,\- ])", tags.get("isced:level") or ""):
            skipped["upper_secondary"] += 1   # the canton's list has the Mittel- / Berufsfachschulen
            continue
        add(lon, lat, name=tags.get("name") or "", kind=kind_of[tags["amenity"]], info="", srcs=["osm"],
            **osm_extra(tags), ages=osm_ages(tags), grades=tags.get("grades") or "",
            public=osm_public(tags), stage=osm_stage(tags) if tags.get("amenity") == "school" else "")
    # an OSM school on the same grounds as a canton school (an OSM school
    # outline holds both points) is that canton school: the canton's point stays
    grounds = Outlines(overpass_geom("schools", 'way["amenity"~"^(school|kindergarten|childcare)$"]{bbox};'
                                                'relation["amenity"~"^(school|kindergarten|childcare)$"]{bbox};'))
    canton_grounds = {id(g) for p in pts if p["kind"] == "upper" for g, _ in grounds.all_at(p["lon"], p["lat"])}
    keep = []
    for p in pts:
        hits = grounds.all_at(p["lon"], p["lat"]) if p["srcs"] == ["osm"] and p["kind"] == "school" else []
        if any(id(g) in canton_grounds for g, _ in hits):
            skipped["same_grounds_as_canton_school"] = skipped.get("same_grounds_as_canton_school", 0) + 1
            continue
        keep.append(p)
    notes["osm_skipped"] = skipped
    return dedupe(keep), notes


NEAR_M = 3000


def _get_bytes(url, cache_name):
    """A binary download (the canton's spreadsheets), cached like _get."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / cache_name
    if not path.exists() or REFRESH:
        req = urllib.request.Request(url, headers={"User-Agent": "bg-map (open data)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path


# The Canton of Zürich's hospital lists (Zürcher Spitalliste 2023), from
# https://www.zh.ch/de/gesundheit/spitaeler-kliniken/spitalplanung.html. A new
# version gets a new file name there: update the URL and re-run.
SPL = "https://www.zh.ch/content/dam/zhweb/bilder-dokumente/themen/gesundheit/gesundheitsversorgung/" \
      "spitaeler_kliniken/spitalplanung/"
HOSPITAL_LISTS = {   # list: (url, row with the hospital names, first hospital column)
    "acute": (SPL + "spitalliste-akut-ab-2026/2_Z%C3%BCrcher%20Spitalliste%202023%20Akutsomatik%202026.4.xlsx", 5, 3),
    "psych": (SPL + "spitalliste-psychiatrie-ab-2026/3_Z%C3%BCrcher%20Spitalliste%202023%20Psychiatrie%202026.1.xlsx", 4, 2),
    "rehab": (SPL + "reha-spitalliste-ab-2025/Zuercher_Spitalliste_2023_Rehabilitation_2026.1.xlsx", 4, 6),
}
GWR_FIND = "https://api3.geo.admin.ch/rest/services/ech/MapServer/find?layer=ch.bfs.gebaeude_wohnungs_register" \
           "&searchField={field}&searchText={text}&contains=false&returnGeometry=true&sr=4326"
CITY_SPITAL_URL = "https://www.ogd.stadt-zuerich.ch/wfs/geoportal/Spital"


def _list_name(cell):
    """("name", "operator") from a list's column head, e.g. " Spital Uster (c)\n (Spital
    Uster AG)" -> ("Spital Uster", "Spital Uster AG"); footnote letters dropped."""
    s = re.sub(r"\s+", " ", str(cell)).strip()
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", s)
    name, op = (m.group(1), m.group(2)) if m else (s, "")
    name = re.sub(r"\s*\([a-z]\)", "", name)
    return re.sub(r"\s+[a-z]$", "", name).strip(), op


def hospital_lists():
    """{name: {"op", "lists": [...], "bp": bool, "bpe": bool, "groups": n, "areas": [...]}}
    from the canton's spreadsheets: which lists a hospital is on and, from the
    acute list (cells say "ausgewählt"), its basic package (BP = general, which
    requires an emergency station; BPE = elective, none required) and the
    service groups (Leistungsgruppen) it holds, by service area."""
    import openpyxl
    out = {}
    for lst, (url, head_row, first) in HOSPITAL_LISTS.items():
        ws = openpyxl.load_workbook(_get_bytes(url, f"canton_spitalliste_{lst}.xlsx"),
                                    read_only=True, data_only=True).worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        head = rows[head_row - 1]
        cols = [(i, *_list_name(c)) for i, c in enumerate(head) if i >= first and c and str(c).strip()]
        if not cols:
            raise SystemExit(f"hospital list {lst}: no hospital names in row {head_row} -- the file's layout changed")
        for i, name, op in cols:
            h = out.setdefault(name, {"op": op, "lists": [], "bp": False, "bpe": False, "groups": 0, "areas": []})
            h["lists"].append(lst)
            h["op"] = h["op"] or op
        if lst != "acute":
            continue   # psychiatry / rehab mark their service groups by cell colour only: list membership is all we read
        area = ""
        for r in rows[head_row:]:
            if r[0]:
                area = re.sub(r"\s+", " ", str(r[0])).strip()
            code = str(r[1] or "").split(" ")[0].strip()
            if not code:
                continue
            for i, name, _ in cols:
                if i >= len(r) or r[i] != "ausgewählt":
                    continue
                h = out[name]
                if code == "BP":
                    h["bp"] = True
                elif code == "BPE":
                    h["bpe"] = True
                else:
                    h["groups"] += 1
                    if area not in h["areas"]:
                        h["areas"].append(area)
    return out


def gwr_find(field, text):
    q = urllib.parse.quote(str(text))
    return _get(GWR_FIND.format(field=field, text=q), f"gwr_{field}_{hashlib.sha1(str(text).encode()).hexdigest()[:10]}.json")["results"]


def _osm_centre(ref):
    typ, oid = ref.split("/")
    q = f"[out:json][timeout:60];{typ}({oid});out center tags;"
    d = _get(OVERPASS, f"osm_hospital_site_{typ}{oid}.json", data=urllib.parse.urlencode({"data": q}).encode())
    el = d["elements"][0]
    c = el.get("center") or el
    return c["lon"], c["lat"]


def _av_building_at(lon, lat):
    """The EGID of the cadastral building the point lies in (containment only)."""
    path = LAYERS / "building_polygons_baujahr.geojson"
    if not path.exists():
        raise SystemExit("hospital sites with osm_point need data/work/building_polygons_baujahr.geojson "
                         "(bash cities/zurich/pipeline/refresh.sh)")
    pt = Point(lon, lat)
    for f in json.loads(path.read_text())["features"]:
        if f["properties"].get("geometry_type") != "cadastral_footprint_av" or not f["properties"].get("egid"):
            continue
        g = shape(f["geometry"])
        if g.bounds[0] <= lon <= g.bounds[2] and g.bounds[1] <= lat <= g.bounds[3] and g.contains(pt):
            return int(f["properties"]["egid"])
    return None


def check_site_sources(sites):
    """Warnings for site-table addresses their cited source no longer states
    (an OSM element's addr:* or the city register's adresse), so a refresh
    shows what to re-check."""
    city = {f["properties"].get("poi_id"): f["properties"] for f in city_wfs("Spital", "poi_spital_view")}
    refs = [s["source"][4:] for s in sites.values() if str(s.get("source", "")).startswith("osm:")]
    q = "[out:json][timeout:120];(" + "".join(f"{r.split('/')[0]}({r.split('/')[1]});" for r in refs) + ");out tags;"
    osm = {f"{e['type']}/{e['id']}": e.get("tags", {}) for e in
           _get(OVERPASS, "osm_hospital_sites.json", data=urllib.parse.urlencode({"data": q}).encode())["elements"]}
    warn = []
    for name, s in sites.items():
        kind, _, ref = str(s.get("source", "")).partition(":")
        if kind == "city":
            stated = (city.get(ref) or {}).get("adresse") or ""
        elif kind == "osm":
            t = osm.get(ref, {})
            stated = f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip()
        else:
            continue
        if not stated.startswith(s["address"]):
            warn.append(f"{name}: {s['source']} states {stated!r}, table has {s['address']!r}")
    return warn


def build_hospitals(area):
    """The canton's listed hospitals (acute, psychiatry, rehabilitation), placed
    by config/hospital_sites.yaml at their GWR building; `er` = the canton's
    general basic package (BP), which requires an emergency station."""
    import yaml
    sites = yaml.safe_load((ROOT / "config" / "hospital_sites.yaml").read_text())
    listed = hospital_lists()
    missing = sorted(set(listed) - set(sites))
    if missing:
        raise SystemExit("hospitals on the canton's lists without an entry in config/hospital_sites.yaml:\n  "
                         + "\n  ".join(missing))
    outlines = Outlines(overpass_geom("hospitals", 'way["amenity"="hospital"]{bbox};relation["amenity"="hospital"]{bbox};'
                                                   'way["healthcare"="hospital"]{bbox};relation["healthcare"="hospital"]{bbox};',
                                      margin_m=NEAR_M))
    by_egid, notes = {}, {"outside": [], "beyond_3km": [], "unresolved": []}
    for w in check_site_sources(sites):
        print("  WARNING site source:", w)
    for name, h in listed.items():
        site = sites[name]
        if "outside" in site:
            notes["outside"].append(name)
            continue
        if "unresolved" in site:
            notes["unresolved"].append(name)
            continue
        srcs = ["canton_spitalliste", "gwr"]
        if "osm_point" in site:
            c = _osm_centre(site["osm_point"])
            if area.municipality(*c) is None:
                # outside the area our cadastral buildings stop, so an OSM point
                # can't be tied to a building (containment only, C-05): not placed
                notes["outside"].append(name)
                continue
            egid = _av_building_at(*c)
            if egid is None:
                raise SystemExit(f"{name}: OSM {site['osm_point']} lies in no cadastral building")
            hits = gwr_find("egid", egid)
            srcs.append("osm")
        else:
            hits = [r for r in gwr_find("strname_deinr", site.get("gwr") or site["address"])
                    if r["attributes"]["ggdename"] == site["town"]]
            kind, _, ref = site["source"].partition(":")
            srcs.append("city_spital" if kind == "city" else "osm")
        hits = list({r["attributes"]["egid"]: r for r in hits}.values())   # one GWR row per entrance
        if len(hits) != 1:
            raise SystemExit(f"{name}: {len(hits)} GWR buildings at {site.get('address') or site.get('osm_point')}, "
                             f"{site['town']} -- fix config/hospital_sites.yaml")
        a, g = hits[0]["attributes"], hits[0]["geometry"]
        lon, lat = g["x"], g["y"]
        bfs = area.municipality(lon, lat)
        if bfs is None:
            if not area.near(lon, lat, NEAR_M):
                notes["beyond_3km"].append(name)
                continue
            bfs = 0
        p = by_egid.get(a["egid"])
        if p is None:
            op, short = h["op"], name
            if not op and " - " in name:   # psychiatry sites: "operator - site"
                op, short = name.split(" - ", 1)
            p = by_egid[a["egid"]] = {
                "lon": lon, "lat": lat, "name": short, "kind": "hospital", "info": "", "srcs": [], "bfs": bfs,
                "town": a["ggdename"], "egid": a["egid"], "op": op, "lists": [], "groups": None, "areas": [],
                "addr": f"{a['strname_deinr']}, {a['dplz4']} {a['ggdename']}"}
            hit = outlines.at(lon, lat)
            if hit:
                p["area_m2"] = m2(hit[0])
                tags = hit[1]
                p["web"] = tags.get("website") or tags.get("contact:website") or ""
                p["tel"] = tags.get("phone") or tags.get("contact:phone") or ""
                p["beds"] = tags.get("beds") or ""
                srcs.append("osm_geom")
        p["srcs"] = list(dict.fromkeys(p["srcs"] + srcs))
        p["lists"] += [x for x in h["lists"] if x not in p["lists"]]
        if "acute" in h["lists"]:   # service groups and basic package: acute list only
            p["groups"] = (p["groups"] or 0) + h["groups"]
            p["areas"] += [x for x in h["areas"] if x not in p["areas"]]
            p["er_mandate"] = 1 if h["bp"] else 0   # 1: BP (emergency station required); 0: not in the mandate
        if h["bp"]:
            p["kind"], p["hub"] = "er", True
    pts = list(by_egid.values())
    for p in pts:
        p["lists"] = ",".join(p["lists"])
        p["areas"] = ";".join(p["areas"])
    notes = {k: len(v) if k == "outside" else v for k, v in notes.items()}
    notes["er"] = sorted(p["name"] for p in pts if p["kind"] == "er")
    return pts, notes


# specialities that are not a first doctor (OSM healthcare:speciality)
GP_SPECIALITIES = {"general", "internal", "paediatrics", "family_medicine", "general_practice"}


def build_health(area):
    """Doctors' practices (minus those OSM states are specialists) and pharmacies."""
    osm = overpass("health", ['["amenity"="doctors"]', '["amenity"="pharmacy"]'])
    pts, dropped = [], 0
    for lon, lat, tags, ref in osm:
        bfs = area.municipality(lon, lat)
        if bfs is None:
            continue
        if tags.get("amenity") == "pharmacy":
            pts.append({"lon": lon, "lat": lat, "name": tags.get("name") or "", "kind": "pharmacy", "info": "",
                        "srcs": ["osm"], "bfs": bfs, **osm_extra(tags), "brand": tags.get("brand") or ""})
            continue
        spec = [s for s in (tags.get("healthcare:speciality") or "").split(";") if s]
        if spec and not set(spec) & GP_SPECIALITIES:
            dropped += 1   # a stated specialist: out of scope
            continue
        pts.append({"lon": lon, "lat": lat, "name": tags.get("name") or "", "kind": "doctor", "info": "",
                    "srcs": ["osm"], "bfs": bfs, **osm_extra(tags), "spec": ",".join(spec)})
    return dedupe(pts, metres=25), {"specialists_dropped": dropped}


DAY = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def parse_hours(s):
    """{day: [(open, close), ...]} for simple OSM opening_hours like
    "Mo-Fr 08:00-20:00; Sa 08:00-18:00; Su off"; None for anything else
    (public-holiday rules, months, comments, ...), so nothing is guessed."""
    if not s:
        return None
    week = {}
    for rule in [r.strip() for r in s.split(";") if r.strip()]:
        m = re.fullmatch(r"((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?(?:,(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*)"
                         r"\s+(off|closed|\d\d:\d\d-\d\d:\d\d(?:,\d\d:\d\d-\d\d:\d\d)*)", rule)
        if not m:
            return None
        days = []
        for part in m.group(1).split(","):
            a, _, b = part.partition("-")
            i, j = DAY.index(a), DAY.index(b or a)
            days += DAY[i:j + 1] if i <= j else DAY[i:] + DAY[:j + 1]
        spans = [] if m.group(2) in ("off", "closed") else [tuple(x.split("-")) for x in m.group(2).split(",")]
        for d in days:
            week[d] = spans
    return week


def build_shops(area):
    """Supermarkets (chain = the OSM brand) and post offices."""
    osm = overpass("shops", ['["shop"="supermarket"]', '["amenity"="post_office"]'])
    pts = []
    for lon, lat, tags, ref in osm:
        bfs = area.municipality(lon, lat)
        if bfs is None:
            continue
        hours = tags.get("opening_hours") or ""
        p = {"lon": lon, "lat": lat, "name": tags.get("name") or "", "info": "", "srcs": ["osm"], "bfs": bfs,
             **osm_extra(tags), "hours": _short(hours, 120)}
        week = parse_hours(hours)
        if week is not None:
            closes = [c for spans in week.values() for _, c in spans]
            if closes:
                p["close_max"] = max(closes)
            p["sunday"] = 1 if week.get("Su") else 0 if "Su" in week else None
        if tags.get("shop") == "supermarket":
            p.update(kind="supermarket", brand=tags.get("brand") or "",
                     cash=1 if tags.get("cash_withdrawal") == "yes" else 0 if tags.get("cash_withdrawal") == "no" else None,
                     organic=tags.get("organic") or "")
        else:
            p.update(kind="post", post_type=tags.get("post_office:type") or tags.get("post_office") or "",
                     brand=tags.get("brand") or "")
        pts.append(p)
    return dedupe(pts, metres=40), {}


def build_baths(area):
    """Lake / river bathing places (canton), outdoor and indoor pools (city, OSM)."""
    pts = []
    # the canton's list of bathing places: art = "<id> - <name> - <street> - <plz> - <town>"
    for f in canton_wfs("ms:ogd-1670_giszhpub_gs_badeplatz_p"):
        lon, lat = f["geometry"]["coordinates"][:2]
        parts = [x.strip() for x in (f["properties"].get("art") or "").split(" - ")]
        if len(parts) < 5:
            continue
        name, street, plz, town = parts[1], parts[2], parts[3], parts[4]
        # some lakeside points lie in the lake, where the municipal polygon
        # stops at the shore: in the area by the canton's own town and PLZ
        bfs = area.municipality(lon, lat)
        if bfs is None:
            bfs = next((b for b, n in TOWN_BFS.items() if n == town), None)
        if bfs is None:
            continue
        pts.append({"lon": lon, "lat": lat, "bfs": bfs, "name": name, "kind": "lakebath", "info": "",
                    "srcs": ["canton_baths"], "water": (f["properties"].get("gewaesser") or "").strip(),
                    "addr": ", ".join(x for x in [street, f"{plz} {town}".strip()] if x), "town": town})
    # City of Zürich: its Freibäder and Hallenbäder (two registers)
    for typename, info in [("poi_freibad_view", "Freibad"), ("poi_hallenbad_view", "Hallenbad")]:
        for f in city_wfs("Sport", typename):
            lon, lat = f["geometry"]["coordinates"][:2]
            bfs = area.municipality(lon, lat)
            if bfs is not None:
                pts.append({"lon": lon, "lat": lat, "bfs": bfs, "name": f["properties"].get("name") or "", "kind": "pool",
                            "info": info, "srcs": ["city_sport"], **city_extra(f["properties"])})
    # OSM pools outside the city, by tag (indoor / outdoor only when OSM says)
    osm = overpass("baths", ['["leisure"="sports_centre"]["sport"~"swimming"]', '["leisure"="water_park"]',
                             '["amenity"="public_bath"]'])
    for lon, lat, tags, ref in osm:
        bfs = area.municipality(lon, lat)
        if bfs is None or bfs == ZURICH_BFS or tags.get("access") in ("private", "no"):
            continue
        indoor = tags.get("indoor") or tags.get("covered")
        pts.append({"lon": lon, "lat": lat, "bfs": bfs, "name": tags.get("name") or "", "kind": "pool",
                    "info": "Hallenbad" if indoor == "yes" else "Freibad" if indoor == "no" else "",
                    "srcs": ["osm"], **osm_extra(tags)})
    return dedupe(pts, metres=120), {}


def build_playgrounds(area):
    """Public playgrounds."""
    pts = []
    for f in city_wfs("POI_oeffentliche_Spielplaetze", "poi_spielplatz_view"):
        lon, lat = f["geometry"]["coordinates"][:2]
        bfs = area.municipality(lon, lat)
        if bfs is not None:
            p = f["properties"]
            pts.append({"lon": lon, "lat": lat, "bfs": bfs, "name": p.get("name") or "", "kind": "playground", "info": "",
                        "srcs": ["city_playgrounds"],
                        **{k: v for k, v in city_extra(p).items() if k != "tel"},   # the parks office's number for all
                        "ages": _short(p.get("eignung"), 30), "equip": _short(p.get("geraete"), 160),
                        "elements": _short(p.get("elemente")), "special": _short(p.get("besonderes")),
                        "setting": p.get("typ") or ""})
    osm = overpass("playgrounds", ['["leisure"="playground"]'])
    private = 0
    for lon, lat, tags, ref in osm:
        bfs = area.municipality(lon, lat)
        if bfs is None or bfs == ZURICH_BFS:
            continue
        if tags.get("access") in ("private", "customers", "permit", "no"):
            private += 1   # housing estates' and restaurants' playgrounds
            continue
        pts.append({"lon": lon, "lat": lat, "bfs": bfs, "name": tags.get("name") or "", "kind": "playground", "info": "",
                    "srcs": ["osm"], **osm_extra(tags), "ages": osm_ages(tags), "surface": tags.get("surface") or ""})
    return dedupe(pts, metres=40), {"private_skipped": private}


BUILDERS = {"schools": build_schools, "hospitals": build_hospitals, "health": build_health, "shops": build_shops,
            "baths": build_baths, "playgrounds": build_playgrounds}


# ---------- more from OSM outlines: only for a point inside one ----------

PLAY_KEYS = ["swing", "basketswing", "slide", "climbingframe", "structure", "climbingwall", "sandpit", "seesaw",
             "springy", "roundabout", "basketrotator", "spinner", "spinning_disc", "trampoline", "zipwire",
             "balancebeam", "playhouse", "tunnel_tube", "water", "pump", "water_channel", "hammock",
             "rope_traverse", "wobble_bridge", "horizontal_bar", "stepping_stone", "activitypanel", "ladder", "platform"]


def enrich_playgrounds(pts):
    feats = overpass_geom("playgrounds", 'way["leisure"="playground"]{bbox};relation["leisure"="playground"]{bbox};'
                                         'nwr["playground"]{bbox};way["leisure"="park"]{bbox};relation["leisure"="park"]{bbox};')
    grounds = Outlines([(g, t) for g, t in feats if t.get("leisure") == "playground"])
    parks = Outlines([(g, t) for g, t in feats if t.get("leisure") == "park"])
    gear = [(g, t) for g, t in feats if t.get("playground") and t.get("leisure") != "playground"]
    gear_tree = STRtree([g for g, _ in gear])
    n_sized = n_gear = n_park = 0
    for p in pts:
        hit = grounds.at(p["lon"], p["lat"])
        if hit:
            poly, tags = hit
            p["area_m2"] = m2(poly)
            counts = {}
            for i in gear_tree.query(poly):
                g, t = gear[i]
                if poly.intersects(g):
                    for v in t["playground"].split(";"):
                        if v.strip() in PLAY_KEYS:
                            counts[v.strip()] = counts.get(v.strip(), 0) + 1
            if counts:
                p["gear"] = ",".join(f"{k}:{counts[k]}" for k in PLAY_KEYS if k in counts)
                n_gear += 1
            n_sized += 1
            if not p.get("surface") and tags.get("surface"):
                p["surface"] = tags["surface"]
            p["srcs"] = p["srcs"] + ["osm_geom"]
        park = parks.at(p["lon"], p["lat"])
        if park and park[1].get("name"):
            p["park"], p["park_m2"] = park[1]["name"], m2(park[0])
            n_park += 1
            if "osm_geom" not in p["srcs"]:
                p["srcs"] = p["srcs"] + ["osm_geom"]
    return {"with_size": n_sized, "with_equipment_counts": n_gear, "in_a_park": n_park}


def enrich_baths(pts):
    feats = overpass_geom("baths", 'way["leisure"~"^(sports_centre|water_park|bathing_place|swimming_area|beach_resort)$"]{bbox};'
                                   'relation["leisure"~"^(sports_centre|water_park|bathing_place|beach_resort)$"]{bbox};'
                                   'way["amenity"="public_bath"]{bbox};nwr["leisure"="swimming_pool"]{bbox};'
                                   'nwr["attraction"="water_slide"]{bbox};nwr["sport"="diving"]{bbox};'
                                   'nwr["leisure"="pitch"]["sport"~"beachvolleyball|volleyball"]{bbox};'
                                   'nwr["amenity"~"^(restaurant|cafe|fast_food|kiosk)$"]{bbox};nwr["shop"="kiosk"]{bbox};'
                                   'nwr["leisure"="sauna"]{bbox};way["leisure"="playground"]{bbox};')
    sites = Outlines([(g, t) for g, t in feats if t.get("leisure") in ("sports_centre", "water_park", "bathing_place",
                                                                        "swimming_area", "beach_resort") or t.get("amenity") == "public_bath"])
    n = 0
    for p in pts:
        hit = sites.at(p["lon"], p["lat"])
        if not hit:
            continue
        poly, _ = hit
        n += 1
        p["area_m2"] = m2(poly)
        p["srcs"] = p["srcs"] + ["osm_geom"]
        inner = [(g, t) for g, t in feats if poly.intersects(g)]
        p["pools"] = sum(1 for g, t in inner if t.get("leisure") == "swimming_pool" and g.geom_type != "Point")
        has = []
        if any(t.get("attraction") == "water_slide" for _, t in inner): has.append("slide")
        if any(t.get("sport") == "diving" for _, t in inner): has.append("diving")
        if any("volleyball" in (t.get("sport") or "") for _, t in inner): has.append("volleyball")
        if any(t.get("leisure") == "playground" for _, t in inner): has.append("playground")
        if any(t.get("leisure") == "sauna" for _, t in inner): has.append("sauna")
        if any(t.get("amenity") in ("restaurant", "cafe", "fast_food", "kiosk") or t.get("shop") == "kiosk" for _, t in inner): has.append("food")
        p["has"] = ",".join(has)   # what OSM maps inside; empty = none mapped
    return {"with_site": n}


def enrich_schools(pts):
    feats = overpass_geom("schools", 'way["amenity"~"^(school|kindergarten|childcare)$"]{bbox};'
                                     'relation["amenity"~"^(school|kindergarten|childcare)$"]{bbox};')
    grounds = Outlines(feats)
    n_area = n_stage = 0
    for p in pts:
        hit = grounds.at(p["lon"], p["lat"])
        if not hit:
            continue
        poly, tags = hit
        p["srcs"] = p["srcs"] + ["osm_geom"]
        if p["kind"] in ("school", "upper"):
            p["area_m2"] = m2(poly)
            n_area += 1
        if p["kind"] == "school" and not p.get("stage") and tags.get("amenity") == "school":
            st = osm_stage(tags)
            if st:
                p["stage"] = st
                n_stage += 1
        if p.get("public") is None and osm_public(tags) is not None:
            p["public"] = osm_public(tags)
    return {"with_grounds": n_area, "stage_from_outline": n_stage,
            "with_stage": sum(1 for p in pts if p.get("stage"))}


def enrich_shops(pts):
    feats = overpass_geom("shops", 'way["shop"="supermarket"]{bbox};', margin_m=0)
    sites = Outlines(feats)
    n = 0
    for p in pts:
        if p["kind"] != "supermarket":
            continue
        hit = sites.at(p["lon"], p["lat"])
        if hit:
            p["area_m2"] = m2(hit[0])
            p["srcs"] = p["srcs"] + ["osm_geom"]
            n += 1
    return {"with_floor_area": n}


ENRICH = {"schools": enrich_schools, "shops": enrich_shops, "baths": enrich_baths, "playgrounds": enrich_playgrounds}


def place_id(layer, p):
    """A short id for a place, the same on every run while the place's layer,
    kind, name and position (1 m) stay: build_walk.py stores it on the
    buildings as their nearest place, the card opens that place's card."""
    key = f"{layer}|{p['kind']}|{p.get('name') or ''}|{p['lon']:.5f}|{p['lat']:.5f}"
    return layer[0] + hashlib.sha1(key.encode()).hexdigest()[:7]


def set_municipality(pts):
    """`muni`: the municipality's name (or, outside the area, the source's town)."""
    names = {f["properties"]["bfs"]: f["properties"]["name"] for f in municipality_features()}
    for p in pts:
        p["muni"] = p.pop("town", None) or names.get(p["bfs"], "")


def _date(path):
    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None


def source_table(layer):
    """{code: {de, en, url, date}} for one layer; the date of an OSM source is
    the date this layer's Overpass result was fetched."""
    out = {}
    for code, (label, url, files) in SOURCES.items():
        if code == "osm":
            files = [p.name for p in CACHE.glob(f"osm_{layer}.*.json")]
        elif code == "osm_geom":
            files = [p.name for p in CACHE.glob(f"osm_{layer}_geom.*.json")]
        files = [q.name for f in files for q in (CACHE.glob(f) if "*" in f else [CACHE / f])]
        dates = [d for d in (_date(CACHE / f) for f in files) if d]
        date = min(dates) if dates else None
        out[code] = {**label, "url": url, "date": date}
    return out


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(BUILDERS)
    area = Area()
    table = json.loads(SOURCES_OUT.read_text()) if SOURCES_OUT.exists() else {}
    for name in names:
        pts, notes = BUILDERS[name](area)
        if name in ENRICH:
            notes["enriched"] = ENRICH[name](pts)
        set_municipality(pts)
        used = sorted({c for p in pts for c in p["srcs"]})
        table[name] = {c: v for c, v in source_table(name).items() if c in used}
        out = LAYERS / f"places_{name}.geojson"
        seen = {}

        def props(p):
            q = {k: v for k, v in p.items() if k not in ("lon", "lat") and v is not None and v is not False and v != ""}
            q["pid"] = place_id(name, p)
            n = seen.get(q["pid"], 0)
            seen[q["pid"]] = n + 1
            if n:   # two points alike (unnamed, same metre): numbered in output order
                q["pid"] = place_id(name, {**p, "name": f"{p.get('name') or ''}#{n}"})
            q["srcs"] = ",".join(dict.fromkeys(p["srcs"]))
            return q
        feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(p["lon"], 6), round(p["lat"], 6)]},
                  "properties": props(p)} for p in sorted(pts, key=lambda p: (p["kind"], p["bfs"], p.get("name") or ""))]
        pids = [f["properties"]["pid"] for f in feats]
        if len(set(pids)) != len(pids):
            raise SystemExit(f"{name}: duplicate place ids -- two identical points?")
        out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=0))
        counts = {}
        for p in pts:
            counts.setdefault(p["kind"], {}).setdefault(p["bfs"], 0)
            counts[p["kind"]][p["bfs"]] += 1
        print(f"{out.relative_to(ROOT)}: {len(feats)} points; {notes}")
        for kind, per in sorted(counts.items()):
            print(f"  {kind:13} {sum(per.values()):5}  " + " ".join(f"{b}:{n}" for b, n in sorted(per.items())))
    SOURCES_OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1))
    print(f"wrote {SOURCES_OUT.relative_to(ROOT)}")


# the canton's bathing-place towns in our area (its `art` field), for points
# that lie in the lake: BFS number by the municipality's name
TOWN_BFS = {f["properties"]["bfs"]: re.sub(r"\s*\(ZH\)$", "", f["properties"]["name"]) for f in
            (json.loads((LAYERS / "municipalities.geojson").read_text())["features"]
             if (LAYERS / "municipalities.geojson").exists() else [])}


if __name__ == "__main__":
    main()
