"""Measured curved memorial wall, with primary photo identity review."""
import json
import numpy as np
from scipy.interpolate import PchipInterpolator
from shapely.geometry import LineString
from shapely import distance,points,line_locate_point
import build_named_feature_blockouts as g
from acquire_sources import save_json,digest
from review_siwash_approach import TerrainQuery

ROOT=g.ROOT
XY=np.array([[-462.2547,-973.2831],[-458.9862,-975.0461],[-455.2767,-974.4642],[-451.9286,-972.7254],[-449.3783,-970.0067],[-447.6278,-967.2865]])

def wall(name,xy,base,top,width,material):
    delta=np.gradient(xy,axis=0);delta/=np.linalg.norm(delta,axis=1)[:,None];n=np.column_stack((-delta[:,1],delta[:,0]))*width/2
    v=np.array([[*(p+off),z] for p,d,b,t in zip(xy,n,base,top) for off,z in [(-d,b),(d,b),(d,t),(-d,t)]])
    faces=[(3,2,1,0)]
    for i in range(len(xy)-1):
        for j in range(4):k=(j+1)%4;faces.append((i*4+j,i*4+k,(i+1)*4+k,(i+1)*4+j))
    faces.append(tuple((len(xy)-1)*4+j for j in range(4)))
    g.mesh(name,v,faces,material,'SP_air_india','complex')

def main():
    g.OUT=ROOT/'data/derived/air-india';g.OUT.mkdir(exist_ok=True);g.ASSETS.clear();g.FEATURES.clear();g.COLORS['wood']=[.40,.25,.13]
    q,c=g.survey('air-india');line=LineString(XY);s=line_locate_point(line,points(q[:,:2]));near=distance(points(q[:,:2]),line)<.65
    # Low vegetation class includes the wall. The continuous narrow vertical
    # face agrees with the primary designer photos; high canopy is rejected.
    selected=q[near&(c!=2)&(q[:,2]<8.8)&(q[:,2]>6.7)];st=s[near&(c!=2)&(q[:,2]<8.8)&(q[:,2]>6.7)]
    knots=np.arange(0,line.length+2,2);heights=[]
    for x in knots:
        v=selected[np.abs(st-min(x,line.length))<1.1,2]
        heights.append(float(np.percentile(v,90)) if len(v) else np.nan)
    valid=np.isfinite(heights);heights=np.array(heights);h=np.interp(knots,knots[valid],heights[valid])
    # A coarse monotone crest prevents isolated twig returns from creating
    # false pointed crenellations. The west end is the high abrupt termination.
    h=np.minimum.accumulate(h);station=np.linspace(0,line.length,41);xy=np.array([line.interpolate(x).coords[0] for x in station]);top=PchipInterpolator(knots,h)(station)
    base=g.HEIGHT(xy[:,[1,0]])-.18;base=np.minimum(base,top-.25)
    wall('SM_AirIndia_CurvedStoneWall',xy,base,top-.14,.35,'stone')
    wall('SM_AirIndia_StoneCap',xy,top-.14,top,.43,'concrete')
    # A second narrow raised arc sits north of the main wall in the low-return
    # survey bands. The designer photo confirms a separate low stone/name
    # seat with a timber section. Its hidden ends and section split are estimates.
    seat_controls=np.array([[-460.9,-969.1],[-459.6,-967.6],[-458.1,-966.4],[-456.4,-965.5],[-454.6,-965.25]])
    seat_line=LineString(seat_controls);seat_s=np.linspace(0,seat_line.length,27);seat_xy=np.array([seat_line.interpolate(x).coords[0] for x in seat_s])
    seat_near=(distance(points(q[:,:2]),seat_line)<.48)&(q[:,2]>6.55)&(q[:,2]<7.5)&(c!=2)
    seat_samples=q[seat_near];seat_st=line_locate_point(seat_line,points(seat_samples[:,:2]));seat_knots=np.linspace(0,seat_line.length,6)
    seat_heights=[]
    for st in seat_knots:
        v=seat_samples[np.abs(seat_st-st)<1.15,2];seat_heights.append(float(np.median(v)) if len(v) else 6.85)
    seat_top=PchipInterpolator(seat_knots,seat_heights)(seat_s);seat_terrain=TerrainQuery([-463,-972,-452,-963]);seat_ground=np.array([seat_terrain.height(p) for p in seat_xy]);seat_top=np.clip(seat_top,seat_ground+.30,seat_ground+.72)
    wall('SM_AirIndia_LowNameSeat_Base',seat_xy,seat_ground-.12,seat_top-.12,.63,'stone')
    split=14
    wall('SM_AirIndia_LowNameSeat_StoneTop',seat_xy[:split+1],seat_top[:split+1]-.12,seat_top[:split+1],.70,'concrete')
    wall('SM_AirIndia_LowNameSeat_TimberTop',seat_xy[split:],seat_top[split:]-.12,seat_top[split:],.70,'wood')
    g.feature('SP_air_india','Air India Memorial main wall and low name/seat arc',[
        'https://elac.ca/projects/air-india-memorial/',
        'https://elac.ca/LEES+Associates/wp-content/uploads/2016/09/IMG_8854-10.jpg',
        'https://elac.ca/LEES+Associates/wp-content/uploads/2016/09/4326-2.jpg',
        'https://parkboardmeetings.vancouver.ca/2007/070402/air_india_memorial.pdf',
        'https://vanmapp1.vancouver.ca/googleKml/stanley_park_monuments/',
        'data/routes/raw/osm/park-map-20260927.osm','manifests/named-air-india-survey.json','evidence/corridor/ortho-utm/named-air-india.json'],
        dict(centre_local_m=xy.mean(0).tolist(),source_way_id='363402998',source_way_role='Curved retaining-wall geometry, independently matched to the narrow survey face and primary memorial photographs',
             centreline_local_xy_m=XY.tolist(),fitted_wall_length_m=line.length,wall_returns=len(selected),crest_stations_m=knots.tolist(),crest_heights_cgvd2013_m=h.tolist(),
             low_seat_arc=dict(centreline_local_xy_m=seat_controls.tolist(),length_m=seat_line.length,nearby_low_returns=len(seat_samples),height_knots_m=seat_heights,terrain_inputs=seat_terrain.inputs,method='Narrow raised low-return band north of the wall, matched to the separate stone/timber seat shown in the primary designer photograph. Canopy conceals exact ends.'),
             photo_inspection='Read-only Chrome on 2026-09-27: designer photos show tall abrupt west end, stone cap and separate curved low name/seat with timber section. Photos were viewed, not copied into distributed geometry.'),
        dict(wall_thickness_m=.35,cap_thickness_m=.14,cap_width_m=.43,ground_embed_m=.18,low_seat_width_m=.70,low_seat_position_uncertainty_m=1.5,low_seat_height_uncertainty_m=.25,timber_fraction='About half of the coarse arc, estimated from the photo; exact split and individual slats unfinished',uncertainty='At least +/-0.3 m for concealed main-wall face width and crest between sparse returns'),
        'Main curved wall plus a source-bounded low name/seat envelope. Exact arc ends, timber split, names, inscriptions, paving stones and masonry detail remain unfinished. Low arc has 1.5 m working position uncertainty. City point is not the model origin. Gazebo retaining curve and north grass strip are not mislabeled as memorial forms. No photo/inscription reproduction licence is inferred.')
    for a in g.ASSETS:a['collision_reason']='Closed narrow wall follows source curve; direct triangle collision, no solid polygon across the memorial garden. Live collision still requires review.'
    result=dict(schema_version=1,revision='air-india-m1-r2',assets=g.ASSETS,features=g.FEATURES,acceptance=False,
        source_period='City 2022 survey/ortho, City2007 design and designer photos uploaded2016; OSM geometry current2026',target_period='September2026',
        reference_rights='City survey derivatives OGL-Vancouver; OSM wall line ODbL attributed in source register. Architect photos and text reference only, not distributed.',
        input_hashes={'manifests/named-air-india-survey.json':digest(ROOT/'manifests/named-air-india-survey.json')})
    save_json(ROOT/'manifests/air-india-blockout.json',result)
    print(json.dumps(dict(assets=len(g.ASSETS),wall_returns=len(selected),crest_h=h.tolist(),manifest_sha256=digest(ROOT/'manifests/air-india-blockout.json'))))

if __name__=='__main__':main()
