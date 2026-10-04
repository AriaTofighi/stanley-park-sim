"""Run with Unreal's PythonScript commandlet or the project editor.

Creates assets and a map. It does not run or validate the bicycle application.
Every imported mesh must meet the declared centimetre bounds before placement.
"""
from pathlib import Path
import hashlib
import json
import traceback
import runpy
from datetime import datetime, timezone
import unreal

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "manifests/blender-export.json").read_text(encoding="utf-8"))
EVIDENCE = ROOT / "evidence/unreal-import.json"
record = {"engine": unreal.SystemLibrary.get_engine_version(), "assets": [], "success": False,
          "export_manifest_sha256": hashlib.sha256((ROOT / "manifests/blender-export.json").read_bytes()).hexdigest(),
          "started_utc": datetime.now(timezone.utc).isoformat()}
# A process-level crash must never leave a previous success as this run's result.
EVIDENCE.write_text(json.dumps(record, indent=2), encoding="utf-8")
tools = unreal.AssetToolsHelpers.get_asset_tools()
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
materials = {}


def material(name, color, use_vertex, two_sided=False):
    if name in materials:
        return materials[name]
    spec = json.dumps(dict(version=3, name=name, color=color, vertex=use_vertex, two_sided=two_sided,
                           roughness=.35 if "Water" in name else .8), sort_keys=True)
    fingerprint = hashlib.sha256(spec.encode()).hexdigest()
    asset_name = f"{name}_{fingerprint[:10]}"
    path = f"/Game/StanleyPark/Materials/{asset_name}"
    mat = assets.load_asset(path) if assets.does_asset_exist(path) else None
    if mat is not None:
        if assets.get_metadata_tag(mat, "SP_MaterialSpec") != fingerprint:
            raise RuntimeError(f"Material exists without a complete matching spec: {path}")
        materials[name] = mat
        return mat
    # UE 5.8 asserted when deleting rooted material expressions during a live MCP
    # invocation. Create a versioned graph once and reuse it. Never erase a graph
    # from a previously imported or hand-authored material.
    mat = tools.create_asset(asset_name, "/Game/StanleyPark/Materials", unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError(f"Cannot create material: {path}")
    if use_vertex:
        expression = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionVertexColor)
        connected = unreal.MaterialEditingLibrary.connect_material_property(expression, "", unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        expression = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
        expression.set_editor_property("constant", unreal.LinearColor(*color))
        connected = unreal.MaterialEditingLibrary.connect_material_property(expression, "", unreal.MaterialProperty.MP_BASE_COLOR)
    if not connected:
        raise RuntimeError(f"Base-color connection failed: {name}")
    roughness = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant)
    roughness.set_editor_property("r", 0.8)
    if not unreal.MaterialEditingLibrary.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS):
        raise RuntimeError(f"Roughness connection failed: {name}")
    mat.set_editor_property("two_sided", two_sided)
    if "Water" in name:
        roughness.set_editor_property("r", 0.35)
    unreal.MaterialEditingLibrary.recompile_material(mat)
    assets.set_metadata_tag(mat, "SP_MaterialSpec", fingerprint)
    assets.save_loaded_asset(mat)
    materials[name] = mat
    return mat


def import_mesh(item):
    filename = ROOT / item["fbx"]
    if hashlib.sha256(filename.read_bytes()).hexdigest() != item["sha256"]:
        raise RuntimeError(f"FBX changed after manifest: {filename.name}")
    options = unreal.FbxImportUI()
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_as_skeletal", False)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    options.set_editor_property("automated_import_should_detect_type", False)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    sm_options = options.static_mesh_import_data
    for key, value in {"combine_meshes": True, "convert_scene": False, "convert_scene_unit": False,
                       "force_front_x_axis": False, "generate_lightmap_u_vs": False,
                       "auto_generate_collision": False, "transform_vertex_to_absolute": True,
                       "build_nanite": False}.items():
        sm_options.set_editor_property(key, value)
    sm_options.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    sm_options.set_editor_property("vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(filename))
    task.set_editor_property("destination_path", item["asset_path"].rsplit("/", 1)[0])
    task.set_editor_property("destination_name", item["name"])
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("save", True)
    task.set_editor_property("factory", unreal.FbxFactory())
    task.set_editor_property("options", options)
    tools.import_asset_tasks([task])
    imported_paths=[str(path).split('.')[0] for path in task.get_editor_property('imported_object_paths')]
    if item['asset_path'] not in imported_paths:
        raise RuntimeError(f"Import task did not produce the requested mesh: {item['name']}; {imported_paths}")
    mesh = assets.load_asset(item["asset_path"])
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError(f"No static mesh imported for {item['name']}")
    color_check=None
    if item['vertex_colors']:
        if item.get('vertex_color_space')!='linear' or not item.get('vertex_color_range'):
            raise RuntimeError('Re-export linear vertex colors with the current Blender contract')
        dynamic,outcome=unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
            mesh,unreal.DynamicMesh(),unreal.GeometryScriptCopyMeshFromAssetOptions(),unreal.GeometryScriptMeshReadLOD())
        _,color_list,valid,gaps=unreal.GeometryScript_VertexColors.get_mesh_per_vertex_colors(dynamic)
        values=color_list.convert_color_list_to_array()
        if not valid or not values or gaps:
            raise RuntimeError('Imported vertex colors are incomplete: '+item['name'])
        # The source mesh can retain isolated vertices after Unreal removes a
        # degenerate triangle. GeometryScript fills their unused colors with
        # transparent zero. Compare only vertices used by rendered triangles,
        # matching the Blender export contract. Do not ignore referenced zeros.
        _,triangle_list,_=dynamic.get_all_triangle_indices(True)
        used={getattr(t,k) for t in triangle_list.convert_triangle_list_to_array() for k in ['x','y','z']}
        if not used or min(used)<0 or max(used)>=len(values):
            raise RuntimeError('Imported triangle/color indices are invalid: '+item['name'])
        unused_colors=len(values)-len(used)
        values=[values[i] for i in used]
        actual_colors=dict(minimum=[min(getattr(c,k) for c in values) for k in ['r','g','b']],
                           maximum=[max(getattr(c,k) for c in values) for k in ['r','g','b']])
        error_color=max(abs(actual_colors[key][i]-item['vertex_color_range'][key][i])
                        for key in ['minimum','maximum'] for i in range(3))
        color_check=dict(range=actual_colors,maximum_error=error_color,tolerance=.005,
                         referenced_vertices=len(used),unused_vertex_entries=unused_colors)
        if error_color>.005:
            raise RuntimeError(f"Vertex color transfer failed: {item['name']}; {error_color}")
    box = mesh.get_bounding_box()
    actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
    expected = item["bounds_min_cm"] + item["bounds_max_cm"]
    error = max(abs(a - b) for a, b in zip(actual, expected))
    if error > 1.0:
        raise RuntimeError(f"Scale/axis check failed for {item['name']}: {actual} vs {expected}; {error} cm")
    # FBX omits unused slots and Unreal can preserve old display slot names on
    # reimport. Only the imported source name identifies the intended material.
    source_materials = dict(zip(item["materials"], item["material_colors"]))
    slots = list(mesh.get_editor_property("static_materials"))
    imported_names = [str(slot.get_editor_property("imported_material_slot_name")) for slot in slots]
    if set(imported_names) != set(item["used_materials"]):
        raise RuntimeError(f"Material source slots differ for {item['name']}: {imported_names} vs {item['used_materials']}")
    for index, name in enumerate(imported_names):
        mesh.set_material(index, material(name, source_materials[name], item["vertex_colors"],
                                          item.get("material_two_sided", {}).get(name, "Water" in name)))
    # Refresh the structs after assignment before normalizing their display names.
    slots = list(mesh.get_editor_property("static_materials"))
    for slot, name in zip(slots, imported_names):
        slot.set_editor_property("material_slot_name", unreal.Name(name))
    mesh.set_editor_property("static_materials", slots)
    material_checks = []
    for index, name in enumerate(imported_names):
        expected_material = material(name, source_materials[name], item["vertex_colors"],
                                     item.get("material_two_sided", {}).get(name, "Water" in name))
        if mesh.get_material(index) != expected_material:
            raise RuntimeError(f"Material assignment failed for {item['name']}: {name}")
        material_checks.append(dict(imported_name=name, material=expected_material.get_path_name(),
                                    two_sided=expected_material.get_editor_property("two_sided")))
    body = mesh.get_editor_property("body_setup")
    if body is not None:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
                                if item["collision"] == "complex" else unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
    assets.save_loaded_asset(mesh)
    record["assets"].append({"name": item["name"], "bounds_error_cm": error,
                             "asset_path": item["asset_path"], "vertices_source": item["vertices"],
                             "material_slots_pass": True, "material_slots": material_checks,
                             "vertex_color_check": color_check})
    return mesh


try:
    if hashlib.sha256((ROOT / "manifests/world-origin.json").read_bytes()).hexdigest() != MANIFEST["origin_sha256"]:
        raise RuntimeError("The world origin differs from the export origin.")
    # Explicit legacy FbxFactory plus this flag avoids an implicit Interchange axis policy.
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
    imported = []
    for item in MANIFEST["assets"]:
        imported.append((item, import_mesh(item)))
        if len(imported) % 10 == 0:
            unreal.log(f"SP_IMPORT: {len(imported)}/{len(MANIFEST['assets'])}")
    bell_file = ROOT / "exports/audio/S_Bell.wav"
    if bell_file.exists():
        audio_task = unreal.AssetImportTask()
        audio_task.filename = str(bell_file)
        audio_task.destination_path = "/Game/StanleyPark/Audio"
        audio_task.destination_name = "S_Bell"
        audio_task.automated = True
        audio_task.replace_existing = True
        audio_task.save = True
        tools.import_asset_tasks([audio_task])
    map_path = "/Game/Maps/StanleyPark"
    if assets.does_asset_exist(map_path):
        if not levels.load_level(map_path):
            raise RuntimeError("Cannot open the Stanley Park map for update.")
        # Hand-authored actors stay in place. Only this pipeline's tagged actors update.
        for actor in actors.get_all_level_actors():
            if "SP_Generated" in [str(tag) for tag in actor.tags]:
                actors.destroy_actor(actor)
    elif not levels.new_level(map_path):
        raise RuntimeError("Cannot create the Stanley Park map.")
    for item, mesh in imported:
        if not item["place_in_level"]:
            continue
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*item["position_cm"]))
        # Mark ownership immediately, so a later placement failure is safely
        # recoverable. Source records can exceed Unreal's 1023-character FName
        # limit. Keep the full record in the export manifest and a stable hash
        # here; do not truncate or discard source provenance.
        source_hash = hashlib.sha256(item['source_id'].encode('utf8')).hexdigest()
        actor.tags = ["SP_Generated", "SP_Source_" + source_hash]
        actor.set_actor_label(item["name"])
        component = actor.static_mesh_component
        component.set_static_mesh(mesh)
        component.set_mobility(unreal.ComponentMobility.STATIC)
        # An inherited mesh profile can restore BlockAll when the level reloads.
        # Store an explicit component profile before applying the enabled state.
        component.set_editor_property('use_default_collision', False)
        component.set_collision_profile_name('BlockAll' if item['collision']=='complex' else 'NoCollision')
        component.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS
                                        if item["collision"] == "complex" else unreal.CollisionEnabled.NO_COLLISION)
        name=item['name']
        if name.startswith('SM_Skyline'):
            component.set_editor_property('cast_shadow', False)
        folder='Terrain'
        for prefix,category in [('SM_Route','Routes'),('SM_Pavement','Routes'),('SM_Water','Water'),
            ('SM_Canopy','Vegetation'),('SM_Building','Buildings'),('SM_LionsGate','Landmarks'),
            ('SM_Siwash','Landmarks'),('SM_Brockton','Landmarks'),('SM_Named','Buildings'),
            ('SM_Prospect','Landmarks'),('SM_NineClock','Landmarks'),('SM_Pedestrian','WalkingPaths'),
            ('SM_Underpass','Routes'),('SM_Nav','Navigation'),('SM_YachtPort','Buildings'),
            ('SM_SecondPool','Landmarks'),('SM_HollowTree','Landmarks'),('SM_Cedar','Landmarks'),
            ('SM_PublicSpace','PublicSpaces'),('SM_Skyline','DistantSkyline')]:
            if name.startswith(prefix):folder=category;break
        actor.set_folder_path('StanleyPark/'+folder)
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 10000), unreal.Rotator(pitch=-32, yaw=-30, roll=0))
    sun.set_actor_label("SP_Sun_FixedAfternoon")
    sun.tags = ["SP_Generated"]
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property("intensity", 5.0)
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 10000))
    sky.tags = ["SP_Generated"]
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    # A fixed neutral fill makes shadowed geometry readable in the M1 blockout.
    # Physically calibrated daylight belongs to the representative slice.
    sky.light_component.set_editor_property("real_time_capture", False)
    sky.light_component.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    cube=assets.load_asset('/Engine/EngineResources/GrayLightTextureCube')
    if not isinstance(cube,unreal.TextureCube):raise RuntimeError('Inspection sky cube is unavailable')
    sky.light_component.set_editor_property('cubemap',cube)
    sky.light_component.set_editor_property("intensity", 1.0)
    atmosphere = actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    atmosphere.tags = ["SP_Generated"]
    fog = actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
    fog.tags = ["SP_Generated"]
    fog.component.set_editor_property("fog_density", 0.008)
    world_data = json.loads((ROOT / "unreal/Content/WorldData/world.json").read_text(encoding="utf-8"))
    spawn = list(world_data["spawn"])
    spawn[2] += 80
    start = actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*spawn), unreal.Rotator(pitch=0, yaw=world_data["spawn_yaw"], roll=0))
    start.tags = ["SP_Generated"]
    runpy.run_path(str(ROOT / "pipeline/unreal/adjust_inspection_lighting.py"))
    # Keep the editor camera near the park. Distant regional terrain is not a framing target.
    unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(unreal.Vector(-280000, 160000, 240000), unreal.Rotator(pitch=-39, yaw=-31, roll=0))
    levels.save_current_level()
    assets.save_directory("/Game/StanleyPark", only_if_is_dirty=True, recursive=True)
    # Read the serialized level back. An in-memory setter alone is not proof of
    # the collision state that PIE and the packaged application will load.
    if not levels.load_level(map_path):
        raise RuntimeError('Cannot reload the saved map for collision verification')
    expected_actors = {item['name']: item for item,_ in imported if item['place_in_level']}
    collision_checks = []
    for actor in actors.get_all_level_actors():
        if 'SP_Generated' not in [str(tag) for tag in actor.tags] or not isinstance(actor,unreal.StaticMeshActor):
            continue
        name = actor.get_actor_label()
        if name not in expected_actors:
            raise RuntimeError('Unexpected generated mesh actor: '+name)
        item = expected_actors.pop(name)
        component = actor.static_mesh_component
        expected_enabled = unreal.CollisionEnabled.QUERY_AND_PHYSICS if item['collision']=='complex' else unreal.CollisionEnabled.NO_COLLISION
        expected_profile = 'BlockAll' if item['collision']=='complex' else 'NoCollision'
        row = dict(name=name, declared=item['collision'], actual=str(component.get_collision_enabled()),
                   profile=str(component.get_collision_profile_name()), use_default_collision=component.get_editor_property('use_default_collision'))
        row['pass'] = component.get_collision_enabled()==expected_enabled and row['profile']==expected_profile and not row['use_default_collision']
        collision_checks.append(row)
        if not row['pass']:
            raise RuntimeError('Saved collision contract differs: '+json.dumps(row))
    if expected_actors:
        raise RuntimeError('Generated mesh actors missing after reload: '+str(list(expected_actors)))
    record['saved_actor_collision_checks'] = collision_checks
    record["map"] = "/Game/Maps/StanleyPark"
    record["success"] = True
except Exception:
    record["error"] = traceback.format_exc()
    unreal.log_error(record["error"])
    raise
finally:
    record["completed_utc"] = datetime.now(timezone.utc).isoformat()
    EVIDENCE.write_text(json.dumps(record, indent=2), encoding="utf-8")
