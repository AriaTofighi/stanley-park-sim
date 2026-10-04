"""Fixed-source panels for physical gate and walking-curve inspection."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

ROOT=Path(__file__).resolve().parents[2]
d=json.loads((ROOT/'manifests/maze-gate-blockouts.json').read_text());assets={r['name']:r for r in d['assets']}
f,axs=plt.subplots(1,3,figsize=(18,8))
for ax,site in zip(axs,d['sites']):
    stem=ROOT/f"evidence/corridor/ortho-utm/{site['reference_ortho']}";info=json.loads(stem.with_suffix('.json').read_text());xmin,ymin,xmax,ymax=info['local_bounds_m']
    ax.imshow(Image.open(stem.with_suffix('.png')),extent=[xmin,xmax,ymin,ymax])
    for name in site['meshes']:
        mesh=np.load(ROOT/assets[name]['mesh_path']);v=mesh['vertices'];t=mesh['faces'];ax.add_collection(PolyCollection(v[t,:2],facecolors='yellow',edgecolors='black',linewidth=.4))
    path=np.array(site['walking_path']['points_local_m']);ax.plot(path[:,0],path[:,1],color='red',lw=1.7,label='Walking contact centre')
    lo=path[:,:2].min(0)-3;hi=path[:,:2].max(0)+3;ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_aspect('equal');ax.grid(alpha=.3)
    ax.set_title(site['id']+'\nYellow: estimated fixed steel frames');ax.set_xlabel('Local east m');ax.set_ylabel('Local north m')
    ax.legend(loc='lower left',fontsize=8)
f.tight_layout();f.savefig(ROOT/'evidence/facilities/maze-gate-source-and-walk-review.png',dpi=160)
