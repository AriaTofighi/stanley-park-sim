"""Finite current-footprint M1 skyline package. No Blender or engine control."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon, Point, shape
from shapely.geometry.polygon import orient
from shapely import affinity

from skyline_source_geometry import read_buildings
from skyline_height_sources import HeightSources, metres
from skyline_meshes import extrusion, ring_solid, fabric_surface, validate
from height_reference import VancouverHeightConversion

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/derived/skyline'
COLORS={'glass':[.27,.38,.43,1.], 'stone':[.47,.48,.46,1.], 'light':[.68,.69,.65,1.], 'sail':[.88,.88,.83,1.]}


def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def rectangle_axes(poly):
    coords=np.asarray(orient(poly.minimum_rotated_rectangle,sign=1).exterior.coords)[:4]
    edges=np.roll(coords,-1,axis=0)-coords;i=int(np.argmax(np.linalg.norm(edges,axis=1)))
    u=edges[i]/np.linalg.norm(edges[i]);v=np.array([-u[1],u[0]])
    center=coords.mean(0);p=(coords-center)@np.array([u,v]).T
    return center,np.array([u,v]),np.ptp(p,axis=0)


class SkylineBuilder:
    def __init__(self):
        OUT.mkdir(parents=True,exist_ok=True)
        self.cfg=json.loads((ROOT/'manifests/skyline-authoring-settings.json').read_text())
        origin=json.loads((ROOT/'manifests/world-origin.json').read_text())
        if (origin['horizontal_crs'],origin['easting'],origin['northing'],origin['height'])!=('EPSG:3157',489600,5461100,0):
            raise ValueError('Skyline projection constants do not match the immutable project origin')
        self.rows=read_buildings();self.by_id={r['id']:r for r in self.rows}
        self.heights=HeightSources(ROOT);self.geoid=VancouverHeightConversion()
        self.parents=[r for r in self.rows if 'building:part' not in r['tags']]
        tree=shapely.STRtree([r['polygon'] for r in self.parents])
        self.parent_of={};self.children=defaultdict(list)
        for row in self.rows:
            if 'building:part' not in row['tags']:continue
            hits=[i for i in tree.query(row['polygon'],predicate='intersects')
                  if self.parents[i]['polygon'].intersection(row['polygon']).area/row['polygon'].area>.8]
            parent=min((self.parents[i] for i in hits),key=lambda r:r['polygon'].area) if hits else row
            self.parent_of[row['id']]=parent
            if parent is not row:self.children[parent['id']].append(row)
        self.bases={};self.groups=defaultdict(list);self.parts=[];self.excluded=[]
        boundary=json.loads((ROOT/'data/derived/park_boundary.geojson').read_text())
        self.park=shapely.union_all([shape(f['geometry']) for f in boundary['features']])

    def parent(self,row):return self.parent_of.get(row['id'],row)

    def base(self,row):
        parent=self.parent(row)
        if parent['id'] not in self.bases:self.bases[parent['id']]=self.heights.base(parent['polygon'])
        return self.bases[parent['id']]

    def dimension(self,row):
        tags=row['tags'];parent=self.parent(row);pt=parent['tags']
        height=metres(tags.get('height'));minimum=metres(tags.get('min_height')) or 0.
        if height is not None:return height,minimum,dict(method='OSM tagged height/min_height',height_m=height)
        # Same 57-floor Butterfly lobes share the explicit height of their sibling.
        if parent['osm_id']=='653660958' and tags.get('building:levels')=='57':
            return 178.6,minimum,dict(method='Explicit M1 transfer of sibling57-floor OSM height',height_m=178.6,source_part='way_1524215058_0')
        year=tags.get('start_date',tags.get('building:start_date',pt.get('start_date',pt.get('opening_date',''))))[:4]
        if parent['osm_id'] not in self.cfg['no_historic_height_parent_ids'] and not (year.isdigit() and int(year)>2009):
            historic=self.heights.historic(row['polygon'])
            if historic:return historic['height_m'],minimum,historic
        levels=metres(tags.get('building:levels'))
        spacing=self.cfg['commercial_floor_spacing_m'] if pt.get('building') in ['office','commercial','retail','university'] else self.cfg['generic_floor_spacing_m']
        if levels is not None:
            return levels*spacing,minimum,dict(method='Estimated floor spacing times OSM levels',levels=levels,floor_spacing_m=spacing,height_m=levels*spacing)
        return self.cfg['unknown_low_building_height_m'],minimum,dict(method='Explicit unresolved low-building estimate',height_m=self.cfg['unknown_low_building_height_m'])

    def add(self,row,role,vertices,faces,source,material=None,closed=True):
        check=validate(vertices,faces,closed)
        parent=self.parent(row);base=self.base(row)
        material=material or ('glass' if row['tags'].get('building:material')=='glass' or parent['tags'].get('building') in ['office','hotel'] else 'stone')
        if parent['osm_id'] in self.cfg['significant_parent_ids']:
            key='Landmark_'+parent['osm_id']+'_'+row['id']+'_'+role
        else:
            cell=np.floor(np.array(row['polygon'].centroid.coords[0])/self.cfg['group_cell_m']).astype(int)
            key='Cell_'+'_'.join(map(str,cell))
        key+='_'+material
        part_id=row['id']+'_'+role
        self.groups[key].append((vertices,faces,part_id))
        self.parts.append(dict(id=part_id,source_feature_id=row['id'],parent_id=parent['id'],name=parent['tags'].get('name',''),source_osm_type=row['osm_type'],source_osm_id=row['osm_id'],
            osm_timestamp=row['timestamp'],source_url=f'https://www.openstreetmap.org/{row["osm_type"]}/{row["osm_id"]}',
            tags=row['tags'],role=role,shared_base=base,dimensions=source,
            source_footprint_area_m2=row['polygon'].area,bounds_min_m=np.min(vertices,axis=0).tolist(),bounds_max_m=np.max(vertices,axis=0).tolist(),
            material=material,group=key,mesh_checks=check,collision='none',accuracy_accepted=False))

    def ordinary(self,row):
        height,minimum,evidence=self.dimension(row);base=self.base(row)['height_m']
        if height<=minimum+.1:
            self.excluded.append(dict(id=row['id'],reason='Non-positive source vertical interval',height=height,min_height=minimum,tags=row['tags']));return
        shape=row['polygon']
        children=self.children.get(row['id'],[])
        role='Part' if 'building:part' in row['tags'] else 'Building'
        if children:
            shape=shape.difference(shapely.union_all([c['polygon'] for c in children]))
            child_heights=[self.dimension(c)[0] for c in children]
            low=[h for h in child_heights if h<=self.cfg['podium_height_cap_m']]
            height=min(low) if low else min(height,self.cfg['podium_height_cap_m'])
            evidence=dict(method='Parent residual podium only; never fill child outlines to tower maximum',height_m=height,
                excluded_child_count=len(children),podium_height_estimated=True)
            role='ResidualPodium'
        for i,p in enumerate(shapely.get_parts(shape)):
            if p.geom_type!='Polygon' or p.area<1:continue
            # Small source kink cleanup below1mm avoids zero-area wall faces.
            p=p.simplify(.001,preserve_topology=True)
            try:
                v,f=extrusion(p,base+minimum,base+height)
                self.add(row,role+str(i),v,f,evidence)
            except (ValueError,KeyError) as error:
                self.excluded.append(dict(id=row['id'],role=role+str(i),reason=str(error),area_m2=p.area,
                    status='This fragment is excluded. Other parts of this feature can remain.'))

    def harbour_mast(self):
        # One OSM roof interval is contradictory (160m top, 161m bottom).
        # Do not swap those values. Retain the valid 167-168m cap and connect
        # it to the source 156m deck with a separately recorded thin mast.
        row=self.by_id['way_363433264_0'];base=self.base(row)['height_m']
        center=row['polygon'].centroid
        width=self.cfg['harbour_centre']['mast_diameter_estimate_m']
        poly=center.buffer(width/2,quad_segs=4)
        v,f=extrusion(poly,base+156,base+167)
        self.add(row,'EstimatedMast',v,f,dict(method='Explicit estimated connector from valid OSM deck to cap',
            lower_height_m=156,upper_height_m=167,diameter_m=width,
            evidence='SEABC2017 PDF page27 shows a thin central mast; OSM valid deck/cap provide end heights',
            excluded_contradictory_source='way_363433263_0'),'light')

    def stack(self,row):
        cfg=self.cfg['stack'];base=self.base(row)['height_m'];rect=row['polygon'].minimum_rotated_rectangle
        for i,(lo,hi) in enumerate(zip(cfg['box_height_boundaries_m'],cfg['box_height_boundaries_m'][1:])):
            scale=cfg['box_scale_xy'][i];p=affinity.scale(rect,scale[0],scale[1],origin='centroid')
            p=affinity.rotate(p,cfg['box_rotation_deg'][i],origin='centroid').intersection(row['polygon'])
            v,f=extrusion(p,base+lo,base+hi)
            self.add(row,'Box'+str(i+1),v,f,dict(cfg,method='Four photo-informed box forms inside current OSM envelope',vertical_interval_m=[lo,hi]),'glass')

    def alberni(self,row):
        cfg=self.cfg['alberni'];base=self.base(row)['height_m'];center,axes,size=rectangle_axes(row['polygon'])
        # The visible large cut occupies the lower/middle body; the upper body
        # returns to its full width. Opposite cut and all depths are estimates.
        rows=[]
        for fraction in np.linspace(0,1,cfg['profile_levels']):
            cuts=[]
            for depth,c,h in zip(cfg['scoop_depth_fractions'],cfg['scoop_center_height_fractions'],cfg['scoop_half_height_fractions']):
                q=(fraction-c)/h;cuts.append(depth*size[0]*np.sqrt(max(0,1-q*q)))
            a,b=-size[0]/2+cuts[0],size[0]/2-cuts[1]
            for_z=np.array([[a,-size[1]/2],[b,-size[1]/2],[b,size[1]/2],[a,size[1]/2]])
            rows.append(np.column_stack((center+for_z@axes,np.full(4,base+fraction*cfg['height_m']))))
        v,f=ring_solid(rows);self.add(row,'CurvedBody',v,f,dict(cfg,method='Photo-informed coarse two-scoop profile; editable estimate'), 'light')

    def sail(self,row):
        cfg=self.cfg['canada_place'];center,axes,size=rectangle_axes(row['polygon'])
        candidates=[]
        for i in self.heights.tree.query(row['polygon'],predicate='intersects'):
            ref=self.heights.city[i];p=ref['properties'];top=p.get('topelev_m')
            if top is not None and 30<float(top)<50 and ref['polygon'].intersection(row['polygon']).area>row['polygon'].area*.1:
                candidates.append(dict(city_polygon_id=p['id'],top_cgvd28_m=float(top),overlap_m2=ref['polygon'].intersection(row['polygon']).area))
        high=max((r['top_cgvd28_m'] for r in candidates),default=cfg['sail_high_fallback_cgvd28_m'])
        correction=float(self.geoid.correction([center[0]+489600],[center[1]+5461100])[0])
        low=cfg['sail_low_cgvd28_m']+correction;high+=correction
        boundary=np.asarray(row['polygon'].exterior.coords)[:-1,:2]
        long_coordinate=(boundary-center)@axes[0]
        peaks=boundary[[np.argmin(long_coordinate),np.argmax(long_coordinate)]]
        def z(xy):
            distances=np.linalg.norm(xy[:,None,:]-peaks[None,:,:],axis=2)
            profile=np.max(np.clip(1-distances/size[0],0,1)**2.6,axis=1)
            return low+(high-low)*profile
        v,f=fabric_surface(row['polygon'],z,cfg['membrane_grid_m'])
        self.add(row,'TensionMembrane',v,f,dict(method='Current OSM sail boundary; photo-informed tension surface estimate',
            low_cgvd2013_m=low,peak_cgvd2013_m=high,peak_xy_local_m=peaks.tolist(),geoid_shift_m=correction,city2009_matches=candidates,
            datum_and_shape_limits=cfg['vertical_basis']+' '+cfg['shape_basis']), 'sail',closed=False)

    def build(self):
        for row in self.rows:
            park_overlap=row['polygon'].intersection(self.park).area/row['polygon'].area
            if park_overlap>.5:
                self.excluded.append(dict(id=row['id'],name=row['tags'].get('name',''),
                    reason='Foreground park building belongs to measured park cover/named assets, not distant skyline',
                    park_overlap_fraction=park_overlap,status='Duplicate skyline envelope withheld'))
                continue
            try:
                if row['osm_id']==self.cfg['stack']['osm_id']:self.stack(row)
                elif row['osm_id']==self.cfg['alberni']['osm_id']:self.alberni(row)
                elif row['tags'].get('building:material')=='fabric':self.sail(row)
                else:self.ordinary(row)
            except (ValueError,KeyError) as error:
                self.excluded.append(dict(id=row['id'],name=row['tags'].get('name',''),reason=str(error),status='Explicit unresolved part; not silently substituted'))
        self.harbour_mast()
        meshes=[]
        for key,parts in self.groups.items():
            vertices=[];faces=[];ranges=[]
            for v,f,part_id in parts:
                first=len(faces);faces.extend(f+len(vertices));vertices.extend(v)
                ranges.append(dict(part_id=part_id,first_triangle=first,triangle_count=len(f)))
            v=np.asarray(vertices);f=np.asarray(faces,dtype=np.int32);anchor=np.r_[np.floor(v[:,:2].mean(0)/100)*100,0.]
            name='SM_Skyline_'+key.replace('-','n');path=OUT/(name+'.npz')
            np.savez_compressed(path,vertices=v-anchor,faces=f,anchor=anchor)
            material=key.rsplit('_',1)[1]
            meshes.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=sha(path.relative_to(ROOT)),
                vertices=len(v),triangles=len(f),color=COLORS[material],material=material,two_sided=material=='sail',
                collision='none',parts=ranges,bounds_min_m=v.min(0).tolist(),bounds_max_m=v.max(0).tolist()))
        acquisition=json.loads((ROOT/'manifests/skyline-source-acquisition.json').read_text())
        inputs=[dict(path=r['path'].replace('\\','/'),sha256=r['sha256']) for r in acquisition['files']]
        inputs.extend(dict(path=p,sha256=sha(p)) for p in ['manifests/skyline-authoring-settings.json','manifests/skyline-reference-sources.json','manifests/world-origin.json',
            'data/derived/terrain_2022_park.npz','data/derived/terrain_surroundings.npz','data/derived/park_boundary.geojson',
            'data/raw/geoid/HTMVBC00_Abb.byn','data/raw/geoid/ca_nrc_CGG2013an83.tif'])
        sail_count=sum(p['role']=='TensionMembrane' for p in self.parts)
        if sail_count!=5:raise ValueError(f'Expected five Canada Place sails; built {sail_count}')
        produced={p['source_feature_id'] for p in self.parts};excluded={r['id'] for r in self.excluded}
        suppressed=[dict(id=r['id'],reason='Parent outline fully covered by current parts; no full-height duplicate mass')
            for r in self.rows if r['id'] not in produced|excluded and self.children.get(r['id'])]
        unaccounted=[r['id'] for r in self.rows if r['id'] not in produced|excluded|{s['id'] for s in suppressed}]
        if unaccounted:raise ValueError(f'Unaccounted skyline source records: {unaccounted}')
        result=dict(schema_version=1,scope='M1 downtown/West End distant silhouette; no facades, interiors or city simulation',
            inputs=inputs,meshes=meshes,parts=self.parts,excluded=self.excluded,suppressed_parent_outlines=suppressed,
            check_summary=dict(source_features=len(self.rows),authored_parts=len(self.parts),meshes=len(meshes),
                triangles=sum(m['triangles'] for m in meshes),excluded_parts=len(self.excluded),suppressed_parent_outlines=len(suppressed),canada_place_sails=sail_count,
                dimension_methods=dict(Counter(p['dimensions']['method'] for p in self.parts))),
            attribution=['© OpenStreetMap contributors','Contains information licensed under the Open Government Licence - Vancouver.',
                         'Contains information licensed under the Open Government Licence - Canada.'],
            licence='ODbL1.0 for OSM-derived database; City and NRCan OGL data; original procedural mesh forms. Reference photographs/PDFs are not textures or distributed assets.',
            release_accepted=False,blender_visual_acceptance=False,runtime_view_acceptance=False,
            limitations=['Current OSM tags are not a survey. Historic height matches can be stale.',
                'Parent outlines are residual low podia and do not become full-height towers.',
                'Estimated floor spacing, terrain bases, sculptural profiles, roof simplifications and exclusions need later art/survey review.'])
        (ROOT/'manifests/skyline-blockouts.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result['check_summary']))


if __name__=='__main__':SkylineBuilder().build()
