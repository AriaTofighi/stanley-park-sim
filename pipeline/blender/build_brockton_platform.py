"""Build the two editable platform meshes from the verified fit manifest."""
import json
import hashlib
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
record=json.loads((ROOT/'manifests/brockton-platform.json').read_text())
for item in record['assets']:
    if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Source mesh hash differs')
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections['SP_06_Landmarks']
for obj in list(collection.objects):
    if obj.get('pipeline_owner')=='landmark_brockton_platform':
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
for item in record['assets']:
    data=np.load(ROOT/item['path']);name=item['name']
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(data['vertices'],[],data['faces']);mesh.update()
    obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);obj.location=data['anchor']
    mat_name='M_Brockton_Platform' if 'Walking' in name else 'M_Brockton_WallStone'
    colour=(.21,.22,.21,1.) if 'Walking' in name else (.34,.33,.29,1.)
    mat=bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.diffuse_color=colour;mat.use_nodes=True;mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=colour
    mesh.materials.append(mat);obj['pipeline_owner']='landmark_brockton_platform'
    obj['collision']=record['collision'];obj['release_accepted']=False;obj['source_id']='City LiDAR 2022; manifests/brockton-platform.json'
    obj['limits']=record['scope']
eye,target=Vector((1911,-211,12)),Vector((1894,-188,8))
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        s=area.spaces.active;s.region_3d.view_perspective='PERSP'
        s.region_3d.view_rotation=(target-eye).to_track_quat('-Z','Y');s.region_3d.view_location=target;s.region_3d.view_distance=(target-eye).length
        s.shading.type='SOLID';s.shading.color_type='MATERIAL';s.overlay.show_overlays=False
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(objects=[a['name'] for a in record['assets']],accepted=False,collision='complex')
