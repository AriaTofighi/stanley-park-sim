"""Offline source/mesh inspection panels; does not open the application."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
doc=json.loads((ROOT/'manifests/lumberman-facility-blockouts.json').read_text())
f=plt.figure(figsize=(16,9));a=f.add_subplot(121);b=f.add_subplot(122,projection='3d')
a.imshow(Image.open(ROOT/'evidence/corridor/ortho-utm/named-lumberman-wide.png'),extent=[740,980,-140,100])
for r in doc['assets']:
    p=np.load(ROOT/r['mesh_path']);v=p['vertices'];tri=p['faces'];col=r['color']
    if 'Floor' in r['name'] or 'RoadDeck' in r['name']:
        a.add_collection(PolyCollection(v[tri,:2],facecolors='none',edgecolors='lime' if 'Floor' in r['name'] else 'orange',linewidth=.55))
    b.add_collection3d(Poly3DCollection(v[tri],facecolors=col,edgecolors=np.array(col)*.8,linewidth=.15))
a.set_xlim(874,919);a.set_ylim(23,65);a.set_aspect('equal');a.grid(alpha=.3);a.set_title('City2022 ortho; orange road deck, green lower floor')
b.set_xlim(874,919);b.set_ylim(23,65);b.set_zlim(2,8);b.set_box_aspect([45,42,12]);b.view_init(14,62)
b.set_title('M1 estimated enclosure, measured floor/road heights')
for g in [a,b]:g.set_xlabel('Local east m');g.set_ylabel('Local north m')
f.tight_layout();f.savefig(ROOT/'evidence/facilities/lumberman-facility-mesh-review.png',dpi=160)
