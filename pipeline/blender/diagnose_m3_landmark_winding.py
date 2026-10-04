"""Read-only component winding audit for the original M3 decorative layers."""
from pathlib import Path
import hashlib
import json
import runpy
from collections import Counter, defaultdict

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def components(vertices, faces):
    """Return closed-component signed volumes and radial face orientation."""
    vertices = np.asarray(vertices, float)
    parent = list(range(len(vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for face in faces:
        for i in face[1:]:
            parent[find(i)] = find(face[0])
    groups = defaultdict(list)
    for index, face in enumerate(faces):
        groups[find(face[0])].append(index)
    result = []
    for indexes in groups.values():
        ids = sorted({i for index in indexes for i in faces[index]})
        centre = vertices[ids].mean(axis=0)
        edges = Counter()
        geometric_edges = Counter()
        welded = {i: tuple(np.round(vertices[i], 7)) for i in ids}
        volume = 0.0
        positive = negative = degenerate = 0
        for index in indexes:
            face = faces[index]
            p = vertices[list(face)] - centre
            normal = np.zeros(3)
            for j in range(1, len(face)-1):
                cross = np.cross(p[j], p[j+1])
                volume += float(np.dot(p[0], cross))/6
                normal += np.cross(p[j]-p[0], p[j+1]-p[0])
            radial = float(np.dot(normal, p.mean(axis=0)))
            if np.linalg.norm(normal) < 1e-12:
                degenerate += 1
            elif radial > 1e-10:
                positive += 1
            elif radial < -1e-10:
                negative += 1
            for a, b in zip(face, face[1:]+face[:1]):
                edges[tuple(sorted((a, b)))] += 1
                if welded[a] != welded[b]:
                    geometric_edges[tuple(sorted((welded[a], welded[b])))] += 1
        closed = all(count == 2 for count in edges.values())
        geometrically_closed = bool(geometric_edges) and all(count == 2 for count in geometric_edges.values())
        result.append(dict(face_indexes=indexes, vertices=len(ids), faces=len(indexes),
            closed_by_index_edges=closed, signed_volume_m3=volume,
            closed_after_coordinate_weld_for_analysis=geometrically_closed,
            radial_outward_faces=positive, radial_inward_faces=negative,
            degenerate_faces=degenerate,
            repair_required=geometrically_closed and volume < -1e-9))
    return result


def inspect():
    form_path = 'pipeline/blender/build_m3_landmark_forms.py'
    helper = runpy.run_path(str(ROOT/form_path), run_name='winding_read_only')
    g = helper['Form']()
    g.ellipsoid((0, 0, 0), (1, 1, 1), 0)
    probe = components(g.vertices, g.faces)
    records = []
    inputs = {form_path: sha(ROOT/form_path)}
    for layer in ['m3-landmark-forms', 'm3-landmark-detail', 'm3-second-beach-detail']:
        pointer = ROOT/'exports'/layer/'latest.json'
        source_path = json.loads(pointer.read_text())['manifest']
        inputs[pointer.relative_to(ROOT).as_posix()] = sha(pointer)
        inputs[source_path] = sha(ROOT/source_path)
        source = json.loads((ROOT/source_path).read_text())
        for row in source['assets']:
            obj = bpy.data.objects.get(row['name'])
            if obj is None:
                raise RuntimeError('Missing audit source '+row['name'])
            vertices = [tuple(v.co) for v in obj.data.vertices]
            faces = [list(p.vertices) for p in obj.data.polygons]
            parts = components(vertices, faces)
            records.append(dict(name=obj.name, source_manifest=source_path,
                mesh=obj.data.name, vertex_positions_sha256=hashlib.sha256(np.asarray(vertices,dtype='<f8').tobytes()).hexdigest(),
                faces_sha256=hashlib.sha256(json.dumps(faces).encode()).hexdigest(),
                transform=[list(row) for row in obj.matrix_world],
                components=parts, inward_closed_components=sum(c['repair_required'] for c in parts),
                affected_faces=sum(c['faces'] for c in parts if c['repair_required'])))
    result = dict(scope='Read-only closed-component signed volume and face/centre audit. No scene mutations.',
        input_hashes=inputs, unit_ellipsoid=probe,
        affected_asset_names=[r['name'] for r in records if r['inward_closed_components']],
        assets=records, visual_acceptance=False)
    path = ROOT/'evidence/m3-landmark-winding-diagnosis.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    return dict(report=path.relative_to(ROOT).as_posix(),unit_ellipsoid=[{k:v for k,v in c.items() if k!='face_indexes'} for c in probe],
        affected_assets=[dict(name=r['name'],components=r['inward_closed_components'],faces=r['affected_faces']) for r in records if r['inward_closed_components']])


if __name__ in {'__main__', '<run_path>'}:
    result = inspect()
