"""Import source-bound original M3 forms into the separate Seawall map."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import unreal

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3ShoreToShore'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invariant(actor):
    t=actor.get_actor_transform(); c=actor.static_mesh_component
    return dict(mesh=c.static_mesh.get_path_name(),position=[t.translation.x,t.translation.y,t.translation.z],
        rotation=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],scale=[t.scale3d.x,t.scale3d.y,t.scale3d.z],
        collision=str(c.get_collision_enabled()),profile=str(c.get_collision_profile_name()))


def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name()!='/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':
        raise RuntimeError('Open the separate Seawall map and stop Play')
    pointer=json.loads((ROOT/'exports/m3-shore-to-shore/latest.json').read_text());path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']: raise RuntimeError('Form manifest changed')
    source=json.loads(path.read_text());root=source['asset_root']
    if not root.startswith('/Game/StanleyPark/Seawall/ShoreToShore/v_'): raise RuntimeError('Invalid form asset root')
    for p,h in source['input_hashes'].items():
        if sha(ROOT/p)!=h: raise RuntimeError('Form source changed: '+p)
    for item in source['assets']:
        if sha(ROOT/item['fbx'])!=item['sha256']: raise RuntimeError('Form FBX changed')
    assets=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);tools=unreal.AssetToolsHelpers.get_asset_tools();mat=unreal.MaterialEditingLibrary
    originals=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh and OWNER not in [str(t) for t in a.tags]]
    before={a.get_path_name():invariant(a) for a in originals}
    by_name={a.get_actor_label():a for a in originals}
    for row in source['hidden_originals']:
        if row['name'] not in by_name: raise RuntimeError('Missing landmark source '+row['name'])
    if not levels.save_current_level(): raise RuntimeError('Cannot save before form archive')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap';digest=sha(map_path)
    archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap');archive.parent.mkdir(exist_ok=True)
    if not archive.exists(): shutil.copy2(map_path,archive)
    if sha(archive)!=digest: raise RuntimeError('Map archive differs')
    fingerprint=hashlib.sha256(path.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    report=ROOT/'evidence'/('m3-shore-to-shore-import-'+fingerprint[:12]+'.json')
    record=dict(success=False,started_utc=datetime.now(timezone.utc).isoformat(),manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],
        script_sha256=sha(Path(__file__)),archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,
        visual_acceptance=False,geographic_accuracy_accepted=False,application_tests_run=False,actors=[],
        hidden_baseline=[dict(name=r['name'],visible=by_name[r['name']].static_mesh_component.is_visible()) for r in source['hidden_originals']])
    report.write_text(json.dumps(record,indent=2))
    palette={}
    for row in source['settings']['materials']:
        name='M_M3ShoreToShore_'+row['name']+'_'+source['version'];folder=root+'/Materials';m=assets.load_asset(folder+'/'+name)
        if m is None:
            m=tools.create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew())
            for value,cls,prop in [(row['rgb'],unreal.MaterialExpressionConstant3Vector,unreal.MaterialProperty.MP_BASE_COLOR),
                (row['roughness'],unreal.MaterialExpressionConstant,unreal.MaterialProperty.MP_ROUGHNESS),
                (row['metallic'],unreal.MaterialExpressionConstant,unreal.MaterialProperty.MP_METALLIC)]:
                node=mat.create_material_expression(m,cls)
                if isinstance(value,list): node.set_editor_property('constant',unreal.LinearColor(*value,1))
                else: node.set_editor_property('r',value)
                if not mat.connect_material_property(node,'',prop): raise RuntimeError('Form material link failed')
            errors=mat.recompile_material(m)
            if errors is None or list(errors): raise RuntimeError('Form material compile failed: '+str(errors))
            assets.set_metadata_tag(m,'SP_ShoreToShoreSource',fingerprint)
            if not assets.save_loaded_asset(m): raise RuntimeError('Cannot save form material')
        if assets.get_metadata_tag(m,'SP_ShoreToShoreSource')!=fingerprint: raise RuntimeError('Form material provenance differs')
        palette[name]=m
    unreal.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
    loaded=[]
    for item in source['assets']:
        mesh=assets.load_asset(root+'/Meshes/'+item['name'])
        if mesh is None:
            options=unreal.FbxImportUI()
            for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,import_textures=False,
                automated_import_should_detect_type=False,mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items(): options.set_editor_property(key,value)
            for key,value in dict(combine_meshes=True,convert_scene=False,convert_scene_unit=False,force_front_x_axis=False,
                generate_lightmap_u_vs=False,auto_generate_collision=False,transform_vertex_to_absolute=True,build_nanite=False).items(): options.static_mesh_import_data.set_editor_property(key,value)
            options.static_mesh_import_data.set_editor_property('normal_import_method',unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
            task=unreal.AssetImportTask()
            for key,value in dict(filename=str(ROOT/item['fbx']),destination_path=root+'/Meshes',destination_name=item['name'],
                automated=True,replace_existing=False,save=False,factory=unreal.FbxFactory(),options=options).items(): task.set_editor_property(key,value)
            tools.import_asset_tasks([task]);mesh=assets.load_asset(root+'/Meshes/'+item['name'])
        if not isinstance(mesh,unreal.StaticMesh): raise RuntimeError('Form mesh import failed')
        data=mesh.get_editor_property('asset_import_data')
        if not data or Path(data.get_first_filename()).resolve()!=(ROOT/item['fbx']).resolve(): raise RuntimeError('Form mesh source differs')
        box=mesh.get_bounding_box();actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z]
        if any(abs(a-b)>1 for a,b in zip(actual,item['bounds_min_cm']+item['bounds_max_cm'])): raise RuntimeError('Form mesh bounds differ')
        for i,slot in enumerate(mesh.get_editor_property('static_materials')):
            name=str(slot.get_editor_property('imported_material_slot_name'))
            if name not in palette: raise RuntimeError('Unknown form material '+name)
            mesh.set_material(i,palette[name])
        assets.set_metadata_tag(mesh,'SP_ShoreToShoreSource',item['sha256'])
        if not assets.save_loaded_asset(mesh): raise RuntimeError('Cannot save form mesh')
        loaded.append((item,mesh))
    # Replace only previously owned form actors. Protected source actors remain.
    for actor in actors.get_all_level_actors():
        if OWNER in [str(t) for t in actor.tags]: actors.destroy_actor(actor)
    for item,mesh in loaded:
        actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*item['position_cm']))
        if actor is None: raise RuntimeError('Cannot place form actor')
        actor.set_actor_label(item['name']);actor.tags=[unreal.Name(OWNER),unreal.Name(item['feature_id'])]
        actor.static_mesh_component.set_static_mesh(mesh)
        actor.static_mesh_component.set_editor_property('use_default_collision',False)
        actor.static_mesh_component.set_collision_profile_name('NoCollision')
        actor.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if actor.static_mesh_component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION:
            raise RuntimeError('Form collision is active')
        record['actors'].append(dict(label=item['name'],feature_id=item['feature_id'],mesh=mesh.get_path_name(),position_cm=item['position_cm']))
    for row in source['hidden_originals']:
        actor=by_name[row['name']];actor.modify();actor.static_mesh_component.modify()
        actor.static_mesh_component.set_visibility(False,True)
        actor.static_mesh_component.set_hidden_in_game(True,True)
    after={a.get_path_name():invariant(a) for a in originals}
    if before!=after: raise RuntimeError('Original geometry, transform or collision changed')
    if not levels.save_current_level(): raise RuntimeError('Cannot save form map')
    record.update(success=True,original_geometry_collision_unchanged=True,original_invariants=after,
        added_triangles=sum(i['triangles'] for i in source['assets']),materials=len(palette),source_limits=source['settings']['limits'])
    report.write_text(json.dumps(record,indent=2))
    return dict(success=True,report=str(report),forms=len(loaded),triangles=record['added_triangles'])


if __name__ in {'__main__','<run_path>'}:
    result=apply()
