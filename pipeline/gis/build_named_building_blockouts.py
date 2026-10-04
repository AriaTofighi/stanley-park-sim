"""Measured roof forms for individually matched park buildings.

Identity is checked against official-map geography, dated orthophotos and each
operator or City reference. Roof shapes remain survey-derived. Facade extrusion
does not imply a measured wall or floor plan.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely import contains_xy
import build_named_feature_blockouts as geom
from named_roof_planes import fit_major_planes, rebuild_planar_patches
from acquire_sources import digest, save_json

ROOT=geom.ROOT
geom.OUT=ROOT/'data/derived/named-buildings';geom.OUT.mkdir(exist_ok=True)
MAP='https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf'
IDENTITIES=[
 ('SP_aquarium','Aquarium','Vancouver Aquarium exterior','490000_5460000',[27,31,36,38],
  'https://www.vanaqua.org/Contact-Us','named-central-buildings',
  'Large eastern complex beside Avison Way; outdoor pool courtyards retained as roof gaps; northern service roof included.'),
 ('SP_pavilion','Pavilion','Stanley Park Pavilion','490000_5460000',[25],
  'https://stanleyparkpavilion.com/faq/','named-central-buildings',
  'Building north of the circular garden, west of Aquarium, at 610 Pipeline Road. Roof survey includes the multiple pitched wings.'),
 ('SP_malkin_bowl','MalkinBowl','Malkin Bowl stage and entrance building','490000_5460000',[21,22],
  'https://www.malkinbowl.com/getting-here','named-central-buildings',
  'Stage at south end of the open seating lawn; small northern entrance roof opposite Pavilion. Seating and temporary event equipment not modeled.'),
 ('SP_rowing_club','RowingClub','Vancouver Rowing Club','490000_5460000',[18],
  'https://vancouverrowingclub.ca/Club_Info/VRC_RCS','named-harbour-buildings',
  'Distinct pitched waterfront roof at north-west corner of Coal Harbour, beside the first jetty. Dock and boat geometry is separate.'),
 ('SP_cricket_pavilion','CricketPavilion','Brockton Cricket Pavilion','490000_5460000',[23],
  'https://parkboardmeetings.vancouver.ca/2005/050509/brockton_totem_poles_gift_shop_licence.pdf','named-east-buildings',
  'Pavilion between Brockton Oval and the cricket ground; distinguished from the western oval grandstand.'),
 ('SP_totem_precinct','TotemVisitor','Brockton Point Totem Pole Visitor Centre','491000_5460000',[12],
  'https://parkboardmeetings.vancouver.ca/2005/050509/brockton_totem_poles_gift_shop_licence.pdf','named-east-buildings',
  'Visitor centre at the north-west side of the Totem Pole court. This asset does not stand in for the individual poles or artwork.'),
 ('SP_teahouse','Teahouse','Ferguson Point Teahouse','488000_5460000',[1],
  'https://vancouver.ca/parks-recreation-culture/stories-from-inside-the-park.aspx','named-teahouse',
  'Measured pitched roof and conservatory at the Ferguson Point hairpin. Figure-based registry placements are not used.'),
 ('SP_second_pool','SecondPoolFacilities','Second Beach pool facilities','489000_5460000',[28,29],
  'https://vancouver.ca/parks-recreation-culture/second-beach-pool.aspx','named-second-pool',
  'Curved concession/change building north-east of pool, plus small roof near pool deck. Pool basin is a separate form.'),
 ('SP_lumberman_concession','LumbermanConcession',"Lumberman's Arch concession",'490000_5461000',[5],
  'https://vancouver.ca/parks-recreation-culture/stanley-park-water-park.aspx','named-lumberman-wide',
  'Concession behind water park across Stanley Park Drive. This is not the cedar arch, whose placement remains unresolved.'),
]

def main():
    cover=json.loads((ROOT/'data/derived/cover-blockout.json').read_text(encoding='utf8'))
    by_id={x['id']:x for x in cover['buildings']};cache={}
    for fid,tag,name,tile,groups,url,ortho,identity in IDENTITIES:
        ids=[f'lidar2022_{tile}_{k}' for k in groups]
        records=[by_id[x] for x in ids]
        if tile not in cache:cache[tile]=np.load(ROOT/f'data/derived/lidar2022_{tile}.npz')['buildings'][:,:3].astype(float)
        polygon=unary_union([Polygon(x['outline']).buffer(.05) for x in records])
        q=cache[tile];q=q[contains_xy(polygon,q[:,0],q[:,1])]
        cell=np.floor(q[:,:2]/.8).astype(int);keys,inverse=np.unique(cell,axis=0,return_inverse=True)
        vertices=np.array([np.median(q[inverse==k],axis=0) for k in range(len(keys))])
        plane_review=None
        # Measured roof returns contain equipment and scan noise. Retain the
        # supported roof planes instead of presenting noisy triangles as art.
        support=70 if tag=='Aquarium' else max(12,min(50,len(vertices)//30))
        vertices,plane_review,plane_labels=fit_major_planes(vertices,min_support=support)
        faces=Delaunay(vertices[:,:2]).simplices
        edges=np.linalg.norm(vertices[faces][:,:,:2]-np.roll(vertices[faces][:,:,:2],1,axis=1),axis=2)
        faces=faces[edges.max(1)<2.4]
        mid=vertices[faces,:2].mean(1);faces=faces[contains_xy(polygon,mid[:,0],mid[:,1])]
        if plane_review:
            vertices,faces,steps,step_faces,outer_edges=rebuild_planar_patches(vertices,faces,plane_labels,plane_review)
            if len(step_faces):geom.mesh(f'SM_Named_{tag}_RoofStepClosures',steps,step_faces,'wall',fid)
        geom.mesh(f'SM_Named_{tag}_RoofSurvey',vertices,faces,'roof',fid)
        counts={};directed={}
        for tri in faces:
            for a,b in zip(tri,np.roll(tri,-1)):
                key=tuple(sorted((tuple(np.round(vertices[a,:2],6)),tuple(np.round(vertices[b,:2],6)))));counts[key]=counts.get(key,0)+1;directed[key]=(int(a),int(b))
        wv=[];wf=[]
        boundaries=outer_edges if plane_review else [[vertices[directed[key][0]],vertices[directed[key][1]]] for key,count in counts.items() if count==1]
        for p0,p1 in boundaries:
            h=geom.HEIGHT([[p0[1],p0[0]],[p1[1],p1[0]]])
            if not np.isfinite(h).all():raise ValueError(f'Unresolved wall base: {name}')
            h=np.minimum(h,[p0[2]-.2,p1[2]-.2]);n=len(wv)
            wv.extend([p0,p1,[p1[0],p1[1],h[1]],[p0[0],p0[1],h[0]]]);wf.append((n+3,n+2,n+1,n))
        geom.mesh(f'SM_Named_{tag}_WallsReview',wv,wf,'wall',fid)
        geom.feature(fid,name,[MAP,url,f'evidence/corridor/ortho-utm/{ortho}.json',f'manifests/lidar2022-{tile}.json'],
            dict(source_roof_ids=ids,roof_returns=len(q),sampling_m=.8,roof_min_m=float(vertices[:,2].min()),roof_max_m=float(vertices[:,2].max()),
                 centroid_local_m=np.mean(vertices[:,:2],axis=0).tolist(),source_extent_area_m2=float(polygon.area)),
            dict(walls='Vertical extrusion of roof boundary to terrain, not independently measured wall faces'),
            identity+' M1 form only; roof holes and small appendages, facades, steps, railings and interiors remain unfinished.',ids)
        geom.FEATURES[-1]['identity_review']='Official-map layout, individual operator/City reference and City 2022 orthophoto reviewed together'
        if plane_review:geom.FEATURES[-1]['roof_plane_review']=plane_review
        print(name,len(vertices),len(faces),flush=True)
    save_json(ROOT/'manifests/named-building-blockouts.json',dict(schema_version=1,source_period='City 2022 survey and imagery',
        target_period='September 2026',assets=geom.ASSETS,features=geom.FEATURES,acceptance=False,
        method='Reconstructed class-6 roof surfaces; individually identified records; walls are explicit extrusion estimates',
        reference_rights='Official map, operator pages, City photos and tender drawings are reference only. City survey derivatives use OGL-Vancouver.',
        input_hashes={f'manifests/lidar2022-{k}.json':digest(ROOT/f'manifests/lidar2022-{k}.json') for k in cache}))
    print(json.dumps(dict(features=len(geom.FEATURES),assets=len(geom.ASSETS),triangles=sum(x['triangles'] for x in geom.ASSETS))))

if __name__=='__main__':main()
