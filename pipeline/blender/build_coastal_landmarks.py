"""Create named, editable coastal forms from inspected measurement manifests."""
import json
import math
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'manifests/coastal-landmark-blockouts.json').read_text())
scene=bpy.data.scenes['StanleyPark_M1'];bpy.context.window.scene=scene
collection=bpy.data.collections.get('SP_06_Landmarks')
if collection is None:
    collection=bpy.data.collections.new('SP_06_Landmarks');scene.collection.children.link(collection)
owner='landmark_coastal'
for obj in list(collection.objects):
    if obj.get('pipeline_owner')==owner:
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)

def material(name,color):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color=(*color,1);m.use_nodes=True
    m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
    return m

stone=material('M_SiwashStoneBlockout',(.32,.31,.26))
crown=material('M_SiwashCrownEnvelope',(.09,.18,.075))
white=material('M_BrocktonWhite',(.82,.81,.72))
red=material('M_BrocktonRed',(.55,.035,.025))
glass=material('M_BrocktonLanternDark',(.065,.09,.10))
created=[]

def create(name,vertices,faces,mat,anchor,feature):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata((np.asarray(vertices)-anchor).tolist(),[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);obj.location=anchor;mesh.materials.append(mat)
    obj['pipeline_owner']=owner;obj['collision']='none';obj['release_accepted']=False
    obj['landmark']=feature['name'];obj['source_id']='City LiDAR 2022; manifests/coastal-landmark-blockouts.json'
    obj['limits']=feature['limits'];created.append(name)
    return obj

def ring_mesh(rows):
    n=len(rows[0]);vertices=[p for row in rows for p in row]
    faces=[tuple(range(n-1,-1,-1))]
    for r in range(len(rows)-1):
        for i in range(n):j=(i+1)%n;faces.append((r*n+i,r*n+j,(r+1)*n+j,(r+1)*n+i))
    faces.append(tuple((len(rows)-1)*n+i for i in range(n)))
    return vertices,faces

rock,light=data['landmarks']
anchor=np.array([*rock['centre_local_m'],0.])
rows=rock['rings']
bottom=np.array(rows[0]);bottom[:,2]=-1
rows=[bottom.tolist(),*rows]
v,f=ring_mesh(rows);create('SM_SiwashRock_SurveyEnvelope',v,f,stone,anchor,rock)
low,high=np.array(rock['crown_bounds_min_m']),np.array(rock['crown_bounds_max_m'])
c=(low+high)*.5;r=(high-low)*.5
rows=[]
for phi in np.linspace(-math.pi*.5,math.pi*.5,9):
    rows.append([[c[0]+r[0]*max(.01,math.cos(phi))*math.cos(t),c[1]+r[1]*max(.01,math.cos(phi))*math.sin(t),c[2]+r[2]*math.sin(phi)] for t in np.arange(16)*math.pi/8])
v,f=ring_mesh(rows);create('SM_SiwashRock_CrownEnvelope',v,f,crown,anchor,rock)

anchor=np.array([*light['centre_local_m'],0.])
direction=np.array(light['axis_unit']);normal=np.array(light['transverse_unit'])
body=light['measured_bands'][1]
left,right=np.array(body['bounds_min_m']),np.array(body['bounds_max_m'])
def world(p):
    xy=anchor[:2]+direction*p[0]+normal*p[1]
    return [*xy,p[2]]
def box_rows(lo,hi,z0,z1):
    return [[world([x,y,z]) for x,y in [(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])]] for z in [z0,z1]]
for name,z0,z1,mat in [('LowerBody',7.7,10.15,white),('RedBand',10.15,11.25,red),('UpperBody',11.25,12.85,white)]:
    v,f=ring_mesh(box_rows(left,right,z0,z1));create('SM_Brockton_'+name,v,f,mat,anchor,light)
balcony=light['measured_bands'][2]
v,f=ring_mesh(box_rows(balcony['bounds_min_m'],balcony['bounds_max_m'],12.85,13.05))
create('SM_Brockton_Balcony',v,f,white,anchor,light)
roof=light['measured_bands'][4]
lo,hi=np.array(roof['bounds_min_m']),np.array(roof['bounds_max_m']);center=(lo+hi)*.5;radius=(hi-lo)*.5
for name,z0,z1,r0,r1,mat in [('Lantern',13.1,15.3,1.,1.,glass),('Roof',15.3,light['observed_top_m'],1.12,.02,red)]:
    rows=[[world([*(center+radius*factor*np.array([math.cos(t),math.sin(t)])),z]) for t in np.arange(12)*math.pi/6] for z,factor in [(z0,r0),(z1,r1)]]
    v,f=ring_mesh(rows);create('SM_Brockton_'+name,v,f,mat,anchor,light)

# A visible arch form is required for place recognition. The opening is marked
# for measurement review and is not used as a released collision aperture.
platform_path=ROOT/'manifests/brockton-platform.json'
platform=json.loads(platform_path.read_text()) if platform_path.exists() else None
bottom=4.07
if platform:
    corners=np.asarray(box_rows(left,right,0,0)[0])[:,:2]
    heights=np.column_stack((corners-platform['plane_origin_xy_m'],np.ones(4)))@np.asarray(platform['measured_plane_coefficients'])
    bottom=float(heights.min())-.02
# A hidden 2 cm overlap avoids coplanar top faces at the body join.
vertices,faces=ring_mesh(box_rows(left,right,bottom,7.72))
obj=create('SM_Brockton_ArchReview',vertices,faces,white,anchor,light)
import runpy
runpy.run_path(str(ROOT/'pipeline/blender/arch_geometry.py'))['cut_arches'](obj,collection,anchor,world,bottom)
obj['assumed_opening_width_m']=2.2;obj['assumed_opening_top_m']=7.1
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(objects=created,accepted=False,scope='Measured coastal forms with explicitly marked arch and detail limits')
(ROOT/'evidence/blender-coastal-landmarks-build.json').write_text(json.dumps(result,indent=2)+'\n')
