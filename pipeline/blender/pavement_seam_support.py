"""One bounded backing patch for the observed closed-circuit ray miss.

Pure NumPy preparation and checks; Blender calls this before route authoring.
Source NPZ meshes and source/runtime control points are never changed.
"""
import hashlib
import json
from pathlib import Path

import numpy as np


TARGET = 'SM_PavementSupport_049'
HALF_LENGTH = .10
EDGE_INSET = .02
MIN_DROP, MAX_DROP, DESIGN_DROP = .0005, .002, .00075


def cross2(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def area(poly):
    if len(poly) < 3:
        return 0.
    return abs(float(np.sum(cross2(poly, np.roll(poly, -1, axis=0))))) * .5


def intersect(subject, clip):
    """Clip a convex CCW polygon, using local coordinates for precision."""
    result = np.asarray(subject, dtype=float)
    for a, b in zip(clip, np.roll(clip, -1, axis=0)):
        if not len(result):
            break
        signed = cross2(b-a, result-a)
        output = []
        for i, p in enumerate(result):
            q, dp, dq = result[(i+1) % len(result)], signed[i], signed[(i+1) % len(result)]
            inside_p, inside_q = dp >= -1e-12, dq >= -1e-12
            if inside_p:
                output.append(p)
            if inside_p != inside_q:
                output.append(p + (q-p) * dp/(dp-dq))
        result = np.asarray(output, dtype=float).reshape(-1, 2)
    return result


def plane(triangle):
    return np.linalg.solve(np.c_[triangle[:, :2], np.ones(3)], triangle[:, 2])


def heights(coefficients, xy):
    return np.c_[xy, np.ones(len(xy))] @ coefficients


def quantized_world(vertices, anchor, centimetres=False):
    """Predict mesh float32 and, optionally, FBX/UE asset-centimetre float32.

    The export swaps/signs axes without changing precision. Actor translation
    is separate from asset vertices and is included after the conversion.
    """
    local = (vertices-anchor).astype(np.float32)
    placed = np.asarray(anchor, dtype=np.float32).astype(float)
    if centimetres:
        local = (local.astype(float)*100).astype(np.float32).astype(float)/100
        placed = (placed*100).astype(np.float32).astype(float)/100
    return local.astype(float)+placed


def inspect_patch(vertices, faces, source_triangles, origin):
    """Check all patch/source plane intersections, not just a point sample."""
    local = vertices-origin
    triangles = local[faces]
    total_area, supported_area, drops = 0., 0., []
    smallest_normal_z = 1.
    for tri in triangles:
        normal = np.cross(tri[1]-tri[0], tri[2]-tri[0])
        normal_z = float(normal[2]/np.linalg.norm(normal))
        smallest_normal_z = min(smallest_normal_z, normal_z)
        if normal_z <= .55:
            raise ValueError('Seam backing has a vertical, inverted or steep face')
        total_area += area(tri[:, :2])
        patch_plane = plane(tri)
        pieces = []
        for source in source_triangles:
            piece = intersect(tri[:, :2], source[:, :2])
            piece_area = area(piece)
            if piece_area <= 1e-14:
                continue
            pieces.append(piece)
            supported_area += piece_area
            drops.extend(heights(plane(source), piece)-heights(patch_plane, piece))
        # Coverage by disjoint source pieces plus equal area proves containment.
        for i, first in enumerate(pieces):
            for second in pieces[i+1:]:
                if area(intersect(first, second)) > 1e-10:
                    raise ValueError('Source pavement overlaps inside seam patch')
    unsupported = max(0., total_area-supported_area)
    if unsupported > 1e-9 or not drops:
        raise ValueError(f'Seam backing leaves the pavement footprint: {unsupported} m2')
    minimum, maximum = float(min(drops)), float(max(drops))
    if minimum < MIN_DROP or maximum > MAX_DROP:
        raise ValueError(f'Seam backing separation outside 0.5-2 mm: {minimum}, {maximum}')
    containing = []
    for index, tri in enumerate(triangles):
        bary = np.linalg.solve(np.vstack((tri[:, :2].T, np.ones(3))), [0., 0., 1.])
        if min(bary) > 0:
            edge_margin = min(abs(cross2(b-a, -a))/np.linalg.norm(b-a)
                              for a, b in zip(tri[:, :2], np.roll(tri[:, :2], -1, axis=0)))
            containing.append(dict(face=index, minimum_barycentric=float(min(bary)),
                                   minimum_edge_distance_m=float(edge_margin),
                                   control_drop_m=float(-plane(tri)[2])))
    if len(containing) != 1 or containing[0]['minimum_barycentric'] < .01 or containing[0]['minimum_edge_distance_m'] < .001:
        raise ValueError('Failed seam ray is not safely inside one backing triangle')
    return dict(area_m2=total_area, unsupported_area_m2=unsupported,
                minimum_depression_m=minimum, maximum_depression_m=maximum,
                minimum_up_normal_z=smallest_normal_z, control=containing[0], pass_=True)


def prepare(project_root, prepared, items, paved):
    """Append only to the in-memory support package; return stage evidence."""
    control_path = project_root/'data/derived/surface-control-points.json'
    controls = json.loads(control_path.read_text())
    index = controls['terrain_control_count']
    origin = np.asarray(controls['points_local_m'][index], dtype=float)
    failure_path = project_root/'evidence/unreal-surface-transfer-v25-failure.json'
    failure = json.loads(failure_path.read_text())['points'][2000]
    if index != 2000 or failure['hit_height_m'] is not None or np.max(abs(origin-failure['source_m'])) > 1e-10:
        raise ValueError('Seam backing is restricted to the recorded control 2000 miss')
    points = np.asarray(paved['points_local_m'])
    if np.max(abs(origin-points[0])) > 1e-10 or np.max(abs(points[0]-points[-1])) > 1e-10:
        raise ValueError('Seam control no longer matches the closed route origin')
    first = prepared['SM_Pavement_000']
    edge = first['vertices'][:2]+first['anchor']
    across = edge[1, :2]-edge[0, :2]
    width = np.linalg.norm(across)
    across /= width
    forward = np.array([across[1], -across[0]])
    if np.dot(forward, points[1, :2]-points[-2, :2]) <= 0:
        raise ValueError('Closing cross-section axes do not follow route direction')
    half_width = width*.5-EDGE_INSET
    if half_width <= .5:
        raise ValueError('Closing pavement is too narrow for this bounded patch')
    uv = np.array([[-HALF_LENGTH, -half_width], [HALF_LENGTH, -half_width],
                   [HALF_LENGTH, half_width], [-HALF_LENGTH, half_width], [.023, .193]])
    xy = uv[:, :1]*forward + uv[:, 1:]*across
    faces = np.array([[i, (i+1) % 4, 4] for i in range(4)], dtype=np.int32)
    source, inputs = [], []
    lower, upper = xy.min(0), xy.max(0)
    for item in items:
        if item['role'] != 'pavement':
            continue
        package = prepared[item['name']]
        triangles = (package['vertices']+package['anchor']-origin)[package['faces']]
        selected = np.all(triangles[:, :, :2].max(1) >= lower, axis=1) & np.all(triangles[:, :, :2].min(1) <= upper, axis=1)
        if selected.any():
            source.extend(triangles[selected])
            inputs.append(dict(path=item['path'], sha256=item['sha256']))
    source = np.asarray(source)
    samples = []
    for tri in source:
        piece = intersect(xy[:4], tri[:, :2])
        if area(piece) > 1e-14:
            samples.extend(np.c_[piece, heights(plane(tri), piece)])
    samples = np.asarray(samples)
    coefficients = np.linalg.lstsq(np.c_[samples[:, :2], np.ones(len(samples))], samples[:, 2], rcond=None)[0]
    excess = max(heights(coefficients, samples[:, :2])-samples[:, 2])
    coefficients[2] -= excess+DESIGN_DROP
    world_vertices = np.c_[xy, heights(coefficients, xy)]+origin
    target = prepared[TARGET]
    target_source = next(item for item in items if item['name'] == TARGET)
    inputs.append(dict(path=target_source['path'], sha256=target_source['sha256'], role='unchanged support base'))
    anchor = target['anchor']
    variants = {
        'float64_design': inspect_patch(world_vertices, faces, source, origin),
        'blender_float32_prediction': inspect_patch(quantized_world(world_vertices, anchor), faces, source, origin),
        'fbx_centimetre_float32_prediction': inspect_patch(quantized_world(world_vertices, anchor, True), faces, source, origin)}
    vertex_start, face_start = len(target['vertices']), len(target['faces'])
    target['vertices'] = np.vstack((target['vertices'], world_vertices-anchor))
    target['faces'] = np.vstack((target['faces'], faces+vertex_start))
    report = dict(schema_version=1, mesh=TARGET, trigger_control_index=index, trigger_control_m=origin.tolist(),
        source_inputs=inputs, controls_sha256=hashlib.sha256(control_path.read_bytes()).hexdigest(),
        failure_sha256=hashlib.sha256(failure_path.read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        appended_vertices=5, appended_triangles=4, first_vertex=vertex_start, first_triangle=face_start,
        footprint_length_m=2*HALF_LENGTH, footprint_width_m=2*half_width, pavement_edge_inset_m=EDGE_INSET,
        patch_vertices_world_m=world_vertices.tolist(), patch_triangles=faces.tolist(), checks=variants,
        source_npz_unchanged=True, source_controls_unchanged=True, visible_pavement_unchanged=True,
        no_new_vertical_faces=True, minimum_required_depression_m=MIN_DROP, maximum_allowed_depression_m=MAX_DROP,
        live_blender_verified=False, actual_fbx_import_verified=False, runtime_contact_accepted=False,
        scope='Bounded below-asphalt seam support only. A new exact Unreal ray and normal-controller crossing are required.')
    return report, dict(source_triangles=source, origin=origin, faces=faces)


def inspect_authored(report, context, authored_world_vertices, anchor):
    """Use the actual live Blender vertices after mesh.from_pydata."""
    vertices = np.asarray(authored_world_vertices)[report['first_vertex']:report['first_vertex']+5]
    report['checks']['authored_blender'] = inspect_patch(vertices, context['faces'], context['source_triangles'], context['origin'])
    report['checks']['authored_fbx_centimetre_float32_prediction'] = inspect_patch(
        quantized_world(vertices, anchor, True), context['faces'], context['source_triangles'], context['origin'])
    report['live_blender_verified'] = True
