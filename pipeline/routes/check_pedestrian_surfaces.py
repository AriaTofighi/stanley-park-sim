"""Inspect the saved output topology and provenance, independently of meshing."""
import json
import numpy as np
from build_pedestrian_network import ROOT, digest, save

manifest = json.loads((ROOT / "data/routes/derived/pedestrian-surfaces.json").read_text(encoding="utf8"))
bad_winding = 0
area = 0.
triangle_count = 0
stale = []
for item in manifest["terrain_inputs"]:
    if digest(ROOT / item["path"]) != item["sha256"]:
        stale.append(item["path"])
for item in manifest["meshes"]:
    path = ROOT / item["path"]
    if digest(path) != item["sha256"]:
        stale.append(item["path"])
    with np.load(path) as data:
        vertices, faces = data["vertices"], data["faces"]
        if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
            raise RuntimeError(f"Invalid geometry in {path}")
        triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    bad_winding += int((cross[:, 2] <= 0).sum())
    area += float((cross[:, 2] * .5).sum())
    triangle_count += len(faces)
    if item["collision"]:
        raise RuntimeError("A visual overlay must not add offset collision")
checks_path = ROOT / "evidence/pedestrian-surfaces-checks.json"
checks = json.loads(checks_path.read_text(encoding="utf8"))
checks.update(nonpositive_xy_winding=bad_winding, projected_surface_area_m2=area, saved_triangle_count=triangle_count,
              stale_files=stale, saved_output_geometry_pass=not stale and bad_winding == 0)
save(checks_path, checks)
print(json.dumps({k: checks[k] for k in ["saved_triangle_count", "nonpositive_xy_winding", "projected_surface_area_m2", "stale_files", "saved_output_geometry_pass"]}, indent=2))
if stale or bad_winding:
    raise RuntimeError("Saved pedestrian output check failed")
