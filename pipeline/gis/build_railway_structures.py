"""Open station/queue roofs and rounded Cob House from identified sources."""
import json
import numpy as np
from shapely.geometry import Polygon
import build_named_feature_blockouts as g
from build_lagoon_structures import prism
from build_route_sculpture_blockouts import tube
from named_roof_planes import fit_major_planes
from review_siwash_approach import TerrainQuery
from acquire_sources import save_json,digest

ROOT=g.ROOT
TENDER='https://bids.vancouver.ca/bidopp/ITT/ITT-PS20150687.htm'
COB='https://stanleyparkecology.ca/about-stanley-park-ecology/cob-house/'

def station():
    fid='SP_train';q,c=g.survey('train-plaza');s=q[(c==6)&(q[:,0]>647)&(q[:,0]<669)&(q[:,1]>-94)&(q[:,1]<-76)]
    _,review,_=fit_major_planes(s,min_support=100,max_planes=4);origin=np.array(review['coordinate_origin_xy_m']);queue,p1,p2=[np.array(p['coefficients_local']) for p in review['planes']]
    delta=p1-p2;centre=origin-delta[2]*delta[:2]/(delta[:2]@delta[:2]);v=delta[:2]/np.linalg.norm(delta[:2]);u=np.array([v[1],-v[0]])
    terrain=TerrainQuery([644,-99,674,-73]);height=lambda xy,p:(xy-origin)@p[:2]+p[2]
    # Two independently measured roof planes meet at their shared ridge.
    for i,(left,right,p) in enumerate([(-2.7,0,p1),(0,2.7,p2)]):
        xy=np.array([centre+u*a+v*b for a,b in [(-5.9,left),(5.9,left),(5.9,right),(-5.9,right)]])
        h=height(xy,p);prism(f'SM_RailStation_GableRoof_{i}',xy,h-.22,h,'roof',fid)
    for i,a in enumerate([-4.82,0,4.82]):
        for j,b in enumerate([-1.83,1.83]):
            xy=centre+u*a+v*b;p=p1 if b<0 else p2;top=float(height(xy,p))-.22;low=float(terrain.height(xy))-.12
            # Square wood-clad columns, not an inferred closed facade.
            square=np.array([xy+u*x+v*y for x,y in [(-.13,-.13),(.13,-.13),(.13,.13),(-.13,.13)]])
            prism(f'SM_RailStation_Column_{i}_{j}',square,low,top,'timber',fid)
    for j,b in enumerate([-1.83,1.83]):
        xy=np.array([centre+u*a+v*w for a,w in [(-5.45,b-.12),(5.45,b-.12),(5.45,b+.12),(-5.45,b+.12)]])
        h=height(xy,p1 if b<0 else p2)-.22;prism(f'SM_RailStation_EaveBeam_{j}',xy,h-.28,h,'timber',fid)
    # The queue shelter is skewed relative to the gable, as in A2.2/A2.3.
    angle=np.deg2rad(-10);R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]]);qu=R@u;qv=R@v;start=centre+v*1.60
    xy=np.array([start+qu*a+qv*b for a,b in [(-5.35,0),(5.35,0),(5.35,11.289),(-5.35,11.289)]])
    h=height(xy,queue);prism('SM_RailQueue_LowRoof',xy,h-.16,h,'steel',fid)
    for i,a in enumerate([-4.95,-1.65,1.65,4.95]):
        for j,b in enumerate([2.2,6.245,10.29]):
            xy=start+qu*a+qv*b;top=float(height(xy,queue))-.16;low=float(terrain.height(xy))-.12
            tube(f'SM_RailQueue_Column_{i}_{j}',[*xy,low],[*xy,top],.07,'steel',fid)
    g.feature(fid,'Miniature Railway open station and waiting shelter',[TENDER,'data/references/station-tender-2015-amd1.pdf','https://www.rjc.ca/project-details/stanley-park-mini-train-station-and-waiting.html','manifests/named-train-plaza-survey.json','evidence/corridor/ortho-utm/named-train-buildings.json'],
        dict(centre_local_m=centre.tolist(),source_roof_ids=['lidar2022_490000_5461000_2'],roof_plane_review=review,terrain_inputs=terrain.inputs,
             source_identity='2015 context A1.1 places the station west of washrooms and northwest of the former Contact Barn/current Cafe. A2.2/A2.3 show the gable and skewed open queue shed; 2022 source returns retain both roof forms.'),
        dict(gable_length_m=11.8,gable_width_m=5.4,roof_thickness_m=.22,queue_width_m=10.7,queue_length_m=11.289,queue_skew_degrees=10,
             column_layout='2015 drawing spacing, aligned to 2022 roof forms; dimensions are design-reference constraints, not certified as-built measurements',ground_contact='Columns end 0.12 m below current exported terrain. No new platform floor, gate or inferred exterior wall is added.'),
        'M1 open structural massing. 2015 tender is not an as-built drawing: eaves/column details, exact pavement grades, railings, queues, platform edge, track operation and station signage remain unfinished. Source roof fit has canopy/multi-return uncertainty; no public train boarding simulation.', ['lidar2022_490000_5461000_2'])

def cob_house():
    fid='SP_cob_house';q,c=g.survey('train-plaza-south');s=q[(q[:,0]>655.5)&(q[:,0]<660.9)&(q[:,1]>-136.4)&(q[:,1]<-130.5)&(q[:,2]>27.15)&(q[:,2]<27.85)]
    centre=np.array([658.05,-133.62]);uv=s[:,:2]-centre;A=np.c_[uv,np.ones(len(s))];mask=np.ones(len(s),bool)
    for _ in range(4):
        plane=np.linalg.lstsq(A[mask],s[mask,2],rcond=None)[0];res=s[:,2]-A@plane;mask=abs(res)<.10
    terrain=TerrainQuery([651,-140,664,-126]);theta=np.arange(40)*2*np.pi/40;rotation=np.deg2rad(-20);R=np.array([[np.cos(rotation),-np.sin(rotation)],[np.sin(rotation),np.cos(rotation)]])
    roof=centre+(np.c_[np.cos(theta)*2.6,np.sin(theta)*2.85]@R.T);wall=centre+(np.c_[np.cos(theta)*1.85,np.sin(theta)*2.10]@R.T)
    roofh=(roof-centre)@plane[:2]+plane[2];walltop=(wall-centre)@plane[:2]+plane[2]-.23;low=np.array([terrain.height(x) for x in wall])-.15
    g.rings('SM_CobHouse_StoneFoot', [np.c_[wall,low],np.c_[wall,low+.48]],'stone',fid);g.ASSETS[-1]['collision']='complex'
    g.rings('SM_CobHouse_CurvedEarthShell',[np.c_[wall*.999+centre*.001,low+.3],np.c_[wall,walltop]],'earth',fid);g.ASSETS[-1]['collision']='complex'
    g.rings('SM_CobHouse_WideLivingRoof',[np.c_[roof,roofh-.23],np.c_[roof,roofh]],'roof_green',fid);g.ASSETS[-1]['collision']='complex'
    # A closed service-window panel records the primary photo's useful scale
    # cue without claiming a surveyed opening or interior access.
    outward=np.array([-1.,0.]);tangent=np.array([0.,1.]);p=centre+outward*1.82
    window=np.array([p+tangent*a+outward*b for a,b in [(-.55,0),(.55,0),(.55,.06),(-.55,.06)]])
    base=float(np.median(low));prism('SM_CobHouse_ServiceShutter',window,base+.95,base+2.0,'timber',fid)
    g.feature(fid,'Cob House / earthen popcorn stand',[COB,TENDER,'data/references/station-tender-2015-amd1.pdf','manifests/named-train-plaza-south-survey.json','evidence/corridor/ortho-utm/named-train-buildings.json'],
        dict(centre_local_m=centre.tolist(),roof_returns=len(s),roof_inliers=int(mask.sum()),roof_plane=plane.tolist(),roof_median_residual_m=float(np.median(abs(res[mask]))),terrain_inputs=terrain.inputs,
             source_identity='2015 A1.1 labels Cob Hut east of the station and west of the former Contact Barn. Isolated curved 2022 roof near [658,-134] agrees with that context. Current operator photo shows curved earthen walls, broad living roof and raised stone base.'),
        dict(roof_radii_m=[2.6,2.85],wall_radii_m=[1.85,2.10],roof_thickness_m=.23,roof_angle_degrees=-20,base_height_m=.48,
             outline='Regularized ellipse within the observed sparse roof envelope. The canopy masks the east rim; wall offset, service shutter facing/size and foundation are explicit M1 estimates.'),
        'Distinct small curved exterior and living-roof massing. No interior, bottle-window artwork, earth texture, individual stonework or exact serving aperture. Position is supported by two survey/context sources, while footprint regularization and hidden wall geometry remain provisional.')

def main():
    g.OUT=ROOT/'data/derived/railway-structures';g.OUT.mkdir(exist_ok=True);g.ASSETS.clear();g.FEATURES.clear();g.COLORS.update(earth=[.49,.43,.28],roof_green=[.27,.35,.16],timber=[.39,.28,.16])
    station();cob_house()
    for a in g.ASSETS:a['collision_reason']='Closed individual member only; open station gaps stay open. Exact ground contact and route clearance require live inspection.'
    data=dict(schema_version=1,revision='railway-structures-m1-r1',assets=g.ASSETS,features=g.FEATURES,acceptance=False,source_period='2022 survey/ortho and 2015 station tender; current Cob House operator identity',target_period='September 2026',
        reference_rights='City survey derivatives OGL-Vancouver. Tender and operator images are reference only, not embedded or licensed for public distribution. No artwork texture is reproduced.')
    save_json(ROOT/'manifests/railway-structure-blockouts.json',data);print(json.dumps(dict(assets=len(g.ASSETS),sha256=digest(ROOT/'manifests/railway-structure-blockouts.json'))))

if __name__=='__main__':main()
