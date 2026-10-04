"""Overlay source and proposed paths on georeferenced reference imagery."""
import json
import os
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import rasterio

def main():
    data=np.load(ROOT/'data/derived/paved-circuit-proposal.npz')
    s=data['chainage_source']; source=data['source_xy']; proposed=data['xyz']
    runtime_path=ROOT/'data/derived/paved-circuit-runtime.json'
    runtime=np.asarray(json.loads(runtime_path.read_text())['points_local_m']) if runtime_path.exists() else None
    for name in ['north-lumberman-issue','return-crossing','entrance-underpass','third-beach-gate-detail','prospect-walk','lumberman-walk']:
        path=ROOT/'evidence/corridor/ortho-utm'/f'{name}.tif'
        with rasterio.open(path) as ds:
            rgb=ds.read().transpose(1,2,0)[:,:,:3]
            left,bottom,right,top=ds.bounds
        # GeoTIFF uses absolute UTM, while scene geometry uses the fixed origin.
        if left>100000:left-=489600;right-=489600;bottom-=5461100;top-=5461100
        fig,ax=plt.subplots(figsize=(13,13),dpi=150)
        ax.imshow(rgb,extent=[left,right,bottom,top])
        ax.plot(source[:,0],source[:,1],color='yellow',lw=1.1,label='City source')
        ax.plot(proposed[:,0],proposed[:,1],color='cyan',lw=1.1,label='Surface proposal')
        if runtime is not None:ax.plot(runtime[:,0],runtime[:,1],color='#ff6c2c',lw=1.2,label='Authored pavement')
        for i in range(0,len(s),20):
            x,y=source[i]
            if left<x<right and bottom<y<top:
                ax.text(x,y,f'{s[i]:.0f}',fontsize=8,color='white',bbox=dict(facecolor='black',alpha=.65,pad=1))
        ax.set(xlim=(left,right),ylim=(bottom,top),xlabel='Local east (m)',ylabel='Local north (m)',title=name)
        ax.legend();fig.tight_layout()
        fig.savefig(path.with_name(name+'-review.png'));plt.close(fig)

if __name__=='__main__':main()
