"""Draw a north-up park map from the existing boundary, water and ride data.

Pixel bounds are saved in runtime north/east centimetres so the live marker
uses the same transform as the map. No internet tiles or new survey data.
"""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SIZE = 768
SCALE = 3
inputs = {
    "boundary": ROOT / "data/derived/park_boundary_utm.geojson",
    "origin": ROOT / "manifests/world-origin.json",
    "routes": ROOT / "unreal/Content/WorldData/world.json",
    "water": ROOT / "unreal/Content/WorldData/water-safety.json",
}
origin = json.loads(inputs["origin"].read_text())
boundary = json.loads(inputs["boundary"].read_text())["features"][0]["geometry"]["coordinates"]
park = [[[(n-origin["northing"])*100, (e-origin["easting"])*100] for e,n,*_ in ring] for ring in boundary]
world = json.loads(inputs["routes"].read_text())
main = next(r["points"] for r in world["routes"] if r["id"] == "main_circuit")
points = park[0] + main
min_n, max_n = min(p[0] for p in points), max(p[0] for p in points)
min_e, max_e = min(p[1] for p in points), max(p[1] for p in points)
extent = max(max_n-min_n, max_e-min_e) * 1.13
cn, ce = (min_n+max_n)/2, (min_e+max_e)/2
min_n, max_n, min_e, max_e = cn-extent/2, cn+extent/2, ce-extent/2, ce+extent/2

def pixel(p):
    return ((p[1]-min_e)/extent*SIZE*SCALE, (max_n-p[0])/extent*SIZE*SCALE)

image = Image.new("RGB", (SIZE*SCALE, SIZE*SCALE), (29, 48, 57))
draw = ImageDraw.Draw(image)
draw.polygon([pixel(p) for p in park[0]], fill=(79, 105, 76))
for ring in park[1:]:
    draw.polygon([pixel(p) for p in ring], fill=(29, 48, 57))
draw.line([pixel(p) for p in park[0]], fill=(118, 138, 113), width=2*SCALE)
for r in json.loads(inputs["water"].read_text())["regions"]:
    if r["name"] == "Ocean":
        continue
    for ring in r["rings"]:
        draw.polygon([pixel(p) for p in ring], fill=(29, 48, 57))
secondary = image.copy()
secondary_draw = ImageDraw.Draw(secondary)
for route in world["routes"]:
    if route["id"] == "main_circuit":
        continue
    secondary_draw.line([pixel(p) for p in route["points"]], fill=(111, 133, 102), width=SCALE)
# Only draw interior paths on park land, rather than depicting city connectors
# as lines across the ocean beyond this overview's coverage.
mask = Image.new("L", image.size, 0)
mask_draw = ImageDraw.Draw(mask)
mask_draw.polygon([pixel(p) for p in park[0]], fill=255)
for ring in park[1:]:
    mask_draw.polygon([pixel(p) for p in ring], fill=0)
for region in json.loads(inputs["water"].read_text())["regions"]:
    if region["name"] != "Ocean":
        for ring in region["rings"]:
            mask_draw.polygon([pixel(p) for p in ring], fill=0)
image = Image.composite(secondary,image,mask)
draw = ImageDraw.Draw(image)
draw.line([pixel(p) for p in main], fill=(29, 43, 36), width=7*SCALE, joint="curve")
draw.line([pixel(p) for p in main], fill=(229, 208, 145), width=3*SCALE, joint="curve")
out = ROOT / "exports/ui/T_ParkMinimap.png"
out.parent.mkdir(parents=True, exist_ok=True)
image.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(out)
spec = {
    "schema_version": 1,
    "coordinate_contract": "unreal_north_east_up_cm",
    "north_min": min_n, "north_max": max_n,
    "east_min": min_e, "east_max": max_e,
    "texture": "/Game/StanleyPark/UI/T_ParkMinimap",
    "orientation": "north_up",
    "inputs": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.values()},
    "image_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
}
(ROOT / "unreal/Content/WorldData/minimap.json").write_text(json.dumps(spec, indent=2)+"\n")
(ROOT / "manifests/park-minimap.json").write_text(json.dumps(spec, indent=2)+"\n")
print("Saved", out, "extent metres", round(extent/100))
