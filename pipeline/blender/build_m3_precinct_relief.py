"""Separate Yelton and two-portal sculpture layer. Coordinator-only writer slot."""
from pathlib import Path
import hashlib
import json
import math
import runpy

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3PrecinctRelief'
BASE=runpy.run_path(str(ROOT/'pipeline/blender/build_m3_landmark_forms.py'),run_name='relief_form_helper')['Form']
W,SH,K,R,I,G,V=range(7)


class Form(BASE):
    def ellipsoid(self,*args,**kwargs):
        start=len(self.faces)
        super().ellipsoid(*args,**kwargs)
        self.faces[start:]=[tuple(reversed(f)) for f in self.faces[start:]]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def plate(g,outline,y,depth,slot):
    """A closed extruded 2D relief; local x/z outline, front is negative y."""
    n=len(outline);points=[Vector((x,y-depth,z)) for x,z in outline]
    triangles=tessellate_polygon([points]);lookup={tuple(p):i for i,p in enumerate(points)}
    faces=[]
    for tri in triangles:
        ids=tuple(int(p) if isinstance(p,int) else lookup[tuple(p)] for p in tri)
        faces.extend([ids,tuple(i+n for i in reversed(ids))])
    faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    g.part([tuple(p) for p in points]+[(x,y,z) for x,z in outline],faces,slot)


def oval(g,x,z,w,h,y,slot,depth=.045):
    outline=[(x+w/2*math.cos(a),z+h/2*math.sin(a)) for a in np.linspace(0,math.tau,33)[:-1]]
    plate(g,outline,y,depth,slot)


def eye(g,x,z,w,y,wood=False):
    outer=W if wood else I;inner=SH if wood else K
    oval(g,x,z,w,w*.53,y,outer,.025)
    oval(g,x,z,w*.73,w*.36,y-.027,inner,.02)
    if not wood:oval(g,x,z,w*.25,w*.26,y-.05,K,.015)


def face(g,x,z,w,h,y,wood=False):
    base=W if wood else R;dark=SH if wood else K
    g.ellipsoid((x,y,z),(w*.5,.09,h*.5),base,rings=8,sides=16)
    for side in [-1,1]:
        eye(g,x+side*w*.23,z+h*.12,w*.35,y-.10,wood)
        g.tube([(x+side*w*.44,y-.11,z+h*.28),(x+side*w*.23,y-.14,z+h*.34),(x,y-.13,z+h*.23)],[.025]*3,dark,6)
    plate(g,[(x-w*.065,z+h*.16),(x+w*.065,z+h*.16),(x+w*.095,z-h*.10),(x-w*.095,z-h*.10)],y-.16,.065,base)
    oval(g,x,z-h*.25,w*.40,h*.095,y-.095,dark,.025)


def hand(g,x,z,w,h,y,slot,up=True):
    s=1 if up else -1
    g.ellipsoid((x,y,z),(w*.5,.045,h*.35),slot,rings=6,sides=10)
    for i in range(4):
        xx=x+(i-1.5)*w*.21
        g.tube([(xx,y,z+s*h*.10),(xx,y,z+s*h*(.50-.05*abs(i-1.5)))],[w*.095,w*.07],slot,6)
    g.tube([(x-w*.40,y,z),(x-w*.64,y-.01,z+s*h*.16)],[w*.11,w*.08],slot,6)


def yelton():
    g=Form()
    g.tube([(0,.02,z) for z in [0,1.2,2.8,4.8,6.5,8.4,9.6,10.0]], [.43,.42,.39,.38,.38,.38,.32,.23],W,20)
    # Rose: face, hair, body, bent arms and the held game bones.
    face(g,0,1.92,.77,.92,-.35,True)
    plate(g,[(-.40,.1),(.40,.1),(.38,1.25),(.22,1.49),(-.22,1.49),(-.38,1.25)],-.31,.10,W)
    for s in [-1,1]:
        g.tube([(s*.30,-.40,1.36),(s*.34,-.46,.87),(s*.10,-.54,.94)],[.10,.09,.075],W)
        hand(g,s*.13,.96,.13,.22,-.55,W,False)
        for j in range(3):g.tube([(s*.26,-.35,1.60+j*.17),(s*.37,-.28,1.78+j*.17)],[.022]*2,SH,5)
    g.tube([(-.17,-.56,.93),(.17,-.56,.93)],[.035,.035],W,8)
    # Whale held below the wolf: rounded head, side flippers and downward tail.
    g.ellipsoid((0,-.39,3.55),(.38,.17,.60),W)
    for s in [-1,1]:
        oval(g,s*.20,3.82,.13,.15,-.57,SH)
        plate(g,[(s*.12,3.20),(s*.37,3.52),(s*.41,3.0),(s*.10,2.68)],-.41,.11,W)
    plate(g,[(-.18,3.01),(.18,3.01),(.36,2.50),(0,2.64),(-.36,2.50)],-.37,.12,W)
    # Wolf: muzzle, eyes and front paws around the whale.
    face(g,0,4.78,.82,.75,-.35,True)
    g.ellipsoid((0,-.52,4.64),(.22,.18,.13),W)
    oval(g,0,4.64,.13,.11,-.705,SH)
    for s in [-1,1]:
        plate(g,[(s*.18,5.04),(s*.40,5.34),(s*.38,4.98)],-.24,.16,W)
        g.tube([(s*.33,-.35,4.38),(s*.35,-.46,4.02),(s*.18,-.54,3.89)],[.095,.095,.08],W)
    # Raven: full bird head, long front beak, folded wings, knees and claws.
    g.ellipsoid((0,-.34,6.60),(.37,.15,.88),W)
    g.ellipsoid((0,-.40,7.49),(.43,.23,.30),W)
    plate(g,[(-.28,7.49),(.28,7.49),(.21,6.89),(0,6.53),(-.21,6.89)],-.58,.24,W)
    for s in [-1,1]:
        eye(g,s*.23,7.55,.22,-.60,True)
        plate(g,[(s*.35,7.0),(s*.49,6.10),(s*.27,5.55),(s*.16,6.43)],-.23,.10,W)
        g.ellipsoid((s*.20,-.47,5.98),(.17,.16,.37),W)
        for j in range(3):g.ellipsoid((s*.20+(j-1)*.10,-.51,5.56),(.07,.11,.055),W,rings=5,sides=8)
    # Human face between wide upper wings, with hands below the chin.
    face(g,0,8.62,.82,.72,-.35,True)
    for s in [-1,1]:
        hand(g,s*.18,8.18,.27,.51,-.45,W,True)
        outline=[(s*.34,8.46),(s*2.24,8.69),(s*2.32,9.01),(s*.35,8.87)]
        plate(g,outline,-.03,.20,W)
        for j in range(8):
            x=.48+j*.21
            g.tube([(s*x,-.242,8.58+.115*x),(s*(x+.15),-.242,8.83+.03*x)],[.015,.015],SH,5)
    # Small Thunderbird head above the central human face.
    face(g,0,9.53,.60,.58,-.28,True)
    plate(g,[(-.16,9.56),(.15,9.56),(.18,9.26),(0,9.14),(-.16,9.28)],-.44,.14,W)
    for s in [-1,1]:g.tube([(s*.20,-.02,9.72),(s*.24,-.02,10.0)],[.08,.045],W)
    return g


def welcome():
    """A normalized welcome house post, 1 m wide and 4 m high."""
    g=Form();plate(g,[(-.47,.12),(.47,.12),(.44,3.90),(-.44,3.90)],-.255,.025,K)
    # Blanket and salmon-like sweeping bands are relief geometry, not a photo.
    plate(g,[(-.43,.26),(.43,.26),(.37,2.45),(-.37,2.45)],-.29,.028,V)
    plate(g,[(-.10,.28),(.10,.28),(.12,2.48),(-.12,2.48)],-.326,.02,K)
    for side in [-1,1]:
        for j in range(4):
            z=.53+j*.31
            plate(g,[(side*.17,z-.15),(side*.41,z+.06),(side*.32,z+.19),(side*.22,z+.12)],-.333,.015,G)
        g.tube([(side*.28,-.34,2.62),(side*.35,-.40,2.13),(side*.23,-.43,2.39)],[.11,.10,.085],R)
        hand(g,side*.22,2.55,.17,.35,-.45,R,True)
    for z in np.arange(.45,2.40,.23):oval(g,0,float(z),.052,.069,-.36,G,.01)
    face(g,0,3.13,.72,.75,-.34)
    plate(g,[(-.42,3.53),(.42,3.53),(.35,3.69),(-.35,3.69)],-.38,.08,K)
    for j in range(7):
        x=-.34+j*.11
        plate(g,[(x,3.55),(x+.055,3.65),(x+.11,3.55)],-.47,.01,G)
    g.box((0,-.35,2.70),(.88,.17,.13),K)
    return g


def dancer():
    g=Form();plate(g,[(-.49,.08),(.49,.08),(.49,3.97),(-.49,3.97)],-.25,.025,K)
    # Rounded rattle/serpent loop, red torso and bent arms.
    oval(g,0,.95,.76,1.02,-.29,I,.07);oval(g,0,.94,.47,.66,-.37,K,.03)
    for a in np.linspace(0,math.tau,13)[:-1]:oval(g,.30*math.cos(a),.95+.40*math.sin(a),.055,.07,-.37,K,.012)
    g.ellipsoid((0,-.32,1.82),(.29,.10,.44),R)
    g.tube([(-.23,-.35,2.05),(-.31,-.40,1.55),(-.02,-.48,1.23)],[.115,.10,.075],R)
    g.tube([(.22,-.35,2.04),(.29,-.42,1.76),(.02,-.49,2.0)],[.11,.10,.075],R)
    hand(g,0,1.24,.16,.23,-.49,R,False);hand(g,.02,2.0,.16,.23,-.50,R,True)
    face(g,0,2.40,.72,.53,-.35)
    # Upper Thunderbird face and feather band.
    face(g,0,3.47,.90,.71,-.30)
    plate(g,[(-.14,3.65),(.14,3.65),(.16,3.20),(0,3.01),(-.16,3.2)],-.45,.15,R)
    for s in [-1,1]:
        plate(g,[(s*.18,3.78),(s*.44,3.94),(s*.43,3.67)],-.29,.06,I)
    for j in range(7):
        x=-.40+j*.132
        plate(g,[(x,2.74),(x+.066,3.10),(x+.125,2.74)],-.31,.045,R)
        plate(g,[(x+.035,2.82),(x+.066,3.04),(x+.096,2.82)],-.36,.012,K)
    return g


def whales():
    g=Form();plate(g,[(-.48,.08),(.48,.08),(.48,3.98),(-.48,3.98)],-.25,.025,K)
    for j in range(5):
        z=.47+j*.70
        oval(g,0,z,.74,.61,-.30,V,.025)
        oval(g,0,z,.47,.36,-.33,K,.025)
        for side in [-1,1]:
            eye(g,side*.25,z+.12,.13,-.36)
            plate(g,[(side*.12,z-.14),(side*.46,z-.34),(side*.31,z+.02)],-.32,.055,R)
        plate(g,[(-.14,z+.14),(.17,z+.14),(.33,z-.12),(-.06,z-.03)],-.39,.12,K)
        for k in range(3):oval(g,-.32+k*.32,z-.27,.053,.062,-.34,I,.012)
    return g


def reverse_panel(kind):
    g=Form();plate(g,[(-.48,.08),(.48,.08),(.48,3.98),(-.48,3.98)],-.255,.025,V if kind=='welcome' else R)
    if kind=='welcome':
        for j in range(7):
            z=.42+j*.46
            g.box((0,-.305,z),(.50,.025,.20),G);g.box((0,-.327,z),(.14,.02,.22),K)
    else:
        for j in range(5):
            z=.51+j*.65
            plate(g,[(-.35,z-.21),(-.17,z-.02),(.15,z+.11),(.36,z+.25),(.17,z+.01),(-.14,z-.10)],-.29,.03,I)
    return g


def append(g,part,position,axis=(1,0),scale=(1,1,1)):
    a=np.asarray(axis);n=np.array([-a[1],a[0]])
    start=len(g.vertices)
    for x,y,z in part.vertices:
        xy=np.asarray(position[:2])+a*x*scale[0]+n*y*scale[1]
        g.vertices.append((float(xy[0]),float(xy[1]),float(position[2]+z*scale[2])))
    g.faces.extend(tuple(start+i for i in f) for f in part.faces);g.slots.extend(part.slots)


def snapshot(objects):
    return {o.name:dict(mesh=o.data.name,vertices=len(o.data.vertices),faces=len(o.data.polygons),
        geometry=hashlib.sha256(np.asarray([tuple(v.co) for v in o.data.vertices],dtype='<f8').tobytes()+str([tuple(p.vertices) for p in o.data.polygons]).encode()).hexdigest(),
        matrix=[list(v) for v in o.matrix_world],collision=o.get('collision'),materials=[m.name for m in o.data.materials]) for o in objects}


def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open Seawall source')
    cfg=json.loads((ROOT/'manifests/m3-precinct-relief-settings.json').read_text())
    paths=['pipeline/blender/build_m3_precinct_relief.py','pipeline/blender/build_m3_landmark_forms.py','pipeline/blender/build_seawall_tree_library.py','pipeline/blender/diagnose_m3_landmark_winding.py','manifests/m3-precinct-relief-settings.json','manifests/totem-precinct-forms.json']+cfg['reference_files']
    inputs={p:sha(ROOT/p) for p in paths};version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-precinct-relief'/version;path=folder/'manifest.json'
    if path.exists():raise RuntimeError('Immutable relief export exists')
    scene=bpy.context.scene
    names=('SM_YeltonMemorial_','SM_PeopleSouth_','SM_PeopleNorthEstimate_')
    originals=[o for o in scene.objects if o.type=='MESH' and o.name.startswith(names)]
    if len(originals)!=8:raise RuntimeError('Expected two Yelton and six portal source meshes')
    before=snapshot(originals)
    source=json.loads((ROOT/'manifests/totem-precinct-forms.json').read_text());features={x['id']:x for x in source['features']}
    pending=[];m=features['SP_yelton_pole']['measured'];g=yelton()
    top=max(p[2] for p in g.vertices);s=(m['top_h_m']-m['ground_h_m'])/top
    world=Form();axis=np.asarray(m['broad_member']['axis']);axis=-axis if axis[0]<0 else axis
    append(world,g,[*m['centre_local_m'],m['ground_h_m']],axis,(1,1,s))
    pending.append(('Yelton','SP_yelton_pole',world,[*m['centre_local_m'],0]))
    for label,prefix,kind,axis in [('SouthPortal','SM_PeopleSouth_','welcome',features['SP_people_amongst']['measured']['beam_axis']),('NorthPortal','SM_PeopleNorthEstimate_','dancer',features['SP_people_amongst']['measured']['north_portal']['axis'])]:
        g=Form();members=[o for o in originals if o.name.startswith(prefix)];axis=np.asarray(axis,dtype=float);axis/=np.linalg.norm(axis)
        for obj in members:
            g.part([tuple(obj.matrix_world@v.co) for v in obj.data.vertices],[tuple(p.vertices) for p in obj.data.polygons],K)
        posts=sorted([o for o in members if '_Pier_' in o.name],key=lambda o:o.name)
        for index,obj in enumerate(posts):
            verts=np.asarray([tuple(obj.matrix_world@v.co) for v in obj.data.vertices]);xy=verts[:,:2].mean(axis=0);bottom=float(verts[:,2].min());height=float(verts[:,2].max()-bottom)
            # Source envelope stays exact. Relief may project 0.25 m beyond it.
            art=welcome() if kind=='welcome' else (whales() if index==0 else dancer())
            front_axis=axis if kind=='welcome' else -axis
            append(g,art,[*xy,bottom+.04],front_axis,(.73,1,(height-.10)/4))
            append(g,reverse_panel(kind),[*xy,bottom+.04],-front_axis,(.73,1,(height-.10)/4))
        beam=next(o for o in members if 'Crossbeam' in o.name);v=np.asarray([tuple(beam.matrix_world@q.co) for q in beam.data.vertices]);centre=v[:,:2].mean(axis=0);u=(v[:,:2]-centre)@axis;ends=(float(u.min()),float(u.max()));n=np.array([-axis[1],axis[0]])
        # Fit source beam face heights from its existing lower and upper vertices.
        lower=v[np.argsort(v[:,2])[:len(v)//2]];A=np.c_[u,np.ones(len(u))];coef=np.linalg.lstsq(A,v[:,2],rcond=None)[0]
        for side in [-1,1]:
            for j in range(22):
                a=ends[0]+(ends[1]-ends[0])*j/22;b=ends[0]+(ends[1]-ends[0])*(j+1)/22
                za=float(coef[0]*a+coef[1]);zb=float(coef[0]*b+coef[1]);depth=.178 if kind=='dancer' else .158
                local=Form();plate(local,[(a,za-.14),(b,zb-.14),(b,zb+.14)],-depth,.009,I if j%3==0 else (G if j%3==1 else R))
                if side>0:local.vertices=[(x,-y,z) for x,y,z in local.vertices]
                append(g,local,[*centre,0],axis)
        pending.append((label,'SP_people_amongst',g,[*np.mean([p[:2] for p in g.vertices],axis=0),0]))
    checker=runpy.run_path(str(ROOT/'pipeline/blender/diagnose_m3_landmark_winding.py'),run_name='relief_orientation')['components']
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='relief_export')
    collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection);materials=[]
    for row in cfg['materials']:
        mat=bpy.data.materials.new('M_M3Relief_'+row['name']+'_'+version);mat.diffuse_color=(*row['rgb'],1);mat.use_nodes=True
        node=mat.node_tree.nodes.get('Principled BSDF');node.inputs['Base Color'].default_value=mat.diffuse_color;node.inputs['Roughness'].default_value=row['roughness'];node.inputs['Metallic'].default_value=0;materials.append(mat)
    folder.mkdir(parents=True,exist_ok=True);exports=[]
    for label,fid,g,anchor in pending:
        g.vertices=[tuple(np.asarray(p)-anchor) for p in g.vertices]
        parts=checker(g.vertices,[list(f) for f in g.faces]);flipped=[]
        for part in parts:
            if part['repair_required']:
                for i in part['face_indexes']:g.faces[i]=tuple(reversed(g.faces[i]));flipped.append(i)
        checked=checker(g.vertices,[list(f) for f in g.faces])
        if any(p['repair_required'] for p in checked):raise RuntimeError('New relief has inward closed components')
        g.uvs=[(x*.31,z*.31+y*.07) for x,y,z in g.vertices]
        obj=helpers['make_object']('SM_M3Relief_'+label+'_'+version,g,collection,materials,anchor);obj['pipeline_owner']=OWNER;obj['feature_id']=fid;obj['collision']='none'
        for polygon in obj.data.polygons:polygon.use_smooth=False
        row=helpers['export_object'](obj,folder,scene);row.update(feature_id=fid,source_label=label,position_local_m=list(anchor),corrected_component_faces=len(flipped),remaining_inward_closed_components=0);exports.append(row)
    if before!=snapshot(originals):raise RuntimeError('Protected source geometry changed')
    hidden=[dict(name=o.name,hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()) for o in originals]
    result=dict(schema_version=1,owner=OWNER,version=version,input_hashes=inputs,settings=cfg,assets=exports,asset_root='/Game/StanleyPark/Seawall/PrecinctRelief/v_'+version,hidden_originals=hidden,protected_source_invariants=before,original_geometry_collision_unchanged=True,new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False)
    path.write_text(json.dumps(result,indent=2)+'\n');(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=path.relative_to(ROOT).as_posix(),sha256=sha(path)),indent=2)+'\n')
    for o in originals:o.hide_render=True;o.hide_set(True)
    return dict(version=version,manifest=path.relative_to(ROOT).as_posix(),assets=len(exports),triangles=sum(a['triangles'] for a in exports),protected_sources_unchanged=True)


if __name__ in {'__main__','<run_path>'}:
    result=build()
