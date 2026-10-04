"""Repair flat M3 path surfaces with versioned material-only actor overrides.

The pale shore band is mainly the existing pedestrian overlay, not a wall.
Do not replace its geometry or place rocks over walking surfaces.
Run only in the coordinator's serial Unreal authoring slot.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import runpy
import shutil
import unreal

ROOT=Path(__file__).resolve().parents[2]
HELPER=ROOT/'pipeline/unreal/import_m3_edges.py'
helpers=runpy.run_path(str(HELPER),run_name='m3_path_repair_helpers')
expression=helpers['expression']
invariant=helpers['invariant']
ASSETS=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MAT=unreal.MaterialEditingLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
PALETTES={
    'asphalt':dict(color=[.078,.082,.086],scale_cm=24.0,normal=.09,grain=.42,roughness=.93),
    'branch':dict(color=[.14,.15,.145],scale_cm=38.0,normal=.15,grain=.45,roughness=.92),
    'paved_walk':dict(color=[.19,.18,.16],scale_cm=55.0,normal=.20,grain=.50,roughness=.93),
    'forest_walk':dict(color=[.12,.095,.065],scale_cm=75.0,normal=.24,grain=.58,roughness=.96),
    'unknown_walk':dict(color=[.17,.16,.14],scale_cm=55.0,normal=.18,grain=.45,roughness=.94)}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def classify(name):
    if name.startswith('SM_Pavement_'):return 'asphalt'
    if name.startswith('SM_Route_'):return 'branch'
    for category in ['paved_walk','forest_walk','unknown_walk']:
        if name.startswith('SM_Pedestrian_'+category+'_'):return category
    return None


def build_material(kind,root,fingerprint,textures):
    name='M_M3Path_'+kind
    material=ASSETS.load_asset(root+'/'+name)
    if material:
        if ASSETS.get_metadata_tag(material,'SP_M3PathSource') != fingerprint:
            raise RuntimeError('Incomplete or foreign repair material '+kind)
        return material
    cfg=PALETTES[kind]
    material=TOOLS.create_asset(name,root,unreal.Material,unreal.MaterialFactoryNew())
    material.set_editor_property('tangent_space_normal',False)
    p=expression(material,unreal.MaterialExpressionWorldPosition)
    n=expression(material,unreal.MaterialExpressionVertexNormalWS)
    a=expression(material,unreal.MaterialExpressionTextureObject,texture=textures['T_SeawallMineral'],
        sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    b=expression(material,unreal.MaterialExpressionTextureObject,texture=textures['T_SeawallMineralNormal'],
        sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    def custom(code,inputs,prop,scalar=False):
        slots=[]
        for label in inputs:
            slot=unreal.CustomInput();slot.set_editor_property('input_name',label);slots.append(slot)
        node=expression(material,unreal.MaterialExpressionCustom,code=code,inputs=slots,
            output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1 if scalar else unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        for label,source in inputs.items():
            if not MAT.connect_material_expressions(source,'',node,label):raise RuntimeError('Material input failed')
        if not MAT.connect_material_property(node,'',prop):raise RuntimeError('Material output failed')
    common=f'float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,.0001); float3 q=P/{cfg["scale_cm"]:.6f};\n'
    colour=','.join(str(v) for v in cfg['color'])
    custom(common+f'''float3 grain=Texture2DSample(A,ASampler,q.yz).rgb*w.x+Texture2DSample(A,ASampler,q.xz).rgb*w.y+Texture2DSample(A,ASampler,q.xy).rgb*w.z;
float broad=Texture2DSample(A,ASampler,P.xy/380.0).r;
return float3({colour})*(1.0+(grain-.60)*{cfg['grain']:.6f}+(broad-.60)*.09);''',
           {'P':p,'N':n,'A':a},unreal.MaterialProperty.MP_BASE_COLOR)
    custom(common+f'''float3 x=Texture2DSample(B,BSampler,q.yz).rgb*2.0-1.0;
float3 y=Texture2DSample(B,BSampler,q.xz).rgb*2.0-1.0;
float3 z=Texture2DSample(B,BSampler,q.xy).rgb*2.0-1.0;
float3 perturb=float3(0,x.x,x.y)*w.x+float3(y.x,0,y.y)*w.y+float3(z.x,z.y,0)*w.z;
return normalize(N+perturb*{cfg['normal']:.6f});''',{'P':p,'N':n,'B':b},unreal.MaterialProperty.MP_NORMAL)
    rough=expression(material,unreal.MaterialExpressionConstant,r=cfg['roughness'])
    specular=expression(material,unreal.MaterialExpressionConstant,r=.12)
    if not MAT.connect_material_property(rough,'',unreal.MaterialProperty.MP_ROUGHNESS):raise RuntimeError('Roughness output failed')
    if not MAT.connect_material_property(specular,'',unreal.MaterialProperty.MP_SPECULAR):raise RuntimeError('Specular output failed')
    errors=MAT.recompile_material(material)
    if errors is None or list(errors):raise RuntimeError('Path material compile failed: '+str(errors))
    ASSETS.set_metadata_tag(material,'SP_M3PathSource',fingerprint)
    if not ASSETS.save_loaded_asset(material):raise RuntimeError('Cannot save path material')
    return material


def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name().split('.')[0] != '/Game/Maps/StanleyParkSeawall':
        raise RuntimeError('Open the Seawall editor map and stop Play')
    source_paths=['pipeline/unreal/repair_m3_path_materials.py','pipeline/unreal/import_m3_edges.py',
                  'manifests/blender-export.json','data/routes/derived/pedestrian-surfaces.json',
                  'evidence/m3-edge-pixel-attribution.json','exports/seawall-shore/d2a3c472791b/manifest.json']
    inputs={p:sha(ROOT/p) for p in source_paths}
    fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    root='/Game/StanleyPark/Seawall/Paths/v_'+fingerprint[:12]
    pilot=read(ROOT/'exports/seawall-shore/d2a3c472791b/manifest.json')
    textures={}
    for item in pilot['textures']:
        texture=ASSETS.load_asset(pilot['asset_root']+'/Textures/'+item['name'])
        if not isinstance(texture,unreal.Texture2D) or ASSETS.get_metadata_tag(texture,'SP_ShoreSource') != item['sha256']:
            raise RuntimeError('Accepted path texture missing or changed')
        textures[item['name']]=texture
    exported=read(ROOT/'manifests/blender-export.json')
    expected={a['name']:a for a in exported['assets'] if classify(a['name'])}
    actors=[a for a in ACTORS.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    targets=[a for a in actors if classify(a.get_actor_label())]
    if {a.get_actor_label() for a in targets} != set(expected):raise RuntimeError('Path actor set differs from the source export')
    for actor in targets:
        if actor.static_mesh_component.get_num_materials() != 1:raise RuntimeError('Expected one path material slot')
    before={a.get_path_name():invariant(a) for a in actors}
    baseline=[dict(actor=a.get_path_name(),label=a.get_actor_label(),kind=classify(a.get_actor_label()),
        material= a.static_mesh_component.get_material(0).get_path_name() if a.static_mesh_component.get_material(0) else None,
        overrides=[m.get_path_name() if m else None for m in a.static_mesh_component.get_editor_property('override_materials')]) for a in targets]
    if not LEVELS.save_current_level():raise RuntimeError('Cannot save map before archive')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap';digest=sha(map_path)
    archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():shutil.copy2(map_path,archive)
    if sha(archive) != digest:raise RuntimeError('Map archive mismatch')
    report=ROOT/'evidence'/('m3-path-material-repair-'+fingerprint[:12]+'.json')
    if report.exists() and read(report).get('success'):raise RuntimeError('This material version was already applied')
    record=dict(success=False,time_utc=datetime.now(timezone.utc).isoformat(),input_hashes=inputs,
        version=fingerprint[:12],asset_root=root,archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,
        baseline=baseline,palettes=PALETTES,visual_acceptance=False,
        limits='Material-only repair. Coarse walking overlay shape is unchanged and requires repeat route-view review.')
    report.write_text(json.dumps(record,indent=2))
    materials={kind:build_material(kind,root,fingerprint,textures) for kind in PALETTES}
    counts={kind:0 for kind in PALETTES}
    for actor in targets:
        kind=classify(actor.get_actor_label());actor.modify();actor.static_mesh_component.modify()
        actor.static_mesh_component.set_material(0,materials[kind]);counts[kind]+=1
        if actor.static_mesh_component.get_material(0) != materials[kind]:raise RuntimeError('Path material readback failed')
    after={a.get_path_name():invariant(a) for a in actors}
    if before != after:raise RuntimeError('Original geometry/transform/collision changed')
    if not LEVELS.save_current_level():raise RuntimeError('Cannot save repaired map')
    record.update(success=True,counts=counts,materials={k:v.get_path_name() for k,v in materials.items()},
        original_actor_invariants=after,geometry_collision_unchanged=True,application_tests_run=False)
    report.write_text(json.dumps(record,indent=2))
    return dict(success=True,report=str(report),version=fingerprint[:12],counts=counts)


if __name__ in {'__main__','<run_path>'}:
    result=apply()
