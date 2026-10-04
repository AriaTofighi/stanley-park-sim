"""Split pavement support walls at the planes of the final retained terrain."""
import numpy as np
import shapely
from shapely.geometry import LineString, Point


class PavementTerrainContact:
    def __init__(self, vertices, faces):
        self.triangles=np.asarray(vertices)[faces]
        normal=np.cross(self.triangles[:,1]-self.triangles[:,0],self.triangles[:,2]-self.triangles[:,0])
        self.triangles=self.triangles[abs(normal[:,2])>1e-10]
        self.polygons=shapely.polygons(self.triangles[:,:,:2])
        self.tree=shapely.STRtree(self.polygons)
        self.maximum_boundary_distance=0.
        self.split_segments=0

    def section(self, a, b):
        line=LineString([a[:2],b[:2]])
        ids=self.tree.query(line.buffer(.006),predicate='intersects')
        if not len(ids):raise ValueError('Pavement support has no retained terrain')
        fractions=[0.,1.]
        for index in ids:
            for hit in shapely.get_parts(line.intersection(self.polygons[index].boundary)):
                if hit.is_empty:continue
                if isinstance(hit,Point):fractions.append(line.project(hit)/line.length)
                elif isinstance(hit,LineString):
                    fractions.extend(line.project(Point(xy))/line.length for xy in (hit.coords[0],hit.coords[-1]))
        fractions=np.array(sorted(set(round(float(x),10) for x in fractions)))
        edge=a+(b-a)*fractions[:,None]
        ground=[]
        for point in edge:
            distances=shapely.distance(self.polygons[ids],Point(point[:2]))
            nearest=int(np.argmin(distances));distance=float(distances[nearest])
            if distance>.006:
                raise ValueError(f'Pavement support misses retained terrain by {distance} m at {point.tolist()}')
            self.maximum_boundary_distance=max(self.maximum_boundary_distance,distance)
            tri=self.triangles[ids[nearest]]
            uv=np.linalg.solve(np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2])),point[:2]-tri[0,:2])
            ground.append(float(tri[0,2]+uv@(tri[1:,2]-tri[0,2])))
        ground=np.array(ground)
        # Split a change from fill to cut. Each panel then has one winding and
        # never forms a twisted quad. No arbitrary vertical overlap is needed:
        # both endpoints lie on the same final terrain plane for each panel.
        extra=[]
        for i in range(len(edge)-1):
            delta=ground[i:i+2]-edge[i:i+2,2]
            if delta[0]*delta[1]<0:
                t=delta[0]/(delta[0]-delta[1])
                extra.append((i,t))
        for i,t in reversed(extra):
            point=edge[i]+t*(edge[i+1]-edge[i])
            edge=np.insert(edge,i+1,point,axis=0)
            ground=np.insert(ground,i+1,point[2])
        self.split_segments+=len(edge)-1
        bottom=edge.copy();bottom[:,2]=ground
        return edge,bottom
