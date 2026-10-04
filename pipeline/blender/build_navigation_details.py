"""Author functional M1 route guidance in live Blender, with editable text data.

No real sign location is asserted. Run through Blender MCP, then inspect the
scene. Text uses Blender's built-in font, converted to ordinary mesh geometry.
"""
import hashlib
import json
from pathlib import Path

import bmesh
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
manifest_path=ROOT/'data/routes/derived/navigation-details.json'
data=json.loads(manifest_path.read_text(encoding='utf8'))
manifest_hash=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
for item in data['inputs']+data['meshes']:
    if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
        raise RuntimeError(f"Navigation data changed; rebuild before authoring: {item['path']}")
if data['unplaced']:
    raise RuntimeError('Navigation has unplaced required markers; inspect that register first')
settings=json.loads((ROOT/'manifests/navigation-detail-settings.json').read_text())
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_09_Navigation')
if collection is None:
    collection=bpy.data.collections.new('SP_09_Navigation');scene.collection.children.link(collection)
for obj in list(collection.objects):
    if obj.get('pipeline_owner')=='navigation_details':
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)


def material(name,color):
    value=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    value.diffuse_color=color;value.use_nodes=True
    value.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=color
    value.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85
    return value


def author(name,vertices,faces,anchor,color,marker_id,source_hash=None):
    vertices,faces=np.asarray(vertices),np.asarray(faces,dtype=np.int32)
    if not np.isfinite(vertices).all() or faces.min()<0 or faces.max()>=len(vertices):
        raise RuntimeError(f'Invalid navigation geometry: {name}')
    tri=vertices[faces]
    area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
    if area.min()<1e-12:raise RuntimeError(f'Degenerate navigation geometry: {name}')
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
    obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);obj.location=anchor
    key='M_Navigation_'+('_'.join(f'{int(round(c*1000)):04d}' for c in color[:3]))
    mesh.materials.append(material(key,color))
    obj['pipeline_owner']='navigation_details';obj['collision']='none'
    obj['navigation_id']=marker_id;obj['source_manifest']=manifest_path.relative_to(ROOT).as_posix()
    obj['source_manifest_sha256']=manifest_hash;obj['source_mesh_sha256']=source_hash or 'generated_from_saved_text_lines'
    obj['source_id']='Functional M1 guidance based on City map, current walk-zone register and source topology'
    obj['physical_sign_location_verified']=False;obj['placement_class']='functional_blockout_marker'
    obj['release_accepted']=False
    return obj


created=[]
for item in data['meshes']:
    with np.load(ROOT/item['path']) as p:
        obj=author(item['name'],p['vertices'],p['faces'],p['anchor'],item['material_color'],item['marker_id'],item['sha256'])
    created.append(obj.name)


def text_mesh(line):
    curve=bpy.data.curves.new('TemporaryNavigationText','FONT');curve.body=line
    curve.align_x='CENTER';curve.align_y='CENTER';curve.size=1;curve.extrude=.0005;curve.resolution_u=4
    temporary=bpy.data.objects.new('TemporaryNavigationText',curve);collection.objects.link(temporary)
    bpy.context.view_layer.update()
    mesh=bpy.data.meshes.new_from_object(temporary.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    vertices=np.array([v.co[:] for v in mesh.vertices]);faces=np.array([f.vertices[:] for f in mesh.polygons],dtype=np.int32)
    bpy.data.objects.remove(temporary,do_unlink=True);bpy.data.curves.remove(curve);bpy.data.meshes.remove(mesh)
    if not len(vertices) or not len(faces):raise RuntimeError(f'Empty navigation label: {line}')
    lo,hi=vertices.min(0),vertices.max(0)
    vertices[:,:2]-=(lo[:2]+hi[:2])*.5
    scale=min((settings['board_width_m']-.12)/max(hi[0]-lo[0],.01),.17/max(hi[1]-lo[1],.01))
    vertices*=scale
    return vertices,faces


text_records=[]
for marker in data['markers']:
    center=np.array(marker['board_center_local_m']);t=np.r_[marker['tangent_xy'],0.];n=np.r_[marker['normal_xy'],0.]
    anchor=np.r_[np.floor(center[:2]/10)*10,0.]
    vertices,faces,count=[],[],0
    lines=marker['text_lines'];spacing=.225
    for i,line in enumerate(lines):
        v,f=text_mesh(line)
        # Default font x is reader-right, y is up and its front faces upstream.
        zoffset=((len(lines)-1)*.5-i)*spacing
        origin=center-t*(settings['board_thickness_m']*.5+.003)+np.array([0.,0.,zoffset])
        placed=origin+v[:,0,None]*(-n)+v[:,1,None]*[0.,0.,1.]+v[:,2,None]*(-t)
        vertices.extend(placed-anchor);faces.extend(f+count);count+=len(v)
    name='SM_Nav_'+marker['id']+'_Text'
    obj=author(name,vertices,faces,anchor,[.94,.94,.87,1],marker['id'])
    obj['text_lines']=json.dumps(lines)
    obj['text_source']='Editable lines in navigation-details.json; Blender built-in font converted to mesh'
    created.append(name);text_records.append(dict(name=name,triangles=len(faces),text_lines=lines))

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(objects=created,mesh_count=len(created),text_objects=text_records,
            physical_sign_locations_verified=0,visual_inspection='pending',runtime_acceptance=False)
