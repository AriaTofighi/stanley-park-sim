"""Separate M1 batch: Hollow Tree, Siwash lookout, Third Beach facilities.

No live application operation. Sources determine the unique form and location;
unmeasured shell thickness, roof thickness and enclosure details stay explicit.
"""
import json
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import Delaunay
import shapely
from shapely.geometry import Polygon, LineString
from shapely import contains_xy

import build_named_feature_blockouts as geom
from named_roof_planes import fit_major_planes, rebuild_planar_patches
from acquire_sources import digest, save_json

ROOT=geom.ROOT
OUT=ROOT/'data/derived/west-landmarks'
MAP='https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf'
HT='https://apt.memberclicks.net/assets/docs/Kalman-42-4.pdf'
MILITARY='https://www.vancouvergunners.ca/uploads/2/5/3/2/25322670/photographic_record_of_historical_remains.pdf'


def closed(name,rows,material,fid,collision='complex'):
    geom.rings(name,rows,material,fid)
    geom.ASSETS[-1]['collision']=collision


def robust_plane(points,scale=.04):
    origin=points[:,:2].mean(0)
    a=np.column_stack((points[:,:2]-origin,np.ones(len(points))))
    fit=least_squares(lambda t:a@t-points[:,2],[0,0,np.median(points[:,2])],loss='soft_l1',f_scale=scale)
    return origin,fit.x,dict(returns=len(points),median_abs_residual_m=float(np.median(abs(fit.fun))),
        p95_abs_residual_m=float(np.percentile(abs(fit.fun),95)),independent_accuracy=False)


def hollow_tree():
    fid='SP_hollow_tree';q,c=geom.survey('hollow-tree');centre=np.array([-766.3,484.8])
    take=(np.linalg.norm(q[:,:2]-centre,axis=1)<3)&(q[:,2]>52)&(q[:,2]<64)
    shell=q[take];ground=q[(c==2)&(np.linalg.norm(q[:,:2]-centre,axis=1)<4)]
    ground_origin,ground_plane,ground_review=robust_plane(ground)
    top=float(np.percentile(shell[:,2],99.8));base=float(ground_plane[2]-.15)
    angular=np.arctan2(shell[:,1]-centre[1],shell[:,0]-centre[0]);radial=np.linalg.norm(shell[:,:2]-centre,axis=1)
    levels=np.linspace(base,top,9);sector_bounds=np.linspace(np.deg2rad(5),np.deg2rad(315),8)
    authored=[];unsupported=0
    for part,(start,end) in enumerate(zip(sector_bounds[:-1],sector_bounds[1:])):
        theta=np.linspace(start+.004,end-.004,5)
        radii=[];tops=[]
        for angle in theta:
            da=abs(np.angle(np.exp(1j*(angular-angle))))
            top_points=shell[(da<.19)&(radial>1)&(radial<2.7)]
            tops.append(float(np.percentile(top_points[:,2],98)) if len(top_points)>4 else top)
        tops=np.clip(tops,top-2.4,top)
        rows=[]
        for level in levels:
            rr=[]
            for angle in theta:
                da=abs(np.angle(np.exp(1j*(angular-angle))))
                selected=radial[(da<.22)&(abs(shell[:,2]-max(level,53.6))<1.)]
                if len(selected)<3:
                    selected=radial[da<.26];unsupported+=1
                radius=float(np.percentile(selected,80)) if len(selected) else 1.7
                radius=np.clip(radius,1.05,2.65)
                if level<53.6:radius*=1+.08*(53.6-level)/3
                rr.append(radius)
            rr=np.array(rr);fraction=(level-base)/(top-base);z=base+fraction*(tops-base)
            outer=np.column_stack((centre+rr[:,None]*np.column_stack((np.cos(theta),np.sin(theta))),z))
            inner=np.column_stack((centre+(rr-.32)[:,None]*np.column_stack((np.cos(theta),np.sin(theta))),z))
            rows.append(np.vstack((outer,inner[::-1])))
        # A sector cross section follows the outer arc CCW and the inner arc CW.
        closed(f'SM_HollowTree_Shell_{part:02d}',rows,'old_cedar',fid)
        cap=np.array(rows[-1]);closed(f'SM_HollowTree_TopFlashing_{part:02d}',[cap,cap+[0,0,.025]],'flashing',fid,'none')
        authored.extend(np.array(rows).reshape(-1,3))
    authored=np.asarray(authored)
    geom.feature(fid,'Hollow Tree',[MAP,'https://vancouver.ca/parks-recreation-culture/trees.aspx',HT,
        'manifests/named-hollow-tree-survey.json','evidence/corridor/ortho-utm/named-hollow-tree.json'],
        dict(centre_local_m=centre.tolist(),source_shell_returns=len(shell),ground_fit=ground_review,
             source_top_h_m=top,ground_height_m=float(ground_plane[2]),source_height_m=top-ground_plane[2],
             shell_bounds_local_m=[authored.min(0).tolist(),authored.max(0).tolist()]),
        dict(shell_thickness_m=.32,entrance_open_sector_degrees=[315,365],segment_count=7,
             shell_method='Seven coarse vertical sectors fit to radial source bands; gaps and correspondence to exact wood segments are estimates',
             insufficient_local_bins_using_same_angle_other_heights=unsupported,
             base_flare='Lower unsupported section extrapolates nearest measured shell band by at most 8 percent per 3 m',
             top_flashing_thickness_m=.025),
        'Recognizable hollow dead-cedar shell, no foliage. East/southeast entrance remains open. Wall thickness, individual cracks, braces, bark and exact cavity are unfinished. The 2011 conservation photos confirm the open shell and top flashing; City 2022 returns set present size. No independent accuracy or runtime acceptance.')


def siwash_lookout():
    fid='SP_siwash_lookout';q,c=geom.survey('siwash-lookout')
    # Hand trace of the actual concrete roof edge in the retained City ortho.
    pix=np.array([[244,236],[257,229],[274,231],[288,239],[323,264],[293,301],[282,311],[245,284],[237,270],[238,251]],float)
    xy=np.column_stack((-948.12+(pix[:,0]+.5)*.075,680.9-(pix[:,1]+.5)*.075))
    poly=shapely.orient_polygons(Polygon(xy));xy=np.array(poly.exterior.coords)[:-1]
    selected=q[contains_xy(poly.buffer(.1),q[:,0],q[:,1])&(q[:,2]>23.05)&(q[:,2]<23.3)]
    origin,plane,review=robust_plane(selected,.025);height=lambda p:(p-origin)@plane[:2]+plane[2]
    upper=np.column_stack((xy,height(xy)));lower=upper-[0,0,.25]
    closed('SM_SiwashLookout_ConcreteRoof',[lower,upper],'concrete',fid)
    # Keep the seaward searchlight opening visible. The rear masonry and roof
    # slab are source-identified, but opening/section dimensions are estimates.
    centre=np.array(poly.centroid.coords[0]);front=np.array([-1.,1.]);entry=np.array([1.,-1.]);rail_count=0
    rail_edges=[((a+b)/2-centre)@entry<=1.8 for a,b in zip(xy,np.roll(xy,-1,axis=0))]
    for i,(a,b) in enumerate(zip(xy,np.roll(xy,-1,axis=0))):
        mid=(a+b)/2;za,zb=height(np.array([a,b]));normal=mid-centre
        front_side=normal@front>0
        # Build a low curved sill at the seaward opening and full rear walls.
        top_a=za-.25 if not front_side else za-2.15
        top_b=zb-.25 if not front_side else zb-2.15
        ground=float(np.median(q[(c==2)&(np.linalg.norm(q[:,:2]-mid,axis=1)<2.5),2]))
        if not np.isfinite(ground):ground=float(geom.HEIGHT([[mid[1],mid[0]]])[0])
        bottom=min(ground-.15,top_a-.25,top_b-.25)
        edge=(b-a);inside=np.array([-edge[1],edge[0]])/np.linalg.norm(edge)*.25
        lower_ring=[[ *a,bottom],[*b,bottom],[*(b+inside),bottom],[*(a+inside),bottom]]
        upper_ring=[[ *a,top_a],[*b,top_b],[*(b+inside),top_b],[*(a+inside),top_a]]
        closed(f'SM_SiwashLookout_ShelterWall_{i:02d}',[lower_ring,upper_ring],'concrete',fid)
        if normal@entry>1.8:continue
        for h in [.56,1.08]:
            geom.beam(f'SM_SiwashLookout_Rail_{i:02d}_{int(h*100)}',np.r_[a,za+h],np.r_[b,zb+h],.065,'steel',fid)
            geom.ASSETS[-1]['collision']='complex';rail_count+=1
        geom.beam(f'SM_SiwashLookout_Post_{i:02d}',np.r_[a,za],np.r_[a,za+1.10],.08,'steel',fid)
        geom.ASSETS[-1]['collision']='complex'
        if not rail_edges[(i+1)%len(xy)]:
            geom.beam(f'SM_SiwashLookout_EndPost_{i:02d}',np.r_[b,zb],np.r_[b,zb+1.10],.08,'steel',fid)
            geom.ASSETS[-1]['collision']='complex'
    geom.feature(fid,'Siwash Rock lookout / former No. 6 searchlight shelter',
        [MAP,'https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx',MILITARY,
         'https://www.vancouvergunners.ca/uploads/2/5/3/2/25322670/stanleypark_docent_package_as_at_27aug_2021.pdf',
         'manifests/named-siwash-lookout-survey.json','evidence/corridor/ortho-utm/named-siwash-lookout.json'],
        dict(centre_local_m=centre.tolist(),roof_outline_local_m=xy.tolist(),roof_area_m2=poly.area,
             roof_plane_origin_m=origin.tolist(),roof_plane=plane.tolist(),roof_fit=review),
        dict(outline_trace_uncertainty_m=.3,roof_thickness_m=.25,wall_thickness_m=.25,rail_height_m=1.10,
             rail_section_m=.065,post_section_m=.08,opening_height_below_roof_m=2.15,
             body='Rear and side wall envelope to nearby ground returns; curved seaward window dimensions not measured'),
        'Concrete deck form and height are source-backed. Rail details, window/sill height, wall base and approach transition are blockout estimates. Upper public approach needs terrain/contact review; do not mark this asset walkable from a successful import.')


def third_beach():
    fid='SP_third_beach';q,c=geom.survey('third-beach')
    record=next(x for x in json.loads((ROOT/'data/derived/cover-blockout.json').read_text())['buildings'] if x['id']=='lidar2022_488000_5461000_1')
    polygon=Polygon(record['outline']).buffer(.05)
    q=q[(c==6)&contains_xy(polygon,q[:,0],q[:,1])]
    cell=np.floor(q[:,:2]/.5).astype(int);keys,inv=np.unique(cell,axis=0,return_inverse=True)
    vertices=np.array([np.median(q[inv==k],axis=0) for k in range(len(keys))])
    vertices,review,labels=fit_major_planes(vertices,min_support=45,max_planes=10)
    faces=Delaunay(vertices[:,:2]).simplices
    edge=np.linalg.norm(vertices[faces][:,:,:2]-np.roll(vertices[faces][:,:,:2],1,axis=1),axis=2)
    faces=faces[(edge.max(1)<1.75)&contains_xy(polygon,vertices[faces,:2].mean(1)[:,0],vertices[faces,:2].mean(1)[:,1])]
    vertices,faces,steps,step_faces,boundary=rebuild_planar_patches(vertices,faces,labels,review)
    geom.mesh('SM_ThirdBeach_FacilitiesRoofSurvey',vertices,faces,'roof',fid)
    if len(step_faces):geom.mesh('SM_ThirdBeach_RoofStepClosures',steps,step_faces,'wall',fid)
    walls=[];wall_faces=[]
    for a,b in boundary:
        base=geom.HEIGHT(np.array([a,b])[:,[1,0]]);base=np.minimum(base,np.array([a[2],b[2]])-.25)
        n=len(walls);walls.extend([a,b,[b[0],b[1],base[1]],[a[0],a[1],base[0]]]);wall_faces.extend([(n+3,n+2,n+1),(n+3,n+1,n)])
    # Preserve actual open paths where a roof-edge extrusion could be an eave.
    ped=json.loads((ROOT/'data/routes/derived/pedestrian-network.json').read_text())
    corridors=shapely.unary_union([LineString(e['coordinates_local_xy_m']).buffer(e['width_m']/2) for e in ped['edges'] if e['render_candidate']])
    panels=np.array(walls).reshape(-1,4,3);clear=[];conflict=[]
    for panel in panels:
        (conflict if LineString(panel[:2,:2]).intersects(corridors) else clear).append(panel)
    for selected,suffix,collision in [(clear,'','complex'),(conflict,'_PathConflict','none')]:
        if not selected:continue
        vv=np.array(selected).reshape(-1,3);ff=[t for n in range(0,len(vv),4) for t in [(n+3,n+2,n+1),(n+3,n+1,n)]]
        geom.mesh('SM_ThirdBeach_FacilitiesWallsReview'+suffix,vv,ff,'wall',fid,collision=collision)
    geom.feature(fid,'Third Beach concession and washroom building',
        [MAP,'https://vancouver.ca/parks-recreation-culture/third-beach.aspx',
         'https://vancouver.ca/parks-recreation-culture/dining-in-stanley-park.aspx',
         'manifests/named-third-beach-survey.json','evidence/corridor/ortho-utm/named-third-beach.json'],
        dict(centre_local_m=np.mean(vertices[:,:2],axis=0).tolist(),source_roof_ids=[record['id']],
             roof_returns=len(q),sampling_m=.5,plane_review=review),
        dict(walls='Roof-edge extrusion to City DTM; facade footprint, doors and eaves not measured',
             facade_panels_with_contact=len(clear),facade_panels_withheld_at_public_paths=len(conflict)),
        'The distinct angled facility roof is individually identified. Forecourt, stairs, parking, beach access and exact facades remain unfinished; this building alone does not complete the Third Beach public-space group.',[record['id']])


def main():
    OUT.mkdir(exist_ok=True);geom.OUT=OUT;geom.ASSETS.clear();geom.FEATURES.clear()
    geom.COLORS.update(old_cedar=[.28,.25,.20],flashing=[.60,.60,.56])
    hollow_tree();siwash_lookout();third_beach()
    for asset in geom.ASSETS:
        asset['collision_reason']='Explicit surface or source-located structure. Estimated contact dimensions are recorded per feature; live contact acceptance remains false.' if asset['collision']=='complex' else 'Upper roof detail; contact handled by the structural surface or facade.'
        if asset['name'].endswith('_PathConflict'):
            asset['collision_reason']='Roof-edge extrusion intersects a mapped public path. It may be an eave or doorway; retain the visual panel but do not block passage without ground reference.'
    data=dict(schema_version=1,revision='west-m1-r1',assets=geom.ASSETS,features=geom.FEATURES,
        source_period='City survey 2022-09-07/09; ortho 2022-06-06/07-01; dated primary identity/form references',
        target_period='September 2026',acceptance=False,reference_rights='City survey/ortho derivatives OGL-Vancouver. Published photos, conservation drawings and military-history PDFs are reference only; exclude from runtime/distribution.',
        input_hashes={f'manifests/named-{x}-survey.json':digest(ROOT/f'manifests/named-{x}-survey.json') for x in ['hollow-tree','siwash-lookout','third-beach']})
    save_json(ROOT/'manifests/west-landmark-blockouts.json',data)
    print(json.dumps(dict(features=len(geom.FEATURES),assets=len(geom.ASSETS),triangles=sum(a['triangles'] for a in geom.ASSETS))))


if __name__=='__main__':main()
