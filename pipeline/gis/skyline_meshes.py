"""Small mesh primitives for editable distant skyline forms, in metres."""
import numpy as np
import shapely
from shapely.geometry import Polygon, Point
from shapely.geometry.polygon import orient
from scipy.spatial import Delaunay


def extrusion(polygon, bottom, top):
    polygon=orient(polygon,sign=1.)
    rings=[np.asarray(r.coords)[:-1,:2] for r in [polygon.exterior,*polygon.interiors]]
    xy=np.vstack(rings);count=len(xy)
    vertices=np.vstack((np.column_stack((xy,np.full(count,bottom))),np.column_stack((xy,np.full(count,top)))))
    lookup={tuple(np.round(p,8)):i for i,p in enumerate(xy)}
    faces=[]
    for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(polygon)):
        coords=np.asarray(tri.exterior.coords)[:3,:2]
        if np.linalg.det(np.column_stack((coords[1]-coords[0],coords[2]-coords[0])))<0:coords=coords[::-1]
        ids=[lookup[tuple(np.round(p,8))] for p in coords]
        faces.extend([ids[::-1],[i+count for i in ids]])
    start=0
    for ring in rings:
        for i in range(len(ring)):
            a,b=start+i,start+(i+1)%len(ring)
            faces.extend([[a,b,b+count],[a,b+count,a+count]])
        start+=len(ring)
    return vertices,np.asarray(faces,dtype=np.int32)


def ring_solid(rows):
    rows=np.asarray(rows);n=rows.shape[1];v=rows.reshape(-1,3);f=[]
    for k in range(len(rows)-1):
        for i in range(n):
            a=k*n+i;b=k*n+(i+1)%n
            f.extend([[a,b,b+n],[a,b+n,a+n]])
    for i in range(1,n-1):
        f.append([0,i+1,i]);a=(len(rows)-1)*n;f.append([a,a+i,a+i+1])
    return v,np.asarray(f,dtype=np.int32)


def fabric_surface(polygon, height_fn, spacing=2.):
    # Add regular interior points so a tensioned shape is not reduced to a cap.
    xmin,ymin,xmax,ymax=polygon.bounds
    xx,yy=np.meshgrid(np.arange(xmin,xmax,spacing),np.arange(ymin,ymax,spacing))
    inside=shapely.contains_xy(polygon,xx,yy)
    xy=np.vstack((np.asarray(polygon.exterior.coords)[:-1,:2],np.column_stack((xx[inside],yy[inside]))))
    if len(polygon.interiors):xy=np.vstack((xy,*[np.asarray(r.coords)[:-1,:2] for r in polygon.interiors]))
    faces=[];vertices=[]
    for simplex in Delaunay(xy).simplices:
        piece=Polygon(xy[simplex]).intersection(polygon)
        for poly in shapely.get_parts(piece):
            if poly.geom_type!='Polygon' or poly.area<1e-8:continue
            for t in shapely.get_parts(shapely.constrained_delaunay_triangles(poly)):
                q=np.asarray(t.exterior.coords)[:3,:2]
                if np.linalg.det(np.column_stack((q[1]-q[0],q[2]-q[0])))<0:q=q[::-1]
                i=len(vertices);vertices.extend(np.column_stack((q,height_fn(q))));faces.append([i,i+1,i+2])
    return np.asarray(vertices),np.asarray(faces,dtype=np.int32)


def validate(vertices,faces,closed=True):
    v,f=np.asarray(vertices),np.asarray(faces);t=v[f]
    areas=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)*.5
    if not np.isfinite(v).all() or len(f)==0 or areas.min()<1e-9:
        raise ValueError('Invalid skyline mesh values or degenerate faces')
    _,inv=np.unique(np.round(v,7),axis=0,return_inverse=True);wf=inv[f]
    edge=np.sort(np.concatenate((wf[:,:2],wf[:,1:],wf[:,[2,0]])),axis=1)
    _,counts=np.unique(edge,axis=0,return_counts=True)
    result=dict(finite=True,minimum_triangle_area_m2=float(areas.min()),boundary_edges=int((counts==1).sum()),nonmanifold_edges=int((counts>2).sum()))
    if closed and np.any(counts!=2):raise ValueError(f'Open solid: {result}')
    if closed:
        t=t-v.mean(0);volume=float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)
        if volume<=0:raise ValueError('Inverted skyline solid')
        result['signed_volume_m3']=volume
    return result
