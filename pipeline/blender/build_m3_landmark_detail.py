"""Source-informed runner, gun support and eight individual pole forms.

Serial Blender authoring only. Source objects stay intact with their collision;
only visible source envelopes are hidden after all exports succeed. No save.
"""
from pathlib import Path
import hashlib
import json
import math
import runpy

import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3LandmarkDetail'
FORM_SOURCE='pipeline/blender/build_m3_landmark_forms.py'
Form=runpy.run_path(str(ROOT/FORM_SOURCE),run_name='detail_geometry')['Form']
B,G,D,W,R,V,U,C,Y=range(9)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def oriented_ellipsoid(g,centre,radii,direction,slot):
    start=len(g.vertices);g.ellipsoid((0,0,0),radii,slot,12,20)
    n=np.asarray(direction,float);n/=np.linalg.norm(n)
    u=np.cross([0,1,0],n);u/=np.linalg.norm(u);v=np.cross(n,u)
    for i in range(start,len(g.vertices)):
        x,y,z=g.vertices[i];g.vertices[i]=tuple(np.asarray(centre)+u*x+v*y+n*z)


def runner():
    """Both arms trail, front knee folds back, rear toe supports the bronze."""
    g=Form()
    # Coordinates: forward x, lateral y, plinth top z=0.
    chains=[([(-.72,.12,.10),(-.63,.12,.41),(-.32,.10,.91),(-.06,.10,1.24)],[.075,.12,.14,.19]),
            ([(-.10,-.18,1.28),(.16,-.22,.96),(.27,-.24,.81),(-.10,-.24,.75),(-.54,-.24,.88)],[.21,.20,.13,.12,.07]),
            ([(.29,.27,1.83),(-.03,.39,1.83),(-.39,.49,1.75),(-.78,.51,1.65)],[.14,.12,.09,.055]),
            ([(.32,-.23,1.83),(.10,-.34,1.63),(-.18,-.42,1.61),(-.50,-.46,1.65)],[.13,.105,.075,.05])]
    for points,radii in chains: g.tube(points,radii,B,18)
    oriented_ellipsoid(g,(-.025,0,1.25),(.28,.28,.26),(.16,0,1),B)
    oriented_ellipsoid(g,(.20,0,1.61),(.30,.24,.43),(.42,0,.8),B)
    for side in [-1,1]:
        g.ellipsoid((.30,side*.25,1.85),(.19,.15,.16),B,12,20)
        g.ellipsoid((.19,side*.11,1.81),(.14,.12,.14),B)
    g.tube([(.38,0,1.87),(.51,0,2.02)],[.11,.10],B,16)
    oriented_ellipsoid(g,(.56,0,2.14),(.16,.145,.21),(.15,0,1),B)
    g.ellipsoid((.65,0,2.11),(.10,.13,.13),B)
    g.ellipsoid((.724,0,2.14),(.066,.038,.07),B)
    g.ellipsoid((.709,0,2.025),(.065,.09,.036),B)
    for side in [-1,1]:
        g.ellipsoid((.53,side*.144,2.12),(.045,.028,.067),B)
        g.tube([(.689,side*.092,2.21),(.719,side*.042,2.20)],[.027,.022],B,10)
    # Shoes extend back at the raised ankle and forward at the support toe.
    oriented_ellipsoid(g,(-.68,.12,.07),(.10,.09,.20),(.65,0,-.7),B)
    oriented_ellipsoid(g,(-.59,-.24,.94),(.09,.095,.21),(-.6,0,.75),B)
    for x,y,z in [(-.78,.51,1.65),(-.50,-.46,1.65)]:
        g.ellipsoid((x-.025,y,z),(.09,.07,.045),B)
        for j in range(4):
            yy=y+(j-1.5)*.026
            g.tube([(x-.05,yy,z),(x-.11,yy,z-.035),(x-.10,yy,z-.075)],[.016,.013,.01],B,8)
        g.tube([(x-.01,y-.04,z),(x-.06,y-.09,z-.02)],[.023,.015],B,8)
    # Raised folds follow a singlet neckline, shorts hem and waistband.
    for side in [-1,1]:
        g.tube([(.43,side*.13,1.88),(.35,side*.09,1.71),(.29,0,1.66)],[.018]*3,B,8)
        g.tube([(-.13,side*.22,1.32),(.07,side*.24,1.25),(.20,side*.18,1.19)],[.019]*3,B,8)
    return g


def prism(g,outline,depth,slot,y=0):
    count=len(outline);vertices=[(x,y+d,z) for d in [-depth/2,depth/2] for x,z in outline]
    faces=[tuple(reversed(range(count))),tuple(range(count,count*2))]
    faces.extend((i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count))
    g.part(vertices,faces,slot)


def eye(g,x,z,size=.15,col=U,wood=False,y=-.38):
    g.ellipsoid((x,y,z),(size*1.25,.036,size),C if wood else W,7,14)
    g.ellipsoid((x,y-.033,z),(size,.025,size*.75),C if wood else col,7,14)
    g.ellipsoid((x,y-.054,z),(size*.48,.018,size*.55),C if wood else D,7,14)


def face(g,z,h=1,width=.8,kind='human',wood=False,base=C):
    """Carved cheek, eyebrow, eye, mouth and beak volumes; front is -y."""
    col=C if wood else base
    g.ellipsoid((0,0,z),(width*.54,.38,h*.48),col,10,20)
    for side in [-1,1]:
        eye(g,side*width*.24,z+h*.13,width*.18,wood=wood)
        g.tube([(side*width*.47,-.30,z+h*.30),(side*width*.22,-.41,z+h*.32),(0,-.41,z+h*.20)],
            [.045,.045,.029],C if wood else D,9)
    if kind in {'bird','raven'}:
        prism(g,[(-width*.15,z+h*.16),(0,z-h*.38),(width*.15,z+h*.16),(0,z+h*.31)],.46,C if wood else Y,-.46)
    else:
        g.ellipsoid((0,-.41,z-h*.01),(width*.11,.105,h*.12),C if wood else R)
    g.ellipsoid((0,-.37,z-h*.23),(width*.31,.07,h*.12),C if wood else R,8,16)
    g.ellipsoid((0,-.425,z-h*.23),(width*.25,.022,h*.035),C if wood else D,6,16)
    if kind=='bear' and not wood:
        for j in range(5):g.box(((j-2)*width*.08,-.45,z-h*.205),(width*.062,.025,h*.065),W)
        for side in [-1,1]:g.box((side*width*.37,.01,z+h*.44),(width*.16,.25,h*.22),D)


def hands(g,z,width=.7,col=C,held=False):
    for side in [-1,1]:
        g.tube([(side*width*.48,0,z+.34),(side*width*.59,-.16,z),(side*width*.25,-.38,z+.01)],[.10,.11,.09],col)
        for j in range(4):g.tube([(side*width*.25,-.43,z+.10-j*.052),(side*width*.05,-.44,z+.10-j*.052)],[.025,.022],col,8)
    if held: g.ellipsoid((0,-.32,z+.25),(.21,.19,.34),U if col!=C else C)


def body(g,z,h=.8,width=.65,col=C):
    g.ellipsoid((0,0,z),(width*.50,.30,h*.58),col)
    hands(g,z,width,col)
    for side in [-1,1]:
        g.ellipsoid((side*width*.28,-.10,z-h*.43),(.14,.23,h*.25),col)
        g.ellipsoid((side*width*.28,-.30,z-h*.65),(.14,.15,.075),W if col!=C else C)


def wing(g,z,span,rise=.3,white=True):
    """Source wing silhouette and repeated feather bands, with open space below."""
    for side in [-1,1]:
        outline=[(side*.28,z+.18),(side*span*.5,z+rise+.25),(side*span*.46,z+rise-.12),
                 (side*span*.34,z-.25),(side*.35,z-.40)]
        prism(g,outline,.13,W if white else D)
        for j in range(7):
            t=(j+.45)/7; x=.35+t*(span*.45-.35);top=z+.14+t*rise;bottom=z-.35+t*t*(rise-.05)
            g.tube([(side*x,-.082,top),(side*(x+.04),-.085,bottom)],[.070,.048],D if white else W,8)
            g.tube([(side*x,-.101,top-.05),(side*(x+.02),-.107,bottom+.045)],[.034,.022],R if j%2 else U,8)


def pole(kind):
    g=Form()
    wood=kind=='beaver';base=C if wood else D
    levels=[0,1.5,3.5,5.5,6.65] if kind=='thunderbird' else [0,2,5,8,9.8]
    g.tube([(0,0,z) for z in levels],[.39,.40,.37,.35,.30],base,20)
    if kind=='beaver':
        for z in [1.2,3.0,4.6,6.35]:
            body(g,z-.25,1.0,.78,C);face(g,z+.5,.72,.83,wood=True)
            for side in [-1,1]:
                g.ellipsoid((side*.33,-.35,z-.12),(.19,.17,.26),C)
        face(g,8.0,1.05,1.0,wood=True);hands(g,7.1,1.1,C)
        for side in [-1,1]:
            start=len(g.vertices)
            face(g,7.24,.45,.32,wood=True);body(g,6.86,.40,.30,C)
            for i in range(start,len(g.vertices)):
                x,y,z=g.vertices[i];g.vertices[i]=(x+side*.24,y-.20,z)
        body(g,8.91,.8,.68,C);face(g,9.48,.66,.70,wood=True)
    elif kind=='matilpi':
        face(g,1.0,1.2,.78,'bird',base=D)
        # Broad flat central whale/bird panel and folded wings.
        prism(g,[(-.47,2),(-.48,7.2),(.48,7.2),(.47,2)],.31,C)
        for side in [-1,1]:
            g.box((side*.30,-.20,4.75),(.26,.045,4.1),D)
            for z in [2.5,3.1,5.6,6.15]:g.box((side*.28,-.23,z),(.22,.04,.34),R)
        prism(g,[(-.15,4.6),(0,5.25),(.16,4.6)],.55,W,-.34)
        face(g,7.4,.70,.8,'human',base=C);body(g,7.1,.55,.7,D)
        face(g,8.98,1.30,.83,'bird',base=D)
        for side in [-1,1]:
            g.box((side*.33,0,9.77),(.14,.28,.53),D)
            g.box((side*.21,-.3,7.88),(.23,.1,.38),Y)
    elif kind=='kakasolas':
        face(g,.7,1.15,.72,'raven',base=D)
        body(g,2.0,.9,.74,D);face(g,2.75,.9,.83,'human',base=D)
        face(g,3.73,.8,.79,'bird',base=D)
        body(g,4.80,1.1,.78,C);face(g,5.52,.80,.8,'human',base=C);hands(g,4.90,.82,W,True)
        face(g,6.75,1.15,.93,'bear',base=D)
        body(g,7.8,.75,.74,W);face(g,8.92,1.1,.8,'bird',base=W);wing(g,8.15,3.65,.9)
        for side in [-1,1]:g.box((side*.27,0,9.66),(.17,.24,.38),D)
    elif kind=='thunderbird':
        body(g,1.0,1.45,.90,C);face(g,1.7,.55,.52,'human',base=C)
        face(g,3.2,1.35,1.08,'bear',base=D)
        body(g,4.8,1.8,.86,W);face(g,6.6,1.4,1.12,'bird',base=W);wing(g,5.5,5.5,.35)
        # Normalize this shorter house-post profile to the full local range.
        g.vertices=[(x,y,z*1.35) for x,y,z in g.vertices]
    elif kind=='skedans':
        body(g,1.3,.8,.65,D);face(g,1.88,.6,.65,'bird',base=D)
        body(g,3.0,1.5,.8,C);face(g,4.12,1.3,1.0,'bear',base=C)
        body(g,5.9,1.4,.80,C);face(g,7.02,1.3,1.0,'bear',base=C)
        # Wide mortuary board and raised Moon face.
        g.box((0,.06,9.1),(2.50,.18,1.52),W)
        for z in [8.37,9.83]:g.box((0,-.04,z),(2.5,.055,.20),D)
        g.ellipsoid((0,-.09,9.08),(.66,.04,.65),R)
        face(g,9.10,1.02,.90,'bird',base=C)
        for side in [-1,1]:
            eye(g,side*.96,9.40,.17,R,y=-.045)
            g.tube([(side*1.14,-.065,8.65),(side*.91,-.065,8.73),(side*.96,-.065,9.11)],[.045]*3,D,8)
    elif kind=='wakas':
        face(g,.85,1.1,.80,'raven',base=D)
        body(g,2.3,1.0,.78,D);face(g,3.10,.95,.82,'bear',base=D)
        face(g,4.15,.88,.77,'raven',base=W)
        body(g,5.2,1.0,.75,D);face(g,6.0,.82,.8,'bear',base=D)
        # Raised black-and-white whale with long dorsal/side projections.
        g.ellipsoid((0,-.05,7.4),(.31,.37,.8),D)
        g.tube([(0,-.34,7.0),(0,-.55,7.65),(0,-.34,8.0)],[.12,.15,.08],W)
        prism(g,[(.21,7.5),(.9,7.95),(.63,7.45)],.1,D)
        body(g,8.6,.55,.55,D);face(g,9.20,.65,.63,'bird',base=D);wing(g,8.95,3.15,.2,False)
    elif kind=='skychief':
        body(g,.8,.70,.73,C);face(g,1.33,.59,.63,base=C)
        face(g,2.6,1.3,.94,'bear',base=C)
        # Long whale profile, paired wolf-headed lightning snakes and bird.
        g.ellipsoid((0,-.15,4.35),(.34,.24,1.12),D)
        for side in [-1,1]:
            g.tube([(side*.30,-.06,3.4),(side*.40,-.05,4.5),(side*.75,-.07,4.9)],[.1,.09,.07],U)
            g.ellipsoid((side*.71,-.10,4.98),(.18,.13,.12),R)
        body(g,5.45,.75,.6,R);face(g,6.02,.60,.67,'bird',base=C)
        face(g,7.38,.76,.70,'human',base=C)
        g.ring((0,-.37,7.39),.48,.06,Y)
        face(g,9.0,.81,.77,'human',base=C)
        g.tube([(0,0,9.60),(0,0,9.83)],[.38,.37],R,24)
    elif kind=='gaakstalas':
        body(g,.54,.6,.74,D);face(g,1.12,.7,.75,'human',base=D)
        for side in [-1,1]:g.tube([(side*.3,0,.85),(side*.8,-.02,1.1),(side*.95,-.03,1.28)],[.08,.075,.05],D)
        body(g,2.0,.72,.76,D);face(g,2.74,.82,.80,'bear',base=D)
        body(g,3.78,1.0,.78,W);face(g,4.72,.87,.79,'bird',base=D)
        # Slender central human against the whale, above a small Moon face.
        face(g,5.56,.49,.52,'human',base=W);body(g,6.07,.95,.40,C);face(g,6.62,.38,.44,base=C)
        face(g,7.4,.75,.86,'bear',base=D)
        body(g,8.25,.7,.72,C);face(g,8.89,.65,.75,base=W)
        g.tube([(-.72,-.17,8.43),(0,-.29,8.33),(.72,-.17,8.43)],[.09,.13,.09],D)
        face(g,9.56,.4,.40,'bird',base=W);wing(g,9.42,2.0,.35)
    else: raise RuntimeError('Unknown pole '+kind)
    return g


def gun_detail(measured):
    g=Form();base=measured['base_m'];eave=measured['eave_m'];length=measured['roof_length_m'];width=measured['roof_width_m']
    # Foundation is an inferred hidden continuation of the photographed platform.
    radius=math.hypot(length/2,width/2)+.55
    g.tube([(0,0,-.8),(0,0,base-.07)],[radius+.15,radius],G,48)
    g.tube([(0,0,base-.08),(0,0,base+.01)],[radius,radius],G,48)
    for side in [-1,1]:
        # Tapered masonry buttress and diagonal green roof strut.
        g.box((-.72,side*(width/2-.27),(base+eave-1.15)/2),(.95,.57,eave-1.15-base),G,.58)
        g.tube([(-.72,side*(width/2-.15),eave-1.12),(-length/2+.2,side*(width/2-.15),eave-.10)],[.065,.065],V)
        for j in range(4):
            x=-length/2+.65+j*(length-1.30)/3
            g.box((x,side*(width/2-.14),eave-.56),((length-1.3)/3-.08,.035,.90),U)
        # Fine open mesh uses explicit rods; does not become an opaque wall.
        for x in np.arange(-length/2+.23,length/2-.19,.16):
            g.tube([(x,side*(width/2-.14),base+.1),(x,side*(width/2-.14),eave-1.04)],[.006,.006],D,5)
        for z in np.arange(base+.16,eave-1.0,.18):
            g.tube([(-length/2+.2,side*(width/2-.14),z),(length/2-.2,side*(width/2-.14),z)],[.006,.006],D,5)
    # Cannon carriage, trunnions, cascabel and open-looking muzzle rim.
    for side in [-1,1]:
        g.box((.0,side*.32,base+.47),(1.26,.17,.77),C,.85)
        for x in [-.46,.49]:g.ellipsoid((x,side*.43,base+.18),(.20,.11,.20),D)
    g.tube([(-.15,-.53,base+.97),(-.15,.53,base+.97)],[.09,.09],D)
    g.tube([(-1.00,0,base+1.0),(-.86,0,base+1.0)],[.12,.14],D)
    # Barrel axis is local x; the dark inset does not fill the bright muzzle rim.
    g.ellipsoid((1.20,0,base+1.08),(.018,.115,.115),D)
    g.box((length/2-.18,0,base+1.54),(.026,.54,.38),W)
    return g


def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve(): raise RuntimeError('Open the Seawall source')
    cfg=json.loads((ROOT/'manifests/m3-landmark-detail-settings.json').read_text())
    paths=[FORM_SOURCE,'pipeline/blender/build_m3_landmark_detail.py','pipeline/blender/build_seawall_tree_library.py','manifests/m3-landmark-detail-settings.json','manifests/totem-precinct-forms.json','manifests/named-feature-blockouts.json','manifests/route-sculpture-blockouts.json']
    paths+=cfg['reference_files']
    inputs={p:sha(ROOT/p) for p in paths};version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-landmark-detail'/version;manifest_path=folder/'manifest.json'
    if manifest_path.exists():raise RuntimeError('Immutable detail export exists')
    scene=bpy.context.scene
    if abs(scene.unit_settings.scale_length-1)>1e-7:raise RuntimeError('Scene must use metres')
    collection=bpy.data.collections.new(OWNER+'_'+version);scene.collection.children.link(collection)
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='m3_detail_export')
    materials=[]
    for row in cfg['materials']:
        m=bpy.data.materials.new('M_M3Detail_'+row['name']+'_'+version);m.diffuse_color=(*row['rgb'],1);m.use_nodes=True
        s=m.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=m.diffuse_color;s.inputs['Roughness'].default_value=row['roughness'];s.inputs['Metallic'].default_value=row['metallic'];materials.append(m)
    pending=[];hide=[]
    # Bronze pose is fitted back to the independently measured head and plinth.
    g=runner();angle=math.radians(140);c,s=math.cos(angle),math.sin(angle)
    head=np.array([.56*c,.56*s]);xy=np.array([1742.80,-484.77])-head
    pending.append(('runner','SP_harry_jerome',g,[*xy,6.59],angle,1.0,True))
    hide.extend(o for o in scene.objects if o.name.startswith('SM_HarryJerome_') and o.name!='SM_HarryJerome_Plinth')
    features=json.loads((ROOT/'manifests/named-feature-blockouts.json').read_text())['features'];gun=next(r['measured'] for r in features if r['id']=='SP_nine_oclock')
    barrel=bpy.data.objects.get('SM_NineClockGun_Barrel')
    if barrel is None:raise RuntimeError('Missing original gun barrel')
    points=np.asarray([tuple(barrel.matrix_world@v.co) for v in barrel.data.vertices]);e,v=np.linalg.eigh(np.cov(points[:,:2].T));u=v[:,-1]
    if u[1]>0:u=-u
    pending.append(('gun_support','SP_nine_oclock',gun_detail(gun),[*gun['centre_local_m'],0],math.atan2(u[1],u[0]),1.,False))
    source=json.loads((ROOT/'manifests/totem-precinct-forms.json').read_text());poles=source['features'][0]['measured']['individual_forms']
    order=['beaver','matilpi','kakasolas','thunderbird','gaakstalas','skedans','wakas','skychief']
    for row,kind in zip(poles,order):
        z=row['ground_h_m'];height=row.get('top_h_m',z+row.get('height_above_ground_m',0))-z
        g=pole(kind);actual=max(p[2] for p in g.vertices);scale=height/actual
        # Horizontal dimensions follow photographed proportions scaled to the observed height.
        pending.append((kind,'SP_totem_precinct',g,[*row['centre_local_m'],z-.03],math.radians(122),scale,False))
        hide.extend(o for o in scene.objects if o.name.startswith('SM_'+row['component']+'_'))
    if len(pending)!=10:raise RuntimeError('Expected runner, support and eight poles')
    folder.mkdir(parents=True,exist_ok=True);exports=[]
    for label,fid,g,position,angle,scale,merge in pending:
        c,s=math.cos(angle),math.sin(angle);g.vertices=[((x*c-y*s)*scale,(x*s+y*c)*scale,z*scale) for x,y,z in g.vertices]
        obj=helpers['make_object']('SM_M3Detail_'+label+'_'+version,g,collection,materials,position)
        obj['pipeline_owner']=OWNER;obj['feature_id']=fid;obj['collision']='none'
        if merge:
            bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
            m=obj.modifiers.new('Unified bronze anatomy','REMESH');m.mode='VOXEL';m.voxel_size=.024;m.use_smooth_shade=True
            bpy.ops.object.modifier_apply(modifier=m.name)
            m=obj.modifiers.new('Bronze surface','SMOOTH');m.factor=.6;m.iterations=3;bpy.ops.object.modifier_apply(modifier=m.name)
            m=obj.modifiers.new('Bronze render budget','DECIMATE');m.ratio=.50;bpy.ops.object.modifier_apply(modifier=m.name)
            for p in obj.data.polygons:p.material_index=B;p.use_smooth=True
        else:
            for p in obj.data.polygons:p.use_smooth=p.material_index not in {G,W,D}
        item=helpers['export_object'](obj,folder,scene);item.update(feature_id=fid,source_label=label,position_local_m=position);exports.append(item)
    hidden=[dict(name=o.name,hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()) for o in sorted(set(hide),key=lambda o:o.name)]
    if not hidden:raise RuntimeError('No source envelopes matched')
    manifest=dict(schema_version=1,owner=OWNER,version=version,input_hashes=inputs,settings=cfg,assets=exports,
        asset_root='/Game/StanleyPark/Seawall/LandmarkDetail/v_'+version,hidden_originals=hidden,
        original_collision_unchanged=True,new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False)
    manifest_path.write_text(json.dumps(manifest,indent=2));(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(),sha256=sha(manifest_path)),indent=2))
    for obj in hide:obj.hide_render=True;obj.hide_set(True)
    return dict(version=version,forms=len(exports),triangles=sum(a['triangles'] for a in exports),manifest=str(manifest_path))


if __name__ in {'__main__','<run_path>'}:
    result=build()
