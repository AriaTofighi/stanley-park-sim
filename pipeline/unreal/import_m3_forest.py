"""Apply the M3 forest sidecar in the already open Seawall map.

Reuse the six accepted foliage types and their four LODs. Exact source
instances are checked before replacement; unrelated foliage is untouched.
"""
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_M3Forest"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def transform(row):
    east, north, up = row["position_local_m"]
    return unreal.Transform(location=unreal.Vector(north*100, east*100, up*100),
        rotation=unreal.Rotator(pitch=0.0, yaw=row["yaw_degrees"], roll=0.0),
        scale=unreal.Vector(*row["scale"]))


def transform_record(value):
    return dict(translation=[value.translation.x, value.translation.y, value.translation.z],
        rotation=[value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w],
        scale=[value.scale3d.x, value.scale3d.y, value.scale3d.z])


TRANSFORM_TOLERANCE = dict(translation_cm=0.1, rotation_degrees=0.005, scale_absolute=0.00001)


def transform_delta(actual, expected):
    translation = math.dist(actual["translation"], expected["translation"])
    a, b = actual["rotation"], expected["rotation"]
    norm = math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    if norm < 1e-12:
        angle = 180.0
    else:
        # Quaternions q and -q describe the same orientation. Normalize both
        # before the angular comparison; foliage storage uses float values.
        cosine = min(1.0, max(0.0, abs(sum(x*y for x, y in zip(a, b)))/norm))
        angle = math.degrees(2*math.acos(cosine))
    scale = max(abs(x-y) for x, y in zip(actual["scale"], expected["scale"]))
    return dict(translation_cm=translation, rotation_degrees=angle, scale_absolute=scale)


def compare_transforms(actual, expected):
    """One-to-one matching with real tolerances, never rounded-bin equality."""
    expected_by_tree = defaultdict(list)
    for index, row in enumerate(expected):
        expected_by_tree[row["tree_id"]].append(index)
    adjacency, nearest = [], []
    for row in actual:
        candidates = []
        nearest_row = None
        for index in expected_by_tree[row["tree_id"]]:
            other = expected[index]
            distance = math.dist(row["translation"], other["translation"])
            if nearest_row is None or distance < nearest_row[0]:
                nearest_row = (distance, index)
            if distance > TRANSFORM_TOLERANCE["translation_cm"]:
                continue
            delta = transform_delta(row, other)
            if all(math.isfinite(value) and value <= TRANSFORM_TOLERANCE[key] for key, value in delta.items()):
                candidates.append((distance, index))
        adjacency.append([index for _, index in sorted(candidates)])
        nearest.append(nearest_row[1] if nearest_row else None)
    # An augmenting path gives a genuine bijection, even when two source
    # transforms are identical or are within tolerance of the same instance.
    expected_owner = {}

    def assign(actual_index, visited):
        for expected_index in adjacency[actual_index]:
            if expected_index in visited:
                continue
            visited.add(expected_index)
            if expected_index not in expected_owner or assign(expected_owner[expected_index], visited):
                expected_owner[expected_index] = actual_index
                return True
        return False

    for index in sorted(range(len(actual)), key=lambda value: len(adjacency[value])):
        assign(index, set())
    matched_actual = set(expected_owner.values())
    mismatches = []
    for index, row in enumerate(actual):
        if index in matched_actual:
            continue
        reference = expected[nearest[index]] if nearest[index] is not None else None
        mismatches.append(dict(actual=row, nearest_expected=reference,
            delta=transform_delta(row, reference) if reference else None))
    maximum = {key: 0.0 for key in TRANSFORM_TOLERANCE}
    for expected_index, actual_index in expected_owner.items():
        for key, value in transform_delta(actual[actual_index], expected[expected_index]).items():
            maximum[key] = max(maximum[key], value)
    return dict(matches=len(actual) == len(expected) == len(expected_owner),
        actual_count=len(actual), expected_count=len(expected), matched_count=len(expected_owner),
        tolerance=TRANSFORM_TOLERANCE, maximum_matched_delta=maximum, unmatched_actual=mismatches,
        unmatched_expected=[row for index, row in enumerate(expected) if index not in expected_owner])


def write_transform_diagnostic(stage, pointer, actual, comparisons):
    directory = ROOT/"evidence"
    directory.mkdir(exist_ok=True)
    attempt = 1
    while (directory/f"m3-forest-transform-{stage}-{attempt:03d}.json").exists():
        attempt += 1
    path = directory/f"m3-forest-transform-{stage}-{attempt:03d}.json"
    path.write_text(json.dumps(dict(stage=stage, manifest=pointer,
        importer_sha256=digest(Path(__file__)), observed_transforms=actual,
        comparisons=comparisons), indent=2), encoding="utf-8")
    return path.relative_to(ROOT).as_posix()


def apply(map_path):
    pointer = read("exports/m3-forest/latest.json")
    source = ROOT/pointer["manifest"]
    if digest(source) != pointer["sha256"]:
        raise RuntimeError("M3 forest manifest changed")
    manifest = read(pointer["manifest"])
    cfg = manifest["settings"]
    if map_path != "/Game/Maps/StanleyParkSeawall" or map_path != cfg["map_path"]:
        raise RuntimeError("M3 forest requires the separate Seawall map")
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if editor.get_game_world() is not None:
        raise RuntimeError("Stop Play before applying M3 forest assets")
    if world.get_path_name().split(".")[0] != map_path:
        raise RuntimeError("Open the Seawall map first")
    for path, expected in manifest["input_hashes"].items():
        if digest(ROOT/path) != expected:
            raise RuntimeError("M3 forest input changed: "+path)
    baseline = read(manifest["baseline_manifest"])
    for path, expected in baseline["input_hashes"].items():
        if not path.startswith("live_") and digest(ROOT/path) != expected:
            raise RuntimeError("M2 tree input changed: "+path)
    for entry in manifest["coarse_replacements"]:
        item = entry["replacement"]
        if digest(ROOT/item["fbx"]) != item["sha256"]:
            raise RuntimeError("M3 canopy export changed")
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    root = manifest["asset_root"]
    if not root.startswith("/Game/StanleyPark/Seawall/M3Forest/v_"):
        raise RuntimeError("Invalid M3 forest namespace")
    by_label = defaultdict(list)
    for actor in actors.get_all_level_actors():
        by_label[actor.get_actor_label()].append(actor)
    for entry in manifest["coarse_replacements"]:
        if len(by_label[entry["replaced_m2_actor"]]) != 1:
            raise RuntimeError("Expected one M2 background actor: "+entry["replaced_m2_actor"])
    foliage, mesh_ids = {}, {}
    for tree in baseline["trees"]:
        name = "FT_"+tree["id"].removeprefix("SM_")
        ft = assets.load_asset(baseline["asset_root"]+"/Foliage/"+name)
        if not isinstance(ft, unreal.FoliageType_InstancedStaticMesh) or assets.get_metadata_tag(ft, "SP_Owner") != "SP_SeawallTrees":
            raise RuntimeError("Accepted M2 foliage type is missing or unowned")
        mesh = ft.get_editor_property("mesh")
        if mesh is None or mesh.get_num_lods() != 4:
            raise RuntimeError("Accepted four-LOD tree mesh is missing")
        foliage[tree["id"]] = ft
        mesh_ids[mesh.get_path_name()] = tree["id"]

    def inventory():
        records, values_flat = [], []
        for actor in actors.get_all_level_actors():
            if not isinstance(actor, unreal.InstancedFoliageActor):
                continue
            for component in actor.get_components_by_class(unreal.FoliageInstancedStaticMeshComponent):
                mesh = component.get_editor_property("static_mesh")
                tree_id = mesh_ids.get(mesh.get_path_name()) if mesh else None
                if tree_id is None:
                    continue
                values = []
                for index in range(component.get_instance_count()):
                    value = component.get_instance_transform(index, world_space=True)
                    saved = transform_record(value)
                    values.append(saved)
                    values_flat.append(dict(tree_id=tree_id, component=component.get_path_name(),
                                            instance_index=index, **saved))
                records.append(dict(component=component.get_path_name(), tree_id=tree_id, transforms=values))
        return records, values_flat

    def expected(rows):
        return [dict(source_id=row["source_id"], tree_id=row["tree_id"],
                     **transform_record(transform(row))) for row in rows]

    before, current_values = inventory()
    baseline_values = expected(baseline["instances"])
    desired_values = expected(baseline["instances"]+manifest["instances"])
    allowed = [("m2_baseline", baseline_values), ("m3_requested", desired_values)]
    active_path = ROOT/"exports/m3-forest/active-unreal.json"
    if active_path.exists():
        active = read(active_path.relative_to(ROOT))
        if digest(ROOT/active["manifest"]) != active["sha256"]:
            raise RuntimeError("Active M3 restoration source changed")
        prior = read(active["manifest"])
        allowed.append(("m3_active", expected(baseline["instances"]+prior["instances"])))
    comparisons = {name: compare_transforms(current_values, rows) for name, rows in allowed}
    diagnostic = write_transform_diagnostic("preflight", pointer, current_values, comparisons)
    if not any(row["matches"] for row in comparisons.values()):
        raise RuntimeError("Tree transforms differ from the recorded M2/M3 set; preserve manual edits. See "+diagnostic)
    record = dict(success=False, version=manifest["version"], map=map_path,
        manifest=pointer["manifest"], manifest_sha256=pointer["sha256"], importer_sha256=digest(Path(__file__)),
        prior_foliage=before, prior_actor_visibility=[], transform_preflight=diagnostic, application_run=False)
    for actor in actors.get_all_level_actors():
        if unreal.Name(OWNER) in actor.tags or actor.get_actor_label() in {r["replaced_m2_actor"] for r in manifest["coarse_replacements"]}:
            record["prior_actor_visibility"].append(dict(label=actor.get_actor_label(),
                hidden=actor.get_editor_property("hidden"), editor_hidden=actor.is_temporarily_hidden_in_editor(),
                components=[dict(path=c.get_path_name(), visible=c.get_editor_property("visible"),
                                 hidden_in_game=c.get_editor_property("hidden_in_game"))
                            for c in actor.get_components_by_class(unreal.StaticMeshComponent)]))
    attempt = 1
    while source.with_name(f"unreal-restore-{attempt:03d}.json").exists():
        attempt += 1
    restore = source.with_name(f"unreal-restore-{attempt:03d}.json")
    restore.write_text(json.dumps(record, indent=2))
    record_path = source.with_name("unreal-apply.json")
    record_path.write_text(json.dumps(record, indent=2))

    def import_mesh(item):
        path = root+"/Meshes/"+item["name"]
        mesh = assets.load_asset(path)
        if mesh is None:
            options = unreal.FbxImportUI()
            for key, value in dict(import_mesh=True, import_as_skeletal=False, import_materials=False,
                import_textures=False, automated_import_should_detect_type=False,
                mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items():
                options.set_editor_property(key, value)
            for key, value in dict(combine_meshes=True, convert_scene=False, convert_scene_unit=False,
                force_front_x_axis=False, generate_lightmap_u_vs=False, auto_generate_collision=False,
                transform_vertex_to_absolute=True, build_nanite=False).items():
                options.static_mesh_import_data.set_editor_property(key, value)
            options.static_mesh_import_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
            task = unreal.AssetImportTask()
            for key, value in dict(filename=str(ROOT/item["fbx"]), destination_path=root+"/Meshes",
                destination_name=item["name"], automated=True, replace_existing=False, save=False,
                factory=unreal.FbxFactory(), options=options).items():
                task.set_editor_property(key, value)
            tools.import_asset_tasks([task])
            mesh = assets.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError("M3 canopy import failed: "+path)
        source_data = mesh.get_editor_property("asset_import_data")
        if not source_data or Path(source_data.get_first_filename()).resolve() != (ROOT/item["fbx"]).resolve():
            raise RuntimeError("M3 mesh has another source: "+path)
        bounds = mesh.get_bounding_box()
        actual_min = [bounds.min.x, bounds.min.y, bounds.min.z]
        actual_max = [bounds.max.x, bounds.max.y, bounds.max.z]
        if any(abs(a-b) > 1 for a,b in zip(actual_min+actual_max, item["bounds_min_cm"]+item["bounds_max_cm"])):
            raise RuntimeError("M3 canopy import bounds differ from export")
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            name = str(slot.get_editor_property("imported_material_slot_name"))
            if name not in item["materials"]:
                raise RuntimeError("Unexpected canopy material slot: "+name)
            material = assets.load_asset(baseline["asset_root"]+"/Materials/"+name+"_Graph02")
            if material is None:
                raise RuntimeError("Accepted M2 tree material is missing: "+name)
            mesh.set_material(index, material)
        assets.set_metadata_tag(mesh, "SP_Owner", OWNER)
        assets.set_metadata_tag(mesh, "SP_SourceHash", item["sha256"])
        assets.save_loaded_asset(mesh)
        return mesh

    unreal.SystemLibrary.execute_console_command(world, "Interchange.FeatureFlags.Import.FBX 0")
    imported = {row["replacement"]["name"]: import_mesh(row["replacement"]) for row in manifest["coarse_replacements"]}

    def visibility(actor, enabled):
        actor.modify()
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            component.modify()
            component.set_visibility(enabled, propagate_to_children=False)
            component.set_hidden_in_game(not enabled, propagate_to_children=False)
        actor.set_actor_hidden_in_game(not enabled)
        actor.set_is_temporarily_hidden_in_editor(not enabled)

    # Same six native types: retain the entire accepted set and add only the
    # immutable manifest rows. This also keeps ordinary foliage tooling usable.
    if not comparisons["m3_requested"]["matches"]:
        for ft in foliage.values():
            unreal.InstancedFoliageActor.remove_all_instances(world, ft)
        if inventory()[1]:
            raise RuntimeError("Tree instances remain after owned set removal")
        grouped = defaultdict(list)
        for row in baseline["instances"]+manifest["instances"]:
            grouped[row["tree_id"]].append(transform(row))
        for tree_id, values in grouped.items():
            unreal.InstancedFoliageActor.add_instances(world, foliage[tree_id], values)
    for actor in actors.get_all_level_actors():
        if unreal.Name(OWNER) in actor.tags:
            visibility(actor, False)
    for row in manifest["coarse_replacements"]:
        visibility(by_label[row["replaced_m2_actor"]][0], False)
        item = row["replacement"]
        found = by_label[item["name"]]
        if len(found) > 1:
            raise RuntimeError("Duplicate M3 forest actor")
        actor = found[0] if found else actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*item["position_cm"]))
        actor.set_actor_label(item["name"])
        actor.set_folder_path("StanleyPark/20_Seawall/Trees")
        actor.static_mesh_component.set_static_mesh(imported[item["name"]])
        actor.static_mesh_component.set_editor_property("use_default_collision", False)
        actor.static_mesh_component.set_collision_profile_name("NoCollision")
        actor.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if unreal.Name(OWNER) not in actor.tags:
            actor.tags = list(actor.tags)+[unreal.Name(OWNER)]
        visibility(actor, True)
    final, final_values = inventory()
    final_comparison = compare_transforms(final_values, desired_values)
    final_diagnostic = write_transform_diagnostic("final", pointer, final_values, dict(m3_requested=final_comparison))
    if not final_comparison["matches"]:
        raise RuntimeError("Final tree source transforms differ from the manifest. See "+final_diagnostic)
    if not levels.save_current_level():
        raise RuntimeError("Cannot save the Seawall map")
    record.update(success=True, restoration=restore.relative_to(ROOT).as_posix(),
                  summary=manifest["summary"], final_foliage=final,
                  transform_final=final_diagnostic, visual_review_complete=False)
    record_path.write_text(json.dumps(record, indent=2))
    active_path.write_text(json.dumps(pointer, indent=2))
    return dict(success=True, version=manifest["version"], **manifest["summary"],
                record=record_path.relative_to(ROOT).as_posix(), application_run=False)


if __name__ in {"__main__", "<run_path>"}:
    requested_map = (globals().get("SP_SEAWALL_MAP_PATH") or os.environ.get("SP_SEAWALL_MAP_PATH")
                     or "/Game/Maps/StanleyParkSeawall")
    result = apply(requested_map)
