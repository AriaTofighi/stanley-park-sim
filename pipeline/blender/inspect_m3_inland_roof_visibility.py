"""Read-only source terrain screening for inland roof review.

This writes a diagnostic sidecar only. It changes no Blender data and does
not establish visual acceptance. The coordinator authorizes its serial use.
"""
from pathlib import Path
import hashlib,json,math
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def world(o):
 a=np.empty(len(o.data.vertices)*3,dtype=np.float32);o.data.vertices.foreach_get('co',a)
 a=a.reshape(-1,3);m=np.asarray(o.matrix_world,dtype=np.float64)
 return a@m[:3,:3].T+m[:3,3]
def camera(p,t):
 d=t-p
 return dict(location=dict(x=float(p[1]*100),y=float(p[0]*100),z=float(p[2]*100)),rotation=dict(pitch=math.degrees(math.atan2(d[2],np.linalg.norm(d[:2]))),yaw=math.degrees(math.atan2(d[0],d[1])),roll=0),scale=dict(x=1,y=1,z=1))
def inspect():
 assert Path(bpy.data.filepath).resolve()==(ROOT/'blender/StanleyPark_Seawall.blend').resolve()
 routepath=ROOT/'data/derived/paved-circuit-runtime.json';route=np.asarray(json.loads(routepath.read_text())['points_local_m'])
 lengths=np.linalg.norm(np.diff(route,axis=0),axis=1);stations=np.r_[0,np.cumsum(lengths)]
 planpath=ROOT/'manifests/m3-landmark-final-camera-candidates.json';plan=json.loads(planpath.read_text())
 vertices=[];faces=[];owners=[];geometry=[]
 for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
  if o.type!='MESH' or not o.name.startswith('SM_Terrain_') or o.hide_render or o.hide_get():continue
  points=world(o);polys=[tuple(p.vertices) for p in o.data.polygons];start=len(vertices)
  vertices.extend(points.tolist());faces.extend(tuple(start+i for i in p) for p in polys);owners.extend([o.name]*len(polys))
  geometry.append(dict(name=o.name,sha256=hashlib.sha256(points.astype('<f8').tobytes()+json.dumps(polys).encode()).hexdigest()))
 tree=BVHTree.FromPolygons(vertices,faces)
 features=[]
 for fid in ('SP_teahouse','SP_third_beach'):
  entry=next(x for x in plan['views'] if x['id']==fid)
  names=[n for n in entry['source_linked_meshes'] if 'Roof' in n]
  targets=[];target_geometry=[]
  for name in names:
   o=bpy.data.objects[name];points=world(o);polys=[tuple(p.vertices) for p in o.data.polygons]
   targets.extend(points.tolist());targets.extend(points[list(p)].mean(0).tolist() for p in polys)
   target_geometry.append(dict(name=name,sha256=hashlib.sha256(points.astype('<f8').tobytes()+json.dumps(polys).encode()).hexdigest()))
  targets=np.unique(np.round(targets,5),axis=0);base=entry['nearest_station_m'];rows=[]
  for offset in range(-350,351,10):
   s=float(np.clip(base+offset,0,stations[-1]));i=min(len(route)-2,int(np.searchsorted(stations,s,side='right')-1));f=(s-stations[i])/lengths[i]
   eye=route[i]*(1-f)+route[i+1]*f;eye=eye.copy();eye[2]+=1.65
   hits=[];clear=[]
   for ti,t in enumerate(targets):
    d=t-eye;distance=float(np.linalg.norm(d));h,n,ix,gap=tree.ray_cast(Vector(eye),Vector(d/distance),distance-.05)
    if h is None:clear.append(ti)
    else:hits.append(dict(target_index=ti,occluder=owners[ix],hit_distance_m=float(gap),distance_to_target_m=distance))
   aim=targets[clear].mean(0) if clear else targets[np.argmax(targets[:,2])]
   rows.append(dict(station_m=s,offset_m=offset,eye_local_m=eye.tolist(),clear_target_count=len(clear),clear_target_indices=clear,hits=hits,target_local_m=aim.tolist(),requested_camera=camera(eye,aim)))
  features.append(dict(feature_id=fid,route_interval_m=[rows[0]['station_m'],rows[-1]['station_m']],sample_spacing_m=10,source_roof_geometry=target_geometry,target_points_local_m=targets.tolist(),target_count=len(targets),samples=rows,clear_sample_count=sum(bool(r['clear_target_count']) for r in rows)))
 out=dict(schema_version=1,input_hashes={routepath.relative_to(ROOT).as_posix():sha(routepath),planpath.relative_to(ROOT).as_posix():sha(planpath),Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))},terrain_geometry=geometry,features=features,scope='Terrain-only ray screening at 1.65 m above the measured route, to every roof vertex and polygon centre. Clear rays can still meet trees or other structures. This is not image review, continuous visibility proof, or acceptance.',scene_changed=False)
 output=ROOT/'evidence/m3-inland-roof-visibility.json';output.write_text(json.dumps(out,indent=2)+'\n')
 return dict(path=str(output),features=[dict(id=x['feature_id'],targets=x['target_count'],samples=len(x['samples']),clear_samples=x['clear_sample_count'],maximum_clear_targets=max(r['clear_target_count'] for r in x['samples'])) for x in features])
if __name__ in {'__main__','<run_path>'}:result=inspect()
