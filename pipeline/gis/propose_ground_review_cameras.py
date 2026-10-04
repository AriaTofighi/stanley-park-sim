"""Propose bounded review cameras from saved geometry. Does not run an application."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import shapely
from shapely.geometry import Polygon, Point, box, shape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'pipeline/routes'))


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))


def hashed(path):
    return dict(path=path, sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())


@lru_cache(None)
def mesh(path):
    with np.load(ROOT/path) as data:
        v = data['vertices'] + (data['anchor'] if 'anchor' in data else 0)
        return v[data['faces']]


def in_bounds(tri, bounds):
    lo, hi = tri[:, :, :2].min(1), tri[:, :, :2].max(1)
    return (lo[:, 0] <= bounds[2]) & (hi[:, 0] >= bounds[0]) & (lo[:, 1] <= bounds[3]) & (hi[:, 1] >= bounds[1])


class Surface:
    def __init__(self, records, bounds):
        self.inputs = []
        triangles = []
        for r in records:
            t = mesh(r['path'])
            selected = t[in_bounds(t, bounds)]
            if len(selected):
                self.inputs.append(hashed(r['path']))
                normal = np.cross(selected[:, 1]-selected[:, 0], selected[:, 2]-selected[:, 0])
                triangles.append(selected[normal[:, 2] > 1e-9])
        self.triangles = np.concatenate(triangles)
        self.polygons = shapely.polygons(self.triangles[:, :, :2])
        self.tree = shapely.STRtree(self.polygons)

    def height(self, xy):
        point = Point(xy)
        ids = self.tree.query(point, predicate='intersects')
        heights = []
        for i in ids:
            t = self.triangles[i]
            uv = np.linalg.solve(np.column_stack((t[1, :2]-t[0, :2], t[2, :2]-t[0, :2])), np.asarray(xy)-t[0, :2])
            heights.append(t[0, 2]+uv@(t[1:, 2]-t[0, 2]))
        return max(heights) if heights else np.nan


class Rays:
    def __init__(self, triangles):
        self.a = triangles[:, 0]
        self.e1 = triangles[:, 1]-self.a
        self.e2 = triangles[:, 2]-self.a

    def clear(self, eye, target):
        direction = target-eye
        p = np.cross(direction, self.e2)
        det = np.einsum('ij,ij->i', self.e1, p)
        use = np.abs(det) > 1e-9
        if not use.any():
            return True
        inv = 1/det[use]
        tv = eye-self.a[use]
        u = np.einsum('ij,ij->i', tv, p[use])*inv
        q = np.cross(tv, self.e1[use])
        v = q@direction*inv
        t = np.einsum('ij,ij->i', self.e2[use], q)*inv
        return not np.any((u >= -1e-7) & (v >= -1e-7) & (u+v <= 1+1e-7) & (t > 1e-6) & (t < .985))


def cover_triangles(cover, zones, bounds, omitted_buildings=()):
    triangles = []
    canopy_rows = []
    for tile in cover['canopy']:
        for index, ((x, y, base, top), assignment) in enumerate(zip(tile['points'], zones[tile['tile']])):
            radius = min(6., (top-base)*.25)
            if not box(*bounds).intersects(box(x-radius, y-radius, x+radius, y+radius)):
                continue
            rings = [(base+1.2, .3), (base+(top-base)*.45, radius), (base+(top-base)*.8, radius*.65), (top, .1)]
            if assignment['species_group'] in {'MB', 'DR'}:
                rings = [(base+1.2, .3), (base+(top-base)*.38, radius*.8), (base+(top-base)*.7, radius), (top, radius*.35)]
            v = np.array([[x+np.cos(a)*r, y+np.sin(a)*r, z] for z, r in rings for a in np.arange(6)*np.pi/3])
            f = []
            for ring in range(3):
                for i in range(6):
                    a, b = ring*6+i, ring*6+(i+1)%6
                    f.extend([(a, b, a+6), (b, b+6, a+6)])
            f.extend([(18, i, i+1) for i in range(19, 23)])
            triangles.extend(v[np.asarray(f)])
            canopy_rows.append(dict(tile=tile['tile'], point_index=index, local_point=[x, y, base, top]))
    building_rows = []
    for b in cover['buildings']:
        poly = Polygon(b['outline'])
        if b['id'] in omitted_buildings or not poly.intersects(box(*bounds)):
            continue
        xy = np.asarray(b['outline']); n = len(xy)
        v = np.vstack((np.c_[xy, np.full(n, b['base_m'])], np.c_[xy, np.full(n, b['roof_m'])]))
        f = [(n, n+i, n+i+1) for i in range(1, n-1)]
        for i in range(n):
            j = (i+1)%n
            f.extend([(i, j, n+j), (i, n+j, n+i)])
        triangles.extend(v[np.asarray(f)])
        building_rows.append(b)
    return np.asarray(triangles).reshape(-1, 3, 3), canopy_rows, building_rows


def target_samples(rows, desired, radius=3.5):
    tri = np.concatenate([mesh(r.get('path', r.get('mesh_path'))) for r in rows])
    centres = tri.mean(1)
    centres = centres[np.isfinite(centres).all(1)]
    index = np.argmin(np.linalg.norm(centres[:, :2]-desired, axis=1))
    target = centres[index].copy()
    nearby = centres[np.linalg.norm(centres[:, :2]-target[:2], axis=1) <= radius]
    chosen = [target]
    for axis, sign in [(0, -1), (0, 1), (1, -1), (1, 1)]:
        chosen.append(nearby[np.argmax(nearby[:, axis]*sign)])
    samples = np.unique(np.array(chosen), axis=0)
    samples[:, 2] += .12
    target[2] += .12
    return target, samples, tri


def main():
    cover = read('data/derived/cover-blockout.json')
    zones = {r['tile']: r['clusters'] for r in read('data/derived/canopy-zone-assignments.json')['assignments']}
    surface = read('manifests/surface-model.json')
    surface_records = surface['terrain'] + surface['pavement'] + surface['routes']
    surface_records += read('data/routes/derived/pedestrian-surfaces.json')['meshes']
    ground = read('manifests/ground-space-blockouts.json')['meshes']
    site = read('manifests/site-completion-blockouts.json')['meshes']
    play = read('manifests/waterpark-low-forms.json')['meshes']
    all_ground = ground+site+play
    land = shapely.union_all([shape(f['geometry']) for f in read('data/derived/park_boundary.geojson')['features']])
    # Devonian Harbour Park is in the requested setting but outside Stanley Park's legal boundary.
    devonian = next(r for r in read('manifests/m1-existing-site-linkage.json')['links'] if r['feature_id'] == 'SP_devonian')
    land = land.union(shape(devonian['selection_geometry']))
    lakes = shapely.union_all([shape(f['geometry']) for f in read('data/derived/lake-surfaces.geojson')['features']])
    site_water = [shape(f['geometry']) for f in read('data/derived/site-completions/site-completions-local.geojson')['features'] if f['properties']['material_role'] == 'pond_water']
    lakes = lakes.union(shapely.union_all(site_water))
    named_records, replaced = [], set()
    named_manifests = ['railway-structure-blockouts', 'lagoon-structure-blockouts', 'harbour-building-blockouts', 'named-feature-blockouts', 'route-sculpture-blockouts', 'west-landmark-blockouts', 'lumberman-facility-blockouts']
    named_inputs = []
    for stem in named_manifests:
        path = f'manifests/{stem}.json'
        if not (ROOT/path).exists():
            continue
        d = read(path); named_inputs.append(hashed(path))
        named_records += d.get('assets', d.get('meshes', []))
        for f in d.get('features', []):
            replaced.update(f.get('replace_cover_ids', []))
    jobs = [
        ('ground_golf_greens', 'SM_Ground_Golf_green_752863893', [-233, -1032], 'One complete green and its surrounding ground'),
        ('ground_community_garden', 'SM_Ground_CommunityBed_', [318, -990], 'Central bed groups from the open north side'),
        ('ground_railway_tracks', 'SM_Ground_MiniatureRail_241887212_', [683, -79], 'A short paired-rail segment near the station'),
        ('ground_biofilter', 'SM_Ground_BiofilterVisiblePool_', [377, -563], 'Visible pool portion and wetland rim'),
        ('ground_rose_gardens', 'SM_Ground_RoseBedGroup_', [511, -424], 'One visible rose-bed group and retained path context'),
        ('ground_greig_garden', 'SM_Ground_GreigGardenEast_', [-86, -1025], 'A local understorey/lawn patch, not the full garden'),
        ('site_heron_habitat', None, [-211, -1245], 'Existing colony-region ground and nearby source canopy; no bird claim'),
        ('site_devonian_pond', 'SM_Site_DevonianPond_01_04', [558, -902], 'A source basin/water patch without the distant high-rise obstruction'),
        ('site_hallelujah', None, [1740, -496], 'Existing near-shore landform and retained canopy context'),
        ('site_port_view', 'SM_Site_PortViewPlatform_', [1931, -262], 'Small source-defined platform projection'),
        ('site_rock_garden', None, [682, -367], 'Existing Pavilion-south garden ground, not a new monument'),
        ('site_painters_circle', 'SM_Site_PaintersCircleCourt_', [829, -466], 'Court edge and central paved meeting circle'),
        ('site_portrait_painters', 'SM_Site_PortraitPaintersGround_', [888, -339], 'Lawn island and its adjacent public path'),
        ('site_salmon_lower_pool', 'SM_Site_SalmonLowerPool_BasinGround_', [861, -455], 'Source lower basin form; water level remains a proxy'),
        ('site_waterpark_low_forms', 'SM_WaterPark_BoatOpenRim', [954, 58], 'Open low boat form; separate rock view is also supplied'),
        ('site_waterpark_rock', 'SM_WaterPark_ClimbingOutcrop', [965, 45], 'Climbing outcrop and the retained canopy overlap for review'),
        ('site_pitch_putt_clubhouse', 'clubhouse', [-258.2, -1057], 'Measured existing clubhouse envelope'),
    ]
    result = dict(schema_version=1, coordinates='Local east/north/up metres', method='Finite camera search against saved terrain, pavement, building envelopes, named meshes and exact source canopy proxy triangles. Five local target samples; no scene or application operation.',
        limits=['These are candidates for live review, not completed visual acceptance.', 'Clear centre/local samples do not prove that the complete viewport or full feature is visible.', 'Source canopy is the unchanged 2022 blockout; no vegetation was removed to expose a view.', 'Existing-site views show a small landform area only.'],
        source_inputs=[hashed(p) for p in ['manifests/surface-model.json', 'manifests/ground-space-blockouts.json', 'manifests/site-completion-blockouts.json', 'manifests/waterpark-low-forms.json', 'data/derived/cover-blockout.json', 'data/derived/canopy-zone-assignments.json', 'pipeline/blender/build_cover_blockout.py']]+named_inputs,
        views={}, unresolved=[])
    if len(sys.argv) > 1:
        requested = set(sys.argv[1:])
        jobs = [j for j in jobs if j[0] in requested]
        existing_path = ROOT/'manifests/m1-public-space-inspection-views-r2.json'
        if existing_path.exists():
            result = read('manifests/m1-public-space-inspection-views-r2.json')
            result['unresolved'] = [r for r in result['unresolved'] if r['view_id'] not in requested]
    for view_id, prefix, desired, purpose in jobs:
        bounds = [desired[0]-50, desired[1]-50, desired[0]+50, desired[1]+50]
        query = Surface(surface_records, bounds)
        own_buildings = []
        rows = []
        if prefix == 'clubhouse':
            own_buildings = ['lidar2022_489000_5460000_8']
            b = next(b for b in cover['buildings'] if b['id'] == own_buildings[0])
            target = np.array([*desired, (b['base_m']+b['roof_m'])/2])
            samples = np.array([target])
            target_bounds = [*Polygon(b['outline']).bounds]
        elif prefix:
            rows = [r for r in all_ground if r['name'].startswith(prefix)]
            target, samples, tri = target_samples(rows, desired)
            target_bounds = [tri[:, :, :2].min((0, 1)).tolist(), tri[:, :, :2].max((0, 1)).tolist()]
        else:
            target = np.array([*desired, query.height(desired)+.15])
            samples = np.array([[desired[0]+dx, desired[1]+dy, query.height([desired[0]+dx, desired[1]+dy])+.15] for dx, dy in [(0, 0), (-2, 0), (2, 0), (0, -2), (0, 2)]])
            samples = samples[np.isfinite(samples).all(1)]
            target_bounds = bounds
        cover_mesh, canopy_rows, building_rows = cover_triangles(cover, zones, bounds, replaced|set(own_buildings))
        obstacles = [query.triangles, cover_mesh]
        obstacle_paths = []
        for row in named_records + play:
            path = row.get('mesh_path', row.get('path'))
            if not path or not (ROOT/path).exists() or any(r.get('path') == path for r in rows):
                continue
            t = mesh(path); t = t[in_bounds(t, bounds)]
            if len(t):
                obstacles.append(t); obstacle_paths.append(hashed(path))
        rays = Rays(np.concatenate(obstacles))
        candidates = []; evaluated = 0
        for camera_height in [2.2, 3.5, 5.0]:
            for distance in ([10., 14., 18., 24., 30.] if view_id == 'site_devonian_pond' else [10., 14., 18.]):
                for angle in np.arange(16)*np.pi/8:
                    xy = target[:2] + distance*np.array([np.cos(angle), np.sin(angle)])
                    if not land.covers(Point(xy)) or lakes.contains(Point(xy)):
                        continue
                    z = query.height(xy)
                    if not np.isfinite(z) or z < .35452:
                        continue
                    eye = np.r_[xy, z+camera_height]
                    # A camera inside a building cannot be rescued by looking out through a wall.
                    if any(Polygon(b['outline']).buffer(.5).contains(Point(xy)) and b['base_m']-.5 <= eye[2] <= b['roof_m']+.5 for b in cover['buildings']):
                        continue
                    evaluated += 1
                    if not rays.clear(eye, target):
                        continue
                    clear = [rays.clear(eye, p) for p in samples]
                    score = sum(clear)/len(clear)*100 - (camera_height-2.2)*3 - abs(distance-14)*.25
                    candidates.append((score, eye, camera_height, clear, distance))
        if not candidates:
            result['unresolved'].append(dict(view_id=view_id, reason='No centre-ray-clear finite candidate. Requires a live view or a different source patch.'))
            print(view_id, 'NO CANDIDATE', flush=True)
            continue
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, eye, camera_height, clear, distance = candidates[0]
        result['views'][view_id+'_r2'] = dict(eye=np.round(eye, 4).tolist(), target=np.round(target, 4).tolist(), purpose=purpose,
            accepted=False, camera_ground_height_m=float(eye[2]-camera_height), camera_height_above_ground_m=camera_height,
            target_meshes=[r['name'] for r in rows], target_source_bounds_local_xy_m=target_bounds, target_samples_local_m=samples.tolist(),
            target_samples_clear=clear, candidate_positions_evaluated=evaluated, finite_clear_candidates=len(candidates),
            camera_to_target_xy_m=distance, selected_canopy_clusters=len(canopy_rows), local_terrain_inputs=query.inputs,
            local_named_occluder_inputs=obstacle_paths, omitted_named_replacement_cover_ids=sorted(replaced),
            own_building_target_ids=own_buildings, live_review_status='pending')
        print(view_id, np.round(eye, 2).tolist(), '->', np.round(target, 2).tolist(), sum(clear), '/', len(clear), flush=True)
    path = ROOT/'manifests/m1-public-space-inspection-views-r2.json'
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(output=str(path), views=len(result['views']), unresolved=result['unresolved'])))


if __name__ == '__main__':
    main()
