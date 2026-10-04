"""Append top-surface probes for the new M1 structural collision meshes.

Run after check_pavement_mesh.py. These controls compare exported collision to
authored geometry. They do not certify dimensions or replace interactive rides.
"""
import json
from pathlib import Path

import numpy as np
from acquire_sources import digest, save_json

ROOT = Path(__file__).resolve().parents[2]


def top_centroids(path):
    with np.load(path) as mesh:
        vertices = mesh['vertices'].astype(float)
        if 'anchor' in mesh:
            vertices += mesh['anchor']
        triangles = vertices[mesh['faces']]
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    selected = (lengths > 1e-8) & (normals[:, 2] > lengths * .5)
    return triangles[selected].mean(axis=1)


def main():
    target = ROOT / 'data/derived/surface-control-points.json'
    record = json.loads(target.read_text(encoding='utf8'))
    base = record.get('pre_structure_control_count', len(record['points_local_m']))
    record['pre_structure_control_count'] = base
    record['points_local_m'] = record['points_local_m'][:base]
    groups = []
    tunnel_path = ROOT / 'data/derived/underpass-blockouts.json'
    tunnel = json.loads(tunnel_path.read_text(encoding='utf8'))
    for row in tunnel['meshes']:
        if row['reference_only'] or row['collision'] != 'complex':
            continue
        if not (row['role'].startswith('Floor') or row['role'] == 'Deck'):
            continue
        mesh_path = ROOT / row['path']
        if digest(mesh_path) != row['sha256']:
            raise ValueError(f'Changed structure mesh: {mesh_path}')
        probes = top_centroids(mesh_path)
        first = len(record['points_local_m'])
        record['points_local_m'].extend(probes.tolist())
        groups.append(dict(name=row['name'], first_index=first, count=len(probes),
                           mesh_path=row['path'], sha256=row['sha256']))
    named_path = ROOT / 'manifests/named-feature-terrain-cuts.json'
    for row in json.loads(named_path.read_text(encoding='utf8'))['cuts']:
        if row['id'] != 'SP_prospect_lookout':
            continue
        mesh_path = ROOT / row['visible_surface_mesh']
        if digest(mesh_path) != row['visible_surface_sha256']:
            raise ValueError('Changed terrace replacement')
        probes = top_centroids(mesh_path)
        first = len(record['points_local_m'])
        record['points_local_m'].extend(probes.tolist())
        groups.append(dict(name=row['name'], first_index=first, count=len(probes),
                           mesh_path=row['visible_surface_mesh'], sha256=row['visible_surface_sha256']))
    record['structure_control_groups'] = groups
    # The raised Siwash connector must be checked against its top, not the
    # classified ground below it. Rail tops are deliberately not walk probes.
    for relative,selected_names in [
        ('manifests/siwash-approach-blockout.json', {'SM_SiwashLookout_RaisedApproach'}),
        ('manifests/west-landmark-blockouts.json', {'SM_SiwashLookout_ConcreteRoof'}),
        ('manifests/lumberman-facility-blockouts.json', {'SM_LumbermanFacility_PedestrianFloor','SM_LumbermanFacility_RoadDeck'}),
        ('manifests/lagoon-structure-blockouts.json', {'SM_NatureHouse_ViewingDeck'}),
        ('manifests/nature-house-threshold.json', {'SM_NatureHouse_RearDeckThreshold'})
    ]:
        manifest=ROOT/relative
        assets=json.loads(manifest.read_text(encoding='utf8'))['assets']
        missing=selected_names-{row['name'] for row in assets}
        if missing:raise ValueError('Missing required walking surface controls: '+str(missing))
        for row in assets:
            if row['name'] not in selected_names:continue
            path=ROOT/row['mesh_path']
            if digest(path)!=row['sha256']:raise ValueError('Changed raised walking surface')
            probes=top_centroids(path);first=len(record['points_local_m'])
            record['points_local_m'].extend(probes.tolist())
            groups.append(dict(name=row['name'],first_index=first,count=len(probes),
                               mesh_path=row['mesh_path'],sha256=row['sha256']))
    record['structure_control_count'] = sum(g['count'] for g in groups)
    record['structure_control_method'] = 'Every upward-facing selected underpass floor/deck, Prospect terrace, Siwash roof/approach, Lumberman floor/deck and Nature House deck/threshold triangle centroid'
    record['structure_manifests'] = [dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p))
                                     for p in (tunnel_path, named_path,
                                               ROOT/'manifests/siwash-approach-blockout.json',
                                               ROOT/'manifests/west-landmark-blockouts.json',
                                               ROOT/'manifests/lumberman-facility-blockouts.json',
                                               ROOT/'manifests/lagoon-structure-blockouts.json',
                                               ROOT/'manifests/nature-house-threshold.json')]
    save_json(target, record)
    print(json.dumps(dict(controls=len(record['points_local_m']), groups=groups), indent=2))


if __name__ == '__main__':
    main()
