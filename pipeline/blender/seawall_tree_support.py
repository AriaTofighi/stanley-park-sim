"""Grounded, clearance-aware support for measured canopy sample centres."""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from seawall_tree_geometry import Geometry


class Ground:
    def __init__(self, scene):
        self.tiles=[]
        for obj in scene.objects:
            if obj.type!="MESH" or not obj.name.startswith("SM_Terrain_"):
                continue
            vertices=[tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]
            points=np.asarray(vertices)
            tree=BVHTree.FromPolygons(vertices,[tuple(p.vertices) for p in obj.data.polygons])
            self.tiles.append((points[:,:2].min(0),points[:,:2].max(0),tree,obj.name))
        if not self.tiles:
            raise RuntimeError("No terrain is available for crown support")

    def at(self, xy):
        hits=[]
        for low,high,tree,name in self.tiles:
            if np.any(xy<low) or np.any(xy>high):
                continue
            point,normal,_,distance=tree.ray_cast(Vector((xy[0],xy[1],1000)),Vector((0,0,-1)),2000)
            if point is not None:
                hits.append((point.z,normal.z,name))
        return max(hits,key=lambda row:row[0]) if hits else None


def make_support(clearance, ground, anchor, height, radius, floor, cfg, seed):
    """Keep the canopy centre fixed; infer a root within its crown footprint."""
    anchor=np.asarray(anchor,dtype=float)
    top=anchor[2]+height
    if floor>=top-.35:
        return None,dict(reason="crown_below_clearance")
    safe_at_centre=clearance.blocked(anchor[:2],anchor[2],10000,radius,cfg)!="stem_clearance"
    candidates=[anchor[:2]] if safe_at_centre else []
    if not safe_at_centre:
        # Select the shortest supported offset. No crown anchor is moved.
        for distance in np.arange(.75,radius+.001,.75):
            for i in range(24):
                angle=(i+seed%24)*math.tau/24
                candidates.append(anchor[:2]+distance*np.array([math.cos(angle),math.sin(angle)]))
    trunk_radius=max(.10,radius*.076)
    for xy in candidates:
        if clearance.blocked(xy,anchor[2],10000,radius,cfg)=="stem_clearance":
            continue
        hit=ground.at(xy)
        if hit is None:
            if not safe_at_centre:
                continue
            ground_z,normal_z,terrain=anchor[2],1.0,"source_base_fallback"
        else:
            ground_z,normal_z,terrain=hit
        distance=float(np.linalg.norm(xy-anchor[:2]))
        if distance and (abs(ground_z-anchor[2])>2.5 or normal_z<.22):
            continue
        root=np.array([xy[0],xy[1],ground_z-.08])
        if distance<.01:
            join_z=max(anchor[2]+height*.48,floor+.35)
            if join_z>=top-.3:
                continue
            points=[root, np.array([xy[0],xy[1],ground_z+(join_z-ground_z)*.52]),
                    np.array([xy[0],xy[1],join_z]),
                    np.array([xy[0],xy[1],min(top-.25,join_z+height*.10)])]
            radii=[trunk_radius,trunk_radius*.80,trunk_radius*.45,trunk_radius*.22]
        else:
            # All horizontal movement begins above the rider clearance plane.
            bend_z=max(ground_z+1.4,floor+trunk_radius+.20)
            join_z=max(anchor[2]+height*.52,bend_z+1.2)
            if join_z>=top-.6:
                continue
            points=[root, np.array([xy[0],xy[1],bend_z])]
            radii=[trunk_radius,trunk_radius*.72]
            for t in (.25,.50,.75,1.0):
                curve=t*t*(3-2*t)
                position=xy*(1-curve)+anchor[:2]*curve
                points.append(np.r_[position,bend_z+(join_z-bend_z)*t])
                radii.append(trunk_radius*(.72-.40*t))
            clear=True
            for a,b,ra,rb in zip(points[:-1],points[1:],radii[:-1],radii[1:]):
                count=max(2,int(np.linalg.norm(b-a)/.4)+1)
                for t in np.linspace(0,1,count):
                    point=a*(1-t)+b*t
                    r=ra*(1-t)+rb*t
                    path_floor=clearance.crown_floor(point[:2],r+cfg["trunk_margin_m"],cfg)
                    if point[2]-r < path_floor:
                        clear=False
                        break
                if not clear:
                    break
            if not clear:
                continue
        geometry=Geometry()
        geometry.tube(points,radii,8 if distance else 6)
        return geometry,dict(reason="offset_support" if distance else "centre_support",
            root_local_m=root.tolist(),root_offset_m=(root-anchor).tolist(),
            horizontal_offset_m=distance,terrain_mesh=terrain,
            connection_height_m=float(points[-1][2]),centre_stem_clear=safe_at_centre)
    return None,dict(reason="no_safe_grounded_support",maximum_search_radius_m=radius)
