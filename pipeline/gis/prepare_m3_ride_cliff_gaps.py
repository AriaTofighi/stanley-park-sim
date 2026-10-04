"""Prepare small separate fills from actual terrain and support boundary vertices."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = 'manifests/m3-ride-cliff-gap-settings.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mesh(name):
    path = ROOT/'data/derived/surface-meshes'/(name+'.npz')
    data = np.load(path)
    return data['vertices'].astype(float)+data['anchor'], data['faces'], path


def boundary_vertices(vertices, faces):
    # Terrain faces have split vertex indices. Weld only for topology lookup,
    # then retain the original unrounded measured coordinate at every vertex.
    _, first, indices = np.unique(np.round(vertices,6),axis=0,return_index=True,return_inverse=True)
    welded_faces = indices[faces]
    edges = np.sort(np.concatenate([welded_faces[:,[0,1]],welded_faces[:,[1,2]],welded_faces[:,[2,0]]]),axis=1)
    unique, counts = np.unique(edges,axis=0,return_counts=True)
    ids = np.unique(unique[counts==1])
    return vertices[first[ids]], first[ids]


def add_prism(vertices, triangles, low_a, low_b, high_a, high_b, normal, depth):
    centre_line = np.array([low_a,low_b,high_b,high_a])
    points = np.concatenate([centre_line-normal*depth/2,centre_line+normal*depth/2])
    centre = points.mean(0)
    offset = len(vertices)
    vertices.extend(points.tolist())
    for corners in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(3,2,6,7),(0,3,7,4),(1,5,6,2)]:
        corners = list(corners)
        n = np.cross(points[corners[1]]-points[corners[0]],points[corners[2]]-points[corners[0]])
        if n@(points[corners].mean(0)-centre)<0:
            corners.reverse()
        triangles.extend([(offset+corners[0],offset+corners[1],offset+corners[2]),(offset+corners[0],offset+corners[2],offset+corners[3])])


def prepare():
    settings = json.loads((ROOT/SETTINGS).read_text())
    paths = [SETTINGS,'pipeline/gis/prepare_m3_ride_cliff_gaps.py','evidence/m3-full-ride-shore-review.json','manifests/m3-ride-cliff-gap-views.json']
    for case in settings['cases']:
        paths.extend(['data/derived/surface-meshes/'+case[key]+'.npz' for key in ['terrain','support']])
    hashes = {p:sha(ROOT/p) for p in paths}
    version = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:12]
    folder = ROOT/'data/derived/m3-ride-cliff-gaps'/version
    if (folder/'source.json').exists():
        raise RuntimeError('Immutable source version already exists')
    assets = []
    overlap = settings['overlap_m']
    for case in settings['cases']:
        tv,tf,_ = load_mesh(case['terrain'])
        sv,sf,_ = load_mesh(case['support'])
        bv,bids = boundary_vertices(tv,tf)
        vertices, triangles, patches = [],[],[]
        for face_pair in case['support_face_pairs']:
            source_corners = sv[sf[face_pair]].reshape(-1,3)
            xy,inv = np.unique(np.round(source_corners[:,:2],6),axis=0,return_inverse=True)
            if len(xy)!=2:
                raise RuntimeError('Expected a vertical source support quad')
            top = np.array([source_corners[inv==j][np.argmax(source_corners[inv==j,2])] for j in range(2)])
            a,b = top
            edge = b[:2]-a[:2]
            length = np.linalg.norm(edge)
            t = ((bv[:,:2]-a[:2])@edge)/(length*length)
            projection = a[:2]+t[:,None]*edge
            xy_error = np.linalg.norm(bv[:,:2]-projection,axis=1)
            good = (t>1e-5)&(t<1-1e-5)&(xy_error<settings['boundary_xy_match_tolerance_m'])
            ids = np.flatnonzero(good)
            ids = ids[np.argsort(t[ids])]
            chain = np.concatenate([[a],bv[ids],[b]])
            parameters = np.r_[0,t[ids],1]
            base = a+(b-a)*parameters[:,None]
            gaps = chain[:,2]-base[:,2]
            if gaps.max()<=.005 or gaps.min()<-.002:
                raise RuntimeError('Selected span does not have the expected positive terrain peak')
            # The exact measured edge coordinates define the unexpanded fill.
            # The 12 mm overlap is buried in existing surfaces at all joins.
            low = base.copy();low[:,2]-=overlap
            high = chain.copy();high[:,2]+=overlap
            tangent = (b-a)/length
            low[0]-=tangent*overlap;high[0]-=tangent*overlap
            low[-1]+=tangent*overlap;high[-1]+=tangent*overlap
            normal = np.array([-edge[1],edge[0],0.])/length
            for i in range(len(chain)-1):
                add_prism(vertices,triangles,low[i],low[i+1],high[i],high[i+1],normal,settings['solid_depth_m'])
            patches.append(dict(support_face_pair=face_pair,source_top_edge=top.tolist(),terrain_boundary_vertex_indices=bids[ids].tolist(),terrain_boundary_points=bv[ids].tolist(),maximum_missing_height_m=float(gaps.max()),maximum_boundary_xy_error_m=float(xy_error[ids].max()),span_length_m=float(length),buried_overlap_m=overlap,solid_depth_m=settings['solid_depth_m'],prisms=len(chain)-1))
        v=np.asarray(vertices)
        assets.append(dict(name='SM_M3RideCliffGap_'+case['id'],section_id=case['section_id'],finding=case['finding'],source_terrain=case['terrain'],source_support=case['support'],local_ride_start_station_m=case['local_ride_start_station_m'],local_ride_requested_range_m=case['local_ride_requested_range_m'],vertices_local_m=vertices,triangles=triangles,patches=patches,bounds_min_local_m=v.min(0).tolist(),bounds_max_local_m=v.max(0).tolist()))
    result=dict(schema_version=1,version=version,input_hashes=hashes,assets=assets,source_geometry_unchanged=True,collision='none',visual_acceptance=False,scope='Separate tiny solid fills between terrain boundary peaks and support top edges. Does not edit any measured surface or its collision.')
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'source.json';path.write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'data/derived/m3-ride-cliff-gaps/latest.json').write_text(json.dumps(dict(source=path.relative_to(ROOT).as_posix(),sha256=sha(path)),indent=2)+'\n')
    return path,result


if __name__=='__main__':
    path,result=prepare()
    print(path)
    for asset in result['assets']:
        print(asset['name'],len(asset['triangles']),[(p['support_face_pair'],p['maximum_missing_height_m']) for p in asset['patches']])
