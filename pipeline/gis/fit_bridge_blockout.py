"""Fit main Lions Gate silhouettes to 2022 returns; retain measurement residuals."""
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[2] / 'cache/matplotlib'))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter1d
from acquire_sources import ROOT, digest, save_json

source = ROOT / "data/derived/lions-gate-survey.npz"
survey = np.load(source)
p = survey["xyz"].astype(float)
structural = survey["classification"] == 1
seeds = np.array([[206., 1220.], [445., 1625.]])
centres = []
for seed in seeds:
    top = p[(np.linalg.norm(p[:,:2]-seed, axis=1)<30)&(p[:,2]>121)]
    centres.append((top[:,:2].min(0)+top[:,:2].max(0))*.5)
a,b = np.array(centres)
d = (b-a)/np.linalg.norm(b-a)
n = np.array([-d[1], d[0]])
q = np.column_stack(((p[:,:2]-a)@d, (p[:,:2]-a)@n, p[:,2]))
span = np.linalg.norm(b-a)
stations = np.arange(-187.147, span+187.004, 2.)
deck = []
for s in stations:
    values = q[(abs(q[:,0]-s)<1)&(abs(q[:,1])<3)&(q[:,2]>35)&(q[:,2]<85),2]
    deck.append(np.percentile(values,20) if len(values)>10 else np.nan)
deck = np.asarray(deck)
valid = np.isfinite(deck)
deck = np.interp(stations,stations[valid],deck[valid])
deck = gaussian_filter1d(deck, 2)
# Fit each suspension span's upper cable envelope. Road vehicles and hangers
# fall below it. A fit residual is retained; this is not an as-built CAD model.
cable_fits = []
for lo,hi in [(-187.147,0),(0,span),(span,span+187.004)]:
    x, z = [], []
    for s in np.arange(lo+5,hi-5,3):
        level = np.interp(s,stations,deck)
        take = structural&(abs(q[:,0]-s)<1.2)&(abs(q[:,1])>5.2)&(abs(q[:,1])<7)&(q[:,2]>level+4)&(q[:,2]<122)
        values = q[take,2]
        if len(values)>5: x.append(s); z.append(np.percentile(values,95))
    coef = np.polyfit(x,z,2)
    residual = np.asarray(z)-np.polyval(coef,x)
    keep = abs(residual-np.median(residual))<2
    coef = np.polyfit(np.asarray(x)[keep],np.asarray(z)[keep],2)
    cable_fits.append(dict(start_m=lo,end_m=hi,polynomial=coef.tolist(),
        sample_station_m=x,sample_height_m=z,residual_p95_m=float(np.percentile(abs(np.asarray(z)[keep]-np.polyval(coef,np.asarray(x)[keep])),95))))
# Fit the visible steel-leg taper away from deck and horizontal-brace levels.
# The outer half of each transverse band suppresses diagonal braces.
towers=[]
for s in [0,span]:
    near=q[abs(q[:,0]-s)<4]
    tops=near[near[:,2]>120]
    levels=[]
    for z in [20,30,45,70,85,105,112]:
        band=near[(abs(near[:,2]-z)<.3)&(abs(near[:,1])>5)&(abs(near[:,1])<14)]
        outer=band[abs(band[:,1])>np.percentile(abs(band[:,1]),50)]
        if len(band): levels.append(dict(height_m=z,half_width_m=float(np.percentile(abs(band[:,1]),65)),
            along_depth_m=float(np.percentile(outer[:,0],95)-np.percentile(outer[:,0],5)),
            return_count=len(band)))
    towers.append(dict(station_m=s,top_m=float(np.percentile(tops[:,2],99)),
        top_half_width_m=float((tops[:,1].max()-tops[:,1].min())*.5),samples=levels,
        leg_centre_polynomial=np.polyfit([row['height_m'] for row in levels],[row['half_width_m'] for row in levels],1).tolist(),
        leg_depth_polynomial=np.polyfit([row['height_m'] for row in levels],[row['along_depth_m'] for row in levels],1).tolist()))
deck_at_return=np.interp(q[:,0],stations,deck)
deck_take=structural&(q[:,0]>30)&(q[:,0]<span-30)&(abs(q[:,2]-deck_at_return)<.25)
deck_edges=np.percentile(q[deck_take,1],[.1,99.9])
cable_take=structural&(q[:,0]>40)&(q[:,0]<span-40)&(q[:,2]>deck_at_return+8)&(abs(q[:,1])<7)
cable_half_width=float(np.median(abs(q[cable_take,1])))
foundations=[]
for station in [0.,float(span)]:
    sides=[]
    for sign in [-1,1]:
        centre=sign*(43.273-20.)*.5
        radius=np.hypot(q[:,0]-station,q[:,1]-centre)
        levels=[]
        for seed in [3.45,6.1,7.4]:
            take=(radius<9.5)&(abs(q[:,2]-seed)<.2)&np.isin(survey['classification'],[1,2])
            if take.sum()<100:raise RuntimeError('Insufficient pedestal returns')
            levels.append(dict(height_m=float(np.median(q[take,2])),
                radius90_m=float(np.percentile(radius[take],90)),returns=int(take.sum()),
                extraction_seed_height_m=seed))
        sides.append(dict(transverse_centre_m=centre,levels=levels))
    foundations.append(dict(station_m=station,sides=sides,
        method='Median observed top bands; P90 radius is a blockout envelope, not the exact masonry edge',
        south_collar_width_m=43.273 if station==0 else None,
        base_below_visibility_m=-1. if station==0 else 2.5,
        hidden_base_measured=False))
result=dict(source_sha256=digest(source),axis_origin_local_m=a.tolist(),axis_unit=d.tolist(),
    transverse_unit=n.tolist(),tower_span_m=float(span),
    drawing_main_span_m=472.427,span_difference_m=float(span-472.427),
    drawing_side_spans_m=[187.147,187.004],
    drawing_reference="BC 2018 risk assessment, PDF p29 / report Figure 2-3",
    deck_edges_transverse_m=deck_edges.tolist(),roadway_width_m=10.7,
    roadway_width_reference='BC 2018 report section 3.1; excludes outside walkways',
    cable_half_width_m=cable_half_width,
    simplified_dimensions=dict(cable_radius_m=.25,hanger_radius_m=.05,deck_thickness_m=.6,
        transverse_leg_width_m=1.3,brace_width_m=.65),
    simplification_note='Member thicknesses above are visual blockout assumptions, not survey controls. Tower axes, taper, top, deck edges/profile and cable line use measured returns.',
    stations_m=stations.tolist(),deck_heights_m=deck.tolist(),cable_fits=cable_fits,towers=towers,foundations=foundations,
    blockout_only=True,accepted=False,
    limits="Tower centres use observed top envelopes. Deck fit includes measurement occlusion and vehicles. Member thickness, hangers, foundation contours and north viaduct require separate review. No bridge riding surface is released.")
save_json(ROOT/"manifests/lions-gate-blockout.json",result)
fig,axes=plt.subplots(2,1,figsize=(14,9),dpi=150)
take=(np.arange(len(q))%12==0)&(q[:,2]>10)
axes[0].scatter(q[take,0],q[take,2],s=.1,c=q[take,1],cmap="coolwarm",vmin=-15,vmax=15)
axes[0].plot(stations,deck,"k",lw=1,label="Deck profile fit")
for fit in cable_fits:
    x=np.linspace(fit['start_m'],fit['end_m'],250)
    axes[0].plot(x,np.polyval(fit['polynomial'],x),lw=1)
axes[0].set(xlabel="Distance along bridge (m)",ylabel="CGVD2013 height (m)",ylim=(0,130))
axes[0].legend()
for tower in towers:
    t=abs(q[:,0]-tower['station_m'])<3
    axes[1].scatter(q[t,1],q[t,2],s=.25,label=f"Tower at {tower['station_m']:.2f}m")
axes[1].set(xlabel="Transverse distance (m)",ylabel="CGVD2013 height (m)",xlim=(-25,25),ylim=(0,130))
axes[1].legend();fig.tight_layout()
fig.savefig(ROOT/"evidence/landmarks/lions-gate-survey-fit.png")
print(json.dumps({k:result[k] for k in ['axis_origin_local_m','axis_unit','tower_span_m','span_difference_m','towers']},indent=2))
print('Cable fit P95 residuals', [x['residual_p95_m'] for x in cable_fits])
