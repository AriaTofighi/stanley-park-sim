"""Stage physical dated gate frames. Keep their collision enabled."""
import json
import hashlib
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
path='manifests/maze-gate-blockouts.json'
data=json.loads((ROOT/path).read_text(encoding='utf8'))
if not data['checks_pass']:raise ValueError('Gate walking reference fails geometric clearance')
for row in data['assets']:
    if hashlib.sha256((ROOT/row['mesh_path']).read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Changed gate mesh: '+row['mesh_path'])
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_07_PhysicalGates')
if collection is None:
    collection=bpy.data.collections.new('SP_07_PhysicalGates');scene.collection.children.link(collection)
owner='maze_gate_v1'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
created=[]
mat=bpy.data.materials.get('M_PhysicalGateSteel') or bpy.data.materials.new('M_PhysicalGateSteel')
mat.diffuse_color=(.59,.62,.60,1);mat.use_nodes=True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.59,.62,.60,1)
mat.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.35
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.65
for row in data['assets']:
    with np.load(ROOT/row['mesh_path']) as geo:
        vertices=geo['vertices'];anchor=np.array([*vertices[:,:2].mean(0),0.])
        mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata((vertices-anchor).tolist(),[],geo['faces'].tolist());mesh.update()
    obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=anchor;mesh.materials.append(mat)
    for key,value in dict(pipeline_owner=owner,collision='complex',source_id=path,feature_id=row['feature_id'],
        landmark=row['feature_id']+' maze-gate existing-condition blockout',release_accepted=False,
        source_period=data['source_period'],limits='Estimated dimensions; dated existing condition; current field state not certified',collision_reason=row['collision_reason']).items():obj[key]=value
    created.append(obj.name)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
(ROOT/'evidence/blender-maze-gates-build.json').write_text(json.dumps(dict(objects=created,walking_paths='manifests/maze-gate-blockouts.json sites[].walking_path',application_review='pending',release_accepted=False),indent=2)+'\n',encoding='utf8')
