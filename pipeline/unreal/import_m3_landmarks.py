"""Apply source-bound landmark finishes as Seawall-only actor overrides.

Never edits the M1 static meshes or material assets. Run in editor authoring mode.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

import unreal

ROOT=Path(__file__).resolve().parents[2]
ASSETS=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
MAT=unreal.MaterialEditingLibrary


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invariant(actor):
    component=actor.static_mesh_component
    transform=actor.get_actor_transform()
    return dict(mesh=component.static_mesh.get_path_name(),
        position=[transform.translation.x,transform.translation.y,transform.translation.z],
        rotation=[transform.rotation.x,transform.rotation.y,transform.rotation.z,transform.rotation.w],
        scale=[transform.scale3d.x,transform.scale3d.y,transform.scale3d.z],
        collision=str(component.get_collision_enabled()),profile=str(component.get_collision_profile_name()))


def node(material,cls,**properties):
    result=MAT.create_material_expression(material,cls)
    if result is None: raise RuntimeError('Cannot create '+cls.__name__)
    for key,value in properties.items(): result.set_editor_property(key,value)
    return result


def output(material,expression,prop):
    if not MAT.connect_material_property(expression,'',prop): raise RuntimeError('Cannot connect material output')


def custom(material,code,inputs,kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    slots=[]
    for name in inputs:
        item=unreal.CustomInput(); item.set_editor_property('input_name',name); slots.append(item)
    result=node(material,unreal.MaterialExpressionCustom,code=code,inputs=slots,output_type=kind)
    for name,value in inputs.items():
        if not MAT.connect_material_expressions(value,'',result,name): raise RuntimeError('Cannot connect '+name)
    return result


def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name()!='/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':
        raise RuntimeError('Open the separate Seawall map and stop Play')
    pointer=json.loads((ROOT/'exports/seawall-landmarks/latest.json').read_text())
    path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']: raise RuntimeError('Landmark manifest changed')
    source=json.loads(path.read_text(encoding='utf8'))
    for name,expected in source['input_hashes'].items():
        if sha(ROOT/name)!=expected: raise RuntimeError('Landmark source changed: '+name)
    item=source['texture']
    if sha(ROOT/item['path'])!=item['sha256']: raise RuntimeError('Landmark texture changed')
    root=source['asset_root']
    if not root.startswith('/Game/StanleyPark/Seawall/Landmarks/v_'): raise RuntimeError('Unexpected landmark asset root')
    fingerprint=hashlib.sha256(path.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    actors={}
    all_static=[]
    for actor in ACTORS.get_all_level_actors():
        if isinstance(actor,unreal.StaticMeshActor) and actor.static_mesh_component.static_mesh:
            all_static.append(actor)
            actors.setdefault(actor.get_actor_label(),[]).append(actor)
    selected=[]
    for row in source['targets']:
        matches=actors.get(row['name'],[])
        if len(matches)!=1: raise RuntimeError('Landmark actor missing or ambiguous: '+row['name'])
        actor=matches[0]
        actual=actor.static_mesh_component.static_mesh.get_path_name().split('.')[0]
        if actual!=row['asset_path']: raise RuntimeError('Landmark mesh differs: '+row['name'])
        for slot in row['slots']:
            if slot['slot']>=actor.static_mesh_component.get_num_materials(): raise RuntimeError('Landmark slot missing: '+row['name'])
        selected.append((row,actor))
    before={a.get_path_name():invariant(a) for a in all_static}
    baseline=ROOT/'evidence/m3-landmark-material-baseline.json'
    if not baseline.exists():
        baseline.write_text(json.dumps(dict(map=world.get_path_name(),actors=[dict(
            actor=a.get_path_name(),label=a.get_actor_label(),invariant=invariant(a),
            overrides=[m.get_path_name() if m else None for m in a.static_mesh_component.get_editor_property('override_materials')])
            for _,a in selected]),indent=2))
    report=ROOT/'evidence'/('m3-landmark-import-'+fingerprint[:12]+'.json')
    record=dict(started_utc=datetime.now(timezone.utc).isoformat(),success=False,
        manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],script_sha256=sha(Path(__file__)),
        materials=[],instances=[],actors=[],application_test=False,visual_acceptance=False,
        source_limits=source['settings']['unresolved_limits'])
    report.write_text(json.dumps(record,indent=2))
    texture_path=root+'/Textures/'+item['name']
    texture=ASSETS.load_asset(texture_path)
    if texture is None:
        task=unreal.AssetImportTask()
        for key,value in dict(filename=str(ROOT/item['path']),destination_path=root+'/Textures',
            destination_name=item['name'],automated=True,replace_existing=False,save=False).items(): task.set_editor_property(key,value)
        TOOLS.import_asset_tasks([task]); texture=ASSETS.load_asset(texture_path)
        if not isinstance(texture,unreal.Texture2D): raise RuntimeError('Landmark grain import failed')
        texture.set_editor_property('srgb',False)
        texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
        ASSETS.set_metadata_tag(texture,'SP_M3LandmarkSource',item['sha256'])
        if not ASSETS.save_loaded_asset(texture): raise RuntimeError('Cannot save grain texture')
    if ASSETS.get_metadata_tag(texture,'SP_M3LandmarkSource')!=item['sha256']: raise RuntimeError('Existing grain texture differs')
    cache={}
    parents={}
    def parent_material(spec):
        kind=spec['kind']
        if kind in parents: return parents[kind]
        name='M_M3Landmark_'+kind.replace('-','_')+'_'+fingerprint[:12]
        material_path=root+'/Materials/'+name
        result=ASSETS.load_asset(material_path)
        if result:
            if ASSETS.get_metadata_tag(result,'SP_M3LandmarkMaterial')!=fingerprint:
                raise RuntimeError('Incomplete existing landmark material')
            parents[kind]=result
            record['materials'].append(dict(path=material_path,reused=True))
            return result
        result=TOOLS.create_asset(name,root+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
        result.set_editor_property('tangent_space_normal',False)
        channel='rgb'[spec['channel']]
        position=node(result,unreal.MaterialExpressionWorldPosition)
        normal=node(result,unreal.MaterialExpressionVertexNormalWS)
        grain=node(result,unreal.MaterialExpressionTextureObject,texture=texture,
            sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        # Project in the original east/north/up frame. No UV changes are required.
        # World-space sampling avoids texture size changes across separate forms.
        height=custom(result,f'''float3 q=P.yxz/{spec['tile_m']*100:.8f};
float3 w=pow(abs(N.yxz),4); w/=max(w.x+w.y+w.z,.0001);
return Texture2DSample(T,TSampler,q.yz).{channel}*w.x+
       Texture2DSample(T,TSampler,q.xz).{channel}*w.y+
       Texture2DSample(T,TSampler,q.xy).{channel}*w.z;''',
            {'P':position,'N':normal,'T':grain},unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        tint=node(result,unreal.MaterialExpressionVectorParameter,parameter_name='SourceColor',default_value=unreal.LinearColor(1,1,1,1))
        base=custom(result,f'return C*(1.0+(H-.5)*{spec["contrast"]*2:.8f});',{'H':height,'C':tint})
        output(result,base,unreal.MaterialProperty.MP_BASE_COLOR)
        rough=custom(result,f'return saturate({spec["roughness"]:.8f}+(H-.5)*.10);',{'H':height},unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        output(result,rough,unreal.MaterialProperty.MP_ROUGHNESS)
        metal=node(result,unreal.MaterialExpressionConstant,r=spec['metallic'])
        output(result,metal,unreal.MaterialProperty.MP_METALLIC)
        if spec['relief_m']:
            bumped=custom(result,f'''float3 dx=ddx(P),dy=ddy(P);
float3 r1=cross(dy,N),r2=cross(N,dx); float d=dot(dx,r1);
float3 gradient=(r1*ddx(H)+r2*ddy(H))*sign(d)/max(abs(d),.00001);
return normalize(N-gradient*{spec['relief_m']*100:.8f});''',{'P':position,'N':normal,'H':height})
            output(result,bumped,unreal.MaterialProperty.MP_NORMAL)
        diagnostics=MAT.recompile_material(result)
        if diagnostics is None: raise RuntimeError('Missing landmark shader diagnostics')
        errors=[str(error) for error in diagnostics]
        if errors: raise RuntimeError('Landmark shader error: '+str(errors))
        ASSETS.set_metadata_tag(result,'SP_M3LandmarkMaterial',fingerprint)
        if not ASSETS.save_loaded_asset(result): raise RuntimeError('Cannot save landmark material')
        record['materials'].append(dict(path=material_path,compile_errors=errors,profile=spec['kind']))
        parents[kind]=result
        return result
    def material(slot):
        signature=json.dumps(dict(color=slot['color'],profile=slot['profile']),sort_keys=True)
        if signature in cache: return cache[signature]
        parent=parent_material(slot['profile'])
        key=hashlib.sha256((signature+fingerprint).encode()).hexdigest()[:12]
        name='MI_M3Landmark_'+slot['profile']['kind'].replace('-','_')+'_'+key
        material_path=root+'/Materials/'+name
        result=ASSETS.load_asset(material_path)
        setter_return=None
        if result:
            if ASSETS.get_metadata_tag(result,'SP_M3LandmarkMaterial')!=fingerprint:
                raise RuntimeError('Incomplete existing landmark instance')
        else:
            result=TOOLS.create_asset(name,root+'/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
            if not isinstance(result,unreal.MaterialInstanceConstant): raise RuntimeError('Cannot create landmark instance')
            MAT.set_material_instance_parent(result,parent)
            # UE5.8 MaterialEditingLibrary.cpp:1573 sets the vector and updates
            # the instance, but returns an unchanged false bResult. Verify the
            # resulting value; the API boolean is not a success indication.
            setter_return=MAT.set_material_instance_vector_parameter_value(result,'SourceColor',unreal.LinearColor(*slot['color'],1.))
        actual=MAT.get_material_instance_vector_parameter_value(result,'SourceColor')
        actual_color=[actual.r,actual.g,actual.b,actual.a]
        expected_color=[*slot['color'],1.]
        color_error=max(abs(a-b) for a,b in zip(actual_color,expected_color))
        if color_error>1e-6: raise RuntimeError('Landmark instance color readback differs: '+name)
        if result.get_editor_property('parent')!=parent: raise RuntimeError('Landmark instance parent differs: '+name)
        if setter_return is not None:
            ASSETS.set_metadata_tag(result,'SP_M3LandmarkMaterial',fingerprint)
            if not ASSETS.save_loaded_asset(result): raise RuntimeError('Cannot save landmark instance')
        record['instances'].append(dict(path=material_path,parent=parent.get_path_name(),
            setter_return=setter_return,color=actual_color,color_error=color_error))
        cache[signature]=result
        return result
    # Compile all materials before changing the map. A failed shader leaves actor
    # materials untouched, and the incomplete version has no map references.
    for row,_ in selected:
        for slot in row['slots']: material(slot)
    for row,actor in selected:
        actor.modify(); actor.static_mesh_component.modify()
        for slot in row['slots']: actor.static_mesh_component.set_material(slot['slot'],material(slot))
        record['actors'].append(dict(label=row['name'],group=row['group'],route_station_m=row['route_station_m'],slots=len(row['slots'])))
    after={a.get_path_name():invariant(a) for a in all_static}
    if before!=after: raise RuntimeError('Static mesh geometry, transform or collision changed')
    if not LEVELS.save_current_level(): raise RuntimeError('Cannot save landmark layer')
    record.update(success=True,geometry_collision_unchanged=True,static_actor_count=len(before),
        target_count=len(selected),material_count=len(cache),parent_material_count=len(parents),texture=texture_path,
        completed_utc=datetime.now(timezone.utc).isoformat())
    report.write_text(json.dumps(record,indent=2))
    (ROOT/'evidence/m3-landmark-import-latest.json').write_text(json.dumps(dict(report=report.relative_to(ROOT).as_posix(),sha256=sha(report)),indent=2))
    return record


if __name__ in {'__main__', '<run_path>'}:
    result=apply()
