"""Inspect seven at-grade joins on exported triangles, not the source DTM grid.

This is a numerical data inspection, not a runtime collision test. It preserves
the excluded grade-separated crossing and never enables route transfers.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, box

from mesh_surface_query import MeshSurfaceQuery

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def points(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Point':
        return [geometry]
    if geometry.geom_type in ('MultiPoint', 'GeometryCollection'):
        return [p for part in geometry.geoms for p in points(part)]
    # A line on the boundary is not an ordinary crossing. Report its endpoints.
    if geometry.geom_type == 'LineString':
        return [Point(geometry.coords[0]), Point(geometry.coords[-1])]
    return [p for part in geometry.geoms for p in points(part)]


def inspect_branch(junction, branch, incident, surfaces):
    xy = np.asarray(branch['coordinates_local_xy_m'])
    if incident['endpoint'] == 'end':
        xy = xy[::-1]
    line = LineString(xy)
    stations = np.arange(0, min(line.length, 12)+.0001, .1)
    center = np.array([line.interpolate(s).coords[0] for s in stations])
    tangent = np.gradient(center, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    left = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    xmin, ymin = center.min(0)-4
    xmax, ymax = center.max(0)+4
    bounds = [xmin, ymin, xmax, ymax]
    terrain = MeshSurfaceQuery(ROOT, surfaces['terrain'], bounds)
    pavement = MeshSurfaceQuery(ROOT, [p for p in surfaces['pavement'] if p['role'] == 'pavement'], bounds)
    branch_mesh = MeshSurfaceQuery(ROOT, [r for r in surfaces['routes'] if r['edge_id'] == branch['edge_id']], bounds)
    if pavement.footprint.is_empty or branch_mesh.footprint.is_empty:
        raise ValueError(f'Missing source mesh at {junction["junction_id"]}')
    contact = shapely.union_all([terrain.footprint, pavement.footprint])
    probes, mesh_crossings = [], []
    # Three wheel/clearance tracks cover the central 1 m of this estimated 3 m lane.
    # Full lane-footprint contact is separately measured below.
    for offset in [-.5, 0., .5]:
        track = LineString(center+left*offset)
        crossings = []
        for crossing in points(track.intersection(pavement.footprint.boundary)):
            at = track.project(crossing)
            pavement_heights = pavement.heights(crossing.coords[0])
            terrain_heights = terrain.heights(crossing.coords[0])
            if not pavement_heights or not terrain_heights:
                crossings.append(dict(xy=list(crossing.coords[0]), distance_from_endpoint_m=at,
                    status='missing_exact_contact_side', pavement_heights_m=pavement_heights,
                    terrain_heights_m=terrain_heights))
                continue
            gap = max(abs(a-b) for a in pavement_heights for b in terrain_heights)
            record = dict(xy=list(crossing.coords[0]), distance_from_endpoint_m=at,
                pavement_heights_m=pavement_heights, terrain_heights_m=terrain_heights,
                maximum_contact_step_m=gap, status='within_step_limit' if gap <= .03 else 'contact_step_exceeds_limit')
            crossings.append(record)
            mesh_crossings.append(gap)
        # A 1 micrometre buffer suppresses triangle roundoff, not physical gaps.
        uncovered = track.difference(contact.buffer(1e-6))
        samples = []
        for p in center+left*offset:
            ph, th, bh = pavement.heights(p), terrain.heights(p), branch_mesh.heights(p)
            contact_heights = ph+th
            if bh and contact_heights:
                samples.append(max(bh)-max(contact_heights))
        probes.append(dict(lateral_offset_m=offset, crossing_count=len(crossings), crossings=crossings,
            unsupported_track_length_m=float(uncovered.length),
            branch_visual_minus_collision_range_m=[min(samples), max(samples)] if samples else None))
    # Restrict the full-width check to the first 12 m, including its endpoint cap.
    region = LineString(center).buffer(1.5, cap_style='flat', join_style='mitre')
    full_uncovered = region.difference(contact.buffer(1e-6))
    # The whole lane seam, not only the wheel tracks: linear triangle-plane
    # differences attain extrema at boundary/triangle intersection vertices.
    seam = pavement.footprint.boundary.intersection(region)
    critical = points(seam)
    for layer in [terrain, pavement]:
        for index in layer.tree.query(seam, predicate='intersects'):
            critical.extend(points(layer.polygons[index].boundary.intersection(seam)))
    unique = {tuple(np.round(p.coords[0], 7)): p.coords[0] for p in critical}
    seam_checks = []
    for xy in unique.values():
        ph, th = pavement.heights(xy), terrain.heights(xy)
        seam_checks.append(dict(xy=list(xy), pavement_heights_m=ph, terrain_heights_m=th,
            maximum_contact_step_m=max(abs(a-b) for a in ph for b in th) if ph and th else None))
    seam_steps = [s['maximum_contact_step_m'] for s in seam_checks if s['maximum_contact_step_m'] is not None]
    gap = branch_mesh.footprint.distance(pavement.footprint)
    steps_present = bool(mesh_crossings) and all(p['crossing_count'] for p in probes)
    missing_sides = any(c['status'] == 'missing_exact_contact_side' for p in probes for c in p['crossings'])
    passed = (steps_present and not missing_sides and bool(seam_steps)
              and all(s['maximum_contact_step_m'] is not None for s in seam_checks)
              and max(mesh_crossings+seam_steps) <= .03
              and gap <= .001 and full_uncovered.area <= .001
              and max(p['unsupported_track_length_m'] for p in probes) <= .001)
    return dict(edge_id=branch['edge_id'], endpoint=incident['endpoint'],
        visual_ribbon_collision='none; contact uses exported terrain plus main pavement',
        visual_ribbon_declared_lift_m=.06, geometry_gap_between_visual_branch_and_pavement_m=float(gap),
        local_full_width_uncovered_contact_area_m2=float(full_uncovered.area),
        maximum_exact_contact_step_m=max(mesh_crossings+seam_steps) if mesh_crossings+seam_steps else None,
        full_lane_seam_checks=seam_checks,
        probes=probes, numerical_contact_pass=passed,
        runtime_collision_verified=False,
        inputs=list({i['path']: i for layer in [terrain, pavement, branch_mesh] for i in layer.inputs}.values()))


def main():
    source_paths = ['data/routes/derived/city-branch-connections-reviewed.json',
                    'data/routes/derived/city-branch-junctions.json', 'manifests/surface-model.json']
    review, city, surfaces = [read(p) for p in source_paths]
    branches = {b['edge_id']: b for b in city['branches']}
    result, excluded = [], []
    for junction in review['main_circuit_junction_reviews']:
        if junction['connection_status'] == 'grade_separated_no_transfer':
            excluded.append(dict(junction_id=junction['junction_id'], transfer_enabled=False,
                reason='Road-top branches and underpass are separate levels; no connection created.'))
            continue
        checks = [inspect_branch(junction, branches[e['edge_id']], e, surfaces)
                  for e in junction['incident_edges'] if not e['main_circuit']]
        result.append(dict(junction_id=junction['junction_id'],
            source_station_m=junction['source_circuit_station_m'], branches=checks,
            numerical_contact_pass=all(b['numerical_contact_pass'] for b in checks),
            navigation_transfer_enabled=False, interactive_acceptance=False))
    assert len(result) == 7 and [e['junction_id'] for e in excluded] == ['city_junction_041']
    output = dict(schema_version=1, method='Actual exported top triangles and exact branch-track / pavement-boundary crossings',
        limits=dict(maximum_contact_step_m=.03, maximum_unsupported_track_length_m=.001,
                    maximum_uncovered_full_width_area_m2=.001, projection_roundoff_buffer_m=.000001),
        acceptance_limits_status='M1 numerical inspection limits; not surveyed design tolerances',
        runtime_status='Not tested by this file. Application ride-through and side inspection remain required.',
        source_inputs=[dict(path=p, sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in source_paths],
        junction_count=len(result), branch_count=sum(len(j['branches']) for j in result),
        numerical_pass_count=sum(j['numerical_contact_pass'] for j in result),
        junctions=result, excluded_grade_separated_junctions=excluded)
    path = ROOT/'evidence/main-branch-join-inspection.json'
    path.write_text(json.dumps(output, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k: output[k] for k in ['junction_count', 'branch_count', 'numerical_pass_count']}))
    for j in result:
        print(j['junction_id'], [(b['edge_id'], b['maximum_exact_contact_step_m'], b['local_full_width_uncovered_contact_area_m2']) for b in j['branches']])


if __name__ == '__main__':
    main()
