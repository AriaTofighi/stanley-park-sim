"""Check authored deck against the current exported terrain; no app test."""
import json
import numpy as np
from build_lagoon_structures import ROOT,NATURE_XY,nature_plane
from review_siwash_approach import TerrainQuery
from acquire_sources import save_json,digest

def main():
    terrain=TerrainQuery([350,-931,403,-894]);origin,coeff,_=nature_plane();edges=[]
    for i in [0,1,3]:
        a,b=NATURE_XY[i],NATURE_XY[(i+1)%4];xy=np.linspace(a,b,int(np.ceil(np.linalg.norm(b-a)/.1))+1)
        top=(xy-origin)@coeff[:2]+coeff[2]+.025;ground=np.array([terrain.height(p) for p in xy]);gap=top-ground
        edges.append(dict(edge=i,samples=len(xy),finite=bool(np.isfinite(ground).all()),minimum_gap_m=float(np.nanmin(gap)),maximum_gap_m=float(np.nanmax(gap)),p95_absolute_gap_m=float(np.nanpercentile(abs(gap),95))))
    a,b=NATURE_XY[2],NATURE_XY[3];d=b-a;outward=np.array([d[1],-d[0]])/np.linalg.norm(d);frontage=[]
    from refine_nature_house_terrain import patch_samples
    _,refine=patch_samples();low=refine['lower_front_plane'];lo=np.array(low['origin_local_m']);lc=np.array(low['coefficients'])
    for offset in [.02,.20,.50,1.0]:
        xy=np.linspace(a,b,151)+outward*offset;actual=np.array([terrain.height(p) for p in xy]);expected=(xy-lo)@lc[:2]+lc[2]
        frontage.append(dict(distance_outside_wall_m=offset,minimum_terrain_h_m=float(actual.min()),maximum_terrain_h_m=float(actual.max()),maximum_above_source_plane_m=float((actual-expected).max()),maximum_below_source_plane_m=float((expected-actual).max())))
    # Only rear edge0 is an upper approach; side edges retain the level change.
    threshold=json.loads((ROOT/'manifests/nature-house-threshold.json').read_text());asset=threshold['assets'][0];m=np.load(ROOT/asset['mesh_path']);v=m['vertices'];n=len(v)//4
    outer=v[n:2*n];gap=outer[:,2]-np.array([terrain.height(p) for p in outer[:,:2]])
    joins=dict(samples=n,minimum_outer_step_m=float(gap.min()),maximum_outer_step_m=float(gap.max()),manifest_sha256=digest(ROOT/'manifests/nature-house-threshold.json'))
    result=dict(manifest_sha256=digest(ROOT/'manifests/lagoon-structure-blockouts.json'),terrain_inputs=terrain.inputs,deck_boundary_edges=edges,lower_frontage=frontage,rear_threshold=joins,
                pass_numerical=bool(np.isfinite(gap).all() and abs(gap-.025).max()<1e-6 and max(x['maximum_above_source_plane_m'] for x in frontage)<.12),
                criterion='Rear threshold outer edge is 0.025 m above actual exported terrain. Lower frontage remains within 0.12 m above its measured source plane. Side edges are retaining edges, not access ramps. This does not certify accessibility grades.',live_acceptance=False)
    save_json(ROOT/'evidence/nature-house-terrain-contact-review.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
