"""Import only the three gull assets. No map edits, enable flag, or play session.

Run after build_seawall_bird.py through Unreal MCP with runpy.run_path.
Bounds/material checks are import guards; live visual acceptance is separate.
"""
from pathlib import Path
import hashlib
import json
import unreal

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = "/Game/StanleyPark/Seawall/Birds"
config_path = ROOT / "manifests/seawall-birds.json"
source = json.loads((ROOT / "manifests/seawall-birds-export.json").read_text(encoding="utf-8"))
config = json.loads(config_path.read_text(encoding="utf-8"))
if source["runtime_config_sha256"] != hashlib.sha256(config_path.read_bytes()).hexdigest():
    raise RuntimeError("Bird config changed after export; rebuild the bird assets")
if config["schema_version"] != 1 or config["coordinate_contract"] != "unreal_north_east_up_cm":
    raise RuntimeError("Unsupported bird coordinates")
expected_names = {"SM_GullBody", "SM_GullWingLeft", "SM_GullWingRight"}
if {item["name"] for item in source["assets"]} != expected_names or len(source["assets"]) != 3:
    raise RuntimeError("Expected the body and two shoulder-pivot wings")
for zone in config["zones"]:
    east, north, up = zone["centre_local_east_north_up_m"]
    if zone["centre_unreal_cm"] != [north * 100, east * 100, up * 100]:
        raise RuntimeError("Bird zone axis transfer differs")

assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
cache = {}


def material(spec):
    fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    name = spec["name"] + "_" + fingerprint[:10]
    if name in cache:
        return cache[name]
    path = DESTINATION + "/" + name
    if assets.does_asset_exist(path):
        mat = assets.load_asset(path)
        if assets.get_metadata_tag(mat, "SP_SeawallBirdMaterial") != fingerprint:
            raise RuntimeError("Existing bird material has a different source: " + path)
    else:
        mat = tools.create_asset(name, DESTINATION, unreal.Material, unreal.MaterialFactoryNew())
        if mat is None:
            raise RuntimeError("Cannot create bird material: " + path)
        expression = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
        expression.set_editor_property("constant", unreal.LinearColor(*spec["color"], 1.0))
        if not unreal.MaterialEditingLibrary.connect_material_property(expression, "", unreal.MaterialProperty.MP_BASE_COLOR):
            raise RuntimeError("Cannot connect gull base color")
        roughness = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant)
        roughness.set_editor_property("r", 0.85)
        if not unreal.MaterialEditingLibrary.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS):
            raise RuntimeError("Cannot connect gull roughness")
        unreal.MaterialEditingLibrary.recompile_material(mat)
        assets.set_metadata_tag(mat, "SP_SeawallBirdMaterial", fingerprint)
        assets.save_loaded_asset(mat)
    cache[name] = mat
    return mat


records = []
for item in source["assets"]:
    fbx = ROOT / item["fbx"]
    if hashlib.sha256(fbx.read_bytes()).hexdigest() != item["sha256"]:
        raise RuntimeError("Bird FBX changed after export: " + item["name"])
    options = unreal.FbxImportUI()
    for key, value in dict(import_mesh=True, import_as_skeletal=False, import_materials=False,
            import_textures=False, import_animations=False, automated_import_should_detect_type=False,
            mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items():
        options.set_editor_property(key, value)
    for key, value in dict(combine_meshes=True, convert_scene=False, convert_scene_unit=False,
            force_front_x_axis=False, generate_lightmap_u_vs=False, auto_generate_collision=False,
            transform_vertex_to_absolute=True, build_nanite=False).items():
        options.static_mesh_import_data.set_editor_property(key, value)
    options.static_mesh_import_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    task = unreal.AssetImportTask()
    task.filename = str(fbx)
    task.destination_path = DESTINATION
    task.destination_name = item["name"]
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    task.factory = unreal.FbxFactory()
    task.options = options
    tools.import_asset_tasks([task])
    path = DESTINATION + "/" + item["name"]
    if path not in [str(value).split(".")[0] for value in task.imported_object_paths]:
        raise RuntimeError("Import did not produce " + path)
    mesh = assets.load_asset(path)
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError("Missing bird mesh: " + path)
    bounds = mesh.get_bounding_box()
    actual = [bounds.min.x, bounds.min.y, bounds.min.z, bounds.max.x, bounds.max.y, bounds.max.z]
    expected = item["bounds_min_cm"] + item["bounds_max_cm"]
    error = max(abs(a - b) for a, b in zip(actual, expected))
    if error > 0.25:
        raise RuntimeError(f"Bird bounds differ by {error:.4f} cm: {item['name']}")
    materials = {spec["name"]: spec for spec in item["materials"]}
    slots = list(mesh.get_editor_property("static_materials"))
    names = [str(slot.get_editor_property("imported_material_slot_name")) for slot in slots]
    if set(names) != set(materials):
        raise RuntimeError(f"Bird material slots differ: {names} vs {list(materials)}")
    for index, name in enumerate(names):
        mesh.set_material(index, material(materials[name]))
    unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).remove_collisions(mesh)
    assets.save_loaded_asset(mesh)
    records.append(dict(asset_path=path, bounds_error_cm=error, source_sha256=item["sha256"]))

# Stage only after all three meshes pass their import guards. Existing packaging
# already includes WorldData and /Game/StanleyPark. Runtime has its own map guard.
target = ROOT / "unreal/Content/WorldData/seawall-birds.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
result = dict(assets=records, runtime_config=str(target),
    enabled_by_default=config["enabled_by_default"], visual_acceptance=False)
unreal.log("SP_SEAWALL_BIRDS_IMPORT: " + json.dumps(result))
