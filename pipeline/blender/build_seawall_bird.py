"""Author three original gull meshes in an isolated Blender scene, then export.

Run via Blender MCP with runpy.run_path. Does not save or change the park file.
The mesh contract follows export_assets.py: Blender E/N/U metres -> UE N/E/U cm.
"""
from pathlib import Path
import hashlib
import json
import math
import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
OWNER = "seawall_birds"
previous_scene = bpy.context.window.scene
if bpy.context.object and bpy.context.object.mode != "OBJECT":
    raise RuntimeError("Leave edit mode before the bird asset build")
scene = bpy.data.scenes.get("SP_SeawallBirdKit") or bpy.data.scenes.new("SP_SeawallBirdKit")
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
bpy.context.window.scene = scene
for obj in list(scene.objects):
    if obj.get("pipeline_owner") == OWNER:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)


def material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = 0.85
    return mat


white = material("M_SeawallGullWhite", (0.72, 0.73, 0.70))
grey = material("M_SeawallGullGrey", (0.37, 0.40, 0.42))
bill = material("M_SeawallGullBill", (0.61, 0.44, 0.13))
eye = material("M_SeawallGullEye", (0.015, 0.018, 0.017))


def mesh_object(name, vertices, faces, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    mesh.materials.append(mat)
    obj["pipeline_owner"] = OWNER
    obj["collision"] = "none"
    return obj


def ellipsoid(name, centre, radii, mat, segments=12, rings=6):
    vertices = []
    for ring in range(rings + 1):
        phi = -math.pi / 2 + ring * math.pi / rings
        for segment in range(segments):
            theta = segment * math.tau / segments
            vertices.append((centre[0] + radii[0] * math.cos(phi) * math.cos(theta),
                             centre[1] + radii[1] * math.cos(phi) * math.sin(theta),
                             centre[2] + radii[2] * math.sin(phi)))
    faces = []
    for ring in range(rings):
        for segment in range(segments):
            following = (segment + 1) % segments
            faces.append((ring * segments + segment, ring * segments + following,
                          (ring + 1) * segments + following, (ring + 1) * segments + segment))
    obj = mesh_object(name, vertices, faces, mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def make_body():
    # +Y is the beak axis in Blender; the export converts it to UE +X.
    parts = [ellipsoid("GullTorso", (0, -0.02, 0), (0.105, 0.235, 0.105), white),
             ellipsoid("GullMantle", (0, -0.045, 0.065), (0.10, 0.19, 0.05), grey),
             ellipsoid("GullHead", (0, 0.215, 0.075), (0.069, 0.083, 0.074), white),
             ellipsoid("GullBill", (0, 0.31, 0.063), (0.025, 0.072, 0.024), bill, 8, 4),
             ellipsoid("GullEyeLeft", (-0.063, 0.24, 0.095), (0.009, 0.009, 0.009), eye, 8, 4),
             ellipsoid("GullEyeRight", (0.063, 0.24, 0.095), (0.009, 0.009, 0.009), eye, 8, 4)]
    parts.append(mesh_object("GullTail", [(-0.065, -0.16, 0.01), (0.065, -0.16, 0.01),
        (0.092, -0.34, -0.01), (-0.092, -0.34, -0.01),
        (-0.065, -0.16, -0.02), (0.065, -0.16, -0.02),
        (0.092, -0.34, -0.025), (-0.092, -0.34, -0.025)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)], white))
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = "SM_GullBody"
    return obj


def make_wing(name, side):
    # Each mesh origin is its shoulder. Runtime shoulders sit at +/-9 cm.
    outline = [(0.0, 0.07), (0.23, 0.10), (0.40, 0.03), (0.63, -0.18),
               (0.58, -0.24), (0.36, -0.14), (0.12, -0.19), (0.0, -0.15)]
    vertices = [(side * x, y, z) for z in (-0.006, 0.012) for x, y in outline]
    faces = [tuple(range(8)), tuple(range(15, 7, -1))]
    faces.extend((i, (i + 1) % 8, (i + 1) % 8 + 8, i + 8) for i in range(8))
    if side < 0:
        faces = [tuple(reversed(face)) for face in faces]
    obj = mesh_object(name, vertices, faces, grey)
    obj.data.materials.append(white)
    obj.data.polygons[0].material_index = 1
    return obj


try:
    objects = [make_body(), make_wing("SM_GullWingLeft", -1), make_wing("SM_GullWingRight", 1)]
    output = ROOT / "exports/seawall-birds"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    rotation = Matrix.Rotation(-math.pi / 2, 4, "Z")
    for source in objects:
        mesh = source.data.copy()
        mesh.transform(rotation)
        temporary = bpy.data.objects.new("Export_" + source.name, mesh)
        scene.collection.objects.link(temporary)
        bpy.ops.object.select_all(action="DESELECT")
        temporary.select_set(True)
        bpy.context.view_layer.objects.active = temporary
        path = output / (source.name + ".fbx")
        try:
            bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={"MESH"},
                use_mesh_modifiers=True, mesh_smooth_type="FACE", use_triangles=True,
                use_space_transform=False, axis_forward="Y", axis_up="Z", global_scale=1.0,
                apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", bake_space_transform=True,
                bake_anim=False, add_leaf_bones=False, path_mode="STRIP", use_custom_props=False)
        finally:
            bpy.data.objects.remove(temporary, do_unlink=True)
            bpy.data.meshes.remove(mesh)
        points = [(vertex.co.y * 100, vertex.co.x * 100, vertex.co.z * 100)
                  for vertex in source.data.vertices]
        records.append(dict(name=source.name, fbx=path.relative_to(ROOT).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            bounds_min_cm=[min(point[i] for point in points) for i in range(3)],
            bounds_max_cm=[max(point[i] for point in points) for i in range(3)],
            materials=[dict(name=mat.name, color=list(mat.diffuse_color)[:3]) for mat in source.data.materials]))
    library = ROOT / "blender/SeawallBirds.blend"
    library.parent.mkdir(parents=True, exist_ok=True)
    bpy.data.libraries.write(str(library), {scene}, fake_user=True)
    result = dict(schema_version=1, assets=records, source_blend=library.relative_to(ROOT).as_posix(),
        rights="Original procedural meshes and materials; no external media",
        runtime_config_sha256=hashlib.sha256((ROOT / "manifests/seawall-birds.json").read_bytes()).hexdigest())
    (ROOT / "manifests/seawall-birds-export.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
finally:
    bpy.context.window.scene = previous_scene
