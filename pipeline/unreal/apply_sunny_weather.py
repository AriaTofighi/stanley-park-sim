"""Save a sunny lighting setup in the Seawall authoring map, without gameplay.

Use after the base park detail and ground/minimap passes. Existing source
meshes, terrain coordinates, and the protected M1 map are not changed.
"""
import hashlib
import json
import shutil
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "unreal/Content/Maps/StanleyParkSeawall.umap"
backup = ROOT / "local-archive/editor-sunny-ride/StanleyParkSeawall.umap"
backup.parent.mkdir(parents=True,exist_ok=True)
if not backup.exists():
    shutil.copy2(MAP,backup)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not levels.load_level("/Game/Maps/StanleyParkSeawall"):
    raise RuntimeError("Cannot load the Seawall authoring map")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if world.get_path_name().split(".")[0] != "/Game/Maps/StanleyParkSeawall":
    raise RuntimeError("Wrong authoring map")
by_label = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
for label in ["SP_Seawall_OvercastSun","SP_Seawall_OvercastSkyLight","SP_Seawall_OvercastFog","SP_Seawall_OvercastDome"]:
    if label not in by_label:
        raise RuntimeError("Missing lighting actor: "+label)

material_path = "/Game/StanleyPark/Seawall/Weather/M_ParkSunnySky"
mat = assets.load_asset(material_path) if assets.does_asset_exist(material_path) else None
if mat is None:
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_ParkSunnySky",
        material_path.rsplit("/",1)[0],unreal.Material,unreal.MaterialFactoryNew())
mel = unreal.MaterialEditingLibrary
mel.delete_all_material_expressions(mat)
mat.set_editor_property("shading_model",unreal.MaterialShadingModel.MSM_UNLIT)
mat.set_editor_property("two_sided",True)
mat.set_editor_property("is_sky",True)
vector = mel.create_material_expression(mat,unreal.MaterialExpressionCameraVectorWS)
entry = unreal.CustomInput()
entry.set_editor_property("input_name","V")
sky = mel.create_material_expression(mat,unreal.MaterialExpressionCustom)
sky.set_editor_property("inputs",[entry])
sky.set_editor_property("output_type",unreal.CustomMaterialOutputType.CMOT_FLOAT3)
sky.set_editor_property("code",'''
float3 d=-normalize(V);
float height=pow(saturate(d.z),.42);
float3 blue=lerp(float3(.49,.68,.84),float3(.10,.31,.68),height);
// Match the disk to the opposite of the directional light's ray direction.
float3 sun=normalize(float3(-.448,.497,.743));
float alignment=saturate(dot(d,sun));
float glow=pow(alignment,96)*.13;
float disk=smoothstep(.99994,.999985,alignment)*7;
return blue+float3(1,.92,.72)*(disk+glow);
''')
if not mel.connect_material_expressions(vector,"",sky,"V"):
    raise RuntimeError("Cannot connect sky direction")
if not mel.connect_material_property(sky,"",unreal.MaterialProperty.MP_EMISSIVE_COLOR):
    raise RuntimeError("Cannot connect sky color")
mel.layout_material_expressions(mat)
errors = mel.recompile_material(mat)
if errors:
    raise RuntimeError("Sunny sky compilation failed: "+str(errors))
if not assets.save_loaded_asset(mat):
    raise RuntimeError("Cannot save sunny sky")
by_label["SP_Seawall_OvercastDome"].static_mesh_component.set_material(0,mat)
sun_actor = by_label["SP_Seawall_OvercastSun"]
sun_actor.set_actor_rotation(unreal.Rotator(pitch=-48,yaw=-48),False)
sun = sun_actor.light_component
sun.set_intensity(5.2)
sun.set_light_color(unreal.LinearColor(1,.96,.86,1))
sun.set_cast_shadows(True)
for key,value in dict(light_source_angle=.65,shadow_bias=.8,shadow_slope_bias=1.0,
    dynamic_shadow_distance_movable_light=20000.0,dynamic_shadow_cascades=3).items():
    sun.set_editor_property(key,value)

# Shadow only nearby detailed objects. The source terrain and coarse shore
# relief previously produced overlapping triangle shadow streaks. They still
# receive tree/building shadows; disable their own shadow casting on the map
# components rather than changing any shared static mesh asset.
noncasters = []
for actor in by_label.values():
    label = actor.get_actor_label()
    if label.startswith("SM_Terrain_"):
        actor.static_mesh_component.set_cast_shadow(False)
        noncasters.append(label)
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        mesh = component.get_editor_property("static_mesh")
        if mesh and ("/Seawall/Shore/" in mesh.get_path_name() or mesh.get_name().startswith("SM_Ocean")):
            component.set_cast_shadow(False)
            noncasters.append(label+":"+component.get_name())
fill = by_label["SP_Seawall_OvercastSkyLight"].light_component
fill.set_intensity(.85)
fill.recapture_sky()
fog = by_label["SP_Seawall_OvercastFog"].component
fog.set_editor_property("fog_density",.00025)
fog.set_editor_property("fog_inscattering_luminance",unreal.LinearColor(.52,.69,.84,1))
if not levels.save_current_level():
    raise RuntimeError("Cannot save sunny Seawall map")
record = dict(application_test_run=False,success=True,sky_material=material_path,
    sun_intensity=sun.get_editor_property("intensity"),sun_pitch=-48,sun_yaw=-48,
    sun_cast_shadows=bool(sun.get_editor_property("cast_shadows")),shadow_distance_cm=20000,
    skylight_intensity=fill.get_editor_property("intensity"),fog_density=fog.get_editor_property("fog_density"),
    noncasting_map_components=noncasters,map_sha256=hashlib.sha256(MAP.read_bytes()).hexdigest())
(ROOT/"evidence/editor-sunny-weather.json").write_text(json.dumps(record,indent=2)+"\n")
print("SP_SUNNY_WEATHER_SAVED",json.dumps({k:v for k,v in record.items() if k != "noncasting_map_components"}))
