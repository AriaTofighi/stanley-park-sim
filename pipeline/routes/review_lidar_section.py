"""Plot independent ground returns across the failed source terrain corridor."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import RegularGridInterpolator
from ground_reference import GroundReference, circuit_samples, ROOT

ground=GroundReference()
s,xy,tangent,normal=circuit_samples()
heights={}
for name in ["terrain_corridor_reference","terrain_2016_reference"]:
    g=np.load(ROOT/f"data/derived/{name}.npz")
    heights[name]=RegularGridInterpolator((g["y"],g["x"]),g["z"],bounds_error=False)
fig,axes=plt.subplots(3,2,figsize=(14,11),dpi=140)
records=[]
for ax,station in zip(axes.ravel(),[5680,5740,5800,5860,5920,6020]):
    i=int(np.argmin(abs(s-station)))
    idx=ground.tree.query_ball_point(xy[i],12)
    pts=ground.points[idx]; rel=pts[:,:2]-xy[i]
    along=rel@tangent[i]; across=rel@normal[i]
    take=abs(along)<.8
    rgb=ground.colors[idx][take].astype(float)
    if rgb.max(initial=0)>255:rgb/=257
    ax.scatter(across[take],pts[take,2],s=4,c=np.clip(rgb/255,0,1),label="2022 ground returns")
    offset=np.linspace(-12,12,193)
    probes=xy[i]+offset[:,None]*normal[i]
    for name,query in heights.items():ax.plot(offset,query(probes[:,::-1]),lw=1,label=name)
    ax.axvline(0,c="red",lw=1,ls="--",label="catalogue route")
    ax.set(xlim=(-12,12),ylim=(0,18),title=f"Chainage {s[i]:.1f} m",xlabel="Offset: negative toward sea (m)",ylabel="CGVD2013 height (m)")
    ax.grid(alpha=.2)
    records.append(dict(station_m=float(s[i]),local_xy=xy[i].tolist(),returns=int(take.sum())))
axes[0,0].legend(fontsize=7)
fig.suptitle("Source review: actual ground points versus terrain samples; no route changes yet")
fig.tight_layout();fig.savefig(ROOT/"evidence/corridor/lidar-cliff-cross-sections.png")
(ROOT/"evidence/corridor/lidar-cliff-cross-sections.json").write_text(json.dumps(dict(inputs=ground.inputs,sections=records),indent=2))
print(records,flush=True)
