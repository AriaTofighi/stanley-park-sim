"""Bounded terrain correction from saved raw-return controls. Root integrates it."""
import json
import numpy as np
import shapely
from shapely.geometry import Point,Polygon,shape
from lumberman_integration_geometry import sha


class LumbermanTerrainTransition:
    def __init__(self,root):
        self.root=root;self.path='manifests/lumberman-terrain-transitions.json'
        self.data=json.loads((root/self.path).read_text(encoding='utf8'))
        for row in self.data['inputs']:
            if sha(root/row['path'])!=row['sha256']:raise ValueError('Stale Lumberman transition input: '+row['path'])
        p=root/self.data['mesh_path']
        if sha(p)!=self.data['mesh_sha256']:raise ValueError('Changed Lumberman transition cells')
        with np.load(p) as package:
            self.triangles=package['vertices'][package['faces']]
            self.weights=package['weights'][package['faces']]
            self.paint=package['paint_asphalt']
        self.polygons=shapely.polygons(self.triangles[:,:,:2]);self.tree=shapely.STRtree(self.polygons)
        self.footprint=shape(self.data['footprint'])

    def apply(self,vertices,faces,colors=None):
        vertices,faces=np.asarray(vertices),np.asarray(faces)
        triangles=vertices[faces];lo,hi=triangles[:,:,:2].min(1),triangles[:,:,:2].max(1)
        xmin,ymin,xmax,ymax=self.footprint.bounds
        candidate=np.flatnonzero((lo[:,0]<=xmax)&(hi[:,0]>=xmin)&(lo[:,1]<=ymax)&(hi[:,1]>=ymin))
        ids=[i for i in candidate if Polygon(triangles[i,:,:2]).intersection(self.footprint).area>1e-9]
        keep=np.ones(len(faces),bool);keep[ids]=False
        extra_v,extra_f,extra_c=[],[],[];max_displacement=0.;area_before=0.;area_after=0.
        for index in ids:
            original=triangles[index];polygon=Polygon(original[:,:2]);area_before+=polygon.area
            matrix=np.column_stack((original[1,:2]-original[0,:2],original[2,:2]-original[0,:2]))
            if abs(np.linalg.det(matrix))<1e-10:raise ValueError('Degenerate input to Lumberman transition')
            fragments=[(polygon.difference(self.footprint),None)]
            fragments.extend((polygon.intersection(self.polygons[i]),int(i)) for i in self.tree.query(polygon,predicate='intersects'))
            for fragment,cell in fragments:
                for part in shapely.get_parts(fragment):
                    if not isinstance(part,Polygon) or part.area<1e-10:continue
                    for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(part)):
                        xy=np.asarray(triangle.exterior.coords)[:3,:2]
                        signed=np.linalg.det(np.column_stack((xy[1]-xy[0],xy[2]-xy[0])))
                        if abs(signed)<2e-10:continue
                        if signed<0:xy=xy[::-1]
                        bary=np.linalg.solve(matrix,(xy-original[0,:2]).T).T
                        blend=np.column_stack((1-bary.sum(1),bary));ground=blend@original[:,2];z=ground.copy()
                        if cell is not None:
                            target=self.triangles[cell]
                            uv=np.linalg.solve(np.column_stack((target[1,:2]-target[0,:2],target[2,:2]-target[0,:2])),(xy-target[0,:2]).T).T
                            cb=np.column_stack((1-uv.sum(1),uv));weight=np.clip(cb@self.weights[cell],0,1)
                            z=ground+weight*(cb@target[:,2]-ground)
                        offset=len(vertices)+len(extra_v);extra_v.extend(np.column_stack((xy,z)));extra_f.append([offset,offset+1,offset+2])
                        if colors is not None:
                            c=blend@colors[faces[index]]
                            if cell is not None and self.paint[cell]:c[:,:3]=[.12,.125,.12]
                            extra_c.extend(c)
                        max_displacement=max(max_displacement,float(np.max(abs(z-ground))))
                        area_after+=abs(signed)/2
        if abs(area_after-area_before)>1e-5:raise ValueError('Lumberman transition changed terrain coverage')
        output_v=np.vstack((vertices,extra_v)) if extra_v else vertices.copy()
        output_f=np.vstack((faces[keep],extra_f)).astype(np.int32) if extra_f else faces.copy()
        output_c=(np.vstack((colors,extra_c)) if extra_c else colors.copy()) if colors is not None else None
        report=dict(manifest=self.path,manifest_sha256=sha(self.root/self.path),affected_input_triangles=len(ids),
            replacement_triangles=len(extra_f),xy_area_error_m2=abs(area_after-area_before),maximum_vertex_shift_m=max_displacement,
            outside_patch_unchanged=True,lower_cut_preserved=True,seawall_pavement_modified=False,
            source='City2022 raw returns, OSM road alignment, saved measured floor/deck endpoints and explicit engineering fade bands',
            acceptance='Repeat build_lumberman_closures.py against exported terrain and inspect contacts before live acceptance')
        return output_v,output_f,output_c,report

    def bind_rendered_terrain(self,vertices,faces):
        """Bind final corrected triangles for support sampling and route displays."""
        triangles=np.asarray(vertices)[faces];lo,hi=triangles[:,:,:2].min(1),triangles[:,:,:2].max(1)
        xmin,ymin,xmax,ymax=self.footprint.bounds
        take=(lo[:,0]<=xmax+1)&(hi[:,0]>=xmin-1)&(lo[:,1]<=ymax+1)&(hi[:,1]>=ymin-1)
        self.final_triangles=triangles[take]
        self.final_polygons=shapely.polygons(self.final_triangles[:,:,:2])
        self.final_tree=shapely.STRtree(self.final_polygons)

    def final_height(self,xy):
        point=Point(xy);ids=self.final_tree.query(point.buffer(1e-6),predicate='intersects')
        ids=[i for i in ids if self.final_polygons[i].distance(point)<1e-6]
        if not ids:raise ValueError('No final Lumberman triangle at '+str(list(xy)))
        t=self.final_triangles[ids[0]]
        uv=np.linalg.solve(np.column_stack((t[1,:2]-t[0,:2],t[2,:2]-t[0,:2])),np.asarray(xy)-t[0,:2])
        return float(t[0,2]+uv@(t[1:,2]-t[0,2]))

    def sample_heights(self,points,fallback):
        """Use final planes within this patch and the supplied sampler elsewhere."""
        points=np.asarray(points);result=np.asarray(fallback(points)).copy()
        take=shapely.contains_xy(self.footprint.buffer(1e-7),points[:,0],points[:,1])
        for i in np.flatnonzero(take):result[i]=self.final_height(points[i,:2])
        return result

    def refit_overlay(self,vertices,faces,lift=.06):
        """Clip affected display ribbons to actual final terrain planes."""
        vertices,faces=np.asarray(vertices),np.asarray(faces);triangles=vertices[faces]
        polygons=shapely.polygons(triangles[:,:,:2])
        ids=[int(i) for i in shapely.STRtree(polygons).query(self.footprint,predicate='intersects')
             if polygons[i].intersection(self.footprint).area>1e-9]
        if not ids:return vertices,faces,dict(affected=False,actual_terrain_plane_max_error_m=0.)
        keep=np.ones(len(faces),bool);keep[ids]=False
        overlay_patch=shapely.union_all(polygons[ids]).intersection(self.footprint)
        extra_v,extra_f,checked=[],[],[]
        def append(tri,fragment,zlift,check):
            matrix=np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2]))
            if abs(np.linalg.det(matrix))<1e-10:raise ValueError('Degenerate overlay source')
            for part in shapely.get_parts(fragment):
                if not isinstance(part,Polygon) or part.area<1e-10:continue
                for item in shapely.get_parts(shapely.constrained_delaunay_triangles(part)):
                    xy=np.asarray(item.exterior.coords)[:3,:2]
                    signed=np.linalg.det(np.column_stack((xy[1]-xy[0],xy[2]-xy[0])))
                    if abs(signed)<2e-10:continue
                    if signed<0:xy=xy[::-1]
                    uv=np.linalg.solve(matrix,(xy-tri[0,:2]).T).T
                    xyz=np.column_stack((xy,tri[0,2]+uv@(tri[1:,2]-tri[0,2])+zlift))
                    n=len(vertices)+len(extra_v);extra_v.extend(xyz);extra_f.append([n,n+1,n+2])
                    if check:checked.append(xyz.mean(0))
        for i in ids:append(triangles[i],polygons[i].difference(self.footprint),0.,False)
        for i in self.final_tree.query(overlay_patch,predicate='intersects'):
            append(self.final_triangles[i],self.final_polygons[i].intersection(overlay_patch),lift,True)
        output_v=np.vstack((vertices,extra_v)) if extra_v else vertices.copy()
        output_f=np.vstack((faces[keep],extra_f)).astype(np.int32) if extra_f else faces[keep]
        error=max((abs(p[2]-self.final_height(p[:2])-lift) for p in checked),default=0.)
        if error>1e-6:raise ValueError('Lumberman display does not match actual terrain: '+str(error))
        return output_v,output_f,dict(affected=True,replaced_input_triangles=len(ids),
            replacement_triangles=len(extra_f),checked_face_centroids=len(checked),
            actual_terrain_plane_max_error_m=float(error),display_lift_m=lift)
