"""Record source-scene collision rays without changing controls or scene objects.

Run in Blender after saving the authored scene and exporting its manifest.
This is a geometric source oracle, not an import, runtime or accuracy pass.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / 'data/derived/surface-control-points.json'
EXPORT_PATH = ROOT / 'manifests/blender-export.json'
OUTPUT_PATH = ROOT / 'evidence/blender-source-surface-ray-oracle.json'
EXPECTED_CONTROL_SHA256 = '7f8d10ea8f19372d99fcb0ecc7a07d0de629d8ec23e56ddc75ce9999ffa36749'
EXPECTED_CONTROL_COUNT = 5052


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exported_mesh_fingerprint(source, scene, exporter_hash):
    """Read-only equivalent of export_assets.py's current static fingerprint."""
    digest = hashlib.sha256()
    digest.update(json.dumps(dict(exporter=exporter_hash, blender=bpy.app.version_string,
        unit_scale=scene.unit_settings.scale_length,
        materials=[(m.name, list(m.diffuse_color)) for m in source.data.materials])).encode())
    for values, attribute, count, dtype in [
            (source.data.vertices, 'co', 3, np.float32),
            (source.data.loops, 'vertex_index', 1, np.int32),
            (source.data.polygons, 'loop_start', 1, np.int32),
            (source.data.polygons, 'loop_total', 1, np.int32),
            (source.data.polygons, 'material_index', 1, np.int32),
            (source.data.polygons, 'use_smooth', 1, np.bool_),
            (source.data.corner_normals, 'vector', 3, np.float32)]:
        buffer = np.empty(len(values) * count, dtype=dtype)
        values.foreach_get(attribute, buffer)
        digest.update(buffer.tobytes())
    for layer in source.data.color_attributes:
        digest.update((layer.name + layer.domain + layer.data_type).encode())
        buffer = np.empty(len(layer.data) * 4, dtype=np.float32)
        layer.data.foreach_get('color', buffer)
        digest.update(buffer.tobytes())
    for layer in source.data.uv_layers:
        digest.update((layer.name + str(layer.active_render)).encode())
        buffer = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get('uv', buffer)
        digest.update(buffer.tobytes())
    return digest.hexdigest()


def build_oracle():
    started = time.perf_counter()
    control_hash, export_hash = sha256(CONTROL_PATH), sha256(EXPORT_PATH)
    if control_hash != EXPECTED_CONTROL_SHA256:
        raise RuntimeError('The fixed control file changed; do not silently rebase this oracle')
    controls = json.loads(CONTROL_PATH.read_text(encoding='utf8'))
    original = controls['points_local_m']
    points = np.asarray(original, dtype=np.float64)
    if points.shape != (EXPECTED_CONTROL_COUNT, 3) or not np.isfinite(points).all():
        raise ValueError('Expected exactly 5052 finite, unchanged local-metre control points')
    export = json.loads(EXPORT_PATH.read_text(encoding='utf8'))
    scene = bpy.data.scenes['StanleyPark_M1']
    blend_path = ROOT / export['source_blend']
    if Path(bpy.data.filepath).resolve() != blend_path.resolve() or not blend_path.is_file():
        raise RuntimeError('Open the exported authored .blend source before running the oracle')
    blend_hash = sha256(blend_path)
    exporter_hash = sha256(ROOT / 'pipeline/blender/export_assets.py')
    ray_starts = points + [0., 0., 2.]
    ray_ends = points - [0., 0., 2.]
    hits = [[] for _ in original]
    object_records, excluded = [], []
    seen_sources = set()
    direction = Vector((0., 0., -1.))
    ray_count = 0
    bvh_count = 0
    for item in sorted(export['assets'], key=lambda row: row['name']):
        source_name = item['source_object']
        if not item['place_in_level']:
            excluded.append(dict(export_asset=item['name'], source_object=source_name, reason='place_in_level is false'))
            continue
        if item['collision'] != 'complex':
            excluded.append(dict(export_asset=item['name'], source_object=source_name,
                                 reason='collision=' + item['collision'] + '; only complex source meshes enter this oracle'))
            continue
        if source_name in seen_sources:
            raise RuntimeError('Duplicate placed source object in export manifest: ' + source_name)
        seen_sources.add(source_name)
        source = scene.objects.get(source_name)
        if source is None or source.type != 'MESH' or not source.get('pipeline_owner'):
            raise RuntimeError('Missing authored mesh source: ' + source_name)
        if source.get('collision', 'none') != 'complex' or source.modifiers:
            raise RuntimeError('Source collision/modifier contract differs from export: ' + source_name)
        fingerprint = exported_mesh_fingerprint(source, scene, exporter_hash)
        if fingerprint != item['source_export_fingerprint']:
            raise RuntimeError('Authored source changed after export: ' + source_name)
        mesh = source.data
        if len(mesh.vertices) != item['vertices'] or len(mesh.polygons) != item['polygons']:
            raise RuntimeError('Authored source counts differ from export: ' + source_name)
        local = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get('co', local)
        local = local.reshape(-1, 3)
        matrix = np.asarray(source.matrix_world, dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.isfinite(local).all():
            raise ValueError('Non-finite source coordinates or transform: ' + source_name)
        # Current exporter places translation-only assets. Reject stale parent
        # transforms instead of presenting them as an engine import residual.
        expected_matrix = np.eye(4)
        cm = item['position_cm']
        expected_matrix[:3, 3] = [cm[1]/100., cm[0]/100., cm[2]/100.]
        if np.max(np.abs(matrix - expected_matrix)) > 1e-6:
            raise RuntimeError('World transform differs from current export placement contract: ' + source_name)
        world = local @ matrix[:3, :3].T + matrix[:3, 3]
        if not np.isfinite(world).all():
            raise ValueError('Non-finite transformed source coordinates: ' + source_name)
        mesh.calc_loop_triangles()
        triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get('vertices', triangles)
        triangles = triangles.reshape(-1, 3)
        if not len(triangles) or triangles.min() < 0 or triangles.max() >= len(world):
            raise ValueError('Invalid source triangle index array: ' + source_name)
        polygon_ids = np.empty(len(mesh.loop_triangles), dtype=np.int32)
        mesh.loop_triangles.foreach_get('polygon_index', polygon_ids)
        used = np.unique(triangles)
        lo, hi = world[used].min(axis=0), world[used].max(axis=0)
        candidates = np.flatnonzero(
            (points[:, 0] >= lo[0]-1e-7) & (points[:, 0] <= hi[0]+1e-7) &
            (points[:, 1] >= lo[1]-1e-7) & (points[:, 1] <= hi[1]+1e-7) &
            (ray_starts[:, 2] >= lo[2]-1e-7) & (ray_ends[:, 2] <= hi[2]+1e-7))
        geometry_hash = hashlib.sha256()
        for array in (world, triangles, polygon_ids):
            geometry_hash.update(array.tobytes())
        record = dict(source_object=source_name, export_asset=item['name'],
            asset_path=item['asset_path'], label=str(source.get('landmark', source_name)),
            source_id=str(source.get('source_id', item['source_id'])),
            pipeline_owner=str(source['pipeline_owner']), collision='complex',
            source_export_fingerprint=fingerprint, source_world_triangle_sha256=geometry_hash.hexdigest(),
            world_matrix=matrix.tolist(), bounds_min_local_m=lo.tolist(), bounds_max_local_m=hi.tolist(),
            vertices=len(world), triangles=len(triangles), candidate_control_count=len(candidates))
        object_records.append(record)
        if not len(candidates):
            continue
        # Keep world orientation and use a per-object numerical origin. This
        # applies the exact world matrix while limiting BVH float32 roundoff.
        bvh_origin = (lo + hi) * .5
        bvh = BVHTree.FromPolygons((world-bvh_origin).tolist(), triangles.tolist(), all_triangles=True, epsilon=0.)
        bvh_count += 1
        for index in candidates:
            ray_count += 1
            location, normal, triangle_id, distance = bvh.ray_cast(
                Vector((ray_starts[index]-bvh_origin).tolist()), direction, 4.)
            if location is None:
                continue
            if triangle_id is None or not 0 <= triangle_id < len(polygon_ids):
                raise ValueError('Invalid BVH triangle index: ' + source_name)
            position = np.asarray(location, dtype=float) + bvh_origin
            normal_array = np.asarray(normal, dtype=float)
            if (position.shape != (3,) or normal_array.shape != (3,)
                    or not np.isfinite(position).all() or not np.isfinite(normal_array).all()
                    or not np.isfinite(distance) or distance < 0 or distance > 4.+1e-6):
                raise ValueError('Invalid source ray result: ' + source_name)
            hits[index].append(dict(source_object=source_name, export_asset=item['name'],
                label=record['label'], source_id=record['source_id'],
                hit_local_m=position.tolist(), height_m=float(position[2]),
                ray_distance_m=float(distance), normal_world=normal_array.tolist(),
                source_loop_triangle_index=int(triangle_id), source_polygon_index=int(polygon_ids[triangle_id]),
                residual_to_original_height_m=float(position[2]-points[index, 2])))
        del bvh
    rows = []
    group_by_index = {}
    for group in controls.get('structure_control_groups', []):
        for index in range(group['first_index'], group['first_index']+group['count']):
            if index < 0 or index >= len(points) or index in group_by_index:
                raise ValueError('Invalid original structure-control ranges')
            group_by_index[index] = group['name']
    for index, candidates in enumerate(hits):
        candidates.sort(key=lambda row: (row['ray_distance_m'], row['source_object']))
        nearest = candidates[0] if candidates else None
        rows.append(dict(control_index=index, source_local_m=original[index],
            original_height_m=original[index][2], original_sample_group=group_by_index.get(index),
            ray_start_local_m=ray_starts[index].tolist(), ray_end_local_m=ray_ends[index].tolist(),
            hit_status='hit' if nearest else 'no_source_hit', expected_nearest_hit=nearest,
            object_first_hits=candidates))
    if (sha256(CONTROL_PATH) != control_hash or sha256(EXPORT_PATH) != export_hash
            or sha256(blend_path) != blend_hash):
        raise RuntimeError('An input changed during the source oracle; discard this run')
    residuals = [r['expected_nearest_hit']['residual_to_original_height_m']
                 for r in rows if r['expected_nearest_hit'] is not None]
    output = dict(schema_version=1, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='Authored Blender complex-collision source geometry; not imported meshes, a rider test or an acceptance decision',
        inputs=dict(control_path=CONTROL_PATH.relative_to(ROOT).as_posix(), control_sha256=control_hash,
            export_manifest=EXPORT_PATH.relative_to(ROOT).as_posix(), export_manifest_sha256=export_hash,
            source_blend=export['source_blend'], source_blend_sha256=blend_hash,
            blend_memory_state='dirty' if bpy.data.is_dirty else 'saved',
            blend_hash_scope='Hash of saved file; source fingerprints and world triangle hashes identify the live authored mesh data',
            stage_sha256=sha256(Path(__file__)), exporter_sha256=exporter_hash),
        query_contract=dict(coordinates='project local east,north,up metres', start_offset_z_m=2., end_offset_z_m=-2.,
            maximum_ray_distance_m=4., collision_selection='Only exported place_in_level source MESH objects with collision=complex',
            ray_selection='Closest non-negative BVH intersection; each object contributes its first hit; global minimum distance wins',
            facing='No normal-direction or sampled-component filter; BVH polygon intersections are used as returned',
            bvh_space='World-oriented geometry relative to each object bounds centre; exact source world matrix, epsilon=0',
            aabb_candidate_roundoff_margin_m=1e-7,
            comparison_tolerance_m=.01, tolerance_scope='Recorded unchanged transfer tolerance; this stage makes no pass/fail comparison',
            original_controls='All 5052 original rows, heights and order are preserved; occluders are retained and identified'),
        original_control_metadata={k:v for k,v in controls.items() if k != 'points_local_m'},
        objects=object_records, excluded_export_assets=excluded, points=rows,
        summary=dict(control_count=len(rows), source_object_count=len(object_records), built_bvhs=bvh_count,
            bvh_ray_queries=ray_count, source_hits=len(residuals), no_source_hits=len(rows)-len(residuals),
            minimum_original_height_residual_m=min(residuals) if residuals else None,
            maximum_original_height_residual_m=max(residuals) if residuals else None,
            nearest_source_object_counts=dict(Counter(r['expected_nearest_hit']['source_object'] for r in rows if r['expected_nearest_hit'])),
            elapsed_seconds=time.perf_counter()-started))
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, allow_nan=False)+'\n', encoding='utf8')
    return dict(output=OUTPUT_PATH.relative_to(ROOT).as_posix(), output_sha256=sha256(OUTPUT_PATH),
                **output['summary'])


result = build_oracle()
