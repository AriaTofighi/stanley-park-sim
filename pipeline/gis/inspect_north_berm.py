"""Inspect existing survey returns before defining a bridge berm surface."""
import os
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'tmp/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

source = np.load(ROOT/'data/derived/lions-gate-north-ground-survey.npz')
xyz, rgb = source['xyz'], source['rgb'].astype(float)
rgb /= max(255., float(rgb.max()))
keep = (xyz[:,2] > .4) & (xyz[:,2] < 10.)
points = xyz[keep]
colours = rgb[keep]
fig, axes = plt.subplots(1, 2, figsize=(14,7), dpi=140)
axes[0].scatter(points[::8,0],points[::8,1],c=colours[::8],s=1)
image=axes[1].scatter(points[::8,0],points[::8,1],c=points[::8,2],s=1,vmin=.4,vmax=10.,cmap='terrain')
fig.colorbar(image,ax=axes[1],label='CGVD2013 height (m)')
for axis in axes:
    axis.plot([446.628],[1624.853],'r+',ms=10)
    axis.set(xlabel='Local east (m)',ylabel='Local north (m)');axis.axis('equal');axis.grid(alpha=.2)
axes[0].set_title('2022 survey RGB: returns between 0.4 and 10 m')
axes[1].set_title('2022 low-return heights: unclassified, not an accepted DTM')
fig.tight_layout();fig.savefig(ROOT/'evidence/landmarks/north-berm-source.png')
print(json.dumps(dict(points=len(xyz),low_points=len(points),classes=np.unique(source['classification'],return_counts=True)[0].tolist(),height_quantiles=np.percentile(xyz[:,2],[0,5,25,50,75,95,100]).tolist()),indent=2))
