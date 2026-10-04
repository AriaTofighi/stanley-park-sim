"""Local two-level Nature House approach controls; root integrates this hook.

No shared terrain files or app state are changed here. The closed building
encloses the 2.5D join between the measured upper deck and lower front walk.
"""
import numpy as np
from shapely.geometry import Polygon,LineString,Point
from shapely import contains_xy
from build_lagoon_structures import ROOT,NATURE_XY,nature_data,nature_plane
from acquire_sources import save_json,digest

BOUNDS=[351.,-930.,402.,-895.]
CELL=.35

def patch_samples(root=ROOT):
    q,c=nature_data();lo,hi=np.array(BOUNDS[:2]),np.array(BOUNDS[2:]);q=q[(c==2)&np.all(q[:,:2]>=lo,axis=1)&np.all(q[:,:2]<=hi,axis=1)]
    poly=Polygon(NATURE_XY);q=q[~contains_xy(poly.buffer(.12),q[:,0],q[:,1])]
    cell=np.floor((q[:,:2]-lo)/CELL).astype(int);_,inverse=np.unique(cell,axis=0,return_inverse=True);order=np.argsort(inverse,kind='stable')
    groups=np.split(order,np.flatnonzero(np.diff(inverse[order]))+1);samples=np.array([np.median(q[ids],axis=0) for ids in groups])
    origin,coeff,_=nature_plane();controls=[]
    front_a,front_b=NATURE_XY[2],NATURE_XY[3];front=LineString([front_a,front_b]);direction=front_b-front_a
    outward=np.array([direction[1],-direction[0]])/np.linalg.norm(direction)
    # Ground source samples immediately in front of the wall define the lower
    # public level. Do not interpolate upper-deck samples into that frontage.
    frontage=front.buffer(1.25,cap_style=2);lower=q[contains_xy(frontage,q[:,0],q[:,1])&(q[:,2]<2.5)]
    lower_origin=(front_a+front_b)/2;A=np.column_stack((lower[:,:2]-lower_origin,np.ones(len(lower))))
    low_coeff=np.linalg.lstsq(A,lower[:,2],rcond=None)[0]
    # Classified samples close to this vertical wall also include masonry
    # returns up to 2.4 m. Retaining these among lower controls makes local
    # spikes; replace this narrow frontage by the supported ground plane.
    on_front=contains_xy(front.buffer(.66,cap_style=2),samples[:,0],samples[:,1])
    replaced_front_samples=int(on_front.sum());samples=samples[~on_front]
    # Only the three land-facing boundaries receive upper-deck controls. The
    # north-facing facade ends at the separate lower walk and is not a ramp.
    for i in [0,1,3]:
        a,b=NATURE_XY[i],NATURE_XY[(i+1)%4];xy=np.linspace(a,b,int(np.ceil(np.linalg.norm(b-a)/.2))+1)
        distance=np.array([front.distance(Point(p)) for p in xy]);xy=xy[distance>.50]
        h=(xy-origin)@coeff[:2]+coeff[2];controls.extend(np.column_stack((xy,h)))
    # Retain a dense lower strip on both sides of the actual facade boundary.
    # The vertical change remains behind the closed wall and slab.
    front_xy=np.linspace(front_a,front_b,int(np.ceil(front.length/.12))+1)
    for offset in [-.22,0,.22,.44,.66]:
        xy=front_xy+outward*offset;h=(xy-lower_origin)@low_coeff[:2]+low_coeff[2];controls.extend(np.column_stack((xy,h)))
    # Interior samples lie just below the authored slab, enclosed by the mass.
    x,y=np.meshgrid(np.arange(lo[0],hi[0],CELL),np.arange(lo[1],hi[1],CELL));xy=np.column_stack((x.ravel(),y.ravel()));xy=xy[contains_xy(poly,xy[:,0],xy[:,1])]
    distance=np.array([front.distance(Point(p)) for p in xy]);blend=np.clip((distance-.35)/.55,0,1)
    low=(xy-lower_origin)@low_coeff[:2]+low_coeff[2];high=(xy-origin)@coeff[:2]+coeff[2]-.10
    interior=np.column_stack((xy,low+(high-low)*blend))
    result=np.vstack((samples,controls,interior))
    report=dict(bounds_local_xy_m=BOUNDS,cell_m=CELL,raw_ground_returns=len(q),source_samples=len(samples),deck_boundary_controls=len(controls),enclosed_interior_controls=len(interior),
        lower_front_plane=dict(origin_local_m=lower_origin.tolist(),coefficients=low_coeff.tolist(),source_returns=len(lower),median_residual_m=float(np.median(abs(A@low_coeff-lower[:,2])))),
        replaced_wall_adjacent_ground_cells=replaced_front_samples,
        method='0.35 m classified-ground median cells outside measured deck. Upper boundary controls stop 0.50 m before the lower front. Five dense lines at the front replace wall-adjacent classified outliers with a source-fitted lower-ground plane. The high-to-low interior join remains behind the closed wall, at least 0.35 m inside its front.',
        sources=[dict(path=f'data/derived/named-{x}-survey.npz',sha256=digest(root/f'data/derived/named-{x}-survey.npz')) for x in ['nature-house-west','nature-house-east']],
        scope='Local approach refinement only. No lake/water level change, no terrain cut and no interior access.',numerical_acceptance=False,live_acceptance=False)
    return result,report

def refine_samples(root,xyz,inside):
    extra,review=patch_samples(root);lo,hi=np.array(BOUNDS[:2]),np.array(BOUNDS[2:]);mask=np.all(xyz[:,:2]>=lo,axis=1)&np.all(xyz[:,:2]<=hi,axis=1)
    review['replaced_coarse_samples']=int(mask.sum());return np.vstack((xyz[~mask],extra)),np.r_[inside[~mask],np.ones(len(extra),bool)],review

if __name__=='__main__':
    s,r=patch_samples();p=ROOT/'data/derived/nature-house-refinement-samples.npz';np.savez_compressed(p,xyz=s);r['output']=dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p));save_json(ROOT/'manifests/nature-house-terrain-refinement.json',r);print(r)
