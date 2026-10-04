"""Author finite contact-crossing fixtures; never change geometry or permissions."""
import hashlib
import json
from pathlib import Path
import numpy as np
from shapely.geometry import LineString, Point
from mesh_surface_query import MeshSurfaceQuery

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def main():
    review = read('data/routes/derived/city-branch-connections-reviewed.json')
    city = read('data/routes/derived/city-branch-junctions.json')
    surface = read('manifests/surface-model.json')
    runtime = read('data/derived/paved-circuit-runtime.json')
    world_path = ROOT/'unreal/Content/WorldData/world.json'
    branches = {b['edge_id']: b for b in city['branches']}
    directions = {b['edge_id']: b['permitted_direction'] for b in review['direction_reviews']}
    source = np.asarray(runtime['chainage_source_m'])
    travel = np.asarray(runtime['chainage_runtime_m'])
    main_points = np.asarray(runtime['points_local_m'])
    rows, inputs = [], {}
    for junction in review['main_circuit_junction_reviews']:
        if junction['connection_status'] == 'grade_separated_no_transfer':
            continue
        station = junction['source_circuit_station_m']
        main_point = [float(np.interp(station,source,main_points[:,i])) for i in range(3)]
        for incident in junction['incident_edges']:
            if incident['main_circuit']:
                continue
            branch = branches[incident['edge_id']]
            xy = np.asarray(branch['coordinates_local_xy_m'])
            if incident['endpoint'] == 'end':
                xy = xy[::-1]
            line = LineString(xy)
            if line.length < 12.5:
                raise ValueError('The 12 m fixture requires at least 0.5 m of stopping allowance')
            extent = min(14., line.length-.02)
            source_vertices = np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
            stations = np.unique(np.r_[np.arange(0,extent,.1),source_vertices[source_vertices<extent],12.,extent])
            centres = np.asarray([line.interpolate(s).coords[0] for s in stations])
            bounds = [*(centres.min(0)-3),*(centres.max(0)+3)]
            terrain = MeshSurfaceQuery(ROOT,surface['terrain'],bounds)
            pavement = MeshSurfaceQuery(ROOT,[p for p in surface['pavement'] if p['role']=='pavement'],bounds)
            if not pavement.footprint.covers(Point(centres[0])) or pavement.footprint.covers(Point(centres[-1])):
                raise ValueError(f'{branch["edge_id"]}: fixture must cross from main pavement to branch contact')
            crossing = LineString(centres).intersection(pavement.footprint.boundary)
            hits = [crossing] if crossing.geom_type=='Point' else list(getattr(crossing,'geoms',[]))
            seam = sorted(line.project(p) for p in hits if p.geom_type=='Point')
            if not seam or not any(0 < s < 12 for s in seam):
                raise ValueError('No main/branch seam within the first 12 m')
            heights = []
            for point in centres:
                values = pavement.heights(point)+terrain.heights(point)
                if not values:
                    raise ValueError(f'Unsupported fixture point: {point}')
                heights.append(max(values))
            points = np.c_[centres,heights]
            chainage = np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
            allowed = directions.get(branch['edge_id'],branch['permitted_direction'])
            if allowed == 'both':
                modes = ['out','in']
            elif allowed == 'forward_relative_to_city_geometry':
                modes = ['out' if incident['endpoint']=='start' else 'in']
            elif allowed == 'reverse_relative_to_city_geometry':
                modes = ['in' if incident['endpoint']=='start' else 'out']
            else:
                raise ValueError('Unresolved direction cannot be a contact fixture')
            for mode in modes:
                xyz = points if mode=='out' else points[::-1]
                finish = float(np.interp(12,stations,chainage)) if mode=='out' else float(chainage[-1]-.1)
                rows.append(dict(id=f"{junction['junction_id'].split('_')[-1]}-{branch['source_object_id']}-{mode}",
                    junction_id=junction['junction_id'],branch_id=branch['edge_id'],direction=mode,
                    source_permitted_direction=allowed,branch_endpoint=incident['endpoint'],
                    main_chainage_cm=float(np.interp(station,source,travel)*100),
                    main_contact_cm=[main_point[1]*100,main_point[0]*100,main_point[2]*100],
                    points_cm=[[p[1]*100,p[0]*100,p[2]*100] for p in xyz],
                    finish_distance_cm=finish*100,minimum_branch_source_extent_m=12.,
                    main_pavement_seam_source_distances_m=seam,
                    starting_surface='main pavement' if mode=='out' else 'branch contact',
                    final_surface='branch contact' if mode=='out' else 'main pavement',
                    geometry_setup='One initial fixture placement, aligned with the source branch. No movement or route permission is changed.',
                    scope='Contact crossing on the first 12 m of the source branch; not a complete turn along the main circuit or acceptance of the rest of the branch'))
            for query in [terrain,pavement]:
                inputs.update({r['path']:r['sha256'] for r in query.inputs})
    paths = ['data/routes/derived/city-branch-connections-reviewed.json','data/routes/derived/city-branch-junctions.json',
        'data/derived/paved-circuit-runtime.json','manifests/surface-model.json']
    inputs.update({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    result = dict(schema_version=1,coordinate_contract='unreal_north_east_up_cm',
        source_world_sha1=hashlib.sha1(world_path.read_bytes()).hexdigest().upper(),
        source_inputs=[dict(path=p,sha256=h) for p,h in sorted(inputs.items())],fixtures=rows,
        excluded_junctions=['city_junction_041'],fixture_count=len(rows),branch_end_count=8,
        runtime_tested=False,release_accepted=False,
        licence='Contains City OGL Vancouver data and OSM-derived direction review under ODbL-1.0; retain the project source distribution and attribution.')
    if len(rows)!=13:
        raise ValueError(f'Expected13 finite directional fixtures, got{len(rows)}')
    target=ROOT/'unreal/Content/WorldData/join_checks.json'
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    (ROOT/'manifests/join-check-fixtures.json').write_text(json.dumps(dict(runtime_path=str(target.relative_to(ROOT)).replace('\\','/'),
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),**{k:v for k,v in result.items() if k!='fixtures'},
        fixtures=[{k:v for k,v in row.items() if k!='points_cm'} for row in rows]),indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(fixture_count=len(rows),ids=[r['id'] for r in rows],application_run=False)))


if __name__=='__main__':main()
