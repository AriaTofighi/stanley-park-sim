"""Source-based local samples for the cliff beside Prospect lookout.

Root may call refine_samples before the shared terrain Delaunay step. This
module does not write shared terrain or operate Blender/Unreal. The uppermost
supported height group avoids averaging upper and lower cliff returns into a
false mid-air ramp. Exact floor-boundary controls are explicit authored joins,
not independent survey control.
"""
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely import contains_xy

from acquire_sources import digest, save_json
from repair_prospect_terrace import profile

ROOT = Path(__file__).resolve().parents[2]
BOUNDS = [48., 1230., 89., 1265.]
CELL = .4


def patch_samples(root=ROOT):
    source = root/'data/derived/named-prospect-lookout-survey.npz'
    manifest = root/'manifests/named-feature-blockouts.json'
    data = json.loads(manifest.read_text(encoding='utf8'))
    terrace = next(x for x in data['features'] if x['id']=='SP_prospect_lookout')
    polygon = Polygon(terrace['terrain_cut_polygon_local_m'])
    with np.load(source) as p:
        q = p['xyz'].astype(float)
        q = q[p['classification']==2]
    lo,hi=np.array(BOUNDS[:2]),np.array(BOUNDS[2:])
    q=q[np.all(q[:,:2]>=lo,axis=1)&np.all(q[:,:2]<=hi,axis=1)]
    cell=np.floor((q[:,:2]-lo)/CELL).astype(int)
    _,inverse=np.unique(cell,axis=0,return_inverse=True)
    order=np.argsort(inverse,kind='stable')
    groups=np.split(order,np.flatnonzero(np.diff(inverse[order]))+1)
    samples=[];multilevel=0;unsupported=0
    for ids in groups:
        points=q[ids];points=points[np.argsort(points[:,2])]
        parts=np.split(points,np.flatnonzero(np.diff(points[:,2])>1.)+1)
        supported=[p for p in parts if len(p)>=2]
        if len(parts)>1:multilevel+=1
        if supported:points=supported[-1]
        else:unsupported+=1;points=max(parts,key=len)
        samples.append(np.median(points,axis=0))
    samples=np.asarray(samples)
    # The replacement terrace occupies this footprint. Its controls only define
    # the seam; they do not alter terrain beyond the local patch.
    samples=samples[~contains_xy(polygon.buffer(.12),samples[:,0],samples[:,1])]
    t=np.array(terrace['stable_floor_review']['parameters'])
    breaks=[t[0],t[0]+t[1],t[2],t[2]+t[3]]
    boundary=[]
    points=np.array(polygon.exterior.coords)
    for a,b in zip(points[:-1],points[1:]):
        fractions=list(np.linspace(0,1,max(2,int(np.ceil(np.linalg.norm(b-a)/.2))+1)))
        ds=(b-a).sum()
        if abs(ds)>1e-10:
            fractions.extend((cut-a.sum())/ds for cut in breaks if 0<(cut-a.sum())/ds<1)
        xy=a+np.array(sorted(set(fractions)))[:,None]*(b-a)
        boundary.extend(np.column_stack((xy,profile(t,xy)+.025)))
    boundary=np.unique(np.round(boundary,9),axis=0)
    result=np.vstack((samples,boundary))
    review=dict(source=dict(path=source.relative_to(root).as_posix(),sha256=digest(source)),
        floor=dict(path='data/derived/named-features/SM_ProspectLookout_TerraceSurvey.npz',
                   sha256=digest(root/'data/derived/named-features/SM_ProspectLookout_TerraceSurvey.npz')),
        bounds_local_xy_m=BOUNDS,cell_m=CELL,raw_ground_returns=len(q),source_samples=len(samples),
        multilevel_cells=multilevel,single_return_cells=unsupported,boundary_controls=len(boundary),
        method='Median of highest height group with at least two returns per 0.4 m cell; retain densest group if no group has two returns. Groups split at 1 m height gaps. Explicit terrace boundary controls at 0.2 m spacing and every fitted profile break.',
        limitations='A 2.5D cliff envelope cannot represent overhangs. Boundary controls join the stable M1 floor and are not independent measured control. No application acceptance.',
        numerical_acceptance=False,live_acceptance=False)
    return result,review


def refine_samples(root,xyz,inside):
    """Replace only local coarse samples; return arrays and provenance record."""
    extra,review=patch_samples(root)
    xmin,ymin,xmax,ymax=BOUNDS
    selected=(xyz[:,0]>=xmin)&(xyz[:,0]<=xmax)&(xyz[:,1]>=ymin)&(xyz[:,1]<=ymax)
    review['replaced_coarse_samples']=int(selected.sum())
    return np.vstack((xyz[~selected],extra)),np.r_[inside[~selected],np.ones(len(extra),dtype=bool)],review


if __name__=='__main__':
    samples,review=patch_samples()
    path=ROOT/'data/derived/prospect-terrain-refinement-samples.npz'
    np.savez_compressed(path,xyz=samples)
    review['output']=dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path))
    save_json(ROOT/'manifests/prospect-terrain-refinement.json',review)
    print(json.dumps(review,indent=2))
