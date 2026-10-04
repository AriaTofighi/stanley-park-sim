"""Editable procedural proxies for measured cover; no finished tree/landmark claim."""
import bpy
import numpy as np
import json
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
data=json.loads((ROOT/'data/derived/cover-blockout.json').read_text())
zone_data=json.loads((ROOT/'data/derived/canopy-zone-assignments.json').read_text())
if zone_data['cover_sha256'] != hashlib.sha256((ROOT/'data/derived/cover-blockout.json').read_bytes()).hexdigest():
    raise RuntimeError('Canopy source changed. Rebuild vegetation zone assignments first.')
zone_by_tile={row['tile']:row['clusters'] for row in zone_data['assignments']}
collection=bpy.data.collections.get('SP_05_SurveyCover')
if collection is None:
    collection=bpy.data.collections.new('SP_05_SurveyCover');scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get('pipeline_owner')=='cover':
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
def mat(name,color):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color=(*color,1);m.use_nodes=True
    m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
    return m
group_colors={'HW':(.065,.15,.085),'FDC':(.09,.19,.11),'CW':(.08,.18,.12),
              'BA':(.10,.19,.16),'SS':(.085,.18,.16),'MB':(.22,.31,.10),
              'DR':(.16,.25,.10),'UNKNOWN':(.14,.20,.13)}
canopy_mats={code:mat('M_CanopyGroup_'+code,color) for code,color in group_colors.items()}
building_mat=mat('M_SurveyBuildingMass',(.43,.43,.41))
def create(name,vertices,faces,materials,anchor,face_materials=None):
    if not faces:return
    mesh=bpy.data.meshes.new(name);mesh.from_pydata((np.asarray(vertices)-anchor).tolist(),[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);obj.location=anchor
    for material in materials:mesh.materials.append(material)
    if face_materials is not None:
        for poly,index in zip(mesh.polygons,face_materials):poly.material_index=index
    obj['pipeline_owner']='cover';obj['collision']='none'
    obj['source_id']='Vancouver 2022 LAS class 5/6; procedural envelopes, not accepted 2026 cover'
    if name.startswith('SM_Canopy_'):
        obj['source_id']='Vancouver 2022 LAS canopy clusters; BC VRI dated species-group proxies; see manifests/vegetation-zones.json'
        obj['vegetation_zone_manifest']='manifests/vegetation-zones.json'
    obj['release_accepted']=False
for tile in data['canopy']:
    vertices=[];faces=[];face_materials=[]
    assignments=zone_by_tile[tile['tile']]
    if len(assignments)!=len(tile['points']):raise RuntimeError('Canopy assignment count mismatch')
    for point,assignment in zip(tile['points'],assignments):
        x,y,base,top=point
        if (x,y)!=(assignment['x_m'],assignment['y_m']):raise RuntimeError('Canopy assignment position mismatch')
        code=assignment['species_group'];slot=list(group_colors).index(code)
        radius=min(6.,(top-base)*.25);offset=len(vertices)
        # Broadleaf groups have a rounder envelope. Top and centre stay measured.
        rings=[(base+1.2,.3),(base+(top-base)*.45,radius),(base+(top-base)*.8,radius*.65),(top,.1)]
        if code in {'MB','DR'}:
            rings=[(base+1.2,.3),(base+(top-base)*.38,radius*.8),(base+(top-base)*.7,radius),(top,radius*.35)]
        first_face=len(faces)
        for z,r in rings:
            for a in np.arange(6)*np.pi/3:vertices.append([x+np.cos(a)*r,y+np.sin(a)*r,z])
        for ring in range(3):
            for i in range(6):
                a=offset+ring*6+i;b=offset+ring*6+(i+1)%6
                faces.extend([(a,b,a+6),(b,b+6,a+6)])
        faces.append(tuple(offset+18+i for i in range(6)))
        face_materials.extend([slot]*(len(faces)-first_face))
    if vertices:create('SM_Canopy_'+tile['tile'].split('_',1)[1],vertices,faces,list(canopy_mats.values()),np.array([*tile['points'][0][:2],0.]),face_materials)
# Bundle distant masses by survey tile, while preserving their footprint records.
groups={}
for item in data['buildings']:groups.setdefault('_'.join(item['id'].split('_')[:3]),[]).append(item)
for tile,items in groups.items():
    vertices=[];faces=[]
    for item in items:
        outline=item['outline'];n=len(outline);offset=len(vertices)
        vertices.extend([[*p,item['base_m']] for p in outline]);vertices.extend([[*p,item['roof_m']] for p in outline])
        faces.append(tuple(offset+n+i for i in range(n)))
        for i in range(n):j=(i+1)%n;faces.append((offset+i,offset+j,offset+n+j,offset+n+i))
    create('SM_BuildingMass_'+tile,vertices,faces,[building_mat],np.array([*items[0]['outline'][0],0.]))
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result={'canopy_envelopes':sum(len(t['points']) for t in data['canopy']),'building_masses':len(data['buildings']),'survey_year':2022,'zone_manifest':'manifests/vegetation-zones.json','release_accepted':False}
