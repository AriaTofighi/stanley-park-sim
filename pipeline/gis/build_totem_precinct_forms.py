"""Measured coarse pole profiles and the resolved southern welcome portal.

Names with inconsistent registry points are not used as placement controls.
Carving, paint patterns and cultural imagery are intentionally not fabricated.
"""
import json
import numpy as np
import build_named_feature_blockouts as g
from build_lagoon_structures import prism
from build_route_sculpture_blockouts import tube
from review_siwash_approach import TerrainQuery
from acquire_sources import save_json,digest

ROOT=g.ROOT

def estimated_rear_pole(tag, xy, height, radii):
    terrain=TerrainQuery([xy[0]-2,xy[1]-2,xy[0]+2,xy[1]+2]);ground=float(terrain.height(xy));theta=np.arange(16)*2*np.pi/16
    rows=[np.c_[np.array(xy)+np.c_[np.cos(theta),np.sin(theta)]*r,np.full(16,ground+h)] for h,r in zip(np.linspace(-.15,height,len(radii)),radii)]
    g.rings('SM_'+tag+'_EstimatedEnvelope',rows,'cedar','SP_totem_precinct');g.ASSETS[-1]['collision']='complex'
    return dict(component=tag,centre_local_m=xy,ground_h_m=ground,height_above_ground_m=height,position_uncertainty_m=2.0,height_uncertainty_m=2.5,
                method='OSM rear-row node position, City in-place identity and relative location, ortho canopy edge and the measured neighbouring row; profile dimensions estimated, not survey certified.',
                source_profile_radii_m=radii,terrain_inputs=terrain.inputs)
POLES=[([1612.7,-357.8],8.85,'northwestern open-display pole','Name not safely matched; OSM Beaver Crest node is 7.6 m east',None),
       ([1610.3,-362.6],10.02,'second open-display pole','OSM Oscar Matilpi node is 1.6 m east; provisional name match only',None),
       ([1608.9,-370.5],11.30,'western tall winged pole','City/OSM identities disagree; keep measured component ID', [10.4,11.35]),
       ([1613.8,-375.0],8.46,'Thunderbird House Post candidate','Shape and nearby OSM name support the low winged house-post identification; no carving replica',[6.85,7.35]),
       ([1620.2,-377.9],14.80,"Ga'akstalas candidate",'OSM node8555605624 is about 1.5 m east; measured tall upright supports this candidate',None),
       ([1621.1,-383.7],12.33,'Chief Skedans mortuary pole candidate','OSM node8555605622 is about 1 m east; broad upper form supports the mortuary-pole candidate',[12.12,12.34])]

def pole_profile(tag,xy,top,fid,wing=None):
    q,c=g.survey('totem-sculptures');xy=np.array(xy);terrain=TerrainQuery([xy[0]-3,xy[1]-3,xy[0]+3,xy[1]+3]);ground=float(terrain.height(xy));base=ground-.15
    s=q[(np.linalg.norm(q[:,:2]-xy,axis=1)<1.9)&(q[:,2]>ground+.65)&(q[:,2]<=top+.02)&(c==1)]
    theta=np.arange(14)*2*np.pi/14;heights=np.linspace(base,top,14);rows=[];widths=[]
    for h in heights:
        near=s[(abs(s[:,2]-h)<.65)&(np.linalg.norm(s[:,:2]-xy,axis=1)<.70)]
        if len(near)>=4:r=float(np.clip(np.percentile(np.linalg.norm(near[:,:2]-xy,axis=1),75),.19,.52))
        else:r=.28
        if h==heights[-1]:r=min(r,.28)
        rows.append(np.c_[xy+np.c_[np.cos(theta),np.sin(theta)]*r,np.full(len(theta),h)]);widths.append(r)
    g.rings(f'SM_{tag}_CoarseProfile',rows,'cedar',fid);g.ASSETS[-1]['collision']='complex'
    wing_record=None
    if wing:
        p=s[(s[:,2]>wing[0])&(s[:,2]<wing[1])];centre=p[:,:2].mean(0);_,vec=np.linalg.eigh(np.cov(p[:,:2].T));axis=vec[:,-1];normal=np.array([-axis[1],axis[0]]);projection=(p[:,:2]-centre)@axis;ends=np.percentile(projection,[2,98]);h=float(np.median(p[:,2]));outline=np.array([centre+axis*a+normal*b for a,b in [(ends[0],-.12),(ends[1],-.12),(ends[1],.12),(ends[0],.12)]])
        prism(f'SM_{tag}_BroadUpperMember',outline,h-.17,h+.17,'cedar',fid);wing_record=dict(returns=len(p),axis=axis.tolist(),span_m=float(np.diff(ends)[0]),height_m=h)
    return dict(centre_local_m=xy.tolist(),ground_h_m=ground,top_h_m=top,source_returns=len(s),profile_radii_m=widths,broad_member=wing_record,
                limit='Coarse radial profile only. Sparse/hidden intervals use 0.28 m radius. Broad members use observed PCA span with estimated 0.24 m thickness; no exact carved outline.')

def main():
    g.OUT=ROOT/'data/derived/totem-precinct-forms';g.OUT.mkdir(exist_ok=True);g.ASSETS.clear();g.FEATURES.clear();g.COLORS.update(cedar=[.43,.25,.13])
    forms=[]
    for i,(xy,h,label,note,wing) in enumerate(POLES):
        record=pole_profile(f'TotemMeasured_{i+1:02d}',xy,h,'SP_totem_precinct',wing);record.update(component=f'TotemMeasured_{i+1:02d}',identity=label,identity_limit=note);forms.append(record)
    forms.append(estimated_rear_pole('ChiefWakasRearEstimate',[1620.72,-362.96],8.8,[.38,.40,.34,.37,.32,.29,.22]))
    forms.append(estimated_rear_pole('SkyChiefRearEstimate',[1621.51,-369.26],7.4,[.44,.46,.38,.40,.33,.29,.25]))
    g.feature('SP_totem_precinct','Totem Pole precinct measured open-display silhouettes',[
        'data/raw/city/public-art-park-records-0.json','https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId=91','https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId=92','https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf','manifests/named-totem-sculptures-survey.json','evidence/corridor/ortho-utm/named-totem-sculptures.json','data/routes/raw/osm/park-map-20260927.osm'],
        dict(centre_local_m=np.mean([p[0] for p in POLES],axis=0).tolist(),individual_forms=forms),
        dict(hidden_profile_radius_m=.28,broad_member_thickness_m=.24,material='Unpatterned cedar review material; no invented culturally specific carving or paint'),
        'Six individually measured open-display forms and two explicitly estimated canopy-hidden rear envelopes. Rear positions have a 2 m working uncertainty and heights have a 2.5 m uncertainty; these are not surveyed dimensions. Name-to-pole crosswalk is provisional where source points conflict. No carving, plaques or visitor barriers; full precinct acceptance is false.')
    record=pole_profile('YeltonMemorial',[1585.8,-388.3],14.67,'SP_yelton_pole',[14.2,14.67])
    g.feature('SP_yelton_pole','Yelton Memorial Pole coarse silhouette',[
        'https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId=563','manifests/named-totem-sculptures-survey.json','evidence/corridor/ortho-utm/named-totem-sculptures.json','data/routes/raw/osm/park-map-20260927.osm'],record,
        dict(hidden_body_profile='Upper narrow axis and broad top fit classified returns; much of the body is canopy masked, so hidden band radii remain estimated'),
        'Source-located memorial pole envelope only. No carved figures, exact wing contour or painted artwork. Branch returns are excluded by classification and radius but sparse airborne data does not independently certify the body dimensions.')
    fid='SP_people_amongst';q,c=g.survey('totem-sculptures');s=q[(q[:,0]>1581)&(q[:,0]<1587)&(q[:,1]>-434.5)&(q[:,1]<-433)&(q[:,2]>7.5)&(q[:,2]<8.65)&(c==1)];centre=s[:,:2].mean(0);_,vec=np.linalg.eigh(np.cov(s[:,:2].T));axis=vec[:,-1]
    if axis[0]<0:axis=-axis
    normal=np.array([-axis[1],axis[0]]);st=(s[:,:2]-centre)@axis;ends=np.percentile(st,[2,98]);A=np.c_[st,np.ones(len(st))];coef=np.linalg.lstsq(A,s[:,2],rcond=None)[0];terrain=TerrainQuery([1579,-437,1589,-430])
    for i,d in enumerate([ends[0]+.16,ends[1]-.16]):
        xy=centre+axis*d;h=float(d*coef[0]+coef[1]);outline=np.array([xy+axis*a+normal*b for a,b in [(-.29,-.25),(.29,-.25),(.29,.25),(-.29,.25)]])
        prism(f'SM_PeopleSouth_Pier_{i}',outline,float(terrain.height(xy))-.16,h+.27,'cedar',fid)
    outline=np.array([centre+axis*a+normal*b for a,b in [(ends[0],-.15),(ends[1],-.15),(ends[1],.15),(ends[0],.15)]]);h=(outline-centre)@axis*coef[0]+coef[1]
    prism('SM_PeopleSouth_SlopedCrossbeam',outline,h-.42,h,'cedar',fid)
    # Ortho shows a narrow beam/shadow beside the gift shop. City images 912
    # and 914 show this portal between the building, trees and north waterfront.
    # Airborne returns do not isolate the beam, so the pose remains an estimate.
    north_centre=np.array([1591.0,-339.8]);north_axis=np.array([.50,-.8660254]);north_normal=np.array([-north_axis[1],north_axis[0]])
    nt=TerrainQuery([1587,-345,1596,-335]);ng=float(nt.height(north_centre));north_ends=np.array([-2.25,2.25])
    for i,d in enumerate(north_ends):
        xy=north_centre+north_axis*d;outline=np.array([xy+north_axis*a+north_normal*b for a,b in [(-.32,-.25),(.32,-.25),(.32,.25),(-.32,.25)]])
        prism(f'SM_PeopleNorthEstimate_Pier_{i}',outline,float(nt.height(xy))-.15,ng+4.5+.16*d+.2,'cedar',fid)
    outline=np.array([north_centre+north_axis*a+north_normal*b for a,b in [(-2.55,-.17),(2.55,-.17),(2.55,.17),(-2.55,.17)]])
    nh=ng+4.5+(outline-north_centre)@north_axis*.16
    prism('SM_PeopleNorthEstimate_SlopedCrossbeam',outline,nh-.50,nh,'cedar',fid)
    g.feature(fid,'People Amongst the People: southern and approximate northern portals',[
        'https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId=424','https://vancouver.ca/files/cov/people-amongst-the-people-susan-point.pdf','manifests/named-totem-sculptures-survey.json','evidence/corridor/ortho-utm/named-totem-sculptures.json'],
        dict(centre_local_m=centre.tolist(),beam_returns=len(s),beam_axis=axis.tolist(),beam_span_m=float(np.diff(ends)[0]),beam_height_fit=coef.tolist(),beam_median_residual_m=float(np.median(abs(A@coef-s[:,2]))),terrain_inputs=terrain.inputs,
             north_portal=dict(centre_local_m=north_centre.tolist(),axis=north_axis.tolist(),position_uncertainty_m=3.0,height_uncertainty_m=1.0,rotation_uncertainty_deg=20,method='City photos 912/914 setting plus 2022 ortho beam/shadow; source-bounded estimate, no isolated LiDAR beam fit'),
             southwest_portal=dict(status='unplaced',official_fact='Southwest of the path, toward the playing fields',candidate_search_bounds_local_m=[[1543,-398,1564,-380],[1564,-388,1584,-368]],reason='Trees conceal both plausible grass-side sites; survey returns do not isolate two posts and a beam. No unique photo-to-ground control distinguishes the candidates. A ground photo with the gift shop and path bend together, or a site plan with post centres, is needed.')),
        dict(pier_width_m=.58,pier_depth_m=.5,beam_depth_m=.30,beam_height_m=.42,meaning='Primary City/artist description confirms three sloped timber portals; the south open gate is isolated in survey. Cross-sections and upright shape are estimated M1 envelopes.'),
        'Southern portal is survey fitted; northern portal is a bounded setting/ortho estimate. Southwest portal remains visibly missing, with two candidate areas and the exact missing source control recorded. Carved figures, colour patterns and exact post outlines remain unfinished.')
    for a in g.ASSETS:a['collision_reason']='Closed individual source-fitted envelope; no large obstacle spans the portal opening. Source-name and hidden-shape uncertainty remain recorded.'
    d=dict(schema_version=1,revision='totem-precinct-m1-r2',assets=g.ASSETS,features=g.FEATURES,acceptance=False,reference_rights='City survey derivatives OGL-Vancouver; OSM rear positions and candidate names require ODbL attribution. Public-art images, carved design and text are not distributed.',source_period='City 2022 survey and ortho; current official identities',target_period='September 2026')
    save_json(ROOT/'manifests/totem-precinct-forms.json',d);print(json.dumps(dict(assets=len(g.ASSETS),sha256=digest(ROOT/'manifests/totem-precinct-forms.json'))))

if __name__=='__main__':main()
