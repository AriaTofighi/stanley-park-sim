"""Read-only camera plan for the six required R checklist entries.

Run in the coordinator's serial Blender slot after the final geometry updates.
This does not change the scene, save the blend, or replace the primary plan.
"""
from pathlib import Path
import hashlib
import json
import runpy

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
IDS = ('ART_533', 'ART_534', 'SP_lions_gate', 'SP_restoration_donor',
       'SP_second_beach', 'SP_water_park')
OUTPUT = ROOT / 'manifests/m3-landmark-supplemental-camera-candidates.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    source_path = ROOT / 'manifests/m3-landmark-coverage-reconciliation.json'
    source = json.loads(source_path.read_text())
    rows = {row['id']: row for row in source['features']}
    entries = []
    positions = {}
    for fid in IDS:
        row = rows[fid]
        entry = dict(id=fid, name=row['name'], linked_meshes=row['linked_meshes'])
        if 'position_local_m' in row:
            positions[fid] = row['position_local_m']
        if fid == 'SP_restoration_donor':
            # A local terrain sample supplies a search height, not monument geometry.
            xy = np.asarray(row['candidate_xy_local_m'])
            nearby = []
            for obj in bpy.context.scene.objects:
                if obj.type != 'MESH' or not obj.name.startswith('SM_Terrain_'):
                    continue
                if not obj.data.vertices:
                    continue
                p = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
                d = np.linalg.norm(p[:, :2] - xy, axis=1)
                for index in np.flatnonzero(d <= 25):
                    nearby.append((float(d[index]), p[index].tolist(), obj.name))
            if not nearby:
                raise RuntimeError('No source terrain sample near donor search point')
            nearby.sort(key=lambda item: item[0])
            nearest = nearby[0]
            positions[fid] = [*xy.tolist(), nearest[1][2] + 1.0]
            entry['donor_search_height'] = dict(
                terrain_sample_local_m=nearest[1], sample_distance_m=nearest[0],
                terrain_object=nearest[2], aim_offset_m=1.0,
                limits='Approximate source point and nearest terrain vertex plus a 1 m viewing target. This is not a monument height or surveyed placement.')
        if fid in {'SP_lions_gate', 'SP_second_beach', 'SP_water_park'}:
            extent = np.asarray(row['bounds_max_m']) - np.asarray(row['bounds_min_m'])
            entry['supplemental_span_m'] = float(max(extent[:2]) * 1.1)
        entries.append(entry)

    planner_path = ROOT / 'pipeline/blender/plan_m3_landmark_views.py'
    planner = runpy.run_path(str(planner_path), run_name='m3_supplemental_camera_helpers')
    result = planner['build'](entries=entries, target_positions=positions, output=OUTPUT)
    plan = json.loads(OUTPUT.read_text())
    plan['scope'] = 'Six required R checklist entries missing from the primary 37-landmark plan. Source and camera reconciliation only; capture and review pending.'
    plan['input_hashes'] = {
        str(path.relative_to(ROOT)).replace('\\', '/'): sha(path)
        for path in (source_path, planner_path, Path(__file__).resolve(),
                     ROOT / 'docs/M3-LANDMARK-REVIEW-CHECKLIST.md')}
    for path_string in sorted({p for fid in IDS for p in rows[fid]['source_manifests']}):
        plan['input_hashes'][path_string] = sha(ROOT / path_string)
    entry_map = {entry['id']: entry for entry in entries}
    main_path = ROOT / 'manifests/m3-landmark-final-camera-candidates.json'
    main = json.loads(main_path.read_text()) if main_path.exists() else None
    if main and (main['source_geometry_digest'] != plan['source_geometry_digest'] or
                 main['route_sha256'] != plan['route_sha256']):
        raise RuntimeError('Run the primary planner against the final geometry before this supplemental planner')
    pool = next((row for row in main['views'] if row['id'] == 'SP_second_pool'), None) if main else None
    for row in plan['views']:
        fid = row['id']
        original = rows[fid]
        row['source_manifests'] = original['source_manifests']
        row['source_limits'] = original['source_limits']
        row['source_references'] = original.get('source_references', [])
        row['position_basis'] = original.get('position_basis', 'Approximate donor search point; no known monument form')
        row['review_status'] = 'capture and review pending'
        row['coverage_closed'] = False
        if fid == 'SP_restoration_donor':
            row['donor_search_height'] = entry_map[fid]['donor_search_height']
            # There is no source form to review from an invented close camera.
            row.pop('supplemental', None)
            row['required_review'] = 'Inspect upper cliff from route stations near 4750 to 5000 m. A blocked ray or empty image does not establish source absence. Shape remains unresolved.'
        elif fid == 'SP_lions_gate':
            row['required_review'] = 'Verify both towers, main cables, hangers and continuous deck; also inspect primary route sections 018 and 019.'
            row['existing_route_context'] = ['section_017', 'section_018', 'section_019']
        elif fid in {'ART_533', 'ART_534'}:
            row['required_review'] = 'Review separate tall display form and source silhouette. Identity remains provisional; exact carving and painted design are unproved.'
        elif fid == 'SP_second_beach':
            row['required_review'] = 'Review continuous pool coping, basin and facilities roofline after the facade repair.'
            if pool:
                same_meshes = set(pool['source_linked_meshes']) == set(original['linked_meshes'])
                row['existing_candidate_linkage'] = dict(
                    primary_plan=str(main_path.relative_to(ROOT)).replace('\\', '/'),
                    primary_plan_sha256=sha(main_path), primary_feature_id='SP_second_pool',
                    same_linked_mesh_set=same_meshes,
                    candidate_ids=[item['id'] for item in pool['candidates']],
                    supplemental_id=pool.get('supplemental', {}).get('id'),
                    limits='These views may satisfy the shared pool/facilities checklist item only after actual image review. This linkage does not establish beach visibility or acceptance.')
        else:
            row['required_review'] = 'Review water-park ground forms, open boat rim and climbing outcrop in relation to the seawall and concession.'
    plan['counts'] = dict(required_ids=len(IDS), route_views=sum(len(r['candidates']) for r in plan['views']),
                          form_only_views=sum('supplemental' in r for r in plan['views']), coverage_closed=0)
    OUTPUT.write_text(json.dumps(plan, indent=2))
    return {**result, **plan['counts'], 'sha256': sha(OUTPUT)}


if __name__ in {'__main__', '<run_path>'}:
    result = build()
