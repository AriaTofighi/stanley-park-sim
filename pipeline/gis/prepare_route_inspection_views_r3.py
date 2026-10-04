"""Finite source-geometry camera preparation. No application or shared-registry edits."""
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box

from propose_ground_review_cameras import Rays, Surface, cover_triangles, in_bounds, mesh

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))


def hashed(path):
    return dict(path=path, sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())


def index_rows(value, result):
    if isinstance(value, dict):
        path = value.get('mesh_path') or value.get('path')
        if value.get('name') and path and str(path).endswith('.npz'):
            result[value['name']] = dict(path=path, sha256=value.get('sha256'))
        for child in value.values():
            index_rows(child, result)
    elif isinstance(value, list):
        for child in value:
            index_rows(child, result)


def crown_clear(eye, canopy, zones):
    """Reject an eye inside or within 0.25 m of the source crown envelope."""
    minimum = np.inf
    for row in canopy:
        x, y, base, top = row['local_point']
        if not base+.95 <= eye[2] <= top+.25:
            continue
        group = zones[row['tile']][row['point_index']]['species_group']
        radius = min(6., (top-base)*.25)
        rings = [(base+1.2, .3), (base+(top-base)*.45, radius), (base+(top-base)*.8, radius*.65), (top, .1)]
        if group in {'MB', 'DR'}:
            rings = [(base+1.2, .3), (base+(top-base)*.38, radius*.8), (base+(top-base)*.7, radius), (top, radius*.35)]
        radii = [np.interp(z, np.array(rings)[:, 0], np.array(rings)[:, 1]) for z in [eye[2]-.25, eye[2], eye[2]+.25]]
        r = max(radii)
        poly = Polygon([[x+np.cos(a)*r, y+np.sin(a)*r] for a in np.arange(6)*np.pi/3])
        distance = poly.distance(Point(eye[:2]))
        minimum = min(minimum, distance)
        if distance <= .25:
            return False, minimum
    return True, minimum if np.isfinite(minimum) else None


def vertical_hits(triangles, xy):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac, q = b-a, c-a, np.asarray(xy)-a[:, :2]
    det = ab[:, 0]*ac[:, 1]-ab[:, 1]*ac[:, 0]
    use = abs(det) > 1e-10
    u = np.divide(q[:, 0]*ac[:, 1]-q[:, 1]*ac[:, 0], det, out=np.full(len(det), np.nan), where=use)
    v = np.divide(ab[:, 0]*q[:, 1]-ab[:, 1]*q[:, 0], det, out=np.full(len(det), np.nan), where=use)
    use &= (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8)
    return sorted(set(np.round((a[:, 2]+u*ab[:, 2]+v*ac[:, 2])[use], 8)))


def framing(eye, target, vertices):
    forward = target-eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0., 0., 1.])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    delta = vertices-eye
    depth = delta@forward
    if min(depth) <= 0:
        return None
    horizontal = float(np.degrees(np.arctan(max(abs(delta@right)/depth)))*2)
    vertical = float(np.degrees(np.arctan(max(abs(delta@up)/depth)))*2)
    if horizontal > 32.4 or vertical > 20.7:
        return None
    return dict(required_horizontal_fov_degrees=horizontal, required_vertical_fov_degrees=vertical,
                assumed_horizontal_fov_degrees=36., assumed_vertical_fov_degrees=23.,
                minimum_frame_margin_fraction=.1, scope='All source deck vertices, including underside and end faces.')


def main():
    runtime = read('data/derived/paved-circuit-runtime.json')
    points, stations = np.array(runtime['points_local_m']), np.array(runtime['chainage_runtime_m'])
    def route(s):
        return np.array([np.interp(s, stations, points[:, i]) for i in range(3)])
    surface, underpasses = read('manifests/surface-model.json'), read('data/derived/underpass-blockouts.json')
    cover = read('data/derived/cover-blockout.json')
    zones = {row['tile']: row['clusters'] for row in read('data/derived/canopy-zone-assignments.json')['assignments']}
    export = read('manifests/blender-export.json')
    source_rows = {}
    for path in list((ROOT/'manifests').glob('*.json'))+[ROOT/'data/derived/underpass-blockouts.json', ROOT/'data/derived/underpass-closures.json']:
        try:
            index_rows(json.loads(path.read_text(encoding='utf-8-sig')), source_rows)
        except (UnicodeError, json.JSONDecodeError):
            continue
    outputs = dict(schema_version=1, coordinates='Local east/north/up metres, manifests/world-origin.json',
        scope='Source-based camera candidates for live review. No scene, shared camera registry, route or application changes.',
        source_inputs=[hashed(p) for p in ['data/derived/paved-circuit-runtime.json','manifests/surface-model.json',
            'data/derived/underpass-blockouts.json','data/derived/underpass-closures.json','data/derived/cover-blockout.json',
            'data/derived/canopy-zone-assignments.json','manifests/blender-export.json','pipeline/blender/build_cover_blockout.py']],
        views={}, unresolved=[], limitations=['Centre and sample rays do not prove the whole viewport is visible.',
            'The source camera check retains the 2022 canopy proxies.', 'No image or interactive acceptance is claimed.',
            'Underpass width, roof extent and interior floor retain the recorded M1 estimate limits.'])
    for site in underpasses['sites']:
        centre = np.mean(site['floor_center_xyz'], axis=0)
        bounds = [centre[0]-45, centre[1]-45, centre[0]+45, centre[1]+45]
        record_inputs, groups = [], []
        for asset in export['assets']:
            if not asset.get('place_in_level') or asset['name'] not in source_rows:
                continue
            row = source_rows[asset['name']]
            triangles = mesh(row['path']); triangles = triangles[in_bounds(triangles, bounds)]
            if not len(triangles):
                continue
            if row['sha256'] and hashed(row['path'])['sha256'] != row['sha256']:
                raise ValueError('Stale camera source mesh: '+row['path'])
            groups.append((asset['name'], triangles)); record_inputs.append(hashed(row['path']))
        cover_mesh, crowns, buildings = cover_triangles(cover, zones, bounds)
        obstacles = np.concatenate([tri for _, tri in groups]+[cover_mesh])
        rays = Rays(obstacles)
        ground = Surface(surface['terrain']+surface['pavement'], bounds)
        shells = [(name, tri) for name, tri in groups if name.startswith('SM_Underpass_') and
                  any(part in name for part in ['_Deck','_Wall'])]
        def valid_eye(eye):
            clear, crown_margin = crown_clear(eye, crowns, zones)
            if not clear:
                return None
            for b in buildings:
                if b['base_m']-.25 <= eye[2] <= b['roof_m']+.25 and Polygon(b['outline']).buffer(.25).covers(Point(eye[:2])):
                    return None
            for _, tri in shells:
                levels = vertical_hits(tri, eye[:2])
                if any(lo-.20 < eye[2] < hi+.20 for lo, hi in zip(levels[::2], levels[1::2])):
                    return None
            return crown_margin
        def save_view(key, eye, target, samples, purpose, metadata):
            margin = valid_eye(eye)
            if margin is None:
                # No crown at camera height also has no finite distance; distinguish it below.
                if not crown_clear(eye, crowns, zones)[0]:
                    return False
                for b in buildings:
                    if b['base_m']-.25 <= eye[2] <= b['roof_m']+.25 and Polygon(b['outline']).buffer(.25).covers(Point(eye[:2])):
                        return False
                for _, tri in shells:
                    levels = vertical_hits(tri, eye[:2])
                    if any(lo-.20 < eye[2] < hi+.20 for lo, hi in zip(levels[::2], levels[1::2])):
                        return False
            clear = [rays.clear(eye, sample) for sample in samples]
            if not rays.clear(eye, target) or not all(clear):
                return False
            outputs['views'][key] = dict(eye=eye.tolist(), target=target.tolist(), purpose=purpose,
                target_samples_local_m=np.asarray(samples).tolist(), target_samples_clear=clear,
                camera_crown_section_clearance_m=margin, minimum_camera_crown_margin_required_m=.25,
                camera_outside_source_underpass_solids=True, local_source_inputs=record_inputs,
                selected_canopy_clusters=len(crowns), live_review_status='pending', accepted=False, **metadata)
            return True
        if site['id'] == 'Chilco':
            for key, eye_s, target_s in [('join_041_lower_r3', 9379.5, 9387.470), ('join_041_portal_side_r3', 9411., 9405.33982052057)]:
                eye = route(eye_s)+[0,0,1.6]
                target = route(target_s)+[0,0,1.05 if 'lower' in key else 1.55]
                samples = [target+v for v in [[0,0,-.5],[0,0,.5],[.2,-.2,0],[-.2,.2,0]]]
                if not save_view(key, eye, target, samples,
                    'Lower route and upper crossing remain separate; inspect the tunnel opening, ceiling and floor without an at-grade connector.',
                    dict(eye_runtime_chainage_m=eye_s, target_runtime_chainage_m=target_s, eye_above_route_m=1.6,
                         target_floor_height_m=float(route(target_s)[2]), junction_runtime_chainage_m=9387.470, grade_separated=True)):
                    outputs['unresolved'].append(dict(view=key, reason='Proposed lower/portal eye or sample ray was obstructed.'))
        else:
            deck = next(tri for name, tri in groups if name == 'SM_Underpass_Ceperley_Deck')
            norms = np.cross(deck[:, 1]-deck[:, 0], deck[:, 2]-deck[:, 0])
            top = deck[norms[:, 2] > 0]
            top_surface = Surface([next(row for row in underpasses['meshes'] if row['name']=='SM_Underpass_Ceperley_Deck')], bounds)
            target = np.r_[centre[:2], top_surface.height(centre[:2])+.07]
            xy_samples = np.array(site['floor_center_xyz'])[[3,len(site['floor_center_xyz'])//2,-4], :2]
            samples = [np.r_[xy,top_surface.height(xy)+.07] for xy in xy_samples]
            centres = top.mean(1)
            for axis, sign in [(0,-1),(0,1),(1,-1),(1,1)]:
                samples.append(centres[np.argmax(centres[:,axis]*sign)]+[0,0,.07])
            footprint = shapely.union_all(shapely.polygons(top[:, :, :2]))
            candidates = []
            for height in [2.,3.,4.5,6.]:
                for distance in [6.,9.,12.,15.,18.,24.,30.]:
                    for angle in np.arange(24)*np.pi/12:
                        xy = centre[:2]+distance*np.array([np.cos(angle),np.sin(angle)])
                        z = ground.height(xy)
                        if not np.isfinite(z) or footprint.buffer(.25).covers(Point(xy)):
                            continue
                        eye = np.r_[xy,z+height]
                        frame = framing(eye, target, deck.reshape(-1,3))
                        if frame is None:
                            continue
                        if save_view('ceperley_deck_side_r3',eye,target,samples,
                            'Oblique side view of the complete retained road-deck span; inspect its roof ends and bank contact.',
                            dict(camera_ground_height_m=float(z),camera_height_above_ground_m=height,deck_runtime_span_m=site['roof_runtime_m'],
                                 target_mesh='SM_Underpass_Ceperley_Deck',framing=frame)):
                            candidates.append((abs(distance-9)+height*.8, outputs['views']['ceperley_deck_side_r3']))
            if candidates:
                outputs['views']['ceperley_deck_side_r3'] = min(candidates,key=lambda row:row[0])[1]
                outputs['views']['ceperley_deck_side_r3']['clear_candidates'] = len(candidates)
            else:
                outputs['unresolved'].append(dict(view='ceperley_deck_side_r3', reason='No clear finite source-based deck camera.'))
    outputs['helper_sha256'] = hashed('pipeline/gis/prepare_route_inspection_views_r3.py')['sha256']
    path = ROOT/'manifests/m1-route-inspection-views-r3.json'
    path.write_text(json.dumps(outputs,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(views={k:{'eye':v['eye'],'target':v['target']} for k,v in outputs['views'].items()},unresolved=outputs['unresolved']),indent=2))


if __name__ == '__main__':
    main()
