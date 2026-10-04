"""Measured 2022 ground queries in a bounded route corridor."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import LineString

ROOT=Path(__file__).resolve().parents[2]


def circuit_samples(spacing=1.):
    routes=json.loads((ROOT/"data/routes/derived/park_routes.json").read_text())
    line=LineString(np.asarray(routes["main_circuit"]["xyz_local_m"])[:,:2])
    s=np.linspace(0,line.length,int(np.ceil(line.length/spacing))+1)
    xy=shapely.get_coordinates(shapely.line_interpolate_point(line,s))
    tangent=np.gradient(xy,axis=0)
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    return s,xy,tangent,np.column_stack((-tangent[:,1],tangent[:,0]))


class GroundReference:
    def __init__(self, main_only=True):
        routes=json.loads((ROOT/"data/routes/derived/park_routes.json").read_text())
        paths=[LineString(np.asarray(routes["main_circuit"]["xyz_local_m"])[:,:2])] if main_only else [LineString(e["coordinates_local_xy_m"]) for e in routes["edges"]]
        corridor=shapely.union_all([l.buffer(40) for l in paths])
        points, colors, inputs=[],[],[]
        for file in sorted((ROOT/"data/derived").glob("lidar2022_*.npz")):
            with np.load(file) as package:
                ground=package["ground"]
                take=shapely.contains_xy(corridor,ground[:,0],ground[:,1])
                points.append(ground[take,:3])
                colors.append(package["ground_rgb"][take] if "ground_rgb" in package else np.zeros((take.sum(),3),np.uint16))
                inputs.append(dict(path=file.relative_to(ROOT).as_posix(),points=int(take.sum())))
        self.points=np.concatenate(points)
        self.colors=np.concatenate(colors)
        self.inputs=inputs
        self.tree=cKDTree(self.points[:,:2])

    def nearest_height(self, xy, count=8, radius=1.):
        distance,index=self.tree.query(xy,k=count,workers=4)
        weight=np.exp(-np.square(distance/.25))
        weight[distance>radius]=0
        total=weight.sum(axis=1)
        z=(self.points[index,2]*weight).sum(axis=1)/np.maximum(total,1e-20)
        z[total<1e-10]=np.nan
        return z,distance[:,0]
