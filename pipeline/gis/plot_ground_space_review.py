"""Static source/mesh diagnostic; not an application check."""
import json
import os
from pathlib import Path
os.environ['MPLCONFIGDIR']=str(Path(__file__).resolve().parents[2]/'evidence/mpl-cache')
import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from shapely.geometry import shape
from build_public_space_meshes import ROOT

source=json.loads((ROOT/'data/derived/ground-spaces/ground-spaces-local.geojson').read_text(encoding='utf8'))
record=json.loads((ROOT/'manifests/ground-space-blockouts.json').read_text(encoding='utf8'))
fig,axes=plt.subplots(1,3,figsize=(19,7))
for ax,name in zip(axes,['m1-gardens-north','m1-community-garden','m1-biofilter']):
    meta=json.loads((ROOT/f'evidence/corridor/ortho-utm/{name}.json').read_text())
    x0,y0,x1,y1=meta['local_bounds_m']
    ax.imshow(Image.open(ROOT/f'evidence/corridor/ortho-utm/{name}.png'),extent=[x0,x1,y0,y1])
    for feature in source['features']:
        geom=shape(feature['geometry'])
        if not geom.intersects(shape({'type':'Polygon','coordinates':[[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]})):continue
        for poly in getattr(geom,'geoms',[geom]):
            if poly.geom_type=='Polygon':
                xy=np.asarray(poly.exterior.coords);ax.plot(xy[:,0],xy[:,1],color='yellow',lw=.65)
    ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect('equal');ax.set_title(name+'\nYellow: retained source/authoring bounds');ax.set_xlabel('local east metres');ax.set_ylabel('local north metres')
fig.suptitle('City 2022 imagery / finite M1 ground forms. Bounds are approximate; no current-condition claim.')
fig.tight_layout();fig.savefig(ROOT/'evidence/ground-spaces/source-overlay-review.png',dpi=180)
plt.close(fig)
