"""Read-only diagnosis of the v26 Girl in a Wetsuit visibility discrepancy.

Load with runpy, then call inspect(). No scene, material or console changes.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'evidence/unreal-girl-visibility-v26.json'


def serial(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if hasattr(value, 'get_path_name'):
        return value.get_path_name()
    if hasattr(value, 'to_dict'):
        return serial(value.to_dict())
    return str(value)


def read(call):
    try:
        return dict(value=serial(call()))
    except Exception as exc:
        return dict(unavailable=str(exc))


def properties(obj, names):
    return {name: read(lambda name=name: obj.get_editor_property(name)) for name in names}


def inspect():
    import unreal

    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name() != '/Game/Maps/StanleyPark.StanleyPark':
        raise RuntimeError('This read-only inspector requires the Stanley Park editor world with play stopped')
    export_path = ROOT / 'manifests/blender-export.json'
    manifest = json.loads(export_path.read_text())
    imports = json.loads((ROOT / 'evidence/unreal-import.json').read_text())
    export_hash = hashlib.sha256(export_path.read_bytes()).hexdigest()
    if not imports.get('success') or imports.get('export_manifest_sha256') != export_hash:
        raise RuntimeError('A successful import of the current export is required')
    source = {a['name']: a for a in manifest['assets']}
    targets = {name for name in source if name.startswith('SM_Wetsuit_')}
    # Read nearby source water as well: it must not conceal an above-water form.
    boulder = source['SM_Wetsuit_IntertidalBoulder']
    centre = boulder['position_cm']
    water = {name for name, a in source.items() if a['place_in_level'] and name.startswith('SM_Water')
             and all(a['position_cm'][axis] + a['bounds_min_cm'][axis] <= centre[axis]
                     <= a['position_cm'][axis] + a['bounds_max_cm'][axis] for axis in (0, 1))}
    if len(water) > 20:
        raise RuntimeError('Unexpectedly broad nearby-water set')
    wanted = targets | water
    imported_rows = {a['name']: a for a in imports['assets']}
    persisted = {a['name']: a for a in imports['saved_actor_collision_checks']}
    camera = read(lambda: editor.get_level_viewport_camera_info())
    rows = []
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in actor_subsystem.get_all_level_actors():
        name = actor.get_actor_label()
        if name not in wanted:
            continue
        component = actor.static_mesh_component if isinstance(actor, unreal.StaticMeshActor) else None
        a = source[name]
        row = dict(name=name, role='Girl assembly' if name in targets else 'Water whose source XY bounds contain the boulder',
                   actor_path=actor.get_path_name(), actor_class=actor.get_class().get_name(),
                   tags=[str(tag) for tag in actor.tags],
                   expected_tags=['SP_Generated', 'SP_Source_' + hashlib.sha256(a['source_id'].encode('utf8')).hexdigest()],
                   source_export=a, import_record=imported_rows.get(name), persisted_collision=persisted.get(name),
                   expected_world_bounds_cm=dict(minimum=[a['position_cm'][i]+a['bounds_min_cm'][i] for i in range(3)],
                                                 maximum=[a['position_cm'][i]+a['bounds_max_cm'][i] for i in range(3)]),
                   actor_transform=read(lambda: actor.get_actor_transform()),
                   actor_location=read(lambda: actor.get_actor_location()),
                   actor_rotation=read(lambda: actor.get_actor_rotation()),
                   actor_scale=read(lambda: actor.get_actor_scale3d()),
                   actor_bounds_all_components=read(lambda: actor.get_actor_bounds(False)),
                   actor_hidden=read(lambda: actor.is_hidden()),
                   actor_temporarily_hidden_in_editor=read(lambda: actor.is_temporarily_hidden_in_editor()),
                   actor_properties=properties(actor, ['hidden', 'is_editor_only_actor', 'is_spatially_loaded',
                       'hidden_editor_views', 'initial_life_span', 'enable_auto_lod_generation']),
                   owner=read(lambda: actor.get_owner()))
        if component is not None:
            row['component_path'] = component.get_path_name()
            row['component_transform'] = read(lambda: component.get_world_transform())
            row['component_bounds'] = read(lambda: unreal.SystemLibrary.get_component_bounds(component))
            row['component_visible'] = read(lambda: component.is_visible())
            row['component_properties'] = properties(component, [
                'visible', 'hidden_in_game', 'owner_no_see', 'only_owner_see', 'cast_hidden_shadow',
                'cast_shadow', 'render_in_main_pass', 'render_in_depth_pass', 'use_as_occluder',
                'min_draw_distance', 'ld_max_draw_distance', 'cached_max_draw_distance',
                'never_distance_cull', 'allow_cull_distance_volume', 'bounds_scale',
                'reverse_culling', 'disallow_nanite', 'force_disable_nanite', 'forced_lod_model',
                'min_lod', 'override_min_lod', 'use_attach_parent_bound', 'mobility'])
            mesh = component.get_editor_property('static_mesh')
            row['mesh_path'] = mesh.get_path_name() if mesh else None
            if mesh:
                row['mesh_bounding_box'] = read(lambda: mesh.get_bounding_box())
                row['mesh_properties'] = properties(mesh, ['nanite_settings', 'min_lod', 'lod_for_collision',
                    'support_ray_tracing', 'positive_bounds_extension', 'negative_bounds_extension',
                    'extended_bounds', 'never_stream', 'num_streamed_lods', 'light_map_resolution'])
                row['nanite_enabled'] = read(lambda: mesh.get_editor_property('nanite_settings').get_editor_property('enabled'))
                row['mesh_lod_count'] = read(lambda: unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).get_lod_count(mesh))
                row['materials'] = []
                for index in range(component.get_num_materials()):
                    material = component.get_material(index)
                    row['materials'].append(dict(index=index, material_path=material.get_path_name() if material else None,
                        properties=properties(material, ['blend_mode', 'two_sided', 'shading_model',
                            'opacity_mask_clip_value', 'disable_depth_test', 'dithered_lod_transition',
                            'is_masked', 'domain']) if material else {}))
        rows.append(row)
    found = [row['name'] for row in rows]
    record = dict(schema_version=1, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='Read-only visibility diagnosis. No scene, console, import, geometry or material changes. No acceptance.',
        world=world.get_path_name(), engine=unreal.SystemLibrary.get_engine_version(),
        export_manifest_sha256=export_hash,
        import_evidence_sha256=hashlib.sha256((ROOT / 'evidence/unreal-import.json').read_bytes()).hexdigest(),
        inspector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        current_camera=camera,
        engine_near_clip=read(lambda: unreal.get_default_object(unreal.Engine).get_editor_property('near_clip_plane')),
        target_actor_count=len(targets), nearby_water_names=sorted(water),
        missing_actor_names=sorted(wanted-set(found)), duplicate_actor_names=sorted({name for name in found if found.count(name)>1}),
        rows=rows,
        property_limit='Unavailable properties are recorded as unavailable; no default value is assumed')
    with OUTPUT.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return dict(evidence=OUTPUT.relative_to(ROOT).as_posix(), actors=len(rows),
                missing=record['missing_actor_names'], duplicates=record['duplicate_actor_names'],
                engine_near_clip=record['engine_near_clip'])
