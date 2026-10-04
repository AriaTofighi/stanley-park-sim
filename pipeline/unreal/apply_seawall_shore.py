"""Versioned visual shore layer; no original mesh, transform or collision edit."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import unreal

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_SeawallShore"
PREFIX = "/Game/StanleyPark/Seawall/Shore"
ASSETS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MESHES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MAT = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def node(material, cls, **properties):
    value = MAT.create_material_expression(material, cls)
    if value is None: raise RuntimeError('Cannot create ' + cls.__name__)
    for key, item in properties.items(): value.set_editor_property(key, item)
    return value


def output(material, expression, prop):
    if not MAT.connect_material_property(expression, '', prop):
        raise RuntimeError('Cannot connect material output')


def custom(material, code, inputs, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    slots = []
    for name in inputs:
        slot = unreal.CustomInput()
        slot.set_editor_property('input_name', name)
        slots.append(slot)
    value = node(material, unreal.MaterialExpressionCustom, code=code,
                 inputs=slots, output_type=output_type)
    for name, source in inputs.items():
        if not MAT.connect_material_expressions(source, '', value, name):
            raise RuntimeError('Cannot connect shore material input ' + name)
    return value


def invariant(actor):
    c = actor.static_mesh_component
    t = actor.get_actor_transform()
    return dict(mesh=c.static_mesh.get_path_name(),
        location=[t.translation.x,t.translation.y,t.translation.z],
        rotation=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],
        scale=[t.scale3d.x,t.scale3d.y,t.scale3d.z],
        collision=str(c.get_collision_enabled()), profile=str(c.get_collision_profile_name()))


def apply():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if editor.get_game_world() is not None or world.get_path_name() != '/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':
        raise RuntimeError('Open the separate seawall editor map and stop Play')
    pointer = json.loads((ROOT/'exports/seawall-shore/latest.json').read_text())
    manifest_path = ROOT/pointer['manifest']
    if sha(manifest_path) != pointer['sha256']: raise RuntimeError('Shore manifest changed')
    source = json.loads(manifest_path.read_text())
    for name, expected in source['input_hashes'].items():
        if sha(ROOT/name) != expected: raise RuntimeError('Shore source changed: ' + name)
    for item in source['assets'] + source['textures']:
        if sha(ROOT/item.get('fbx', item.get('path'))) != item['sha256']:
            raise RuntimeError('Shore asset changed: ' + item['name'])
    root = source['asset_root']
    if not root.startswith(PREFIX + '/v_'): raise RuntimeError('Unexpected shore asset root')
    fingerprint = hashlib.sha256(manifest_path.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), success=False,
        source_manifest=pointer['manifest'], source_sha256=pointer['sha256'], script_sha256=sha(Path(__file__)),
        fingerprint=fingerprint, textures=[], materials=[], meshes=[], terrain=[], instances=0,
        application_test=False, visual_acceptance=False)
    report = ROOT/'evidence'/('seawall-shore-'+fingerprint[:12]+'.json')
    report.write_text(json.dumps(record,indent=2))
    textures = {}
    for item in source['textures']:
        path = root+'/Textures/'+item['name']
        texture = ASSETS.load_asset(path)
        if texture is None:
            task = unreal.AssetImportTask()
            task.filename = str(ROOT/item['path'])
            task.destination_path = root+'/Textures'
            task.destination_name = item['name']
            task.automated = True
            task.replace_existing = False
            task.save = False
            TOOLS.import_asset_tasks([task])
            texture = ASSETS.load_asset(path)
            if not isinstance(texture, unreal.Texture2D): raise RuntimeError('Texture import failed: '+path)
            texture.set_editor_property('srgb', False)
            if 'Normal' in item['name']:
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
            ASSETS.set_metadata_tag(texture,'SP_ShoreSource',item['sha256'])
            ASSETS.save_loaded_asset(texture)
        if ASSETS.get_metadata_tag(texture,'SP_ShoreSource') != item['sha256']:
            raise RuntimeError('Existing texture has a different source')
        textures[item['name']] = texture
        record['textures'].append(path)

    def material(kind):
        name = 'M_Seawall'+kind+'_'+fingerprint[:12]
        path = root+'/Materials/'+name
        result = ASSETS.load_asset(path)
        if result:
            if ASSETS.get_metadata_tag(result,'SP_ShoreMaterial') != fingerprint:
                raise RuntimeError('Incomplete existing shore material')
            return result
        result = TOOLS.create_asset(name,root+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
        result.set_editor_property('tangent_space_normal',False)
        MAT.set_base_material_usage(result,unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES,True)
        p = node(result,unreal.MaterialExpressionWorldPosition)
        n = node(result,unreal.MaterialExpressionVertexNormalWS)
        c = node(result,unreal.MaterialExpressionVertexColor)
        a = node(result,unreal.MaterialExpressionTextureObject,texture=textures['T_SeawallMineral'],
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        b = node(result,unreal.MaterialExpressionTextureObject,texture=textures['T_SeawallMineralNormal'],
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        common = '''float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,0.0001);
float3 q=P/150.0;
float3 x=Texture2DSample(A,ASampler,q.yz).rgb;
float3 y=Texture2DSample(A,ASampler,q.xz).rgb;
float3 z=Texture2DSample(A,ASampler,q.xy).rgb;
float3 grain=x*w.x+y*w.y+z*w.z;
'''
        if kind == 'Terrain':
            code = common + '''float steep=smoothstep(0.18,0.62,1.0-abs(N.z));
float shore=1.0-smoothstep(170.0,420.0,P.z);
float grass=saturate((C.g-C.r)*9.0);
float3 land=lerp(float3(.15,.145,.12),float3(.09,.13,.055),grass);
float3 base=lerp(land,float3(.26,.25,.215),shore);
base=lerp(base,float3(.20,.215,.205),steep);
float wet=1.0-smoothstep(30.0,135.0,P.z);
return base*(grain*.85+.45)*lerp(1.0,.56,wet);'''
        else:
            code = common + '''float wet=1.0-smoothstep(30.0,135.0,P.z);
return float3(.25,.265,.245)*(grain*.9+.38)*lerp(1.0,.54,wet);'''
        base = custom(result,code,{'P':p,'N':n,'C':c,'A':a})
        output(result,base,unreal.MaterialProperty.MP_BASE_COLOR)
        normal = custom(result,'''float3 w=pow(abs(N),4); w/=max(w.x+w.y+w.z,.0001);
float3 q=P/150.0;
float3 x=Texture2DSample(B,BSampler,q.yz).rgb*2.0-1.0;
float3 y=Texture2DSample(B,BSampler,q.xz).rgb*2.0-1.0;
float3 z=Texture2DSample(B,BSampler,q.xy).rgb*2.0-1.0;
float3 perturb=float3(0,x.x,x.y)*w.x+float3(y.x,0,y.y)*w.y+float3(z.x,z.y,0)*w.z;
return normalize(N+perturb*.48);''',{'P':p,'N':n,'B':b})
        output(result,normal,unreal.MaterialProperty.MP_NORMAL)
        rough = custom(result,'return lerp(.55,.91,smoothstep(30.0,135.0,P.z));',{'P':p},unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        output(result,rough,unreal.MaterialProperty.MP_ROUGHNESS)
        diagnostics = MAT.recompile_material(result)
        if diagnostics is None: raise RuntimeError('No shore shader compilation diagnostics')
        errors = [str(v) for v in diagnostics]
        if errors: raise RuntimeError('Shore shader errors: '+str(errors))
        ASSETS.set_metadata_tag(result,'SP_ShoreMaterial',fingerprint)
        if not ASSETS.save_loaded_asset(result): raise RuntimeError('Cannot save shore material')
        record['materials'].append(dict(path=path,compile_errors=errors))
        return result

    terrain_material, rock_material = material('Terrain'), material('Rock')
    targets = [a for a in ACTORS.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor)
               and a.get_actor_label().startswith('SM_Terrain_')]
    if len(targets) != 50: raise RuntimeError('Expected 50 measured terrain tiles')
    baseline_path = ROOT/'evidence/seawall-shore-baseline.json'
    if not baseline_path.exists():
        baseline_path.write_text(json.dumps(dict(map=world.get_path_name(),terrain=[dict(
            actor=a.get_path_name(),invariant=invariant(a),overrides=[m.get_path_name() if m else None
            for m in a.static_mesh_component.get_editor_property('override_materials')]) for a in targets]),indent=2))
    before = {a.get_path_name():invariant(a) for a in targets}
    for actor in targets:
        actor.modify()
        actor.static_mesh_component.modify()
        actor.static_mesh_component.set_material(0,terrain_material)
        record['terrain'].append(actor.get_path_name())

    unreal.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
    foliage, meshes = {}, {}
    for item in source['assets']:
        path = root+'/Meshes/'+item['name']
        mesh = ASSETS.load_asset(path)
        if mesh is None:
            options = unreal.FbxImportUI()
            for key,value in dict(import_mesh=True,import_as_skeletal=False,import_materials=False,
                import_textures=False,automated_import_should_detect_type=False,
                mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items(): options.set_editor_property(key,value)
            for key,value in dict(combine_meshes=True,convert_scene=False,convert_scene_unit=False,
                force_front_x_axis=False,generate_lightmap_u_vs=False,auto_generate_collision=False,
                transform_vertex_to_absolute=True,build_nanite=False,
                normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS).items():
                options.static_mesh_import_data.set_editor_property(key,value)
            task = unreal.AssetImportTask()
            for key,value in dict(filename=str(ROOT/item['fbx']),destination_path=root+'/Meshes',
                destination_name=item['name'],automated=True,replace_existing=False,save=False,
                factory=unreal.FbxFactory(),options=options).items(): task.set_editor_property(key,value)
            TOOLS.import_asset_tasks([task])
            mesh = ASSETS.load_asset(path)
            if not isinstance(mesh,unreal.StaticMesh): raise RuntimeError('Rock import failed')
            MESHES.remove_collisions(mesh)
            ASSETS.set_metadata_tag(mesh,'SP_ShoreSource',item['sha256'])
        if ASSETS.get_metadata_tag(mesh,'SP_ShoreSource') != item['sha256']: raise RuntimeError('Rock source differs')
        bounds = mesh.get_bounding_box()
        actual = [bounds.min.x,bounds.min.y,bounds.min.z,bounds.max.x,bounds.max.y,bounds.max.z]
        error = max(abs(a-b) for a,b in zip(actual,item['bounds_min_cm']+item['bounds_max_cm']))
        if error > .25: raise RuntimeError('Rock axis or scale mismatch')
        mesh.set_material(0,rock_material)
        ASSETS.save_loaded_asset(mesh)
        meshes[item['name']] = mesh
        ft_path = root+'/Foliage/FT_'+item['name']
        ft = ASSETS.load_asset(ft_path)
        if ft is None:
            ft = TOOLS.create_asset('FT_'+item['name'],root+'/Foliage',
                unreal.FoliageType_InstancedStaticMesh,unreal.FoliageType_InstancedStaticMeshFactory())
            ft.set_editor_property('mesh',mesh)
            ft.set_editor_property('enable_density_scaling',False)
            ft.set_editor_property('enable_cull_distance_scaling',False)
            ft.set_editor_property('cull_distance',unreal.Int32Interval(14000,18000))
            ft.set_editor_property('cast_shadow',False)
            body=ft.get_editor_property('body_instance')
            body.set_editor_property('collision_enabled',unreal.CollisionEnabled.NO_COLLISION)
            ft.set_editor_property('body_instance',body)
            ASSETS.set_metadata_tag(ft,'SP_Owner',OWNER)
            ASSETS.save_loaded_asset(ft)
        if ASSETS.get_metadata_tag(ft,'SP_Owner') != OWNER: raise RuntimeError('Rock foliage ownership differs')
        foliage[item['name']] = ft
        record['meshes'].append(dict(path=path,bounds_error_cm=error,triangles=item['triangles']))
    owned = []
    for path in ASSETS.list_assets(PREFIX,recursive=True,include_folder=False):
        if '/Foliage/' not in path: continue
        ft = ASSETS.load_asset(path)
        if isinstance(ft,unreal.FoliageType_InstancedStaticMesh) and ASSETS.get_metadata_tag(ft,'SP_Owner') == OWNER:
            owned.append(ft)
    # Each version's input manifest preserves all prior placements for restoration.
    for ft in owned: unreal.InstancedFoliageActor.remove_all_instances(world,ft)
    grouped = {name:[] for name in meshes}
    for row in source['instances']:
        x,y,z = row['position_local_m']
        sx,sy,sz = row['scale']
        grouped[row['mesh']].append(unreal.Transform(location=unreal.Vector(y*100,x*100,z*100),
            rotation=unreal.Rotator(pitch=0,yaw=-row['yaw_degrees'],roll=0),scale=unreal.Vector(sy,sx,sz)))
    for name, transforms in grouped.items():
        if transforms: unreal.InstancedFoliageActor.add_instances(world,foliage[name],transforms)
    expected = {mesh.get_path_name():len(grouped[name]) for name,mesh in meshes.items()}
    actual = {path:0 for path in expected}
    for actor in ACTORS.get_all_level_actors():
        if not isinstance(actor,unreal.InstancedFoliageActor): continue
        for component in actor.get_components_by_class(unreal.FoliageInstancedStaticMeshComponent):
            mesh=component.get_editor_property('static_mesh')
            if mesh and mesh.get_path_name() in actual: actual[mesh.get_path_name()]+=component.get_instance_count()
    if actual != expected: raise RuntimeError('Shore foliage count mismatch')
    after = {a.get_path_name():invariant(a) for a in targets}
    if before != after: raise RuntimeError('Terrain mesh, transform or collision changed')
    if not ASSETS.save_loaded_assets([terrain_material,rock_material]) or not LEVELS.save_current_level():
        raise RuntimeError('Cannot save shore layer')
    record.update(success=True,instances=sum(actual.values()),instance_counts=actual,
        terrain_invariants=after,terrain_geometry_collision_unchanged=True)
    report.write_text(json.dumps(record,indent=2))
    return record


result = apply()
