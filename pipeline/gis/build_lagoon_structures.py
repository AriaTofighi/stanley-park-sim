"""Source-fitted Nature House/viewing deck and inactive Jubilee support."""
import json
import numpy as np
from shapely.geometry import Polygon
from shapely import contains_xy
from scipy.spatial import cKDTree
import build_named_feature_blockouts as g
from build_route_sculpture_blockouts import tube
from acquire_sources import save_json,digest

ROOT=g.ROOT
# City 2022 ortho traced outer deck, from west-front to east-front then rear.
NATURE_XY=np.array([[362.92,-912.97],[391.45,-902.94],[393.73,-909.32],[365.23,-919.36]])[::-1]

def nature_data():
    a,c=g.survey('nature-house-west');b,d=g.survey('nature-house-east');return np.vstack([a,b]),np.r_[c,d]

def nature_plane():
    q,c=nature_data();poly=Polygon(NATURE_XY);s=q[contains_xy(poly.buffer(-.6),q[:,0],q[:,1])&(q[:,2]>4.65)&(q[:,2]<5.1)]
    origin=NATURE_XY.mean(0);A=np.column_stack((s[:,:2]-origin,np.ones(len(s))));mask=np.ones(len(s),bool)
    for _ in range(4):
        coeff=np.linalg.lstsq(A[mask],s[mask,2],rcond=None)[0];res=s[:,2]-A@coeff;mask=abs(res)<.11
    return origin,coeff,dict(returns=len(s),inliers=int(mask.sum()),median_absolute_residual_m=float(np.median(abs(res[mask]))),p95_absolute_residual_m=float(np.percentile(abs(res[mask]),95)))

def prism(name,xy,low,high,material,fid):
    xy=np.array(Polygon(xy).exterior.coords)[:-1]
    if not Polygon(xy).exterior.is_ccw:xy=xy[::-1]
    low=np.broadcast_to(low,(len(xy),));high=np.broadcast_to(high,(len(xy),))
    g.rings(name,[np.column_stack((xy,low)),np.column_stack((xy,high))],material,fid);g.ASSETS[-1]['collision']='complex'

def nature_house():
    fid='SP_nature_house';origin,coeff,review=nature_plane();h=(NATURE_XY-origin)@coeff[:2]+coeff[2];q,c=nature_data()
    prism('SM_NatureHouse_BelowDeckExterior',NATURE_XY,1.35,h-.22,'wall',fid)
    prism('SM_NatureHouse_ViewingDeck',NATURE_XY,h-.22,h+.025,'concrete',fid)
    # Front parapet follows the actual low-side edge and retains the plaza.
    a,b=np.array([362.92,-912.97]),np.array([391.45,-902.94]);p=np.linspace(a,b,12)
    for i,x in enumerate(p):
        z=float((x-origin)@coeff[:2]+coeff[2]);tube(f'SM_NatureHouse_RailPost_{i:02d}',[*x,z],[*x,z+1.03],.055,'steel',fid)
    for i,(a,b) in enumerate(zip(p[:-1],p[1:])):
        za=float((a-origin)@coeff[:2]+coeff[2]);zb=float((b-origin)@coeff[:2]+coeff[2]);tube(f'SM_NatureHouse_RailTop_{i:02d}',[*a,za+1.03],[*b,zb+1.03],.045,'steel',fid)
    g.feature(fid,'Lost Lagoon Nature House and upper viewing deck',[
        'https://stanleyparkecology.ca/2020/07/16/the-new-nature-house-is-open/',
        'https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf',
        'evidence/corridor/ortho-utm/named-nature-house.json','manifests/named-nature-house-west-survey.json','manifests/named-nature-house-east-survey.json'],
        dict(centre_local_m=origin.tolist(),deck_outline_local_xy_m=NATURE_XY.tolist(),deck_plane_origin_m=origin.tolist(),deck_plane_coefficients=coeff.tolist(),deck_fit=review,
             upper_deck_h_range_m=[float(h.min()),float(h.max())],lower_front_path_h_m='Classified lower frontage returns cluster near 1.55 m CGVD2013',
             identity='Operator explicitly places Nature House below the viewing platform at the end of Chilco Street. OSM underground building way363832217 and toilet way74267954 are reference cross-checks, not placement controls.'),
        dict(closed_exterior_bottom_h_m=1.35,slab_thickness_m=.22,rail_height_m=1.03,post_radius_m=.055,rail_radius_m=.045),
        'Closed building exterior below a measured upper viewing deck; interiors, individual door/window positions and display detail are outside M1. Upper approach requires refine_nature_house_terrain.py before contact acceptance. Rail spacing and concealed foundation are estimated. The current coarse terrain does not prove the two separate public levels.')

def jubilee():
    fid='SP_jubilee';q,c=g.survey('jubilee');centre=np.array([336.47,-771.42])
    diamond=np.array([[331.23,-771.35],[336.44,-766.32],[341.63,-771.39],[336.49,-776.55]])
    if not Polygon(diamond).exterior.is_ccw:diamond=diamond[::-1]
    s=q[contains_xy(Polygon(diamond).buffer(-.3),q[:,0],q[:,1])&(q[:,2]>3)&(q[:,2]<3.4)];h=float(np.median(s[:,2]))
    theta=np.arange(8)*2*np.pi/8+np.pi/8;outer=centre+np.column_stack((np.cos(theta),np.sin(theta)))*6.15
    prism('SM_Jubilee_OctagonalIsland',outer,.8,1.88,'stone',fid)
    prism('SM_Jubilee_RaisedDiamondPlatform',diamond,1.85,h,'concrete',fid)
    # Low octagonal perimeter, retained as separate closed wall members.
    for i,(a,b) in enumerate(zip(outer,np.roll(outer,-1,axis=0))):
        d=(b-a)/np.linalg.norm(b-a);n=np.array([-d[1],d[0]])*.10;xy=[a-n,b-n,b+n,a+n]
        prism(f'SM_Jubilee_Perimeter_{i:02d}',xy,1.72,1.97,'concrete',fid)
    # The narrow service platform to the southwest is visible in 2022 imagery.
    service=np.array([[327.0,-780.8],[329.0,-782.8],[334.2,-777.35],[332.2,-775.35]])
    prism('SM_Jubilee_ServicePlatform',service,1.28,1.72,'concrete',fid)
    north=np.array([[329.0,-767.85],[330.4,-769.25],[334.0,-765.62],[332.5,-764.18]])
    prism('SM_Jubilee_NorthMaintenancePad',north,1.32,1.87,'concrete',fid)
    g.feature(fid,'Jubilee Fountain inactive support and service platforms',[
        'https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId=158','https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf',
        'evidence/corridor/ortho-utm/named-jubilee.json','manifests/named-jubilee-survey.json'],
        dict(centre_local_m=centre.tolist(),diamond_outline_local_m=diamond.tolist(),platform_top_h_m=h,top_returns=len(s),top_p95_residual_m=float(np.percentile(abs(s[:,2]-h),95)),
             outer_octagonal_radius_m=6.15,outer_edge_h_m=1.9,source_condition='City 2022 ortho clearly shows the octagonal island, raised diamond and service pads. City 2026 map marks the fountain under restoration.'),
        dict(outer_base_h_m=.8,concealed_platform_sides='Vertical closures below visible edge; submerged depths are estimates',service_platform_edges='Manually traced; height uses sparse low returns',pipework='Deferred; no operating spray'),
        'No running fountain, dynamic spray or claim of present restoration completion. Structure is not a public walk destination. Distinct major platforms are measured/traced; hidden underwater foundation, nozzle pipework and exact coping detail remain unfinished.')

def main():
    g.OUT=ROOT/'data/derived/lagoon-structures';g.OUT.mkdir(exist_ok=True);g.ASSETS.clear();g.FEATURES.clear()
    nature_house();jubilee()
    for a in g.ASSETS:a['collision_reason']='Closed source-located exterior or slab; Nature House upper approaches need the separate source refinement before live walking acceptance.' if a['feature_id']=='SP_nature_house' else 'Closed offshore support. Direct contact geometry, no new public route or invisible broad box.'
    d=dict(schema_version=1,revision='lagoon-structures-m1-r1',assets=g.ASSETS,features=g.FEATURES,acceptance=False,
        source_period='City 2022 ortho/survey; official identity references and City2026 condition',target_period='September 2026',
        reference_rights='City geometry derivatives OGL-Vancouver; operator/art registry pages reference only, no source photograph or inscription embedded.',
        input_hashes={f'manifests/named-{x}-survey.json':digest(ROOT/f'manifests/named-{x}-survey.json') for x in ['nature-house-west','nature-house-east','jubilee']})
    save_json(ROOT/'manifests/lagoon-structure-blockouts.json',d)
    print(json.dumps(dict(assets=len(g.ASSETS),manifest_sha256=digest(ROOT/'manifests/lagoon-structure-blockouts.json'))))

if __name__=='__main__':main()
