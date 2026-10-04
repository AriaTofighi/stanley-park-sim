"""Small solids for coarse industrial silhouettes. No machinery simulation."""
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString
from shapely.ops import split
from shapely.geometry.polygon import orient
from skyline_meshes import extrusion,ring_solid,validate


def axes(poly):
    q=np.asarray(orient(poly.minimum_rotated_rectangle,sign=1).exterior.coords)[:4,:2]
    e=np.roll(q,-1,axis=0)-q;u=e[np.argmax(np.linalg.norm(e,axis=1))];u=u/np.linalg.norm(u)
    if u[0]<0:u=-u
    v=np.array([-u[1],u[0]]);center=q.mean(0);size=np.ptp((q-center)@np.array([u,v]).T,axis=0)
    return center,np.array([u,v]),size


def beam(a,b,width,depth=None):
    a,b=np.asarray(a,dtype=float),np.asarray(b,dtype=float);axis=(b-a)/np.linalg.norm(b-a)
    reference=np.array([0.,0.,1.]) if abs(axis[2])<.95 else np.array([1.,0.,0.])
    u=np.cross(reference,axis);u/=np.linalg.norm(u);v=np.cross(axis,u);depth=depth or width
    q=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])
    delta=q[:,0,None]*u*width/2+q[:,1,None]*v*depth/2
    vertices,faces=ring_solid([a+delta,b+delta]);validate(vertices,faces)
    return vertices,faces


def silo(poly,base,body,roof):
    p=orient(poly,sign=1);q=np.asarray(p.exterior.coords)[:-1,:2];c=np.array(p.centroid.coords[0])
    if not p.equals(p.convex_hull):return extrusion(p,base,base+body+roof)
    rows=[np.column_stack((q,np.full(len(q),base))),np.column_stack((q,np.full(len(q),base+body))),
          np.column_stack((c+(q-c)*.02,np.full(len(q),base+body+roof)))]
    return ring_solid(rows)


def gable(poly,base,eave,ridge):
    center,ab,size=axes(poly);line=LineString([center-ab[0]*size[0],center+ab[0]*size[0]])
    pieces=[]
    for p in shapely.get_parts(split(poly,line)):
        if p.geom_type!='Polygon' or p.area<.1:continue
        v,f=extrusion(p,base,base+eave);n=len(v)//2
        across=(v[n:,:2]-center)@ab[1]
        v[n:,2]+=np.clip(1-np.abs(across)/(size[1]/2),0,1)*(ridge-eave)
        pieces.append((v,f))
    return pieces
