"""Build seven bounded industrial silhouettes from current source geometry."""
from collections import Counter,defaultdict
import hashlib,json
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon,LineString,box,mapping
from northshore_source_geometry import read_sources
from northshore_meshes import axes,beam,silo,gable
from skyline_meshes import extrusion,validate
from skyline_height_sources import HeightSources,metres

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/derived/northshore'
COLORS={'light':[.68,.69,.66,1.],'steel':[.4,.46,.49,1.],'shed':[.31,.43,.5,1.],
        'blue':[.035,.19,.47,1.],'red':[.52,.24,.17,1.]}


def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


class Builder:
    def __init__(self):
        self.cfg=json.loads((ROOT/'manifests/northshore-authoring-settings.json').read_text())
        self.rows,self.sites,self.source_failures=read_sources();self.heights=HeightSources(ROOT)
        self.bases={k:self.heights.base(max(shapely.get_parts(v['geometry']),key=lambda p:p.area)) for k,v in self.sites.items()}
        self.groups=defaultdict(list);self.parts=[];self.excluded=[];OUT.mkdir(parents=True,exist_ok=True)
        origin=json.loads((ROOT/'manifests/world-origin.json').read_text())
        assert [origin['easting'],origin['northing'],origin['height']]==[489600,5461100,0]

    def add(self,site,row,role,vertices,faces,material,evidence):
        check=validate(vertices,faces);key=site+'_'+material;pid=site+'_'+row['id']+'_'+role
        self.groups[key].append((vertices,faces,pid))
        self.parts.append(dict(id=pid,site=site,source_feature_id=row['id'],source_url=row['source_url'],
            source_timestamp=row['timestamp'],source_tags=row['tags'],source_bounds_xy_m=list(row['geometry'].bounds),
            role=role,dimensions=evidence,shared_base=self.bases[site],group=key,material=material,
            bounds_min_m=np.min(vertices,axis=0).tolist(),bounds_max_m=np.max(vertices,axis=0).tolist(),
            geometry_checks=check,collision='none',accuracy_accepted=False))

    def solid(self,site,row,role,poly,height,material='steel',basis='Explicit M1 height estimate',minimum=0):
        base=self.bases[site]['height_m'];v,f=extrusion(poly,base+minimum,base+height)
        self.add(site,row,role,v,f,material,dict(height_m=height,min_height_m=minimum,basis=basis))

    def girder(self,site,row,role,a,b,width,depth,material='steel',basis='Current mapped XY; estimated section and height'):
        v,f=beam(a,b,width,depth);self.add(site,row,role,v,f,material,dict(basis=basis,width_m=width,depth_m=depth))

    def gantry(self,row):
        site='Seaspan';c=self.cfg['sites'][site];base=self.bases[site]['height_m'];center,ab,size=axes(row['geometry'])
        # The OSM crane polygon is a travel envelope, not a solid crane body.
        center=center+ab[0]*size[0]*(c['parked_fraction_estimate']-.5)
        span=c['crane_width_m'];top=c['crane_height_m'];depth=c['girder_depth_estimate_m'];leg=c['leg_width_estimate_m']
        endpoints=[center+ab[1]*sign*(span/2-leg/2) for sign in [-1,1]]
        for end,xy in enumerate(endpoints):
            for sign in [-1,1]:
                foot=xy+ab[0]*sign*c['footprint_depth_estimate_m']/2
                self.girder(site,row,f'Leg{end}_{sign}',[*foot,base],[*xy,base+top-depth],leg,leg,'blue',c['height_status'])
        a=center-ab[1]*span/2;b=center+ab[1]*span/2
        self.girder(site,row,'MainGirder',[*a,base+top-depth/2],[*b,base+top-depth/2],c['girder_thickness_estimate_m'],depth,'blue',c['height_status'])
        # One simple hoist line preserves the open gantry; no machinery motion.
        self.girder(site,row,'Hoist',[*center,base+top-depth],[*center,base+35],.45,.45,'steel','Estimated static hoist pose')

    def richardson(self,row):
        site='Richardson';c=self.cfg['sites'][site];poly=row['geometry'];lo=poly.bounds[0];hi=poly.bounds[2]
        cut=hi-(hi-lo)*c['workhouse_east_fraction_estimate'];tower=poly.intersection(box(cut,-1e5,1e5,1e5)).simplify(.001,preserve_topology=True);storage=poly.intersection(box(-1e5,-1e5,cut,1e5)).simplify(.001,preserve_topology=True)
        self.solid(site,row,'OldStorage',storage,c['old_storage_m'],'red',c['height_status'])
        self.solid(site,row,'WorkhouseLower',tower,58,'red','Estimated two-colour division within source73m workhouse height')
        self.solid(site,row,'WorkhouseTop',tower,c['workhouse_m'],'light',c['height_status'],minimum=58)

    def loaders(self,row):
        site='G3';c=self.cfg['sites'][site];base=self.bases[site]['height_m'];center,ab,size=axes(row['geometry'])
        sea=ab[1] if ab[1][1]<0 else -ab[1]
        for i,fraction in enumerate(c['loader_positions_estimate']):
            pos=center+ab[0]*size[0]*(fraction-.5);mast=c['loader_mast_estimate_m']
            for sign in [-1,1]:
                foot=pos+ab[0]*sign*4
                self.girder(site,row,f'Loader{i}_Leg{sign}',[*foot,base],[*foot,base+22],1.7,1.7)
            self.girder(site,row,f'Loader{i}_Cross',*(np.r_[pos+ab[0]*sign*4,base+22] for sign in [-1,1]),2.5,2.5)
            self.girder(site,row,f'Loader{i}_Mast',[*pos,base+22],[*pos,base+mast],3,3)
            tip=pos+sea*c['loader_boom_estimate_m']
            self.girder(site,row,f'Loader{i}_Boom',[*pos,base+mast],[*tip,base+23],3,3,
                basis='Three loaders documented by supplier. Static positions along current mapped pier and member dimensions are M1 estimates.')
            self.girder(site,row,f'Loader{i}_Chute',[*tip,base+23],[*tip,base+12],1.4,1.4)

    def generate(self,site,row):
        tags=row['tags'];poly=row['geometry'];c=self.cfg['sites'][site];base=self.bases[site]['height_m']
        if tags.get('man_made')=='crane':self.gantry(row);return
        if site=='Richardson' and row['id']==c['old_storage_way']:self.richardson(row);return
        if tags.get('man_made')=='goods_conveyor':
            q=np.asarray(poly.coords);height=self.cfg['generic_conveyor_height_estimate_m']
            if site=='Richardson':height=52
            if site=='G3' and poly.distance(self.g3_silos)<6:height=c['gallery_height_estimate_m']-1.25
            for i,(a,b) in enumerate(zip(q,q[1:])):
                if np.linalg.norm(b-a)<.1:continue
                self.girder(site,row,'Conveyor'+str(i),[*a,base+height],[*b,base+height],self.cfg['conveyor_width_estimate_m'],self.cfg['conveyor_depth_estimate_m'])
            return
        if tags.get('man_made')=='pier':
            self.solid(site,row,'PierDeck',poly,0,'steel','Source pier footprint; estimated0.8m deck depth',minimum=-.8)
            if site=='G3':self.loaders(row)
            return
        if tags.get('man_made')=='silo':
            body=self.cfg['generic_silo_height_estimate_m'];roof=0.;basis='Mapped source silo footprint; explicit M1 height estimate'
            if site=='Fibreco':
                prefix='pellet' if poly.centroid.y>1200 else 'grain';body=c[prefix+'_silo_body_m'];roof=c[prefix+'_silo_roof_m'];basis=c['height_status']
            elif site=='Richardson':body=c['annex_m'];basis=c['height_status']
            elif site=='Cargill':body=c['silo_body_estimate_m'];basis=c['height_status']
            elif site=='G3':body=c['silo_body_m'];basis=c['height_status']
            v,f=silo(poly,base,body,roof) if roof else extrusion(poly,base,base+body)
            self.add(site,row,'Silo',v,f,'light',dict(body_height_m=body,roof_height_m=roof,basis=basis));return
        if tags.get('man_made')=='storage_tank':
            self.solid(site,row,'Tank',poly,self.cfg['generic_tank_height_estimate_m'],'light');return
        if site=='G3' and row['id']==c['cleaning_tower_way']:
            self.solid(site,row,'CleaningTower',poly,c['cleaning_tower_m'],'light',c['height_status']);return
        if site=='Cargill' and row['id']==c['workhouse_way']:
            self.solid(site,row,'WorkhouseEstimate',poly,c['workhouse_height_estimate_m'],'light',c['height_status']);return
        shed=(site=='Neptune' and row['id'] in c['shed_ways']) or (site in ['VancouverWharves','Fibreco'] and poly.area>2000)
        if shed:
            eave=c.get('shed_eave_m',c.get('shed_eave_estimate_m'));ridge=c.get('shed_ridge_m',c.get('shed_ridge_estimate_m'))
            for i,(v,f) in enumerate(gable(poly,base,eave,ridge)):
                self.add(site,row,'Shed'+str(i),v,f,'shed',dict(eave_height_m=eave,ridge_height_m=ridge,basis=c['height_status']))
            return
        height=metres(tags.get('height')) or self.cfg['generic_building_height_estimate_m']
        if site=='Seaspan' and poly.area>4000:height=c['large_shop_height_estimate_m']
        if site=='Cargill' and poly.area>1500:height=45
        # Mapped enclosing polygons must not cover adjacent circular silo forms.
        shape=poly.difference(self.silos_by_site[site])
        for i,p in enumerate(shapely.get_parts(shape)):
            if p.geom_type=='Polygon' and p.area>1:self.solid(site,row,'Building'+str(i),p,height)

    def build(self):
        selected=[]
        for row in self.rows.values():
            g=row['geometry'];t=row['tags'];kind=t.get('man_made');is_building='building' in t or 'building:part' in t
            if not is_building and kind not in ['silo','storage_tank','crane','goods_conveyor','pier']:continue
            hits=[k for k,s in self.sites.items() if s['geometry'].covers(g.representative_point())]
            if not hits:continue
            site=min(hits,key=lambda k:self.sites[k]['geometry'].area)
            if g.geom_type=='Polygon' and g.area<self.cfg['minimum_generic_building_area_m2'] and kind not in ['silo','storage_tank']:continue
            if g.geom_type=='LineString' and (kind!='goods_conveyor' or g.length<40):continue
            if g.geom_type not in ['Polygon','LineString']:continue
            if kind=='crane' and row['id']!='way_1168344141':continue
            selected.append((site,row))
        self.silos_by_site={k:shapely.union_all([r['geometry'] for site,r in selected if site==k and r['tags'].get('man_made')=='silo']) for k in self.sites}
        self.g3_silos=self.silos_by_site['G3']
        for site,row in selected:
            try:self.generate(site,row)
            except (ValueError,KeyError) as exc:self.excluded.append(dict(site=site,id=row['id'],error=str(exc)))
        meshes=[]
        for key,parts in self.groups.items():
            vertices=[];faces=[];ranges=[]
            for v,f,pid in parts:
                start=len(faces);faces.extend(f+len(vertices));vertices.extend(v)
                ranges.append(dict(part_id=pid,first_triangle=start,triangle_count=len(f)))
            v=np.asarray(vertices);f=np.asarray(faces,dtype=np.int32);anchor=np.r_[np.floor(v[:,:2].mean(0)/100)*100,0.]
            name='SM_NorthShore_'+key;path=OUT/(name+'.npz');np.savez_compressed(path,vertices=v-anchor,faces=f,anchor=anchor)
            material=key.rsplit('_',1)[1]
            meshes.append(dict(name=name,path=path.relative_to(ROOT).as_posix(),sha256=sha(path.relative_to(ROOT)),parts=ranges,
                vertices=len(v),triangles=len(f),material=material,color=COLORS[material],collision='none',two_sided=False))
        acquisition=json.loads((ROOT/'manifests/northshore-source-acquisition.json').read_text())
        inputs=[dict(path=r['path'].replace('\\','/'),sha256=r['sha256']) for r in acquisition['files'] if r['status']=='saved' and r['path'].endswith('.osm')]
        for p in ['manifests/world-origin.json','manifests/northshore-authoring-settings.json','manifests/northshore-reference-sources.json','data/derived/terrain_2022_park.npz','data/derived/terrain_surroundings.npz']:
            inputs.append(dict(path=p,sha256=sha(p)))
        counts=Counter(p['site'] for p in self.parts);silos=Counter(p['site'] for p in self.parts if p['role']=='Silo')
        assert silos['G3']==48 and silos['Fibreco']==21 and len(counts)==7
        result=dict(schema_version=1,scope=self.cfg['scope'],inputs=inputs,meshes=meshes,parts=self.parts,excluded=self.excluded,
            sites=[dict(id=k,source_id=s['id'],source_url=s['source_url'],source_timestamp=s['timestamp'],bounds_xy_m=list(s['geometry'].bounds),base=self.bases[k]) for k,s in self.sites.items()],
            source_relation_failures=[x for x in self.source_failures if x['id'] in [s['id'] for s in self.sites.values()]],
            check_summary=dict(sites=len(counts),parts=len(self.parts),meshes=len(meshes),triangles=sum(m['triangles'] for m in meshes),parts_by_site=dict(counts),silos_by_site=dict(silos)),
            limitations=['M1 distant silhouettes only; coarse dimensions and moving-machine poses are recorded estimates.',
                'G3 height-source conflict retained. Neptune B2 replacement equipment, variable stockpiles, vehicles, ships and minor terminal fixtures are excluded.',
                'Shared80m terrain-derived terminal bases are not surveyed wharf levels. No public access or collision is supplied.'],
            licence='OSM-derived database ODbL-1.0; existing terrain OGL-Canada; primary reference documents not distributed assets',
            attribution=['OpenStreetMap contributors','Contains information licensed under the Open Government Licence - Canada.'],
            blender_visual_acceptance=False,runtime_view_acceptance=False,release_accepted=False)
        (ROOT/'manifests/northshore-blockouts.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
        bounds=dict(type='FeatureCollection',features=[dict(type='Feature',properties=dict(site=k,source_id=s['id']),geometry=mapping(s['geometry'])) for k,s in self.sites.items()])
        (OUT/'source-site-bounds-local.geojson').write_text(json.dumps(bounds,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result['check_summary']));print('excluded',json.dumps(self.excluded))


if __name__=='__main__':Builder().build()
