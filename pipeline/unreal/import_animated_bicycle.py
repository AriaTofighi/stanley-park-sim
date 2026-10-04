"""Import separate Seawall frame, crank and pedal assets; preserve the M1 asset."""
from pathlib import Path
import hashlib
import json
import unreal

ROOT = Path(__file__).resolve().parents[2]
source = json.loads((ROOT / 'manifests/animated-bicycle.json').read_text())
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
old = assets.load_asset('/Game/StanleyPark/Kit/SM_Bicycle')
if old is None:
    raise RuntimeError('Original frame is missing')
original_path = ROOT / 'unreal/Content/StanleyPark/Kit/SM_Bicycle.uasset'
original_hash = hashlib.sha256(original_path.read_bytes()).hexdigest()
materials = {str(slot.get_editor_property('imported_material_slot_name')):slot.get_editor_property('material_interface')
             for slot in old.get_editor_property('static_materials')}
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
records = []
for entry in source['assets']:
    fbx = ROOT / entry['fbx']
    if hashlib.sha256(fbx.read_bytes()).hexdigest() != entry['sha256']:
        raise RuntimeError('Export differs from its manifest')
    options = unreal.FbxImportUI()
    for key, value in dict(import_mesh=True, import_as_skeletal=False, import_materials=False,
        import_textures=False, automated_import_should_detect_type=False,
        mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items():
        options.set_editor_property(key, value)
    for key, value in dict(combine_meshes=True, convert_scene=False, convert_scene_unit=False,
        force_front_x_axis=False, generate_lightmap_u_vs=False, auto_generate_collision=False,
        transform_vertex_to_absolute=True, build_nanite=False).items():
        options.static_mesh_import_data.set_editor_property(key, value)
    task = unreal.AssetImportTask()
    task.filename = str(fbx)
    task.destination_path = '/Game/StanleyPark/Kit'
    task.destination_name = entry['name']
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.factory = unreal.FbxFactory()
    task.options = options
    tools.import_asset_tasks([task])
    mesh = assets.load_asset(task.destination_path + '/' + task.destination_name)
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError('Static mesh import failed: ' + entry['name'])
    slots = list(mesh.get_editor_property('static_materials'))
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property('imported_material_slot_name'))
        if name not in materials or materials[name] is None:
            raise RuntimeError('Missing original material: ' + name)
        mesh.set_material(index, materials[name])
    bounds = mesh.get_bounding_box()
    actual_min = [bounds.min.x, bounds.min.y, bounds.min.z]
    actual_max = [bounds.max.x, bounds.max.y, bounds.max.z]
    error = max(abs(a-b) for a,b in zip(actual_min + actual_max, entry['bounds_min_cm'] + entry['bounds_max_cm']))
    if error > .05:
        raise RuntimeError('Bicycle export coordinate contract failed: ' + str(error))
    assets.save_loaded_asset(mesh)
    records.append(dict(asset=mesh.get_path_name(), bounds_error_cm=error,
        material_slots=[mesh.get_material(i).get_path_name() for i in range(len(slots))]))
if hashlib.sha256(original_path.read_bytes()).hexdigest() != original_hash:
    raise RuntimeError('Original M1 asset changed')
(ROOT / 'evidence/animated-bicycle-import.json').write_text(json.dumps(dict(
    original_unchanged=True, original_sha256=original_hash, assets=records, application_tests_run=False), indent=2))
