"""Import the source-fitted Siwash connector after the west landmark stage."""
import hashlib
import json
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'manifests/siwash-approach-blockout.json').read_text())
for item in data['assets']:
    if hashlib.sha256((ROOT/item['mesh_path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Stale approach mesh')
for item in data['features'][0]['measured']['terrain_inputs']:
    if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Terrain changed: repeat the Siwash approach geometry review')
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_SiwashApproach')
if collection is None:
    collection=bpy.data.collections.new('SP_06_SiwashApproach');scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get('pipeline_owner')=='siwash_approach_v1':
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
for row in data['assets']:
    p=np.load(ROOT/row['mesh_path']);v=p['vertices'];f=p['faces'];anchor=np.array([*v[:,:2].mean(0),0.])
    mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata((v-anchor).tolist(),[],f.tolist());mesh.update()
    obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=anchor
    name='M_NamedFeature_'+row['material'];mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color=(*row['color'],1);mat.use_nodes=True;mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*row['color'],1);mesh.materials.append(mat)
    obj['pipeline_owner']='siwash_approach_v1';obj['collision']=row['collision'];obj['feature_id']=row['feature_id'];obj['source_id']='manifests/siwash-approach-blockout.json'
    obj['collision_reason']=row['collision_reason'];obj['limits']=data['features'][0]['limits'];obj['release_accepted']=False
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
(ROOT/'evidence/blender-siwash-approach-build.json').write_text(json.dumps(dict(objects=[a['name'] for a in data['assets']],accepted=False),indent=2)+'\n')
