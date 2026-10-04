"""Source/geometry preview figures; does not operate or test an application."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from build_west_landmark_blockouts import ROOT

d=json.loads((ROOT/'manifests/west-landmark-blockouts.json').read_text())
for feature in d['features']:
    tag={'SP_hollow_tree':'hollow-tree','SP_siwash_lookout':'siwash-lookout','SP_third_beach':'third-beach'}[feature['id']]
    fig=plt.figure(figsize=(15,7));plan=fig.add_subplot(121);view=fig.add_subplot(122,projection='3d')
    meta=json.loads((ROOT/f'evidence/corridor/ortho-utm/named-{tag}.json').read_text());b=meta['local_bounds_m']
    plan.imshow(plt.imread(ROOT/f'evidence/corridor/ortho-utm/named-{tag}.png'),extent=[b[0],b[2],b[1],b[3]])
    allv=[]
    for a in d['assets']:
        if a['feature_id']!=feature['id']:continue
        p=np.load(ROOT/a['mesh_path']);v=p['vertices'];f=p['faces'];allv.extend(v)
        if 'Wall' not in a['name'] and 'Rail' not in a['name'] and 'Post' not in a['name']:
            plan.triplot(v[:,0],v[:,1],f,color='#ed6852',linewidth=.3)
        poly=Poly3DCollection(v[f],facecolor=a['color'],edgecolor=(.12,.12,.1,.28),linewidth=.25);view.add_collection3d(poly)
    q=np.array(allv);lo=q.min(0);hi=q.max(0);mid=(lo+hi)/2;extent=np.maximum(hi-lo,[1,1,1]);margin=2
    plan.set_xlim(lo[0]-margin,hi[0]+margin);plan.set_ylim(lo[1]-margin,hi[1]+margin);plan.set_aspect('equal');plan.set_title('Geometry on City 2022 orthophoto')
    view.set_xlim(lo[0]-margin,hi[0]+margin);view.set_ylim(lo[1]-margin,hi[1]+margin);view.set_zlim(lo[2]-.2,hi[2]+.3);view.set_box_aspect(extent+[4,4,.5]);view.view_init(22,-32 if tag=='hollow-tree' else 133)
    view.set_title('Authored blockout; application review pending');fig.suptitle(feature['name']);fig.tight_layout();fig.savefig(ROOT/f'evidence/named-features/{tag}-m1-geometry-review.png',dpi=145);plt.close(fig)
