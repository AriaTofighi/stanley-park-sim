"""Apply the ground revision and import the fixed park map, without gameplay."""
import hashlib
import json
import shutil
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "unreal/Content/Maps/StanleyParkSeawall.umap"
backup = ROOT / "local-archive/editor-feedback-ground/StanleyParkSeawall.umap"
backup.parent.mkdir(parents=True, exist_ok=True)
if not backup.exists():
    shutil.copy2(MAP, backup)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not levels.load_level("/Game/Maps/StanleyParkSeawall"):
    raise RuntimeError("Cannot load the Seawall authoring map")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if world.get_path_name().split(".")[0] != "/Game/Maps/StanleyParkSeawall":
    raise RuntimeError("Wrong authoring map")
mel = unreal.MaterialEditingLibrary
matpath = "/Game/StanleyPark/Seawall/ParkDetails_v05/Materials/M_ParkForestFloor"
mat = assets.load_asset(matpath) if assets.does_asset_exist(matpath) else None
if mat is None:
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_ParkForestFloor",
        matpath.rsplit("/",1)[0], unreal.Material, unreal.MaterialFactoryNew())
mel.delete_all_material_expressions(mat)
p = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition)
entry = unreal.CustomInput()
entry.set_editor_property("input_name", "P")
color = mel.create_material_expression(mat, unreal.MaterialExpressionCustom)
color.set_editor_property("inputs", [entry])
color.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
color.set_editor_property("code", '''
float v[3]; float scales[3]={.00024,.013,.11};
[unroll] for(int j=0;j<3;j++) {
    float2 q=P.xy*scales[j],c=floor(q),f=frac(q); f=f*f*(3-2*f);
    float4 h=frac(sin(float4(dot(c,float2(127.1,311.7)),dot(c+float2(1,0),float2(127.1,311.7)),dot(c+float2(0,1),float2(127.1,311.7)),dot(c+1,float2(127.1,311.7))))*43758.5453);
    v[j]=lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y);
}
// Continuous green cover. Brown is fine dry litter, never large mud islands.
float3 green=lerp(float3(.073,.119,.037),float3(.124,.181,.062),v[0]);
green *= .89 + .16*v[1] + .10*v[2];
float2 q=P.xy*.28,c=floor(q),f=frac(q);
float h=frac(sin(dot(c,float2(127.1,311.7)))*43758.5453);
float leaf=step(.76,h)*(1-smoothstep(.20,.42,length((f-.5)*float2(1,1.8))));
return lerp(green,float3(.136,.103,.049),leaf*.58);''')
if not mel.connect_material_expressions(p,"",color,"P"):
    raise RuntimeError("Cannot connect forest ground coordinates")
if not mel.connect_material_property(color,"",unreal.MaterialProperty.MP_BASE_COLOR):
    raise RuntimeError("Cannot connect forest ground color")
rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant)
rough.set_editor_property("r",.97)
mel.connect_material_property(rough,"",unreal.MaterialProperty.MP_ROUGHNESS)
specular = mel.create_material_expression(mat, unreal.MaterialExpressionConstant)
specular.set_editor_property("r",.18)
mel.connect_material_property(specular,"",unreal.MaterialProperty.MP_SPECULAR)
normal = mel.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS)
mel.connect_material_property(normal,"",unreal.MaterialProperty.MP_NORMAL)
mat.set_editor_property("tangent_space_normal",False)
mel.layout_material_expressions(mat)
errors = mel.recompile_material(mat)
if errors:
    raise RuntimeError("Forest ground material compile failed: " + str(errors))
if not assets.save_loaded_asset(mat):
    raise RuntimeError("Cannot save forest ground material")
terrain_count = 0
for actor in actors.get_all_level_actors():
    if actor.get_actor_label().startswith("SM_Terrain_"):
        actor.static_mesh_component.set_material(0,mat)
        terrain_count += 1

task = unreal.AssetImportTask()
for k,v in dict(filename=str(ROOT/"exports/ui/T_ParkMinimap.png"),
    destination_path="/Game/StanleyPark/UI",destination_name="T_ParkMinimap",
    automated=True,replace_existing=True,save=False).items():
    task.set_editor_property(k,v)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
texture = assets.load_asset("/Game/StanleyPark/UI/T_ParkMinimap")
if not isinstance(texture,unreal.Texture2D):
    raise RuntimeError("Map texture import failed")
texture.set_editor_property("compression_settings",unreal.TextureCompressionSettings.TC_EDITOR_ICON)
texture.set_editor_property("lod_group",unreal.TextureGroup.TEXTUREGROUP_UI)
texture.set_editor_property("mip_gen_settings",unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
texture.set_editor_property("srgb",True)
assets.save_loaded_asset(texture)
if not levels.save_current_level():
    raise RuntimeError("Cannot save authoring map")
record = dict(application_test_run=False,ground_material=matpath,terrain_actors=terrain_count,
    minimap_texture=texture.get_path_name(),map_sha256=hashlib.sha256(MAP.read_bytes()).hexdigest(),success=True)
(ROOT/"evidence/editor-feedback-ground-minimap.json").write_text(json.dumps(record,indent=2)+"\n")
print("SP_GROUND_MINIMAP_SAVED",json.dumps(record))
