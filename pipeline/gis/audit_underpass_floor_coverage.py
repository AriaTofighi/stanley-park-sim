"""Find actual XY holes in the combined imported terrain, lane and tunnel floors."""
import json
import numpy as np
import shapely
from shapely.geometry import box, mapping
from acquire_sources import ROOT, digest, save_json

surface=json.loads((ROOT/'manifests/surface-model.json').read_text())
underpass=json.loads((ROOT/'data/derived/underpass-blockouts.json').read_text())
reports=[]
for site in underpass['sites']:
    xyz=np.asarray(site['floor_center_xyz'])
    lo,hi=xyz[:,:2].min(0)-5,xyz[:,:2].max(0)+5
    bounds=box(*lo,*hi)
    polys=[];inputs=[]
    records=surface['terrain']+[r for r in surface['pavement'] if r['role']=='pavement']
    records += [r for r in underpass['meshes'] if r['site']==site['id'] and r['role'].startswith('FloorExtension')]
    for row in records:
        with np.load(ROOT/row['path']) as p:
            v=p['vertices']+p['anchor'];f=p['faces']
        if not bounds.intersects(box(*v[:,:2].min(0),*v[:,:2].max(0))):continue
        if digest(ROOT/row['path'])!=row['sha256']:raise ValueError('Stale mesh')
        triangles=v[f];cross=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[:,2]
        values=shapely.polygons(triangles[cross>1e-10,:,:2])
        values=values[shapely.intersects(values,bounds)]
        polys.extend(values);inputs.append(dict(path=row['path'],sha256=row['sha256']))
    missing=bounds.difference(shapely.union_all(polys))
    report=dict(site=site['id'],bounds_local_m=list(bounds.bounds),missing_area_m2=missing.area,
                missing_geometry=mapping(missing),inputs=inputs)
    reports.append(report)
save_json(ROOT/'evidence/underpass-combined-floor-coverage.json',dict(reports=reports))
print(json.dumps([dict(site=r['site'],missing_area_m2=r['missing_area_m2']) for r in reports]))
