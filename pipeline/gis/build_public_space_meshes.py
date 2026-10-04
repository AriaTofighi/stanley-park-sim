"""Clip source-linked public-space patches to the exported terrain triangles.

This does not run Blender or the application. Reference-only mixed sites are
not filled. Collision remains on the existing terrain.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import shapely
from shapely.geometry import Polygon, shape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/derived/public-spaces/meshes"
LIFT = .02
COLORS = {
    "sports_grass": [.23, .36, .13, 1], "meadow": [.30, .40, .18, 1],
    "bowling_grass": [.22, .36, .15, 1], "concrete": [.55, .54, .49, 1],
    "splash_pad": [.49, .48, .41, 1], "play_sand": [.60, .51, .34, 1],
    "court_asphalt": [.26, .31, .31, 1], "court_tennis": [.24, .40, .33, 1],
    "garden_bed": [.28, .23, .14, 1],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8")


def mesh_footprint(rows, inputs):
    polygons = []
    for row in rows:
        path = ROOT / row["path"]
        if digest(path) != row["sha256"]:
            raise ValueError(f"Source mesh changed: {path}")
        with np.load(path) as package:
            vertices = package["vertices"].astype(float) + package["anchor"]
            triangles = vertices[package["faces"], :2]
        polygons.extend(shapely.polygons(triangles))
        inputs.append({"path": row["path"], "sha256": row["sha256"]})
    return shapely.union_all(polygons)


def clip_patch(triangles, polygons, tree, footprint, anchor):
    indices = tree.query(footprint, predicate="intersects")
    fragments = shapely.intersection(polygons[indices], footprint)
    vertices, faces, lookup = [], [], {}
    maximum_error = 0.
    discarded = 0
    for index, fragment in zip(indices, fragments):
        a, b, c = triangles[index]
        basis = np.column_stack((b[:2] - a[:2], c[:2] - a[:2]))
        if abs(np.linalg.det(basis)) < 1e-12:
            continue
        inverse = np.linalg.inv(basis)
        for polygon in shapely.get_parts(fragment):
            if not isinstance(polygon, Polygon) or polygon.area < 1e-8:
                continue
            for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(polygon)):
                xy = np.asarray(triangle.exterior.coords)[:3, :2]
                signed = float(np.linalg.det(np.column_stack((xy[1] - xy[0], xy[2] - xy[0]))))
                if abs(signed) < 1e-10:
                    discarded += 1
                    continue
                if signed < 0:
                    xy = xy[::-1]
                uv = (inverse @ (xy - a[:2]).T).T
                z = a[2] + uv[:, 0] * (b[2] - a[2]) + uv[:, 1] * (c[2] - a[2]) + LIFT
                face = []
                for point in np.column_stack((xy, z)):
                    key = tuple(np.round(point, 7))
                    if key not in lookup:
                        lookup[key] = len(vertices)
                        vertices.append(point - anchor)
                    face.append(lookup[key])
                faces.append(face)
                uv_c = inverse @ (xy.mean(axis=0) - a[:2])
                expected = a[2] + uv_c[0] * (b[2] - a[2]) + uv_c[1] * (c[2] - a[2])
                maximum_error = max(maximum_error, abs(float(z.mean() - expected - LIFT)))
    return np.asarray(vertices), np.asarray(faces, dtype=np.int32), maximum_error, discarded


def main():
    source_path = ROOT / "manifests/public-space-blockouts.json"
    source = json.loads(source_path.read_text(encoding="utf8"))
    geometry_path = ROOT / source["authoring_geometry"]["path"]
    if digest(geometry_path) != source["authoring_geometry"]["sha256"]:
        raise ValueError("Public-space source package changed")
    features = json.loads(geometry_path.read_text(encoding="utf8"))["features"]
    geometries = {f["properties"]["component_id"]: shape(f["geometry"]) for f in features}
    rows = {f["properties"]["component_id"]: f["properties"] for f in features}
    surface_path = ROOT / "manifests/surface-model.json"
    surface = json.loads(surface_path.read_text(encoding="utf8"))
    walk_path = ROOT / "data/routes/derived/pedestrian-surfaces.json"
    walks = json.loads(walk_path.read_text(encoding="utf8"))
    mesh_inputs = []
    pavement = mesh_footprint([r for r in surface["pavement"] if r["role"] == "pavement"], mesh_inputs)
    road_paths = mesh_footprint(surface["routes"], mesh_inputs)
    walking = mesh_footprint(walks["meshes"], mesh_inputs)
    masks = {"main_pavement": pavement.buffer(.025), "road_and_branch_overlays": road_paths.buffer(.025), "walking_overlays": walking.buffer(.025)}
    source_inputs = [source_path, geometry_path, surface_path, walk_path]
    for key, relative in [("water", "data/derived/lake-surfaces.geojson"), ("underpass_holes", "data/derived/underpass-openings.geojson")]:
        path = ROOT / relative
        source_inputs.append(path)
        masks[key] = shapely.union_all([shape(f["geometry"]) for f in json.loads(path.read_text(encoding="utf8"))["features"]])
    cover_path = ROOT / "data/derived/cover-blockout.json"
    source_inputs.append(cover_path)
    cover = json.loads(cover_path.read_text(encoding="utf8"))
    masks["buildings"] = shapely.union_all([shapely.make_valid(Polygon(b["outline"])) for b in cover["buildings"]]).buffer(.025)
    masks["wetlands"] = shapely.union_all([geometries[k] for k, r in rows.items() if r["material_role"] == "wetland"])
    all_exclusions = shapely.union_all(list(masks.values()))
    occupied = shapely.GeometryCollection()
    patches, withheld, summaries = {}, [], []
    for key, row in rows.items():
        if row["display_mode"] != "surface_patch" or row.get("level_review_required"):
            withheld.append({"component_id": key, "reason": "Upper plaza level requires a separate structure" if row.get("level_review_required") else row["display_mode"], "counted_as_completed_surface": False})
            continue
        original = geometries[key]
        patch = original.difference(all_exclusions).difference(occupied)
        for excluded in row.get("exclude_component_ids", []):
            patch = patch.difference(geometries[excluded])
        if patch.is_empty:
            withheld.append({"component_id": key, "reason": "No area remains after source exclusions", "counted_as_completed_surface": False})
            continue
        patches[key] = patch
        occupied = occupied.union(patch)
        summaries.append({"component_id": key, "source_area_m2": float(original.area), "authoring_area_m2": float(patch.area),
                          "mask_intersection_m2": {name: float(original.intersection(mask).area) for name, mask in masks.items()}})
    OUT.mkdir(parents=True, exist_ok=True)
    meshes, terrain_inputs, coverage = [], [], {k: 0. for k in patches}
    maximum_error, discarded = 0., 0
    for terrain in surface["terrain"]:
        path = ROOT / terrain["path"]
        if digest(path) != terrain["sha256"]:
            raise ValueError(f"Terrain changed: {path}")
        with np.load(path) as package:
            anchor = package["anchor"].astype(float)
            source_vertices = package["vertices"].astype(float) + anchor
            triangles = source_vertices[package["faces"]]
        polygons = shapely.polygons(triangles[:, :, :2])
        tree = shapely.STRtree(polygons)
        for key, footprint in patches.items():
            vertices, faces, error, rejected = clip_patch(triangles, polygons, tree, footprint, anchor)
            maximum_error = max(maximum_error, error)
            discarded += rejected
            if not len(faces):
                continue
            row = rows[key]
            name = row["expected_object_name"] + "_" + path.stem.removeprefix("SM_Terrain_")
            mesh_path = OUT / (name + ".npz")
            color = COLORS[row["material_role"]]
            np.savez_compressed(mesh_path, vertices=vertices, faces=faces, anchor=anchor, colors=np.tile(color, (len(vertices), 1)).astype(np.float32))
            actual_polygons = shapely.polygons((vertices + anchor)[faces, :2])
            area = float(shapely.area(actual_polygons).sum())
            coverage[key] += area
            meshes.append({"name": name, "path": mesh_path.relative_to(ROOT).as_posix(), "sha256": digest(mesh_path), "component_id": key,
                           "feature_id": row["feature_id"], "m1_group": row["m1_group"], "material_role": row["material_role"], "material_color": color,
                           "vertices": len(vertices), "triangles": len(faces), "area_xy_m2": area, "contact_surface": terrain["path"], "visual_lift_m": LIFT,
                           "collision": False, "source_way_id": row["way_id"], "absolute_accuracy_accepted": False, "release_accepted": False})
        terrain_inputs.append({"path": terrain["path"], "sha256": terrain["sha256"]})
    for row in summaries:
        row["mesh_area_m2"] = coverage[row["component_id"]]
        row["missing_terrain_area_m2"] = max(0., row["authoring_area_m2"] - row["mesh_area_m2"])
    record = {"schema_version": 1, "source_manifest": source_path.relative_to(ROOT).as_posix(), "source_manifest_sha256": digest(source_path),
              "source_inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in source_inputs], "exclusion_mesh_inputs": mesh_inputs,
              "terrain_inputs": terrain_inputs, "meshes": meshes, "components": summaries, "withheld_components": withheld,
              "reference_components": [r for r in source["features"] if r["display_mode"] != "surface_patch"],
              "attribution": ["© OpenStreetMap contributors", "Contains information licensed under the Open Government Licence - Vancouver."],
              "licence": "ODbL-1.0 derived source database; OGL Vancouver terrain", "visual_lift_m": LIFT,
              "application_visual_check": "pending", "full_m1_groups_complete": False, "release_accepted": False}
    checks = {"kind": "Numerical source-mesh check, not application test", "meshes": len(meshes), "surface_components": len(patches),
              "withheld_components": len(withheld), "triangles": sum(r["triangles"] for r in meshes), "maximum_terrain_plane_offset_error_m": maximum_error,
              "degenerate_fragments_discarded": discarded, "visual_lift_m": LIFT, "exclusion_overlap_m2": float(occupied.intersection(all_exclusions).area),
              "total_missing_terrain_area_m2": sum(r["missing_terrain_area_m2"] for r in summaries),
              "numerical_pass": maximum_error < 1e-7 and occupied.intersection(all_exclusions).area < 1e-7,
              "absolute_accuracy_accepted": False, "blender_and_runtime_inspection": "pending"}
    save(ROOT / "data/derived/public-spaces/public-space-meshes.json", record)
    save(ROOT / "evidence/public-spaces/mesh-checks.json", checks)
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
