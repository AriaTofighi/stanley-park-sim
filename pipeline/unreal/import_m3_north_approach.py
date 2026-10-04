"""Import the source-supported north approach as a separate visual-only layer."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,runpy,shutil
import unreal

ROOT=Path(__file__).resolve().parents[2]
HELPERS=runpy.run_path(str(ROOT/'pipeline/unreal/import_m3_edges.py'),run_name='m3_north_helpers')
ASSETS=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MESHES=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
OWNER='SP_M3NorthApproach'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name().split('.')[0]!='/Game/Maps/StanleyParkSeawall':raise RuntimeError('Open the separate Seawall map and stop Play')
    pointer=read(ROOT/'exports/m3-north-approach/latest.json');path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']:raise RuntimeError('North approach manifest changed')
    source=read(path)
    for name,digest in source['input_hashes'].items():
        if name!='scene_geometry_digest' and sha(ROOT/name)!=digest:raise RuntimeError('North approach input changed: '+name)
    prepared=ROOT/source['prepared_source']
    if sha(prepared)!=source['prepared_source_sha256']:raise RuntimeError('North prepared source changed')
    for name,digest in read(prepared)['input_hashes'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('North source changed: '+name)
    for item in source['assets']:
        if sha(ROOT/item['fbx'])!=item['sha256']:raise RuntimeError('North FBX changed')
    root=source['asset_root']
    if not root.startswith('/Game/StanleyPark/Seawall/NorthApproach/v_'):raise RuntimeError('Unexpected north approach root')
    fingerprint=hashlib.sha256(path.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    existing=[a for a in ACTORS.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    originals=[a for a in existing if OWNER not in [str(t) for t in a.tags]]
    before={a.get_path_name():HELPERS['invariant'](a) for a in originals}
    materials={};references={}
    for item in source['assets']:
        reference=item['material_reference_actor']
        matches=[a for a in originals if a.get_actor_label().startswith(reference)] if reference.endswith('_') else [a for a in originals if a.get_actor_label()==reference]
        if not matches or (not reference.endswith('_') and len(matches)!=1):raise RuntimeError('Material reference missing or ambiguous: '+reference)
        actor=sorted(matches,key=lambda a:a.get_actor_label())[0];material=actor.static_mesh_component.get_material(0)
        if material is None:raise RuntimeError('Reference actor has no material: '+reference)
        materials[item['kind']]=material;references[item['kind']]=dict(actor=actor.get_path_name(),material=material.get_path_name())
    if not LEVELS.save_current_level():raise RuntimeError('Cannot save before north archive')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap';digest=sha(map_path);archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap');archive.parent.mkdir(exist_ok=True)
    if not archive.exists():shutil.copy2(map_path,archive)
    if sha(archive)!=digest:raise RuntimeError('North map archive differs')
    report=ROOT/'evidence'/('m3-north-approach-import-'+fingerprint[:12]+'.json')
    record=dict(success=False,started_utc=datetime.now(timezone.utc).isoformat(),manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],script_sha256=sha(Path(__file__)),archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,material_references=references,actors=[],visual_acceptance=False)
    report.write_text(json.dumps(record,indent=2))
    unreal.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
    meshes={}
    for item in source['assets']:
        asset_path=root+'/Meshes/'+item['name'];mesh=ASSETS.load_asset(asset_path)
        if mesh is None:
            options=unreal.FbxImportUI()
            for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,import_textures=False,automated_import_should_detect_type=False,mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items():options.set_editor_property(key,value)
            for key,value in dict(combine_meshes=True,convert_scene=False,convert_scene_unit=False,force_front_x_axis=False,generate_lightmap_u_vs=False,auto_generate_collision=False,transform_vertex_to_absolute=True,build_nanite=False,normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,vertex_color_import_option=unreal.VertexColorImportOption.REPLACE).items():options.static_mesh_import_data.set_editor_property(key,value)
            task=unreal.AssetImportTask()
            for key,value in dict(filename=str(ROOT/item['fbx']),destination_path=root+'/Meshes',destination_name=item['name'],automated=True,replace_existing=False,save=False,factory=unreal.FbxFactory(),options=options).items():task.set_editor_property(key,value)
            TOOLS.import_asset_tasks([task]);mesh=ASSETS.load_asset(asset_path)
            if not isinstance(mesh,unreal.StaticMesh):raise RuntimeError('North mesh import failed: '+item['name'])
            MESHES.remove_collisions(mesh);ASSETS.set_metadata_tag(mesh,'SP_M3NorthSource',item['sha256'])
        if ASSETS.get_metadata_tag(mesh,'SP_M3NorthSource')!=item['sha256']:raise RuntimeError('North mesh source differs')
        box=mesh.get_bounding_box();actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z]
        error=max(abs(a-b) for a,b in zip(actual,item['bounds_min_cm']+item['bounds_max_cm']))
        if error>1.0:raise RuntimeError('North mesh axis or scale differs: '+item['name'])
        mesh.set_material(0,materials[item['kind']])
        if not ASSETS.save_loaded_asset(mesh):raise RuntimeError('Cannot save north mesh')
        meshes[item['name']]=mesh
    for actor in existing:
        if OWNER in [str(t) for t in actor.tags]:ACTORS.destroy_actor(actor)
    for item in source['assets']:
        x,y,z=item['anchor_local_m'];actor=ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(y*100,x*100,z*100));actor.set_actor_label(item['name']+'_'+source['version']);actor.set_editor_property('tags',[unreal.Name(OWNER),unreal.Name('SP_VisualOnly')])
        component=actor.static_mesh_component;component.set_static_mesh(meshes[item['name']]);component.set_editor_property('use_default_collision',False);component.set_collision_profile_name('NoCollision');component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION or str(component.get_collision_profile_name())!='NoCollision':raise RuntimeError('North visual collision is active')
        record['actors'].append(dict(actor=actor.get_path_name(),label=actor.get_actor_label(),kind=item['kind'],invariant=HELPERS['invariant'](actor)))
    after={a.get_path_name():HELPERS['invariant'](a) for a in originals}
    if before!=after:raise RuntimeError('Original mesh, transform or collision changed')
    if not LEVELS.save_current_level():raise RuntimeError('Cannot save north approach')
    record.update(success=True,assets=len(meshes),triangles=sum(a['triangles'] for a in source['assets']),source_length_m=source['source_length_m'],span_count=source['span_count'],original_geometry_collision_unchanged=True,original_actor_invariants=after,all_new_actors_no_collision=True)
    report.write_text(json.dumps(record,indent=2))
    return dict(success=True,report=str(report),assets=len(meshes),triangles=record['triangles'])

if __name__ in {'__main__','<run_path>'}:result=apply()
