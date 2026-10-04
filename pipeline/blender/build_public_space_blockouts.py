"""Stage editable public-space patches; root runs this in the live Blender.

Reference boundaries remain hidden curves at source XY / unknown Z. They are
not surface meshes and are not counted as completed terrain forms.
"""
from pathlib import Path
import hashlib
import json

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OWNER = "public_space_blockouts_v1"
manifest_path = ROOT / "data/derived/public-spaces/public-space-meshes.json"
record = json.loads(manifest_path.read_text(encoding="utf8"))
manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
for item in record["source_inputs"] + record["terrain_inputs"] + record["exclusion_mesh_inputs"] + record["meshes"]:
    if hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
        raise RuntimeError(f"Public-space source changed; rebuild first: {item['path']}")

scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene


def collection(name):
    value = bpy.data.collections.get(name)
    if value is None:
        value = bpy.data.collections.new(name)
        scene.collection.children.link(value)
    for obj in list(value.objects):
        if obj.get("pipeline_owner") == OWNER:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
    return value


surfaces = collection("SP_08_PublicSpaces")
references = collection("SP_REF_PublicSpaceBoundaries")
references.hide_render = True
created = []
for row in record["meshes"]:
    with np.load(ROOT / row["path"]) as package:
        vertices, faces, anchor = package["vertices"], package["faces"], package["anchor"]
    if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError(f"Invalid public-space mesh: {row['name']}")
    mesh = bpy.data.meshes.new(row["name"])
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(row["name"], mesh)
    surfaces.objects.link(obj)
    obj.location = anchor
    name = "M_PublicSpace_" + row["material_role"]
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = row["material_color"]
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = row["material_color"]
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .9
    mesh.materials.append(material)
    for key in ["component_id", "feature_id", "m1_group", "material_role", "contact_surface", "visual_lift_m", "source_way_id"]:
        obj[key] = row[key]
    obj["pipeline_owner"] = OWNER
    obj["source_id"] = "OSM public-space polygon; City 2022 terrain"
    obj["source_manifest"] = manifest_path.relative_to(ROOT).as_posix()
    obj["source_manifest_sha256"] = manifest_hash
    obj["source_mesh_sha256"] = row["sha256"]
    obj["licence"] = record["licence"]
    obj["attribution"] = json.dumps(record["attribution"], ensure_ascii=False)
    obj["collision"] = "none"
    obj["absolute_accuracy_accepted"] = False
    obj["release_accepted"] = False
    created.append(obj.name)

geometry = json.loads((ROOT / "data/derived/public-spaces/public-space-blockouts-local.geojson").read_text(encoding="utf8"))
reference_ids = {r["component_id"] for r in record["withheld_components"]}
reference_objects = []
for feature in geometry["features"]:
    row, geom = feature["properties"], feature["geometry"]
    if row["component_id"] not in reference_ids:
        continue
    rings = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
    curve = bpy.data.curves.new("REF_PublicSpace_" + row["component_id"], "CURVE")
    curve.dimensions = "3D"
    for ring in rings:
        points = ring[:-1] if geom["type"] == "Polygon" else ring
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, xy in zip(spline.points, points):
            point.co = (xy[0], xy[1], 0., 1.)
        spline.use_cyclic_u = geom["type"] == "Polygon"
    obj = bpy.data.objects.new(curve.name, curve)
    references.objects.link(obj)
    obj["pipeline_owner"] = OWNER
    obj["source_manifest"] = record["source_manifest"]
    obj["source_way_id"] = row["way_id"]
    obj["display_mode"] = row["display_mode"]
    obj["source_reference_z_unknown"] = True
    obj["counted_as_completed_surface"] = False
    obj["collision"] = "none"
    obj.hide_render = True
    obj.hide_set(True)
    reference_objects.append(obj.name)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "blender/StanleyPark_Blockout.blend"))
result = {"mesh_objects": created, "hidden_source_curves": reference_objects,
          "triangles": sum(r["triangles"] for r in record["meshes"]), "collision": "none",
          "visual_inspection": "pending", "full_m1_groups_complete": False, "release_accepted": False}
(ROOT / "evidence/public-spaces/blender-stage.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
