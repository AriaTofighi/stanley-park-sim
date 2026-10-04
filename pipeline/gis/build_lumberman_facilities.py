"""Located below-road washroom massing and open pedestrian passage.

Writes separate data for terrain/road replacement. It never edits terrain or
launches an application. Concealed dimensions are explicit M1 estimates.
"""
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, mapping
from acquire_sources import digest, save_json
import build_named_feature_blockouts as geom

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/derived/lumberman-facilities'


def fit_plane(xy,z,limit=.12):
    a=np.column_stack([np.ones(len(xy)),xy]);keep=np.ones(len(z),bool)
    for _ in range(6):
        coef=np.linalg.lstsq(a[keep],z[keep],rcond=None)[0]
        keep=np.abs(z-a@coef)<limit
    error=z[keep]-a[keep]@coef
    return coef,dict(candidate_returns=len(z),inliers=int(keep.sum()),rms_m=float(np.sqrt(np.mean(error**2))),p95_m=float(np.percentile(np.abs(error),95)))


def main():
    cfgpath='manifests/lumberman-facility-settings.json';cfg=json.loads((ROOT/cfgpath).read_text())
    geom.OUT=OUT;OUT.mkdir(exist_ok=True);geom.ASSETS.clear();geom.FEATURES.clear()
    geom.COLORS.update(green=[.24,.43,.055],glass=[.39,.45,.38],asphalt=[.12,.125,.12])
    centre=np.array(cfg['origin_local_xy_m']);v=np.array(cfg['axis_to_waterpark_xy']);v/=np.linalg.norm(v);u=np.array([v[1],-v[0]])
    skew=cfg['road_edge_skew_v_per_u']
    def xy(a,b): return centre+u*a+v*(b+skew*a)
    survey=np.load(ROOT/cfg['source_survey']);q=survey['xyz'].astype(float);cl=survey['classification']
    uv=(q[:,:2]-centre)@np.array([u,v]).T;uv[:,1]-=skew*uv[:,0]
    road=(np.abs(uv[:,0])<13)&(uv[:,1]>-3.5)&(uv[:,1]<1.5)&(q[:,2]>5.9)&(q[:,2]<6.65)
    roadcoef,roadstats=fit_plane(uv[road],q[road,2],.10)
    low=(np.abs(uv[:,0])<5)&(((uv[:,1]>6.0)&(uv[:,1]<9.0))|((uv[:,1]>-10)&(uv[:,1]<-7.5)))&(q[:,2]>2.4)&(q[:,2]<3.05)&(cl==2)
    floorcoef,floorstats=fit_plane(uv[low],q[low,2],.07)
    def height(a,b,coef): return float(coef@[1,a,b])
    def point(a,b,coef,offset=0): return [*xy(a,b),height(a,b,coef)+offset]
    fid='SP_lumberman_washrooms';depth=cfg['estimated_slab_depth_m'];half=cfg['facade_half_span_m'];back,front=cfg['road_edges_v_m'];flo,fhi=cfg['floor_edges_v_m'];gap=cfg['opening_width_m']/2
    def prism(name,a0,a1,b0,b1,bottom,top,mat,collision='complex'):
        corners=[(a0,b0),(a1,b0),(a1,b1),(a0,b1)]
        rows=[[point(a,b,coef,off) for a,b in corners] for coef,off in [bottom,top]]
        # rings uses upward top winding; closed solid includes a bottom face.
        geom.rings(name,rows,mat,fid);geom.ASSETS[-1]['collision']=collision
    prism('SM_LumbermanFacility_PedestrianFloor',-half,half,flo,fhi,(floorcoef,-.14),(floorcoef,.0),'concrete')
    prism('SM_LumbermanFacility_RoadDeck',-half,half,back,front,(roadcoef,-depth),(roadcoef,0),'asphalt')
    wall=cfg['wall_thickness_m']
    for side,lo,hi in [('West',-half,-gap),('East',gap,half)]:
        for tag,b0,b1 in [('Waterpark',front-wall,front),('Park',back,back+wall)]:
            prism(f'SM_LumbermanFacility_{side}_{tag}Facade',lo,hi,b0,b1,(floorcoef,0),(roadcoef,-depth),'stone')
        x0,x1=(lo,lo+wall) if side=='West' else (hi-wall,hi)
        prism(f'SM_LumbermanFacility_{side}_OuterReturn',x0,x1,back+wall,front-wall,(floorcoef,0),(roadcoef,-depth),'stone')
        x0,x1=(-gap-wall,-gap) if side=='West' else (gap,gap+wall)
        prism(f'SM_LumbermanFacility_{side}_PassageWall',x0,x1,back+wall,front-wall,(floorcoef,0),(roadcoef,-depth),'stone')
        # Visible green upper panels and closed door leaves identify the two
        # facility wings. Texture, real text, room plans and access are omitted.
        door_c=(lo+hi)/2
        constant=floorcoef.copy()
        prism(f'SM_LumbermanFacility_{side}_ClosedDoor',door_c-.52,door_c+.52,front+.002,front+.025,(constant,.0),(constant,2.05),'green','none')
        prism(f'SM_LumbermanFacility_{side}_UpperGreenBand',lo+.08,hi-.08,front+.002,front+.018,(roadcoef,-depth-.52),(roadcoef,-depth+.015),'green','none')
        for ix,a in enumerate(np.linspace(lo+.5,hi-.5,7)):
            prism(f'SM_LumbermanFacility_{side}_UpperPanel_{ix}',a-.34,a+.34,front+.02,front+.032,(roadcoef,-depth-.46),(roadcoef,-depth-.08),'glass','none')
    for edge,b in [('Waterpark',front),('Park',back)]:
        z=lambda a:height(a,b,roadcoef)
        posts=np.linspace(-half,half,15)
        for i,a in enumerate(posts):geom.beam(f'SM_LumbermanFacility_{edge}_ParapetPost_{i}',[*xy(a,b),z(a)],[*xy(a,b),z(a)+cfg['parapet_height_m']],.14,'stone',fid)
        for k,off in enumerate([.18,.9]):geom.beam(f'SM_LumbermanFacility_{edge}_ParapetRail_{k}',[*xy(-half,b),z(-half)+off],[*xy(half,b),z(half)+off],.07,'steel',fid)
    # These three distinct polygons let the integration remove obsolete low
    # terrain, a road patch and pedestrian overlays without moving the route.
    def rectangle(a0,a1,b0,b1): return Polygon([xy(a0,b0),xy(a1,b0),xy(a1,b1),xy(a0,b1)])
    footprint=rectangle(-half,half,flo,fhi);deck=rectangle(-half,half,back,front);opening=rectangle(-gap,gap,back,front)
    replacement=OUT/'replacement-footprints-local.geojson'
    save_json(replacement,dict(type='FeatureCollection',crs='local XY metres; EPSG3157 minus[489600,5461100]',features=[dict(type='Feature',properties=dict(id=tag,purpose=purpose),geometry=mapping(poly)) for tag,purpose,poly in [('terrain_and_existing_walk','Replace ground and overlaid pedestrian faces in this region, keep supplied lower floor. Root must stitch perimeter to the surrounding terrain; do not retain a road-height terrain curtain across the passage.',footprint),('road_deck','Replace only the road surface in this footprint with the supplied upper deck. Do not cut adjacent seawall cycling pavement.',deck),('walkthrough_opening','Keep this floor-to-soffit pedestrian passage clear of terrain and facade collision.',opening)]]))
    assets=geom.ASSETS
    for a in assets:
        a['collision_reason']='Closed physical building or slab envelope' if a['collision']=='complex' else 'Small facade/rail detail; no separate collision'
    controls=[dict(id=f'floor_{i}',xy_local_m=xy(a,b).tolist(),z_cgvd2013_m=height(a,b,floorcoef),uv_m=[a,b]) for i,(a,b) in enumerate([(-gap,flo),(gap,flo),(-gap,fhi),(gap,fhi),(0,back),(0,front)])]
    roof=[dict(id=f'deck_{i}',xy_local_m=xy(a,b).tolist(),top_cgvd2013_m=height(a,b,roadcoef),underside_cgvd2013_m=height(a,b,roadcoef)-depth,uv_m=[a,b]) for i,(a,b) in enumerate([(-half,back),(half,back),(half,front),(-half,front),(0,0)])]
    clearance=min(height(a,b,roadcoef)-depth-height(a,b,floorcoef) for a,b in [(-gap,back),(gap,back),(gap,front),(-gap,front)])
    feature=dict(id=fid,name='Lumberman’s Arch below-road washrooms and pedestrian underpass',replace_cover_ids=[],limits='M1 massing: interior rooms omitted, central pedestrian passage open. Hidden width, slab depth, facade spans, door/window layout and rails are estimates. No current facade survey or independent accuracy control.',source_identity_verified=True,release_accepted=False)
    doc=dict(schema_version=1,settings_path=cfgpath,settings_sha256=digest(ROOT/cfgpath),source_inputs=[dict(path=p,sha256=digest(ROOT/p)) for p in [cfg['source_survey'],'manifests/named-lumberman-arch-survey.json','data/raw/facilities/PS20180362-ADD2.pdf','data/raw/corridor/maze-gates-2025.pdf','data/routes/raw/osm/park-map-20260927.osm','evidence/corridor/ortho-utm/named-lumberman-wide.json']],assets=assets,features=[feature],replacement_footprints_path=replacement.relative_to(ROOT).as_posix(),replacement_footprints_sha256=digest(replacement),plane_convention='z=coef[0]+coef[1]*u+coef[2]*v; localXY=origin+road_u*u+waterpark_v*(v+skew*u)',frame=dict(origin=centre.tolist(),road_u=u.tolist(),waterpark_v=v.tolist(),skew=skew),road_plane_coefficients=roadcoef.tolist(),road_fit=roadstats,floor_plane_coefficients=floorcoef.tolist(),floor_fit=floorstats,floor_controls=controls,roof_controls=roof,minimum_estimated_clearance_m=clearance,opening_width_estimate_m=cfg['opening_width_m'],geometry_checks=dict(finite=True,nondegenerate=True,minimum_clearance_above_2_4m=clearance>2.4),required_integration=['Cut the explicit ground/pedestrian footprint and road-deck replacement area, then stitch floor perimeter and deck edges.','Keep seawall cycling pavement untouched. The lower passage belongs to the pedestrian footway, not the main cycling loop.','Review terrace levels, portal view and all seams in Blender, then walk through and cross the road deck in the application.'],licences=dict(lidar='City Open Government Licence Vancouver',osm='ODbL-1.0; attribution © OpenStreetMap contributors',reference_documents='Reference only; PDF/photo pixels not incorporated or redistributed'),release_accepted=False,application_review='not run')
    save_json(ROOT/'manifests/lumberman-facility-blockouts.json',doc)
    print(json.dumps(dict(meshes=len(assets),triangles=sum(a['triangles'] for a in assets),road=roadstats,floor=floorstats,clearance=clearance)))


if __name__=='__main__': main()
