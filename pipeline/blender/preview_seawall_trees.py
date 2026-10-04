"""Render the actual tree library in an isolated Blender review scene."""
import hashlib
import importlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import seawall_tree_geometry
import seawall_tree_textures
importlib.reload(seawall_tree_geometry)
importlib.reload(seawall_tree_textures)
tree_geometry=seawall_tree_geometry.tree_geometry
create_textures=seawall_tree_textures.create_textures
create_materials=seawall_tree_textures.create_materials


def preview(capture_id="seawall-tree-detail-v2-01",kind=None,variant=0,lod=0,rider=False):
    if Path(bpy.data.filepath).resolve()!=(ROOT/"blender/StanleyPark_Seawall.blend").resolve():
        raise RuntimeError("Use the separate Seawall blend")
    directory=ROOT/"exports/seawall-trees"/"texture-review"
    directory.mkdir(parents=True,exist_ok=True)
    output=ROOT/"evidence"/(capture_id+".png")
    if output.exists():
        raise FileExistsError(output)
    previous=bpy.context.window.scene
    scene=bpy.data.scenes.new("SP_TreeTextureReview_"+capture_id)
    scene.unit_settings.system="METRIC"
    scene.unit_settings.scale_length=1
    bpy.context.window.scene=scene
    images,texture_records=create_textures(directory,capture_id)
    materials,specs=create_materials(images,capture_id)
    rows=[]
    variants=[(kind,variant)] if kind else [(k,v) for k in ("conifer","broadleaf") for v in range(3)]
    for index,(k,v) in enumerate(variants):
        geometry=tree_geometry(k,v,lod)
        mesh=bpy.data.meshes.new("Preview_"+k+str(v))
        mesh.from_pydata(geometry.vertices,[],geometry.faces)
        mesh.update()
        uv=mesh.uv_layers.new(name="UVMap")
        for material in materials:mesh.materials.append(material)
        for face,slot in zip(mesh.polygons,geometry.slots):
            face.material_index=slot
            face.use_smooth=slot!=1
            for loop_index in face.loop_indices:
                uv.data[loop_index].uv=geometry.uvs[mesh.loops[loop_index].vertex_index]
        obj=bpy.data.objects.new(mesh.name,mesh)
        scene.collection.objects.link(obj)
        obj.location=((index%3)*16,(index//3)*28,0)
        rows.append(dict(kind=k,variant=v,lod=lod,triangles=geometry.triangles))
    floor_mesh=bpy.data.meshes.new("ReviewFloor")
    floor_mesh.from_pydata([(-60,-40,-.03),(100,-40,-.03),(100,85,-.03),(-60,85,-.03)],[],[(0,1,2,3)])
    floor=bpy.data.objects.new("ReviewFloor",floor_mesh)
    scene.collection.objects.link(floor)
    ground=bpy.data.materials.new("ReviewGround")
    ground.diffuse_color=(.14,.17,.12,1)
    ground.use_nodes=True
    ground.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(.14,.17,.12,1)
    ground.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value=.95
    floor_mesh.materials.append(ground)
    world=bpy.data.worlds.new("TreeReviewWorld")
    world.use_nodes=True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.44,.48,.52,1)
    world.node_tree.nodes["Background"].inputs[1].default_value=.7
    scene.world=world
    light_data=bpy.data.lights.new("TreeReviewCloudLight","AREA")
    light_data.energy=55000
    light_data.shape="DISK"
    light_data.size=45
    light=bpy.data.objects.new("TreeReviewCloudLight",light_data)
    scene.collection.objects.link(light)
    light.location=(-15,-18,40)
    light.rotation_euler=(Vector((12,12,7))-light.location).to_track_quat('-Z','Y').to_euler()
    camera_data=bpy.data.cameras.new("TreeReviewCamera")
    camera=bpy.data.objects.new("TreeReviewCamera",camera_data)
    scene.collection.objects.link(camera)
    eye,target=((28,-92,27),(16,12,10)) if not kind else ((21,-44,13),(0,0,10))
    if rider:
        eye,target=(8,-23,1.8),(0,0,9)
    camera.location=eye
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.lens=30 if rider else (47 if not kind else 42)
    scene.camera=camera
    scene.render.engine="CYCLES"
    scene.cycles.samples=24
    scene.cycles.use_denoising=True
    scene.cycles.transparent_max_bounces=16
    scene.render.resolution_x=1600
    scene.render.resolution_y=1100
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.filepath=str(output)
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        bpy.context.window.scene=previous
    record=dict(image=output.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                scene=scene.name,models=rows,material_specs=specs,method="Actual Cycles render of Blender source meshes",accepted=False)
    output.with_suffix(".json").write_text(json.dumps(record,indent=2))
    return record
