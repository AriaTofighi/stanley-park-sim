"""Build editable measured terrain in the live Blender scene through official MCP.

This is the M1 blockout, not finished environment art. Never treat its materials,
water level, or missing vegetation as a survey of present conditions.
"""
from pathlib import Path
import json
import math
import hashlib
import sys
import bpy
import numpy as np
from mathutils import Vector, geometry

ROOT = Path(__file__).resolve().parents[2]
BLEND = ROOT / "blender/StanleyPark_Blockout.blend"
BLEND.parent.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).parent))
SCENE_NAME = "StanleyPark_M1"

if SCENE_NAME not in bpy.data.scenes:
    backup = ROOT / "blender/backups/session-before-authoring.blend"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        bpy.ops.wm.save_as_mainfile(filepath=str(backup), copy=True)
    scene = bpy.data.scenes.new(SCENE_NAME)
else:
    scene = bpy.data.scenes[SCENE_NAME]
bpy.context.window.scene = scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene["origin_manifest"] = "manifests/world-origin.json"
scene["reference_period"] = "September 2026 target; near terrain 2022 survey with explicit historic gaps"
scene["acceptance_status"] = "M1 in progress; route heights and water alignment not accepted"


def collection(name):
    found = bpy.data.collections.get(name)
    if found is None:
        found = bpy.data.collections.new(name)
        scene.collection.children.link(found)
    return found


def clear_generated(owner):
    for obj in list(scene.objects):
        if obj.get("pipeline_owner") == owner:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)


def material(name, color, roughness=0.8, vertex=False):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    if vertex:
        node = mat.node_tree.nodes.get("SP_VertexColor")
        if node is None:
            node = mat.node_tree.nodes.new("ShaderNodeVertexColor")
            node.name = "SP_VertexColor"
        node.layer_name = "Color"
        mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    mat.diffuse_color = (*color, 1)
    return mat


def mesh_object(name, vertices, faces, target, mat, anchor=(0, 0, 0), colors=None,
                owner="terrain", collision="complex"):
    # Nodata edges can leave isolated survey samples. A render mesh only contains
    # vertices referenced by faces; this also makes source/import bounds comparable.
    used = sorted({index for face in faces for index in face})
    if len(used) != len(vertices):
        remap = {old: new for new, old in enumerate(used)}
        vertices = [vertices[index] for index in used]
        faces = [tuple(remap[index] for index in face) for face in faces]
        if colors is not None:
            colors = np.asarray(colors)[used]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    target.objects.link(obj)
    obj.location = anchor
    obj.data.materials.append(mat)
    obj["pipeline_owner"] = owner
    obj["collision"] = collision
    obj["source_id"] = "NRCan Vancouver 2013 DTM" if owner == "terrain" else "authored blockout"
    if colors is not None:
        attribute = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="POINT")
        attribute.data.foreach_set("color", np.asarray(colors, dtype=np.float32).ravel())
    return obj


clear_generated("terrain")
clear_generated("presentation")
clear_generated("water")
terrain_collection = collection("SP_01_MeasuredTerrain")
far_collection = collection("SP_02_RegionalTerrain")
presentation = collection("SP_90_Inspection")
terrain_material = material("M_TerrainBlockout", (0.17, 0.24, 0.14), vertex=True)
far_material = material("M_RegionalBlockout", (0.16, 0.22, 0.24), vertex=True)
water_material = material("M_WaterMeanScenario", (0.055, 0.19, 0.24), 0.3)
water_collection = collection("SP_04_Water")


def build_tiles(filename, step, tile_samples, target, mat, prefix, collision):
    grid = np.load(ROOT / "data/derived" / filename)
    x, y = grid["x"][::step], grid["y"][::step]
    heights = grid["z"][::step, ::step]
    park = grid["inside_park"][::step, ::step] if "inside_park" in grid else None
    ocean = None
    if "surroundings" in filename:
        mask_grid = np.load(ROOT / "data/derived/regional-ocean-mask.npz")
        if not (np.array_equal(grid["x"], mask_grid["x"]) and np.array_equal(grid["y"], mask_grid["y"])):
            raise RuntimeError("Ocean mask and regional terrain grids differ")
        ocean = mask_grid["ocean"][::step, ::step]
    count = 0
    for j in range(0, len(y) - 1, tile_samples):
        for i in range(0, len(x) - 1, tile_samples):
            tx, ty = x[i:i + tile_samples + 1], y[j:j + tile_samples + 1]
            tz = heights[j:j + len(ty), i:i + len(tx)]
            valid = np.isfinite(tz)
            if ocean is not None:
                valid &= ~ocean[j:j + len(ty), i:i + len(tx)]
            if not valid.any():
                continue
            # The far terrain omits the measured near crop. Preserve the source's holes.
            if "surroundings" in filename:
                near = np.load(ROOT / "data/derived/terrain_park.npz")
                xx, yy = np.meshgrid(tx, ty)
                valid &= ~((xx > near["x"][0] + 100) & (xx < near["x"][-1] - 100)
                           & (yy > near["y"][0] + 100) & (yy < near["y"][-1] - 100))
            index = np.full(tz.shape, -1, dtype=np.int32)
            index[valid] = np.arange(valid.sum())
            anchor = (float(tx[0]), float(ty[0]), 0.0)
            xx, yy = np.meshgrid(tx - tx[0], ty - ty[0])
            vertices = np.column_stack((xx[valid], yy[valid], tz[valid])).tolist()
            faces = []
            for row in range(len(ty) - 1):
                for col in range(len(tx) - 1):
                    a, b, c, d = index[row, col], index[row, col + 1], index[row + 1, col], index[row + 1, col + 1]
                    if min(a, b, c) >= 0:
                        faces.append((int(a), int(b), int(c)))
                    if min(b, d, c) >= 0:
                        faces.append((int(b), int(d), int(c)))
            if not faces:
                continue
            colors = np.tile(np.array([0.24, 0.27, 0.24, 1.0]), (valid.sum(), 1))
            if park is not None:
                mask = park[j:j + len(ty), i:i + len(tx)][valid]
                colors[mask] = [0.20, 0.29, 0.13, 1.0]
                colors[tz[valid] < 2] = [0.42, 0.40, 0.32, 1.0]
            else:
                colors[:] = [0.17, 0.24, 0.23, 1.0]
                colors[tz[valid] > 900] = [0.32, 0.36, 0.36, 1.0]
                colors[tz[valid] > 1600] = [0.51, 0.52, 0.51, 1.0]
            obj = mesh_object(f"{prefix}_{j // tile_samples:02d}_{i // tile_samples:02d}",
                              vertices, faces, target, mat, anchor, colors, collision=collision)
            obj["source_file"] = filename
            obj["measured_grid_metres"] = float(tx[1] - tx[0])
            for poly in obj.data.polygons:
                poly.use_smooth = True
            count += 1
    return count


surface_manifest = json.loads((ROOT / "manifests/surface-model.json").read_text())
if surface_manifest["origin_sha256"] != hashlib.sha256((ROOT / "manifests/world-origin.json").read_bytes()).hexdigest():
    raise RuntimeError("Surface mesh origin differs from project origin")
near_count = 0
for item in surface_manifest["terrain"]:
    path = ROOT / item["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise RuntimeError(f"Changed surface mesh: {path.name}")
    package = np.load(path)
    obj = mesh_object(item["name"], package["vertices"].tolist(), package["faces"].tolist(),
                      terrain_collection, terrain_material, package["anchor"], package["colors"])
    obj["source_file"] = "terrain_2022_park.npz"
    obj["source_id"] = "City Vancouver 2022 LiDAR ground; geoid-converted; explicit NRCan 2013 gaps"
    obj["measured_grid_metres"] = 2.0
    obj["mesh_sampling"] = "2m within 14m of source routes; 8m elsewhere; shared TIN"
    for poly in obj.data.polygons:
        poly.use_smooth = True
    near_count += 1
far_count = build_tiles("terrain_surroundings.npz", 2, 64, far_collection, far_material,
                       "SM_Region", "none")
water_levels=json.loads((ROOT/'manifests/water-levels.json').read_text())
ocean_height=water_levels['ocean']['height_m']
water = mesh_object("SM_Water_OceanMean",
                    [(-32000, -32000, ocean_height), (32000, -32000, ocean_height), (32000, 40000, ocean_height), (-32000, 40000, ocean_height)],
                    [(0, 1, 2, 3)], water_collection, water_material, owner="water", collision="none")
water["water_height_status"] = "DFO Vancouver mean-water scenario; epoch 2010; not a current tide"
water['source_id']='DFO CAN-EWLAT, Vancouver 7735, CGVD2013'
lake_data=json.loads((ROOT/'data/derived/lake-surfaces.geojson').read_text())
for feature in lake_data['features']:
    prop=feature['properties'];geom=feature['geometry']
    polygons=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
    vertices=[];faces=[]
    for polygon in polygons:
        ring=[Vector((p[0],p[1],prop['height_m'])) for p in polygon[0][:-1]]
        offset=len(vertices)
        faces.extend([tuple(offset+i for i in tri) for tri in geometry.tessellate_polygon([ring])])
        vertices.extend(ring)
    obj=mesh_object('SM_Water_'+prop['name'].replace(' ',''),vertices,faces,water_collection,water_material,owner='water',collision='none')
    obj['source_id']=prop['height_source']
    obj['water_height_m']=prop['height_m']
    obj['water_height_status']=prop['uncertainty']

light_data = bpy.data.lights.new("Sun_Inspection", "SUN")
light_data.energy = 2.2
light = bpy.data.objects.new("Sun_Inspection", light_data)
presentation.objects.link(light)
light.rotation_euler = (math.radians(28), math.radians(-20), math.radians(-30))
light["pipeline_owner"] = "presentation"
world = bpy.data.worlds.get("SP_Daylight") or bpy.data.worlds.new("SP_Daylight")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.34, 0.43, 0.57, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.65
scene.world = world
camera_data = bpy.data.cameras.new("Camera_ParkOverview")
camera = bpy.data.objects.new("Camera_ParkOverview", camera_data)
presentation.objects.link(camera)
camera.location = (2700, -3550, 2900)
camera.rotation_euler = (Vector((0, 200, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 4200
camera.data.clip_end = 100000
camera["pipeline_owner"] = "presentation"
scene.camera = camera
scene.render.engine = "CYCLES"
scene.cycles.samples = 12
scene.render.resolution_x = 1600
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(ROOT / "evidence/blender-park-overview.png")
scene.view_settings.view_transform = "AgX"
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        area.spaces.active.clip_end = 100000
        area.spaces.active.clip_start = 5
        area.spaces.active.overlay.show_extras = False
        area.spaces.active.region_3d.view_distance = 3700
        area.spaces.active.region_3d.view_location = Vector((0, 150, 0))
        area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
        area.spaces.active.shading.color_type = "MATERIAL"
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
result = {"blend": str(BLEND), "near_tiles": near_count, "far_tiles": far_count,
          "objects": len(scene.objects), "status": "measured blockout; acceptance pending"}
