"""Stage the located Lumberman facility package. Root owns terrain cuts."""
import json
import hashlib
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
path='manifests/lumberman-facility-blockouts.json'
data=json.loads((ROOT/path).read_text(encoding='utf8'))
for row in data['assets']:
    if hashlib.sha256((ROOT/row['mesh_path']).read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Changed facility mesh: '+row['mesh_path'])
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_LumbermanFacilities')
if collection is None:
    collection=bpy.data.collections.new('SP_06_LumbermanFacilities');scene.collection.children.link(collection)
owner='lumberman_facility_v1'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
created=[]
for row in data['assets']:
    with np.load(ROOT/row['mesh_path']) as geo:
        vertices=geo['vertices'];anchor=np.array([*vertices[:,:2].mean(0),0])
        mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata((vertices-anchor).tolist(),[],geo['faces'].tolist());mesh.update()
    obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=anchor
    name='M_LumbermanFacility_'+row['material'];mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color=(*row['color'],1);mat.use_nodes=True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*row['color'],1)
    mesh.materials.append(mat)
    for key,value in dict(pipeline_owner=owner,collision=row['collision'],feature_id=row['feature_id'],source_id=path,
                          landmark=data['features'][0]['name'],limits=data['features'][0]['limits'],release_accepted=False,
                          collision_reason=row['collision_reason']).items():obj[key]=value
    created.append(obj.name)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
(ROOT/'evidence/blender-lumberman-facilities-build.json').write_text(json.dumps(dict(objects=created,
    integration_required=data['required_integration'],application_review='pending',release_accepted=False),indent=2)+'\n',encoding='utf8')
