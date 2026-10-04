"""Import a separate NoCollision layer for ride-visible cliff seam closures."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import runpy
import shutil
import unreal

ROOT=Path(__file__).resolve().parents[2]
HELPERS=runpy.run_path(str(ROOT/'pipeline/unreal/import_m3_edges.py'),run_name='m3_ride_cliff_gap_helpers')
ASSETS=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MESHES=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
OWNER='SP_M3RideCliffGaps'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name().split('.')[0]!='/Game/Maps/StanleyParkSeawall':
        raise RuntimeError('Open the Seawall map and stop Play')
    pointer=read(ROOT/'exports/m3-ride-cliff-gaps/latest.json')
    path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']:
        raise RuntimeError('Gap export manifest changed')
    source=read(path)
    for name,digest in source['input_hashes'].items():
        if name!='scene_geometry_digest' and sha(ROOT/name)!=digest:
            raise RuntimeError('Gap source changed: '+name)
    for item in source['assets']:
        if sha(ROOT/item['fbx'])!=item['sha256']:
            raise RuntimeError('Gap FBX changed')
    root=source['asset_root']
    if not root.startswith('/Game/StanleyPark/Seawall/RideCliffGaps/v_'):
        raise RuntimeError('Unexpected gap asset root')
    fingerprint=hashlib.sha256(path.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    all_actors=[a for a in ACTORS.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    originals=[a for a in all_actors if OWNER not in [str(t) for t in a.tags]]
    before={a.get_path_name():HELPERS['invariant'](a) for a in originals}
    materials={}
    for item in source['assets']:
        matches=[a for a in originals if a.static_mesh_component.static_mesh.get_name()==item['source_support']]
        if len(matches)!=1:
            raise RuntimeError('Expected one original support material source')
        material=matches[0].static_mesh_component.get_material(0)
        if not material:
            raise RuntimeError('Original support material is missing')
        materials[item['name']]=material
    if not LEVELS.save_current_level():
        raise RuntimeError('Cannot save before archive')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap'
    digest=sha(map_path)
    archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        shutil.copy2(map_path,archive)
    if sha(archive)!=digest:
        raise RuntimeError('Map archive differs')
    report=ROOT/'evidence'/('m3-ride-cliff-gaps-import-'+fingerprint[:12]+'.json')
    record=dict(success=False,started_utc=datetime.now(timezone.utc).isoformat(),manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],script_sha256=sha(Path(__file__)),archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,actors=[],visual_acceptance=False,application_tests_run=False)
    report.write_text(json.dumps(record,indent=2)+'\n')
    unreal.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
    meshes={}
    for item in source['assets']:
        asset_path=root+'/Meshes/'+item['name']
        mesh=ASSETS.load_asset(asset_path)
        if mesh is None:
            options=unreal.FbxImportUI()
            for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,import_textures=False,automated_import_should_detect_type=False,mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items():
                options.set_editor_property(key,value)
            for key,value in dict(combine_meshes=True,convert_scene=False,convert_scene_unit=False,force_front_x_axis=False,generate_lightmap_u_vs=False,auto_generate_collision=False,transform_vertex_to_absolute=True,build_nanite=False,normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS).items():
                options.static_mesh_import_data.set_editor_property(key,value)
            task=unreal.AssetImportTask()
            for key,value in dict(filename=str(ROOT/item['fbx']),destination_path=root+'/Meshes',destination_name=item['name'],automated=True,replace_existing=False,save=False,factory=unreal.FbxFactory(),options=options).items():
                task.set_editor_property(key,value)
            TOOLS.import_asset_tasks([task])
            mesh=ASSETS.load_asset(asset_path)
            if not isinstance(mesh,unreal.StaticMesh):
                raise RuntimeError('Gap import failed')
            MESHES.remove_collisions(mesh)
            ASSETS.set_metadata_tag(mesh,'SP_M3RideCliffGapSource',item['sha256'])
        if ASSETS.get_metadata_tag(mesh,'SP_M3RideCliffGapSource')!=item['sha256']:
            raise RuntimeError('Gap mesh source differs')
        box=mesh.get_bounding_box()
        actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z]
        if max(abs(a-b) for a,b in zip(actual,item['bounds_min_cm']+item['bounds_max_cm']))>.5:
            raise RuntimeError('Gap scale or axes differ')
        mesh.set_material(0,materials[item['name']])
        if not ASSETS.save_loaded_asset(mesh):
            raise RuntimeError('Cannot save gap mesh')
        meshes[item['name']]=mesh
    for actor in all_actors:
        if OWNER in [str(t) for t in actor.tags]:
            ACTORS.destroy_actor(actor)
    for item in source['assets']:
        x,y,z=item['anchor_local_m']
        actor=ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(y*100,x*100,z*100))
        actor.set_actor_label(item['name']+'_'+source['version'])
        actor.set_editor_property('tags',[unreal.Name(OWNER),unreal.Name('SP_VisualOnly')])
        component=actor.static_mesh_component
        component.set_static_mesh(meshes[item['name']])
        component.set_editor_property('use_default_collision',False)
        component.set_collision_profile_name('NoCollision')
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        component.set_editor_property('cast_shadow',False)
        if component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION or str(component.get_collision_profile_name())!='NoCollision':
            raise RuntimeError('Gap collision is active')
        record['actors'].append(dict(actor=actor.get_path_name(),label=actor.get_actor_label(),section_id=item['section_id'],source_support=item['source_support'],material=materials[item['name']].get_path_name(),invariant=HELPERS['invariant'](actor)))
    after={a.get_path_name():HELPERS['invariant'](a) for a in originals}
    if before!=after:
        raise RuntimeError('Original source, transform or collision changed')
    if not LEVELS.save_current_level():
        raise RuntimeError('Cannot save gap layer')
    record.update(success=True,original_geometry_collision_unchanged=True,original_actor_invariants=after,assets=len(meshes),triangles=sum(a['triangles'] for a in source['assets']),source_counts=source['counts'],all_new_actors_no_collision=True)
    report.write_text(json.dumps(record,indent=2)+'\n')
    return dict(success=True,report=report.relative_to(ROOT).as_posix(),assets=len(meshes),triangles=record['triangles'])


if __name__ in {'__main__','<run_path>'}:
    result=apply()
