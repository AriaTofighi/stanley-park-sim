"""Editable geometry for the bicycle and agent blockout. No purchased assets."""
from pathlib import Path
import math
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene
kit = bpy.data.collections.get("SP_10_ReusableKit")
if kit is None:
    kit = bpy.data.collections.new("SP_10_ReusableKit")
    scene.collection.children.link(kit)
for obj in list(kit.objects):
    if obj.get("pipeline_owner") == "kit":
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)


def material(name, color, metal=0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = 0.35 if metal else 0.8
    return mat


frame_mat = material("M_BicycleTeal", (0.035, 0.27, 0.28), 0.65)
rubber_mat = material("M_Rubber", (0.022, 0.027, 0.031))
steel_mat = material("M_Steel", (0.48, 0.51, 0.54), 0.8)
cloth_mat = material("M_JacketOchre", (0.66, 0.30, 0.07))
skin_mat = material("M_SkinBlockout", (0.5, 0.3, 0.2))
parts = []


def attach(obj, mat):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    kit.objects.link(obj)
    obj.data.materials.append(mat)
    parts.append(obj)
    return obj


def tube(a, b, radius, mat, vertices=12):
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=(b - a).length,
                                      location=(a + b) / 2)
    obj = bpy.context.object
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return attach(obj, mat)


def box(center, size, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.scale = size
    return attach(obj, mat)


def sphere(center, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=center)
    obj = bpy.context.object
    obj.scale = scale
    return attach(obj, mat)


def finish(name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj["pipeline_owner"] = "kit"
    obj["source_id"] = "Original procedural blockout design; no landmark geometry"
    obj["collision"] = "none"
    obj["kit_asset"] = True
    obj.hide_render = True
    obj.hide_set(True)
    parts.clear()
    return obj


def bicycle_frame():
    rear, crank, seat, head, front = (0, -0.55, 0.34), (0, -0.08, 0.30), (0, -0.20, 0.83), (0, 0.37, 0.80), (0, 0.55, 0.34)
    for a, b in [(rear, seat), (rear, crank), (crank, seat), (seat, head), (head, crank), (head, front)]:
        tube(a, b, 0.024, frame_mat)
    tube(seat, (0, -0.22, 0.97), 0.017, steel_mat)
    box((0, -0.24, 0.98), (0.18, 0.28, 0.045), rubber_mat)
    tube(head, (0, 0.38, 1.06), 0.02, steel_mat)
    tube((-0.31, 0.38, 1.06), (0.31, 0.38, 1.06), 0.018, steel_mat)
    for x in (-0.25, 0.25):
        tube((x - 0.06, 0.38, 1.06), (x + 0.06, 0.38, 1.06), 0.025, rubber_mat)
    tube((-0.19, -0.08, 0.30), (0.19, -0.08, 0.30), 0.014, steel_mat)
    for x in (-0.2, 0.2):
        box((x, -0.08, 0.30), (0.10, 0.09, 0.025), rubber_mat)


def wheel(center=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=40, minor_segments=8, major_radius=0.32,
                                    minor_radius=0.023, location=center, rotation=(0, math.pi / 2, 0))
    attach(bpy.context.object, rubber_mat)
    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        end = Vector(center) + Vector((0, 0.30 * math.cos(rad), 0.30 * math.sin(rad)))
        tube(center, end, 0.0025, steel_mat, 6)
    tube(Vector(center) + Vector((-0.06, 0, 0)), Vector(center) + Vector((0.06, 0, 0)), 0.025, steel_mat)


bicycle_frame()
finish("SM_Bicycle")
wheel()
finish("SM_Wheel")

box((0, 0, 1.17), (0.38, 0.23, 0.52), cloth_mat)
sphere((0, 0, 1.62), (0.12, 0.12, 0.15), skin_mat)
for sign in (-1, 1):
    tube((sign * 0.10, 0, 0.96), (sign * 0.12, sign * 0.12, 0.12), 0.078, rubber_mat)
    tube((sign * 0.22, 0, 1.40), (sign * 0.23, -sign * 0.08, 0.85), 0.055, cloth_mat)
    box((sign * 0.12, sign * 0.12 + 0.03, 0.07), (0.13, 0.23, 0.10), rubber_mat)
finish("SM_Walker")

bicycle_frame()
wheel((0, -0.55, 0.34))
wheel((0, 0.55, 0.34))
tube((0, -0.23, 1.02), (0, 0.08, 1.47), 0.17, cloth_mat)
sphere((0, 0.15, 1.65), (0.13, 0.16, 0.12), skin_mat)
sphere((0, 0.13, 1.74), (0.15, 0.17, 0.07), frame_mat)
for sign in (-1, 1):
    tube((sign * 0.17, 0.06, 1.41), (sign * 0.25, 0.38, 1.08), 0.05, cloth_mat)
    tube((sign * 0.12, -0.24, 1.00), (sign * 0.16, 0.11, 0.62), 0.075, rubber_mat)
    tube((sign * 0.16, 0.11, 0.62), (sign * 0.19, -0.08, 0.32), 0.06, rubber_mat)
finish("SM_Cyclist")

# Asymmetric export fixture: east length 1 m, north 2 m, height 3 m.
box((0.5, 1.0, 1.5), (1, 2, 3), cloth_mat)
fixture = finish("SM_AxisFixture")
fixture["expected_unreal_min_cm"] = [0.0, 0.0, 0.0]
fixture["expected_unreal_max_cm"] = [200.0, 100.0, 300.0]
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "blender/StanleyPark_Blockout.blend"))
result = {"kit_objects": [obj.name for obj in kit.objects], "source": "editable procedural meshes",
          "agent_status": "rigid visual proxies; rigging and animation not complete"}
