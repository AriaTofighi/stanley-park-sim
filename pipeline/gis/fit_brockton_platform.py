"""Fit the visible lighthouse walking platform from its retained low returns."""
import os
import json
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon
from acquire_sources import save_json, digest
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

source=ROOT/'data/derived/brockton-lighthouse-survey.npz'
survey=np.load(source);p=survey['xyz'].astype(float)
light=json.loads((ROOT/'manifests/coastal-landmark-blockouts.json').read_text())['landmarks'][1]
center=np.array(light['centre_local_m'])
roi=(p[:,0]>1870)&(p[:,0]<1910)&(p[:,1]>-215)&(p[:,1]<-175)
candidate=p[roi&(p[:,2]>3.85)&(p[:,2]<4.25)]
a=np.column_stack((candidate[:,:2]-center,np.ones(len(candidate))))
# Fit and validate disjoint source samples. This verifies the fit only; the
# survey itself still needs independent geographic controls.
train=np.arange(len(candidate))%5!=0
coef=np.linalg.lstsq(a[train],candidate[train,2],rcond=None)[0]
for _ in range(4):
    use=train&(abs(a@coef-candidate[:,2])<.075)
    coef=np.linalg.lstsq(a[use],candidate[use,2],rcond=None)[0]
residual=abs(a@coef-candidate[:,2]);inliers=residual<.075
floor=candidate[inliers]
shape=shapely.union_all(shapely.buffer(shapely.points(floor[:,:2]),.28,quad_segs=3))
shape=shape.buffer(.2).buffer(-.2)
shape=shapely.union_all([shape,Polygon(light['body_outline_local_m']).buffer(.02)])
parts=[poly for poly in shapely.get_parts(shape) if isinstance(poly,Polygon)]
shape=max(parts,key=lambda poly:poly.area)
shape=Polygon(shape.exterior).simplify(.06,preserve_topology=True)
top_vertices=[];top_faces=[]
for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(shape)):
    xy=np.asarray(tri.exterior.coords)[:3]
    if np.cross(np.append(xy[1]-xy[0],0),np.append(xy[2]-xy[0],0))[2]<0:xy=xy[::-1]
    z=np.column_stack((xy-center,np.ones(len(xy))))@coef
    k=len(top_vertices);top_vertices.extend(np.column_stack((xy,z)).tolist());top_faces.append([k,k+1,k+2])
edge=np.asarray(shapely.orient_polygons(shape).exterior.coords)[:-1]
height=np.column_stack((edge-center,np.ones(len(edge))))@coef
wall_vertices=np.vstack((np.column_stack((edge,height-.02)),np.column_stack((edge,np.full(len(edge),-1.)))))
wall_faces=[];n=len(edge)
for i in range(n):
    j=(i+1)%n;wall_faces.extend([[i,i+n,j+n],[i,j+n,j]])
files=[]
for name,vertices,faces in [('WalkingPlatformReview',np.asarray(top_vertices),np.asarray(top_faces)),('SeawallBaseReview',wall_vertices,np.asarray(wall_faces))]:
    path=ROOT/f'data/derived/brockton-{name}.npz'
    np.savez_compressed(path,vertices=vertices-[*center,0.],faces=faces,anchor=[*center,0.])
    files.append(dict(name='SM_Brockton_'+name,path=path.relative_to(ROOT).as_posix(),sha256=digest(path),vertices=len(vertices),triangles=len(faces)))
check=residual[(~train)&inliers]
record=dict(source=source.relative_to(ROOT).as_posix(),source_sha256=digest(source),
    measured_plane_coefficients=coef.tolist(),plane_origin_xy_m=center.tolist(),
    source_floor_inliers=len(floor),source_candidates=len(candidate),held_out_inlier_count=len(check),
    held_out_inlier_p95_residual_m=float(np.percentile(check,95)),
    footprint_local_m=list(shape.exterior.coords),footprint_area_m2=shape.area,assets=files,
    survey_period='2022-09-07/09',vertical_datum='CGVD2013',accepted=False,collision='complex',
    reference='https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx',
    assumptions=['0.28 m sampling buffer defines a review boundary, not an accepted path width','Small source holes are filled within the measured floor outline','Tower footprint supports the hidden floor below the arches','Straight wall closure to -1 m; detailed masonry and foundations remain open','Crop ends do not define pedestrian-network endpoints'],
    scope='Visible walking platform and wall mass. Fit quality is not independent geographic accuracy.')
save_json(ROOT/'manifests/brockton-platform.json',record)
fig,ax=plt.subplots(figsize=(8,8),dpi=150)
ax.scatter(p[roi,0],p[roi,1],c='#bbbbbb',s=.3);ax.scatter(floor[:,0],floor[:,1],c='#20627b',s=1)
ax.plot(*np.array(shape.exterior.coords).T,color='#b65d1b',lw=1);ax.axis('equal');ax.grid(alpha=.2)
ax.set(xlabel='Local east (m)',ylabel='Local north (m)',title='Brockton walking platform: floor returns and review footprint')
fig.tight_layout();fig.savefig(ROOT/'evidence/landmarks/brockton-platform-fit.png')
print(json.dumps({k:v for k,v in record.items() if k not in ['footprint_local_m','assets']},indent=2))
