"""Apply or restore the bounded water/sky pass on an already loaded seawall map.

Use runpy.run_path with SP_SEAWALL_MAP_PATH and SP_SEAWALL_ACTION (apply/restore).
This script never loads a map, imports a mesh, changes terrain, or starts a game.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "manifests/seawall-water-sky.json"
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
TEXTURE_MANIFEST_PATH = ROOT / SPEC["water"]["texture_manifest"]
TAG = SPEC["actor_tag"]
MAT = unreal.MaterialEditingLibrary
ASSETS = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
FINGERPRINT = hashlib.sha256(SPEC_PATH.read_bytes() + Path(__file__).read_bytes()
                             + (TEXTURE_MANIFEST_PATH.read_bytes() if TEXTURE_MANIFEST_PATH.exists() else b"missing-texture-manifest")).hexdigest()
REPORT = ROOT / "evidence/seawall-water-sky.json"
BASELINE = ROOT / "evidence/seawall-water-sky-baseline.json"
record = dict(success=False, started_utc=datetime.now(timezone.utc).isoformat(),
              engine=unreal.SystemLibrary.get_engine_version(), fingerprint=FINGERPRINT,
              manifest_sha256=hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest(),
              script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              action=globals().get("SP_SEAWALL_ACTION") or os.environ.get("SP_SEAWALL_ACTION", "apply"), materials=[], connections=[],
              application_test_run=False, visual_acceptance=False, performance_verified=False)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def tagged(actor, tag):
    return tag in [str(t) for t in actor.tags]


def vec(value):
    return [value.x, value.y, value.z]


def invariant(actor):
    component = actor.static_mesh_component
    rotation = actor.get_actor_rotation()
    return dict(location=vec(actor.get_actor_location()), scale=vec(actor.get_actor_scale3d()),
                rotation=[rotation.pitch, rotation.yaw, rotation.roll],
                mesh=component.static_mesh.get_path_name(),
                collision=str(component.get_collision_enabled()),
                profile=str(component.get_collision_profile_name()),
                use_default_collision=component.get_editor_property("use_default_collision"))


def node(material, expression_type, **properties):
    expression = MAT.create_material_expression(material, expression_type)
    if expression is None:
        raise RuntimeError("Cannot create " + expression_type.__name__)
    for key, value in properties.items():
        expression.set_editor_property(key, value)
    return expression


def scalar(material, value):
    return node(material, unreal.MaterialExpressionConstant, r=value)


def color(material, value):
    return node(material, unreal.MaterialExpressionConstant3Vector,
                constant=unreal.LinearColor(*value, 1.0))


def wire(source, target, input_name):
    # Names are read from the running engine. No positional guess is permitted.
    names = [str(n) for n in MAT.get_material_expression_input_names(target)]
    normalized = lambda s: s.replace(" ", "").replace("_", "").lower()
    matches = [n for n in names if normalized(n) == normalized(input_name)]
    if len(matches) != 1 or not MAT.connect_material_expressions(source, "", target, matches[0]):
        raise RuntimeError(f"Cannot connect {input_name}; engine inputs: {names}")
    record["connections"].append(dict(input=matches[0], node=target.get_class().get_name()))


def output(material, expression, property_name):
    prop = getattr(unreal.MaterialProperty, property_name)
    if not MAT.connect_material_property(expression, "", prop):
        raise RuntimeError("Cannot connect " + property_name)
    if MAT.get_material_property_input_node(material, prop) != expression:
        raise RuntimeError("Output connection readback failed: " + property_name)
    record["connections"].append(dict(output=property_name, readback=True))


def custom(material, code, inputs, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    custom_inputs = []
    for name in inputs:
        entry = unreal.CustomInput()
        entry.set_editor_property("input_name", name)
        custom_inputs.append(entry)
    expression = node(material, unreal.MaterialExpressionCustom, code=code,
                      output_type=output_type,
                      inputs=custom_inputs)
    for name, source in inputs.items():
        wire(source, expression, name)
    return expression


def import_wave_texture():
    """Import only the original normal texture, to a content-addressed asset."""
    source = json.loads(TEXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))
    if source["authoring"] != SPEC["water"]["texture_authoring"]:
        raise RuntimeError("The water normal source is stale. Run build_seawall_water_textures.py")
    if source["material_layers"] != SPEC["water"]["texture_layers"]:
        raise RuntimeError("The source motion diagnostics are stale. Run build_seawall_water_textures.py")
    filename = ROOT / source["normal_texture"]["path"]
    if hashlib.sha256(filename.read_bytes()).hexdigest() != source["normal_texture"]["sha256"]:
        raise RuntimeError("The water normal texture differs from its source manifest")
    settings = dict(srgb=False, compression_settings=unreal.TextureCompressionSettings.TC_NORMALMAP,
                    lod_group=unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP,
                    mip_gen_settings=unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
                    filter=unreal.TextureFilter.TF_DEFAULT, address_x=unreal.TextureAddress.TA_WRAP,
                    address_y=unreal.TextureAddress.TA_WRAP, flip_green_channel=False,
                    normalize_normals=True, never_stream=True, virtual_texture_streaming=False,
                    max_texture_size=1024, lod_bias=0, compression_no_alpha=True)
    digest = hashlib.sha256((source["normal_texture"]["sha256"] + json.dumps(
        {key: str(value) for key, value in settings.items()}, sort_keys=True)).encode()).hexdigest()
    name = "T_SeawallSpectralWaves_N_" + digest[:12]
    folder = SPEC["asset_folder"] + "/Textures"
    path = folder + "/" + name
    exists = ASSETS.does_asset_exist(path)
    if exists:
        texture = ASSETS.load_asset(path)
        if not isinstance(texture, unreal.Texture2D) or ASSETS.get_metadata_tag(texture, TAG) != digest:
            raise RuntimeError("Unfinished or foreign texture exists: " + path)
    else:
        task = unreal.AssetImportTask()
        for key, value in dict(filename=str(filename), destination_path=folder, destination_name=name,
                               automated=True, replace_existing=False, save=False, factory=unreal.TextureFactory()).items():
            task.set_editor_property(key, value)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture = ASSETS.load_asset(path)
        if not isinstance(texture, unreal.Texture2D):
            raise RuntimeError("Cannot import the water normal texture: " + path)
        for key, value in settings.items():
            texture.set_editor_property(key, value)
        ASSETS.set_metadata_tag(texture, TAG, digest)
        if not ASSETS.save_loaded_asset(texture):
            raise RuntimeError("Cannot save " + path)
    for key, value in settings.items():
        if texture.get_editor_property(key) != value:
            raise RuntimeError("Normal texture setting readback differs: " + key)
    dimensions = [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()]
    if dimensions != source["resolution"]:
        raise RuntimeError("Normal texture dimensions differ: " + str(dimensions))
    record["normal_texture"] = dict(path=path, reused=exists, dimensions=dimensions,
                                    source_sha256=source["normal_texture"]["sha256"],
                                    source_manifest_sha256=hashlib.sha256(TEXTURE_MANIFEST_PATH.read_bytes()).hexdigest(),
                                    settings={key: str(value) for key, value in settings.items()},
                                    expected_bc5_bytes_with_mips=source["expected_bc5_bytes_with_mips"],
                                    source_motion_diagnostics=source["temporal_source_diagnostics"])
    return texture


def build_water(material, texture):
    water = SPEC["water"]
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    material.set_editor_property("tangent_space_normal", False)
    material.set_editor_property("two_sided", True)
    for key, prop in [("specular", "MP_SPECULAR"), ("opacity", "MP_OPACITY")]:
        output(material, scalar(material, water[key]), prop)
    output(material, scalar(material, 0.0), "MP_METALLIC")
    world_position = node(material, unreal.MaterialExpressionWorldPosition)
    time = node(material, unreal.MaterialExpressionTime, ignore_pause=False, override_period=False)
    inputs = {"Depth": node(material, unreal.MaterialExpressionPixelDepth)}
    code = ["float2 slope=float2(0,0);"]
    animation = []
    for index, layer in enumerate(water["texture_layers"]):
        dx, dy = layer["axis_xy"]
        flow_x, flow_y = layer["flow_world_cm_per_second"]
        offset_x, offset_y = layer["offset_uv"]
        tile = layer["tile_cm"]
        uv = custom(material,
                    f"return float2(dot(P.xy,float2({dx},{dy})),dot(P.xy,float2({-dy},{dx})))"
                    f"/{tile}+float2({offset_x},{offset_y});", {"P": world_position},
                    unreal.CustomMaterialOutputType.CMOT_FLOAT2)
        # Advect a fixed world pattern: UV(P,t)=R*(P-flow*t)/tile + offset.
        # Native Panner keeps Time visible and auditable in the material graph.
        speed_x = -(flow_x * dx + flow_y * dy) / tile
        speed_y = -(-flow_x * dy + flow_y * dx) / tile
        panner = node(material, unreal.MaterialExpressionPanner, speed_x=speed_x, speed_y=speed_y,
                      fractional_part=True)
        wire(uv, panner, "Coordinate")
        wire(time, panner, "Time")
        linked = list(MAT.get_inputs_for_material_expression(material, panner))
        if time not in linked or uv not in linked:
            raise RuntimeError("Panner time/world-coordinate input readback failed")
        sample = node(material, unreal.MaterialExpressionTextureSample, texture=texture,
                      sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
                      sampler_source=unreal.SamplerSourceMode.SSM_FROM_TEXTURE_ASSET,
                      automatic_view_mip_bias=False)
        # UE 5.8 MaterialGraphNode shortens the reflected Coordinates pin to UVs.
        wire(panner, sample, "UVs")
        inputs["N" + str(index)] = sample
        code.append(f"float2 s{index}=N{index}.xy/max(N{index}.z,0.25);\n"
                    f"slope+=(float2({dx},{dy})*s{index}.x+float2({-dy},{dx})*s{index}.y)*{layer['strength']};")
        animation.append(dict(layer=index, coordinate_source="absolute_world_position_xy_cm",
                              native_time_connected=True, native_panner_connected=True,
                              speed_uv_per_second=[speed_x, speed_y],
                              flow_world_cm_per_second=layer["flow_world_cm_per_second"], tile_cm=tile))
    code += ["slope*=min(1.0,0.60/max(length(slope),0.0001));",
             f"float fade=1.0-smoothstep({water['normal_fade_start_cm']},{water['normal_fade_end_cm']},Depth);",
             f"return float4(normalize(float3(slope*fade,1.0)),lerp({water['roughness_far']},{water['roughness_near']},fade));"]
    ripple = custom(material, "\n".join(code), inputs, unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    normal = node(material, unreal.MaterialExpressionComponentMask, r=True, g=True, b=True, a=False)
    roughness = node(material, unreal.MaterialExpressionComponentMask, r=False, g=False, b=False, a=True)
    # ComponentMask has one unnamed input in some engine versions.
    for mask in (normal, roughness):
        if not MAT.connect_material_expressions(ripple, "", mask, ""):
            raise RuntimeError("Cannot unpack the spectral normal/roughness output")
        record["connections"].append(dict(input="ComponentMask.Input", checked=True))
    output(material, normal, "MP_NORMAL")
    output(material, color(material, water["base_color_linear"]), "MP_BASE_COLOR")
    output(material, roughness, "MP_ROUGHNESS")
    volume = node(material, unreal.MaterialExpressionSingleLayerWaterMaterialOutput)
    wire(color(material, water["scattering_per_cm"]), volume, "ScatteringCoefficients")
    wire(color(material, water["absorption_per_cm"]), volume, "AbsorptionCoefficients")
    wire(scalar(material, water["phase_g"]), volume, "PhaseG")
    wire(scalar(material, water["color_scale_behind_water"]), volume, "ColorScaleBehindWater")
    record["material_animation"] = dict(time_source="Game Time", ignore_pause=time.get_editor_property("ignore_pause"),
                                         override_period=time.get_editor_property("override_period"),
                                         layers=animation, screen_space_noise=False,
                                         color_animation=False, vertex_displacement=False,
                                         runtime_motion_verified=False)
    ASSETS.set_metadata_tag(material, "SP_WaterAnimation", json.dumps(record["material_animation"], sort_keys=True))


def build_sky(material):
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("is_sky", True)
    sky = SPEC["sky"]
    rgb = lambda values: "float3(" + ",".join(str(v) for v in values) + ")"
    # Original three-octave value noise. No textures, ray march, time, or asset downloads.
    code = """
float3 d = normalize(-ViewToEye);
float3 p = d * CLOUD_SCALE + float3(17.1,31.7,8.3);
float total=0.0, weight=0.57142857;
[unroll] for(int octave=0;octave<3;octave++) {
    float3 cell=floor(p), f=frac(p); f=f*f*(3.0-2.0*f);
    float value=0.0;
    [unroll] for(int z=0;z<2;z++) {
        [unroll] for(int y=0;y<2;y++) {
            [unroll] for(int x=0;x<2;x++) {
                float3 corner=float3(x,y,z);
                float3 blend=lerp(1.0-f,f,corner);
                float hash=frac(sin(dot(cell+corner,float3(127.1,311.7,74.7)))*43758.5453);
                value+=hash*blend.x*blend.y*blend.z;
            }
        }
    }
    total+=value*weight; p=p*2.03+13.1; weight*=0.5;
}
float cloud=smoothstep(0.20,0.82,total);
float3 overhead=lerp(CLOUD_DARK,CLOUD_LIGHT,cloud);
return lerp(HORIZON,overhead,smoothstep(0.0,0.45,max(d.z,0.0)));
"""
    for key, value in {"CLOUD_SCALE": str(sky["noise_scale"]),
                       "CLOUD_DARK": rgb(sky["cloud_dark_linear"]),
                       "CLOUD_LIGHT": rgb(sky["cloud_light_linear"]),
                       "HORIZON": rgb(sky["horizon_linear"])}.items():
        code = code.replace(key, value)
    output(material, custom(material, code, {
        "ViewToEye": node(material, unreal.MaterialExpressionCameraVectorWS)}), "MP_EMISSIVE_COLOR")


def material(name, builder):
    asset_name = name + "_" + FINGERPRINT[:12]
    path = SPEC["asset_folder"] + "/" + asset_name
    exists = ASSETS.does_asset_exist(path)
    if exists:
        result = ASSETS.load_asset(path)
        if not isinstance(result, unreal.Material) or ASSETS.get_metadata_tag(result, TAG) != FINGERPRINT:
            raise RuntimeError("Unfinished or foreign material exists; do not erase its graph: " + path)
        if name == "M_SeawallWater":
            saved_animation = ASSETS.get_metadata_tag(result, "SP_WaterAnimation")
            if not saved_animation:
                raise RuntimeError("The water material has no saved animation diagnostics")
            record["material_animation"] = json.loads(saved_animation)
            record["material_animation"]["diagnostic_source"] = "Saved creation-time graph readback; current material recompiled."
    else:
        result = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name, SPEC["asset_folder"], unreal.Material, unreal.MaterialFactoryNew())
        if result is None:
            raise RuntimeError("Cannot create " + path)
        result.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
        builder(result)
        MAT.layout_material_expressions(result)
    # UE 5.8 returns error strings. Do not treat a trigger-only API as compile evidence.
    errors = MAT.recompile_material(result)
    if errors is None:
        raise RuntimeError("Engine did not return material compile diagnostics: " + path)
    if errors:
        raise RuntimeError(path + ": " + "\n".join(str(e) for e in errors))
    ASSETS.set_metadata_tag(result, TAG, FINGERPRINT)
    if not ASSETS.save_loaded_asset(result):
        raise RuntimeError("Cannot save " + path)
    record["materials"].append(dict(path=path, reused=exists, compile_errors=[]))
    return result


def owned_actor(label, actor_type):
    matches = [a for a in ACTORS.get_all_level_actors() if a.get_actor_label() == label]
    if matches:
        if len(matches) != 1 or not tagged(matches[0], TAG) or not isinstance(matches[0], actor_type):
            raise RuntimeError("Actor ownership conflict: " + label)
        return matches[0]
    actor = ACTORS.spawn_actor_from_class(actor_type, unreal.Vector(0, 0, 0))
    if actor is None:
        raise RuntimeError("Cannot spawn " + label)
    actor.tags = [TAG]
    actor.set_actor_label(label)
    actor.set_folder_path("StanleyPark/SeawallWaterSky")
    return actor


def inherited_components():
    classes = [unreal.DirectionalLightComponent, unreal.SkyLightComponent,
               unreal.SkyAtmosphereComponent, unreal.ExponentialHeightFogComponent]
    result = []
    for actor in ACTORS.get_all_level_actors():
        if tagged(actor, TAG):
            continue
        for cls in classes:
            component = actor.get_component_by_class(cls)
            if component:
                if not tagged(actor, "SP_Generated"):
                    raise RuntimeError("Unowned environment actor needs review: " + actor.get_actor_label())
                result.append(component)
    return result


def apply_sky(sky_material, sphere):
    sky = SPEC["sky"]
    dome = owned_actor("SP_Seawall_OvercastDome", unreal.StaticMeshActor)
    dome.set_actor_scale3d(unreal.Vector(*([sky["sphere_scale"]] * 3)))
    component = dome.static_mesh_component
    component.set_static_mesh(sphere)
    component.set_material(0, sky_material)
    component.set_collision_profile_name("NoCollision")
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property("cast_shadow", False)
    sun = owned_actor("SP_Seawall_OvercastSun", unreal.DirectionalLight)
    pitch, yaw, roll = sky["sun_rotation_deg"]
    sun.set_actor_rotation(unreal.Rotator(pitch=pitch, yaw=yaw, roll=roll), False)
    light = sun.light_component
    light.set_mobility(unreal.ComponentMobility.MOVABLE)
    # The 6200 m capture pair isolates dry-shore streaks to cast shadows.
    # Deep overcast uses directional fill, captured sky, and existing AO.
    light.set_cast_shadows(sky["sun_cast_shadows"])
    actual_cast_shadows = bool(light.get_editor_property("cast_shadows"))
    if actual_cast_shadows != sky["sun_cast_shadows"]:
        raise RuntimeError("Overcast directional-light shadow readback failed")
    record["directional_light"] = dict(actor=sun.get_path_name(),
                                       cast_shadows=actual_cast_shadows,
                                       policy=sky["sun_shadow_policy"])
    for key, value in {"intensity": sky["sun_intensity"],
                       "light_source_angle": sky["sun_source_angle_deg"]}.items():
        light.set_editor_property(key, value)
    fill = owned_actor("SP_Seawall_OvercastSkyLight", unreal.SkyLight).light_component
    fill.set_mobility(unreal.ComponentMobility.MOVABLE)
    for key, value in {"source_type": unreal.SkyLightSourceType.SLS_CAPTURED_SCENE,
                       "real_time_capture": False, "capture_emissive_only": True,
                       "cubemap_resolution": sky["skylight_capture_resolution"],
                       "sky_distance_threshold": sky["skylight_distance_threshold_cm"],
                       "intensity": sky["skylight_intensity"], "lower_hemisphere_is_black": True,
                       "lower_hemisphere_color": unreal.LinearColor(0.015, 0.018, 0.02, 1)}.items():
        fill.set_editor_property(key, value)
    fog = owned_actor("SP_Seawall_OvercastFog", unreal.ExponentialHeightFog).component
    for key, value in {"fog_density": sky["fog_density"], "start_distance": sky["fog_start_distance_cm"],
                       "fog_cutoff_distance": sky["fog_cutoff_distance_cm"],
                       "enable_volumetric_fog": False, "enable_fsss": False,
                       "fog_inscattering_luminance": unreal.LinearColor(*sky["horizon_linear"], 1)}.items():
        fog.set_editor_property(key, value)
    fill.recapture_sky()
    record["sky_capture"] = "Requested once. Completion and image quality need editor review."


def run():
    requested = globals().get("SP_SEAWALL_MAP_PATH") or os.environ.get("SP_SEAWALL_MAP_PATH")
    current = LEVELS.get_current_level().get_outer().get_path_name().split(".")[0]
    if requested != SPEC["map_path"] or current != requested:
        raise RuntimeError(f"Load the separate {SPEC['map_path']} map and pass SP_SEAWALL_MAP_PATH; current={current}")
    if not record["engine"].startswith(SPEC["engine_prefix"]):
        raise RuntimeError("This pass requires the inspected Unreal 5.8.3 API")
    if record["action"] not in ("apply", "restore"):
        raise RuntimeError("Pass SP_SEAWALL_ACTION='apply' or 'restore'")
    water = SPEC["water"]
    if len(water["texture_layers"]) != 3 or SPEC["sky"]["noise_octaves"] != 3:
        raise RuntimeError("This pass requires three wave texture samples and three cloud noise levels")
    if not 0 <= water["normal_fade_start_cm"] < water["normal_fade_end_cm"] <= 150000:
        raise RuntimeError("Water normals must fade to zero within 1500 metres")
    if water["texture_authoring"]["resolution"] != 1024:
        raise RuntimeError("This pass uses one 1024-pixel normal texture")
    if not 0.08 <= water["roughness_near"] <= water["roughness_far"] <= 0.35:
        raise RuntimeError("Water roughness is outside the bounded preset")
    for layer in water["texture_layers"]:
        if not 500 <= layer["tile_cm"] <= 5000 or not 0 <= layer["strength"] <= 1.0:
            raise RuntimeError("Water texture scale or strength exceeds the preset bounds")
        if abs(sum(v*v for v in layer["axis_xy"]) - 1.0) > 0.0001:
            raise RuntimeError("Water texture axes must have unit length")
        speed = sum(v*v for v in layer["flow_world_cm_per_second"]) ** 0.5
        if not 20 <= speed <= 70:
            raise RuntimeError("Water layer speed must stay between 20 and 70 cm/s")
    if SPEC["sky"]["skylight_capture_resolution"] not in (64, 128, 256):
        raise RuntimeError("Sky capture resolution must be 64, 128 or 256")
    if SPEC["sky"]["sun_cast_shadows"] is not False:
        raise RuntimeError("This fixed overcast pass requires directional fill without cast shadows")
    record["map"] = current
    record["water_levels_sha256"] = hashlib.sha256((ROOT / SPEC["water"]["level_source"]).read_bytes()).hexdigest()
    record["export_manifest_sha256"] = hashlib.sha256((ROOT / "manifests/blender-export.json").read_bytes()).hexdigest()
    all_actors = list(ACTORS.get_all_level_actors())
    water = []
    exports = json.loads((ROOT / "manifests/blender-export.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in exports["assets"]}
    for target in SPEC["water_actors"]:
        matches = [a for a in all_actors if a.get_actor_label() == target["label"]]
        if not matches and not target["required"]:
            continue
        if len(matches) != 1 or not isinstance(matches[0], unreal.StaticMeshActor) or not tagged(matches[0], "SP_Generated"):
            raise RuntimeError("Missing, duplicate or unowned water actor: " + target["label"])
        actor = matches[0]
        declaration = by_name[target["label"]]
        state = invariant(actor)
        if state["mesh"].split(".")[0] != declaration["asset_path"] or declaration["collision"] != "none":
            raise RuntimeError("Water source contract differs: " + target["label"])
        if actor.static_mesh_component.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION:
            raise RuntimeError("Water collision must already be disabled: " + target["label"])
        if actor.static_mesh_component.get_num_materials() != 1:
            raise RuntimeError("Expected one source water material slot: " + target["label"])
        water.append(actor)
    before = {a.get_path_name(): invariant(a) for a in water}
    if record["action"] == "restore":
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        if baseline["map"] != current:
            raise RuntimeError("Baseline map differs")
        restore_water = []
        for row in baseline["water"]:
            actor = next((a for a in water if a.get_path_name() == row["actor"]), None)
            if actor is None or invariant(actor) != row["invariant"]:
                raise RuntimeError("Baseline water identity differs: " + row["actor"])
            values = [ASSETS.load_asset(path) if path else None for path in row["overrides"]]
            if any(path and asset is None for path, asset in zip(row["overrides"], values)):
                raise RuntimeError("Baseline material is missing")
            restore_water.append((actor, values))
        components = {c.get_path_name(): c for c in inherited_components()}
        if any(row["component"] not in components for row in baseline["environment"]):
            raise RuntimeError("A baseline environment component is missing")
        for actor, values in restore_water:
            actor.static_mesh_component.set_editor_property("override_materials", values)
        for row in baseline["environment"]:
            components[row["component"]].set_visibility(row["visible"])
        for actor in all_actors:
            if tagged(actor, TAG) and not ACTORS.destroy_actor(actor):
                raise RuntimeError("Cannot remove owned actor: " + actor.get_actor_label())
    else:
        sphere = ASSETS.load_asset(SPEC["sky"]["sphere_asset"])
        if not isinstance(sphere, unreal.StaticMesh):
            raise RuntimeError("Built-in sphere is missing")
        environment = inherited_components()
        if not BASELINE.exists():
            if any(tagged(a, TAG) for a in all_actors):
                raise RuntimeError("Owned actors exist but the restore baseline is missing")
            baseline = dict(map=current, created_utc=datetime.now(timezone.utc).isoformat(),
                            water=[dict(actor=a.get_path_name(), invariant=invariant(a),
                                        overrides=[m.get_path_name() if m else None for m in
                                                   a.static_mesh_component.get_editor_property("override_materials")])
                                   for a in water],
                            environment=[dict(component=c.get_path_name(), visible=c.get_editor_property("visible"))
                                         for c in environment])
            write_json(BASELINE, baseline)
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        if baseline["map"] != current or {r["actor"] for r in baseline["water"]} != set(before):
            raise RuntimeError("Restore baseline does not match the current water actors")
        if {r["component"] for r in baseline["environment"]} != {c.get_path_name() for c in environment}:
            raise RuntimeError("Restore baseline does not match the current environment actors")
        normal_texture = import_wave_texture()
        water_material = material("M_SeawallWater", lambda mat: build_water(mat, normal_texture))
        sky_material = material("M_SeawallOvercast", build_sky)
        for actor in water:
            component = actor.static_mesh_component
            for slot in range(component.get_num_materials()):
                component.set_material(slot, water_material)
                if component.get_material(slot) != water_material:
                    raise RuntimeError("Water material readback failed")
        for component in environment:
            component.set_visibility(False)
        apply_sky(sky_material, sphere)
    after = {a.get_path_name(): invariant(a) for a in water}
    if after != before:
        raise RuntimeError("Water transform, source mesh or collision changed")
    record["water_invariants"] = after
    record["water_invariants_unchanged"] = True
    if not LEVELS.save_current_level():
        raise RuntimeError("Cannot save the seawall map")
    record["success"] = True


try:
    write_json(REPORT, record)
    run()
except Exception:
    record["error"] = traceback.format_exc()
    record["recovery"] = "Do not save partial work. Inspect the report, then run restore on the same seawall map. Materials are retained."
    unreal.log_error(record["error"])
    raise
finally:
    record["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(REPORT, record)

result = record
