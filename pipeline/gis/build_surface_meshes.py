"""Build one shared measured surface for terrain and route review ribbons.

The 2013 DTM and City route centre lines stay immutable. This repairs mesh
alignment; it does not resolve outdated data, widths, cliff traces or underpasses.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import Delaunay
import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from acquire_sources import save_json, digest
from paved_surfaces import load_profile,terrain_opening,build_pavement
from landmark_terrain import cut_landmark_terrain, registered_openings
from refine_prospect_terrain import refine_samples
from refine_nature_house_terrain import refine_samples as refine_nature_house_samples
from junction_terrain_transition import JunctionTerrainTransition
from pavement_terrain_contact import PavementTerrainContact
from lumberman_terrain_transition import LumbermanTerrainTransition

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/derived/surface-meshes"
OUT.mkdir(parents=True, exist_ok=True)
grid_path = ROOT / "data/derived/terrain_2022_park.npz"
routes_path = ROOT / "data/routes/derived/park_routes.json"
grid = np.load(grid_path)
routes = json.loads(routes_path.read_text())
edges = [e for e in routes["edges"] if not e["missing_height_samples"]]
corridor = unary_union([LineString(e["coordinates_local_xy_m"]).buffer(14) for e in edges])
profile,paved_points,paved_normal,paved_displacement=load_profile()
corridor=shapely.union_all([corridor,LineString(paved_points[:,:2]).buffer(10)])
xx, yy = np.meshgrid(grid["x"], grid["y"])
select = np.zeros(xx.shape, dtype=bool)
select[::4, ::4] = True
select[0, :] = select[-1, :] = select[:, 0] = select[:, -1] = True
select |= shapely.contains_xy(corridor, xx, yy)
select &= np.isfinite(grid["z"])
xyz = np.column_stack((xx[select], yy[select], grid["z"][select])).astype(np.float64)
inside = grid["inside_park"][select]
xyz, inside, prospect_refinement = refine_samples(ROOT, xyz, inside)
xyz, inside, nature_house_refinement = refine_nature_house_samples(ROOT, xyz, inside)
del xx, yy, select
print("Triangulating measured samples", len(xyz), flush=True)
tin = Delaunay(xyz[:, :2])
faces = tin.simplices.copy()
edge_max = np.max(np.linalg.norm(xyz[faces, :2] - np.roll(xyz[faces, :2], 1, axis=1), axis=2), axis=1)
# A missing-data hole must not become a giant invented triangle.
valid_triangles = edge_max <= 15
faces = faces[valid_triangles]
source_indices = np.flatnonzero(valid_triangles)
centres = xyz[faces, :2].mean(axis=1)
cells = np.floor((centres - [grid["x"][0], grid["y"][0]]) / 512).astype(np.int32)
colors = np.tile([.24, .27, .24, 1.], (len(xyz), 1)).astype(np.float32)
colors[inside] = [.20, .29, .13, 1.]
colors[xyz[:, 2] < 2] = [.42, .40, .32, 1.]

def original_surface_z(points):
    xy = np.asarray(points)[:, :2]
    simplex = tin.find_simplex(xy)
    if np.any(simplex < 0) or not np.all(valid_triangles[simplex]):
        raise RuntimeError("Route samples cross a missing-data triangle")
    weights = np.einsum("ijk,ik->ij", tin.transform[simplex, :2], xy - tin.transform[simplex, 2])
    weights = np.column_stack((weights, 1-weights.sum(axis=1)))
    return np.sum(xyz[tin.simplices[simplex], 2] * weights, axis=1)

render_xyz,render_faces,render_colors=terrain_opening(xyz,faces,colors,tin,source_indices,paved_points,paved_normal,profile['width_m'])
render_xyz,render_faces,render_colors,landmark_cuts=cut_landmark_terrain(ROOT,render_xyz,render_faces,render_colors)
# Exact clipping at a source vertex can return a zero-area polygon triangle.
# It must not become a mesh face or hide an edge from the boundary stitch.
triangles = render_xyz[render_faces]
projected_cross = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])[:,2]
degenerate_cut_faces = int((abs(projected_cross) < 1e-10).sum())
render_faces = render_faces[abs(projected_cross) >= 1e-10]
del triangles, projected_cross
junction_transition = JunctionTerrainTransition(ROOT, paved_points, paved_normal, profile, original_surface_z)
render_xyz, render_faces, render_colors, junction_transition_report = junction_transition.apply(render_xyz, render_faces, render_colors)
lumberman_transition=LumbermanTerrainTransition(ROOT)
render_xyz,render_faces,render_colors,lumberman_transition_report=lumberman_transition.apply(render_xyz,render_faces,render_colors)
lumberman_transition.bind_rendered_terrain(render_xyz,render_faces)

def surface_z(points):
    # Support bottoms must follow the corrected boundary, or their former tops
    # could remain as an invisible obstacle beside the lowered terrain edge.
    def fallback(values):
        return original_surface_z(values) + junction_transition.offset(np.asarray(values)[:, :2])
    return lumberman_transition.sample_heights(points,fallback)

centres=render_xyz[render_faces,:2].mean(axis=1)
cells=np.floor((centres-[grid['x'][0],grid['y'][0]])/512).astype(np.int32)
tiles = []
for col, row in sorted(set(map(tuple, cells))):
    selection = render_faces[(cells[:, 0] == col) & (cells[:, 1] == row)]
    indices, local_faces = np.unique(selection, return_inverse=True)
    anchor = [float(grid["x"][0] + col * 512), float(grid["y"][0] + row * 512), 0.]
    name = f"SM_Terrain_{row:02d}_{col:02d}"
    path = OUT / f"{name}.npz"
    np.savez_compressed(path, vertices=render_xyz[indices] - anchor, faces=local_faces.reshape(-1, 3),
                        colors=render_colors[indices], anchor=anchor)
    tiles.append(dict(name=name, path=path.relative_to(ROOT).as_posix(), sha256=digest(path),
                      vertices=len(indices), triangles=len(selection)))
print("Terrain tiles", len(tiles), "triangles", len(faces), flush=True)

# Intersect each route footprint with the actual terrain triangles. Every output
# face lies in one terrain face's plane. No independent ribbon triangulation can
# cut through the terrain between sampled vertices.
polygons = shapely.polygons(xyz[faces, :2])
tree = shapely.STRtree(polygons)
route_meshes, height_records = [], []
max_offset_error = 0.
junction_overlay_report = None
main_edge_ids={item['edge_id'] for item in routes['main_circuit']['ordered_edges']}
half_width=profile['width_m'][:,None]*.5
right_xy=paved_points[:,:2]-paved_normal*half_width
left_xy=paved_points[:,:2]+paved_normal*half_width
paved_footprint=shapely.union_all(shapely.make_valid([
    Polygon([right_xy[i],right_xy[i+1],left_xy[i+1],left_xy[i]])
    for i in range(len(paved_points)-1)]))
replacement_footprint=shapely.union_all([row[1] for row in registered_openings(ROOT)])
for edge in edges:
    footprint = LineString(edge["coordinates_local_xy_m"]).buffer(1.5, cap_style="flat", join_style="mitre")
    # A visual branch ribbon must end at the paved lane edge. It must not float
    # across the engineered lane or hide its continuous asphalt at junctions.
    if edge['edge_id'] not in main_edge_ids:
        footprint=footprint.difference(paved_footprint)
    # The named floor/deck is authoritative inside these cuts. An old DTM
    # ribbon must not span an open passage or float above its lower floor.
    footprint=footprint.difference(replacement_footprint)
    candidates = tree.query(footprint, predicate="intersects")
    pieces = shapely.intersection(polygons[candidates], footprint)
    vertices, route_faces, lookup = [], [], {}
    anchor = np.array([*edge["coordinates_local_xy_m"][0][:2], 0.])
    for candidate, piece in zip(candidates, pieces):
        if piece.is_empty or piece.area < 1e-9:
            continue
        simplex = source_indices[candidate]
        for fragment in shapely.get_parts(piece):
            if not isinstance(fragment, Polygon) or fragment.area < 1e-9:
                continue
            for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(fragment)):
                xy = np.asarray(tri.exterior.coords)[:3, :2]
                cross = np.cross(np.append(xy[1]-xy[0], 0), np.append(xy[2]-xy[0], 0))[2]
                if abs(cross) < 1e-9:
                    continue
                if cross < 0:
                    xy = xy[::-1]
                weights2 = (tin.transform[simplex, :2] @ (xy-tin.transform[simplex, 2]).T).T
                weights = np.column_stack((weights2, 1-weights2.sum(axis=1)))
                height = weights @ xyz[tin.simplices[simplex], 2] + .06
                face = []
                for point in np.column_stack((xy, height)):
                    key = tuple(np.round(point, 6))
                    if key not in lookup:
                        lookup[key] = len(vertices)
                        vertices.append(point-anchor)
                    face.append(lookup[key])
                route_faces.append(face)
    if not route_faces:
        raise RuntimeError(f"No route surface for {edge['edge_id']}")
    vertices = np.asarray(vertices)
    route_faces = np.asarray(route_faces, dtype=np.int32)
    if edge['edge_id'] == junction_transition.settings['branch_id']:
        world_vertices, route_faces, junction_overlay_report = junction_transition.refit_overlay(
            vertices+anchor, route_faces, render_xyz, render_faces, lift=.06)
        vertices = world_vertices-anchor
        offset_error = junction_overlay_report['actual_terrain_plane_max_error_m']
    else:
        probes = (vertices[route_faces].mean(axis=1) + anchor)
        offset_error = float(np.max(np.abs(probes[:, 2] - original_surface_z(probes) - .06)))
    world_vertices,route_faces,lumberman_overlay_report=lumberman_transition.refit_overlay(vertices+anchor,route_faces,lift=.06)
    if lumberman_overlay_report['affected']:
        vertices=world_vertices-anchor
        offset_error=lumberman_overlay_report['actual_terrain_plane_max_error_m']
    max_offset_error = max(max_offset_error, offset_error)
    if offset_error > .0001:
        raise RuntimeError(f"Route/terrain mismatch: {edge['edge_id']} {offset_error} m")
    name = f"SM_Route_{edge['source_object_id']}"
    path = OUT / f"{name}.npz"
    np.savez_compressed(path, vertices=vertices, faces=route_faces, anchor=anchor)
    route_meshes.append(dict(edge_id=edge["edge_id"], name=name, path=path.relative_to(ROOT).as_posix(),
                             sha256=digest(path), vertices=len(vertices), triangles=len(route_faces),
                             pavement_overlap_removed=edge['edge_id'] not in main_edge_ids,
                             replacement_footprints_removed=True,lumberman_overlay=lumberman_overlay_report,
                             display_offset_m=.06, clearance_error_m=offset_error))
    points = np.asarray(edge["xyz_local_m"], dtype=float)
    points[:, 2] = surface_z(points)
    height_records.append(dict(edge_id=edge["edge_id"], xyz_local_m=points.tolist()))
    print(name, len(vertices), len(route_faces), flush=True)

terrain_contact=PavementTerrainContact(render_xyz,render_faces)
pavement=build_pavement(paved_points,paved_normal,profile,paved_displacement,surface_z,OUT,terrain_contact=terrain_contact)
main = np.asarray(routes["main_circuit"]["xyz_local_m"], dtype=float)
main[:, 2] = surface_z(main)
save_json(ROOT / "data/derived/route-surface-samples.json", dict(
    route_source_sha256=digest(routes_path), terrain_source_sha256=digest(grid_path),
    status="Shared rendered surface samples; source route geometry still under review",
    edges=height_records, main_circuit=main.tolist()))
save_json(ROOT / "manifests/surface-model.json", dict(schema_version=1,
    origin_sha256=digest(ROOT / "manifests/world-origin.json"),
    route_source_sha256=digest(routes_path), terrain_source_sha256=digest(grid_path),
    sampling=dict(corridor_radius_m=14, corridor_grid_m=2, other_grid_m=8,
                  source_grid_m=2, tile_size_m=512, method="Delaunay; shared triangle clipping"),
    route_width_m=3, width_surveyed=False, heights_survey_accepted=False,
    terrain=tiles, routes=route_meshes, pavement=pavement, landmark_cuts=landmark_cuts,
    prospect_refinement=prospect_refinement,nature_house_refinement=nature_house_refinement,
    junction_transition=junction_transition_report,
    junction_overlay=junction_overlay_report,
    lumberman_transition=lumberman_transition_report,
    pavement_support_contact=dict(method='Split at actual retained terrain triangle planes',
        split_segments=terrain_contact.split_segments,maximum_boundary_distance_m=terrain_contact.maximum_boundary_distance),
    numerical_checks=dict(
        all_shared_route_faces_clear_ground=True, maximum_offset_error_m=max_offset_error,
        degenerate_cut_faces_removed=degenerate_cut_faces,
        terrain_vertices=len(xyz), terrain_triangles=len(faces), terrain_tiles=len(tiles))))
print("Surface build complete; this is alignment acceptance only", max_offset_error, flush=True)
rng = np.random.default_rng(101)
controls = []
for tile in tiles:
    package = np.load(ROOT / tile["path"])
    indices = rng.choice(len(package["faces"]), size=min(40, len(package["faces"])), replace=False)
    controls.extend((package["vertices"][package["faces"][indices]].mean(axis=1) + package["anchor"]).tolist())
save_json(ROOT / "data/derived/surface-control-points.json", dict(seed=101,
    method="40 triangle centroids per terrain section",
    surface_manifest_sha256=digest(ROOT / "manifests/surface-model.json"), points_local_m=controls))
