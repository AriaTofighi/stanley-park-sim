"""Author a measured bridge silhouette in the live, editable Blender scene.

The source fit controls all large dimensions. Small member sizes remain explicit
blockout assumptions. This is neither a structural model nor a bridge route.
"""
import json
import math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
source = json.loads((ROOT / 'manifests/lions-gate-blockout.json').read_text())
for key in ['towers','foundations','stations_m','deck_heights_m','cable_fits']:
    if key not in source:raise RuntimeError(f'Fit the complete bridge manifest first: missing {key}')
scene = bpy.data.scenes['StanleyPark_M1']
bpy.context.window.scene = scene
collection = bpy.data.collections.get('SP_06_Landmarks')
if collection is None:
    collection = bpy.data.collections.new('SP_06_Landmarks')
    scene.collection.children.link(collection)
owner = 'landmark_lions_gate'
for obj in list(collection.objects):
    if obj.get('pipeline_owner') == owner:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

origin = np.array([*source['axis_origin_local_m'], 0.])
direction = np.array([*source['axis_unit'], 0.])
normal = np.array([*source['transverse_unit'], 0.])
dimensions = source['simplified_dimensions']

def material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = .8
    return mat

steel = material('M_LionsGate_SteelBlockout', (.09, .26, .20))
road = material('M_LionsGate_RoadBlockout', (.15, .16, .16))
walk = material('M_LionsGate_WalkwayBlockout', (.48, .48, .44))
cable = material('M_LionsGate_CableBlockout', (.40, .44, .42))
stone = material('M_LionsGate_FoundationBlockout', (.45, .42, .35))

def xyz(point):
    return direction * point[0] + normal * point[1] + np.array([0., 0., point[2]])

class MeshParts:
    def __init__(self):
        self.vertices, self.faces = [], []

    def rings(self, rows):
        offset, count = len(self.vertices), len(rows[0])
        self.vertices.extend([xyz(p).tolist() for row in rows for p in row])
        self.faces.append(tuple(offset+i for i in range(count-1, -1, -1)))
        for r in range(len(rows)-1):
            for i in range(count):
                j = (i+1) % count
                self.faces.append((offset+r*count+i, offset+r*count+j,
                    offset+(r+1)*count+j, offset+(r+1)*count+i))
        self.faces.append(tuple(offset+(len(rows)-1)*count+i for i in range(count)))

    def beam(self, a, b, width, depth=None, sides=4):
        a, b = Vector(a), Vector(b)
        tangent = (b-a).normalized()
        reference = Vector((1, 0, 0)) if abs(tangent.x) < .8 else Vector((0, 1, 0))
        u = tangent.cross(reference).normalized()
        v = tangent.cross(u).normalized()
        if sides == 4:
            offsets = [u*x*width*.5+v*y*(depth or width)*.5 for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        else:
            offsets = [(u*math.cos(t)+v*math.sin(t))*width*.5 for t in np.arange(sides)*2*math.pi/sides]
        self.rings([[list(p+o) for o in offsets] for p in [a,b]])

    def object(self, name, mat, collision='none'):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj.location = origin
        mesh.materials.append(mat)
        obj['pipeline_owner'] = owner
        obj['source_id'] = 'City LiDAR 2022; BC Lions Gate engineering report 2018; manifests/lions-gate-blockout.json'
        obj['collision'] = collision
        obj['release_accepted'] = False
        obj['landmark'] = 'Lions Gate Bridge'
        obj['representation'] = 'Measured major silhouette; simplified members; north viaduct incomplete'
        return obj

stations = np.asarray(source['stations_m'])
heights = np.asarray(source['deck_heights_m'])
deck_edges = source['deck_edges_transverse_m']
road_half = source['roadway_width_m'] * .5
for name, left, right, mat in [
    ('Road', -road_half, road_half, road),
    ('WalkWest', deck_edges[0], -road_half, walk),
    ('WalkEast', road_half, deck_edges[1], walk),
]:
    parts = MeshParts()
    rows = [[[s,left,h-.6],[s,right,h-.6],[s,right,h],[s,left,h]] for s,h in zip(stations,heights)]
    parts.rings(rows)
    parts.object('SM_LionsGate_'+name, mat)

tower_parts = MeshParts()
for tower,foundation in zip(source['towers'],source['foundations']):
    s, top = tower['station_m'], tower['top_m']
    def half(z):
        return float(np.polyval(tower['leg_centre_polynomial'], z))
    def depth(z):
        return max(1., float(np.polyval(tower['leg_depth_polynomial'], z)))
    for sign,side in zip([-1, 1],foundation['sides']):
        rows = []
        for z in [side['levels'][-1]['height_m'],20.,45.,70.,95.,top-1.]:
            t = sign*half(z)
            ds, dt = depth(z)*.5, dimensions['transverse_leg_width_m']*.5
            rows.append([[s-ds,t-dt,z],[s+ds,t-dt,z],[s+ds,t+dt,z],[s-ds,t+dt,z]])
        tower_parts.rings(rows)
    # Visible levels read from the retained LiDAR elevation plot. Fine lattice,
    # curved braces and their joints require later individual modelling.
    for z in [13., 74.5, 97., 116.]:
        tower_parts.beam([s,-half(z),z],[s,half(z),z],1.1,1.1)
    for low, high in [(14.,38.),(77.5,94.5),(99.5,114.5)]:
        for sign in [-1,1]:
            tower_parts.beam([s,sign*half(low),low],[s,-sign*half(high),high],dimensions['brace_width_m'])
tower_parts.object('SM_LionsGate_Towers', steel)

cable_parts, hanger_parts = MeshParts(), MeshParts()
for fit in source['cable_fits']:
    line = np.linspace(fit['start_m'], fit['end_m'], math.ceil((fit['end_m']-fit['start_m'])/2)+1)
    for sign in [-1,1]:
        t = source['cable_half_width_m']*sign
        z = np.polyval(fit['polynomial'], line)
        for i in range(len(line)-1):
            cable_parts.beam([line[i],t,z[i]],[line[i+1],t,z[i+1]],dimensions['cable_radius_m']*2,sides=6)
        # Approximately regular hangers are a declared blockout representation.
        # Exact hanger stations remain a separate drawing/point-fit task.
        for s in np.arange(fit['start_m']+10., fit['end_m']-5., 10.):
            bottom, top = float(np.interp(s,stations,heights)), float(np.polyval(fit['polynomial'],s))
            if top>bottom:
                hanger_parts.beam([s,t,bottom],[s,t,top],dimensions['hanger_radius_m']*2,sides=4)
cable_parts.object('SM_LionsGate_MainCables', cable)
hanger_parts.object('SM_LionsGate_Hangers', cable)

# Use observed CGVD2013 top bands rather than unconverted drawing elevations.
# The south collar is one connected capsule, as seen in report Figure 3-4/5.
# The north has separate pedestals above its rock berm (Figure 3-1).
for number,foundation in enumerate(source['foundations']):
    footings=MeshParts();s=foundation['station_m']
    if number==0:
        outline=[]
        for centre,angles in [(11.6365,np.linspace(0,math.pi,13)),(-11.6365,np.linspace(math.pi,2*math.pi,13))]:
            outline.extend([[s+10*math.cos(a),centre+10*math.sin(a)] for a in angles])
        top=sum(side['levels'][0]['height_m'] for side in foundation['sides'])/2
        footings.rings([[[*p,z] for p in outline] for z in [-1.,top]])
    for side in foundation['sides']:
        t=side['transverse_centre_m'];levels=side['levels']
        bottom=levels[0]['height_m'] if number==0 else foundation['base_below_visibility_m']
        for level in levels[1:]:
            radius=level['radius90_m'];top=level['height_m']
            rows=[[[s+radius*math.cos(a),t+radius*math.sin(a),z] for a in np.arange(24)*math.pi/12] for z in [bottom,top]]
            footings.rings(rows);bottom=top
    footings.object('SM_LionsGate_'+('South' if number==0 else 'North')+'FootingReview',stone)

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result = dict(landmark='Lions Gate Bridge',objects=[o.name for o in collection.objects if o.get('pipeline_owner')==owner],
    tower_span_m=source['tower_span_m'],height_datum='CGVD2013',complete=False,
    unresolved=['North viaduct','Exact foundation contours and north rock berm','Exact hangers and member sizes','Visual inspection','Engine import'])
(ROOT/'evidence/blender-lions-gate-build.json').write_text(json.dumps(result,indent=2)+'\n')
