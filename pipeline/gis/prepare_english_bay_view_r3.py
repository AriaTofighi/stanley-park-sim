"""One English Bay shoreline camera from saved source geometry; no app calls."""
import json
from itertools import product
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box, shape

from prepare_route_inspection_views_r3 import crown_clear, framing, hashed, index_rows, read
from propose_ground_review_cameras import Rays, Surface, cover_triangles, in_bounds, mesh

ROOT = Path(__file__).resolve().parents[2]


def main():
    bounds = [-650,-2200,720,-900]
    search_bounds = [-560,-1530,0,-950]
    skyline = read('manifests/skyline-blockouts.json')
    target_ids = ['way_51055658_0_Part0','way_311209819_0_Building0',
        'way_1093420374_0_Part0','way_1093420377_0_Part0',
        'way_312125684_0_Building0','way_310600279_0_Building0']
    selected = [next(p for p in skyline['parts'] if p['id']==key) for key in target_ids]
    samples = np.array([[*(np.mean([p['bounds_min_m'][:2],p['bounds_max_m'][:2]],axis=0)),
        p['bounds_max_m'][2]+.25] for p in selected])
    target = samples.mean(0)
    index, replaced = {}, set()
    for path in (ROOT/'manifests').glob('*.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (UnicodeError,json.JSONDecodeError):
            continue
        index_rows(data,index)
        if isinstance(data,dict):
            for feature in data.get('features',[]):
                replaced.update(feature.get('replace_cover_ids',[]))
    surface = read('manifests/surface-model.json')
    pedestrian = read('data/routes/derived/pedestrian-surfaces.json')
    ground = Surface(surface['terrain']+surface['pavement']+pedestrian['meshes'],bounds)
    cover = read('data/derived/cover-blockout.json')
    zones = {r['tile']:r['clusters'] for r in read('data/derived/canopy-zone-assignments.json')['assignments']}
    cover_mesh,crowns,buildings = cover_triangles(cover,zones,bounds,replaced)
    triangles = [ground.triangles,cover_mesh]
    inputs = list(ground.inputs)
    for asset in read('manifests/blender-export.json')['assets']:
        if not asset.get('place_in_level') or asset['name'] not in index:
            continue
        pos = np.array(asset['position_cm'])
        lo = (pos+asset['bounds_min_cm'])[[1,0]]/100
        hi = (pos+asset['bounds_max_cm'])[[1,0]]/100
        if hi[0]<bounds[0] or hi[1]<bounds[1] or lo[0]>bounds[2] or lo[1]>bounds[3]:
            continue
        row = index[asset['name']]
        tri = mesh(row['path']);tri = tri[in_bounds(tri,bounds)]
        if len(tri):
            digest = hashed(row['path'])
            if row['sha256'] and row['sha256']!=digest['sha256']:
                raise ValueError('Stale source: '+row['path'])
            triangles.append(tri);inputs.append(digest)
    rays = Rays(np.concatenate(triangles))
    candidates = []
    evaluated = 0
    max_clear = 0
    for feature in read('data/routes/derived/pedestrian-network-local.geojson')['features']:
        props = feature['properties']; line = shape(feature['geometry'])
        if props['name']!='Stanley Park Seawall' or props['walking_type']!='paved_walk' or not line.intersects(box(*search_bounds)):
            continue
        for along,west_offset in product(np.arange(0,line.length+1e-6,10.),[0.,3.,6.,10.,15.]):
            xy = np.array(line.interpolate(along).coords[0])+[-west_offset,0.]
            if not box(*search_bounds).covers(Point(xy)):
                continue
            z = ground.height(xy)
            if not np.isfinite(z) or z<.4:
                continue
            eye = np.r_[xy,z+1.7]; evaluated += 1
            clear,margin = crown_clear(eye,crowns,zones)
            if not clear or any(b['base_m']-.25 <= eye[2] <= b['roof_m']+.25 and
                Polygon(b['outline']).buffer(.25).covers(Point(xy)) for b in buildings):
                continue
            clear_samples = [bool(rays.clear(eye,p)) for p in samples]
            max_clear = max(max_clear,sum(clear_samples))
            # The view centre can lie in front of an ordinary background tower;
            # require at least two selected silhouette rays, not an empty
            # centre or visibility of every roof behind the waterfront towers.
            if sum(clear_samples)<2:
                continue
            framed_samples = samples[np.array(clear_samples)]
            look_at = framed_samples.mean(0)
            frame = framing(eye,look_at,framed_samples)
            if frame is None:
                continue
            frame['scope'] = 'Clear selected West End roof/silhouette samples only; complete scene framing remains a live check.'
            candidates.append(dict(eye=eye.tolist(),target=look_at.tolist(),source_pedestrian_edge=props['edge_id'],
                source_edge_distance_m=float(along),source_edge_offset_local_m=[-west_offset,0.],
                camera_ground_height_m=float(z),camera_height_above_ground_m=1.7,
                camera_crown_section_clearance_m=margin,selected_samples_clear=clear_samples,
                selected_samples_near_150m_clear=[bool(rays.clear(eye,eye+(p-eye)*min(1.,150./np.linalg.norm(p-eye)))) for p in samples],
                framing=frame))
    result = dict(schema_version=1,coordinates='Local east/north/up metres; CGVD2013 vertical datum',
        scope='One alternate shoreline view toward the existing English Bay / West End skyline. No geometry or app change.',
        source_inputs=[hashed(p) for p in ['manifests/skyline-blockouts.json','manifests/blender-export.json',
            'manifests/surface-model.json','data/routes/derived/pedestrian-network-local.geojson',
            'data/routes/derived/pedestrian-surfaces.json','data/derived/cover-blockout.json',
            'data/derived/canopy-zone-assignments.json','data/derived/park_boundary.geojson']],
        old_views_inspected=[hashed('evidence/blender-skyline-english-bay-v26.png'),hashed('evidence/unreal-skyline_english_bay-v26.png')],
        previous_view_observation='Near canopy obscures much of the skyline. Keep this old evidence and add the alternate; do not remove trees.',
        bounded_eye_search_local_xy=search_bounds,eyes_evaluated=evaluated,clear_candidates=len(candidates),
        maximum_clear_sample_count=max_clear,required_clear_sample_count=2,views={})
    if candidates:
        # Prefer the first clear shoreline station nearest the old Second Beach
        # view. Eyes use measured terrain at pedestrian height, on the mapped
        # path or a bounded westward beach offset with ground above mean water.
        chosen = min(candidates,key=lambda r:(-sum(r['selected_samples_near_150m_clear']),-sum(r['selected_samples_clear']),
            np.linalg.norm(np.array(r['eye'][:2])-[-617.72741,-767.33322])))
        park = shapely.union_all([shape(f['geometry']) for f in read('data/derived/park_boundary.geojson')['features']])
        chosen['eye_inside_city_park_polygon'] = bool(park.covers(Point(chosen['eye'][:2])))
        chosen['distance_to_city_park_boundary_m'] = float(park.boundary.distance(Point(chosen['eye'][:2])))
        chosen.update(purpose='View the English Bay / West End waterfront silhouette from source terrain beside the mapped pedestrian shoreline south of Second Beach.',
            selected_skyline_samples=[dict(id=p['id'],name=p['name'],source_url=p['source_url'],point_local_m=q.tolist(),
                ray_clear=bool(clear)) for p,q,clear in zip(selected,samples,chosen['selected_samples_clear'])],
            local_source_inputs=list({r['path']:r for r in inputs}.values()),live_review_status='pending',accepted=False,
            limits=['Camera is a source-based inspection location, not a surveyed photo match.',
                'Selected roof rays do not prove all skyline, lower facades or the complete viewport are visible.',
                'Pedestrian eye placement does not change cycling permissions.',
                'Building heights and forms retain the source/estimate limits in skyline-blockouts.json.'])
        result['views']['skyline_english_bay_shore_r3'] = chosen
    else:
        result['unresolved'] = 'No finite shoreline candidate clears two selected skyline rays. Do not fabricate a clear view.'
    result['helper'] = hashed('pipeline/gis/prepare_english_bay_view_r3.py')
    (ROOT/'manifests/m1-english-bay-inspection-view-r3.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(eyes_evaluated=evaluated,clear_candidates=len(candidates),maximum_clear_sample_count=max_clear,
        views={k:dict(eye=v['eye'],target=v['target'],edge=v['source_pedestrian_edge'],sample_clear=v['selected_samples_clear']) for k,v in result['views'].items()},unresolved=result.get('unresolved')),indent=2))


if __name__=='__main__':
    main()
