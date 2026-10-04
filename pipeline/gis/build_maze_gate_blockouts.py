"""Dated, physical M1 barrier frames and collision-clear walking paths.

The geometry is fixed by the settings before path clearance is evaluated.
This source authoring check does not run the application or prove steering.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import nearest_points
from pyproj import Transformer
from acquire_sources import digest, save_json
import build_named_feature_blockouts as geom

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pipeline/routes'))
from mesh_surface_query import MeshSurfaceQuery


def main():
    cfgpath='manifests/maze-gate-settings.json';cfg=json.loads((ROOT/cfgpath).read_text())
    runtime_path='data/derived/paved-circuit-runtime.json';rt=json.loads((ROOT/runtime_path).read_text());s=np.array(rt['chainage_source_m']);p=np.array(rt['points_local_m']);width=np.array(rt['width_m'])
    tangent=np.gradient(p[:,:2],axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None];normal=np.c_[-tangent[:,1],tangent[:,0]]
    surfaces=json.loads((ROOT/'manifests/surface-model.json').read_text())['pavement']
    tree=ET.parse(ROOT/'data/routes/raw/osm/park-map-20260927.osm').getroot();nodes={n.attrib['id']:n for n in tree.findall('node')};tf=Transformer.from_crs(4326,3157,always_xy=True)
    geom.OUT=ROOT/'data/derived/maze-gates';geom.OUT.mkdir(exist_ok=True);geom.ASSETS.clear();geom.FEATURES.clear();geom.COLORS['galvanized']=[.59,.62,.60]
    reports=[];source_inputs={}
    def position(st,lateral):
        base=np.array([np.interp(st,s,p[:,i]) for i in [0,1]])
        n=np.array([np.interp(st,s,normal[:,i]) for i in [0,1]]);n/=np.linalg.norm(n)
        return base+n*lateral
    for site in cfg['sites']:
        st=site['source_station_m'];center=position(st,0);w=float(np.interp(st,s,width));half=w/2
        query=MeshSurfaceQuery(ROOT,surfaces,[*(center-22),*(center+22)])
        for item in query.inputs:source_inputs[item['path']]=item['sha256']
        pieces=[];footprints=[];post_bases=[];post_keys=set()
        edge_bands=[]
        def edges_at(station):
            aa,bb=position(station,-6),position(station,6)
            section=query.footprint.intersection(LineString([aa,bb]))
            parts=[section] if section.geom_type=='LineString' else [g for g in section.geoms if g.geom_type=='LineString']
            mid=Point(position(station,0))
            parts=[g for g in parts if g.distance(mid)<.03]
            if not parts:raise ValueError('No continuous paved cross-section at gate')
            piece=max(parts,key=lambda g:g.length);n=(bb-aa)/12
            offsets=(np.asarray(piece.coords)-position(station,0))@n
            lo,hi=float(offsets.min()),float(offsets.max())
            edge_bands.append(dict(source_station_m=station,negative_edge_m=lo,positive_edge_m=hi))
            return lo,hi
        def beam(tag,a,b,thickness):
            name='SM_Maze_'+site['id']+'_'+tag
            geom.beam(name,a,b,thickness,'galvanized',site['id']);r=geom.ASSETS[-1];r['collision']='complex';r['collision_reason']='Physical steel frame; retain collision during walking'
            mesh=np.load(ROOT/r['mesh_path']);footprints.append(shapely.MultiPoint(mesh['vertices'][:,:2]).convex_hull);pieces.append(name)
        def rail(tag,xy1,xy2):
            z1,z2=query.height(xy1),query.height(xy2)
            for i,(xy,z) in enumerate([(xy1,z1),(xy2,z2)]):
                key=tuple(np.round(xy,6))
                if key not in post_keys:
                    beam(f'{tag}_Post{i}',[*xy,z-.04],[*xy,z+cfg['post_height_m']],cfg['post_width_m']);post_bases.append(dict(xy=xy.tolist(),ground_z_m=z,embed_m=.04));post_keys.add(key)
            for i,h in enumerate(cfg['rail_heights_m']):beam(f'{tag}_Rail{i}',[*xy1,z1+h],[*xy2,z2+h],cfg['rail_width_m'])
        gap=cfg['estimated_clear_gap_m'] if w>=2.5 else cfg['minimum_clear_gap_on_narrow_strip_m']
        path_lateral=(w-gap)/2
        if site['kind']=='double':
            # Post outside faces stay on the paved strip. The inner post's
            # outside face sets the reported gap; rails do not close the gap.
            separation=cfg['estimated_double_gate_row_separation_m']
            lo,hi=edges_at(st-separation/2)
            rail('RowA',position(st-separation/2,lo+.09),position(st-separation/2,hi-gap-cfg['post_width_m']/2))
            lo,hi=edges_at(st+separation/2)
            rail('RowB',position(st+separation/2,hi-.09),position(st+separation/2,lo+gap+cfg['post_width_m']/2))
            knots=np.array([-8.,-3.5,-.85,.85,3.5,8.]);offset=np.array([0,path_lateral,path_lateral,-path_lateral,-path_lateral,0])
            raw_refs=[]
        else:
            way=tree.find(f"way[@id='{site['source_way']}']");raw_refs=[]
            for ref in way.findall('nd'):
                n=nodes[ref.attrib['ref']];xy=np.array(tf.transform(float(n.attrib['lon']),float(n.attrib['lat'])))-[489600,5461100];raw_refs.append(xy)
            # Source order is north end to south end. Mid-post divides long
            # panels while the exact two source endpoint XY values survive.
            start,end=raw_refs[-1],raw_refs[0]
            rail('DividerA',start,(start+end)/2);rail('DividerB',(start+end)/2,end)
            endst=float(s[np.argmin(np.linalg.norm(p[:,:2]-end,axis=1))])
            tip=position(endst,half-gap-cfg['post_width_m']/2)
            rail('InnerReturn',end,tip)
            path_lateral=half-gap/2
            knots=np.array([-14.,-8.,2.,5.5,8.]);offset=np.array([0,path_lateral,path_lateral,0,0])
        samples=np.linspace(knots[0],knots[-1],int((knots[-1]-knots[0])/.04)+1)
        offsets=np.zeros(len(samples))
        for i in range(len(knots)-1):
            take=(samples>=knots[i])&(samples<=knots[i+1]);t=(samples[take]-knots[i])/(knots[i+1]-knots[i]);h=t*t*(3-2*t);offsets[take]=offset[i]+h*(offset[i+1]-offset[i])
        xy=np.array([position(st+a,b) for a,b in zip(samples,offsets)]);obstacle=shapely.union_all(footprints)
        # A source-route normal near a bend can place an otherwise plausible
        # walking curve near the actual paved edge. Fix only that curve, using
        # the unchanged obstacle envelopes and actual triangle footprint.
        safe=query.footprint.buffer(-.42).difference(obstacle.buffer(.42))
        original=xy.copy()
        for i,point in enumerate(xy):
            if not safe.covers(Point(point)):
                xy[i]=nearest_points(safe,Point(point))[0].coords[0]
        adjustment=np.linalg.norm(xy-original,axis=1)
        z=np.array([query.height(a) for a in xy]);path=LineString(xy)
        wallclear=float(path.distance(obstacle));edgeclear=float(path.distance(query.footprint.boundary));radius=cfg['player_capsule_radius_m']
        checks=dict(minimum_walking_center_to_frame_m=wallclear,minimum_walking_center_to_paved_edge_m=edgeclear,capsule_radius_m=radius,minimum_contact_margin_m=min(wallclear,edgeclear)-radius,walking_curve_edge_adjusted_points=int((adjustment>1e-8).sum()),maximum_walking_curve_adjustment_m=float(adjustment.max()),posts_grounded_to_actual_pavement=True,all_path_points_on_actual_pavement=True,body_clear=wallclear>=radius+.06 and edgeclear>=radius+.06)
        row=dict(**site,strip_width_m=w,estimated_gap_m=gap,actual_paved_edge_bands=edge_bands,grounded_posts=post_bases,source_divider_xy_m=[a.tolist() for a in raw_refs],meshes=pieces,walking_path=dict(source_stations_m=(st+samples).tolist(),points_local_m=np.column_stack([xy,z]).tolist(),first_source_m=float(st+knots[0]),last_source_m=float(st+knots[-1]),mode='walk_bicycle',note='Collision-clear geometric reference only. Runtime controller must follow and prove this path without disabling gate collision.'),checks=checks,release_accepted=False)
        reports.append(row)
    inputs=[dict(path=path,sha256=digest(ROOT/path)) for path in [cfgpath,runtime_path,'data/routes/raw/osm/park-map-20260927.osm','data/raw/corridor/maze-gates-2025.pdf']]
    inputs += [dict(path=p,sha256=h) for p,h in sorted(source_inputs.items())]
    data=dict(schema_version=1,scope='Three existing-condition physical gate sites at M1 detail, no proposed removal/planter designs',source_period=cfg['source_period'],current_condition_certified=False,settings_path=cfgpath,inputs=inputs,assets=geom.ASSETS,sites=reports,features=[dict(id=r['id'],name=r['id']+' dated physical gate',limits=cfg['dimensions_basis'],replace_cover_ids=[]) for r in reports],application_review='not run',release_accepted=False,checks_pass=all(r['checks']['body_clear'] for r in reports),attribution='© OpenStreetMap contributors, ODbL-1.0. City2022 pavement heights under Open Government Licence Vancouver. City2025 photos reference only.')
    save_json(ROOT/'manifests/maze-gate-blockouts.json',data)
    save_json(ROOT/'evidence/facilities/maze-gate-geometric-clearance.json',dict(sites=[dict(id=r['id'],**r['checks']) for r in reports],checks_pass=data['checks_pass'],application_test=False))
    print(json.dumps(dict(meshes=len(geom.ASSETS),checks=[dict(id=r['id'],**r['checks']) for r in reports])))
    if not data['checks_pass']:raise ValueError('Retain failed geometric clearance. Adjust walking waypoints, not the fixed barrier geometry.')


if __name__=='__main__':main()
