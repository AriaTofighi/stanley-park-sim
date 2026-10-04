"""Separate engineered ride surface and a clipped terrain opening.

The measured-fit proposal is not upgraded to survey acceptance by meshing it.
"""
import json
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString
from scipy.signal import savgol_filter
from scipy.interpolate import CubicHermiteSpline
from acquire_sources import save_json,digest
from refine_pavement_alignment import refine_pavement_alignment

ROOT=Path(__file__).resolve().parents[2]


def support_suppression_windows():
    """Use source chainage from the authored underpass cavities, never runtime distance."""
    path=ROOT/'data/derived/underpass-blockouts.json'
    if not path.exists():
        return [],None
    record=json.loads(path.read_text(encoding='utf8'))
    windows=[]
    for site in record['sites']:
        start,end=map(float,site['support_removal_source_m'])
        if not np.isfinite([start,end]).all() or end<=start:
            raise ValueError(f"Invalid underpass support removal interval: {site['id']}")
        windows.append(dict(site=site['id'],start_m=start,end_m=end))
    windows.sort(key=lambda item:item['start_m'])
    for previous,current in zip(windows,windows[1:]):
        if current['start_m']<previous['end_m']:
            raise ValueError('Overlapping support suppression windows need an explicit union')
    return windows,dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path))


def retained_support_parts(start,end,windows):
    """Return exact retained subintervals, splitting a segment at cavity boundaries."""
    if end<=start:
        raise ValueError('Support source chainage must increase, including the closing overlap')
    parts=[(float(start),float(end))]
    for window in windows:
        lo,hi=window['start_m'],window['end_m']
        kept=[]
        for a,b in parts:
            if hi<=a or lo>=b:
                kept.append((a,b))
            else:
                if a<lo:kept.append((a,lo))
                if hi<b:kept.append((hi,b))
        parts=kept
    return parts


def support_suppression_counts(stations,parts,indices):
    """Count route segments once; mesh triangle counts include both support sides."""
    indices=list(indices)
    full=sum(not parts[i] for i in indices)
    split=sum(bool(parts[i]) and parts[i]!=[(float(stations[i]),float(stations[i+1]))] for i in indices)
    removed=sum(float(stations[i+1]-stations[i])-sum(b-a for a,b in parts[i]) for i in indices)
    replacement=sum(len(parts[i])*4 for i in indices
                    if parts[i] and parts[i]!=[(float(stations[i]),float(stations[i+1]))])
    return dict(source_segments=len(indices),fully_suppressed_segments=full,boundary_split_segments=split,
        source_length_suppressed_m=removed,fully_suppressed_input_triangles=full*4,
        boundary_input_triangles_replaced=split*4,boundary_replacement_triangles=replacement)

def load_profile():
    with np.load(ROOT/'data/derived/paved-circuit-proposal.npz') as source:
        package={name:source[name].copy() for name in source.files}
    points=package['xyz'].copy()
    # Smooth the noisy automatic lateral choice on a physical riding scale.
    # Save displacement; this is development authoring, not survey correction.
    raw_xy=points[:,:2].copy()
    for axis in (0,1):points[:,axis]=savgol_filter(points[:,axis],21,2,mode='wrap')
    # At this sharp corner in the approximate City line, its lateral normals
    # fold across one another. The aerial reference shows a continuous, shallow
    # seawall curve. Join the measured-fit endpoints with their local tangents.
    # This authored repair remains separate from immutable source geometry.
    s=package['chainage_source'];a,b=np.searchsorted(s,[3275.,3345.])
    derivatives=np.stack(((points[a+2,:2]-points[a-2,:2])/(s[a+2]-s[a-2]),
                          (points[b+2,:2]-points[b-2,:2])/(s[b+2]-s[b-2])))
    spline=CubicHermiteSpline([s[a],s[b]],points[[a,b],:2],derivatives)
    points[a:b+1,:2]=spline(s[a:b+1])
    points[-1]=points[0]
    points,package['crossfall'],package['width_m'],review=refine_pavement_alignment(
        points,package['chainage_source'],package['crossfall'],package['width_m'],
        project_root=ROOT)
    package['alignment_review']=review
    tangent=np.gradient(points[:,:2],axis=0)
    tangent[0]=tangent[-1]=points[1,:2]-points[-2,:2]
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    normal=np.column_stack((-tangent[:,1],tangent[:,0]))
    return package,points,normal,np.linalg.norm(points[:,:2]-raw_xy,axis=1)

def terrain_opening(xyz,faces,colors,tin,source_indices,points,normal,width):
    # Use the actual ruled mesh boundary so path and opening have no seams.
    left=points[:,:2]+normal*width[:,None]*.5
    right=points[:,:2]-normal*width[:,None]*.5
    strips=[Polygon([right[i],right[i+1],left[i+1],left[i]]) for i in range(len(points)-1)]
    strips=np.asarray(shapely.make_valid(strips),dtype=object)
    footprint=shapely.union_all(strips)
    strip_tree=shapely.STRtree(strips)
    triangles=shapely.polygons(xyz[faces,:2])
    tree=shapely.STRtree(triangles)
    hits=tree.query(footprint,predicate='intersects')
    keep=np.ones(len(faces),bool);keep[hits]=False
    extra_vertices=[];extra_faces=[];extra_colors=[]
    for face_index in hits:
        triangle=triangles[face_index]
        local=strip_tree.query(triangle,predicate='intersects')
        piece=shapely.difference(triangle,shapely.union_all(strips[local]))
        if piece.is_empty:continue
        simplex=source_indices[face_index]
        for fragment in shapely.get_parts(piece):
            if not isinstance(fragment,Polygon) or fragment.area<1e-8:continue
            for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(fragment)):
                xy=np.asarray(tri.exterior.coords)[:3,:2]
                a,b=xy[1]-xy[0],xy[2]-xy[0]
                signed=a[0]*b[1]-a[1]*b[0]
                if abs(signed)<1e-8:continue
                if signed<0:xy=xy[::-1]
                w2=(tin.transform[simplex,:2]@(xy-tin.transform[simplex,2]).T).T
                weights=np.column_stack((w2,1-w2.sum(axis=1)))
                height=weights@xyz[tin.simplices[simplex],2]
                start=len(xyz)+len(extra_vertices)
                extra_faces.append([start,start+1,start+2])
                extra_vertices.extend(np.column_stack((xy,height)))
                extra_colors.extend(weights@colors[tin.simplices[simplex]])
    print('Cut terrain triangles',len(hits),'replacement',len(extra_faces),flush=True)
    return np.vstack((xyz,extra_vertices)),np.vstack((faces[keep],extra_faces)).astype(np.int32),np.vstack((colors,extra_colors))

def build_pavement(points,normal,package,displacement,surface_z,out,terrain_contact=None):
    edges=[]
    fall=package['crossfall']
    for side in (-1,1):
        half=package['width_m']*.5
        edge=points.copy();edge[:,:2]+=normal*(side*half[:,None])
        edge[:,2]+=fall*side*half
        edges.append(edge)
    # Close end cross-sections exactly, including crossfall.
    for edge in edges:edge[-1]=edge[0]
    # One shared station overlaps adjacent chunks. This keeps Chaos queries
    # continuous when centimetre float conversion rounds separate pivots at a seam.
    edges=[np.vstack((edge,edge[1])) for edge in edges]
    # Export chunks overlap by one segment. Their support decisions must use
    # the same global source interval so neither copy leaves an invisible wall.
    source_s=np.asarray(package['chainage_source'],dtype=float)
    extended_s=np.r_[source_s,source_s[-1]+source_s[1]-source_s[0]]
    windows,suppression_source=support_suppression_windows()
    support_parts=[retained_support_parts(a,b,windows) for a,b in zip(extended_s,extended_s[1:])]
    # The final exported segment repeats route segment zero after one full lap.
    # Apply its original decision in the shifted interval, including a future
    # suppression window at the route origin.
    source_period=source_s[-1]-source_s[0]
    support_parts[-1]=[(a+source_period,b+source_period) for a,b in support_parts[0]]
    suppression_chunks=[]
    records=[]
    for start in range(0,len(points)-1,192):
        end=min(start+193,len(points))
        anchor=np.r_[np.floor(points[start,:2]/10)*10,0.]
        right,left=(e[start:end+1] for e in edges)
        vertices=np.stack((right,left),axis=1).reshape(-1,3)
        faces=[]
        for i in range(end-start):
            a=2*i;faces.extend([[a,a+2,a+1],[a+1,a+2,a+3]])
        name=f'SM_Pavement_{start//192:03d}'
        path=out/f'{name}.npz'
        np.savez_compressed(path,vertices=vertices-anchor,faces=np.asarray(faces),anchor=anchor)
        records.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=digest(path),
            collision='complex',source_start_m=float(package['chainage_source'][start]),source_end_m=float(package['chainage_source'][min(end,len(points)-1)]),
            overlap_stations=1,
            vertices=len(vertices),triangles=len(faces),role='pavement'))
        # Vertical skirts join measured terrain at the cut edge. Their geometry
        # is a development support closure, not a surveyed retaining wall.
        skirt_vertices=[];skirt_faces=[]
        for edge_index,edge in enumerate((right,left)):
            bottom=edge.copy();bottom[:,2]=surface_z(edge)-.02
            skirt=np.stack((edge,bottom),axis=1).reshape(-1,3)
            offset=len(skirt_vertices);skirt_vertices.extend(skirt)
            for i in range(end-start):
                global_index=start+i
                s0,s1=extended_s[global_index:global_index+2]
                for kept_start,kept_end in support_parts[global_index]:
                    if terrain_contact is not None:
                        alpha,beta=(kept_start-s0)/(s1-s0),(kept_end-s0)/(s1-s0)
                        a0=edge[i]+alpha*(edge[i+1]-edge[i])
                        b0=edge[i]+beta*(edge[i+1]-edge[i])
                        top,ground=terrain_contact.section(a0,b0)
                        for j in range(len(top)-1):
                            quad=np.stack((top[j],ground[j],top[j+1],ground[j+1]))
                            for indices in ([0,1,2],[1,3,2]):
                                tri=quad[indices]
                                if np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))<1e-9:continue
                                # The left edge has the opposite solid side.
                                # Above-road banks face into the riding bay;
                                # below-road fill faces out toward the terrain.
                                if edge_index==1:tri=tri[::-1]
                                a=len(skirt_vertices);skirt_vertices.extend(tri)
                                skirt_faces.append([a,a+1,a+2])
                        continue
                    if kept_start==s0 and kept_end==s1:
                        a=offset+i*2;skirt_faces.extend([[a,a+1,a+2],[a+1,a+3,a+2]])
                        continue
                    # Preserve the original ruled vertical surface on the kept
                    # side of a partial segment. No midpoint or whole-chunk mask.
                    alpha,beta=(kept_start-s0)/(s1-s0),(kept_end-s0)/(s1-s0)
                    a=len(skirt_vertices)
                    for fraction in (alpha,beta):
                        skirt_vertices.extend((edge[i]+fraction*(edge[i+1]-edge[i]),
                                               bottom[i]+fraction*(bottom[i+1]-bottom[i])))
                    skirt_faces.extend([[a,a+1,a+2],[a+1,a+3,a+2]])
        suppression=support_suppression_counts(extended_s,support_parts,range(start,end))
        suppression_chunks.append(dict(chunk=start//192,**suppression))
        if not skirt_faces:
            # An empty cavity chunk has no collision object. Other chunks retain
            # their original names and mesh records.
            continue
        skirt_faces=np.asarray(skirt_faces,dtype=np.int32)
        used,remapped=np.unique(skirt_faces,return_inverse=True)
        skirt_vertices=np.asarray(skirt_vertices)[used]
        skirt_faces=remapped.reshape(-1,3).astype(np.int32)
        name=f'SM_PavementSupport_{start//192:03d}'
        path=out/f'{name}.npz'
        np.savez_compressed(path,vertices=skirt_vertices-anchor,faces=skirt_faces,anchor=anchor)
        records.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=digest(path),collision='complex',role='support',
            vertices=len(skirt_vertices),triangles=len(skirt_faces),support_suppression=suppression,
            suppression_manifest=suppression_source))
    save_json(ROOT/'data/derived/pavement-support-suppression.json',dict(
        schema_version=1,chainage_reference='chainage_source; never chainage_runtime',windows=windows,
        source_manifest=suppression_source,
        unique_route_segments=support_suppression_counts(extended_s,support_parts,range(len(points)-1)),
        exported_chunks=suppression_chunks,
        note='Chunk counts include their shared overlap segments. The unique-route counts exclude duplicate chunk overlaps and the closing repeat of segment zero. Boundary segments are split at exact source chainages.'))
    length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    save_json(ROOT/'data/derived/paved-circuit-runtime.json',dict(points_local_m=points.tolist(),
        chainage_source_m=package['chainage_source'].tolist(),chainage_runtime_m=length.tolist(),
        width_m=package['width_m'].tolist(),crossfall=package['crossfall'].tolist(),
        fit_sha256=digest(ROOT/'data/derived/paved-circuit-proposal.npz'),
        alignment_review=package.get('alignment_review'),
        release_accepted=False,development_width_m=3.,
        lateral_smoothing_displacement_p99_m=float(np.percentile(displacement,99)),
        lateral_smoothing_displacement_max_m=float(displacement.max()),
        note='Source accuracy and widths remain open. Smoothing displacement must be checked against pavement boundaries.'))
    return records
