"""Replace the raw terrace TIN with a robust measured three-level profile.

Two stair flights use continuous contact ramps in M1. This avoids claiming
surveyed tread dimensions from sparse/misclassified returns.
"""
import json
import numpy as np
from scipy.optimize import least_squares
import shapely
from shapely.geometry import Polygon
from shapely import contains_xy
import build_named_feature_blockouts as geom
from acquire_sources import save_json

ROOT=geom.ROOT

def profile(t,xy):
    s=np.asarray(xy).sum(axis=-1);a,w,b,v,h,m,l=t
    return h-(h-m)*np.clip((s-a)/w,0,1)-(m-l)*np.clip((s-b)/v,0,1)

def main():
    path=ROOT/'manifests/named-feature-blockouts.json';d=json.loads(path.read_text());feature=next(x for x in d['features'] if x['id']=='SP_prospect_lookout')
    xy=np.array(feature['terrain_cut_polygon_local_m']);poly=Polygon(xy);q,c=geom.survey('prospect-lookout');q=q[(c==2)&contains_xy(poly.buffer(-.15),q[:,0],q[:,1])]
    initial=[1311.5,1.5,1317.5,2,57.95,57.35,56.23]
    fit=least_squares(lambda t:profile(t,q[:,:2])-q[:,2],initial,
        bounds=([1310,.3,1316.5,.3,57.75,57.15,56.05],[1313,3,1320,3,58.1,57.55,56.4]),loss='soft_l1',f_scale=.06)
    t=fit.x;cuts=[-10000,t[0],t[0]+t[1],t[2],t[2]+t[3],10000]
    vertices=[];faces=[];parts=[]
    # (s=x+y, r=x-y) defines exact strips through both fitted stair flights.
    for low,high in zip(cuts[:-1],cuts[1:]):
        sr=np.array([[low,-2000],[high,-2000],[high,2000],[low,2000]],float)
        window=np.column_stack(((sr[:,0]+sr[:,1])/2,(sr[:,0]-sr[:,1])/2));region=poly.intersection(Polygon(window))
        for part in shapely.get_parts(region):
            if not isinstance(part,Polygon) or part.area<1e-8:continue
            parts.append(part)
            for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(part)):
                a=np.array(tri.exterior.coords)[:3];u,v=a[1]-a[0],a[2]-a[0]
                if u[0]*v[1]-u[1]*v[0]<0:a=a[::-1]
                n=len(vertices);vertices.extend(np.column_stack((a,profile(t,a)+.025)));faces.append((n,n+1,n+2))
    vertices=np.array(vertices);faces=np.array(faces);_,first,inv=np.unique(np.round(vertices,7),axis=0,return_index=True,return_inverse=True);vertices=vertices[first];faces=inv[faces]
    geom.mesh('SM_ProspectLookout_TerraceSurvey',vertices,faces,'concrete','SP_prospect_lookout',collision='complex')
    replacements=[geom.ASSETS[-1]]
    z=profile(t,xy)+.025
    for i in range(3,len(xy)-12):
        geom.beam(f'SM_ProspectLookout_Parapet_{i:02d}',[*xy[i],z[i]+.8],[*xy[i+1],z[i+1]+.8],.20,'stone','SP_prospect_lookout')
        geom.ASSETS[-1]['collision']='complex';replacements.append(geom.ASSETS[-1])
    names={x['name'] for x in replacements};d['assets']=[a for a in d['assets'] if a['name'] not in names]+replacements
    union=shapely.unary_union(parts);res=profile(t,q[:,:2])-q[:,2]
    review=dict(method='Robust low-return three-level profile with two M1 contact ramps; no per-vertex nearest-neighbour height noise',
        parameters=t.tolist(),axis='s=local East+local North',level_heights_m=t[4:].tolist(),source_returns=len(q),
        median_abs_residual_m=float(np.median(abs(res))),p95_abs_residual_m=float(np.percentile(abs(res),95)),
        footprint_area_m2=poly.area,mesh_coverage_area_m2=union.area,uncovered_area_m2=poly.difference(union).area,
        excess_area_m2=union.difference(poly).area,triangles=len(faces),maximum_ramp_grade=float(max((t[4]-t[5])*2**.5/t[1],(t[5]-t[6])*2**.5/t[3])),
        independent_accuracy=False,stair_treads='Exact tread count/depth not resolved. M1 uses source-fitted flight envelopes as continuous contact ramps.',
        terrain_seam_acceptance=False)
    feature['stable_floor_review']=review;feature['limits']='Three measured height modes and fitted flight envelopes replace noisy raw ground triangulation. Exact stair treads, parapet sections and rails remain unfinished. Terrain boundary closure and live contact require repeat checks.'
    feature['measured']['surface_height_range_m']=[float(vertices[:,2].min()),float(vertices[:,2].max())]
    save_json(path,d);save_json(ROOT/'evidence/prospect-terrace-floor-repair.json',review)
    print(json.dumps(review,indent=2))

if __name__=='__main__':main()
