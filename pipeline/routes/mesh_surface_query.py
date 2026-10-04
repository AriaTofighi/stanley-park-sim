"""Query actual exported top-facing mesh triangles without terrain-grid guesses."""
import hashlib

import numpy as np
import shapely
from shapely.geometry import Point, box


class MeshSurfaceQuery:
    def __init__(self, root, records, bounds):
        self.inputs, triangles = [], []
        xmin, ymin, xmax, ymax = bounds
        area = box(*bounds)
        for item in records:
            path = root/item['path']
            with np.load(path) as mesh:
                vertices = mesh['vertices'] + mesh['anchor']
                if not box(*vertices[:, :2].min(0), *vertices[:, :2].max(0)).intersects(area):
                    continue
                tri = vertices[mesh['faces']]
            lo, hi = tri[:, :, :2].min(1), tri[:, :, :2].max(1)
            normal = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
            take = ((lo[:, 0] <= xmax) & (hi[:, 0] >= xmin) &
                    (lo[:, 1] <= ymax) & (hi[:, 1] >= ymin) & (normal[:, 2] > 1e-10))
            if not take.any():
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != item['sha256']:
                raise ValueError(f'Stale exported mesh hash: {path}')
            self.inputs.append(dict(path=item['path'], sha256=actual))
            triangles.append(tri[take])
        self.triangles = np.concatenate(triangles) if triangles else np.empty((0, 3, 3))
        self.polygons = shapely.polygons(self.triangles[:, :, :2])
        self.tree = shapely.STRtree(self.polygons)
        self.footprint = shapely.union_all(self.polygons)

    def heights(self, xy, tolerance=1e-6):
        point = Point(xy)
        ids = self.tree.query(point.buffer(tolerance), predicate='intersects')
        result = []
        for index in ids:
            if self.polygons[index].distance(point) > tolerance:
                continue
            tri = self.triangles[index]
            uv = np.linalg.solve(np.column_stack((tri[1, :2]-tri[0, :2], tri[2, :2]-tri[0, :2])), np.asarray(xy)-tri[0, :2])
            result.append(float(tri[0, 2]+uv@(tri[1:, 2]-tri[0, 2])))
        return result

    def height(self, xy, tolerance=1e-6):
        result = self.heights(xy, tolerance)
        if not result:
            raise ValueError(f'No exported top surface at {list(xy)}')
        if max(result)-min(result) > 1e-4:
            raise ValueError(f'Multiple exported heights at {list(xy)}: {result}')
        return float(np.mean(result))
