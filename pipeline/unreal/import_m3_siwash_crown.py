"""Apply the Siwash foliage correction in Seawall, retaining original geometry."""
import hashlib
import json
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_M3SiwashCrown"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def invariant(actor):
    component = actor.static_mesh_component
    transform = actor.get_actor_transform()
    return dict(mesh=component.static_mesh.get_path_name(),
        translation=[transform.translation.x, transform.translation.y, transform.translation.z],
        rotation=[transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w],
        scale=[transform.scale3d.x, transform.scale3d.y, transform.scale3d.z],
        collision=str(component.get_collision_enabled()), profile=str(component.get_collision_profile_name()))


def apply():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name() != "/Game/Maps/StanleyParkSeawall.StanleyParkSeawall":
        raise RuntimeError("Open the Seawall map and stop Play")
    pointer = read("exports/m3-siwash-crown/latest.json")
    source = ROOT/pointer["manifest"]
    if sha(source) != pointer["sha256"]:
        raise RuntimeError("Siwash crown manifest changed")
    manifest = read(pointer["manifest"])
    for path, expected in manifest["input_hashes"].items():
        if sha(ROOT/path) != expected:
            raise RuntimeError("Siwash crown source changed: "+path)
    for item in manifest["lods"]:
        if sha(ROOT/item["fbx"]) != item["sha256"]:
            raise RuntimeError("Siwash crown FBX changed")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    labels = {}
    for actor in actors.get_all_level_actors():
        labels.setdefault(actor.get_actor_label(), []).append(actor)
    protected = {}
    for name in (manifest["replaced_actor"], manifest["protected_rock_actor"]):
        if len(labels.get(name, [])) != 1:
            raise RuntimeError("Expected one protected Siwash source: "+name)
        protected[name] = invariant(labels[name][0])
    original = labels[manifest["replaced_actor"]][0]
    component = original.static_mesh_component
    record = dict(success=False, manifest=pointer, importer_sha256=sha(Path(__file__)),
        protected_before=protected, prior_visibility=dict(hidden=original.get_editor_property("hidden"),
            editor_hidden=original.is_temporarily_hidden_in_editor(), visible=component.get_editor_property("visible"),
            hidden_in_game=component.get_editor_property("hidden_in_game")), application_run=False)
    attempt = 1
    while source.with_name(f"unreal-restore-{attempt:03d}.json").exists():
        attempt += 1
    restoration = source.with_name(f"unreal-restore-{attempt:03d}.json")
    restoration.write_text(json.dumps(record, indent=2))
    record_path = source.with_name("unreal-apply.json")
    record_path.write_text(json.dumps(record, indent=2))
    root, name = manifest["asset_root"], manifest["asset_name"]
    if not root.startswith("/Game/StanleyPark/Seawall/M3SiwashCrown/v_"):
        raise RuntimeError("Invalid Siwash crown namespace")
    item = manifest["lods"][0]
    mesh = assets.load_asset(root+"/Meshes/"+name)
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
        for key, value in dict(filename=str(ROOT/item["fbx"]), destination_path=root+"/Meshes", destination_name=name,
            automated=True, replace_existing=False, save=False, factory=unreal.FbxFactory(), options=options).items():
            task.set_editor_property(key, value)
        unreal.SystemLibrary.execute_console_command(world, "Interchange.FeatureFlags.Import.FBX 0")
        tools.import_asset_tasks([task])
        mesh = assets.load_asset(root+"/Meshes/"+name)
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError("Siwash crown mesh import failed")
    data = mesh.get_editor_property("asset_import_data")
    if not data or Path(data.get_first_filename()).resolve() != (ROOT/item["fbx"]).resolve():
        raise RuntimeError("Siwash mesh has another source")
    box = mesh.get_bounding_box()
    actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
    if any(abs(a-b)>1 for a,b in zip(actual, item["bounds_min_cm"]+item["bounds_max_cm"])):
        raise RuntimeError("Siwash crown bounds differ from export")
    for index, lod in enumerate(manifest["lods"][1:], 1):
        if mesh.get_num_lods() <= index and meshes.import_lod(mesh, index, str(ROOT/lod["fbx"])) != index:
            raise RuntimeError("Siwash crown LOD import failed")
    if mesh.get_num_lods() != 4 or not meshes.set_lod_screen_sizes(mesh, manifest["lod_screen_sizes"]):
        raise RuntimeError("Siwash crown LOD setup failed")
    for index, slot in enumerate(mesh.get_editor_property("static_materials")):
        material_name = str(slot.get_editor_property("imported_material_slot_name"))
        if material_name not in item["materials"]:
            raise RuntimeError("Unexpected Siwash crown material slot")
        material = assets.load_asset(manifest["baseline_asset_root"]+"/Materials/"+material_name+"_Graph02")
        if material is None:
            raise RuntimeError("Accepted foliage material missing")
        mesh.set_material(index, material)
    assets.set_metadata_tag(mesh, "SP_Owner", OWNER)
    assets.set_metadata_tag(mesh, "SP_SourceHash", item["sha256"])
    assets.save_loaded_asset(mesh)

    def visibility(actor, enabled):
        actor.modify()
        for c in actor.get_components_by_class(unreal.StaticMeshComponent):
            c.modify()
            c.set_visibility(enabled, propagate_to_children=False)
            c.set_hidden_in_game(not enabled, propagate_to_children=False)
        actor.set_actor_hidden_in_game(not enabled)
        actor.set_is_temporarily_hidden_in_editor(not enabled)

    for actor in actors.get_all_level_actors():
        if unreal.Name(OWNER) in actor.tags:
            visibility(actor, False)
    matches = labels.get(name, [])
    if len(matches)>1:
        raise RuntimeError("Duplicate Siwash crown actor")
    actor = matches[0] if matches else actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*item["position_cm"]))
    actor.set_actor_label(name)
    actor.set_folder_path("StanleyPark/20_Seawall/Trees")
    component = actor.static_mesh_component
    component.set_static_mesh(mesh)
    component.set_editor_property("use_default_collision", False)
    component.set_collision_profile_name("NoCollision")
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    if unreal.Name(OWNER) not in actor.tags:
        actor.tags = list(actor.tags)+[unreal.Name(OWNER)]
    visibility(actor, True)
    visibility(original, False)
    after = {name: invariant(labels[name][0]) for name in protected}
    if after != protected:
        raise RuntimeError("Protected Siwash geometry, transforms or collision changed")
    if not levels.save_current_level():
        raise RuntimeError("Cannot save the Siwash crown correction")
    record.update(success=True, protected_after=after, restoration=restoration.relative_to(ROOT).as_posix(),
        asset=mesh.get_path_name(), classified_returns=manifest["original_classified_returns"], visual_review_complete=False)
    record_path.write_text(json.dumps(record, indent=2))
    (source.parent.parent/"active-unreal.json").write_text(json.dumps(pointer, indent=2))
    return dict(success=True, version=manifest["version"], record=record_path.relative_to(ROOT).as_posix(),
                protected_geometry_unchanged=True, classified_returns=manifest["original_classified_returns"])


if __name__ in {"__main__", "<run_path>"}:
    result = apply()
