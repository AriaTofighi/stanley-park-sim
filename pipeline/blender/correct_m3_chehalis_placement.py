"""Move only the new Chehalis decoration to its raw OSM point after clearance.

No original mesh, material, collision or form geometry changes. The coordinator
saves the blend and applies the matching Unreal translation in a serial slot.
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

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open Seawall source')
    pointer_path=ROOT/'exports/m3-landmark-forms/latest.json';pointer=json.loads(pointer_path.read_text())
    path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']:raise RuntimeError('Form manifest differs')
    source=json.loads(path.read_text());asset=next(a for a in source['assets'] if a['feature_id']=='ART_96')
    obj=bpy.data.objects.get(asset['name'])
    if obj is None or obj.get('feature_id')!='ART_96' or obj.parent:raise RuntimeError('Missing unparented new Chehalis form')
    before=list(obj.location)
    if np.linalg.norm(np.array(before)-asset['position_local_m'])>.01:raise RuntimeError('Chehalis source transform differs')
    reconciliation_path=ROOT/'evidence/m3-landmark-placement-source-reconciliation.json'
    reconciliation=json.loads(reconciliation_path.read_text())
    if sha(ROOT/reconciliation['source'])!=reconciliation['source_sha256']:raise RuntimeError('OSM source differs')
    point=np.array(next(r for r in reconciliation['rows'] if r['feature_id']=='ART_96')['source_local_xy_m'])
    local=np.array([tuple(obj.matrix_world@v.co) for v in obj.data.vertices])-before
    radius=float(np.linalg.norm(local[:,:2],axis=1).max())
    paved=[];ground_verts=[];ground_faces=[];geometry=[]
    for item in bpy.context.scene.objects:
        is_paved=item.name.startswith(('SM_Pavement_','SM_Pedestrian_','SM_Route_'))
        is_ground=item.name.startswith('SM_Terrain_')
        if item.type!='MESH' or not (is_paved or is_ground):continue
        vertices=np.array([tuple(item.matrix_world@v.co) for v in item.data.vertices])
        if np.any(vertices[:,:2].max(0)<point-20) or np.any(vertices[:,:2].min(0)>point+20):continue
        faces=[tuple(p.vertices) for p in item.data.polygons]
        geometry.append(dict(name=item.name,sha256=hashlib.sha256(vertices.astype('<f8').tobytes()+json.dumps(faces).encode()).hexdigest()))
        if is_ground:
            start=len(ground_verts);ground_verts.extend(vertices.tolist());ground_faces.extend(tuple(start+i for i in f) for f in faces)
        if is_paved:
            item.data.calc_loop_triangles()
            paved.extend(vertices[list(f.vertices)].tolist() for f in item.data.loop_triangles)
    if not paved or not ground_faces:raise RuntimeError('Missing local pavement or terrain')
    triangles=np.array(paved);a=triangles[:,:,:2];b=np.roll(a,-1,axis=1);delta=b-a
    def clearance(p):
        cross=delta[:,:,0]*(p[1]-a[:,:,1])-delta[:,:,1]*(p[0]-a[:,:,0])
        inside=(cross.min(1)>=0)|(cross.max(1)<=0)
        t=np.clip(np.sum((p-a)*delta,axis=2)/np.maximum(np.sum(delta*delta,axis=2),1e-12),0,1)
        distances=np.linalg.norm(p-a-t[:,:,None]*delta,axis=2).min(1);distances[inside]=0
        return float(distances.min()-radius)
    gap=clearance(point)
    if gap<.35:raise RuntimeError('Raw OSM point fails conservative pavement clearance: '+str(gap))
    tree=BVHTree.FromPolygons(ground_verts,ground_faces)
    footprint=local[np.abs(local[:,2]-local[:,2].min())<.001,:2]
    supports=[]
    for xy in [point]+[point+p for p in footprint]:
        hit,normal,_,_=tree.ray_cast(Vector((float(xy[0]),float(xy[1]),100)),Vector((0,0,-1)),150)
        if hit is None or normal.z<.8:raise RuntimeError('Ground support missing or steep')
        supports.append(float(hit.z))
    if max(supports)-min(supports)>.45:raise RuntimeError('Ground slope exceeds base allowance')
    after=[float(point[0]),float(point[1]),min(supports)-float(local[:,2].min())-.035]
    inputs={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [Path(__file__),path,reconciliation_path,ROOT/reconciliation['source']]}
    version=hashlib.sha256(json.dumps(dict(inputs=inputs,geometry=geometry),sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-landmark-placement'/version
    if (folder/'manifest.json').exists():raise RuntimeError('Placement version exists')
    mesh_sha=hashlib.sha256(np.array([tuple(v.co) for v in obj.data.vertices],dtype='<f8').tobytes()).hexdigest()
    result=dict(version=version,feature_id='ART_96',actor_label=asset['name'],input_hashes=inputs,source_geometry=geometry,
        original_asset=asset,asset_root=source['asset_root'],before_local_m=before,after_local_m=after,
        delta_unreal_cm=[(after[1]-before[1])*100,(after[0]-before[0])*100,(after[2]-before[2])*100],
        conservative_footprint_radius_m=radius,before_pavement_gap_m=clearance(np.array(before[:2])),
        after_pavement_gap_m=gap,minimum_required_gap_m=.35,terrain_support_heights_m=supports,
        mesh_geometry_sha256=mesh_sha,form_geometry_unchanged=True,detail_layer_unchanged=True,
        source_basis='Raw OSM node 5237345536 transformed to project EPSG:3157. Exact surveyed placement remains unverified.',
        visual_acceptance=False,geographic_accuracy_accepted=False)
    folder.mkdir(parents=True);(folder/'manifest.json').write_text(json.dumps(result,indent=2))
    (folder.parent/'latest.json').write_text(json.dumps(dict(manifest=(folder/'manifest.json').relative_to(ROOT).as_posix(),sha256=sha(folder/'manifest.json')),indent=2))
    obj.location=after;bpy.context.view_layer.update()
    if hashlib.sha256(np.array([tuple(v.co) for v in obj.data.vertices],dtype='<f8').tobytes()).hexdigest()!=mesh_sha:raise RuntimeError('Geometry changed')
    return dict(version=version,before=before,after=after,pavement_gap_m=gap,form_geometry_unchanged=True,detail_layer_unchanged=True)

if __name__ in {'__main__','<run_path>'}:result=build()
