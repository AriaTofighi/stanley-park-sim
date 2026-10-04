"""Set a repeatable view of the authored east-shore vegetation groups."""
import bpy
from mathutils import Vector

scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
eye=Vector((1450,120,145));target=Vector((1250,-100,30))
for window in bpy.context.window_manager.windows:
    if window.scene!=scene:continue
    for area in window.screen.areas:
        if area.type!='VIEW_3D':continue
        space=area.spaces.active
        space.shading.type='SOLID';space.shading.color_type='MATERIAL'
        space.clip_start=.1;space.clip_end=100000
        space.overlay.show_overlays=False
        region=space.region_3d
        region.view_perspective='PERSP';region.view_location=target
        region.view_distance=(eye-target).length
        region.view_rotation=(target-eye).to_track_quat('-Z','Y')
result=dict(scene=scene.name,eye=list(eye),target=list(target),
            visual_check_required=True,source='2022 canopy heights with dated VRI groups')
