"""Observed cedar-arch members with explicit occlusion and diameter limits."""
import json
import numpy as np
from scipy.optimize import least_squares
import build_named_feature_blockouts as geom
from acquire_sources import save_json,digest

ROOT=geom.ROOT


def log_mesh(name,a,b,radius):
    axis=np.asarray(b)-a;axis/=np.linalg.norm(axis)
    u=np.cross(axis,[0,0,1.])
    if np.linalg.norm(u)<.1:u=np.cross(axis,[1.,0,0])
    u/=np.linalg.norm(u);v=np.cross(axis,u);theta=np.arange(16)*2*np.pi/16
    cross=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v
    geom.rings(name,[p+radius*cross for p in [np.asarray(a),np.asarray(b)]],'cedar','SP_lumberman_arch')
    geom.ASSETS[-1]['collision']='complex'


def fit_axis(points,initial,bounds,radius,vertical=False):
    def line(t):
        if vertical:return np.array([t[0],t[2],7.]),np.array([t[1],t[3],1.])
        return np.array([908.,t[0],t[2]]),np.array([1.,t[1],t[3]])
    def residual(t):
        anchor,direction=line(t);direction/=np.linalg.norm(direction);q=points-anchor;s=q@direction
        return np.linalg.norm(q-s[:,None]*direction,axis=1)-radius
    result=least_squares(residual,initial,bounds=bounds,loss='soft_l1',f_scale=.05)
    return result.x,dict(returns=len(points),parameters=result.x.tolist(),radius_estimate_m=radius,
        median_abs_radial_residual_m=float(np.median(abs(result.fun))),p95_abs_radial_residual_m=float(np.percentile(abs(result.fun),95)),
        independent_accuracy=False,limitation='One-sided airborne returns do not constrain log diameter reliably. Radius is an explicit M1 estimate; axis fitted to the visible shell.')


def main():
    geom.OUT=ROOT/'data/derived/cedar-arch';geom.OUT.mkdir(exist_ok=True);geom.ASSETS.clear();geom.FEATURES.clear();geom.COLORS['cedar']=[.29,.27,.22]
    q,c=geom.survey('lumberman-arch');dx=q[:,0]-908
    selected=q[(q[:,0]>898)&(q[:,0]<917.8)&(abs(q[:,1]-(-2.1-.205*dx))<1)&(abs(q[:,2]-(9.4+.135*dx))<1)]
    t,main_review=fit_axis(selected,[-1.9,-.23,9.1,.14],([-2.8,-.35,8.8,.07],[-1,-.1,9.8,.24]),.65)
    x0,x1=np.percentile(selected[:,0],[.5,99.5]);main_axis=[np.array([x,t[0]+t[1]*(x-908),t[2]+t[3]*(x-908)]) for x in [x0,x1]]
    log_mesh('SM_LumbermanArch_MainLog',*main_axis,.65)
    support_reviews=[];axes=[main_axis]
    for index,(lo,hi) in enumerate([(-4.3,-2.5),(-6.4,-4.45)]):
        points=q[(q[:,0]>914)&(q[:,0]<917.8)&(q[:,1]>lo)&(q[:,1]<hi)&(q[:,2]>5.3)&(q[:,2]<9.4)]
        t,review=fit_axis(points,[916.6,-.25,(lo+hi)/2,-.1 if hi>-3 else .25],([915.5,-.55,lo,-.6],[917.3,.05,hi,.6]),.43,True)
        base=float(geom.HEIGHT([[t[2],t[0]]])[0])-.15;top=10.35
        ends=[np.array([t[0]+t[1]*(h-7),t[2]+t[3]*(h-7),h]) for h in [base,top]]
        log_mesh(f'SM_LumbermanArch_SupportLog_{index:02d}',*ends,.43);axes.append(ends);support_reviews.append(review)
    # The primary Parks Canada description identifies the western rock mound.
    # Only its low envelope is represented; canopy masks precise rock faces.
    centre=main_axis[0][:2];base=float(geom.HEIGHT([[centre[1],centre[0]]])[0])-.12;top=main_axis[0][2]-.45
    theta=np.arange(10)*2*np.pi/10
    rows=[np.column_stack((centre+np.column_stack((np.cos(theta),np.sin(theta)))*radius,np.full(10,h))) for radius,h in [(2.0,base),(1.45,(base+top)/2),(1.,top)]]
    geom.rings('SM_LumbermanArch_MoundEnvelope',rows,'stone','SP_lumberman_arch');geom.ASSETS[-1]['collision']='complex'
    geom.feature('SP_lumberman_arch',"Lumberman's Arch",[
        'https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf',
        'https://vancouver.ca/files/cov/MEMO-LumbermansArchClosureInspection-20190201.pdf',
        'https://stanleyparkecology.ca/wp-content/uploads/2021/07/ParksCanada_Commemorative-Integrity-Statement-2002.pdf',
        'https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId=99',
        'manifests/named-lumberman-arch-survey.json','evidence/corridor/ortho-utm/named-lumberman-wide.json'],
        dict(centre_local_m=((main_axis[0]+main_axis[1])/2)[:2].tolist(),main_observed_length_m=float(np.linalg.norm(main_axis[1]-main_axis[0])),
             source_fitted_member_axes_local_m=[[p.tolist() for p in a] for a in axes],main_fit=main_review,support_fits=support_reviews),
        dict(main_log_radius_m=.65,support_log_radius_m=.43,diameter_uncertainty_m='At least +/-0.3 m; underside is not resolved',
             western_mound_radius_m=[2,1],mound='Primary source confirms a rock mound; geometric envelope under canopy is estimated',
             eastern_support_top_h_m=10.35),
        'City 2022 returns identify the straight rising main log and two converging support traces. The official registry point was used only as a search aid. Partial airborne shells require estimated radii and end sections. The second horizontal member in the 2019 memo is not isolated; it is not fabricated or counted as complete. Bark, exact concrete/rock support and close structural detail remain unfinished.')
    for asset in geom.ASSETS:asset['collision_reason']='Source-located log or explicit support envelope; direct triangles preserve the arch opening. Public-path clearance and live contact remain to be checked.'
    data=dict(schema_version=1,revision='cedar-arch-m1-r1',source_period='City LiDAR September 2022; City ortho June/July 2022; dated identity references',target_period='September 2026',
        assets=geom.ASSETS,features=geom.FEATURES,acceptance=False,reference_rights='Survey/ortho derivatives: OGL-Vancouver. Primary documents and photographs: reference only; not distributed.',
        input_hashes={'manifests/named-lumberman-arch-survey.json':digest(ROOT/'manifests/named-lumberman-arch-survey.json')})
    save_json(ROOT/'manifests/cedar-arch-blockout.json',data)
    print(json.dumps(dict(assets=len(geom.ASSETS),triangles=sum(a['triangles'] for a in geom.ASSETS),main_fit=main_review,supports=support_reviews),indent=2))


if __name__=='__main__':main()
