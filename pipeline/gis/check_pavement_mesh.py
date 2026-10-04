"""Numerical continuity checks and runtime collision transfer controls."""
import json
from pathlib import Path
import numpy as np
from acquire_sources import save_json,digest
ROOT=Path(__file__).resolve().parents[2]
manifest=json.loads((ROOT/'manifests/surface-model.json').read_text())
runtime=json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text())
points=np.asarray(runtime['points_local_m'])
seams=[];last=None;first=None;bad_faces=0;triangle_count=0
for item in manifest['pavement']:
    if item['role']!='pavement':continue
    p=np.load(ROOT/item['path']);v=p['vertices']+p['anchor'];f=p['faces']
    if first is None:first=v[:2]
    if last is not None:seams.append(float(abs(last-v[:2]).max()))
    last=v[-4:-2] if item.get('overlap_stations') else v[-2:]
    a=v[f[:,1],:2]-v[f[:,0],:2];b=v[f[:,2],:2]-v[f[:,0],:2]
    area=a[:,0]*b[:,1]-a[:,1]*b[:,0]
    bad_faces+=int((area<=1e-8).sum());triangle_count+=len(f)
seams.append(float(abs(last-first).max()))
grade=np.diff(points[:,2])/np.maximum(np.linalg.norm(np.diff(points[:,:2],axis=0),axis=1),1e-8)
result=dict(pavement_triangles=triangle_count,inverted_or_degenerate_faces=bad_faces,
    maximum_chunk_seam_m=max(seams),closed_seam_m=seams[-1],max_grade=float(abs(grade).max()),
    route_length_m=float(runtime['chainage_runtime_m'][-1]),
    max_lateral_smoothing_m=runtime['lateral_smoothing_displacement_max_m'],
    source_accuracy_accepted=False,scope='Geometry continuity only; not surveyed lane-edge or height acceptance')
result['pass']=bool(bad_faces==0 and max(seams)<1e-5 and abs(grade).max()<.15)
save_json(ROOT/'evidence/paved-mesh-continuity.json',result)
controls=json.loads((ROOT/'data/derived/surface-control-points.json').read_text())
base=controls.get('terrain_control_count',len(controls['points_local_m']))
controls['terrain_control_count']=base
controls['points_local_m']=controls['points_local_m'][:base]+points[::10].tolist()
controls['pavement_control_count']=len(points[::10])
controls['method']='40 terrain triangle centroids per section plus a pavement centre point every 10 source metres'
for key in ('pre_structure_control_count', 'structure_control_groups', 'structure_control_count',
            'structure_control_method', 'structure_manifests'):
    controls.pop(key, None)
platform_file=ROOT/'manifests/brockton-platform.json'
controls['landmark_control_count']=0
controls['landmark_sources']=[]
if platform_file.exists():
    platform=json.loads(platform_file.read_text())
    floor=next(asset for asset in platform['assets'] if asset['name']=='SM_Brockton_WalkingPlatformReview')
    mesh_path=ROOT/floor['path']
    if digest(mesh_path)!=floor['sha256']:
        raise RuntimeError('Brockton floor differs from its manifest')
    mesh=np.load(mesh_path)
    centroids=(mesh['vertices'][mesh['faces']]+mesh['anchor']).mean(axis=1)
    controls['points_local_m'].extend(centroids.tolist())
    controls['landmark_control_count']=len(centroids)
    controls['landmark_sources']=[dict(path=platform_file.relative_to(ROOT).as_posix(),sha256=digest(platform_file))]
    controls['method']+='; every Brockton walking-floor triangle centroid'
save_json(ROOT/'data/derived/surface-control-points.json',controls)
print(json.dumps(result,indent=2))
if not result['pass']:raise RuntimeError('Pavement continuity failed')
