"""
Rebuild data/featured.json: prebuilt Overture Maps extracts for the featured districts.

For each district: find its boundary with Nominatim, download Overture "place" points in its
bounding box, keep schools and medical facilities inside the boundary, and merge facilities
within 75 m of each other.

Usage (from the repo root):
    pip install overturemaps shapely
    python scripts/make_featured.py
"""
import json, sys, math, shutil, subprocess, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "GeoMindAI/1.0 (hackathon project)"}
REPO = Path(__file__).resolve().parent.parent
HERE = Path(tempfile.mkdtemp(prefix="geomind-overture-"))      # downloads go to a temp folder
OVT = shutil.which("overturemaps") or sys.exit("The overturemaps CLI is missing: pip install overturemaps")

PLACES = [
    ("ghirnatah", "Ghirnatah, Riyadh, Saudi Arabia",  "Ghirnatah District, Riyadh"),
    ("gulberg",   "Gulberg, Lahore, Pakistan",        "Gulberg, Lahore"),
    ("clifton",   "Clifton, Karachi, Pakistan",       "Clifton, Karachi"),
]

SCHOOL = ("school", "elementary_school", "middle_school", "high_school", "primary_school",
          "secondary_school", "private_school", "preschool", "kindergarten")
MED = ("hospital", "clinic", "medical_center", "doctor", "physician", "dentist",
       "urgent_care", "emergency_room", "health_and_medical", "medical_service")

from shapely.geometry import shape, Point, box


def as_dict(v):
    if isinstance(v, str):
        try: return json.loads(v)
        except ValueError: return {}
    return v or {}

def cat(p):  return (as_dict(p.get("categories")).get("primary") or "").lower()
def nm(p):   return as_dict(p.get("names")).get("primary") or ""

def haversine(a, b):
    (lo1, la1), (lo2, la2) = a, b
    R = 6371000
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1); dl = math.radians(lo2 - lo1)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def build(key, query, label):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1, "polygon_geojson": 1})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        hit = json.load(r)[0]
    bb = hit["boundingbox"]
    s, n, w, e = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
    geom = hit["geojson"]
    osm_ref = hit["osm_type"][0].upper() + str(hit["osm_id"])   # e.g. "R13254432"

    # If the geocoder gave a point (no boundary), use the bbox rectangle instead
    if geom["type"] == "Point":
        poly = box(w, s, e, n)
        geom = json.loads(json.dumps(poly.__geo_interface__))
        print(f"  ({key}: no polygon from geocoder — using bbox rectangle)")
    else:
        poly = shape(geom)

    out = HERE / f"_places_{key}.geojson"
    subprocess.run([str(OVT), "download", f"--bbox={w},{s},{e},{n}",
                    "-f", "geojson", "--type=place", "-o", str(out)], check=True)
    feats = json.loads(out.read_text(encoding="utf-8"))["features"]

    def collect(pats, exact):
        rows = []
        for f in feats:
            p = f["properties"]; c = cat(p)
            ok = (c in pats) if exact else any(k in c for k in pats)
            if ok and (p.get("confidence") or 0) > 0.5:
                lon, lat = f["geometry"]["coordinates"]
                if poly.contains(Point(lon, lat)):
                    rows.append({"lon": lon, "lat": lat, "name": nm(p), "category": c,
                                 "confidence": round(p.get("confidence", 0), 3)})
        return rows

    schools = collect(SCHOOL, True)
    medical = collect(MED, False)
    medical.sort(key=lambda r: -r["confidence"])
    kept = []
    for r in medical:
        if all(haversine((r["lon"], r["lat"]), (k["lon"], k["lat"])) > 75 for k in kept):
            kept.append(r)

    def fc(rows):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
             "properties": {"name": r["name"], "category": r["category"]}} for r in rows]}

    c0 = poly.centroid
    print(f"  {label}: {len(schools)} schools, {len(kept)} facilities  (osm {osm_ref})")
    return {
        "name": label, "osm": osm_ref,
        "center": [round(c0.y, 5), round(c0.x, 5)],
        "boundary": {"type": "Feature", "geometry": geom, "properties": {"name": label}},
        "schools": fc(schools), "facilities": fc(kept),
    }


featured = {}
for key, query, label in PLACES:
    print(f"Building {key} …")
    featured[key] = build(key, query, label)
    time.sleep(2)

path = REPO / "data" / "featured.json"
path.write_text(json.dumps(featured, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"\nWrote {path}  ({path.stat().st_size/1024:.1f} KB)")
