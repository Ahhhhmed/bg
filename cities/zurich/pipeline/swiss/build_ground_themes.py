"""
Ground themes for the map area (backlogs 033 / 034): risks and property facts
as polygon layers, plus a per-building join.

Every theme is cut to the area, reduced to a short legend code
(<= 9 classes, German / English labels in LEGENDS below), dissolved per code
(not the runoff map: too dense, see runoff_records), simplified ~1 m in LV95
and written as one GeoJSON per theme (WGS84):

  zurich_hazard.geojson        Naturgefahren: synoptic hazard map (flood + mass
                               movement), level red / blue / yellow / residual
  zurich_runoff.geojson        Oberflächenabfluss: BAFU overland-flow map, flow
                               depth class
  zurich_aircraft_noise.geojson Fluglärm: Zürich airport noise exposure, day Lr
                               in 1 dB bands, 3 dB legend classes
  zurich_contaminated.geojson  Belastete Standorte: cantonal register of
                               polluted sites (KbS), status under the AltlV
  zurich_zoning.geojson        Grundnutzung: zoning plan, cantonal main zone
                               type + the municipality's own zone name
  zurich_noise_es.geojson      Lärmempfindlichkeitsstufen ES I-IV

Sources: the Canton of Zürich's open WFS https://maps.zh.ch/wfs/OGDZHWFS
(one service for all but the runoff map), and for the overland-flow map the
federal download on data.geo.admin.ch (ESRI FileGDB per canton, ~1 GB for
ZH): the same data is on the canton WFS (ogd-0035_awel_wb_ofa_gefaehrdung_f)
but as 275k densely-vertexed polygons in the area (~11 GB of GeoJSON, hours),
so the FileGDB is read locally with pyogrio (`pip install pyogrio`; only
needed for the runoff theme).

The join writes building_ground_facts.json (gitignored, an intermediate) and
the same keys onto every building in building_polygons_baujahr.geojson: {egid: {hazard, hazard_process,
runoff, aircraft_db, aircraft_limit, contaminated, contaminated_site, zone,
zone_zh, zone_abbr, zone_name, es}}, only the keys that have a value, by
testing each building against the six written theme files (so a run for one
theme refreshes the join for all of them): a point inside the building, or for
hazard and runoff, whose maps leave holes at buildings, the footprint grown by
FOOTPRINT_BUFFER_M.

  python3 cities/zurich/pipeline/swiss/build_ground_themes.py [theme ...] [--buildings PATH]
                                              [--join-only | --no-join]

Themes: hazard runoff aircraft contaminated zoning es (default: all). Run after
clip_to_area.py (needs municipalities.geojson; the join reads the buildings,
so after build_parcels.py too). Fetches are cached in
data/work/_ground_<theme>_cache.json (WFS) and _runoff_cache/ (FileGDB);
delete them to re-fetch. A failed WFS tile stops the script.
"""
import argparse
import collections
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).parent))
from area import area_polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "data" / "work"
DEFAULT_BUILDINGS = LAYERS / "building_polygons_baujahr.geojson"
FACTS = LAYERS / "building_ground_facts.json"

WFS_URL = "https://maps.zh.ch/wfs/OGDZHWFS"
TILE_DEG = 0.04       # ~3 x 4.5 km; split further when a tile hits PAGE_CAP
PAGE_CAP = 5000
REQUEST_DELAY = 0.2
SIMPLIFY_M = 1.0      # LV95 metres
COORD_DECIMALS = 6    # ~0.1 m in WGS84

RUNOFF_URL = ("https://data.geo.admin.ch/ch.bafu.gefaehrdungskarte-oberflaechenabfluss/"
              "gefaehrdungskarte-oberflaechenabfluss_zh/gefaehrdungskarte-oberflaechenabfluss_zh_2056.gdb.zip")
RUNOFF_ZIP = LAYERS / "_runoff_cache" / "gefaehrdungskarte-oberflaechenabfluss_zh_2056.gdb.zip"
RUNOFF_GDB = ("GefaehrdungskarteOberflaechenabfluss_ZH/Gefaehrdungskarte_Oberflaechenabfluss_ZH.gdb")
RUNOFF_TILE_M = 2000
# hazard and runoff maps leave holes where buildings stand: those themes join
# on the footprint grown by this much ("the ground at the building"), the others
# on a point inside the building
FOOTPRINT_BUFFER_M = 2.0
RUNOFF_MIN_M2 = 50       # smaller runoff patches are dropped (the source's scale is 1:12,500)
RUNOFF_SIMPLIFY_M = 2.0  # 1 m left 50 MB of GeoJSON; 2 m is 0.16 mm at 1:12,500

TO_LV95 = Transformer.from_crs(4326, 2056, always_xy=True)
TO_WGS84 = Transformer.from_crs(2056, 4326, always_xy=True)

# ---------------------------------------------------------------------------
# Legend codes: code -> (German, English). Order = legend order (worst first).
LEGENDS = {
    "hazard": {
        "red": ("Erhebliche Gefährdung", "Significant hazard"),
        "blue": ("Mittlere Gefährdung", "Moderate hazard"),
        "yellow": ("Geringe Gefährdung", "Low hazard"),
        "residual": ("Restgefährdung", "Residual hazard"),
    },
    "hazard_process": {
        "flood": ("Hochwasser", "Flooding"),
        "landslide": ("Massenbewegung (Rutschung, Steinschlag)", "Mass movement (landslide, rockfall)"),
        "both": ("Hochwasser und Massenbewegung", "Flooding and mass movement"),
    },
    "runoff": {
        "d25": ("Fliesstiefe über 25 cm", "Flow depth over 25 cm"),
        "d10": ("Fliesstiefe 10-25 cm", "Flow depth 10-25 cm"),
        "d0": ("Fliesstiefe bis 10 cm", "Flow depth up to 10 cm"),
    },
    "aircraft": {
        "db67": ("67 dB und mehr", "67 dB and more"),
        "db64": ("64-66 dB", "64-66 dB"),
        "db61": ("61-63 dB", "61-63 dB"),
        "db58": ("58-60 dB", "58-60 dB"),
    },
    "aircraft_limit": {
        "aw": ("Alarmwert überschritten", "Alarm value exceeded"),
        "igw": ("Immissionsgrenzwert überschritten", "Exposure limit exceeded"),
        "pw": ("Planungswert überschritten", "Planning value exceeded"),
        "ok": ("Planungswert eingehalten", "Planning value met"),
        "no_es": ("Keine Beurteilung (keine ES)", "Not assessed (no ES)"),
    },
    "contaminated": {
        "remediate": ("Sanierungsbedürftig (Altlast)", "Needs remediation"),
        "monitor": ("Überwachungsbedürftig", "Needs monitoring"),
        "investigate": ("Untersuchungsbedürftig", "Needs investigation"),
        "undefined": ("Untersuchungsbedarf noch offen", "Need for investigation not yet defined"),
        "provisional": ("Provisorischer Eintrag", "Provisional entry"),
        "no_action": ("Weder überwachungs- noch sanierungsbedürftig", "Needs neither monitoring nor remediation"),
        "no_harm": ("Keine schädlichen Einwirkungen zu erwarten", "No harmful effects expected"),
    },
    "contaminated_site": {
        "landfill": ("Ablagerungsstandort", "Landfill site"),
        "industrial": ("Betriebsstandort", "Industrial / commercial site"),
        "accident": ("Unfallstandort", "Accident site"),
        "shooting": ("Schiessanlage", "Shooting range"),
    },
    "zoning": {},  # filled below (ZONE_GROUPS)
    "es": {
        "I": ("ES I: erhöhtes Lärmschutzbedürfnis (Erholung)", "ES I: increased noise protection (recreation)"),
        "II": ("ES II: keine störenden Betriebe (Wohnen)", "ES II: no disturbing businesses (residential)"),
        "III": ("ES III: mässig störende Betriebe (Misch)", "ES III: moderately disturbing businesses (mixed)"),
        "IV": ("ES IV: stark störende Betriebe (Industrie)", "ES IV: strongly disturbing businesses (industry)"),
        "none": ("Keine ES zugewiesen", "No ES assigned"),
    },
}

# ---------------------------------------------------------------------------
# Per-theme classifiers: raw WFS properties -> compact properties (or None to
# drop the feature). The first key is the legend code.


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


HAZARD_LEVEL = {4: "red", 3: "blue", 2: "yellow", 1: "residual"}


def classify_hazard(p):
    lvl = _int(p.get("gefstufe"))
    if lvl not in HAZARD_LEVEL:
        return None
    hw, mb = _int(p.get("gefstufe_hw")) or 0, _int(p.get("gefstufe_mb")) or 0
    proc = "both" if hw == lvl and mb == lvl else "landslide" if mb == lvl else "flood"
    return {"level": HAZARD_LEVEL[lvl], "process": proc}


def aircraft_class(db):
    """3 dB steps; the layer starts at 58 dB (day Lr, all traffic) in the area."""
    if db >= 67:
        return "db67"
    if db >= 64:
        return "db64"
    if db >= 61:
        return "db61"
    return "db58"


AIRCRAFT_LIMIT = {
    "Alarmwert überschritten": "aw",
    "Immissionsgrenzwert überschritten": "igw",
    "Planungswert überschritten": "pw",
    "Planungswert eingehalten": "ok",
    "Keine Beurteilung (ES fehlt)": "no_es",
}


def classify_aircraft(p):
    db = _int(p.get("overalltrafficday_lr"))
    if db is None:
        return None
    lim = AIRCRAFT_LIMIT.get((p.get("belastungsgrenzwert") or "").strip())
    if lim is None:
        raise ValueError(f"unknown aircraft-noise limit text {p.get('belastungsgrenzwert')!r}")
    return {"cls": aircraft_class(db), "db": db, "limit": lim}


KBS_STATUS = {
    "StatusAltlV1": "no_harm", "StatusAltlV2": "investigate", "StatusAltlV3": "no_action",
    "StatusAltlV4": "monitor", "StatusAltlV5": "remediate", "StatusAltlV6": "undefined",
    "provisorisch": "provisional",
}
KBS_SITE = {"StaoTyp1": "landfill", "StaoTyp2": "industrial", "StaoTyp3": "accident", "StaoTyp4": "shooting"}


# Federal registers of contaminated sites (owner, 2026-10-19): sites on land
# of the public transport (BAV), civil airfields (BAZL, none in the area) and
# the army (VBS) are not in the canton's register. geo.admin.ch identify;
# the status / site type come as German text. 14 military sites are points
# only: drawn as a FEDERAL_POINT_M circle (`approx: true`).
FEDERAL_KBS = {
    "ch.bav.kataster-belasteter-standorte-oev": "BAV",
    "ch.bazl.kataster-belasteter-standorte-zivilflugplaetze": "BAZL",
    "ch.vbs.kataster-belasteter-standorte-militaer": "VBS",
}
FEDERAL_STATUS = {
    "Belastet, sanierungsbedürftig": "remediate",
    "Belastet, überwachungsbedürftig": "monitor",
    "Belastet, untersuchungsbedürftig": "investigate",
    "Belastet, weder überwachungs- noch sanierungsbedürftig": "no_action",
    "Belastet, keine schädlichen oder lästigen Einwirkungen zu erwarten": "no_harm",
}
FEDERAL_SITE = {"Betriebsstandort": "industrial", "Ablagerungsstandort": "landfill",
                "Unfallstandort": "accident", "Schiessanlage": "shooting"}
FEDERAL_POINT_M = 15.0


def federal_contaminated_records(area_wgs, area_lv95):
    """[(props, polygon LV95)] from the federal registers, clipped to the area."""
    from geoadmin_tiles import fetch_layer
    from shapely.geometry import box as _box
    recs = []
    for layer, register in FEDERAL_KBS.items():
        raw = fetch_layer(layer, area_wgs.bounds, geometry_format="geojson", log_prefix=f"  [{register}] ",
                          region=area_wgs.buffer(0.002))
        n = 0
        for f in raw:
            p = f["properties"]
            st = FEDERAL_STATUS.get((p.get("statusaltlv_de") or "").strip())
            if st is None:
                raise ValueError(f"unknown federal KbS status {p.get('statusaltlv_de')!r}")
            props = {"status": st, "register": register}
            site = next((v for k, v in FEDERAL_SITE.items() if (p.get("standorttyp_de") or "").startswith(k)), None)
            if site:
                props["site"] = site
            if p.get("katasternummer"):
                props["nr"] = p["katasternummer"]
            g = shapely.transform(shape(f["geometry"]), lambda c: np.column_stack(TO_LV95.transform(c[:, 0], c[:, 1])))
            if g.geom_type in ("Point", "MultiPoint"):
                g = g.buffer(FEDERAL_POINT_M)
                props["approx"] = True
            if not g.is_valid:
                g = shapely.make_valid(g)
            if not g.intersects(area_lv95):
                continue
            g = g.intersection(area_lv95)
            for part in _to_polys(g):
                recs.append((props, part))
                n += 1
        print(f"  {register}: {len(raw)} fetched -> {n} polygons in the area")
    return recs


def classify_contaminated(p):
    st = p.get("statusaltlv")
    if st not in KBS_STATUS:
        raise ValueError(f"unknown KbS status {st!r}")
    out = {"status": KBS_STATUS[st], "register": "ZH"}
    site = KBS_SITE.get(p.get("standorttyp"))
    if site:
        out["site"] = site
    if p.get("katasternummer"):
        out["nr"] = p["katasternummer"]
    return out


# Cantonal main zone types (typ_zh_abkuerzung of the ÖREB simplified zoning
# model) grouped into the legend; see SOURCES.md for the full list.
ZONE_GROUPS = {
    # code: (German, English, [typ_zh_abkuerzung ...])
    # residential split by the floors allowed (owner, 2026-10-19)
    "W2": ("Wohnzone bis 2 Geschosse", "Residential zone, up to 2 floors", ["W1", "W2"]),
    "W3": ("Wohnzone 3 Geschosse", "Residential zone, 3 floors", ["W3"]),
    "W4": ("Wohnzone 4 Geschosse", "Residential zone, 4 floors", ["W4"]),
    "W5": ("Wohnzone 5 und mehr Geschosse", "Residential zone, 5 and more floors", ["W5+"]),
    "WG": ("Wohnzone mit Gewerbeerleichterung", "Residential zone with business", ["WG1", "WG2", "WG3", "WG4", "WG5+"]),
    "K": ("Kern- und Quartiererhaltungszone", "Core and neighbourhood-preservation zone", ["K", "Q", "KW"]),
    "Z": ("Zentrumszone", "Centre zone", ["Z"]),
    "I": ("Industrie- und Gewerbezone", "Industrial and business zone", ["IG", "IG-HD", "IG-eHD"]),
    "OE": ("Zone für öffentliche Bauten", "Public buildings zone", ["OE"]),
    "F": ("Freihalte-, Erholungs- und Reservezone", "Open space, recreation and reserve zone", ["Fk", "Fko", "E", "R"]),
    "N": ("Landwirtschaft, Wald, Gewässer", "Farmland, forest, water", ["Lk", "Lko", "Wa", "G"]),
    "V": ("Verkehrsfläche, nicht zugewiesen", "Roads, railway, unassigned", ["VS", "VB", "NZ"]),
}
LEGENDS["zoning"] = {k: v[:2] for k, v in ZONE_GROUPS.items()}
ZONE_OF = {abbr: k for k, v in ZONE_GROUPS.items() for abbr in v[2]}


def classify_zoning(p):
    zh = (p.get("typ_zh_abkuerzung") or "").strip()
    if zh not in ZONE_OF:
        raise ValueError(f"unmapped cantonal zone type {zh!r} ({p.get('typ_zh_bezeichnung')!r}) -- add it to ZONE_GROUPS")
    out = {"zone": ZONE_OF[zh], "zh": zh}
    if p.get("typ_gde_abkuerzung"):
        out["abbr"] = p["typ_gde_abkuerzung"].strip()
    if p.get("typ_gde_bezeichnung"):
        out["name"] = " ".join(p["typ_gde_bezeichnung"].split())
    return out


ES_CODE = {"ES_I": "I", "ES_II": "II", "ES_III": "III", "ES_IV": "IV", "Keine_ES": "none"}


def classify_es(p):
    c = p.get("typ_code")
    if c not in ES_CODE:
        raise ValueError(f"unknown ES code {c!r}")
    out = {"es": ES_CODE[c]}
    if p.get("aufgestuft") == "ja":
        out["upgraded"] = True
    return out


RUNOFF_DEPTH = {0.0: "d0", 0.1: "d10", 0.25: "d25"}

# key -> config. `code` is the property holding the legend code; `join_by` is
# "point" (default) or "footprint" (see FOOTPRINT_BUFFER_M); `fields` are
# requested from the WFS (plus the geometry); `rank` orders codes for the
# per-building pick (higher wins).
THEMES = {
    "hazard": {
        "code": "level",
        "typename": "ms:ogd-0044_giszhpub_wb_syn_gk_f",
        "fields": ["gefstufe", "gefstufe_hw", "gefstufe_mb"],
        "classify": classify_hazard, "out": "zurich_hazard.geojson", "coverage": True,
        "join_by": "footprint",  # the map leaves holes at buildings
        "rank": lambda q: ["residual", "yellow", "blue", "red"].index(q["level"]),
        "facts": lambda q: {"hazard": q["level"], "hazard_process": q["process"]},
    },
    "runoff": {
        "code": "depth",
        "classify": None, "out": "zurich_runoff.geojson", "coverage": False,  # not dissolved, see runoff_records
        "join_by": "footprint",  # the flow model routes water around buildings
        "rank": lambda q: ["d0", "d10", "d25"].index(q["depth"]),
        "facts": lambda q: {"runoff": q["depth"]},
    },
    "aircraft": {
        "code": "cls",
        "typename": "ms:ogd-0360_tba_fals_fluglaerm_wohnen_f",
        "fields": ["overalltrafficday_lr", "belastungsgrenzwert"],
        "classify": classify_aircraft, "out": "zurich_aircraft_noise.geojson", "coverage": True,
        "rank": lambda q: q["db"],
        "facts": lambda q: {"aircraft_db": q["db"], "aircraft_limit": q["limit"]},
    },
    "contaminated": {
        "code": "status",
        "typename": "ms:ogd-0144_awel_aw_al_kbs_oereb_f",
        "fields": ["katasternummer", "standorttyp", "statusaltlv"],
        "classify": classify_contaminated, "out": "zurich_contaminated.geojson", "coverage": False,
        "rank": lambda q: list(LEGENDS["contaminated"])[::-1].index(q["status"]),
        "facts": lambda q: {"contaminated": q["status"], "contaminated_register": q["register"],
                            **({"contaminated_site": q["site"]} if "site" in q else {})},
    },
    "zoning": {
        "code": "zone",
        "typename": "ms:ogd-0156_arv_basis_np_gn_zonenflaeche_f",
        "fields": ["typ_zh_abkuerzung", "typ_zh_bezeichnung", "typ_gde_abkuerzung", "typ_gde_bezeichnung"],
        "classify": classify_zoning, "out": "zurich_zoning.geojson", "coverage": True,
        "rank": lambda q: 0,
        "facts": lambda q: {"zone": q["zone"], "zone_zh": q["zh"],
                            **({"zone_abbr": q["abbr"]} if "abbr" in q else {}),
                            **({"zone_name": q["name"]} if "name" in q else {})},
    },
    "es": {
        "code": "es",
        "typename": "ms:ogd-0154_arv_basis_np_ls_festlegung_f",
        "fields": ["typ_code", "aufgestuft"],
        "classify": classify_es, "out": "zurich_noise_es.geojson", "coverage": True,
        "rank": lambda q: ["none", "I", "II", "III", "IV"].index(q["es"]),
        "facts": lambda q: {"es": q["es"]},
    },
}

# ---------------------------------------------------------------------------
# Fetching


def _filter(bbox):
    xmin, ymin, xmax, ymax = bbox
    return (
        '<Filter xmlns="http://www.opengis.net/fes/2.0" xmlns:gml="http://www.opengis.net/gml/3.2">'
        '<BBOX><ValueReference>geometry</ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">'
        f"<gml:lowerCorner>{ymin} {xmin}</gml:lowerCorner><gml:upperCorner>{ymax} {xmax}</gml:upperCorner>"
        "</gml:Envelope></BBOX></Filter>"
    )


def _fetch_tile(typename, fields, bbox):
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": typename,
        "FILTER": _filter(bbox), "COUNT": str(PAGE_CAP), "SRSNAME": "EPSG:2056",
        "PROPERTYNAME": ",".join(["geometry", "geodb_oid", *fields]),
        "OUTPUTFORMAT": "application/json; subtype=geojson",
    }
    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as resp:
                return json.loads(resp.read())["features"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            if attempt == 3:
                # a hole in a theme would be silent on the map: stop
                raise RuntimeError(f"WFS {typename} tile {bbox} failed: {e}") from e
            time.sleep(2 * (attempt + 1))


def fetch_wfs(key, cfg, area_wgs):
    cache = LAYERS / f"_ground_{key}_cache.json"
    if cache.exists():
        print(f"  cached {cache.name} (delete it to re-fetch)")
        return json.loads(cache.read_text())
    print(f"  fetching {cfg['typename']} from {WFS_URL} ...")
    xmin, ymin, xmax, ymax = area_wgs.bounds
    area_p = prep(area_wgs)
    stack = []
    x = xmin
    while x < xmax:
        y = ymin
        while y < ymax:
            t = (x, y, min(x + TILE_DEG, xmax), min(y + TILE_DEG, ymax))
            if area_p.intersects(box(*t)):
                stack.append(t)
            y += TILE_DEG
        x += TILE_DEG
    seen, out, tiles, t0 = set(), [], 0, time.time()
    while stack:
        bbox = stack.pop()
        feats = _fetch_tile(cfg["typename"], cfg["fields"], bbox)
        time.sleep(REQUEST_DELAY)
        tiles += 1
        if len(feats) >= PAGE_CAP:
            bx0, by0, bx1, by1 = bbox
            mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
            stack += [(bx0, by0, mx, my), (mx, by0, bx1, my), (bx0, my, mx, by1), (mx, my, bx1, by1)]
            continue
        for f in feats:
            oid = f["properties"].get("geodb_oid")
            if oid is None:
                raise RuntimeError(f"{cfg['typename']}: feature without geodb_oid, can't dedup")
            if oid in seen or not f.get("geometry"):
                continue
            seen.add(oid)
            out.append(f)
        if tiles % 10 == 0:
            print(f"    ...{tiles} tiles, {len(out)} features, {time.time() - t0:.0f} s")
    cache.write_text(json.dumps(out))
    print(f"  {tiles} tiles, {len(out)} unique features -> {cache.name} ({time.time() - t0:.0f} s)")
    return out


def _to_polys(g):
    """Polygonal parts of a geometry (drops stray points / lines)."""
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [q for p in g.geoms for q in _to_polys(p)]
    return []


def wfs_records(key, cfg, area_wgs, area_lv95):
    """[(props, polygon LV95)] for one WFS theme, clipped to the area."""
    raw = fetch_wfs(key, cfg, area_wgs)
    area_p = prep(area_lv95)
    recs, dropped = [], collections.Counter()
    for f in raw:
        props = cfg["classify"](f["properties"])
        if props is None:
            dropped["no class"] += 1
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = shapely.make_valid(g)
        if not area_p.contains(g):
            if not area_p.intersects(g):
                dropped["outside area"] += 1
                continue
            g = g.intersection(area_lv95)
        for part in _to_polys(g):
            recs.append((props, part))
    print(f"  {len(raw)} fetched -> {len(recs)} polygons in the area; dropped {dict(dropped)}")
    return recs


def runoff_records(area_lv95):
    """[(props, polygon LV95)] for the overland-flow map, from the FileGDB."""
    try:
        import pyogrio
        import pyogrio.raw
    except ImportError:
        sys.exit("the runoff theme needs pyogrio: pip install pyogrio")
    if not RUNOFF_ZIP.exists():
        RUNOFF_ZIP.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {RUNOFF_URL} (~1 GB) ...")
        tmp = RUNOFF_ZIP.with_suffix(".part")
        urllib.request.urlretrieve(RUNOFF_URL, tmp)
        tmp.rename(RUNOFF_ZIP)
    else:
        print(f"  cached {RUNOFF_ZIP.relative_to(LAYERS)} (delete it to re-download)")
    path = f"/vsizip/{RUNOFF_ZIP}/{RUNOFF_GDB}"
    # FileGDB rings are oriented (outer CW, holes CCW): GDAL needn't test every
    # ring against every other one (same result, half the read time)
    pyogrio.set_gdal_config_options({"OGR_ORGANIZE_POLYGONS": "ONLY_CCW"})
    xmin, ymin, xmax, ymax = area_lv95.bounds
    area_p = prep(area_lv95)
    recs, n_raw, t0 = [], 0, time.time()
    x = xmin
    while x < xmax:
        y = ymin
        while y < ymax:
            tile = box(x, y, x + RUNOFF_TILE_M, y + RUNOFF_TILE_M)
            y += RUNOFF_TILE_M
            if not area_p.intersects(tile):
                continue
            cut = area_lv95.intersection(tile)
            _, _, wkb, fields = pyogrio.raw.read(path, bbox=tile.bounds, columns=["UE_Tiefe_UG"])
            if wkb is None or len(wkb) == 0:
                continue
            n_raw += len(wkb)
            geoms = shapely.from_wkb(wkb)
            depth = np.array([RUNOFF_DEPTH.get(round(float(v), 2)) for v in fields[0]], dtype=object)
            sel = depth != None  # noqa: E711 -- drops 99 = river (modelled, not a runoff depth)
            # simplify each source polygon first (~2M vertices per 2 km tile; a
            # union per class took ~100 s a tile, make_valid + topology-preserving
            # simplify ~55 s, plain Douglas-Peucker ~6 s), repair what that
            # breaks, then cut to the tile: a polygon straddling tiles comes back
            # from each, the cut keeps every piece once
            g = shapely.simplify(geoms[sel], RUNOFF_SIMPLIFY_M, preserve_topology=False)
            bad = ~shapely.is_valid(g)
            g[bad] = shapely.make_valid(g[bad])
            for code in set(depth[sel]):
                # dissolve per class within the tile (cheap once simplified):
                # merges neighbouring polygons and the source's map-sheet edges
                u = shapely.intersection(shapely.union_all(g[depth[sel] == code]), cut)
                recs += [({"depth": code}, q) for q in _to_polys(u) if q.area >= RUNOFF_MIN_M2]
        x += RUNOFF_TILE_M
        print(f"    ...column {int((x - xmin) / RUNOFF_TILE_M)}: {n_raw} read, {len(recs)} polygons, {time.time() - t0:.0f} s")
    return recs


def dissolve(recs):
    groups = collections.defaultdict(list)
    for props, g in recs:
        groups[json.dumps(props, sort_keys=True, ensure_ascii=False)].append(g)
    out = []
    for k, gs in groups.items():
        u = shapely.union_all(gs) if len(gs) > 1 else gs[0]
        out += [(json.loads(k), p) for p in _to_polys(u)]
    return out


# ---------------------------------------------------------------------------
# Join


def building_points(path):
    print(f"Reading buildings from {path} ...")
    fc = json.loads(Path(path).read_text())
    egids, polys = [], []
    for f in fc["features"]:
        e = f["properties"].get("egid")
        if not e or not f.get("geometry"):
            continue
        egids.append(str(e))
        polys.append(shape(f["geometry"]))
    del fc
    polys = np.array(polys, dtype=object)
    points = shapely.point_on_surface(polys)
    lv95 = shapely.transform(polys, lambda c: np.column_stack(TO_LV95.transform(c[:, 0], c[:, 1])))
    rings = shapely.transform(shapely.buffer(lv95, FOOTPRINT_BUFFER_M),
                              lambda c: np.column_stack(TO_WGS84.transform(c[:, 0], c[:, 1])))
    print(f"  {len(egids)} buildings with an EGID")
    return egids, {"point": points, "footprint": rings}


def join(cfg, path, egids, shapes):
    """{egid: facts} for one theme from its written GeoJSON (WGS84, simplified
    ~1-2 m -- below the buildings' size); the highest-ranked polygon wins."""
    feats = json.loads(path.read_text())["features"]
    tree = shapely.STRtree([shape(f["geometry"]) for f in feats])
    bi, pi = tree.query(shapes[cfg.get("join_by", "point")], predicate="intersects")
    best = {}
    for b, p in zip(bi, pi):
        props = feats[p]["properties"]
        r = cfg["rank"](props)
        if b not in best or r > best[b][0]:
            best[b] = (r, props)
    return {egids[b]: cfg["facts"](props) for b, (_, props) in best.items()}


def write_facts(buildings):
    if not Path(buildings).exists():
        sys.exit(f"{buildings} missing (bash cities/zurich/pipeline/refresh.sh, or --buildings PATH)")
    egids, shapes = building_points(buildings)
    facts = collections.defaultdict(dict)
    for key, cfg in THEMES.items():
        path = LAYERS / cfg["out"]
        if not path.exists():
            sys.exit(f"{path.name} missing -- run this script for theme {key!r} first")
        j = join(cfg, path, egids, shapes)
        for e, d in j.items():
            facts[e].update(d)
        print(f"  buildings in a {key} polygon: {len(j)}")
    FACTS.write_text(json.dumps(dict(sorted(facts.items())), ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {len(facts)} buildings -> {FACTS.relative_to(ROOT)} ({FACTS.stat().st_size / 1e6:.1f} MB)")
    # and onto the buildings themselves (the hover card reads them from the tiles)
    fc = json.loads(Path(buildings).read_text())
    keys = {k for d in facts.values() for k in d}
    for f in fc["features"]:
        p = f["properties"]
        for k in keys:
            p.pop(k, None)
        p.update(facts.get(str(p.get("egid")), {}))
    Path(buildings).write_text(json.dumps(fc))
    print(f"  ground facts written onto {Path(buildings).name}: {', '.join(sorted(keys))}")


# ---------------------------------------------------------------------------
# Output


def _to_wgs84(coords):
    x, y = TO_WGS84.transform(coords[:, 0], coords[:, 1])
    return np.round(np.column_stack([x, y]), COORD_DECIMALS)


def write_theme(key, cfg, recs, min_part_m2):
    geoms = np.array([g for _, g in recs], dtype=object)
    if cfg["coverage"]:
        try:
            simple = shapely.coverage_simplify(geoms, SIMPLIFY_M)
        except shapely.errors.GEOSException as e:
            print(f"  coverage_simplify failed ({e}); simplifying each polygon")
            simple = shapely.simplify(geoms, SIMPLIFY_M, preserve_topology=True)
    else:
        simple = shapely.simplify(geoms, SIMPLIFY_M, preserve_topology=True)
    keep = ~shapely.is_empty(simple) & (shapely.area(simple) >= min_part_m2)
    wgs = shapely.transform(simple[keep], _to_wgs84)
    # rounding to ~0.1 m can fold a narrow neck onto itself: repair those
    bad = ~shapely.is_valid(wgs)
    for i in np.flatnonzero(bad):
        parts = _to_polys(shapely.make_valid(wgs[i]))
        wgs[i] = shapely.multipolygons(parts) if len(parts) > 1 else (parts[0] if parts else shapely.Polygon())
    ok = ~shapely.is_empty(wgs)
    keep[np.flatnonzero(keep)[~ok]] = False
    wgs = wgs[ok]
    props = [p for (p, _), k in zip(recs, keep) if k]
    feats = [{"type": "Feature", "geometry": json.loads(shapely.to_geojson(g)), "properties": p}
             for g, p in zip(wgs, props)]
    out = LAYERS / cfg["out"]
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                              ensure_ascii=False, separators=(",", ":")))
    first = cfg["code"]
    counts = collections.Counter(p[first] for p in props)
    areas = collections.defaultdict(float)
    for g, p in zip(simple[keep], props):
        areas[p[first]] += g.area
    print(f"  wrote {len(feats)} polygons ({int((~keep).sum())} slivers < {min_part_m2} m2 dropped), "
          f"{out.stat().st_size / 1e6:.1f} MB -> {out.relative_to(ROOT)}")
    for code in LEGENDS[key]:
        if code in counts:
            print(f"    {code:12s} {counts[code]:6d} polygons {areas[code] / 1e6:8.2f} km2")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("themes", nargs="*", help=f"any of {' '.join(THEMES)} (default: all)")
    ap.add_argument("--buildings", default=str(DEFAULT_BUILDINGS),
                    help="building GeoJSON for the join (default: data/work/building_polygons_baujahr.geojson)")
    ap.add_argument("--join-only", action="store_true", help="only redo the join from the written theme files")
    ap.add_argument("--no-join", action="store_true", help="don't (re)write building_ground_facts.json")
    args = ap.parse_args()
    unknown = set(args.themes) - set(THEMES)
    if unknown:
        ap.error(f"unknown theme(s) {sorted(unknown)}; pick from {list(THEMES)}")
    themes = [] if args.join_only else (args.themes or list(THEMES))

    area_wgs = area_polygon()
    area_lv95 = shapely.transform(area_wgs, lambda c: np.column_stack(TO_LV95.transform(c[:, 0], c[:, 1])))
    for key in themes:
        cfg = THEMES[key]
        print(f"[{key}]")
        recs = runoff_records(area_lv95) if key == "runoff" else wfs_records(key, cfg, area_wgs, area_lv95)
        if key == "contaminated":
            recs += federal_contaminated_records(area_wgs, area_lv95)
        if cfg["coverage"]:
            recs = dissolve(recs)
            print(f"  dissolved per class -> {len(recs)} polygons")
        write_theme(key, cfg, recs, min_part_m2=RUNOFF_MIN_M2 if key == "runoff" else 1)
    if not args.no_join:
        print("[join]")
        write_facts(args.buildings)


if __name__ == "__main__":
    main()
