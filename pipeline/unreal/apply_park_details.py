"""Apply the v0.5 forest, understory, picnic, ground, lighting and sound pass.

Use UnrealEditor-Cmd -run=pythonscript -script=... (no PIE or gameplay).
Only the Seawall map and the new ParkDetails_v05 asset namespace are written.
Existing mesh assets and the original M1 map are not edited.
"""
import hashlib
import json
import math
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT=Path(__file__).resolve().parents[2]
SPEC=ROOT/'manifests/park-details-v0.5.json'
cfg=json.loads(SPEC.read_text())
PREFIX=cfg['asset_root']
OWNER='SP_ParkDetails_v05'
assets=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
tools=unreal.AssetToolsHelpers.get_asset_tools()
meshes=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
mel=unreal.MaterialEditingLibrary
record=dict(started_utc=datetime.now(timezone.utc).isoformat(),success=False,application_test_run=False,
    visual_review_complete=False,manifest_sha256=hashlib.sha256(SPEC.read_bytes()).hexdigest(),
    hidden_layers=[],disabled_hidden_collision=[],material_compile_errors=[],counts={})

def save_report():
    (ROOT/'evidence/feedback-park-details-apply.json').write_text(json.dumps(record,indent=2)+'\n')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return assets.load_asset(path) if assets.does_asset_exist(path) else None
for rel,expected in cfg['input_hashes'].items():
    if digest(ROOT/rel)!=expected:raise RuntimeError('Changed authoring input: '+rel)
for asset in cfg['assets']:
    if digest(ROOT/asset['fbx'])!=asset['sha256']:raise RuntimeError('Changed FBX: '+asset['fbx'])
if PREFIX!='/Game/StanleyPark/Seawall/ParkDetails_v05':raise RuntimeError('Unexpected asset namespace')
backup=ROOT/'local-archive/feedback-v0.5/StanleyParkSeawall.umap'
backup.parent.mkdir(parents=True,exist_ok=True)
if not backup.exists():shutil.copy2(ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap',backup)
if not levels.load_level('/Game/Maps/StanleyParkSeawall'):raise RuntimeError('Cannot open authoring map')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if world.get_path_name().split('.')[0]!='/Game/Maps/StanleyParkSeawall':raise RuntimeError('Wrong authoring map')
save_report()

def expression(mat,cls,**props):
    n=mel.create_material_expression(mat,cls)
    for k,v in props.items():n.set_editor_property(k,v)
    return n
def constant(mat,value):return expression(mat,unreal.MaterialExpressionConstant,r=value)
def color(mat,value):return expression(mat,unreal.MaterialExpressionConstant3Vector,constant=unreal.LinearColor(*value[:3],1))
def link(src,out,dst,pin):
    names=[str(n) for n in mel.get_material_expression_input_names(dst)]
    if pin not in names and len(names)==1:pin=names[0]
    if not mel.connect_material_expressions(src,out,dst,pin):raise RuntimeError('Cannot link material pin '+pin)
def output(mat,src,prop,out=''):
    if not mel.connect_material_property(src,out,getattr(unreal.MaterialProperty,prop)):raise RuntimeError('Cannot link output '+prop)
def custom(mat,code,inputs):
    entries=[]
    for name in inputs:
        item=unreal.CustomInput();item.set_editor_property('input_name',name);entries.append(item)
    n=expression(mat,unreal.MaterialExpressionCustom,code=code,inputs=entries,output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    for key,src in inputs.items():link(src,'',n,key)
    return n
def material(name,builder):
    path=PREFIX+'/Materials/'+name
    mat=load(path)
    if mat is None:mat=tools.create_asset(name,PREFIX+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    if assets.get_metadata_tag(mat,OWNER)=='complete':return mat
    mel.delete_all_material_expressions(mat)
    builder(mat)
    mel.set_base_material_usage(mat,unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES,True)
    mel.set_base_material_usage(mat,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH,True)
    mel.layout_material_expressions(mat)
    errors=mel.recompile_material(mat)
    if errors:
        record['material_compile_errors'].append(dict(path=path,errors=[str(e) for e in errors]));save_report()
        raise RuntimeError('Material compilation failed: '+path)
    assets.set_metadata_tag(mat,OWNER,'complete')
    if not assets.save_loaded_asset(mat):raise RuntimeError('Cannot save material: '+path)
    return mat

all_materials={}
for asset in cfg['assets']:
    for spec in asset['materials']:
        if spec['name'] in all_materials:continue
        def build(mat,spec=spec):
            output(mat,color(mat,spec['color']),'MP_BASE_COLOR')
            output(mat,constant(mat,.86),'MP_ROUGHNESS')
            mat.set_editor_property('two_sided',spec['two_sided'])
            if spec['two_sided']:
                mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
                output(mat,color(mat,[v*.25 for v in spec['color'][:3]]),'MP_SUBSURFACE_COLOR')
                p=expression(mat,unreal.MaterialExpressionWorldPosition)
                o=expression(mat,unreal.MaterialExpressionObjectPositionWS)
                t=expression(mat,unreal.MaterialExpressionTime)
                motion=custom(mat,'return float3(1.2,0.6,0)*sin(T*1.8+P.x*0.005+P.y*0.003)*saturate((P.z-O.z+8)/45);',{'P':p,'O':o,'T':t})
                output(mat,motion,'MP_WORLD_POSITION_OFFSET')
        all_materials[spec['name']]=material(spec['name'],build)

imported={}
for role,palette in {
    'Jacket':[(.10,.23,.32),(.43,.18,.075),(.28,.31,.11),(.38,.12,.16)],
    'Skin':[(.47,.26,.14),(.69,.46,.29),(.28,.14,.075),(.78,.57,.42)]
}.items():
    for index,value in enumerate(palette):
        def build_visitor(mat,value=value):
            output(mat,color(mat,value),'MP_BASE_COLOR');output(mat,constant(mat,.8),'MP_ROUGHNESS')
        material(f'M_Visitor{role}_{index}',build_visitor)

for asset in cfg['assets']:
    path=PREFIX+'/Meshes/'+asset['name'];mesh=load(path)
    if mesh is None:
        options=unreal.FbxImportUI();options.set_editor_property('import_mesh',True)
        options.set_editor_property('import_materials',False);options.set_editor_property('import_textures',False)
        options.set_editor_property('import_as_skeletal',False)
        options.static_mesh_import_data.set_editor_property('combine_meshes',True)
        options.static_mesh_import_data.set_editor_property('auto_generate_collision',False)
        task=unreal.AssetImportTask()
        for k,v in dict(filename=str(ROOT/asset['fbx']),destination_path=PREFIX+'/Meshes',destination_name=asset['name'],
            automated=True,replace_existing=False,save=False,options=options).items():task.set_editor_property(k,v)
        tools.import_asset_tasks([task]);mesh=assets.load_asset(path)
    if not isinstance(mesh,unreal.StaticMesh):raise RuntimeError('Cannot import '+path)
    for index,slot in enumerate(mesh.get_editor_property('static_materials')):
        name=str(slot.get_editor_property('imported_material_slot_name'))
        if name not in all_materials:raise RuntimeError('Unknown imported material '+name)
        mesh.set_material(index,all_materials[name])
    # FbxImportUI disables automatic simple collision. The static mesh editor
    # subsystem is not created in a headless Python commandlet.
    assets.save_loaded_asset(mesh)
    imported[asset['name']]=mesh

# Reject submerged placements against the exact same cached polygon source
# used by player recovery. Bucket edges by Y to keep this authoring pass small.
water=json.loads((ROOT/'unreal/Content/WorldData/water-safety.json').read_text())
regions=[]
for region in water['regions']:
    bins=defaultdict(list)
    for ring in region['rings']:
        for a,b in zip(ring,ring[1:]+ring[:1]):
            if a[1]==b[1]:continue
            for band in range(math.floor(min(a[1],b[1])/12800),math.floor(max(a[1],b[1])/12800)+1):bins[band].append((a,b))
    regions.append((region['surface_z_cm'],bins))
def dry(point):
    x,y,z=point
    for water_z,bins in regions:
        if z>=water_z+5:continue
        inside=False
        for a,b in bins.get(math.floor(y/12800),[]):
            if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
        if inside:return False
    return True

# Retired scenery must not retain invisible physical contacts. Explicit
# collision-only meshes are excluded; these are visible-authoring mesh layers.
tree_prefixes=('/Game/StanleyPark/Seawall/Trees/','/Game/StanleyPark/Seawall/M3Forest/',
    '/Game/StanleyPark/Seawall/M3CrownRepair/','/Game/StanleyPark/Seawall/M3CrownTaper/',
    '/Game/StanleyPark/Seawall/M3SiwashCrown/')
for actor in actors.get_all_level_actors():
    if isinstance(actor,unreal.InstancedFoliageActor):continue
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        mesh=component.get_editor_property('static_mesh')
        if mesh is None:continue
        path=mesh.get_path_name()
        is_tree=path.startswith(tree_prefixes) or mesh.get_name().startswith('SM_Canopy_')
        invisible=not component.get_editor_property('visible') or component.get_editor_property('hidden_in_game')
        if is_tree:
            component.modify();component.set_visibility(False);component.set_hidden_in_game(True)
            component.set_editor_property('use_default_collision',False)
            component.set_collision_profile_name('NoCollision');component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            record['hidden_layers'].append(actor.get_actor_label())
        elif invisible and component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION and 'Collision' not in actor.get_actor_label():
            component.modify();component.set_editor_property('use_default_collision',False)
            component.set_collision_profile_name('NoCollision');component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            record['disabled_hidden_collision'].append(actor.get_actor_label())
for path in assets.list_assets('/Game/StanleyPark/Seawall',recursive=True,include_folder=False):
    if '/Foliage/' not in path or not path.startswith(tree_prefixes):continue
    ft=load(path)
    if isinstance(ft,unreal.FoliageType_InstancedStaticMesh):unreal.InstancedFoliageActor.remove_all_instances(world,ft)

def instances(name,mesh,rows,cull,shadows=True):
    path=PREFIX+'/Foliage/FT_'+name
    ft=load(path)
    if ft is None:ft=tools.create_asset('FT_'+name,PREFIX+'/Foliage',unreal.FoliageType_InstancedStaticMesh,unreal.FoliageType_InstancedStaticMeshFactory())
    ft.set_editor_property('mesh',mesh)
    ft.set_editor_property('cull_distance',unreal.Int32Interval(int(cull*.8),int(cull)))
    ft.set_editor_property('cast_shadow',shadows)
    ft.set_editor_property('receives_decals',False)
    body=ft.get_editor_property('body_instance');body.set_editor_property('collision_enabled',unreal.CollisionEnabled.NO_COLLISION);ft.set_editor_property('body_instance',body)
    assets.set_metadata_tag(ft,'SP_Owner',OWNER);assets.save_loaded_asset(ft)
    unreal.InstancedFoliageActor.remove_all_instances(world,ft)
    transforms=[unreal.Transform(location=unreal.Vector(*r['position_cm']),rotation=unreal.Rotator(yaw=r['yaw']),scale=unreal.Vector(*r['scale'])) for r in rows if dry(r['position_cm'])]
    unreal.InstancedFoliageActor.add_instances(world,ft,transforms)
    record['counts'][name]=len(transforms)

grouped=defaultdict(list)
for row in cfg['trees']:grouped[(row['kind'],row['variant'])].append(row)
for (kind,variant),rows in grouped.items():
    name=f'SM_SWTree_{kind}_{variant}_0551a03260b4'
    mesh=assets.load_asset('/Game/StanleyPark/Seawall/Trees/v_0551a03260b4/Meshes/'+name)
    if mesh is None:raise RuntimeError('Missing shared tree '+name)
    instances(f'GroundedTree_{kind}_{variant}',mesh,rows,130000)
grouped=defaultdict(list)
for row in cfg['plants']+cfg['picnics']:grouped[row['mesh']].append(row)
for name,rows in grouped.items():instances(name,imported[name],rows,16000 if 'Picnic' in name else 11000,False)

# A multiscale world-space surface adds moss, soil, fine gravel and roughness
# without modifying any source height, surface normal, pavement or collision.
def ground_material(mat):
    p=expression(mat,unreal.MaterialExpressionWorldPosition)
    code='''float values[3];
    float scales[3]={0.0007,0.012,0.13};
    [unroll] for(int j=0;j<3;j++) {
        float2 q=P.xy*scales[j],c=floor(q),f=frac(q); f=f*f*(3-2*f);
        float4 h=frac(sin(float4(dot(c,float2(127.1,311.7)),dot(c+float2(1,0),float2(127.1,311.7)),dot(c+float2(0,1),float2(127.1,311.7)),dot(c+1,float2(127.1,311.7))))*43758.5453);
        values[j]=lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y);
    }
    float3 soil=float3(.085,.071,.042),moss=float3(.092,.145,.058),grass=float3(.155,.205,.089);
    float3 base=lerp(soil,lerp(moss,grass,values[0]),smoothstep(.22,.68,values[1]));
    return base*(.82+values[2]*.32);'''
    output(mat,custom(mat,code,{'P':p}),'MP_BASE_COLOR')
    output(mat,constant(mat,.94),'MP_ROUGHNESS')
    # Use built-in vertex normals with restrained detail; the surveyed slope
    # remains dominant rather than replacing it with a flat world-up normal.
    normal=expression(mat,unreal.MaterialExpressionVertexNormalWS)
    output(mat,normal,'MP_NORMAL');mat.set_editor_property('tangent_space_normal',False)
ground_mat=material('M_ParkMossSoilGrass',ground_material)
for actor in actors.get_all_level_actors():
    if not actor.get_actor_label().startswith('SM_Terrain_'):continue
    actor.static_mesh_component.set_material(0,ground_mat)

# Built-in light, height fog, ambient occlusion and tone mapping. Retain the
# prior shadow policy because its release record identifies shore artifacts.
light_rows=[]
for actor in actors.get_all_level_actors():
    label=actor.get_actor_label()
    if label=='SP_Seawall_OvercastSun':
        c=actor.light_component;c.set_intensity(3.4);c.set_light_color(unreal.LinearColor(1,.94,.83,1))
        c.set_editor_property('light_source_angle',4.0)
        actor.set_actor_rotation(unreal.Rotator(pitch=-38,yaw=-48),False)
        light_rows.append(dict(label=label,intensity=3.4,color=[1,.94,.83]))
    if label=='SP_Seawall_OvercastSkyLight':
        c=actor.light_component;c.set_intensity(.95);c.recapture_sky()
    if label=='SP_Seawall_OvercastFog':
        actor.component.set_editor_property('fog_density',.001)
        actor.component.set_editor_property('fog_inscattering_luminance',unreal.LinearColor(.47,.57,.67,1))
    if isinstance(actor,unreal.PostProcessVolume):
        settings=actor.get_editor_property('settings')
        settings.set_editor_property('override_ambient_occlusion_intensity',True)
        settings.set_editor_property('ambient_occlusion_intensity',1.05)
        settings.set_editor_property('override_ambient_occlusion_radius',True)
        settings.set_editor_property('ambient_occlusion_radius',90)
        actor.set_editor_property('settings',settings)

# Brighter breaks in the fixed cloud cover; this is an artistic sky, not a
# weather system. Native directional/skylight components light the geometry.
def sky_material(mat):
    mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('two_sided',True);mat.set_editor_property('is_sky',True)
    v=expression(mat,unreal.MaterialExpressionCameraVectorWS)
    code='''float3 d=-normalize(V);float3 p=d*4+float3(17.1,31.7,8.3);float total=0,weight=.57142857;
    [unroll]for(int j=0;j<3;j++){float3 c=floor(p),f=frac(p);f=f*f*(3-2*f);float value=0;
    [unroll]for(int z=0;z<2;z++)[unroll]for(int y=0;y<2;y++)[unroll]for(int x=0;x<2;x++){
    float3 q=float3(x,y,z),b=lerp(1-f,f,q);value+=frac(sin(dot(c+q,float3(127.1,311.7,74.7)))*43758.5453)*b.x*b.y*b.z;}
    total+=value*weight;p=p*2.03+13.1;weight*=.5;}
    float cloud=smoothstep(.38,.68,total);
    float3 sky=lerp(float3(.19,.36,.56),float3(.76,.79,.78),cloud);
    return lerp(float3(.52,.63,.72),sky,smoothstep(0,.5,max(d.z,0)));'''
    output(mat,custom(mat,code,{'V':v}),'MP_EMISSIVE_COLOR')
sky_mat=material('M_ParkBrokenClouds',sky_material)
for actor in actors.get_all_level_actors():
    if actor.get_actor_label()=='SP_Seawall_OvercastDome':actor.static_mesh_component.set_material(0,sky_mat)

audio_path='/Game/StanleyPark/Audio/S_ForestAmbience'
sound=load(audio_path)
if sound is None:
    task=unreal.AssetImportTask()
    for k,v in dict(filename=str(ROOT/'exports/audio/S_ForestAmbience.wav'),destination_path='/Game/StanleyPark/Audio',
        destination_name='S_ForestAmbience',automated=True,replace_existing=False,save=False).items():task.set_editor_property(k,v)
    tools.import_asset_tasks([task]);sound=assets.load_asset(audio_path)
if not isinstance(sound,unreal.SoundWave):raise RuntimeError('Cannot import forest audio')
sound.set_editor_property('looping',True);assets.save_loaded_asset(sound)
if not levels.save_current_level():raise RuntimeError('Cannot save authoring map')
record.update(success=True,finished_utc=datetime.now(timezone.utc).isoformat(),lighting=light_rows,
    nature_audio=dict(asset=audio_path,looping=True,license='CC0-1.0',source='https://opengameart.org/content/forest-ambience',
        author='TinyWorlds',source_sha256=digest(ROOT/'exports/audio/sources/Forest_Ambience.mp3'),wav_sha256=digest(ROOT/'exports/audio/S_ForestAmbience.wav')),
    map_sha256=digest(ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap'))
save_report()
print('SP_PARK_DETAILS_APPLIED',json.dumps(record['counts']))
