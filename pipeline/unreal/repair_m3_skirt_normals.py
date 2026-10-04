"""Correct lighting on downward-facing visual skirt meshes with actor materials.

The frozen FBX and all source geometry remain unchanged. No collision changes.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,runpy,shutil
import unreal

ROOT=Path(__file__).resolve().parents[2]
HELPERS=runpy.run_path(str(ROOT/'pipeline/unreal/import_m3_edges.py'),run_name='m3_skirt_normal_helpers')
ASSETS=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MAT=unreal.MaterialEditingLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
expression=HELPERS['expression']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def build_material(root,fingerprint,source):
    name='M_M3EdgeSkirt_UpwardNormals';material=ASSETS.load_asset(root+'/'+name)
    if material:
        if ASSETS.get_metadata_tag(material,'SP_M3SkirtNormalRepair')!=fingerprint:raise RuntimeError('Existing normal repair source differs')
        return material
    material=TOOLS.create_asset(name,root,unreal.Material,unreal.MaterialFactoryNew())
    material.set_editor_property('tangent_space_normal',False);material.set_editor_property('two_sided',True)
    position=expression(material,unreal.MaterialExpressionWorldPosition);normal=expression(material,unreal.MaterialExpressionVertexNormalWS)
    grain=ASSETS.load_asset(source['pilot_asset_root']+'/Textures/T_SeawallMineral');relief=ASSETS.load_asset(source['pilot_asset_root']+'/Textures/T_SeawallMineralNormal')
    if not isinstance(grain,unreal.Texture2D) or not isinstance(relief,unreal.Texture2D):raise RuntimeError('Accepted mineral textures absent')
    a=expression(material,unreal.MaterialExpressionTextureObject,texture=grain,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    b=expression(material,unreal.MaterialExpressionTextureObject,texture=relief,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    def custom(code,inputs,prop,scalar=False):
        slots=[]
        for label in inputs:
            item=unreal.CustomInput();item.set_editor_property('input_name',label);slots.append(item)
        node=expression(material,unreal.MaterialExpressionCustom,code=code,inputs=slots,output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1 if scalar else unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        for label,source_node in inputs.items():
            if not MAT.connect_material_expressions(source_node,'',node,label):raise RuntimeError('Normal repair input failed')
        if not MAT.connect_material_property(node,'',prop):raise RuntimeError('Normal repair output failed')
    custom('''float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,.0001);
float3 q=P/150.0;
float3 grain=Texture2DSample(A,ASampler,q.yz).rgb*w.x+Texture2DSample(A,ASampler,q.xz).rgb*w.y+Texture2DSample(A,ASampler,q.xy).rgb*w.z;
float wet=1.0-smoothstep(30.0,135.0,P.z);
return float3(.25,.255,.23)*(grain*.7+.5)*lerp(1.0,.62,wet);''',{'P':position,'N':normal,'A':a},unreal.MaterialProperty.MP_BASE_COLOR)
    custom('''// The source FBX audit proves every skirt triangle faces downward.
// World-space two-sided normals are not automatically flipped by Unreal.
N=-N;
float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,.0001);
float3 q=P/150.0;
float3 x=Texture2DSample(B,BSampler,q.yz).rgb*2.0-1.0;
float3 y=Texture2DSample(B,BSampler,q.xz).rgb*2.0-1.0;
float3 z=Texture2DSample(B,BSampler,q.xy).rgb*2.0-1.0;
float3 perturb=float3(0,x.x,x.y)*w.x+float3(y.x,0,y.y)*w.y+float3(z.x,z.y,0)*w.z;
return normalize(N+perturb*.24);''',{'P':position,'N':normal,'B':b},unreal.MaterialProperty.MP_NORMAL)
    custom('return lerp(.65,.91,smoothstep(30.0,135.0,P.z));',{'P':position},unreal.MaterialProperty.MP_ROUGHNESS,True)
    errors=MAT.recompile_material(material)
    if errors is None or list(errors):raise RuntimeError('Skirt normal material compilation failed: '+str(errors))
    ASSETS.set_metadata_tag(material,'SP_M3SkirtNormalRepair',fingerprint)
    if not ASSETS.save_loaded_asset(material):raise RuntimeError('Cannot save skirt normal repair')
    return material

def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem);world=editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name().split('.')[0]!='/Game/Maps/StanleyParkSeawall':raise RuntimeError('Open the separate Seawall map and stop Play')
    pointer=read(ROOT/'exports/m3-edge-skirts/latest.json');path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']:raise RuntimeError('Skirt manifest changed')
    source=read(path);audit=read(ROOT/'evidence/m3-skirt-normal-attribution.json')
    if audit['manifest_sha256']!=pointer['sha256'] or audit['upward_faces'] or audit['downward_faces']!=sum(a['triangles'] for a in source['assets']):raise RuntimeError('Normal audit does not cover this complete skirt export')
    for asset in source['assets']:
        if sha(ROOT/asset['fbx'])!=asset['sha256']:raise RuntimeError('Audited skirt FBX changed')
    inputs={p:sha(ROOT/p) for p in ['pipeline/unreal/repair_m3_skirt_normals.py','pipeline/unreal/import_m3_edges.py','exports/m3-edge-skirts/latest.json','evidence/m3-skirt-normal-attribution.json','exports/m3-edges/latest.json']}
    fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest();root='/Game/StanleyPark/Seawall/EdgeSkirts/NormalRepair/v_'+fingerprint[:12]
    actors=[a for a in ACTORS.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    targets=[a for a in actors if 'SP_M3EdgeSkirts' in [str(t) for t in a.tags]];expected={a['name']+'_'+source['version'] for a in source['assets']}
    if len(targets)!=len(expected) or {a.get_actor_label() for a in targets}!=expected:raise RuntimeError('Live skirt actor set differs')
    before={a.get_path_name():HELPERS['invariant'](a) for a in actors}
    baseline=[dict(actor=a.get_path_name(),label=a.get_actor_label(),overrides=[m.get_path_name() if m else None for m in a.static_mesh_component.get_editor_property('override_materials')],material=a.static_mesh_component.get_material(0).get_path_name()) for a in targets]
    if not LEVELS.save_current_level():raise RuntimeError('Cannot save before normal archive')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap';digest=sha(map_path);archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap');archive.parent.mkdir(exist_ok=True)
    if not archive.exists():shutil.copy2(map_path,archive)
    if sha(archive)!=digest:raise RuntimeError('Normal repair archive differs')
    report=ROOT/'evidence'/('m3-skirt-normal-repair-'+fingerprint[:12]+'.json');record=dict(success=False,started_utc=datetime.now(timezone.utc).isoformat(),input_hashes=inputs,asset_root=root,baseline=baseline,archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,visual_acceptance=False)
    report.write_text(json.dumps(record,indent=2))
    edges=read(ROOT/read(ROOT/'exports/m3-edges/latest.json')['manifest']);material=build_material(root,fingerprint,edges)
    for actor in targets:
        actor.modify();actor.static_mesh_component.modify();actor.static_mesh_component.set_material(0,material)
        if actor.static_mesh_component.get_material(0)!=material:raise RuntimeError('Normal repair material readback differs')
    after={a.get_path_name():HELPERS['invariant'](a) for a in actors}
    if before!=after:raise RuntimeError('Geometry, transform or collision changed during material repair')
    if not LEVELS.save_current_level():raise RuntimeError('Cannot save normal repair')
    record.update(success=True,actors=len(targets),material=material.get_path_name(),geometry_collision_unchanged=True,original_actor_invariants=after)
    report.write_text(json.dumps(record,indent=2));return dict(success=True,report=str(report),actors=len(targets),material=material.get_path_name())

if __name__ in {'__main__','<run_path>'}:result=apply()
