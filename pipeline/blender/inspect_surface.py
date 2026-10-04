"""Show and render the authored surface at the route entrance."""
import json
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene
samples = json.loads((ROOT / "data/derived/route-surface-samples.json").read_text())
points = samples["main_circuit"]
position = Vector(points[0]) + Vector((0, 0, 3.5))
target = Vector(points[4])
rotation = (target-position).to_track_quat("-Z", "Y")
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        space = area.spaces.active
        space.clip_start = .1
        space.clip_end = 100000
        space.overlay.show_extras = False
        space.region_3d.view_perspective = "PERSP"
        space.region_3d.view_rotation = rotation
        space.region_3d.view_distance = 10
        space.region_3d.view_location = position - rotation @ Vector((0, 0, 10))
        space.shading.color_type = "MATERIAL"
camera = bpy.data.objects.get("Camera_SurfaceInspection")
if camera is None:
    camera = bpy.data.objects.new("Camera_SurfaceInspection", bpy.data.cameras.new("Camera_SurfaceInspection"))
    bpy.data.collections["SP_90_Inspection"].objects.link(camera)
camera["pipeline_owner"] = "presentation"
camera.location = position
camera.rotation_euler = rotation.to_euler()
camera.data.type = "PERSP"
camera.data.lens = 24
camera.data.clip_start = .1
camera.data.clip_end = 100000
scene.camera = camera
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.filepath = str(ROOT / "evidence/blender-route-surface-fixed.png")
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "blender/StanleyPark_Blockout.blend"))
result = dict(view="Route entrance", file=scene.render.filepath, status="inspect rendered surface, not route survey")
