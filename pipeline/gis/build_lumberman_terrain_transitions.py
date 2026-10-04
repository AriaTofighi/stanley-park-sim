"""Prepare bounded raw-return road and walking corrections, without editing terrain."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon,mapping
from acquire_sources import save_json
from lumberman_integration_geometry import FacilitySolids,sha

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/derived/lumberman-facilities'
SETTINGS='manifests/lumberman-transition-settings.json'
DEFAULTS=dict(road_osm_ways=['58361906','58361911','1353319157'],
    road_station_step_m=2.,west_outer_u_m=-44.,west_full_u_m=-36.,
    east_outer_u_m=40.,east_full_u_m=30.,
    outer_road_half_width_m=4.,road_bank_fade_m=3.,road_width_blend_length_m=10.,
    walking_outer_v_m=-20.,walking_full_v_m=-16.,walking_side_fade_m=1.,
    fit_road_u_radius_m=1.75,fit_road_v_radius_m=2.5,fit_walk_v_radius_m=1.25,
    fit_residual_limit_m=.10,
    accuracy='Raw 2022 LiDAR elevations and current OSM alignment; bank fade limits and outer road width are explicit M1 surface engineering estimates. No new surveyed construction dimensions.',
    boundary_rule='Match actual saved deck/floor planes at the existing replacement cut. Fade to unchanged terrain at all new outer edges; keep the lower passage separate.')


def robust_plane(uv,z,limit):
    if len(z)<30:raise ValueError('Too few raw returns for a Lumberman transition control')
    a=np.column_stack((np.ones(len(z)),uv))
    keep=abs(z-np.quantile(z,.3))<.4
    for _ in range(8):
        if keep.sum()<25:raise ValueError('Raw-return plane lost source support')
        coef=np.linalg.lstsq(a[keep],z[keep],rcond=None)[0]
        keep=abs(z-a@coef)<limit
    error=z[keep]-a[keep]@coef
    return coef,dict(candidate_returns=len(z),inliers=int(keep.sum()),
        rms_m=float(np.sqrt(np.mean(error**2))),p95_m=float(np.quantile(abs(error),.95)))


def main():
    if not (ROOT/SETTINGS).exists():save_json(ROOT/SETTINGS,DEFAULTS)
    cfg=json.loads((ROOT/SETTINGS).read_text(encoding='utf8'))
    f=FacilitySolids(ROOT)
    survey_path='data/derived/named-lumberman-arch-survey.npz'
    osm_path='data/routes/raw/osm/park-map-20260927.osm'
    with np.load(ROOT/survey_path) as package:q,classification=package['xyz'],package['classification']
    xy=q[:,:2]-f.origin;u=xy@f.u;v=xy@f.v-f.skew*u;uv=np.column_stack((u,v));z=q[:,2]
    tree=ET.parse(ROOT/osm_path).getroot();tr=Transformer.from_crs(4326,3157,always_xy=True)
    nodes={n.get('id'):tr.transform(float(n.get('lon')),float(n.get('lat'))) for n in tree.findall('node')}
    centre_points=[];osm_rows=[]
    for way in tree.findall('way'):
        if way.get('id') not in cfg['road_osm_ways']:continue
        coords=[f.uv(np.asarray(nodes[n.get('ref')])-[489600,5461100]) for n in way.findall('nd')]
        centre_points.extend(coords)
        osm_rows.append(dict(id=way.get('id'),url='https://www.openstreetmap.org/way/'+way.get('id'),
            timestamp=way.get('timestamp'),version=way.get('version'),tags={t.get('k'):t.get('v') for t in way.findall('tag')}))
    centre_points=np.unique(np.asarray(centre_points),axis=0);centre_points=centre_points[np.argsort(centre_points[:,0])]
    deck_uv=np.array([f.uv(p) for p in f.footprints['road_deck'].exterior.coords]);umin,umax=deck_uv[:,0].min(),deck_uv[:,0].max()
    vlo,vhi=deck_uv[:,1].min(),deck_uv[:,1].max();deck_centre=(vlo+vhi)/2;deck_half=(vhi-vlo)/2
    floor_uv=np.array([f.uv(p) for p in f.footprints['terrain_and_existing_walk'].exterior.coords]);walk_end=floor_uv[:,1].min()
    opening_uv=np.array([f.uv(p) for p in f.footprints['walkthrough_opening'].exterior.coords]);walk_half=max(abs(opening_uv[:,0]))
    vertices,weights,faces,paint,groups,controls=[],[],[],[],[],[]

    def add_grid(rows,group,core_bands):
        start=len(vertices)
        for row in rows:
            for point,height,weight in row:vertices.append([*point,height]);weights.append(weight)
        width=len(rows[0])
        for i in range(len(rows)-1):
            for j in range(width-1):
                a=start+i*width+j;b=a+1;c=a+width+1;d=a+width
                for face in ([a,b,c],[a,c,d]):
                    p=np.asarray(vertices)[face,:2]
                    if np.linalg.det(np.column_stack((p[1]-p[0],p[2]-p[0])))<0:face=face[::-1]
                    faces.append(face);paint.append(group.startswith('road') and j in core_bands);groups.append(group)

    for side,inner,outer,full in [('west',umin,cfg['west_outer_u_m'],cfg['west_full_u_m']),
                                  ('east',umax,cfg['east_outer_u_m'],cfg['east_full_u_m'])]:
        sign=1 if outer>inner else -1
        stations=np.r_[np.arange(inner,outer,sign*cfg['road_station_step_m']),outer]
        rows=[]
        for station in stations:
            t=min(1.,abs(station-inner)/cfg['road_width_blend_length_m'])
            map_centre=float(np.interp(station,centre_points[:,0],centre_points[:,1]))
            centre=(1-t)*deck_centre+t*map_centre
            half=(1-t)*deck_half+t*cfg['outer_road_half_width_m']
            take=(abs(u-station)<cfg['fit_road_u_radius_m'])&(abs(v-centre)<cfg['fit_road_v_radius_m'])&np.isin(classification,[1,2])&(z>3)&(z<8)
            coef,stats=robust_plane(uv[take]-[station,centre],z[take],cfg['fit_residual_limit_m'])
            if abs(coef[2])>.15:raise ValueError('Unresolved road cross slope at u='+str(station))
            source_classes={str(int(c)):int((classification[take]==c).sum()) for c in np.unique(classification[take])}
            endpoint=bool(abs(station-inner)<1e-6)
            longitudinal=1. if abs(station-inner)<=abs(full-inner) else max(0.,1-abs(station-full)/abs(outer-full))
            row=[]
            for offset,lateral in [(-half-cfg['road_bank_fade_m'],0.),(-half,1.),(0.,1.),(half,1.),(half+cfg['road_bank_fade_m'],0.)]:
                b=centre+offset;point=f.xy([station,b])
                height=float(np.asarray(f.data['road_plane_coefficients'])@[1,station,b]) if endpoint else float(coef@[1,0,offset])
                row.append((point,height,longitudinal*lateral))
            rows.append(row)
            controls.append(dict(kind='road_'+side,u_m=float(station),centre_v_m=centre,half_width_m=half,
                plane_about_station_centre=coef.tolist(),endpoint_uses_saved_deck_plane=endpoint,
                longitudinal_weight=longitudinal,source_classes=source_classes,fit=stats))
        add_grid(rows,'road_'+side,[1,2])

    rows=[]
    for station in np.r_[np.arange(walk_end,cfg['walking_outer_v_m'],-2.),cfg['walking_outer_v_m']]:
        take=(abs(u)<walk_half)&(abs(v-station)<cfg['fit_walk_v_radius_m'])&(classification==2)&(z>2)&(z<8)
        coef,stats=robust_plane(uv[take]-[0,station],z[take],cfg['fit_residual_limit_m'])
        endpoint=bool(abs(station-walk_end)<1e-6)
        longitudinal=1. if station>=cfg['walking_full_v_m'] else max(0.,(station-cfg['walking_outer_v_m'])/(cfg['walking_full_v_m']-cfg['walking_outer_v_m']))
        row=[]
        for a,lateral in [(-walk_half-cfg['walking_side_fade_m'],0.),(-walk_half,1.),(0.,1.),(walk_half,1.),(walk_half+cfg['walking_side_fade_m'],0.)]:
            point=f.xy([a,station])
            height=float(np.asarray(f.data['floor_plane_coefficients'])@[1,a,station]) if endpoint else float(coef@[1,a,0])
            row.append((point,height,longitudinal*lateral))
        rows.append(row);controls.append(dict(kind='south_walk',v_m=float(station),plane_about_station_centre=coef.tolist(),
            endpoint_uses_saved_floor_plane=endpoint,longitudinal_weight=longitudinal,source_classes={'2':int(take.sum())},fit=stats))
    add_grid(rows,'south_walk',[])
    vertices=np.array(vertices);faces=np.array(faces,dtype=np.int32);weights=np.array(weights)
    footprint=shapely.union_all(shapely.polygons(vertices[faces,:2]))
    if footprint.intersection(f.footprints['terrain_and_existing_walk']).area>1e-6:
        raise ValueError('Transition intrudes into existing lower facility cut')
    mesh=OUT/'terrain-transition-cells.npz';np.savez_compressed(mesh,vertices=vertices,faces=faces,weights=weights,paint_asphalt=np.array(paint))
    path='manifests/lumberman-terrain-transitions.json'
    doc=dict(schema_version=1,settings_path=SETTINGS,settings_sha256=sha(ROOT/SETTINGS),
        inputs=[dict(path=p,sha256=sha(ROOT/p)) for p in [SETTINGS,f.path,survey_path,osm_path]],
        mesh_path=mesh.relative_to(ROOT).as_posix(),mesh_sha256=sha(mesh),
        footprint=mapping(footprint),controls=controls,source_road_ways=osm_rows,
        cell_groups=groups,triangle_count=len(faces),method=cfg['accuracy'],
        patch_area_m2=float(footprint.area),existing_cut_overlap_m2=float(footprint.intersection(f.footprints['terrain_and_existing_walk']).area),
        integration='Apply LumbermanTerrainTransition.apply after all exact landmark/facility cuts and degenerate-face filtering, before tile assignment. It modifies retained terrain only. Refit affected route displays to the final terrain planes; do not touch main seawall pavement.',
        lower_passage_preserved=True,visual_acceptance=False,runtime_acceptance=False)
    save_json(ROOT/path,doc)
    print(json.dumps(dict(triangles=len(faces),controls=len(controls),area_m2=doc['patch_area_m2'],manifest=path)))


if __name__=='__main__':main()
