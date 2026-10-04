"""Author editable pedestrian overlays from the source-backed sidecar manifest.

Run through the existing live Blender MCP workflow. This stage is intentionally
separate from the shared terrain/route authoring stage. It does not move the
view, run an engine test, or modify the bicycle pavement.
"""
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
manifest_path = ROOT / "data/routes/derived/pedestrian-surfaces.json"
record = json.loads(manifest_path.read_text(encoding="utf8"))
manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

# Validate all provenance before replacing any existing objects.
for item in record["terrain_inputs"] + record["meshes"]:
    if hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
        raise RuntimeError(f"Pedestrian input changed; rebuild before authoring: {item['path']}")
if hashlib.sha256((ROOT / record["network_path"]).read_bytes()).hexdigest() != record["network_sha256"]:
    raise RuntimeError("Pedestrian graph changed; rebuild its surface sidecar first")

scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene
collection = bpy.data.collections.get("SP_07_PedestrianSurfaces")
if collection is None:
    collection = bpy.data.collections.new("SP_07_PedestrianSurfaces")
    scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get("pipeline_owner") == "pedestrian_overlays":
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

created = []
for item in record["meshes"]:
    with np.load(ROOT / item["path"]) as package:
        vertices, faces, anchor = package["vertices"], package["faces"], package["anchor"]
    if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
        raise RuntimeError(f"Invalid pedestrian source mesh {item['name']}")
    mesh = bpy.data.meshes.new(item["name"])
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(item["name"], mesh)
    collection.objects.link(obj)
    obj.location = anchor
    material_name = "M_Pedestrian_" + item["category"]
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.diffuse_color = item["material_color"]
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = item["material_color"]
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .85
    mesh.materials.append(material)
    obj["pipeline_owner"] = "pedestrian_overlays"
    obj["collision"] = "none"
    obj["source_id"] = "OpenStreetMap candidate pedestrian paths; City 2022 terrain"
    obj["source_manifest"] = manifest_path.relative_to(ROOT).as_posix()
    obj["source_manifest_sha256"] = manifest_hash
    obj["source_mesh_sha256"] = item["sha256"]
    obj["source_edge_ids"] = json.dumps(item["source_edge_ids"])
    obj["width_register"] = "manifests/pedestrian-dimensions.json"
    obj["surface_category"] = item["category"]
    obj["contact_surface"] = item["contact_surface"]
    obj["visual_lift_m"] = item["visual_lift_m"]
    obj["release_accepted"] = False
    obj["licence"] = "ODbL-1.0 pedestrian data; OGL Vancouver terrain"
    created.append(obj.name)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "blender/StanleyPark_Blockout.blend"))
result = {"objects": created, "mesh_count": len(created), "triangles": sum(x["triangles"] for x in record["meshes"]),
          "collision": "none", "visual_inspection": "pending", "release_accepted": False}
