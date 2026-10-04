"""Author narrow noncollision strips between real pavement boundaries and terrain.

Only a separate visual layer is created. No source surface is moved or rebuilt.
Run in the coordinator's serial Blender authoring slot.
"""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import math
import shutil
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]
OWNER='m3_edge_skirts'
WIDTHS=(.12,.22,.35)
MAX_HEIGHT=.75
STEP=.5


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def key(p): return tuple(round(float(v),4) for v in p)


def geometry(scene):
    groups={name:([],[]) for name in ['terrain','pavement']}
    records=[]; boundary=defaultdict(list)
    for obj in sorted(scene.objects,key=lambda o:o.name):
        category='terrain' if obj.name.startswith('SM_Terrain_') else 'pavement' if obj.name.startswith('SM_Pavement_') else None
        if obj.type!='MESH' or category is None: continue
        points=np.asarray([tuple(obj.matrix_world@v.co) for v in obj.data.vertices],dtype='<f8')
        faces=[tuple(p.vertices) for p in obj.data.polygons]
        records.append(dict(name=obj.name,category=category,sha256=hashlib.sha256(points.tobytes()+json.dumps(faces).encode()).hexdigest()))
        vertices,polygons=groups[category]; start=len(vertices)
        vertices.extend(points.tolist()); polygons.extend(tuple(start+i for i in f) for f in faces)
        if category=='pavement':
            for face in faces:
                normal=np.cross(points[face[1]]-points[face[0]],points[face[2]]-points[face[0]])
                if abs(normal[2])<1e-8: continue
                for ai,bi in zip(face,face[1:]+face[:1]):
                    a,b=points[ai],points[bi]
                    boundary[tuple(sorted((key(a),key(b))))].append((a,b,1 if normal[2]>0 else -1,obj.name))
    trees={k:BVHTree.FromPolygons(v,f) for k,(v,f) in groups.items()}
    return trees,[v[0] for v in boundary.values() if len(v)==1],records


def build():
    expected=ROOT/'blender/StanleyPark_Seawall.blend'
    if Path(bpy.data.filepath).resolve()!=expected.resolve(): raise RuntimeError('Open the separate Seawall source')
    scene=bpy.data.scenes['StanleyPark_M1']
    if scene.unit_settings.scale_length!=1: raise RuntimeError('Expected metre source')
    if bpy.context.object and bpy.context.object.mode!='OBJECT': raise RuntimeError('Leave edit mode')
    trees,boundary,records=geometry(scene)
    inputs={p:sha(ROOT/p) for p in ['pipeline/blender/build_m3_edge_skirts.py','exports/m3-edges/latest.json','data/derived/paved-circuit-runtime.json','evidence/m3-edge-review-v1.json']}
    inputs['scene_geometry_digest']=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-edge-skirts'/version
    if (folder/'manifest.json').exists(): raise RuntimeError('Immutable skirt export already exists')
    route=np.asarray(read(ROOT/'data/derived/paved-circuit-runtime.json')['points_local_m'])
    delta=np.diff(route[:,:2],axis=0); length2=np.maximum((delta*delta).sum(1),1e-9)
    chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(route,axis=0),axis=1))]
    def station(p):
        t=np.clip(((p[:2]-route[:-1,:2])*delta).sum(1)/length2,0,1)
        distance=((route[:-1,:2]+delta*t[:,None]-p[:2])**2).sum(1); i=int(distance.argmin())
        return float(chain[i]+t[i]*(chain[i+1]-chain[i]))
    groups=defaultdict(lambda:([],[])); stats=Counter(); spans=[]; exclusions=[]
    for a,b,sign,name in boundary:
        horizontal=b[:2]-a[:2]; distance=float(np.linalg.norm(horizontal))
        if distance<.002: stats['degenerate_edge']+=1; continue
        outward=np.array([horizontal[1],-horizontal[0]])/distance*sign
        count=max(1,int(math.ceil(distance/STEP)))
        for i in range(count):
            ends=[a+(b-a)*i/count,a+(b-a)*(i+1)/count]
            midpoint=(ends[0]+ends[1])*.5; s=station(midpoint)
            chosen=None; reason='no_adjacent_terrain'
            for width in WIDTHS:
                terrain=[]; valid=True
                for p in [ends[0],midpoint,ends[1]]:
                    xy=p[:2]+outward*width
                    hit,_,_,_=trees['pavement'].ray_cast(Vector((float(xy[0]),float(xy[1]),float(p[2]+1))),Vector((0,0,-1)),2)
                    if hit is not None: valid=False; reason='adjacent_pavement'; break
                    hit,_,_,_=trees['terrain'].ray_cast(Vector((float(xy[0]),float(xy[1]),float(p[2]+MAX_HEIGHT+.05))),Vector((0,0,-1)),MAX_HEIGHT*2+.1)
                    if hit is None or abs(hit.z-p[2])>MAX_HEIGHT:
                        valid=False; reason='no_near_terrain'; break
                    terrain.append(np.array(tuple(hit)))
                if valid:
                    chosen=(width,terrain[0],terrain[2]); break
            if chosen is None:
                stats[reason]+=1
                exclusions.append(dict(source=name,station_m=s,reason=reason))
                continue
            width,c,d=chosen
            # Both seams are buried slightly. The strip stays outside the source path.
            aa=ends[0].copy(); bb=ends[1].copy(); aa[2]-=.002; bb[2]-=.002
            c[2]-=.012; d[2]-=.012
            tile=int(s/250); vertices,faces=groups[tile]; start=len(vertices)
            vertices.extend([aa.tolist(),bb.tolist(),d.tolist(),c.tolist()])
            faces.extend([(start,start+1,start+2),(start,start+2,start+3)])
            stats['strips']+=1
            spans.append(dict(source=name,station_m=s,width_m=width,length_m=distance/count,height_difference_m=max(abs(c[2]-aa[2]),abs(d[2]-bb[2]))))
    if not groups: raise RuntimeError('No safe visual strips found')
    bpy.context.window.scene=scene
    bpy.ops.wm.save_as_mainfile(filepath=str(expected)); digest=sha(expected)
    archive=ROOT/'blender/archive'/('StanleyPark_Seawall_'+digest[:12]+'.blend')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists(): shutil.copy2(expected,archive)
    if sha(archive)!=digest: raise RuntimeError('Archive differs')
    collection=bpy.data.collections.new('SP_M3EdgeSkirts_'+version); scene.collection.children.link(collection)
    folder.mkdir(parents=True,exist_ok=True); assets=[]
    material=bpy.data.materials.new('M_M3EdgeSkirt_'+version); material.diffuse_color=(.16,.155,.13,1)
    rotation=Matrix.Rotation(-math.pi/2,4,'Z')
    for tile,(vertices,faces) in sorted(groups.items()):
        values=np.asarray(vertices); anchor=(values.min(0)+values.max(0))*.5
        local=values-anchor; name=f'SM_M3EdgeSkirt_{tile:03d}'
        mesh=bpy.data.meshes.new(name+'_'+version); mesh.from_pydata(local.tolist(),[],faces); mesh.update(); mesh.materials.append(material)
        obj=bpy.data.objects.new(name+'_'+version,mesh); collection.objects.link(obj); obj.location=anchor
        obj['pipeline_owner']=OWNER; obj['collision']='none'
        temp_mesh=mesh.copy(); temp_mesh.transform(rotation)
        temporary=bpy.data.objects.new('Export_'+name,temp_mesh); scene.collection.objects.link(temporary)
        bpy.ops.object.select_all(action='DESELECT'); temporary.select_set(True); bpy.context.view_layer.objects.active=temporary
        path=folder/(name+'.fbx')
        try:
            bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},use_mesh_modifiers=True,mesh_smooth_type='FACE',use_triangles=True,use_space_transform=False,axis_forward='Y',axis_up='Z',global_scale=1.0,apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',bake_space_transform=True,bake_anim=False,add_leaf_bones=False,path_mode='STRIP',use_custom_props=False,colors_type='LINEAR')
        finally:
            bpy.data.objects.remove(temporary,do_unlink=True); bpy.data.meshes.remove(temp_mesh)
        exported=local[:,[1,0,2]]*100
        assets.append(dict(name=name,blender_object=obj.name,fbx=path.relative_to(ROOT).as_posix(),sha256=sha(path),anchor_local_m=anchor.tolist(),bounds_min_cm=exported.min(0).tolist(),bounds_max_cm=exported.max(0).tolist(),triangles=len(faces),section_id=f'section_{tile:03d}'))
    for old in bpy.data.collections:
        if old!=collection and old.name.startswith('SP_M3EdgeSkirts_'): old.hide_viewport=old.hide_render=True
    # Re-read actual authored source vertices. New strips are outside this digest.
    _,_,after=geometry(scene)
    if records!=after: raise RuntimeError('Original terrain or pavement changed')
    manifest=dict(schema_version=1,version=version,input_hashes=inputs,source_geometry=records,asset_root='/Game/StanleyPark/Seawall/EdgeSkirts/v_'+version,assets=assets,spans=spans,exclusions=exclusions,counts=dict(stats),archive=archive.relative_to(ROOT).as_posix(),archive_sha256=digest,collision='none',widths_m=WIDTHS,max_terrain_height_difference_m=MAX_HEIGHT,maximum_segment_m=STEP,source_geometry_unchanged=True,visual_acceptance=False,scope='Narrow visual closure between actual pavement boundary and nearby terrain. Excludes large cliffs and underpasses. Not a surveyed wall or a walkable surface.')
    path=folder/'manifest.json'; path.write_text(json.dumps(manifest,indent=2),encoding='utf8')
    bpy.ops.wm.save_as_mainfile(filepath=str(expected))
    (ROOT/'exports/m3-edge-skirts/latest.json').write_text(json.dumps(dict(manifest=path.relative_to(ROOT).as_posix(),sha256=sha(path)),indent=2))
    return dict(version=version,manifest=str(path),assets=len(assets),counts=dict(stats))

if __name__ in {'__main__','<run_path>'}: result=build()
