"""Static package geometry review; never substitutes for Blender/app review."""
import json,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from build_named_feature_blockouts import ROOT

def main(package):
    d=json.loads((ROOT/f'manifests/{package}.json').read_text());features=d['features']
    fig=plt.figure(figsize=(8*min(3,len(features)),7*((len(features)+2)//3)))
    for i,feature in enumerate(features):
        ax=fig.add_subplot((len(features)+2)//3,min(3,len(features)),i+1,projection='3d');allv=[]
        for a in d['assets']:
            if a['feature_id']!=feature['id']:continue
            p=np.load(ROOT/a['mesh_path']);v=p['vertices'];f=p['faces'];allv.append(v)
            ax.add_collection3d(Poly3DCollection(v[f],facecolor=a['color'],edgecolor='#4a4943',linewidth=.18))
        v=np.vstack(allv);lo=v.min(0);hi=v.max(0);pad=max(hi-lo)*.1
        for method,k in [(ax.set_xlim,0),(ax.set_ylim,1),(ax.set_zlim,2)]:method(lo[k]-pad,hi[k]+pad)
        ax.set_box_aspect(hi-lo+pad);ax.view_init(20,-65);ax.set_title(feature['name']+'\nM1 envelope; detail unfinished')
    fig.tight_layout();fig.savefig(ROOT/f'evidence/named-features/{package}-geometry-review.png',dpi=145)

if __name__=='__main__':main(sys.argv[1])
