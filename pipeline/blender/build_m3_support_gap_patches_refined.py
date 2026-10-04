"""Refine the underpass seam patch rim; preserve the accepted shore patch geometry."""
from pathlib import Path
import hashlib, json, math, shutil
import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
OWNER = 'm3_support_gap_patches'
CASES = [
    dict(section=23, source='SM_PavementSupport_030', faces=[45,47,49], lower=-.25, upper=.035, image='boundary/section_023', pixel=[1083,550]),
    dict(section=37, source='SM_PavementSupport_048', faces=[443,445,447], lower=-.035, upper=.035, image='midpoint/section_037', pixel=[1087,657]),
]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def geometry(scene):
    baseline=json.loads((ROOT/'evidence/m3-baseline-20261003/blender-original-geometry.json').read_text())
    result=[]
    for row in baseline:
        obj=bpy.data.objects[row['name']]
        coordinates=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
        obj.data.vertices.foreach_get('co',coordinates)
        indices=np.empty(len(obj.data.loops),dtype=np.int32)
        obj.data.loops.foreach_get('vertex_index',indices)
        result.append(dict(name=obj.name,geometry_sha256=hashlib.sha256(coordinates.tobytes()+indices.tobytes()).hexdigest(),matrix=[list(r) for r in obj.matrix_world],collision=obj.get('collision')))
    if result!=baseline: raise RuntimeError('Protected original geometry differs from its baseline')
    return result

def build():
    expected=ROOT/'blender/StanleyPark_Seawall.blend'
    if Path(bpy.data.filepath).resolve()!=expected.resolve(): raise RuntimeError('Open Seawall source')
    scene=bpy.data.scenes['StanleyPark_M1']; bpy.context.window.scene=scene
    if scene.unit_settings.scale_length!=1: raise RuntimeError('Expected metre source')
    before=geometry(scene)
    inputs={p:sha(ROOT/p) for p in ['pipeline/blender/build_m3_support_gap_patches_refined.py','pipeline/blender/build_m3_support_gap_patches.py','exports/m3-support-gap-patches/f67ce93a75fe/manifest.json','evidence/m3-views/m3-v4-local-repairs/midpoint/section_037.png','evidence/m3-v3-small-wedge-attribution.json','exports/m3-edges/latest.json','evidence/m3-baseline-20261003/blender-original-geometry.json']}
    for case in CASES:
        for p in [f"data/derived/surface-meshes/{case['source']}.npz",f"evidence/m3-views/m3-v3-final-route/{case['image']}.png",f"evidence/m3-views/m3-v3-final-route/{case['image']}.json"]: inputs[p]=sha(ROOT/p)
    inputs['scene_geometry_digest']=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-support-gap-patches'/version
    if (folder/'manifest.json').exists(): raise RuntimeError('Immutable version already exists')
    bpy.ops.wm.save_as_mainfile(filepath=str(expected)); digest=sha(expected)
    archive=ROOT/'blender/archive'/('StanleyPark_Seawall_'+digest[:12]+'.blend'); archive.parent.mkdir(exist_ok=True)
    if not archive.exists(): shutil.copy2(expected,archive)
    if sha(archive)!=digest: raise RuntimeError('Archive differs')
    collection=bpy.data.collections.new('SP_M3SupportGapPatches_'+version); scene.collection.children.link(collection)
    folder.mkdir(parents=True,exist_ok=True); assets=[];details=[]
    rotation=Matrix.Rotation(-math.pi/2,4,'Z')
    for case in CASES:
        source=np.load(ROOT/f"data/derived/surface-meshes/{case['source']}.npz"); points=source['vertices']+source['anchor']; faces=source['faces']
        obj=bpy.data.objects[case['source']]
        local_actual=np.empty(len(obj.data.vertices)*3,dtype=np.float32);obj.data.vertices.foreach_get('co',local_actual)
        transform=np.asarray(obj.matrix_world,dtype=np.float64)
        actual=local_actual.reshape(-1,3)@transform[:3,:3].T+transform[:3,3]
        vertices=[]; triangles=[]
        for face_index in case['faces']:
            corners=points[faces[face_index]]
            if any(np.linalg.norm(actual-p,axis=1).min()>.001 for p in corners): raise RuntimeError('Source endpoints differ from the live Blender mesh')
            a,b=corners[:2]; normal=np.cross(b-a,corners[2]-a); normal/=np.linalg.norm(normal)
            if abs(normal[2])>1e-6: raise RuntimeError('Expected vertical support face')
            # The first edge of each odd source triangle is the ground seam.
            # The solid thickness straddles the support plane. All ends overlap.
            tangent=b-a; tangent/=np.linalg.norm(tangent)
            a=a-tangent*.025; b=b+tangent*.025
            low=np.array([a,b]);low[:,2]+=case['lower'];high=np.array([a,b]);high[:,2]+=case['upper']
            half_depth=.001 if case['section']==37 else .015
            vv=np.array([low[0]-normal*half_depth,low[1]-normal*half_depth,high[1]-normal*half_depth,high[0]-normal*half_depth,low[0]+normal*half_depth,low[1]+normal*half_depth,high[1]+normal*half_depth,high[0]+normal*half_depth])
            center=vv.mean(0); offset=len(vertices);vertices.extend(vv.tolist())
            for quad in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(3,2,6,7),(0,3,7,4),(1,5,6,2)]:
                quad=list(quad);n=np.cross(vv[quad[1]]-vv[quad[0]],vv[quad[2]]-vv[quad[0]])
                if np.dot(n,vv[quad].mean(0)-center)<0: quad.reverse()
                triangles.extend([(offset+quad[0],offset+quad[1],offset+quad[2]),(offset+quad[0],offset+quad[2],offset+quad[3])])
        values=np.asarray(vertices);anchor=(values.min(0)+values.max(0))*.5;local=values-anchor
        name=f"SM_M3SupportGap_{case['section']:03d}"
        mesh=bpy.data.meshes.new(name+'_'+version);mesh.from_pydata(local.tolist(),[],triangles);mesh.update()
        if obj.data.materials: mesh.materials.append(obj.data.materials[0])
        authored=bpy.data.objects.new(name+'_'+version,mesh);collection.objects.link(authored);authored.location=anchor;authored['pipeline_owner']=OWNER;authored['collision']='none'
        temporary_mesh=mesh.copy();temporary_mesh.transform(rotation);temporary=bpy.data.objects.new('Export_'+name,temporary_mesh);scene.collection.objects.link(temporary)
        bpy.ops.object.select_all(action='DESELECT');temporary.select_set(True);bpy.context.view_layer.objects.active=temporary
        path=folder/(name+'.fbx')
        try:
            bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},use_mesh_modifiers=True,mesh_smooth_type='FACE',use_triangles=True,use_space_transform=False,axis_forward='Y',axis_up='Z',global_scale=1.0,apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',bake_space_transform=True,bake_anim=False,add_leaf_bones=False,path_mode='STRIP',use_custom_props=False,colors_type='LINEAR')
        finally:
            bpy.data.objects.remove(temporary,do_unlink=True);bpy.data.meshes.remove(temporary_mesh)
        exported=local[:,[1,0,2]]*100
        assets.append(dict(name=name,blender_object=authored.name,fbx=path.relative_to(ROOT).as_posix(),sha256=sha(path),anchor_local_m=anchor.tolist(),bounds_min_cm=exported.min(0).tolist(),bounds_max_cm=exported.max(0).tolist(),triangles=len(triangles),section_id=f"section_{case['section']:03d}"))
        details.append(dict(case,ground_edge_vertex_rule='First two vertices of each listed source face',solid_depth_m=.002 if case['section']==37 else .03,end_overlap_m=.025,bounds_min_local_m=values.min(0).tolist(),bounds_max_local_m=values.max(0).tolist()))
    for old in bpy.data.collections:
        if old!=collection and old.name.startswith('SP_M3SupportGapPatches_'):
            old.hide_viewport=True;old.hide_render=True
    if before!=geometry(scene): raise RuntimeError('An original mesh changed')
    manifest=dict(schema_version=1,version=version,input_hashes=inputs,asset_root='/Game/StanleyPark/Seawall/SupportGapPatches/v_'+version,assets=assets,counts=dict(patches=len(assets),solid_prisms=6),patches=details,archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,collision='none',source_geometry_unchanged=True,visual_acceptance=False,scope='Two localized support/terrain seam closures tied to unchanged source endpoints. No route surface or collision change.')
    path=folder/'manifest.json';path.write_text(json.dumps(manifest,indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(expected))
    (ROOT/'exports/m3-support-gap-patches/latest.json').write_text(json.dumps(dict(manifest=path.relative_to(ROOT).as_posix(),sha256=sha(path)),indent=2))
    return dict(version=version,manifest=str(path),assets=len(assets),triangles=sum(x['triangles'] for x in assets))

if __name__ in {'__main__','<run_path>'}: result=build()
