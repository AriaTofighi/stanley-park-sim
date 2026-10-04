"""Separate the Seawall bicycle pedals without changing the original M1 source."""
from pathlib import Path
import hashlib
import json
import math
import bpy
import bmesh
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'blender/StanleyPark_Blockout.blend'
OUT = ROOT / 'exports/animated-bicycle'
OUT.mkdir(exist_ok=True)
source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.file_preview_type = 'NONE'
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
with bpy.data.libraries.load(str(SOURCE), link=False) as (available, loaded):
    if 'SM_Bicycle' not in available.objects:
        raise RuntimeError('Original bicycle frame is missing')
    loaded.objects = ['SM_Bicycle']
frame = loaded.objects[0]
scene.collection.objects.link(frame)
frame.hide_render = False
frame.hide_set(False)
frame.name = 'SM_Bicycle_Animated'

# The two pedal platforms are separate, eight-vertex islands in the original
# joined frame. Match both their centre and size before removing either one.
bm = bmesh.new()
bm.from_mesh(frame.data)
unvisited = set(bm.verts)
removed = []
while unvisited:
    island = {unvisited.pop()}
    stack = list(island)
    while stack:
        vertex = stack.pop()
        for edge in vertex.link_edges:
            other = edge.other_vert(vertex)
            if other in unvisited:
                unvisited.remove(other)
                island.add(other)
                stack.append(other)
    if len(island) != 8:
        continue
    centre = sum((v.co for v in island), Vector()) / 8
    extent = Vector(max(v.co[axis] for v in island) - min(v.co[axis] for v in island) for axis in range(3))
    if abs(abs(centre.x) - .2) < .0001 and abs(centre.y + .08) < .0001 and abs(centre.z - .3) < .0001:
        if (extent - Vector((.10, .09, .025))).length > .0001:
            raise RuntimeError('Pedal island dimensions differ from the source contract')
        removed.extend(island)
if len(removed) != 16:
    raise RuntimeError(f'Expected exactly two original pedal islands; found {len(removed)} vertices')
bmesh.ops.delete(bm, geom=removed, context='VERTS')
bm.to_mesh(frame.data)
bm.free()
rubber = bpy.data.materials['M_Rubber']
steel = bpy.data.materials['M_Steel']

def box(name, position, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=position)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(material)
    return obj

pedal = box('SM_Pedal', (0, 0, 0), (.10, .09, .025), rubber)
crank = box('SM_CrankArm', (0, 0, .085), (.025, .025, .17), steel)
objects = [frame, pedal, crank]
records = []
for obj in objects:
    minimum = [min((v.co.y, v.co.x, v.co.z)[axis] * 100 for v in obj.data.vertices) for axis in range(3)]
    maximum = [max((v.co.y, v.co.x, v.co.z)[axis] * 100 for v in obj.data.vertices) for axis in range(3)]
    bpy.ops.object.select_all(action='DESELECT')
    data = obj.data.copy()
    data.transform(Matrix.Rotation(-math.pi / 2, 4, 'Z'))
    temporary = bpy.data.objects.new(obj.name + '_export', data)
    scene.collection.objects.link(temporary)
    temporary.select_set(True)
    bpy.context.view_layer.objects.active = temporary
    fbx = OUT / (obj.name + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'MESH'},
        use_mesh_modifiers=True, mesh_smooth_type='FACE', use_triangles=True,
        use_space_transform=False, axis_forward='Y', axis_up='Z', global_scale=1.0,
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', bake_space_transform=True,
        bake_anim=False, add_leaf_bones=False, path_mode='STRIP', use_custom_props=False)
    bpy.data.objects.remove(temporary, do_unlink=True)
    bpy.data.meshes.remove(data)
    records.append(dict(name=obj.name, fbx=fbx.relative_to(ROOT).as_posix(),
        sha256=hashlib.sha256(fbx.read_bytes()).hexdigest(),
        bounds_min_cm=minimum, bounds_max_cm=maximum,
        materials=[m.name for m in obj.data.materials],
        material_colors={m.name:list(m.diffuse_color) for m in obj.data.materials}))
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'blender/Bicycle_Animated.blend'), compress=True)
if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_hash:
    raise RuntimeError('Original source changed during the separate export')
(ROOT / 'manifests/animated-bicycle.json').write_text(json.dumps(dict(
    source='blender/Bicycle_Animated.blend', original_source=SOURCE.relative_to(ROOT).as_posix(),
    original_sha256=source_hash, original_unchanged=True, pedal_islands_removed=2,
    crank_radius_cm=17, assets=records), indent=2))
