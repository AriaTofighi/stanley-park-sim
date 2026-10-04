"""Robust large roof-plane reconstruction for M1 architectural massing.

Fits measured height levels independently. Small equipment and scan edge
returns attach to the nearest supported plane rather than becoming spikes.
"""
import numpy as np
from scipy.ndimage import label
from scipy.spatial import cKDTree

def fit_major_planes(vertices,seed=731,min_support=70,max_planes=18):
    q=np.asarray(vertices,float);origin=q[:,:2].mean(0);xy=q[:,:2]-origin
    remaining=np.ones(len(q),bool);labels=np.full(len(q),-1,int);planes=[];rng=np.random.default_rng(seed)
    for iteration in range(max_planes):
        ids=np.flatnonzero(remaining)
        if len(ids)<min_support:break
        z=q[ids,2];local=xy[ids]
        # Horizontal modes give exact constant-height candidates; random planar
        # triples permit pitched roofs. Do not force separate levels to blend.
        hist,edges=np.histogram(z,bins=np.arange(z.min()-.2,z.max()+.4,.15))
        candidates=[np.array([0.,0.,(edges[k]+edges[k+1])/2]) for k in np.argsort(hist)[-20:]]
        for _ in range(350):
            chosen=rng.choice(len(ids),3,replace=False);a=np.column_stack((local[chosen],np.ones(3)))
            if abs(np.linalg.det(a))<8:continue
            plane=np.linalg.solve(a,z[chosen])
            if np.linalg.norm(plane[:2])<1.25:candidates.append(plane)
        ranked=[]
        for plane in candidates:
            residual=abs(z-(local@plane[:2]+plane[2]));ranked.append((int(np.count_nonzero(residual<.16)),plane))
        ranked.sort(key=lambda x:x[0],reverse=True)
        best=None
        for _,plane in ranked[:8]:
            take=abs(z-(local@plane[:2]+plane[2]))<.16
            # Require connected, spatially supported patches. A slanted plane
            # crossing many unrelated roof levels must not win by raw count.
            cells=np.floor(q[ids[take],:2]/.8).astype(int);base=cells.min(0);ij=cells-base
            raster=np.zeros(ij.max(0)+1,dtype=bool);raster[ij[:,0],ij[:,1]]=True
            parts,_=label(raster,structure=np.ones((3,3)));partids=parts[ij[:,0],ij[:,1]];counts=np.bincount(partids)
            stable=counts[partids]>=min_support
            supported=ids[take][stable]
            if best is None or len(supported)>len(best[0]):best=(supported,plane)
        if best is None or len(best[0])<min_support:break
        supported,plane=best
        for _ in range(3):
            a=np.column_stack((xy[supported],np.ones(len(supported))));plane=np.linalg.lstsq(a,q[supported,2],rcond=None)[0]
            residual=abs(q[supported,2]-a@plane);supported=supported[residual<.18]
        if len(supported)<min_support:break
        labels[supported]=len(planes);remaining[supported]=False
        planes.append(dict(coefficients_local=plane.tolist(),support_vertices=len(supported),median_abs_residual_m=float(np.median(residual))))
    if not planes:raise ValueError('No supported architectural roof plane')
    core=np.flatnonzero(labels>=0);tree=cKDTree(q[core,:2]);distance,near=tree.query(q[:,:2],k=min(12,len(core)))
    candidates=core[near];coeff=np.array([p['coefficients_local'] for p in planes])
    candidate_labels=labels[candidates];candidate_heights=np.einsum('nki,ni->nk',coeff[candidate_labels][:,:,:2],xy)+coeff[candidate_labels][:,:,2]
    # Distance controls locality. Height penalty preserves a nearby true level
    # when two roof patches meet, without retaining unsupported tall clutter.
    score=distance+.8*np.minimum(abs(candidate_heights-q[:,None,2]),3)
    assignment=candidate_labels[np.arange(len(q)),score.argmin(1)];assignment[core]=labels[core]
    fitted=q.copy();selected=coeff[assignment];fitted[:,2]=np.sum(xy*selected[:,:2],axis=1)+selected[:,2]
    return fitted,dict(seed=seed,planes=planes,coordinate_origin_xy_m=origin.tolist(),direct_plane_support=len(core),
                      vertices=len(q),unsupported_vertices_snapped_to_nearby_plane=int(remaining.sum()),
                      displacement_p95_m=float(np.percentile(abs(fitted[:,2]-q[:,2]),95)),
                      displacement_max_m=float(abs(fitted[:,2]-q[:,2]).max()),
                      limits='M1 large roof planes only. HVAC, skylights, parapets and small roof breaks are suppressed. Plane fit uses the same source and is not an independent accuracy check.'),assignment

def rebuild_planar_patches(vertices,faces,assignment,review):
    from shapely.geometry import Polygon, LineString, Point
    from shapely.ops import unary_union, linemerge, polygonize
    from shapely import constrained_delaunay_triangles
    from collections import Counter
    q=np.asarray(vertices);tree=cKDTree(q[:,:2]);_,near=tree.query(q[:,:2],k=13);labels=assignment.copy()
    for _ in range(2):
        labels=np.array([np.bincount(row,minlength=len(review['planes'])).argmax() for row in labels[near]])
    face_labels=np.array([Counter(row).most_common(1)[0][0] for row in labels[faces]])
    patches=[]
    for label_id in range(len(review['planes'])):
        triangles=[Polygon(q[tri,:2]) for tri in faces[face_labels==label_id]]
        if triangles:patches.append((label_id,unary_union(triangles)))
    coverage=unary_union([p for _,p in patches])
    network=linemerge(unary_union([p.boundary for _,p in patches]))
    lines=list(network.geoms) if hasattr(network,'geoms') else [network]
    # Shared boundary segments are simplified once, retaining shared junctions.
    # Independent simplification of each polygon would leave gaps/overlaps.
    regions=list(polygonize(unary_union([line.simplify(.85) for line in lines])))
    coeff=np.array([p['coefficients_local'] for p in review['planes']]);origin=np.array(review['coordinate_origin_xy_m'])
    outv=[];outf=[];edge_heights={};area_discarded=0.;used_labels=set();finished_patches={}
    for region in regions:
        if not coverage.covers(region.representative_point()):continue
        if region.area<2:
            area_discarded+=region.area;continue
        label_id=max(patches,key=lambda item:region.intersection(item[1]).area)[0];used_labels.add(label_id)
        finished_patches.setdefault(label_id,[]).append(region)
        plane=coeff[label_id]
        for tri in constrained_delaunay_triangles(region).geoms:
            xy=np.array(tri.exterior.coords)[:3]
            axy,bxy=xy[1]-xy[0],xy[2]-xy[0]
            if axy[0]*bxy[1]-axy[1]*bxy[0]<0:xy=xy[::-1]
            z=(xy-origin)@plane[:2]+plane[2];n=len(outv);outv.extend(np.column_stack((xy,z)));outf.append((n,n+1,n+2))
        for boundary in [region.exterior,*region.interiors]:
            coords=np.asarray(boundary.coords)
            for a,b in zip(coords[:-1],coords[1:]):
                key=tuple(sorted((tuple(np.round(a,6)),tuple(np.round(b,6)))))
                edge_heights.setdefault(key,[]).append(label_id)
    # Only plane-to-plane height changes receive a vertical transition face.
    stepv=[];stepf=[];outer_edges=[]
    for edge,ids in edge_heights.items():
        ids=list(set(ids))
        if len(ids)==1:
            xy=np.array(edge);plane=coeff[ids[0]];edgev=xy[1]-xy[0];left=np.array([-edgev[1],edgev[0]])/np.linalg.norm(edgev)
            owner=unary_union(finished_patches[ids[0]])
            if not owner.covers(Point(xy.mean(0)+left*.02)):xy=xy[::-1]
            z=(xy-origin)@plane[:2]+plane[2];outer_edges.append(np.column_stack((xy,z)))
        if len(ids)!=2:continue
        xy=np.array(edge);a,b=coeff[ids];za=(xy-origin)@a[:2]+a[2];zb=(xy-origin)@b[:2]+b[2]
        if abs(za-zb).max()<.05:continue
        top=np.maximum(za,zb);bottom=np.minimum(za,zb);n=len(stepv)
        stepv.extend([[*xy[0],top[0]],[*xy[1],top[1]],[*xy[1],bottom[1]],[*xy[0],bottom[0]]])
        high_id=ids[0] if za.mean()>zb.mean() else ids[1];edgev=xy[1]-xy[0];left=np.array([-edgev[1],edgev[0]])/np.linalg.norm(edgev)
        high_patch=unary_union(finished_patches[high_id])
        triangles=[(n,n+1,n+2),(n,n+2,n+3)]
        if high_patch.covers(Point(xy.mean(0)+left*.02)):triangles=[tuple(reversed(t)) for t in triangles]
        stepf.extend(triangles)
    vv=np.array(outv);ff=np.array(outf,dtype=np.int32)
    # Weld same-level vertices for a compact surface and boundary extraction.
    _,first,inv=np.unique(np.round(vv,6),axis=0,return_index=True,return_inverse=True);vv=vv[first];ff=inv[ff]
    review.update(boundary_simplification_m=.85,spatial_label_vote='13 neighbours, two passes; no height blending',
                  planes_retained=sorted(used_labels),discarded_tiny_patch_area_m2=area_discarded,patch_regions=len(regions),roof_triangles=len(ff))
    return vv,ff,np.array(stepv),np.array(stepf,dtype=np.int32),outer_edges
