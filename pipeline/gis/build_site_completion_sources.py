"""Bounded named ground forms and honest links to existing terrain/cover."""
import json
import xml.etree.ElementTree as ET
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, box, shape, mapping
from pyproj import Transformer
from build_public_space_meshes import ROOT,digest,save

OUT=ROOT/'data/derived/site-completions'
RAW=ROOT/'data/routes/raw/osm/park-map-20260927.osm'
MAP='https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf'


def main():
    xml=ET.parse(RAW).getroot();nodes={int(n.get('id')):(float(n.get('lon')),float(n.get('lat')))for n in xml.findall('node')}
    ways={int(w.get('id')):w for w in xml.findall('way')};project=Transformer.from_crs(4326,3157,always_xy=True)
    features=[];inputs=[RAW];links=[]
    def way_geometry(wid):
        w=ways[wid];ll=np.array([nodes[int(n.get('ref'))]for n in w.findall('nd')]);e,n=project.transform(ll[:,0],ll[:,1]);xy=np.c_[e-489600,n-5461100]
        return (Polygon(xy) if np.allclose(xy[0],xy[-1])else LineString(xy)),dict(type='OSM source geometry',way_id=wid,url=f'https://www.openstreetmap.org/way/{wid}',timestamp=w.get('timestamp'),licence='ODbL-1.0')
    def add(cid,fid,group,role,geom,source,**extra):
        if not geom.is_valid or geom.is_empty:raise ValueError(cid)
        features.append(dict(type='Feature',properties=dict(component_id=cid,feature_id=fid,m1_group=group,material_role=role,source=source,
            priority=30,surveyed_boundary=False,absolute_accuracy_accepted=False,**extra),geometry=mapping(geom)))
    def pick(cid,fid,group,role,name,pixels,display_size=None,**extra):
        p=ROOT/f'evidence/corridor/ortho-utm/{name}.json';m=json.loads(p.read_text());b=m['local_bounds_m'];size=display_size or m['image_size']
        for f in [p,p.with_suffix('.png')]:
            if f not in inputs:inputs.append(f)
        geom=Polygon([(b[0]+x/size[0]*(b[2]-b[0]),b[3]-y/size[1]*(b[3]-b[1]))for x,y in pixels])
        add(cid,fid,group,role,geom,dict(type='Coarse visible image trace',metadata=p.relative_to(ROOT).as_posix(),image_sha256=digest(p.with_suffix('.png')),
            capture_period=m['capture_period'],pixels=pixels,picked_display_size=size,licence='OGL Vancouver'),**extra)
        return geom
    devonian,src=way_geometry(37056115)
    parking=[];parking_ids=[]
    for wid,w in ways.items():
        tags={t.get('k'):t.get('v')for t in w.findall('tag')}
        if tags.get('amenity')!='parking':continue
        geom,_=way_geometry(wid)
        if geom.geom_type=='Polygon' and geom.intersects(devonian):parking.append(geom);parking_ids.append(wid)
    devonian_ground=devonian.difference(shapely.union_all(parking))
    src={**src,'original_park_geometry':mapping(devonian),'excluded_parking_way_ids':parking_ids}
    add('DevonianParkGround','SP_devonian','M1-F11','public_lawn',devonian_ground,src,priority_override=90,
        limit='Park envelope with roads, paths, buildings and pond removed. Canopy and current measured terrain remain; no blanket tree removal or city simulation.')
    for wid,name,fid,group,survey in [(5405086,'DevonianPond','SP_devonian','M1-F11','devonian-pond'),(1170395077,'SalmonLowerPool','SP_salmon_stream','M1-F10','salmon-lower-pool')]:
        geom,src=way_geometry(wid);p=ROOT/f'data/derived/named-{survey}-survey.npz';inputs.append(p)
        with np.load(p)as d:q=d['xyz'];c=d['classification']
        inner=shapely.contains_xy(geom.buffer(-2),q[:,0],q[:,1]);classified=q[inner&(c==9),2];ground=q[inner&(c==2),2]
        level=float(np.median(classified))if len(classified)>=20 else float(np.percentile(ground,35))
        add(name,fid,group,'pond_water',geom,src,water_mask=False,water_z=level,priority_override=15,
            height_evidence=dict(class9_count=len(classified),class2_count=len(ground),class2_p05_p50_p95=np.percentile(ground,[5,50,95]).tolist(),
                datum='CGVD2013',survey_path=p.relative_to(ROOT).as_posix(),height_is_measured_water=len(classified)>=20,
                method='Class9 median'if len(classified)>=20 else 'Unmeasured water-level proxy from class2 interior 35th percentile'),
            limit='Source pond boundary, flight-period survey context. No hydraulic or current water-state claim. Render only where current terrain lies below this proxy.')
        add(name+'_BasinGround',fid,group,'stream_bed',geom,src,source_basin_underlay=True,priority_override=95,
            limit='Complete source basin footprint draped on coarse current terrain. This is a ground-space blockout, not a surveyed basin floor or a flat operating water surface. The partial proxy-water mesh stays separate.')
    pick('PaintersCircleCourt','SP_painters_circle','M1-F09','public_concrete','m1-painters-stream',
        [(832,1000),(859,1000),(876,1017),(876,1045),(858,1063),(831,1061),(813,1042),(813,1019)],[1600,1600],
        limit='Finite central paved meeting circle from official inset B and 2022 image. Artist stalls, art and occupancy are not added.')
    pick('PortraitPaintersGround','SP_portrait_painters','M1-F09','public_lawn','m1-painters-stream',
        [(1100,340),(1150,333),(1207,350),(1230,382),(1220,429),(1200,458),(1156,470),(1108,455),(1066,430),(1037,408),(1015,384),(1026,352),(1056,340)],[1600,1600],
        limit='Visible lawn/tree island within the public paths south of Aquarium. Existing walking surfaces remain separate. Official map location is approximate; this is not a licensed vending boundary or an interior exhibit.')
    # Source OSM channel pieces remain exact; gaps under canopy use a stated, finite trace estimate.
    for wid in [1495282021,1495282022]:
        geom,src=way_geometry(wid);add('SalmonChannel_'+str(wid),'SP_salmon_stream','M1-F10','stream_bed',geom.buffer(.8),src,
            limit='1.6 m visible coarse channel width is estimated. Culvert segments are not painted across paths.')
    centreline=[[812.4,-339.9],[821,-354],[830,-367],[836,-391],[846,-413],[854,-432],[860,-444]]
    lower=[[863,-466],[860,-481],[861,-496],[866,-511],[867,-526]]
    for name,line in [('Middle',centreline),('OutletApproach',lower)]:
        add('SalmonChannel_'+name,'SP_salmon_stream','M1-F10','stream_bed',LineString(line).buffer(.9),
            dict(type='Approximate canopy-occluded channel trace',primary_map=MAP,map_revision='2026-05-19',
                primary_description='https://stanleyparkecology.ca/wp-content/uploads/2021/07/SOPEI-Full-2010.pdf',source_page=80,
                image='evidence/corridor/ortho-utm/m1-painters-stream.json',coordinates_local_m=line,licence='Project estimate from reference context'),
            limit='Inferred short channel continuation joining visible/source water. 1.8 m width is a blockout estimate. Existing crossing pavements are retained; buried outlet and fish-ladder detail are later work.')
    pick('WaterParkBoatPad','SP_water_park','M1-F05','play_rubber','m1-waterpark',[(723,724),(838,724),(838,801),(723,801)],
        internal_play_surface=True,limit='Visible internal dark play-surface rectangle, layered 0.025 m above the prior pad for a total0.045m terrain display lift.')
    pick('PortViewPlatform','SP_port_view','M1-F11','public_concrete','m1-port-view',
        [(434,516),(454,519),(474,514),(496,511),(516,516),(534,531),(543,548),(540,563),(528,576),(508,581),(489,576),(474,561),(452,558)],
        limit='Visible semicircular seawall projection. Actual terrain supplies Z; no independent wall/deck thickness is inferred.')
    # These forms already exist. Their source-linked extents are reference selections, not added monuments.
    selections=[
        ('SP_heron_colony',box(-265,-1290,-80,-1145),'City identifies current colony around Park Lane and Park Board office tennis trees. No exact nest census or individual nesting-tree claim.',
         ['https://vancouver.ca/parks-recreation-culture/history-of-herons-in-stanley-park.aspx','https://vancouver.ca/news-calendar/stanley-park-herons-return-to-raise-next-generation.aspx']),
        ('SP_hallelujah',box(1650,-530,1815,-420),'Finite south Brockton shore/grass/canopy site. Bounds select existing landforms; they are not a survey boundary.',[MAP,'https://vancouver.ca/parks-recreation-culture/monuments-and-sculptures.aspx']),
        ('SP_port_view',box(1905,-281,1952,-227),'Port viewpoint is the visible semicircular seawall projection south of Brockton lighthouse. Surrounding landform links retain existing terrain and walking surface.',[MAP,'evidence/corridor/ortho-utm/m1-port-view.json']),
        ('SP_rock_garden',box(650,-389,712,-337),'Finite Pavilion-south garden context from City map and adjacent source beds. This links existing terrain, canopy and garden beds; no invented rock monument.',[MAP,'https://vancouver.ca/parks-recreation-culture/gardens-in-stanley-park.aspx']),
        ('SP_devonian',devonian,'City park identity and OSM boundary; existing path/shore/cover geometry retained.', ['https://covapp.vancouver.ca/parkfinder/parkdetail.aspx?inparkid=18']),
    ]
    cover_path=ROOT/'data/derived/cover-blockout.json';surface_path=ROOT/'manifests/surface-model.json';inputs.extend([cover_path,surface_path])
    cover=json.loads(cover_path.read_text());surface=json.loads(surface_path.read_text())
    for fid,region,limit,refs in selections:
        terrain=[]
        for row in surface['terrain']:
            with np.load(ROOT/row['path'])as d:v=d['vertices']+d['anchor'];tri=v[d['faces'],:2]
            polys=shapely.polygons(tri);hit=shapely.intersects(polys,region);area=float(shapely.area(shapely.intersection(polys[hit],region)).sum())
            if area>1e-6:terrain.append(dict(name=row['name'],path=row['path'],sha256=row['sha256'],selected_area_m2=area))
        canopy=[]
        for tile in cover['canopy']:
            if not tile['points']:continue
            points=np.array(tile['points']);hit=shapely.contains_xy(region,points[:,0],points[:,1]);indices=np.flatnonzero(hit)
            if len(indices):canopy.append(dict(name='SM_Canopy_'+tile['tile'].split('_',1)[1],cover_tile=tile['tile'],point_indices=indices.tolist(),cluster_count=len(indices)))
        links.append(dict(feature_id=fid,selection_geometry=mapping(region),selection_is_surveyed_boundary=False,
            existing_terrain=terrain,existing_canopy=canopy,source_urls=refs,source_date='City map May19 2026; imagery/survey2022; primary pages read2026-09-27',
            limit=limit,rendered_geometry_reused=True,live_visual_acceptance=False))
    club,src=way_geometry(722554183)
    candidates=[]
    for b in cover['buildings']:
        footprint=Polygon(b['outline']);overlap=footprint.intersection(club).area
        if overlap>0:candidates.append(dict(cover_id=b['id'],intersection_m2=overlap,source_footprint_fraction=overlap/club.area,
            object_name='SM_BuildingMass_'+'_'.join(b['id'].split('_')[:3]),base_m=b['base_m'],roof_m=b['roof_m']))
    links.append(dict(feature_id='SP_pitch_putt',part='Rental/ticket clubhouse',source=src,source_geometry=mapping(club),existing_building_candidates=candidates,
        primary_url='https://vancouver.ca/parks-recreation-culture/stanley-park-pitch-putt.aspx',image_reference='evidence/ground-spaces/heron-golf-source-crop.png',
        limit='OSM named retail footprint and visible2022roof agree with measured park cover. No skyline duplicate or interior is used.',live_visual_acceptance=False))
    for f in features:
        p=f['properties']
        if 'priority_override'in p:p['priority']=p.pop('priority_override')
    save(OUT/'site-completions-local.geojson',dict(type='FeatureCollection',features=features))
    save(ROOT/'manifests/site-completion-sources.json',dict(schema_version=1,authoring_geometry='data/derived/site-completions/site-completions-local.geojson',
        source_inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p))for p in inputs],references=[],unresolved=[],
        source_period='City2022 survey/images; OSM September27 2026 snapshot; official map May19 2026',
        licence='OSM ODbL-1.0, City survey/ortho derivatives OGL Vancouver; project estimates explicitly labelled',
        source_links=links,application_visual_check='pending',full_m1_groups_complete=False))
    save(ROOT/'manifests/m1-existing-site-linkage.json',dict(schema_version=1,links=links,source_inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p))for p in [cover_path,surface_path]],
        purpose='Link actual existing land/cover to named M1 sites; not extra geometry or accepted visual evidence'))
    print(json.dumps(dict(ground_components=len(features),existing_site_links=len(links),clubhouse_candidates=candidates)))


if __name__=='__main__':main()
