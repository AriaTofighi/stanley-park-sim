"""Original pilot shore rocks and textures; keep the measured surfaces intact.

Run in the separate Seawall blend through the official Blender connection.
Rocks are visual interpretations, not surveyed individual features.
"""
from pathlib import Path
import hashlib
import json
import math
import random

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
OWNER = "seawall_shore"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rock_geometry(index):
    # A deformed, smooth icosphere makes rounded weathered stones with broad
    # irregular fracture planes. Six reusable variants have no player collision.
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1)
    obj = bpy.context.object
    obj.name = f"SM_SeawallRock_{index:02d}"
    rng = random.Random(7319 + index)
    phase = np.array([rng.uniform(-5, 5) for _ in range(3)])
    for vertex in obj.data.vertices:
        p = np.array(vertex.co)
        wave = .11 * math.sin(p[0] * 4.1 + phase[0]) * math.cos(p[1] * 3.3 + phase[1])
        wave += .045 * math.cos(p[2] * 7.2 + p[0] * 2.1 + phase[2])
        p *= 1 + wave
        p *= [1, .72 + .06 * index, .49 + .035 * index]
        p[2] = max(p[2], -.30)
        vertex.co = p
    for face in obj.data.polygons:
        face.use_smooth = True
    obj.data.update()
    return obj


def textures(folder):
    """Tileable original mineral grains and small pebble relief, no source photo."""
    n = 1024
    rng = np.random.default_rng(472901)
    freq = np.fft.fftfreq(n)
    radius = np.hypot(freq[:, None], freq[None, :])
    spectrum = (radius + .004) ** -1.35
    spectrum[0, 0] = 0
    noise = np.fft.ifft2(np.fft.fft2(rng.normal(size=(n, n))) * spectrum).real
    noise = (noise - noise.mean()) / noise.std()
    yy, xx = np.mgrid[:n, :n] / n
    # Rounded pebbles with independently rotated elliptical outlines; looped
    # distance makes the boundaries seamless at all four texture edges.
    relief = np.zeros((n, n), dtype=np.float32)
    tones = np.zeros((n, n), dtype=np.float32)
    for _ in range(380):
        cx, cy = rng.random(2)
        dx, dy = (xx - cx + .5) % 1 - .5, (yy - cy + .5) % 1 - .5
        a = rng.uniform(0, math.tau)
        u = (dx * math.cos(a) + dy * math.sin(a)) / rng.uniform(.010, .040)
        v = (-dx * math.sin(a) + dy * math.cos(a)) / rng.uniform(.009, .029)
        pebble = np.maximum(0, 1 - u * u - v * v) ** .7
        take = pebble > relief
        tones[take] = rng.uniform(-.18, .18)
        relief = np.maximum(relief, pebble)
    height = relief * .55 + noise * .045
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 7.5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 7.5
    normal = np.stack((-dx, -dy, np.ones_like(dx)), -1)
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    grain = np.clip(.64 + noise * .085 + tones + relief * .04, .18, .92)
    color = np.stack((grain * 1.02, grain, grain * .94, np.ones_like(grain)), -1)
    norm = np.concatenate((normal * .5 + .5, np.ones((n, n, 1))), axis=2)
    result = []
    for name, pixels in [("T_SeawallMineral", color), ("T_SeawallMineralNormal", norm)]:
        image = bpy.data.images.new(name + "_" + folder.name, width=n, height=n, alpha=True)
        image.colorspace_settings.name = "Non-Color"
        image.pixels.foreach_set(pixels.astype(np.float32).ravel())
        image.filepath_raw = str(folder / (name + ".png"))
        image.file_format = "PNG"
        image.save()
        result.append(dict(name=name, path=Path(image.filepath_raw).relative_to(ROOT).as_posix(),
                           sha256=sha(Path(image.filepath_raw)), size=[n, n], image=image.name))
    return result


def build():
    if Path(bpy.data.filepath).resolve() != (ROOT / "blender/StanleyPark_Seawall.blend").resolve():
        raise RuntimeError("Use the separate Seawall blend")
    scene = bpy.data.scenes.get("StanleyPark_M1")
    if scene is None or scene.unit_settings.scale_length != 1:
        raise RuntimeError("Expected the measured scene in metres")
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        raise RuntimeError("Leave edit mode first")
    bpy.context.window.scene = scene
    inputs = {p: sha(ROOT / p) for p in ["pipeline/blender/build_seawall_shore.py",
        "manifests/surface-model.json", "data/derived/paved-circuit-runtime.json"]}
    version = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:12]
    folder = ROOT / "exports/seawall-shore" / version
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        raise RuntimeError("This shore version already exists; reuse its manifest")
    collection = bpy.data.collections.new("SP_SeawallShore_" + version)
    scene.collection.children.link(collection)
    # Previous generated layers remain available but hidden in this working copy.
    for c in bpy.data.collections:
        if c.name.startswith("SP_SeawallShore_") and c != collection:
            c.hide_viewport = c.hide_render = True
    material = bpy.data.materials.new("M_SeawallShoreRock_" + version)
    material.diffuse_color = (.19, .205, .185, 1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs['Base Color'].default_value = material.diffuse_color
    bsdf.inputs['Roughness'].default_value = .88
    tex = textures(folder)
    # Blender's preview uses the same original mineral texture as Unreal.
    coord = material.node_tree.nodes.new('ShaderNodeTexCoord')
    sample = material.node_tree.nodes.new('ShaderNodeTexImage')
    sample.image = bpy.data.images[tex[0]['image']]
    sample.projection = 'BOX'
    sample.projection_blend = .2
    material.node_tree.links.new(coord.outputs['Generated'], sample.inputs['Vector'])
    mix = material.node_tree.nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 1
    mix.inputs[2].default_value = (.34, .36, .33, 1)
    material.node_tree.links.new(sample.outputs['Color'], mix.inputs[1])
    material.node_tree.links.new(mix.outputs[0], bsdf.inputs['Base Color'])
    rocks, assets = [], []
    for index in range(6):
        obj = rock_geometry(index)
        asset_name = f"SM_SeawallRock_{index:02d}"
        obj.name = asset_name + '_' + version
        for c in list(obj.users_collection): c.objects.unlink(obj)
        collection.objects.link(obj)
        obj.data.materials.append(material)
        obj['pipeline_owner'] = OWNER
        obj['collision'] = 'none'
        rocks.append(obj)
        path = folder / (asset_name + '.fbx')
        mesh = obj.data.copy()
        mesh.transform(Matrix.Rotation(-math.pi / 2, 4, 'Z'))
        temporary = bpy.data.objects.new('ShoreExportTemporary', mesh)
        collection.objects.link(temporary)
        bpy.ops.object.select_all(action='DESELECT')
        temporary.select_set(True)
        bpy.context.view_layer.objects.active = temporary
        try:
            bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
                mesh_smooth_type='FACE', use_triangles=True, use_space_transform=False,
                axis_forward='Y', axis_up='Z', global_scale=1, apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_NONE', bake_space_transform=True,
                bake_anim=False, add_leaf_bones=False, path_mode='STRIP')
        finally:
            bpy.data.objects.remove(temporary, do_unlink=True)
            bpy.data.meshes.remove(mesh)
        points = np.array([(v.co.y * 100, v.co.x * 100, v.co.z * 100) for v in obj.data.vertices])
        assets.append(dict(name=asset_name, blender_object=obj.name, fbx=path.relative_to(ROOT).as_posix(), sha256=sha(path),
            bounds_min_cm=points.min(0).tolist(), bounds_max_cm=points.max(0).tolist(),
            triangles=len(obj.data.polygons)))
        obj.hide_render = True
        obj.hide_set(True)
    # Sample the actual preserved terrain and all route surfaces. No rock may
    # enter the route buffer. Decorative rocks are not new contact geometry.
    terrain_vertices, terrain_faces = [], []
    pavement_vertices, pavement_faces = [], []
    for obj in scene.objects:
        if obj.type != 'MESH': continue
        is_terrain = obj.name.startswith('SM_Terrain_')
        is_pavement = obj.name.startswith(('SM_Pavement_', 'SM_Pedestrian_', 'SM_Route_'))
        if not is_terrain and not is_pavement: continue
        vertices, faces = (terrain_vertices, terrain_faces) if is_terrain else (pavement_vertices, pavement_faces)
        start = len(vertices)
        vertices.extend(tuple(obj.matrix_world @ v.co) for v in obj.data.vertices)
        faces.extend(tuple(start + i for i in p.vertices) for p in obj.data.polygons)
    ground = BVHTree.FromPolygons(terrain_vertices, terrain_faces)
    paved = BVHTree.FromPolygons(pavement_vertices, pavement_faces)
    route = np.asarray(json.loads((ROOT/'data/derived/paved-circuit-runtime.json').read_text())['points_local_m'])
    lengths = np.linalg.norm(np.diff(route, axis=0), axis=1)
    chain = np.r_[0, np.cumsum(lengths)]
    # M2: the 400 m pilot and three shore views; full coast treatment is M3.
    bands = [(0, 110), (1850, 2050), (5200, 5600), (6040, 6330), (7400, 7580)]
    rng = random.Random(661923)
    instances = []
    occupied = set()
    for i in range(0, len(route)-1, 4):
        s = float(chain[i])
        if not any(a <= s <= b for a, b in bands): continue
        centre = route[i]
        for _ in range(10):
            angle, distance = rng.uniform(0, math.tau), rng.uniform(5, 37)
            x, y = centre[:2] + np.array([math.cos(angle), math.sin(angle)]) * distance
            cell = (math.floor(x/1.6), math.floor(y/1.6))
            if cell in occupied: continue
            hit, normal, _, _ = ground.ray_cast(Vector((x,y,30)), Vector((0,0,-1)), 45)
            if hit is None or hit.z < -.4 or hit.z > 3.2 or normal.z < .90: continue
            size = rng.uniform(.22, .78)
            variant = rng.randrange(len(rocks))
            position = [x, y, hit.z - size * .18]
            scale = [size * rng.uniform(.85, 1.2), size * rng.uniform(.8, 1.15), size * rng.uniform(.75, 1.1)]
            radius = max(Vector((v.co.x*scale[0],v.co.y*scale[1],v.co.z*scale[2])).length
                         for v in rocks[variant].data.vertices)
            supports = []
            for j in range(8):
                angle = j*math.tau/8
                foot, foot_normal, _, _ = ground.ray_cast(Vector((x+radius*math.cos(angle),
                    y+radius*math.sin(angle),30)),Vector((0,0,-1)),45)
                if foot is None or foot_normal.z < .85: break
                supports.append(foot.z)
            if len(supports) != 8 or max(supports)-min(supports) > size*.65: continue
            position[2] = min(supports+[hit.z])-size*.12
            closest, _, _, gap = paved.find_nearest(Vector(position), radius + 1.2)
            if closest is not None and gap < radius + 1.2: continue
            occupied.add(cell)
            yaw = rng.uniform(0, 360)
            obj = bpy.data.objects.new(f'SW_ShoreInstance_{len(instances):04d}', rocks[variant].data)
            collection.objects.link(obj)
            obj.location = position
            obj.scale = scale
            obj.rotation_euler.z = math.radians(yaw)
            obj['pipeline_owner'] = OWNER
            obj['collision'] = 'none'
            instances.append(dict(mesh=assets[variant]['name'], position_local_m=position,
                scale=scale, yaw_degrees=yaw, bounds_radius_m=radius, route_station_m=s))
    result = dict(schema_version=1, version=version, input_hashes=inputs,
        source_blend='blender/StanleyPark_Seawall.blend', map='/Game/Maps/StanleyParkSeawall',
        asset_root='/Game/StanleyPark/Seawall/Shore/v_'+version,
        assets=assets, textures=tex, instances=instances, review_bands_m=bands,
        placement='Actual terrain ray hits below 3.2m, minimum 1.2m beyond each rock from all measured path meshes',
        rights='Original procedural rock geometry and mineral textures. No external image or asset.',
        source_limit='Rocks and surface texture are visual interpretations; individual rocks are not surveyed.',
        collision='none', geometry_acceptance=False, visual_acceptance=False)
    manifest_path.write_text(json.dumps(result, indent=2), encoding='utf8')
    (ROOT/'exports/seawall-shore/latest.json').write_text(json.dumps(dict(
        manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=sha(manifest_path)), indent=2))
    bpy.context.view_layer.update()
    return dict(version=version, rock_assets=len(assets), instances=len(instances), manifest=str(manifest_path))


result = build()
