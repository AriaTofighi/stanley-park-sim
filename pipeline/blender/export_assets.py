"""Explicit legacy FBX export with a measured axis/scale fixture.

Blender authoring stays east/north/up metres. Disposable export copies rotate
to (north,-east,up). FBX applies metres -> centimetres once. Unreal's legacy
FBX data converter flips Y to its left-handed frame, yielding north/east/up.
Unreal import must disable additional scene/unit conversion and check bounds.
"""
from pathlib import Path
import hashlib
import json
import math
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene
export_dir = ROOT / "exports/fbx"
export_dir.mkdir(parents=True, exist_ok=True)
records = []
previous_path=ROOT/'manifests/blender-export.json'
previous={r['name']:r for r in json.loads(previous_path.read_text())['assets']} if previous_path.exists() else {}
exporter_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
cache_hits=0
objects = sorted([o for o in scene.objects if o.type == "MESH" and o.get("pipeline_owner")],
                 key=lambda obj: (not obj.name.startswith("SM_AxisFixture"), obj.name))
rotation = Matrix.Rotation(-math.pi / 2, 4, "Z")


def export_fingerprint(source):
    """Hash all authored static mesh data used by this export contract."""
    digest=hashlib.sha256()
    digest.update(json.dumps(dict(exporter=exporter_hash,blender=bpy.app.version_string,
        unit_scale=scene.unit_settings.scale_length,
        materials=[(m.name,list(m.diffuse_color)) for m in source.data.materials])).encode())
    for values,attribute,count,dtype in [(source.data.vertices,'co',3,np.float32),
        (source.data.loops,'vertex_index',1,np.int32),(source.data.polygons,'loop_start',1,np.int32),
        (source.data.polygons,'loop_total',1,np.int32),(source.data.polygons,'material_index',1,np.int32),
        (source.data.polygons,'use_smooth',1,np.bool_), (source.data.corner_normals,'vector',3,np.float32)]:
        buffer=np.empty(len(values)*count,dtype=dtype);values.foreach_get(attribute,buffer);digest.update(buffer.tobytes())
    for layer in source.data.color_attributes:
        digest.update((layer.name+layer.domain+layer.data_type).encode())
        buffer=np.empty(len(layer.data)*4,dtype=np.float32);layer.data.foreach_get('color',buffer);digest.update(buffer.tobytes())
    for layer in source.data.uv_layers:
        digest.update((layer.name+str(layer.active_render)).encode())
        buffer=np.empty(len(layer.data)*2,dtype=np.float32);layer.data.foreach_get('uv',buffer);digest.update(buffer.tobytes())
    return digest.hexdigest()

for source in objects:
    # All placed environment objects have translation only. Kit transforms were applied.
    if any(abs(v - 1) > 1e-6 for v in source.scale) or source.rotation_euler.to_matrix() != Matrix.Identity(3):
        raise RuntimeError(f"Unapplied source transform: {source.name}")
    if source.modifiers:
        raise RuntimeError(f"Bake the export mesh modifiers before this static contract: {source.name}")
    fingerprint=export_fingerprint(source)
    path = export_dir / (source.name + ".fbx")
    old=previous.get(source.name,{})
    cached=old.get('source_export_fingerprint')==fingerprint and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==old.get('sha256')
    cache_hits+=int(cached)
    if not cached:
        source_local = source.data.copy()
        source_local.transform(rotation)
        temporary = bpy.data.objects.new("Export_" + source.name, source_local)
        scene.collection.objects.link(temporary)
        bpy.ops.object.select_all(action="DESELECT")
        temporary.select_set(True)
        bpy.context.view_layer.objects.active = temporary
        try:
            bpy.ops.export_scene.fbx(
                filepath=str(path), use_selection=True, object_types={"MESH"},
                use_mesh_modifiers=True, mesh_smooth_type="FACE", use_triangles=True,
                use_space_transform=False, axis_forward="Y", axis_up="Z",
                global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE",
                bake_space_transform=True, bake_anim=False, add_leaf_bones=False,
                # Measured UE 5.8 import retains these values as shader input;
                # it does not decode sRGB. Export linear values once.
                path_mode="STRIP", use_custom_props=False, colors_type="LINEAR",
            )
        finally:
            bpy.data.objects.remove(temporary, do_unlink=True)
            bpy.data.meshes.remove(source_local)
    # FBX/Unreal omit isolated survey vertices that belong to no polygon.
    # Compare the actual rendered mesh, while retaining their count for review.
    used_vertices = sorted({index for poly in source.data.polygons for index in poly.vertices})
    coordinates = [source.data.vertices[index].co for index in used_vertices]
    if not coordinates:
        raise RuntimeError(f"Export source has no polygon vertices: {source.name}")
    # Predict the final asset-space bounds independently from the FBX exporter.
    values = [(v.y * 100, v.x * 100, v.z * 100) for v in coordinates]
    minimum = [min(v[axis] for v in values) for axis in range(3)]
    maximum = [max(v[axis] for v in values) for axis in range(3)]
    category = "Kit" if source.get("kit_asset") else "Generated"
    color_range=None
    if source.data.color_attributes:
        attribute=source.data.color_attributes.active_color
        if attribute is None or attribute.domain!='POINT':
            raise ValueError('Static color contract requires one active POINT color layer')
        color_buffer=np.empty(len(attribute.data)*4,dtype=np.float32)
        attribute.data.foreach_get('color',color_buffer)
        colors=color_buffer.reshape(-1,4)[used_vertices,:3]
        color_range=dict(minimum=colors.min(axis=0).tolist(),maximum=colors.max(axis=0).tolist())
    records.append({
        "name": source.name, "fbx": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_export_fingerprint": fingerprint,
        "fbx_reused": cached,
        "asset_path": f"/Game/StanleyPark/{category}/{source.name}",
        "position_cm": [source.location.y * 100, source.location.x * 100, source.location.z * 100],
        "bounds_min_cm": minimum, "bounds_max_cm": maximum,
        "materials": [mat.name for mat in source.data.materials],
        "used_materials": sorted({source.data.materials[poly.material_index].name for poly in source.data.polygons}),
        "material_colors": [list(mat.diffuse_color) for mat in source.data.materials],
        "material_two_sided": {mat.name: bool(mat.get("sp_two_sided", False)) or "Water" in mat.name
                               for mat in source.data.materials},
        "vertex_colors": bool(source.data.color_attributes),
        "vertex_color_space": "linear", "vertex_color_range": color_range,
        "collision": source.get("collision", "none"),
        "place_in_level": not source.get("kit_asset", False),
        "source_id": source.get("source_id", "blockout"),
        "source_object": source.name,
        "vertices": len(source.data.vertices), "polygons": len(source.data.polygons),
        "unused_source_vertices": len(source.data.vertices)-len(used_vertices),
    })

manifest = {"schema_version": 1, "blender_version": bpy.app.version_string,
            "source_blend": "blender/StanleyPark_Blockout.blend",
            "origin_sha256": hashlib.sha256((ROOT / "manifests/world-origin.json").read_bytes()).hexdigest(),
            "unreal_contract": "legacy_fbx_convert_scene_false_convert_units_false_north_east_up_cm",
            "assets": records}
(ROOT / "manifests/blender-export.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
result = {"asset_count": len(records), "manifest": "manifests/blender-export.json",
          "fbx_cache_hits": cache_hits,
          "fixture": "SM_AxisFixture: min (0,0,0), max (200,100,300) cm",
          "import_verified": False}
