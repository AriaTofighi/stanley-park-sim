"""Import the original Blender explorer and four clips. Authoring only."""
from pathlib import Path
import hashlib
import json
import unreal

ROOT = Path(__file__).resolve().parents[2]
source = json.loads((ROOT/'manifests/explorer.json').read_text())
DEST = '/Game/StanleyPark/Explorer'
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
mesh = None
clips = {}
for name, entry in source['clips'].items():
    fbx = ROOT/entry['file']
    if hashlib.sha256(fbx.read_bytes()).hexdigest() != entry['sha256']:
        raise RuntimeError('Export differs from the character manifest')
    options = unreal.FbxImportUI()
    first = mesh is None
    for key, value in dict(import_mesh=first,import_as_skeletal=True,import_animations=True,
        import_materials=False,import_textures=False,create_physics_asset=False,
        automated_import_should_detect_type=False,
        mesh_type_to_import=unreal.FBXImportType.FBXIT_SKELETAL_MESH if first else unreal.FBXImportType.FBXIT_ANIMATION).items():
        options.set_editor_property(key,value)
    if not first:
        options.skeleton = mesh.get_editor_property('skeleton')
    for settings in [options.skeletal_mesh_import_data,options.anim_sequence_import_data]:
        for key,value in dict(convert_scene=False,convert_scene_unit=False,force_front_x_axis=False).items():
            settings.set_editor_property(key,value)
    options.anim_sequence_import_data.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    task = unreal.AssetImportTask()
    task.filename = str(fbx)
    task.destination_path = DEST
    task.destination_name = 'SK_Explorer' if first else 'A_Explorer_'+name
    task.automated=True
    task.replace_existing=True
    task.save=True
    task.factory=unreal.FbxFactory()
    task.options=options
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = [assets.load_asset(path) for path in task.imported_object_paths]
    if first:
        mesh = next((obj for obj in imported if isinstance(obj,unreal.SkeletalMesh)),None)
        if not mesh: raise RuntimeError('Character mesh import failed')
    candidates = [assets.load_asset(path) for path in assets.list_assets(DEST,recursive=False)]
    clip = next((a for a in candidates if isinstance(a,unreal.AnimSequence) and
                 a.get_name().startswith(task.destination_name) and
                 a.get_editor_property('skeleton') == mesh.get_editor_property('skeleton')),None)
    if not clip: raise RuntimeError('Missing animation: '+name)
    target=DEST+'/A_Explorer_'+name
    if clip.get_path_name().split('.')[0] != target:
        if assets.does_asset_exist(target): raise RuntimeError('Animation rename target exists: '+target)
        if not assets.rename_asset(clip.get_path_name(),target): raise RuntimeError('Animation rename failed')
    clips[name]=target

slots=list(mesh.get_editor_property('materials'))
for index, slot in enumerate(slots):
    material_name=str(slot.get_editor_property('imported_material_slot_name'))
    color=source['materials'].get(material_name)
    if color is None: raise RuntimeError('Unknown character material slot: '+material_name)
    path=DEST+'/'+material_name
    material=assets.load_asset(path) if assets.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(material_name,DEST,unreal.Material,unreal.MaterialFactoryNew())
    # New materials only contain these two expressions.
    unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
    rgb=unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionConstant3Vector,-300,0)
    rgb.set_editor_property('constant',unreal.LinearColor(*color))
    unreal.MaterialEditingLibrary.connect_material_property(rgb,'',unreal.MaterialProperty.MP_BASE_COLOR)
    rough=unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionConstant,-300,150)
    rough.set_editor_property('r',.8)
    unreal.MaterialEditingLibrary.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS)
    unreal.MaterialEditingLibrary.recompile_material(material)
    slot.set_editor_property('material_interface',material)
    slots[index] = slot
    assets.save_loaded_asset(material)
mesh.set_editor_property('materials',slots)
assets.save_loaded_asset(mesh)
assets.save_directory(DEST)
result=dict(mesh=mesh.get_path_name(),clips=clips,source=source['source'],application_tests_run=False)
(ROOT/'evidence/explorer-import.json').write_text(json.dumps(result,indent=2))
