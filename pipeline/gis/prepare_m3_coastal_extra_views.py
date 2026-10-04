"""Offline source camera sidecar. Does not change an editor or existing plan."""
from pathlib import Path
import hashlib
import json
import math
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
def sha(p): return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def camera(eye,target):
    d=np.asarray(target)-eye
    return dict(location=dict(x=float(eye[1]*100),y=float(eye[0]*100),z=float(eye[2]*100)),rotation=dict(pitch=math.degrees(math.atan2(d[2],np.linalg.norm(d[:2]))),yaw=math.degrees(math.atan2(d[0],d[1])),roll=0),scale=dict(x=1,y=1,z=1))
def build():
    plan=json.loads((ROOT/'manifests/m3-landmark-final-camera-candidates.json').read_text())
    targets={r['id']:r['target_local_m'] for r in plan['views']}
    terrain=np.load(ROOT/'data/derived/terrain_park.npz')
    def ground(x,y):
        i=int(np.argmin(abs(terrain['x']-x)));j=int(np.argmin(abs(terrain['y']-y)))
        if not terrain['valid'][j,i]: raise RuntimeError('Invalid terrain sample')
        return float(terrain['z'][j,i])
    rows=[]
    def add(fid,suffix,eye,target,purpose):
        rows.append(dict(id=fid+'_'+suffix,feature_id=fid,kind='form-only',requested_camera=camera(eye,target),eye_local_m=eye,target_local_m=target,purpose=purpose,view_scope='Form-only evidence; not route visibility or acceptance',accepted=False))
    add('SP_girl_wetsuit','extra_west_close',[1239.8,5.0,3.2],[1245.8,4.5,2.05],'Show the west side of the seated figure, its legs and fins; the prior east-side view hid the lower body.')
    p=targets['ART_96'];add('ART_96','extra_front_close',[p[0],p[1]-8,p[2]+.5],p,'Show the complete cross and stepped base without the close route crop or the edge-on form view.')
    p=targets['SP_prospect_lookout'];eye=[p[0]-16,p[1]+12,ground(p[0]-16,p[1]+12)+4]
    add('SP_prospect_lookout','extra_upper_context',eye,p,'Show the upper source building and lookout from above the local terrain. The actual route views remain cliff-occluded.')
    p=targets['ART_315'];p=[p[0],p[1],ground(*p[:2])+1];eye=[p[0]+10,p[1]-8,ground(p[0]+10,p[1]-8)+3]
    add('ART_315','extra_terrain_context',eye,p,'Replace the invalid below-terrain form view with an above-terrain search view at the approximate registry point. No linked cairn mesh exists; this view cannot prove its identity or presence.')
    paths=['pipeline/gis/prepare_m3_coastal_extra_views.py','manifests/m3-landmark-final-camera-candidates.json','manifests/route-sculpture-blockouts.json','manifests/critical-features.json','data/derived/terrain_park.npz']
    hashes={p:sha(p) for p in paths}
    for r in rows:r['source_hashes']=hashes
    result=dict(schema_version=1,views=rows,source_hashes=hashes,source_geometry_digest=plan['source_geometry_digest'],accepted=False,application_tests_run=False)
    output=ROOT/'manifests/m3-coastal-extra-camera-candidates.json';output.write_text(json.dumps(result,indent=2));return dict(path=str(output),views=len(rows))
if __name__=='__main__':print(build())
