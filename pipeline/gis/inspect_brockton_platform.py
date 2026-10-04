"""Plot survey returns at the lighthouse walkway and adjoining seawall."""
import os
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

data=np.load(ROOT/'data/derived/brockton-lighthouse-survey.npz')
p=data['xyz'];rgb=data['rgb'].astype(float);rgb/=max(255.,rgb.max())
inside=(p[:,0]>1870)&(p[:,0]<1910)&(p[:,1]>-225)&(p[:,1]<-150)
fig,axes=plt.subplots(1,3,figsize=(16,8),dpi=140)
low=inside&(p[:,2]>2)&(p[:,2]<6)
axes[0].scatter(p[low,0],p[low,1],c=rgb[low],s=1)
img=axes[1].scatter(p[low,0],p[low,1],c=p[low,2],s=1,cmap='terrain',vmin=2,vmax=6)
fig.colorbar(img,ax=axes[1],label='CGVD2013 (m)')
for ax in axes[:2]:
    ax.axis('equal');ax.grid(alpha=.2);ax.set(xlabel='Local east (m)',ylabel='Local north (m)')
    ax.plot([1893.88],[-188.225],'r+',ms=10)
axes[0].set_title('Low survey RGB');axes[1].set_title('Low survey heights')
axes[2].scatter(p[inside,1],p[inside,2],c=rgb[inside],s=1)
axes[2].set(xlabel='Local north (m)',ylabel='CGVD2013 (m)',ylim=(0,18),title='Side profile')
axes[2].grid(alpha=.2)
fig.tight_layout();fig.savefig(ROOT/'evidence/landmarks/brockton-platform-source.png')
print(json.dumps(dict(returns=int(inside.sum()),low_returns=int(low.sum()),classes=np.unique(data['classification'][low],return_counts=True)[1].tolist()),indent=2))
