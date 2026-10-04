"""Individually located M1 sculpture silhouettes; no carving or art textures.

The survey controls position and the major envelope. Small body poses and
hidden sections are explicit blockout estimates, not reconstructed artwork.
"""
import json
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import MultiPoint
import build_named_feature_blockouts as g
from acquire_sources import digest, save_json

ROOT=g.ROOT

def hull(name,points,material,fid):
    points=np.unique(np.asarray(points),axis=0);h=ConvexHull(points);faces=h.simplices.copy()
    for i,f in enumerate(faces):
        n=np.cross(points[f[1]]-points[f[0]],points[f[2]]-points[f[0]])
        if n@h.equations[i,:3]<0:faces[i]=f[::-1]
    g.mesh(name,points,faces,material,fid,'complex')

def ellipsoid(name,centre,radius,material,fid):
    # A convex low resolution envelope, with no duplicate pole vertices.
    t=np.arange(12)*2*np.pi/12;p=np.linspace(-np.pi/2,np.pi/2,9)
    points=np.array([[np.cos(a)*np.cos(b),np.sin(a)*np.cos(b),np.sin(b)] for a in t for b in p])
    hull(name,np.asarray(centre)+points*np.asarray(radius),material,fid)

def tube(name,a,b,radius,material,fid):
    a,b=np.asarray(a),np.asarray(b);axis=(b-a)/np.linalg.norm(b-a);seed=np.array([0.,0,1])
    if abs(axis@seed)>.9:seed=np.array([1.,0,0])
    u=np.cross(axis,seed);u/=np.linalg.norm(u);v=np.cross(axis,u);t=np.arange(12)*2*np.pi/12
    cross=np.cos(t)[:,None]*u+np.sin(t)[:,None]*v
    g.rings(name,[a+radius*cross,b+radius*cross],material,fid);g.ASSETS[-1]['collision']='complex'

def pedestal(tag,fid,centre,wh,base,top,angle=0,material='stone'):
    a=np.deg2rad(angle);u=np.array([np.cos(a),np.sin(a)]);v=np.array([-u[1],u[0]])
    rows=[[[*(centre+x*u+y*v),z] for x,y in [(-wh[0]/2,-wh[1]/2),(wh[0]/2,-wh[1]/2),(wh[0]/2,wh[1]/2),(-wh[0]/2,wh[1]/2)]] for z in [base,top]]
    g.rings('SM_'+tag,rows,material,fid);g.ASSETS[-1]['collision']='complex'

def source(crop,art):
    return [f'manifests/named-{crop}-survey.json',f'evidence/corridor/ortho-utm/named-{crop}.json',
        f'https://covapp.vancouver.ca/PublicArtRegistry/ArtworkDetail.aspx?ArtworkId={art}',
        'https://vancouver.ca/parks-recreation-culture/monuments-and-sculptures.aspx']

def empress():
    fid='SP_empress_japan';q,c=g.survey('north-sculptures')
    body=q[(q[:,0]>1201)&(q[:,0]<1205.2)&(q[:,1]>8)&(q[:,1]<14.7)&(q[:,2]>5.12)&(q[:,2]<6.8)]
    # Small overlapping measured hull sections preserve the rising figurehead
    # envelope instead of filling the whole tall empty area with one hull.
    parts=[]
    for i,(low,high) in enumerate([(8.0,10.3),(9.8,11.6),(11.1,12.8),(12.3,14.7)]):
        s=body[(body[:,1]>=low)&(body[:,1]<=high)]
        if len(s)>4:hull(f'SM_Empress_FigureheadEnvelope_{i:02d}',s,'figure_white',fid);parts.append(len(s))
    pedestal('Empress_StoneBase',fid,np.array([1203.1,10.55]),[1.35,4.4],3.31,4.44,-14)
    tube('SM_Empress_ConcealedMount',[1203.0,10.4,4.42],[1203.25,10.65,5.5],.23,'steel',fid)
    g.feature(fid,'Empress of Japan figurehead',source('north-sculptures',98),
        dict(centre_local_m=[1203.3,11.3],figure_returns=len(body),figure_bounds_m=[body.min(0).tolist(),body.max(0).tolist()],hull_section_returns=parts,
             placement_correction='The City registry point is about 695 m east of the actual figurehead. OSM node 1178757953 plus the 2022 ortho and separate rising survey trace identify the current form.'),
        dict(stone_base_xy_m=[1.35,4.4],stone_base_top_h_m=4.44,hidden_mount_radius_m=.23,base_angle_degrees=-14),
        'Measured coarse figurehead envelope only. Dragon carving, mouth openings, paint, support detail and plaque are unfinished. Sparse airborne undersides are closed by local convex hull sections; this is not an exact artwork replica.')

def wetsuit():
    fid='SP_girl_wetsuit';q,c=g.survey('north-sculptures');s=q[(np.linalg.norm(q[:,:2]-[1246,4.5],axis=1)<2.7)&(q[:,2]<2.15)&(q[:,2]>-.4)]
    # Rock shell returns and an estimated hidden basal footprint form one hull.
    foot=s[s[:,2]<.6].copy();foot[:,2]=-.9
    hull('SM_Wetsuit_IntertidalBoulder',np.vstack([s,foot]),'stone',fid)
    centre=np.array([1245.92,4.22]);top=q[(np.linalg.norm(q[:,:2]-centre,axis=1)<.55)&(q[:,2]>2.2)&(q[:,2]<3)]
    ellipsoid('SM_Wetsuit_Head',[1245.92,4.22,2.60],[.14,.15,.145],'bronze',fid)
    tube('SM_Wetsuit_Torso',[1246.05,4.48,1.86],[1245.94,4.27,2.40],.20,'bronze',fid)
    tube('SM_Wetsuit_Neck',[1245.94,4.27,2.35],[1245.92,4.22,2.55],.09,'bronze',fid)
    # Seated body, bent knees and the two fins retain the published basic pose.
    for i,dy in enumerate([-.16,.16]):
        tube(f'SM_Wetsuit_Thigh_{i}',[1246.05,4.48+dy,1.91],[1245.65,4.77+dy,1.81],.12,'bronze',fid)
        tube(f'SM_Wetsuit_Shin_{i}',[1245.65,4.77+dy,1.81],[1245.58,4.94+dy,1.36],.08,'bronze',fid)
        ellipsoid(f'SM_Wetsuit_Fin_{i}',[1245.47,5.07+dy,1.28],[.13,.28,.045],'bronze',fid)
        tube(f'SM_Wetsuit_Arm_{i}',[1245.92,4.22+dy*1.7,2.31],[1245.68,4.66+dy,1.91],.065,'bronze',fid)
    g.feature(fid,'Girl in Wetsuit and intertidal boulder',source('north-sculptures',97),
        dict(centre_local_m=centre.tolist(),rock_returns=len(s),head_returns=len(top),head_maximum_h_m=float(top[:,2].max()),rock_shell_bounds_m=[s.min(0).tolist(),s.max(0).tolist()],
             placement_correction='OSM node 1337999643 plus isolated 2022 intertidal boulder and figure returns replace the incorrect registry search point.'),
        dict(hidden_rock_base_h_m=-.9,body_pose='Seated figure with bent legs and fins; limb pose, facing, radii and hidden attachment are M1 estimates anchored to the measured head and rock'),
        'Distinct boulder and seated figure are present. Face, hands, mask, exact body pose, bolts and submerged concrete ring are unfinished. Body fit uncertainty is about 0.3 m; no survey accuracy claim.')

def harry():
    fid='SP_harry_jerome';q,c=g.survey('harry-jerome');near=q[np.linalg.norm(q[:,:2]-[1743.3,-485.1],axis=1)<2]
    base=near[(near[:,2]>6.4)&(near[:,2]<6.7)];centre=base[:,:2].mean(0);rect=np.array(MultiPoint(base[:,:2]).minimum_rotated_rectangle.exterior.coords)[:4]
    # Source gives plinth geometry and upper torso/head, while limbs are sparse.
    g.rings('SM_HarryJerome_Plinth',[[[*p,z] for p in rect[::-1]] for z in [5.53,6.59]],'stone',fid);g.ASSETS[-1]['collision']='complex'
    ellipsoid('SM_HarryJerome_Head',[1742.80,-484.77,8.72],[.14,.15,.19],'bronze',fid)
    tube('SM_HarryJerome_Neck',[1742.98,-484.96,8.40],[1742.80,-484.77,8.60],.10,'bronze',fid)
    tube('SM_HarryJerome_Torso',[1743.36,-485.24,7.72],[1742.98,-484.96,8.45],.23,'bronze',fid)
    bones=[([1743.35,-485.22,7.75],[1743.86,-485.55,7.28],.15),([1743.86,-485.55,7.28],[1744.00,-485.83,6.62],.11),
           ([1743.29,-485.33,7.75],[1742.73,-485.61,7.12],.15),([1742.73,-485.61,7.12],[1743.38,-485.79,6.65],.10),
           ([1742.94,-484.80,8.31],[1743.51,-484.50,7.94],.09),([1743.51,-484.50,7.94],[1743.32,-484.32,8.43],.075),
           ([1743.15,-485.22,8.31],[1742.67,-485.50,7.98],.09),([1742.67,-485.50,7.98],[1742.27,-485.28,8.18],.075)]
    for i,(a,b,r) in enumerate(bones):tube(f'SM_HarryJerome_Limb_{i:02d}',a,b,r,'bronze',fid)
    g.feature(fid,'Harry Jerome running statue',source('harry-jerome',162)+['https://vancouver.ca/people-programs/honoring-black-history-in-parks.aspx'],
        dict(centre_local_m=centre.tolist(),plinth_returns=len(base),plinth_outline_m=rect.tolist(),plinth_top_h_m=6.59,head_observed_max_h_m=8.911,
             identity='Official site identifies the running statue; OSM point and nearby registry agree with the isolated plinth/bronze survey returns.'),
        dict(plinth_bottom_h_m=5.53,limbs='Runner pose and limb radii are an explicit anatomical envelope estimate; sparse returns constrain head, torso and plinth, not complete joints'),
        'M1 runner silhouette and survey plinth only. Exact limb pose, anatomy, facial likeness, finish and plaque remain unfinished; estimated joints are not survey controls.')

def shore():
    fid='SP_shore_to_shore';q,c=g.survey('totem-sculptures');near=q[np.linalg.norm(q[:,:2]-[1635.65,-405.48],axis=1)<2.2]
    base=near[(near[:,2]>4.10)&(near[:,2]<4.35)];centre=base[:,:2].mean(0)
    theta=np.arange(28)*2*np.pi/28
    g.rings('SM_ShoreToShore_StonePodium',[np.column_stack([centre+np.column_stack([np.cos(theta),np.sin(theta)])*r,np.full(28,z)]) for r,z in [(1.85,3.53),(1.82,4.25)]],'stone',fid);g.ASSETS[-1]['collision']='complex'
    # Three figure envelopes around the tall carved bronze centre. The artist
    # description supports the number and overall form; details stay deferred.
    tube('SM_ShoreToShore_CentralForm',[1635.75,-405.4,4.24],[1635.7,-405.4,7.35],.30,'bronze',fid)
    ellipsoid('SM_ShoreToShore_UpperForm',[1635.73,-405.35,7.69],[.18,.20,.40],'bronze',fid)
    for i,xy in enumerate([[1635.05,-405.17],[1636.15,-405.10],[1635.77,-406.10]]):
        ellipsoid(f'SM_ShoreToShore_FigureHead_{i}',[*xy,6.14],[.14,.14,.19],'bronze',fid)
        tube(f'SM_ShoreToShore_FigureBody_{i}',[*xy,4.36],[*xy,5.97],.22,'bronze',fid)
    g.feature(fid,'Shore to Shore',source('totem-sculptures',596)+['https://shoretoshore.ca/'],
        dict(centre_local_m=centre.tolist(),podium_returns=len(base),podium_top_h_m=4.25,upper_observed_h_m=8.102,
             placement_correction='OSM node 7519548166, circular podium in ortho and isolated bronze returns identify this position; registry point is about 368 m northeast.'),
        dict(podium_radius_m=1.82,figures='Three simple standing envelopes and central tall form; positions/radii estimated within measured outer envelope'),
        'No carving, individual face, garment, exact sculptural pose or stone inscriptions. The three figure count and 14-foot overall composition are supported by the artist; the small body arrangement remains a blockout estimate.')

def main():
    g.OUT=ROOT/'data/derived/route-sculptures';g.OUT.mkdir(exist_ok=True);g.ASSETS.clear();g.FEATURES.clear()
    g.COLORS.update(bronze=[.18,.22,.18],figure_white=[.77,.75,.62])
    empress();wetsuit();harry();shore()
    for a in g.ASSETS:a['collision_reason']='Closed source-located M1 envelope. Detailed triangle collision preserves open spaces between limbs and avoids a large invisible blocking box; live contact remains untested.'
    d=dict(schema_version=1,revision='route-sculptures-m1-r1',assets=g.ASSETS,features=g.FEATURES,acceptance=False,
        source_period='City 2022 survey and imagery; individual official identity references',target_period='September 2026',
        reference_rights='City survey derivatives use OGL-Vancouver. Registry metadata does not grant artwork rights. No source photos, carving textures or text inscriptions are distributed.',
        input_hashes={f'manifests/named-{x}-survey.json':digest(ROOT/f'manifests/named-{x}-survey.json') for x in ['north-sculptures','totem-sculptures','harry-jerome']})
    save_json(ROOT/'manifests/route-sculpture-blockouts.json',d)
    print(json.dumps(dict(assets=len(g.ASSETS),triangles=sum(a['triangles'] for a in g.ASSETS),manifest_sha256=digest(ROOT/'manifests/route-sculpture-blockouts.json'))))

if __name__=='__main__':main()
