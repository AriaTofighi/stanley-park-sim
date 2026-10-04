"""Make editable route ribbons from source polylines; retain all uncertainty."""
from pathlib import Path
import hashlib
import json
import math
import runpy
import numpy as np
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene
source_path = ROOT / "data/routes/derived/park_routes.json"
data = json.loads(source_path.read_text(encoding="utf-8"))
surface_manifest = json.loads((ROOT / "manifests/surface-model.json").read_text())
surface_samples = json.loads((ROOT / "data/derived/route-surface-samples.json").read_text())
source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
if surface_manifest["route_source_sha256"] != source_hash or surface_samples["route_source_sha256"] != source_hash:
    raise RuntimeError("Surface meshes use a different route source")
surface_meshes = {item["edge_id"]: item for item in surface_manifest["routes"]}
surface_points = {item["edge_id"]: item["xyz_local_m"] for item in surface_samples["edges"]}
if hashlib.sha256((ROOT / data["origin_path"]).read_bytes()).hexdigest() != data["origin_sha256"]:
    raise RuntimeError("Route and terrain origins differ. Rebuild the route data.")
def prepare_gate_zones(paved):
    """Validate guides before changing the scene or writing runtime data."""
    gate_path = ROOT / 'manifests/maze-gate-blockouts.json'
    gate_data = json.loads(gate_path.read_text(encoding='utf8'))
    if not gate_data['checks_pass']:
        raise ValueError('Physical gate walking paths have not passed geometric clearance')
    inputs = {row['path']: row['sha256'] for row in gate_data['inputs']}
    if 'data/derived/paved-circuit-runtime.json' not in inputs:
        raise ValueError('Physical gate package has no pavement provenance')
    for relative, expected in inputs.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Stale physical gate input: {relative}. Rebuild the gate package.')
    source = np.asarray(paved['chainage_source_m'], dtype=float)
    runtime = np.asarray(paved['chainage_runtime_m'], dtype=float)
    points = np.asarray(paved['points_local_m'], dtype=float)
    if (source.ndim != 1 or len(source) < 2 or runtime.shape != source.shape
            or points.shape != (len(source), 3) or not np.isfinite(points).all()
            or not np.isfinite(source).all() or not np.isfinite(runtime).all()
            or np.any(np.diff(source) <= 0) or np.any(np.diff(runtime) <= 0)):
        raise ValueError('Invalid source/runtime pavement chainage')
    geometric_length = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    if np.max(np.abs(runtime - geometric_length)) > 1e-4:
        raise ValueError('Runtime chainage does not match the exported 3D polyline')
    sites = {row['id']: row for row in gate_data['sites']}
    zones = []
    for name, gate_id, original_start, end in [
            ("Lumberman's Arch", 'Lumberman', 3170., 3268.),
            ('Prospect Point', 'Prospect', 4698., 4784.),
            ('Third Beach', 'ThirdBeach', 6684., 6714.)]:
        site = sites[gate_id]
        guide = site['walking_path']
        guide_points = np.asarray(guide['points_local_m'], dtype=float)
        stations = np.asarray(guide['source_stations_m'], dtype=float)
        first, last = guide['first_source_m'], guide['last_source_m']
        start = min(original_start, first - 2.)
        if (stations.ndim != 1 or len(stations) < 2
                or guide_points.shape != (len(stations), 3)
                or not np.isfinite(guide_points).all() or not np.isfinite(stations).all()
                or np.any(np.diff(stations) <= 0)
                or not np.isfinite([start, end, first, last]).all()
                or not source[0] <= start <= first < last <= end <= source[-1]
                or abs(stations[0] - first) > 1e-6 or abs(stations[-1] - last) > 1e-6):
            raise ValueError(f'Invalid or out-of-range physical gate guide: {gate_id}')
        for point, station in [(guide_points[0], first), (guide_points[-1], last)]:
            expected = np.array([np.interp(station, source, points[:, axis]) for axis in range(3)])
            if np.linalg.norm(point - expected) > .001:
                raise ValueError(f'Gate guide is detached from the main path: {gate_id}')
        margin = float(site['checks']['minimum_contact_margin_m'])
        radius = float(site['checks']['capsule_radius_m'])
        if not site['checks']['body_clear'] or not math.isfinite(margin) or margin <= .02 or abs(radius - .32) > 1e-6:
            raise ValueError(f'Gate clearance does not support the current 32 cm capsule: {gate_id}')
        zones.append(dict(name=name, guide_id=gate_id,
            start_cm=float(np.interp(start, source, runtime) * 100),
            end_cm=float(np.interp(end, source, runtime) * 100),
            source_start_m=start, source_end_m=end, survey_accepted=False,
            source_original_start_m=original_start,
            start_policy='Approximate development limit extended to allow safe guide entry; not a surveyed sign location',
            guide_start_cm=float(np.interp(first, source, runtime) * 100),
            guide_end_cm=float(np.interp(last, source, runtime) * 100),
            guide_source_start_m=first, guide_source_end_m=last,
            guide_capsule_radius_cm=radius * 100,
            guide_clearance_margin_cm=margin * 100,
            guide_tracking_limit_cm=(margin - .02) * 100,
            guide_tracking_policy='Planar guide distance; retain 2 cm of the geometric contact margin. Does not validate the visible bicycle envelope.',
            guide_points=[[round(p[1] * 100, 4), round(p[0] * 100, 4), round(p[2] * 100, 4)] for p in guide_points],
            evidence='2025 engineering report existing conditions, 2022 orthophoto; estimated gate geometry and approximate development limits, current sign-end survey pending'))
    return zones, hashlib.sha256(gate_path.read_bytes()).hexdigest()


def pavement_triangle_key(triangle):
    """Canonical world-metre key; ignore winding but not geometric position."""
    return tuple(sorted(tuple(row) for row in np.round(triangle, 9)))


def prepare_pavement_face_ownership(items, project_root):
    """Remove only repeated top faces, retaining the first named chunk owner.

    The 1 nm hash grid finds candidates. A separate 2 pm coordinate comparison
    permits only float64 anchor-addition roundoff; distinct overlapping faces
    and quantization-key collisions are retained. Support faces are untouched.
    """
    owners = {}
    prepared = {}
    duplicate_records = []
    mesh_records = []
    input_count = 0
    for item in sorted(items, key=lambda row: row['name']):
        path = project_root / item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Pavement hash mismatch: ' + item['name'])
        with np.load(path) as package:
            vertices = package['vertices'].copy()
            faces = package['faces'].copy()
            anchor = package['anchor'].copy()
        keep = []
        if item['role'] == 'pavement':
            world = vertices + anchor
            input_count += len(faces)
            for face_index, face in enumerate(faces):
                triangle = world[face]
                key = pavement_triangle_key(triangle)
                ordered = np.array(sorted(map(tuple, triangle)))
                match = next((owner for owner in owners.get(key, [])
                              if np.max(np.abs(ordered-owner['coordinates'])) <= 2e-12), None)
                if match is not None:
                    duplicate_records.append(dict(
                        removed_mesh=item['name'], removed_source_face=face_index,
                        retained_mesh=match['mesh'], retained_source_face=match['face'],
                        maximum_world_vertex_difference_m=float(np.max(np.abs(ordered-match['coordinates']))),
                        centre_local_m=triangle.mean(axis=0).tolist()))
                    continue
                owner = dict(mesh=item['name'], face=face_index, coordinates=ordered)
                owners.setdefault(key, []).append(owner)
                keep.append(face_index)
            faces = faces[keep]
            # Compact unused seam vertices without moving any retained point.
            used, remap = np.unique(faces, return_inverse=True)
            vertices = vertices[used]
            faces = remap.reshape(-1, 3)
            mesh_records.append(dict(mesh=item['name'], source_triangles=item['triangles'],
                                     authored_triangles=len(faces), removed_triangles=item['triangles']-len(faces),
                                     source_path=item['path'], source_sha256=item['sha256']))
        prepared[item['name']] = dict(vertices=vertices, faces=faces, anchor=anchor)
    # Validate the retained set independently; a key collision alone is not
    # sufficient evidence that two different triangles are the same surface.
    checked = {}
    retained_count = 0
    for item in sorted(items, key=lambda row: row['name']):
        if item['role'] != 'pavement':
            continue
        package = prepared[item['name']]
        world = package['vertices'] + package['anchor']
        for triangle in world[package['faces']]:
            key = pavement_triangle_key(triangle)
            ordered = np.array(sorted(map(tuple, triangle)))
            if any(np.max(np.abs(ordered-old)) <= 2e-12 for old in checked.get(key, [])):
                raise RuntimeError('Repeated pavement triangle remains after ownership assignment')
            checked.setdefault(key, []).append(ordered)
            retained_count += 1
    if retained_count + len(duplicate_records) != input_count:
        raise RuntimeError('Pavement triangle ownership count does not balance')
    report = dict(method='Global canonical world-metre triangle ownership, lexicographic mesh order',
                  key_decimal_places=9, equality_roundoff_limit_m=2e-12,
                  scope='Pavement top faces only; support faces and source NPZ files unchanged',
                  source_triangles=input_count, retained_triangles=retained_count,
                  removed_duplicate_triangles=len(duplicate_records), duplicates=duplicate_records,
                  meshes=mesh_records, each_retained_triangle_has_one_owner=True,
                  non_identical_overlap_removed=False, live_acceptance=False)
    return prepared, report


paved = json.loads((ROOT / 'data/derived/paved-circuit-runtime.json').read_text())
zones, gate_hash = prepare_gate_zones(paved)
prepared_pavement, pavement_ownership = prepare_pavement_face_ownership(surface_manifest['pavement'], ROOT)
seam_helper = runpy.run_path(str(ROOT / 'pipeline/blender/pavement_seam_support.py'))
seam_support, seam_context = seam_helper['prepare'](
    ROOT, prepared_pavement, surface_manifest['pavement'], paved)

target = bpy.data.collections.get("SP_03_RouteBlockout")
if target is None:
    target = bpy.data.collections.new("SP_03_RouteBlockout")
    scene.collection.children.link(target)
for obj in list(target.objects):
    if obj.get("pipeline_owner") == "routes":
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def make_material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.9
    return mat


materials = {
    "circuit": make_material("M_CircuitBlockout", (0.8, 0.51, 0.11)),
    "branch": make_material("M_BranchBlockout", (0.30, 0.39, 0.42)),
    "review": make_material("M_RouteHeightReview", (0.70, 0.24, 0.15)),
    "asphalt": make_material("M_PavementAsphalt", (.105,.11,.115)),
    "support": make_material("M_PavementSupport", (.29,.28,.25)),
}
main_ids = {part["edge_id"] for part in data["main_circuit"]["ordered_edges"]}
runtime_routes = []
records = []


def runtime_points(points):
    return [[round(p[1] * 100, 4), round(p[0] * 100, 4), round((p[2] + 0.06) * 100, 4)] for p in points]


for edge in data["edges"]:
    if edge["missing_height_samples"]:
        records.append({"edge_id": edge["edge_id"], "status": "not_meshed_missing_height"})
        continue
    if edge['edge_id'] in main_ids:
        # The circuit now uses its independent measured-fit pavement below.
        # Do not keep an old strip on the approximate City line beside it.
        continue
    points = []
    for value in surface_points[edge["edge_id"]]:
        point = Vector(value)
        if not points or (point.xy - points[-1].xy).length > 0.01:
            points.append(point)
    if len(points) < 2:
        continue
    surface_item = surface_meshes[edge["edge_id"]]
    package_path = ROOT / surface_item["path"]
    if hashlib.sha256(package_path.read_bytes()).hexdigest() != surface_item["sha256"]:
        raise RuntimeError(f"Route mesh changed: {package_path.name}")
    package = np.load(package_path)
    anchor = Vector(package["anchor"])
    vertices, faces = package["vertices"].tolist(), package["faces"].tolist()
    mesh = bpy.data.meshes.new(f"SM_Route_{edge['source_object_id']}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    obj.location = anchor
    target.objects.link(obj)
    review = edge["unresolved_cliff_height"] or edge["maximum_raw_sample_grade"] > 0.18
    mat_key = "review" if review else "circuit" if edge["edge_id"] in main_ids else "branch"
    mesh.materials.append(materials[mat_key])
    obj["pipeline_owner"] = "routes"
    # The measured terrain is the single contact surface until path engineering
    # is accepted. A coloured unsurveyed review strip is not a second collider.
    obj["collision"] = "none"
    obj["source_id"] = edge["edge_id"]
    obj["surveyed_width"] = False
    obj["development_width_m"] = 3.0
    obj["path_height_survey"] = False
    obj["surface_alignment"] = "Clipped to shared terrain triangles; 0.06m display offset"
    obj["access_notes"] = json.dumps(edge["restrictions"])
    obj["collision_ready"] = False
    obj["source_sha256"] = data["source_sha256"]
    records.append({"edge_id": edge["edge_id"], "mesh": obj.name,
                    "width_status": "3m development proxy, unsurveyed",
                    "raw_max_grade": edge["maximum_raw_sample_grade"],
                    "collision": obj["collision"], "release_accepted": False})
    runtime_routes.append({"id": edge["edge_id"], "name": edge["name"], "closed": False,
                           "cycling": edge["mode"] == "ride", "points": runtime_points(points),
                           "access_status": "under_review", "restrictions": edge["restrictions"]})

for item in surface_manifest['pavement']:
    package=prepared_pavement[item['name']]
    mesh=bpy.data.meshes.new(item['name']);mesh.from_pydata(package['vertices'].tolist(),[],package['faces'].tolist());mesh.update()
    obj=bpy.data.objects.new(item['name'],mesh);target.objects.link(obj);obj.location=package['anchor']
    mesh.materials.append(materials['asphalt' if item['role']=='pavement' else 'support'])
    obj['pipeline_owner']='routes';obj['collision']=item['collision']
    obj['source_id']='2022 measured ground fit; see paved-circuit-proposal.json and pavement-review-overrides.json'
    obj['surveyed_width']=False;obj['collision_ready']=True;obj['release_accepted']=False
    records.append(dict(mesh=obj.name,collision=obj['collision'],role=item['role'],release_accepted=False))

seam_object = bpy.data.objects[seam_support['mesh']]
seam_helper['inspect_authored'](seam_support, seam_context,
    np.array([tuple(vertex.co) for vertex in seam_object.data.vertices]) + np.array(seam_object.location),
    np.array(seam_object.location))
seam_object['source_id'] += '; bounded closing-seam backing: evidence/blender-pavement-closing-seam-support.json'
seam_object['seam_support_control_index'] = seam_support['trigger_control_index']

# Inspect the authored Blender triangles as well as the prepared float64 data.
# Blender stores mesh coordinates as floats; no exact duplicate may reappear.
authored_pavement_keys = set()
authored_pavement_count = 0
for item in surface_manifest['pavement']:
    if item['role'] != 'pavement':
        continue
    obj = bpy.data.objects[item['name']]
    world_vertices = np.array([tuple(vertex.co) for vertex in obj.data.vertices]) + np.array(obj.location)
    for polygon in obj.data.polygons:
        if len(polygon.vertices) != 3:
            raise RuntimeError('Authored pavement contains a non-triangle')
        key = pavement_triangle_key(world_vertices[list(polygon.vertices)])
        if key in authored_pavement_keys:
            raise RuntimeError('An exact repeated pavement triangle exists in the authored scene')
        authored_pavement_keys.add(key)
        authored_pavement_count += 1
if authored_pavement_count != pavement_ownership['retained_triangles']:
    raise RuntimeError('Authored pavement triangle count differs from the prepared ownership set')
pavement_ownership['authored_blender_triangle_count'] = authored_pavement_count
pavement_ownership['authored_blender_uniqueness_pass'] = True

main_points = paved['points_local_m']
main_engine_points=[[round(p[1]*100,4),round(p[0]*100,4),round(p[2]*100,4)] for p in main_points]
runtime_routes.insert(0, {"id": "main_circuit", "name": "Stanley Park counter-clockwise circuit",
                          "closed": True, "cycling": True, "points": main_engine_points,
                          "access_status": "walk_zone_limits_under_review"})
spawn = main_engine_points[0]
first, second = runtime_routes[0]["points"][:2]
yaw = math.degrees(math.atan2(second[1] - first[1], second[0] - first[0]))
world_data = {"schema_version": 1, "coordinate_contract": "unreal_north_east_up_cm",
              "status": "M1 blockout; source-supported circuit, surveyed widths/heights and dismount limits pending",
              "routes": runtime_routes, "spawn": spawn, "spawn_yaw": yaw,
              "route_source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
              "origin_sha256": data["origin_sha256"], "random_seed": 101}
world_data['walk_zones']=zones
world_data['maze_gate_source_sha256']=gate_hash
world_data['status']='Paved survey-based development circuit. Lane bounds, tunnel interiors and walk-zone endpoints await independent acceptance.'
output = ROOT / "unreal/Content/WorldData"
output.mkdir(parents=True, exist_ok=True)
(output / "world.json").write_text(json.dumps(world_data, indent=2), encoding="utf-8")
(ROOT / "manifests/blender-routes.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
(ROOT / "evidence/blender-pavement-face-ownership.json").write_text(json.dumps(pavement_ownership, indent=2)+'\n', encoding='utf8')
(ROOT / 'evidence/blender-pavement-closing-seam-support.json').write_text(json.dumps(seam_support, indent=2)+'\n', encoding='utf8')
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        area.spaces.active.clip_start = 5
        area.spaces.active.clip_end = 100000
        area.spaces.active.region_3d.view_perspective = "ORTHO"
        area.spaces.active.region_3d.view_distance = 6000
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "blender/StanleyPark_Blockout.blend"))
result = {"route_meshes": len(target.objects), "runtime_routes": len(runtime_routes),
          "circuit_metres": data["main_circuit"]["length_m"], "release_accepted": False,
          "removed_duplicate_pavement_triangles": pavement_ownership['removed_duplicate_triangles'],
          "pavement_triangle_ownership_pass": pavement_ownership['each_retained_triangle_has_one_owner'],
          "closing_seam_support_blender_pass": seam_support['live_blender_verified']}
