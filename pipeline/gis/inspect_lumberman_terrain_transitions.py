"""Numerical and static preflight on saved terrain; no shared rebuild or app test."""
import json
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Point
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from acquire_sources import save_json
from lumberman_integration_geometry import FacilitySolids,sha
from terrain_boundary_stitch import ExportedTerrainPatch
from lumberman_terrain_transition import LumbermanTerrainTransition

ROOT=Path(__file__).resolve().parents[2]
facility=FacilitySolids(ROOT);patch=ExportedTerrainPatch(ROOT,facility.footprints['terrain_and_existing_walk'],margin=60)
helper=LumbermanTerrainTransition(ROOT)
vertices=patch.triangles.reshape(-1,3);faces=np.arange(len(vertices)).reshape(-1,3)
v,f,_,report=helper.apply(vertices,faces)
helper.bind_rendered_terrain(v,f)
overlay_checks=[]
surface_manifest=json.loads((ROOT/'manifests/surface-model.json').read_text(encoding='utf8'))
for row in surface_manifest['routes']:
    with np.load(ROOT/row['path']) as package:
        rv=package['vertices']+package['anchor'];rf=package['faces']
    lo,hi=rv[:,:2].min(0),rv[:,:2].max(0)
    xmin,ymin,xmax,ymax=helper.footprint.bounds
    if lo[0]>xmax or hi[0]<xmin or lo[1]>ymax or hi[1]<ymin:continue
    _,_,check=helper.refit_overlay(rv,rf,lift=.06)
    if check['affected']:overlay_checks.append(dict(path=row['path'],sha256=sha(ROOT/row['path']),**check))
triangles=v[f];polygons=shapely.polygons(triangles[:,:,:2]);tree=shapely.STRtree(polygons)

def height(xy):
    p=Point(xy);ids=tree.query(p.buffer(1e-6),predicate='intersects')
    ids=[i for i in ids if polygons[i].distance(p)<1e-6]
    if not ids:raise ValueError('No preflight terrain at '+str(list(xy)))
    t=triangles[ids[0]];uv=np.linalg.solve(np.column_stack((t[1,:2]-t[0,:2],t[2,:2]-t[0,:2])),np.asarray(xy)-t[0,:2])
    return float(t[0,2]+uv@(t[1:,2]-t[0,2]))

deck_uv=np.array([facility.uv(p) for p in facility.footprints['road_deck'].exterior.coords])
floor_uv=np.array([facility.uv(p) for p in facility.footprints['terrain_and_existing_walk'].exterior.coords])
opening_uv=np.array([facility.uv(p) for p in facility.footprints['walkthrough_opening'].exterior.coords])
controls=[]
for u in (deck_uv[:,0].min(),deck_uv[:,0].max()):
    for b in np.linspace(deck_uv[:,1].min(),deck_uv[:,1].max(),101):
        xy=facility.xy([u,b]);target=facility.vertical_range(facility.deck,xy)[1]
        controls.append(dict(kind='deck_end',uv_m=[float(u),float(b)],target_z_m=target,actual_z_m=height(xy)))
for a in np.linspace(opening_uv[:,0].min(),opening_uv[:,0].max(),41):
    b=floor_uv[:,1].min();xy=facility.xy([a,b]);target=facility.vertical_range(facility.floor,xy)[1]
    controls.append(dict(kind='south_walking_end',uv_m=[float(a),float(b)],target_z_m=target,actual_z_m=height(xy)))
max_error=max(abs(c['actual_z_m']-c['target_z_m']) for c in controls)
if max_error>1e-6:raise ValueError('Lumberman preflight join mismatch: '+str(max_error))
input_area=float(shapely.area(shapely.polygons(patch.triangles[:,:,:2])).sum())
output_area=float(shapely.area(polygons).sum())
cut_overlap=float(shapely.area(shapely.intersection(polygons,facility.footprints['terrain_and_existing_walk'])).sum())
if abs(input_area-output_area)>1e-5 or cut_overlap>1e-5:raise ValueError('Transition changed coverage or entered lower cut')
figure,axes=plt.subplots(1,2,figsize=(14,6))
for side,u0,u1 in [('west',-44,-14),('east',14,40)]:
    rows=[c for c in helper.data['controls'] if c['kind']=='road_'+side]
    rows=sorted(rows,key=lambda c:c['u_m']);points=[facility.xy([r['u_m'],r['centre_v_m']]) for r in rows]
    stations=[r['u_m'] for r in rows]
    axes[0].plot(stations,[patch.height(p) for p in points],'--',label=side+' source DTM')
    axes[0].plot(stations,[height(p) for p in points],'-o',ms=3,label=side+' corrected road')
    axes[0].plot(stations,[r['plane_about_station_centre'][0] for r in rows],'.',label=side+' raw-return controls')
rows=sorted([c for c in helper.data['controls'] if c['kind']=='south_walk'],key=lambda c:c['v_m'])
stations=[r['v_m'] for r in rows];points=[facility.xy([0,b]) for b in stations]
axes[1].plot(stations,[patch.height(p) for p in points],'--',label='source DTM')
axes[1].plot(stations,[height(p) for p in points],'-o',ms=3,label='corrected walking approach')
axes[1].plot(stations,[r['plane_about_station_centre'][0] for r in rows],'.',label='raw ground controls')
for ax,title,xlabel in [(axes[0],'Upper road approaches','Road axis u, m'),(axes[1],'Lower south walking approach','Waterpark axis v, m')]:
    ax.set_title(title);ax.set_xlabel(xlabel);ax.set_ylabel('CGVD2013 height, m');ax.grid(alpha=.3);ax.legend(fontsize=8)
figure.suptitle('Lumberman terrain correction preflight — separate road and walking contact layers')
figure.tight_layout();figure.savefig(ROOT/'evidence/facilities/lumberman-transition-profiles.png',dpi=150)
result=dict(transition_manifest_sha256=sha(ROOT/'manifests/lumberman-terrain-transitions.json'),
    terrain_inputs=patch.inputs,transformation=report,join_probes=len(controls),maximum_join_error_m=max_error,
    input_area_m2=input_area,output_area_m2=output_area,lower_cut_overlap_m2=cut_overlap,
    controls=controls,shared_terrain_modified=False,actual_export_repeat_required=True,
    affected_route_overlay_checks=overlay_checks,
    visual_acceptance=False,runtime_acceptance=False)
save_json(ROOT/'evidence/facilities/lumberman-transition-preflight.json',result)
print(json.dumps(dict(join_probes=len(controls),max_error_m=max_error,lower_cut_overlap_m2=cut_overlap,report=report)))
