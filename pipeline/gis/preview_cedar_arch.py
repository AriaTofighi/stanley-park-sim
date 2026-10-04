"""Review authored cedar members beside retained source returns."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from build_named_feature_blockouts import ROOT, survey

d=json.loads((ROOT/'manifests/cedar-arch-blockout.json').read_text())
fig=plt.figure(figsize=(16,8));plan=fig.add_subplot(121);view=fig.add_subplot(122,projection='3d')
m=json.loads((ROOT/'evidence/corridor/ortho-utm/named-lumberman-wide.json').read_text());b=m['local_bounds_m']
plan.imshow(plt.imread(ROOT/'evidence/corridor/ortho-utm/named-lumberman-wide.png'),extent=[b[0],b[2],b[1],b[3]])
q,c=survey('lumberman-arch');q=q[(q[:,0]>897)&(q[:,0]<919)&(q[:,1]>-8)&(q[:,1]<3)&(q[:,2]>4)&(q[:,2]<11.5)]
view.scatter(*q[::2].T,s=.4,c='#2b7282',alpha=.3)
for a in d['assets']:
    p=np.load(ROOT/a['mesh_path']);v=p['vertices'];f=p['faces']
    plan.triplot(v[:,0],v[:,1],f,color='#ff8d30',linewidth=.5)
    view.add_collection3d(Poly3DCollection(v[f],facecolor=a['color'],edgecolor='#34322a',alpha=.7,linewidth=.35))
plan.set_xlim(895,920);plan.set_ylim(-10,6);plan.set_aspect('equal');plan.set_title('Authored members on City 2022 orthophoto')
view.set_xlim(895,920);view.set_ylim(-10,6);view.set_zlim(2,12);view.set_box_aspect([25,16,10]);view.view_init(20,-66)
view.set_title('Authored geometry with source returns (blue)')
fig.suptitle("Lumberman's Arch M1: three observed log members; unresolved fourth member remains explicit")
fig.tight_layout();fig.savefig(ROOT/'evidence/named-features/cedar-arch-m1-geometry-review.png',dpi=145)
