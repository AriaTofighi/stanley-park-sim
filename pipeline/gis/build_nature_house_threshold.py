"""Close the rear deck-to-upper-ground seam using actual terrain planes."""
import json
import numpy as np
from shapely.geometry import LineString
import build_named_feature_blockouts as g
from build_lagoon_structures import NATURE_XY,nature_plane
from review_siwash_approach import TerrainQuery
from acquire_sources import save_json,digest

def main():
    g.OUT=g.ROOT/'data/derived/nature-house-threshold';g.OUT.mkdir(exist_ok=True);g.ASSETS.clear();g.FEATURES.clear()
    terrain=TerrainQuery([350,-931,403,-894]);origin,coeff,_=nature_plane();a,b=NATURE_XY[:2];d=b-a;length=np.linalg.norm(d);out=np.array([d[1],-d[0]])/length*.22
    line=LineString([a+out,b+out]);ts=list(np.linspace(0,1,int(np.ceil(length/.10))+1))
    for poly in terrain.polygons:
        cut=line.intersection(poly)
        if cut.is_empty:continue
        geoms=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
        for shape in geoms:
            if hasattr(shape,'coords'):
                for p in shape.coords:ts.append(float(np.dot(np.array(p)-a-out,d)/length**2))
    ts=np.unique(np.round(ts,9));inner=a+ts[:,None]*d;outer=inner+out;n=len(ts)
    hi=(inner-origin)@coeff[:2]+coeff[2]+.025;ho=np.array([terrain.height(p) for p in outer])+.025
    if not np.isfinite(ho).all():raise ValueError('Missing retained terrain at threshold')
    low=np.minimum(hi,ho)-.26
    v=np.vstack((np.column_stack((inner,hi)),np.column_stack((outer,ho)),np.column_stack((inner,low)),np.column_stack((outer,low))))
    f=[]
    for i in range(n-1):
        j=i+1;f.extend([[i,n+i,n+j,j],[2*n+j,3*n+j,3*n+i,2*n+i],[i,j,2*n+j,2*n+i],[n+j,n+i,3*n+i,3*n+j]])
    f.extend([[0,2*n,3*n,n],[n-1,2*n-1,4*n-1,3*n-1]])
    g.mesh('SM_NatureHouse_RearDeckThreshold',v,f,'concrete','SP_nature_house',collision='complex')
    g.ASSETS[-1]['collision_reason']='Closed 0.22 m rear threshold; top meets measured deck and actual exported upper-ground triangle planes plus 0.025 m. No side ramp or lower-level access claim.'
    g.feature('SP_nature_house','Nature House upper rear deck threshold',['manifests/lagoon-structure-blockouts.json','manifests/nature-house-terrain-refinement.json'],
        dict(centre_local_m=((a+b)/2).tolist(),terrain_inputs=terrain.inputs,sampled_stations=n,maximum_crossfall_height_m=float(abs(hi-ho).max())),
        dict(threshold_width_m=.22,closure_depth_m=.26,method='Bounded M1 seam closure. Long rear upper-ground edge only; outer samples include terrain-triangle intersections. Geometry is a contact repair, not a survey of a separate real curb.'),
        'The front and side retaining edges remain part of the closed building. Detailed edge railing and exact accessibility grades need live/source review. This threshold does not create a ramp down the western side.')
    result=dict(schema_version=1,revision='nature-house-threshold-r1',assets=g.ASSETS,features=g.FEATURES,acceptance=False,reference_rights='City survey derivative OGL-Vancouver',terrain_inputs=terrain.inputs)
    save_json(g.ROOT/'manifests/nature-house-threshold.json',result);print(digest(g.ROOT/'manifests/nature-house-threshold.json'))

if __name__=='__main__':main()
