"""Apply M3 edge placements and material-only route support treatment in the editor."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import unreal

ROOT = Path(__file__).resolve().parents[2]
MAP = '/Game/Maps/StanleyParkSeawall'
OWNER = 'SP_M3Edges'
ASSETS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MAT = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def invariant(actor):
    c = actor.static_mesh_component
    t = actor.get_actor_transform()
    return dict(mesh=c.static_mesh.get_path_name(),
        location=[t.translation.x,t.translation.y,t.translation.z],
        rotation=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],
        scale=[t.scale3d.x,t.scale3d.y,t.scale3d.z],
        collision=str(c.get_collision_enabled()), profile=str(c.get_collision_profile_name()))


def expression(material, cls, **properties):
    node = MAT.create_material_expression(material, cls)
    if node is None: raise RuntimeError('Cannot create '+cls.__name__)
    for key, value in properties.items(): node.set_editor_property(key,value)
    return node


def material(source, fingerprint):
    """Mineral texture and world normals; no fictional masonry block pattern."""
    name = 'M_M3RouteSupport_'+fingerprint[:12]
    folder = source['asset_root']+'/Materials'
    value = ASSETS.load_asset(folder+'/'+name)
    if value:
        if ASSETS.get_metadata_tag(value,'SP_M3EdgeMaterial') != fingerprint:
            raise RuntimeError('Existing material has a different source')
        return value
    value = TOOLS.create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew())
    value.set_editor_property('tangent_space_normal',False)
    p = expression(value,unreal.MaterialExpressionWorldPosition)
    n = expression(value,unreal.MaterialExpressionVertexNormalWS)
    grain = ASSETS.load_asset(source['pilot_asset_root']+'/Textures/T_SeawallMineral')
    relief = ASSETS.load_asset(source['pilot_asset_root']+'/Textures/T_SeawallMineralNormal')
    if not isinstance(grain,unreal.Texture2D) or not isinstance(relief,unreal.Texture2D):
        raise RuntimeError('Accepted mineral textures are absent')
    a = expression(value,unreal.MaterialExpressionTextureObject,texture=grain,
        sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    b = expression(value,unreal.MaterialExpressionTextureObject,texture=relief,
        sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    def custom(code, inputs, prop, scalar=False):
        slots=[]
        for name in inputs:
            slot=unreal.CustomInput()
            slot.set_editor_property('input_name',name)
            slots.append(slot)
        node=expression(value,unreal.MaterialExpressionCustom,code=code,inputs=slots,
            output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1 if scalar else unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        for name, source_node in inputs.items():
            if not MAT.connect_material_expressions(source_node,'',node,name): raise RuntimeError('Material input failed')
        if not MAT.connect_material_property(node,'',prop): raise RuntimeError('Material output failed')
    custom('''float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,.0001);
float3 q=P/150.0;
float3 grain=Texture2DSample(A,ASampler,q.yz).rgb*w.x+Texture2DSample(A,ASampler,q.xz).rgb*w.y+Texture2DSample(A,ASampler,q.xy).rgb*w.z;
float wet=1.0-smoothstep(30.0,135.0,P.z);
return float3(.25,.255,.23)*(grain*.7+.5)*lerp(1.0,.62,wet);''',{'P':p,'N':n,'A':a},unreal.MaterialProperty.MP_BASE_COLOR)
    custom('''float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,.0001);
float3 q=P/150.0;
float3 x=Texture2DSample(B,BSampler,q.yz).rgb*2.0-1.0;
float3 y=Texture2DSample(B,BSampler,q.xz).rgb*2.0-1.0;
float3 z=Texture2DSample(B,BSampler,q.xy).rgb*2.0-1.0;
float3 perturb=float3(0,x.x,x.y)*w.x+float3(y.x,0,y.y)*w.y+float3(z.x,z.y,0)*w.z;
return normalize(N+perturb*.24);''',{'P':p,'N':n,'B':b},unreal.MaterialProperty.MP_NORMAL)
    custom('return lerp(.65,.91,smoothstep(30.0,135.0,P.z));',{'P':p},unreal.MaterialProperty.MP_ROUGHNESS,True)
    errors=MAT.recompile_material(value)
    if errors is None or list(errors): raise RuntimeError('M3 support material compilation failed: '+str(errors))
    ASSETS.set_metadata_tag(value,'SP_M3EdgeMaterial',fingerprint)
    if not ASSETS.save_loaded_asset(value): raise RuntimeError('Cannot save support material')
    return value


def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name().split('.')[0] != MAP:
        raise RuntimeError('Open the separate Seawall map and stop Play')
    pointer=read(ROOT/'exports/m3-edges/latest.json')
    path=ROOT/pointer['manifest']
    if sha(path) != pointer['sha256']: raise RuntimeError('M3 edge manifest changed')
    source=read(path)
    for name,expected in source['input_hashes'].items():
        if name != 'scene_geometry_digest' and sha(ROOT/name) != expected:
            raise RuntimeError('M3 edge input changed: '+name)
    for item in source['assets']+source['textures']:
        if sha(ROOT/item.get('fbx',item.get('path'))) != item['sha256']:
            raise RuntimeError('Accepted asset source changed: '+item['name'])
    root=source['asset_root']
    if not root.startswith('/Game/StanleyPark/Seawall/Shore/M3/v_'): raise RuntimeError('Unexpected asset root')
    fingerprint=hashlib.sha256(path.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    report=ROOT/'evidence'/('m3-edges-import-'+fingerprint[:12]+'.json')
    actors=[a for a in ACTORS.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    by_name={a.get_actor_label():a for a in actors}
    missing=[n for n in source['material_override_targets'] if n not in by_name]
    if missing: raise RuntimeError('Missing original support actors: '+str(missing))
    before={a.get_path_name():invariant(a) for a in actors}
    targets=[by_name[n] for n in source['material_override_targets']]
    baseline=[dict(actor=a.get_path_name(),label=a.get_actor_label(),
        override_materials=[m.get_path_name() if m else None for m in a.static_mesh_component.get_editor_property('override_materials')]) for a in targets]
    if not LEVELS.save_current_level(): raise RuntimeError('Cannot save before archive')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap'
    digest=sha(map_path)
    archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists(): shutil.copy2(map_path,archive)
    if sha(archive) != digest: raise RuntimeError('Map archive differs')
    record=dict(success=False,started_utc=datetime.now(timezone.utc).isoformat(),
        manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],script_sha256=sha(Path(__file__)),
        archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,
        support_baseline=baseline,application_tests_run=False,visual_acceptance=False)
    report.write_text(json.dumps(record,indent=2))
    support=material(source,fingerprint)
    meshes={}
    foliage={}
    for item in source['assets']:
        mesh=ASSETS.load_asset(source['pilot_asset_root']+'/Meshes/'+item['name'])
        if not isinstance(mesh,unreal.StaticMesh) or ASSETS.get_metadata_tag(mesh,'SP_ShoreSource') != item['sha256']:
            raise RuntimeError('Accepted stone mesh missing or altered')
        meshes[item['name']]=mesh
        ft_name='FT_M3_'+item['name']
        ft=ASSETS.load_asset(root+'/Foliage/'+ft_name)
        if ft is None:
            ft=TOOLS.create_asset(ft_name,root+'/Foliage',unreal.FoliageType_InstancedStaticMesh,
                                  unreal.FoliageType_InstancedStaticMeshFactory())
            ft.set_editor_property('mesh',mesh)
            ft.set_editor_property('enable_density_scaling',False)
            ft.set_editor_property('enable_cull_distance_scaling',False)
            ft.set_editor_property('cull_distance',unreal.Int32Interval(14000,18000))
            ft.set_editor_property('cast_shadow',False)
            body=ft.get_editor_property('body_instance')
            body.set_editor_property('collision_enabled',unreal.CollisionEnabled.NO_COLLISION)
            ft.set_editor_property('body_instance',body)
            ASSETS.set_metadata_tag(ft,'SP_Owner',OWNER)
            if not ASSETS.save_loaded_asset(ft): raise RuntimeError('Cannot save foliage type')
        if ASSETS.get_metadata_tag(ft,'SP_Owner') != OWNER: raise RuntimeError('Foliage ownership differs')
        foliage[item['name']]=ft
    # All required sources exist before the first placement/material replacement.
    owned=[]
    for asset_path in ASSETS.list_assets('/Game/StanleyPark/Seawall/Shore',recursive=True,include_folder=False):
        if '/Foliage/' not in asset_path: continue
        ft=ASSETS.load_asset(asset_path)
        if isinstance(ft,unreal.FoliageType_InstancedStaticMesh) and ASSETS.get_metadata_tag(ft,'SP_Owner') in (OWNER,'SP_SeawallShore'):
            owned.append(ft)
    for ft in owned: unreal.InstancedFoliageActor.remove_all_instances(world,ft)
    grouped={name:[] for name in meshes}
    for row in source['instances']:
        x,y,z=row['position_local_m']
        sx,sy,sz=row['scale']
        grouped[row['mesh']].append(unreal.Transform(location=unreal.Vector(y*100,x*100,z*100),
            rotation=unreal.Rotator(pitch=0,yaw=-row['yaw_degrees'],roll=0),scale=unreal.Vector(sy,sx,sz)))
    for name, transforms in grouped.items():
        if transforms: unreal.InstancedFoliageActor.add_instances(world,foliage[name],transforms)
    for actor in targets:
        actor.modify()
        actor.static_mesh_component.modify()
        actor.static_mesh_component.set_material(0,support)
    expected={mesh.get_path_name():len(grouped[name]) for name,mesh in meshes.items()}
    actual={path:0 for path in expected}
    for actor in ACTORS.get_all_level_actors():
        if isinstance(actor,unreal.InstancedFoliageActor):
            for component in actor.get_components_by_class(unreal.FoliageInstancedStaticMeshComponent):
                mesh=component.get_editor_property('static_mesh')
                if mesh and mesh.get_path_name() in actual: actual[mesh.get_path_name()]+=component.get_instance_count()
    if actual != expected: raise RuntimeError('M3 stone instance count mismatch: '+str(actual))
    after={a.get_path_name():invariant(a) for a in actors}
    if before != after: raise RuntimeError('Original mesh, transform or collision changed')
    if not LEVELS.save_current_level(): raise RuntimeError('Cannot save M3 edge layer')
    record.update(success=True,instances=sum(actual.values()),instance_counts=actual,
        support_material=support.get_path_name(),support_count=len(targets),
        original_actor_invariants=after,original_geometry_collision_unchanged=True,
        pilot_instances_retained=len(read(ROOT/source['pilot_manifest'])['instances']),
        sections=source['sections'],new_meshes=0,new_textures=0,new_materials=1)
    report.write_text(json.dumps(record,indent=2))
    return dict(success=True,report=str(report),instances=record['instances'],support_count=len(targets))


if __name__ in {'__main__', '<run_path>'}:
    result=apply()

