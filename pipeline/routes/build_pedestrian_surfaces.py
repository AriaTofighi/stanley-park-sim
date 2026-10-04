"""Create separate walking surface overlays on the actual exported terrain.

Every generated triangle is clipped to a single existing terrain triangle and
uses that plane plus a 12mm visual lift. These meshes have no collision. The
terrain supplies contact. Bridges, tunnels, stairs and shared cycle facilities
are withheld. This is an inspectable source-based blockout, not survey approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from build_pedestrian_network import ROOT, save, digest

OUT = ROOT / "data/routes/derived/pedestrian-meshes"
COLORS = {"paved_walk": [.40, .38, .33, 1.], "forest_walk": [.30, .23, .15, 1.], "unknown_walk": [.35, .33, .28, 1.]}
LIFT = .012


def main():
    network_path = ROOT / "data/routes/derived/pedestrian-network.json"
    graph = json.loads(network_path.read_text(encoding="utf8"))
    runtime_path = ROOT / "data/derived/paved-circuit-runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf8"))
    # Use the authored triangles, including local width changes and exact seam
    # overlaps. A constant-width reconstruction can erase the adjacent walk lane.
    surface_path = ROOT / "manifests/surface-model.json"
    surface = json.loads(surface_path.read_text(encoding="utf8"))
    pavement_polygons = []
    for row in surface["pavement"]:
        if row["role"] != "pavement":
            continue
        mesh_path = ROOT / row["path"]
        if digest(mesh_path) != row["sha256"]:
            raise ValueError(f"Pavement changed after manifest: {mesh_path}")
        with np.load(mesh_path) as mesh:
            xyz = mesh["vertices"] + mesh["anchor"]
            pavement_polygons.extend(shapely.polygons(xyz[mesh["faces"], :2]))
    bicycle_footprint = shapely.union_all(pavement_polygons).buffer(.025)

    # Water is never painted as a path. Unknown bridge tags cannot silently turn
    # lake-bed DTM samples into walkable surfaces.
    lakes_path = ROOT / "data/derived/lake-surfaces.geojson"
    lakes = json.loads(lakes_path.read_text(encoding="utf8"))
    lake_mask = shapely.union_all([shapely.geometry.shape(f["geometry"]) for f in lakes["features"]])
    footprints, ids = {}, {}
    occupied = bicycle_footprint
    warnings = []
    for category in COLORS:
        selected = [e for e in graph["edges"] if e["walking_type"] == category and e["render_candidate"]]
        ids[category] = [e["edge_id"] for e in selected]
        raw = shapely.union_all([LineString(e["coordinates_local_xy_m"]).buffer(e["width_m"] / 2, cap_style="round", join_style="round") for e in selected])
        footprints[category] = raw.difference(occupied).difference(lake_mask)
        lake_intersection = float(raw.intersection(lake_mask).area)
        if lake_intersection > 0:
            warnings.append({"category": category, "lake_overlap_removed_m2": lake_intersection})
        occupied = occupied.union(footprints[category])

    OUT.mkdir(parents=True, exist_ok=True)
    meshes, inputs = [], []
    max_offset_error, total_degenerate = 0., 0
    for terrain_path in sorted((ROOT / "data/derived/surface-meshes").glob("SM_Terrain_*.npz")):
        with np.load(terrain_path) as package:
            anchor = package["anchor"].astype(float)
            source_vertices = package["vertices"].astype(float) + anchor
            source_faces = package["faces"]
        tris = source_vertices[source_faces]
        triangle_polygons = shapely.polygons(tris[:, :, :2])
        tree = shapely.STRtree(triangle_polygons)
        for category, footprint in footprints.items():
            candidates = tree.query(footprint, predicate="intersects")
            if not len(candidates):
                continue
            fragments = shapely.intersection(triangle_polygons[candidates], footprint)
            vertices, faces, lookup = [], [], {}
            for index, fragment in zip(candidates, fragments):
                a, b, c = tris[index]
                basis = np.column_stack((b[:2] - a[:2], c[:2] - a[:2]))
                if abs(np.linalg.det(basis)) < 1e-12:
                    continue
                inverse = np.linalg.inv(basis)
                for poly in shapely.get_parts(fragment):
                    if not isinstance(poly, Polygon) or poly.area < 1e-8:
                        continue
                    for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(poly)):
                        xy = np.asarray(triangle.exterior.coords)[:3, :2]
                        signed_area = float(np.linalg.det(np.column_stack((xy[1] - xy[0], xy[2] - xy[0]))))
                        if abs(signed_area) < 1e-10:
                            total_degenerate += 1
                            continue
                        if signed_area < 0:
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
                        centre = xy.mean(axis=0)
                        uv_c = inverse @ (centre - a[:2])
                        expected = a[2] + uv_c[0] * (b[2] - a[2]) + uv_c[1] * (c[2] - a[2])
                        max_offset_error = max(max_offset_error, abs(float(z.mean() - expected - LIFT)))
            if not faces:
                continue
            vertices = np.asarray(vertices)
            faces = np.asarray(faces, dtype=np.int32)
            suffix = terrain_path.stem.removeprefix("SM_Terrain_")
            name = f"SM_Pedestrian_{category}_{suffix}"
            path = OUT / f"{name}.npz"
            colors = np.tile(COLORS[category], (len(vertices), 1)).astype(np.float32)
            np.savez_compressed(path, vertices=vertices, faces=faces, colors=colors, anchor=anchor)
            meshes.append({"name": name, "path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "vertices": len(vertices), "triangles": len(faces),
                           "category": category, "material_color": COLORS[category], "collision": False, "contact_surface": terrain_path.relative_to(ROOT).as_posix(),
                           "visual_lift_m": LIFT, "source_edge_ids": ids[category], "release_accepted": False})
        inputs.append({"path": terrain_path.relative_to(ROOT).as_posix(), "sha256": digest(terrain_path)})
        print(terrain_path.stem, "meshes", len(meshes), flush=True)
    record = {"schema_version": 1, "licence": "ODbL-1.0 derived pedestrian database; City terrain under Open Government Licence - Vancouver",
              "attribution": ["© OpenStreetMap contributors", "Contains information licensed under the Open Government Licence - Vancouver."],
              "origin_path": "manifests/world-origin.json", "network_path": network_path.relative_to(ROOT).as_posix(), "network_sha256": digest(network_path),
              "runtime_cycle_path_sha256": digest(runtime_path), "surface_manifest_sha256": digest(surface_path),
              "cycle_exclusion_method": "Actual pavement triangles with a 25 mm display margin",
              "terrain_inputs": inputs, "meshes": meshes, "withheld_edges": [e["edge_id"] for e in graph["edges"] if not e["render_candidate"] or e["walking_type"] == "shared"],
              "release_accepted": False, "notes": ["All widths remain estimates.", "Footbridges, tunnels and stairs are not terrain overlays.", "No collision; existing measured terrain supplies contact.", "Cycling permissions are never inferred from these pedestrian meshes.", "Special structures and source-position conflicts remain open."]}
    save(ROOT / "data/routes/derived/pedestrian-surfaces.json", record)
    checks = {"kind": "numerical_mesh_check_not_application_test", "meshes": len(meshes), "triangles": sum(m["triangles"] for m in meshes),
              "maximum_terrain_plane_offset_error_m": max_offset_error, "visual_lift_m": LIFT, "degenerate_triangles_discarded": total_degenerate,
              "footprint_cycle_overlap_m2": float(shapely.union_all(list(footprints.values())).intersection(bicycle_footprint).area), "water_conflicts": warnings,
              "separate_surface_geometry_pass": max_offset_error < 1e-7, "geographic_accuracy_pass": False, "application_visual_check": "pending"}
    save(ROOT / "evidence/pedestrian-surfaces-checks.json", checks)
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
