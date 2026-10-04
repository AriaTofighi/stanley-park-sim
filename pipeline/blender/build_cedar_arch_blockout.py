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
data=json.loads((ROOT/'manifests/cedar-arch-blockout.json').read_text(encoding='utf8'))
for row in data['assets']:
    if hashlib.sha256((ROOT/row['mesh_path']).read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Changed cedar arch mesh: '+row['mesh_path'])
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_CedarArch')
if collection is None:
    collection=bpy.data.collections.new('SP_06_CedarArch');scene.collection.children.link(collection)
owner='cedar_arch_v1'
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
    obj['source_id']='manifests/cedar-arch-blockout.json'
    obj['collision_reason']=row['collision_reason']
    obj['limits']=features[row['feature_id']]['limits'];created.append(obj.name)

# Preserve other building masses and remove only positively identified IDs.
cover=json.loads((ROOT/'data/derived/cover-blockout.json').read_text(encoding='utf8'))
exclusions={x for f in data['features'] for x in f['replace_cover_ids']}
tiles={'_'.join(x.split('_')[:3]) for x in exclusions}
# Keep exclusions from the previous named-feature stage when rebuilding tiles.
for previous_name in ['named-feature-blockouts','named-building-blockouts','named-waterfront-blockouts']:
    previous=json.loads((ROOT/f'manifests/{previous_name}.json').read_text(encoding='utf8'))
    exclusions.update(x for f in previous['features'] for x in f.get('replace_cover_ids',[]))
cover_collection=bpy.data.collections['SP_05_SurveyCover']
for tile in sorted(tiles):
    name='SM_BuildingMass_'+tile
    old=bpy.data.objects.get(name)
    if old:
        mesh=old.data;bpy.data.objects.remove(old,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    items=[x for x in cover['buildings'] if '_'.join(x['id'].split('_')[:3])==tile and x['id'] not in exclusions]
    if not items:continue
    vertices=[];faces=[]
    for item in items:
        outline=item['outline'];n=len(outline);offset=len(vertices)
        vertices.extend([[*p,item['base_m']] for p in outline]);vertices.extend([[*p,item['roof_m']] for p in outline])
        faces.append(tuple(offset+n+i for i in range(n)))
        for i in range(n):j=(i+1)%n;faces.append((offset+i,offset+j,offset+n+j,offset+n+i))
    anchor=np.array([*items[0]['outline'][0],0.]);mesh=bpy.data.meshes.new(name)
    mesh.from_pydata((np.asarray(vertices)-anchor).tolist(),[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);cover_collection.objects.link(obj);obj.location=anchor
    mesh.materials.append(material('M_SurveyBuildingMass',(.43,.43,.41)))
    obj['pipeline_owner']='cover';obj['collision']='none';obj['release_accepted']=False
    obj['source_id']='City 2022 building classes; named-feature exclusions applied'
    obj['named_feature_exclusions']=json.dumps(sorted(exclusions))

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(objects=created,features=list(features),removed_cover_ids=sorted(exclusions),
            accepted=False,scope='Cedar arch observed members; fourth member remains unresolved; visual and runtime inspection pending')
(ROOT/'evidence/blender-cedar-arch-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
