"""Read exact exported terrain edges for replacement-surface boundary stitches.

This module does not alter terrain. Call it after the footprint has been cut.
Its vertices include every actual terrain/footprint clipping intersection.
"""
import hashlib
import json

import numpy as np
import shapely
from shapely.geometry import Point, box


class ExportedTerrainPatch:
    def __init__(self, root, footprint, margin=3):
        self.root, self.footprint = root, footprint
        manifest = json.loads((root/'manifests/surface-model.json').read_text(encoding='utf8'))
        xmin,ymin,xmax,ymax = footprint.bounds
        area = box(xmin-margin,ymin-margin,xmax+margin,ymax+margin)
        triangles, self.inputs = [], []
        for item in manifest['terrain']:
            path = root/item['path']
            with np.load(path) as data:
                vertices = data['vertices']+data['anchor']
                if not box(*vertices[:,:2].min(0),*vertices[:,:2].max(0)).intersects(area):continue
                t = vertices[data['faces']]
            lo,hi=t[:,:,:2].min(1),t[:,:,:2].max(1)
            take=(lo[:,0]<=xmax+margin)&(hi[:,0]>=xmin-margin)&(lo[:,1]<=ymax+margin)&(hi[:,1]>=ymin-margin)
            if not take.any():continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != item['sha256']:raise ValueError(f'Stale exported terrain manifest: {path}')
            self.inputs.append(dict(path=item['path'],sha256=actual))
            triangles.append(t[take])
        if not triangles:raise ValueError('No exported terrain beside the replacement footprint')
        self.triangles=np.concatenate(triangles)
        normal=np.cross(self.triangles[:,1]-self.triangles[:,0],self.triangles[:,2]-self.triangles[:,0])
        # Exact polygon clipping can leave round-off slivers or duplicate
        # vertices on an existing boundary. Such zero-area faces must not
        # increase edge counts or enter a singular barycentric height query.
        usable=np.abs(normal[:,2])>2e-8
        self.ignored_degenerate_triangles=int(np.count_nonzero(~usable))
        self.triangles=self.triangles[usable];normal=normal[usable]
        negative=normal[:,2]<0
        self.triangles[negative]=self.triangles[negative,::-1]
        self.polygons=shapely.polygons(self.triangles[:,:,:2])
        self.tree=shapely.STRtree(self.polygons)
        # Count edges across tile boundaries; retain full precision coordinates.
        flat=self.triangles.reshape(-1,3)
        _,first,weld=np.unique(np.round(flat,7),axis=0,return_index=True,return_inverse=True)
        vertices=flat[first];faces=weld.reshape(-1,3)
        counts={};directed={}
        for face in faces:
            for a,b in zip(face,np.roll(face,-1)):
                key=tuple(sorted((int(a),int(b))))
                counts[key]=counts.get(key,0)+1;directed[key]=(int(a),int(b))
        self.boundary_segments=[]
        for key,count in counts.items():
            if count!=1:continue
            a,b=vertices[list(directed[key])]
            checks=[Point(a[:2]),Point(b[:2]),Point((a[:2]+b[:2])*.5)]
            if max(p.distance(footprint.boundary) for p in checks)<=1e-5:
                self.boundary_segments.append(np.stack((a,b)))
        if not self.boundary_segments:
            raise ValueError('No exact exported cut boundary. Build the registered terrain cut first.')
        self.boundary_segments=np.asarray(self.boundary_segments)

    def height(self, xy, tolerance=1e-5):
        """Height on a retained triangle plane. Refuse extrapolation into a cut."""
        xy=np.asarray(xy,dtype=float)
        point=Point(xy)
        ids=self.tree.query(point.buffer(tolerance),predicate='intersects')
        ids=[i for i in ids if self.polygons[i].distance(point)<=tolerance]
        if not ids:raise ValueError(f'No retained terrain triangle at {xy.tolist()}')
        tri=self.triangles[ids[0]]
        uv=np.linalg.solve(np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2])),xy-tri[0,:2])
        return float(tri[0,2]+uv@(tri[1:,2]-tri[0,2]))
