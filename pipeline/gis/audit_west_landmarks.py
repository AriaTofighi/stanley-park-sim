"""Numerical review of the separate west landmark package; no app testing."""
import json
from collections import Counter
import numpy as np
from shapely.geometry import LineString,Polygon
import shapely
from acquire_sources import digest,save_json
from build_west_landmark_blockouts import ROOT


def main(package='west-landmark-blockouts',evidence='west-landmark-numerical-review.json'):
    path=ROOT/f'manifests/{package}.json';d=json.loads(path.read_text());rows=[];failures=[]
    runtime=json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text());cycle=LineString(np.array(runtime['points_local_m'])[:,:2]).buffer(runtime['development_width_m']/2)
    ped=json.loads((ROOT/'data/routes/derived/pedestrian-network.json').read_text());paths=shapely.unary_union([LineString(e['coordinates_local_xy_m']).buffer(e['width_m']/2) for e in ped['edges'] if e['render_candidate']])
    for a in d['assets']:
        p=np.load(ROOT/a['mesh_path']);v=p['vertices'];f=p['faces'];normal=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);area=np.linalg.norm(normal,axis=1)/2
        _,weld=np.unique(np.round(v,7),axis=0,return_inverse=True);counts=Counter();orientation=Counter()
        for tri in weld[f]:
            for x,y in zip(tri,np.roll(tri,-1)):
                key=tuple(sorted((int(x),int(y))));counts[key]+=1;orientation[key]+=1 if x<y else -1
        boundary=sum(n==1 for n in counts.values());winding=sum(n==2 and orientation[k]!=0 for k,n in counts.items());nonmanifold=sum(n>2 for n in counts.values())
        errors=[]
        if not np.isfinite(v).all():errors.append('Non-finite coordinates')
        if area.min()<1e-8:errors.append('Degenerate triangles')
        if digest(ROOT/a['mesh_path'])!=a['sha256']:errors.append('Hash mismatch')
        if winding:errors.append('Inconsistent winding')
        warnings=[]
        if nonmanifold:
            if a.get('expected_coincident_facade_edges')==nonmanifold and a['collision']=='none' and 'WallsReview' in a['name']:
                warnings.append(a['contact_topology_limit'])
            else:errors.append('Non-manifold welded edge')
        row=dict(name=a['name'],sha256=a['sha256'],triangles=len(f),minimum_area_m2=float(area.min()),boundary_edges=boundary,nonmanifold_edges=nonmanifold,inconsistent_shared_edges=winding)
        if boundary==0:
            centred=v-v.mean(0);vol=float(np.einsum('ij,ij->i',centred[f[:,0]],np.cross(centred[f[:,1]],centred[f[:,2]])).sum()/6);row['signed_volume_m3']=vol
            if vol<=0:errors.append('Inward closed mesh')
        elif 'RoofSurvey' in a['name']:
            if (normal[:,2]<=0).any():errors.append('Downward roof')
        elif 'WallsReview' in a['name']:
            panels=v.reshape(-1,4,3);expected=np.cross(panels[:,1]-panels[:,0],[0,0,1]);actual=normal.reshape(-1,2,3).sum(1)
            if (np.sum(expected*actual,axis=1)<=0).any():errors.append('Inward facade')
            row['pedestrian_corridor_intersections']=sum(LineString(x[:2,:2]).intersects(paths) for x in panels)
            row['cycle_corridor_intersections']=sum(LineString(x[:2,:2]).intersects(cycle) for x in panels)
            if a['collision']!='none' and (row['pedestrian_corridor_intersections'] or row['cycle_corridor_intersections']):errors.append('Inferred facade intersects a public corridor')
        elif 'RoofStepClosures' in a['name']:
            if (abs(normal[:,2])>1e-7).any():errors.append('Non-vertical roof closure')
        else:errors.append('Unknown open surface')
        row['errors']=errors;row['warnings']=warnings;rows.append(row);failures.extend(a['name']+': '+e for e in errors)
    output=dict(revision='west-m1-r1',manifest_sha256=digest(path),assets=rows,asset_count=len(rows),triangles=sum(x['triangles'] for x in rows),failures=failures,pass_numerical=not failures,live_acceptance=False,absolute_accuracy_accepted=False)
    save_json(ROOT/'evidence'/evidence,output)
    print(json.dumps(dict(assets=len(rows),triangles=output['triangles'],failures=failures,manifest_sha256=digest(path)),indent=2))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
