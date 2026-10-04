"""Source-fitted raised lookout access with an exact existing-terrain join.

This small package requires no shared terrain change. Airborne class-1 returns
resolve the raised connector while class-2 points resolve its ground approach.
"""
import json
from collections import Counter
import numpy as np
import shapely
from shapely.geometry import Polygon,Point,LineString
import build_named_feature_blockouts as geom
from review_siwash_approach import TerrainQuery
from acquire_sources import digest,save_json

ROOT=geom.ROOT


def clip_positive(points,values):
    output=[]
    for a,b,va,vb in zip(points,np.roll(points,-1,axis=0),values,np.roll(values,-1)):
        if va>=-1e-9:output.append(a)
        if va*vb<0:output.append(a+(b-a)*va/(va-vb))
    return np.asarray(output)


def main():
    source=json.loads((ROOT/'manifests/west-landmark-blockouts.json').read_text())
    feature=next(f for f in source['features'] if f['id']=='SP_siwash_lookout');m=feature['measured']
    a=np.array([-926.9325,657.5375]);b=np.array([-926.1075,658.2875]);origin=(a+b)/2
    across=(b-a)/np.linalg.norm(b-a);along=np.array([across[1],-across[0]]);half=np.linalg.norm(b-a)/2
    roof_origin=np.array(m['roof_plane_origin_m']);roof_plane=np.array(m['roof_plane'])
    roof_h=lambda xy:(xy-roof_origin)@roof_plane[:2]+roof_plane[2]
    q,c=geom.survey('siwash-lookout');s=(q[:,:2]-origin)@along;t=(q[:,:2]-origin)@across
    stations=np.array([0.,.75,2.25,3.75,5.5,7.5,10.]);heights=[float(roof_h(origin))];reviews=[]
    for station in stations[1:]:
        take=(abs(s-station)<.65)&(abs(t)<half+.15)&(q[:,2]>22.9)&(q[:,2]<25)&(np.isin(c,[1,2]))
        if station>=3.75:take&=c==2
        pts=q[take]
        if len(pts)<4:raise ValueError(f'Insufficient source approach returns at {station}')
        h=float(np.median(pts[:,2]));heights.append(h)
        reviews.append(dict(station_m=float(station),returns=len(pts),median_h_m=h,p10_p90_h_m=np.percentile(pts[:,2],[10,90]).tolist()))
    heights=np.array(heights)
    cross_slope=float(roof_plane[:2]@across)
    profile=lambda xy:np.interp((xy-origin)@along,stations,heights)+((xy-origin)@across)*cross_slope
    terrain=TerrainQuery([-935,644,-913,663]);triangles=[]
    for start,end in zip(stations[:-1],stations[1:]):
        strip=Polygon([origin+along*start-across*half,origin+along*end-across*half,origin+along*end+across*half,origin+along*start+across*half])
        for index in terrain.tree.query(strip,predicate='intersects'):
            tt=terrain.triangles[index];basis=np.linalg.inv(np.column_stack((tt[1,:2]-tt[0,:2],tt[2,:2]-tt[0,:2])))
            h=lambda xy:tt[0,2]+((xy-tt[0,:2])@basis.T)@(tt[1:,2]-tt[0,2])
            fragment=strip.intersection(terrain.polygons[index])
            for p in shapely.get_parts(fragment):
                if not isinstance(p,Polygon) or p.area<1e-8:continue
                xy=np.array(shapely.orient_polygons(p).exterior.coords)[:-1];xy=clip_positive(xy,profile(xy)-h(xy))
                if len(xy)<3 or Polygon(xy).area<1e-8:continue
                for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(Polygon(xy))):
                    xy=np.array(shapely.orient_polygons(tri).exterior.coords)[:3]
                    triangles.append(np.column_stack((xy,profile(xy))))
    vertices=[];faces=[];lookup={}
    for tri in triangles:
        face=[]
        for p in tri:
            key=tuple(np.round(p,7))
            if key not in lookup:lookup[key]=len(vertices);vertices.append(p)
            face.append(lookup[key])
        faces.append(face)
    top=np.array(vertices);faces=np.array(faces);counts=Counter();directed={}
    for face in faces:
        for i,j in zip(face,np.roll(face,-1)):
            key=tuple(sorted((int(i),int(j))));counts[key]+=1;directed[key]=(int(i),int(j))
    boundary=[directed[k] for k,n in counts.items() if n==1]
    # Continuous slab underside is a section estimate. It can enter the ground
    # at the exact contact line; the top itself never lies below that ground.
    allv=np.vstack((top,top-[0,0,.18]));n=len(top);allf=faces.tolist()+[[int(k+n) for k in f[::-1]] for f in faces]
    for i,j in boundary:allf.extend([(j,i,i+n),(j,i+n,j+n)])
    geom.OUT=ROOT/'data/derived/siwash-approach';geom.OUT.mkdir(exist_ok=True);geom.ASSETS.clear();geom.FEATURES.clear()
    geom.mesh('SM_SiwashLookout_RaisedApproach',allv,allf,'concrete','SP_siwash_lookout',collision='complex')
    # Source notes confirm handrails. Exact rail sections remain estimates.
    # Limit these to the genuinely elevated connector, not the ground trail.
    for side in [-1,1]:
        for k,(sa,sb) in enumerate(zip([0,.75,2.25],[.75,2.25,3.2])):
            pa=origin+along*sa+across*half*side;pb=origin+along*sb+across*half*side
            for lift in [.56,1.08]:
                geom.beam(f'SM_SiwashApproach_Rail_{side+1}_{k}_{int(lift*100)}',np.r_[pa,profile(pa)+lift],np.r_[pb,profile(pb)+lift],.065,'steel','SP_siwash_lookout');geom.ASSETS[-1]['collision']='complex'
        for k,station in enumerate([0,1.6,3.2]):
            p=origin+along*station+across*half*side
            geom.beam(f'SM_SiwashApproach_Post_{side+1}_{k}',np.r_[p,profile(p)],np.r_[p,profile(p)+1.1],.08,'steel','SP_siwash_lookout');geom.ASSETS[-1]['collision']='complex'
    # The broad southeast edge was left open by the first massing stage.
    # Only the source-visible narrow connector needs that opening. Extend the
    # estimated perimeter rail across the remaining edge, without closing it.
    end=np.array([-923.8575,661.0625]);middle=(b+end)/2
    for k,(pa,pb) in enumerate([(b,middle),(middle,end)]):
        for lift in [.56,1.08]:
            geom.beam(f'SM_SiwashApproach_PerimeterRail_{k}_{int(lift*100)}',np.r_[pa,roof_h(pa)+lift],np.r_[pb,roof_h(pb)+lift],.065,'steel','SP_siwash_lookout');geom.ASSETS[-1]['collision']='complex'
    geom.beam('SM_SiwashApproach_PerimeterPost',np.r_[middle,roof_h(middle)],np.r_[middle,roof_h(middle)+1.1],.08,'steel','SP_siwash_lookout');geom.ASSETS[-1]['collision']='complex'
    contact=[];roof=[];side=[]
    for i,j in boundary:
        va,vb=top[[i,j]];sa,sb=(top[[i,j],:2]-origin)@along
        for fraction in [0,.25,.5,.75,1]:
            p=va+(vb-va)*fraction
            if abs(sa)<1e-5 and abs(sb)<1e-5:roof.append(abs(p[2]-roof_h(p[:2])))
            elif abs(abs((va[:2]-origin)@across)-half)<1e-5 and abs(abs((vb[:2]-origin)@across)-half)<1e-5 and ((va[:2]-origin)@across)*((vb[:2]-origin)@across)>0:side.append(float(p[2]-terrain.height(p[:2])))
            else:contact.append(abs(p[2]-terrain.height(p[:2])))
    raised=shapely.union_all(shapely.polygons(top[faces,:2]));main_part=max(shapely.get_parts(raised),key=lambda p:p.area)
    review=dict(source_profile_stations_m=stations.tolist(),source_profile_h_m=heights.tolist(),source_bins=reviews,
        along_axis=along.tolist(),across_axis=across.tolist(),origin_local_m=origin.tolist(),width_m=half*2,width_trace_uncertainty_m=.3,
        roof_join_max_error_m=max(roof),terrain_join_max_error_m=max(contact),terrain_contact_samples=len(contact),
        max_profile_grade=float(max(abs(np.diff(heights)/np.diff(stations)))),surface_area_m2=raised.area,
        surface_parts=len(list(shapely.get_parts(raised))),terrain_inputs=terrain.inputs,
        surface_footprint_local_m=list(main_part.exterior.coords),
        numerical_pass=bool(max(roof)<1e-6 and max(contact)<1e-6),application_acceptance=False,
        limits='The raised approach is observed in unclassified survey returns; slab thickness, rail sections and exact edge width remain M1 estimates. The profile is a continuous contact envelope, not a claim of exact stair treads. No terrain cut is required. Terrain-contact values are internal consistency, not independent accuracy.')
    if not review['numerical_pass']:raise ValueError(review)
    geom.feature('SP_siwash_lookout','Siwash lookout raised approach',feature['sources'],review,
        dict(slab_thickness_m=.18,rail_height_m=1.1,rail_section_m=.065,post_section_m=.08),review['limits'])
    for asset in geom.ASSETS:asset['collision_reason']='Source-located raised access surface or estimated handrail. The slab joins roof and actual terrain planes; live contact remains unaccepted.'
    data=dict(schema_version=1,revision='siwash-approach-m1-r1',assets=geom.ASSETS,features=geom.FEATURES,acceptance=False,
        source_period='City 2022 survey and ortho; dated primary references',target_period='September 2026',
        reference_rights='City survey/ortho derivatives OGL-Vancouver; historic documents reference only.',input_hashes={'manifests/west-landmark-blockouts.json':digest(ROOT/'manifests/west-landmark-blockouts.json')})
    save_json(ROOT/'manifests/siwash-approach-blockout.json',data);save_json(ROOT/'evidence/siwash-approach-repair.json',review)
    print(json.dumps(review,indent=2))


if __name__=='__main__':main()
