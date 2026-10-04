"""Bake whole-tree far silhouettes from the authored Blender meshes.

The atlas has six 512 x 1024 cells in a 2048 square image. Each cell shows a
complete tree at its true 20 m local height. It is not a scaled twig texture.
"""
import hashlib
import math
import shutil
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from seawall_tree_geometry import Geometry, tree_geometry
from seawall_tree_textures import write_image


def billboard_geometry(kind, variant):
    g = Geometry()
    x, y = variant, 0 if kind == "conifer" else 1
    # The bake uses an exact 10.5 x 21 m orthographic frame. The small transparent
    # frame border keeps the crown from touching adjacent atlas cells.
    uv_min = np.array([x/4, y/2])
    uv_max = uv_min + np.array([.25,.5])
    for angle in (0,math.pi/3,math.pi*2/3):
        across = np.array([math.cos(angle),math.sin(angle),0])
        start = len(g.vertices)
        for u,v in ((0,0),(1,0),(1,1),(0,1)):
            point = across*((u-.5)*10.5)+np.array([0,0,-.5+v*21])
            g.vertex(point,uv_min+(uv_max-uv_min)*np.array([u,v]))
        g.face((start,start+1,start+2,start+3),2)
    return g


def far_material(image, version):
    material=bpy.data.materials.new("M_SW_FarTrees_"+version)
    material.use_nodes=True
    shader=material.node_tree.nodes.get("Principled BSDF")
    tex=material.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image=image
    tint=material.node_tree.nodes.new("ShaderNodeMixRGB")
    tint.blend_type="MULTIPLY"
    tint.inputs[0].default_value=1
    tint.inputs[2].default_value=(.45,.45,.45,1)
    material.node_tree.links.new(tex.outputs["Color"],tint.inputs[1])
    material.node_tree.links.new(tint.outputs["Color"],shader.inputs["Base Color"])
    material.node_tree.links.new(tex.outputs["Alpha"],shader.inputs["Alpha"])
    shader.inputs["Roughness"].default_value=.95
    material.surface_render_method="DITHERED"
    material.use_backface_culling=False
    material.diffuse_color=(.032,.070,.017,1)
    spec=dict(role="whole_tree",texture=image.name,masked=True,two_sided=True,
              roughness=.95,opacity_mask_clip=.24,wind=False,color_scale=.45)
    return material,spec


def bake(directory, version, materials, cache=None):
    if cache:
        source,prior=cache
        item=next(t for t in prior["textures"] if t["role"]=="whole_tree_mask")
        root=Path(__file__).resolve().parents[2]
        old_path=root/item["path"]
        if hashlib.sha256(old_path.read_bytes()).hexdigest()!=item["sha256"]:
            raise RuntimeError("Cached tree atlas hash mismatch")
        name="T_SW_FarTrees_"+version
        path=directory/(name+".png")
        shutil.copyfile(old_path,path)
        image=bpy.data.images.load(str(path),check_existing=False)
        image.name=name
        image.colorspace_settings.name="Non-Color"
        image.pack()
        captures=prior["far_tree_captures"]
        for capture in captures:
            old=source.parent/capture["path"]
            if hashlib.sha256(old.read_bytes()).hexdigest()!=capture["sha256"]:
                raise RuntimeError("Cached tree capture hash mismatch")
            shutil.copyfile(old,directory/capture["path"])
        record=dict(item,name=name,path=path)
        material,spec=far_material(image,version)
        return material,record,spec,captures
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new("SP_TreeFarBake_"+version)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    bpy.context.window.scene = scene
    world = bpy.data.worlds.new("SWTreeBakeWorld_"+version)
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.66,.70,.74,1)
    world.node_tree.nodes["Background"].inputs[1].default_value=.8
    scene.world=world
    light_data=bpy.data.lights.new("SWTreeBakeSoftbox_"+version,"AREA")
    light_data.energy=35000
    light_data.shape="DISK"
    light_data.size=35
    light=bpy.data.objects.new(light_data.name,light_data)
    scene.collection.objects.link(light)
    light.location=(-12,-20,32)
    light.rotation_euler=(Vector((0,0,10))-light.location).to_track_quat('-Z','Y').to_euler()
    camera_data=bpy.data.cameras.new("SWTreeBakeCamera_"+version)
    camera=bpy.data.objects.new(camera_data.name,camera_data)
    scene.collection.objects.link(camera)
    camera.location=(0,-40,10)
    camera.rotation_euler=(Vector((0,0,10))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.type="ORTHO"
    camera_data.ortho_scale=21
    scene.camera=camera
    scene.render.engine="CYCLES"
    scene.cycles.samples=24
    scene.cycles.use_denoising=True
    scene.cycles.transparent_max_bounces=24
    scene.render.resolution_x=512
    scene.render.resolution_y=1024
    scene.render.resolution_percentage=100
    scene.render.film_transparent=True
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGBA"
    scene.view_settings.view_transform="Standard"
    atlas=np.zeros((2048,2048,4),np.float32)
    captures=[]
    try:
        for kind in ("conifer","broadleaf"):
            for variant in range(3):
                geometry=tree_geometry(kind,variant,0)
                mesh=bpy.data.meshes.new(f"FarBake_{kind}_{variant}_{version}")
                mesh.from_pydata(geometry.vertices,[],geometry.faces)
                mesh.update()
                uv=mesh.uv_layers.new(name="UVMap")
                for mat in materials:mesh.materials.append(mat)
                for face,slot in zip(mesh.polygons,geometry.slots):
                    face.material_index=slot
                    face.use_smooth=slot==0
                for loop in mesh.loops:
                    uv.data[loop.index].uv=geometry.uvs[loop.vertex_index]
                obj=bpy.data.objects.new(mesh.name,mesh)
                scene.collection.objects.link(obj)
                path=directory/f"far-source-{kind}-{variant}.png"
                scene.render.filepath=str(path)
                bpy.ops.render.render(write_still=True)
                rendered=bpy.data.images.load(str(path),check_existing=False)
                values=np.empty(512*1024*4,np.float32)
                rendered.pixels.foreach_get(values)
                values=values.reshape((1024,512,4))
                # Blender image pixels are scene-linear after PNG decode.
                y=0 if kind=="conifer" else 1024
                atlas[y:y+1024,variant*512:(variant+1)*512]=values
                captures.append(dict(kind=kind,variant=variant,path=path.name,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                obj.hide_render=True
        # Keep a leaf-colored transparent border to avoid dark mip halos.
        atlas[atlas[:,:,3]<.001,:3]=(.052,.11,.025)
        image,record=write_image(directory,"T_SW_FarTrees_"+version,atlas,"whole_tree_mask")
        material,spec=far_material(image,version)
        return material,record,spec,captures
    finally:
        bpy.context.window.scene=previous
