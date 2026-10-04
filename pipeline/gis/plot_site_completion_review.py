"""Inspect retained source picks and low-volume envelopes without an app."""
from pathlib import Path
import os,json
ROOT=Path(__file__).resolve().parents[2]
os.environ['MPLCONFIGDIR']=str(ROOT/'evidence/mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import shapely
from shapely.geometry import shape,box

source=json.loads((ROOT/'data/derived/site-completions/site-completions-local.geojson').read_text())
fig,axes=plt.subplots(1,3,figsize=(19,7))
for ax,name in zip(axes,['m1-painters-stream','m1-port-view','m1-waterpark']):
    meta=json.loads((ROOT/f'evidence/corridor/ortho-utm/{name}.json').read_text());b=meta['local_bounds_m']
    ax.imshow(Image.open(ROOT/f'evidence/corridor/ortho-utm/{name}.png'),extent=[b[0],b[2],b[1],b[3]])
    for f in source['features']:
        geom=shape(f['geometry'])
        if not geom.intersects(box(*b)):continue
        for part in shapely.get_parts(geom):
            if part.geom_type=='Polygon':ax.plot(*np.asarray(part.exterior.coords).T,color='yellow',lw=1)
    if name=='m1-waterpark':
        for row in json.loads((ROOT/'manifests/waterpark-low-forms.json').read_text())['meshes']:
            with np.load(ROOT/row['path'])as p:v=p['vertices']+p['anchor'];f=p['faces']
            ax.triplot(v[:,0],v[:,1],f,color='cyan',lw=.25)
    ax.set_xlim(b[0],b[2]);ax.set_ylim(b[1],b[3]);ax.set_aspect('equal');ax.set_title(name+' / City2022 source');ax.set_xlabel('east metres');ax.set_ylabel('north metres')
fig.suptitle('Yellow: coarse source ground bounds; cyan: measured low-form envelope. No current-condition or geodetic certification.')
fig.tight_layout();out=ROOT/'evidence/site-completions/source-and-low-form-review.png';out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,dpi=170)
