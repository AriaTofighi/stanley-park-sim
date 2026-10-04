"""Offline views of actual terrain/facility seams. Does not launch an app."""
import json
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon,box
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from lumberman_integration_geometry import FacilitySolids,sha
from terrain_boundary_stitch import ExportedTerrainPatch

ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'manifests/lumberman-facility-closures.json').read_text(encoding='utf8'))
for row in data['inputs']+data['meshes']:
    if sha(ROOT/row['path'])!=row['sha256']:
        raise ValueError('Stale Lumberman closure inspection input: '+row['path'])
facility=FacilitySolids(ROOT)
terrain=ExportedTerrainPatch(ROOT,facility.footprints['terrain_and_existing_walk'],margin=6)
figure=plt.figure(figsize=(16,10));plan=figure.add_subplot(221)
views=[figure.add_subplot(222,projection='3d'),figure.add_subplot(223,projection='3d'),figure.add_subplot(224,projection='3d')]
palette=dict(road_deck_end='darkorange',pedestrian_approach_end='royalblue',floor_bank='gray')
for row in data['contacts']:
    uv=np.array([facility.uv(p) for p in row['xy_m']])
    color='crimson' if row['role']!='floor_bank' and row['maximum_step_m']>.03 else palette[row['role']]
    plan.plot(uv[:,0],uv[:,1],color=color,lw=2)
for key,style in [('road_deck','--'),('walkthrough_opening',':')]:
    uv=np.array([facility.uv(p) for p in facility.footprints[key].exterior.coords])
    plan.plot(uv[:,0],uv[:,1],style,color='black',lw=.8)
plan.set_aspect('equal');plan.set_xlabel('Road axis u, m');plan.set_ylabel('Waterpark axis v, m')
plan.set_title('Exact cut boundary; red = contact step above 3 cm')
plan.grid(alpha=.3)

def plot_triangles(triangles,color,alpha=1.,clip_terrain=False):
    local=triangles.copy()
    for i,t in enumerate(triangles):
        local[i,:,:2]=np.array([facility.uv(p) for p in t[:,:2]])
    if clip_terrain:
        # Matplotlib does not clip large terrain triangles at the 3D axes.
        # Crop their actual planes first so off-view slopes cannot hide the site.
        cropped=[];window=box(-19,-15,19,14)
        for tri in local:
            matrix=np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2]))
            if abs(np.linalg.det(matrix))<1e-10:continue
            for part in shapely.get_parts(Polygon(tri[:,:2]).intersection(window)):
                if not isinstance(part,Polygon) or part.area<1e-9:continue
                for cell in shapely.get_parts(shapely.constrained_delaunay_triangles(part)):
                    xy=np.asarray(cell.exterior.coords)[:3,:2]
                    uv=np.linalg.solve(matrix,(xy-tri[0,:2]).T).T
                    cropped.append(np.column_stack((xy,tri[0,2]+uv@(tri[1:,2]-tri[0,2]))))
        local=np.asarray(cropped)
    for view in views:
        view.add_collection3d(Poly3DCollection(local,facecolors=color,edgecolors='none',alpha=alpha))

plot_triangles(terrain.triangles,[.35,.43,.26],clip_terrain=True)
for row in facility.data['assets']:
    if not any(k in row['name'] for k in ('PedestrianFloor','RoadDeck','Facade','OuterReturn','PassageWall')):
        continue
    with np.load(ROOT/row['mesh_path']) as package:
        triangles=package['vertices'][package['faces']]
    plot_triangles(triangles,row['color'])
for row in data['meshes']:
    with np.load(ROOT/row['path']) as package:
        triangles=(package['vertices']+package['anchor'])[package['faces']]
    plot_triangles(triangles,[.8,.35,.18])
for view,(elev,azim,title) in zip(views,[(18,65,'Waterpark approach'),(16,245,'Park approach'),(65,-30,'Road ends and floor bank')]):
    view.set_xlim(-19,19);view.set_ylim(-15,14);view.set_zlim(1.5,8)
    view.set_box_aspect([38,29,13]);view.view_init(elev,azim)
    view.set_title(title);view.set_xlabel('u, m');view.set_ylabel('v, m')
figure.suptitle('Lumberman exact terrain closure review — closure skins shown orange; no application acceptance')
figure.tight_layout()
target=ROOT/'evidence/facilities/lumberman-closure-review.png';target.parent.mkdir(exist_ok=True)
figure.savefig(target,dpi=150)
print(json.dumps(dict(image=target.relative_to(ROOT).as_posix(),checks=data['checks'])))
