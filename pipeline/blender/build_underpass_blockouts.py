"""Author M1 underpass meshes in the live Blender scene; never launch Blender.

Run only after the GIS package has been regenerated for the current pavement.
The REF object is an unlocated design envelope, not a finished structure.
"""
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
manifest_path = ROOT / "data/derived/underpass-blockouts.json"
record = json.loads(manifest_path.read_text(encoding="utf8"))
manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
closure_path = ROOT / "data/derived/underpass-closures.json"
closure_hash = None
if closure_path.exists():
    closures = json.loads(closure_path.read_text(encoding="utf8"))
    if closures["underpass_sha256"] != manifest_hash:
        raise RuntimeError("Underpass blockout changed; regenerate its terrain closures after the current terrain cut")
    record["meshes"] += closures["meshes"]
    record["inputs"] += closures["inputs"]
    closure_hash = hashlib.sha256(closure_path.read_bytes()).hexdigest()

checks = record["inputs"] + record["meshes"] + [{"path": record["openings_path"], "sha256": record["openings_sha256"]}]
checks += [{"path": s["survey_path"], "sha256": s["survey_sha256"]} for s in record["sites"]]
for item in checks:
    if hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
        raise RuntimeError(f"Underpass input changed; rebuild GIS sidecar first: {item['path']}")

scene = bpy.data.scenes["StanleyPark_M1"]
bpy.context.window.scene = scene
collection = bpy.data.collections.get("SP_08_Underpasses")
if collection is None:
    collection = bpy.data.collections.new("SP_08_Underpasses")
    scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get("underpass_stage_owner") == "underpass_blockouts" or obj.get("pipeline_owner") == "underpass_blockouts":
        old_mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

created = []
for item in record["meshes"]:
    with np.load(ROOT / item["path"]) as package:
        vertices, faces, anchor = package["vertices"], package["faces"], package["anchor"]
    if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
        raise RuntimeError(f"Invalid underpass mesh: {item['name']}")
    mesh = bpy.data.meshes.new(item["name"])
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(item["name"], mesh)
    collection.objects.link(obj)
    obj.location = anchor
    role = item["role"]
    material_kind = "Pavement" if role.startswith("Floor") else "Deck" if role == "Deck" else "Concrete"
    color = {"Pavement": (.16, .17, .18, 1), "Deck": (.28, .29, .30, 1), "Concrete": (.48, .47, .43, 1)}[material_kind]
    material_name = "M_Underpass_" + material_kind
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.diffuse_color = color
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .88
    mesh.materials.append(material)
    obj["underpass_stage_owner"] = "underpass_blockouts"
    # Shared export selects all meshes with pipeline_owner, regardless of name
    # or hide_render. Keep the unresolved reference out of that exact contract.
    if not item["reference_only"]:
        obj["pipeline_owner"] = "underpass_blockouts"
    obj["collision"] = item["collision"]
    obj["source_manifest"] = manifest_path.relative_to(ROOT).as_posix()
    obj["source_manifest_sha256"] = manifest_hash
    obj["source_mesh_sha256"] = item["sha256"]
    if closure_hash:
        obj["closure_manifest_sha256"] = closure_hash
    obj["dimension_register"] = "manifests/underpass-dimensions.json"
    obj["accuracy_status"] = "M1 estimate; deck top informed by City 2022 LiDAR; interior not surveyed"
    obj["source_id"] = "City 2022 LiDAR; City 2001 Chilco design reference; editable M1 dimensions"
    obj["site"] = item["site"]
    obj["release_accepted"] = False
    obj["reference_only"] = item["reference_only"]
    obj["export"] = not item["reference_only"]
    if item["reference_only"]:
        obj.display_type = "WIRE"
        obj.hide_render = True
        obj.hide_set(True)
    created.append(obj.name)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "blender/StanleyPark_Blockout.blend"))
result = {"objects": created, "mesh_count": len(created), "visual_inspection": "pending",
          "terrain_cavity_integration": "required before runtime acceptance", "release_accepted": False}
