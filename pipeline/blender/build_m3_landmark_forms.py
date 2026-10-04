"""Create original source-informed sculpture forms in the separate Seawall file.

Run only in the coordinator's serial Blender slot. No existing mesh, transform,
collision, material or pavement changes. The coordinator saves the blend.
"""
from pathlib import Path
import hashlib
import json
import math
import runpy

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
OWNER = 'SP_M3LandmarkForms'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Form:
    def __init__(self):
        self.vertices, self.faces, self.slots, self.uvs = [], [], [], []

    def part(self, vertices, faces, slot):
        start = len(self.vertices)
        self.vertices.extend(tuple(p) for p in vertices)
        self.uvs.extend((0, 0) for _ in vertices)
        self.faces.extend(tuple(start+i for i in f) for f in faces)
        self.slots.extend(slot for _ in faces)

    def box(self, centre, size, slot, taper=1):
        x,y,z = centre; a,b,c = np.asarray(size)/2
        self.part([(x+i*a*s,y+j*b*s,z+k*c) for k,s in [(-1,1),(1,taper)] for i,j in [(-1,-1),(1,-1),(1,1),(-1,1)]],
            [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],slot)

    def ellipsoid(self, centre, radii, slot, rings=10, sides=16):
        vertices=[]; faces=[]
        for i in range(rings+1):
            a=math.pi*i/rings
            for j in range(sides):
                b=math.tau*j/sides
                vertices.append(np.asarray(centre)+np.asarray(radii)*[math.sin(a)*math.cos(b),math.sin(a)*math.sin(b),math.cos(a)])
        for i in range(rings):
            for j in range(sides):
                k=(j+1)%sides; faces.append((i*sides+j,i*sides+k,(i+1)*sides+k,(i+1)*sides+j))
        self.part(vertices,faces,slot)

    def tube(self, points, radii, slot, sides=12):
        points=np.asarray(points,float); vertices=[]; faces=[]
        for i,(p,r) in enumerate(zip(points,radii)):
            n=points[min(i+1,len(points)-1)]-points[max(0,i-1)]; n/=np.linalg.norm(n)
            u=np.cross(n,[0,1,0] if abs(n[1])<.9 else [1,0,0]); u/=np.linalg.norm(u); v=np.cross(n,u)
            for j in range(sides):
                a=math.tau*j/sides; vertices.append(p+r*(math.cos(a)*u+math.sin(a)*v))
        faces.append(tuple(reversed(range(sides))))
        for i in range(len(points)-1):
            for j in range(sides):
                k=(j+1)%sides; faces.append((i*sides+j,i*sides+k,(i+1)*sides+k,(i+1)*sides+j))
        faces.append(tuple((len(points)-1)*sides+j for j in range(sides)))
        self.part(vertices,faces,slot)

    def ring(self, centre, radius, thickness, slot, plane='XZ', arc=math.tau):
        p=[]
        for a in np.linspace(0,arc,49):
            q=[radius*math.cos(a),0,radius*math.sin(a)] if plane=='XZ' else [radius*math.cos(a),radius*math.sin(a),0]
            p.append(np.asarray(centre)+q)
        self.tube(p,[thickness]*len(p),slot)


# Shared palette: bronze, granite, dark plaque, ivory paint, red, green, blue.
B,G,D,W,R,V,U=range(7)


def plinth(g, height=2.5, width=1.7):
    g.box((0,0,.16),(width+1.2,width+1.2,.32),G)
    g.box((0,0,.48),(width+.55,width+.55,.32),G)
    g.box((0,0,(height+.64)/2),(width,width,height-.64),G,.83)
    g.box((0,0,height+.10),(width+.2,width+.2,.2),G)
    g.box((0,-width*.46,height*.59),(width*.54,.045,height*.28),D)
    return height+.2


def man(g, z, raised):
    # Long formal coat, waistcoat, lapels, shaped head, hands and footwear.
    for x,y in [(-.19,-.12),(.2,.12)]:
        g.ellipsoid((x,y-.08,z+.10),(.17,.30,.12),B)
        g.tube([(x,y,z+.19),(x*.8,y+.03,z+.66),(x*.7,0,z+1.13)],[.12,.13,.17],B)
    g.ellipsoid((0,0,z+1.18),(.35,.23,.29),B)
    g.box((0,.10,z+.96),(.76,.30,.85),B,.76)
    g.ellipsoid((0,0,z+1.54),(.39,.24,.5),B)
    g.box((0,-.23,z+1.57),(.27,.06,.55),D,.6)
    for side in [-1,1]:
        g.tube([(side*.29,-.20,z+1.93),(side*.12,-.26,z+1.57),(side*.21,-.23,z+1.47)],[.045,.052,.025],B)
    g.tube([(0,0,z+1.89),(0,0,z+2.10)],[.14,.13],B)
    g.ellipsoid((0,-.01,z+2.27),(.21,.19,.28),B)
    g.ellipsoid((0,-.19,z+2.26),(.065,.09,.095),B)
    g.ellipsoid((0,.045,z+2.43),(.218,.18,.14),D)
    if raised:
        g.ellipsoid((0,-.10,z+2.08),(.17,.17,.20),B)
        chains=[[(-.31,0,z+1.84),(-.67,-.03,z+2.10),(-.99,-.11,z+2.43)],[(.31,0,z+1.84),(.62,-.02,z+2.27),(.67,-.10,z+2.76)]]
    else:
        chains=[[(-.32,0,z+1.86),(-.48,-.14,z+1.57),(.17,-.36,z+1.75)],[(.32,0,z+1.86),(.46,-.15,z+1.56),(-.20,-.39,z+1.79)]]
    for chain in chains:
        g.tube(chain,[.16,.13,.095],B)
        g.ellipsoid(chain[-1],(.115,.08,.15),B)
        if raised:
            x,y,zz=chain[-1]
            for i in range(4): g.tube([(x+(i-1.5)*.035,y,zz+.07),(x+(i-1.5)*.043,y-.04,zz+.23)],[.021,.013],B,8)


def statue(raised):
    g=Form(); z=plinth(g,1.8 if raised else 3.0,1.6); man(g,z,raised); return g


def victoria():
    g=Form()
    for i in range(3): g.box((0,0,.12+i*.20),(5.5-i*.5,2.5-i*.35,.24),G)
    g.box((0,.35,1.86),(1.6,.62,2.7),G,.84)
    g.ellipsoid((0,.35,3.16),(.7,.31,.35),G)
    for s in [-1,1]:
        g.box((s*1.55,.3,1.23),(1.65,.38,1.18),G)
        g.box((s*1.55,-.06,.87),(1.85,.86,.19),G)
        g.box((s*2.35,.28,1.11),(.42,.64,1.23),G,.83)
        g.box((s*2.35,.28,1.76),(.55,.75,.12),G)
    g.box((0,.018,2.3),(1.02,.065,1.32),B)
    g.ellipsoid((0,-.028,2.65),(.39,.045,.45),D)
    g.ellipsoid((0,-.074,2.69),(.18,.035,.23),B)
    g.ellipsoid((0,-.35,1.43),(.59,.51,.15),B)
    g.ring((0,-.12,1.52),.53,.045,B,'XY',math.pi)
    g.tube([(0,-.03,1.88),(0,-.20,1.79)],[.055,.05],B)
    return g


def chehalis():
    g=Form()
    g.box((0,0,.28),(2,1.7,.56),G,.80)
    g.box((0,0,.77),(1.28,1.10,.42),G,.7)
    g.box((0,0,1.32),(.86,.74,.72),W,.67)
    g.box((0,0,2.58),(.39,.31,1.85),W,.77)
    g.box((0,0,3.57),(.35,.30,1.36),W)
    g.box((0,0,3.61),(1.22,.30,.34),W)
    g.ring((0,0,3.61),.46,.10,W)
    g.box((0,0,4.27),(.48,.40,.10),W)
    g.box((0,-.375,1.33),(.51,.026,.39),G)
    return g


def aerodynamic():
    g=Form()
    g.tube([(0,0,0),(0,0,.22)],[2.1,2.1],G,48)
    g.tube([(0,0,.22),(0,0,.39)],[1.79,1.79],W,48)
    # Inclined pedestal and near-vertical toy glider, source height 35 feet.
    g.part([(-.8,-.75,.39),(.8,-.75,.39),(.8,.75,.39),(-.8,.75,.39),(-.29,-.22,3.5),(.29,-.22,3.5),(.29,.25,3.5),(-.29,.25,3.5)],
        [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],W)
    g.tube([(0,0,2.5),(.4,0,6),(1.0,0,10.0)],[.16,.12,.08],W)
    g.box((.34,0,5.57),(3.05,.76,.085),W)
    g.box((.62,0,7.55),(1.27,.46,.065),W)
    for i in range(4):
        for j in range(3): g.box((-.18+i*.22,-.045,5.9+j*.25),(.22,.15,.25),V if (i+j)%2 else W)
    for side in [-1,1]:
        g.tube([(.34+side*1.43,0,5.6),(1,0,9.6)],[.021,.021],U,8)
    g.tube([(.3,0,5.17),(-.73,-.02,4.84)],[.04,.04],W)
    g.ellipsoid((-.77,-.01,4.82),(.24,.095,.24),R)
    g.tube([(.96,-.14,9.99),(.96,.14,9.99)],[.10,.10],R)
    g.tube([(.46,-.06,9.36),(.96,-.06,9.99),(1.46,-.06,10.63)],[.065,.075,.055],R)
    return g


def dragon():
    g=Form()
    # Profile coordinates run along local y, centred in the measured envelope.
    g.tube([(0,-2.55,.17),(0,-1.7,.21),(0,-.9,.34),(0,-.05,.62),(0,.72,.84),(0,1.42,1.00)], [.16,.24,.29,.32,.33,.29],V,16)
    g.tube([(0,-2.6,.04),(0,-1.7,.02),(0,-.8,.10),(0,.1,.30),(0,.9,.55)],[.12,.14,.16,.17,.15],W,12)
    for side in [-1,1]:
        x=side*.25
        for i in range(9):
            y=-2.2+i*.39; z=.27+max(0,y+1.5)*.25
            g.tube([(x,y,z),(x*1.35,y-.23,z+.25),(x*.85,y-.40,z+.12)],[.085,.10,.018],R,9)
        g.tube([(side*.16,.30,.61),(side*.46,.48,.34),(side*.59,.96,.34)],[.11,.11,.07],V)
        for j in range(3): g.tube([(side*.59,.92+j*.08,.33),(side*.68,1.08+j*.06,.25)],[.035,.012],D,8)
    g.ellipsoid((0,1.42,1.07),(.34,.40,.28),V)
    g.ellipsoid((0,1.98,1.18),(.30,.59,.19),V)
    g.ellipsoid((0,1.91,.65),(.25,.47,.12),R)
    g.ellipsoid((0,1.91,.60),(.25,.49,.085),W)
    # Mouth remains open between the two jaws; teeth and fangs frame it.
    for side in [-1,1]:
        for y in [1.70,1.9,2.10,2.28]:
            g.tube([(side*.21,y,1.07),(side*.19,y+.025,.91)],[.05,.003],W,8)
        g.tube([(side*.22,1.57,1.08),(side*.27,1.68,.88),(side*.24,1.76,.72)],[.065,.04,.003],W,10)
        g.ellipsoid((side*.305,1.34,1.2),(.055,.10,.08),W)
        g.ellipsoid((side*.35,1.35,1.22),(.026,.046,.047),D)
        g.tube([(side*.30,1.10,1.39),(side*.38,.83,1.49),(side*.30,.60,1.35)],[.065,.08,.008],R)
        g.tube([(side*.28,1.86,1.04),(side*.57,1.82,1.01),(side*.67,1.57,.91),(side*.61,1.32,.91),(side*.44,1.36,.99)],[.035]*5,V)
    g.tube([(0,-2.58,.38),(0,-1.45,.49),(0,-.2,.84),(0,.61,1.20)],[.07]*4,W)
    return g


def build():
    if Path(bpy.data.filepath).resolve() != (ROOT/'blender/StanleyPark_Seawall.blend').resolve():
        raise RuntimeError('Open the separate Seawall source')
    scene=bpy.context.scene
    if abs(scene.unit_settings.scale_length-1)>1e-7: raise RuntimeError('Scene must use metres')
    cfg=json.loads((ROOT/'manifests/m3-landmark-form-settings.json').read_text())
    paths=['pipeline/blender/build_m3_landmark_forms.py','pipeline/blender/build_seawall_tree_library.py','manifests/m3-landmark-form-settings.json','manifests/route-sculpture-blockouts.json']
    paths+=cfg['survey_manifests']
    inputs={p:sha(ROOT/p) for p in paths}
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-landmark-forms'/version; manifest_path=folder/'manifest.json'
    if manifest_path.exists(): raise RuntimeError('Immutable landmark form export exists')
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='m3_form_helpers')
    verts=[];faces=[]
    for obj in scene.objects:
        if obj.type=='MESH' and obj.name.startswith(('SM_Terrain_','SM_Pavement_','SM_Pedestrian_')):
            start=len(verts);verts.extend(tuple(obj.matrix_world@v.co) for v in obj.data.vertices)
            faces.extend(tuple(start+i for i in p.vertices) for p in obj.data.polygons)
    ground=BVHTree.FromPolygons(verts,faces)
    collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection)
    materials=[]
    for row in cfg['materials']:
        m=bpy.data.materials.new('M_M3Form_'+row['name']+'_'+version);m.diffuse_color=(*row['rgb'],1);m.use_nodes=True
        shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=m.diffuse_color
        shader.inputs['Metallic'].default_value=row['metallic'];shader.inputs['Roughness'].default_value=row['roughness'];materials.append(m)
    factory={'lord':lambda:statue(True),'burns':lambda:statue(False),'victoria':victoria,'aerodynamic':aerodynamic,'chehalis':chehalis,'dragon':dragon}
    folder.mkdir(parents=True,exist_ok=True);exports=[]
    for row in cfg['forms']:
        form=factory[row['form']]();x,y=row['position_local_m'][:2]
        if row['form']=='dragon': z=row['position_local_m'][2]
        else:
            hit,_,_,_=ground.ray_cast(Vector((x,y,100)),Vector((0,0,-1)),150)
            if hit is None: raise RuntimeError('No existing surface under '+row['id'])
            z=float(hit.z)-.025
        angle=math.radians(row['yaw_degrees']); c,s=math.cos(angle),math.sin(angle)
        form.vertices=[(a*c-b*s,a*s+b*c,h) for a,b,h in form.vertices]
        obj=helpers['make_object']('SM_M3Form_'+row['form']+'_'+version,form,collection,materials,(x,y,z))
        obj['pipeline_owner']=OWNER;obj['feature_id']=row['id'];obj['collision']='none'
        # Only curved pieces use smooth normals; planar stone retains corners.
        for p in obj.data.polygons: p.use_smooth=p.material_index!=G and p.material_index!=W
        item=helpers['export_object'](obj,folder,scene);item.update(feature_id=row['id'],source=row,position_local_m=[x,y,z]);exports.append(item)
    hide=[o for o in scene.objects if o.name.startswith('SM_Empress_FigureheadEnvelope_')]
    if len(hide)!=4: raise RuntimeError('Expected four source Empress envelopes')
    baseline=[dict(name=o.name,hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()) for o in hide]
    for obj in hide: obj.hide_render=True;obj.hide_set(True)
    result=dict(schema_version=1,version=version,owner=OWNER,input_hashes=inputs,settings=cfg,assets=exports,
        asset_root='/Game/StanleyPark/Seawall/LandmarkForms/v_'+version,hidden_originals=baseline,
        original_collision_unchanged=True,new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False)
    manifest_path.write_text(json.dumps(result,indent=2));(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(),sha256=sha(manifest_path)),indent=2))
    return dict(version=version,assets=len(exports),triangles=sum(a['triangles'] for a in exports),manifest=str(manifest_path))


if __name__ in {'__main__','<run_path>'}:
    result=build()
