"""Import the Blender fixture and compare evaluated component-space bone heads."""
import hashlib
import json
import math
from pathlib import Path
import unreal

ROOT=Path(__file__).resolve().parents[2]
manifest=ROOT/'manifests/animation-fixture.json'
source=json.loads(manifest.read_text())
fbx=ROOT/source['fbx']
if hashlib.sha256(fbx.read_bytes()).hexdigest()!=source['sha256']:
    raise RuntimeError('Animation FBX changed after its manifest')
evidence=ROOT/'evidence/unreal-animation-fixture.json'
record=dict(pass_=False,source_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),samples=[])
evidence.write_text(json.dumps(record,indent=2)+'\n')
assets=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
options=unreal.FbxImportUI()
for key,value in dict(import_mesh=True,import_as_skeletal=True,import_animations=True,
    import_materials=False,import_textures=False,create_physics_asset=False,
    automated_import_should_detect_type=False,mesh_type_to_import=unreal.FBXImportType.FBXIT_SKELETAL_MESH).items():
    options.set_editor_property(key,value)
for settings in [options.skeletal_mesh_import_data,options.anim_sequence_import_data]:
    for key,value in dict(convert_scene=False,convert_scene_unit=False,force_front_x_axis=False).items():
        settings.set_editor_property(key,value)
task=unreal.AssetImportTask();task.filename=str(fbx);task.destination_path='/Game/StanleyPark/Fixtures'
task.destination_name='SK_AnimationFixture';task.automated=True;task.replace_existing=True;task.save=True
task.factory=unreal.FbxFactory();task.options=options
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
imported=[assets.load_asset(path) for path in task.imported_object_paths]
mesh=next((obj for obj in imported if isinstance(obj,unreal.SkeletalMesh)),None)
# Legacy FBX lists the primary mesh only. The importer also creates a skeleton
# and animation. Inspect the fixture directory, then require one matching clip.
related=[assets.load_asset(path) for path in assets.list_assets(task.destination_path,recursive=False)]
sequences=[obj for obj in related if isinstance(obj,unreal.AnimSequence)
    and obj.get_name().startswith(task.destination_name+'_')
    and mesh and obj.get_editor_property('skeleton')==mesh.get_editor_property('skeleton')]
sequence=sequences[0] if len(sequences)==1 else None
if mesh is None or sequence is None:
    raise RuntimeError(f'Missing fixture mesh or animation: {list(task.imported_object_paths)}')
for obj in [mesh,sequence,mesh.get_editor_property('skeleton')]:assets.save_loaded_asset(obj)
record.update(mesh=mesh.get_path_name(),animation=sequence.get_path_name(),length_seconds=sequence.get_play_length())
maximum_error=0.
for mode in ['SOURCE','COMPRESSED']:
    evaluation=unreal.AnimPoseEvaluationOptions(optional_skeletal_mesh=mesh,should_retarget=False,
        evaluation_type=getattr(unreal.AnimDataEvalType,mode))
    for sample in source['samples']:
        pose=unreal.AnimPoseExtensions.get_anim_pose_at_time(sequence,sample['seconds'],evaluation)
        if not unreal.AnimPoseExtensions.is_valid(pose):raise RuntimeError('Invalid evaluated fixture pose')
        names=[str(name) for name in unreal.AnimPoseExtensions.get_bone_names(pose)]
        if not set(source['bone_names']).issubset(names):raise RuntimeError(f'Missing fixture bones: {names}')
        row=dict(seconds=sample['seconds'],evaluation=mode,bones={})
        for name,expected in sample['bone_heads_unreal_cm'].items():
            transform=unreal.AnimPoseExtensions.get_bone_pose(pose,name,unreal.AnimPoseSpaces.WORLD)
            p=transform.translation;actual=[p.x,p.y,p.z]
            error=math.dist(actual,expected);maximum_error=max(maximum_error,error)
            row['bones'][name]=dict(expected_cm=expected,actual_cm=actual,error_cm=error)
        record['samples'].append(row)
length_error=abs(record['length_seconds']-source['duration_seconds'])
record.update(maximum_position_error_cm=maximum_error,duration_error_seconds=length_error,
    tolerance_cm=source['translation_tolerance_cm'],
    pass_=maximum_error<=source['translation_tolerance_cm'] and length_error<=source['duration_tolerance_seconds'])
evidence.write_text(json.dumps(record,indent=2)+'\n')
if not record['pass_']:raise RuntimeError(f'Animation transfer failed: {maximum_error}cm / {length_error}s')
unreal.log(f'SP_ANIMATION_FIXTURE: pass; max residual {maximum_error:.6f} cm')
result=record
