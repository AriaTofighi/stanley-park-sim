"""Offline source-geometry overlap record; no application is opened."""
from pathlib import Path
import json, hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
source=json.loads((ROOT/'manifests/route-sculpture-blockouts.json').read_text())
rows=[r for r in source['assets'] if r['name'].startswith('SM_Wetsuit_')]
rock=next(r for r in rows if r['name'].endswith('Boulder'));d=np.load(ROOT/rock['mesh_path']);tri=d['vertices'][d['faces']]
def top(xy):
    a=tri[:,0,:2];b=tri[:,1,:2]-a;c=tri[:,2,:2]-a;v=np.asarray(xy)-a
    det=b[:,0]*c[:,1]-b[:,1]*c[:,0];ok=abs(det)>1e-10
    u=np.divide(v[:,0]*c[:,1]-v[:,1]*c[:,0],det,out=np.zeros(len(tri)),where=ok)
    w=np.divide(b[:,0]*v[:,1]-b[:,1]*v[:,0],det,out=np.zeros(len(tri)),where=ok)
    hit=ok&(u>=-1e-7)&(w>=-1e-7)&(u+w<=1+1e-7)
    z=tri[:,0,2]+u*(tri[:,1,2]-tri[:,0,2])+w*(tri[:,2,2]-tri[:,0,2])
    return float(z[hit].max()) if hit.any() else None
out=[]
for r in rows:
    if r==rock:continue
    d=np.load(ROOT/r['mesh_path']);v=d['vertices'];below=[top(p[:2]) is not None and p[2]<top(p[:2])-.005 for p in v]
    centre=(np.asarray(r['bounds_min_m'])+r['bounds_max_m'])/2
    out.append(dict(name=r['name'],vertices=len(v),vertices_below_rock_top=int(sum(below)),fraction_below_rock_top=float(sum(below)/len(v)),centre_local_m=centre.tolist(),rock_top_at_centre_m=top(centre[:2])))
record=dict(scope='Vertical source-surface overlap analysis of the unchanged convex intertidal boulder. Source geometry inspection, not an application test.',source_manifest_sha256=hashlib.sha256((ROOT/'manifests/route-sculpture-blockouts.json').read_bytes()).hexdigest(),boulder_sha256=rock['sha256'],components=out,accepted=False)
(ROOT/'evidence/m3-wetsuit-source-overlap.json').write_text(json.dumps(record,indent=2));print(json.dumps(out,indent=2))
