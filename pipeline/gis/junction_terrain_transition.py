"""Bounded M1 contact blend for the failed City branch 2336/main-path join.

The source terrain and main pavement remain immutable inputs. This class clips
only intersecting mesh triangles at the patch's outer/inner fade boundaries.
Apply the same object to terrain and visual route meshes (lift=.06 for those).
No additional collider is made. All geometry outside the patch is unchanged.
"""
import hashlib
import json

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, Point


class JunctionTerrainTransition:
    def __init__(self, root, points, normal, profile, source_surface_z):
        self.root, self.source_z = root, source_surface_z
        settings_path = root/'manifests/junction-transition-settings.json'
        self.settings = cfg = json.loads(settings_path.read_text(encoding='utf8'))
        self.settings_hash = hashlib.sha256(settings_path.read_bytes()).hexdigest()
        city = json.loads((root/'data/routes/derived/city-branch-junctions.json').read_text(encoding='utf8'))
        branch = next(b for b in city['branches'] if b['edge_id'] == cfg['branch_id'])
        xy = np.array(branch['coordinates_local_xy_m'])
        if cfg['branch_endpoint'] == 'end':
            xy = xy[::-1]
        line = LineString(xy)
        stations = np.r_[np.arange(0, cfg['approach_length_m'], .5), cfg['approach_length_m']]
        approach = LineString([line.interpolate(s).coords[0] for s in stations])
        self.core = approach.buffer(cfg['branch_half_width_m'], cap_style='flat', join_style='mitre')
        source_s = np.asarray(profile['chainage_source'])
        select = np.flatnonzero(abs(source_s-cfg['source_station_m']) < 30)
        width, fall = np.asarray(profile['width_m'])[select], np.asarray(profile['crossfall'])[select]
        points, normal = np.asarray(points)[select], np.asarray(normal)[select]
        edge = []
        for sign in [-1, 1]:
            xyz = points.copy()
            xyz[:, :2] += normal*sign*width[:, None]*.5
            xyz[:, 2] += fall*sign*width*.5
            edge.append(xyz)
        self.edge_a = np.concatenate([e[:-1] for e in edge])
        self.edge_b = np.concatenate([e[1:] for e in edge])
        self.edge_delta = self.edge_b-self.edge_a
        self.edge_length2 = np.sum(self.edge_delta[:, :2]**2, axis=1)
        strips = [Polygon([edge[0][i, :2], edge[0][i+1, :2], edge[1][i+1, :2], edge[1][i, :2]]) for i in range(len(points)-1)]
        self.pavement = shapely.union_all(shapely.make_valid(strips))
        self.footprint = (self.core.buffer(cfg['lateral_fade_m'], join_style='mitre')
                          .intersection(self.pavement.buffer(cfg['outward_fade_m'], join_style='mitre'))
                          .difference(self.pavement))
        if self.footprint.is_empty:
            raise ValueError('Junction transition misses pavement')

    def offset(self, xy):
        xy = np.asarray(xy)
        offsets = np.zeros(len(xy))
        for i, p in enumerate(xy):
            point = Point(p)
            if self.footprint.distance(point) > 1e-7:
                continue
            u = np.clip(np.sum((p-self.edge_a[:, :2])*self.edge_delta[:, :2], axis=1)/self.edge_length2, 0, 1)
            foot = self.edge_a + u[:, None]*self.edge_delta
            distances = np.linalg.norm(p-foot[:, :2], axis=1)
            k = int(np.argmin(distances))
            outward = np.clip(1-distances[k]/self.settings['outward_fade_m'], 0, 1)
            lateral = np.clip(1-self.core.distance(point)/self.settings['lateral_fade_m'], 0, 1)
            original = float(self.source_z([foot[k]])[0])
            offsets[i] = (foot[k, 2]-original)*outward*lateral
        return offsets

    def apply(self, vertices, faces, colors=None, lift=0.):
        """Return vertices, faces, colors, report; never modify caller arrays.

        lift is only a report field: .06 m on a visual ribbon is preserved since
        the same source-to-target displacement applies to its lifted vertices.
        """
        vertices, faces = np.asarray(vertices), np.asarray(faces)
        triangles = vertices[faces]
        polygons = shapely.polygons(triangles[:, :, :2])
        ids = shapely.STRtree(polygons).query(self.footprint, predicate='intersects')
        # Mere point/line contact must not rewrite an otherwise untouched face.
        ids = np.array([i for i in ids if polygons[i].intersection(self.footprint).area > 1e-9], dtype=int)
        keep = np.ones(len(faces), dtype=bool)
        keep[ids] = False
        extra_v, extra_f, extra_c, all_offsets = [], [], [], []
        for i in ids:
            tri = triangles[i]
            matrix = np.column_stack((tri[1, :2]-tri[0, :2], tri[2, :2]-tri[0, :2]))
            if abs(np.linalg.det(matrix)) < 1e-10:
                continue
            inside = polygons[i].intersection(self.footprint)
            fragments = [polygons[i].difference(self.footprint), inside.intersection(self.core), inside.difference(self.core)]
            for fragment in fragments:
                for piece in shapely.get_parts(fragment):
                    if piece.geom_type != 'Polygon' or piece.area < 1e-9:
                        continue
                    for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(piece)):
                        xy = np.asarray(triangle.exterior.coords)[:3, :2]
                        cross = np.linalg.det(np.column_stack((xy[1]-xy[0], xy[2]-xy[0])))
                        if abs(cross) < 1e-10:
                            continue
                        if cross < 0:
                            xy = xy[::-1]
                        uv = np.linalg.solve(matrix, (xy-tri[0, :2]).T).T
                        weights = np.column_stack((1-uv.sum(1), uv))
                        offset = self.offset(xy)
                        z = weights@tri[:, 2]+offset
                        begin = len(vertices)+len(extra_v)
                        extra_v.extend(np.column_stack((xy, z)))
                        extra_f.append([begin, begin+1, begin+2])
                        all_offsets.extend(offset)
                        if colors is not None:
                            extra_c.extend(weights@colors[faces[i]])
        result_v = np.vstack((vertices, extra_v)) if extra_v else vertices.copy()
        result_f = np.vstack((faces[keep], extra_f)).astype(np.int32) if extra_f else faces.copy()
        result_c = (np.vstack((colors, extra_c)) if extra_c else colors.copy()) if colors is not None else None
        report = dict(junction_id=self.settings['junction_id'], branch_id=self.settings['branch_id'],
            settings_sha256=self.settings_hash, footprint_geojson=shapely.to_geojson(self.footprint),
            footprint_area_m2=float(self.footprint.area), source='Explicit M1 surface engineering estimate',
            affected_input_triangles=len(ids), replacement_triangles=len(extra_f),
            maximum_vertex_displacement_m=float(max(abs(np.asarray(all_offsets)), default=0)),
            preserved_display_lift_m=lift, new_collider_created=False,
            outside_patch_geometry_unchanged=True, main_pavement_unchanged=True,
            numerical_contact_acceptance=False, runtime_acceptance=False)
        return result_v, result_f, result_c, report

    def refit_overlay(self, vertices, faces, terrain_vertices, terrain_faces, lift=.06):
        """Keep original overlay outside the patch; clip its inside to final TIN."""
        vertices, faces = np.asarray(vertices), np.asarray(faces)
        triangles = vertices[faces]
        polygons = shapely.polygons(triangles[:, :, :2])
        ids = shapely.STRtree(polygons).query(self.footprint, predicate='intersects')
        ids = np.array([i for i in ids if polygons[i].intersection(self.footprint).area > 1e-9], dtype=int)
        keep = np.ones(len(faces), dtype=bool)
        keep[ids] = False
        patch = shapely.union_all(polygons[ids]).intersection(self.footprint)
        extra_v, extra_f = [], []

        def append_clipped(tri, fragment, z_lift):
            matrix = np.column_stack((tri[1, :2]-tri[0, :2], tri[2, :2]-tri[0, :2]))
            if abs(np.linalg.det(matrix)) < 1e-10:
                return
            for piece in shapely.get_parts(fragment):
                if piece.geom_type != 'Polygon' or piece.area < 1e-9:
                    continue
                for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(piece)):
                    xy = np.asarray(triangle.exterior.coords)[:3, :2]
                    cross = np.linalg.det(np.column_stack((xy[1]-xy[0], xy[2]-xy[0])))
                    if abs(cross) < 1e-10:
                        continue
                    if cross < 0:
                        xy = xy[::-1]
                    uv = np.linalg.solve(matrix, (xy-tri[0, :2]).T).T
                    z = tri[0, 2]+uv@(tri[1:, 2]-tri[0, 2])+z_lift
                    begin = len(vertices)+len(extra_v)
                    extra_v.extend(np.column_stack((xy, z)))
                    extra_f.append([begin, begin+1, begin+2])

        for i in ids:
            append_clipped(triangles[i], polygons[i].difference(self.footprint), 0.)
        # Query only local actual triangles; avoid constructing a full-park tree.
        all_terrain = np.asarray(terrain_vertices)[terrain_faces]
        lo, hi = all_terrain[:, :, :2].min(1), all_terrain[:, :, :2].max(1)
        xmin, ymin, xmax, ymax = patch.bounds
        take = (lo[:, 0] <= xmax) & (hi[:, 0] >= xmin) & (lo[:, 1] <= ymax) & (hi[:, 1] >= ymin)
        local = all_terrain[take]
        local_polys = shapely.polygons(local[:, :, :2])
        local_tree = shapely.STRtree(local_polys)
        for i in local_tree.query(patch, predicate='intersects'):
            append_clipped(local[i], local_polys[i].intersection(patch), lift)
        output_v = np.vstack((vertices, extra_v))
        output_f = np.vstack((faces[keep], extra_f)).astype(np.int32)
        probes = output_v[output_f].mean(1)
        expected = np.asarray(self.source_z(probes))+lift
        changed = shapely.contains_xy(self.footprint, probes[:, 0], probes[:, 1])
        for index in np.flatnonzero(changed):
            point = Point(probes[index, :2])
            matches = local_tree.query(point.buffer(1e-7), predicate='intersects')
            matches = [i for i in matches if local_polys[i].distance(point) < 1e-7]
            if not matches:
                raise ValueError('Transition overlay lacks an actual terrain triangle')
            tri = local[matches[0]]
            uv = np.linalg.solve(np.column_stack((tri[1, :2]-tri[0, :2], tri[2, :2]-tri[0, :2])), probes[index, :2]-tri[0, :2])
            expected[index] = tri[0, 2]+uv@(tri[1:, 2]-tri[0, 2])+lift
        error = float(np.max(np.abs(probes[:, 2]-expected)))
        if error > 1e-6:
            raise ValueError(f'Transition overlay/actual triangle mismatch: {error} m')
        return output_v, output_f, dict(branch_id=self.settings['branch_id'],
            replaced_overlay_triangles=len(ids), replacement_triangles=len(extra_f),
            checked_face_centroids=len(probes), actual_terrain_plane_max_error_m=error,
            display_lift_m=lift, method='Clipped directly to actual final transition terrain triangles')
