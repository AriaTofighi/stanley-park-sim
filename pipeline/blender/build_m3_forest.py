"""Add a tapered route forest layer; preserve the frozen M2 tree export.

Run in the saved Seawall working scene through Blender MCP. No render, ride,
application test, source mesh edit or blend save is performed here.
"""
import ast
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_M3Forest"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def frozen_helpers(baseline):
    """Reuse the accepted export/clearance code, without running its builder."""
    path = ROOT / "pipeline/blender/build_seawall_tree_library.py"
    if digest(path) != baseline["input_hashes"][path.relative_to(ROOT).as_posix()]:
        raise RuntimeError("Frozen M2 authoring helpers changed")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    terminal = tree.body.pop()
    if not (isinstance(terminal, ast.Assign) and len(terminal.targets) == 1
            and isinstance(terminal.targets[0], ast.Name) and terminal.targets[0].id == "result"
            and isinstance(terminal.value, ast.Call) and isinstance(terminal.value.func, ast.Name)
            and terminal.value.func.id == "build" and not terminal.value.args and not terminal.value.keywords):
        raise RuntimeError("Frozen builder entry point changed")
    namespace = {"__file__": str(path), "__name__": "m3_frozen_tree_helpers"}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def live_hash(scene, prefixes):
    result = hashlib.sha256()
    for obj in sorted(scene.objects, key=lambda value: value.name):
        if obj.type == "MESH" and obj.name.startswith(prefixes):
            result.update(obj.name.encode())
            result.update(np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices], dtype="<f8").tobytes())
            result.update(str([tuple(p.vertices) for p in obj.data.polygons]).encode())
    return result.hexdigest()


def build():
    cfg = read("manifests/m3-forest-settings.json")
    if Path(bpy.data.filepath).resolve() != (ROOT / cfg["working_blend"]).resolve():
        raise RuntimeError("Open the Seawall working blend first")
    source = ROOT / cfg["baseline_manifest"]
    if digest(source) != cfg["baseline_manifest_sha256"]:
        raise RuntimeError("Frozen tree baseline changed")
    baseline = read(cfg["baseline_manifest"])
    for path, expected in baseline["input_hashes"].items():
        if not path.startswith("live_") and digest(ROOT / path) != expected:
            raise RuntimeError("Frozen tree input changed: " + path)
    scene = bpy.context.scene
    if abs(scene.unit_settings.scale_length - 1) > 1e-7:
        raise RuntimeError("The working scene must use metres")
    for key, prefixes in [("live_clearance_meshes", ("SM_Pavement_", "SM_Pedestrian_", "SM_Route_")),
                          ("live_ground_meshes", ("SM_Terrain_",))]:
        if live_hash(scene, prefixes) != baseline["input_hashes"][key]:
            raise RuntimeError("M2 source geometry changed: " + key)
    inputs = {path: digest(ROOT / path) for path in [cfg["baseline_manifest"],
        "manifests/m3-forest-settings.json", "pipeline/blender/build_m3_forest.py"]}
    version = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:12]
    directory = ROOT / "exports/m3-forest" / version
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    collection_name = OWNER + "_" + version
    previous = bpy.data.collections.get(collection_name)
    if previous:
        if not manifest_path.exists():
            raise RuntimeError("Incomplete M3 collection; retain it for inspection")
        saved = read(manifest_path.relative_to(ROOT))
        if any(digest(ROOT / item["replacement"]["fbx"]) != item["replacement"]["sha256"]
               for item in saved["coarse_replacements"]):
            raise RuntimeError("An immutable M3 export changed")
        (directory.parent / "latest.json").write_text(json.dumps(dict(
            manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=digest(manifest_path)), indent=2))
        return dict(reused=True, manifest=manifest_path.relative_to(ROOT).as_posix(), **saved["summary"])
    helpers = frozen_helpers(baseline)
    tree_cfg = baseline["settings"]
    clearance = helpers["Clearance"](scene, read("data/routes/derived/pedestrian-network.json"))
    ground = helpers["seawall_tree_support"].Ground(scene)
    cover = read("data/derived/cover-blockout.json")
    groups = {row["tile"]: row["clusters"] for row in read("data/derived/canopy-zone-assignments.json")["assignments"]}
    route = np.asarray(read("data/derived/paved-circuit-runtime.json")["points_local_m"])[:, :2]
    lengths = np.linalg.norm(np.diff(route, axis=0), axis=1)
    stations = np.r_[0, np.cumsum(lengths)]
    old_ids = {row["source_id"] for row in baseline["instances"]}
    old_background = {row["source_id"]: row for tile in baseline["coarse_replacements"] for row in tile["retained_crowns"]}
    trees = {(row["visual_type"], row["variant"]): row for row in baseline["trees"]}
    promoted, candidates, all_rows = [], [], []
    start, end = baseline["pilot"]["station_start_m"], baseline["pilot"]["station_end_m"]
    for tile in cover["canopy"]:
        for index, (point, group) in enumerate(zip(tile["points"], groups[tile["tile"]])):
            x, y, base, top = point
            distances, factors = helpers["nearest_segments"](np.array([x, y]), route[:-1], route[1:])
            nearest = int(distances.argmin())
            distance = float(distances[nearest])
            station = float(stations[nearest] + factors[nearest] * lengths[nearest])
            source_id = f"{tile['tile']}:{index}"
            row = dict(source_id=source_id, tile=tile["tile"], cluster_index=index,
                       position_local_m=[x, y, base], top_m=top, height_m=top-base,
                       route_distance_m=distance, station_m=station, species_group=group["species_group"],
                       representation="m2_detail" if source_id in old_ids else "background")
            if old_background.get(source_id, {}).get("excluded"):
                row["representation"] = "recorded_exclusion"
            all_rows.append(row)
            if source_id in old_ids or distance > cfg["transition_outer_distance_m"]:
                continue
            row["decision"] = "retained_background"
            candidates.append(row)
            if group["species_group"] == "UNKNOWN" or top-base < tree_cfg["minimum_height_m"]:
                row["decision"] = "unresolved_group_or_small_crown"
                continue
            radius = min(tree_cfg["maximum_crown_radius_m"], (top-base)*.25)
            reason = clearance.blocked(np.array([x, y]), base, top-base, radius, tree_cfg)
            if reason:
                row["decision"] = reason
                continue
            if row["representation"] == "recorded_exclusion":
                row["decision"] = "retain_recorded_exclusion"
                continue
            radial = 1-smooth((distance-cfg["full_detail_distance_m"])
                             /(cfg["transition_outer_distance_m"]-cfg["full_detail_distance_m"]))
            beyond_pilot = max(start-station, station-end, 0)
            pilot_weight = 1-smooth(beyond_pilot/cfg["pilot_boundary_blend_m"])
            weight = max(radial, pilot_weight)
            seed = int(hashlib.sha256(source_id.encode()).hexdigest()[:8], 16)
            selection = int(hashlib.sha256((source_id+":m3-transition").encode()).hexdigest()[:8], 16)/2**32
            row.update(detail_weight=weight, selection_value=selection)
            if selection >= weight:
                row["decision"] = "tapered_background"
                continue
            kind = "broadleaf" if group["species_group"] in {"MB", "DR"} else "conifer"
            row.update(representation="m3_detail", decision="promoted", visual_type=kind,
                       variant=seed%3, yaw_degrees=(seed%36000)/100, crown_radius_m=radius,
                       scale=[radius/5, radius/5, (top-base)/20], tree_id=trees[kind, seed%3]["id"])
            promoted.append(row)
    if not promoted:
        raise RuntimeError("No safe background crowns qualify for M3 promotion")
    selected = {row["source_id"] for row in promoted}
    affected = {row["tile"] for row in promoted}
    prototypes = {key: bpy.data.objects.get(row["id"]+"_LOD0") for key, row in trees.items()}
    if any(obj is None for obj in prototypes.values()):
        raise RuntimeError("The accepted M2 source tree prototypes are missing")
    materials = list(next(iter(prototypes.values())).data.materials)
    for entry in baseline["coarse_replacements"]:
        if entry["replacement"] and not bpy.data.objects.get(entry["replacement"]["name"]):
            raise RuntimeError("An active M2 background tile is missing")
    collection = bpy.data.collections.new(collection_name)
    scene.collection.children.link(collection)
    for row in promoted:
        obj = bpy.data.objects.new("M3Tree_"+row["source_id"], prototypes[row["visual_type"], row["variant"]].data)
        collection.objects.link(obj)
        obj.location, obj.scale = row["position_local_m"], row["scale"]
        obj.rotation_euler.z = math.radians(-row["yaw_degrees"])
        obj["pipeline_owner"], obj["source_id"], obj["kit_asset"] = OWNER, row["source_id"], True
    coarse = []
    crown_cache = {(kind, variant): helpers["seawall_tree_impostors"].billboard_geometry(kind, variant)
                   for kind in ("conifer", "broadleaf") for variant in range(3)}
    baseline_tiles = {row["object_name"]: row for row in baseline["coarse_replacements"]}
    for tile in cover["canopy"]:
        if tile["tile"] not in affected:
            continue
        name = "SM_Canopy_"+tile["tile"].split("_", 1)[1]
        old = baseline_tiles[name]
        old_obj = bpy.data.objects[old["replacement"]["name"]]
        geometry = helpers["Geometry"]()
        retained = []
        for index, (point, group) in enumerate(zip(tile["points"], groups[tile["tile"]])):
            source_id = f"{tile['tile']}:{index}"
            if source_id in old_ids or source_id in selected:
                continue
            x, y, base, top = point
            height, radius = top-base, min(tree_cfg["maximum_crown_radius_m"], (top-base)*.25)
            seed = int(hashlib.sha256(source_id.encode()).hexdigest()[:8], 16)
            kind = "broadleaf" if group["species_group"] in {"MB", "DR"} else "conifer"
            floor = clearance.crown_floor(np.array([x, y]), radius, tree_cfg)
            support, support_record = helpers["seawall_tree_support"].make_support(
                clearance, ground, [x, y, base], height, radius, floor, tree_cfg, seed)
            prior = old_background[source_id]
            if (support is None) != bool(prior["excluded"]):
                raise RuntimeError("Unchanged support classification differs: "+source_id)
            retained.append(dict(prior))
            if support is None:
                continue
            local_floor = max(6.0, (floor-base)*20/height) if height > 0 else 21
            geometry.append(support, translation=-np.asarray(old_obj.location))
            geometry.append(crown_cache[kind, seed%3], scale=(radius/5, radius/5, height/20),
                translation=np.array([x, y, base])-np.asarray(old_obj.location),
                yaw=math.radians(-(seed%36000)/100), clip_z=local_floor)
        obj = helpers["make_object"]("SM_M3Canopy_"+name.removeprefix("SM_Canopy_")+"_"+version,
                                   geometry, collection, materials, tuple(old_obj.location))
        obj["pipeline_owner"] = OWNER
        exported = helpers["export_object"](obj, directory, scene)
        coarse.append(dict(source_tile=tile["tile"], replaced_m2_actor=old_obj.name,
                           replacement=exported, retained_crowns=retained,
                           blender_prior=dict(hide_render=old_obj.hide_render,
                                              hide_viewport=old_obj.hide_viewport, hide_set=old_obj.hide_get())))
    section_rows = []
    for index in range(int(math.ceil(stations[-1]/cfg["section_length_m"]))):
        low, high = index*cfg["section_length_m"], min((index+1)*cfg["section_length_m"], float(stations[-1]))
        local = [r for r in all_rows if low <= r["station_m"] < high and r["route_distance_m"] <= 60]
        section_rows.append(dict(station_start_m=low, station_end_m=high,
            source_samples_within_60m=len(local), representations=dict(Counter(r["representation"] for r in local)),
            near_background_clipped_ids=[r["source_id"] for r in local if r["representation"] == "background"
                and r["route_distance_m"] <= 35 and old_background[r["source_id"]].get("crown_clip_height_m", 0)>0],
            view_review="pending; source counts do not establish visible completeness"))
    summary = dict(preserved_m2_instances=len(old_ids), added_detail_instances=len(promoted),
        total_detail_instances=len(old_ids)+len(promoted), replaced_background_tiles=len(coarse),
        preserved_visible_source_count=len(old_ids)+sum(not r["excluded"] for r in old_background.values()),
        preserved_exclusions=sum(r["excluded"] for r in old_background.values()))
    manifest = dict(schema_version=1, version=version, owner=OWNER,
        asset_root=cfg["asset_root"]+"/v_"+version, settings=cfg, input_hashes=inputs,
        baseline_manifest=cfg["baseline_manifest"], baseline_asset_root=baseline["asset_root"],
        shared_trees=baseline["trees"], instances=promoted, candidate_decisions=candidates,
        coarse_replacements=coarse, sections=section_rows, summary=summary,
        clearance_meshes=clearance.names, application_run=False, visual_review_complete=False,
        remaining_visual_limits=["Six near silhouettes still repeat; individual yaw is deterministic.",
            "Existing clipped background crowns stay explicit; this layer does not claim to repair every crown cut.",
            "Recorded source exclusions remain; inspect all section views before acceptance."])
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Publish only after every export exists; then hide the replaced background.
    for entry in coarse:
        obj = bpy.data.objects[entry["replaced_m2_actor"]]
        obj.hide_render = True
        obj.hide_set(True)
    for old_collection in scene.collection.children:
        if old_collection.name.startswith(OWNER+"_") and old_collection != collection:
            old_collection.hide_viewport = True
            old_collection.hide_render = True
    (directory.parent/"latest.json").write_text(json.dumps(dict(
        manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=digest(manifest_path)), indent=2))
    return dict(manifest=manifest_path.relative_to(ROOT).as_posix(), version=version, **summary)


if __name__ in {"__main__", "<run_path>"}:
    result = build()
