"""Numerical geometry review. This does not test the running application."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
PACKAGES=['named-feature-blockouts','named-building-blockouts','named-waterfront-blockouts']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    rows=[];failures=[];warnings=[];cuts=[];packages=[]
    for name in PACKAGES:
        source=ROOT/f'manifests/{name}.json';data=json.loads(source.read_text())
        packages.append(dict(path=source.relative_to(ROOT).as_posix(),sha256=sha(source)))
        for feature in data['features']:
            polygon=feature.get('terrain_cut_polygon_local_m')
            if not polygon:continue
            surface='SM_ProspectLookout_TerraceSurvey' if feature['id']=='SP_prospect_lookout' else 'SM_SecondPool_SurfaceReview'
            asset=next(x for x in data['assets'] if x['name']==surface)
            cuts.append(dict(id=feature['id'],name=feature['name'],polygon_local_xy_m=polygon,
                source_manifest=source.relative_to(ROOT).as_posix(),visible_surface_mesh=asset['mesh_path'],visible_surface_sha256=asset['sha256'],
                closure_mesh=feature.get('terrain_closure_mesh',feature.get('containment_mesh')),safety_floor_mesh=feature.get('safety_floor_mesh'),
                operation='Replace terrain inside the polygon; conform the boundary. Do not remove whole coarse terrain triangles by centroid alone.',
                vertical_rule=(dict(kind='surface_tin_minus_offset',offset_m=.12) if feature['id']=='SP_prospect_lookout' else dict(kind='constant',height_m=feature['terrain_cut_target_height_m'])),
                collision_rule=('Replace coarse terrain collision with the terrace TIN and vertical terrain-boundary stitch after boundary and stair review' if feature['id']=='SP_prospect_lookout' else 'Remove coarse terrain collision; retain the synthetic safety floor and basin sides. Water stays non-colliding. Keep closed facility entry outside public navigation; perimeter fence is not yet modeled.'),
                integrated=False,visual_acceptance=False,collision_acceptance=False))
        for asset in data['assets']:
            file=ROOT/asset['mesh_path'];p=np.load(file);v=p['vertices'];f=p['faces']
            n=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
            area=np.linalg.norm(n,axis=1)*.5
            row=dict(name=asset['name'],file=asset['mesh_path'],sha256=sha(file),vertices=len(v),triangles=len(f),
                minimum_triangle_area_m2=float(area.min()),finite=bool(np.isfinite(v).all()),hash_matches=sha(file)==asset['sha256'])
            error=[]
            if not row['finite']:error.append('non-finite vertex')
            if not row['hash_matches']:error.append('hash mismatch')
            if (area<1e-8).any():error.append('degenerate face')
            # Weld for topology only. Authoring vertices remain unchanged.
            _,weld=np.unique(np.round(v,5),axis=0,return_inverse=True);t=weld[f]
            counts=Counter();orientation=Counter()
            for a,b,c in t:
                for u,w in [(int(a),int(b)),(int(b),int(c)),(int(c),int(a))]:
                    key=tuple(sorted((u,w)));counts[key]+=1;orientation[key]+=1 if u<w else -1
            bad_winding=sum(count==2 and orientation[key]!=0 for key,count in counts.items())
            nonmanifold=sum(count>2 for count in counts.values());boundary=sum(count==1 for count in counts.values())
            row.update(inconsistent_shared_edges=bad_winding,nonmanifold_edges=nonmanifold,boundary_edges=boundary)
            if bad_winding:error.append('inconsistent winding on shared edge')
            if nonmanifold:
                if 'WallsReview' in asset['name']:
                    warnings.append(dict(asset=asset['name'],coincident_vertical_wall_junctions=nonmanifold,
                        limitation='Separate facade panels meet at a sampled roof-boundary pinch. Winding is checked below; these are visual massing panels, not watertight collision meshes.'))
                else:error.append('non-manifold welded edge')
            if 'WallsReview' in asset['name']:
                # Every authored quad stores roof A, roof B, lower B, lower A.
                # A->B follows a CCW roof boundary. Exterior is right of A->B.
                quads=v.reshape(-1,4,3);e=quads[:,1]-quads[:,0];expected=np.cross(e,[0.,0.,1.])
                normal=n.reshape(-1,2,3).sum(1);dot=np.sum(normal*expected,axis=1)
                row['outward_wall_quads']=int((dot>0).sum());row['wall_quads']=len(dot)
                if (dot<=0).any():error.append('inward wall normal')
            elif 'RoofSurvey' in asset['name'] or 'TerraceSurvey' in asset['name'] or 'SurfaceReview' in asset['name'] or 'CopingSurvey' in asset['name'] or 'SyntheticSafetyFloor' in asset['name']:
                row['upward_triangles']=int((n[:,2]>0).sum())
                if (n[:,2]<=0).any():error.append('downward surface normal')
            elif 'TerrainBoundaryClosure' in asset['name'] or 'BasinContainmentReview' in asset['name'] or 'RoofStepClosures' in asset['name']:
                row['horizontal_normals']=int((abs(n[:,2])<1e-7).sum())
                if (abs(n[:,2])>=1e-7).any():error.append('non-vertical closure geometry')
            elif boundary==0:
                centred=v-v.mean(0);volume=float(np.sum(np.einsum('ij,ij->i',centred[f[:,0]],np.cross(centred[f[:,1]],centred[f[:,2]])))/6)
                row['signed_volume_m3']=volume
                if volume<=0:error.append('closed mesh has inward orientation')
            elif asset['name']=='SM_NineClockGun_GabledRoof':
                row['upward_sloped_triangles']=int((n[:4,2]>0).sum())
                if (n[:4,2]<=0).any():error.append('downward pitched roof')
            else:error.append('unclassified open surface requires numerical review')
            row['errors']=error;rows.append(row)
            failures.extend(f"{row['name']}: {x}" for x in error)
    payload=dict(schema_version=1,revision='named-m1-r4',scope='Numerical source-mesh review only; no Blender or application operation',
                 packages=packages,assets=rows,asset_count=len(rows),triangles=sum(x['triangles'] for x in rows),failures=failures,topology_warnings=warnings,
                 pass_numerical=not failures,all_meshes_manifold=not warnings,
                 visual_acceptance=False,runtime_acceptance=False)
    (ROOT/'evidence/named-blockout-numerical-review.json').write_text(json.dumps(payload,indent=2)+'\n')
    (ROOT/'manifests/named-feature-terrain-cuts.json').write_text(json.dumps(dict(schema_version=1,coordinates='Local east/north/up metres; CGVD2013; manifests/world-origin.json',cuts=cuts),indent=2)+'\n')
    print(json.dumps(dict(assets=len(rows),triangles=payload['triangles'],failures=failures,packages=packages),indent=2))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
