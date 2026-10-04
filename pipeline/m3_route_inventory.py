"""Build the source-based M3 route sections and preserve the starting files."""
import bisect
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    output = ROOT/'evidence/m3-baseline-20261003'
    output.mkdir(exist_ok=True)
    baseline = output/'sources.json'
    if not baseline.exists():
        records = []
        for relative in ['blender/StanleyPark_Seawall.blend', 'unreal/Content/Maps/StanleyParkSeawall.umap',
                         'blender/StanleyPark_Blockout.blend', 'unreal/Content/Maps/StanleyPark.umap',
                         'manifests/blender-export.json', 'data/derived/paved-circuit-runtime.json',
                         'unreal/Content/WorldData/world.json', 'manifests/world-origin.json']:
            path = ROOT/relative
            if not path.is_file():
                raise FileNotFoundError(relative)
            row = dict(path=relative, sha256=digest(path), bytes=path.stat().st_size)
            if relative in ['blender/StanleyPark_Seawall.blend', 'unreal/Content/Maps/StanleyParkSeawall.umap']:
                snapshot = output/path.name
                shutil.copy2(path, snapshot)
                if digest(snapshot) != row['sha256']:
                    raise RuntimeError('Snapshot does not match '+relative)
                row['snapshot'] = snapshot.relative_to(ROOT).as_posix()
            records.append(row)
        baseline.write_text(json.dumps(dict(time_utc=datetime.now(timezone.utc).isoformat(), files=records), indent=2))
    points = read('data/derived/paved-circuit-runtime.json')['points_local_m']
    chain = [0.0]
    for a, b in zip(points, points[1:]):
        chain.append(chain[-1]+math.dist(a,b))

    def sample(station):
        i = max(1, min(len(points)-1, bisect.bisect_left(chain, station)))
        a, b = points[i-1], points[i]
        t = (station-chain[i-1])/max(chain[i]-chain[i-1], 1e-12)
        return [x+(y-x)*t for x,y in zip(a,b)], [y-x for x,y in zip(a,b)]

    def view(station, target=None):
        p, d = sample(station)
        p[2] += 1.75
        if target:
            d = [b-a for a,b in zip(p,target)]
        return dict(location=dict(x=p[1]*100,y=p[0]*100,z=p[2]*100),
                    rotation=dict(pitch=math.degrees(math.atan2(d[2],math.hypot(d[0],d[1]))) if target else 2,
                                  yaw=math.degrees(math.atan2(d[0],d[1])),roll=0),
                    scale=dict(x=1,y=1,z=1))

    sections = []
    for index in range(math.ceil(chain[-1]/250)):
        start, end = index*250., min((index+1)*250.,chain[-1])
        middle = (start+end)/2
        sections.append(dict(id=f'section_{index:03d}', start_m=start, end_m=end,
            view_station_m=middle, requested_camera=view(middle), fixed_view_status='pending',
            boundary_station_m=start, boundary_camera=view(start), boundary_view_status='pending',
            scenery_status='pending_actual_review', ridden_status='pending'))
    export = {x['name']: x for x in read('manifests/blender-export.json')['assets']}
    landmarks = []
    unresolved = []
    for feature in read('manifests/critical-features.json')['features']:
        xy = feature.get('position_local_m')
        if not xy:
            unresolved.append(feature['id'])
            continue
        best = (float('inf'),0)
        for i,(a,b) in enumerate(zip(points,points[1:])):
            dx,dy = b[0]-a[0],b[1]-a[1]
            t = min(1,max(0,((xy[0]-a[0])*dx+(xy[1]-a[1])*dy)/max(dx*dx+dy*dy,1e-12)))
            dist = math.hypot(xy[0]-a[0]-dx*t,xy[1]-a[1]-dy*t)
            if dist < best[0]: best=(dist,chain[i]+(chain[i+1]-chain[i])*t)
        if best[0] > 150: continue
        linked = [export[n] for n in feature.get('linked_meshes',[]) if n in export]
        route_point,_ = sample(best[1])
        heights = [(a['position_cm'][2]+a['bounds_max_cm'][2])/100 for a in linked]
        height = max(route_point[2]+2, min(max(heights,default=route_point[2]+2),route_point[2]+15))
        landmarks.append(dict(id=feature['id'],name=feature['name'],station_m=best[1],
            route_distance_m=best[0], linked_meshes=[a['name'] for a in linked],
            requested_camera=view(max(0,best[1]-12),[xy[0],xy[1],height]),
            visibility='candidate_from_distance_only; actual route view required',review_status='pending'))
    result=dict(schema_version=1,route_length_m=chain[-1],section_length_m=250,
        route_sha256=digest(ROOT/'data/derived/paved-circuit-runtime.json'),
        sections=sections,landmark_views=landmarks,unlocated_feature_ids=unresolved,
        source_limit='Source-based review plan. Proximity is not visibility or visual acceptance.',
        test_authorization='User explicitly authorized required M3 checks after implementation on 2026-10-03.')
    (ROOT/'manifests/seawall-m3-sections.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(sections=len(sections),route_length_m=chain[-1],landmark_views=len(landmarks),unlocated=len(unresolved))))


if __name__ == '__main__':
    main()
