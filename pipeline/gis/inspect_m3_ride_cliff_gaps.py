"""Read-only source ray attribution for two gaps found in original ride frames."""
from pathlib import Path
import hashlib
import json
import math
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TRACE = 'unreal/Saved/Diagnostics/ride-20261004-004146.json'
CASES = [
    (8764, [(123,140), (342,276), (359,292), (277,224)]),
    (8766, [(274,293), (290,270), (311,312)]),
    (8768, [(126,330), (149,293), (211,354)]),
    (13765, [(821,289), (832,310), (849,286), (791,338)]),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def camera_at(trace, capture, index):
    time = capture['frames'][index]['seconds']
    samples = trace['samples']
    i = next(i for i, s in enumerate(samples) if s['seconds'] >= time)
    a, b = samples[i-1:i+1]
    u = (time-a['seconds'])/(b['seconds']-a['seconds'])
    point = ((1-u)*np.array([a['east_cm'], a['north_cm'], a['height_cm']])
             + u*np.array([b['east_cm'], b['north_cm'], b['height_cm']]))/100
    delta = np.array([b['east_cm']-a['east_cm'], b['north_cm']-a['north_cm']])
    delta /= np.linalg.norm(delta)
    yaw = math.atan2(delta[0], delta[1])
    point[:2] += delta*.12
    point[2] += .78
    pitch = math.radians(-4)
    forward = np.array([math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)])
    right = np.array([-math.sin(yaw), math.cos(yaw), 0.])
    up = np.cross(forward, right)
    return dict(index=index, seconds=time, origin_local_m=point.tolist(), yaw_degrees=math.degrees(yaw), pitch_degrees=-4, fov_degrees=trace['ride_settings']['FieldOfView'], interpolated_chainage_m=(1-u)*a['chainage_m']+u*b['chainage_m'], sample_before=a, sample_after=b), (point, forward, right, up)


def ray_hits(origin, direction, meshes):
    hits = []
    for name, path, vertices, faces in meshes:
        t = vertices[faces]
        a, e1, e2 = t[:,0], t[:,1]-t[:,0], t[:,2]-t[:,0]
        p = np.cross(direction, e2)
        det = (e1*p).sum(1)
        inv = np.divide(1., det, out=np.zeros_like(det), where=np.abs(det)>1e-10)
        tv = origin-a
        u = (tv*p).sum(1)*inv
        q = np.cross(tv,e1)
        v = (q*direction).sum(1)*inv
        d = (q*e2).sum(1)*inv
        good = (np.abs(det)>1e-10)&(u>=0)&(v>=0)&(u+v<=1)&(d>.001)
        for idx in np.flatnonzero(good):
            normal = np.cross(e1[idx],e2[idx]); normal /= np.linalg.norm(normal)
            hits.append(dict(name=name, face_index=int(idx), distance_m=float(d[idx]), point_local_m=(origin+d[idx]*direction).tolist(), normal=normal.tolist(), ray_dot_normal=float(normal@direction), front_facing=bool(normal@direction<0), vertices_local_m=t[idx].tolist(), source=path.relative_to(ROOT).as_posix(), source_sha256=sha(path)))
    return sorted(hits, key=lambda row:row['distance_m'])[:10]


def run():
    trace = json.loads((ROOT/TRACE).read_text())
    folder = Path(trace['video_capture_directory'])
    capture = json.loads((folder/'capture.json').read_text())
    names = {r['name'] for r in json.loads((ROOT/'manifests/blender-export.json').read_text())['assets']}
    meshes = []
    for path in (ROOT/'data').rglob('*.npz'):
        if path.stem not in names:
            continue
        data = np.load(path)
        if not {'vertices','faces','anchor'} <= set(data.files):
            continue
        vertices = data['vertices'].astype(float)+data['anchor']
        meshes.append((path.stem,path,vertices,data['faces']))
    rows = []
    for index, pixels in CASES:
        camera, (origin, forward, right, up) = camera_at(trace,capture,index)
        image = folder/capture['frames'][index]['file']
        row = dict(camera=camera,image=image.relative_to(ROOT).as_posix(),image_sha256=sha(image),pixels=[])
        width = capture['content_width']; height = capture['content_height']
        # The JPEG stores the full original viewport with centred black margins.
        cx = capture['content_x']+width/2
        cy = capture['content_y']+height/2
        scale = math.tan(math.radians(camera['fov_degrees']/2))
        for x,y in pixels:
            ray = forward+right*((x+.5-cx)/(width/2))*scale-up*((y+.5-cy)/(width/2))*scale
            ray = ray[[1,0,2]];ray/=np.linalg.norm(ray)
            row['pixels'].append(dict(pixel=[x,y],direction_local=ray.tolist(),hits=ray_hits(origin,ray,meshes)))
        rows.append(row)
    out = dict(scope='Estimated ride camera derived from adjacent stored pawn positions, default camera offset and pitch. It is not an exact runtime camera record. Source rays use measured mesh NPZ and include both face sides. Existing decorative layers require separate inspection.',trace=TRACE,trace_sha256=sha(ROOT/TRACE),capture=(folder/'capture.json').relative_to(ROOT).as_posix(),capture_sha256=sha(folder/'capture.json'),source_name_filter='Only original names in manifests/blender-export.json.',frames=rows)
    path = ROOT/'evidence/m3-ride-cliff-source-attribution.json'
    path.write_text(json.dumps(out,indent=2)+'\n')
    return out


if __name__ == '__main__':
    output = run()
    for row in output['frames']:
        print(row['camera']['index'],row['camera']['origin_local_m'])
        for pixel in row['pixels']:
            print(pixel['pixel'],[(h['name'],h['face_index'],round(h['distance_m'],3),h['front_facing']) for h in pixel['hits'][:4]])
