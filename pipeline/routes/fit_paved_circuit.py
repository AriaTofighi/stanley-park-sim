"""Fit an inspectable pavement proposal to measured ground, not the rough DTM.

This is constrained surface fitting, not an automatic acceptance of lane limits.
Every correction is retained against the unchanged City source centre line.
"""
import json
import os
from pathlib import Path
import sys
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter
from numpy.lib.stride_tricks import sliding_window_view

from ground_reference import ROOT, GroundReference, circuit_samples
sys.path.insert(0,str(ROOT/"pipeline/gis"))
from acquire_sources import digest,save_json

os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"tmp/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    ground=GroundReference()
    s,xy,tangent,normal=circuit_samples()
    print("Measured corridor points",len(ground.points),flush=True)
    overrides=json.loads((ROOT/'manifests/pavement-review-overrides.json').read_text())
    offsets=np.arange(-26.5,9.01,.25)
    probes=xy[:,None,:]+normal[:,None,:]*offsets[None,:,None]
    z,distance=ground.nearest_height(probes.reshape(-1,2),count=8,radius=.8)
    z=z.reshape(len(s),-1);distance=distance.reshape(z.shape)
    # A full 3m cross-section must fit a plane. This is the current lane-width
    # proposal, explicitly awaiting orthophoto lane-edge checks.
    windows=sliding_window_view(z,13,axis=1)
    cross=np.linspace(-1.5,1.5,13)
    width=np.full(len(s),3.)
    lane_limits=[(2980,3180,-2.,.5,2.5),(6640,6740,.5,2.,2.)]
    for lo,hi,omin,omax,w in lane_limits:width[(s>=lo)&(s<=hi)]=w
    mask=(abs(cross[None,None,:])<=width[:,None,None]/2).astype(float)
    missing=(np.isnan(windows)*mask).sum(axis=2)
    value=np.nan_to_num(windows)
    centre=(value*mask).sum(axis=2)/mask.sum(axis=2)
    slope=(value*cross*mask).sum(axis=2)/(np.square(cross)*mask).sum(axis=2)
    residual=np.sqrt((np.square(value-centre[:,:,None]-slope[:,:,None]*cross)*mask).sum(axis=2)/mask.sum(axis=2))
    candidates=offsets[6:-6]
    cost=residual*30+np.abs(slope)*4+np.square(candidates[None,:])*.009
    cost += missing*20
    cost += np.maximum(abs(slope)-.1,0)*20
    # Colour is a supporting cue, not proof of pavement: discourage green turf.
    _,nearest=ground.tree.query(probes[:,6:-6,:].reshape(-1,2),workers=4)
    rgb=ground.colors[nearest].astype(float).reshape(len(s),len(candidates),3)
    if rgb.max(initial=0)>255:rgb/=257
    green=np.maximum(0,(rgb[:,:,1]-(rgb[:,:,0]+rgb[:,:,2])*.5)/255-.06)
    cost+=green*5
    allowed=np.broadcast_to((candidates>=-7.5)&(candidates<=7.5),cost.shape).copy()
    for area in overrides['surface_constraints']:
        rows=(s>=area['start_m'])&(s<=area['end_m'])
        lo,hi=area['offset_range_m']; low_z,high_z=area['height_range_m']
        allowed[rows]=(candidates[None,:]>=lo)&(candidates[None,:]<=hi)
        cost[rows]+=np.maximum(low_z-centre[rows],0)*200+np.maximum(centre[rows]-high_z,0)*200
    for lo,hi,omin,omax,w in lane_limits:
        rows=(s>=lo)&(s<=hi)
        allowed[rows]=(candidates[None,:]>=omin)&(candidates[None,:]<=omax)
    cost[~allowed]=1e6
    occluded=np.zeros(len(s),bool)
    for span in overrides['occluded_underpasses']:
        a,b=np.searchsorted(s,[span['start_m'],span['end_m']])
        occluded[a:b+1]=True
        # Freeze horizontal position to the source crossing in the blind span.
        # This is a recorded development interpolation, never a measured floor.
        cost[a:b+1]=np.square(candidates[None,:])*10
        centre[a:b+1]=np.linspace(np.nanmedian(centre[a-2:a]),np.nanmedian(centre[b+1:b+3]),b-a+1)[:,None]
    # Dynamic programming discourages sudden lateral/height jumps. It cannot
    # repair missing survey data, which stays explicitly flagged below.
    previous=cost[0].copy()
    parents=np.zeros(cost.shape,np.int16)
    horizontal=np.square(candidates[:,None]-candidates[None,:])*.5
    for i in range(1,len(s)):
        vertical=np.minimum(np.square(centre[i-1,:,None]-centre[i,None,:]),100)*16
        transition=previous[:,None]+horizontal+vertical
        parent=np.argmin(transition,axis=0)
        previous=cost[i]+transition[parent,np.arange(len(candidates))]
        parents[i]=parent
    choice=np.empty(len(s),np.int16);choice[-1]=np.argmin(previous)
    for i in range(len(s)-1,0,-1):choice[i-1]=parents[i,choice[i]]
    row=np.arange(len(s))
    offset=candidates[choice]
    raw_z=centre[row,choice];crossfall=slope[row,choice]
    fit_rms=residual[row,choice]
    valid=(missing[row,choice]==0)&(fit_rms<.12)&(abs(crossfall)<.15)&(~occluded)
    if valid.sum()<len(s)*.9:raise RuntimeError(f"Insufficient fit coverage: {valid.mean():.3f}")
    # Interpolation is for the development mesh only, with all affected sections
    # retained for review. Never turn this into an accuracy acceptance result.
    proposal_z=np.interp(s,s[valid],raw_z[valid])
    proposal_z=savgol_filter(median_filter(proposal_z,size=5,mode="wrap"),11,2,mode="wrap")
    smooth_offset=savgol_filter(median_filter(offset,size=5,mode="wrap"),15,2,mode="wrap")
    proposed_xy=xy+normal*smooth_offset[:,None]
    for axis in (0,1):proposed_xy[:,axis]=savgol_filter(proposed_xy[:,axis],7,2,mode="wrap")
    proposed_xy[-1]=proposed_xy[0];proposal_z[-1]=proposal_z[0]
    crossfall=savgol_filter(np.clip(crossfall,-.08,.08),11,2,mode="wrap")
    points=np.column_stack((proposed_xy,proposal_z))
    grade=np.diff(proposal_z)/np.maximum(np.linalg.norm(np.diff(proposed_xy,axis=0),axis=1),1e-5)
    issue=(~valid)|(np.abs(proposal_z-raw_z)>.15)
    groups=[]
    indices=np.flatnonzero(issue)
    for ids in np.split(indices,np.flatnonzero(np.diff(indices)>10)+1):
        if len(ids):groups.append(dict(start_m=float(s[max(0,ids[0]-5)]),end_m=float(s[min(len(s)-1,ids[-1]+5)]),
            bad_samples=int(len(ids)),source="Missing/non-planar returns or fit residual >0.15m; needs inspection"))
    out=ROOT/"data/derived/paved-circuit-proposal.npz"
    np.savez_compressed(out,chainage_source=s,source_xy=xy,xyz=points,offset_m=smooth_offset,
        raw_fit_height=raw_z,crossfall=crossfall,fit_rms=fit_rms,valid_fit=valid,needs_review=issue,occluded=occluded,width_m=width)
    save_json(ROOT/"manifests/paved-circuit-proposal.json",dict(schema_version=1,
        status="measured surface proposal; lane widths, local corrections and clearance require visual review",
        input_files=ground.inputs,origin_sha256=digest(ROOT/"manifests/world-origin.json"),
        source_route_sha256=digest(ROOT/"data/routes/derived/park_routes.json"),output_sha256=digest(out),
        vertical_datum="CGVD2013(CGG2013a), see each LiDAR conversion record",
        width_m=3.,width_accepted=False,source_sample_spacing_m=float(s[1]-s[0]),
        local_lane_constraints=[dict(source_start_m=a,source_end_m=b,offset_min_m=c,offset_max_m=d,development_width_m=e,
            evidence='evidence/corridor/ortho-utm/lumberman-walk-review.png' if a<4000 else 'evidence/corridor/ortho-utm/third-beach-gate-detail-review.png',
            status='Visual lane selection; exact boundaries and widths not accepted') for a,b,c,d,e in lane_limits],
        valid_fit_fraction=float(valid.mean()),review_areas=groups,
        smoothing="5m median; 11m quadratic height / 15m lateral fit; all >0.15m height changes retained as issues",
        correction_limits=dict(default_lateral_search_m=7.5,reviewed_maximum_seaward_search_m=25,physical_path_surface="separate mesh and collision"),
        review_overrides_sha256=digest(ROOT/'manifests/pavement-review-overrides.json'),
        occluded_underpasses=overrides['occluded_underpasses'],
        maximum_grade=float(np.max(abs(grade))),p99_grade=float(np.percentile(abs(grade),99)),
        source_geometry_unchanged=True,release_accepted=False))
    fig,axes=plt.subplots(3,1,figsize=(16,10),dpi=130)
    axes[0].plot(s,raw_z,lw=.5,label="measured local fit");axes[0].plot(s,proposal_z,lw=.7,label="pavement proposal")
    axes[0].set(ylabel="CGVD2013 height (m)",ylim=(0,15));axes[0].legend()
    axes[1].plot(s,smooth_offset,lw=.6);axes[1].set(ylabel="Lateral correction (m)")
    axes[2].plot(s,fit_rms,lw=.6);axes[2].set(ylabel="Plane fit RMS (m)",ylim=(0,.3),xlabel="Source circuit chainage (m)")
    for ax in axes:
        for g in groups:ax.axvspan(g["start_m"],g["end_m"],color="red",alpha=.12)
        ax.grid(alpha=.2)
    fig.suptitle("2022 LiDAR pavement proposal — red areas require source review")
    fig.tight_layout();fig.savefig(ROOT/"evidence/corridor/paved-circuit-fit.png")
    print(json.dumps(dict(valid_fraction=float(valid.mean()),review_areas=len(groups),max_grade=float(np.max(abs(grade))),p99_grade=float(np.percentile(abs(grade),99))),indent=2),flush=True)


if __name__=="__main__":main()
