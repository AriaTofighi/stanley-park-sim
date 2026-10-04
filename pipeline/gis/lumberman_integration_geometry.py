"""Read actual Lumberman solids and contact planes. No terrain or app changes."""
import hashlib
import json
import numpy as np
import shapely
from shapely.geometry import LineString, Point, shape


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FacilitySolids:
    def __init__(self, root):
        self.root = root
        self.path = 'manifests/lumberman-facility-blockouts.json'
        self.data = json.loads((root/self.path).read_text(encoding='utf8'))
        p = self.data['replacement_footprints_path']
        if sha(root/p) != self.data['replacement_footprints_sha256']:
            raise ValueError('Lumberman replacement footprints changed')
        self.inputs = [dict(path=self.path, sha256=sha(root/self.path)),
                       dict(path=p, sha256=sha(root/p))]
        rows = json.loads((root/p).read_text(encoding='utf8'))['features']
        self.footprints = {r['properties']['id']: shape(r['geometry']) for r in rows}
        frame = self.data['frame']
        self.origin = np.array(frame['origin'])
        self.u, self.v = np.array(frame['road_u']), np.array(frame['waterpark_v'])
        self.skew = frame['skew']
        self.solids = []
        # These are closed structural prisms. Railings, door overlays and upper
        # green panels do not form a continuous bank-retaining envelope.
        roles = ('PedestrianFloor', 'RoadDeck', 'Facade', 'OuterReturn', 'PassageWall')
        for row in self.data['assets']:
            if not any(role in row['name'] for role in roles):
                continue
            path = root/row['mesh_path']
            if sha(path) != row['sha256']:
                raise ValueError('Lumberman solid changed: '+row['name'])
            self.inputs.append(dict(path=row['mesh_path'], sha256=row['sha256']))
            with np.load(path) as package:
                vertices = package['vertices']
                if 'anchor' in package:
                    vertices = vertices+package['anchor']
                triangles = vertices[package['faces']]
            normals = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])
            triangles = triangles[np.abs(normals[:,2]) > 1e-8]
            polygons = shapely.polygons(triangles[:,:,:2])
            self.solids.append(dict(name=row['name'], triangles=triangles, polygons=polygons,
                                    tree=shapely.STRtree(polygons)))
        self.floor = next(s for s in self.solids if s['name'].endswith('PedestrianFloor'))
        self.deck = next(s for s in self.solids if s['name'].endswith('RoadDeck'))

    def uv(self, xy):
        xy = np.asarray(xy)-self.origin
        u, v = xy@self.u, xy@self.v
        return np.array([u, v-self.skew*u])

    def xy(self, uv):
        u, v = uv
        return self.origin+self.u*u+self.v*(v+self.skew*u)

    def vertical_range(self, solid, xy, required=True):
        point = Point(xy)
        ids = solid['tree'].query(point.buffer(1e-6), predicate='intersects')
        ids = [i for i in ids if solid['polygons'][i].distance(point) < 1e-6]
        if not ids:
            if required:
                raise ValueError('No solid plane at '+str(list(xy))+': '+solid['name'])
            return None
        heights = []
        for i in ids:
            t = solid['triangles'][i]
            uv = np.linalg.solve(np.column_stack((t[1,:2]-t[0,:2],t[2,:2]-t[0,:2])),np.asarray(xy)-t[0,:2])
            heights.append(float(t[0,2]+uv@(t[1:,2]-t[0,2])))
        return np.array([min(heights), max(heights)])

    def ranges_along(self, xy):
        rows = []
        for solid in self.solids:
            if self.vertical_range(solid, xy.mean(0), required=False) is not None:
                ranges = np.array([self.vertical_range(solid, p) for p in xy])
                rows.append(dict(name=solid['name'], low=ranges[:,0], high=ranges[:,1]))
        return rows

    def split_fractions(self, line):
        fractions = [0., 1.]
        def add(hit):
            if hit.is_empty:
                return
            if isinstance(hit, Point):
                fractions.append(line.project(hit)/line.length)
            elif isinstance(hit, LineString):
                fractions.extend(line.project(Point(p))/line.length for p in (hit.coords[0],hit.coords[-1]))
            else:
                for part in shapely.get_parts(hit):
                    add(part)
        for solid in self.solids:
            for i in solid['tree'].query(line.buffer(1e-6), predicate='intersects'):
                polygon=solid['polygons'][i]
                add(line.intersection(polygon.boundary))
                # Cut edges can be a few ulps outside a coincident solid edge.
                # Split at its actual corner projections under the same 1 um
                # contact tolerance used by vertical_range; do not extrapolate
                # a shortened return wall across the neighbouring facade.
                for point in polygon.exterior.coords:
                    p=Point(point)
                    if line.distance(p)<1e-6:
                        fractions.append(line.project(p)/line.length)
        return sorted(set(round(min(1.,max(0.,v)),12) for v in fractions))


def height_order_splits(ground, ranges):
    """Split where linear terrain/solid levels cross, so interval order is fixed."""
    levels = [ground]+[r[k] for r in ranges for k in ('low','high')]
    fractions = [0.,1.]
    for i,a in enumerate(levels):
        for b in levels[i+1:]:
            d = a-b
            if d[0]*d[1] < -1e-16:
                fractions.append(float(d[0]/(d[0]-d[1])))
    return sorted(set(round(v,12) for v in fractions))


def exposed_ranges(ground, ranges):
    """Return only the terrain-to-floor vertical intervals not filled by a solid."""
    floor = next(r for r in ranges if r['name'].endswith('PedestrianFloor'))
    low = min((ground,floor['low']),key=lambda a:a.mean())
    high = max((ground,floor['high']),key=lambda a:a.mean())
    cursor = low.copy()
    result = []
    for row in sorted(ranges,key=lambda r:r['low'].mean()):
        if row['high'].mean() <= cursor.mean()+1e-8:
            continue
        if row['low'].mean() >= high.mean()-1e-8:
            break
        end = min((row['low'],high),key=lambda a:a.mean())
        if end.mean() > cursor.mean()+1e-8:
            result.append((cursor.copy(),end.copy()))
        cursor = max((cursor,row['high']),key=lambda a:a.mean()).copy()
        if cursor.mean() >= high.mean()-1e-8:
            break
    if high.mean() > cursor.mean()+1e-8:
        result.append((cursor,high))
    return result
