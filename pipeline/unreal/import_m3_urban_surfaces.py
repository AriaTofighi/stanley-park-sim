"""Apply frozen urban finishes to actors; never modify shared M1 mesh assets."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import runpy
import unreal

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'pipeline/unreal/import_m3_landmarks.py'
H = runpy.run_path(str(HELPER), run_name='m3_urban_material_helpers')
ASSETS, ACTORS, LEVELS, TOOLS, MAT = (H[k] for k in ('ASSETS', 'ACTORS', 'LEVELS', 'TOOLS', 'MAT'))
sha, invariant, node, output, custom = (H[k] for k in ('sha', 'invariant', 'node', 'output', 'custom'))


def shader(kind, settings, roughness):
    # RGB is base color, A is roughness. A single evaluation feeds both outputs.
    prefix = f'''float d=distance(P,Camera);
float fade=1-smoothstep({settings['detail_fade_start_m']*100:.8f},{settings['detail_fade_end_m']*100:.8f},d);
float3 base=C.rgb; float rough={roughness:.8f};
if(d>{settings['detail_fade_end_m']*100:.8f}) return float4(base,rough);
float vertical=1-smoothstep(.18,.45,abs(N.z));
float u=abs(N.x)>abs(N.y)?P.y:P.x;
'''
    if kind == 'concrete':
        return prefix + '''float2 q=float2(u/240.0,P.z/120.0);
float2 fw=max(fwidth(q),.0001);
float2 edge=min(frac(q),1-frac(q));
float2 joint=1-smoothstep(float2(.003,.003),float2(.003,.003)+fw,edge);
float seams=max(joint.x,joint.y)*saturate(1-max(fw.x,fw.y)*2);
float grain=sin(P.x*.23+P.y*.31+P.z*.27)*sin(P.x*.39-P.y*.17+P.z*.19);
grain*=saturate(1-length(fwidth(P))*.13);
float stain=sin(u*.005+sin(P.z*.002))*sin(P.z*.0013+u*.0007);
float shade=1+grain*.035+stain*.055-seams*vertical*.15;
return float4(base*lerp(1,shade,fade),saturate(rough+grain*.025*fade));'''
    glass = kind == 'glass'
    light = kind == 'light'
    width = .065 if glass else (.16 if light else .21)
    bottom = .07 if glass else .22
    top = .90 if glass else .83
    return prefix + f'''float2 q=float2(u/{settings['estimated_window_bay_m']*100:.8f},P.z/{settings['estimated_floor_spacing_m']*100:.8f});
float2 fw=max(fwidth(q),.0001);
float2 f=frac(q); float2 cell=floor(q);
float pixels=saturate(1-max(fw.x,fw.y)*2);
float wx=smoothstep({width:.8f},{width:.8f}+fw.x,f.x)*(1-smoothstep({1-width:.8f}-fw.x,{1-width:.8f},f.x));
float wz=smoothstep({bottom:.8f},{bottom:.8f}+fw.y,f.y)*(1-smoothstep({top:.8f}-fw.y,{top:.8f},f.y));
float window=wx*wz;
float hash=frac(sin(dot(cell,float2(12.9898,78.233)))*43758.5453);
float variation=.90+hash*.20;
float3 glazing=base*float3(.49,.64,.70)*variation;
float3 wall=base*{1.14 if glass else 1.03:.8f};
float band=1-smoothstep(.012,.012+fw.y,min(f.y,1-f.y));
float3 detailed=lerp(wall,glazing,window)*(1-band*.13);
float amount=vertical*fade*pixels;
return float4(lerp(base,detailed,amount),lerp(rough,lerp(rough,.24,window),amount));'''


def apply():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name() != '/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':
        raise RuntimeError('Open the Seawall map and stop Play')
    pointer = json.loads((ROOT / 'exports/m3-urban-surfaces/latest.json').read_text())
    path = ROOT / pointer['manifest']
    if sha(path) != pointer['sha256']:
        raise RuntimeError('Urban manifest changed')
    source = json.loads(path.read_text())
    for name, expected in source['input_hashes'].items():
        if sha(ROOT / name) != expected:
            raise RuntimeError('Urban source changed: ' + name)
    root = source['asset_root']
    if not root.startswith('/Game/StanleyPark/Seawall/UrbanSurfaces/v_'):
        raise RuntimeError('Unexpected urban asset root')
    fingerprint = hashlib.sha256(path.read_bytes()+Path(__file__).read_bytes()+HELPER.read_bytes()).hexdigest()
    all_static = [a for a in ACTORS.get_all_level_actors()
        if isinstance(a, unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    actors = {}
    for actor in all_static:
        actors.setdefault(actor.get_actor_label(), []).append(actor)
    selected = []
    for row in source['targets']:
        matches = actors.get(row['name'], [])
        if len(matches) != 1:
            raise RuntimeError('Urban actor missing or ambiguous: ' + row['name'])
        actor = matches[0]
        component = actor.static_mesh_component
        if component.static_mesh.get_path_name().split('.')[0] != row['asset_path']:
            raise RuntimeError('Urban mesh differs: ' + row['name'])
        for slot in row['slots']:
            if slot['slot'] >= component.get_num_materials():
                raise RuntimeError('Urban material slot missing: ' + row['name'])
        selected.append((row, actor))
    before = {a.get_path_name(): invariant(a) for a in all_static}
    baseline = ROOT / 'evidence/m3-urban-material-baseline.json'
    if not baseline.exists():
        baseline.write_text(json.dumps(dict(map=world.get_path_name(), actors=[dict(
            actor=a.get_path_name(), label=a.get_actor_label(), invariant=invariant(a),
            overrides=[m.get_path_name() if m else None for m in a.static_mesh_component.get_editor_property('override_materials')])
            for _, a in selected]), indent=2))
    report = ROOT / 'evidence' / ('m3-urban-import-' + fingerprint[:12] + '.json')
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), success=False,
        manifest=pointer['manifest'], manifest_sha256=pointer['sha256'],
        script_sha256=sha(Path(__file__)), helper_sha256=sha(HELPER), materials=[], instances=[],
        actors=[], application_test=False, visual_acceptance=False, source_limits=source['settings']['source_limits'])
    report.write_text(json.dumps(record, indent=2))
    parents, cache = {}, {}

    def material(slot):
        spec = slot['profile']
        parent_key = json.dumps(dict(profile=spec, two_sided=slot['two_sided']), sort_keys=True)
        parent_id = hashlib.sha256(parent_key.encode()).hexdigest()[:8]
        if parent_key not in parents:
            name = 'M_M3Urban_' + spec['kind'] + '_' + parent_id + '_' + fingerprint[:12]
            parent = ASSETS.load_asset(root + '/Materials/' + name)
            if parent:
                if ASSETS.get_metadata_tag(parent, 'SP_M3UrbanMaterial') != fingerprint:
                    raise RuntimeError('Incomplete existing urban material')
            else:
                parent = TOOLS.create_asset(name, root + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
                parent.set_editor_property('two_sided', slot['two_sided'])
                p = node(parent, unreal.MaterialExpressionWorldPosition)
                n = node(parent, unreal.MaterialExpressionVertexNormalWS)
                camera = node(parent, unreal.MaterialExpressionCameraPositionWS)
                c = node(parent, unreal.MaterialExpressionVectorParameter, parameter_name='SourceColor', default_value=unreal.LinearColor(1,1,1,1))
                detail = custom(parent, shader(spec['kind'], source['settings'], spec['roughness']),
                    {'P':p, 'N':n, 'Camera':camera, 'C':c}, unreal.CustomMaterialOutputType.CMOT_FLOAT4)
                rgb = node(parent, unreal.MaterialExpressionComponentMask, r=True, g=True, b=True, a=False)
                rough = node(parent, unreal.MaterialExpressionComponentMask, r=False, g=False, b=False, a=True)
                for mask in (rgb, rough):
                    if not MAT.connect_material_expressions(detail, '', mask, ''):
                        raise RuntimeError('Cannot connect urban shader mask')
                output(parent, rgb, unreal.MaterialProperty.MP_BASE_COLOR)
                output(parent, rough, unreal.MaterialProperty.MP_ROUGHNESS)
                diagnostics = MAT.recompile_material(parent)
                if diagnostics is None or len(diagnostics):
                    raise RuntimeError('Urban shader diagnostics: ' + str(diagnostics))
                ASSETS.set_metadata_tag(parent, 'SP_M3UrbanMaterial', fingerprint)
                if not ASSETS.save_loaded_asset(parent):
                    raise RuntimeError('Cannot save urban material')
            parents[parent_key] = parent
            record['materials'].append(dict(path=parent.get_path_name(), profile=spec, compile_errors=[]))
        parent = parents[parent_key]
        key = json.dumps(dict(parent=parent_key, color=slot['color']), sort_keys=True)
        if key not in cache:
            name = 'MI_M3Urban_' + hashlib.sha256((key+fingerprint).encode()).hexdigest()[:16]
            instance = ASSETS.load_asset(root + '/Materials/' + name)
            if instance:
                if ASSETS.get_metadata_tag(instance, 'SP_M3UrbanMaterial') != fingerprint:
                    raise RuntimeError('Incomplete urban material instance')
            else:
                instance = TOOLS.create_asset(name, root + '/Materials', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
                MAT.set_material_instance_parent(instance, parent)
                MAT.set_material_instance_vector_parameter_value(instance, 'SourceColor', unreal.LinearColor(*slot['color'], 1))
            actual = MAT.get_material_instance_vector_parameter_value(instance, 'SourceColor')
            error = max(abs(a-b) for a,b in zip([actual.r,actual.g,actual.b,actual.a], [*slot['color'],1]))
            if error > 1e-6 or instance.get_editor_property('parent') != parent:
                raise RuntimeError('Urban instance color or parent readback differs')
            ASSETS.set_metadata_tag(instance, 'SP_M3UrbanMaterial', fingerprint)
            if not ASSETS.save_loaded_asset(instance):
                raise RuntimeError('Cannot save urban material instance')
            cache[key] = instance
            record['instances'].append(dict(path=instance.get_path_name(), color_error=error))
        return cache[key]

    # Build and compile all shared materials before any actor is changed.
    for row, _ in selected:
        for slot in row['slots']:
            material(slot)
    for row, actor in selected:
        actor.modify()
        actor.static_mesh_component.modify()
        for slot in row['slots']:
            actor.static_mesh_component.set_material(slot['slot'], material(slot))
        record['actors'].append(dict(label=row['name'], slots=len(row['slots'])))
    after = {a.get_path_name(): invariant(a) for a in all_static}
    if before != after:
        raise RuntimeError('Static mesh geometry, transform or collision changed')
    if not LEVELS.save_current_level():
        raise RuntimeError('Cannot save urban material layer')
    record.update(success=True, geometry_collision_unchanged=True, static_actor_count=len(before),
        target_count=len(selected), parent_material_count=len(parents), instance_count=len(cache),
        completed_utc=datetime.now(timezone.utc).isoformat())
    report.write_text(json.dumps(record, indent=2))
    (ROOT / 'evidence/m3-urban-import-latest.json').write_text(json.dumps(dict(
        report=report.relative_to(ROOT).as_posix(), sha256=sha(report)), indent=2))
    return record


if __name__ in {'__main__', '<run_path>'}:
    result = apply()
