"""Bounded M1 navigation markers from current rule and topology registers.

Markers are functional blockout aids. None is a surveyed physical sign. This
stage writes data only and does not change controller permissions or terrain.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import Polygon

from navigation_meshes import box, mesh_check
from mesh_surface_query import MeshSurfaceQuery

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/routes/derived/navigation-meshes'


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def save(path, data):
    (ROOT/path).write_text(json.dumps(data, indent=2)+'\n', encoding='utf8')


class NavigationBuilder:
    def __init__(self):
        self.settings = read('manifests/navigation-detail-settings.json')
        self.runtime = read('data/derived/paved-circuit-runtime.json')
        self.world = read('unreal/Content/WorldData/world.json')
        self.junctions = read('data/routes/derived/city-branch-connections-reviewed.json')
        self.ped = read('data/routes/derived/pedestrian-network.json')
        self.s = np.asarray(self.runtime['chainage_source_m'])
        self.rs = np.asarray(self.runtime['chainage_runtime_m'])
        self.p = np.asarray(self.runtime['points_local_m'])
        t = np.gradient(self.p[:,:2], axis=0)
        t[0] = t[-1] = self.p[1,:2] - self.p[-2,:2]
        t /= np.linalg.norm(t, axis=1)[:,None]
        self.n = np.column_stack((-t[:,1], t[:,0]))
        self.width, self.fall = np.asarray(self.runtime['width_m']), np.asarray(self.runtime['crossfall'])
        if self.width.shape != self.s.shape or self.fall.shape != self.s.shape:
            raise ValueError('Navigation requires the effective runtime pavement profile')
        self.surface = read('manifests/surface-model.json')
        self.surface_inputs, self.arrow_checks = {}, []
        left = self.p[:,:2] + self.n*self.width[:,None]*.5
        right = self.p[:,:2] - self.n*self.width[:,None]*.5
        self.pavement = shapely.union_all(shapely.make_valid([Polygon([right[i],right[i+1],left[i+1],left[i]]) for i in range(len(self.p)-1)]))
        with np.load(ROOT/'data/derived/terrain_2022_park.npz') as terrain:
            self.height = RegularGridInterpolator((terrain['y'],terrain['x']),terrain['z'],bounds_error=False,fill_value=np.nan)
        self.markers, self.meshes, self.unplaced, self.junction_records = [], [], [], []
        OUT.mkdir(parents=True,exist_ok=True)

    def route_sample(self, station):
        station = station % self.s[-1]
        p = np.array([np.interp(station,self.s,self.p[:,i]) for i in range(3)])
        n = np.array([np.interp(station,self.s,self.n[:,i]) for i in range(2)])
        n /= np.linalg.norm(n)
        return p, np.array([n[1],-n[0]]), n

    def add_mesh(self, marker_id, role, v, f, color, closed=True):
        name = 'SM_Nav_' + marker_id + '_' + role
        anchor = np.r_[np.floor(v[0,:2]/10)*10, 0.]
        path = OUT/(name+'.npz')
        check = mesh_check(v,f,closed)
        np.savez_compressed(path,vertices=v-anchor,faces=f,anchor=anchor)
        self.meshes.append(dict(name=name,marker_id=marker_id,role=role,path=path.relative_to(ROOT).as_posix(),
                                sha256=sha(path.relative_to(ROOT)),vertices=len(v),triangles=len(f),checks=check,
                                material_color=color,collision='none',placement_class='functional_blockout_marker'))

    def add_board(self, marker_id, kind, lines, point, tangent, evidence, station=None, association=None):
        cfg = self.settings
        point, tangent = np.array(point), np.array(tangent)
        tangent /= np.linalg.norm(tangent)
        normal = np.array([-tangent[1],tangent[0]])
        axes = np.array([[*normal,0.],[*tangent,0.],[0.,0.,1.]])
        candidates = []
        for side in (1,-1):
            for offset in cfg['lateral_candidates_m']:
                xy = point[:2] + normal*side*offset
                ground = float(self.height([[xy[1],xy[0]]])[0])
                if not np.isfinite(ground):continue
                center = np.r_[xy,point[2]+cfg['board_center_above_path_m']]
                v,f = box(center,axes,[cfg['board_width_m'],cfg['board_thickness_m'],cfg['board_height_m']])
                footprint = shapely.MultiPoint(v[:,:2]).convex_hull
                gap = footprint.distance(self.pavement)
                if gap < cfg['minimum_pavement_clearance_m'] or ground > center[2]-cfg['board_height_m']*.5-.1 or ground < point[2]-2:
                    continue
                score = abs(ground-point[2]) + (0 if side==1 else .4) + abs(offset-2.8)*.2
                candidates.append((score,center,ground,gap,v,f,side,offset))
        if not candidates:
            self.unplaced.append(dict(id=marker_id,kind=kind,reason='No above-ground side placement with the required pavement clearance',source_point_local_m=point.tolist()))
            return
        _,center,ground,gap,v,f,side,offset = min(candidates,key=lambda item:item[0])
        color = [0.66,.31,.035,1] if kind=='walk_advance' else [.52,.065,.045,1] if kind in ('walk_start','no_cycle') else [.025,.19,.25,1]
        self.add_mesh(marker_id,'Board',v,f,color)
        post_bottom = ground-cfg['post_embed_m'];post_top = center[2]+.1
        # Text faces approaching riders (-tangent). Keep the support entirely
        # behind that face so it cannot obscure the instruction.
        post_xy=center[:2]+tangent*(cfg['board_thickness_m']+cfg['post_width_m'])*.5
        pv,pf = box(np.array([*post_xy,(post_bottom+post_top)*.5]),axes,[cfg['post_width_m'],cfg['post_width_m'],post_top-post_bottom])
        self.add_mesh(marker_id,'Post',pv,pf,[.18,.19,.18,1])
        self.markers.append(dict(id=marker_id,kind=kind,text_lines=lines,source_point_local_m=point.tolist(),
            board_center_local_m=center.tolist(),tangent_xy=tangent.tolist(),normal_xy=normal.tolist(),
            ground_z_m=ground,source_station_m=station,
            runtime_station_m=None if station is None else float(np.interp(station%self.s[-1],self.s,self.rs)),
            minimum_paved_gap_m=float(gap),side=side,lateral_offset_m=offset,
            evidence=evidence,association=association,physical_sign_location_verified=False,
            placement_class='functional_marker_offset_from_sourced_route_or_topology_boundary',
            geometry_dimensions='editable_blockout_estimates',collision='none',release_accepted=False))

    def arrow(self, marker_id, station):
        # Original arrow shape following the authored surface, not photographed paint.
        uv=np.array([[-.8,-.11],[.1,-.11],[.1,-.3],[.8,0.],[.1,.3],[.1,.11],[-.8,.11]])
        vertices=[]
        for along,across in uv:
            p,t,n=self.route_sample(station+along)
            fall=np.interp((station+along)%self.s[-1],self.s,self.fall)
            vertices.append([*(p[:2]+n*across),p[2]+fall*across+self.settings['ground_marking_lift_m']])
        vertices=np.asarray(vertices)
        bounds=np.r_[vertices[:,:2].min(0)-.1,vertices[:,:2].max(0)+.1]
        surface=MeshSurfaceQuery(ROOT,[r for r in self.surface['pavement'] if r['role']=='pavement'],bounds)
        actual=np.array([surface.height(p[:2]) for p in vertices])
        profile_difference=float(np.max(np.abs(vertices[:,2]-self.settings['ground_marking_lift_m']-actual)))
        vertices[:,2]=actual+self.settings['ground_marking_lift_m']
        self.surface_inputs.update({item['path']:item for item in surface.inputs})
        self.arrow_checks.append(dict(marker_id=marker_id,source_station_m=station,
            method='Arrow vertices sampled on actual final exported pavement triangle planes',
            profile_to_actual_mesh_max_difference_m=profile_difference,
            final_vertex_lift_m=self.settings['ground_marking_lift_m']))
        # CCW triangles in (forward,left) coordinates point upward.
        f=np.array([[0,1,5],[0,5,6],[2,3,1],[1,3,5],[5,3,4]],dtype=np.int32)
        if np.any(np.cross(vertices[f[:,1]]-vertices[f[:,0]],vertices[f[:,2]]-vertices[f[:,0]])[:,2]<=0):
            raise ValueError('Navigation arrow faces must point upward')
        self.add_mesh(marker_id,'DirectionArrow',vertices,f,[.85,.85,.71,1],closed=False)

    def walk_markers(self):
        records=[]
        for index,zone in enumerate(self.world['walk_zones'],1):
            a,b=zone['source_start_m'],zone['source_end_m']
            expected=np.interp([a,b],self.s,self.rs)*100
            if max(abs(expected-np.array([zone['start_cm'],zone['end_cm']])))>.02:
                raise ValueError('World walk-zone chainages are stale; rebuild world before navigation markers')
            records.append(dict(**zone,restriction='walk_bicycle',physical_sign_endpoints_verified=False))
            choices=[('Advance',a-self.settings['warning_advance_source_m'],'walk_advance',['WALK BIKES AHEAD',zone['name'].upper()]),
                     ('Start',a,'walk_start',['WALK BIKES','STOP - PRESS E']),
                     ('End',b,'walk_end',['CYCLING RESUMES','STOP - PRESS E'])]
            for suffix,s,kind,lines in choices:
                p,t,n=self.route_sample(s)
                self.add_board(f'Walk{index}_{suffix}',kind,lines,p,t,['city-map-2026:MAP_WALK','city-maze-gates-2025'],s,
                               {'walk_zone_name':zone['name'],'boundary_source_m':[a,b],'boundary_status':'existing_authorized_M1_estimate'})
            self.arrow(f'Walk{index}_Resume',b+5)
        return records

    def junction_markers(self):
        for item in self.junctions['main_circuit_junction_reviews']:
            id=item['junction_id']
            if item['connection_status']=='grade_separated_no_transfer':
                self.junction_records.append(dict(junction_id=id,action='no_transfer_no_junction_marker',source_record=item))
                continue
            station=item['source_circuit_station_m']
            entry=self.settings['entrance_connections'].get(id)
            kind='entrance_connection' if entry else 'main_junction'
            lines=entry['lines'] if entry else ['SEAWALL CONTINUES',self.settings['junction_labels'].get(id,'BIKE PATH')]
            p,t,n=self.route_sample(station-self.settings['junction_notice_advance_source_m'])
            self.add_board('Junction'+id.rsplit('_',1)[1],kind,lines,p,t,['city-bikeways','city-map-2026:MAP_RETURN'],
                           station-self.settings['junction_notice_advance_source_m'],
                           {'junction_id':id,'junction_source_station_m':station,'source_xy_local_m':item['xy_local_m'],
                            'incident_edges':item['incident_edges'],'entry_name':entry['name'] if entry else None,
                            'branch_permission_changed':False})
            self.arrow('Junction'+id.rsplit('_',1)[1],station+5)
            self.junction_records.append(dict(junction_id=id,action='main_circuit_continuation_only',source_record=item))

    def inland_restrictions(self):
        edges={e['edge_id']:e for e in self.ped['edges']}
        restricted={key:e for key,e in edges.items() if e['name'] in ('Beaver Lake Trail','Ravine Trail') and e['source_tags'].get('bicycle')=='no'}
        boundaries=[]
        for node in self.ped['nodes']:
            incident=[restricted[key] for key in node['edges'] if key in restricted]
            others=[edges[key] for key in node['edges'] if key not in restricted]
            if not incident or not others:continue
            ground_edges=[e for e in others if e['render_candidate'] and not e['special_surface_review']]
            if not ground_edges:continue
            incoming=ground_edges[0];xy=np.array(incoming['coordinates_local_xy_m'])
            direction=xy[-1]-xy[-2] if incoming['end_node']==node['node_id'] else xy[0]-xy[1]
            point=np.array([*node['xy_local_m'],float(self.height([[node['xy_local_m'][1],node['xy_local_m'][0]]])[0])])
            name=incident[0]['name'].upper()
            self.add_board('Access'+str(node['source_node_id']),'no_cycle',['NO CYCLING',name],point,direction,
                           ['city-map-2026:MAP_BEAVER','osm-pedestrian-graph'],association={'node_id':node['node_id'],'restricted_edge_ids':[e['edge_id'] for e in incident],
                                                                                      'incoming_edge_id':incoming['edge_id'],'restriction_boundary_not_physical_sign':True})
            boundaries.append(dict(node_id=node['node_id'],xy_local_m=node['xy_local_m'],restricted_edges=[e['edge_id'] for e in incident]))
        return dict(rule='no_cycling',edge_ids=sorted(restricted),boundary_nodes=boundaries,
                    source_basis='City map access callout corroborated by OSM bicycle=no tags; no cycle permission inferred from trail existence',
                    runtime_enforcement='not implemented by this data/geometry package')

    def build(self):
        walk=self.walk_markers();self.junction_markers();inland=self.inland_restrictions()
        inputs=['manifests/navigation-detail-settings.json','data/derived/paved-circuit-runtime.json','manifests/surface-model.json',
                'unreal/Content/WorldData/world.json','data/routes/derived/city-branch-connections-reviewed.json',
                'data/routes/derived/pedestrian-network.json','data/derived/terrain_2022_park.npz','manifests/routes-map-observations.json']
        data=dict(schema_version=1,scope='M1 functional navigation; no surveyed sign reconstruction',
            inputs=[dict(path=p,sha256=sha(p)) for p in inputs]+list(self.surface_inputs.values()),markers=self.markers,meshes=self.meshes,unplaced=self.unplaced,
            arrow_surface_checks=self.arrow_checks,
            walk_zones=walk,junctions=self.junction_records,inland_no_cycling=inland,
            restrictions=[dict(id='main_ccw',rule='counter_clockwise',source='city-map-2026:MAP_CCW',enforcement='guidance markers and route graph; no controller change'),
                          dict(id='cliff_no_transfer',rule='no_inferred_cliff_trail_connections',source='city-map-2026:MAP_CLIFF',
                               chainage='Map 4.5–6.5 km callout not converted to precise route stations; no invented access junctions')],
            physical_sign_locations_verified=0,physical_gate_construction_state='unverified; no gate geometry generated',
            controller_contract='world.json walk_zones only; UpdateRouteRules uses current runtime chainage within 5 m of main route',
            check_summary=dict(markers=len(self.markers),meshes=len(self.meshes),triangles=sum(m['triangles'] for m in self.meshes),
                               unplaced_markers=len(self.unplaced),minimum_paved_marker_gap_m=min(m['minimum_paved_gap_m'] for m in self.markers),
                               grade_separated_junctions_skipped=sum(j['action']=='no_transfer_no_junction_marker' for j in self.junction_records)),
            licence='Original marker geometry; City OGL Vancouver route data; ODbL-1.0 for OSM-derived inland restriction database. Keep source databases and both attributions.',
            visual_acceptance=False,runtime_acceptance=False,release_accepted=False)
        save('data/routes/derived/navigation-details.json',data)
        print(json.dumps(data['check_summary']))
        if self.unplaced:print(json.dumps(self.unplaced,indent=2))


if __name__=='__main__':
    NavigationBuilder().build()
