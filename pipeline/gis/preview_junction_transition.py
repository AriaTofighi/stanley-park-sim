"""Numerical local preview only; does not rebuild or overwrite shared terrain."""
import json
from pathlib import Path
import sys

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'pipeline/routes'))
from mesh_surface_query import MeshSurfaceQuery
from junction_terrain_transition import JunctionTerrainTransition
from paved_surfaces import load_profile


def main():
    surface = json.loads((ROOT/'manifests/surface-model.json').read_text())
    old = MeshSurfaceQuery(ROOT, surface['terrain'], [390, 850, 430, 895])
    overlay = MeshSurfaceQuery(ROOT, [r for r in surface['routes'] if r['edge_id']=='city_bikeways_2336'], [394, 854, 426, 891])
    def original_z(pts):
        result=[]
        for p in pts:
            heights=old.heights(p[:2])
            result.append(float(np.mean(heights)) if heights else overlay.height(p[:2])-.06)
        return np.asarray(result)
    profile, points, normals, _ = load_profile()
    transition = JunctionTerrainTransition(ROOT, points, normals, profile, original_z)
    vertices = old.triangles.reshape(-1, 3)
    faces = np.arange(len(vertices)).reshape(-1, 3)
    v, f, _, report = transition.apply(vertices, faces)
    updated = MeshSurfaceQuery(ROOT, [], [390, 850, 430, 895])
    updated.triangles = v[f]
    updated.polygons = shapely.polygons(updated.triangles[:, :, :2])
    updated.tree = shapely.STRtree(updated.polygons)
    old_checks = json.loads((ROOT/'evidence/main-branch-join-inspection-before-transition.json').read_text())
    branch = next(j for j in old_checks['junctions'] if j['junction_id']=='city_junction_036')['branches'][0]
    checks = []
    for check in branch['full_lane_seam_checks']:
        height = updated.height(check['xy'])
        checks.append(dict(xy=check['xy'], old_step_m=check['maximum_contact_step_m'],
            preview_step_m=max(abs(height-z) for z in check['pavement_heights_m'])))
    report['local_preview_full_width_max_step_m'] = max(c['preview_step_m'] for c in checks)
    report['local_preview_seam_checks'] = checks
    report['original_terrain_inputs'] = old.inputs
    report['preview_only_not_integrated'] = True
    ov=overlay.triangles.reshape(-1,3)
    of=np.arange(len(ov)).reshape(-1,3)
    rv,rf,overlay_report=transition.refit_overlay(ov,of,v,f)
    report['overlay_preview']=overlay_report
    assert report['local_preview_full_width_max_step_m'] <= .03
    np.savez_compressed(ROOT/'data/derived/junction036-transition-preview.npz', vertices=v, faces=f, anchor=np.zeros(3))
    (ROOT/'evidence/junction036-transition-preview.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['affected_input_triangles', 'replacement_triangles',
        'maximum_vertex_displacement_m', 'footprint_area_m2', 'local_preview_full_width_max_step_m']}))
    print(json.dumps(overlay_report))


if __name__ == '__main__':
    main()
