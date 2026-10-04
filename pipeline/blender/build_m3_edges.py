"""Extend accepted shore placements; run once in the serial Blender authoring slot.

Uses six immutable pilot meshes. Changes no measured surface or collision.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import random
import shutil

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
OWNER = 'm3_edges'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def source_geometry(scene):
    """Hash evaluated placement inputs without altering source datablocks."""
    groups = {k: ([], []) for k in ('ground', 'paved', 'structures')}
    records = []
    for obj in sorted(scene.objects, key=lambda o: o.name):
        if obj.type != 'MESH' or not obj.name.startswith('SM_'):
            continue
        if obj.name.startswith(('SM_Seawall', 'SM_SW', 'SM_Canopy', 'SM_Water', 'SM_Ocean', 'SM_Lake')):
            continue
        category = ('ground' if obj.name.startswith('SM_Terrain_') else
                    'paved' if obj.name.startswith(('SM_Pavement_', 'SM_Pedestrian_', 'SM_Route_')) else
                    'structures')
        verts = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices], dtype='<f8')
        faces = [tuple(p.vertices) for p in obj.data.polygons]
        digest = hashlib.sha256(verts.tobytes() + json.dumps(faces).encode()).hexdigest()
        records.append(dict(name=obj.name, geometry_sha256=digest, category=category))
        all_verts, all_faces = groups[category]
        start = len(all_verts)
        all_verts.extend(verts.tolist())
        all_faces.extend(tuple(start + i for i in f) for f in faces)
    return {k: BVHTree.FromPolygons(v, f) for k, (v, f) in groups.items() if f}, records


def coastline_segments():
    source = read(ROOT/'data/derived/shoreline.geojson')
    lines = []
    for feature in source['features']:
        geometry = feature['geometry']
        lines.extend(geometry['coordinates'] if geometry['type'] == 'MultiLineString' else [geometry['coordinates']])
    pairs = [(a[:2], b[:2]) for line in lines for a, b in zip(line[:-1], line[1:])]
    a, b = np.asarray(pairs, dtype=float).transpose(1, 0, 2)
    d = b-a
    return a, d, np.maximum((d*d).sum(axis=1), 1e-10)


def build():
    expected = ROOT/'blender/StanleyPark_Seawall.blend'
    if Path(bpy.data.filepath).resolve() != expected.resolve():
        raise RuntimeError('Open the separate Seawall source')
    scene = bpy.data.scenes.get('StanleyPark_M1')
    if scene is None or scene.unit_settings.scale_length != 1:
        raise RuntimeError('Expected measured scene in metres')
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        raise RuntimeError('Leave edit mode first')
    settings_path = ROOT/'manifests/m3-edge-settings.json'
    cfg = read(settings_path)
    pilot_path = ROOT/cfg['source_pilot_manifest']
    pilot = read(pilot_path)
    inputs = {p: sha(ROOT/p) for p in ['pipeline/blender/build_m3_edges.py',
        'manifests/m3-edge-settings.json', 'manifests/surface-model.json',
        'data/derived/paved-circuit-runtime.json', 'data/derived/shoreline.geojson',
        cfg['source_pilot_manifest'], cfg['source_pilot_import_record']]}
    ground_inputs, geometry = source_geometry(scene)
    inputs['scene_geometry_digest'] = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()
    version = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:12]
    folder = ROOT/'exports/m3-edges'/version
    if (folder/'manifest.json').exists():
        raise RuntimeError('Immutable M3 edge version exists; use its manifest')
    # Save and preserve a complete source snapshot before changing collections.
    bpy.context.window.scene = scene
    bpy.ops.wm.save_as_mainfile(filepath=str(expected))
    digest = sha(expected)
    archive = ROOT/'blender/archive'/('StanleyPark_Seawall_'+digest[:12]+'.blend')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists(): shutil.copy2(expected, archive)
    if sha(archive) != digest: raise RuntimeError('Blender archive differs')
    collection = bpy.data.collections.new('SP_M3Edges_'+version)
    scene.collection.children.link(collection)
    rocks = {}
    for asset in pilot['assets']:
        obj = bpy.data.objects.get(asset['blender_object'])
        if obj is None: raise RuntimeError('Missing accepted stone source '+asset['blender_object'])
        rocks[asset['name']] = obj.data
    route = np.asarray(read(ROOT/'data/derived/paved-circuit-runtime.json')['points_local_m'])
    chain = np.r_[0, np.cumsum(np.linalg.norm(np.diff(route, axis=0), axis=1))]
    section_count = int(math.ceil(chain[-1]/cfg['section_length_m']))
    sections = [dict(id=f'section_{i:03d}', start_m=i*250, end_m=min((i+1)*250, float(chain[-1])),
                     pilot_stones=0, new_stones=0, attempts=0, exclusions=Counter()) for i in range(section_count)]
    def section(station):
        return sections[min(len(sections)-1, int(station/cfg['section_length_m']))]
    rows = [dict(row, origin='retained_M2_pilot') for row in pilot['instances']]
    cell_size = cfg['occupancy_cell_m']
    occupied = {(math.floor(r['position_local_m'][0]/cell_size), math.floor(r['position_local_m'][1]/cell_size)) for r in rows}
    for row in rows: section(row['route_station_m'])['pilot_stones'] += 1
    a, d, dd = coastline_segments()
    ground, paved, structures = (ground_inputs[k] for k in ('ground', 'paved', 'structures'))
    rng = random.Random(cfg['seed'])
    names = list(rocks)
    for station in np.arange(0, chain[-1], cfg['station_step_m']):
        segment = min(len(route)-2, int(np.searchsorted(chain, station, side='right')-1))
        f = (station-chain[segment])/max(chain[segment+1]-chain[segment], 1e-9)
        centre = route[segment]*(1-f)+route[segment+1]*f
        stats = section(station)
        for _ in range(cfg['attempts_per_station']):
            stats['attempts'] += 1
            angle, distance = rng.uniform(0, math.tau), rng.uniform(*cfg['route_distance_range_m'])
            x, y = centre[:2]+np.array([math.cos(angle), math.sin(angle)])*distance
            cell = (math.floor(x/cell_size), math.floor(y/cell_size))
            reason = None
            if cell in occupied: reason = 'occupied'
            offset = np.asarray([x, y])-a
            t = np.clip((offset*d).sum(axis=1)/dd, 0, 1)
            coast_distance = float(np.sqrt(((offset-d*t[:, None])**2).sum(axis=1).min()))
            if reason is None and coast_distance > cfg['coast_distance_max_m']: reason = 'away_from_approximate_coast'
            hit, normal, _, _ = ground.ray_cast(Vector((x,y,30)), Vector((0,0,-1)),45)
            if reason is None and (hit is None or not cfg['height_range_m'][0] <= hit.z <= cfg['height_range_m'][1]): reason = 'no_low_shore_surface'
            if reason is None and normal.z < cfg['minimum_ground_normal_z']: reason = 'steep_surface'
            if reason:
                stats['exclusions'][reason] += 1
                continue
            size = rng.uniform(.22, .78)
            name = rng.choice(names)
            scale = [size*rng.uniform(.85,1.2), size*rng.uniform(.8,1.15), size*rng.uniform(.75,1.1)]
            radius = max(Vector(tuple(v.co[k]*scale[k] for k in range(3))).length for v in rocks[name].vertices)
            supports = []
            for j in range(8):
                angle = j*math.tau/8
                foot, fn, _, _ = ground.ray_cast(Vector((x+radius*math.cos(angle), y+radius*math.sin(angle),30)),Vector((0,0,-1)),45)
                if foot is None or fn.z < cfg['minimum_support_normal_z']: break
                supports.append(foot.z)
            if len(supports) != 8 or max(supports)-min(supports) > size*.65:
                stats['exclusions']['incomplete_or_uneven_support'] += 1
                continue
            position = [float(x),float(y),min(supports+[hit.z])-size*.12]
            reject = False
            for tree, margin, label in [(paved,cfg['path_clearance_m'],'path_clearance'), (structures,cfg['structure_clearance_m'],'structure_clearance')]:
                near, _, _, gap = tree.find_nearest(Vector(position), radius+margin)
                if near is not None and gap < radius+margin:
                    stats['exclusions'][label] += 1
                    reject = True
                    break
            if reject: continue
            occupied.add(cell)
            rows.append(dict(mesh=name, position_local_m=position, scale=scale,
                yaw_degrees=rng.uniform(0,360), bounds_radius_m=radius, route_station_m=float(station),
                section_id=stats['id'], coast_distance_m=coast_distance, support_range_m=[min(supports),max(supports)],
                origin='M3_ground_supported_visual_interpretation'))
            stats['new_stones'] += 1
    for i, row in enumerate(rows):
        row['section_id'] = section(row['route_station_m'])['id']
        obj = bpy.data.objects.new(f'SW_M3Shore_{version}_{i:05d}', rocks[row['mesh']])
        collection.objects.link(obj)
        obj.location = row['position_local_m']
        obj.scale = row['scale']
        obj.rotation_euler.z = math.radians(row['yaw_degrees'])
        obj['pipeline_owner'] = OWNER
        obj['collision'] = 'none'
    for old in bpy.data.collections:
        if old != collection and old.name.startswith(('SP_SeawallShore_', 'SP_M3Edges_')):
            old.hide_viewport = old.hide_render = True
    targets = [o.name for o in scene.objects if o.type == 'MESH' and o.name.startswith(tuple(cfg['surface_override_prefixes']))]
    for s in sections:
        s['total_stones'] = s['new_stones']+s['pilot_stones']
        s['coverage_note'] = ('Ground-supported stones plus existing terrain texture' if s['total_stones'] else
                              'No eligible low coastal surface; preserve existing terrain and route supports. Visual review pending.')
    folder.mkdir(parents=True, exist_ok=True)
    result = dict(schema_version=1, version=version, input_hashes=inputs,
        source_blend='blender/StanleyPark_Seawall.blend', map='/Game/Maps/StanleyParkSeawall',
        asset_root='/Game/StanleyPark/Seawall/Shore/M3/v_'+version,
        pilot_manifest=cfg['source_pilot_manifest'], pilot_asset_root=pilot['asset_root'],
        assets=pilot['assets'], textures=pilot['textures'], instances=rows, sections=sections,
        material_override_targets=sorted(targets), source_geometry=geometry,
        archive=archive.relative_to(ROOT).as_posix(), archive_sha256=digest,
        collision='none', placement_limit=cfg['placement_limit'], material_limit=cfg['material_limit'],
        geometry_acceptance=False, visual_acceptance=False, application_tests_run=False)
    manifest_path = folder/'manifest.json'
    manifest_path.write_text(json.dumps(result, indent=2),encoding='utf8')
    bpy.ops.wm.save_as_mainfile(filepath=str(expected))
    (ROOT/'exports/m3-edges/latest.json').write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(),sha256=sha(manifest_path)),indent=2))
    return dict(version=version, manifest=str(manifest_path), instances=len(rows), new_instances=len(rows)-len(pilot['instances']), support_targets=len(targets), sections=len(sections))


if __name__ in {'__main__', '<run_path>'}:
    result = build()

