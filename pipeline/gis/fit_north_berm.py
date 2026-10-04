"""Fit a distant review surface from low, unclassified survey returns.

This is not a ground-class DTM. The shore threshold and hidden edge closure are
recorded assumptions. No riding collision or geographic acceptance is assigned.
"""
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from scipy.stats import binned_statistic_2d
from acquire_sources import digest, save_json

ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'data/derived/lions-gate-north-ground-survey.npz'
cloud=np.load(source);points=cloud['xyz']
center=np.array([446.62800598,1624.85253906]);step=2.
edges=[np.arange(np.floor(c-140),np.ceil(c+140)+step,step) for c in center]
take=(cloud['classification']==1)&(points[:,2]>.0)&(points[:,2]<8.)
p=points[take]
z=binned_statistic_2d(p[:,0],p[:,1],p[:,2],statistic=lambda a:np.percentile(a,10),bins=edges).statistic
xx,yy=np.meshgrid((edges[0][:-1]+edges[0][1:])/2,(edges[1][:-1]+edges[1][1:])/2,indexing='ij')
# Low broad land is continuous in the inspected RGB/height plot. Isolated sea
# returns do not define ground. The two measured pedestals are separate meshes.
land=np.isfinite(z)&(z>1.4)&(z<6.)
land=ndimage.binary_closing(land,iterations=2)
labels,count=ndimage.label(land)
seed=np.unravel_index(np.argmin((xx-center[0])**2+(yy-center[1])**2),xx.shape)
label=labels[seed]
if label==0:raise RuntimeError('The measured tower centre is outside the review land surface')
land=labels==label
valid=land&np.isfinite(z)&(z<6.)
nearest=ndimage.distance_transform_edt(~valid,return_distances=False,return_indices=True)
z[land&~valid]=z[tuple(nearest[:,land&~valid])]
vertices=np.column_stack((xx.ravel(),yy.ravel(),z.ravel()))
faces=[];ny=xx.shape[1]
for i in range(xx.shape[0]-1):
    for j in range(xx.shape[1]-1):
        if land[i:i+2,j:j+2].all():
            a=i*ny+j;b=(i+1)*ny+j;c=b+1;d=a+1
            faces.extend([[a,b,c],[a,c,d]])
faces=np.asarray(faces,dtype=np.int32)
indices,local_faces=np.unique(faces,return_inverse=True)
vertices=vertices[indices];faces=local_faces.reshape(-1,3)
# Close exposed mesh boundaries below the ocean. This closure is hidden support,
# not a measured revetment. It prevents a visibly floating distant shore edge.
directed=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
ordered=np.sort(directed,axis=1)
_,inverse,counts=np.unique(ordered,axis=0,return_inverse=True,return_counts=True)
boundary=directed[counts[inverse]==1]
v=vertices.tolist();f=faces.tolist()
for a,b in boundary:
    k=len(v);v.extend([[*vertices[a,:2],-.5],[*vertices[b,:2],-.5]])
    f.extend([[int(b),int(a),k],[int(b),k,k+1]])
out=ROOT/'data/derived/lions-gate-north-berm.npz'
np.savez_compressed(out,vertices=np.asarray(v)-[*center,0.],faces=np.asarray(f),anchor=[*center,0.])
record=dict(source=str(source.relative_to(ROOT)),source_sha256=digest(source),
    output=str(out.relative_to(ROOT)),output_sha256=digest(out),survey_period='2022-09-07/09',
    vertical_datum='CGVD2013',cell_size_m=step,vertices=len(v),triangles=len(f),
    method='Cell 10th percentile of low unclassified returns; connected broad land; separate foundation meshes',
    assumptions=['1.4 m wet-shore threshold','2-cell closing of pedestal shadows','Nearest valid fill only inside the connected land region','Hidden vertical edge closures to -0.5 m'],
    accepted=False,collision='none',accuracy='Review surface. Shore outline and outer crop transition remain unaccepted.')
save_json(ROOT/'manifests/lions-gate-north-berm.json',record)
print(json.dumps(record,indent=2))
