"""Survey-driven canopy envelopes and building masses, explicitly dated 2022."""
import json
from pathlib import Path
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import label,binary_closing
from scipy.spatial import ConvexHull
from acquire_sources import digest,save_json
ROOT=Path(__file__).resolve().parents[2]
g=np.load(ROOT/'data/derived/terrain_2022_park.npz')
height=RegularGridInterpolator((g['y'],g['x']),g['z'],bounds_error=False,fill_value=np.nan)
park=RegularGridInterpolator((g['y'],g['x']),g['inside_park'].astype(float),method='nearest',bounds_error=False,fill_value=0)
route=json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text())
from scipy.spatial import cKDTree
path_tree=cKDTree(np.asarray(route['points_local_m'])[:,:2])
canopy=[];buildings=[]
for file in sorted((ROOT/'data/derived').glob('lidar2022_*.npz')):
    with np.load(file) as p:
        x,y=np.meshgrid(p['canopy_x'][::3],p['canopy_y'][::3])
        top=p['canopy_max'][::3,::3];count=p['canopy_count'][::3,::3]
        xy=np.column_stack((x.ravel(),y.ravel()));base=height(xy[:,::-1])
        delta=top.ravel()-base;distance=path_tree.query(xy)[0]
        take=(park(xy[:,::-1])>.5)&np.isfinite(delta)&(delta>4)&(count.ravel()>30)&(distance>6)
        cells=np.column_stack((xy[take],base[take],top.ravel()[take]))
        canopy.append(dict(tile=file.stem,points=cells.tolist()))
        pts=p['buildings']
        if len(pts)<20:continue
        origin=np.floor(pts[:,:2].min(axis=0)/2)*2
        cell=np.floor((pts[:,:2]-origin)/2).astype(int)
        shape=tuple((cell.max(axis=0)+1)[::-1]);occupancy=np.zeros(shape,bool)
        occupancy[cell[:,1],cell[:,0]]=True
        labels,total=label(binary_closing(occupancy),structure=np.ones((3,3)))
        groups=labels[cell[:,1],cell[:,0]]
        for group in range(1,total+1):
            points=pts[groups==group]
            if len(points)<15:continue
            try:hull=ConvexHull(points[:,:2]);outline=points[hull.vertices,:2]
            except Exception:continue
            if hull.volume<8:continue
            base=float(np.nanmedian(height(outline[:,::-1])))
            roof=float(np.percentile(points[:,2],90))
            if not np.isfinite(base) or roof<base+1.5:continue
            buildings.append(dict(id=f'{file.stem}_{group}',outline=outline.tolist(),base_m=base,roof_m=roof,returns=len(points)))
save_json(ROOT/'data/derived/cover-blockout.json',dict(canopy=canopy,buildings=buildings,
    reference_date='2022-09-07/09',status='Geographic blockout only; not individual trees or final building models',
    canopy_method='15m sample of 5m high-vegetation maxima; surveyed top/base, generic crown envelope',
    building_method='Connected 2m class-6 occupancy; convex footprint envelope; 90th-percentile roof height',
    unresolved='2026 forestry changes, species, roof forms, building identities, and close-range accuracy'))
print('Canopy envelopes',sum(len(t['points']) for t in canopy),'building masses',len(buildings),flush=True)
