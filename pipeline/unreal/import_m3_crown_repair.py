"""Import the separate crown repair without changing the 1,012 full trees."""
import hashlib
import json
import runpy
from collections import defaultdict
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_M3CrownRepair"
PREFIX = "/Game/StanleyPark/Seawall/M3CrownRepair"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def apply():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name() != "/Game/Maps/StanleyParkSeawall.StanleyParkSeawall":
        raise RuntimeError("Open the Seawall map and stop Play")
    pointer = read("exports/m3-crown-repair/latest.json")
    source = ROOT/pointer["manifest"]
    if sha(source) != pointer["sha256"]:
        raise RuntimeError("Crown repair manifest changed")
    manifest = read(pointer["manifest"])
    for path, expected in manifest["input_hashes"].items():
        if sha(ROOT/path) != expected:
            raise RuntimeError("Crown repair source changed: "+path)
    items = [item for tree in manifest["trees"] for item in tree["lods"]]
    items += [row["replacement"] for row in manifest["coarse_replacements"]]
    for item in items:
        if sha(ROOT/item["fbx"]) != item["sha256"]:
            raise RuntimeError("Crown repair FBX changed")
    helpers = runpy.run_path(str(ROOT/"pipeline/unreal/import_m3_forest.py"), run_name="m3_repair_import_helpers")
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    root = manifest["asset_root"]
    if not root.startswith(PREFIX+"/v_"):
        raise RuntimeError("Invalid crown repair namespace")
    labels = defaultdict(list)
    for actor in actors.get_all_level_actors():
        labels[actor.get_actor_label()].append(actor)
    for row in manifest["coarse_replacements"]:
        if len(labels[row["replaced_actor"]]) != 1:
            raise RuntimeError("Expected one active source tile: "+row["replaced_actor"])
    owned, mesh_to_id = {}, {}
    for path in assets.list_assets(PREFIX, recursive=True, include_folder=False):
        if "/Foliage/" not in path:
            continue
        ft = assets.load_asset(path)
        if isinstance(ft, unreal.FoliageType_InstancedStaticMesh) and assets.get_metadata_tag(ft, "SP_Owner") == OWNER:
            mesh = ft.get_editor_property("mesh")
            if mesh is None or not mesh.get_path_name().startswith(PREFIX):
                raise RuntimeError("Owned crown foliage has an external mesh")
            owned[ft.get_path_name()] = ft
            mesh_to_id[mesh.get_path_name()] = mesh.get_name()

    def inventory():
        rows = []
        for actor in actors.get_all_level_actors():
            if not isinstance(actor, unreal.InstancedFoliageActor):
                continue
            for component in actor.get_components_by_class(unreal.FoliageInstancedStaticMeshComponent):
                mesh = component.get_editor_property("static_mesh")
                tree_id = mesh_to_id.get(mesh.get_path_name()) if mesh else None
                if tree_id is None:
                    continue
                for index in range(component.get_instance_count()):
                    value = component.get_instance_transform(index, world_space=True)
                    rows.append(dict(tree_id=tree_id, component=component.get_path_name(), index=index,
                                     **helpers["transform_record"](value)))
        return rows

    def expected(rows):
        return [dict(source_id=row["source_id"], tree_id=row["tree_id"],
                     **helpers["transform_record"](helpers["transform"](row))) for row in rows]

    before = inventory()
    desired = expected(manifest["instances"])
    comparisons = dict(requested=helpers["compare_transforms"](before, desired))
    active_path = ROOT/"exports/m3-crown-repair/active-unreal.json"
    if active_path.exists():
        active = read(active_path.relative_to(ROOT))
        if sha(ROOT/active["manifest"]) != active["sha256"]:
            raise RuntimeError("Active crown repair record changed")
        previous = read(active["manifest"])
        comparisons["active"] = helpers["compare_transforms"](before, expected(previous["instances"]))
    if before and not any(row["matches"] for row in comparisons.values()):
        diagnostic = helpers["write_transform_diagnostic"]("crown-preflight", pointer, before, comparisons)
        raise RuntimeError("Crown transforms contain unrecorded edits; see "+diagnostic)
    visibility_rows = []
    replaced_labels = {row["replaced_actor"] for row in manifest["coarse_replacements"]}
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label() in replaced_labels or unreal.Name(OWNER) in actor.tags:
            visibility_rows.append(dict(label=actor.get_actor_label(), hidden=actor.get_editor_property("hidden"),
                editor_hidden=actor.is_temporarily_hidden_in_editor(), components=[dict(path=c.get_path_name(),
                visible=c.get_editor_property("visible"), hidden_in_game=c.get_editor_property("hidden_in_game"))
                for c in actor.get_components_by_class(unreal.StaticMeshComponent)]))
    record = dict(success=False, manifest=pointer, importer_sha256=sha(Path(__file__)),
        matching_helper_sha256=sha(ROOT/"pipeline/unreal/import_m3_forest.py"),
        prior_instances=before, prior_visibility=visibility_rows, application_run=False)
    attempt = 1
    while source.with_name(f"unreal-restore-{attempt:03d}.json").exists():
        attempt += 1
    restoration = source.with_name(f"unreal-restore-{attempt:03d}.json")
    restoration.write_text(json.dumps(record, indent=2))
    record_path = source.with_name("unreal-apply.json")
    record_path.write_text(json.dumps(record, indent=2))

    def import_mesh(item, name, lods=None):
        path = root+"/Meshes/"+name
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
                destination_name=name, automated=True, replace_existing=False, save=False,
                factory=unreal.FbxFactory(), options=options).items():
                task.set_editor_property(key, value)
            tools.import_asset_tasks([task])
            mesh = assets.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError("Crown mesh import failed: "+path)
        data = mesh.get_editor_property("asset_import_data")
        if not data or Path(data.get_first_filename()).resolve() != (ROOT/item["fbx"]).resolve():
            raise RuntimeError("Crown mesh has another source")
        box = mesh.get_bounding_box()
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        if any(abs(a-b)>1 for a,b in zip(actual, item["bounds_min_cm"]+item["bounds_max_cm"])):
            raise RuntimeError("Crown import bounds changed")
        if lods:
            for index, lod in enumerate(lods[1:], 1):
                if mesh.get_num_lods() <= index and meshes.import_lod(mesh, index, str(ROOT/lod["fbx"])) != index:
                    raise RuntimeError("Crown LOD import failed")
            if mesh.get_num_lods() != 4 or not meshes.set_lod_screen_sizes(mesh, manifest["settings"]["lod_screen_sizes"]):
                raise RuntimeError("Crown LOD setup failed")
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            material_name = str(slot.get_editor_property("imported_material_slot_name"))
            if material_name not in item["materials"]:
                raise RuntimeError("Unexpected crown material slot")
            material = assets.load_asset(manifest["baseline_asset_root"]+"/Materials/"+material_name+"_Graph02")
            if material is None:
                raise RuntimeError("Accepted tree material missing: "+material_name)
            mesh.set_material(index, material)
        assets.set_metadata_tag(mesh, "SP_Owner", OWNER)
        assets.set_metadata_tag(mesh, "SP_SourceHash", item["sha256"])
        assets.save_loaded_asset(mesh)
        return mesh

    unreal.SystemLibrary.execute_console_command(world, "Interchange.FeatureFlags.Import.FBX 0")
    foliage = {}
    for tree in manifest["trees"]:
        mesh = import_mesh(tree["lods"][0], tree["id"], tree["lods"])
        name = "FT_"+tree["id"].removeprefix("SM_")
        path = root+"/Foliage/"+name
        ft = assets.load_asset(path)
        if ft is None:
            ft = tools.create_asset(name, root+"/Foliage", unreal.FoliageType_InstancedStaticMesh,
                                    unreal.FoliageType_InstancedStaticMeshFactory())
            if ft is None:
                raise RuntimeError("Cannot create crown foliage type")
            ft.set_editor_property("mesh", mesh)
            ft.set_editor_property("enable_density_scaling", False)
            ft.set_editor_property("enable_cull_distance_scaling", False)
            ft.set_editor_property("cull_distance", unreal.Int32Interval(0, 0))
            ft.set_editor_property("cast_shadow", True)
            ft.set_editor_property("receives_decals", False)
            body = ft.get_editor_property("body_instance")
            body.set_editor_property("collision_enabled", unreal.CollisionEnabled.NO_COLLISION)
            ft.set_editor_property("body_instance", body)
            assets.set_metadata_tag(ft, "SP_Owner", OWNER)
            assets.save_loaded_asset(ft)
        if assets.get_metadata_tag(ft, "SP_Owner") != OWNER:
            raise RuntimeError("Crown foliage ownership mismatch")
        foliage[tree["id"]] = ft
        owned[ft.get_path_name()] = ft
        mesh_to_id[mesh.get_path_name()] = tree["id"]
    coarse = {r["replacement"]["name"]: import_mesh(r["replacement"], r["replacement"]["name"])
              for r in manifest["coarse_replacements"]}
    if not comparisons["requested"]["matches"]:
        for ft in owned.values():
            unreal.InstancedFoliageActor.remove_all_instances(world, ft)
        if inventory():
            raise RuntimeError("Crown instances remain after owned removal")
        grouped = defaultdict(list)
        for row in manifest["instances"]:
            grouped[row["tree_id"]].append(helpers["transform"](row))
        for tree_id, values in grouped.items():
            unreal.InstancedFoliageActor.add_instances(world, foliage[tree_id], values)

    def visibility(actor, enabled):
        actor.modify()
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            component.modify()
            component.set_visibility(enabled, propagate_to_children=False)
            component.set_hidden_in_game(not enabled, propagate_to_children=False)
        actor.set_actor_hidden_in_game(not enabled)
        actor.set_is_temporarily_hidden_in_editor(not enabled)

    for actor in actors.get_all_level_actors():
        if unreal.Name(OWNER) in actor.tags:
            visibility(actor, False)
    for row in manifest["coarse_replacements"]:
        visibility(labels[row["replaced_actor"]][0], False)
        item = row["replacement"]
        matching = labels[item["name"]]
        if len(matching) > 1:
            raise RuntimeError("Duplicate crown tile actor")
        actor = matching[0] if matching else actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*item["position_cm"]))
        actor.set_actor_label(item["name"])
        actor.set_folder_path("StanleyPark/20_Seawall/Trees")
        component = actor.static_mesh_component
        component.set_static_mesh(coarse[item["name"]])
        component.set_editor_property("use_default_collision", False)
        component.set_collision_profile_name("NoCollision")
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if unreal.Name(OWNER) not in actor.tags:
            actor.tags = list(actor.tags)+[unreal.Name(OWNER)]
        visibility(actor, True)
    final = inventory()
    match = helpers["compare_transforms"](final, desired)
    if not match["matches"]:
        diagnostic = helpers["write_transform_diagnostic"]("crown-final", pointer, final, dict(requested=match))
        raise RuntimeError("Final crown transforms differ: "+diagnostic)
    if not levels.save_current_level():
        raise RuntimeError("Cannot save crown repair map")
    record.update(success=True, final_instances=final, transform_comparison=match,
        summary=manifest["summary"], restoration=restoration.relative_to(ROOT).as_posix(), visual_review_complete=False)
    record_path.write_text(json.dumps(record, indent=2))
    active_path.write_text(json.dumps(pointer, indent=2))
    return dict(success=True, record=record_path.relative_to(ROOT).as_posix(), **manifest["summary"])


if __name__ in {"__main__", "<run_path>"}:
    result = apply()
