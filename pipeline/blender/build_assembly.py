"""Build the linked light assembly from the module manifest in background Blender."""
from pathlib import Path
import json
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
record = json.loads((ROOT/'manifests/blender-modules.json').read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.file_preview_type = 'NONE'
scene = bpy.context.scene
scene.name = 'StanleyPark_Assembly'
scene.unit_settings.system = 'METRIC'
for row in record['modules']:
    if row['collection'] == 'MODULE_Retired_Reference':
        continue  # Retired sources are available in their own file, not loaded.
    with bpy.data.libraries.load(str(ROOT/row['file']), link=True, relative=True) as (src, dst):
        dst.collections = [row['collection']]
    scene.collection.children.link(dst.collections[0])
    if row['excluded']:
        bpy.context.view_layer.layer_collection.children[row['collection']].exclude = True
scene['editing_help'] = 'Open blender/modules/*.blend to edit a layer. Reload this assembly to see saved changes. Enable forest layers in the Outliner when needed.'
scene['source_archive'] = record['source']
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            space.shading.type = 'SOLID'
            space.shading.color_type = 'MATERIAL'
            space.clip_end = 30000
            space.region_3d.view_distance = 4000
            space.region_3d.view_location = Vector((0, 0, 0))
            space.region_3d.view_rotation = Vector((1, 1, -1)).to_track_quat('-Z', 'Y')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/record['assembly']), compress=True)
