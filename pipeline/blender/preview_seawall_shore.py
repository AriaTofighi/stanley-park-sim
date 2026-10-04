"""Render the actual exported shore meshes in a separate review scene."""
from pathlib import Path
import hashlib
import json
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]


def preview():
    if Path(bpy.data.filepath).resolve() != (ROOT/'blender/StanleyPark_Seawall.blend').resolve():
        raise RuntimeError('Use the separate Seawall blend')
    pointer = json.loads((ROOT/'exports/seawall-shore/latest.json').read_text())
    manifest = json.loads((ROOT/pointer['manifest']).read_text())
    output = ROOT/'evidence/seawall-shore-blender-01.png'
    if output.exists(): raise FileExistsError(output)
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('SP_ShoreReview_01')
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    bpy.context.window.scene = scene
    for index, row in enumerate(manifest['assets']):
        source = bpy.data.objects[row['blender_object']]
        obj = bpy.data.objects.new('ShoreReview_'+row['name'],source.data)
        scene.collection.objects.link(obj)
        obj.location = ((index%3)*2.4,(index//3)*2.3,.30)
    floor_mesh = bpy.data.meshes.new('ShoreReviewFloor')
    floor_mesh.from_pydata([(-30,-30,-.02),(30,-30,-.02),(30,30,-.02),(-30,30,-.02)],[],[(0,1,2,3)])
    floor = bpy.data.objects.new('ShoreReviewFloor',floor_mesh)
    scene.collection.objects.link(floor)
    material = bpy.data.materials.new('ShoreReviewFloor')
    material.use_nodes = True
    material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.17,.18,.16,1)
    material.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .95
    floor_mesh.materials.append(material)
    world = bpy.data.worlds.new('ShoreReviewWorld')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.44,.48,.52,1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .7
    scene.world = world
    light_data = bpy.data.lights.new('ShoreReviewCloudLight','AREA')
    light_data.energy,light_data.size = 1100,8
    light = bpy.data.objects.new('ShoreReviewCloudLight',light_data)
    scene.collection.objects.link(light)
    light.location = (-2,-3,9)
    light.rotation_euler = (Vector((2,1,0))-light.location).to_track_quat('-Z','Y').to_euler()
    camera_data = bpy.data.cameras.new('ShoreReviewCamera')
    camera = bpy.data.objects.new('ShoreReviewCamera',camera_data)
    scene.collection.objects.link(camera)
    camera.location = (9,-9,7)
    camera.rotation_euler = (Vector((2.4,1,.3))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.lens = 48
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage = 1280,800,100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(output)
    try: bpy.ops.render.render(write_still=True)
    finally: bpy.context.window.scene = previous
    record = dict(image=output.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        source=pointer['manifest'],scene=scene.name,method='Actual Blender source meshes rendered with Cycles',inspected=False)
    output.with_suffix('.json').write_text(json.dumps(record,indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Seawall.blend'))
    return record


result = preview()
