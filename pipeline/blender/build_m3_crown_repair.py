"""Repair sliced near crowns, preserving source centres, tops and supports.

Runs only in the serial Blender authoring slot. It creates a new immutable
layer; no renders, gameplay, scene save or frozen export edits occur here.
"""
import hashlib
import json
import math
import runpy
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_M3CrownRepair"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def without_root_flares(geometry, factory):
    """Remove only disconnected basal root tubes, retaining all crown leaves."""
    parent = list(range(len(geometry.vertices)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for face in geometry.faces:
        for index in face[1:]:
            parent[root(index)] = root(face[0])
    bounds = {}
    for index, point in enumerate(geometry.vertices):
        key = root(index)
        low, high = bounds.get(key, (float("inf"), -float("inf")))
        bounds[key] = min(low, point[2]), max(high, point[2])
    removed = {key for key, (low, high) in bounds.items() if low < .2 and high < 1.0}
    result = factory()
    mapping = {}
    for face, slot in zip(geometry.faces, geometry.slots):
        if root(face[0]) in removed:
            continue
        indices = []
        for index in face:
            if index not in mapping:
                mapping[index] = result.vertex(geometry.vertices[index], geometry.uvs[index])
            indices.append(mapping[index])
        result.face(indices, slot)
    if sum(slot == 1 for slot in result.slots) != sum(slot == 1 for slot in geometry.slots):
        raise RuntimeError("Root removal changed foliage")
    return result


def full_silhouette(kind, variant, factory):
    """Keep the whole silhouette, trimming only transparent image framing."""
    geometry = factory()
    u0, v0 = variant/4, 0 if kind == "conifer" else .5
    for angle in (0, math.pi/3, math.pi*2/3):
        across = np.array([math.cos(angle), math.sin(angle), 0])
        face = []
        for u, height in ((0, 0), (1, 0), (1, 20), (0, 20)):
            # The accepted image frame is z=-0.5..20.5. These UVs retain
            # the entire z=0..20 tree, never cut through its lower foliage.
            point = across*((u-.5)*10.5)+np.array([0, 0, height])
            face.append(geometry.vertex(point, (u0+u*.25, v0+(.5+height)/21*.5)))
        geometry.face(face, 2)
    return geometry


def build():
    cfg = read("manifests/m3-crown-repair-settings.json")
    if Path(bpy.data.filepath).resolve() != (ROOT/cfg["working_blend"]).resolve():
        raise RuntimeError("Open the Seawall working blend first")
    if sha(ROOT/cfg["forest_manifest"]) != cfg["forest_manifest_sha256"]:
        raise RuntimeError("The bound M3 forest export changed")
    forest = read(cfg["forest_manifest"])
    baseline = read(forest["baseline_manifest"])
    inputs = {path: sha(ROOT/path) for path in [cfg["forest_manifest"], forest["baseline_manifest"],
        "manifests/m3-crown-repair-settings.json", "pipeline/blender/build_m3_crown_repair.py"]}
    for path, expected in forest["input_hashes"].items():
        if sha(ROOT/path) != expected:
            raise RuntimeError("Frozen M3 forest input changed: "+path)
    for path, expected in baseline["input_hashes"].items():
        if not path.startswith("live_") and sha(ROOT/path) != expected:
            raise RuntimeError("Frozen M2 tree input changed: "+path)
    bridge = runpy.run_path(str(ROOT/"pipeline/blender/build_m3_forest.py"), run_name="m3_crown_helpers")
    helpers = bridge["frozen_helpers"](baseline)
    scene = bpy.context.scene
    if abs(scene.unit_settings.scale_length-1) > 1e-7:
        raise RuntimeError("The scene must use metres")
    for key, prefixes in [("live_clearance_meshes", ("SM_Pavement_", "SM_Pedestrian_", "SM_Route_")),
                          ("live_ground_meshes", ("SM_Terrain_",))]:
        if bridge["live_hash"](scene, prefixes) != baseline["input_hashes"][key]:
            raise RuntimeError("Protected live geometry changed: "+key)
    version = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:12]
    directory = ROOT/"exports/m3-crown-repair"/version
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory/"manifest.json"
    collection_name = OWNER+"_"+version
    if bpy.data.collections.get(collection_name):
        if not manifest_path.exists():
            raise RuntimeError("Incomplete crown repair collection; preserve it for review")
        previous = read(manifest_path.relative_to(ROOT))
        exports = [item for tree in previous["trees"] for item in tree["lods"]]
        exports += [row["replacement"] for row in previous["coarse_replacements"]]
        if any(sha(ROOT/item["fbx"]) != item["sha256"] for item in exports):
            raise RuntimeError("Immutable crown repair export changed")
        (directory.parent/"latest.json").write_text(json.dumps(dict(
            manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=sha(manifest_path)), indent=2))
        return dict(reused=True, version=version, **previous["summary"])
    tree_cfg = baseline["settings"]
    clearance = helpers["Clearance"](scene, read("data/routes/derived/pedestrian-network.json"))
    ground = helpers["seawall_tree_support"].Ground(scene)
    source_rows = {r["source_id"]: r for entry in baseline["coarse_replacements"] for r in entry["retained_crowns"]}
    detailed_ids = {r["source_id"] for r in baseline["instances"]+forest["instances"]}
    route = np.asarray(read("data/derived/paved-circuit-runtime.json")["points_local_m"])[:, :2]
    lengths = np.linalg.norm(np.diff(route, axis=0), axis=1)
    stations = np.r_[0, np.cumsum(lengths)]
    groups = {row["tile"]: row["clusters"] for row in read("data/derived/canopy-zone-assignments.json")["assignments"]}
    active_tiles = {row["replaced_m2_actor"]: row["replacement"]["name"] for row in forest["coarse_replacements"]}
    originals = {}
    for row in baseline["coarse_replacements"]:
        if row["replacement"]:
            name = active_tiles.get(row["replacement"]["name"], row["replacement"]["name"])
            obj = bpy.data.objects.get(name)
            if obj is None:
                raise RuntimeError("Active background tile is missing: "+name)
            originals[row["object_name"]] = obj
    prototype = bpy.data.objects.get(baseline["trees"][0]["id"]+"_LOD0")
    if prototype is None:
        raise RuntimeError("Accepted source tree library is missing")
    materials = list(prototype.data.materials)
    collection = bpy.data.collections.new(collection_name)
    scene.collection.children.link(collection)
    trees, prototypes, silhouettes = [], {}, {}
    for kind in ("conifer", "broadleaf"):
        for variant in range(3):
            tree_id = f"SM_M3Crown_{kind}_{variant}_{version}"
            lods = []
            silhouettes[kind, variant] = full_silhouette(kind, variant, helpers["Geometry"])
            for lod in range(4):
                geometry = (silhouettes[kind, variant] if lod == 3 else
                    without_root_flares(helpers["tree_geometry"](kind, variant, lod), helpers["Geometry"]))
                obj = helpers["make_object"](tree_id+f"_LOD{lod}", geometry, collection, materials)
                obj["pipeline_owner"] = OWNER
                lods.append(helpers["export_object"](obj, directory, scene))
                obj.hide_render = True
                obj.hide_set(True)
                if lod == 0:
                    prototypes[kind, variant] = obj
            trees.append(dict(id=tree_id, visual_type=kind, variant=variant, lods=lods))
    replacements, instances, all_records = [], [], []
    for tile in read("data/derived/cover-blockout.json")["canopy"]:
        if not tile["points"]:
            continue
        source_name = "SM_Canopy_"+tile["tile"].split("_", 1)[1]
        old_obj = originals[source_name]
        geometry = helpers["Geometry"]()
        records = []
        for index, (point, group) in enumerate(zip(tile["points"], groups[tile["tile"]])):
            source_id = f"{tile['tile']}:{index}"
            if source_id in detailed_ids:
                continue
            prior = source_rows[source_id]
            x, y, base, top = point
            height = top-base
            radius = min(tree_cfg["maximum_crown_radius_m"], height*.25)
            seed = int(hashlib.sha256(source_id.encode()).hexdigest()[:8], 16)
            kind = "broadleaf" if group["species_group"] in {"MB", "DR"} else "conifer"
            floor = clearance.crown_floor(np.array([x, y]), radius, tree_cfg)
            support, support_record = helpers["seawall_tree_support"].make_support(
                clearance, ground, [x, y, base], height, radius, floor, tree_cfg, seed)
            if (support is None) != bool(prior["excluded"]):
                raise RuntimeError("Support/exclusion changed: "+source_id)
            row = dict(source_id=source_id, source_position_local_m=[x, y, base], source_top_m=top,
                species_group=group["species_group"], excluded=bool(prior["excluded"]),
                support=support_record, prior_support=prior["support"])
            records.append(row)
            all_records.append(row)
            if support is None:
                continue
            if support_record != prior["support"]:
                raise RuntimeError("A grounded support changed: "+source_id)
            bottom = max(base, floor+cfg["clearance_extra_m"])
            if not bottom < top:
                raise RuntimeError("No safe crown envelope: "+source_id)
            if support_record["connection_height_m"] <= bottom:
                raise RuntimeError("Crown would separate from its grounded support: "+source_id)
            distances, factors = helpers["nearest_segments"](np.array([x, y]), route[:-1], route[1:])
            nearest = int(distances.argmin())
            distance = float(distances[nearest])
            station = float(stations[nearest]+factors[nearest]*lengths[nearest])
            scale = [radius/5, radius/5, (top-bottom)/20]
            row.update(route_distance_m=distance, station_m=station, crown_base_m=bottom,
                crown_top_m=top, clearance_floor_m=floor, crown_envelope_height_m=top-bottom,
                representation="shared_3d_crown" if distance <= cfg["near_crown_distance_m"] else "complete_far_silhouette")
            geometry.append(support, translation=-np.asarray(old_obj.location))
            if distance <= cfg["near_crown_distance_m"]:
                tree_id = f"SM_M3Crown_{kind}_{seed%3}_{version}"
                placement = dict(source_id=source_id, tree_id=tree_id, visual_type=kind, variant=seed%3,
                    position_local_m=[x, y, bottom], source_position_local_m=[x, y, base], top_m=top,
                    scale=scale, yaw_degrees=(seed%36000)/100, route_distance_m=distance, station_m=station)
                instances.append(placement)
                obj = bpy.data.objects.new("M3Crown_"+source_id, prototypes[kind, seed%3].data)
                collection.objects.link(obj)
                obj.location, obj.scale = placement["position_local_m"], scale
                obj.rotation_euler.z = math.radians(-placement["yaw_degrees"])
                obj["pipeline_owner"], obj["source_id"], obj["kit_asset"] = OWNER, source_id, True
            else:
                geometry.append(silhouettes[kind, seed%3], scale=scale,
                    translation=np.array([x, y, bottom])-np.asarray(old_obj.location),
                    yaw=math.radians(-(seed%36000)/100))
        obj = helpers["make_object"]("SM_M3CrownTile_"+source_name.removeprefix("SM_Canopy_")+"_"+version,
            geometry, collection, materials, tuple(old_obj.location))
        obj["pipeline_owner"] = OWNER
        item = helpers["export_object"](obj, directory, scene)
        replacements.append(dict(replaced_actor=old_obj.name, replacement=item, source_records=records,
            prior_visibility=dict(hide_render=old_obj.hide_render, hide_viewport=old_obj.hide_viewport, hide_set=old_obj.hide_get())))
    summary = dict(preserved_detail_instances=len(detailed_ids), shared_near_crowns=len(instances),
        total_near_instances=len(detailed_ids)+len(instances), background_tiles=len(replacements),
        complete_far_silhouettes=sum(r.get("representation") == "complete_far_silhouette" for r in all_records),
        retained_exclusions=sum(r["excluded"] for r in all_records),
        visible_source_anchors=len(detailed_ids)+sum(not r["excluded"] for r in all_records),
        modified_source_anchors=0, changed_grounded_supports=0, removed_visible_sources=0)
    manifest = dict(schema_version=1, version=version, owner=OWNER, settings=cfg, input_hashes=inputs,
        asset_root=cfg["asset_root"]+"/v_"+version, baseline_asset_root=baseline["asset_root"],
        trees=trees, instances=instances, coarse_replacements=replacements, summary=summary,
        source_contract=cfg["source_contract"], visual_review_complete=False, application_run=False)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for row in replacements:
        obj = bpy.data.objects[row["replaced_actor"]]
        obj.hide_render = True
        obj.hide_set(True)
    for old in scene.collection.children:
        if old.name.startswith(OWNER+"_") and old != collection:
            old.hide_render = True
            old.hide_viewport = True
    (directory.parent/"latest.json").write_text(json.dumps(dict(
        manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=sha(manifest_path)), indent=2))
    return dict(version=version, manifest=manifest_path.relative_to(ROOT).as_posix(), **summary)


if __name__ in {"__main__", "<run_path>"}:
    result = build()
