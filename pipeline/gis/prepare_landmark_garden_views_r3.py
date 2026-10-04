"""Prepare four finite camera candidates; no scene, app or shared-registry edits."""
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon

from prepare_route_inspection_views_r3 import crown_clear, framing, hashed, index_rows, read
from propose_ground_review_cameras import Rays, Surface, cover_triangles, in_bounds, mesh, target_samples

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = {}
    replaced = set()
    for path in (ROOT/'manifests').glob('*.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (UnicodeError, json.JSONDecodeError):
            continue
        index_rows(data, source)
        for feature in data.get('features', []) if isinstance(data,dict) else []:
            replaced.update(feature.get('replace_cover_ids', []))
    export = read('manifests/blender-export.json')['assets']
    cover = read('data/derived/cover-blockout.json')
    zones = {r['tile']: r['clusters'] for r in read('data/derived/canopy-zone-assignments.json')['assignments']}
    surface = read('manifests/surface-model.json')
    ground_rows = read('manifests/ground-space-blockouts.json')['meshes']
    jobs = [
        dict(id='hollow_tree_cavity_r3', prefix='SM_HollowTree_', centre=[-766.3,484.8],
             purpose='Close view through the east/southeast opening: lower hollow shell, base contact and cavity. The top is intentionally outside this close view; the saved full-height v14 view remains required.',
             limits='Entrance sector and 0.32 m shell thickness are M1 estimates. Braces, bark, cracks and exact interior remain unfinished.'),
        dict(id='cedar_arch_logs_r3', prefix='SM_LumbermanArch_', centre=[908.1997119140625,-1.83209797044514],
             purpose='Oblique view of the measured main log, two support logs, opening and estimated low mound. Frame the complete current three-member blockout.',
             limits='Three source-fitted axes only. Radii and mound are estimates. The second horizontal member in the 2019 memo is unresolved and is not represented.'),
        dict(id='garden_air_force_r3', prefix='SM_Ground_AirForceGarden_Ground_', centre=[635.,-266.],
             purpose='A close local garden-ground patch and retained path/tree context. This is the coarse M1 ground and vegetation extent, not a monument or planting-detail review.',
             limits='Ground extent is source-derived M1 blockout. A clear local patch does not establish the complete garden perimeter, memorial details or horticultural layout.'),
        dict(id='garden_shakespeare_r3', prefix='SM_Ground_ShakespeareArboretumGround_', centre=[492.,-316.],
             purpose='A close local arboretum-ground patch with retained source canopy and nearby path context.',
             limits='Selected garden bounds are inferred. This view does not accept exact boundaries, named trees, inscriptions or planting detail.'),
    ]
    result = dict(schema_version=1, coordinates='Local east/north/up metres; CGVD2013 vertical datum',
        scope='Four additional source-geometry inspection cameras only. No scene, geometry, shared registry or application changes.',
        source_inputs=[hashed(p) for p in ['manifests/blender-export.json','manifests/surface-model.json',
            'manifests/west-landmark-blockouts.json','manifests/cedar-arch-blockout.json',
            'manifests/ground-space-blockouts.json','data/derived/cover-blockout.json',
            'data/derived/canopy-zone-assignments.json','pipeline/blender/build_cover_blockout.py']],
        views={}, unresolved=[], limitations=['No live view or interactive acceptance is claimed.',
            'Selected target rays do not prove that all visible geometry is free from occlusion.',
            'Source canopy stays unchanged. The camera is an inspection aid, not a surveyed observer location.'])
    for job in jobs:
        centre = np.array(job['centre'])
        bounds = [*(centre-65), *(centre+65)]
        query = Surface(surface['terrain']+surface['pavement']+ground_rows, bounds)
        rows = []
        obstacles = [query.triangles]
        inputs = list(query.inputs)
        for asset in export:
            if not asset.get('place_in_level') or asset['name'] not in source:
                continue
            pos = np.array(asset['position_cm'])
            lo = (pos + asset['bounds_min_cm'])[[1,0]]/100
            hi = (pos + asset['bounds_max_cm'])[[1,0]]/100
            if np.any(hi < centre-65) or np.any(lo > centre+65):
                continue
            row = source[asset['name']]
            tri = mesh(row['path']); tri = tri[in_bounds(tri,bounds)]
            if not len(tri):
                continue
            digest = hashed(row['path'])
            if row['sha256'] and row['sha256'] != digest['sha256']:
                raise ValueError('Stale source: '+row['path'])
            inputs.append(digest)
            if asset['name'].startswith(job['prefix']):
                rows.append(dict(name=asset['name'],**row))
            if not (job['id']=='cedar_arch_logs_r3' and asset['name'].startswith(job['prefix'])):
                obstacles.append(tri)
        cover_mesh, crowns, buildings = cover_triangles(cover,zones,bounds,replaced)
        obstacles.append(cover_mesh)
        rays = Rays(np.concatenate(obstacles))
        target_tri = np.concatenate([mesh(r['path']) for r in rows])
        target_bounds = [target_tri.min((0,1)).tolist(),target_tri.max((0,1)).tolist()]
        if job['id']=='hollow_tree_cavity_r3':
            target = np.r_[centre,52.53]
            samples = np.array([target+[0,0,dz] for dz in [-1.,0,1.]])
            frame_vertices = np.array([[centre[0]+dx,centre[1]+dy,50.73+dz]
                for dx in [-1.6,1.6] for dy in [-1.6,1.6] for dz in [0,4.]])
            angles = np.radians([320,330,340,350,360])
            distances, heights = [10.,12.,15.], [1.8,2.2,3.]
        elif job['id']=='cedar_arch_logs_r3':
            feature = read('manifests/cedar-arch-blockout.json')['features'][0]
            axes = np.array(feature['measured']['source_fitted_member_axes_local_m'])
            target = target_tri.reshape(-1,3).mean(0)
            samples = np.concatenate([axes.mean(1), axes[0]])
            frame_vertices = target_tri.reshape(-1,3)
            angles = np.arange(24)*np.pi/12
            distances, heights = [30.,36.,42.,48.], [2.2,3.5,5.]
        else:
            target,samples,unused = target_samples(rows,centre,radius=4.)
            frame_vertices = samples
            angles = np.arange(24)*np.pi/12
            distances, heights = [10.,14.,18.,24.], [2.2,3.5,5.]
        candidates = []
        for distance in distances:
            for angle in angles:
                if job['id']=='cedar_arch_logs_r3':
                    # Avoid an end-on camera that projects all three members
                    # into one small shape although its centre rays are clear.
                    main_axis = axes[0,1,:2]-axes[0,0,:2]
                    main_axis /= np.linalg.norm(main_axis)
                    if abs(main_axis@np.array([np.cos(angle),np.sin(angle)])) > .65:
                        continue
                xy = target[:2]+distance*np.array([np.cos(angle),np.sin(angle)])
                z = query.height(xy)
                if not np.isfinite(z):
                    continue
                for height in heights:
                    eye = np.r_[xy,z+height]
                    clear, margin = crown_clear(eye,crowns,zones)
                    if not clear or any(b['base_m']-.25 <= eye[2] <= b['roof_m']+.25 and
                        Polygon(b['outline']).buffer(.25).covers(Point(xy)) for b in buildings):
                        continue
                    frame = framing(eye,target,frame_vertices)
                    if frame is None:
                        continue
                    sample_clear = [bool(rays.clear(eye,s)) for s in samples]
                    if not rays.clear(eye,target) or not all(sample_clear):
                        continue
                    frame['scope'] = 'Whole current arch blockout' if job['id']=='cedar_arch_logs_r3' else 'Selected close-review region only'
                    candidates.append((distance+height*.3,dict(eye=eye.tolist(),target=target.tolist(),
                        purpose=job['purpose'],feature_limits=job['limits'],target_meshes=[r['name'] for r in rows],
                        source_target_bounds_local_m=target_bounds,selected_samples_local_m=samples.tolist(),
                        selected_samples_clear=sample_clear,camera_ground_height_m=float(z),
                        camera_height_above_ground_m=height,camera_crown_section_clearance_m=margin,
                        framing=frame,local_source_inputs=list({r['path']:r for r in inputs}.values()),
                        canopy_cluster_count=len(crowns),live_review_status='pending',accepted=False,
                        self_occlusion_limit='Arch member self-occlusion must be inspected live; arch samples lie on measured axes and own meshes were excluded from these rays.' if job['id']=='cedar_arch_logs_r3' else 'Own shell/ground meshes included in rays.')))
        if candidates:
            result['views'][job['id']] = min(candidates,key=lambda r:r[0])[1]
            result['views'][job['id']]['clear_candidates'] = len(candidates)
        else:
            result['unresolved'].append(dict(view=job['id'],reason='No finite candidate clears all selected rays and frame bounds. No canopy or geometry was removed.'))
    result['helper'] = hashed('pipeline/gis/prepare_landmark_garden_views_r3.py')
    (ROOT/'manifests/m1-landmark-garden-inspection-views-r3.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(views={k:dict(eye=v['eye'],target=v['target'],samples=v['selected_samples_clear']) for k,v in result['views'].items()},unresolved=result['unresolved']),indent=2))


if __name__=='__main__':
    main()
