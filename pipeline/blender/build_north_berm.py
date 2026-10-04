"""Place the source-fitted north bridge berm in the editable park scene."""
import json
import hashlib
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
record=json.loads((ROOT/'manifests/lions-gate-north-berm.json').read_text())
path=ROOT/record['output']
if hashlib.sha256(path.read_bytes()).hexdigest()!=record['output_sha256']:raise RuntimeError('Fit hash changed')
data=np.load(path)
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections['SP_06_Landmarks']
for obj in list(collection.objects):
    if obj.get('pipeline_owner')=='landmark_north_berm':
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
name='SM_LionsGate_NorthBermReview'
mesh=bpy.data.meshes.new(name);mesh.from_pydata(data['vertices'],[],data['faces']);mesh.update()
obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);obj.location=data['anchor']
mat=bpy.data.materials.get('M_LionsGate_BermBlockout') or bpy.data.materials.new('M_LionsGate_BermBlockout')
mat.diffuse_color=(.32,.31,.26,1);mat.use_nodes=True
mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=mat.diffuse_color
mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.95
mesh.materials.append(mat)
obj['pipeline_owner']='landmark_north_berm';obj['source_id']='City LiDAR 2022; manifests/lions-gate-north-berm.json'
obj['collision']='none';obj['release_accepted']=False;obj['representation']=record['accuracy']
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(name=name,vertices=len(mesh.vertices),polygons=len(mesh.polygons),accepted=False)
