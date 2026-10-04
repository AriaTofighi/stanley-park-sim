"""Measure coastal landmark envelopes after inspecting orthophoto and point plots."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'cache/matplotlib'))
import json
import numpy as np
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import MultiPoint, LineString
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from acquire_sources import save_json,digest

rock_path=ROOT/'data/derived/siwash-rock-survey.npz'
rock=np.load(rock_path);p=rock['xyz'].astype(float);classes=rock['classification']
crop=np.linalg.norm(p[:,:2]-[-941.,691.],axis=1)<12
stone=p[crop&np.isin(classes,[1,2])&(p[:,2]>-.3)&(p[:,2]<=15.94)]
top=stone[stone[:,2]>12]
center=np.median(top[:,:2],axis=0)
angles=np.arange(48)*np.pi/24
directions=np.column_stack((np.cos(angles),np.sin(angles)))
levels=np.arange(.3,15.4,.5)
rings=[]; counts=[]
for h in levels:
    band=stone[abs(stone[:,2]-h)<.38]
    if len(band)<8:
        rings.append(None);counts.append(len(band));continue
    hull=MultiPoint(band[:,:2]).convex_hull
    ring_center=np.array(hull.centroid.coords[0])
    radii=[]
    for direction in directions:
        line=LineString([ring_center,ring_center+direction*24])
        section=line.intersection(hull)
        radii.append(max(np.linalg.norm(np.asarray(section.coords)-ring_center,axis=1)) if not section.is_empty and hasattr(section,'coords') else np.nan)
    radii=np.asarray(radii)
    valid=np.isfinite(radii)
    if valid.sum()<20: raise RuntimeError(f'Rock band {h} lacks a usable radial profile')
    radii=np.interp(angles,angles[valid],radii[valid],period=2*np.pi)
    radii=gaussian_filter1d(radii,.7,mode='wrap')
    rings.append(np.column_stack((ring_center+directions*radii[:,None],h*np.ones(len(angles)))).tolist());counts.append(len(band))
if any(row is None for row in rings): raise RuntimeError('Rock level missing; inspect before bridging it')
vegetation=p[crop&(classes==5)&(p[:,2]>14)]
rock_result=dict(id='siwash-rock',name='Siwash Rock / sɬχil̕əx slhx̱í7elsh',
    source_sha256=digest(rock_path),centre_local_m=center.tolist(),rings=rings,band_counts=counts,
    crown_bounds_min_m=vegetation.min(0).tolist(),crown_bounds_max_m=vegetation.max(0).tolist(),
    method='48 radial samples of measured convex cross-sections at 0.5m levels; excludes classified vegetation',
    accepted=False,limits='Convex section envelopes omit caves and undercuts. Crown is a measured envelope, not a tree model. Top cap and below-water closure are simplified.')

lighthouse_path=ROOT/'data/derived/brockton-lighthouse-survey.npz'
survey=np.load(lighthouse_path);p=survey['xyz'].astype(float)
near=p[np.linalg.norm(p[:,:2]-[1894.,-188.],axis=1)<7]
body=near[(near[:,2]>10)&(near[:,2]<12.4)]
rect=np.array(MultiPoint(body[:,:2]).minimum_rotated_rectangle.exterior.coords)[:4]
centre=rect.mean(0);d=rect[1]-rect[0];d/=np.linalg.norm(d);n=np.array([-d[1],d[0]])
q=np.column_stack(((near[:,:2]-centre)@d,(near[:,:2]-centre)@n,near[:,2]))
bands=[]
for lo,hi in [(8.8,9.3),(10.,12.4),(12.85,13.25),(13.65,13.95),(15.25,15.5)]:
    band=q[(q[:,2]>lo)&(q[:,2]<hi)&(np.linalg.norm(q[:,:2],axis=1)<3.3)]
    bounds=np.percentile(band[:,:2],[1,99],axis=0)
    bands.append(dict(height_range_m=[lo,hi],bounds_min_m=bounds[0].tolist(),bounds_max_m=bounds[1].tolist(),returns=len(band)))
lighthouse_result=dict(id='brockton-lighthouse',name='Brockton Point Lighthouse',source_sha256=digest(lighthouse_path),
    centre_local_m=centre.tolist(),axis_unit=d.tolist(),transverse_unit=n.tolist(),body_outline_local_m=rect.tolist(),
    measured_bands=bands,observed_top_m=float(near[:,2].max()),walking_level_m=4.07,
    vertical_datum='CGVD2013',accepted=False,
    limits='Body outline and upper levels measured from returns. Arch opening, railings and stairs need separate close-range controls. Colour divisions are visual blockout assumptions.')
save_json(ROOT/'manifests/coastal-landmark-blockouts.json',dict(landmarks=[rock_result,lighthouse_result]))
fig,ax=plt.subplots(figsize=(9,7),dpi=140)
for i,row in enumerate(rings):
    points=np.array(row);ax.plot(points[:,0],points[:,1],lw=.8,label=f'{levels[i]:.1f}m' if i%6==0 else None)
ax.scatter(stone[::8,0],stone[::8,1],s=.2,c='gray');ax.set_aspect('equal');ax.legend();ax.set(xlabel='Local East (m)',ylabel='Local North (m)',title='Siwash Rock: observed stone sections (CGVD2013)')
fig.tight_layout();fig.savefig(ROOT/'evidence/landmarks/siwash-section-fit.png')
print(json.dumps(dict(rock_center=center.tolist(),stone_top=float(stone[:,2].max()),lighthouse_center=centre.tolist(),lighthouse_bands=bands,lighthouse_top=lighthouse_result['observed_top_m']),indent=2))
