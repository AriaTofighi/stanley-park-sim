"""Read-only route camera candidates for the final landmark review.

The coordinator executes this in the serial Blender slot. It does not change
the scene, camera, map or v1 evidence. Ray screening excludes vegetation, so
only actual Unreal captures can establish visibility or visual acceptance.
"""
from pathlib import Path
import hashlib
import json
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def camera(eye,target):
    d=np.asarray(target)-eye
    return dict(location=dict(x=float(eye[1]*100),y=float(eye[0]*100),z=float(eye[2]*100)),
        rotation=dict(pitch=math.degrees(math.atan2(d[2],np.linalg.norm(d[:2]))),yaw=math.degrees(math.atan2(d[0],d[1])),roll=0),
        scale=dict(x=1,y=1,z=1))


def build(entries=None, target_positions=None, output=None):
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open the Seawall source')
    scene=bpy.context.scene
    route_path=ROOT/'data/derived/paved-circuit-runtime.json';route=np.asarray(json.loads(route_path.read_text())['points_local_m'])
    lengths=np.linalg.norm(np.diff(route,axis=0),axis=1);stations=np.r_[0,np.cumsum(lengths)]
    if entries is None:
        entries=json.loads((ROOT/'manifests/seawall-m3-sections.json').read_text())['landmark_views']
    inventory={r['id']:r for r in json.loads((ROOT/'manifests/critical-features.json').read_text())['features']}
    positions={}
    for path in [ROOT/'exports/m3-landmark-forms/latest.json',ROOT/'exports/m3-landmark-detail/latest.json']:
        if path.exists():
            ptr=json.loads(path.read_text());data=json.loads((ROOT/ptr['manifest']).read_text())
            for row in data['assets']:
                if row['feature_id']=='SP_totem_precinct':continue
                low=np.asarray(row['bounds_min_cm'])/100;high=np.asarray(row['bounds_max_cm'])/100;local=np.asarray(row['position_cm'])/100
                p=local+(low+high)/2;positions[row['feature_id']]=p[[1,0,2]]
    placement_pointer=ROOT/'exports/m3-landmark-placement/latest.json'
    if placement_pointer.exists():
        pointer=json.loads(placement_pointer.read_text());path=ROOT/pointer['manifest']
        if sha(path)!=pointer['sha256']:raise RuntimeError('Landmark placement manifest differs')
        placement=json.loads(path.read_text());fid=placement['feature_id']
        if fid in positions:positions[fid]+=np.asarray(placement['after_local_m'])-np.asarray(placement['before_local_m'])
    # Survey-derived centres override group-centre metadata that aimed at buildings.
    explicit={'SP_totem_precinct':[1614.5,-371.25,8.0],'SP_people_amongst':[1583.86,-433.82,6.4],
        'SP_yelton_pole':[1585.8,-388.3,9.2],'ART_94':[1612.7,-357.8,6.5],
        'ART_202':[1608.9,-370.5,8.0],'ART_89':[1613.8,-375,6.0],
        'ART_91':[1620.72,-362.96,8.0],'ART_92':[1621.51,-369.26,7.0],
        'ART_93':[1621.1,-383.7,8.5]}
    positions.update({k:np.asarray(v) for k,v in explicit.items()})
    positions.update({k:np.asarray(v) for k,v in (target_positions or {}).items()})
    verts=[];faces=[];owners=[];records=[]
    for obj in sorted(scene.objects,key=lambda o:o.name):
        if obj.type!='MESH' or not obj.name.startswith('SM_') or obj.hide_render or obj.hide_get():continue
        if obj.name.startswith(('SM_Canopy','SM_SeawallTree','SM_M3Crown','SM_M3Canopy','SM_SWCanopy','SM_M3SiwashCrown','SM_Water','SM_Ocean','SM_Lake','SM_Axis','SM_SWTree','SM_SeawallShore')):continue
        points=np.asarray([tuple(obj.matrix_world@v.co) for v in obj.data.vertices]);start=len(verts);verts.extend(points.tolist())
        polys=[tuple(p.vertices) for p in obj.data.polygons];faces.extend(tuple(start+i for i in p) for p in polys);owners.extend([obj.name]*len(polys))
        records.append(dict(name=obj.name,geometry_sha256=hashlib.sha256(points.astype('<f8').tobytes()+json.dumps(polys).encode()).hexdigest()))
    tree=BVHTree.FromPolygons(verts,faces)
    rows=[]
    for entry in entries:
        fid=entry['id'];names=entry['linked_meshes'];target=positions.get(fid)
        if target is None:
            objs=[bpy.data.objects[n] for n in names if n in bpy.data.objects]
            if objs:
                points=np.asarray([tuple(o.matrix_world@Vector(c)) for o in objs for c in o.bound_box]);target=(points.min(0)+points.max(0))/2
            else:
                p=inventory.get(fid,{}).get('position_local_m')
                if p is None:
                    rows.append(dict(id=fid,result='no_source_target',candidates=[],accepted=False));continue
                target=np.asarray(p if len(p)==3 else p+[8.0])
        distances=np.linalg.norm(route[:,:2]-target[:2],axis=1);nearest=int(np.argmin(distances));base_station=stations[nearest]
        candidates=[]
        for offset in [-110,-70,-40,0,40,70,110]:
            station=float(np.clip(base_station+offset,0,stations[-1]));i=min(len(route)-2,int(np.searchsorted(stations,station,side='right')-1));f=(station-stations[i])/max(lengths[i],1e-8)
            eye=route[i]*(1-f)+route[i+1]*f;eye=eye.copy();eye[2]+=1.65
            delta=target-eye;distance=float(np.linalg.norm(delta));hit,normal,index,gap=tree.ray_cast(Vector(eye),Vector(delta/distance),max(0,distance-.15))
            occluder=owners[index] if hit is not None else None
            own_hit=occluder in names or (occluder and (fid=='SP_totem_precinct' and 'M3Detail_' in occluder))
            clear=hit is None or own_hit or (gap is not None and distance-gap<1.0)
            candidates.append(dict(id=fid+'_route_'+str(offset).replace('-','m'),station_m=station,offset_m=offset,
                requested_camera=camera(eye,target),target_local_m=target.tolist(),range_m=distance,
                terrain_structure_ray_clear=bool(clear),first_occluder=occluder,first_hit_distance_m=float(gap) if gap is not None else None,
                view_scope='route evidence candidate; vegetation excluded from ray screening',accepted=False))
        candidates.sort(key=lambda r:(not r['terrain_structure_ray_clear'],r['range_m']))
        selected=candidates[:2]
        # A separate source-centred authoring angle checks form quality only.
        # It never establishes route visibility and is explicitly labelled.
        span=entry.get('supplemental_span_m',18 if fid.startswith('ART_') or 'totem' in fid or fid in {'SP_lord_stanley','SP_robert_burns','SP_queen_victoria'} else 25)
        eye=target+np.array([span,-span*.35,max(2,span*.12)])
        supplemental=dict(id=fid+'_form_only',requested_camera=camera(eye,target),target_local_m=target.tolist(),
            view_scope='supplemental form review only; not a route view or visibility proof',accepted=False)
        rows.append(dict(id=fid,name=entry['name'],target_local_m=target.tolist(),nearest_station_m=float(base_station),
            source_linked_meshes=names,candidates=selected,all_candidate_screens=candidates,supplemental=supplemental,
            result='screened_candidates' if any(r['terrain_structure_ray_clear'] for r in candidates) else 'all_screened_route_views_blocked',accepted=False))
    output=Path(output) if output is not None else ROOT/'manifests/m3-landmark-final-camera-candidates.json'
    result=dict(schema_version=1,route_sha256=sha(route_path),source_geometry_digest=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),
        scene_geometry=records,views=rows,route_eye_height_m=1.65,limits='Read-only candidate plan. Ray casts screen terrain and structures only. They do not prove visibility, identity, safety, performance or acceptance. Keep v1 evidence unchanged. Capture under a fresh source binding.',accepted=False)
    output.write_text(json.dumps(result,indent=2))
    return dict(path=str(output),landmarks=len(rows),all_route_candidates_blocked=sum(r['result']=='all_screened_route_views_blocked' for r in rows))


if __name__ in {'__main__','<run_path>'}:
    result=build()
