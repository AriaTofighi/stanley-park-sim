"""Build original tree meshes and a bounded, source-backed placement sidecar.

Run in the saved Seawall working copy. This script does not save the blend,
change the M1 mesh data, or run the application. No third-party assets are used.
"""
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
OWNER = "seawall_trees"
SETTINGS = ROOT / "manifests/seawall-tree-settings.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


# Reload source helpers because the Blender MCP process is persistent.
import importlib
import sys
sys.path.insert(0, str(Path(__file__).parent))
import seawall_tree_geometry
import seawall_tree_textures
import seawall_tree_impostors
import seawall_tree_support
importlib.reload(seawall_tree_geometry)
importlib.reload(seawall_tree_textures)
importlib.reload(seawall_tree_impostors)
importlib.reload(seawall_tree_support)
Geometry = seawall_tree_geometry.Geometry
tree_geometry = seawall_tree_geometry.tree_geometry


def nearest_segments(point, a, b):
    delta = b - a
    t = np.clip(np.einsum("ij,ij->i", point - a, delta) / np.maximum(np.einsum("ij,ij->i", delta, delta), 1e-12), 0, 1)
    distances = np.linalg.norm(point - (a + t[:, None] * delta), axis=1)
    return distances, t


class Clearance:
    def __init__(self, scene, network):
        self.cells = defaultdict(list)
        self.names = []
        for obj in scene.objects:
            if obj.type != "MESH" or not obj.name.startswith(("SM_Pavement_", "SM_Pedestrian_", "SM_Route_")):
                continue
            obj.data.calc_loop_triangles()
            points = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
            self.names.append(obj.name)
            for face in obj.data.loop_triangles:
                tri = points[list(face.vertices)]
                self.insert(tri)
        if not any(n.startswith("SM_Pavement_") for n in self.names):
            raise RuntimeError("The working scene has no paved route meshes")
        # Include mapped walks that do not yet have a visible overlay.
        for edge in network["edges"]:
            xyz = np.asarray(edge["xyz_local_m"])
            half = edge["width_m"] / 2 + edge.get("width_uncertainty_m", 0)
            for a, b in zip(xyz[:-1], xyz[1:]):
                delta = b[:2] - a[:2]
                length = np.linalg.norm(delta)
                if length < 1e-6 or not np.isfinite([a, b]).all():
                    continue
                n = np.array([-delta[1], delta[0], 0]) / length * half
                self.insert(np.array([a - n, b - n, b + n]))
                self.insert(np.array([a - n, b + n, a + n]))

    def insert(self, tri):
        low = np.floor(tri[:, :2].min(0) / 20).astype(int)
        high = np.floor(tri[:, :2].max(0) / 20).astype(int)
        for x in range(low[0], high[0] + 1):
            for y in range(low[1], high[1] + 1):
                self.cells[x, y].append(tri)

    def crown_floor(self, point, radius, cfg):
        low = np.floor((point-radius-1)/20).astype(int)
        high = np.floor((point+radius+1)/20).astype(int)
        triangles = [t for x in range(low[0],high[0]+1) for y in range(low[1],high[1]+1)
                     for t in self.cells[x,y]]
        if not triangles:
            return -1e6
        triangles = np.asarray(triangles)
        a, b = triangles[:,:,:2], np.roll(triangles[:,:,:2],-1,axis=1)
        d = b-a
        cross = d[:,:,0]*(point[1]-a[:,:,1])-d[:,:,1]*(point[0]-a[:,:,0])
        inside = (cross.min(1)>=0)|(cross.max(1)<=0)
        distance, _ = nearest_segments(point,a.reshape(-1,2),b.reshape(-1,2))
        distance = distance.reshape(-1,3).min(1)
        distance[inside]=0
        overlap = triangles[distance<radius]
        return float(overlap[:,:,2].max()+cfg["rider_clearance_m"]) if len(overlap) else -1e6

    def blocked(self, point, base, height, radius, cfg):
        low = np.floor((point - radius - 1) / 20).astype(int)
        high = np.floor((point + radius + 1) / 20).astype(int)
        triangles = [t for x in range(low[0], high[0] + 1) for y in range(low[1], high[1] + 1) for t in self.cells[x, y]]
        if not triangles:
            return None
        triangles = np.asarray(triangles)
        a, b = triangles[:, :, :2], np.roll(triangles[:, :, :2], -1, axis=1)
        d = b - a
        cross = d[:, :, 0] * (point[1] - a[:, :, 1]) - d[:, :, 1] * (point[0] - a[:, :, 0])
        inside = (cross.min(1) >= 0) | (cross.max(1) <= 0)
        distance, _ = nearest_segments(point, a.reshape(-1, 2), b.reshape(-1, 2))
        distance = distance.reshape(-1, 3).min(1)
        distance[inside] = 0
        # Conservative bound for the root flare and stem in all variants.
        if np.any(distance < radius * .22 + cfg["trunk_margin_m"]):
            return "stem_clearance"
        low_branch = base + height * cfg["lower_branch_height_fraction"]
        if np.any((distance < radius) & (triangles[:, :, 2].max(1) + cfg["rider_clearance_m"] > low_branch)):
            return "low_branch_clearance"
        return None


def make_object(name, geometry, collection, materials, position=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(geometry.vertices, [], geometry.faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        uv.data[loop.index].uv = geometry.uvs[loop.vertex_index]
    for material in materials:
        mesh.materials.append(material)
    for polygon, slot in zip(mesh.polygons, geometry.slots):
        polygon.material_index = slot
        polygon.use_smooth = slot != 1
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = position
    obj["pipeline_owner"], obj["kit_asset"], obj["collision"] = OWNER, True, "none"
    return obj


def export_object(obj, directory, scene):
    path = directory / (obj.name + ".fbx")
    mesh = obj.data.copy()
    mesh.transform(Matrix.Rotation(-math.pi / 2, 4, "Z"))
    temporary = bpy.data.objects.new("SW_ExportTemporary", mesh)
    scene.collection.objects.link(temporary)
    bpy.ops.object.select_all(action="DESELECT")
    temporary.select_set(True)
    bpy.context.view_layer.objects.active = temporary
    try:
        bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={"MESH"},
            use_mesh_modifiers=True, mesh_smooth_type="FACE", use_triangles=True,
            use_space_transform=False, axis_forward="Y", axis_up="Z", global_scale=1.0,
            apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", bake_space_transform=True,
            bake_anim=False, add_leaf_bones=False, path_mode="STRIP", use_custom_props=False, colors_type="LINEAR")
    finally:
        bpy.data.objects.remove(temporary, do_unlink=True)
        bpy.data.meshes.remove(mesh)
    values = np.asarray([(v.co.y * 100, v.co.x * 100, v.co.z * 100) for v in obj.data.vertices])
    return dict(name=obj.name, fbx=path.relative_to(ROOT).as_posix(), sha256=digest(path),
        bounds_min_cm=values.min(0).tolist(), bounds_max_cm=values.max(0).tolist(),
        triangles=sum(len(p.vertices) - 2 for p in obj.data.polygons),
        materials={m.name: list(m.diffuse_color) for m in obj.data.materials},
        position_cm=[obj.location.y * 100, obj.location.x * 100, obj.location.z * 100])


def build():
    cfg = read("manifests/seawall-tree-settings.json")
    if Path(bpy.data.filepath).resolve() != (ROOT / cfg["working_blend"]).resolve():
        raise RuntimeError("Save the separate Seawall working blend before running this script")
    scene = bpy.context.scene
    if abs(scene.unit_settings.scale_length - 1) > 1e-7:
        raise RuntimeError("The authoring scene must use metres")
    cover = read("data/derived/cover-blockout.json")
    groups = read("data/derived/canopy-zone-assignments.json")
    if groups["cover_sha256"] != digest(ROOT / "data/derived/cover-blockout.json"):
        raise RuntimeError("Canopy group assignments are stale")
    assignments = {row["tile"]: row["clusters"] for row in groups["assignments"]}
    route = np.asarray(read("data/derived/paved-circuit-runtime.json")["points_local_m"])[:, :2]
    lengths = np.linalg.norm(np.diff(route, axis=0), axis=1)
    station = np.r_[0, np.cumsum(lengths)]
    inputs = ["manifests/seawall-tree-settings.json", "manifests/world-origin.json", "data/derived/cover-blockout.json",
              "data/derived/canopy-zone-assignments.json", "data/derived/paved-circuit-runtime.json",
              "data/routes/derived/pedestrian-network.json", "manifests/vegetation-zones.json"]
    hashes = {path: digest(ROOT / path) for path in inputs}
    for script in ("build_seawall_tree_library.py", "seawall_tree_geometry.py", "seawall_tree_textures.py", "seawall_tree_impostors.py", "seawall_tree_support.py"):
        hashes["pipeline/blender/"+script] = digest(Path(__file__).with_name(script))
    # Include actual live surface geometry in the content version and provenance.
    surface_hash = hashlib.sha256()
    for obj in sorted(scene.objects, key=lambda o: o.name):
        if obj.type == "MESH" and obj.name.startswith(("SM_Pavement_", "SM_Pedestrian_", "SM_Route_")):
            surface_hash.update(obj.name.encode())
            surface_hash.update(np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices], dtype="<f8").tobytes())
            surface_hash.update(str([tuple(p.vertices) for p in obj.data.polygons]).encode())
    hashes["live_clearance_meshes"] = surface_hash.hexdigest()
    ground_hash = hashlib.sha256()
    for obj in sorted(scene.objects,key=lambda o:o.name):
        if obj.type=="MESH" and obj.name.startswith("SM_Terrain_"):
            ground_hash.update(obj.name.encode())
            ground_hash.update(np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices],dtype="<f8").tobytes())
            ground_hash.update(str([tuple(p.vertices) for p in obj.data.polygons]).encode())
    hashes["live_ground_meshes"] = ground_hash.hexdigest()
    version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
    directory = ROOT / "exports/seawall-trees" / version
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    candidates, bins = [], defaultdict(lambda: defaultdict(int))
    for tile in cover["canopy"]:
        if len(tile["points"]) != len(assignments[tile["tile"]]):
            raise RuntimeError("Canopy group count mismatch")
        for index, (point, group) in enumerate(zip(tile["points"], assignments[tile["tile"]])):
            x, y, base, top = point
            if [x, y] != [group["x_m"], group["y_m"]]:
                raise RuntimeError("Canopy group position mismatch")
            if group["species_group"] == "UNKNOWN" or top - base < cfg["minimum_height_m"]:
                continue
            distances, t = nearest_segments(np.array([x, y]), route[:-1], route[1:])
            nearest = int(distances.argmin())
            distance = float(distances[nearest])
            if distance > cfg["representative_corridor_m"]:
                continue
            s = float(station[nearest] + t[nearest] * lengths[nearest])
            kind = "broadleaf" if group["species_group"] in {"MB", "DR"} else "conifer"
            row = dict(source_id=f"{tile['tile']}:{index}", tile=tile["tile"], cluster_index=index,
                       position_local_m=[x, y, base], top_m=top, height_m=top-base, station_m=s,
                       route_distance_m=distance, visual_type=kind, species_group=group["species_group"], zone_id=group["zone_id"])
            candidates.append(row)
            bins[int(s // cfg["representative_length_m"])][kind] += 1
    if not candidates:
        raise RuntimeError("No source-supported route crowns were found")
    # Prefer a slice with both visual groups, then the greatest source count.
    pilot_bin = max(sorted(bins), key=lambda k: (min(bins[k]["conifer"], bins[k]["broadleaf"]), sum(bins[k].values())))
    pilot_start = pilot_bin * cfg["representative_length_m"]
    clearance = Clearance(scene, read("data/routes/derived/pedestrian-network.json"))
    accepted, rejected = [], []
    for row in sorted(candidates, key=lambda r: (r["route_distance_m"], r["source_id"])):
        row["pilot"] = pilot_start <= row["station_m"] < pilot_start + cfg["representative_length_m"]
        if row["route_distance_m"] > cfg["route_corridor_m"] and not row["pilot"]:
            continue
        radius = min(cfg["maximum_crown_radius_m"], row["height_m"] * .25)
        reason = clearance.blocked(np.array(row["position_local_m"][:2]), row["position_local_m"][2], row["height_m"], radius, cfg)
        if reason or len(accepted) >= cfg["maximum_instances"]:
            rejected.append(dict(source_id=row["source_id"], reason=reason or "instance_budget"))
            continue
        seed = int(hashlib.sha256(row["source_id"].encode()).hexdigest()[:8], 16)
        row.update(variant=seed % 3, yaw_degrees=(seed % 36000) / 100, crown_radius_m=radius,
                   scale=[radius / 5, radius / 5, row["height_m"] / 20])
        accepted.append(row)
    if not accepted:
        raise RuntimeError("No route crowns passed the placement constraints")
    collection_name = "SP_SeawallTrees_" + version
    previous = bpy.data.collections.get(collection_name)
    if previous and manifest_path.exists():
        prior = json.loads(manifest_path.read_text())
        files = [item for tree in prior["trees"] for item in tree["lods"]]
        files += [entry["replacement"] for entry in prior["coarse_replacements"] if entry["replacement"]]
        if all((ROOT / item["fbx"]).exists() and digest(ROOT / item["fbx"]) == item["sha256"] for item in files):
            (ROOT / "exports/seawall-trees/latest.json").write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=digest(manifest_path)), indent=2))
            return dict(reused=True, manifest=manifest_path.relative_to(ROOT).as_posix(), instances=len(prior["instances"]))
    if previous:
        raise RuntimeError("Incomplete prior collection; retain it for review before rebuilding")
    collection = bpy.data.collections.new(collection_name)
    scene.collection.children.link(collection)
    # Restore source visibility before replacing an older working-tree version.
    # Keep the previous objects and versioned exports for direct restoration.
    old_state = []
    for obj in scene.objects:
        if obj.get("seawall_restore_visibility"):
            saved = json.loads(obj["seawall_restore_visibility"])
            old_state.append(saved)
    (directory / "blender-restore.json").write_text(json.dumps(old_state, indent=2))
    for saved in old_state:
        obj = bpy.data.objects[saved["object_name"]]
        obj.hide_viewport = saved["hide_viewport"]
        obj.hide_render = saved["hide_render"]
        obj.hide_set(saved["hide_set"])
    for old_collection in scene.collection.children:
        if old_collection.name.startswith("SP_SeawallTrees_") and old_collection != collection:
            old_collection.hide_viewport = True
            old_collection.hide_render = True
    images, texture_records = seawall_tree_textures.create_textures(directory, version)
    mats, material_specs = seawall_tree_textures.create_materials(images, version)
    cache = None
    pointer_path = ROOT/"exports/seawall-trees/latest.json"
    if pointer_path.exists():
        pointer = json.loads(pointer_path.read_text())
        prior_path = ROOT/pointer["manifest"]
        if digest(prior_path)!=pointer["sha256"]:
            raise RuntimeError("Cached far-tree manifest hash mismatch")
        prior = json.loads(prior_path.read_text())
        cache_keys = ["pipeline/blender/seawall_tree_geometry.py","pipeline/blender/seawall_tree_textures.py"]
        if prior.get("far_tree_captures") and all(prior["input_hashes"].get(k)==hashes[k] for k in cache_keys):
            cache=(prior_path,prior)
    far_material, far_record, far_spec, far_captures = seawall_tree_impostors.bake(directory, version, mats, cache=cache)
    mats.append(far_material)
    material_specs[far_material.name] = far_spec
    texture_records.append(far_record)
    for texture in texture_records:
        texture["path"] = texture["path"].relative_to(ROOT).as_posix()
    trees, prototypes = [], {}
    for kind in ("conifer", "broadleaf"):
        for variant in range(3):
            tree_id = f"SM_SWTree_{kind}_{variant}_{version}"
            lods = []
            for lod in range(4):
                geometry = (seawall_tree_impostors.billboard_geometry(kind,variant) if lod==3
                            else tree_geometry(kind,variant,lod))
                obj = make_object(tree_id + f"_LOD{lod}", geometry, collection, mats)
                lods.append(export_object(obj, directory, scene))
                obj.hide_set(True)
                obj.hide_render = True
                if lod == 0:
                    prototypes[kind, variant] = obj
            trees.append(dict(id=tree_id, visual_type=kind, variant=variant, lods=lods))
    for row in accepted:
        prototype = prototypes[row["visual_type"], row["variant"]]
        row["tree_id"] = prototype.name.rsplit("_LOD", 1)[0]
        preview = bpy.data.objects.new("SWTree_" + row["source_id"], prototype.data)
        collection.objects.link(preview)
        preview.location, preview.scale = row["position_local_m"], row["scale"]
        preview.rotation_euler.z = math.radians(-row["yaw_degrees"])
        preview["pipeline_owner"], preview["kit_asset"] = OWNER, True
        preview["source_id"] = row["source_id"]
    # Retain every measured sample. The remaining crowns use masked branch cards.
    # Never add an inferred stem at a sample which failed route clearance.
    selected = defaultdict(set)
    for row in accepted:
        selected[row["tile"]].add(row["cluster_index"])
    replacements = []
    ground = seawall_tree_support.Ground(scene)
    crown_cache = {(kind,variant): seawall_tree_impostors.billboard_geometry(kind,variant)
                   for kind in ("conifer","broadleaf") for variant in range(3)}
    for tile in cover["canopy"]:
        if not tile["points"]:
            continue
        name = "SM_Canopy_" + tile["tile"].split("_", 1)[1]
        source = bpy.data.objects.get(name)
        if source is None or len(source.data.vertices) != len(tile["points"]) * 24:
            raise RuntimeError(f"Source canopy topology changed: {name}")
        g = Geometry()
        retained = []
        for index, (point, group) in enumerate(zip(tile["points"], assignments[tile["tile"]])):
            if index in selected[tile["tile"]]:
                continue
            x, y, base, top = point
            height = top-base
            seed = int(hashlib.sha256(f"{tile['tile']}:{index}".encode()).hexdigest()[:8], 16)
            # Unresolved groups keep a documented generic visual form.
            kind = "broadleaf" if group["species_group"] in {"MB", "DR"} else "conifer"
            radius = min(cfg["maximum_crown_radius_m"], height*.25)
            scale = (radius/5, radius/5, height/20)
            local = np.array([x,y,base])-np.array(source.location)
            floor = clearance.crown_floor(np.array([x,y]), radius, cfg)
            support, support_record = seawall_tree_support.make_support(
                clearance,ground,[x,y,base],height,radius,floor,cfg,seed)
            row = dict(source_id=f"{tile['tile']}:{index}", visual_type=kind,
                species_group=group["species_group"], crown_clip_height_m=max(0,floor-base),
                physical_stem=support is not None, support=support_record,
                excluded=support is None)
            retained.append(row)
            if support is None:
                continue
            # Keep the measured crown centre and its top. A local root offset
            # changes only the inferred support below the source crown.
            local_floor = max(6.0,(floor-base)*20/height) if height>0 else 21
            g.append(support,translation=-np.asarray(source.location))
            g.append(crown_cache[kind,seed%3],scale=scale,translation=local,
                     yaw=math.radians(-(seed%36000)/100),clip_z=local_floor)
        obj = make_object("SM_SWCanopy_" + name.removeprefix("SM_Canopy_") + "_" + version,
                          g, collection, mats, tuple(source.location))
        item = export_object(obj, directory, scene) if g.faces else None
        restoration = dict(object_name=name, hide_viewport=source.hide_viewport, hide_render=source.hide_render,
                           hide_set=source.hide_get(), removed_clusters=sorted(selected[tile["tile"]]),
                           retained_crowns=retained, replacement=item)
        (directory / (name + "-restore.json")).write_text(json.dumps(restoration, indent=2))
        source["seawall_restore_visibility"] = json.dumps(restoration)
        source.hide_set(True)
        source.hide_render = True
        replacements.append(restoration)
    manifest = dict(schema_version=2, version=version, asset_root=cfg["asset_root"] + "/v_" + version,
        source_blend=cfg["working_blend"], input_hashes=hashes, settings=cfg, trees=trees,
        instances=accepted, rejected=rejected, coarse_replacements=replacements,
        textures=texture_records, material_specs=material_specs, far_tree_captures=far_captures,
        far_tree_cache_source=cache[0].relative_to(ROOT).as_posix() if cache else None,
        pilot=dict(station_start_m=pilot_start, station_end_m=pilot_start + cfg["representative_length_m"],
                   method="400 m route interval with the most balanced source conifer and broadleaf counts"),
        clearance_meshes=clearance.names, placement_status=cfg["placement_status"], visual_review_complete=False)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (ROOT / "exports/seawall-trees/latest.json").write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=digest(manifest_path)), indent=2))
    return dict(manifest=manifest_path.relative_to(ROOT).as_posix(), instances=len(accepted), rejected=len(rejected), pilot=manifest["pilot"], version=version)


result = build()
