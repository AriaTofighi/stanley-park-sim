"""Author grounded forest placements and original understory/picnic assets.

Run with background Blender 5.2. It reads the existing terrain modules, but
never writes those modules or the protected M1 scene. No game is started.
"""
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'exports/park-details-v0.5'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
random.seed(501)

# Ground and clearance inputs use local east/north/up metres.
for module in ('Terrain_Water', 'Routes_Ground'):
    with bpy.data.libraries.load(str(ROOT / f'blender/modules/{module}.blend'), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith(('SM_Terrain_', 'SM_Route_', 'SM_Join_', 'SM_Walk_'))]
    for obj in dst.objects:
        if obj is not None: scene.collection.objects.link(obj)
bpy.context.view_layer.update()

tiles = []
for obj in scene.objects:
    if obj.type != 'MESH' or not obj.name.startswith('SM_Terrain_'): continue
    points = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    bvh = BVHTree.FromPolygons(points.tolist(), [tuple(p.vertices) for p in obj.data.polygons])
    tiles.append((points[:, :2].min(0), points[:, :2].max(0), bvh, obj.name))
if not tiles: raise RuntimeError('Terrain modules have no terrain mesh')

def ground(xy):
    hits = []
    for low, high, tree, name in tiles:
        if np.any(np.asarray(xy) < low) or np.any(np.asarray(xy) > high): continue
        p, normal, _, _ = tree.ray_cast(Vector((xy[0], xy[1], 500)), Vector((0, 0, -1)), 1000)
        if p is not None: hits.append((p.z, normal.z, name))
    return max(hits) if hits else None

world = json.loads((ROOT/'unreal/Content/WorldData/world.json').read_text())
route_grid = defaultdict(list)
route_points = []
for route in world['routes']:
    for p in route['points']:
        q = np.asarray([p[1]/100, p[0]/100, p[2]/100])
        route_points.append(q)
        route_grid[(math.floor(q[0]/10), math.floor(q[1]/10))].append(q)

def route_distance(xy, search=4):
    cell = (math.floor(xy[0]/10), math.floor(xy[1]/10))
    points = [p for dx in range(-search, search+1) for dy in range(-search, search+1)
              for p in route_grid.get((cell[0]+dx, cell[1]+dy), [])]
    if not points: return 1000.0
    return min(float(np.linalg.norm(p[:2]-xy)) for p in points)

def dry_ground(xy):
    hit = ground(xy)
    # The terrain water planes are not ground. A positive dry margin prevents
    # plants on the ocean margin; polygon checks are applied by the importer.
    return hit if hit and hit[0] > .5 and hit[1] > .55 else None

# Replace offset/cut crowns with complete trees. Deduplicate the older detail
# and crown layers by their original source sample ID.
source = json.loads((ROOT/'exports/m3-crown-repair/a0f7b40568c5/manifest.json').read_text())
sources = {}
for tile in source['coarse_replacements']:
    for row in tile['source_records']:
        sources[row['source_id']] = dict(source_id=row['source_id'], xy=row['source_position_local_m'][:2],
            top=row['source_top_m'], kind='conifer' if row.get('species_group') in ('CW','FD','HW','SS','YC') else 'broadleaf')
for rel in ('exports/seawall-trees/0551a03260b4/manifest.json', 'exports/m3-forest/659dc73e2ffc/manifest.json'):
    for row in json.loads((ROOT/rel).read_text())['instances']:
        sources[row['source_id']] = dict(source_id=row['source_id'], xy=row['position_local_m'][:2],
            top=row['top_m'], kind=row['visual_type'])
trees, rejected, occupied = [], [], defaultdict(list)
for sid, row in sorted(sources.items()):
    xy = np.asarray(row['xy']); hit = dry_ground(xy)
    if not hit or route_distance(xy, 1) < 3.5:
        rejected.append(dict(source_id=sid, reason='no_dry_ground_or_path_clearance')); continue
    cell = (math.floor(xy[0]/4), math.floor(xy[1]/4))
    neighbours = [p for dx in (-1,0,1) for dy in (-1,0,1) for p in occupied.get((cell[0]+dx,cell[1]+dy),[])]
    if any(np.linalg.norm(xy-p) < 2.8 for p in neighbours):
        rejected.append(dict(source_id=sid,reason='trunk_spacing')); continue
    height = min(48, max(6, row['top'] - hit[0]))
    if row['top']-hit[0] < 4:
        rejected.append(dict(source_id=sid,reason='low_source_height')); continue
    occupied[cell].append(xy)
    variant = int(hashlib.sha256(sid.encode()).hexdigest()[:8],16)%3
    # Tall conifers have slender crowns; keep the sampled top and an upright
    # trunk. Root Z embeds 12 cm to remove a visible gap on uneven terrain.
    width = min(1.15,max(.28,height/25))
    trees.append(dict(source_id=sid,kind=row['kind'],variant=variant,
        position_cm=[xy[1]*100,xy[0]*100,(hit[0]-.12)*100],scale=[width,width,height/20],
        yaw=int(hashlib.sha256((sid+'yaw').encode()).hexdigest()[:8],16)%360,
        terrain=hit[2],root_gap_cm=-12))

# Original opaque leaf geometry is inexpensive and needs no external texture.
colors = {'Leaf':(.045,.16,.035,1),'LeafLight':(.11,.24,.065,1),'Grass':(.15,.22,.055,1),
    'Stem':(.105,.075,.035,1),'PetalPink':(.55,.12,.20,1),'PetalWhite':(.72,.69,.52,1),
    'PetalGold':(.66,.38,.06,1),'FabricBlue':(.09,.21,.29,1),'FabricRust':(.43,.17,.09,1),
    'Clothes':(.055,.26,.23,1),'Trousers':(.075,.10,.14,1),'Skin':(.47,.26,.14,1),'Basket':(.34,.22,.095,1)}
materials = {}
for name,color in colors.items():
    m=bpy.data.materials.new('M_Park_'+name);m.diffuse_color=color;m.use_nodes=True
    bsdf=m.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=color;bsdf.inputs['Roughness'].default_value=.87
    materials[name]=m
assets=[]

class Geometry:
    def __init__(self): self.v=[];self.f=[];self.slots=[]
    def face(self,points,slot):
        start=len(self.v);self.v.extend([tuple(p) for p in points]);self.f.append(tuple(range(start,len(self.v))));self.slots.append(slot)
    def leaf(self,start,end,width,slot):
        a,b=np.asarray(start),np.asarray(end);d=b-a
        side=np.cross(d,[0,0,1]);side=side/max(np.linalg.norm(side),.001)*width
        mid=a+d*.46; ridge=mid+np.array([0,0,width*.20])
        self.face([a,mid+side,b,ridge],slot);self.face([a,ridge,b,mid-side],slot)
    def tube(self,a,b,radius,slot,sides=6):
        a,b=np.asarray(a),np.asarray(b);d=(b-a)/np.linalg.norm(b-a)
        u=np.cross(d,[0,0,1])
        if np.linalg.norm(u)<.001:u=np.array([1,0,0])
        u=u/np.linalg.norm(u);v=np.cross(d,u)
        for i in range(sides):
            p=u*math.cos(math.tau*i/sides)+v*math.sin(math.tau*i/sides)
            q=u*math.cos(math.tau*(i+1)/sides)+v*math.sin(math.tau*(i+1)/sides)
            self.face([a+p*radius,a+q*radius,b+q*radius*.72,b+p*radius*.72],slot)
    def box(self,centre,size,slot):
        c=np.asarray(centre);r=np.asarray(size)/2
        p=[c+np.array([x,y,z])*r for x,y,z in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        for indices in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):self.face([p[i] for i in indices],slot)

names=list(materials)
slot=lambda name:names.index(name)

def export(name,g):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(g.v,[],g.f);mesh.update()
    obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj)
    for m in materials.values():mesh.materials.append(m)
    for poly,index in zip(mesh.polygons,g.slots):poly.material_index=index
    # Match the existing exporter convention: local north becomes UE +X.
    temporary_mesh=mesh.copy();temporary_mesh.transform(Matrix.Rotation(-math.pi/2,4,'Z'))
    temporary=bpy.data.objects.new('Export_'+name,temporary_mesh);scene.collection.objects.link(temporary)
    bpy.ops.object.select_all(action='DESELECT');temporary.select_set(True);bpy.context.view_layer.objects.active=temporary
    path=OUT/(name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},use_triangles=True,
        axis_forward='Y',axis_up='Z',use_space_transform=False,bake_space_transform=True,
        apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',mesh_smooth_type='FACE',bake_anim=False,path_mode='STRIP')
    bpy.data.objects.remove(temporary,do_unlink=True)
    assets.append(dict(name=name,fbx=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        materials=[dict(name=m.name,color=list(m.diffuse_color),two_sided=k in ('Leaf','LeafLight','Grass','PetalPink','PetalWhite','PetalGold')) for k,m in materials.items()],
        triangles=sum(len(f)-2 for f in g.f)))
    return obj

for variant in range(3):
    rng=random.Random(600+variant)
    g=Geometry()
    for i in range(90):
        x,y=rng.uniform(-.55,.55),rng.uniform(-.55,.55);height=rng.uniform(.16,.45)
        angle=rng.random()*math.tau;side=np.array([math.cos(angle),math.sin(angle),0])*.012
        base=np.array([x,y,0]);mid=base+np.array([math.cos(angle)*.07,math.sin(angle)*.07,height*.6]);tip=base+np.array([math.cos(angle)*.15,math.sin(angle)*.15,height])
        g.face([base-side,base+side,mid+side*.65,tip,mid-side*.65],slot('Grass' if i%3 else 'LeafLight'))
    export(f'SM_ParkGrass_{variant}',g)
    g=Geometry()
    for frond in range(9):
        angle=frond*math.tau/9+rng.random()*.2;d=np.array([math.cos(angle),math.sin(angle),0]);length=rng.uniform(.6,1.05)
        def centre(t):return d*(length*t)+np.array([0,0,.04+math.sin(t*math.pi*.8)*.55])
        for i in range(12):
            t=(i+.5)/13;a=centre(t);b=centre((i+1.5)/13);g.tube(a,b,.006,slot('Stem'),4)
            side=np.array([-d[1],d[0],0]);width=.16*math.sin(t*math.pi)
            for sign in (-1,1):g.leaf(a,a+side*sign*width+d*.04+np.array([0,0,.025]),width*.16,slot('LeafLight' if frond%3==0 else 'Leaf'))
    export(f'SM_ParkSwordFern_{variant}',g)
    g=Geometry()
    for branch in range(13):
        angle=rng.random()*math.tau;d=np.array([math.cos(angle),math.sin(angle),0]);height=rng.uniform(.4,.9)
        end=d*rng.uniform(.15,.48)+np.array([0,0,height]);g.tube([0,0,0],end,.013,slot('Stem'))
        for j in range(6):
            a=end*((j+2)/8);side=np.array([-d[1],d[0],0])*(-1 if j%2 else 1)
            g.leaf(a,a+side*.19+d*.055+np.array([0,0,.03]),.072,slot('LeafLight' if j%3==0 else 'Leaf'))
    export(f'SM_ParkSalal_{variant}',g)
    g=Geometry()
    for i in range(24):
        x,y=rng.uniform(-.5,.5),rng.uniform(-.5,.5);h=rng.uniform(.17,.34)
        g.tube([x,y,0],[x,y,h],.004,slot('Leaf'),4)
        for petal in range(5):
            a=petal*math.tau/5;g.leaf([x,y,h],[x+math.cos(a)*.04,y+math.sin(a)*.04,h+.009],.016,slot(('PetalWhite','PetalPink','PetalGold')[variant]))
        g.leaf([x,y,h*.5],[x+.08,y+.035,h*.6],.016,slot('LeafLight'))
    export(f'SM_ParkFlowers_{variant}',g)

# Small seated picnic groups, with baskets and folded blankets. The limbs are
# built in seated poses rather than shrinking or burying a standing person.
for variant in range(3):
    g=Geometry();g.box([0,0,.015],[2.5,2,.03],slot('FabricBlue' if variant%2 else 'FabricRust'))
    for person in range(2+(variant==2)):
        x=-.7+person*.65;y=.25 if person%2 else -.4
        g.box([x,y,.47],[.30,.22,.42],slot('Clothes'));g.box([x,y,.80],[.18,.18,.22],slot('Skin'))
        for side in (-1,1):
            g.tube([x+side*.08,y,.30],[x+side*.15,y+.3,.18],.075,slot('Trousers'))
            g.tube([x+side*.15,y+.3,.18],[x+side*.27,y+.52,.10],.06,slot('Trousers'))
            g.tube([x+side*.17,y,.6],[x+side*.20,y+.25,.38],.045,slot('Clothes'))
            g.tube([x+side*.20,y+.25,.38],[x+side*.12,y+.32,.32],.035,slot('Skin'))
    g.box([.8,-.55,.17],[.38,.3,.32],slot('Basket'))
    export(f'SM_ParkPicnic_{variant}',g)

# Ecological art direction: low grass at open edges, fern/salal clusters in
# shaded forest, and restrained flowers around open lawns. No pavement edits.
main=np.asarray(world['routes'][0]['points'])[:,[1,0,2]]/100
segments=np.linalg.norm(np.diff(main[:,:2],axis=0),axis=1);chain=np.r_[0,np.cumsum(segments)]
plants=[];picnics=[]
def route_sample(distance):
    index=min(len(main)-2,int(np.searchsorted(chain,distance,side='right')-1));index=max(0,index)
    alpha=(distance-chain[index])/max(chain[index+1]-chain[index],.0001)
    p=main[index]*(1-alpha)+main[index+1]*alpha;d=main[index+1]-main[index];d=d/max(np.linalg.norm(d[:2]),.0001)
    return p,np.array([-d[1],d[0]])
for station in np.arange(0,chain[-1],8):
    p,side=route_sample(station)
    for sign in (-1,1):
        for offset in (4.0,6.5,10.0,16.0,24.0):
            xy=p[:2]+side*sign*(offset+random.uniform(-.5,.5))+np.array([random.uniform(-1.5,1.5),random.uniform(-1.5,1.5)])
            hit=dry_ground(xy)
            if not hit or abs(hit[0]-p[2])>10 or route_distance(xy,1)<3.0:continue
            kind=random.choices(['Grass','SwordFern','Salal','Flowers'],[.52,.22,.22,.04])[0]
            if offset>12 and kind=='Flowers':kind='SwordFern'
            scale=random.uniform(.65,1.35)
            plants.append(dict(mesh=f'SM_Park{kind}_{random.randrange(3)}',position_cm=[xy[1]*100,xy[0]*100,(hit[0]-.035)*100],
                yaw=random.randrange(360),scale=[scale,scale,scale],terrain=hit[2]))
for station in (70,300,1100,2800,6500,7200,8200,9000):
    p,side=route_sample(station)
    for sign in (-1,1):
        xy=p[:2]+side*sign*12;hit=dry_ground(xy)
        if not hit or hit[1]<.95 or abs(hit[0]-p[2])>2.0 or route_distance(xy,1)<8:continue
        # Require all four corners of the blanket to meet one flat lawn.
        corners=[ground(xy+np.array([dx,dy])) for dx in (-1.2,1.2) for dy in (-1,1)]
        if any(h is None for h in corners) or max(h[0] for h in corners)-min(h[0] for h in corners)>.18:continue
        picnics.append(dict(mesh=f'SM_ParkPicnic_{len(picnics)%3}',position_cm=[xy[1]*100,xy[0]*100,(hit[0]+.02)*100],yaw=random.randrange(360),scale=[1,1,1]))
        break

# Save only the new mesh library; leave large source modules untouched.
library=ROOT/'blender/ParkDetails_v0.5.blend'
bpy.data.libraries.write(str(library),{obj for obj in scene.objects if obj.name.startswith('SM_Park')},fake_user=True)
result=dict(schema_version=1,version='0.5.0',asset_root='/Game/StanleyPark/Seawall/ParkDetails_v05',
    source_blend=library.relative_to(ROOT).as_posix(),assets=assets,trees=trees,rejected_trees=rejected,plants=plants,picnics=picnics,
    original_geometry=True,application_test_run=False,visual_review_complete=False,
    tree_policy='Complete separate upright trees, grounded to original terrain, no offset trunk-to-crown connectors.',
    plant_reference='Stanley Park Ecology Society State of the Park 2010; salal, sword fern, grasses and illustrative flowers.',
    sources=['https://stanleyparkecology.ca/wp-content/uploads/2021/07/SOPEI-Full-2010.pdf'],
    input_hashes={rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() for rel in ('blender/modules/Terrain_Water.blend','blender/modules/Routes_Ground.blend','unreal/Content/WorldData/world.json')})
(ROOT/'manifests/park-details-v0.5.json').write_text(json.dumps(result,indent=2)+'\n')
print('SP_PARK_DETAILS_AUTHORED',len(trees),'trees',len(plants),'plants',len(picnics),'picnics')
