"""Read-only editor comparison with the fixed Blender source-scene ray oracle.

Load with runpy, then call check(). No imports, world changes, play or saves occur.
Only the new evidence file is written. A repeat needs a new reviewed output name.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / 'data/derived/surface-control-points.json'
EXPORT_PATH = ROOT / 'manifests/blender-export.json'
ORACLE_PATH = ROOT / 'evidence/blender-source-surface-ray-oracle.json'
IMPORT_PATH = ROOT / 'evidence/unreal-import.json'
OUTPUT_PATH = ROOT / 'evidence/unreal-source-surface-transfer-v26.json'
CONTROL_SHA256 = '7f8d10ea8f19372d99fcb0ecc7a07d0de629d8ec23e56ddc75ce9999ffa36749'
CONTROL_COUNT = 5052
TOLERANCE_M = 0.01
MAP_PATH = '/Game/Maps/StanleyPark'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def finite(values, context):
    if isinstance(values, dict):
        for key, value in values.items():
            finite(value, context + '.' + key)
    elif isinstance(values, list):
        for index, value in enumerate(values):
            finite(value, context + '[' + str(index) + ']')
    elif isinstance(values, (float, int)):
        require(math.isfinite(values), 'Non-finite number: ' + context)


def index_unique(rows, field, context):
    result = {row[field]: row for row in rows}
    require(len(result) == len(rows), 'Duplicate ' + context)
    return result


def near_source_hits(row):
    """A uniform 1 cm source-height window, not a named-mesh exemption.

    The nearest source remains the height oracle. Absolute difference also
    handles sub-micrometre BVH ordering roundoff between coincident surfaces.
    Both UE-to-nearest and UE-to-matched-source errors are checked separately.
    """
    nearest = row['expected_nearest_hit']
    if nearest is None:
        return []
    return [hit for hit in row['object_first_hits']
            if abs(hit['height_m'] - nearest['height_m']) <= TOLERANCE_M]


def preflight():
    """File-only prerequisite checks; safe to run without Unreal or Blender."""
    require(not OUTPUT_PATH.exists(), 'Refuse to overwrite evidence: ' + str(OUTPUT_PATH))
    files = {path.relative_to(ROOT).as_posix(): sha256(path)
             for path in (CONTROL_PATH, EXPORT_PATH, ORACLE_PATH, IMPORT_PATH)}
    controls = json.loads(CONTROL_PATH.read_text(encoding='utf-8'))
    export = json.loads(EXPORT_PATH.read_text(encoding='utf-8'))
    oracle = json.loads(ORACLE_PATH.read_text(encoding='utf-8'))
    imported = json.loads(IMPORT_PATH.read_text(encoding='utf-8'))
    require(files[CONTROL_PATH.relative_to(ROOT).as_posix()] == CONTROL_SHA256,
            'The fixed control file has changed')
    require(oracle['schema_version'] == 1, 'Unsupported source oracle schema')
    inputs = oracle['inputs']
    require(inputs['control_path'] == CONTROL_PATH.relative_to(ROOT).as_posix()
            and inputs['control_sha256'] == CONTROL_SHA256, 'Oracle control identity differs')
    export_hash = files[EXPORT_PATH.relative_to(ROOT).as_posix()]
    require(inputs['export_manifest'] == EXPORT_PATH.relative_to(ROOT).as_posix()
            and inputs['export_manifest_sha256'] == export_hash, 'Oracle export revision differs')
    require(inputs['blend_memory_state'] == 'saved', 'Oracle used an unsaved Blender scene')
    require(inputs['source_blend'] == export['source_blend'], 'Source blend path differs')
    for relative, expected in [(inputs['source_blend'], inputs['source_blend_sha256']),
            ('pipeline/blender/build_source_surface_ray_oracle.py', inputs['stage_sha256']),
            ('pipeline/blender/export_assets.py', inputs['exporter_sha256'])]:
        files[relative] = sha256(ROOT / relative)
        require(files[relative] == expected, 'Oracle input changed: ' + relative)
    contract = oracle['query_contract']
    for key, expected in [('start_offset_z_m', 2), ('end_offset_z_m', -2),
                          ('maximum_ray_distance_m', 4), ('comparison_tolerance_m', TOLERANCE_M)]:
        require(contract[key] == expected, 'Oracle ray contract differs: ' + key)
    require(imported.get('success') is True and 'error' not in imported,
            'Current import did not finish successfully')
    require(imported.get('export_manifest_sha256') == export_hash,
            'Successful import is not for the current export')
    require(imported.get('map') == MAP_PATH and imported.get('completed_utc'),
            'Import map or completion record is missing')
    assets = index_unique(export['assets'], 'name', 'export asset name')
    imported_assets = index_unique(imported['assets'], 'name', 'import asset name')
    require(assets.keys() == imported_assets.keys(), 'Import asset coverage differs')
    placed = {name: asset for name, asset in assets.items() if asset['place_in_level']}
    audit = index_unique(imported.get('saved_actor_collision_checks', []), 'name', 'saved actor name')
    require(audit.keys() == placed.keys(), 'Persisted collision audit coverage differs')
    for name, asset in placed.items():
        row = audit[name]
        require(asset['collision'] in ('complex', 'none'), 'Unknown collision policy: ' + name)
        expected_profile = 'BlockAll' if asset['collision'] == 'complex' else 'NoCollision'
        expected_enabled = 'QUERY_AND_PHYSICS' if asset['collision'] == 'complex' else 'NO_COLLISION'
        require(row.get('pass') is True and row['declared'] == asset['collision']
                and row['profile'] == expected_profile and row['use_default_collision'] is False
                and ('.' + expected_enabled + ':') in row['actual'],
                'Persisted collision contract differs: ' + name)
    sources = index_unique(oracle['objects'], 'export_asset', 'oracle export asset')
    require(sources.keys() == {name for name, asset in placed.items() if asset['collision'] == 'complex'},
            'Oracle does not cover the exact placed complex-collision set')
    for name, source in sources.items():
        asset = assets[name]
        require(source['collision'] == 'complex' and source['source_object'] == asset['source_object']
                and source['asset_path'] == asset['asset_path']
                and source['source_export_fingerprint'] == asset['source_export_fingerprint'],
                'Oracle source/export identity differs: ' + name)
    points = controls['points_local_m']
    require(len(points) == len(oracle['points']) == CONTROL_COUNT, 'Control count differs')
    require(oracle['original_control_metadata'] == {key: value for key, value in controls.items()
                                                   if key != 'points_local_m'},
            'Original component metadata was not preserved')
    finite(points, 'controls')
    finite(oracle['objects'], 'oracle.objects')
    finite(oracle['points'], 'oracle.points')
    for index, (point, row) in enumerate(zip(points, oracle['points'])):
        require(row['control_index'] == index and row['source_local_m'] == point
                and row['original_height_m'] == point[2], 'Control row changed: ' + str(index))
        require(row['ray_start_local_m'] == [point[0], point[1], point[2] + 2]
                and row['ray_end_local_m'] == [point[0], point[1], point[2] - 2],
                'Ray endpoints changed: ' + str(index))
        hits = row['object_first_hits']
        index_unique(hits, 'export_asset', 'source hit at control ' + str(index))
        for hit in hits:
            require(hit['export_asset'] in sources
                    and hit['source_object'] == sources[hit['export_asset']]['source_object']
                    and 0 <= hit['ray_distance_m'] <= 4
                    and hit['height_m'] == hit['hit_local_m'][2],
                    'Source hit identity or interval differs: ' + str(index))
        require(hits == sorted(hits, key=lambda hit: (hit['ray_distance_m'], hit['source_object'])),
                'Source hits are not in nearest order: ' + str(index))
        require(row['expected_nearest_hit'] == (hits[0] if hits else None)
                and row['hit_status'] == ('hit' if hits else 'no_source_hit'),
                'Source nearest hit differs: ' + str(index))
    return dict(files=files, controls=controls, export=export, oracle=oracle,
                imported=imported, placed=placed, sources=sources)


def current_collision_audit(unreal, placed):
    """Read current actors as well as requiring the saved/reloaded import audit."""
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    rows = []
    for actor in actors.get_all_level_actors():
        if 'SP_Generated' not in [str(tag) for tag in actor.tags] or not isinstance(actor, unreal.StaticMeshActor):
            continue
        name = actor.get_actor_label()
        require(name in placed, 'Unexpected current generated mesh actor: ' + name)
        asset = placed[name]
        component = actor.static_mesh_component
        mesh = component.get_editor_property('static_mesh')
        expected_enabled = (unreal.CollisionEnabled.QUERY_AND_PHYSICS if asset['collision'] == 'complex'
                            else unreal.CollisionEnabled.NO_COLLISION)
        expected_profile = 'BlockAll' if asset['collision'] == 'complex' else 'NoCollision'
        mesh_path = mesh.get_path_name() if mesh else None
        expected_path = asset['asset_path'] + '.' + asset['name']
        visibility = component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)
        valid = (component.get_collision_enabled() == expected_enabled
                 and str(component.get_collision_profile_name()) == expected_profile
                 and component.get_editor_property('use_default_collision') is False
                 and mesh_path == expected_path)
        if asset['collision'] == 'complex':
            valid = valid and visibility == unreal.CollisionResponseType.ECR_BLOCK
        row = dict(name=name, declared=asset['collision'], mesh_path=mesh_path,
                   enabled=str(component.get_collision_enabled()),
                   profile=str(component.get_collision_profile_name()),
                   use_default_collision=component.get_editor_property('use_default_collision'),
                   visibility_response=str(visibility), contract_matches=valid)
        rows.append(row)
    indexed = index_unique(rows, 'name', 'current generated actor name')
    require(indexed.keys() == placed.keys(), 'Current generated actor coverage differs')
    require(all(row['contract_matches'] for row in rows),
            'Current collision contract differs: ' + str([row for row in rows if not row['contract_matches']]))
    return rows


def check():
    """Trace all immutable rays in the current editor world; write unique evidence."""
    import unreal

    started = time.perf_counter()
    state = preflight()
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    require(editor.get_game_world() is None, 'This bounded editor check requires the play session to be stopped')
    world = editor.get_editor_world()
    require(world and world.get_path_name() == MAP_PATH + '.StanleyPark', 'Open the Stanley Park editor map first')
    live_audit = current_collision_audit(unreal, state['placed'])
    rows = []
    for original in state['oracle']['points']:
        point = original['source_local_m']
        # Match the existing check's arithmetic and axis conversion exactly.
        start = unreal.Vector(point[1] * 100, point[0] * 100, point[2] * 100 + 200)
        end = unreal.Vector(start.x, start.y, start.z - 400)
        hit = unreal.SystemLibrary.line_trace_single(world, start, end,
            unreal.TraceTypeQuery.ECC_VISIBILITY, True, [], unreal.DrawDebugTrace.NONE, True)
        values = hit.to_dict() if hit else {}
        nearest = original['expected_nearest_hit']
        allowed = near_source_hits(original)
        actual = None
        if hit:
            actor = values.get('hit_actor')
            component = values.get('hit_component')
            mesh = component.get_editor_property('static_mesh') if isinstance(component, unreal.StaticMeshComponent) else None
            position = values['location']
            actual = dict(hit_local_m=[position.y / 100, position.x / 100, position.z / 100],
                          height_m=position.z / 100,
                          actor_label=actor.get_actor_label() if actor else None,
                          mesh_name=mesh.get_name() if mesh else None,
                          mesh_path=mesh.get_path_name() if mesh else None,
                          component_path=component.get_path_name() if component else None,
                          collision_enabled=str(component.get_collision_enabled()) if component else None,
                          collision_profile=str(component.get_collision_profile_name()) if component else None)
            finite(actual, 'actual hit ' + str(original['control_index']))
        declared_hit = next((candidate for candidate in original['object_first_hits']
            if actual and candidate['export_asset'] == actual['mesh_name']
            and actual['mesh_path'] == state['sources'][candidate['export_asset']]['asset_path'] + '.' + candidate['export_asset']
            and actual['actor_label'] == candidate['export_asset']), None)
        identity_matches = declared_hit is not None and declared_hit in allowed
        nearest_error = actual['height_m'] - nearest['height_m'] if actual and nearest else None
        declared_error = actual['height_m'] - declared_hit['height_m'] if actual and declared_hit else None
        failures = []
        if nearest is None:
            failures.append('no_source_hit')
        if actual is None:
            failures.append('no_unreal_hit')
        if actual is not None and not identity_matches:
            failures.append('source_identity_outside_nearest_window')
        if nearest_error is not None and abs(nearest_error) > TOLERANCE_M:
            failures.append('nearest_source_height_error')
        if declared_error is not None and abs(declared_error) > TOLERANCE_M:
            failures.append('matched_source_height_error')
        rows.append(dict(control_index=original['control_index'], source_local_m=point,
            original_height_m=original['original_height_m'], original_sample_group=original['original_sample_group'],
            ray_start_local_m=original['ray_start_local_m'], ray_end_local_m=original['ray_end_local_m'],
            expected_nearest_hit=nearest, allowed_source_hits=allowed,
            actual_hit=actual, matched_declared_source_hit=declared_hit,
            residual_to_original_component_m=actual['height_m'] - point[2] if actual else None,
            residual_to_nearest_source_m=nearest_error, residual_to_matched_source_m=declared_error,
            exact_nearest_identity_match=declared_hit == nearest if declared_hit else False,
            source_identity_within_window=identity_matches, failures=failures,
            transfer_matches=not failures))
    # A file revision during the traces invalidates the comparison.
    for relative, digest in state['files'].items():
        require(sha256(ROOT / relative) == digest, 'Input changed during traces: ' + relative)
    failures = Counter(reason for row in rows for reason in row['failures'])
    max_error = lambda key: max((abs(row[key]) for row in rows if row[key] is not None), default=None)
    summary = dict(controls=len(rows), source_hits=sum(row['expected_nearest_hit'] is not None for row in rows),
        unreal_hits=sum(row['actual_hit'] is not None for row in rows),
        exact_nearest_identity_matches=sum(row['exact_nearest_identity_match'] for row in rows),
        near_coincident_identity_matches=sum(row['source_identity_within_window'] and not row['exact_nearest_identity_match'] for row in rows),
        matching_controls=sum(row['transfer_matches'] for row in rows),
        failed_control_indices=[row['control_index'] for row in rows if not row['transfer_matches']],
        failure_counts=dict(failures), maximum_nearest_source_error_m=max_error('residual_to_nearest_source_m'),
        maximum_matched_source_error_m=max_error('residual_to_matched_source_m'),
        maximum_original_component_residual_m=max_error('residual_to_original_component_m'),
        tolerance_m=TOLERANCE_M, persisted_collision_actors=len(state['placed']),
        current_collision_actors=len(live_audit), transfer_pass=all(row['transfer_matches'] for row in rows),
        elapsed_seconds=time.perf_counter() - started)
    record = dict(schema_version=1, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='Fixed numerical source-to-Unreal collision transfer only; not a ride, visual, performance or M1 acceptance',
        inputs=state['files'], comparison_stage_sha256=sha256(Path(__file__)),
        source_oracle_inputs=state['oracle']['inputs'],
        engine=unreal.SystemLibrary.get_engine_version(), world=world.get_path_name(),
        query_contract=dict(source_axes='east,north,up metres', unreal_axes='north,east,up centimetres',
            start_offset_z_m=2, end_offset_z_m=-2, trace_channel='Visibility', trace_complex=True,
            actors_to_ignore=[], ignore_self=True, tolerance_m=TOLERANCE_M,
            identity_window_m=TOLERANCE_M,
            identity_rule='Exact mesh path, mesh name and actor label must identify a source first hit within 1 cm of the nearest source height; no object-specific exceptions',
            height_rule='Both actual-minus-nearest and actual-minus-matched-source must be within the unchanged 1 cm limit',
            near_coincident_scope='The identity window is a declared transfer allowance, not a claim that these surfaces are geometrically identical',
            controls='All 5052 original points, heights, order and component metadata are preserved'),
        original_control_metadata=state['oracle']['original_control_metadata'],
        persisted_collision_audit=dict(evidence=IMPORT_PATH.relative_to(ROOT).as_posix(),
            completed_utc=state['imported']['completed_utc'], actor_count=len(state['placed']),
            policy_counts=dict(Counter(asset['collision'] for asset in state['placed'].values()))),
        current_collision_audit=live_audit, summary=summary, points=rows)
    finite(record, 'result')
    with OUTPUT_PATH.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return dict(summary=summary, evidence=OUTPUT_PATH.relative_to(ROOT).as_posix(), evidence_sha256=sha256(OUTPUT_PATH))
