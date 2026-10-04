"""Polygonize open BC coastline linework. Heights never classify sea as land."""
import json
import os
from pathlib import Path
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Point, box, mapping
from shapely.ops import polygonize, unary_union
from acquire_sources import save_json, digest

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "tmp/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

source = ROOT / "data/raw/corridor/fwa-coast-merged.json"
origin = json.loads((ROOT / "manifests/world-origin.json").read_text())
grid = np.load(ROOT / "data/derived/terrain_surroundings.npz")
extent = box(float(grid["x"][0])-100, float(grid["y"][0])-100,
             float(grid["x"][-1])+100, float(grid["y"][-1])+100)
lines = []
for feature in json.loads(source.read_text())["features"]:
    for coordinates in feature["geometry"]["paths"]:
        points = np.asarray(coordinates)[:, :2] - [origin["easting"], origin["northing"]]
        clipped = LineString(points).intersection(extent)
        if not clipped.is_empty:
            lines.append(clipped)
regions = list(polygonize(unary_union([extent.boundary, *lines])))
if abs(sum(p.area for p in regions) - extent.area) > 1:
    raise RuntimeError("Coastline did not form a complete partition")
to_utm = Transformer.from_crs(4326, 3157, always_xy=True)
# These interior classification points do not alter any shoreline coordinates.
checks = [
    ("English Bay", -123.18, 49.285, True),
    ("Strait of Georgia", -123.30, 49.28, True),
    ("Burrard Inlet", -123.08, 49.30, True),
    ("Howe Sound", -123.28, 49.44, True),
    ("Stanley Park interior", -123.145, 49.304, False),
    ("Downtown Vancouver", -123.12, 49.28, False),
    ("North Shore mountains", -123.10, 49.37, False),
]
ocean_regions = set()
records = []
for name, lon, lat, expected in checks:
    east, north = to_utm.transform(lon, lat)
    point = Point(east-origin["easting"], north-origin["northing"])
    matches = [i for i, polygon in enumerate(regions) if polygon.contains(point)]
    if len(matches) != 1:
        raise RuntimeError(f"Ambiguous control location: {name}")
    if expected:
        ocean_regions.add(matches[0])
    records.append(dict(name=name, lon=lon, lat=lat, expected_ocean=expected,
                        region=matches[0], local_m=list(point.coords)[0]))
for record in records:
    if (record["region"] in ocean_regions) != record["expected_ocean"]:
        raise RuntimeError(f"Coastline classification conflicts at {record['name']}")
ocean = unary_union([regions[i] for i in sorted(ocean_regions)])
gx, gy = np.meshgrid(grid["x"], grid["y"])
np.savez_compressed(ROOT / "data/derived/regional-ocean-mask.npz",
                    x=grid["x"], y=grid["y"], ocean=shapely.contains_xy(ocean, gx, gy))
save_json(ROOT / "data/derived/ocean_mask.geojson", dict(type="FeatureCollection", features=[dict(
    type="Feature", properties=dict(source="BC FWA Coastlines", source_sha256=digest(source),
    crs="EPSG:3157 translated by immutable world origin", generalization_metres=2,
    intended_use="Regional mesh mask only; not close seawall geometry"), geometry=mapping(ocean))]))
save_json(ROOT / "evidence/ocean-mask-checks.json", dict(regions=len(regions),
    ocean_regions=sorted(ocean_regions), controls=records, source_sha256=digest(source),
    partition_area_residual_m2=sum(p.area for p in regions)-extent.area))
fig, ax = plt.subplots(figsize=(10,10), dpi=140)
for p in regions:
    xx, yy = p.exterior.xy
    ax.fill(xx, yy, color="#bad8df" if p.representative_point().within(ocean) else "#9ba982", lw=.2, ec="#64705d")
    for ring in p.interiors:
        ax.fill(*ring.xy, color="#9ba982")
for r in records:
    ax.plot(*r["local_m"], "o", ms=3, color="#c94e35")
    ax.annotate(r["name"], r["local_m"], fontsize=7)
ax.set_aspect("equal"); ax.set_title("Regional ocean mask from BC FWA Coastlines")
ax.set_xlabel("Local east (m)"); ax.set_ylabel("Local north (m)")
fig.savefig(ROOT / "evidence/ocean-mask-map.png", bbox_inches="tight")
print(json.dumps(dict(regions=len(regions), ocean_regions=sorted(ocean_regions), controls_pass=True)))
