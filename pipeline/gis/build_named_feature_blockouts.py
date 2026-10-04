"""Build individually researched M1 forms. No live Blender or game operations.

The output separates measured geometry from explicit visual estimates. It does
not grant an accuracy pass, artwork rights, or a completed M4 model.
"""
import json
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay, cKDTree
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import Polygon, MultiPoint
from shapely import contains_xy

from acquire_sources import digest, save_json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'data/derived/named-features'
OUT.mkdir(exist_ok=True)
ASSETS = []
FEATURES = []
G = np.load(ROOT/'data/derived/terrain_2022_park.npz')
HEIGHT = RegularGridInterpolator((G['y'], G['x']), G['z'], bounds_error=False, fill_value=np.nan)
COLORS = {'white': [.82,.81,.75], 'red': [.63,.035,.025], 'stone': [.39,.40,.35],
          'steel': [.17,.20,.17], 'roof': [.21,.24,.20], 'wall': [.49,.44,.34],
          'concrete': [.49,.49,.45], 'gun': [.11,.12,.10]}

def mesh(name, vertices, faces, material, feature, collision='none'):
    v=np.asarray(vertices,dtype=np.float64)
    triangles=[]
    for face in faces:
        triangles.extend((face[0],face[k],face[k+1]) for k in range(1,len(face)-1))
    f=np.asarray(triangles,dtype=np.int32)
    area=np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1)*.5
    if not np.isfinite(v).all() or np.any(area<1e-8):
        raise ValueError(f'Invalid or degenerate mesh {name}')
    path=OUT/f'{name}.npz';np.savez_compressed(path,vertices=v,faces=f)
    ASSETS.append(dict(name=name,feature_id=feature,mesh_path=path.relative_to(ROOT).as_posix(),
                      sha256=digest(path),material=material,color=COLORS[material],collision=collision,
                      vertices=len(v),triangles=len(f),bounds_min_m=v.min(0).tolist(),bounds_max_m=v.max(0).tolist()))

def rings(name, rows, material, feature):
    n=len(rows[0]);faces=[tuple(range(n-1,-1,-1))]
    for k in range(len(rows)-1):
        for i in range(n): j=(i+1)%n;faces.append((k*n+i,k*n+j,(k+1)*n+j,(k+1)*n+i))
    faces.append(tuple((len(rows)-1)*n+i for i in range(n)))
    mesh(name,np.asarray(rows).reshape(-1,3),faces,material,feature)

def beam(name,a,b,width,material,feature):
    a,b=np.asarray(a,float),np.asarray(b,float);d=(b-a)/np.linalg.norm(b-a)
    q=np.array([0,0,1.]) if abs(d[2])<.9 else np.array([1.,0,0])
    u=np.cross(d,q);u/=np.linalg.norm(u);v=np.cross(d,u)
    rows=[[p+(u*s+v*t)*width/2 for s,t in [(-1,-1),(1,-1),(1,1),(-1,1)]] for p in [a,b]]
    rings(name,rows,material,feature)

def survey(name):
    p=np.load(ROOT/f'data/derived/named-{name}-survey.npz')
    return p['xyz'].astype(float),p['classification']

def feature(id,name,sources,measured,estimates,limits,exclude=None):
    FEATURES.append(dict(id=id,name=name,sources=sources,measured=measured,estimates=estimates,
        limits=limits,release_accepted=False,geographic_accuracy_accepted=False,
        model_stage='M1 source-driven massing; Blender/runtime review pending',
        replace_cover_ids=exclude or []))

def prospect_light():
    id='SP_prospect_light';q,c=survey('prospect-light');centre=np.array([121.5,1272.5])
    a=np.deg2rad(-19);u=np.array([np.cos(a),np.sin(a)]);v=np.array([-u[1],u[0]])
    roof=q[(np.linalg.norm(q[:,:2]-centre,axis=1)<3.2)&(q[:,2]>11.8)&(q[:,2]<12.05)]
    xy=(roof[:,:2]-centre)@np.array([u,v]).T;lo,hi=np.percentile(xy,[2,98],axis=0)
    centre=centre+np.array([u,v]).T@((lo+hi)/2);deck=(hi-lo);ztop=float(np.median(roof[:,2]))
    def row(z,wh):
        return [[*(centre+u*x+v*y),z] for x,y in [(-wh[0]/2,-wh[1]/2),(wh[0]/2,-wh[1]/2),(wh[0]/2,wh[1]/2),(-wh[0]/2,wh[1]/2)]]
    # Profiles follow inspected LAS bands. Hidden sides and the colour boundary
    # are estimates; the top deck and pose are explicit survey measurements.
    profile=[(3.72,(5.4,5.0)),(6.45,(5.4,5.0)),(6.8,(4.3,3.9)),(7.5,(3.1,2.9)),
             (8.5,(2.45,2.3)),(9.0,(2.22,2.1)),(10.0,(1.96,1.86)),(ztop-.18,(1.70,1.64))]
    rings('SM_ProspectLight_LowerWhite',[row(z,w) for z,w in profile[:6]],'white',id)
    rings('SM_ProspectLight_RedBand',[row(z,w) for z,w in profile[5:7]],'red',id)
    rings('SM_ProspectLight_UpperWhite',[row(z,w) for z,w in profile[6:]],'white',id)
    rings('SM_ProspectLight_TopDeck',[row(ztop-.18,deck),row(ztop,deck)],'white',id)
    beam('SM_ProspectLight_Beacon',[*centre,ztop],[*centre,ztop+.55],.24,'red',id)
    feature(id,'Prospect Point Lighthouse',[
        'https://www.notmar.gc.ca/publications/monthly/archives/eng/services/notmar/western-pdf/wes10e02.pdf',
        'https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/chs-shc-PAC201-eng-202411-4126986x.pdf',
        'https://www.lighthousefriends.com/prospect1_2009.jpg',
        'evidence/corridor/ortho-utm/named-prospect-light.json','manifests/named-prospect-light-survey.json'],
        dict(centre_local_m=centre.tolist(),axis_degrees=-19,top_deck_height_m=ztop,top_deck_dimensions_m=deck.tolist(),top_returns=len(roof)),
        dict(profile='Lower profile manually reviewed against LAS bands; concealed sides mirrored',base_height_m=3.72,red_band_z_m=[9,10],beacon_height_m=.55),
        'No ladder, door, aerials, rail or operational light. Minor details and hidden sides are estimates. Tower LAS returns are mainly class 5, not class 6.')

def gun_pavilion():
    id='SP_nine_oclock';q,c=survey('nine-clock-gun')
    roof=q[(q[:,2]>6.95)&(q[:,2]<8.3)&(np.linalg.norm(q[:,:2]-[1855.5,-506.5],axis=1)<5)]
    rect=np.array(MultiPoint(roof[:,:2]).minimum_rotated_rectangle.exterior.coords)[:4]
    lengths=np.linalg.norm(np.roll(rect,-1,axis=0)-rect,axis=1);i=int(np.argmax(lengths));u=(rect[(i+1)%4]-rect[i])/lengths[i]
    if u[1]>0:u=-u
    v=np.array([-u[1],u[0]]);centre=rect.mean(0);uv=(roof[:,:2]-centre)@np.array([u,v]).T
    lo,hi=np.percentile(uv,[1,99],axis=0);centre+=np.array([u,v]).T@((lo+hi)/2);length,width=hi-lo
    uv=(roof[:,:2]-centre)@np.array([u,v]).T
    A=np.column_stack((np.ones(len(roof)),-np.abs(uv[:,1])))
    keep=np.ones(len(roof),bool)
    for _ in range(4):
        coeff=np.linalg.lstsq(A[keep],roof[keep,2],rcond=None)[0];res=roof[:,2]-A@coeff;keep=np.abs(res)<.17
    ridge=float(coeff[0]);eave=float(coeff[0]-coeff[1]*width/2)
    def point(x,y,z):return [*(centre+u*x+v*y),z]
    verts=[point(x,y,z) for x in [-length/2,length/2] for y,z in [(-width/2,eave),(0,ridge),(width/2,eave)]]
    mesh('SM_NineClockGun_GabledRoof',verts,[(0,3,4,1),(1,4,5,2),(0,1,2),(3,5,4)],'roof',id)
    # Front paving level is observed near the northern end; the rear stone wall
    # goes down to the foreshore. Frame sizes are visual blockout estimates.
    ground=q[(c==2)&(np.linalg.norm(q[:,:2]-(centre-u*length/2),axis=1)<2.5)&(q[:,2]>2.5)&(q[:,2]<4)]
    base=float(np.median(ground[:,2]));fx=length/2-.20;fy=width/2-.18
    for ix,x in enumerate([-fx,fx]):
        for iy,y in enumerate([-fy,fy]):beam(f'SM_NineClockGun_Post_{ix}{iy}',point(x,y,base),point(x,y,eave),.12,'steel',id)
    for iz,z in enumerate([base+.1,base+1.5,base+2.8,eave]):
        for iy,y in enumerate([-fy,fy]):beam(f'SM_NineClockGun_Rail_{iz}{iy}',point(-fx,y,z),point(fx,y,z),.085,'steel',id)
        for ix,x in enumerate([-fx,fx]):beam(f'SM_NineClockGun_EndRail_{iz}{ix}',point(x,-fy,z),point(x,fy,z),.085,'steel',id)
    # A low-resolution barrel identifies this historical fixture. Bore/markings
    # and carriage are not claimed as measured production geometry.
    beam('SM_NineClockGun_Barrel',point(-.8,0,base+1.0),point(1.2,0,base+1.08),.33,'gun',id)
    feature(id,"Nine O'Clock Gun",['https://vancouver.ca/parks-recreation-culture/monuments-and-sculptures.aspx',
        'https://vancouver.ca/images/cov/content/9-O-clock-Gun-Monument.jpg',
        'https://veterans.gc.ca/en/remembrance/memorials/canada/nine-oclock-gun',
        'evidence/corridor/ortho-utm/named-gun-detail.json','manifests/named-nine-clock-gun-survey.json'],
        dict(centre_local_m=centre.tolist(),roof_length_m=float(length),roof_width_m=float(width),ridge_m=ridge,eave_m=eave,
             base_m=base,roof_returns=len(roof),fit_inliers=int(keep.sum()),roof_fit_p95_m=float(np.percentile(np.abs(res[keep]),95))),
        dict(frame_post_width_m=.12,rails_m=.085,barrel_length_m=2,barrel_width_m=.33),
        'Open frame massing only; wire mesh, stone support, plaque and carriage need detail. VAC location is an approximate search point, not a survey control.',
        ['lidar2022_491000_5460000_11'])

def lookout():
    id='SP_prospect_lookout';q,c=survey('prospect-lookout')
    px=np.array([[197,301],[218,279],[213,265],[241,242],[268,257],[294,255],[315,242],[327,250],[359,238],[392,246],[416,265],[438,296],[450,329],[442,364],[425,380],[403,373],[416,345],[417,324],[406,301],[383,288],[356,291],[329,296],[307,291],[286,309],[261,332],[224,314]])
    xy=np.column_stack((46.588+(px[:,0]+.5)*.075,1269.341-(px[:,1]+.5)*.075));poly=Polygon(xy)
    ground=q[(c==2)&contains_xy(poly.buffer(.1),q[:,0],q[:,1])];tree=cKDTree(ground[:,:2])
    x,y=np.meshgrid(np.arange(xy[:,0].min(),xy[:,0].max(),.4),np.arange(xy[:,1].min(),xy[:,1].max(),.4))
    grid=np.column_stack((x.ravel(),y.ravel()));grid=grid[contains_xy(poly,grid[:,0],grid[:,1])];grid=np.vstack((xy,grid))
    dist,index=tree.query(grid,k=7);z=np.median(ground[index,2],axis=1)+.025
    tris=Delaunay(grid).simplices;mid=grid[tris].mean(1);tris=tris[contains_xy(poly,mid[:,0],mid[:,1])]
    vertices=np.column_stack((grid,z));mesh('SM_ProspectLookout_TerraceSurvey',vertices,tris,'concrete',id)
    # Edge parapet is deliberately low-detail and not collision. Interpolated
    # stair edges remain visibly stepped only to the 0.4 m sampling resolution.
    for i in range(3,len(xy)-12):
        a=np.array([*xy[i],z[i]+.8]);b=np.array([*xy[i+1],z[i+1]+.8]);beam(f'SM_ProspectLookout_Parapet_{i:02d}',a,b,.20,'stone',id)
    feature(id,'Prospect Point Lookout',[
        'https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx',
        'https://geonetbc.gov.bc.ca/geonetbc/gcm/details/590034',
        'evidence/corridor/ortho-utm/survey-prospect.json','manifests/named-prospect-lookout-survey.json'],
        dict(outline_local_m=xy.tolist(),surface_ground_returns=len(ground),sampling_m=.4,surface_height_range_m=[float(z.min()),float(z.max())],surface_area_m2=poly.area),
        dict(visible_offset_m=.025,parapet_height_m=.8,parapet_width_m=.2),
        'Terrace envelope measured from 2022 imagery and ground returns. Individual stair treads and parapets are not surveyed models. Lower approach remains terrain. Requires terrain cut before contact/collision acceptance.')
    FEATURES[-1]['terrain_cut_polygon_local_m']=xy.tolist()

def cafe():
    id='SP_prospect_cafe';q,c=survey('prospect-cafe');q=q[(c==6)&(q[:,2]<80)]
    # Keep measured roof complexity instead of one flat convex lid.
    cells=np.floor(q[:,:2]/.6).astype(int);keys,inv=np.unique(cells,axis=0,return_inverse=True)
    vertices=np.array([np.median(q[inv==k],axis=0) for k in range(len(keys))])
    faces=Delaunay(vertices[:,:2]).simplices;edge=np.linalg.norm(vertices[faces][:,:,:2]-np.roll(vertices[faces][:,:,:2],1,axis=1),axis=2)
    faces=faces[edge.max(1)<1.8]
    mesh('SM_ProspectCafe_RoofSurvey',vertices,faces,'roof',id)
    edges={};directed={}
    for tri in faces:
        for a,b in zip(tri,np.roll(tri,-1)):
            key=tuple(sorted((int(a),int(b))));edges[key]=edges.get(key,0)+1;directed[key]=(int(a),int(b))
    wallverts=[];wallfaces=[]
    for key,count in edges.items():
        if count!=1:continue
        a,b=directed[key]
        p0,p1=vertices[a],vertices[b];h=HEIGHT([[p0[1],p0[0]],[p1[1],p1[0]]]);h=np.minimum(h,[p0[2]-.3,p1[2]-.3])
        n=len(wallverts);wallverts.extend([p0,p1,[p1[0],p1[1],h[1]],[p0[0],p0[1],h[0]]]);wallfaces.append((n+3,n+2,n+1,n))
    mesh('SM_ProspectCafe_WallsReview',wallverts,wallfaces,'wall',id)
    feature(id,'Prospect Point Cafe and Gift Shop',[
        'https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx',
        'https://bids.vancouver.ca/bidopp/ITT/documents/PS20181755-Drawings-ProspectPointPavementConstruction2019.pdf',
        'evidence/corridor/ortho-utm/named-prospect-cafe.json','manifests/named-prospect-cafe-survey.json'],
        dict(roof_returns=len(q),roof_sampling_m=.6,roof_min_m=float(vertices[:,2].min()),roof_max_m=float(vertices[:,2].max())),
        dict(walls='Extruded from measured roof boundaries to terrain; no facade or floor survey'),
        '2022 roof returns identify the building seen on the City map and 2017/2019 tender. Under-canopy holes, roof eaves and facade details remain approximate. Tender is proposed work, not as-built proof.',
        ['lidar2022_489000_5462000_1','lidar2022_489000_5462000_2'])

def main():
    prospect_light();gun_pavilion();lookout();cafe()
    save_json(ROOT/'manifests/named-feature-blockouts.json',dict(schema_version=1,source_period='2022 survey with dated identity references',
        target_period='September 2026',coordinates='Local east/north/up metres; manifests/world-origin.json',
        assets=ASSETS,features=FEATURES,acceptance=False,
        blocked_features=[dict(id='SP_lumberman_arch',reason='Registry point and canopy-covered imagery did not positively identify the logs. Raw crop retained. Do not create a blind marker model.')],
        reference_rights='City/CCG/photographer web pages and photos are reference only; do not bundle. Geometry is authored from licensed City LAS and orthophoto measurements with listed estimates.'))
    print(json.dumps(dict(features=len(FEATURES),assets=len(ASSETS),triangles=sum(x['triangles'] for x in ASSETS),acceptance=False)))

if __name__=='__main__':main()
