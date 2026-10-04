"""Author the measured named-feature package without hiding its review limits.

Run after build_cover_blockout.py. Rebuild affected survey bundles to exclude
the exact roof IDs replaced by the new named models. Keep editable sources.
"""
import json
import hashlib
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'manifests/route-sculpture-blockouts.json').read_text(encoding='utf8'))
for row in data['assets']:
    if hashlib.sha256((ROOT/row['mesh_path']).read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Changed route sculpture mesh: '+row['mesh_path'])
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_RouteSculptures')
if collection is None:
    collection=bpy.data.collections.new('SP_06_RouteSculptures');scene.collection.children.link(collection)
owner='route_sculptures_v1'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)

def material(name,color):
    mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color=(*color,1);mat.use_nodes=True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
    return mat

features={x['id']:x for x in data['features']}
created=[]
for row in data['assets']:
    with np.load(ROOT/row['mesh_path']) as geometry:
        vertices=geometry['vertices'];faces=geometry['faces']
        anchor=np.array([*np.mean(vertices[:,:2],axis=0),0.])
        mesh=bpy.data.meshes.new(row['name']);mesh.from_pydata((vertices-anchor).tolist(),[],faces.tolist());mesh.update()
    obj=bpy.data.objects.new(row['name'],mesh);collection.objects.link(obj);obj.location=anchor
    mesh.materials.append(material('M_NamedFeature_'+row['material'],row['color']))
    obj['pipeline_owner']=owner;obj['collision']=row['collision'];obj['release_accepted']=False
    obj['feature_id']=row['feature_id'];obj['landmark']=features[row['feature_id']]['name']
    obj['source_id']='manifests/route-sculpture-blockouts.json'
    obj['collision_reason']=row['collision_reason']
    obj['limits']=features[row['feature_id']]['limits'];created.append(obj.name)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(objects=created,features=list(features),removed_cover_ids=[],
            accepted=False,scope='Four route sculpture silhouettes; measured envelopes, estimated poses; visual and runtime inspection pending')
(ROOT/'evidence/blender-route-sculptures-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
