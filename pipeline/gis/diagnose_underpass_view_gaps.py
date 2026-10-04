"""Locate retained viewport rays that pass below a terrain boundary."""
import json
import numpy as np
import shapely
from shapely.geometry import LineString, Point, box, shape
from acquire_sources import ROOT, save_json
from terrain_boundary_stitch import ExportedTerrainPatch

opening=json.loads((ROOT/'data/derived/underpass-openings.geojson').read_text())['features'][0]
patch=ExportedTerrainPatch(ROOT,shape(opening['geometry']),margin=15)
tri=patch.triangles
flat=tri.reshape(-1,3)
_,first,weld=np.unique(np.round(flat,7),axis=0,return_index=True,return_inverse=True)
vertices=flat[first];faces=weld.reshape(-1,3)
edges={}
for face in faces:
    for a,b in zip(face,np.roll(face,-1)):
        key=tuple(sorted((int(a),int(b))))
        edges.setdefault(key,[]).append((int(a),int(b)))
boundary=[vertices[list(v[0])] for v in edges.values() if len(v)==1]
reports=[]
for ray in json.loads((ROOT/'evidence/ceperley-gap-rays.json').read_text()):
    o,d=np.array(ray['origin']),np.array(ray['direction'])
    line=LineString([o[:2],np.array(ray['position'])[:2]])
    hits=[]
    for a,b in boundary:
        seg=LineString([a[:2],b[:2]])
        p=line.intersection(seg)
        if not isinstance(p,Point) or p.is_empty:continue
        xy=np.array(p.coords[0]);fraction=seg.project(p)/seg.length
        ground=float(a[2]+fraction*(b[2]-a[2]))
        t=float(np.dot(xy-o[:2],d[:2])/np.dot(d[:2],d[:2]))
        hits.append(dict(xy=xy.tolist(),distance=t,ray_z=float(o[2]+t*d[2]),ground_z=ground,
                         on_underpass_opening=p.distance(shape(opening['geometry']).boundary)<1e-5))
    reports.append(dict(ray=ray,boundary_crossings=sorted(hits,key=lambda h:h['distance'])))
save_json(ROOT/'evidence/ceperley-gap-ray-boundaries.json',reports)
print(json.dumps(reports[:3],indent=2))
