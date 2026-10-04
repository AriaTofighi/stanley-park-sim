"""Offline tangent-pose probe clearance against fixed exported gate boxes.

This checks authored geometry only. It does not run the pawn, a controller,
Blender or Unreal, and is not a runtime acceptance result.
"""
import json
import sys
from pathlib import Path
import numpy as np
from shapely.geometry import Point
from acquire_sources import digest, save_json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'pipeline/routes'))
from mesh_surface_query import MeshSurfaceQuery


def box_from_asset(asset):
    path = ROOT/asset['mesh_path']
    if digest(path) != asset['sha256']:
        raise ValueError(f'Stale gate mesh: {path}')
    with np.load(path) as mesh:
        vertices = mesh['vertices']
        if len(vertices) != 8:
            raise ValueError('Gate contact check requires an eight-vertex beam box')
        # The authoring rings preserve the four corners at each beam end.
        axes = np.array([vertices[1]-vertices[0],vertices[3]-vertices[0],vertices[4]-vertices[0]])
    lengths = np.linalg.norm(axes,axis=1)
    axes /= lengths[:,None]
    if np.max(np.abs(axes@axes.T-np.eye(3))) > 1e-7:
        raise ValueError('Gate beam is not an orthogonal box')
    return dict(name=asset['name'], centre=vertices.mean(axis=0), axes=axes, half=lengths/2)


def clearance(centres, radii, boxes):
    best = np.full(centres.shape[:-1], np.inf)
    closest = np.full(centres.shape[:-1], -1, dtype=int)
    for index, box in enumerate(boxes):
        local = (centres-box['centre'])@box['axes'].T
        distance = np.linalg.norm(np.maximum(np.abs(local)-box['half'],0),axis=-1)-radii
        take = distance < best
        best[take],closest[take] = distance[take],index
    return best,closest


def path_probe_centres(points, contact, query):
    delta = np.gradient(points[:,:2],axis=0)
    tangent = delta/np.linalg.norm(delta,axis=1)[:,None]
    right = np.c_[tangent[:,1],-tangent[:,0]]
    poses = []
    for point, forward, across in zip(points,tangent,right):
        front, back = query.height(point[:2]+forward*.5),query.height(point[:2]-forward*.5)
        grade = np.clip(front-back,-.65,.65)
        angle = np.arctan(grade)
        ids = query.tree.query(Point(point[:2]),predicate='intersects')
        if not len(ids):
            raise ValueError('No triangle at the guide contact point')
        tri = query.triangles[ids[0]]
        normal = np.cross(tri[1]-tri[0],tri[2]-tri[0]); normal /= np.linalg.norm(normal)
        base = point.copy();base[2] += .02 + .32/normal[2]-.32
        f = np.r_[forward*np.cos(angle),np.sin(angle)]
        r = np.r_[across,0.]
        u = np.r_[-forward*np.sin(angle),np.cos(angle)]
        poses.append(base+contact@np.array([f,r,u]))
    return np.array(poses)


def inspect_site(site, assets, specification, surfaces):
    points = np.asarray(site['walking_path']['points_local_m'])
    probes = specification['probes']
    local = np.asarray([p['centre_cm'] for p in probes])/100
    radii = np.asarray([p['radius_cm'] for p in probes])/100
    query = MeshSurfaceQuery(ROOT,surfaces,[*(points[:,:2].min(0)-2),*(points[:,:2].max(0)+2)])
    boxes = [box_from_asset(asset) for asset in assets if asset['feature_id']==site['id']]
    centres = path_probe_centres(points,local,query)
    margins,nearest = clearance(centres,radii,boxes)
    pose_index,probe_index = np.unravel_index(np.argmin(margins),margins.shape)
    collisions = np.argwhere(margins <= 0)
    return dict(id=site['id'],pose_count=len(points),probe_count=len(probes),
        minimum_probe_to_frame_margin_m=float(margins.min()),
        minimum_at_source_station_m=site['walking_path']['source_stations_m'][pose_index],
        closest_probe=probes[probe_index]['id'],closest_frame=boxes[nearest[pose_index,probe_index]]['name'],
        contact_count=len(collisions),contact_pose_count=len(np.unique(collisions[:,0])) if len(collisions) else 0,
        checks_pass=bool(margins.min()>.02),required_geometric_reserve_m=.02,
        contacts=[dict(source_station_m=site['walking_path']['source_stations_m'][int(i)],
            probe=probes[int(j)]['id'],frame=boxes[nearest[i,j]]['name'],margin_m=float(margins[i,j]))
            for i,j in collisions[:50]])


def main():
    manifest_path=ROOT/'manifests/maze-gate-blockouts.json'
    probe_path=ROOT/'manifests/walking-bike-contact.json'
    data=json.loads(manifest_path.read_text());spec=json.loads(probe_path.read_text())
    if digest(ROOT/spec['source_path']) != spec['source_sha256']:
        raise ValueError('Walking probe source changed; regenerate the probe contract')
    surfaces=json.loads((ROOT/'manifests/surface-model.json').read_text())['pavement']
    reports=[inspect_site(site,data['assets'],spec,surfaces) for site in data['sites']]
    result=dict(schema_version=1,scope='Offline guide tangent poses and sphere probes against fixed gate boxes; not a controller or app test',
        manifest_sha256=digest(manifest_path),probe_specification_sha256=digest(probe_path),
        runtime_probe_header_sha256=digest(ROOT/'unreal/Source/StanleyParkSim/SPWalkingBikeGeometry.h'),
        sites=reports,checks_pass=all(r['checks_pass'] for r in reports),application_run=False,release_accepted=False,
        limitation='Pose samples are spaced about4 cm. Runtime checks swept probes through each turn and translation. Guide following error is not part of this offline tangent-pose check.')
    save_json(ROOT/'evidence/facilities/walking-bike-gate-clearance.json',result)
    print(json.dumps({**result,'sites':[{k:v for k,v in r.items() if k!='contacts'} for r in reports]}))


if __name__=='__main__':main()
