"""Keep generic survey roof masses only where no live named replacement exists."""
import hashlib
import json
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
present={o.get('feature_id') for o in scene.objects if o.type=='MESH' and o.get('pipeline_owner')}
exclusions=set();sources=[]
for path in sorted((ROOT/'manifests').glob('*.json')):
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    features=data.get('features',[]) if isinstance(data,dict) else []
    if not isinstance(features,list):continue
    selected=[f for f in features if isinstance(f,dict) and f.get('id') in present and f.get('replace_cover_ids')]
    if not selected:continue
    exclusions.update(i for f in selected for i in f['replace_cover_ids'])
    sources.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
cover=json.loads((ROOT/'data/derived/cover-blockout.json').read_text())
collection=bpy.data.collections['SP_05_SurveyCover']
material=bpy.data.materials['M_SurveyBuildingMass']
by_tile={}
for item in cover['buildings']:
    by_tile.setdefault('_'.join(item['id'].split('_')[:3]),[]).append(item)
count=0
for tile,items in sorted(by_tile.items()):
    name='SM_BuildingMass_'+tile
    old=bpy.data.objects.get(name)
    if old:
        if old.get('pipeline_owner')!='cover':raise RuntimeError('Cannot replace a non-pipeline roof mass')
        mesh=old.data;bpy.data.objects.remove(old,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    items=[i for i in items if i['id'] not in exclusions]
    if not items:continue
    vertices=[];faces=[]
    for item in items:
        outline=item['outline'];n=len(outline);offset=len(vertices)
        vertices.extend([[*p,item['base_m']] for p in outline]);vertices.extend([[*p,item['roof_m']] for p in outline])
        faces.append(tuple(offset+n+i for i in range(n)))
        for i in range(n):
            j=(i+1)%n;faces.append((offset+i,offset+j,offset+n+j,offset+n+i))
    anchor=np.array([*items[0]['outline'][0],0.])
    mesh=bpy.data.meshes.new(name);mesh.from_pydata((np.asarray(vertices)-anchor).tolist(),[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);obj.location=anchor;mesh.materials.append(material)
    obj['pipeline_owner']='cover';obj['collision']='none';obj['release_accepted']=False
    obj['source_id']='City 2022 class-6 roof envelopes, excluding live named replacements'
    obj['named_feature_exclusions']=json.dumps(sorted(exclusions));obj['cover_source_ids']=json.dumps([i['id'] for i in items])
    count+=len(items)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(excluded_source_roofs=sorted(exclusions),remaining_source_roofs=count,source_manifests=sources,
            method='Only feature IDs present in live authored meshes can replace a generic roof',accepted=False)
(ROOT/'evidence/named-cover-reconciliation.json').write_text(json.dumps(result,indent=2)+'\n')
