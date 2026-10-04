"""Deterministic original branches and folded botanical cards in metres.

Meshes have two material slots: bark and masked foliage. No solid foliage
envelopes are used. A local tree is 20 m high with a 5 m crown radius limit.
"""
import math
import random

import numpy as np


def unit(vector):
    value = np.asarray(vector, dtype=float)
    return value / max(float(np.linalg.norm(value)), 1e-9)


class Geometry:
    def __init__(self):
        self.vertices, self.faces, self.slots, self.uvs = [], [], [], []

    def vertex(self, point, uv=(0, 0)):
        self.vertices.append(tuple(point))
        self.uvs.append(tuple(uv))
        return len(self.vertices)-1

    def face(self, indices, slot):
        self.faces.append(tuple(indices))
        self.slots.append(slot)

    def tube(self, points, radii, sides=8, phase=0):
        start = len(self.vertices)
        points = np.asarray(points, dtype=float)
        along = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
        previous_u = None
        for i, (point, radius) in enumerate(zip(points,radii)):
            tangent = unit(points[min(i+1,len(points)-1)]-points[max(i-1,0)])
            u = unit(np.cross(tangent,(0,1,0)))
            if np.linalg.norm(u)<.1:
                u = unit(np.cross(tangent,(1,0,0)))
            if previous_u is not None and np.dot(u,previous_u)<0:
                u = -u
            previous_u = u
            v = unit(np.cross(tangent,u))
            for j in range(sides+1):
                angle = math.tau*j/sides + phase
                # Shallow fluting creates a bark silhouette without a smooth pole.
                flute = 1 + .07*math.sin(angle*5 + i*.41)
                self.vertex(point + radius*flute*(math.cos(angle)*u+math.sin(angle)*v),
                            (j/sides*math.tau*max(radii[0],.035)*1.8, along[i]*.7))
        stride = sides+1
        self.face(reversed([start+j for j in range(sides)]),0)
        for ring in range(len(points)-1):
            for j in range(sides):
                a = start+ring*stride+j
                self.face((a,a+1,a+stride+1,a+stride),0)
        self.face([start+(len(points)-1)*stride+j for j in range(sides)],0)

    def card(self, base, direction, across, length, width, cell, fold=.10, flip=False):
        base, direction = np.asarray(base), unit(direction)
        across = unit(np.asarray(across)-direction*np.dot(across,direction))
        if np.linalg.norm(across)<.1:
            across = unit(np.cross(direction,(0,0,1)))
        normal = unit(np.cross(across,direction))
        start = len(self.vertices)
        # The atlas cells have an inset, so bilinear samples cannot cross cells.
        x, y = cell%2, cell//2
        low = np.array([x,y])*.5 + .004
        high = np.array([x+1,y+1])*.5 - .004
        for v in (0,1):
            for u in (0,.5,1):
                bend = (1-abs(u*2-1))*width*fold
                point = base+direction*(v*length)+across*((u-.5)*width)+normal*bend
                uv = low+(high-low)*np.array([1-u if flip else u,v])
                self.vertex(point,uv)
        self.face((start,start+1,start+4,start+3),1)
        self.face((start+1,start+2,start+5,start+4),1)

    def append(self, other, scale=(1,1,1), translation=(0,0,0), yaw=0, clip_z=None):
        vertices = np.asarray(other.vertices)
        if clip_z is not None:
            other = other.clipped(clip_z)
            vertices = np.asarray(other.vertices)
        if not len(vertices):
            return
        vertices = vertices*np.asarray(scale)
        c,s = math.cos(yaw),math.sin(yaw)
        vertices[:,:2] = vertices[:,:2] @ np.array([[c,s],[-s,c]])
        vertices += np.asarray(translation)
        offset = len(self.vertices)
        self.vertices.extend(vertices.tolist())
        self.uvs.extend(other.uvs)
        self.faces.extend(tuple(index+offset for index in face) for face in other.faces)
        self.slots.extend(other.slots)

    def clipped(self, floor):
        """Keep the canopy above a measured path clearance plane, including UVs."""
        result = Geometry()
        for face,slot in zip(self.faces,self.slots):
            polygon = [(np.array(self.vertices[i]),np.array(self.uvs[i])) for i in face]
            output = []
            for current,following in zip(polygon,polygon[1:]+polygon[:1]):
                a,uv_a = current
                b,uv_b = following
                keep_a,keep_b = a[2]>=floor,b[2]>=floor
                if keep_a:
                    output.append(current)
                if keep_a!=keep_b:
                    t=(floor-a[2])/(b[2]-a[2])
                    output.append((a+(b-a)*t,uv_a+(uv_b-uv_a)*t))
            if len(output)>=3:
                indices=[result.vertex(point,uv) for point,uv in output]
                result.face(indices,slot)
        return result

    def normalize(self):
        vertices=np.asarray(self.vertices)
        vertices[:,2]-=vertices[:,2].min()
        vertices[:,2]*=20/vertices[:,2].max()
        vertices[:,:2]*=5/np.linalg.norm(vertices[:,:2],axis=1).max()
        self.vertices=vertices.tolist()
        return self

    @property
    def triangles(self):
        return sum(len(face)-2 for face in self.faces)


def branch_frame(direction):
    direction=unit(direction)
    across=unit(np.cross(direction,(0,0,1)))
    if np.linalg.norm(across)<.1:
        across=unit(np.cross(direction,(0,1,0)))
    normal=unit(np.cross(across,direction))
    return across,normal


def trunk(g,variant,lod,kind):
    rng=random.Random(904+variant)
    bend=np.array([rng.uniform(-.25,.25),rng.uniform(-.25,.25),0])
    samples=[15,10,6,4][lod]
    points=[]
    for i in range(samples):
        t=i/(samples-1)
        point=bend*math.sin(t*math.pi*.7)
        point[0]+=.05*math.sin(t*13+variant)*t
        point[1]+=.04*math.sin(t*8)*t
        point[2]=t*(19.45 if kind=="conifer" else 13.8)
        points.append(point)
    radii=[.36*(1-i/(samples-1))**1.16+.018 for i in range(samples)]
    radii[0]*=1.28
    g.tube(points,radii,[10,8,6,5][lod],phase=variant*.7)
    if lod<2:
        for i in range(5):
            angle=i*math.tau/5+.2*variant
            end=np.array([math.cos(angle)*.82,math.sin(angle)*.82,.02])
            g.tube([(0,0,.65),end*.5+np.array([0,0,.12]),end],[.19,.12,.015],5)


def conifer(variant,lod):
    g=Geometry()
    trunk(g,variant,lod,"conifer")
    cell=1 if variant==2 else 0
    levels=15
    for level in range(levels):
        t=level/(levels-1)
        rng=random.Random(1581+variant*313+level*151)
        z=5.9+t*12.4+rng.uniform(-.25,.25)
        reach=(.6+4.0*(1-t)**.72)*(1+.13*math.sin(level*1.9+variant))
        arms=4
        for arm in range(arms):
            seed=2083+variant*1037+level*89+arm*31
            r=random.Random(seed)
            angle=arm*math.tau/arms+level*2.399+r.uniform(-.40,.40)
            forward=np.array([math.cos(angle),math.sin(angle),0.])
            side=np.array([-forward[1],forward[0],0.])
            spread=reach*r.uniform(.78,1.10)
            # Old branches sag at the elbow and turn towards light at their tips.
            drop=[.75,1.15,.95][variant]*(1-t)
            start=np.array([0.,0.,z+r.uniform(-.68,.68)*(1-.45*t)])
            elbow=start+forward*spread*.55-np.array([0,0,drop])
            end=start+forward*spread+side*r.uniform(-.2,.2)+np.array([0,0,r.uniform(-.25,.45)])
            if lod==3:
                if level%2 or arm>=3:
                    continue
                g.card(elbow-forward*.18,unit(end-elbow)+np.array([0,0,.12]),side,
                       max(.75,spread*.82),max(.62,spread*.72),cell,fold=.12,flip=arm%2==0)
                g.card(elbow-forward*.18,unit(end-elbow)+np.array([0,0,.08]),np.array([0,0,1]),
                       max(.75,spread*.82),max(.45,spread*.50),cell,fold=.07)
                continue
            middle=(start+elbow)*.5+np.array([0,0,.15])
            outer=(elbow+end)*.5-np.array([0,0,.08])
            g.tube([start,middle,elbow,outer,end],
                   [.105*(1-t*.78),.078*(1-t*.68),.055*(1-t*.6),.028,.007],[6,5,4][lod])
            twig_count=[18,9,4][lod]
            for twig in range(twig_count):
                s=.08+.87*twig/(twig_count-1)
                root=start*(1-s)+end*s-np.array([0,0,drop*math.sin(s*math.pi)])
                # Alternate fans fill an irregular branch, without stacked discs.
                sign=-1 if twig%2 else 1
                direction=unit(forward*.48+side*sign*.72+np.array([0,0,r.uniform(-.06,.32)]))
                twig_length=max(.35,spread*.38*(1-.58*s))
                tip=root+direction*twig_length
                if lod<2:
                    g.tube([root,tip],[.023*(1-.45*t),.006],3 if lod else 4)
                across,normal=branch_frame(direction)
                for spray in range([8,4,1][lod]):
                    sr=random.Random(seed+twig*237+spray*619)
                    offset=direction*twig_length*(.01+spray*.12)+np.array([0,0,sr.uniform(-.36,.42)])
                    tilt=sr.uniform(-1.2,1.2)
                    card_across=across*math.cos(tilt)+normal*math.sin(tilt)
                    length=(.67-.21*t)*[1.,1.42,2.20][lod]*sr.uniform(.80,1.17)
                    width=length*(1.00 if variant==2 else .83)
                    g.card(root+offset-direction*.17,direction+np.array([0,0,sr.uniform(-.15,.25)]),card_across,
                           length,width,cell,fold=sr.uniform(.06,.14),flip=(twig+spray)%2==0)
                    # A second face plane prevents an empty edge-on branch.
                    if (twig+spray)%3==0 or lod==2:
                        g.card(root+offset,direction,normal,length*.87,width*.85,cell,fold=.09)
    # A small flexible leader is foliated, rather than a hard cone point.
    for tip_level in range(6):
        for angle in (0,1.8,3.8):
            g.card((0,0,18.3+tip_level*.19),(.15*math.cos(angle),.15*math.sin(angle),1),
                   (math.cos(angle),math.sin(angle),0),.32,.22*(1-tip_level*.12),cell,fold=.04)
    if lod<2:
        # Sparse old dead branches help expose the trunk and scale the tree.
        for i in range(5):
            angle=i*2.399+variant
            start=np.array([0,0,3.4+i*.53])
            end=start+np.array([math.cos(angle),math.sin(angle),-.25])*(.9+i*.10)
            g.tube([start,end],[.045,.009],4)
    return g.normalize()


def broadleaf(variant,lod):
    g=Geometry()
    trunk(g,variant,lod,"broadleaf")
    cell=3 if variant==1 else 2
    for arm in range(8):
        rng=random.Random(7321+variant*231+arm*137)
        angle=arm*2.399+variant*.71
        forward=np.array([math.cos(angle),math.sin(angle),0])
        side=np.array([-forward[1],forward[0],0])
        rise=8.0+arm*.68
        start=np.array([0.,0.,6.0+arm*.53])
        elbow=forward*rng.uniform(1.1,2.1)+np.array([0,0,rise])
        end=forward*rng.uniform(3.1,4.3)+side*rng.uniform(-.5,.5)+np.array([0,0,10.6+(arm%4)*1.8])
        if lod<3:
            g.tube([start,(start+elbow)*.5+side*.20,elbow,(elbow+end)*.5+side*.24,end],
                   [.20-arm*.01,.15-arm*.008,.10,.065,.029],[7,5,4][lod])
        for fork in range(4):
            f=random.Random(931+variant*601+arm*143+fork*71)
            tip=end+side*(fork-1.5)*.85+forward*f.uniform(-1.3,.8)+np.array([0,0,f.uniform(-.8,1.6)])
            origin=elbow*.36+end*.64
            if lod<2:
                g.tube([origin,tip],[.062,.009],5 if lod==0 else 3)
            spray_count=[40,20,8,1][lod]
            for spray in range(spray_count):
                sr=random.Random(8201+variant*881+arm*1117+fork*373+spray*71)
                theta=spray*2.399+sr.uniform(-.2,.2)
                radius=sr.uniform(.2,1.25)
                centre=tip+np.array([math.cos(theta)*radius,math.sin(theta)*radius,sr.uniform(-1.1,1.8)])
                direction=unit(np.array([math.cos(theta)*.7,math.sin(theta)*.7,sr.uniform(.1,.8)]))
                across,normal=branch_frame(direction)
                tilt=sr.uniform(-1.2,1.2)
                across=across*math.cos(tilt)+normal*math.sin(tilt)
                length=[1.30,1.65,2.05,4.0][lod]*sr.uniform(.85,1.1)
                width=length*(1.0 if cell==2 else .88)
                g.card(centre-direction*length*.35,direction,across,length,width,cell,
                       fold=sr.uniform(.06,.18),flip=spray%2==0)
                if lod==3:
                    g.card(centre-direction*length*.35,direction,normal,length,width,cell,fold=.1)
                if lod==0 and spray%4==0:
                    g.tube([origin*.20+tip*.80,centre],[.013,.003],3)
    return g.normalize()


def tree_geometry(kind,variant,lod):
    if kind not in {"conifer","broadleaf"} or variant not in range(3) or lod not in range(4):
        raise ValueError("Invalid tree library variant")
    return conifer(variant,lod) if kind=="conifer" else broadleaf(variant,lod)
